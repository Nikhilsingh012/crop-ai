import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.historical_weather import DownloadError, derive_daily, run


def sample_payload(days=8):
    times, temperatures, rain = [], [], []
    for day in range(days):
        for hour in range(24):
            times.append(f"2022-01-{day + 1:02d}T{hour:02d}:00")
            temperatures.append(31 if day < 3 else 20)
            rain.append(1 if day == 0 else 0)
    return {
        "latitude": 28.5, "longitude": 77.5, "timezone": "Asia/Kolkata", "utc_offset_seconds": 19800,
        "elevation": 200, "generationtime_ms": 1,
        "hourly_units": {"temperature_2m": "°C", "precipitation": "mm"},
        "hourly": {"time": times, "temperature_2m": temperatures, "precipitation": rain,
                   "soil_temperature_0cm": [None] * len(times)},
    }


class HistoricalWeatherTests(unittest.TestCase):
    def test_mocked_download_outputs_raw_metadata_csv_and_quality_report(self):
        payload = sample_payload()
        calls = []

        def mock_fetch(url, timeout):
            calls.append((url, timeout))
            return payload, 200

        with tempfile.TemporaryDirectory() as temp:
            args = SimpleNamespace(latitude=28.4744, longitude=77.504, start_date="2022-01-01", end_date="2022-01-08",
                endpoint="https://example.test/history", variables="temperature_2m,precipitation,soil_temperature_0cm",
                timezone="Asia/Kolkata", output_root=temp, output_dir=None, timeout=2,
                hot_day_threshold_c=30, dry_day_threshold_mm=0)
            report = run(args, opener=mock_fetch)
            paths = report["output_files"]
            self.assertEqual(len(calls), 1)
            self.assertEqual(report["rows_downloaded"], 192)
            self.assertEqual(report["missingness_by_variable"]["soil_temperature_0cm"]["missing"], 192)
            self.assertTrue(all(Path(p).exists() for p in paths.values()))
            raw = json.loads(Path(paths["raw_json"]).read_text(encoding="utf-8"))
            metadata = json.loads(Path(paths["metadata_json"]).read_text(encoding="utf-8"))
            self.assertEqual(raw["hourly"]["time"][0], "2022-01-01T00:00")
            self.assertEqual(metadata["dataset_type"], "historical_forecast")
            with Path(paths["hourly_csv"]).open(encoding="utf-8-sig") as f:
                hourly = list(csv.DictReader(f))
            self.assertEqual(hourly[0]["temperature_2m_unit"], "°C")
            self.assertEqual(hourly[0]["dataset_type"], "historical_forecast")
            with Path(paths["daily_features_csv"]).open(encoding="utf-8-sig") as f:
                daily = list(csv.DictReader(f))
            self.assertEqual(daily[0]["daily_max_temperature_2m"], "31.0")
            self.assertEqual(daily[0]["consecutive_hot_days"], "1")
            self.assertEqual(daily[2]["consecutive_hot_days"], "3")
            self.assertEqual(daily[1]["dry_spell_days"], "1")
            self.assertEqual(daily[2]["rolling_3_day_rainfall_mm"], "24.0")
            self.assertEqual(daily[6]["rolling_7_day_rainfall_mm"], "24.0")

    def test_missing_hours_and_duplicate_timestamps_reported(self):
        payload = sample_payload(1)
        payload["hourly"]["time"].pop(5)
        payload["hourly"]["temperature_2m"].pop(5)
        payload["hourly"]["precipitation"].pop(5)
        payload["hourly"]["time"].append(payload["hourly"]["time"][0])
        payload["hourly"]["temperature_2m"].append(20)
        payload["hourly"]["precipitation"].append(0)
        with tempfile.TemporaryDirectory() as temp:
            args = SimpleNamespace(latitude=1, longitude=2, start_date="2022-01-01", end_date="2022-01-01",
                endpoint="https://example.test", variables="temperature_2m,precipitation", timezone="UTC",
                output_root=temp, output_dir=None, timeout=1, hot_day_threshold_c=None, dry_day_threshold_mm=None)
            report = run(args, opener=lambda *_: (payload, 200))
        self.assertEqual(report["duplicate_timestamp_count"], 1)
        self.assertEqual(report["missing_hour_count"], 1)

    def test_api_errors_propagate_without_writing_output(self):
        with tempfile.TemporaryDirectory() as temp:
            args = SimpleNamespace(latitude=1, longitude=2, start_date="2022-01-01", end_date="2022-01-01",
                endpoint="https://example.test", variables="temperature_2m", timezone="UTC",
                output_root=temp, output_dir=None, timeout=1, hot_day_threshold_c=None, dry_day_threshold_mm=None)
            with self.assertRaises(DownloadError):
                run(args, opener=lambda *_: (_ for _ in ()).throw(DownloadError("HTTP 503")))
            self.assertEqual(list(Path(temp).iterdir()), [])

    def test_refuses_to_overwrite_existing_output_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            existing = Path(temp) / "already-here"
            existing.mkdir()
            args = SimpleNamespace(latitude=1, longitude=2, start_date="2022-01-01", end_date="2022-01-01",
                endpoint="https://example.test", variables="temperature_2m", timezone="UTC",
                output_root=temp, output_dir=str(existing), timeout=1, hot_day_threshold_c=None, dry_day_threshold_mm=None)
            with self.assertRaises(FileExistsError):
                run(args, opener=lambda *_: (sample_payload(1), 200))

    def test_incomplete_daily_rainfall_is_not_filled_as_zero(self):
        rows = [{"timestamp": f"2022-01-01T{h:02}:00", "temperature_2m": 10, "precipitation": 0} for h in range(23)]
        daily = derive_daily(rows, 20, 0)
        self.assertIsNone(daily[0]["rainfall_mm"])
        self.assertIsNone(daily[0]["dry_spell_days"])


if __name__ == "__main__":
    unittest.main()
