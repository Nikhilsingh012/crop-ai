import json
import os
import sys
import unittest
from urllib.error import URLError
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.market_data import MarketDataError, fetch_records, normalize_record
from services.market_forecast import forecast_from_history
from services.market_forecast import walk_forward_predictions
from services.market_analytics import trend_summary


def record(**updates):
    value = {"state":"Maharashtra", "district":"Pune", "market":"Pune", "commodity":"Onion", "variety":"Red", "grade":"FAQ", "arrival_date":"01/10/2026", "min_price":"1000", "modal_price":"1200", "max_price":"1400"}
    value.update(updates)
    return value


class Response:
    def __init__(self, payload): self.payload = payload
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self): return json.dumps(self.payload).encode()


class MarketDataTests(unittest.TestCase):
    def test_default_client_uses_configured_resource_and_filters(self):
        calls = []

        def opener(req, timeout):
            calls.append((req.full_url, timeout))
            return Response({"total": 1, "records": [record()]})

        with patch.dict(os.environ, {"DATA_GOV_IN_BASE_URL": "https://api.example.test/resource", "DATA_GOV_IN_MANDI_RESOURCE_ID": "resource-test"}), patch("services.market_data.urlopen", opener):
            result = fetch_records("server-key-test", filters={"state": "Maharashtra"}, max_records=1)
        self.assertEqual(len(result), 1)
        self.assertIn("https://api.example.test/resource/resource-test", calls[0][0])
        self.assertIn("filters%5Bstate%5D=Maharashtra", calls[0][0])
        self.assertNotIn("server-key-test", str([item for item in result]))

    def test_client_rejects_malformed_payload(self):
        with patch("services.market_data.urlopen", lambda req, timeout: Response({"total": 1})), patch("services.market_data.time.sleep"):
            with self.assertRaises(MarketDataError):
                fetch_records("server-key-test", max_records=1)

    def test_normalizes_source_fields_and_date(self):
        item = normalize_record(record())
        self.assertEqual(item["mandi"], "Pune")
        self.assertEqual(item["observed_on"], date(2026, 10, 1))
        self.assertEqual(item["price_unit"], "INR/quintal")

    def test_missing_fields_invalid_prices_and_inconsistent_units_rejected(self):
        for bad in (record(state=""), record(modal_price="0"), record(min_price="bad"), record(min_price="1300"), record(unit="kg")):
            with self.subTest(bad=bad), self.assertRaises(MarketDataError): normalize_record(bad)

    def test_api_paginates_and_uses_documented_page_fields(self):
        calls = []
        def opener(req, timeout):
            calls.append(req.full_url)
            offset = 0 if "offset=0" in req.full_url else 1
            return Response({"total":2,"records":[record(arrival_date="01/10/2026" if offset == 0 else "02/10/2026")]})
        with patch("services.market_data.PAGE_SIZE", 1):
            result = fetch_records("server-key-test", max_records=2, opener=opener)
        self.assertEqual(len(result), 2)
        self.assertIn("offset=1", calls[1])
        self.assertNotIn("server-key-test", str(result))

    def test_stale_data_is_labelled_by_observation_date(self):
        item = normalize_record(record(arrival_date="01/01/2020"))
        self.assertEqual(item["freshness"], "stale")

    def test_provider_failure_is_not_fabricated(self):
        with patch.dict(os.environ, {"DATA_GOV_IN_API_KEY": "fallback-test-key"}):
            for missing_key in ("", "   "):
                with self.subTest(api_key=repr(missing_key)), self.assertRaisesRegex(MarketDataError, "Configure DATA_GOV_IN_API_KEY") as raised:
                    fetch_records(api_key=missing_key)
                self.assertNotIn("fallback-test-key", str(raised.exception))
        with patch.dict(os.environ, {"DATA_GOV_IN_API_KEY": ""}):
            with self.assertRaisesRegex(MarketDataError, "Configure DATA_GOV_IN_API_KEY"):
                fetch_records(api_key=None)
        with patch("services.market_data.time.sleep"):
            with self.assertRaises(MarketDataError):
                fetch_records(api_key="configured", opener=lambda *args, **kwargs: (_ for _ in ()).throw(URLError("offline")))

    def test_omitted_key_uses_configured_environment_key_and_accepts_empty_provider_result(self):
        with patch.dict(os.environ, {"DATA_GOV_IN_API_KEY": "configured-test-key"}), \
                patch("services.market_data._provider_config", return_value=("https://api.example.test/resource", "test-resource")), \
                patch("services.market_data._request_page", return_value={"total": 0, "records": []}) as request_page:
            result = fetch_records(api_key=None, max_records=1)
        self.assertEqual(result, [])
        self.assertEqual(request_page.call_args.args[0], "configured-test-key")

    def test_forecast_requires_history_and_uses_chronological_holdout(self):
        short = [{"observed_on":date(2026,1,1)+timedelta(days=i),"modal_price":100+i} for i in range(30)]
        self.assertEqual(forecast_from_history(short)["status"], "insufficient_history")
        long = [{"observed_on":date(2026,1,1)+timedelta(days=i),"modal_price":100+i} for i in range(70)]
        result = forecast_from_history(long)
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["backtest"]["observations"], 21)
        self.assertEqual(result["points"][0]["point"], 163.0)

    def test_forecast_rejects_sparse_or_missing_price_calendar(self):
        dense = [{"observed_on":date(2026,1,1)+timedelta(days=i),"modal_price":100+i} for i in range(70)]
        sparse = dense.copy()
        sparse[35] = {**sparse[35], "observed_on": sparse[35]["observed_on"] + timedelta(days=1)}
        self.assertEqual(forecast_from_history(sparse)["status"], "insufficient_history")
        missing = dense.copy()
        missing[40] = {**missing[40], "modal_price": None}
        self.assertEqual(forecast_from_history(missing)["status"], "insufficient_history")

    def test_forecast_walk_forward_predictions_do_not_read_the_target_value(self):
        values = list(range(100, 180))
        first = list(walk_forward_predictions(values))[0]
        changed = values.copy()
        changed[first[0]] = 99999
        second = list(walk_forward_predictions(changed))[0]
        self.assertEqual(first[1], second[1])
        self.assertNotEqual(first[2], second[2])

    def test_trends_use_calendar_windows_not_number_of_rows(self):
        points = [{"date": "2026-01-01", "modal_price": 100}, {"date": "2026-01-19", "modal_price": 100}, {"date": "2026-01-25", "modal_price": 120}, {"date": "2026-01-26", "modal_price": 120}]
        result = trend_summary(points)
        self.assertEqual(result["daily_change"], 0.0)
        self.assertEqual(result["7_day"], 20.0)
        self.assertIsNone(result["30_day"])

    def test_daily_change_requires_adjacent_observation_dates(self):
        points = [{"date": "2026-01-01", "modal_price": 100}, {"date": "2026-01-03", "modal_price": 120}]
        self.assertIsNone(trend_summary(points)["daily_change"])

    def test_market_api_emits_iso_dates_and_seasonal_comparison(self):
        from flask import Flask
        from routes.markets import markets_bp
        from unittest.mock import patch

        class FakeConnection:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def execute(self, sql, values=()):
                class Result:
                    def fetchall(self):
                        return [
                            {"id": 1, "observed_on": date(2025, 10, 1), "modal_price": 100,
                             "variety": "Red", "grade": "FAQ", "price_unit": "INR/quintal"},
                            {"id": 2, "observed_on": date(2026, 10, 1), "modal_price": 120,
                             "variety": "Red", "grade": "FAQ", "price_unit": "INR/quintal"},
                        ]
                return Result()

        app = Flask(__name__)
        app.register_blueprint(markets_bp, url_prefix="/api")
        with patch("routes.markets.connection", FakeConnection):
            response = app.test_client().get("/api/markets/trends?commodity=Onion&mandi=Pune")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["seasonal_comparison"]["comparison_date"], "2025-10-01")
        self.assertEqual(data["seasonal_comparison"]["change_percent"], 20.0)

    def test_market_api_rejects_reversed_date_range(self):
        from flask import Flask
        from routes.markets import markets_bp
        app = Flask(__name__)
        app.register_blueprint(markets_bp, url_prefix="/api")
        response = app.test_client().get("/api/markets/prices?date_from=2026-10-02&date_to=2026-10-01")
        self.assertEqual(response.status_code, 400)

    def test_market_status_serializes_dates_and_never_returns_credentials(self):
        from flask import Flask
        from routes.markets import markets_bp

        class Result:
            def __init__(self, value): self.value = value
            def fetchone(self): return self.value

        class FakeConnection:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def execute(self, sql, values=()):
                if "COUNT(*) AS records" in sql:
                    return Result({"records": 1, "newest_observation": date(2026,10,1), "last_fetched": datetime(2026,10,2,tzinfo=timezone.utc)})
                return Result({"status":"succeeded", "completed_at":datetime(2026,10,2,tzinfo=timezone.utc), "latest_observed_on":date(2026,10,1)})

        app = Flask(__name__)
        app.register_blueprint(markets_bp, url_prefix="/api")
        with patch("routes.markets.connection", FakeConnection), patch.dict("os.environ", {"DATA_GOV_IN_API_KEY":"secret-test-key"}):
            response = app.test_client().get("/api/markets/status")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["newest_observation"], "2026-10-01")
        self.assertEqual(response.json["last_ingestion"]["completed_at"], "2026-10-02T00:00:00+00:00")
        self.assertNotIn("secret-test-key", response.get_data(as_text=True))

    def test_duplicate_ingestion_upserts_same_stable_record_key(self):
        from db import connection
        key = normalize_record(record())["source_record_key"]
        with connection() as conn:
            if not conn.execute("SELECT to_regclass('public.market_prices') AS table_name").fetchone()["table_name"]:
                self.skipTest("PostgreSQL market schema is not initialized")
            conn.execute("""INSERT INTO market_prices(provider,source_record_key,commodity,state,district,mandi,observed_on,source_url,modal_price)
                VALUES ('test-provider',%s,'Test crop','Test state','Test district','Test mandi','2026-01-01','https://example.invalid',10)
                ON CONFLICT(provider,source_record_key) DO UPDATE SET modal_price=EXCLUDED.modal_price""", (key,))
            conn.execute("""INSERT INTO market_prices(provider,source_record_key,commodity,state,district,mandi,observed_on,source_url,modal_price)
                VALUES ('test-provider',%s,'Test crop','Test state','Test district','Test mandi','2026-01-01','https://example.invalid',11)
                ON CONFLICT(provider,source_record_key) DO UPDATE SET modal_price=EXCLUDED.modal_price""", (key,))
            row = conn.execute("SELECT COUNT(*) AS count, MAX(modal_price) AS modal FROM market_prices WHERE provider='test-provider' AND source_record_key=%s", (key,)).fetchone()
            self.assertEqual(row["count"], 1)
            self.assertEqual(float(row["modal"]), 11.0)
            conn.rollback()


if __name__ == "__main__": unittest.main()
