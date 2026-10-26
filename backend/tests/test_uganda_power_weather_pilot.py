import csv
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from uganda_power_weather_pilot import PARAMETERS, PowerApiError, run_pilot


def payload(date="20040727", values=None, *, include_date=True, sources=None):
    values = values or {"T2M": 23.4, "PRECTOTCORR": 2.1, "RH2M": 82.0}
    series = {name: ({date: values.get(name)} if include_date else {}) for name in PARAMETERS}
    return {
        "header": {"sources": sources or ["MERRA2", "POWER"], "time_standard": "LST", "fill_value": -999.0},
        "geometry": {"type": "Point", "coordinates": [31.0, 0.8, 1170]},
        "parameters": {"T2M": {"units": "C"}, "PRECTOTCORR": {"units": "mm/day"}, "RH2M": {"units": "%"}},
        "properties": {"parameter": series},
    }


def write_input(path, rows, headers=None):
    headers = headers or ["id", "date", "year", "latitude", "longitude", "data_origin", "matched"]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


class UgandaPowerPilotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.input = self.root / "pilot.csv"
        self.output = self.root / "weather_pilot"
        self.row = {"id": "field-1", "date": "2004-07-27", "year": "2004", "latitude": "0.8",
                    "longitude": "31.0", "data_origin": "dbA", "matched": "NO"}
        self.now = lambda: datetime(2026, 10, 25, tzinfo=timezone.utc)

    def tearDown(self):
        self.temp.cleanup()

    def run_with(self, rows, opener):
        write_input(self.input, rows)
        return run_pilot(self.input, self.output, opener=opener, now=self.now)

    def read_output(self):
        with (self.output / "weather_matches.csv").open(encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))

    def test_successful_exact_date_match_and_provenance(self):
        calls = []
        report = self.run_with([self.row], lambda url, timeout: (calls.append(url) or payload(), 200))
        row = self.read_output()[0]
        self.assertEqual(row["status"], "matched")
        self.assertEqual(row["observation_date_iso"], "2004-07-27")
        self.assertEqual(row["T2M"], "23.4")
        self.assertEqual(row["PRECTOTCORR_unit"], "mm/day")
        self.assertEqual(row["returned_elevation"], "1170")
        self.assertEqual(row["data_origin"], "dbA")
        self.assertEqual(len(calls), 1)
        self.assertIn("time-standard=LST", calls[0])
        self.assertEqual(report["status_counts"]["matched"], 1)
        metadata = json.loads((self.output / "request_metadata.json").read_text())
        self.assertEqual(metadata["input_column_mapping"]["date"], "date")

    def test_fill_values_are_missing_not_zero(self):
        report = self.run_with([self.row], lambda *_: (payload(values={"T2M": -999.0, "PRECTOTCORR": 0, "RH2M": 81}), 200))
        row = self.read_output()[0]
        self.assertEqual(row["status"], "missing weather")
        self.assertEqual(row["T2M"], "")
        self.assertEqual(row["PRECTOTCORR"], "0.0")
        self.assertEqual(report["rows_missing_parameter_in_successful_responses"]["T2M"], 1)

    def test_missing_exact_date_does_not_substitute_neighboring_date(self):
        report = self.run_with([self.row], lambda *_: (payload(date="20040726", include_date=True), 200))
        row = self.read_output()[0]
        self.assertEqual(row["status"], "missing weather")
        self.assertEqual(row["missing_weather_variables"], ";".join(PARAMETERS))
        self.assertEqual(report["status_counts"]["matched"], 0)

    def test_api_and_http_errors_preserve_output_row(self):
        cases = [
            lambda *_: (_ for _ in ()).throw(PowerApiError("NASA POWER HTTP 503: unavailable")),
            lambda *_: ({"error": True, "reason": "invalid parameter"}, 200),
            lambda *_: ({"header": {}, "properties": {"parameter": "malformed"}}, 200),
        ]
        for opener in cases:
            with self.subTest(opener=opener):
                self.output = self.root / f"out-{cases.index(opener)}"
                report = self.run_with([self.row], opener)
                self.assertEqual(len(self.read_output()), 1)
                self.assertEqual(self.read_output()[0]["status"], "API failure")
                self.assertTrue(self.read_output()[0]["retrieved_at_utc"])
                self.assertEqual(report["status_counts"]["API failure"], 1)
                self.assertFalse(report["quality_pass"])

    def test_invalid_coordinates_and_date_do_not_call_api(self):
        bad = dict(self.row, date="NA", latitude="91")
        report = self.run_with([bad], lambda *_: self.fail("invalid observation must not call API"))
        row = self.read_output()[0]
        self.assertEqual(row["status"], "invalid coordinates/date")
        self.assertEqual(report["status_counts"]["invalid coordinates/date"], 1)

    def test_duplicate_observations_are_preserved_and_fetched_once(self):
        calls = []
        report = self.run_with([self.row, dict(self.row)], lambda url, timeout: (calls.append(url) or payload(), 200))
        rows = self.read_output()
        self.assertEqual(len(rows), 2)
        self.assertEqual([row["status"] for row in rows], ["matched", "matched"])
        self.assertEqual(rows[1]["duplicate_observation"], "True")
        self.assertEqual(len(calls), 1)
        self.assertEqual(report["duplicate_observation_rows_dropped"], 0)

    def test_reuses_successful_raw_response_cache(self):
        first_calls = []
        self.run_with([self.row], lambda url, timeout: (first_calls.append(url) or payload(), 200))
        second_calls = []
        report = run_pilot(self.input, self.output, opener=lambda url, timeout: (second_calls.append(url) or payload(), 200), now=self.now)
        self.assertEqual(len(first_calls), 1)
        self.assertEqual(second_calls, [])
        self.assertTrue(self.read_output()[0]["cache_hit"] == "True")
        self.assertEqual(report["status_counts"]["matched"], 1)


if __name__ == "__main__":
    unittest.main()
