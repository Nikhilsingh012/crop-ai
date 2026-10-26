import os
import urllib.error
import time
from datetime import datetime, timezone

from services.weather import forecast_weather

_CACHE = {}


class WeatherProviderError(RuntimeError):
    """Safe provider failure that does not expose request URLs or credentials."""

    def __init__(self, status, message):
        super().__init__(message)
        self.provider_status = status
        self.provider_error = message


def _provider_failure(error):
    if isinstance(error, urllib.error.HTTPError):
        return f"Weather provider returned HTTP {error.code}."
    if isinstance(error, TimeoutError) or (isinstance(error, urllib.error.URLError) and isinstance(error.reason, TimeoutError)):
        return "Weather provider request timed out."
    return f"Weather provider request failed ({type(error).__name__})."


def _demo(latitude, longitude):
    return {"provider":"demo","latitude":latitude,"longitude":longitude,"temperature":31,"humidity":88,"rainfall":4,"wind_speed":12,"weather_condition":"rain","precipitation_probability":85,"forecast":[{"date":"tomorrow","rainfall":15,"temperature_max":32,"temperature_min":25,"precipitation_probability":75},{"date":"day-2","rainfall":85,"temperature_max":31,"temperature_min":24,"precipitation_probability":90},{"date":"day-3","rainfall":65,"temperature_max":30,"temperature_min":24,"precipitation_probability":85},{"date":"day-4","rainfall":12,"temperature_max":31,"temperature_min":24,"precipitation_probability":45},{"date":"day-5","rainfall":4,"temperature_max":32,"temperature_min":25,"precipitation_probability":25},{"date":"day-6","rainfall":0,"temperature_max":33,"temperature_min":25,"precipitation_probability":10},{"date":"day-7","rainfall":0,"temperature_max":33,"temperature_min":25,"precipitation_probability":10}]}


def _fetch(latitude, longitude):
    return forecast_weather(latitude, longitude)


def get_weather(latitude, longitude, force=False):
    key = (round(float(latitude), 3), round(float(longitude), 3))
    ttl = int(os.getenv("WEATHER_FORECAST_CACHE_TTL_SECONDS", "3600"))
    cached = _CACHE.get(key)
    if cached and not force and time.time() - cached["at"] < ttl:
        return {**cached["data"], "cache": "hit", "cache_age_seconds": max(0, int(time.time() - cached["at"])), "provider_status": "cached", "freshness_status": "fresh", "stale": False}
    if os.getenv("DEMO_WEATHER_MODE", "false").lower() == "true":
        data = _demo(*key)
        provider_status = "demo"
    else:
        try:
            data = _fetch(*key)
            provider_status = "live"
        except Exception as error:
            message = _provider_failure(error)
            if cached:
                age = max(0, int(time.time() - cached["at"]))
                status = error.code if isinstance(error, urllib.error.HTTPError) else None
                return {**cached["data"], "cache": "stale_fallback", "cache_age_seconds": age, "provider_status": "stale_fallback", "freshness_status": "stale", "provider_http_status": status, "provider_error": message, "stale": True}
            status = error.code if isinstance(error, urllib.error.HTTPError) else None
            raise WeatherProviderError(status, message) from error
    data = {**data, "retrieved_at": datetime.now(timezone.utc).isoformat(), "provider_status": provider_status, "freshness_status": "fresh", "stale": False}
    _CACHE[key] = {"at": time.time(), "data": data}
    return {**data, "cache": "miss", "cache_age_seconds": 0, "stale": False}
