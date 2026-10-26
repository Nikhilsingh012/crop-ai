"""Download and quality-check Open-Meteo historical forecast data.

Run from backend/: ``python -m services.historical_weather --help``.
This dataset is historical forecast output, not observed or reanalysis weather.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

LOG = logging.getLogger("historical_weather")
DEFAULT_ENDPOINT = "https://historical-forecast-api.open-meteo.com/v1/forecast"
DEFAULT_VARIABLES = (
    "temperature_2m,relative_humidity_2m,precipitation,soil_temperature_0cm,"
    "soil_temperature_6cm,soil_temperature_18cm,soil_moisture_0_to_1cm,"
    "soil_moisture_1_to_3cm,soil_moisture_3_to_9cm,et0_fao_evapotranspiration"
)
DATASET_TYPE = "historical_forecast"


class DownloadError(RuntimeError):
    """A provider, HTTP, or response-shape failure safe to show in CLI output."""


def build_url(endpoint: str, latitude: float, longitude: float, start: date,
              end: date, variables: list[str], timezone_name: str) -> str:
    query = urllib.parse.urlencode({
        "latitude": latitude, "longitude": longitude,
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "hourly": ",".join(variables), "timezone": timezone_name,
    })
    return f"{endpoint}{'&' if '?' in endpoint else '?'}{query}"


def fetch_json(url: str, timeout: float = 60) -> tuple[dict[str, Any], int]:
    request = urllib.request.Request(url, headers={"User-Agent": "CropAI-HistoricalWeather/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
            raw = response.read()
    except urllib.error.HTTPError as exc:
        # Include provider's safe error body and status, never request headers.
        body = exc.read().decode("utf-8", errors="replace")[:1000]
        raise DownloadError(f"Open-Meteo HTTP {exc.code}: {body}") from None
    except urllib.error.URLError as exc:
        raise DownloadError(f"Open-Meteo connection failed: {exc.reason}") from None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DownloadError(f"Open-Meteo returned invalid JSON: {exc}") from None
    if status != 200:
        raise DownloadError(f"Open-Meteo HTTP {status}")
    if not isinstance(payload, dict) or payload.get("error"):
        raise DownloadError(f"Open-Meteo error response: {payload.get('reason', 'invalid response') if isinstance(payload, dict) else 'invalid response'}")
    if not isinstance(payload.get("hourly"), dict) or not isinstance(payload["hourly"].get("time"), list):
        raise DownloadError("Open-Meteo response has no hourly.time array")
    return payload, status


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def convert_hourly(payload: dict[str, Any], variables: list[str], source_url: str,
                   retrieved_at: str) -> tuple[list[dict[str, Any]], dict[str, str]]:
    hourly = payload["hourly"]
    times = hourly["time"]
    units = payload.get("hourly_units") or {}
    rows = []
    for index, timestamp in enumerate(times):
        row: dict[str, Any] = {
            "timestamp": timestamp,
            "latitude": payload.get("latitude"), "longitude": payload.get("longitude"),
            "timezone": payload.get("timezone"), "utc_offset_seconds": payload.get("utc_offset_seconds"),
            "elevation": payload.get("elevation"), "timezone_abbreviation": payload.get("timezone_abbreviation"),
            "source_provider": "Open-Meteo Historical Forecast API", "source_url": source_url,
            "dataset_type": DATASET_TYPE, "retrieved_at_utc": retrieved_at,
            "generationtime_ms": payload.get("generationtime_ms"),
        }
        for variable in variables:
            values = hourly.get(variable)
            row[variable] = values[index] if isinstance(values, list) and index < len(values) else None
            row[f"{variable}_unit"] = units.get(variable)
        rows.append(row)
    return rows, {name: str(units[name]) for name in variables if name in units}


def derive_daily(rows: list[dict[str, Any]], hot_threshold_c: float | None = None,
                 dry_day_threshold_mm: float | None = None) -> list[dict[str, Any]]:
    days: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        days[str(row["timestamp"])[:10]].append(row)
    daily: list[dict[str, Any]] = []
    for day in sorted(days):
        entries = days[day]
        temps = [_number(r.get("temperature_2m")) for r in entries]
        temps = [v for v in temps if v is not None]
        rain_values = [_number(r.get("precipitation")) for r in entries]
        complete_rain = len(entries) == 24 and all(v is not None for v in rain_values)
        rain = sum(v for v in rain_values if v is not None) if complete_rain else None
        night = []
        for r in entries:
            try:
                hour = datetime.fromisoformat(str(r["timestamp"])).hour
            except ValueError:
                continue
            if hour <= 5 or hour >= 20:
                value = _number(r.get("temperature_2m"))
                if value is not None:
                    night.append(value)
        daily.append({
            "date": day, "hourly_rows": len(entries), "valid_temperature_hours": len(temps),
            "daily_min_temperature_2m": min(temps) if temps else None,
            "daily_max_temperature_2m": max(temps) if temps else None,
            "rainfall_mm": rain, "valid_rainfall_hours": sum(v is not None for v in rain_values),
            "night_hours_definition_local": "00:00-05:59 and 20:00-23:59",
            "nighttime_temperature_mean_2m": sum(night) / len(night) if night else None,
            "nighttime_temperature_min_2m": min(night) if night else None,
            "nighttime_temperature_max_2m": max(night) if night else None,
            "nighttime_valid_hours": len(night),
            "hot_day_threshold_c": hot_threshold_c, "consecutive_hot_days": None,
            "dry_day_rainfall_threshold_mm": dry_day_threshold_mm, "dry_spell_days": None,
            "rolling_3_day_rainfall_mm": None, "rolling_7_day_rainfall_mm": None,
        })
    for i, record in enumerate(daily):
        for window in (3, 7):
            chunk = daily[max(0, i - window + 1):i + 1]
            if len(chunk) == window and all(r["rainfall_mm"] is not None for r in chunk):
                record[f"rolling_{window}_day_rainfall_mm"] = sum(r["rainfall_mm"] for r in chunk)
        if hot_threshold_c is not None:
            if record["daily_max_temperature_2m"] is None:
                record["consecutive_hot_days"] = None
            elif record["daily_max_temperature_2m"] > hot_threshold_c:
                record["consecutive_hot_days"] = (daily[i - 1]["consecutive_hot_days"] or 0) + 1 if i and daily[i - 1]["consecutive_hot_days"] is not None else 1
            else:
                record["consecutive_hot_days"] = 0
        if dry_day_threshold_mm is not None:
            if record["rainfall_mm"] is None:
                record["dry_spell_days"] = None
            elif record["rainfall_mm"] <= dry_day_threshold_mm:
                record["dry_spell_days"] = (daily[i - 1]["dry_spell_days"] or 0) + 1 if i and daily[i - 1]["dry_spell_days"] is not None else 1
            else:
                record["dry_spell_days"] = 0
    return daily


def quality_report(rows: list[dict[str, Any]], variables: list[str], start: date, end: date,
                   payload: dict[str, Any], status: int, output_paths: dict[str, str]) -> dict[str, Any]:
    timestamps = [str(r["timestamp"]) for r in rows]
    counts: dict[str, int] = defaultdict(int)
    for ts in timestamps:
        counts[ts] += 1
    try:
        actual_start = date.fromisoformat(timestamps[0][:10]) if timestamps else None
        actual_end = date.fromisoformat(timestamps[-1][:10]) if timestamps else None
        expected = set()
        if actual_start and actual_end:
            cursor = datetime.combine(actual_start, datetime.min.time())
            stop = datetime.combine(actual_end + timedelta(days=1), datetime.min.time())
            while cursor < stop:
                expected.add(cursor.isoformat(timespec="minutes"))
                cursor += timedelta(hours=1)
        actual_set = set(timestamps)
        missing_ts = sorted(expected - actual_set)
    except (ValueError, IndexError):
        actual_start = actual_end = None
        missing_ts = []
    requested_expected = set()
    cursor = datetime.combine(start, datetime.min.time())
    stop = datetime.combine(end + timedelta(days=1), datetime.min.time())
    while cursor < stop:
        requested_expected.add(cursor.isoformat(timespec="minutes"))
        cursor += timedelta(hours=1)
    missing_requested_hours = sorted(requested_expected - set(timestamps))
    missingness = {}
    for variable in variables:
        missing = sum(_number(row.get(variable)) is None for row in rows)
        missingness[variable] = {"missing": missing, "total": len(rows), "fraction": missing / len(rows) if rows else None}
    duplicate_timestamps = sorted(ts for ts, count in counts.items() if count > 1)
    return {
        "dataset_type": DATASET_TYPE,
        "weather_classification": "Historical forecast output; not observed weather or reanalysis.",
        "http_status": status, "requested_date_range": {"start": start.isoformat(), "end": end.isoformat()},
        "actual_downloaded_date_range": {"start": actual_start.isoformat() if actual_start else None, "end": actual_end.isoformat() if actual_end else None},
        "rows_downloaded": len(rows), "duplicate_timestamp_count": sum(count - 1 for count in counts.values() if count > 1),
        "duplicate_timestamps": duplicate_timestamps[:100], "missing_hour_count": len(missing_ts),
        "missing_hour_samples": missing_ts[:100],
        "missing_requested_hour_count": len(missing_requested_hours),
        "missing_requested_hour_samples": missing_requested_hours[:100],
        "missingness_by_variable": missingness,
        "returned_location": {"latitude": payload.get("latitude"), "longitude": payload.get("longitude"),
                              "timezone": payload.get("timezone"), "elevation": payload.get("elevation")},
        "validations": {"timestamps_unique": not duplicate_timestamps, "no_missing_hours_in_returned_span": not missing_ts,
                        "all_requested_hours_returned": not missing_requested_hours,
                        "returned_date_coverage_matches_request": actual_start == start and actual_end == end,
                        "all_requested_variables_present": all(v in (payload.get("hourly") or {}) for v in variables)},
        "output_files": output_paths,
    }


def run(args: argparse.Namespace, opener=fetch_json) -> dict[str, Any]:
    start, end = date.fromisoformat(args.start_date), date.fromisoformat(args.end_date)
    if end < start:
        raise ValueError("end-date must be on or after start-date")
    variables = [part.strip() for part in args.variables.split(",") if part.strip()]
    if not variables:
        raise ValueError("at least one hourly variable is required")
    endpoint_url = build_url(args.endpoint, args.latitude, args.longitude, start, end, variables, args.timezone)
    payload, status = opener(endpoint_url, args.timeout)
    retrieved_at = datetime.now(timezone.utc).isoformat()
    rows, units = convert_hourly(payload, variables, endpoint_url, retrieved_at)
    daily = derive_daily(rows, args.hot_day_threshold_c, args.dry_day_threshold_mm)

    root = Path(args.output_root)
    root.mkdir(parents=True, exist_ok=True)
    if args.output_dir:
        out_dir = Path(args.output_dir)
    else:
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        out_dir = root / f"{start.isoformat()}_{end.isoformat()}_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=False)
    base_columns = ["timestamp", "latitude", "longitude", "timezone", "utc_offset_seconds", "elevation", "timezone_abbreviation",
                    "source_provider", "source_url", "dataset_type", "retrieved_at_utc", "generationtime_ms"]
    for v in variables:
        base_columns.extend((v, f"{v}_unit"))
    paths = {"raw_json": str(out_dir / "raw_response.json"), "metadata_json": str(out_dir / "metadata.json"),
             "hourly_csv": str(out_dir / "hourly.csv"), "daily_features_csv": str(out_dir / "daily_features.csv"),
             "quality_report_json": str(out_dir / "quality_report.json")}
    metadata = {"dataset_type": DATASET_TYPE, "source_provider": "Open-Meteo Historical Forecast API",
                "source_url": endpoint_url, "request": {"latitude": args.latitude, "longitude": args.longitude,
                "start_date": start.isoformat(), "end_date": end.isoformat(), "timezone": args.timezone,
                "variables": variables}, "http_status": status, "retrieved_at_utc": retrieved_at,
                "returned_location": {k: payload.get(k) for k in ("latitude", "longitude", "timezone", "utc_offset_seconds", "elevation")},
                "hourly_units": units}
    _write_json(Path(paths["raw_json"]), payload)
    _write_json(Path(paths["metadata_json"]), metadata)
    _write_csv(Path(paths["hourly_csv"]), base_columns, rows)
    daily_columns = list(daily[0]) if daily else ["date"]
    _write_csv(Path(paths["daily_features_csv"]), daily_columns, daily)
    report = quality_report(rows, variables, start, end, payload, status, paths)
    _write_json(Path(paths["quality_report_json"]), report)
    return report


def parser() -> argparse.ArgumentParser:
    default_root = Path(__file__).resolve().parents[2] / "data" / "historical_weather"
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--latitude", type=float, default=28.4744)
    p.add_argument("--longitude", type=float, default=77.5040)
    p.add_argument("--start-date", default="2022-01-01")
    p.add_argument("--end-date", default="2026-10-20")
    p.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    p.add_argument("--variables", default=DEFAULT_VARIABLES)
    p.add_argument("--timezone", default="Asia/Kolkata")
    p.add_argument("--output-root", default=str(default_root))
    p.add_argument("--output-dir", help="Exact new directory to create; must not already exist")
    p.add_argument("--timeout", type=float, default=60)
    p.add_argument("--hot-day-threshold-c", type=float, help="Optional evidence-backed threshold; consecutive days use Tmax > threshold")
    p.add_argument("--dry-day-threshold-mm", type=float, help="Optional evidence-backed rainfall cutoff; dry days use rainfall <= threshold")
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        report = run(parser().parse_args(argv))
    except (DownloadError, ValueError, OSError) as exc:
        LOG.error("%s", exc)
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
