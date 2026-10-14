import sys
import unittest
import uuid
from pathlib import Path
from flask import Flask

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from db import connection
from routes.platform import platform_bp


class FinanceIntegrationTests(unittest.TestCase):
    def test_owner_scoped_finance_crud_and_profit_calculation(self):
        email=f"finance-test-{uuid.uuid4().hex}@example.invalid"
        with connection() as conn:
            if not conn.execute("SELECT to_regclass('public.farm_sales') AS t").fetchone()["t"]:
                self.skipTest("PostgreSQL finance schema is not initialized")
            user=conn.execute("INSERT INTO users(name,email,user_type) VALUES('Test farmer',%s,'farmer') RETURNING id",(email,)).fetchone()
            farm=conn.execute("INSERT INTO farms(user_id,name,area_amount,area_unit) VALUES(%s,'Test farm',2,'acre') RETURNING id",(user["id"],)).fetchone()
            field=conn.execute("INSERT INTO fields(farm_id,name,area_acres) VALUES(%s,'Test field',2) RETURNING id",(farm["id"],)).fetchone()
            crop=conn.execute("INSERT INTO crops(field_id,crop_name,season) VALUES(%s,'Wheat','Rabi') RETURNING id",(field["id"],)).fetchone()
            user_id,farm_id,crop_id=user["id"],farm["id"],crop["id"]
        try:
            app=Flask(__name__);app.secret_key="test";app.register_blueprint(platform_bp,url_prefix="/api")
            client=app.test_client()
            with client.session_transaction() as session:session["user_id"]=user_id
            expense=client.post("/api/farm/expenses",json={"category":"seeds","description":"Wheat seed","amount":"1000","incurred_on":"2026-10-01","farm_id":farm_id,"crop_id":crop_id,"season":"Rabi"})
            self.assertEqual(expense.status_code,201,expense.get_json())
            sale=client.post("/api/farm/sales",json={"quantity":"1000","quantity_unit":"kg","price_unit":"quintal","unit_price":"2500","selling_cost":"100","sold_on":"2026-10-02","farm_id":farm_id,"crop_id":crop_id,"season":"Rabi"})
            self.assertEqual(sale.status_code,201,sale.get_json())
            summary=client.get("/api/farm/profit-summary?farm_id=%s&crop_id=%s&season=Rabi&expected_quantity=12&expected_quantity_unit=quintal"%(farm_id,crop_id)).get_json()
            self.assertEqual(summary["gross_revenue"],"25000.00")
            self.assertEqual(summary["net_return"],"23900.00")
            self.assertEqual(summary["break_even_status"],"available")
            self.assertEqual(summary["breakdown"][0]["cost_per_acre"],"500.00")
            updated=client.patch(f"/api/farm/sales/{sale.json['id']}",json={"quantity":"2000"})
            self.assertEqual(updated.status_code,200,updated.get_json())
            self.assertEqual(float(updated.json["quantity"]),2000.0)
            self.assertEqual(client.delete(f"/api/farm/sales/{sale.json['id']}").status_code,204)
            self.assertEqual(client.delete(f"/api/farm/expenses/{expense.json['id']}").status_code,204)
        finally:
            with connection() as conn:conn.execute("DELETE FROM users WHERE email=%s",(email,))


if __name__=="__main__":unittest.main()
