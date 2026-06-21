from __future__ import annotations

from pathlib import Path
import argparse

import numpy as np
import pandas as pd
import trimesh
from scipy.signal import find_peaks


SUPPORTED_EXTENSIONS = {".glb", ".gltf", ".obj", ".stl", ".ply"}

OUTPUT_COLUMNS = [
    "piece_id",
    "scan_file",
    "total_length_mm",
    "node_a_mm",
    "node_b_mm",
    "chamber_length_mm",
    "cut_position_mm",
    "diameter_at_cut_mm",
    "left_tail_length_mm",
    "right_tail_length_mm",
    "profile_status",
    "error_message",
]


def load_mesh(path: Path) -> trimesh.Trimesh:
    loaded = trimesh.load(path, force=None)

    if isinstance(loaded, trimesh.Scene):
        meshes = [
            geom for geom in loaded.geometry.values()
            if isinstance(geom, trimesh.Trimesh)
        ]
        if not meshes:
            raise ValueError(f"No mesh found in {path}")
        mesh = trimesh.util.concatenate(meshes)

    elif isinstance(loaded, trimesh.Trimesh):
        mesh = loaded

    else:
        raise TypeError(f"Unsupported file type: {path}")

    mesh.remove_unreferenced_vertices()
    return mesh


def get_piece_id(path: Path, scans_dir: Path) -> str:
    if path.parent == scans_dir:
        return path.stem
    return path.parent.name


def moving_average(values: np.ndarray, window: int = 11) -> np.ndarray:
    if len(values) < window:
        return values

    kernel = np.ones(window) / window
    return np.convolve(values, kernel, mode="same")


def build_axis_profile(
    mesh: trimesh.Trimesh,
    scale_to_mm: float,
    bin_count: int = 260,
) -> dict:
    points = np.asarray(mesh.vertices, dtype=float) * scale_to_mm

    center = points.mean(axis=0)
    centered = points - center

    _, _, vh = np.linalg.svd(centered, full_matrices=False)
    axis = vh[0]

    projected = centered @ axis

    s_min = np.percentile(projected, 0.5)
    s_max = np.percentile(projected, 99.5)

    total_length = float(s_max - s_min)

    radial_vectors = centered - np.outer(projected, axis)
    radial_distances = np.linalg.norm(radial_vectors, axis=1)

    bins = np.linspace(s_min, s_max, bin_count + 1)
    centers = (bins[:-1] + bins[1:]) / 2

    radius_profile = []

    for i in range(bin_count):
        mask = (projected >= bins[i]) & (projected < bins[i + 1])
        values = radial_distances[mask]

        if len(values) < 5:
            radius_profile.append(np.nan)
        else:
            radius_profile.append(np.percentile(values, 60))

    radius_profile = np.array(radius_profile, dtype=float)

    valid = ~np.isnan(radius_profile)

    if np.any(valid) and np.any(~valid):
        radius_profile[~valid] = np.interp(
            np.flatnonzero(~valid),
            np.flatnonzero(valid),
            radius_profile[valid],
        )

    if not np.any(valid):
        raise ValueError("Could not build valid radius profile")

    smooth_radius = moving_average(radius_profile, window=11)

    return {
        "total_length": total_length,
        "s_min": s_min,
        "s_max": s_max,
        "centers": centers,
        "smooth_radius": smooth_radius,
    }


def diameter_at_position(
    centers: np.ndarray,
    smooth_radius: np.ndarray,
    s_min: float,
    position_mm: float,
    total_length_mm: float,
) -> float | None:
    cut_global = s_min + position_mm
    cut_window = max(total_length_mm * 0.025, 8.0)

    mask = np.abs(centers - cut_global) < cut_window

    if not np.any(mask):
        return None

    diameter = float(np.nanmedian(smooth_radius[mask]) * 2)
    return diameter


def empty_result(total_length: float, status: str) -> dict:
    return {
        "total_length_mm": round(float(total_length), 2),
        "node_a_mm": None,
        "node_b_mm": None,
        "chamber_length_mm": None,
        "cut_position_mm": None,
        "diameter_at_cut_mm": None,
        "left_tail_length_mm": None,
        "right_tail_length_mm": None,
        "profile_status": status,
    }


def measure_with_expected_chamber(
    profile: dict,
    expected_chamber_length_mm: float,
) -> dict:
    total_length = profile["total_length"]
    s_min = profile["s_min"]
    centers = profile["centers"]
    smooth_radius = profile["smooth_radius"]

    node_a = (total_length - expected_chamber_length_mm) / 2
    node_b = node_a + expected_chamber_length_mm
    cut_position = (node_a + node_b) / 2

    diameter = diameter_at_position(
        centers=centers,
        smooth_radius=smooth_radius,
        s_min=s_min,
        position_mm=cut_position,
        total_length_mm=total_length,
    )

    return {
        "total_length_mm": round(float(total_length), 2),
        "node_a_mm": round(float(node_a), 2),
        "node_b_mm": round(float(node_b), 2),
        "chamber_length_mm": round(float(expected_chamber_length_mm), 2),
        "cut_position_mm": round(float(cut_position), 2),
        "diameter_at_cut_mm": round(float(diameter), 2) if diameter is not None else None,
        "left_tail_length_mm": round(float(node_a), 2),
        "right_tail_length_mm": round(float(total_length - node_b), 2),
        "profile_status": "expected_chamber_centered",
    }


def measure_with_auto_nodes(profile: dict) -> dict:
    """
    Improved MVP bamboo node detection.

    Logic:
    - Build radius profile along reed axis.
    - Ignore both scan ends because mesh ends often create false peaks.
    - Detect local radius peaks.
    - Choose two peaks that create a plausible chamber.
    """
    total_length = profile["total_length"]
    s_min = profile["s_min"]
    centers = profile["centers"]
    smooth_radius = profile["smooth_radius"]

    position_mm = centers - s_min

    edge_margin = max(total_length * 0.12, 35.0)
    valid_mask = (position_mm > edge_margin) & (position_mm < total_length - edge_margin)

    if not np.any(valid_mask):
        return empty_result(total_length, "nodes_not_found")

    peak_signal = smooth_radius.copy()

    min_valid = np.nanmin(peak_signal[valid_mask])
    peak_signal[~valid_mask] = min_valid

    baseline = moving_average(peak_signal, window=31)
    detail_signal = peak_signal - baseline

    prominence = max(np.nanstd(detail_signal[valid_mask]) * 0.75, 0.18)
    min_distance = max(10, len(peak_signal) // 14)

    peaks, properties = find_peaks(
        detail_signal,
        distance=min_distance,
        prominence=prominence,
    )

    peaks = [p for p in peaks if valid_mask[p]]

    if len(peaks) < 2:
        return empty_result(total_length, "nodes_not_found")

    candidates = []

    for i in range(len(peaks)):
        for j in range(i + 1, len(peaks)):
            a = float(position_mm[peaks[i]])
            b = float(position_mm[peaks[j]])
            chamber = b - a

            if chamber < 60:
                continue

            if chamber > total_length * 0.88:
                continue

            chamber_center = (a + b) / 2
            center_penalty = abs(chamber_center - total_length / 2) / total_length

            strength = (
                float(detail_signal[peaks[i]])
                + float(detail_signal[peaks[j]])
            )

            # Prefer strong peaks and reasonably centered chamber.
            score = strength - center_penalty * 0.8

            candidates.append((score, a, b, chamber))

    if not candidates:
        return empty_result(total_length, "nodes_not_found")

    candidates.sort(reverse=True)
    _, node_a, node_b, chamber_length = candidates[0]

    cut_position = (node_a + node_b) / 2
    left_tail = node_a
    right_tail = total_length - node_b

    diameter = diameter_at_position(
        centers=centers,
        smooth_radius=smooth_radius,
        s_min=s_min,
        position_mm=cut_position,
        total_length_mm=total_length,
    )

    return {
        "total_length_mm": round(float(total_length), 2),
        "node_a_mm": round(float(node_a), 2),
        "node_b_mm": round(float(node_b), 2),
        "chamber_length_mm": round(float(chamber_length), 2),
        "cut_position_mm": round(float(cut_position), 2),
        "diameter_at_cut_mm": round(float(diameter), 2) if diameter is not None else None,
        "left_tail_length_mm": round(float(left_tail), 2),
        "right_tail_length_mm": round(float(right_tail), 2),
        "profile_status": "auto_nodes_improved",
    }


def measure_profile(
    mesh: trimesh.Trimesh,
    scale_to_mm: float,
    expected_chamber_length_mm: float | None = None,
) -> dict:
    profile = build_axis_profile(mesh, scale_to_mm=scale_to_mm)

    if expected_chamber_length_mm is not None:
        return measure_with_expected_chamber(
            profile=profile,
            expected_chamber_length_mm=expected_chamber_length_mm,
        )

    return measure_with_auto_nodes(profile=profile)


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
        path
        for path in scans_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )

    rows = []

    for path in files:
        piece_id = get_piece_id(path, scans_dir)

        expected_chamber = None
        matching_rows = master[master["piece_id"] == piece_id]

        if (
            not matching_rows.empty
            and "expected_chamber_length_mm" in master.columns
        ):
            value = matching_rows.iloc[0]["expected_chamber_length_mm"]

            if pd.notna(value):
                expected_chamber = float(value)

        try:
            mesh = load_mesh(path)

            result = measure_profile(
                mesh=mesh,
                scale_to_mm=args.scale,
                expected_chamber_length_mm=expected_chamber,
            )

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

    df = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    df.to_csv(output_dir / "profile_results.csv", index=False)

    print(df)
    print(f"\nSaved: {output_dir / 'profile_results.csv'}")


if __name__ == "__main__":
    main()