import math
from datetime import datetime, timezone


def _number(value, name, low, high):
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number.")
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number.")
    if not math.isfinite(parsed) or not low <= parsed <= high:
        raise ValueError(f"{name} must be between {low} and {high}.")
    return parsed


def recommend_irrigation(crop, growth_stage, soil_type=None, rainfall=None, temperature=None,
                         forecast_rainfall=None, soil_moisture_status=None):
    """Use only supplied observations; never infer a crop water threshold or dose."""
    for value, name, limit in ((crop, "crop", 120), (growth_stage, "growth_stage", 100), (soil_type, "soil_type", 100)):
        if value is not None and (not isinstance(value, str) or len(value.strip()) > limit):
            raise ValueError(f"{name} must be text within {limit} characters.")
    observed_rainfall = _number(rainfall, "rainfall", 0, 5000)
    temperature = _number(temperature, "temperature", -50, 70)
    forecast = _number(forecast_rainfall, "forecast_rainfall", 0, 1000)
    if soil_moisture_status not in (None, "", "unknown", "dry", "adequate", "wet"):
        raise ValueError("soil_moisture_status must be dry, adequate, wet, or unknown.")
    moisture = soil_moisture_status if soil_moisture_status not in (None, "", "unknown") else None
    inputs = {"crop": crop, "growth_stage": growth_stage, "soil_type": soil_type,
              "soil_moisture_status": moisture, "recent_rainfall_mm": observed_rainfall,
              "temperature_c": temperature, "forecast_rainfall_mm": forecast}
    result = {
        "status": "insufficient_data", "needed": None, "priority": None,
        "timing": "Check root-zone soil moisture and local extension guidance before irrigating.",
        "reason": "The available inputs do not establish crop-specific water demand or field moisture.",
        "evidence_quality": "insufficient",
        "limitations": ["No verified crop-specific water decision rule is configured; no irrigation quantity is calculated."],
        "inputs_received": inputs,
        "source_references": [], "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    if moisture is None:
        return result

    result["status"] = "conditional"
    result["evidence_quality"] = "user_input"
    result["source_references"] = [{"type": "farmer_observation", "label": "Farmer-reported root-zone moisture", "observed_value": moisture}]
    result["limitations"] = [
        "This is a conditional prompt based on your field observation, not a crop-specific irrigation prescription.",
        "No exact water amount or crop threshold is calculated. Confirm with local IMD/ICAR or State Agriculture University guidance.",
    ]
    if moisture == "dry":
        if forecast is not None and forecast > 0:
            result["timing"] = "You reported dry root-zone soil and entered forecast rain. Verify the forecast source and recheck the field after the rain before deciding."
            result["reason"] = "The suggestion follows your moisture observation and user-supplied forecast only; forecast rainfall may not reach the root zone."
        else:
            result["timing"] = "You reported dry root-zone soil. Check the crop-stage guidance from your local agriculture office before irrigating."
            result["reason"] = "A dry-soil observation can justify checking whether irrigation is due, but crop, soil, and local method determine the decision."
    elif moisture == "wet":
        result["timing"] = "You reported wet root-zone soil. Recheck drainage and reassess moisture before adding irrigation."
        result["reason"] = "This prompt reflects your field observation; it does not measure soil moisture remotely."
    else:
        result["timing"] = "You reported adequate root-zone moisture. Recheck the field and local crop-stage guidance before the next irrigation."
        result["reason"] = "No immediate water need is inferred from weather numbers alone."
    return result
