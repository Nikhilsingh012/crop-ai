import json
import math
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def _api_number(value, minimum=None, maximum=None):
    """Return only finite numeric provider values; preserve missing/invalid data as None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        parsed = float(value)
    except (OverflowError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    if minimum is not None and parsed < minimum or maximum is not None and parsed > maximum:
        return None
    return parsed


def current_weather(location):
    geocode_query = urlencode({"name": location, "count": 1, "language": "en", "format": "json"})
    with urlopen(Request(f"https://geocoding-api.open-meteo.com/v1/search?{geocode_query}", headers={"Accept": "application/json"}), timeout=8) as response:
        places = json.loads(response.read().decode("utf-8")).get("results", [])
    if not places:
        raise ValueError(f"Location '{location}' was not found.")
    place = places[0]
    result = forecast_weather(place["latitude"], place["longitude"])
    result.update({"location": place.get("name", location), "country": place.get("country")})
    return result


def forecast_weather(latitude, longitude):
    query = urlencode({
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m",
        "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min",
        "hourly": "precipitation,temperature_2m,relative_humidity_2m,wind_speed_10m,wind_gusts_10m,precipitation_probability",
        "forecast_days": 7,
        "forecast_hours": 49,
        "past_hours": 0,
        "timezone": "auto",
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
    })
    with urlopen(Request(f"https://api.open-meteo.com/v1/forecast?{query}", headers={"Accept": "application/json"}), timeout=8) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Weather provider returned a non-object response.")
    current = payload.get("current") if isinstance(payload.get("current"), dict) else {}
    daily = payload.get("daily") if isinstance(payload.get("daily"), dict) else {}
    hourly = payload.get("hourly") if isinstance(payload.get("hourly"), dict) else {}
    forecast = []
    dates = daily.get("time") if isinstance(daily.get("time"), list) else []
    for index, day in enumerate(dates):
        if not isinstance(day, str):
            continue
        rainfall = daily.get("precipitation_sum")
        maximums = daily.get("temperature_2m_max")
        minimums = daily.get("temperature_2m_min")
        forecast.append({
            "date": day,
            "rainfall": _api_number(rainfall[index], 0) if isinstance(rainfall, list) and index < len(rainfall) else None,
            "temperature_max": _api_number(maximums[index], -100, 70) if isinstance(maximums, list) and index < len(maximums) else None,
            "temperature_min": _api_number(minimums[index], -100, 70) if isinstance(minimums, list) and index < len(minimums) else None,
        })
    hourly_keys = {
        "rainfall": "precipitation",
        "temperature": "temperature_2m",
        "humidity": "relative_humidity_2m",
        "wind_speed": "wind_speed_10m",
        "wind_gust": "wind_gusts_10m",
        "precipitation_probability": "precipitation_probability",
    }
    hourly_forecast = []
    hourly_times = hourly.get("time") if isinstance(hourly.get("time"), list) else []
    for index, hour in enumerate(hourly_times):
        item = {"time": hour}
        for target, source in hourly_keys.items():
            values = hourly.get(source, [])
            limits = {
                "rainfall": (0, None), "temperature": (-100, 70), "humidity": (0, 100),
                "wind_speed": (0, 500), "wind_gust": (0, 600), "precipitation_probability": (0, 100),
            }[target]
            item[target] = _api_number(values[index], *limits) if isinstance(values, list) and index < len(values) else None
        hourly_forecast.append(item)
    raw_probability = hourly.get("precipitation_probability")
    probability = [_api_number(value, 0, 100) for value in raw_probability] if isinstance(raw_probability, list) else []
    probability = [value for value in probability if value is not None]
    return {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": payload.get("timezone"),
        "provider": "open-meteo",
        "provider_status": "live",
        "configured": True,
        "forecast_issued_at": current.get("time"),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "stale": False,
        "forecast_resolution": "hourly",
        "temperature": _api_number(current.get("temperature_2m"), -100, 70),
        "humidity": _api_number(current.get("relative_humidity_2m"), 0, 100),
        "rainfall": _api_number(current.get("precipitation"), 0),
        "wind_speed": _api_number(current.get("wind_speed_10m"), 0, 500),
        "weather_condition": current.get("weather_code"),
        "precipitation_probability": max(probability) if probability else None,
        "forecast": forecast,
        "hourly_forecast": hourly_forecast,
    }
