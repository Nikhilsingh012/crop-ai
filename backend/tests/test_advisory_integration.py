import sys
import unittest
import uuid
from pathlib import Path
from flask import Flask

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db import connection
from routes.insights import insights_bp


class AdvisoryIntegrationTests(unittest.TestCase):
    def test_irrigation_and_harvest_advisories_are_owner_scoped_and_persisted(self):
        email = f"advisory-test-{uuid.uuid4().hex}@example.invalid"
        with connection() as conn:
            if not conn.execute("SELECT to_regclass('public.advisory_records') AS t").fetchone()["t"]:
                self.skipTest("PostgreSQL advisory schema is not initialized")
            user_id = conn.execute("INSERT INTO users(name,email,user_type) VALUES('Advisory test',%s,'farmer') RETURNING id", (email,)).fetchone()["id"]
            farm_id = conn.execute("INSERT INTO farms(user_id,name) VALUES(%s,'Advisory farm') RETURNING id", (user_id,)).fetchone()["id"]
            field_id = conn.execute("INSERT INTO fields(farm_id,name) VALUES(%s,'Advisory field') RETURNING id", (farm_id,)).fetchone()["id"]
            crop_id = conn.execute("INSERT INTO crops(field_id,crop_name,current_stage) VALUES(%s,'Rice','flowering') RETURNING id", (field_id,)).fetchone()["id"]
        try:
            app = Flask(__name__); app.secret_key = "test"; app.register_blueprint(insights_bp, url_prefix="/api")
            client = app.test_client()
            with client.session_transaction() as session: session["user_id"] = user_id

            irrigation = client.post("/api/advisories/irrigation", json={"crop_id": crop_id, "soil_moisture_status": "dry", "forecast_rainfall": 0})
            self.assertEqual(irrigation.status_code, 201, irrigation.get_json())
            self.assertEqual(irrigation.json["status"], "conditional")
            self.assertIsNone(irrigation.json["needed"])
            invalid = client.post("/api/advisories/irrigation", json={"crop_id": crop_id, "soil_moisture_status": "maybe"})
            self.assertEqual(invalid.status_code, 400)

            harvest = client.post("/api/advisories/harvest-window", json={"crop_id": crop_id, "expected_harvest_date": "2026-12-10"})
            self.assertEqual(harvest.status_code, 200, harvest.get_json())
            self.assertEqual(harvest.json["confidence"], "farmer_entered_date")
            self.assertIsNone(harvest.json["estimated_date_range"])
            self.assertEqual(client.get(f"/api/crops/{crop_id}/harvest-window").status_code, 200)

            with connection() as conn:
                rows = conn.execute("SELECT advisory_type,evidence_quality FROM advisory_records WHERE crop_id=%s ORDER BY id", (crop_id,)).fetchall()
            self.assertEqual([row["advisory_type"] for row in rows], ["irrigation", "harvest"])
        finally:
            with connection() as conn:
                conn.execute("DELETE FROM users WHERE email=%s", (email,))


if __name__ == "__main__":
    unittest.main()
