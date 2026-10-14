import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.finance import FinanceInputError, calculate_finance, price_per_quintal, quantity_in_quintals


class FinanceTests(unittest.TestCase):
    def test_converts_supported_quantity_and_price_units(self):
        self.assertEqual(quantity_in_quintals(1000, "kg"), Decimal("10.00"))
        self.assertEqual(quantity_in_quintals(2, "tonne"), Decimal("20"))
        self.assertEqual(price_per_quintal(12, "kg"), Decimal("1.2E+3"))
        with self.assertRaises(FinanceInputError): quantity_in_quintals(4, "bag")

    def test_calculates_revenue_cost_net_and_break_even_only_with_output(self):
        expenses = [{"amount": Decimal("1000"), "crop_id": 1, "crop_name": "Wheat", "season": "Rabi", "area_acres": 2}]
        sales = [{"quantity": Decimal("1000"), "quantity_unit": "kg", "price_unit": "quintal", "unit_price": Decimal("2500"), "selling_cost": Decimal("100"), "crop_id": 1, "crop_name": "Wheat", "season": "Rabi", "area_acres": 2}]
        base = calculate_finance(expenses, sales)
        self.assertEqual(base["gross_revenue"], Decimal("25000"))
        self.assertEqual(base["net_return"], Decimal("23900"))
        self.assertIsNone(base["break_even_price_per_quintal"])
        with_output = calculate_finance(expenses, sales, Decimal("12"), "quintal", 10, -5)
        self.assertEqual(with_output["break_even_price_per_quintal"], Decimal("91.67"))
        self.assertEqual(with_output["scenario"]["expected_quantity_quintals"], Decimal("13.2"))
        self.assertEqual(with_output["breakdown"][0]["cost_per_acre"], Decimal("500"))

    def test_missing_recorded_sale_price_marks_scenario_incomplete(self):
        result = calculate_finance([], [], Decimal("2"), "tonne")
        self.assertEqual(result["scenario"]["status"], "incomplete_missing_recorded_sale_price")
        self.assertIsNone(result["scenario"]["estimated_net_return"])

    def test_invalid_or_extreme_scenario_is_rejected(self):
        with self.assertRaises(FinanceInputError): calculate_finance([], [], 1, "quintal", -101, 0)
        with self.assertRaises(FinanceInputError): calculate_finance([], [], 1, "quintal", 0, 501)


if __name__ == "__main__": unittest.main()
