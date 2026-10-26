import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.market_estimate import calculate_gross_values, decimal_strings, parse_quantity
from services.market_data import normalize_record


class MarketEstimateTests(unittest.TestCase):
    def test_quantity_converts_quintals_to_kilograms(self):
        quantity, kilograms = parse_quantity("2.5", "quintal")
        self.assertEqual(quantity, Decimal("2.5"))
        self.assertEqual(kilograms, Decimal("250.0"))

    def test_kilogram_quantity_stays_in_kilograms(self):
        _, kilograms = parse_quantity("12.75", "kg")
        self.assertEqual(kilograms, Decimal("12.75"))

    def test_price_conversion_and_gross_value_are_deterministic(self):
        values = calculate_gross_values(Decimal("200"), Decimal("1000"), Decimal("1200"), Decimal("1400"))
        self.assertEqual(decimal_strings(values), {
            "minimum_price_per_kg": "10.0000", "modal_price_per_kg": "12.0000", "maximum_price_per_kg": "14.0000",
            "minimum_value": "2000.00", "expected_value": "2400.00", "maximum_value": "2800.00",
        })

    def test_missing_modal_is_not_substituted(self):
        values = calculate_gross_values(Decimal("100"), Decimal("800"), None, Decimal("1200"))
        self.assertEqual(values["minimum_value"], Decimal("800.00"))
        self.assertIsNone(values["expected_value"])
        self.assertEqual(values["maximum_value"], Decimal("1200.00"))

    def test_invalid_quantity_and_unit_are_rejected(self):
        for value, unit in (("0", "kg"), ("-3", "quintal"), ("nan", "kg"), ("1", "tonne"), ("1e20", "kg")):
            with self.subTest(value=value, unit=unit), self.assertRaises(ValueError):
                parse_quantity(value, unit)

    def test_endpoint_validates_before_calling_provider(self):
        from flask import Flask
        from routes.markets import markets_bp

        app = Flask(__name__)
        app.register_blueprint(markets_bp, url_prefix="/api")
        with patch("routes.markets.fetch_records") as fetch:
            response = app.test_client().get("/api/markets/estimate?commodity=Onion&state=Maharashtra&district=Pune&quantity=-2&unit=kg")
        self.assertEqual(response.status_code, 400)
        fetch.assert_not_called()

    def test_endpoint_returns_source_dates_and_calculated_values(self):
        from flask import Flask
        from routes.markets import markets_bp

        app = Flask(__name__)
        app.register_blueprint(markets_bp, url_prefix="/api")
        provider_record = normalize_record({
            "state": "Maharashtra", "district": "Pune", "market": "Pune", "commodity": "Onion",
            "variety": "Red", "grade": "FAQ", "arrival_date": date.today().strftime("%d/%m/%Y"),
            "min_price": "1000", "modal_price": "1200", "max_price": "1400",
        })
        with patch("routes.markets.fetch_records", return_value=[provider_record]), patch("routes.markets._quote_rate_limited", return_value=(False, 0)):
            response = app.test_client().get("/api/markets/estimate?commodity=Onion&state=Maharashtra&district=Pune&quantity=2&unit=quintal")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["items"][0]["quantity_kg"], "200")
        self.assertEqual(payload["items"][0]["modal_price_per_kg"], "12.0000")
        self.assertEqual(payload["items"][0]["expected_value"], "2400.00")
        self.assertEqual(payload["items"][0]["reporting_date"], date.today().isoformat())
        self.assertIn("retrieved_at", payload)

    def test_endpoint_accepts_common_gujarat_misspelling(self):
        from flask import Flask
        from routes.markets import markets_bp

        app = Flask(__name__)
        app.register_blueprint(markets_bp, url_prefix="/api")
        provider_record = normalize_record({
            "state": "Gujarat", "district": "Rajkot", "market": "Rajkot", "commodity": "Onion",
            "arrival_date": date.today().strftime("%d/%m/%Y"),
            "min_price": "1000", "modal_price": "1200", "max_price": "1400",
        })
        with patch("routes.markets.fetch_records", return_value=[provider_record]) as fetch, patch("routes.markets._quote_rate_limited", return_value=(False, 0)):
            response = app.test_client().get("/api/markets/estimate?commodity=onion&state=gujrat&district=rajkot&quantity=12&unit=kg")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "available")
        self.assertEqual(fetch.call_args.kwargs["filters"]["state"], "Gujarat")
        self.assertEqual(fetch.call_args.kwargs["filters"]["commodity"], "Onion")
        self.assertEqual(fetch.call_args.kwargs["filters"]["district"], "Rajkot")

    def test_endpoint_searches_all_india_when_location_is_blank(self):
        from flask import Flask
        from routes.markets import markets_bp

        app = Flask(__name__)
        app.register_blueprint(markets_bp, url_prefix="/api")
        records = [
            normalize_record({"state": "Gujarat", "district": "Rajkot", "market": "Rajkot", "commodity": "Onion", "arrival_date": date.today().strftime("%d/%m/%Y"), "min_price": "1000", "modal_price": "1200", "max_price": "1400"}),
            normalize_record({"state": "Maharashtra", "district": "Pune", "market": "Pune", "commodity": "Onion", "arrival_date": date.today().strftime("%d/%m/%Y"), "min_price": "1100", "modal_price": "1300", "max_price": "1500"}),
        ]
        with patch("routes.markets.fetch_records", return_value=records) as fetch, patch("routes.markets._quote_rate_limited", return_value=(False, 0)):
            response = app.test_client().get("/api/markets/estimate?commodity=onion&quantity=12&unit=kg")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "available")
        self.assertEqual({item["state"] for item in payload["items"]}, {"Gujarat", "Maharashtra"})
        self.assertIsNone(payload["query"]["state"])
        self.assertEqual(fetch.call_args.kwargs["filters"], {"commodity": "Onion"})

    def test_endpoint_searches_every_district_in_selected_state(self):
        from flask import Flask
        from routes.markets import markets_bp

        app = Flask(__name__)
        app.register_blueprint(markets_bp, url_prefix="/api")
        rows = [
            ("Haryana", "Hisar", "Hisar"),
            ("Haryana", "Karnal", "Karnal"),
            ("Uttar Pradesh", "Agra", "Agra"),
        ]
        records = [normalize_record({
            "state": state, "district": district, "market": market, "commodity": "Onion",
            "arrival_date": date.today().strftime("%d/%m/%Y"),
            "min_price": "1000", "modal_price": "1200", "max_price": "1400",
        }) for state, district, market in rows]
        with patch("routes.markets.fetch_records", return_value=records) as fetch, patch("routes.markets._quote_rate_limited", return_value=(False, 0)):
            response = app.test_client().get("/api/markets/estimate?commodity=Onion&state=Haryana&quantity=12&unit=kg")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual({item["district"] for item in payload["items"]}, {"Hisar", "Karnal"})
        self.assertIsNone(payload["query"]["district"])
        self.assertEqual(fetch.call_args.kwargs["filters"], {"commodity": "Onion", "state": "Haryana"})

    def test_endpoint_returns_a_clear_empty_search_without_a_route_error(self):
        from flask import Flask
        from routes.markets import markets_bp

        app = Flask(__name__)
        app.register_blueprint(markets_bp, url_prefix="/api")
        with patch("routes.markets.fetch_records", return_value=[]), patch("routes.markets._quote_rate_limited", return_value=(False, 0)):
            response = app.test_client().get("/api/markets/estimate?commodity=Onion&state=Haryana&district=Faridabad&quantity=12&unit=kg")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "empty")
        self.assertEqual(response.get_json()["items"], [])
        self.assertIn("No unambiguous reported prices", response.get_json()["message"])


if __name__ == "__main__":
    unittest.main()
