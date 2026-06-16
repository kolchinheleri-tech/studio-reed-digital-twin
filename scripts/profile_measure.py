from __future__ import annotations

from pathlib import Path
import argparse
import numpy as np
import pandas as pd
import trimesh
from scipy.signal import find_peaks

SUPPORTED_EXTENSIONS = {".glb", ".gltf", ".obj", ".stl", ".ply"}


def load_mesh(path: Path) -> trimesh.Trimesh:
    loaded = trimesh.load(path, force=None)

    if isinstance(loaded, trimesh.Scene):
        meshes = [g for g in loaded.geometry.values() if isinstance(g, trimesh.Trimesh)]
        if not meshes:
            raise ValueError(f"No mesh found in {path}")
        mesh = trimesh.util.concatenate(meshes)
    elif isinstance(loaded, trimesh.Trimesh):
        mesh = loaded
    else:
        raise TypeError(f"Unsupported file: {path}")

    mesh.remove_unreferenced_vertices()
    return mesh


def get_piece_id(path: Path, scans_dir: Path) -> str:
    if path.parent == scans_dir:
        return path.stem
    return path.parent.name


def moving_average(values: np.ndarray, window: int = 7) -> np.ndarray:
    if len(values) < window:
        return values
    kernel = np.ones(window) / window
    return np.convolve(values, kernel, mode="same")


def measure_profile(mesh: trimesh.Trimesh, scale_to_mm: float, expected_chamber_length_mm=None) -> dict:
    points = np.asarray(mesh.vertices, dtype=float) * scale_to_mm

    center = points.mean(axis=0)
    centered = points - center

    _, _, vh = np.linalg.svd(centered, full_matrices=False)
    axis = vh[0]

    projected = centered @ axis
    s_min = np.percentile(projected, 0.5)
    s_max = np.percentile(projected, 99.5)

    total_length = s_max - s_min

    radial_vectors = centered - np.outer(projected, axis)
    radial_distances = np.linalg.norm(radial_vectors, axis=1)

    bin_count = 220
    bins = np.linspace(s_min, s_max, bin_count + 1)
    centers = (bins[:-1] + bins[1:]) / 2

    radius_profile = []

    for i in range(bin_count):
        mask = (projected >= bins[i]) & (projected < bins[i + 1])
        values = radial_distances[mask]

        if len(values) < 5:
            radius_profile.append(np.nan)
        else:
            radius_profile.append(np.percentile(values, 55))

    radius_profile = np.array(radius_profile, dtype=float)

    valid = ~np.isnan(radius_profile)
    radius_profile[~valid] = np.interp(
        np.flatnonzero(~valid),
        np.flatnonzero(valid),
        radius_profile[valid]
    )

    smooth_radius = moving_average(radius_profile, window=9)

    prominence = max(np.std(smooth_radius) * 0.4, 0.5)
    peaks, properties = find_peaks(
        smooth_radius,
        distance=bin_count // 8,
        prominence=prominence
    )

    node_a = None
    node_b = None
    profile_status = "nodes_not_found"

    if len(peaks) >= 2:
        candidates = []

        for i in range(len(peaks)):
            for j in range(i + 1, len(peaks)):
                a = centers[peaks[i]] - s_min
                b = centers[peaks[j]] - s_min
                chamber = b - a

                if chamber <= 0:
                    continue

                if expected_chamber_length_mm:
                    score = abs(chamber - expected_chamber_length_mm)
                else:
                    score = -smooth_radius[peaks[i]] - smooth_radius[peaks[j]]

                candidates.append((score, a, b, chamber))

        if candidates:
            candidates.sort(key=lambda x: x[0])
            _, node_a, node_b, chamber_length = candidates[0]
            profile_status = "estimated"

    if node_a is None or node_b is None:
        if expected_chamber_length_mm:
            node_a = (total_length - expected_chamber_length_mm) / 2
            node_b = node_a + expected_chamber_length_mm
            chamber_length = expected_chamber_length_mm
            profile_status = "fallback_expected_chamber_centered"
        else:
            node_a = None
            node_b = None
            chamber_length = None

    if node_a is not None and node_b is not None:
        cut_position = (node_a + node_b) / 2
        left_tail = node_a
        right_tail = total_length - node_b

        cut_global = s_min + cut_position
        cut_window = total_length * 0.025

        cut_mask = np.abs(centers - cut_global) < cut_window

        if np.any(cut_mask):
            diameter_at_cut = float(np.nanmedian(smooth_radius[cut_mask]) * 2)
        else:
            diameter_at_cut = None

    else:
        cut_position = None
        left_tail = None
        right_tail = None
        diameter_at_cut = None

    return {
        "total_length_mm": round(float(total_length), 2),
        "node_a_mm": round(float(node_a), 2) if node_a is not None else None,
        "node_b_mm": round(float(node_b), 2) if node_b is not None else None,
        "chamber_length_mm": round(float(chamber_length), 2) if chamber_length is not None else None,
        "cut_position_mm": round(float(cut_position), 2) if cut_position is not None else None,
        "diameter_at_cut_mm": round(float(diameter_at_cut), 2) if diameter_at_cut is not None else None,
        "left_tail_length_mm": round(float(left_tail), 2) if left_tail is not None else None,
        "right_tail_length_mm": round(float(right_tail), 2) if right_tail is not None else None,
        "profile_status": profile_status,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scans", default="scans")
    parser.add_argument("--master", default="data/master.csv")
    parser.add_argument("--output", default="output")
    parser.add_argument("--scale", type=float, default=895.0)

    args = parser.parse_args()

    scans_dir = Path(args.scans)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    master = pd.read_csv(args.master)

    files = sorted(
        path for path in scans_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )

    rows = []

    for path in files:
        piece_id = get_piece_id(path, scans_dir)

        expected_row = master[master["piece_id"] == piece_id]

        expected_chamber = None
        if not expected_row.empty and "expected_chamber_length_mm" in master.columns:
            value = expected_row.iloc[0]["expected_chamber_length_mm"]
            if pd.notna(value):
                expected_chamber = float(value)

        try:
            mesh = load_mesh(path)
            result = measure_profile(mesh, args.scale, expected_chamber)

            rows.append({
                "piece_id": piece_id,
                "scan_file": str(path),
                **result,
                "error_message": "",
            })

        except Exception as exc:
            rows.append({
                "piece_id": piece_id,
                "scan_file": str(path),
                "total_length_mm": None,
                "node_a_mm": None,
                "node_b_mm": None,
                "chamber_length_mm": None,
                "cut_position_mm": None,
                "diameter_at_cut_mm": None,
                "left_tail_length_mm": None,
                "right_tail_length_mm": None,
                "profile_status": "error",
                "error_message": str(exc),
            })

    df = pd.DataFrame(rows)
    df.to_csv(output_dir / "profile_results.csv", index=False)

    print(df)
    print(f"\nSaved: {output_dir / 'profile_results.csv'}")


if __name__ == "__main__":
    main()