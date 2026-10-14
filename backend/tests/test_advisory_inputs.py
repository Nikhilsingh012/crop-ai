import unittest
from datetime import date

from services.lifecycle import estimate_lifecycle
from services.irrigation import recommend_irrigation


class AdvisoryInputTests(unittest.TestCase):
    def test_harvest_estimate_requires_farmer_date(self):
        missing = estimate_lifecycle({"crop_name": "Rice", "sowing_date": date(2026, 1, 1)}, today=date(2026, 2, 1))
        self.assertEqual(missing["status"], "insufficient_data")
        self.assertIsNone(missing["expected_harvest_date"])
        supplied = estimate_lifecycle({"crop_name": "Rice", "expected_harvest_date": date(2026, 3, 1)}, today=date(2026, 2, 1))
        self.assertEqual(supplied["status"], "farmer_estimate")
        self.assertEqual(supplied["days_until_harvest"], 28)

    def test_irrigation_does_not_infer_need_from_unverified_cutoffs(self):
        result = recommend_irrigation("Rice", "flowering", rainfall=0, temperature=40)
        self.assertEqual(result["status"], "insufficient_data")
        self.assertIsNone(result["needed"])
        self.assertEqual(result["evidence_quality"], "insufficient")

    def test_irrigation_prompt_uses_explicit_moisture_input_without_a_crop_dose(self):
        dry = recommend_irrigation("Rice", "flowering", soil_moisture_status="dry", forecast_rainfall=0)
        self.assertEqual(dry["status"], "conditional")
        self.assertEqual(dry["evidence_quality"], "user_input")
        self.assertIsNone(dry["needed"])
        self.assertIn("no exact water amount", " ".join(dry["limitations"]).lower())
        wet = recommend_irrigation("Tomato", "fruiting", soil_moisture_status="wet", forecast_rainfall=15)
        self.assertIn("drainage", wet["timing"])

    def test_irrigation_rejects_invalid_sensor_and_weather_values(self):
        for options in ({"soil_moisture_status":"saturated-ish"}, {"forecast_rainfall":float("nan")}, {"temperature":100}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                recommend_irrigation("Rice", "flowering", **options)


if __name__ == "__main__":
    unittest.main()
