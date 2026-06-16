"""
Measures all Polycam / KIRI Engine GLB/GLTF/OBJ/STL/PLY scans in the scans/ folder.
Outputs: output/scan_results.csv

Main idea:
- If file is scans/P001.obj -> piece_id = P001
- If file is scans/P001/3DModel.obj -> piece_id = P001
- mesh bounding box gives approximate length / diameter
- this is not a full metrology tool, but it is good for sorting and first-pass QC
"""

from __future__ import annotations

from pathlib import Path
import argparse

import numpy as np
import pandas as pd
import trimesh


SUPPORTED_EXTENSIONS = {".glb", ".gltf", ".obj", ".stl", ".ply"}

OUTPUT_COLUMNS = [
    "piece_id",
    "scan_file",
    "scan_status",
    "length_mm",
    "width_mm",
    "height_mm",
    "approx_diameter_mm",
    "volume_mm3",
    "surface_area_mm2",
    "vertex_count",
    "face_count",
    "error_message",
]


def load_mesh(path: Path) -> trimesh.Trimesh:
    """Load a mesh from a file. GLB files may load as a Scene; merge geometries."""
    loaded = trimesh.load(path, force=None)

    if isinstance(loaded, trimesh.Scene):
        geometries = []

        for geom in loaded.geometry.values():
            if isinstance(geom, trimesh.Trimesh):
                geometries.append(geom)

        if not geometries:
            raise ValueError(f"No mesh geometry found in {path}")

        mesh = trimesh.util.concatenate(geometries)

    elif isinstance(loaded, trimesh.Trimesh):
        mesh = loaded

    else:
        raise TypeError(f"Unsupported loaded object type for {path}: {type(loaded)}")

    mesh.remove_unreferenced_vertices()
    return mesh


def measure_mesh(mesh: trimesh.Trimesh, scale_to_mm: float = 1.0) -> dict:
    """Return simple measurements from an oriented bounding box."""
    extents = np.array(mesh.bounding_box_oriented.extents, dtype=float) * scale_to_mm
    sorted_extents = np.sort(extents)

    height_mm = sorted_extents[0]
    width_mm = sorted_extents[1]
    length_mm = sorted_extents[2]
    approx_diameter_mm = float((width_mm + height_mm) / 2.0)

    volume = None
    surface_area = None

    try:
        volume = float(mesh.volume) * (scale_to_mm ** 3)
    except Exception:
        volume = None

    try:
        surface_area = float(mesh.area) * (scale_to_mm ** 2)
    except Exception:
        surface_area = None

    return {
        "length_mm": round(float(length_mm), 2),
        "width_mm": round(float(width_mm), 2),
        "height_mm": round(float(height_mm), 2),
        "approx_diameter_mm": round(float(approx_diameter_mm), 2),
        "volume_mm3": round(volume, 2) if volume is not None else None,
        "surface_area_mm2": round(surface_area, 2) if surface_area is not None else None,
        "vertex_count": int(len(mesh.vertices)),
        "face_count": int(len(mesh.faces)),
    }


def get_piece_id(path: Path, scans_dir: Path) -> str:
    """
    Get piece ID from file path.

    Supports:
    scans/P001.obj -> P001
    scans/P001/3DModel.obj -> P001
    """
    if path.parent == scans_dir:
        return path.stem

    return path.parent.name


def scan_folder(scans_dir: Path, output_dir: Path, scale_to_mm: float) -> pd.DataFrame:
    """Scan all supported 3D files in scans_dir and save scan_results.csv."""
    output_dir.mkdir(parents=True, exist_ok=True)
    scans_dir.mkdir(parents=True, exist_ok=True)

    rows = []

    files = sorted(
        path
        for path in scans_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )

    for path in files:
        piece_id = get_piece_id(path, scans_dir)

        try:
            mesh = load_mesh(path)
            measurements = measure_mesh(mesh, scale_to_mm=scale_to_mm)

            rows.append({
                "piece_id": piece_id,
                "scan_file": str(path),
                "scan_status": "measured",
                **measurements,
                "error_message": "",
            })

        except Exception as exc:
            rows.append({
                "piece_id": piece_id,
                "scan_file": str(path),
                "scan_status": "error",
                "length_mm": None,
                "width_mm": None,
                "height_mm": None,
                "approx_diameter_mm": None,
                "volume_mm3": None,
                "surface_area_mm2": None,
                "vertex_count": None,
                "face_count": None,
                "error_message": str(exc),
            })

    df = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    df.to_csv(output_dir / "scan_results.csv", index=False)

    return df


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scans", default="scans", help="Folder containing scan exports")
    parser.add_argument("--output", default="output", help="Output folder")
    parser.add_argument(
        "--scale",
        type=float,
        default=1.0,
        help="Scale factor to convert model units to mm"
    )

    args = parser.parse_args()

    df = scan_folder(Path(args.scans), Path(args.output), args.scale)

    print(df)
    print(f"\nSaved: {Path(args.output) / 'scan_results.csv'}")


if __name__ == "__main__":
    main()