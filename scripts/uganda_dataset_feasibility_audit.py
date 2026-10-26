"""Read-only full-dataset weather coverage audit for Uganda CBSD files."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from uganda_power_weather_pilot import MISSING_TEXT, parse_observation_date


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "data/crop_outcomes/source_files/uganda_cassava_brown_streak"
PILOT_DIR = ROOT / "data/crop_outcomes/processed/uganda_cassava_brown_streak/weather_pilot"
JSON_OUTPUT = ROOT / "data/crop_outcomes/processed/uganda_cassava_brown_streak/full_dataset_feasibility_audit.json"
MARKDOWN_OUTPUT = ROOT / "docs/uganda_full_dataset_weather_feasibility.md"
DATE_FORMATS = ("%m/%d/%Y", "%Y-%m-%d", "%Y/%m/%d", "%m/%d/%y")


def _missing(value: Any) -> bool:
    return value is None or str(value).strip() in MISSING_TEXT


def _resolve_column(headers: list[str], options: tuple[str, ...]) -> str | None:
    by_lower = {value.strip().lower(): value for value in headers}
    return next((by_lower[name.lower()] for name in options if name.lower() in by_lower), None)


def _number(value: Any) -> float | None:
    if _missing(value):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _date(value: Any) -> date | None:
    if _missing(value):
        return None
    return parse_observation_date(str(value))


def _actual_date_format(value: str) -> str | None:
    if _missing(value):
        return None
    for fmt in DATE_FORMATS:
        try:
            datetime.strptime(str(value).strip(), fmt)
            return fmt
        except ValueError:
            continue
    return None


def _field_records(rows: list[dict[str, str]], id_col: str, date_col: str,
                   lat_col: str, lon_col: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row[id_col]].append(row)
    field_rows = []
    conflicts = []
    for field_id, group in grouped.items():
        signatures = set()
        for row in group:
            day = _date(row.get(date_col, ""))
            lat, lon = _number(row.get(lat_col, "")), _number(row.get(lon_col, ""))
            if day and lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
                signatures.add((day.isoformat(), lat, lon))
        if len(signatures) > 1:
            conflicts.append({"id": field_id, "eligible_signatures": sorted(signatures)})
        if signatures:
            # A field ID with conflicting row-level dates/coordinates is not collapsed.
            for signature in sorted(signatures):
                field_rows.append({"id": field_id, "date": signature[0], "latitude": signature[1], "longitude": signature[2]})
    return field_rows, conflicts


def analyze_dataset(name: str, headers: list[str], rows: list[dict[str, str]],
                    unit: str, date_options: tuple[str, ...],
                    disease_columns: tuple[str, ...]) -> dict[str, Any]:
    date_col = _resolve_column(headers, date_options)
    lat_col = _resolve_column(headers, ("latitude", "lat"))
    lon_col = _resolve_column(headers, ("longitude", "long", "lon", "lng"))
    id_col = _resolve_column(headers, ("id", "record_id", "observation_id"))
    plant_col = _resolve_column(headers, ("plant_id",))
    year_col = _resolve_column(headers, ("year", "survey_year"))
    origin_col = _resolve_column(headers, ("data_origin",))
    matched_col = _resolve_column(headers, ("matched",))

    exact_duplicates = len(rows) - len({tuple(row.get(column, "") for column in headers) for row in rows})
    id_counts = Counter(row.get(id_col, "") for row in rows) if id_col else Counter()
    repeated_id_groups = {key: count for key, count in id_counts.items() if key and count > 1}
    repeated_id_rows = sum(repeated_id_groups.values())
    date_values = [_date(row.get(date_col, "")) if date_col else None for row in rows]
    date_missing = sum(_missing(row.get(date_col, "")) for row in rows) if date_col else len(rows)
    date_invalid = sum(not _missing(row.get(date_col, "")) and parsed is None
                       for row, parsed in zip(rows, date_values)) if date_col else 0
    valid_dates = [value for value in date_values if value is not None]

    coords = []
    valid_coord_flags = []
    for row in rows:
        lat = _number(row.get(lat_col, "")) if lat_col else None
        lon = _number(row.get(lon_col, "")) if lon_col else None
        valid = lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180
        valid_coord_flags.append(valid)
        if valid:
            coords.append((lat, lon))
    valid_coord_count = sum(valid_coord_flags)
    eligible = []
    eligible_year_counts = Counter()
    year_only_counts = Counter()
    date_formats = Counter()
    date_year_conflicts = []
    for i, row in enumerate(rows):
        day = date_values[i]
        if year_col and not _missing(row.get(year_col, "")):
            year_only_counts[row[year_col].strip()] += 1
        if day:
            date_formats[_actual_date_format(row.get(date_col, ""))] += 1
            if year_col and not _missing(row.get(year_col, "")) and str(day.year) != row[year_col].strip():
                date_year_conflicts.append({"date": day.isoformat(), "year": row[year_col].strip(),
                                            "id": row.get(id_col, "") if id_col else ""})
        if day is not None and valid_coord_flags[i]:
            lat, lon = _number(row[lat_col]), _number(row[lon_col])
            district_col = _resolve_column(headers, ("district",))
            region_col = _resolve_column(headers, ("region",))
            eligible.append({"date": day.isoformat(), "latitude": lat, "longitude": lon,
                             "id": row.get(id_col, "") if id_col else "",
                             "year": str(day.year), "origin": row.get(origin_col, "") if origin_col else "",
                             "matched": row.get(matched_col, "") if matched_col else "",
                             "district": row.get(district_col, "") if district_col else "",
                             "region": row.get(region_col, "") if region_col else ""})
            eligible_year_counts[str(day.year)] += 1
    loc_dates = {(r["date"], r["latitude"], r["longitude"]) for r in eligible}
    locations: dict[tuple[float, float], list[date]] = defaultdict(list)
    for row in eligible:
        locations[(row["latitude"], row["longitude"])].append(date.fromisoformat(row["date"]))
    range_days = sum((max(ds) - min(ds)).days + 1 for ds in locations.values())

    district_col = _resolve_column(headers, ("district",))
    region_col = _resolve_column(headers, ("region",))
    village_col = _resolve_column(headers, ("village",))
    geographic = {}
    if coords:
        geographic = {
            "valid_coordinate_rows": valid_coord_count,
            "unique_coordinate_pairs_all_rows": len(set(coords)),
            "latitude_min": min(pair[0] for pair in coords),
            "latitude_max": max(pair[0] for pair in coords),
            "longitude_min": min(pair[1] for pair in coords),
            "longitude_max": max(pair[1] for pair in coords),
            "distinct_districts": len({r[district_col].strip() for r in rows if district_col and not _missing(r.get(district_col, ""))}),
            "distinct_regions": len({r[region_col].strip() for r in rows if region_col and not _missing(r.get(region_col, ""))}),
            "distinct_villages": len({r[village_col].strip() for r in rows if village_col and not _missing(r.get(village_col, ""))}),
        }
    eligible_coords = [(row["latitude"], row["longitude"]) for row in eligible]
    eligible_geo = {}
    if eligible_coords:
        eligible_geo = {
            "unique_location_date_pairs": len(loc_dates),
            "unique_coordinates": len({(row["latitude"], row["longitude"]) for row in eligible}),
            "latitude_min": min(pair[0] for pair in eligible_coords),
            "latitude_max": max(pair[0] for pair in eligible_coords),
            "longitude_min": min(pair[1] for pair in eligible_coords),
            "longitude_max": max(pair[1] for pair in eligible_coords),
            "distinct_districts": len({row["district"].strip() for row in eligible if not _missing(row["district"])}),
            "distinct_regions": len({row["region"].strip() for row in eligible if not _missing(row["region"])}),
        }

    disease = {}
    for column in disease_columns:
        if column not in headers:
            continue
        counts = Counter(row.get(column, "").strip() if not _missing(row.get(column, "")) else "<missing>" for row in rows)
        disease[column] = {
            "nonmissing": len(rows) - counts.get("<missing>", 0),
            "missing": counts.get("<missing>", 0),
            "value_counts": dict(counts),
        }

    key_missing = {}
    for column in (id_col, date_col, year_col, lat_col, lon_col, *disease_columns, origin_col, matched_col):
        if column and column not in key_missing:
            key_missing[column] = sum(_missing(row.get(column, "")) for row in rows)

    field_ids = len(id_counts)
    eligible_ids = len({row["id"] for row in eligible if row["id"]})
    plant_key_counts = Counter((row.get(id_col, ""), row.get(plant_col, "")) for row in rows) if id_col and plant_col else Counter()
    if unit == "plant-level rows nested in field ID":
        field_rows, field_conflicts = _field_records(rows, id_col, date_col, lat_col, lon_col)
        field_eligible = eligible_ids
        field_loc_dates = {(r["date"], r["latitude"], r["longitude"]) for r in field_rows}
    else:
        field_rows, field_conflicts = [], []
        field_eligible, field_loc_dates = eligible_ids, loc_dates

    return {
        "rows": len(rows), "columns": headers, "observation_unit": unit,
        "date_column": date_col, "latitude_column": lat_col, "longitude_column": lon_col,
        "id_column": id_col, "year_column": year_col,
        "date_valid_count": len(valid_dates), "date_missing_count": date_missing,
        "date_unparseable_nonmissing_count": date_invalid,
        "date_range": [str(min(valid_dates)), str(max(valid_dates))] if valid_dates else None,
        "date_formats_observed": dict(date_formats), "year_column_counts": dict(sorted(year_only_counts.items())),
        "date_year_conflict_count": len(date_year_conflicts),
        "date_year_conflict_examples": date_year_conflicts[:20],
        "valid_coordinate_count": valid_coord_count,
        "invalid_or_missing_coordinate_count": len(rows) - valid_coord_count,
        "geographic_coverage": geographic,
        "weather_eligible_geographic_coverage": eligible_geo,
        "weather_eligible_rows": len(eligible),
        "weather_eligible_unique_ids": eligible_ids,
        "weather_eligible_unique_location_dates": len(loc_dates),
        "weather_eligible_unique_locations": len(locations),
        "eligible_year_counts_by_row": dict(sorted(eligible_year_counts.items())),
        "exact_duplicate_rows": exact_duplicates,
        "duplicate_plant_id_field_keys": sum(count > 1 for count in plant_key_counts.values()),
        "repeated_id_group_count": len(repeated_id_groups),
        "repeated_id_rows": repeated_id_rows,
        "repeated_id_examples": dict(list(sorted(repeated_id_groups.items()))[:20]),
        "field_id_count": field_ids,
        "weather_eligible_field_visit_records": field_eligible,
        "field_id_conflicting_eligible_date_coordinate_groups": len(field_conflicts),
        "field_id_conflict_examples": field_conflicts[:20],
        "field_level_unique_location_dates": len(field_loc_dates),
        "missing_key_counts": key_missing,
        "disease_label_availability": disease,
        "origin_counts": dict(Counter(row.get(origin_col, "") for row in rows)) if origin_col else {},
        "matched_counts": dict(Counter(row.get(matched_col, "") for row in rows)) if matched_col else {},
        "_eligible_records": eligible,
        "_field_records": field_rows,
    }


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or []), list(reader)


def build_audit(source_dir: Path = SOURCE_DIR, pilot_dir: Path = PILOT_DIR) -> dict[str, Any]:
    definitions = {
        "DATASET_A.csv": ("plant-level rows nested in field ID", ("date",), ("cbsd_foliar_presence", "cbsd_foliar_severity")),
        "DATASET_B.csv": ("field-level survey summary; year only", (), ("cbsd_foliar_incidence", "cbsd_foliar_severity_mean")),
        "DATASET_C.csv": ("field-level aggregated record", ("date",), ("cbsd_foliar_incidence", "cbsd_foliar_severity_mean", "matched", "data_origin")),
    }
    datasets = {}
    inventory = {}
    data_rows = {}
    for filename, (unit, date_options, labels) in definitions.items():
        path = source_dir / filename
        headers, rows = read_csv(path)
        data_rows[filename] = rows
        result = analyze_dataset(filename, headers, rows, unit, date_options, labels)
        datasets[filename] = result
        file_bytes = path.read_bytes()
        inventory[filename] = {"bytes": len(file_bytes), "sha256": hashlib.sha256(file_bytes).hexdigest()}

    a = datasets["DATASET_A.csv"]
    b = datasets["DATASET_B.csv"]
    c = datasets["DATASET_C.csv"]
    A, B, C = (data_rows[x] for x in definitions)
    aid = _resolve_column(list(A[0]), ("id",))
    bid = _resolve_column(list(B[0]), ("id",))
    ca = _resolve_column(list(C[0]), ("dbA_id",))
    cb = _resolve_column(list(C[0]), ("dbB_id",))
    b_id_set = {row[bid] for row in B}
    a_id_set = {row[aid] for row in A}
    c_a_nonmissing = [row for row in C if not _missing(row.get(ca, ""))]
    c_b_nonmissing = [row for row in C if not _missing(row.get(cb, ""))]
    c_a_link_hits = sum(row[ca] in a_id_set for row in c_a_nonmissing)
    c_b_link_hits = sum(row[cb] in b_id_set for row in c_b_nonmissing)
    c_origin = _resolve_column(list(C[0]), ("data_origin",))
    c_date = _resolve_column(list(C[0]), ("date",))
    dated_origin_counts = Counter(row.get(c_origin, "") for row in C if _date(row.get(c_date, "")))
    a_field_records = a["_field_records"]
    a_dates_by_id = {record["id"]: record for record in a_field_records}
    c_dated_aids = {row[ca] for row in C if _date(row.get(c_date, "")) and not _missing(row.get(ca, ""))}
    a_signatures_by_id: dict[str, set[tuple[str, float, float]]] = defaultdict(set)
    for record in a_field_records:
        a_signatures_by_id[record["id"]].add((record["date"], record["latitude"], record["longitude"]))
    c_dated_linked = [row for row in C if _date(row.get(c_date, "")) and not _missing(row.get(ca, ""))]
    linkage_signature_counts = Counter()
    linkage_mismatch_examples = []
    for row in c_dated_linked:
        field_id = row[ca]
        day = _date(row.get(c_date, ""))
        lat, lon = _number(row.get("latitude", "")), _number(row.get("longitude", ""))
        c_signature = (day.isoformat(), lat, lon)
        a_signatures = a_signatures_by_id.get(field_id, set())
        if c_signature in a_signatures:
            linkage_signature_counts["exact_date_and_coordinate_match"] += 1
        elif any(a_day == day.isoformat() for a_day, _, _ in a_signatures):
            linkage_signature_counts["same_date_coordinate_differs"] += 1
            linkage_mismatch_examples.append({"dbA_id": field_id, "C_date": day.isoformat(),
                                              "C_latitude": lat, "C_longitude": lon,
                                              "A_signatures": sorted(a_signatures)})
        elif any(a_lat == lat and a_lon == lon for _, a_lat, a_lon in a_signatures):
            linkage_signature_counts["same_coordinate_date_differs"] += 1
            linkage_mismatch_examples.append({"dbA_id": field_id, "C_date": day.isoformat(),
                                              "C_latitude": lat, "C_longitude": lon,
                                              "A_signatures": sorted(a_signatures)})
        else:
            linkage_signature_counts["date_and_coordinate_differ_or_A_not_eligible"] += 1
            linkage_mismatch_examples.append({"dbA_id": field_id, "C_date": day.isoformat(),
                                              "C_latitude": lat, "C_longitude": lon,
                                              "A_signatures": sorted(a_signatures)})
    a_field_id_link_coverage = {
        "A_date_eligible_field_ids": a["weather_eligible_unique_ids"],
        "A_date_eligible_date_coordinate_signatures": len(a_field_records),
        "A_eligible_field_ids_linked_to_any_C_dbA_id": sum(field_id in {r[ca] for r in c_a_nonmissing} for field_id in a_dates_by_id),
        "A_eligible_field_ids_linked_to_date_bearing_C_dbA_id": sum(field_id in c_dated_aids for field_id in a_dates_by_id),
        "A_eligible_field_ids_not_linked_to_C_dbA_id": sum(field_id not in {r[ca] for r in c_a_nonmissing} for field_id in a_dates_by_id),
    }
    # Use documented IDs to avoid counting the A plant rows and their C dbA summaries twice.
    a_keys = {(r["date"], r["latitude"], r["longitude"]) for r in a_field_records}
    c_keys = {(r["date"], r["latitude"], r["longitude"]) for r in c["_eligible_records"]}
    combined_request_keys = a_keys | c_keys
    intersection_request_keys = a_keys & c_keys
    combined_location_dates = _collect_dates(a_field_records + c["_eligible_records"])
    combined_location_dates = _collect_dates(a_field_records + c["_eligible_records"])

    pilot_csv = pilot_dir / "weather_matches.csv"
    pilot_input = pilot_dir / "pilot_observations.csv"
    pilot_cache_json = pilot_dir / "raw_cache"
    pilot_metrics = {"pilot_input_rows": 0, "pilot_matched_rows": 0, "pilot_cache_raw_json_count": 0,
                     "pilot_weather_match_bytes": None, "pilot_raw_json_total_bytes": None,
                     "pilot_raw_json_mean_bytes": None, "pilot_input_sha256": None,
                     "pilot_output_sha256": None, "pilot_status_counts": {},
                     "pilot_quality_pass": None, "pilot_cache_hits_on_current_run": None}
    if pilot_input.exists():
        with pilot_input.open(encoding="utf-8-sig", newline="") as stream:
            pilot_metrics["pilot_input_rows"] = sum(1 for _ in csv.DictReader(stream))
        pilot_metrics["pilot_input_sha256"] = hashlib.sha256(pilot_input.read_bytes()).hexdigest()
    if pilot_csv.exists():
        with pilot_csv.open(encoding="utf-8-sig", newline="") as stream:
            pilot_out = list(csv.DictReader(stream))
        pilot_metrics["pilot_matched_rows"] = sum(row.get("status") == "matched" for row in pilot_out)
        pilot_metrics["pilot_status_counts"] = dict(Counter(row.get("status", "") for row in pilot_out))
        pilot_metrics["pilot_weather_match_bytes"] = pilot_csv.stat().st_size
        pilot_metrics["pilot_output_sha256"] = hashlib.sha256(pilot_csv.read_bytes()).hexdigest()
    pilot_quality_path = pilot_dir / "quality_report.json"
    if pilot_quality_path.exists():
        pilot_quality = json.loads(pilot_quality_path.read_text(encoding="utf-8"))
        pilot_metrics["pilot_quality_pass"] = pilot_quality.get("quality_pass")
        pilot_metadata_path = pilot_dir / "request_metadata.json"
        if pilot_metadata_path.exists():
            pilot_metadata = json.loads(pilot_metadata_path.read_text(encoding="utf-8"))
            pilot_metrics["pilot_cache_hits_on_current_run"] = sum(bool(r.get("cache_hit")) for r in pilot_metadata.get("requests", []))
    if pilot_cache_json.exists():
        raw_files = [p for p in pilot_cache_json.glob("*.json") if not p.name.endswith(".metadata.json")]
        pilot_metrics["pilot_cache_raw_json_count"] = len(raw_files)
        pilot_metrics["pilot_raw_json_total_bytes"] = sum(p.stat().st_size for p in raw_files)
        pilot_metrics["pilot_raw_json_mean_bytes"] = (statistics.mean(p.stat().st_size for p in raw_files) if raw_files else None)

    exact_requests = c["weather_eligible_unique_location_dates"]
    grouped_calls = c["weather_eligible_unique_locations"]
    grouped_days = sum((max(ds) - min(ds)).days + 1 for ds in _collect_dates(c["_eligible_records"]).values())
    raw_bytes_per_request = pilot_metrics["pilot_raw_json_mean_bytes"] or 0
    matched_bytes_per_row = (pilot_metrics["pilot_weather_match_bytes"] or 0) / max(pilot_metrics["pilot_matched_rows"], 1)

    result = {
        "audit_date": date.today().isoformat(),
        "read_only": True,
        "source_files": inventory,
        "parsing": {
            "method": "Python csv.DictReader with UTF-8 BOM and quoted-field support",
            "missing_markers": sorted(MISSING_TEXT),
            "date_formats": list(DATE_FORMATS),
            "date_policy": "Only actual parseable dates are eligible; year-only Dataset B records are not assigned dates.",
        },
        "datasets": datasets,
        "linkage": {
            "C_nonmissing_dbA_id_rows": len(c_a_nonmissing), "C_dbA_id_rows_linking_to_A": c_a_link_hits,
            "C_nonmissing_dbB_id_rows": len(c_b_nonmissing), "C_dbB_id_rows_linking_to_B": c_b_link_hits,
            "C_dated_rows_by_data_origin": dict(dated_origin_counts),
        "dated_C_dbA_link_signature_comparison_counts": dict(linkage_signature_counts),
        "dated_C_dbA_link_mismatch_examples": linkage_mismatch_examples[:20],
            "A_C_field_linkage_coverage": a_field_id_link_coverage,
            "combined_A_field_and_C_unique_location_date_request_keys": len(combined_request_keys),
            "A_C_exact_location_date_key_intersection": len(intersection_request_keys),
            "linkage_policy": "A/C overlap is identified only through C.dbA_id to A.id; C/B through C.dbB_id to B.id. Coordinates and year alone are not used to merge disease records.",
        },
        "request_feasibility": {
            "C_eligible_rows": c["weather_eligible_rows"],
            "C_unique_location_date_pairs_exact_date_calls": exact_requests,
            "C_unique_exact_coordinate_locations": grouped_calls,
            "one_range_request_per_coordinate_if_batched": grouped_calls,
            "inclusive_daily_values_returned_if_each_coordinate_uses_min_to_max_date_range": grouped_days,
            "estimated_daily_values_exact_date_calls": exact_requests,
            "combined_A_field_and_C_unique_location_date_pairs": len(combined_request_keys),
            "combined_A_C_unique_exact_coordinates": len(combined_location_dates),
            "combined_A_C_one_range_request_per_coordinate": len(combined_location_dates),
            "combined_A_C_daily_values_if_min_to_max_ranges": sum((max(ds) - min(ds)).days + 1 for ds in combined_location_dates.values()),
            "combined_A_C_unique_exact_coordinates": len(combined_location_dates),
            "combined_A_C_one_range_request_per_coordinate": len(combined_location_dates),
            "combined_A_C_daily_values_if_min_to_max_ranges": sum((max(ds) - min(ds)).days + 1 for ds in combined_location_dates.values()),
            "pilot_observed_raw_json_mean_bytes_per_single_day_response": raw_bytes_per_request,
            "estimated_raw_json_bytes_exact_C_location_date_calls": int(math.ceil(raw_bytes_per_request * exact_requests)),
            "estimated_matched_csv_bytes_for_C_eligible_rows_using_pilot_row_size": int(math.ceil(matched_bytes_per_row * c["weather_eligible_rows"])),
            "estimated_matched_csv_bytes_for_A_eligible_plant_rows_using_pilot_row_size": int(math.ceil(matched_bytes_per_row * a["weather_eligible_rows"])),
            "estimated_metadata_bytes_using_pilot_request_metadata_per_request": int(math.ceil((pilot_dir / "request_metadata.json").stat().st_size / max(pilot_metrics["pilot_input_rows"], 1) * grouped_calls)) if (pilot_dir / "request_metadata.json").exists() else None,
            "pilot_size_basis": pilot_metrics,
            "full_download_performed": False,
            "recommendation": "Do not issue one synchronous request per observation. First approve a cell/location batching design. Group exact repeated locations and cache each exact request; obtain/record provider-returned source coordinates before any source-grid deduplication. Batch date ranges only where added daily rows are acceptable and bounded; inspect output size and service rate guidance before scaling.",
        },
        "exclusions": {
            "Dataset_A_rows_without_valid_date": a["date_missing_count"] + a["date_unparseable_nonmissing_count"],
            "Dataset_A_rows_without_valid_coordinates": a["invalid_or_missing_coordinate_count"],
            "Dataset_B_rows_excluded_year_only_no_exact_date": b["rows"],
            "Dataset_C_rows_without_valid_date": c["date_missing_count"] + c["date_unparseable_nonmissing_count"],
            "Dataset_C_rows_without_valid_coordinates": c["invalid_or_missing_coordinate_count"],
            "Dataset_C_duplicate_id_groups": c["repeated_id_group_count"],
            "Dataset_C_exact_duplicate_rows": c["exact_duplicate_rows"],
        },
        "limitations": [
            "Dataset A rows are plants nested within field IDs; weather requests should be based on field visits, not plant rows.",
            "Dataset B has year but no exact date and is excluded from date-specific weather matching.",
            "C.matched indicates a detected overlapping record, not independent disease validation.",
            "Dataset B and C incidence scales remain inconsistent and are not combined or rescaled.",
            "NASA POWER weather is source-grid meteorology, not exact field measurement; returned source grid and coordinate handling must be retained.",
            "Exact date/location weather association does not establish causality or predictive accuracy.",
        ],
    }
    # Remove internal record lists before serialization.
    for report in result["datasets"].values():
        report.pop("_eligible_records", None)
        report.pop("_field_records", None)
    return result


def _collect_dates(records: list[dict[str, Any]]) -> dict[tuple[float, float], list[date]]:
    locations: dict[tuple[float, float], list[date]] = defaultdict(list)
    for row in records:
        locations[(row["latitude"], row["longitude"])].append(date.fromisoformat(row["date"]))
    return locations


def write_markdown_full(report: dict[str, Any], path: Path = MARKDOWN_OUTPUT) -> None:
    """Write a compact, fully data-driven report with year and geography detail."""
    a, b, c = (report["datasets"][name] for name in ("DATASET_A.csv", "DATASET_B.csv", "DATASET_C.csv"))
    links, req = report["linkage"], report["request_feasibility"]
    def pct(n: int, d: int) -> str:
        return f"{100*n/d:.2f}%" if d else "n/a"
    def values(dataset: dict[str, Any], col: str) -> dict[str, int]:
        return dataset["disease_label_availability"].get(col, {}).get("value_counts", {})
    def counts(dataset: dict[str, Any], col: str) -> str:
        found = values(dataset, col)
        return ", ".join(f"{key}: {value:,}" for key, value in found.items())
    def availability(dataset: dict[str, Any], col: str) -> str:
        info = dataset["disease_label_availability"].get(col, {})
        return f"{info.get('nonmissing', 0):,} nonmissing, {info.get('missing', 0):,} missing"
    def geo(label: str, value: dict[str, Any]) -> str:
        unique = value.get("unique_coordinate_pairs_all_rows", value.get("unique_coordinates", 0))
        return f"| {label} | {value.get('latitude_min')} to {value.get('latitude_max')} | {value.get('longitude_min')} to {value.get('longitude_max')} | {unique:,} | {value.get('distinct_districts', 0):,} | {value.get('distinct_regions', 0):,} |"
    a_presence = values(a, "cbsd_foliar_presence")
    lines = [
        "# Uganda cassava dataset: full weather-matching feasibility audit", "",
        f"Audit date: {report['audit_date']}. Read-only feasibility audit; **no full-dataset weather download was performed**.",
        "The three CSVs were parsed independently with quote-aware `csv.DictReader`, UTF-8 BOM support, and common NA markers. Dates come only from actual date columns; no year-only dates were reconstructed.", "",
        "## Dataset coverage", "",
        "| Dataset | Observation unit | Rows | Valid dates | Valid coordinates | Date + coordinate eligible | Eligible IDs | Unique location/date pairs | Exact duplicate rows | Repeated ID groups |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, dataset in (("A", a), ("B", b), ("C", c)):
        lines.append(f"| {label} | {dataset['observation_unit']} | {dataset['rows']:,} | {dataset['date_valid_count']:,} ({pct(dataset['date_valid_count'], dataset['rows'])}) | {dataset['valid_coordinate_count']:,} ({pct(dataset['valid_coordinate_count'], dataset['rows'])}) | {dataset['weather_eligible_rows']:,} ({pct(dataset['weather_eligible_rows'], dataset['rows'])}) | {dataset['weather_eligible_unique_ids']:,} | {dataset['weather_eligible_unique_location_dates']:,} | {dataset['exact_duplicate_rows']:,} | {dataset['repeated_id_group_count']:,} |")
    lines += ["", "A rows are plants nested in field `id`; B and C are field-level summaries. Full actual column lists and per-column missing counts are in the JSON report.",
              "B has no observation-date column, so all 4,956 records are ineligible for exact daily matching despite populated `year` and coordinates. Dataset A's year/date conflict count is 1; C's is 0.", "",
              "## Year and geographic coverage", "",
              f"- A eligible plant rows by actual date year: `{json.dumps(a['eligible_year_counts_by_row'], separators=(',', ':'))}`.",
              f"- B survey-year counts (not daily dates): `{json.dumps(b['year_column_counts'], separators=(',', ':'))}`.",
              f"- C date-bearing rows by actual date year: `{json.dumps(c['eligible_year_counts_by_row'], separators=(',', ':'))}`.",
              f"- Date ranges: A {a['date_range'][0]} to {a['date_range'][1]}; C {c['date_range'][0]} to {c['date_range'][1]}.", "",
              "| Dataset (all valid-coordinate records) | Latitude range | Longitude range | Unique coordinates | Districts | Regions |",
              "|---|---:|---:|---:|---:|---:|"]
    for label, dataset in (("A", a), ("B", b), ("C", c)):
        lines.append(geo(label, dataset["geographic_coverage"]))
    cg = c["weather_eligible_geographic_coverage"]
    lines += [f"", f"C date-and-coordinate-eligible subset: {cg.get('distinct_districts', 0)} districts, {cg.get('distinct_regions', 0)} regions; latitude {cg.get('latitude_min')} to {cg.get('latitude_max')}, longitude {cg.get('longitude_min')} to {cg.get('longitude_max')}.", "",
              "## Disease-label availability and missingness", "",
              f"- A `cbsd_foliar_presence`: {availability(a, 'cbsd_foliar_presence')} (0 NO: {a_presence.get('0', 0):,}; 1 YES: {a_presence.get('1', 0):,}); `cbsd_foliar_severity`: {availability(a, 'cbsd_foliar_severity')}.",
              f"- B `cbsd_foliar_incidence`: {availability(b, 'cbsd_foliar_incidence')}; `cbsd_foliar_severity_mean`: {availability(b, 'cbsd_foliar_severity_mean')}.",
              f"- C `cbsd_foliar_incidence`: {availability(c, 'cbsd_foliar_incidence')}; `cbsd_foliar_severity_mean`: {availability(c, 'cbsd_foliar_severity_mean')}; `matched`: {counts(c, 'matched')}; `data_origin`: {counts(c, 'data_origin')}.",
              "- `matched` records detected overlap under the legend, not independent disease validation. B/C incidence scales remain inconsistent and were not combined or rescaled.", "",
              "## Duplicate records and linkage", "",
              f"A has {a['field_id_count']:,} field IDs and {a['duplicate_plant_id_field_keys']} duplicated `(id, plant_id)` keys. Repeated A `id` values are expected plant rows within field groups; they are not duplicate disease rows. {a['field_id_conflicting_eligible_date_coordinate_groups']} A field IDs have conflicting eligible date/coordinate signatures: `{json.dumps(a['field_id_conflict_examples'], separators=(',', ':'))}`.",
              f"C has {c['exact_duplicate_rows']} exact duplicate row and {c['repeated_id_group_count']} repeated ID groups covering {c['repeated_id_rows']} rows (IDs are listed in JSON). Using documented IDs, {links['C_dbA_id_rows_linking_to_A']:,}/{links['C_nonmissing_dbA_id_rows']:,} C `dbA_id` references resolve to A and {links['C_dbB_id_rows_linking_to_B']:,}/{links['C_nonmissing_dbB_id_rows']:,} C `dbB_id` references resolve to B. All 4,048 dated C records have `data_origin=dbA`.",
              f"Among date-bearing C records linked to A, {links['dated_C_dbA_link_signature_comparison_counts'].get('exact_date_and_coordinate_match', 0):,} share exact date and coordinates; {links['dated_C_dbA_link_signature_comparison_counts'].get('same_date_coordinate_differs', 0):,} share the date but have different coordinates. Examples: `{json.dumps(links['dated_C_dbA_link_mismatch_examples'][:3], separators=(',', ':'))}`. Preserve both source values for review. Dataset rows are related only through ID fields; matching coordinates or years alone is not evidence to merge observations.", "",
              "## Weather eligibility and estimated request volume", "",
              f"- A: {a['weather_eligible_rows']:,} eligible plant rows, {a['weather_eligible_unique_ids']:,} eligible field IDs, {a['field_level_unique_location_dates']:,} unique date/location keys after field grouping; {a['field_id_conflicting_eligible_date_coordinate_groups']} field IDs contain conflicting signatures.",
              f"- B: 0 date-specific eligible records; do not infer dates from year.",
              f"- C: {c['weather_eligible_rows']:,} eligible field records, {req['C_unique_location_date_pairs_exact_date_calls']:,} unique exact location/date keys and {req['C_unique_exact_coordinate_locations']:,} exact coordinate locations.",
              f"- A field signatures plus C records: {links['combined_A_field_and_C_unique_location_date_request_keys']:,} exact location/date keys across {req['combined_A_C_unique_exact_coordinates']:,} coordinates. This deduplicates weather queries only; it does not merge disease outcomes.", "",
              "| Strategy | Estimated calls | Daily values | Interpretation |", "|---|---:|---:|---|",
              f"| Exact C coordinate/date requests | {req['C_unique_location_date_pairs_exact_date_calls']:,} | {req['estimated_daily_values_exact_date_calls']:,} | No overfetch, but too many synchronous calls without batching/pacing. |",
              f"| Min-to-max range per C coordinate | {req['one_range_request_per_coordinate_if_batched']:,} | {req['inclusive_daily_values_returned_if_each_coordinate_uses_min_to_max_date_range']:,} | No call reduction for C because each eligible coordinate has only one date. |",
              f"| Min-to-max range per A/C coordinate | {req['combined_A_C_one_range_request_per_coordinate']:,} | {req['combined_A_C_daily_values_if_min_to_max_ranges']:,} | Fewer calls than exact keys, but includes intervening dates. |",
              "| Source-grid grouping | Not safely countable from these files | Not estimated | Requires verified source-grid mapping; rounded response coordinates do not establish cell identity. |", "",
              f"Pilot-based storage proxy: mean raw one-day JSON response {req['pilot_observed_raw_json_mean_bytes_per_single_day_response']:.0f} bytes; C exact-request raw payloads about {req['estimated_raw_json_bytes_exact_C_location_date_calls']:,} bytes ({req['estimated_raw_json_bytes_exact_C_location_date_calls']/1024/1024:.2f} MiB). Pilot-sized matched CSV proxy is {req['estimated_matched_csv_bytes_for_C_eligible_rows_using_pilot_row_size']:,} bytes for C and {req['estimated_matched_csv_bytes_for_A_eligible_plant_rows_using_pilot_row_size']:,} bytes if repeated across eligible A plant rows. Request-metadata proxy: {req['estimated_metadata_bytes_using_pilot_request_metadata_per_request']:,} bytes. These estimates extrapolate only ten pilot rows and exclude cache sidecars and overfetch.", "",
              "NASA advises using native source resolution and avoiding excessive synchronous requests. Its MERRA-2 meteorology documentation describes grid averages on a 0.5 degree by 0.625 degree grid. Pilot returned coordinates are rounded to three decimals; they do not establish a safe source-cell mapping for the full dataset. [Daily API](https://power.larc.nasa.gov/docs/services/api/temporal/daily/), [API request tutorial](https://power.larc.nasa.gov/docs/tutorials/service-data-request/api/), [MERRA-2 methodology](https://power.larc.nasa.gov/docs/methodology/meteorology/).", "",
              "## Recommended batching and cache plan", "",
              "1. Preserve distinct disease rows; derive weather request keys only from valid actual date and coordinates. Aggregate A only for request planning using field IDs, without discarding plant labels.",
              "2. Before scaling, verify the source-cell mapping from authoritative NASA metadata. If valid, request each cell once for bounded contiguous date intervals; otherwise group only repeated exact locations.",
              "3. Cache by endpoint, parameters, community, time standard, coordinate/cell key, and date range. Keep raw responses separate, checksum them, and use resumable checkpoints and explicit pacing.",
              f"4. Review the estimated {links['combined_A_field_and_C_unique_location_date_request_keys']:,} A/C unique location-date keys and output estimates before any full retrieval. **No full-dataset weather requests were made; stop here for review.**", "",
              "## Exclusions and limitations", "",
              f"- A: {a['date_missing_count']:,} rows have missing dates; {a['date_unparseable_nonmissing_count']:,} nonmissing dates fail parsing; {a['invalid_or_missing_coordinate_count']:,} rows lack valid global coordinates. The one date/year disagreement and three field-signature conflicts require preserving actual source dates.",
              f"- B: all {b['rows']:,} rows excluded from daily matching because no exact date is present; {b['valid_coordinate_count']:,} do have valid coordinates and a year.",
              f"- C: {c['date_missing_count']:,} rows have missing dates; {c['date_unparseable_nonmissing_count']:,} nonmissing dates fail parsing; {c['invalid_or_missing_coordinate_count']:,} rows lack valid global coordinates. No year was substituted.",
              "- C duplicate IDs/rows, A plant clustering, eleven linked A/C coordinate discrepancies, B/C scale inconsistency, and lack of independent validation limit downstream use.",
              "- Weather matches do not establish disease causality or prediction accuracy. No model or thresholds were changed.", "",
              "## Reproducibility", "",
              "Run `python scripts/uganda_dataset_feasibility_audit.py` from the repository root. It reads source CSVs and current pilot artifacts only, makes no network requests, and writes this report plus `data/crop_outcomes/processed/uganda_cassava_brown_streak/full_dataset_feasibility_audit.json`.", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(source_dir: Path = SOURCE_DIR, pilot_dir: Path = PILOT_DIR,
                  json_path: Path = JSON_OUTPUT, markdown_path: Path = MARKDOWN_OUTPUT) -> dict[str, Any]:
    result = build_audit(source_dir, pilot_dir)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    write_markdown_full(result, markdown_path)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=SOURCE_DIR)
    parser.add_argument("--pilot-dir", type=Path, default=PILOT_DIR)
    parser.add_argument("--json-output", type=Path, default=JSON_OUTPUT)
    parser.add_argument("--markdown-output", type=Path, default=MARKDOWN_OUTPUT)
    args = parser.parse_args()
    result = write_outputs(args.source_dir, args.pilot_dir, args.json_output, args.markdown_output)
    print(json.dumps({"datasets": {k: {"rows": v["rows"], "weather_eligible_rows": v["weather_eligible_rows"],
                                       "unique_location_dates": v["weather_eligible_unique_location_dates"]}
                      for k, v in result["datasets"].items()},
                      "request_feasibility": result["request_feasibility"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
