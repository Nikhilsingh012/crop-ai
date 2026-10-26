"""Source-backed crop weather exposure assessment.

Indices describe forecast exposure to a documented trigger. They are not
probabilities of crop damage. Each hazard is evaluated independently.
"""
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from services.agriculture.weather_risk_model import assess_crop_weather_risk
from services.crop_catalog import crop_by_id, resolve_crop

UNAVAILABLE_MESSAGE = "No supported crop hazard rule matched the available crop, stage, location and forecast data."
HAZARDS = (
    ("EXCESS_RAINFALL", "Excess rainfall / waterlogging"),
    ("HEAT_STRESS", "Heat stress"),
    ("COLD_FROST", "Cold / frost stress"),
    ("DRY_SPELL", "Dry spell / drought stress"),
    ("DISEASE_FAVOURABLE_WEATHER", "Disease-favourable weather"),
    ("SEVERE_WEATHER", "Severe weather"),
)
RULE_REGISTRY = Path(__file__).resolve().parents[3] / "data" / "crop_knowledge" / "risk_rule_registry.json"
INDIAN_STATES_AND_UTS = {"andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh", "goa", "gujarat", "haryana", "himachal pradesh", "jharkhand", "karnataka", "kerala", "madhya pradesh", "maharashtra", "manipur", "meghalaya", "mizoram", "nagaland", "odisha", "punjab", "rajasthan", "sikkim", "tamil nadu", "telangana", "tripura", "uttar pradesh", "uttarakhand", "west bengal", "andaman and nicobar islands", "chandigarh", "dadra and nagar haveli and daman and diu", "delhi", "jammu and kashmir", "ladakh", "lakshadweep", "puducherry"}


def load_rule_records():
    """Return registry entries with provenance status preserved for reporting."""
    try:
        payload = json.loads(RULE_REGISTRY.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rules = payload.get("rules", []) if isinstance(payload, dict) else []
    records = [rule for rule in rules if isinstance(rule, dict)]
    for rule in records:
        crop = crop_by_id(rule.get("crop_id"))
        rule.setdefault("crop_aliases", list(crop.get("aliases", [])) if crop else [])
    return records


def load_verified_rules():
    return [rule for rule in load_rule_records() if rule.get("verification_status") == "verified" and rule.get("source_validation_status") == "verified"]


def _finite(value, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        result = float(value)
    except (OverflowError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    if (minimum is not None and result < minimum) or (maximum is not None and result > maximum):
        return None
    return result


def _forecast_timestamp(value, timezone_name=None):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        try:
            parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name)) if timezone_name else parsed.replace(tzinfo=timezone.utc)
        except (ZoneInfoNotFoundError, TypeError, ValueError):
            parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _weather_summary(weather):
    weather = weather if isinstance(weather, dict) else {}
    forecast = weather.get("forecast")
    forecast = forecast if isinstance(forecast, list) else []
    daily = []
    for day in forecast:
        if not isinstance(day, dict):
            continue
        daily.append({
            "date": day.get("date") if isinstance(day.get("date"), str) else None,
            "rainfall_mm": _finite(day.get("rainfall"), 0),
            "temperature_max_c": _finite(day.get("temperature_max"), -100, 70),
            "temperature_min_c": _finite(day.get("temperature_min"), -100, 70),
            "precipitation_probability_percent": _finite(day.get("precipitation_probability"), 0, 100),
        })
    hourly = weather.get("hourly_forecast")
    hourly = hourly if isinstance(hourly, list) else []
    forecast_reference = weather.get("forecast_issued_at")
    reference_time = _forecast_timestamp(forecast_reference, weather.get("timezone"))
    reference_date = forecast_reference[:10] if isinstance(forecast_reference, str) and len(forecast_reference) >= 10 else None
    parsed_hours = []
    seen_timestamps = set()
    invalid_timestamp_count = 0
    duplicate_timestamp_count = 0
    for item in hourly:
        if not isinstance(item, dict):
            invalid_timestamp_count += 1
            continue
        timestamp = _forecast_timestamp(item.get("time"), weather.get("timezone"))
        if timestamp is None:
            invalid_timestamp_count += 1
            continue
        if reference_time is not None and timestamp <= reference_time:
            continue
        if timestamp in seen_timestamps:
            duplicate_timestamp_count += 1
            continue
        seen_timestamps.add(timestamp)
        parsed_hours.append((timestamp, item))
    parsed_hours.sort(key=lambda pair: pair[0])
    hourly = [item for _, item in parsed_hours[:48]]
    valid_hourly = []
    for item in hourly:
        if not isinstance(item, dict):
            continue
        raw_temperature = item.get("temperature")
        valid_hourly.append({
            "time": item.get("time") if isinstance(item.get("time"), str) else None,
            "rainfall_mm": _finite(item.get("rainfall"), 0),
            "temperature_c": _finite(raw_temperature, -100, 70),
            "temperature_is_valid": isinstance(raw_temperature, (int, float)) and not isinstance(raw_temperature, bool) and _finite(raw_temperature, -100, 70) is not None,
            "humidity_percent": _finite(item.get("humidity"), 0, 100),
            "wind_speed_kmh": _finite(item.get("wind_speed"), 0, 500),
        })
    rain_values = [day["rainfall_mm"] for day in daily if day["rainfall_mm"] is not None]
    max_values = [day["temperature_max_c"] for day in daily if day["temperature_max_c"] is not None]
    min_values = [day["temperature_min_c"] for day in daily if day["temperature_min_c"] is not None]
    temps = [hour["temperature_c"] for hour in valid_hourly if hour["temperature_c"] is not None]
    rains = [hour["rainfall_mm"] for hour in valid_hourly if hour["rainfall_mm"] is not None]
    complete_hourly_rain = len(valid_hourly) == 48 and len(rains) == 48
    complete_hourly_temperature = len(valid_hourly) == 48 and len(temps) == 48
    return {
        "forecast_days": daily,
        "forecast_reference_date": reference_date,
        "forecast_rainfall_total_mm": round(sum(rain_values), 1) if rain_values else None,
        "peak_daily_rainfall_mm": round(max(rain_values), 1) if rain_values else None,
        "forecast_max_temperature_c": max(max_values) if max_values else None,
        "forecast_min_temperature_c": min(min_values) if min_values else None,
        "next_48h_hour_count": len(valid_hourly),
        "hourly_invalid_timestamp_count": invalid_timestamp_count,
        "hourly_duplicate_timestamp_count": duplicate_timestamp_count,
        "next_48h_rainfall_total_mm": round(sum(rains), 1) if complete_hourly_rain else None,
        "next_48h_temperature_min_c": min(temps) if complete_hourly_temperature else None,
        "next_48h_temperature_max_c": max(temps) if complete_hourly_temperature else None,
        "current_temperature_c": _finite(weather.get("temperature"), -100, 70),
        "current_humidity_percent": _finite(weather.get("humidity"), 0, 100),
        "current_rainfall_mm": _finite(weather.get("rainfall"), 0),
        "current_wind_speed_kmh": _finite(weather.get("wind_speed"), 0, 500),
        "provider": weather.get("provider"),
        "timezone": weather.get("timezone"),
        "forecast_issued_at": weather.get("forecast_issued_at"),
        "retrieved_at": weather.get("retrieved_at"),
        "stale": bool(weather.get("stale")),
        "cache_age_seconds": weather.get("cache_age_seconds"),
        "cache": weather.get("cache"),
        "provider_status": weather.get("provider_status"),
        "provider_http_status": weather.get("provider_http_status"),
        "provider_error": weather.get("provider_error"),
        "freshness_status": weather.get("freshness_status") or ("stale" if weather.get("stale") else "fresh" if forecast else "unavailable"),
        "hourly_observations": valid_hourly,
    }


def _normal(value):
    return " ".join(str(value or "").lower().replace("_", " ").replace("-", " ").split())


def normalize_stage(value):
    """Map common farmer stage labels to a stable comparison key; never infer a stage."""
    key = _normal(value)
    aliases = {
        "reproductive": "flowering", "blooming": "flowering", "anthesis": "flowering",
        "grain fill": "grain filling", "grain formation": "grain filling",
        "tuberization": "tuber initiation", "tuber initiation": "tuber initiation",
        "fruit set": "fruiting", "fruit development": "fruiting",
    }
    return aliases.get(key, key)


def _source(rule):
    return {key: rule.get(key) for key in ("publication_title", "source_url", "publication_date", "last_reviewed", "evidence_excerpt", "source_validation_status", "source_validation_note") if rule.get(key) is not None}


def _indicator_alert(rule, crop_name, hazard_code, expected_time, condition, timezone_name):
    """Build one in-app event alert per rule and forecast calendar date."""
    expected_day = expected_time[:10] if isinstance(expected_time, str) and len(expected_time) >= 10 else "forecast"
    title = f"{crop_name}: {rule.get('publication_title') or hazard_code} indicator — {expected_day}"
    return {
        "risk_type": hazard_code,
        "rule_id": rule.get("rule_id"),
        "title": title,
        "severity": "WATCH",
        "expected_time": expected_time,
        "forecast_timezone": timezone_name or "UTC",
        "explanation": condition,
        "sources": [_source(rule)],
        "assessment_type": "deterministic_exposure_indicator",
    }


def _region_matches(rule_regions, region):
    if not isinstance(rule_regions, list):
        rule_regions = [rule_regions]
    normalized_regions = {_normal(value) for value in rule_regions}
    normalized_region = _normal(region)
    if not normalized_regions:
        return True
    if "india" in normalized_regions:
        return normalized_region in INDIAN_STATES_AND_UTS | {"india"}
    return normalized_region in normalized_regions


def _applicable(rule, crop_id, stage, region):
    if rule.get("verification_status") != "verified" or rule.get("source_validation_status") != "verified" or not rule.get("source_url") or not rule.get("publication_title"):
        return False
    if rule.get("crop_id") != crop_id:
        return False
    if not _region_matches(rule.get("region", ""), region):
        return False
    rule_stages = rule.get("growth_stage", "")
    if not isinstance(rule_stages, list):
        rule_stages = [rule_stages]
    normalized_stages = {normalize_stage(value) for value in rule_stages}
    return not normalized_stages or "all" in normalized_stages or normalize_stage(stage) in normalized_stages


def _applicability_reason(rule, stage, region):
    """Explain why a crop-specific candidate was excluded before evaluation."""
    if rule.get("verification_status") != "verified":
        return f"Excluded from scoring: evidence status is {rule.get('verification_status') or 'missing'}."
    if rule.get("source_validation_status") != "verified":
        return f"Excluded from scoring: source validation is {rule.get('source_validation_status') or 'missing'}."
    if not rule.get("source_url") or not rule.get("publication_title"):
        return "Excluded from scoring: authoritative source metadata is incomplete."
    stages = rule.get("growth_stage", "")
    stages = stages if isinstance(stages, list) else [stages]
    normalized_stages = {normalize_stage(value) for value in stages}
    reasons = []
    if stage is None and normalized_stages and "all" not in normalized_stages:
        reasons.append("Growth stage is missing; this rule is stage-specific.")
    if stage is not None and normalized_stages and "all" not in normalized_stages and normalize_stage(stage) not in normalized_stages:
        expected = ", ".join(str(value) for value in stages)
        reasons.append(f"Stage mismatch: saved stage is {stage!r}; rule requires {expected}.")
    regions = rule.get("region", "")
    regions = regions if isinstance(regions, list) else [regions]
    normalized_regions = {_normal(value) for value in regions if value}
    if region is None and normalized_regions:
        reasons.append(f"Farm state or region is missing; geographic applicability for {', '.join(str(value) for value in regions)} cannot be verified.")
    if region is not None and not _region_matches(regions, region):
        reasons.append(f"Region mismatch: saved region is {region!r}; rule applies to {', '.join(str(value) for value in regions)}.")
    return " ".join(reasons) or None


def _evaluate_rule(rule, weather_summary):
    """Evaluate a declared hourly threshold rule after validating its units and window."""
    if weather_summary["stale"]:
        return None, "The cached forecast is stale; refresh weather before scoring this hazard."
    if rule.get("evaluator") == "daily_max_threshold_indicator":
        return _evaluate_daily_max_indicator(rule, weather_summary)
    if rule.get("evaluator") == "daily_min_temperature_condition_indicator":
        return _evaluate_daily_min_temperature_indicator(rule, weather_summary)
    if rule.get("evaluator") == "hourly_temperature_condition_indicator":
        return _evaluate_hourly_temperature_condition(rule, weather_summary)
    if rule.get("evaluator") not in ("hourly_threshold_exposure", "night_hourly_threshold_exposure"):
        return None, "No deterministic evaluator is configured for this rule."
    observation_fields = {
        "temperature_2m": ("temperature_c", "deg C"),
        "relative_humidity_2m": ("humidity_percent", "%"),
        "precipitation": ("rainfall_mm", "mm"),
        "wind_speed_10m": ("wind_speed_kmh", "km/h"),
    }
    parameter = rule.get("weather_parameter")
    observation_field = observation_fields.get(parameter)
    if observation_field is None:
        return None, "The forecast provider does not expose the weather variable required by this rule."
    field, forecast_unit = observation_field
    requested_unit = _normal(rule.get("unit"))
    conversions = {
        ("temperature_2m", "deg c"): lambda value: value,
        ("temperature_2m", "c"): lambda value: value,
        ("temperature_2m", "°c"): lambda value: value,
        ("temperature_2m", "f"): lambda value: (value - 32) * 5 / 9,
        ("relative_humidity_2m", "%"): lambda value: value,
        ("relative_humidity_2m", "percent"): lambda value: value,
        ("precipitation", "mm"): lambda value: value,
        ("wind_speed_10m", "km h"): lambda value: value,
        ("wind_speed_10m", "km/h"): lambda value: value,
        ("wind_speed_10m", "m s"): lambda value: value * 3.6,
        ("wind_speed_10m", "m/s"): lambda value: value * 3.6,
    }
    convert = conversions.get((parameter, requested_unit))
    if convert is None:
        return None, f"Rule unit {rule.get('unit')!r} is unsupported for {parameter}."
    raw_threshold = _finite(rule.get("threshold"))
    if raw_threshold is None or rule.get("operator") not in ("gt", "gte", "lt", "lte"):
        return None, "The rule threshold or comparison operator is invalid."
    threshold = convert(raw_threshold)
    window_hours = rule.get("window_hours", 48)
    minimum_samples = rule.get("minimum_samples", window_hours)
    if not isinstance(window_hours, int) or not 1 <= window_hours <= 168 or not isinstance(minimum_samples, int) or not 1 <= minimum_samples <= window_hours:
        return None, "The rule forecast window or minimum sample count is invalid."
    observations = weather_summary["hourly_observations"][:window_hours]
    if len(observations) < minimum_samples:
        return None, f"This rule needs at least {minimum_samples} hourly forecast observations; {len(observations)} are available."
    values = [item.get(field) for item in observations]
    if any(value is None for value in values):
        return None, f"Hourly {forecast_unit} {parameter} data is incomplete for this rule window."
    denominator = observations
    if rule.get("evaluator") == "night_hourly_threshold_exposure":
        if parameter != "temperature_2m":
            return None, "Night-hour evaluation is supported only for hourly temperature rules."
        denominator = [hour for hour in observations if hour.get("time") and (_forecast_hour(hour["time"]) >= 20 or _forecast_hour(hour["time"]) < 6)]
        if len(denominator) < min(12, minimum_samples):
            return None, "The forecast does not contain enough nighttime temperature samples."
    comparator = {"gt": lambda value: value > threshold, "gte": lambda value: value >= threshold,
                  "lt": lambda value: value < threshold, "lte": lambda value: value <= threshold}[rule["operator"]]
    exposed = [hour for hour in denominator if comparator(hour[field])]
    index = round(100 * len(exposed) / len(denominator))
    bands = rule.get("index_bands", [])
    severity = next((band["label"] for band in bands if band["minimum"] <= index <= band["maximum"]), None)
    if severity is None:
        return None, "The computed exposure index is outside the documented severity bands."
    return {
        "risk_index": index,
        "severity": severity,
        "exposed_hours": len(exposed),
        "forecast_hours": len(denominator),
        "window_start": denominator[0].get("time") if denominator else None,
        "window_end": denominator[-1].get("time") if denominator else None,
        "measured_min": min(hour[field] for hour in denominator) if denominator else None,
        "measured_max": max(hour[field] for hour in denominator) if denominator else None,
        "forecast_unit": forecast_unit,
        "threshold_in_forecast_unit": threshold,
        "first_exposure_at": next((hour["time"] for hour in exposed if hour.get("time")), None),
    }, None


def _evaluate_hourly_temperature_condition(rule, weather_summary):
    """Report whether the forecast contains a source-defined temperature event."""
    if (rule.get("weather_parameter") != "temperature_2m"
            or _normal(rule.get("unit")) not in {"deg c", "c", "Â°c"}):
        return None, "The hourly temperature condition requires Celsius temperature_2m forecast data."
    threshold = _finite(rule.get("threshold"), -100, 70)
    if threshold is None or rule.get("operator") not in {"gt", "gte", "lt", "lte"}:
        return None, "The hourly condition threshold or comparison operator is invalid."
    window_hours = rule.get("window_hours")
    minimum_samples = rule.get("minimum_samples", window_hours)
    if not isinstance(window_hours, int) or not 1 <= window_hours <= 168 or minimum_samples != window_hours:
        return None, "The hourly condition forecast window or sample count is invalid."
    observations = weather_summary["hourly_observations"][:window_hours]
    if weather_summary.get("hourly_invalid_timestamp_count", 0):
        return None, "Hourly forecast contains a missing or malformed timestamp; the consecutive rule window cannot be verified."
    if weather_summary.get("hourly_duplicate_timestamp_count", 0):
        return None, "Hourly forecast contains duplicate timestamps; the consecutive rule window cannot be verified."
    if len(observations) < window_hours:
        return None, f"This rule needs {window_hours} hourly forecast observations; {len(observations)} are available."
    timestamps = [_forecast_timestamp(item.get("time"), weather_summary.get("timezone")) for item in observations]
    if any(timestamp is None for timestamp in timestamps) or any(
        timestamps[index] - timestamps[index - 1] != timedelta(hours=1)
        for index in range(1, len(timestamps))
    ):
        return None, "Hourly forecast timestamps are not 48 consecutive hourly observations; the rule window cannot be evaluated."
    reference_text = weather_summary.get("forecast_issued_at")
    if not isinstance(reference_text, str):
        return None, "A valid forecast issue timestamp is required to identify the next 48 hourly observations."
    try:
        reference_local = datetime.fromisoformat(reference_text.replace("Z", "+00:00"))
        if reference_local.tzinfo is None:
            reference_local = reference_local.replace(tzinfo=ZoneInfo(weather_summary.get("timezone") or "UTC"))
        local_start = reference_local.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        expected_start = local_start.astimezone(timezone.utc)
    except (ValueError, TypeError, ZoneInfoNotFoundError):
        return None, "A valid forecast issue timestamp is required to identify the next 48 hourly observations."
    if timestamps[0] != expected_start:
        return None, "The hourly forecast does not begin at the first complete hour after the issue time."
    if any(item.get("temperature_is_valid") is not True for item in observations):
        return None, "Hourly temperature data contains malformed or out-of-range values for this rule window."
    values = [item.get("temperature_c") for item in observations]
    if any(value is None for value in values):
        return None, "Hourly temperature data is incomplete for this rule window."
    comparator = {"gt": lambda value: value > threshold, "gte": lambda value: value >= threshold,
                  "lt": lambda value: value < threshold, "lte": lambda value: value <= threshold}[rule["operator"]]
    events = [{"time": item["time"], "temperature_c": item["temperature_c"]}
              for item in observations if comparator(item["temperature_c"])]
    index = _weather_exposure_index(
        len(events), len(observations), "hourly forecast observations",
        observations[0].get("time"), observations[-1].get("time"),
    )
    return {
        "assessment_type": "deterministic_exposure_indicator", "triggered_hours": events,
        "forecast_hours": len(observations), "window_start": observations[0].get("time"),
        "window_end": observations[-1].get("time"), "measured_min": min(values),
        "measured_max": max(values), "forecast_unit": "deg C",
        "forecast_timezone": weather_summary.get("timezone") or "UTC",
        "threshold_in_forecast_unit": threshold, "severity": None, **index,
    }, None


def _weather_exposure_index(exposed_count, observation_count, observation_unit, window_start=None, window_end=None):
    """Report the rounded share of valid rule-window observations meeting its condition."""
    counts_valid = (isinstance(exposed_count, int) and not isinstance(exposed_count, bool)
                    and isinstance(observation_count, int) and not isinstance(observation_count, bool)
                    and 0 <= exposed_count <= observation_count)
    index = (int(math.floor((100 * exposed_count / observation_count) + 0.5))
             if counts_valid and observation_count > 0 else None)
    return {
        "risk_index": index,
        "risk_index_type": "rule_window_weather_exposure_share",
        "risk_index_details": {
            "exposed_observations": exposed_count,
            "valid_observations": observation_count,
            "observation_unit": observation_unit,
            "window_start": window_start,
            "window_end": window_end,
            "formula": "round_half_up(100 * exposed_observations / valid_observations)",
            "interpretation": "Weather exposure share for this rule window; not probability or crop-damage severity.",
        },
    }


def _evaluate_daily_max_indicator(rule, weather_summary):
    """Evaluate a source-defined daily Tmax trigger without manufacturing a score."""
    if (rule.get("weather_parameter") != "temperature_2m" or rule.get("daily_field") != "temperature_max"
            or _normal(rule.get("unit")) not in {"deg c", "c", "°c"}):
        return None, "The daily maximum-temperature evaluator requires a Celsius temperature_2m rule."
    threshold = _finite(rule.get("threshold"), -100, 70)
    operator = rule.get("operator")
    if threshold is None or operator not in {"gt", "gte", "lt", "lte"}:
        return None, "The daily rule threshold or comparison operator is invalid."
    window_days = rule.get("forecast_window_days")
    minimum_samples = rule.get("minimum_samples", window_days)
    if not isinstance(window_days, int) or not 1 <= window_days <= 7 or minimum_samples != window_days:
        return None, "The daily rule forecast window or minimum sample count is invalid."
    days = weather_summary["forecast_days"][:window_days]
    if len(days) < window_days:
        return None, f"This rule needs {window_days} daily forecast observations; {len(days)} are available."
    try:
        dates = [datetime.strptime(day.get("date", ""), "%Y-%m-%d").date() for day in days]
    except (TypeError, ValueError):
        return None, "Daily forecast dates must be valid ISO calendar dates for this rule."
    if any((dates[index] - dates[index - 1]).days != 1 for index in range(1, len(dates))):
        return None, "Daily forecast dates are not consecutive; the rule window cannot be evaluated."
    values = [day.get("temperature_max_c") for day in days]
    if any(value is None for value in values):
        return None, "Daily maximum-temperature data is incomplete for this rule window."
    comparator = {"gt": lambda value: value > threshold, "gte": lambda value: value >= threshold,
                  "lt": lambda value: value < threshold, "lte": lambda value: value <= threshold}[operator]
    exposed = [{"date": day["date"], "temperature_max_c": day["temperature_max_c"]}
               for day in days if comparator(day["temperature_max_c"])]
    index = _weather_exposure_index(len(exposed), len(days), "daily Tmax forecasts", days[0]["date"], days[-1]["date"])
    return {
        "assessment_type": "deterministic_exposure_indicator", "triggered_days": exposed,
        "forecast_days": len(days), "window_start": days[0]["date"], "window_end": days[-1]["date"],
        "measured_min": min(values), "measured_max": max(values), "forecast_unit": "deg C",
        "threshold_in_forecast_unit": threshold, "severity": None, **index,
    }, None


def _evaluate_daily_min_temperature_indicator(rule, weather_summary):
    """Flag daily Tmin outside a source-stated potato tuberization condition."""
    if (rule.get("weather_parameter") != "temperature_2m" or rule.get("daily_field") != "temperature_min"
            or _normal(rule.get("unit")) not in {"deg c", "c", "Â°c"} or rule.get("operator") not in {"gt", "gte"}):
        return None, "The daily minimum-temperature condition requires Celsius temperature_2m forecast data and a supported upper-bound comparison."
    threshold = _finite(rule.get("threshold"), -100, 70)
    if threshold is None:
        return None, "The daily minimum-temperature threshold is invalid."
    window_days = rule.get("forecast_window_days")
    minimum_samples = rule.get("minimum_samples", window_days)
    if not isinstance(window_days, int) or not 1 <= window_days <= 7 or minimum_samples != window_days:
        return None, "The daily minimum-temperature forecast window or sample count is invalid."
    reference_date = weather_summary.get("forecast_reference_date")
    if not reference_date:
        return None, "A forecast issue date is required to separate future daily minimum-temperature forecasts from the current day."
    days = [day for day in weather_summary["forecast_days"] if day.get("date") and day["date"] > reference_date][:window_days]
    if len(days) < window_days:
        return None, f"This rule needs {window_days} daily minimum-temperature forecasts; {len(days)} are available."
    try:
        dates = [datetime.strptime(day.get("date", ""), "%Y-%m-%d").date() for day in days]
    except (TypeError, ValueError):
        return None, "Daily forecast dates must be valid ISO calendar dates for this rule."
    if any((dates[index] - dates[index - 1]).days != 1 for index in range(1, len(dates))):
        return None, "Daily forecast dates are not consecutive; the rule window cannot be evaluated."
    values = [day.get("temperature_min_c") for day in days]
    if any(value is None for value in values):
        return None, "Daily minimum-temperature data is incomplete for this rule window."
    comparator = (lambda value: value > threshold) if rule["operator"] == "gt" else (lambda value: value >= threshold)
    exposed = [{"date": day["date"], "temperature_min_c": day["temperature_min_c"]}
               for day in days if comparator(day["temperature_min_c"])]
    index = _weather_exposure_index(len(exposed), len(days), "daily Tmin forecasts", days[0]["date"], days[-1]["date"])
    return {
        "assessment_type": "deterministic_exposure_indicator", "triggered_days": exposed,
        "forecast_days": len(days), "window_start": days[0]["date"], "window_end": days[-1]["date"],
        "measured_min": min(values), "measured_max": max(values), "forecast_unit": "deg C",
        "threshold_in_forecast_unit": threshold, "severity": None, **index,
    }, None


def _forecast_hour(value):
    try:
        return int(value[11:13])
    except (TypeError, ValueError, IndexError):
        return -1


def _indicator_rule_assessment(rule, result):
    triggered = result.get("triggered_hours", result.get("triggered_days", []))
    details = result["risk_index_details"]
    return {
        "rule_id": rule.get("rule_id"),
        "evaluation_status": "trigger_detected" if triggered else "no_trigger_detected",
        "risk_index": result["risk_index"],
        "risk_index_type": result["risk_index_type"],
        "risk_index_details": details,
        "threshold": rule.get("threshold"),
        "operator": rule.get("operator"),
        "unit": rule.get("unit"),
        "window_start": details["window_start"],
        "window_end": details["window_end"],
    }


def analyze_forecast(crop, weather, knowledge, growth_stage=None, region=None, verified_rules=None):
    """Assess hazards independently using provenance-reviewed registry rules."""
    crop = crop if isinstance(crop, dict) else {}
    crop_name = crop.get("crop_name") or crop.get("crop") or "Unknown crop"
    canonical, candidates = resolve_crop(crop_name)
    stage = growth_stage or crop.get("growth_stage") or crop.get("current_stage")
    # Country may establish national rule scope, but is not reported as a saved
    # state. The missing-input list below preserves absent farm-state context.
    state = region or crop.get("state") or crop.get("region") or crop.get("country")
    farm_state = crop.get("state") or crop.get("region")
    summary = _weather_summary(weather)
    all_rules = load_rule_records() if verified_rules is None else list(verified_rules)
    crop_id = (canonical or {}).get("crop_id")
    verified = [rule for rule in all_rules if _applicable(rule, crop_id, stage, state)] if crop_id else []
    latitude = _finite(crop.get("latitude", crop.get("lat")), -90, 90)
    longitude = _finite(crop.get("longitude", crop.get("lon")), -180, 180)
    weather_lat = _finite((weather or {}).get("latitude"), -90, 90) if isinstance(weather, dict) else None
    weather_lon = _finite((weather or {}).get("longitude"), -180, 180) if isinstance(weather, dict) else None
    context_failures = []
    if summary.get("provider") == "demo":
        context_failures.append("A simulated demo forecast cannot be used for crop-risk assessment.")
    if latitude is None or longitude is None:
        context_failures.append("Valid farm coordinates are missing.")
    if weather_lat is None or weather_lon is None:
        context_failures.append("The forecast provider did not return coordinates, so this forecast cannot be matched to the crop location.")
    if ((latitude is not None and weather_lat is not None and abs(latitude - weather_lat) > 0.1)
            or (longitude is not None and weather_lon is not None and abs(longitude - weather_lon) > 0.1)):
        context_failures.append("The weather forecast coordinates do not match this crop location.")
    hazards = []
    alerts = []
    for code, title in HAZARDS:
        rules_for_hazard = [rule for rule in verified if rule.get("hazard_type") == code]
        if not rules_for_hazard:
            candidates = [rule for rule in all_rules if rule.get("crop_id") == crop_id and rule.get("hazard_type") == code]
            crop_hazard_rules = [rule for rule in candidates if rule.get("verification_status") == "verified"]
            unverified = [rule for rule in candidates if rule.get("verification_status") != "verified"]
            skipped_rules = [
                {"rule_id": rule.get("rule_id"), "reason": _applicability_reason(rule, stage, state)}
                for rule in candidates
                if _applicability_reason(rule, stage, state)
            ]
            explanation = "No verified rule applies to this crop, growth stage and region."
            evaluation_status = "no_applicable_rule"
            if any("Growth stage is missing" in item["reason"] for item in skipped_rules):
                explanation = "Growth stage is missing; add or update the crop stage to check these stage-specific rules."
                evaluation_status = "insufficient_data"
            elif any("Farm state or region is missing" in item["reason"] for item in skipped_rules):
                explanation = "Farm region is missing; add the farm state to match region-specific rules."
                evaluation_status = "insufficient_data"
            elif unverified:
                explanation = "Candidate rules exist but are unverified or have incomplete source validation and are excluded from scoring."
            elif skipped_rules:
                explanation = skipped_rules[0]["reason"]
            hazards.append({"hazard": code, "title": title, "status": "unavailable", "evaluation_status": evaluation_status, "risk_index": None, "severity": None, "explanation": explanation, "reason": explanation, "matched_rule_ids": [], "skipped_rule_ids": [item["rule_id"] for item in skipped_rules if item.get("rule_id")], "skipped_rules": skipped_rules, "measured_values": [], "thresholds": [{"rule_id": rule.get("rule_id"), "value": rule.get("threshold"), "unit": rule.get("unit")} for rule in candidates if rule.get("threshold") is not None], "triggered_rules": [], "recommended_actions": [], "sources": [_source(rule) for rule in candidates]})
            continue
        results = []
        failures = list(context_failures)
        skipped_rules = []
        for rule in rules_for_hazard:
            if context_failures:
                skipped_rules.append({"rule_id": rule.get("rule_id"), "reason": "; ".join(context_failures)})
                continue
            rule_stages = rule.get("growth_stage", "")
            if not isinstance(rule_stages, list):
                rule_stages = [rule_stages]
            if stage is None and not any(normalize_stage(value) in ("", "all") for value in rule_stages):
                reason = "Record the growth stage to check this stage-specific rule."
                failures.append(reason)
                skipped_rules.append({"rule_id": rule.get("rule_id"), "reason": reason})
                continue
            applicability_reason = _applicability_reason(rule, stage, state)
            if applicability_reason:
                failures.append(applicability_reason)
                skipped_rules.append({"rule_id": rule.get("rule_id"), "reason": applicability_reason})
                continue
            result, failure = _evaluate_rule(rule, summary)
            if result is not None:
                results.append((rule, result))
            elif failure:
                failures.append(failure)
                skipped_rules.append({"rule_id": rule.get("rule_id"), "reason": failure})
        if not results:
            reason = "; ".join(dict.fromkeys(failures)) or "No valid weather data matched this rule."
            hazards.append({"hazard": code, "title": title, "status": "unavailable", "evaluation_status": "insufficient_data", "risk_index": None, "severity": None, "explanation": reason, "reason": reason, "matched_rule_ids": [rule.get("rule_id") for rule in rules_for_hazard if rule.get("rule_id")], "skipped_rules": skipped_rules, "measured_values": [], "thresholds": [{"rule_id": rule.get("rule_id"), "value": rule.get("threshold"), "unit": rule.get("unit")} for rule in rules_for_hazard], "triggered_rules": [], "recommended_actions": [], "sources": [_source(rule) for rule in rules_for_hazard]})
            continue
        if len(results) > 1 and all(item[1].get("assessment_type") == "deterministic_exposure_indicator" for item in results):
            rule_assessments = []
            triggered_rules = []
            measured_values = []
            recommendations = []
            alerts_for_hazard = []
            for candidate_rule, candidate_result in results:
                assessment = _indicator_rule_assessment(candidate_rule, candidate_result)
                rule_assessments.append(assessment)
                events = candidate_result.get("triggered_hours", candidate_result.get("triggered_days", []))
                if events:
                    triggered_rules.append({
                        "rule_id": candidate_rule.get("rule_id"),
                        "weather_parameter": candidate_rule.get("weather_parameter"),
                        "operator": candidate_rule.get("operator"),
                        "threshold": candidate_rule.get("threshold"),
                        "unit": candidate_rule.get("unit"), **candidate_result,
                    })
                    recommendations.extend(candidate_rule.get("recommended_actions", []))
                    first = events[0]
                    if "triggered_hours" in candidate_result:
                        expected_time = first.get("time")
                        condition = f"Forecast hourly air temperature is {first.get('temperature_c')} {candidate_rule['unit']} (threshold {candidate_rule['operator']} {candidate_rule['threshold']} {candidate_rule['unit']}); {len(events)} forecast hour(s) match. This is weather exposure, not confirmed crop damage."
                    else:
                        expected_time = first.get("date")
                        field = "temperature_min_c" if candidate_rule.get("daily_field") == "temperature_min" else "temperature_max_c"
                        condition = f"Forecast daily {candidate_rule['daily_field']} is {first.get(field)} {candidate_rule['unit']} on {first.get('date')} (threshold {candidate_rule['operator']} {candidate_rule['threshold']} {candidate_rule['unit']}). This is weather exposure, not confirmed crop damage."
                    alerts_for_hazard.append(_indicator_alert(candidate_rule, crop_name, code, expected_time, condition, summary.get("timezone")))
                measured_values.append({
                    "rule_id": candidate_rule.get("rule_id"),
                    "parameter": candidate_rule.get("weather_parameter"),
                    "minimum": candidate_result.get("measured_min"),
                    "maximum": candidate_result.get("measured_max"),
                    "unit": candidate_result.get("forecast_unit"),
                    "window_start": candidate_result.get("window_start"),
                    "window_end": candidate_result.get("window_end"),
                    "triggered_observations": len(events),
                    "valid_observations": candidate_result["risk_index_details"]["valid_observations"],
                })
            evaluation_status = "trigger_detected" if triggered_rules else "no_trigger_detected"
            explanation = (f"{len(rule_assessments)} verified rules were evaluated independently. "
                           "Their exposure indices are kept separate because their thresholds or observation windows differ.")
            hazards.append({
                "hazard": code, "title": title, "status": "assessed", "evaluation_status": evaluation_status,
                "assessment_type": "deterministic_exposure_indicator", "risk_index": None,
                "risk_index_type": "separate_per_rule_weather_exposure_shares", "risk_index_details": None,
                "severity": None, "explanation": explanation, "reason": explanation,
                "matched_rule_ids": [rule.get("rule_id") for rule, _result in results],
                "rule_assessments": rule_assessments, "measured_values": measured_values,
                "thresholds": [{"rule_id": rule.get("rule_id"), "value": rule.get("threshold"), "unit": rule.get("unit")} for rule, _result in results],
                "triggered_rules": triggered_rules, "recommended_actions": list(dict.fromkeys(recommendations)),
                "sources": [_source(rule) for rule, _result in results],
                "limitations": list(dict.fromkeys(limit for rule, _result in results for limit in rule.get("limitations", []))),
            })
            alerts.extend(alerts_for_hazard)
            continue
        rule, result = max(results, key=lambda item: item[1].get("risk_index") or 0)
        threshold = rule["threshold"]
        if result.get("assessment_type") == "deterministic_exposure_indicator":
            if "triggered_hours" in result:
                events = result["triggered_hours"]
                triggered = bool(events)
                evaluation_status = "trigger_detected" if triggered else "no_trigger_detected"
                if triggered:
                    times = ", ".join(f"{item['time']} ({item['temperature_c']} Â°C)" for item in events)
                    explanation = (f"Forecast hourly air temperature was above {threshold} {rule['unit']} at {times}. "
                                   "These are weather-favourable exposure hours, not evidence of crop damage.")
                    triggered_rules = [{"rule_id": rule.get("rule_id"), "weather_parameter": rule["weather_parameter"],
                                        "operator": rule["operator"], "threshold": threshold, "unit": rule["unit"], **result}]
                else:
                    explanation = (f"No hourly forecast temperature exceeded {threshold} {rule['unit']} in the "
                                   f"{result['forecast_hours']}-hour window. This only assesses this indicator.")
                    triggered_rules = []
                index_details = result["risk_index_details"]
                hazards.append({
                    "hazard": code, "title": title, "status": "assessed", "evaluation_status": evaluation_status,
                    "assessment_type": result["assessment_type"], "risk_index": result["risk_index"],
                    "risk_index_type": result["risk_index_type"], "risk_index_details": index_details, "severity": None,
                    "rule_assessments": [_indicator_rule_assessment(rule, result)],
                    "explanation": explanation, "reason": explanation, "matched_rule_ids": [rule.get("rule_id")],
                    "measured_values": [{"parameter": rule.get("weather_parameter"), "minimum": result["measured_min"],
                                         "maximum": result["measured_max"], "unit": result["forecast_unit"],
                                         "window_start": result["window_start"], "window_end": result["window_end"],
                                         "triggered_hours": events}],
                    "thresholds": [{"rule_id": rule.get("rule_id"), "value": rule.get("threshold"), "unit": rule.get("unit")}],
                    "triggered_rules": triggered_rules, "recommended_actions": [],
                    "sources": [_source(rule)], "limitations": rule.get("limitations", []),
                })
                if triggered:
                    first = events[0]
                    alerts.append(_indicator_alert(
                        rule, crop_name, code, first.get("time"),
                        f"Forecast hourly air temperature is {first.get('temperature_c')} {rule['unit']} (threshold {rule['operator']} {threshold} {rule['unit']}); {len(events)} forecast hour(s) match. This is weather exposure, not confirmed crop damage.",
                        summary.get("timezone"),
                    ))
                continue
            triggered_days = result.get("triggered_days", [])
            triggered = bool(triggered_days)
            evaluation_status = "trigger_detected" if triggered else "no_trigger_detected"
            if triggered:
                if triggered_days and rule.get("daily_field") == "temperature_min":
                    day_values = ", ".join(f"{day['date']} ({day['temperature_min_c']}°C)" for day in triggered_days)
                    details = (f"Daily forecast minimum temperature is at or above {threshold} {rule['unit']} on "
                               f"{day_values}. "
                               "This is outside the source's stated preferred tuberization condition; it does not establish crop damage.")
                elif triggered_days:
                    details = f"Daily forecast maximum temperature exceeds {threshold} {rule['unit']} on {', '.join(day['date'] for day in triggered_days)}."
                explanation = details + " This is a deterministic weather-exposure indicator, not a probability of crop damage."
                triggered_rules = [{"rule_id": rule.get("rule_id"), "weather_parameter": rule["weather_parameter"],
                                    "operator": rule["operator"], "threshold": threshold, "unit": rule["unit"], **result}]
            else:
                if "forecast_days" in result:
                    measure = "minimum" if rule.get("daily_field") == "temperature_min" else "maximum"
                    relation = "reached" if rule.get("daily_field") == "temperature_min" else "exceeded"
                    explanation = (f"No daily forecast {measure} temperature {relation} {threshold} {rule['unit']} in the "
                                   f"{result['forecast_days']}-day rule window. This only assesses this indicator.")
                triggered_rules = []
            index_details = result["risk_index_details"]
            hazards.append({
                "hazard": code, "title": title, "status": "assessed", "evaluation_status": evaluation_status,
                "assessment_type": result["assessment_type"], "risk_index": result["risk_index"],
                "risk_index_type": result["risk_index_type"], "risk_index_details": index_details, "severity": None,
                "rule_assessments": [_indicator_rule_assessment(rule, result)],
                "explanation": explanation, "reason": explanation, "matched_rule_ids": [rule.get("rule_id")],
                "measured_values": [{"parameter": rule.get("weather_parameter"), "minimum": result["measured_min"],
                                     "maximum": result["measured_max"], "unit": result["forecast_unit"],
                                     "window_start": result["window_start"], "window_end": result["window_end"],
                                     "triggered_days": triggered_days}],
                "thresholds": [{"rule_id": rule.get("rule_id"), "value": rule.get("threshold"), "unit": rule.get("unit")}],
                "triggered_rules": triggered_rules,
                "recommended_actions": rule.get("recommended_actions", []) if triggered else [],
                "sources": [_source(rule)], "limitations": rule.get("limitations", []),
            })
            if triggered:
                first = triggered_days[0]
                field = "temperature_min_c" if rule.get("daily_field") == "temperature_min" else "temperature_max_c"
                alerts.append(_indicator_alert(
                    rule, crop_name, code, first.get("date"),
                    f"Forecast daily {rule['daily_field']} is {first.get(field)} {rule['unit']} on {first.get('date')} (threshold {rule['operator']} {threshold} {rule['unit']}). This is a deterministic weather indicator, not a prediction of crop damage.",
                    summary.get("timezone"),
                ))
            continue
        if result["exposed_hours"]:
            explanation = (f"Forecast {rule['weather_parameter']} crossed the {rule['operator']} {threshold} {rule['unit']} threshold "
                           f"in {result['exposed_hours']} of {result['forecast_hours']} hourly samples. "
                           "This indicates weather exposure only; it does not predict disease or crop loss.")
            triggered_rules = [{"rule_id": rule.get("rule_id"), "weather_parameter": rule["weather_parameter"], "operator": rule["operator"], "threshold": threshold, "unit": rule["unit"], **result}]
        else:
            explanation = f"No hourly sample crossed the {rule['operator']} {threshold} {rule['unit']} threshold during the configured forecast window. This only assesses this rule; other hazards may still apply."
            triggered_rules = []
        hazard_item = {"hazard": code, "title": title, "status": "assessed", "evaluation_status": "evaluated" if triggered_rules else "no_trigger_detected", "risk_index": result["risk_index"], "severity": result["severity"], "explanation": explanation, "reason": explanation, "matched_rule_ids": [rule.get("rule_id")], "measured_values": [{"parameter": rule.get("weather_parameter"), "minimum": result["measured_min"], "maximum": result["measured_max"], "exposed_samples": result["exposed_hours"], "forecast_samples": result["forecast_hours"], "unit": result["forecast_unit"], "window_start": result["window_start"], "window_end": result["window_end"]}], "thresholds": [{"rule_id": rule.get("rule_id"), "value": rule.get("threshold"), "unit": rule.get("unit")}], "triggered_rules": triggered_rules, "recommended_actions": rule.get("recommended_actions", []) if triggered_rules else [], "sources": [_source(rule)], "limitations": rule.get("limitations", [])}
        hazards.append(hazard_item)
        if triggered_rules:
            alerts.append({"risk_type": code, "title": f"{title} exposure watch: {crop_name}", "severity": result["severity"], "expected_time": result.get("first_exposure_at") or "next 48 hours", "explanation": explanation, "recommended_actions": hazard_item["recommended_actions"], "sources": hazard_item["sources"]})

    # A stable four-state field lets API consumers distinguish a valid no-trigger
    # evaluation from missing inputs and from a crop/hazard with no verified rule.
    for item in hazards:
        if item.get("status") == "assessed":
            item["outcome"] = "ASSESSED/NO_TRIGGER" if item.get("evaluation_status") == "no_trigger_detected" else "ASSESSED/TRIGGERED"
        elif item.get("evaluation_status") == "insufficient_data":
            item["outcome"] = "INSUFFICIENT_DATA"
        else:
            item["outcome"] = "UNSUPPORTED"

    assessed = [item for item in hazards if item["status"] == "assessed" and item["risk_index"] is not None
                and item.get("assessment_type") != "deterministic_exposure_indicator"]
    indicator_assessed = [item for item in hazards if item["status"] == "assessed" and item.get("assessment_type") == "deterministic_exposure_indicator"]
    complete_assessment = bool(assessed) and len(assessed) == len(HAZARDS)
    risk_score = max((item["risk_index"] for item in assessed), default=None)
    overall = max(assessed, key=lambda item: item["risk_index"])["severity"] if complete_assessment else "PARTIAL" if assessed or indicator_assessed else "UNAVAILABLE"
    missing = []
    if summary.get("provider") == "demo":
        missing.append("Weather is a simulated demo scenario; it is not assessed as a crop-specific forecast.")
    if not summary["forecast_days"]:
        missing.append("No valid daily forecast observations were provided.")
    if latitude is None or longitude is None:
        missing.append("Valid farm coordinates are missing.")
    if weather_lat is None or weather_lon is None:
        missing.append("Forecast coordinates are missing; crop location cannot be verified against this forecast.")
    if ((latitude is not None and weather_lat is not None and abs(latitude - weather_lat) > 0.1)
            or (longitude is not None and weather_lon is not None and abs(longitude - weather_lon) > 0.1)):
        missing.append("The weather forecast coordinates do not match this crop location.")
    if stage is None:
        missing.append("Growth stage is missing; stage-specific rules cannot be evaluated.")
    if not farm_state:
        missing.append("Farm state is missing; state-specific applicability cannot be verified.")
    if summary.get("provider_status") == "unavailable":
        provider_error = summary.get("provider_error")
        detail = f" Provider detail: {provider_error}" if provider_error else ""
        missing.append(f"Weather provider is unavailable; no forecast observations can be assessed.{detail}")
    elif summary["stale"]:
        provider_error = summary.get("provider_error")
        cache_age = summary.get("cache_age_seconds")
        age_note = f" The cached forecast is {cache_age} seconds old." if isinstance(cache_age, (int, float)) else ""
        error_note = f" Provider detail: {provider_error}" if provider_error else ""
        missing.append(f"Live weather refresh failed; assessment is limited because this cached forecast is stale.{age_note}{error_note}")
    status = "assessed" if complete_assessment else "partially_assessed" if assessed or indicator_assessed else "unavailable"
    # A separate, clearly labelled estimate covers crops that have no verified
    # rule. It never changes the verified status, risk_score or alert semantics
    # above, and callers must keep it visually distinct.
    model_assessment = assess_crop_weather_risk(
        crop, weather, growth_stage=stage, region=state, weather_summary=summary,
    )
    return {
        "overall_risk": overall,
        "risk_score": risk_score,
        "risk_index_type": "partial forecast exposure index; assessed hazards only, not a probability" if risk_score is not None and not complete_assessment else "forecast exposure index; not a probability" if risk_score is not None else None,
        "status": status,
        "crop_id": crop_id,
        "crop_name": (canonical or {}).get("canonical_name", crop_name),
        "crop_candidates": candidates if not canonical else [],
        "growth_stage": stage,
        "region": state,
        "location": {key: crop.get(key) for key in ("latitude", "longitude", "city", "district", "state") if crop.get(key) is not None},
        "crop_context": {key: crop.get(key) for key in ("variety", "planting_date", "growth_stage", "country", "soil_type", "drainage_condition", "irrigation_availability")},
        "knowledge_status": "VERIFIED" if status == "assessed" else "PARTIAL" if assessed or indicator_assessed else "LIMITED",
        "summary": "A deterministic weather-exposure indicator is available; no overall crop-risk score is calculated." if indicator_assessed and not assessed else "Some source-backed hazard assessments are available; the overall crop risk remains incomplete." if status == "partially_assessed" else "A source-backed assessment is available for all configured hazards." if assessed else UNAVAILABLE_MESSAGE,
        "hazards": hazards,
        "alerts": alerts,
        "model_assessment": model_assessment,
        "limitations": ["Hazard indices and deterministic indicators are weather assessments, not probabilities of crop damage.", *(["Candidate rules marked unverified were excluded from scoring."] if any(rule.get("verification_status") != "verified" for rule in all_rules) else []), *(["An overall crop risk score is withheld because some hazards do not have a verified applicable rule and evaluator. Review the individual assessed hazards below."] if status == "partially_assessed" else []), *missing],
        "missing_inputs": missing,
        "weather_observations": {key: value for key, value in summary.items() if key != "hourly_observations"},
        "evidence": [source for item in hazards for source in item.get("sources", [])],
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
    }
