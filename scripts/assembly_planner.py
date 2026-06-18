from pathlib import Path
import pandas as pd


def main():
    input_csv = Path("output/rhino_digital_twin_status.csv")
    output_csv = Path("output/tree_assembly_status.csv")

    df = pd.read_csv(input_csv)

    rows = []

    for tree_id, group in df.groupby("tree_id"):
        group = group.sort_values("assembly_order")

        required = group["piece_id"].tolist()
        present = group[group["status"] != "missing"]["piece_id"].tolist()
        missing = group[group["status"] == "missing"]["piece_id"].tolist()
        check = group[group["status"].str.startswith("check", na=False)]["piece_id"].tolist()

        if len(missing) == 0 and len(check) == 0:
            assembly_status = "ready"
            rhino_color = "green"
        elif len(present) == 0:
            assembly_status = "not_started"
            rhino_color = "red"
        elif len(missing) > 0:
            assembly_status = "incomplete"
            rhino_color = "yellow"
        else:
            assembly_status = "needs_check"
            rhino_color = "orange"

        rows.append({
            "tree_id": tree_id,
            "group_name": group["group_name"].iloc[0],
            "required_count": len(required),
            "present_count": len(present),
            "missing_count": len(missing),
            "check_count": len(check),
            "required_pieces": " ".join(required),
            "present_pieces": " ".join(present),
            "missing_pieces": " ".join(missing),
            "check_pieces": " ".join(check),
            "assembly_status": assembly_status,
            "rhino_color": rhino_color,
        })

    out = pd.DataFrame(rows)
    out.to_csv(output_csv, index=False)

    print(out)
    print(f"\nSaved: {output_csv}")


if __name__ == "__main__":
    main()