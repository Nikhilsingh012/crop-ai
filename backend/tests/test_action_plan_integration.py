import sys
import unittest
import uuid
from datetime import date, timedelta
from pathlib import Path
from flask import Flask

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db import connection
from routes.platform import platform_bp


class DailyActionPlanIntegrationTests(unittest.TestCase):
    def test_daily_actions_are_persisted_idempotently_and_owner_scoped(self):
        email=f"action-plan-test-{uuid.uuid4().hex}@example.invalid"
        with connection() as conn:
            required=conn.execute("SELECT to_regclass('public.farm_tasks') AS tasks, to_regclass('public.crops') AS crops").fetchone()
            if not required["tasks"] or not required["crops"]:
                self.skipTest("PostgreSQL application schema is not initialized")
            user=conn.execute("INSERT INTO users(name,email,user_type) VALUES('Test farmer',%s,'farmer') RETURNING id",(email,)).fetchone()
            farm=conn.execute("INSERT INTO farms(user_id,name,state) VALUES(%s,'Test farm','Bihar') RETURNING id",(user["id"],)).fetchone()
            field=conn.execute("INSERT INTO fields(farm_id,name) VALUES(%s,'Test field') RETURNING id",(farm["id"],)).fetchone()
            crop=conn.execute("INSERT INTO crops(field_id,crop_name,current_stage) VALUES(%s,'Tomato','flowering') RETURNING id",(field["id"],)).fetchone()
            alert_id=conn.execute("INSERT INTO alerts(crop_id,alert_type,severity,title,message) VALUES(%s,'forecast_weather','HIGH','Rain alert','Recent forecast alert') RETURNING id",(crop["id"],)).fetchone()["id"]
            scheme_id=f"daily-plan-{uuid.uuid4().hex}"
            conn.execute("""INSERT INTO schemes(scheme_id,official_name,government_level,official_source_url,official_application_url,
                deadline,application_status,last_checked_at,verification_status)
                VALUES(%s,'Verified test scheme','central','https://example.gov.in/source','https://example.gov.in/app',%s,'open',NOW(),'verified')""",(scheme_id,date.today()+timedelta(days=7)))
            out_of_state_scheme_id=f"daily-plan-{uuid.uuid4().hex}"
            conn.execute("""INSERT INTO schemes(scheme_id,official_name,government_level,state_scope,official_source_url,deadline,application_status,last_checked_at,verification_status)
                VALUES(%s,'Out-of-state test scheme','state',ARRAY['Uttar Pradesh'],'https://example.gov.in/source',%s,'open',NOW(),'verified')""",(out_of_state_scheme_id,date.today()+timedelta(days=5)))
            closed_scheme_id=f"daily-plan-{uuid.uuid4().hex}"
            conn.execute("""INSERT INTO schemes(scheme_id,official_name,government_level,official_source_url,deadline,application_status,last_checked_at,verification_status)
                VALUES(%s,'Closed test scheme','central','https://example.gov.in/source',%s,'closed',NOW(),'verified')""",(closed_scheme_id,date.today()+timedelta(days=3)))
            user_id,crop_id=user["id"],crop["id"]
        try:
            app=Flask(__name__);app.secret_key="test";app.register_blueprint(platform_bp,url_prefix="/api")
            client=app.test_client()
            with client.session_transaction() as session: session["user_id"]=user_id
            first=client.get("/api/farm/actions/today")
            second=client.get("/api/farm/actions/today")
            self.assertEqual(first.status_code,200)
            self.assertEqual(len(first.json["items"]),4)
            self.assertEqual(second.json["generated_count"],0)
            weather_task=next(item for item in first.json["items"] if item["generated_by"]=="recent_weather_alert")
            self.assertEqual(weather_task["evidence_quality"],"limited")
            self.assertEqual(weather_task["source_references"],[{"type":"weather_alert","id":alert_id}])
            self.assertEqual([item["scheme_id"] for item in first.json["scheme_deadlines"]],[scheme_id])
            self.assertIn("verified",first.json["notice"])
            with connection() as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM farm_tasks WHERE user_id=%s AND crop_id=%s",(user_id,crop_id)).fetchone()["n"],4)
            action_id=first.json["items"][0]["id"]
            self.assertEqual(client.post(f"/api/farm/actions/{action_id}/complete",json={}).json["state"],"completed")
            self.assertEqual(client.post(f"/api/farm/actions/{action_id}/complete",json={}).status_code,409)
            dismiss_id=first.json["items"][1]["id"]
            self.assertEqual(client.post(f"/api/farm/actions/{dismiss_id}/dismiss",json={}).json["state"],"dismissed")
        finally:
            with connection() as conn:
                if "scheme_id" in locals(): conn.execute("DELETE FROM schemes WHERE scheme_id=%s",(scheme_id,))
                if "out_of_state_scheme_id" in locals(): conn.execute("DELETE FROM schemes WHERE scheme_id=%s",(out_of_state_scheme_id,))
                if "closed_scheme_id" in locals(): conn.execute("DELETE FROM schemes WHERE scheme_id=%s",(closed_scheme_id,))
                conn.execute("DELETE FROM users WHERE email=%s",(email,))


if __name__=="__main__":unittest.main()
