import unittest
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from flask import Flask

import services.agriculture.crop_risk_engine as risk_engine
from services.rag.knowledge_loader import get_document
from services.crop_catalog import load_catalog, resolve_crop
import services.crop_risk_service
from services.rag.source_ingest import load_source_documents
from services.weather_signals import rainfall_signals


def weather(rainfall, humidity=55, temperature=24, wind=8):
    return {"temperature": temperature, "humidity": humidity, "wind_speed": wind, "forecast": [{"rainfall": value} for value in rainfall]}


def analyze_verified(crop_name, weather_data, growth_stage=None):
    knowledge = dict(get_document(crop_name))
    knowledge["threshold_evidence_status"] = "verified"
    registry_entry, _ = resolve_crop(crop_name)
    legacy_risks = set(knowledge.get("risks", []))
    supported = []
    if legacy_risks & {"waterlogging", "heavy_rain"}: supported.extend(["EXCESSIVE_RAINFALL", "WATERLOGGING"])
    if "high_humidity" in legacy_risks: supported.append("HIGH_HUMIDITY")
    if "heat" in legacy_risks: supported.append("HEAT_STRESS")
    if "wind" in legacy_risks: supported.append("STRONG_WIND")
    if "cold" in legacy_risks: supported.append("COLD_STRESS")
    with patch.object(risk_engine, "crop_by_id", return_value={"crop_id": registry_entry["crop_id"], "knowledge_status": "PARTIAL", "supported_risk_types": supported}):
        return risk_engine.analyze_forecast({}, weather_data, knowledge, growth_stage)


class CropRiskIntelligenceTests(unittest.TestCase):
    def test_rice_heavy_rain_is_high_risk(self):
        result = analyze_verified("rice", weather([15, 85, 65], 88), "vegetative")
        self.assertIn(result["overall_risk"], {"HIGH", "SEVERE"})
        self.assertTrue(any(alert["risk_type"] == "EXCESSIVE_RAINFALL" for alert in result["alerts"]))

    def test_wheat_extreme_heat(self):
        result = analyze_verified("wheat", weather([0, 0], 45, 36), "grain filling")
        self.assertTrue(any(alert["risk_type"] == "HEAT_STRESS" for alert in result["alerts"]))

    def test_tomato_humidity_and_rain(self):
        result = analyze_verified("tomato", weather([20, 30], 90, 27), "flowering")
        self.assertTrue(any(alert["risk_type"] == "HIGH_HUMIDITY" for alert in result["alerts"]))

    def test_waterlogging_and_cold_rules_use_crop_metadata(self):
        wet = analyze_verified("potato", weather([70, 50], 60), "tuber development")
        cold_weather = weather([0], 55, 3)
        cold_weather["forecast"][0]["temperature_min"] = 0
        cold = analyze_verified("potato", cold_weather, "vegetative")
        self.assertTrue(any(alert["risk_type"] == "WATERLOGGING" for alert in wet["alerts"]))
        self.assertTrue(any(alert["risk_type"] == "COLD_STRESS" for alert in cold["alerts"]))

    def test_normal_weather_is_low(self):
        result = analyze_verified("rice", weather([0, 2], 55, 24), "vegetative")
        self.assertEqual(result["overall_risk"], "LOW")

    def test_missing_weather_is_safe(self):
        result = analyze_verified("rice", {"forecast": []}, None)
        self.assertEqual(result["overall_risk"], "LOW")

    def test_missing_knowledge_is_detectable(self):
        self.assertIsNone(get_document("unknown crop"))

    def test_general_rainfall_signals_follow_imd_ranges_without_claiming_crop_risk(self):
        forecast = [
            {"date": "2026-10-12", "rainfall": 64.4},
            {"date": "2026-10-13", "rainfall": 64.5},
            {"date": "2026-10-14", "rainfall": 115.6},
            {"date": "2026-10-15", "rainfall": 204.5},
            {"date": "2026-10-16", "rainfall": float("nan")},
        ]
        signals = rainfall_signals(forecast)
        self.assertEqual([item["category"] for item in signals], ["heavy", "very heavy", "extremely heavy"])
        self.assertTrue(all("not an official warning" in item["explanation"] for item in signals))
        self.assertTrue(all("crop-specific risk score" in item["explanation"] for item in signals))

    def test_catalog_aliases_resolve_to_canonical_ids(self):
        expected = {"Paddy": "rice", "Dhan": "rice", "Arhar": "pigeon_pea", "Toor": "pigeon_pea", "Chana": "chickpea", "Bhindi": "okra", "Baingan": "brinjal", "Bajra": "pearl_millet", "Jowar": "sorghum", "Moong": "green_gram", "Urad": "black_gram", "Til": "sesame", "Alsi": "linseed"}
        for alias, crop_id in expected.items():
            with self.subTest(alias=alias):
                crop, candidates = resolve_crop(f"  {alias.upper()}!! ")
                self.assertEqual(crop["crop_id"], crop_id)
                self.assertEqual(candidates, [crop["canonical_name"]])

    def test_registry_has_over_150_unique_crops_and_no_alias_collisions(self):
        catalog = load_catalog()
        self.assertGreaterEqual(len(catalog), 150)
        self.assertEqual(len({item["crop_id"] for item in catalog}), len(catalog))
        owners = {}
        for item in catalog:
            for name in [item["crop_id"].replace("_", " "), item["canonical_name"], *item["aliases"]]:
                from services.crop_catalog import normalize_text
                key = normalize_text(name)
                self.assertTrue(key not in owners or owners[key] == item["crop_id"], f"{name!r} conflicts with {owners.get(key)}")
                owners[key] = item["crop_id"]

    def test_limited_crop_has_watch_and_no_fabricated_score(self):
        result = risk_engine.analyze_forecast({}, weather([80, 20], 95, 40, 60), None, None)
        self.assertEqual(result["overall_risk"], "WATCH")
        self.assertIsNone(result["risk_score"])
        self.assertEqual(result["knowledge_status"], "LIMITED")

    def test_legacy_unverified_thresholds_cannot_create_a_score_or_alert(self):
        result = risk_engine.analyze_forecast({}, weather([200, 150], 99, 48, 90), get_document("rice"), "flowering")
        self.assertEqual(result["overall_risk"], "WATCH")
        self.assertIsNone(result["risk_score"])
        self.assertEqual(result["alerts"], [])
        self.assertTrue(any("verified source" in item for item in result["limitations"]))
        self.assertEqual(result["weather_observations"]["forecast_rainfall_mm"], 350.0)
        self.assertEqual(result["weather_observations"]["peak_daily_rainfall_mm"], 200.0)

    def test_ambiguous_regional_names_request_a_choice(self):
        for name in ("tori", "gobhi", "methi", "chilli"):
            with self.subTest(name=name):
                crop, candidates = resolve_crop(name)
                self.assertIsNone(crop)
                self.assertGreaterEqual(len(candidates), 2)

    def test_singular_plural_crop_names_resolve(self):
        for name, crop_id in (("grape", "grapes"), ("tomatoes", "tomato")):
            with self.subTest(name=name):
                crop, _ = resolve_crop(name)
                self.assertEqual(crop["crop_id"], crop_id)

    def test_retrieval_never_falls_back_to_another_crop(self):
        from services.rag.retriever import retrieve
        dragon_docs = retrieve("Dragon Fruit", "weather risk")
        rice_docs = retrieve("paddy", "weather risk")
        self.assertEqual(dragon_docs, [])
        self.assertEqual(rice_docs, [])

    def test_retrieval_prefers_matching_region_and_stage(self):
        from services.rag.embeddings import embed
        from services.rag.retriever import retrieve
        from unittest.mock import patch as mock_patch
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.json"
            records = []
            for crop_id, region, stage, source in (("rice", "Odisha", "flowering", "Odisha flowering"), ("rice", "Punjab", "harvest", "Punjab harvest"), ("wheat", "Odisha", "flowering", "wrong crop")):
                metadata = {"crop_id": crop_id, "region": region, "stage": stage, "source": source, "source_url": "https://example.org/source", "source_file": "source.txt"}
                records.append({"metadata": metadata, "text": source, "embedding": embed(source)})
            path.write_text(json.dumps(records), encoding="utf-8")
            with mock_patch("services.rag.retriever.INDEX_PATH", path):
                found = retrieve("paddy", "advisory", top_k=5, region="Odisha", stage="flowering")
            self.assertEqual([item["metadata"]["source"] for item in found], ["Odisha flowering"])

    @patch("services.crop_risk_service.save_crop_risk", return_value={"id": 10})
    @patch("services.crop_risk_service.save_weather_snapshot")
    @patch("services.crop_risk_service.latest_crop_risk", return_value=None)
    @patch("services.crop_risk_service.retrieve", return_value=[])
    @patch("services.crop_risk_service.get_weather", return_value=weather([0, 0]))
    @patch("services.crop_risk_service.get_user_crop", return_value={"id": 7, "crop_name": "Dragon Fruit", "latitude": 19.0, "longitude": 73.0})
    def test_registered_limited_crop_uses_weather_and_returns_structured_watch(self, *_mocks):
        from services.crop_risk_service import run_crop_risk_analysis
        response = run_crop_risk_analysis(7, force=True)
        self.assertEqual(response["risk"]["crop_id"], "dragon_fruit")
        self.assertEqual(response["risk"]["knowledge_status"], "LIMITED")
        self.assertIsNone(response["risk"]["risk_score"])
        self.assertIn("forecast", response["weather"])

    def test_full_requested_sample_runs_through_mocked_analysis_pipeline(self):
        samples = ["Rice", "Wheat", "Maize", "Chickpea", "Pigeon Pea", "Indian Mustard", "Soybean", "Cotton", "Sugarcane", "Potato", "Tomato", "Onion", "Groundnut", "Mango", "Banana", "Grapes", "Turmeric", "Ginger", "Tea", "Coffee", "Dragon Fruit", "Moringa", "Berseem", "Napier Grass"]
        for crop_name in samples:
            with self.subTest(crop=crop_name):
                stored_crop = {"id": 29, "crop_name": crop_name, "latitude": 19.0, "longitude": 73.0, "growth_stage": "vegetative"}
                with patch.object(services.crop_risk_service, "get_user_crop", return_value=stored_crop), \
                     patch.object(services.crop_risk_service, "get_weather", return_value=weather([0, 0])), \
                     patch.object(services.crop_risk_service, "retrieve", return_value=[]), \
                     patch.object(services.crop_risk_service, "latest_crop_risk", return_value=None), \
                     patch.object(services.crop_risk_service, "save_weather_snapshot"), \
                     patch.object(services.crop_risk_service, "save_crop_risk", return_value={"id": 1}), \
                     patch.object(services.crop_risk_service, "create_alert"):
                    response = services.crop_risk_service.run_crop_risk_analysis(29, force=True)
                expected_crop, _ = resolve_crop(crop_name)
                self.assertEqual(response["risk"]["crop_name"], expected_crop["canonical_name"])
                self.assertIn(response["risk"]["knowledge_status"], {"PARTIAL", "LIMITED"})
                self.assertIn(response["risk"]["overall_risk"], {"WATCH", "LOW", "MODERATE", "HIGH", "SEVERE"})
                self.assertIsInstance(response["risk"]["alerts"], list)
                self.assertIn("analyzed_at", response["risk"])
                self.assertIn("latitude", response["risk"]["location"])
                self.assertIsInstance(response["risk"]["retrieved_sources"], list)
                if response["risk"]["knowledge_status"] == "LIMITED":
                    self.assertIsNone(response["risk"]["risk_score"])

    def test_api_catalog_aliases_and_ambiguous_name_responses(self):
        from routes.agriculture import agriculture_bp
        from routes.crop_intelligence import crop_intelligence_bp
        app = Flask(__name__)
        app.secret_key = "test"
        app.register_blueprint(agriculture_bp, url_prefix="/api")
        app.register_blueprint(crop_intelligence_bp, url_prefix="/api")
        client = app.test_client()
        catalog_items = client.get("/api/crop-catalog").get_json()["items"]
        self.assertEqual(len(catalog_items), 188)
        self.assertEqual({item["knowledge_status"] for item in catalog_items}, {"LIMITED"})
        legacy_knowledge = client.get("/api/crop-knowledge").get_json()["items"]
        self.assertTrue(all(item["knowledge_status"] == "LIMITED" and "optimal_temperature_c" not in item for item in legacy_knowledge))
        with client.session_transaction() as session:
            session["user_id"] = 9
        with patch("routes.agriculture.get_user", return_value={"id": 9, "user_type": "farmer"}), \
             patch("routes.agriculture.create_user_crop", side_effect=lambda values: values):
            accepted = client.post("/api/crops", json={"crop_name": "toor", "latitude": 19, "longitude": 73, "growth_stage": "flowering"})
            ambiguous = client.post("/api/crops", json={"crop_name": "tori", "latitude": 19, "longitude": 73})
            self.assertEqual(accepted.status_code, 201)
            self.assertEqual(accepted.get_json()["crop_name"], "Pigeon Pea")
            self.assertEqual(accepted.get_json()["growth_stage"], "flowering")
            self.assertEqual(ambiguous.status_code, 400)
            self.assertEqual(len(ambiguous.get_json()["candidates"]), 2)

    def test_location_risk_checks_every_saved_crop_without_unverified_scores(self):
        from routes.weather import weather_bp
        app = Flask(__name__)
        app.secret_key = "test"
        app.register_blueprint(weather_bp, url_prefix="/api")
        client = app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = 3
        forecast = weather([90, 45, 10], humidity=96)
        crops = [
            {"id": 21, "crop_name": "Rice", "current_stage": "vegetative"},
            {"id": 22, "crop_name": "Tomato", "current_stage": "flowering"},
        ]
        limited_result = {
            "overall_risk": "WATCH", "risk_score": None, "knowledge_status": "LIMITED",
            "summary": "Verified crop thresholds are unavailable.", "alerts": [],
            "limitations": ["No verified crop-specific thresholds."], "evidence": [],
        }
        with patch("routes.weather.get_user", return_value={"id": 3, "location_consent_at": "consented"}), \
             patch("routes.weather.save_user_location"), \
             patch("routes.weather.forecast_weather", return_value=forecast), \
             patch("routes.weather.list_farms", return_value=[{"id": 4}]), \
             patch("routes.weather.list_fields", return_value=[{"id": 5}]), \
             patch("routes.weather.list_crops", return_value=crops), \
             patch("routes.weather.analyze_forecast", return_value=limited_result) as analyze, \
             patch("routes.weather.create_risk_prediction", side_effect=lambda value: value):
            response = client.post("/api/weather/risk", json={"latitude": 19, "longitude": 73})
        self.assertEqual(response.status_code, 200)
        risks = response.get_json()["risks"]
        self.assertEqual([item["crop"] for item in risks], ["Rice", "Tomato"])
        self.assertTrue(all(item["score"] is None and item["level"] == "WATCH" for item in risks))
        self.assertEqual([call.kwargs["weather"]["forecast"] for call in analyze.call_args_list], [forecast["forecast"][:2]] * 2)

    def test_location_risk_accepts_browser_fetched_forecast_for_serverless_weather(self):
        from routes.weather import weather_bp
        app = Flask(__name__)
        app.secret_key = "test"
        app.register_blueprint(weather_bp, url_prefix="/api")
        client = app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = 3
        browser_weather = {
            "provider": "open-meteo", "latitude": 19, "longitude": 73,
            "temperature": 30, "humidity": 70, "rainfall": 0, "wind_speed": 8,
            "forecast": [{"date": "2026-10-12", "rainfall": 64.5}, {"date": "2026-10-13", "rainfall": 12}],
        }
        with patch("routes.weather.get_user", return_value={"id": 3, "location_consent_at": "consented"}), \
             patch("routes.weather.save_user_location"), \
             patch("routes.weather.forecast_weather", side_effect=AssertionError("should use browser forecast")), \
             patch("routes.weather.list_farms", return_value=[]), \
             patch("routes.weather.analyze_forecast"):
            response = client.post("/api/weather/risk", json={"latitude": 19, "longitude": 73, "weather": browser_weather})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["weather"]["provider"], "open-meteo")
        self.assertEqual(len(response.get_json()["weather"]["forecast"]), 2)
        self.assertEqual(response.get_json()["weather_signals"][0]["category"], "heavy")

    def test_source_ingestion_requires_crop_metadata_and_preserves_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = {"crop_id": "rice", "region": "Odisha", "stage": "flowering", "risk_type": "high_humidity", "source": "Test advisory", "source_url": "https://example.org/advisory"}
            for filename, content in (("advisory.txt", "Plain text advisory."), ("table.csv", "stage,value\nflowering,wet\n"), ("record.json", '{"text":"JSON advisory."}'), ("guide.md", "# Markdown advisory"), ("guide.pdf", "placeholder")):
                (root / filename).write_text(content, encoding="utf-8")
                (root / f"{filename}.metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
            fake_pdf = SimpleNamespace(PdfReader=lambda _path: SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda: "Extracted PDF advisory.")]))
            with patch.dict(sys.modules, {"pypdf": fake_pdf}):
                records = load_source_documents(root)
            self.assertEqual(len(records), 5)
            self.assertTrue(all(item["crop_id"] == "rice" for item in records))
            self.assertEqual(next(item for item in records if item["source_file"] == "table.csv")["region"], "Odisha")
            sidecar = root / "advisory.txt.metadata.json"
            sidecar.write_text(json.dumps({"crop_id": "rice", "source_url": "not-a-url"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_source_documents(root)

    def test_scheme_entry_points_disclose_unknown_status_without_fabricated_deadlines(self):
        from routes.platform import platform_bp
        app = Flask(__name__)
        app.secret_key = "test"
        app.register_blueprint(platform_bp, url_prefix="/api")
        response = app.test_client().get("/api/schemes")
        self.assertEqual(response.status_code, 200)
        items = response.get_json()["items"]
        self.assertGreaterEqual(len(items), 5)
        pm_kisan = next(item for item in items if item["scheme_id"] == "pm-kisan")
        self.assertEqual(pm_kisan["verification_status"], "verified")
        self.assertTrue(all(item["application_status"] == "unknown" and item["deadline"] is None for item in items))

    def test_platform_personal_records_require_authentication(self):
        from routes.platform import platform_bp
        app = Flask(__name__)
        app.secret_key = "test"
        app.register_blueprint(platform_bp, url_prefix="/api")
        client = app.test_client()
        self.assertEqual(client.get("/api/tasks").status_code, 401)
        self.assertEqual(client.get("/api/farm/expenses").status_code, 401)
        self.assertEqual(client.get("/api/farm/actions/today").status_code, 401)
        self.assertEqual(client.post("/api/farm/actions/1/complete").status_code, 401)
        self.assertEqual(client.post("/api/disease-reports", json={}).status_code, 401)

    def test_official_source_monitor_rejects_unlisted_hosts_and_keys(self):
        from services.source_monitor import SOURCES
        self.assertTrue(all(url.startswith("https://") for url, _hosts in SOURCES.values()))
        with self.assertRaises(ValueError):
            from services.source_monitor import check_official_sources
            check_official_sources(["http://127.0.0.1/private"])

    def test_chat_language_must_be_supported(self):
        from routes.chat import chat_bp
        app = Flask(__name__)
        app.secret_key = "test"
        app.register_blueprint(chat_bp, url_prefix="/api")
        response = app.test_client().post("/api/chat", json={"message":"Hello", "language":"fr"})
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
