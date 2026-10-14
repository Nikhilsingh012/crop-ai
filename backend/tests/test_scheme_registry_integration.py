import sys
import unittest
import uuid
from pathlib import Path
from flask import Flask

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db import connection
from routes.platform import platform_bp


class SchemeRegistryIntegrationTests(unittest.TestCase):
    def test_registry_details_matching_and_saved_checklist_are_database_backed(self):
        email = f"scheme-test-{uuid.uuid4().hex}@example.invalid"
        with connection() as conn:
            if not conn.execute("SELECT to_regclass('public.schemes') AS t").fetchone()["t"]:
                self.skipTest("PostgreSQL scheme schema is not initialized")
            user_id = conn.execute("INSERT INTO users(name,email,user_type,state) VALUES('Scheme test',%s,'farmer','Bihar') RETURNING id", (email,)).fetchone()["id"]
        try:
            app = Flask(__name__); app.secret_key = "test"; app.register_blueprint(platform_bp, url_prefix="/api")
            client = app.test_client()
            with client.session_transaction() as session: session["user_id"] = user_id

            listing = client.get("/api/schemes?q=KISAN&level=central")
            self.assertEqual(listing.status_code, 200, listing.get_json())
            self.assertTrue(any(item["scheme_id"] == "pm-kisan" for item in listing.json["items"]))
            self.assertEqual(client.get("/api/schemes?page=0").status_code, 400)
            details = client.get("/api/schemes/pm-kisan")
            self.assertEqual(details.status_code, 200, details.get_json())
            self.assertEqual(details.json["scheme"]["application_status"], "unknown")

            invalid = client.post("/api/schemes/match", json={"answers": {"landholding_family": "yes"}})
            self.assertEqual(invalid.status_code, 400)
            match = client.post("/api/schemes/match", json={"answers": {"landholding_family": True}})
            self.assertEqual(match.status_code, 200, match.get_json())
            self.assertFalse(match.json["answers_saved"])
            self.assertIn("pm-kisan", {item["scheme_id"] for item in match.json["results"]})

            saved = client.post("/api/schemes/saved", json={"scheme_id": "pm-kisan"})
            self.assertEqual(saved.status_code, 201, saved.get_json())
            checklist = client.patch("/api/schemes/saved/pm-kisan", json={"checklist_state": {"eKYC": True}})
            self.assertEqual(checklist.status_code, 200, checklist.get_json())
            self.assertTrue(checklist.json["checklist_state"]["eKYC"])
            self.assertEqual(client.get("/api/schemes/deadlines").status_code, 200)
            self.assertEqual(client.get("/api/schemes/updates").status_code, 200)
        finally:
            with connection() as conn:
                conn.execute("DELETE FROM users WHERE email=%s", (email,))


if __name__ == "__main__":
    unittest.main()
