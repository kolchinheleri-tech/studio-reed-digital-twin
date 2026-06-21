from pathlib import Path
import pandas as pd


MIN_REQUIRED_SCAN_RATIO = 0.30
DEFAULT_TARGET_TOTAL_LENGTH_MM = 200
SAFETY_MARGIN_MM = 10


def main():
    input_csv = Path("output/rhino_digital_twin_status.csv")
    output_csv = Path("output/cut_plan.csv")

    df = pd.read_csv(input_csv)

    valid = df[
        (df["status"] != "missing")
        & df["node_a_mm"].notna()
        & df["node_b_mm"].notna()
        & df["cut_position_mm"].notna()
    ].copy()

    rows = []

    for group_name, group in df.groupby("group_name"):
        valid_group = valid[valid["group_name"] == group_name].copy()

        required_count = len(group)
        scanned_count = len(group[group["status"] != "missing"])
        valid_count = len(valid_group)
        valid_node_ratio = valid_count / required_count if required_count else 0

        if valid_count > 0:
            valid_group["left_available_mm"] = (
                valid_group["cut_position_mm"] - valid_group["node_a_mm"]
            )
            valid_group["right_available_mm"] = (
                valid_group["node_b_mm"] - valid_group["cut_position_mm"]
            )
            valid_group["max_centered_cut_length_mm"] = (
                valid_group[["left_available_mm", "right_available_mm"]].min(axis=1) * 2
            )

            short_count = len(
                valid_group[
                    valid_group["max_centered_cut_length_mm"]
                    < DEFAULT_TARGET_TOTAL_LENGTH_MM
                ]
            )
            short_ratio = short_count / valid_count

            if valid_node_ratio < MIN_REQUIRED_SCAN_RATIO:
                recommended_total_length_mm = None
                recommendation_status = "not_enough_valid_scans"

            elif short_ratio >= MIN_REQUIRED_SCAN_RATIO:
                group_limit = valid_group["max_centered_cut_length_mm"].median()
                recommended_total_length_mm = max(0, group_limit - SAFETY_MARGIN_MM)
                recommendation_status = "reduce_model_length"

            else:
                recommended_total_length_mm = DEFAULT_TARGET_TOTAL_LENGTH_MM
                recommendation_status = "use_default_200mm"

        else:
            short_ratio = None
            recommended_total_length_mm = None
            recommendation_status = "no_valid_node_data"

        for _, row in group.iterrows():
            node_a = row.get("node_a_mm")
            node_b = row.get("node_b_mm")
            cut_pos = row.get("cut_position_mm")

            if pd.notna(node_a) and pd.notna(node_b) and pd.notna(cut_pos):
                left_available = cut_pos - node_a
                right_available = node_b - cut_pos
                max_centered = min(left_available, right_available) * 2

                if recommended_total_length_mm is not None:
                    half = recommended_total_length_mm / 2
                    left_saw_cut_mm = cut_pos - half
                    right_saw_cut_mm = cut_pos + half

                    if left_saw_cut_mm < node_a or right_saw_cut_mm > node_b:
                        cut_status = "does_not_fit_chamber"
                    else:
                        cut_status = "cut_possible"
                else:
                    half = None
                    left_saw_cut_mm = None
                    right_saw_cut_mm = None
                    cut_status = "no_group_recommendation"
            else:
                left_available = None
                right_available = None
                max_centered = None
                half = None
                left_saw_cut_mm = None
                right_saw_cut_mm = None
                cut_status = "missing_node_data"

            rows.append({
                "piece_id": row["piece_id"],
                "group_name": group_name,
                "tree_id": row["tree_id"],
                "status": row["status"],
                "profile_status": row.get("profile_status"),
                "node_a_mm": node_a,
                "node_b_mm": node_b,
                "bend_position_mm": cut_pos,
                "robot_cut_position_mm": cut_pos,
                "left_available_mm": left_available,
                "right_available_mm": right_available,
                "max_centered_cut_length_mm": max_centered,
                "recommended_total_length_mm": recommended_total_length_mm,
                "recommended_half_length_mm": (
                    recommended_total_length_mm / 2
                    if recommended_total_length_mm is not None
                    else None
                ),
                "left_saw_cut_from_scan_start_mm": left_saw_cut_mm,
                "right_saw_cut_from_scan_start_mm": right_saw_cut_mm,
                "cut_status": cut_status,
                "group_required_count": required_count,
                "group_scanned_count": scanned_count,
                "group_valid_node_count": valid_count,
                "valid_node_ratio": valid_node_ratio,
                "short_chamber_ratio": short_ratio,
                "recommendation_status": recommendation_status,
            })

    out = pd.DataFrame(rows)
    out.to_csv(output_csv, index=False)

    print(out)
    print(f"\nSaved: {output_csv}")


if __name__ == "__main__":
    main()