from pathlib import Path
import pandas as pd


PROFILE_COLUMNS = [
    "piece_id",
    "total_length_mm",
    "node_a_mm",
    "node_b_mm",
    "chamber_length_mm",
    "cut_position_mm",
    "diameter_at_cut_mm",
    "left_tail_length_mm",
    "right_tail_length_mm",
    "profile_status",
]


def refine_status(row: pd.Series) -> str:
    current = row.get("status")

    if current == "missing":
        return "missing"

    if current in ["scan_error", "not_measured"]:
        return current

    profile_status = row.get("profile_status")

    if profile_status == "nodes_not_found":
        return "check_nodes"

    if profile_status == "auto_nodes_estimated":
        return "check_nodes"

    if current == "check_length":
        return "check_length"

    return "ok"


def main() -> None:
    output_dir = Path("output")

    assembly_path = output_dir / "assembly_status.csv"
    profile_path = output_dir / "profile_results.csv"
    export_path = output_dir / "rhino_digital_twin_status.csv"

    assembly = pd.read_csv(assembly_path)

    if profile_path.exists():
        profile = pd.read_csv(profile_path)
    else:
        profile = pd.DataFrame(columns=PROFILE_COLUMNS)

    available_profile_columns = [
        column for column in PROFILE_COLUMNS
        if column in profile.columns
    ]

    df = assembly.merge(
        profile[available_profile_columns],
        on="piece_id",
        how="left",
    )

    df["status"] = df.apply(refine_status, axis=1)

    color_map = {
        "ok": "green",
        "missing": "red",
        "scan_error": "magenta",
        "not_measured": "orange",
        "check_length": "yellow",
        "check_nodes": "orange",
    }

    df["rhino_color"] = df["status"].map(color_map).fillna("gray")

    df.to_csv(export_path, index=False)

    print(df)
    print(f"\nSaved: {export_path}")


if __name__ == "__main__":
    main()