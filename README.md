# Studio Reed Digital Twin — Rhino / Grasshopper + Polycam + Python

This is an MVP workflow for scanning, checking, sorting and assembling robot-milled pieces.

## Core idea

1. Grasshopper/Rhino exports a master table: `data/master.csv`
2. Polycam exports physical scans as `.glb` files into `scans/`
3. Python measures every scan and compares it with the master table
4. Python exports `output/assembly_status.csv`
5. Grasshopper imports `assembly_status.csv` and colors/sorts the digital model

## Project structure

```text
studio_reed_digital_twin/
├── data/
│   └── master.csv
├── scans/
│   └── P001.glb, P002.glb, ...
├── ideal_models/
│   └── optional later
├── output/
│   ├── scan_results.csv
│   ├── assembly_status.csv
│   ├── missing_pieces.csv
│   ├── check_pieces.csv
│   └── next_assembly_sequence.csv
├── scripts/
│   ├── scan_measure.py
│   ├── compare_to_master.py
│   └── run_pipeline.py
├── requirements.txt
└── README.md
```

## Setup in VS Code + Ubuntu terminal

Open Ubuntu terminal:

```bash
cd ~/Desktop
unzip studio_reed_digital_twin.zip
cd studio_reed_digital_twin
code .
```

Create virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Daily use

1. Export/update `data/master.csv` from Grasshopper.
2. Put Polycam files in `scans/`.
   - file names must match IDs: `P001.glb`, `P002.glb`, etc.
3. Run:

```bash
python scripts/run_pipeline.py
```

The main result is:

```text
output/assembly_status.csv
```

Import this CSV back into Grasshopper.

## Master CSV columns

Required columns:

```csv
piece_id,assembly_order,target_position,expected_length_mm,expected_diameter_mm,tolerance_length_mm,tolerance_diameter_mm,notes
```

Example:

```csv
P001,1,A01,500,25,10,4,first piece
```

## Important scanning rules

- One physical piece = one Polycam model.
- File name must equal piece ID.
- Try to scan in similar orientation each time.
- Keep units consistent. This project assumes millimetres.
- If measurements are too large/small by factor 10/100/1000, run with scale:

```bash
python scripts/run_pipeline.py --scale 1000
```

or edit the scale value after testing.

## Output meaning

`status` can be:

- `ok` — scanned and inside tolerance
- `missing` — exists in master table but no scan file found
- `check_length` — length outside tolerance
- `check_diameter` — diameter outside tolerance
- `scan_error` — Python could not read the file
- `not_measured` — file exists but measurement failed

`rhino_color` is intended for Grasshopper preview/material logic:

- green = ok
- red = missing
- yellow = check
- magenta = scan error
- orange = not measured

## Grasshopper side

Recommended plugins/components:

- Native Grasshopper `File Path`, `Read File`, `Text Split`, `Text Trim`
- Or plugins: LunchBox / TT Toolbox / Elefront
- Use `piece_id` as the matching key between Rhino objects and CSV rows
- Use `rhino_color` to preview object status
- Use `assembly_order` to sort objects

## Next professional upgrades

Later, add:

- Open3D shape comparison against ideal GLB models
- QR/ArUco camera station with OpenCV
- Rhino user text / attributes for every object ID
- Automatic Grasshopper export from generated geometry
- A dashboard showing missing / checked / assembled pieces
