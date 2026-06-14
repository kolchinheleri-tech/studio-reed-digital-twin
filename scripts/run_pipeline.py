"""
One-command pipeline:
1. measure scans
2. compare against master.csv
3. export Grasshopper/Rhino-friendly CSVs
"""

from pathlib import Path
import argparse
import subprocess
import sys


def run(command: list[str]) -> None:
    print("\n> " + " ".join(command))
    completed = subprocess.run(command)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--master", default="data/master.csv")
    parser.add_argument("--scans-dir", default="scans")
    parser.add_argument("--output", default="output")
    args = parser.parse_args()

    run([sys.executable, "scripts/scan_measure.py", "--scans", args.scans_dir, "--output", args.output, "--scale", str(args.scale)])
    run([sys.executable, "scripts/compare_to_master.py", "--master", args.master, "--scans", str(Path(args.output) / "scan_results.csv"), "--output", args.output])

    print("\nDone. Main file for Grasshopper/Rhino:")
    print(Path(args.output) / "assembly_status.csv")


if __name__ == "__main__":
    main()
