"""
Compares measured Polycam scans with the Grasshopper/Rhino master CSV.
Outputs:
- output/assembly_status.csv        for Rhino/Grasshopper import
- output/missing_pieces.csv         not scanned yet
- output/check_pieces.csv           outside tolerance or scan error
- output/next_assembly_sequence.csv sorted list of OK pieces
"""

from __future__ import annotations

from pathlib import Path
import argparse
import pandas as pd
import numpy as np


def choose_status(row: pd.Series) -> str:
    if pd.isna(row.get("scan_file")):
        return "missing"
    if row.get("scan_status") == "error":
        return "scan_error"
    if pd.isna(row.get("length_mm")):
        return "not_measured"

    length_error = row.get("length_error_mm")
    diameter_error = row.get("diameter_error_mm")
    length_tol = row.get("tolerance_length_mm")
    diameter_tol = row.get("tolerance_diameter_mm")

    if pd.notna(length_error) and pd.notna(length_tol) and abs(length_error) > length_tol:
        return "check_length"
    if pd.notna(diameter_error) and pd.notna(diameter_tol) and abs(diameter_error) > diameter_tol:
        return "check_diameter"
    return "ok"


def compare(master_csv: Path, scan_results_csv: Path, output_dir: Path) -> pd.DataFrame:
    output_dir.mkdir(parents=True, exist_ok=True)

    master = pd.read_csv(master_csv)
    scans = pd.read_csv(scan_results_csv) if scan_results_csv.exists() else pd.DataFrame(columns=["piece_id"])

    required = {"piece_id", "assembly_order", "target_position", "expected_length_mm", "expected_diameter_mm"}
    missing_columns = required - set(master.columns)
    if missing_columns:
        raise ValueError(f"Master CSV missing columns: {sorted(missing_columns)}")

    if "tolerance_length_mm" not in master.columns:
        master["tolerance_length_mm"] = 10
    if "tolerance_diameter_mm" not in master.columns:
        master["tolerance_diameter_mm"] = 4

    df = master.merge(scans, on="piece_id", how="left")

    df["length_error_mm"] = df["length_mm"] - df["expected_length_mm"]
    df["diameter_error_mm"] = df["approx_diameter_mm"] - df["expected_diameter_mm"]
    df["status"] = df.apply(choose_status, axis=1)

    # Numeric color codes are easy to use in Grasshopper.
    color_map = {
        "ok": "green",
        "missing": "red",
        "scan_error": "magenta",
        "not_measured": "orange",
        "check_length": "yellow",
        "check_diameter": "yellow",
    }
    df["rhino_color"] = df["status"].map(color_map).fillna("gray")

    df = df.sort_values("assembly_order")

    df.to_csv(output_dir / "assembly_status.csv", index=False)
    df[df["status"] == "missing"].to_csv(output_dir / "missing_pieces.csv", index=False)
    df[df["status"].str.startswith("check") | df["status"].isin(["scan_error", "not_measured"])].to_csv(
        output_dir / "check_pieces.csv", index=False
    )
    df[df["status"] == "ok"].to_csv(output_dir / "next_assembly_sequence.csv", index=False)

    return df


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--master", default="data/master.csv")
    parser.add_argument("--scans", default="output/scan_results.csv")
    parser.add_argument("--output", default="output")
    args = parser.parse_args()

    df = compare(Path(args.master), Path(args.scans), Path(args.output))
    print(df[["piece_id", "assembly_order", "target_position", "length_mm", "approx_diameter_mm", "status", "rhino_color"]])
    print(f"\nSaved: {Path(args.output) / 'assembly_status.csv'}")


if __name__ == "__main__":
    main()
