import unittest

from services.agriculture.risk_engine import compute_risk


class AgriculturalRiskEngineTests(unittest.TestCase):
    def test_high_risk_for_tomato_flowering_in_high_humidity(self):
        result = compute_risk(
            crop="Tomato",
            growth_stage="Flowering",
            humidity=88,
            temperature=29,
            rainfall=48,
            wind=12,
            soil_type="Loam",
            season="Monsoon",
            location="Uttar Pradesh",
        )

        self.assertEqual(result["level"], "HIGH")
        self.assertIn("Humidity", result["reasons"][0])

    def test_low_risk_for_healthy_conditions(self):
        result = compute_risk(
            crop="Wheat",
            growth_stage="Vegetative",
            humidity=45,
            temperature=22,
            rainfall=8,
            wind=8,
            soil_type="Clay loam",
            season="Rabi",
            location="Punjab",
        )

        self.assertEqual(result["level"], "LOW")


if __name__ == "__main__":
    unittest.main()
