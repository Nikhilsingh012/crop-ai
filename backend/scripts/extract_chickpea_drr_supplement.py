"""Extract source-faithful candidate tables from the Springer Nature workbook.

This script only copies cells from two named source sheets. It does not create
outcome labels, convert units, infer dates, or modify the source workbook.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, time
from pathlib import Path

from openpyxl import load_workbook


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WORKBOOK = (
    PROJECT_ROOT
    / "data/crop_outcomes/source_files/chickpea_dry_root_rot/"
    / "41598_2021_85928_MOESM2_ESM.xlsx"
)
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "data/crop_outcomes/processed/chickpea_dry_root_rot"
)

LITERATURE_SHEET = "Supplementary Table S1 DataFile"
FARMER_SHEET = "Supplementary Figure S14"
LITERATURE_HEADERS = [
    "State", "Location", "Taluka", "Village", "Variety", "Variety",
    "Seed treatment", "Soil type", "Rainfed/Irrigated", "Soil number",
    "DRR-DI", "Year", "RainF-Oct", "RainF-Nov", "RainF-Dec", "RainF-Jan",
    "RainF-Feb", "RainF-OctNov", "RainF-NovDec", "RainF-DecJan",
    "RainF-JanFeb", "RainF-OctNovDec", "RainF-NovDecJan",
    "RainF-DecJanFeb", "MinT-Oct", "MinT-Nov", "MinT-Dec", "MinT-Jan",
    "MinT-Feb", "MinT-OctNov", "MinT-NovDec", "MinT-DecJan",
    "MinT-JanFeb", "MinT-OctNovDec", "MinT-NovDecJan", "MinT-DecJanFeb",
    "MaxT-Oct", "MaxT-Nov", "MaxT-Dec", "MaxT-Jan", "MaxT-Feb",
    "MaxT-OctNov", "MaxT-NovDec", "MaxT-DecJan", "MaxT-JanFeb",
    "MaxT-OctNovDec", "MaxT-NovDecJan", "MaxT-DecJanFeb",
]
FARMER_HEADERS = [
    "Location 1 Kadappa", "N", "E", "Name of the farmer", "Name of village",
    "Mode of irrigation", "Previous crop", "Plant growth stage", "Month of sowing",
    "Reading 1", "Reading 2", "Reading 3", "Reading 4", "Reading 5",
    "Reading 1", "Reading 2", "Reading 3", "Reading 4", "Reading 5",
]
SUMMARY_HEADERS = [None, "Location", "DI (%)", "SMC (%)", "DI SEM", "SMC SEM"]


def _as_csv(value: object) -> str:
    """Serialize cell values without changing numeric values or blank cells."""
    if value is None:
        return ""
    if isinstance(value, (datetime, date, time)):
        return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    return str(value)


def _write_csv(path: Path, header: list[object], rows: list[list[object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow([_as_csv(value) for value in header])
        writer.writerows([_as_csv(value) for value in row] for row in rows)


def extract(workbook_path: Path, output_dir: Path, *, overwrite: bool = False) -> dict[str, int]:
    """Extract verified workbook rows; refuse changed layouts or accidental overwrite."""
    if not workbook_path.is_file():
        raise FileNotFoundError(f"Workbook not found: {workbook_path}")

    output_names = [
        "literature_records.csv",
        "farmer_field_entries.csv",
        "farmer_field_summary_measurements.csv",
    ]
    if output_dir.exists() and not output_dir.is_dir():
        raise NotADirectoryError(output_dir)
    existing = [output_dir / name for name in output_names if (output_dir / name).exists()]
    if existing and not overwrite:
        raise FileExistsError(
            "Refusing to overwrite existing extraction output(s): "
            + ", ".join(str(path) for path in existing)
            + ". Pass --overwrite only when intentionally regenerating them."
        )

    # Normal mode is substantially faster here: one workbook sheet carries formatting
    # through Excel's maximum column, making repeated read-only random cell access slow.
    workbook = load_workbook(workbook_path, data_only=True, read_only=False)
    try:
        if LITERATURE_SHEET not in workbook.sheetnames or FARMER_SHEET not in workbook.sheetnames:
            raise ValueError(f"Required sheets missing; found: {workbook.sheetnames}")

        literature = workbook[LITERATURE_SHEET]
        actual_literature_headers = [literature.cell(3, col).value for col in range(1, 49)]
        if actual_literature_headers != LITERATURE_HEADERS:
            raise ValueError("Literature sheet header row 3 differs from verified source layout")
        literature_rows = [
            [LITERATURE_SHEET, row]
            + [literature.cell(row, col).value for col in range(1, 49)]
            for row in range(4, 101)
        ]
        if len(literature_rows) != 97:
            raise ValueError(f"Expected 97 literature rows, found {len(literature_rows)}")

        farmer = workbook[FARMER_SHEET]
        actual_farmer_headers = [farmer.cell(3, col).value for col in range(1, 20)]
        if actual_farmer_headers != FARMER_HEADERS:
            raise ValueError("Farmer-field header row 3 differs from verified source layout")
        field_rows: list[list[object]] = []
        farmer_rows_by_village: dict[str, list[int]] = {}
        section = str(farmer.cell(3, 1).value or "")
        for row in range(4, 17):
            first_cell = farmer.cell(row, 1).value
            if isinstance(first_cell, str) and first_cell.startswith("Location "):
                section = first_cell
                continue
            if isinstance(first_cell, str) and first_cell.startswith("Field"):
                values = [farmer.cell(row, col).value for col in range(1, 20)]
                village = values[4]
                previous_crop = values[6]
                crop_flag = (
                    "previous_crop_is_chickpea"
                    if isinstance(previous_crop, str) and previous_crop.strip().casefold() == "chickpea"
                    else "previous_crop_is_not_chickpea"
                    if previous_crop not in (None, "")
                    else "previous_crop_missing"
                )
                field_rows.append(
                    [FARMER_SHEET, row, section, "ambiguous_current_crop", crop_flag] + values
                )
                if village not in (None, ""):
                    farmer_rows_by_village.setdefault(str(village).strip().casefold(), []).append(row)

        summary_header_row = 17
        actual_summary_headers = [farmer.cell(summary_header_row, col).value for col in range(1, 7)]
        if actual_summary_headers != SUMMARY_HEADERS:
            raise ValueError("Farmer-field summary header row 17 differs from verified source layout")
        summary_rows: list[list[object]] = []
        section = ""
        for row in range(18, 29):
            first_cell = farmer.cell(row, 1).value
            if first_cell not in (None, ""):
                section = str(first_cell)
            village = farmer.cell(row, 2).value
            incidence = farmer.cell(row, 3).value
            moisture = farmer.cell(row, 4).value
            if village not in (None, "") and (incidence is not None or moisture is not None):
                candidate_rows = farmer_rows_by_village.get(str(village).strip().casefold(), [])
                summary_rows.append(
                    [FARMER_SHEET, row, section, ";".join(map(str, candidate_rows))]
                    + [farmer.cell(row, col).value for col in range(2, 7)]
                )

        if len(field_rows) != 6:
            raise ValueError(f"Expected 6 farmer-field entries, found {len(field_rows)}")
        if len(summary_rows) != 8:
            raise ValueError(f"Expected 8 associated summary rows, found {len(summary_rows)}")
    finally:
        workbook.close()

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir / output_names[0], ["source_sheet", "source_excel_row"] + LITERATURE_HEADERS, literature_rows)
    _write_csv(
        output_dir / output_names[1],
        ["source_sheet", "source_excel_row", "source_location_section", "current_crop_identity_status",
         "previous_crop_flag"] + FARMER_HEADERS,
        field_rows,
    )
    _write_csv(
        output_dir / output_names[2],
        ["source_sheet", "source_excel_row", "source_location_section",
         "candidate_related_field_excel_rows"] + SUMMARY_HEADERS[1:],
        summary_rows,
    )
    return {
        "literature_records": len(literature_rows),
        "farmer_field_entries": len(field_rows),
        "farmer_field_summary_measurements": len(summary_rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--overwrite", action="store_true", help="replace existing CSV outputs")
    args = parser.parse_args()
    counts = extract(args.workbook, args.output_dir, overwrite=args.overwrite)
    for name, count in counts.items():
        print(f"{name}: {count}")
    for name in (
        "literature_records.csv",
        "farmer_field_entries.csv",
        "farmer_field_summary_measurements.csv",
    ):
        path = args.output_dir / name
        print(f"{path}: {path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
