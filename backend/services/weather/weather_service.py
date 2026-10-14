import os
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_CACHE = {}


def _demo(latitude, longitude):
    return {"provider":"demo","latitude":latitude,"longitude":longitude,"temperature":31,"humidity":88,"rainfall":4,"wind_speed":12,"weather_condition":"rain","precipitation_probability":85,"forecast":[{"date":"tomorrow","rainfall":15,"temperature_max":32,"temperature_min":25,"precipitation_probability":75},{"date":"day-2","rainfall":85,"temperature_max":31,"temperature_min":24,"precipitation_probability":90},{"date":"day-3","rainfall":65,"temperature_max":30,"temperature_min":24,"precipitation_probability":85},{"date":"day-4","rainfall":12,"temperature_max":31,"temperature_min":24,"precipitation_probability":45},{"date":"day-5","rainfall":4,"temperature_max":32,"temperature_min":25,"precipitation_probability":25},{"date":"day-6","rainfall":0,"temperature_max":33,"temperature_min":25,"precipitation_probability":10},{"date":"day-7","rainfall":0,"temperature_max":33,"temperature_min":25,"precipitation_probability":10}]}


def _fetch(latitude, longitude):
    query = urlencode({"latitude":latitude,"longitude":longitude,"current":"temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m","daily":"precipitation_sum,temperature_2m_max,temperature_2m_min,precipitation_probability_max","forecast_days":7,"timezone":"auto"})
    with urlopen(Request(f"https://api.open-meteo.com/v1/forecast?{query}", headers={"Accept":"application/json"}), timeout=8) as response:
        payload = __import__("json").loads(response.read().decode("utf-8"))
    current, daily = payload.get("current", {}), payload.get("daily", {})
    forecast = []
    for index, date in enumerate(daily.get("time", [])):
        forecast.append({"date":date,"rainfall":(daily.get("precipitation_sum", [0])[index] or 0),"temperature_max":daily.get("temperature_2m_max", [None])[index],"temperature_min":daily.get("temperature_2m_min", [None])[index],"precipitation_probability":daily.get("precipitation_probability_max", [0])[index]})
    return {"provider":"open-meteo","latitude":latitude,"longitude":longitude,"timezone":payload.get("timezone"),"temperature":current.get("temperature_2m"),"humidity":current.get("relative_humidity_2m"),"rainfall":current.get("precipitation"),"wind_speed":current.get("wind_speed_10m"),"weather_condition":current.get("weather_code"),"precipitation_probability":max((item.get("precipitation_probability", 0) or 0) for item in forecast) if forecast else 0,"forecast":forecast}


def get_weather(latitude, longitude, force=False):
    key = (round(float(latitude), 3), round(float(longitude), 3))
    ttl = int(os.getenv("WEATHER_FORECAST_CACHE_TTL_SECONDS", "3600"))
    cached = _CACHE.get(key)
    if cached and not force and time.time() - cached["at"] < ttl:
        return {**cached["data"], "cache": "hit"}
    if os.getenv("DEMO_WEATHER_MODE", "false").lower() == "true":
        data = _demo(*key)
    else:
        data = _fetch(*key)
    _CACHE[key] = {"at": time.time(), "data": data}
    return {**data, "cache": "miss"}
