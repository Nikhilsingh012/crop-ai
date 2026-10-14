import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def current_weather(location):
    """Use a configured provider, otherwise use live Open-Meteo data without a key."""
    provider_url = os.getenv("WEATHER_API_URL")
    api_key = os.getenv("WEATHER_API_KEY")
    if provider_url and api_key:
        query = urlencode({"location": location, "key": api_key})
        request = Request(f"{provider_url}?{query}", headers={"Accept": "application/json"})
        with urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
        payload["provider"] = "configured"
        return payload

    geocode_query = urlencode({"name": location, "count": 1, "language": "en", "format": "json"})
    with urlopen(
        Request(
            f"https://geocoding-api.open-meteo.com/v1/search?{geocode_query}",
            headers={"Accept": "application/json"},
        ),
        timeout=8,
    ) as response:
        places = json.loads(response.read().decode("utf-8")).get("results", [])
    if not places:
        raise ValueError(f"Location '{location}' was not found.")

    place = places[0]
    forecast_query = urlencode(
        {
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m",
            "timezone": "auto",
        }
    )
    with urlopen(
        Request(
            f"https://api.open-meteo.com/v1/forecast?{forecast_query}",
            headers={"Accept": "application/json"},
        ),
        timeout=8,
    ) as response:
        current = json.loads(response.read().decode("utf-8")).get("current", {})

    return {
        "location": place.get("name", location),
        "country": place.get("country"),
        "latitude": place.get("latitude"),
        "longitude": place.get("longitude"),
        "provider": "open-meteo",
        "configured": True,
        "temperature": current.get("temperature_2m"),
        "humidity": current.get("relative_humidity_2m"),
        "rainfall": current.get("precipitation"),
        "wind_speed": current.get("wind_speed_10m"),
        "time": current.get("time"),
    }


def forecast_weather(latitude, longitude):
    """Return current conditions and daily rainfall totals for the next 7 days."""
    forecast_query = urlencode(
        {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m",
            "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min",
            "hourly": "precipitation_probability",
            "forecast_days": 7,
            "timezone": "auto",
        }
    )
    with urlopen(
        Request(
            f"https://api.open-meteo.com/v1/forecast?{forecast_query}",
            headers={"Accept": "application/json"},
        ),
        timeout=8,
    ) as response:
        payload = json.loads(response.read().decode("utf-8"))

    current = payload.get("current", {})
    daily = payload.get("daily", {})
    hourly = payload.get("hourly", {})
    dates = daily.get("time", [])
    rainfall = daily.get("precipitation_sum", [])
    forecast = [
        {
            "date": date,
            "rainfall": amount or 0,
            "temperature_max": (daily.get("temperature_2m_max", [])[index] if index < len(daily.get("temperature_2m_max", [])) else None),
            "temperature_min": (daily.get("temperature_2m_min", [])[index] if index < len(daily.get("temperature_2m_min", [])) else None),
        }
        for index, (date, amount) in enumerate(zip(dates, rainfall))
    ]
    return {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": payload.get("timezone"),
        "provider": "open-meteo",
        "configured": True,
        "temperature": current.get("temperature_2m"),
        "humidity": current.get("relative_humidity_2m"),
        "rainfall": current.get("precipitation"),
        "wind_speed": current.get("wind_speed_10m"),
        "weather_condition": current.get("weather_code"),
        "precipitation_probability": max(hourly.get("precipitation_probability", [0]) or [0]),
        "forecast": forecast,
    }