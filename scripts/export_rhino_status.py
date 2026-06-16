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


def main() -> None:
    output_dir = Path("output")

    assembly_path = output_dir / "assembly_status.csv"
    profile_path = output_dir / "profile_results.csv"
    export_path = output_dir / "rhino_digital_twin_status.csv"

    assembly = pd.read_csv(assembly_path)
    profile = pd.read_csv(profile_path)

    available_profile_columns = [
        column for column in PROFILE_COLUMNS
        if column in profile.columns
    ]

    df = assembly.merge(
        profile[available_profile_columns],
        on="piece_id",
        how="left",
    )

    df.to_csv(export_path, index=False)

    print(df)
    print(f"\nSaved: {export_path}")


if __name__ == "__main__":
    main()