import unittest
import json
import urllib.error
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from services.weather import weather_service


class WeatherProviderTests(unittest.TestCase):
    def test_live_forecast_is_cached_with_retrieval_time(self):
        payload = {"provider": "open-meteo", "forecast_issued_at": "2026-10-15T10:00", "forecast": []}
        with patch.object(weather_service, "_CACHE", {}), patch.object(weather_service, "_fetch", return_value=payload), patch.dict("os.environ", {"DEMO_WEATHER_MODE": "false"}):
            result = weather_service.get_weather(19, 73, force=True)
        self.assertEqual(result["provider"], "open-meteo")
        self.assertFalse(result["stale"])
        self.assertTrue(result["retrieved_at"])
        self.assertEqual(result["provider_status"], "live")
        self.assertEqual(result["cache_age_seconds"], 0)

    def test_provider_failure_returns_cached_data_as_explicitly_stale(self):
        payload = {"provider": "open-meteo", "forecast": []}
        cache = {(19.0, 73.0): {"at": 0, "data": payload}}
        with patch.object(weather_service, "_CACHE", cache), patch.object(weather_service, "_fetch", side_effect=TimeoutError), patch.dict("os.environ", {"DEMO_WEATHER_MODE": "false"}):
            result = weather_service.get_weather(19, 73, force=True)
        self.assertTrue(result["stale"])
        self.assertEqual(result["cache"], "stale_fallback")
        self.assertGreater(result["cache_age_seconds"], 0)
        self.assertEqual(result["provider_status"], "stale_fallback")
        self.assertEqual(result["provider_error"], "Weather provider request timed out.")

    def test_http_provider_failure_is_reported_without_echoing_url_or_query(self):
        error = urllib.error.HTTPError("https://provider.invalid/?token=secret", 502, "Bad Gateway", {}, None)
        with patch.object(weather_service, "_CACHE", {}), patch.object(weather_service, "_fetch", side_effect=error), patch.dict("os.environ", {"DEMO_WEATHER_MODE": "false"}):
            with self.assertRaises(weather_service.WeatherProviderError) as caught:
                weather_service.get_weather(19, 73, force=True)
        self.assertEqual(caught.exception.provider_status, 502)
        self.assertEqual(caught.exception.provider_error, "Weather provider returned HTTP 502.")
        self.assertNotIn("secret", str(caught.exception))
        self.assertNotIn("provider.invalid", str(caught.exception))

    def test_fresh_cache_hit_has_age_and_cached_status(self):
        cache = {(19.0, 73.0): {"at": 100, "data": {"provider": "open-meteo", "retrieved_at": "earlier"}}}
        with patch.object(weather_service, "_CACHE", cache), patch.object(weather_service.time, "time", return_value=103), patch.dict("os.environ", {"WEATHER_FORECAST_CACHE_TTL_SECONDS": "3600"}):
            result = weather_service.get_weather(19, 73)
        self.assertEqual(result["cache_age_seconds"], 3)
        self.assertEqual(result["provider_status"], "cached")
        self.assertFalse(result["stale"])

    def test_forecast_requests_next_49_steps_so_current_hour_can_be_excluded(self):
        from services.weather import forecast_weather
        start = datetime(2026, 10, 15, 10)
        times = [(start + timedelta(hours=index)).isoformat(timespec="minutes") for index in range(49)]
        response_payload = {
            "latitude": 19, "longitude": 73, "timezone": "Asia/Kolkata",
            "current": {"time": times[0], "temperature_2m": 30},
            "daily": {"time": ["2026-10-15", "2026-10-16"], "precipitation_sum": [4, 5], "temperature_2m_max": [32, 33], "temperature_2m_min": [22, 23]},
            "hourly": {"time": times, "precipitation": [1] * 49, "temperature_2m": [30] * 49, "relative_humidity_2m": [60] * 49, "wind_speed_10m": [5] * 49, "wind_gusts_10m": [8] * 49, "precipitation_probability": [10] * 49},
        }
        response = type("Response", (), {"read": lambda self: json.dumps(response_payload).encode("utf-8"), "__enter__": lambda self: self, "__exit__": lambda self, *args: None})()
        with patch("services.weather.urlopen", return_value=response) as fetch:
            result = forecast_weather(19, 73)
        query = parse_qs(urlparse(fetch.call_args.args[0].full_url).query)
        self.assertEqual(query["forecast_hours"], ["49"])
        self.assertEqual(query["past_hours"], ["0"])
        self.assertEqual(query["temperature_unit"], ["celsius"])
        self.assertEqual(query["wind_speed_unit"], ["kmh"])
        self.assertEqual(query["precipitation_unit"], ["mm"])
        self.assertEqual(len(result["hourly_forecast"]), 49)
        self.assertEqual(result["hourly_forecast"][0]["time"], times[0])

    def test_daily_temperature_dates_survive_short_or_missing_rainfall_arrays(self):
        from services.weather import forecast_weather
        dates = [(datetime(2026, 10, 29) + timedelta(days=index)).date().isoformat() for index in range(5)]
        payload = {
            "latitude": 19, "longitude": 73, "timezone": "Asia/Kolkata",
            "current": {"time": "2026-10-15T10:00"},
            "daily": {"time": dates, "precipitation_sum": [None, 5],
                      "temperature_2m_max": [30, 31, 32, 33, 34],
                      "temperature_2m_min": [20, 21, 22, 23, 24]},
            "hourly": {"time": []},
        }
        response = type("Response", (), {"read": lambda self: json.dumps(payload).encode("utf-8"), "__enter__": lambda self: self, "__exit__": lambda self, *args: None})()
        with patch("services.weather.urlopen", return_value=response):
            result = forecast_weather(19, 73)
        self.assertEqual([day["date"] for day in result["forecast"]], dates)
        self.assertEqual([day["temperature_max"] for day in result["forecast"]], [30, 31, 32, 33, 34])
        self.assertEqual([day["rainfall"] for day in result["forecast"]], [None, 5, None, None, None])
        self.assertIsNone(result["precipitation_probability"])

    def test_invalid_provider_measurements_are_missing_not_zero(self):
        from services.weather import forecast_weather
        payload = {
            "current": {"time": "2026-10-15T10:00", "temperature_2m": True, "relative_humidity_2m": "60", "precipitation": float("nan")},
            "daily": {"time": ["2026-10-15"], "precipitation_sum": [None], "temperature_2m_max": [False], "temperature_2m_min": [22]},
            "hourly": {"time": ["2026-10-15T11:00"], "precipitation": [None], "temperature_2m": ["31"], "relative_humidity_2m": [101], "wind_speed_10m": [4], "wind_gusts_10m": [None], "precipitation_probability": [None]},
        }
        response = type("Response", (), {"read": lambda self: json.dumps(payload).encode("utf-8"), "__enter__": lambda self: self, "__exit__": lambda self, *args: None})()
        with patch("services.weather.urlopen", return_value=response):
            result = forecast_weather(19, 73)
        self.assertIsNone(result["temperature"])
        self.assertIsNone(result["humidity"])
        self.assertIsNone(result["rainfall"])
        self.assertIsNone(result["forecast"][0]["rainfall"])
        self.assertIsNone(result["forecast"][0]["temperature_max"])
        self.assertEqual(result["forecast"][0]["temperature_min"], 22)
        self.assertIsNone(result["hourly_forecast"][0]["temperature"])
        self.assertIsNone(result["hourly_forecast"][0]["humidity"])
        self.assertEqual(result["hourly_forecast"][0]["wind_speed"], 4)
        self.assertIsNone(result["precipitation_probability"])


if __name__ == "__main__":
    unittest.main()
