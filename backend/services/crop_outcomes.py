"""Validate provenance-rich crop outcome CSVs without changing their records or DB.

Run from repository root with ``python -m backend.services.crop_outcomes`` or
from backend/ with ``python -m services.crop_outcomes``.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import re
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

try:
    from backend.services.crop_catalog import normalize_text, resolve_crop
except ModuleNotFoundError:
    from services.crop_catalog import normalize_text, resolve_crop

LOG = logging.getLogger("crop_outcomes")
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEMPLATE = ROOT / "data" / "crop_outcomes" / "template.csv"
DEFAULT_REPORT = ROOT / "data" / "crop_outcomes" / "coverage_report.json"
REQUIRED_COLUMNS = [
    "source_url", "source_citation", "publisher", "original_record_id", "observation_date",
    "crop", "state", "district", "location_description", "latitude", "longitude",
    "growth_stage", "outcome_type", "hazard_or_disease", "label_status", "label_basis",
    "negative_assessment_method",
    "severity", "severity_scale", "measured_loss_value", "measured_loss_unit",
    "verification_status", "uncertainty", "uncertainty_notes",
]
LABEL_STATUSES = {"positive", "negative", "unknown"}
OUTCOME_TYPES = {"disease_observation", "crop_damage", "yield_loss"}
VERIFICATION_STATUSES = {"unverified", "source_documented", "independently_verified", "expert_reviewed"}


def _float(value: str):
    if not value.strip():
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except ValueError:
        return None


def _valid_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except ValueError:
        return False


def validate_row(row: dict[str, str], row_number: int) -> list[str]:
    errors = []
    get = lambda key: (row.get(key) or "").strip()
    if not get("source_url") and not get("source_citation"):
        errors.append("source_url_or_citation_required")
    if get("source_url") and not _valid_url(get("source_url")):
        errors.append("source_url_must_be_http_or_https")
    for col in ("publisher", "original_record_id", "observation_date", "crop", "outcome_type", "hazard_or_disease", "label_status", "label_basis", "verification_status", "uncertainty"):
        if not get(col):
            errors.append(f"missing_{col}")
    if not get("district") and not get("location_description"):
        errors.append("district_or_location_description_required")

    if get("observation_date"):
        try:
            if date.fromisoformat(get("observation_date")).isoformat() != get("observation_date"):
                errors.append("observation_date_must_be_iso_yyyy_mm_dd")
        except ValueError:
            errors.append("observation_date_must_be_iso_yyyy_mm_dd")

    if get("crop"):
        crop, choices = resolve_crop(get("crop"))
        if crop is None:
            errors.append("crop_not_in_catalog" if not choices else "ambiguous_crop_name")
        elif normalize_text(get("crop")) != normalize_text(crop["canonical_name"]):
            errors.append(f"crop_must_use_catalog_canonical_name:{crop['canonical_name']}")

    lat, lon = get("latitude"), get("longitude")
    if bool(lat) != bool(lon):
        errors.append("latitude_and_longitude_must_be_provided_together")
    if lat:
        value = _float(lat)
        if value is None or not -90 <= value <= 90:
            errors.append("invalid_latitude")
    if lon:
        value = _float(lon)
        if value is None or not -180 <= value <= 180:
            errors.append("invalid_longitude")

    label = get("label_status").lower()
    if label and label not in LABEL_STATUSES:
        errors.append("label_status_must_be_positive_negative_or_unknown")
    outcome_type = get("outcome_type").lower()
    if outcome_type and outcome_type not in OUTCOME_TYPES:
        errors.append("invalid_outcome_type")
    verification = get("verification_status").lower()
    if verification and verification not in VERIFICATION_STATUSES:
        errors.append("invalid_verification_status")
    if get("severity") and not get("severity_scale"):
        errors.append("severity_requires_source_defined_scale")

    loss_text, loss_unit = get("measured_loss_value"), get("measured_loss_unit")
    loss_value = _float(loss_text)
    if loss_text and (loss_value is None or loss_value < 0):
        errors.append("measured_loss_must_be_finite_nonnegative_number")
    if bool(loss_text) != bool(loss_unit):
        errors.append("measured_loss_value_and_unit_required_together")
    if label == "positive" and not get("severity") and loss_value is None:
        errors.append("positive_label_requires_severity_or_measured_loss")
    negative_method = get("negative_assessment_method").casefold()
    if label == "negative" and (not negative_method or negative_method in {"not reported", "no report", "absence of report", "unknown", "not available", "n/a"}):
        errors.append("negative_label_requires_explicit_assessment_method_not_absence_of_reporting")
    uncertainty = get("uncertainty").lower()
    if uncertainty and uncertainty not in {"low", "medium", "high", "unknown"}:
        errors.append("uncertainty_must_be_low_medium_high_or_unknown")
    return errors


def validate_csv(input_path: Path) -> dict:
    # Open read-only and retain submitted data as-is; no normalization or DB writes.
    with input_path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        headers = reader.fieldnames or []
        missing_columns = [column for column in REQUIRED_COLUMNS if column not in headers]
        rows = list(reader)
    row_errors: dict[int, list[str]] = {}
    seen_ids: dict[tuple[str, str], int] = {}
    seen_rows: dict[tuple[tuple[str, str], ...], int] = {}
    for row_no, row in enumerate(rows, start=2):
        errors = validate_row(row, row_no)
        key = ((row.get("publisher") or "").strip().casefold(), (row.get("original_record_id") or "").strip().casefold())
        if all(key) and key in seen_ids:
            errors.append(f"duplicate_publisher_record_id:first_seen_row_{seen_ids[key]}")
        elif all(key):
            seen_ids[key] = row_no
        row_key = tuple(sorted((str(k), str(v or "")) for k, v in row.items()))
        if row_key in seen_rows:
            errors.append(f"duplicate_row:first_seen_row_{seen_rows[row_key]}")
        else:
            seen_rows[row_key] = row_no
        if errors:
            row_errors[row_no] = errors

    missingness = {}
    for column in headers:
        count = sum(not (row.get(column) or "").strip() for row in rows)
        missingness[column] = {"missing": count, "total": len(rows), "fraction": count / len(rows) if rows else None}
    by_crop = Counter((row.get("crop") or "").strip() or "[missing]" for row in rows)
    by_hazard = Counter((row.get("hazard_or_disease") or "").strip() or "[missing]" for row in rows)
    by_label = Counter((row.get("label_status") or "").strip().lower() or "unknown_or_missing" for row in rows)
    # Tuple construction kept explicit so source coverage can be audited without exposing content.
    source_records = {(str(r.get("publisher") or "").strip(), str(r.get("source_url") or "").strip(), str(r.get("source_citation") or "").strip()) for r in rows}
    valid_count = len(rows) - len(row_errors) if not missing_columns else 0
    return {
        "report_generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_file": str(input_path.resolve()), "database_import_performed": False,
        "training_store_imported_records": 0,
        "record_counts": {"rows_read": len(rows), "validated_records_ready_for_review": valid_count,
                          "records_with_validation_failures": len(row_errors), "records_written_to_database": 0},
        "missing_template_columns": missing_columns,
        "counts_by_crop_as_submitted": dict(sorted(by_crop.items())),
        "counts_by_hazard_as_submitted": dict(sorted(by_hazard.items())),
        "label_counts_as_submitted": {label: by_label.get(label, 0) for label in ("positive", "negative", "unknown", "unknown_or_missing")},
        "source_coverage": {"distinct_publisher_source_combinations": len(source_records),
                            "publishers": sorted({x[0] for x in source_records if x[0]}),
                            "rows_with_source_url": sum(bool((r.get("source_url") or "").strip()) for r in rows),
                            "rows_with_citation": sum(bool((r.get("source_citation") or "").strip()) for r in rows)},
        "missing_fields_by_column": missingness,
        "validation_failures": [{"row": row, "errors": errors} for row, errors in sorted(row_errors.items())],
        "matching_status": "not_attempted_weather_and_outcome_data_remain_separate",
        "notes": ["No outcome records are inferred from absent reports.",
                  "Submitted CSV rows are read-only; this command does not rewrite records or insert into PostgreSQL.",
                  "CropAI rules and predictions are not accepted as outcome evidence."],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_TEMPLATE, help="CSV template or user-supplied source records")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="Coverage report JSON; replaces only this report file")
    args = parser.parse_args(argv)
    try:
        report = validate_csv(args.input)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except (OSError, csv.Error, UnicodeError) as exc:
        LOG.error("Unable to validate CSV: %s", exc)
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if report["missing_template_columns"] or report["record_counts"]["records_with_validation_failures"] else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR, format="%(levelname)s %(message)s")
    sys.exit(main())
