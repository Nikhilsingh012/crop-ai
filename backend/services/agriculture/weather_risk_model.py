"""Transparent crop-specific weather-risk estimate for every catalog crop.

The verified rule registry in :mod:`crop_risk_engine` remains the only source
used for source-backed hazard findings.  This module adds a separate,
explicitly labelled agronomic estimate so that a crop without a verified rule
still receives a meaningful, colour-coded risk percentage instead of
"unavailable".  It is a deterministic heuristic, never a probability of crop
loss.
"""
from __future__ import annotations

import json
import math
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.crop_catalog import crop_by_id, resolve_crop

MODEL_CONFIG_PATH = Path(__file__).resolve().parents[3] / "data" / "crop_knowledge" / "weather_risk_model.json"
CROP_KNOWLEDGE_PATH = Path(__file__).resolve().parents[3] / "data" / "crop_knowledge" / "crops.json"

_STAGE_ALIASES = {
    "grain fill": "grain_filling",
    "grain filling": "grain_filling",
    "grain formation": "grain_filling",
    "tuberisation": "tuber_initiation",
    "tuberization": "tuber_initiation",
    "tuber initiation": "tuber_initiation",
    "tuber development": "tuber_initiation",
    "reproductive": "flowering",
    "blooming": "flowering",
    "anthesis": "flowering",
    "fruit set": "fruiting",
    "fruit development": "fruiting",
    "podding": "fruiting",
    "seedling": "seedling",
    "vegetative": "vegetative",
    "germination": "germination",
    "maturity": "maturity",
    "harvest": "harvest",
}
_IRRIGATION_WORDS = ("irrig", "drip", "canal", "bore", "tube", "sprinkler", "well", "pump")


def _finite(value: Any, minimum: float | None = None, maximum: float | None = None) -> float | None:
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


def _normal_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    return " ".join(text.lower().replace("_", " ").replace("-", " ").split())


def normalize_stage_key(value: Any) -> str:
    key = _normal_text(value)
    return _STAGE_ALIASES.get(key, key.replace(" ", "_"))


def _ramp(value: float | None, start: float, full: float) -> float | None:
    """Return 0..100 as value moves from start to full."""
    if value is None:
        return None
    if full <= start:
        return 100.0 if value >= full else 0.0
    return max(0.0, min(100.0, (value - start) / (full - start) * 100.0))


def _mean(values: list[float]) -> float | None:
    clean = [value for value in values if value is not None]
    return sum(clean) / len(clean) if clean else None


def load_model_config() -> dict[str, Any]:
    payload = json.loads(MODEL_CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Weather risk model config must be a JSON object.")
    return payload


def _load_knowledge_profiles() -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(CROP_KNOWLEDGE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        item["crop_id"]: item
        for item in payload
        if isinstance(item, dict) and isinstance(item.get("crop_id"), str)
    }


def _profile_for(crop_id: str | None, category: str | None, config: dict[str, Any]):
    """Return (profile, provenance, detailed knowledge record)."""
    categories = config.get("category_profiles", {})
    overrides = config.get("crop_overrides", {})
    knowledge = _load_knowledge_profiles()
    base_key = category if category in categories else "generic"
    profile = dict(categories.get(base_key, categories.get("generic", {})))
    profile["weekly_water_need_mm"] = profile.get("weekly_water_need_mm", 22)
    source = "category_default"
    detail = None

    override = overrides.get(crop_id) if crop_id else None
    if isinstance(override, dict):
        profile.update(override)
        profile["weekly_water_need_mm"] = override.get(
            "weekly_water_need_mm", profile["weekly_water_need_mm"]
        )
        source = "crop_specific_tuning"

    detail = knowledge.get(crop_id) if crop_id else None
    if isinstance(detail, dict):
        for key in (
            "optimal_temperature_c",
            "heat_threshold_c",
            "cold_threshold_c",
            "heavy_rain_mm",
            "waterlogging_sensitivity",
            "drought_sensitivity",
            "humidity_threshold",
            "wind_threshold_kmh",
            "risks",
        ):
            if detail.get(key) is not None:
                profile[key] = detail[key]
        # Detailed knowledge records do not define a weekly water need; keep
        # the category value already in the profile.
        source = "crop_knowledge"
    return profile, source, detail


def _summary_from_weather(weather: dict[str, Any]) -> dict[str, Any]:
    """Minimal local normaliser used when the engine summary is not supplied."""
    days = []
    for day in weather.get("forecast") or []:
        if not isinstance(day, dict):
            continue
        days.append(
            {
                "date": day.get("date") if isinstance(day.get("date"), str) else None,
                "rainfall_mm": _finite(day.get("rainfall"), 0),
                "temperature_max_c": _finite(day.get("temperature_max"), -100, 70),
                "temperature_min_c": _finite(day.get("temperature_min"), -100, 70),
                "precipitation_probability_percent": _finite(day.get("precipitation_probability"), 0, 100),
            }
        )
    hourly = []
    for hour in weather.get("hourly_forecast") or []:
        if not isinstance(hour, dict):
            continue
        hourly.append(
            {
                "time": hour.get("time") if isinstance(hour.get("time"), str) else None,
                "rainfall_mm": _finite(hour.get("rainfall"), 0),
                "temperature_c": _finite(hour.get("temperature"), -100, 70),
                "humidity_percent": _finite(hour.get("humidity"), 0, 100),
                "wind_speed_kmh": _finite(hour.get("wind_speed"), 0, 500),
            }
        )
    return {
        "forecast_days": days[:7],
        "hourly_observations": hourly[:48],
        "current_temperature_c": _finite(weather.get("temperature"), -100, 70),
        "current_humidity_percent": _finite(weather.get("humidity"), 0, 100),
        "current_rainfall_mm": _finite(weather.get("rainfall"), 0),
        "current_wind_speed_kmh": _finite(weather.get("wind_speed"), 0, 500),
        "provider": weather.get("provider"),
        "provider_status": weather.get("provider_status"),
        "stale": bool(weather.get("stale")),
        "timezone": weather.get("timezone"),
        "forecast_issued_at": weather.get("forecast_issued_at"),
    }


def _derive_days_from_hourly(hourly: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {"temps": [], "mins": [], "rain": []})
    for hour in hourly:
        timestamp = hour.get("time")
        if not isinstance(timestamp, str) or len(timestamp) < 10:
            continue
        bucket = grouped[timestamp[:10]]
        if hour.get("temperature_c") is not None:
            bucket["temps"].append(hour["temperature_c"])
        if hour.get("temperature_c") is not None:
            bucket["mins"].append(hour["temperature_c"])
        if hour.get("rainfall_mm") is not None:
            bucket["rain"].append(hour["rainfall_mm"])
    return [
        {
            "date": date,
            "rainfall_mm": round(sum(values["rain"]), 1) if values["rain"] else None,
            "temperature_max_c": max(values["temps"]) if values["temps"] else None,
            "temperature_min_c": min(values["mins"]) if values["mins"] else None,
            "precipitation_probability_percent": None,
        }
        for date, values in sorted(grouped.items())
    ]


def _stage_factor(config: dict[str, Any], hazard: str, stage_key: str) -> float:
    multipliers = config.get("stage_multipliers", {}).get(hazard, {})
    return float(multipliers.get(stage_key, 1.0))


def _level_for(score: float, bands: list[dict[str, Any]]) -> dict[str, Any]:
    rounded = int(round(score))
    for band in bands:
        if float(band.get("minimum", 0)) <= rounded <= float(band.get("maximum", 100)):
            return band
    return bands[-1]


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_result(reason: str, crop_name: str, crop_id: str | None, location: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "insufficient_data",
        "source": "weather_risk_model",
        "model": {
            "name": config.get("name"),
            "version": config.get("version"),
            "method": config.get("method"),
            "is_probability": False,
        },
        "crop_id": crop_id,
        "crop_name": crop_name,
        "risk_percent": None,
        "safe_percent": None,
        "level": "UNAVAILABLE",
        "tone": "unavailable",
        "alert": False,
        "watch": False,
        "label": "Estimate unavailable",
        "summary": f"Estimated weather risk is unavailable: {reason}",
        "factors": [],
        "recommendations": [],
        "confidence": "none",
        "confidence_reason": reason,
        "profile_source": None,
        "location": location,
        "limitations": [reason, config.get("disclaimer", "")],
        "generated_at": _iso_now(),
    }


def assess_crop_weather_risk(
    crop: dict[str, Any] | None,
    weather: dict[str, Any] | None,
    growth_stage: str | None = None,
    region: str | None = None,
    weather_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Estimate crop-specific weather risk from the local forecast.

    The returned percentage is an agronomic screening estimate.  It deliberately
    does not reuse or replace the provenance-checked rule scores produced by
    ``crop_risk_engine.analyze_forecast``.
    """
    config = load_model_config()
    bands = config.get("score_scale", {}).get("bands", [])
    crop = crop if isinstance(crop, dict) else {}
    weather = weather if isinstance(weather, dict) else {}
    crop_name = crop.get("crop_name") or crop.get("crop") or "Unknown crop"
    canonical, _candidates = resolve_crop(crop_name)
    crop_id = (canonical or {}).get("crop_id")
    canonical_name = (canonical or {}).get("canonical_name", crop_name)
    catalog = crop_by_id(crop_id) if crop_id else None
    location = {
        key: crop.get(key)
        for key in ("city", "district", "state", "latitude", "longitude")
        if crop.get(key) is not None
    }
    location_label = ", ".join(
        str(value) for value in (crop.get("city"), crop.get("district"), crop.get("state")) if value
    ) or (region or "")

    if weather.get("provider") == "demo":
        return _empty_result(
            "the forecast is a simulated demo scenario, not live location weather",
            canonical_name,
            crop_id,
            location,
            config,
        )

    summary = weather_summary if isinstance(weather_summary, dict) else _summary_from_weather(weather)
    days = [day for day in summary.get("forecast_days") or [] if isinstance(day, dict)]
    hourly = [hour for hour in summary.get("hourly_observations") or [] if isinstance(hour, dict)]
    if not days and hourly:
        days = _derive_days_from_hourly(hourly)
    if not days and not hourly and summary.get("current_temperature_c") is None:
        return _empty_result(
            "no usable forecast observations were returned for this location",
            canonical_name,
            crop_id,
            location,
            config,
        )
    if summary.get("stale") and not days and not hourly:
        return _empty_result(
            "the cached forecast is stale and no usable observations remain",
            canonical_name,
            crop_id,
            location,
            config,
        )

    profile, profile_source, detail = _profile_for(crop_id, (catalog or {}).get("category"), config)
    stage = growth_stage or crop.get("growth_stage") or crop.get("current_stage")
    stage_key = normalize_stage_key(stage) if stage else ""
    risks = {_normal_text(value).replace(" ", "_") for value in profile.get("risks") or []}
    opt = profile.get("optimal_temperature_c") or [15, 30]
    opt_min = float(opt[0])
    opt_max = float(opt[1])
    heat_threshold = float(profile.get("heat_threshold_c", opt_max + 3))
    cold_threshold = float(profile.get("cold_threshold_c", opt_min - 6))
    heavy_rain = max(1.0, float(profile.get("heavy_rain_mm", 40)))
    humidity_threshold = float(profile.get("humidity_threshold", 80))
    wind_threshold = max(1.0, float(profile.get("wind_threshold_kmh", 42)))
    waterlogging_sensitivity = float(profile.get("waterlogging_sensitivity", 0.65))
    drought_sensitivity = float(profile.get("drought_sensitivity", 0.6))
    weekly_need = max(1.0, float(profile.get("weekly_water_need_mm", 22)))

    hazards = config.get("hazard_labels", {})
    weights = config.get("weights", {})
    factors: list[dict[str, Any]] = []

    def add_factor(key: str, raw: float | None, sensitivity: float, evidence: str):
        if raw is None:
            return
        score = max(0.0, min(100.0, raw * sensitivity * _stage_factor(config, key, stage_key)))
        level = _level_for(score, bands)
        factors.append(
            {
                "key": key,
                "label": hazards.get(key, key.title()),
                "score": int(round(score)),
                "level": level.get("level"),
                "tone": level.get("tone"),
                "weight": weights.get(key),
                "evidence": evidence,
            }
        )

    # Heat stress -----------------------------------------------------------
    heat_scores: list[tuple[str | None, float, float]] = []
    for day in days[:6]:
        value = day.get("temperature_max_c")
        if value is None:
            continue
        if value <= opt_max:
            score = 0.0
        elif value < heat_threshold:
            score = 55.0 * (value - opt_max) / max(0.1, heat_threshold - opt_max)
        else:
            score = 55.0 + 45.0 * min(1.0, (value - heat_threshold) / 4.0)
        heat_scores.append((day.get("date"), score, value))
    hourly_heat = [(hour.get("time"), hour.get("temperature_c")) for hour in hourly if hour.get("temperature_c") is not None]
    if hourly_heat:
        peak_time, peak_temp = max(hourly_heat, key=lambda item: item[1])
        if peak_temp > opt_max:
            if peak_temp < heat_threshold:
                score = 55.0 * (peak_temp - opt_max) / max(0.1, heat_threshold - opt_max)
            else:
                score = 55.0 + 45.0 * min(1.0, (peak_temp - heat_threshold) / 4.0)
            heat_scores.append((peak_time[:10] if isinstance(peak_time, str) else None, score, peak_temp))
    if heat_scores:
        # Six daily slots plus an optional hourly peak, so clamp the decay weight
        # rather than indexing past the end when both sources contribute.
        day_weights = [1.3, 1.2, 1.05, 0.95, 0.85, 0.8]
        heat_weights = [day_weights[min(index, len(day_weights) - 1)] for index in range(len(heat_scores))]
        weighted = sum(score * weight for weight, (_date, score, _value) in zip(heat_weights, heat_scores)) / sum(heat_weights)
        peak = max(heat_scores, key=lambda item: item[1])
        raw_heat = 0.65 * weighted + 0.35 * peak[1]
        evidence = (
            f"Forecast high reaches {round(peak[2], 1)}°C"
            + (f" ({peak[0]})" if peak[0] else "")
            + f"; the crop's comfort range ends near {round(opt_max, 1)}°C and heat threshold is {round(heat_threshold, 1)}°C."
        )
        add_factor("heat", raw_heat, 1.12 if "heat" in risks else 0.95, evidence)

    # Cold / frost ----------------------------------------------------------
    cold_scores: list[tuple[str | None, float, float]] = []
    for day in days[:6]:
        value = day.get("temperature_min_c")
        if value is None:
            continue
        if value >= opt_min:
            score = 0.0
        elif value > cold_threshold:
            score = 55.0 * (opt_min - value) / max(0.1, opt_min - cold_threshold)
        else:
            score = 55.0 + 45.0 * min(1.0, (cold_threshold - value) / 4.0)
        cold_scores.append((day.get("date"), score, value))
    if cold_scores:
        peak = max(cold_scores, key=lambda item: item[1])
        raw_cold = 0.65 * _mean([item[1] for item in cold_scores]) + 0.35 * peak[1]
        evidence = (
            f"Forecast low reaches {round(peak[2], 1)}°C"
            + (f" ({peak[0]})" if peak[0] else "")
            + f"; the crop's comfort range starts near {round(opt_min, 1)}°C and cold threshold is {round(cold_threshold, 1)}°C."
        )
        add_factor("cold", raw_cold, 1.1 if "cold" in risks else 0.94, evidence)

    # Excess rain / waterlogging -------------------------------------------
    rain_values = [(day.get("date"), day.get("rainfall_mm")) for day in days[:7] if day.get("rainfall_mm") is not None]
    if rain_values:
        peak_date, peak_rain = max(rain_values, key=lambda item: item[1])
        total_rain = sum(value for _date, value in rain_values)
        daily_score = _ramp(peak_rain, heavy_rain * 0.35, heavy_rain * 1.8) or 0.0
        accumulation_score = _ramp(total_rain, heavy_rain * 0.6, heavy_rain * 2.8) or 0.0
        raw_rain = 0.55 * daily_score + 0.45 * accumulation_score
        evidence = (
            f"Peak daily rain {round(peak_rain, 1)} mm"
            + (f" ({peak_date})" if peak_date else "")
            + f" and {round(total_rain, 1)} mm across the forecast window; the crop's heavy-rain reference is {round(heavy_rain, 1)} mm/day."
        )
        add_factor("rain", raw_rain, 0.75 + 0.5 * waterlogging_sensitivity, evidence)

    # Dry spell / moisture deficit -----------------------------------------
    dry_days = 0
    run = 0
    for day in days[:7]:
        rain = day.get("rainfall_mm")
        if rain is None:
            continue
        if rain < 1:
            run += 1
            dry_days = max(dry_days, run)
        else:
            run = 0
    if rain_values:
        total_rain = sum(value for _date, value in rain_values)
        irrigation = _normal_text(crop.get("irrigation_availability") or crop.get("irrigation_type") or "")
        if any(word in irrigation for word in _IRRIGATION_WORDS):
            irrigation_credit = weekly_need * 0.55
        else:
            irrigation_credit = 0.0
        shortfall = max(0.0, weekly_need - total_rain - irrigation_credit)
        deficit_score = _ramp(shortfall, weekly_need * 0.45, weekly_need * 1.2) or 0.0
        spell_score = _ramp(float(dry_days), 3.0, 10.0) or 0.0
        raw_dry = (0.65 * deficit_score + 0.35 * spell_score) * (0.45 + 0.6 * drought_sensitivity)
        irrigation_note = " with known irrigation assumed" if irrigation_credit else " without a recorded irrigation source"
        evidence = (
            f"{round(total_rain, 1)} mm forecast rain against an estimated {round(weekly_need, 1)} mm weekly need"
            f"{irrigation_note}; longest dry run is {dry_days} day(s)."
        )
        add_factor("dry", raw_dry, 1.0, evidence)

    # Humidity-driven disease weather --------------------------------------
    humidity_values = [hour.get("humidity_percent") for hour in hourly if hour.get("humidity_percent") is not None]
    current_humidity = summary.get("current_humidity_percent")
    if current_humidity is not None:
        humidity_values.append(current_humidity)
    mean_humidity = _mean(humidity_values)
    if mean_humidity is not None:
        base = _ramp(mean_humidity, humidity_threshold - 15, min(100.0, humidity_threshold + 15)) or 0.0
        high_share = (
            sum(1 for value in humidity_values if value >= humidity_threshold) / len(humidity_values)
            if humidity_values
            else 0.0
        )
        high_share_score = (_ramp(high_share * 100.0, 0.0, 80.0) or 0.0)
        wet_bonus = 8.0 if rain_values and sum(value for _date, value in rain_values) > 2 else 0.0
        raw_humidity = 0.65 * base + 0.35 * high_share_score + wet_bonus
        evidence = (
            f"Mean humidity {round(mean_humidity, 1)}% with {round(high_share * 100)}% of observations at or above "
            f"the crop's {round(humidity_threshold, 1)}% disease-favourable threshold."
        )
        add_factor("humidity", raw_humidity, 1.12 if "high_humidity" in risks else 0.92, evidence)

    # Wind / lodging --------------------------------------------------------
    wind_values = [hour.get("wind_speed_kmh") for hour in hourly if hour.get("wind_speed_kmh") is not None]
    current_wind = summary.get("current_wind_speed_kmh")
    if current_wind is not None:
        wind_values.append(current_wind)
    max_wind = max(wind_values) if wind_values else None
    if max_wind is not None:
        raw_wind = _ramp(max_wind, wind_threshold * 0.65, wind_threshold * 1.35) or 0.0
        evidence = f"Peak forecast wind {round(max_wind, 1)} km/h against the crop's {round(wind_threshold, 1)} km/h reference."
        add_factor("wind", raw_wind, 1.12 if "wind" in risks else 0.92, evidence)

    if not factors:
        return _empty_result(
            "the forecast did not contain enough usable crop-weather measurements",
            canonical_name,
            crop_id,
            location,
            config,
        )

    available_weight = sum(float(factor.get("weight") or 0) for factor in factors)
    weighted = (
        sum(factor["score"] * float(factor.get("weight") or 0) for factor in factors) / available_weight
        if available_weight
        else _mean([factor["score"] for factor in factors]) or 0.0
    )
    peak = max(factor["score"] for factor in factors)
    elevated = [factor for factor in factors if factor["score"] >= 50]
    high = [factor for factor in factors if factor["score"] >= 60]
    compound_boost = max(0, len(elevated) - 1) * 4 + (5 if len(high) >= 2 else 0)
    risk_percent = int(round(max(0.0, min(100.0, 0.65 * weighted + 0.35 * peak + min(10, compound_boost)))))
    safe_percent = 100 - risk_percent
    band = _level_for(float(risk_percent), bands)
    level = band.get("level", "LOW")
    top = max(factors, key=lambda factor: factor["score"])

    # Confidence reflects both data completeness and profile specificity.
    has_daily = len(days) >= 3
    has_hourly = len(hourly) >= 6
    if profile_source == "crop_knowledge" and has_daily and has_hourly and not summary.get("stale"):
        confidence = "high"
        confidence_reason = "Crop-specific agronomic profile with daily and hourly forecast observations."
    elif profile_source in {"crop_knowledge", "crop_specific_tuning"} and has_daily:
        confidence = "medium"
        confidence_reason = "Crop-specific profile with daily forecast observations; hourly detail is limited."
    elif has_daily and has_hourly:
        confidence = "medium"
        confidence_reason = "Category-level crop defaults with daily and hourly forecast observations."
    else:
        confidence = "low"
        confidence_reason = "Limited forecast detail or category-level defaults; treat this as a coarse screening estimate."

    actions: list[str] = []
    for factor in sorted(factors, key=lambda item: item["score"], reverse=True):
        if factor["score"] < 30:
            continue
        actions.extend(config.get("hazard_actions", {}).get(factor["key"], [])[:1])
        if factor["score"] >= 50:
            actions.extend(config.get("hazard_actions", {}).get(factor["key"], [])[1:2])
    if isinstance(detail, dict) and top["score"] >= 45:
        actions.extend(detail.get("preventive_actions") or [])
        stage_actions = detail.get("stages") or {}
        stage_label = str(stage or "").strip().lower()
        for label, action in stage_actions.items():
            if stage_label and _normal_text(label) in stage_label:
                actions.insert(0, action)
                break
    actions = [action.strip() for action in actions if isinstance(action, str) and action.strip()]
    recommendations = list(dict.fromkeys(actions))[:4]

    limitations = [config.get("disclaimer", "")]
    if profile_source == "crop_knowledge":
        limitations.append("Uses the crop-specific agronomic profile from the project knowledge base.")
    elif profile_source == "crop_specific_tuning":
        limitations.append(
            "Uses crop-specific tuning where available; no fully verified hazard rule covers this crop, stage and location."
        )
    else:
        limitations.append(
            f"No crop-specific profile was found; {str((catalog or {}).get('category') or 'generic').title()} category defaults were used. Treat this as a coarse screening estimate."
        )
    if not has_daily:
        limitations.append("Daily temperature and rainfall depth are limited; the estimate relies more on current and hourly values.")
    if not has_hourly:
        limitations.append("Hourly humidity and wind detail is limited; current conditions may be used as a fallback.")
    if not stage:
        limitations.append("Growth stage was not recorded; neutral stage multipliers were applied.")
    if summary.get("stale"):
        limitations.append("The weather provider is serving a cached forecast; refresh before acting on a close call.")
    limitations.append("Irrigation, soil, variety, microclimate and local management can change the actual outcome.")

    location_text = f" at {location_label}" if location_label else ""
    summary_text = (
        f"Estimated weather-related risk for {canonical_name}{location_text} is {risk_percent}% "
        f"({level.lower()}), leaving an estimated {safe_percent}% safe margin across the forecast weather hazards assessed. "
        f"The largest contributor is {top['label'].lower()} at {top['score']}%. "
        "This is a transparent agronomic estimate, not a probability of crop loss."
    )

    return {
        "status": "modelled_estimate",
        "source": "weather_risk_model",
        "model": {
            "name": config.get("name"),
            "version": config.get("version"),
            "method": config.get("method"),
            "is_probability": False,
        },
        "crop_id": crop_id,
        "crop_name": canonical_name,
        "growth_stage": stage,
        "region": region or crop.get("state"),
        "risk_percent": risk_percent,
        "safe_percent": safe_percent,
        "level": level,
        "tone": band.get("tone", "neutral"),
        "alert": bool(band.get("alert")),
        "watch": level == "MODERATE",
        "label": band.get("label", f"{level.title()} estimated risk"),
        "summary": summary_text,
        "top_factor": top["key"],
        "factors": sorted(factors, key=lambda item: item["score"], reverse=True),
        "recommendations": recommendations,
        "confidence": confidence,
        "confidence_reason": confidence_reason,
        "profile_source": profile_source,
        "profile": {
            "category": (catalog or {}).get("category"),
            "optimal_temperature_c": [opt_min, opt_max],
            "heat_threshold_c": heat_threshold,
            "cold_threshold_c": cold_threshold,
            "heavy_rain_mm": heavy_rain,
            "weekly_water_need_mm": weekly_need,
            "humidity_threshold": humidity_threshold,
            "wind_threshold_kmh": wind_threshold,
            "waterlogging_sensitivity": waterlogging_sensitivity,
            "drought_sensitivity": drought_sensitivity,
        },
        "inputs": {
            "forecast_days": len(days),
            "hourly_observations": len(hourly),
            "forecast_rainfall_total_mm": round(sum(value for _date, value in rain_values), 1) if rain_values else None,
            "forecast_max_temperature_c": max((day.get("temperature_max_c") for day in days if day.get("temperature_max_c") is not None), default=None),
            "forecast_min_temperature_c": min((day.get("temperature_min_c") for day in days if day.get("temperature_min_c") is not None), default=None),
            "current_humidity_percent": current_humidity,
            "peak_wind_kmh": round(max_wind, 1) if max_wind is not None else None,
            "provider": summary.get("provider"),
            "stale": bool(summary.get("stale")),
            "timezone": summary.get("timezone"),
        },
        "location": location,
        "limitations": [item for item in dict.fromkeys(limitations) if item],
        "generated_at": _iso_now(),
    }
