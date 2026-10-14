import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen


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
    query = urlencode({"latitude": latitude, "longitude": longitude, "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m", "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min", "hourly": "precipitation_probability", "forecast_days": 7, "timezone": "auto"})
    with urlopen(Request(f"https://api.open-meteo.com/v1/forecast?{query}", headers={"Accept": "application/json"}), timeout=8) as response:
        payload = json.loads(response.read().decode("utf-8"))
    current, daily, hourly = payload.get("current", {}), payload.get("daily", {}), payload.get("hourly", {})
    forecast = [{"date": date, "rainfall": daily.get("precipitation_sum", [0])[index] or 0, "temperature_max": daily.get("temperature_2m_max", [None])[index], "temperature_min": daily.get("temperature_2m_min", [None])[index]} for index, date in enumerate(daily.get("time", []))]
    return {"latitude": latitude, "longitude": longitude, "timezone": payload.get("timezone"), "provider": "open-meteo", "configured": True, "temperature": current.get("temperature_2m"), "humidity": current.get("relative_humidity_2m"), "rainfall": current.get("precipitation"), "wind_speed": current.get("wind_speed_10m"), "weather_condition": current.get("weather_code"), "precipitation_probability": max(hourly.get("precipitation_probability", [0]) or [0]), "forecast": forecast}
