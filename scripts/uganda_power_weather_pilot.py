"""Fetch and match NASA POWER daily weather for the 10-row Uganda pilot.

Run from the repository root with ``python scripts/uganda_power_weather_pilot.py``.
The script only reads the pilot observation CSV and writes into its weather_pilot
directory; successful NASA responses are cached separately from matched output.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
PILOT_DIR = ROOT / "data/crop_outcomes/processed/uganda_cassava_brown_streak/weather_pilot"
INPUT_CSV = PILOT_DIR / "pilot_observations.csv"
ENDPOINT = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMETERS = ("T2M", "PRECTOTCORR", "RH2M")
COMMUNITY = "AG"
TIME_STANDARD = "LST"
DEFAULT_FILL_VALUES = {-999.0}
MISSING_TEXT = {"", "NA", "N/A", "NaN", "nan", "NULL", "null", "-", "--"}


class PowerApiError(RuntimeError):
    """A NASA POWER network, HTTP, JSON, or API response error."""


def parse_observation_date(value: str) -> date | None:
    value = (value or "").strip()
    if value in MISSING_TEXT:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%m/%d/%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def resolve_columns(fieldnames: list[str] | None) -> dict[str, str]:
    """Resolve known schema aliases from the actual CSV header."""
    if not fieldnames:
        raise ValueError("Input CSV has no header")
    aliases = {
        "id": ("id", "record_id", "observation_id"),
        "date": ("date", "observation_date", "survey_date"),
        "latitude": ("latitude", "lat"),
        "longitude": ("longitude", "long", "lon", "lng"),
    }
    actual = {name.strip().lower(): name for name in fieldnames}
    resolved = {}
    for logical, options in aliases.items():
        match = next((actual[x] for x in options if x in actual), None)
        if match is None:
            raise ValueError(f"Input CSV is missing a {logical} column; headers={fieldnames!r}")
        resolved[logical] = match
    return resolved


def build_request_url(latitude: float, longitude: float, start: date, end: date) -> str:
    params = {
        "parameters": ",".join(PARAMETERS),
        "community": COMMUNITY,
        "longitude": format(longitude, ".10g"),
        "latitude": format(latitude, ".10g"),
        "start": start.strftime("%Y%m%d"),
        "end": end.strftime("%Y%m%d"),
        "format": "JSON",
        "time-standard": TIME_STANDARD,
    }
    return f"{ENDPOINT}?{urllib.parse.urlencode(params)}"


def fetch_json(url: str, timeout: float = 60) -> tuple[dict[str, Any], int]:
    request = urllib.request.Request(url, headers={"User-Agent": "CropAI-UgandaWeatherPilot/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
            body = response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:1000]
        raise PowerApiError(f"NASA POWER HTTP {exc.code}: {body}") from None
    except urllib.error.URLError as exc:
        raise PowerApiError(f"NASA POWER connection failed: {exc.reason}") from None
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PowerApiError(f"NASA POWER returned malformed JSON: {exc}") from None
    if status != 200:
        raise PowerApiError(f"NASA POWER HTTP {status}")
    if not isinstance(payload, dict):
        raise PowerApiError("NASA POWER response JSON is not an object")
    return payload, status


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _valid_coordinate(value: str, lower: float, upper: float) -> float | None:
    if value is None or value.strip() in MISSING_TEXT:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and lower <= number <= upper else None


def _response_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
    geometry = payload.get("geometry") if isinstance(payload.get("geometry"), dict) else {}
    coords = geometry.get("coordinates")
    returned_lon = returned_lat = elevation = None
    if isinstance(coords, (list, tuple)) and len(coords) >= 2:
        returned_lon, returned_lat = coords[0], coords[1]
        if len(coords) >= 3:
            elevation = coords[2]
    location = payload.get("returned_location")
    if isinstance(location, dict):
        returned_lat = location.get("latitude", returned_lat)
        returned_lon = location.get("longitude", returned_lon)
        elevation = location.get("elevation", elevation)
    elevation = header.get("elevation", elevation)
    sources = header.get("sources", payload.get("sources", []))
    return {
        "returned_latitude": returned_lat,
        "returned_longitude": returned_lon,
        "returned_elevation": elevation,
        "time_standard": header.get("time_standard", TIME_STANDARD),
        "api_sources": sources if isinstance(sources, list) else [sources] if sources else [],
        "header_fill_value": header.get("fill_value", payload.get("fill_value")),
    }


def _as_numeric(value: Any, fill_values: set[float]) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result) or result in fill_values:
        return None
    return result


def _extract_series(payload: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Return date -> parameter values and raw response metadata."""
    if payload.get("error"):
        raise PowerApiError(f"NASA POWER API error: {payload.get('reason', payload.get('message', payload['error']))}")
    properties = payload.get("properties")
    parameter_data = properties.get("parameter") if isinstance(properties, dict) else None
    if not isinstance(parameter_data, dict):
        raise PowerApiError("NASA POWER response has no properties.parameter object")
    metadata = _response_metadata(payload)
    fill_values = set(DEFAULT_FILL_VALUES)
    for candidate in (metadata["header_fill_value"],):
        try:
            if candidate is not None:
                fill_values.add(float(candidate))
        except (TypeError, ValueError):
            pass
    parameter_metadata = payload.get("parameters") if isinstance(payload.get("parameters"), dict) else {}
    for item in parameter_metadata.values():
        if isinstance(item, dict):
            for key in ("fill_value", "missing_value", "missing"):
                try:
                    if item.get(key) is not None:
                        fill_values.add(float(item[key]))
                except (TypeError, ValueError):
                    pass
    date_keys = set()
    for parameter in PARAMETERS:
        values = parameter_data.get(parameter)
        if isinstance(values, dict):
            date_keys.update(str(day) for day in values)
    by_date: dict[str, dict[str, Any]] = {}
    for day in date_keys:
        by_date[day] = {}
        for parameter in PARAMETERS:
            series = parameter_data.get(parameter)
            by_date[day][parameter] = _as_numeric(series.get(day), fill_values) if isinstance(series, dict) else None
    metadata["parameter_units"] = {
        name: details.get("units")
        for name, details in parameter_metadata.items()
        if name in PARAMETERS and isinstance(details, dict)
    }
    metadata["fill_values_treated_as_missing"] = sorted(fill_values)
    return by_date, metadata


def _valid_api_payload(payload: dict[str, Any]) -> bool:
    if payload.get("error"):
        return False
    properties = payload.get("properties")
    return isinstance(properties, dict) and isinstance(properties.get("parameter"), dict)


def run_pilot(input_csv: Path = INPUT_CSV, output_dir: Path = PILOT_DIR,
              opener: Callable[..., tuple[dict[str, Any], int]] = fetch_json,
              now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> dict[str, Any]:
    with input_csv.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = resolve_columns(reader.fieldnames)
        input_rows = list(reader)
    if not input_rows:
        raise ValueError("Input pilot CSV contains no observations")

    # Validate all input observations first; never drop a row, even if invalid.
    prepared = []
    seen = set()
    groups: dict[tuple[float, float], list[int]] = defaultdict(list)
    rows_out: list[dict[str, Any] | None] = [None] * len(input_rows)
    for index, source in enumerate(input_rows):
        original_date = source.get(columns["date"], "")
        day = parse_observation_date(original_date)
        lat = _valid_coordinate(source.get(columns["latitude"], ""), -90, 90)
        lon = _valid_coordinate(source.get(columns["longitude"], ""), -180, 180)
        obs_id = source.get(columns["id"], "")
        duplicate_key = (obs_id, original_date, source.get(columns["latitude"], ""), source.get(columns["longitude"], ""))
        duplicate = duplicate_key in seen
        seen.add(duplicate_key)
        item = {"index": index, "source": source, "date": day, "latitude": lat, "longitude": lon,
                "duplicate_observation": duplicate}
        prepared.append(item)
        base = dict(source)
        base.update({
            "observation_date_iso": day.isoformat() if day else "",
            "weather_date_used": "",
            "requested_latitude": lat if lat is not None else "",
            "requested_longitude": lon if lon is not None else "",
            "returned_latitude": "", "returned_longitude": "", "returned_elevation": "",
            "weather_time_standard": TIME_STANDARD, "api_sources": "", "api_endpoint": ENDPOINT,
            "retrieved_at_utc": "", "cache_hit": False,
            "T2M": "", "T2M_unit": "", "PRECTOTCORR": "", "PRECTOTCORR_unit": "",
            "RH2M": "", "RH2M_unit": "", "missing_weather_variables": "",
            "duplicate_observation": duplicate, "status": "", "status_detail": "",
        })
        rows_out[index] = base
        if day is None or lat is None or lon is None:
            base["status"] = "invalid coordinates/date"
            invalid_parts = []
            if day is None:
                invalid_parts.append("invalid or missing date")
            if lat is None:
                invalid_parts.append("invalid or missing latitude")
            if lon is None:
                invalid_parts.append("invalid or missing longitude")
            base["status_detail"] = "; ".join(invalid_parts)
            rows_out[index] = base
        else:
            groups[(lat, lon)].append(index)

    cache_dir = output_dir / "raw_cache"
    failures = []
    request_records = []
    extracted_cache: dict[int, tuple[dict[str, Any], dict[str, Any], str, bool]] = {}
    for (lat, lon), indices in groups.items():
        dates = [prepared[i]["date"] for i in indices]
        start, end = min(dates), max(dates)
        url = build_request_url(lat, lon, start, end)
        cache_key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        raw_path = cache_dir / f"{cache_key}.json"
        cache_hit = raw_path.exists()
        retrieved_at = now().isoformat()
        try:
            if cache_hit:
                payload = json.loads(raw_path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise PowerApiError("Cached NASA POWER response is not a JSON object")
                status = 200
                sidecar = raw_path.with_suffix(".metadata.json")
                cache_metadata = json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.exists() else {}
                retrieved_at = cache_metadata.get("retrieved_at_utc", "")
            else:
                payload, status = opener(url, 60)
                retrieved_at = now().isoformat()
            if status != 200:
                raise PowerApiError(f"NASA POWER HTTP {status}")
            if not _valid_api_payload(payload):
                if payload.get("error"):
                    raise PowerApiError(f"NASA POWER API error: {payload.get('reason', payload.get('message', payload['error']))}")
                raise PowerApiError("NASA POWER response is missing properties.parameter")
            by_date, metadata = _extract_series(payload)
            if not cache_hit:
                _write_json(raw_path, payload)
                _write_json(raw_path.with_suffix(".metadata.json"), {
                    "request_url": url, "retrieved_at_utc": retrieved_at,
                    "http_status": status, "cache_key_sha256": cache_key,
                })
            for i in indices:
                extracted_cache[i] = (by_date, metadata, retrieved_at, cache_hit)
            request_records.append({
                "request_url": url, "cache_key_sha256": cache_key, "cache_file": str(raw_path.relative_to(output_dir)),
                "cache_hit": cache_hit, "http_status": status, "retrieved_at_utc": retrieved_at,
                "requested_latitude": lat, "requested_longitude": lon,
                "requested_start": start.isoformat(), "requested_end": end.isoformat(),
                "returned_latitude": metadata["returned_latitude"], "returned_longitude": metadata["returned_longitude"],
                "returned_elevation": metadata["returned_elevation"], "api_sources": metadata["api_sources"],
                "time_standard": metadata["time_standard"], "parameter_units": metadata["parameter_units"],
                "fill_values_treated_as_missing": metadata["fill_values_treated_as_missing"],
            })
        except (PowerApiError, OSError, json.JSONDecodeError, ValueError) as exc:
            error = str(exc)
            failures.append({"requested_latitude": lat, "requested_longitude": lon,
                             "requested_start": start.isoformat(), "requested_end": end.isoformat(),
                             "request_url": url, "attempted_at_utc": retrieved_at, "error": error})
            for i in indices:
                item = prepared[i]
                row = rows_out[i]
                assert row is not None
                row["status"] = "API failure"
                row["status_detail"] = error
                row["retrieved_at_utc"] = retrieved_at

    for item in prepared:
        i = item["index"]
        if rows_out[i] is not None and rows_out[i]["status"] in ("invalid coordinates/date", "API failure"):
            continue
        row = rows_out[i]
        assert row is not None
        by_date, metadata, retrieved_at, cache_hit = extracted_cache[i]
        obs_day = item["date"].strftime("%Y%m%d")
        values = by_date.get(obs_day)
        row.update({
            "returned_latitude": metadata["returned_latitude"] if metadata["returned_latitude"] is not None else "",
            "returned_longitude": metadata["returned_longitude"] if metadata["returned_longitude"] is not None else "",
            "returned_elevation": metadata["returned_elevation"] if metadata["returned_elevation"] is not None else "",
            "weather_time_standard": metadata["time_standard"],
            "api_sources": ";".join(str(x) for x in metadata["api_sources"]),
            "retrieved_at_utc": retrieved_at, "cache_hit": cache_hit,
        })
        if values is None:
            missing = list(PARAMETERS)
        else:
            row["weather_date_used"] = item["date"].isoformat()
            missing = [name for name in PARAMETERS if values.get(name) is None]
            for name in PARAMETERS:
                row[name] = values.get(name) if values.get(name) is not None else ""
        units = metadata["parameter_units"]
        for name in PARAMETERS:
            row[f"{name}_unit"] = units.get(name) or ""
        row["missing_weather_variables"] = ";".join(missing)
        if missing:
            row["status"] = "missing weather"
            row["status_detail"] = "missing date or parameter: " + ",".join(missing)
        else:
            row["status"] = "matched"
            row["status_detail"] = "exact observation date; no substitute date used"

    output_rows = [row for row in rows_out if row is not None]
    status_counts = Counter(row["status"] for row in output_rows)
    missingness = {name: sum(row[name] == "" for row in output_rows) for name in PARAMETERS}
    response_missing_counts = {
        name: sum(name in row["missing_weather_variables"].split(";") and row["status"] == "missing weather"
                  for row in output_rows)
        for name in PARAMETERS
    }
    matched_rows = [row for row in output_rows if row["status"] == "matched"]
    date_alignment = bool(matched_rows) and all(row["weather_date_used"] == row["observation_date_iso"] for row in matched_rows)
    numeric_valid = bool(matched_rows) and all(isinstance(row[name], (int, float)) and math.isfinite(row[name]) for row in matched_rows for name in PARAMETERS)
    exact_duplicate_count = sum(item["duplicate_observation"] for item in prepared)
    quality = {
        "dataset": "Uganda cassava brown streak Dataset C pilot observations matched to NASA POWER daily data",
        "input_file": str(input_csv), "output_rows": len(output_rows), "input_rows": len(input_rows),
        "row_count_matches_input": len(output_rows) == len(input_rows),
        "status_counts": {name: status_counts.get(name, 0) for name in ("matched", "missing weather", "API failure", "invalid coordinates/date")},
        "duplicate_observation_rows_preserved": exact_duplicate_count,
        "duplicate_observation_rows_dropped": 0,
        "matching_date_is_exact": date_alignment,
        "matched_values_are_finite_numeric_and_not_fill_values": numeric_valid,
        "blank_output_counts_by_parameter": missingness,
        "rows_missing_parameter_in_successful_responses": response_missing_counts,
        "request_count": len(request_records) + len(failures),
        "api_failures": failures,
        "weather_source": "NASA POWER Daily API; MERRA-2 meteorological inputs as identified by response metadata",
        "time_standard": TIME_STANDARD,
        "parameters": list(PARAMETERS),
        "quality_pass": (len(output_rows) == len(input_rows) and date_alignment and numeric_valid
                         and status_counts.get("API failure", 0) == 0
                         and status_counts.get("invalid coordinates/date", 0) == 0),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    output_csv = output_dir / "weather_matches.csv"
    output_columns = list(input_rows[0]) + [
        "observation_date_iso", "weather_date_used", "requested_latitude", "requested_longitude", "returned_latitude", "returned_longitude",
        "returned_elevation", "weather_time_standard", "api_sources", "api_endpoint", "retrieved_at_utc", "cache_hit",
        "T2M", "T2M_unit", "PRECTOTCORR", "PRECTOTCORR_unit", "RH2M", "RH2M_unit",
        "missing_weather_variables", "duplicate_observation", "status", "status_detail",
    ]
    _write_csv(output_csv, output_rows, output_columns)
    quality["output_file"] = output_csv.name
    quality["output_sha256"] = hashlib.sha256(output_csv.read_bytes()).hexdigest()
    quality["raw_response_files"] = [record["cache_file"] for record in request_records]
    quality["raw_response_sha256"] = {
        record["cache_file"]: hashlib.sha256((output_dir / record["cache_file"]).read_bytes()).hexdigest()
        for record in request_records
    }
    _write_json(output_dir / "quality_report.json", quality)
    _write_json(output_dir / "request_metadata.json", {
        "source": "NASA POWER Daily API", "endpoint": ENDPOINT, "parameters": list(PARAMETERS),
        "community": COMMUNITY, "time_standard": TIME_STANDARD, "retrieval_run_at_utc": now().isoformat(),
        "requests": request_records, "failures": failures,
        "input_column_mapping": columns,
        "notes": ["Raw response cache is separate from weather_matches.csv.",
                  "No disease outcomes are inferred from weather.",
                  "Point values represent source-grid data, not exact field measurements."],
    })
    return quality


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=INPUT_CSV)
    parser.add_argument("--output-dir", type=Path, default=PILOT_DIR)
    args = parser.parse_args()
    quality = run_pilot(args.input, args.output_dir)
    print(json.dumps(quality, indent=2, ensure_ascii=False))
    return 0 if quality["row_count_matches_input"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
