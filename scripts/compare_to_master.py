"""
Compares measured scans with the Grasshopper/Rhino master CSV.

Piece-level digital twin logic:
- One row = one real reed/bamboo piece.
- master.csv defines all expected pieces.
- scan_results.csv contains pieces that have been scanned.
- Missing scans stay in the output as red/missing.
- Approx/bounding-box diameter is kept only as info.
- Status is based on scan existence + length tolerance only.
- Node/chamber/cut quality is handled later in export_rhino_status.py.
"""

from __future__ import annotations

from pathlib import Path
import argparse
import pandas as pd


def choose_status(row: pd.Series) -> str:
    if pd.isna(row.get("scan_file")):
        return "missing"

    if row.get("scan_status") == "error":
        return "scan_error"

    if pd.isna(row.get("length_mm")):
        return "not_measured"

    return "scanned"


def compare(master_csv: Path, scan_results_csv: Path, output_dir: Path) -> pd.DataFrame:
    output_dir.mkdir(parents=True, exist_ok=True)

    master = pd.read_csv(master_csv)
    master = master.dropna(how="all")

    if scan_results_csv.exists():
        try:
            scans = pd.read_csv(scan_results_csv)
        except pd.errors.EmptyDataError:
            scans = pd.DataFrame(columns=["piece_id"])
    else:
        scans = pd.DataFrame(columns=["piece_id"])

    required = {
        "piece_id",
        "assembly_order",
        "group_name",
        "tree_id",
        "branch_level",
        "angle_deg",
        "expected_length_mm",
        "expected_diameter_min_mm",
        "expected_diameter_max_mm",
    }

    missing_columns = required - set(master.columns)
    if missing_columns:
        raise ValueError(f"Master CSV missing columns: {sorted(missing_columns)}")

    if "tolerance_length_mm" not in master.columns:
        master["tolerance_length_mm"] = 15

    df = master.merge(scans, on="piece_id", how="left")

    df["length_error_mm"] = df["length_mm"] - df["expected_length_mm"]

    # Diameter is approximate info only. Do not use bounding-box diameter for status.
    if "approx_diameter_mm" in df.columns:
        df["diameter_range_mm"] = (
            df["expected_diameter_min_mm"].astype(str)
            + "-"
            + df["expected_diameter_max_mm"].astype(str)
        )
    else:
        df["diameter_range_mm"] = (
            df["expected_diameter_min_mm"].astype(str)
            + "-"
            + df["expected_diameter_max_mm"].astype(str)
        )

    df["status"] = df.apply(choose_status, axis=1)

    color_map = {
    "scanned": "green",
    "missing": "red",
    "scan_error": "magenta",
    "not_measured": "orange",
}

    df["rhino_color"] = df["status"].map(color_map).fillna("gray")

    df = df.sort_values("assembly_order")

    df.to_csv(output_dir / "assembly_status.csv", index=False)

    df[df["status"] == "missing"].to_csv(
        output_dir / "missing_pieces.csv",
        index=False,
    )

    df[df["status"].isin(["check_length", "scan_error", "not_measured"])].to_csv(
        output_dir / "check_pieces.csv",
        index=False,
    )

    df[df["status"] == "ok"].to_csv(
        output_dir / "next_assembly_sequence.csv",
        index=False,
    )

    return df


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--master", default="data/master.csv")
    parser.add_argument("--scans", default="output/scan_results.csv")
    parser.add_argument("--output", default="output")
    args = parser.parse_args()

    df = compare(Path(args.master), Path(args.scans), Path(args.output))

    columns_to_show = [
        "piece_id",
        "assembly_order",
        "group_name",
        "tree_id",
        "branch_level",
        "angle_deg",
        "expected_length_mm",
        "length_mm",
        "length_error_mm",
        "diameter_range_mm",
        "status",
        "rhino_color",
    ]

    print(df[columns_to_show])
    print(f"\nSaved: {Path(args.output) / 'assembly_status.csv'}")


if __name__ == "__main__":
    main()