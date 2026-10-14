import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.action_plan import daily_actions


class DailyActionPlanTests(unittest.TestCase):
    def test_actions_are_limited_and_disclose_missing_evidence(self):
        actions = daily_actions({"crop_name": "Tomato", "current_stage": "flowering", "sowing_date": None})
        self.assertEqual(len(actions), 3)
        self.assertTrue(all(item["evidence_quality"] == "limited" for item in actions))
        self.assertTrue(all(item["source_references"] == [] for item in actions))
        self.assertFalse(any("fertilizer" in item["recommendation"].lower() or "pesticide" in item["recommendation"].lower() for item in actions))

    def test_unknown_crop_uses_general_inspection_without_inventing_crop_facts(self):
        actions = daily_actions({"crop_name": "Unknown crop"})
        self.assertEqual(len(actions), 3)
        self.assertTrue(any("check soil moisture" in item["recommendation"].lower() for item in actions))

    def test_recent_weather_alert_adds_only_a_refresh_prompt_with_provenance(self):
        actions = daily_actions(
            {"crop_id": 19, "crop_name": "Tomato"},
            recent_weather_alerts=[{"id": 23, "title": "Heavy rain", "severity": "HIGH"}],
        )
        self.assertEqual(len(actions), 4)
        prompt = actions[-1]
        self.assertEqual(prompt["priority"], "high")
        self.assertEqual(prompt["evidence_quality"], "limited")
        self.assertEqual(prompt["source_references"], [{"type": "weather_alert", "id": 23}])
        self.assertIn("Refresh", prompt["recommendation"])


if __name__ == "__main__": unittest.main()
