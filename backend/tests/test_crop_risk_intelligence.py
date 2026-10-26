import unittest
import json
import sys
import tempfile
from datetime import datetime, timedelta
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


def hourly_weather(temperatures, rainfall=0, stale=False):
    start = datetime(2026, 10, 15, 0)
    forecast = [
        {"time": (start + timedelta(hours=index)).isoformat(timespec="minutes"), "temperature": temperatures[index - 1] if 0 < index <= len(temperatures) else 25, "rainfall": rainfall, "humidity": 65, "wind_speed": 8}
        for index in range(49)
    ]
    return {"provider": "open-meteo", "latitude": 19.0, "longitude": 73.0, "forecast_issued_at": start.isoformat(timespec="minutes"), "retrieved_at": start.isoformat(), "stale": stale, "forecast": [{"date": "2026-10-15", "rainfall": 20, "temperature_max": max(temperatures or [25]), "temperature_min": 10}, {"date": "2026-10-16", "rainfall": 15, "temperature_max": 30, "temperature_min": 12}], "hourly_forecast": forecast}


def daily_weather(maximums, stale=False):
    start = datetime(2026, 10, 15)
    forecast = [{"date": (start + timedelta(days=index)).strftime("%Y-%m-%d"), "rainfall": 0,
                 "temperature_max": value, "temperature_min": 10} for index, value in enumerate(maximums)]
    return {"provider": "open-meteo", "latitude": 19.0, "longitude": 73.0, "timezone": "Asia/Kolkata",
            "forecast_issued_at": "2026-10-15T00:00", "stale": stale, "forecast": forecast}


def analyze_verified(crop_name, weather_data, growth_stage=None):
    return risk_engine.analyze_forecast(
        {"crop_name": crop_name, "latitude": 19.0, "longitude": 73.0, "state": "Maharashtra"},
        weather_data,
        get_document(crop_name),
        growth_stage,
        "Maharashtra",
    )


class CropRiskIntelligenceTests(unittest.TestCase):
    def test_requested_crop_aliases_resolve_to_canonical_ids(self):
        expected = {
            "aloo": "potato", "tamatar": "tomato", "paddy": "rice", "dhan": "rice",
            "gehu": "wheat", "palak": "spinach", "gajar": "carrot", "corn": "maize",
            "makka": "maize", "matar": "garden_pea", "chana": "chickpea", "masoor": "lentil",
            "gobi": "cauliflower", "pyaz": "onion", "karela": "bitter_gourd", "kela": "banana",
            "ragi": "finger_millet", "mandua": "finger_millet", "jowar": "sorghum",
            "soya": "soybean", "seb": "apple", "angur": "grapes", "rajma": "kidney_bean",
        }
        for alias, crop_id in expected.items():
            with self.subTest(alias=alias):
                crop, candidates = resolve_crop(alias)
                self.assertEqual(crop["crop_id"] if crop else None, crop_id, candidates)
        peas, candidates = resolve_crop("peas")
        self.assertIsNone(peas)
        self.assertEqual(set(candidates), {"Field Pea", "Garden Pea"})

    def test_missing_state_is_not_replaced_by_country(self):
        crop = {"crop_name": "potato", "country": "India", "latitude": 19, "longitude": 73}
        result = risk_engine.analyze_forecast(crop, hourly_weather([25] * 48), None, "tuberization")
        self.assertEqual(result["region"], "India")
        self.assertIsNone(result["location"].get("state"))
        self.assertTrue(any("Farm state is missing" in item for item in result["missing_inputs"]))
        heat = next(item for item in result["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(heat["outcome"], "INSUFFICIENT_DATA")
        self.assertIn("potato_tuberization_daily_tmin_at_or_above_20c_icar_cpri", heat["matched_rule_ids"])

    def test_outcome_contract_distinguishes_trigger_no_trigger_and_unsupported(self):
        above = risk_engine.analyze_forecast(
            {"crop_name": "rice", "latitude": 19, "longitude": 73, "state": "Maharashtra"},
            hourly_weather([36] * 48), None, "flowering", "Maharashtra",
        )
        heat = next(item for item in above["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(heat["outcome"], "ASSESSED/TRIGGERED")
        below = analyze_verified("rice", hourly_weather([25] * 48), "flowering")
        no_trigger = next(item for item in below["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(no_trigger["outcome"], "ASSESSED/NO_TRIGGER")
        unsupported = next(item for item in below["hazards"] if item["hazard"] == "DRY_SPELL")
        self.assertEqual(unsupported["outcome"], "UNSUPPORTED")

    def test_demo_forecast_is_not_scored_as_a_crop_risk_assessment(self):
        demo = hourly_weather([40] * 48)
        demo["provider"] = "demo"
        result = risk_engine.analyze_forecast(
            {"crop_name": "rice", "latitude": 19.0, "longitude": 73.0, "state": "Maharashtra"},
            demo, None, "flowering", "Maharashtra",
        )
        heat = next(item for item in result["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(heat["outcome"], "INSUFFICIENT_DATA")
        self.assertIsNone(result["risk_score"])
        self.assertEqual(result["alerts"], [])
        self.assertTrue(any("simulated demo" in item for item in result["missing_inputs"]))

    def test_model_interface_stays_unavailable_without_validated_exact_target(self):
        from services.agriculture.ml_prediction import predict_crop_hazard
        self.assertEqual(predict_crop_hazard("rice", "HEAT_STRESS", {})["status"], "MODEL_NOT_AVAILABLE")
        provisional = SimpleNamespace(version="0.1", supported_targets={("rice", "HEAT_STRESS")},
                                      validation_metadata={"validation_status": "provisional"},
                                      predict=lambda features: 0.9)
        self.assertEqual(predict_crop_hazard("rice", "HEAT_STRESS", {}, provisional)["status"], "MODEL_NOT_AVAILABLE")

    def test_provider_failure_without_cache_returns_structured_assessment(self):
        from services.crop_risk_service import run_crop_risk_analysis
        from services.weather.weather_service import WeatherProviderError
        crop = {"id": 91, "crop_name": "Spinach", "latitude": 19, "longitude": 73,
                "country": "India", "state": None, "growth_stage": None}
        with patch("services.crop_risk_service.get_user_crop", return_value=crop), \
             patch("services.crop_risk_service.get_weather", side_effect=WeatherProviderError(503, "Weather provider returned HTTP 503.")), \
             patch("services.crop_risk_service.retrieve", return_value=[]), \
             patch("services.crop_risk_service.latest_crop_risk", return_value=None), \
             patch("services.crop_risk_service.save_weather_snapshot"), \
             patch("services.crop_risk_service.save_crop_risk", return_value={"id": 92}):
            response = run_crop_risk_analysis(91, force=True)
        self.assertEqual(response["weather"]["provider_status"], "unavailable")
        self.assertEqual(response["weather"]["provider_http_status"], 503)
        self.assertEqual(response["risk"]["weather_observations"]["freshness_status"], "unavailable")
        self.assertTrue(any("Weather provider is unavailable" in item for item in response["risk"]["missing_inputs"]))
        self.assertTrue(all(item["outcome"] in {"INSUFFICIENT_DATA", "UNSUPPORTED"} for item in response["risk"]["hazards"]))

    def test_missing_region_is_explicit_for_india_scoped_rule(self):
        rule = next(rule for rule in risk_engine.load_verified_rules() if rule["crop_id"] == "wheat")
        reason = risk_engine._applicability_reason(rule, "grain filling", None)
        self.assertIn("state or region is missing", reason)
        self.assertIn("geographic applicability", reason)

    def test_rice_heuristic_heavy_rain_does_not_create_unverified_risk(self):
        result = analyze_verified("rice", weather([15, 85, 65], 88), "vegetative")
        self.assertEqual(result["overall_risk"], "UNAVAILABLE")
        self.assertIsNone(result["risk_score"])
        self.assertEqual(result["status"], "unavailable")

    def test_rice_vegetative_assessment_explains_each_excluded_heat_rule(self):
        result = risk_engine.analyze_forecast(
            {"crop_name": "Paddy", "latitude": 19, "longitude": 73, "state": "Maharashtra"},
            hourly_weather([25] * 48), get_document("rice"), "vegetative", "Maharashtra",
        )
        heat = next(item for item in result["hazards"] if item["hazard"] == "HEAT_STRESS")
        skipped = {item["rule_id"]: item["reason"] for item in heat["skipped_rules"]}
        self.assertEqual(result["crop_id"], "rice")
        self.assertEqual(result["growth_stage"], "vegetative")
        self.assertIn("rice_flowering_hourly_temperature_above_35c_icar_review", skipped)
        self.assertIn("Stage mismatch", skipped["rice_flowering_hourly_temperature_above_35c_icar_review"])
        self.assertIn("flowering", skipped["rice_flowering_hourly_temperature_above_35c_icar_review"])
        self.assertIn("rice_flowering_heat_exposure_35c_india_2019", skipped)
        self.assertIn("provisional", skipped["rice_flowering_heat_exposure_35c_india_2019"])
        self.assertIsNone(result["risk_score"])
        self.assertEqual(result["status"], "unavailable")

    def test_wheat_heuristic_heat_does_not_create_unverified_risk(self):
        result = analyze_verified("wheat", weather([0, 0], 45, 36), "grain filling")
        self.assertEqual(result["overall_risk"], "UNAVAILABLE")

    def test_tomato_humidity_is_not_called_a_disease_outbreak(self):
        result = analyze_verified("tomato", weather([20, 30], 90, 27), "flowering")
        self.assertEqual(result["overall_risk"], "UNAVAILABLE")
        self.assertFalse(result["alerts"])

    def test_legacy_waterlogging_and_cold_rules_are_not_used(self):
        wet = analyze_verified("potato", weather([70, 50], 60), "tuber development")
        cold_weather = weather([0], 55, 3)
        cold_weather["forecast"][0]["temperature_min"] = 0
        cold = analyze_verified("potato", cold_weather, "vegetative")
        self.assertEqual(wet["overall_risk"], "UNAVAILABLE")
        self.assertEqual(cold["overall_risk"], "UNAVAILABLE")

    def test_normal_weather_does_not_claim_low_crop_risk_without_rules(self):
        result = analyze_verified("rice", weather([0, 2], 55, 24), "vegetative")
        self.assertEqual(result["overall_risk"], "UNAVAILABLE")

    def test_missing_weather_is_explicitly_unavailable(self):
        result = analyze_verified("rice", {"forecast": []}, None)
        self.assertEqual(result["overall_risk"], "UNAVAILABLE")
        self.assertIn("No valid daily forecast", result["missing_inputs"][0])

    def test_missing_weather_and_unsupported_crop_have_distinct_heat_outcomes(self):
        missing = risk_engine.analyze_forecast(
            {"crop_name": "rice", "latitude": 19, "longitude": 73, "state": "Maharashtra"},
            {"provider": "open-meteo", "latitude": 19, "longitude": 73, "forecast": [], "hourly_forecast": []},
            None, "flowering", "Maharashtra",
        )
        unsupported = analyze_verified("carrot", hourly_weather([36] * 48), "vegetative")
        missing_heat = next(item for item in missing["hazards"] if item["hazard"] == "HEAT_STRESS")
        unsupported_heat = next(item for item in unsupported["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(missing_heat["outcome"], "INSUFFICIENT_DATA")
        self.assertEqual(unsupported_heat["outcome"], "UNSUPPORTED")
        self.assertEqual(missing["overall_risk"], "UNAVAILABLE")
        self.assertEqual(unsupported["overall_risk"], "UNAVAILABLE")
        self.assertIsNone(missing["risk_score"])
        self.assertIsNone(unsupported["risk_score"])
        self.assertNotIn("LOW", (missing["overall_risk"], unsupported["overall_risk"]))

    def test_daily_heat_hazard_evaluates_when_provider_has_no_rainfall_series(self):
        import json
        from services.weather import forecast_weather
        dates = [(datetime(2026, 10, 16) + timedelta(days=index)).date().isoformat() for index in range(5)]
        payload = {
            "current": {"time": "2026-10-15T10:00", "temperature_2m": 27},
            "daily": {"time": dates, "temperature_2m_max": [31, 32, 30, 33, 29], "temperature_2m_min": [20] * 5},
            "hourly": {"time": []},
        }
        response = type("Response", (), {"read": lambda self: json.dumps(payload).encode("utf-8"), "__enter__": lambda self: self, "__exit__": lambda self, *args: None})()
        with patch("services.weather.urlopen", return_value=response):
            forecast = forecast_weather(19, 73)
        self.assertEqual([day["date"] for day in forecast["forecast"]], dates)
        self.assertTrue(all(day["rainfall"] is None for day in forecast["forecast"]))
        result = risk_engine.analyze_forecast(
            {"crop_name": "wheat", "latitude": 19, "longitude": 73, "state": "Maharashtra"},
            forecast, get_document("wheat"), "grain filling", "Maharashtra",
        )
        heat = next(item for item in result["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(heat["status"], "assessed")
        self.assertEqual(heat["evaluation_status"], "trigger_detected")
        self.assertEqual([day["date"] for day in heat["triggered_rules"][0]["triggered_days"]], [dates[0], dates[1], dates[3]])
        self.assertIsNone(result["risk_score"])

    def test_weather_numbers_reject_boolean_and_numeric_strings(self):
        self.assertIsNone(risk_engine._finite(True))
        self.assertIsNone(risk_engine._finite("35"))
        self.assertEqual(risk_engine._finite(35), 35.0)

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
        expected = {"Paddy": "rice", "Dhan": "rice", "Gehu": "wheat", "Gehun": "wheat", "Arhar": "pigeon_pea", "Toor": "pigeon_pea", "Chana": "chickpea", "Bhindi": "okra", "Baingan": "brinjal", "Bajra": "pearl_millet", "Jowar": "sorghum", "Moong": "green_gram", "Urad": "black_gram", "Til": "sesame", "Alsi": "linseed", "Masoor Dal": "lentil", "Lentils": "lentil", "Palak": "spinach", "Gajar": "carrot", "Tamatar": "tomato", "Makka": "maize", "Matar": "garden_pea", "Gobi": "cauliflower", "Pyaz": "onion", "Aloo": "potato", "Karela": "bitter_gourd", "Kela": "banana", "Mandua": "finger_millet"}
        for alias, crop_id in expected.items():
            with self.subTest(alias=alias):
                crop, candidates = resolve_crop(f"  {alias.upper()}!! ")
                self.assertEqual(crop["crop_id"], crop_id)
                self.assertEqual(candidates, [crop["canonical_name"]])
        crop, candidates = resolve_crop("peas")
        self.assertIsNone(crop)
        self.assertEqual(candidates, ["Field Pea", "Garden Pea"])

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

    def test_limited_crop_is_unavailable_without_a_fabricated_watch(self):
        result = risk_engine.analyze_forecast({}, weather([80, 20], 95, 40, 60), None, None)
        self.assertEqual(result["overall_risk"], "UNAVAILABLE")
        self.assertIsNone(result["risk_score"])
        self.assertEqual(result["knowledge_status"], "LIMITED")

    def test_spinach_and_carrot_do_not_receive_unverified_or_borrowed_rules(self):
        for crop_name, stage in (("spinach", "vegetative"), ("carrot", "vegetative")):
            with self.subTest(crop=crop_name):
                result = analyze_verified(crop_name, hourly_weather([40] * 48), stage)
                heat = next(item for item in result["hazards"] if item["hazard"] == "HEAT_STRESS")
                self.assertEqual(result["status"], "unavailable")
                self.assertEqual(result["overall_risk"], "UNAVAILABLE")
                self.assertIsNone(result["risk_score"])
                self.assertEqual(result["alerts"], [])
                self.assertEqual(heat["status"], "unavailable")
                self.assertEqual(heat["outcome"], "UNSUPPORTED")
                if crop_name == "spinach":
                    self.assertTrue(any("provisional" in item["reason"] for item in heat["skipped_rules"]))

    def test_legacy_unverified_thresholds_cannot_create_a_score_or_alert(self):
        unverified = {"crop_id": "rice", "hazard_type": "HEAT_STRESS", "growth_stage": "flowering", "region": "India", "verification_status": "unverified", "source_url": "https://example.org/draft", "publication_title": "Unreviewed draft"}
        result = risk_engine.analyze_forecast({"crop_name": "rice"}, hourly_weather([48] * 48), get_document("rice"), "flowering", "India", [unverified])
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["risk_score"])
        self.assertEqual(result["alerts"], [])
        self.assertTrue(any("unverified" in item for item in result["limitations"]))
        self.assertEqual(result["weather_observations"]["forecast_rainfall_total_mm"], 35.0)
        self.assertEqual(result["weather_observations"]["peak_daily_rainfall_mm"], 20.0)

    def test_rice_heat_candidate_with_unverified_forecast_window_is_not_scored(self):
        temperatures = [36] + [30] * 47
        result = risk_engine.analyze_forecast({"crop_name": "Paddy", "latitude": 19, "longitude": 73, "state": "Maharashtra"}, hourly_weather(temperatures), get_document("rice"), "flowering", "Maharashtra")
        heat = next(item for item in result["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(heat["status"], "assessed")
        self.assertEqual(heat["evaluation_status"], "trigger_detected")
        self.assertEqual(heat["risk_index"], 2)
        self.assertEqual(heat["risk_index_details"]["exposed_observations"], 1)
        self.assertEqual(heat["risk_index_details"]["valid_observations"], 48)
        self.assertEqual(heat["triggered_rules"][0]["triggered_hours"][0]["temperature_c"], 36)
        self.assertTrue(any("not evidence of crop damage" in heat["explanation"] for _ in [0]))
        self.assertEqual(result["status"], "partially_assessed")
        self.assertIsNone(result["risk_score"])
        self.assertTrue(all(item["status"] == "unavailable" for item in result["hazards"] if item["hazard"] != "HEAT_STRESS"))

    def test_rice_flowering_rule_requires_stage_and_complete_hourly_forecast(self):
        crop = {"crop_name": "rice", "latitude": 19, "longitude": 73, "state": "Maharashtra"}
        no_stage = risk_engine.analyze_forecast(crop, hourly_weather([40] * 48), None, None, "Maharashtra")
        no_stage_heat = next(item for item in no_stage["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(no_stage_heat["status"], "unavailable")
        self.assertEqual(no_stage_heat["evaluation_status"], "insufficient_data")
        partial_hourly = hourly_weather([40] * 48)
        partial_hourly["hourly_forecast"][5]["temperature"] = None
        no_weather = risk_engine.analyze_forecast(crop, partial_hourly, None, "flowering", "Maharashtra")
        self.assertEqual(next(item for item in no_weather["hazards"] if item["hazard"] == "HEAT_STRESS")["status"], "unavailable")
        no_location = risk_engine.analyze_forecast({"crop_name": "rice", "state": "Maharashtra"}, hourly_weather([40] * 48), None, "flowering", "Maharashtra")
        self.assertEqual(next(item for item in no_location["hazards"] if item["hazard"] == "HEAT_STRESS")["status"], "unavailable")
        stale_weather = hourly_weather([40] * 48, stale=True)
        stale_result = risk_engine.analyze_forecast(crop, stale_weather, None, "flowering", "Maharashtra")
        self.assertEqual(next(item for item in stale_result["hazards"] if item["hazard"] == "HEAT_STRESS")["status"], "unavailable")
        no_forecast_coordinates = hourly_weather([40] * 48)
        no_forecast_coordinates.pop("latitude")
        no_forecast_coordinates.pop("longitude")
        coordinate_result = risk_engine.analyze_forecast(crop, no_forecast_coordinates, None, "flowering", "Maharashtra")
        coordinate_heat = next(item for item in coordinate_result["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(coordinate_heat["evaluation_status"], "insufficient_data")
        self.assertTrue(any(source.get("source_validation_status") == "verified" for source in coordinate_heat["sources"]))

    def test_browser_forecast_rejects_explicit_stale_cache(self):
        from routes.weather import _browser_forecast
        payload = hourly_weather([25] * 48)
        payload.update({"provider": "open-meteo", "latitude": 19, "longitude": 73, "stale": True, "cache": "stale_fallback"})
        self.assertIsNone(_browser_forecast(payload, 19, 73))

    def test_hazards_expose_requested_four_state_outcomes(self):
        result = risk_engine.analyze_forecast(
            {"crop_name": "wheat", "latitude": 19, "longitude": 73, "state": "Haryana"},
            daily_weather([29, 29, 29, 29, 29]), None, "grain filling", "Haryana",
        )
        heat = next(item for item in result["hazards"] if item["hazard"] == "HEAT_STRESS")
        unsupported = next(item for item in result["hazards"] if item["hazard"] == "COLD_FROST")
        self.assertEqual(heat["outcome"], "ASSESSED/NO_TRIGGER")
        self.assertEqual(unsupported["outcome"], "UNSUPPORTED")

    def test_hazard_results_expose_machine_readable_evaluation_status(self):
        result = risk_engine.analyze_forecast(
            {"crop_name": "Rice", "latitude": 19, "longitude": 73, "state": "Maharashtra"},
            hourly_weather([25] * 48), get_document("rice"), "flowering", "Maharashtra",
        )
        heat = next(item for item in result["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(heat["evaluation_status"], "no_trigger_detected")
        self.assertNotIn("rice_flowering_heat_exposure_35c_india_2019", heat["matched_rule_ids"])
        self.assertTrue(any(source.get("source_validation_status") for source in heat["sources"]))
        dry_spell = next(item for item in result["hazards"] if item["hazard"] == "DRY_SPELL")
        self.assertEqual(dry_spell["evaluation_status"], "no_applicable_rule")

    def test_hourly_evaluator_supports_weather_fields_operators_and_unit_conversion(self):
        observations = [{"time": f"2026-10-15T{hour:02d}:00", "temperature_c": 20, "humidity_percent": 70,
                        "rainfall_mm": 0, "wind_speed_kmh": 36} for hour in range(24)]
        summary = {"stale": False, "hourly_observations": observations}
        cases = [
            ({"weather_parameter": "temperature_2m", "unit": "F", "threshold": 68, "operator": "lte"}, 24),
            ({"weather_parameter": "relative_humidity_2m", "unit": "%", "threshold": 70, "operator": "gte"}, 24),
            ({"weather_parameter": "precipitation", "unit": "mm", "threshold": 0, "operator": "lte"}, 24),
            ({"weather_parameter": "wind_speed_10m", "unit": "m/s", "threshold": 10, "operator": "gte"}, 24),
        ]
        for rule, expected in cases:
            with self.subTest(parameter=rule["weather_parameter"]):
                result, reason = risk_engine._evaluate_rule({"evaluator": "hourly_threshold_exposure", "window_hours": 24, "index_bands": [{"minimum": 0, "maximum": 100, "label": "SYNTHETIC_TEST"}], **rule}, summary)
                self.assertIsNone(reason)
                self.assertEqual(result["exposed_hours"], expected)
                self.assertEqual(result["forecast_hours"], 24)

    def test_hourly_evaluator_reports_missing_parameter_and_invalid_window(self):
        summary = {"stale": False, "hourly_observations": [{"time": f"2026-10-15T{hour:02d}:00", "temperature_c": 20} for hour in range(48)]}
        base = {"evaluator": "hourly_threshold_exposure", "weather_parameter": "relative_humidity_2m", "unit": "%", "threshold": 80, "operator": "gt"}
        result, reason = risk_engine._evaluate_rule(base, summary)
        self.assertIsNone(result)
        self.assertIn("incomplete", reason)
        result, reason = risk_engine._evaluate_rule({**base, "window_hours": 0}, summary)
        self.assertIsNone(result)
        self.assertIn("window", reason)

    def test_forecast_hour_filter_uses_timezone_aware_timestamps_and_deduplicates(self):
        start = datetime.fromisoformat("2026-10-15T00:00:00+05:30")
        hourly = [{"time": (start + timedelta(hours=index)).isoformat(), "temperature": 25, "rainfall": 0, "humidity": 60, "wind_speed": 5} for index in range(49)]
        hourly.append({"time": "2026-10-14T19:30:00Z", "temperature": 99, "rainfall": 0, "humidity": 60, "wind_speed": 5})
        summary = risk_engine._weather_summary({"timezone": "Asia/Kolkata", "forecast_issued_at": "2026-10-15T00:00:00+05:30", "hourly_forecast": hourly})
        self.assertEqual(summary["next_48h_hour_count"], 48)
        self.assertEqual(summary["hourly_observations"][0]["time"], "2026-10-15T01:00:00+05:30")

    def test_coverage_endpoint_reports_real_registry_rules_and_scope(self):
        from routes.crop_intelligence import crop_intelligence_bp
        app = Flask(__name__)
        app.register_blueprint(crop_intelligence_bp, url_prefix="/api")
        response = app.test_client().get("/api/crop-risk-coverage?crop=paddy&state=Maharashtra&stage=flowering")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["verified_rule_count"], 3)
        self.assertEqual(payload["verified_executable_rule_count"], 3)
        self.assertEqual(payload["verified_non_executable_rule_count"], 0)
        self.assertEqual(payload["provisional_rule_count"], 9)
        self.assertEqual(payload["invalid_or_mismatched_citation_rule_count"], 1)
        self.assertEqual(payload["unverified_citation_rule_count"], 0)
        self.assertEqual(payload["incomplete_evidence_rule_count"], 8)
        self.assertEqual({item["hazard"] for item in payload["unavailable_hazards"]}, {"EXCESS_RAINFALL", "COLD_FROST", "DRY_SPELL", "DISEASE_FAVOURABLE_WEATHER", "SEVERE_WEATHER"})
        self.assertEqual(payload["crops"][0]["crop_id"], "rice")
        self.assertEqual(payload["applicable_rule_ids"], ["rice_flowering_hourly_temperature_above_35c_icar_review"])

        potato_scope = app.test_client().get("/api/crop-risk-coverage?crop=potato&state=Maharashtra&stage=tuberization").get_json()
        self.assertEqual(potato_scope["applicable_rule_ids"], ["potato_tuberization_daily_tmin_at_or_above_20c_icar_cpri"])
        outside_scope = app.test_client().get("/api/crop-risk-coverage?crop=potato&state=Nepal&stage=tuberization").get_json()
        self.assertEqual(outside_scope["applicable_rule_ids"], [])

    def test_coverage_excludes_verified_records_with_unexecutable_fields(self):
        from services.agriculture.crop_risk_coverage import _execution_issues
        rule = next(rule for rule in risk_engine.load_rule_records() if rule["rule_id"] == "rice_flowering_heat_exposure_35c_india_2019")
        self.assertTrue(any("source evidence is not verified" in issue for issue in _execution_issues(rule)))
        verified = {**rule, "verification_status": "verified", "source_validation_status": "verified"}
        self.assertEqual(_execution_issues(verified), [])
        malformed = {**verified, "weather_parameter": "soil_moisture", "evaluator": "soil_water_deficit"}
        self.assertIn("unsupported forecast variable soil_moisture", _execution_issues(malformed))
        self.assertIn("unsupported evaluator soil_water_deficit", _execution_issues(malformed))

    def test_kalp_wheat_rule_is_verified_and_coverage_executable(self):
        from services.agriculture.crop_risk_coverage import _execution_issues
        rule = next(rule for rule in risk_engine.load_verified_rules() if rule["rule_id"] == "wheat_grain_filling_daily_tmax_above_30c_imd_kalp")
        self.assertEqual(rule["source_validation_status"], "verified")
        self.assertEqual(rule["threshold"], 30)
        self.assertEqual(rule["operator"], "gt")
        self.assertEqual(rule["forecast_window_days"], 5)
        self.assertEqual(_execution_issues(rule), [])

    def test_kalp_wheat_daily_tmax_indicator_flags_only_strictly_above_threshold_without_score(self):
        result = risk_engine.analyze_forecast(
            {"crop_name": "Wheat", "latitude": 19, "longitude": 73, "state": "Haryana"}, daily_weather([30, 30.1, 29, 30, 31]),
            None, "grain filling",
        )
        heat = next(item for item in result["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(heat["status"], "assessed")
        self.assertEqual(heat["assessment_type"], "deterministic_exposure_indicator")
        self.assertEqual(heat["evaluation_status"], "trigger_detected")
        self.assertEqual([day["date"] for day in heat["triggered_rules"][0]["triggered_days"]], ["2026-10-16", "2026-10-19"])
        self.assertEqual(heat["risk_index"], 40)
        self.assertEqual(heat["risk_index_details"]["observation_unit"], "daily Tmax forecasts")
        self.assertEqual(heat["risk_index_details"]["exposed_observations"], 2)
        self.assertEqual(heat["risk_index_details"]["valid_observations"], 5)
        self.assertEqual(heat["risk_index_details"]["window_start"], "2026-10-15")
        self.assertEqual(heat["risk_index_details"]["window_end"], "2026-10-19")
        self.assertIsNone(result["risk_score"])
        self.assertEqual(result["overall_risk"], "PARTIAL")
        self.assertEqual(result["status"], "partially_assessed")
        self.assertEqual(len(result["alerts"]), 1)
        self.assertEqual(result["alerts"][0]["expected_time"], "2026-10-16")
        self.assertEqual(result["alerts"][0]["severity"], "WATCH")
        self.assertIn("not a probability", heat["explanation"])

    def test_kalp_daily_tmax_equal_to_30_is_not_a_trigger(self):
        result = risk_engine.analyze_forecast(
            {"crop_name": "Wheat", "latitude": 19, "longitude": 73, "state": "Haryana"}, daily_weather([30] * 5),
            None, "grain fill",
        )
        heat = next(item for item in result["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(heat["status"], "assessed")
        self.assertEqual(heat["evaluation_status"], "no_trigger_detected")
        self.assertEqual(heat["triggered_rules"], [])
        self.assertEqual(heat["risk_index"], 0)
        self.assertIsNone(result["risk_score"])

    def test_kalp_indicator_requires_five_consecutive_complete_days_and_current_forecast(self):
        crop = {"crop_name": "Wheat", "latitude": 19, "longitude": 73, "state": "Haryana"}
        short = risk_engine.analyze_forecast(crop, daily_weather([32] * 4), None, "grain filling")
        heat = next(item for item in short["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(heat["status"], "unavailable")
        self.assertIn("needs 5 daily", heat["explanation"])

        missing_value = daily_weather([32, 31, None, 32, 29])
        missing = risk_engine.analyze_forecast(crop, missing_value, None, "grain filling")
        self.assertIn("incomplete", next(item for item in missing["hazards"] if item["hazard"] == "HEAT_STRESS")["explanation"])

        gap = daily_weather([32] * 5)
        gap["forecast"][2]["date"] = "2026-10-18"
        nonconsecutive = risk_engine.analyze_forecast(crop, gap, None, "grain filling")
        self.assertIn("not consecutive", next(item for item in nonconsecutive["hazards"] if item["hazard"] == "HEAT_STRESS")["explanation"])

        stale = risk_engine.analyze_forecast(crop, daily_weather([32] * 5, stale=True), None, "grain filling")
        self.assertIn("stale", next(item for item in stale["hazards"] if item["hazard"] == "HEAT_STRESS")["explanation"])

    def test_kalp_rule_requires_wheat_grain_filling_stage(self):
        result = risk_engine.analyze_forecast(
            {"crop_name": "Wheat", "latitude": 19, "longitude": 73}, daily_weather([35] * 5), None, "vegetative",
        )
        heat = next(item for item in result["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(heat["status"], "unavailable")
        self.assertEqual(heat["evaluation_status"], "insufficient_data")

    def test_potato_tuberization_daily_tmin_indicator_boundary_missing_stage_and_region(self):
        crop = {"crop_name": "Potato", "latitude": 19, "longitude": 73, "state": "Maharashtra"}
        weather_data = daily_weather([25, 25, 25])
        weather_data["forecast"][1]["temperature_min"] = 20
        weather_data["forecast"][2]["temperature_min"] = 19
        result = risk_engine.analyze_forecast(crop, weather_data, None, "tuberization", "Maharashtra")
        heat = next(item for item in result["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(heat["evaluation_status"], "trigger_detected")
        self.assertEqual(heat["assessment_type"], "deterministic_exposure_indicator")
        self.assertEqual(heat["risk_index"], 50)
        self.assertEqual(heat["risk_index_details"]["observation_unit"], "daily Tmin forecasts")
        self.assertEqual(heat["risk_index_details"]["exposed_observations"], 1)
        self.assertEqual(heat["risk_index_details"]["valid_observations"], 2)
        self.assertEqual(heat["risk_index_details"]["window_start"], "2026-10-16")
        self.assertEqual(heat["risk_index_details"]["window_end"], "2026-10-17")
        self.assertEqual(heat["triggered_rules"][0]["triggered_days"][0]["temperature_min_c"], 20)
        self.assertIn("does not establish crop damage", heat["explanation"])

        weather_data["forecast"][1]["temperature_min"] = 19.9
        no_trigger = risk_engine.analyze_forecast(crop, weather_data, None, "tuber initiation", "Maharashtra")
        no_trigger_heat = next(item for item in no_trigger["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(no_trigger_heat["evaluation_status"], "no_trigger_detected")
        self.assertEqual(no_trigger_heat["risk_index"], 0)

        weather_data["forecast"][1]["temperature_min"] = None
        insufficient = risk_engine.analyze_forecast(crop, weather_data, None, "tuberization", "Maharashtra")
        insufficient_heat = next(item for item in insufficient["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(insufficient_heat["evaluation_status"], "insufficient_data")
        self.assertIsNone(insufficient_heat["risk_index"])

        wrong_stage = risk_engine.analyze_forecast(crop, weather_data, None, "vegetative", "Maharashtra")
        self.assertEqual(next(item for item in wrong_stage["hazards"] if item["hazard"] == "HEAT_STRESS")["evaluation_status"], "no_applicable_rule")
        wrong_region = risk_engine.analyze_forecast({**crop, "state": "Nepal"}, weather_data, None, "tuberization", "Nepal")
        self.assertEqual(next(item for item in wrong_region["hazards"] if item["hazard"] == "HEAT_STRESS")["evaluation_status"], "no_applicable_rule")

    def test_rule_window_exposure_index_endpoints_and_no_cross_hazard_aggregate(self):
        rice_crop = {"crop_name": "Rice", "latitude": 19, "longitude": 73, "state": "Maharashtra"}
        rice = risk_engine.analyze_forecast(rice_crop, hourly_weather([36] * 48), None, "flowering", "Maharashtra")
        rice_heat = next(item for item in rice["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(rice_heat["risk_index"], 100)
        self.assertEqual(rice_heat["risk_index_details"]["exposed_observations"], 48)
        self.assertIsNone(rice["risk_score"])

        wheat_crop = {"crop_name": "Wheat", "latitude": 19, "longitude": 73, "state": "Haryana"}
        wheat = risk_engine.analyze_forecast(wheat_crop, daily_weather([31] * 5), None, "grain filling", "Haryana")
        wheat_heat = next(item for item in wheat["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(wheat_heat["risk_index"], 100)
        self.assertIsNone(wheat["risk_score"])

        potato_crop = {"crop_name": "Potato", "latitude": 19, "longitude": 73, "state": "Maharashtra"}
        potato_weather = daily_weather([25, 25, 25])
        potato_weather["forecast"][1]["temperature_min"] = 20
        potato_weather["forecast"][2]["temperature_min"] = 20
        potato = risk_engine.analyze_forecast(potato_crop, potato_weather, None, "tuberization", "Maharashtra")
        potato_heat = next(item for item in potato["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(potato_heat["risk_index"], 100)
        self.assertIsNone(potato["risk_score"])

    def test_rule_window_index_formula_zero_valid_and_observation_metadata(self):
        self.assertEqual(risk_engine._weather_exposure_index(0, 8, "daily samples")["risk_index"], 0)
        self.assertEqual(risk_engine._weather_exposure_index(8, 8, "daily samples")["risk_index"], 100)
        half_tie = risk_engine._weather_exposure_index(1, 8, "daily samples", "2026-01-01", "2026-01-08")
        self.assertEqual(half_tie["risk_index"], 13)  # 12.5 rounds half up, not to even.
        self.assertEqual(half_tie["risk_index_details"]["exposed_observations"], 1)
        self.assertEqual(half_tie["risk_index_details"]["valid_observations"], 8)
        self.assertEqual(half_tie["risk_index_details"]["observation_unit"], "daily samples")
        self.assertEqual(half_tie["risk_index_details"]["window_start"], "2026-01-01")
        self.assertEqual(half_tie["risk_index_details"]["window_end"], "2026-01-08")
        empty = risk_engine._weather_exposure_index(0, 0, "daily samples")
        self.assertIsNone(empty["risk_index"])

    def test_incomplete_rule_window_has_no_index_and_multiple_rule_indices_stay_separate(self):
        crop = {"crop_name": "Wheat", "latitude": 19, "longitude": 73, "state": "Haryana"}
        incomplete = risk_engine.analyze_forecast(crop, daily_weather([32, 31, None, 32, 29]), None, "grain filling")
        incomplete_heat = next(item for item in incomplete["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(incomplete_heat["evaluation_status"], "insufficient_data")
        self.assertIsNone(incomplete_heat["risk_index"])

        base = next(rule for rule in risk_engine.load_verified_rules()
                    if rule["rule_id"] == "wheat_grain_filling_daily_tmax_above_30c_imd_kalp")
        second = {**base, "rule_id": "synthetic_test_wheat_second_rule", "threshold": 31.5}
        result = risk_engine.analyze_forecast(
            crop, daily_weather([32, 31.5, 30, 29, 28]), None, "grain filling",
            verified_rules=[base, second],
        )
        heat = next(item for item in result["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual([item["rule_id"] for item in heat["rule_assessments"]], [base["rule_id"], second["rule_id"]])
        self.assertEqual([item["risk_index"] for item in heat["rule_assessments"]], [40, 20])
        self.assertEqual([item["risk_index_details"]["exposed_observations"] for item in heat["rule_assessments"]], [2, 1])
        self.assertEqual([item["risk_index_details"]["valid_observations"] for item in heat["rule_assessments"]], [5, 5])
        self.assertEqual([item["window_start"] for item in heat["rule_assessments"]], ["2026-10-15"] * 2)
        self.assertEqual([item["window_end"] for item in heat["rule_assessments"]], ["2026-10-19"] * 2)
        self.assertIsNone(heat["risk_index"])
        self.assertIsNone(result["risk_score"])

    def test_rule_applicability_requires_audited_source_and_matches_stage_region(self):
        rule = {
            "crop_id": "wheat", "verification_status": "verified", "source_validation_status": "verified",
            "source_url": "https://example.org/evidence", "publication_title": "Synthetic test evidence",
            "growth_stage": ["grain filling"], "region": ["Haryana", "Punjab"],
        }
        self.assertTrue(risk_engine._applicable(rule, "wheat", "grain fill", "Haryana"))
        self.assertFalse(risk_engine._applicable(rule, "wheat", "vegetative", "Haryana"))
        self.assertFalse(risk_engine._applicable(rule, "wheat", "grain filling", "Maharashtra"))
        self.assertFalse(risk_engine._applicable({**rule, "source_validation_status": "incomplete_evidence"}, "wheat", "grain filling", "Haryana"))

    def test_requested_crop_heat_rules_match_supported_stages_and_return_partial_scores(self):
        samples = [
            ("potato", "tuber initiation", 24), ("tomato", "flowering", 36),
            ("onion", "vegetative", 43), ("wheat", "grain filling", 35),
            ("lentil", "flowering", 31), ("field pea", "flowering", 33),
            ("garden pea", "fruiting", 33), ("spinach", "vegetative", 36),
        ]
        for crop_name, stage, temperature in samples:
            with self.subTest(crop=crop_name, stage=stage):
                state = "Haryana" if crop_name == "wheat" else "Maharashtra"
                weather_payload = hourly_weather([temperature] * 48)
                if crop_name == "potato":
                    weather_payload["forecast"].append({"date": "2026-10-17", "rainfall": 0, "temperature_max": 25, "temperature_min": 12})
                result = risk_engine.analyze_forecast(
                    {"crop_name": crop_name, "latitude": 19, "longitude": 73, "state": state},
                    weather_payload, None, stage, state,
                )
                heat = next(item for item in result["hazards"] if item["hazard"] == "HEAT_STRESS")
                self.assertEqual(heat["status"], "assessed" if crop_name == "potato" else "unavailable")
                if crop_name == "potato":
                    self.assertEqual(heat["risk_index"], 0)
                else:
                    self.assertIsNone(heat["risk_index"])
                self.assertTrue(heat["sources"][0]["source_url"].startswith("https://"))
                self.assertEqual(result["status"], "partially_assessed" if crop_name == "potato" and temperature >= 20 else "unavailable")
                self.assertIsNone(result["risk_score"])

    def test_potato_daily_tmin_condition_requires_tuber_stage(self):
        crop = {"crop_name": "potato", "latitude": 19, "longitude": 73, "state": "Maharashtra"}
        weather_data = hourly_weather([22] * 48)
        weather_data["forecast"].append({"date": "2026-10-17", "rainfall": 0, "temperature_max": 25, "temperature_min": 12})
        result = risk_engine.analyze_forecast(crop, weather_data, None, "tuber initiation", "Maharashtra")
        heat = next(item for item in result["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(heat["status"], "assessed")
        self.assertEqual(heat["risk_index"], 0)
        wrong_stage = risk_engine.analyze_forecast(crop, weather_data, None, "vegetative", "Maharashtra")
        self.assertEqual(next(item for item in wrong_stage["hazards"] if item["hazard"] == "HEAT_STRESS")["status"], "unavailable")

    def test_national_rule_requires_explicit_india_context_but_regional_wheat_needs_state(self):
        location = {"latitude": 19, "longitude": 73}
        potato_weather = hourly_weather([23] * 48)
        potato_weather["forecast"].append({"date": "2026-10-17", "rainfall": 0, "temperature_max": 25, "temperature_min": 12})
        potato = risk_engine.analyze_forecast({**location, "crop_name": "potato", "country": "India"}, potato_weather, None, "tuberization")
        potato_heat = next(item for item in potato["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(potato_heat["status"], "assessed")
        self.assertEqual(potato_heat["risk_index"], 0)
        no_country = risk_engine.analyze_forecast({**location, "crop_name": "potato"}, potato_weather, None, "tuberization")
        self.assertEqual(next(item for item in no_country["hazards"] if item["hazard"] == "HEAT_STRESS")["status"], "unavailable")
        wheat = risk_engine.analyze_forecast({**location, "crop_name": "wheat"}, hourly_weather([36] * 48), None, "grain filling")
        heat = next(item for item in wheat["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(heat["status"], "unavailable")
        self.assertIsNone(heat["risk_index"])

    def test_verified_rule_registry_fields_and_provenance_are_complete(self):
        rule = next(rule for rule in risk_engine.load_rule_records() if rule.get("rule_id") == "rice_flowering_heat_exposure_35c_india_2019")
        required = json.loads(risk_engine.RULE_REGISTRY.read_text(encoding="utf-8"))["required_rule_fields"]
        self.assertTrue(all(rule.get(field) is not None for field in required))
        self.assertTrue(rule["source_url"].startswith("https://epubs.icar.org.in/"))
        self.assertEqual(rule["threshold"], 35)
        self.assertEqual(rule["unit"], "deg C")
        self.assertEqual(rule["verification_status"], "provisional")
        self.assertEqual(rule["source_validation_status"], "incomplete_evidence")
        self.assertEqual({rule["rule_id"] for rule in risk_engine.load_verified_rules()}, {
            "wheat_grain_filling_daily_tmax_above_30c_imd_kalp",
            "potato_tuberization_daily_tmin_at_or_above_20c_icar_cpri",
            "rice_flowering_hourly_temperature_above_35c_icar_review",
        })

    def test_rice_flowering_heat_indicator_strict_boundary_and_missing_window(self):
        crop = {"crop_name": "rice", "latitude": 19, "longitude": 73, "state": "Maharashtra"}
        exact = risk_engine.analyze_forecast(crop, hourly_weather([35] * 48), None, "anthesis", "Maharashtra")
        exact_heat = next(item for item in exact["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(exact_heat["evaluation_status"], "no_trigger_detected")
        self.assertEqual(exact_heat["risk_index"], 0)
        above = risk_engine.analyze_forecast(crop, hourly_weather([35, 35.1] + [30] * 46), None, "flowering", "Maharashtra")
        above_heat = next(item for item in above["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(above_heat["evaluation_status"], "trigger_detected")
        self.assertEqual([item["temperature_c"] for item in above_heat["triggered_rules"][0]["triggered_hours"]], [35.1])
        short = hourly_weather([36] * 10)
        short["hourly_forecast"] = short["hourly_forecast"][:10]
        unavailable = risk_engine.analyze_forecast(crop, short, None, "flowering", "Maharashtra")
        self.assertEqual(next(item for item in unavailable["hazards"] if item["hazard"] == "HEAT_STRESS")["evaluation_status"], "insufficient_data")
        wrong_crop = risk_engine.analyze_forecast({**crop, "crop_name": "wheat"}, hourly_weather([40] * 48), None, "flowering", "Maharashtra")
        self.assertEqual(next(item for item in wrong_crop["hazards"] if item["hazard"] == "HEAT_STRESS")["status"], "unavailable")
        wrong_stage = risk_engine.analyze_forecast(crop, hourly_weather([40] * 48), None, "vegetative", "Maharashtra")
        self.assertEqual(next(item for item in wrong_stage["hazards"] if item["hazard"] == "HEAT_STRESS")["status"], "unavailable")
        outside_region = risk_engine.analyze_forecast({**crop, "state": "Nepal"}, hourly_weather([40] * 48), None, "flowering", "Nepal")
        self.assertEqual(next(item for item in outside_region["hazards"] if item["hazard"] == "HEAT_STRESS")["status"], "unavailable")

    def test_rice_hourly_condition_rejects_gaps_duplicates_and_bad_timestamps(self):
        crop = {"crop_name": "rice", "latitude": 19, "longitude": 73, "state": "Maharashtra"}
        def assessment(data):
            return next(item for item in risk_engine.analyze_forecast(crop, data, None, "flowering", "Maharashtra")["hazards"] if item["hazard"] == "HEAT_STRESS")

        gap = hourly_weather([36] * 49)
        gap["hourly_forecast"].pop(12)
        self.assertEqual(assessment(gap)["evaluation_status"], "insufficient_data")
        self.assertIn("48 hourly forecast observations", assessment(gap)["explanation"])

        duplicate = hourly_weather([36] * 48)
        duplicate["hourly_forecast"].append(dict(duplicate["hourly_forecast"][8]))
        duplicate_result = assessment(duplicate)
        self.assertEqual(duplicate_result["evaluation_status"], "insufficient_data")
        self.assertIn("duplicate", duplicate_result["explanation"])

        malformed_time = hourly_weather([36] * 49)
        malformed_time["hourly_forecast"][8]["time"] = "not-an-iso-timestamp"
        malformed_result = assessment(malformed_time)
        self.assertEqual(malformed_result["evaluation_status"], "insufficient_data")
        self.assertIn("malformed timestamp", malformed_result["explanation"])

    def test_rice_hourly_condition_rejects_malformed_temperature_values(self):
        crop = {"crop_name": "rice", "latitude": 19, "longitude": 73, "state": "Maharashtra"}
        for bad_value in (None, "not-a-number", "36.0", float("nan"), 1000, True):
            with self.subTest(value=bad_value):
                data = hourly_weather([36] * 48)
                data["hourly_forecast"][5]["temperature"] = bad_value
                result = risk_engine.analyze_forecast(crop, data, None, "flowering", "Maharashtra")
                heat = next(item for item in result["hazards"] if item["hazard"] == "HEAT_STRESS")
                self.assertEqual(heat["status"], "unavailable")
                self.assertEqual(heat["evaluation_status"], "insufficient_data")
                self.assertFalse(heat["triggered_rules"])

    def test_rice_hourly_condition_uses_timezone_aware_consecutive_instants(self):
        from zoneinfo import ZoneInfo
        timezone_aware = ZoneInfo("Asia/Kolkata")
        reference = datetime.fromisoformat("2026-10-15T23:00:00+05:30")
        hourly = [{
            "time": (reference + timedelta(hours=index)).isoformat(timespec="minutes"),
            "temperature": 36 if index == 1 else 30, "rainfall": 0, "humidity": 65, "wind_speed": 8,
        } for index in range(49)]
        data = hourly_weather([30] * 48)
        data.update({"timezone": "Asia/Kolkata", "forecast_issued_at": reference.isoformat(timespec="minutes"), "hourly_forecast": hourly})
        crop = {"crop_name": "rice", "latitude": 19, "longitude": 73, "state": "Maharashtra"}
        result = risk_engine.analyze_forecast(crop, data, None, "anthesis", "Maharashtra")
        heat = next(item for item in result["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(heat["evaluation_status"], "trigger_detected")
        rule = heat["triggered_rules"][0]
        self.assertEqual(rule["forecast_timezone"], "Asia/Kolkata")
        self.assertEqual(rule["triggered_hours"][0]["time"], "2026-10-16T00:00+05:30")
        self.assertEqual(rule["window_start"], "2026-10-16T00:00+05:30")
        self.assertEqual((reference + timedelta(hours=1)).astimezone(timezone_aware).date().isoformat(), "2026-10-16")

    def test_rice_flowering_indicator_is_executable_in_weather_risk_api(self):
        from routes.weather import weather_bp
        app = Flask(__name__)
        app.secret_key = "test"
        app.register_blueprint(weather_bp, url_prefix="/api")
        client = app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = 3
        payload_weather = hourly_weather([35] * 6 + [36] + [30] * 41)
        payload_weather.update({"provider": "open-meteo", "latitude": 19, "longitude": 73, "timezone": "Asia/Kolkata"})
        with patch("routes.weather.get_user", return_value={"id": 3, "location_consent_at": "consented"}), \
             patch("routes.weather.save_user_location"), \
             patch("routes.weather.list_farms", return_value=[{"id": 4, "state": "Maharashtra", "district": "Pune"}]), \
             patch("routes.weather.list_fields", return_value=[{"id": 5, "soil_type": "loam", "drainage_condition": "good"}]), \
             patch("routes.weather.list_crops", return_value=[{"id": 6, "crop_name": "Paddy", "current_stage": "flowering"}]), \
             patch("routes.weather.analyze_forecast", wraps=risk_engine.analyze_forecast) as analyze, \
             patch("routes.weather.create_risk_prediction") as prediction:
            response = client.post("/api/weather/risk", json={"latitude": 19, "longitude": 73, "weather": payload_weather})
        self.assertEqual(response.status_code, 200, response.get_json())
        risk = response.get_json()["risks"][0]
        heat = next(item for item in risk["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(heat["evaluation_status"], "trigger_detected")
        self.assertEqual(heat["risk_index"], 2)
        self.assertEqual(heat["triggered_rules"][0]["forecast_timezone"], "Asia/Kolkata")
        self.assertEqual(risk["status"], "partially_assessed")
        self.assertIsNone(risk["score"])
        crop_context = analyze.call_args.kwargs["crop"]
        self.assertEqual(crop_context["crop_name"], "Paddy")
        self.assertEqual(crop_context["current_stage"], "flowering")
        self.assertEqual(crop_context["state"], "Maharashtra")
        self.assertEqual((crop_context["latitude"], crop_context["longitude"]), (19, 73))
        self.assertEqual(analyze.call_args.kwargs["growth_stage"], "flowering")
        self.assertEqual(analyze.call_args.kwargs["region"], "Maharashtra")
        prediction.assert_not_called()

    def test_weather_risk_api_incomplete_hourly_response_is_not_low_risk(self):
        from routes.weather import weather_bp
        app = Flask(__name__)
        app.secret_key = "test"
        app.register_blueprint(weather_bp, url_prefix="/api")
        client = app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = 3
        payload_weather = hourly_weather([36] * 48)
        payload_weather.update({"provider": "open-meteo", "latitude": 19, "longitude": 73, "timezone": "Asia/Kolkata"})
        payload_weather["hourly_forecast"] = payload_weather["hourly_forecast"][:25]
        with patch("routes.weather.get_user", return_value={"id": 3, "location_consent_at": "consented"}), \
             patch("routes.weather.save_user_location"), \
             patch("routes.weather.list_farms", return_value=[{"id": 4, "state": "Maharashtra", "district": "Pune"}]), \
             patch("routes.weather.list_fields", return_value=[{"id": 5}]), \
             patch("routes.weather.list_crops", return_value=[{"id": 6, "crop_name": "Paddy", "current_stage": "flowering"}]), \
             patch("routes.weather.create_risk_prediction") as prediction:
            response = client.post("/api/weather/risk", json={"latitude": 19, "longitude": 73, "weather": payload_weather})
        self.assertEqual(response.status_code, 200, response.get_json())
        risk = response.get_json()["risks"][0]
        heat = next(item for item in risk["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(heat["status"], "unavailable")
        self.assertEqual(heat["evaluation_status"], "insufficient_data")
        self.assertEqual(risk["status"], "unavailable")
        self.assertIsNone(risk["score"])
        self.assertEqual(heat["triggered_rules"], [])
        prediction.assert_not_called()

    def test_saved_database_crop_context_flows_through_analyze_api(self):
        from routes.crop_intelligence import crop_intelligence_bp
        app = Flask(__name__)
        app.secret_key = "test"
        app.register_blueprint(crop_intelligence_bp, url_prefix="/api")
        client = app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = 3
        saved_crop = {
            "id": 42, "user_id": 3, "crop_name": "Paddy", "variety": "Local",
            "latitude": 19.076, "longitude": 72.878, "city": "Mumbai", "district": "Mumbai",
            "state": "Maharashtra", "planting_date": "2026-06-10", "growth_stage": "flowering",
            "soil_type": "loam", "drainage_condition": "good", "irrigation_availability": "canal",
        }
        provider_weather = hourly_weather([35] * 3 + [36] + [30] * 44)
        provider_weather.update({"latitude": saved_crop["latitude"], "longitude": saved_crop["longitude"], "timezone": "Asia/Kolkata"})
        with patch("routes.crop_intelligence.get_owned_user_crop", return_value=saved_crop), \
             patch("services.crop_risk_service.get_user_crop", return_value=saved_crop), \
             patch("routes.weather._browser_forecast", return_value=provider_weather) as validate_browser_weather, \
             patch("services.crop_risk_service.get_weather", side_effect=AssertionError("matching browser forecast should be reused")) as fetch_server_weather, \
             patch("services.crop_risk_service.retrieve", return_value=[]), \
             patch("services.crop_risk_service.latest_crop_risk", return_value=None), \
             patch("services.crop_risk_service.find_user_crop_alert_event", return_value=None), \
             patch("services.crop_risk_service.save_weather_snapshot"), \
             patch("services.crop_risk_service.save_crop_risk", return_value={"id": 91}), \
             patch("services.crop_risk_service.create_alert") as create_alert:
            response = client.post("/api/crops/42/analyze", json={"weather": provider_weather})
        self.assertEqual(response.status_code, 200, response.get_json())
        payload = response.get_json()
        self.assertEqual(payload["crop"]["crop_name"], "Paddy")
        self.assertEqual(payload["risk"]["crop_id"], "rice")
        self.assertEqual(payload["risk"]["growth_stage"], "flowering")
        self.assertEqual(payload["risk"]["location"]["state"], "Maharashtra")
        self.assertEqual(payload["risk"]["location"]["latitude"], saved_crop["latitude"])
        self.assertEqual(payload["risk"]["crop_context"]["planting_date"], "2026-06-10")
        validate_browser_weather.assert_called_once()
        fetch_server_weather.assert_not_called()
        heat = next(item for item in payload["risk"]["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(heat["matched_rule_ids"], ["rice_flowering_hourly_temperature_above_35c_icar_review"])
        self.assertEqual(heat["triggered_rules"][0]["triggered_hours"][0]["temperature_c"], 36)
        self.assertIsNone(payload["risk"]["risk_score"])
        self.assertEqual(len(payload["risk"]["alerts"]), 1)
        create_alert.assert_called_once()

    def test_saved_rice_vegetative_api_exposes_rule_skip_reasons(self):
        from routes.crop_intelligence import crop_intelligence_bp
        app = Flask(__name__)
        app.secret_key = "test"
        app.register_blueprint(crop_intelligence_bp, url_prefix="/api")
        client = app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = 3
        saved_crop = {"id": 45, "user_id": 3, "crop_name": "Dhan", "latitude": 28.4744,
                      "longitude": 77.504, "city": "Greater Noida", "district": "Gautam Buddha Nagar",
                      "state": "Uttar Pradesh", "growth_stage": "Vegetative"}
        provider_weather = hourly_weather([25] * 48)
        provider_weather.update({"latitude": saved_crop["latitude"], "longitude": saved_crop["longitude"],
                                 "timezone": "Asia/Kolkata"})
        with patch("routes.crop_intelligence.get_owned_user_crop", return_value=saved_crop), \
             patch("services.crop_risk_service.get_user_crop", return_value=saved_crop), \
             patch("services.crop_risk_service.get_weather", return_value=provider_weather), \
             patch("services.crop_risk_service.retrieve", return_value=[]), \
             patch("services.crop_risk_service.latest_crop_risk", return_value=None), \
             patch("services.crop_risk_service.save_weather_snapshot"), \
             patch("services.crop_risk_service.save_crop_risk", return_value={"id": 93}), \
             patch("services.crop_risk_service.find_user_crop_alert_event"), \
             patch("services.crop_risk_service.create_alert") as create_alert:
            response = client.post("/api/crops/45/analyze")
        self.assertEqual(response.status_code, 200, response.get_json())
        payload = response.get_json()
        self.assertEqual(payload["risk"]["crop_id"], "rice")
        self.assertEqual(payload["risk"]["growth_stage"], "Vegetative")
        self.assertEqual(payload["risk"]["status"], "unavailable")
        self.assertIsNone(payload["risk"]["risk_score"])
        heat = next(item for item in payload["risk"]["hazards"] if item["hazard"] == "HEAT_STRESS")
        reasons = {item["rule_id"]: item["reason"] for item in heat["skipped_rules"]}
        self.assertIn("Stage mismatch", reasons["rice_flowering_hourly_temperature_above_35c_icar_review"])
        self.assertIn("provisional", reasons["rice_flowering_heat_exposure_35c_india_2019"])
        create_alert.assert_not_called()

    def test_saved_crop_without_stage_or_state_stays_explicitly_unavailable_through_api(self):
        from routes.crop_intelligence import crop_intelligence_bp
        app = Flask(__name__)
        app.secret_key = "test"
        app.register_blueprint(crop_intelligence_bp, url_prefix="/api")
        client = app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = 3
        saved_crop = {"id": 43, "user_id": 3, "crop_name": "Paddy", "latitude": 19.076,
                      "longitude": 72.878, "city": "Mumbai", "state": None, "growth_stage": None}
        provider_weather = hourly_weather([40] * 48)
        provider_weather.update({"latitude": 19.076, "longitude": 72.878, "timezone": "Asia/Kolkata"})
        with patch("routes.crop_intelligence.get_owned_user_crop", return_value=saved_crop), \
             patch("services.crop_risk_service.get_user_crop", return_value=saved_crop), \
             patch("services.crop_risk_service.get_weather", return_value=provider_weather), \
             patch("services.crop_risk_service.retrieve", return_value=[]), \
             patch("services.crop_risk_service.latest_crop_risk", return_value=None), \
             patch("services.crop_risk_service.save_weather_snapshot"), \
             patch("services.crop_risk_service.save_crop_risk", return_value={"id": 92}), \
             patch("services.crop_risk_service.find_user_crop_alert_event"), \
             patch("services.crop_risk_service.create_alert") as create_alert:
            response = client.post("/api/crops/43/analyze")
        self.assertEqual(response.status_code, 200, response.get_json())
        payload = response.get_json()
        heat = next(item for item in payload["risk"]["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(payload["risk"]["status"], "unavailable")
        self.assertIsNone(payload["risk"]["risk_score"])
        self.assertEqual(heat["evaluation_status"], "insufficient_data")
        self.assertEqual(heat["triggered_rules"], [])
        self.assertTrue(any("growth stage is missing" in item.lower() for item in payload["risk"]["missing_inputs"]))
        self.assertEqual(payload["risk"]["growth_stage"], None)
        create_alert.assert_not_called()

    def test_saved_crop_context_endpoint_updates_the_risk_record_not_just_legacy_crop(self):
        from routes.crop_intelligence import crop_intelligence_bp
        app = Flask(__name__)
        app.secret_key = "test"
        app.register_blueprint(crop_intelligence_bp, url_prefix="/api")
        client = app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = 3
        saved_crop = {"id": 44, "user_id": 3, "crop_name": "Wheat", "latitude": 29.0, "longitude": 76.0,
                      "state": "Haryana", "growth_stage": None}
        updated_crop = {**saved_crop, "growth_stage": "grain filling"}
        with patch("routes.crop_intelligence.get_owned_user_crop", return_value=saved_crop), \
             patch("routes.crop_intelligence.update_user_crop", return_value=updated_crop) as update:
            response = client.patch("/api/crops/44/context", json={"growth_stage": " grain filling "})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["growth_stage"], "grain filling")
        update.assert_called_once_with(44, {"growth_stage": "grain filling"})

    def test_corn_alias_resolves_to_maize_but_does_not_borrow_maize_risk_rules(self):
        corn, _ = resolve_crop("corn")
        maize, _ = resolve_crop("maize")
        self.assertEqual(corn["crop_id"], maize["crop_id"])
        result = risk_engine.analyze_forecast({"crop_name": "corn", "latitude": 19, "longitude": 73, "state": "Maharashtra"}, hourly_weather([40] * 48), None, "flowering", "Maharashtra")
        self.assertEqual(result["crop_id"], "maize")
        self.assertEqual(result["status"], "unavailable")

    def test_weather_coordinates_staleness_and_rainfall_units_are_explicit(self):
        data = hourly_weather([25] * 48, rainfall=1, stale=True)
        data.update({"latitude": 19, "longitude": 73, "rainfall": 9})
        result = risk_engine.analyze_forecast({"crop_name": "rice", "latitude": 19, "longitude": 73, "state": "Maharashtra"}, data, None, "flowering", "Maharashtra")
        obs = result["weather_observations"]
        self.assertEqual(obs["next_48h_rainfall_total_mm"], 48.0)
        self.assertEqual(obs["forecast_rainfall_total_mm"], 35.0)
        self.assertEqual(obs["current_rainfall_mm"], 9.0)
        self.assertTrue(obs["stale"])
        self.assertTrue(any("cached" in item for item in result["missing_inputs"]))
        data["latitude"] = 30
        mismatched = risk_engine.analyze_forecast({"crop_name": "rice", "latitude": 19, "longitude": 73, "state": "Maharashtra"}, data, None, "flowering", "Maharashtra")
        self.assertTrue(any("coordinates do not match" in item for item in mismatched["missing_inputs"]))

    def test_same_location_forecast_is_shared_but_crop_assessments_are_separate(self):
        shared_weather = weather([12, 4], 88, 34)
        rice = risk_engine.analyze_forecast({"crop_name": "Rice", "latitude": 19, "longitude": 73, "state": "Maharashtra"}, shared_weather, get_document("rice"), "flowering", "Maharashtra")
        wheat = risk_engine.analyze_forecast({"crop_name": "Wheat", "latitude": 19, "longitude": 73, "state": "Maharashtra"}, shared_weather, get_document("wheat"), "vegetative", "Maharashtra")
        self.assertEqual(rice["weather_observations"], wheat["weather_observations"])
        self.assertNotEqual(rice["crop_id"], wheat["crop_id"])
        self.assertTrue(all(item["status"] == "unavailable" for item in rice["hazards"]))
        self.assertTrue(all(item["risk_index"] is None for item in wheat["hazards"]))

    def test_rainfall_totals_do_not_double_count_current_observation(self):
        data = weather([5, 7])
        data["rainfall"] = 3
        result = risk_engine.analyze_forecast({"crop_name": "Wheat", "latitude": 19, "longitude": 73, "state": "Haryana"}, data, get_document("wheat"), "vegetative", "Haryana")
        self.assertEqual(result["weather_observations"]["forecast_rainfall_total_mm"], 12)
        self.assertEqual(result["weather_observations"]["current_rainfall_mm"], 3)

    def test_verified_source_without_implemented_evaluator_stays_unavailable(self):
        rule = {"crop_id": "rice", "hazard_type": "HEAT_STRESS", "growth_stage": "all", "region": "India", "verification_status": "verified", "source_url": "https://example.org/rule", "publication_title": "Example source", "last_reviewed": "2026-10-15"}
        result = risk_engine.analyze_forecast({"crop_name": "Rice", "latitude": 19, "longitude": 73, "state": "Maharashtra"}, weather([0]), get_document("rice"), "vegetative", "Maharashtra", [rule])
        heat = next(item for item in result["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(heat["status"], "unavailable")
        self.assertIsNone(result["risk_score"])
        self.assertEqual(heat["sources"][0]["source_url"], rule["source_url"])

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
        crop, candidates = resolve_crop("peas")
        self.assertIsNone(crop)
        self.assertEqual(candidates, ["Field Pea", "Garden Pea"])

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
    def test_registered_limited_crop_uses_weather_and_returns_unavailable_status(self, *_mocks):
        from services.crop_risk_service import run_crop_risk_analysis
        response = run_crop_risk_analysis(7, force=True)
        self.assertEqual(response["risk"]["crop_id"], "dragon_fruit")
        self.assertEqual(response["risk"]["knowledge_status"], "LIMITED")
        self.assertIsNone(response["risk"]["risk_score"])
        self.assertEqual(response["risk"]["overall_risk"], "UNAVAILABLE")
        self.assertIn("forecast", response["weather"])

    @patch("services.crop_risk_service.create_alert")
    @patch("services.crop_risk_service.save_crop_risk", return_value={"id": 11})
    @patch("services.crop_risk_service.save_weather_snapshot")
    @patch("services.crop_risk_service.latest_crop_risk", return_value=None)
    @patch("services.crop_risk_service.retrieve", return_value=[])
    @patch("services.crop_risk_service.get_weather")
    @patch("services.crop_risk_service.get_user_crop")
    def test_saved_crop_analysis_persists_supported_hazard_alert(self, get_crop, get_weather, _retrieve, _latest, _snapshot, _save, create_alert):
        from services.crop_risk_service import run_crop_risk_analysis
        get_crop.return_value = {"id": 8, "crop_name": "Rice", "latitude": 19, "longitude": 73, "state": "Maharashtra", "district": "Pune", "growth_stage": "flowering"}
        forecast = hourly_weather([36] + [30] * 47)
        forecast.update({"latitude": 19, "longitude": 73})
        get_weather.return_value = forecast
        with patch("services.crop_risk_service.find_user_crop_alert_event", side_effect=[None, {"id": 77}]) as find_event:
            result = run_crop_risk_analysis(8, force=True)
            repeated = run_crop_risk_analysis(8, force=True)
        self.assertEqual(result["risk"]["status"], "partially_assessed")
        self.assertIsNone(result["risk"]["risk_score"])
        self.assertEqual(len(result["risk"]["alerts"]), 1)
        alert = result["risk"]["alerts"][0]
        self.assertEqual(alert["severity"], "WATCH")
        self.assertEqual(alert["expected_time"], "2026-10-15T01:00")
        self.assertIn("not confirmed crop damage", alert["explanation"])
        create_alert.assert_called_once()
        saved_alert = create_alert.call_args.args[0]
        self.assertEqual(saved_alert["user_crop_id"], 8)
        self.assertIn("Expected forecast: 2026-10-15T01:00 (UTC)", saved_alert["message"])
        self.assertIn("Evidence source: https://", saved_alert["message"])
        self.assertEqual(len(repeated["risk"]["alerts"]), 1)
        self.assertEqual(find_event.call_count, 2)
        create_alert.assert_called_once()

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
                     patch.object(services.crop_risk_service, "create_alert"), \
                     patch.object(services.crop_risk_service, "find_user_crop_alert_event", return_value=None):
                    response = services.crop_risk_service.run_crop_risk_analysis(29, force=True)
                expected_crop, _ = resolve_crop(crop_name)
                self.assertEqual(response["risk"]["crop_name"], expected_crop["canonical_name"])
                self.assertIn(response["risk"]["knowledge_status"], {"PARTIAL", "LIMITED"})
                self.assertEqual(response["risk"]["overall_risk"], "UNAVAILABLE")
                self.assertEqual(response["risk"]["status"], "unavailable")
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
        catalog_by_id = {item["crop_id"]: item for item in catalog_items}
        for crop_id in ("rice", "wheat", "potato", "tomato", "onion", "field_pea", "garden_pea", "lentil", "spinach"):
            if crop_id in {"wheat", "rice"}:
                self.assertEqual(catalog_by_id[crop_id]["knowledge_status"], "PARTIAL")
                self.assertEqual(catalog_by_id[crop_id]["verified_hazards"], ["HEAT_STRESS"])
            elif crop_id == "potato":
                self.assertEqual(catalog_by_id[crop_id]["knowledge_status"], "PARTIAL")
                self.assertEqual(catalog_by_id[crop_id]["verified_hazards"], ["HEAT_STRESS"])
            else:
                self.assertEqual(catalog_by_id[crop_id]["knowledge_status"], "LIMITED")
                self.assertEqual(catalog_by_id[crop_id]["verified_hazards"], [])
        self.assertEqual(catalog_by_id["lentil"]["verified_stages"], [])
        self.assertEqual(catalog_by_id["maize"]["knowledge_status"], "LIMITED")
        legacy_knowledge = client.get("/api/crop-knowledge").get_json()["items"]
        self.assertTrue(all(item["knowledge_status"] == "LIMITED" and "optimal_temperature_c" not in item for item in legacy_knowledge))
        with client.session_transaction() as session:
            session["user_id"] = 9
        with patch("routes.agriculture.get_user", return_value={"id": 9, "user_type": "farmer"}), \
             patch("routes.agriculture.create_user_crop", side_effect=lambda values: values):
            accepted = client.post("/api/crops", json={"crop_name": "toor", "latitude": 19, "longitude": 73, "state": "Haryana", "district": "Karnal", "city": "Karnal", "variety": "Example", "soil_type": "loam", "drainage_condition": "well drained", "irrigation_availability": "canal", "growth_stage": "flowering"})
            ambiguous = client.post("/api/crops", json={"crop_name": "tori", "latitude": 19, "longitude": 73})
            peas = client.post("/api/crops", json={"crop_name": "peas", "latitude": 19, "longitude": 73})
            self.assertEqual(accepted.status_code, 201)
            self.assertEqual(accepted.get_json()["crop_name"], "Pigeon Pea")
            self.assertEqual(accepted.get_json()["growth_stage"], "flowering")
            self.assertEqual(accepted.get_json()["district"], "Karnal")
            self.assertEqual(accepted.get_json()["soil_type"], "loam")
            self.assertIsNone(accepted.get_json()["country"])
            self.assertEqual(ambiguous.status_code, 400)
            self.assertEqual(len(ambiguous.get_json()["candidates"]), 2)
            self.assertEqual(peas.status_code, 400)
            self.assertEqual(peas.get_json()["candidates"], ["Field Pea", "Garden Pea"])
            self.assertIn("Choose a specific crop", peas.get_json()["error"])

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
            "overall_risk": "UNAVAILABLE", "risk_score": None, "knowledge_status": "LIMITED",
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
             patch("routes.weather.create_risk_prediction", side_effect=lambda value: value) as save_prediction:
            response = client.post("/api/weather/risk", json={"latitude": 19, "longitude": 73})
        self.assertEqual(response.status_code, 200, response.get_json())
        risks = response.get_json()["risks"]
        self.assertEqual([item["crop"] for item in risks], ["Rice", "Tomato"])
        self.assertTrue(all(item["score"] is None and item["level"] == "UNAVAILABLE" for item in risks))
        save_prediction.assert_not_called()
        self.assertIn("official_advisory_url", response.get_json())
        self.assertEqual([call.kwargs["weather"]["forecast"] for call in analyze.call_args_list], [forecast["forecast"][:5]] * 2)

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
            "hourly_forecast": [{"time": f"2026-10-12T{hour % 24:02d}:00", "rainfall": 1, "temperature": 25, "humidity": 70, "wind_speed": 7, "wind_gust": 10, "precipitation_probability": 20} for hour in range(48)],
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
        self.assertEqual(len(response.get_json()["weather"]["hourly_forecast"]), 48)
        self.assertEqual(response.get_json()["weather_signals"][0]["category"], "heavy")

    def test_weather_risk_api_serializes_partial_rule_result_and_source(self):
        from routes.weather import weather_bp
        app = Flask(__name__)
        app.secret_key = "test"
        app.register_blueprint(weather_bp, url_prefix="/api")
        client = app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = 3
        payload_weather = hourly_weather([36] + [30] * 47)
        payload_weather.update({"provider": "open-meteo", "latitude": 19, "longitude": 73, "temperature": 30, "humidity": 65, "wind_speed": 8})
        with patch("routes.weather.get_user", return_value={"id": 3, "location_consent_at": "consented"}), \
             patch("routes.weather.save_user_location"), \
             patch("routes.weather.list_farms", return_value=[{"id": 4, "state": "Maharashtra", "district": "Pune"}]), \
             patch("routes.weather.list_fields", return_value=[{"id": 5, "soil_type": "loam", "drainage_condition": "good", "irrigation_type": "canal"}]), \
             patch("routes.weather.list_crops", return_value=[{"id": 6, "crop_name": "Paddy", "current_stage": "vegetative"}]), \
             patch("routes.weather.create_alert", return_value={"id": 1}), \
             patch("routes.weather.find_recent_alert", return_value=None), \
             patch("routes.weather.create_risk_prediction", side_effect=lambda value: value) as prediction:
            response = client.post("/api/weather/risk", json={"latitude": 19, "longitude": 73, "location": "Pune, Maharashtra", "weather": payload_weather})
        self.assertEqual(response.status_code, 200, response.get_json())
        data = response.get_json()
        rice = data["risks"][0]
        heat = next(item for item in rice["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(rice["status"], "unavailable")
        self.assertIsNone(rice["score"])
        self.assertIsNone(heat["risk_index"])
        self.assertTrue(any(source.get("source_validation_status") == "incomplete_evidence" for source in heat["sources"]))
        self.assertEqual(rice["state"], "Maharashtra")
        self.assertEqual(rice["district"], "Pune")
        prediction.assert_not_called()

    def test_weather_risk_api_runs_kalp_from_five_daily_forecasts_without_risk_score(self):
        from routes.weather import weather_bp
        app = Flask(__name__)
        app.secret_key = "test"
        app.register_blueprint(weather_bp, url_prefix="/api")
        client = app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = 3
        weather_payload = daily_weather([30, 30, 30.2, 29, 30])
        with patch("routes.weather.get_user", return_value={"id": 3, "location_consent_at": "consented"}), \
             patch("routes.weather.save_user_location"), \
             patch("routes.weather.list_farms", return_value=[{"id": 4, "state": "Haryana", "district": "Rohtak"}]), \
             patch("routes.weather.list_fields", return_value=[{"id": 5, "soil_type": "loam", "drainage_condition": "good"}]), \
             patch("routes.weather.list_crops", return_value=[{"id": 6, "crop_name": "Wheat", "current_stage": "grain filling"}]), \
             patch("routes.weather.create_risk_prediction") as prediction:
            response = client.post("/api/weather/risk", json={"latitude": 19, "longitude": 73, "weather": weather_payload})
        self.assertEqual(response.status_code, 200, response.get_json())
        risk = response.get_json()["risks"][0]
        heat = next(item for item in risk["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(len(response.get_json()["weather"]["forecast"]), 5)
        self.assertEqual(heat["evaluation_status"], "trigger_detected")
        self.assertEqual(heat["triggered_rules"][0]["threshold"], 30)
        self.assertEqual(heat["risk_index"], 20)
        self.assertEqual(heat["risk_index_details"]["exposed_observations"], 1)
        self.assertEqual(heat["risk_index_details"]["valid_observations"], 5)
        self.assertEqual(heat["risk_index_details"]["observation_unit"], "daily Tmax forecasts")
        self.assertEqual(heat["risk_index_details"]["window_start"], "2026-10-15")
        self.assertEqual(heat["risk_index_details"]["window_end"], "2026-10-19")
        self.assertIsNone(risk["score"])
        self.assertEqual(risk["status"], "partially_assessed")
        prediction.assert_not_called()

    def test_weather_risk_api_runs_potato_night_condition_rule(self):
        from routes.weather import weather_bp
        app = Flask(__name__)
        app.secret_key = "test"
        app.register_blueprint(weather_bp, url_prefix="/api")
        client = app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = 3
        weather_payload = hourly_weather([19] * 48)
        weather_payload.update({"provider": "open-meteo", "latitude": 19, "longitude": 73, "timezone": "Asia/Kolkata"})
        weather_payload["forecast"].append({"date": "2026-10-17", "rainfall": 0, "temperature_max": 25, "temperature_min": 19})
        weather_payload["forecast"][1]["temperature_min"] = 20
        with patch("routes.weather.get_user", return_value={"id": 3, "location_consent_at": "consented"}), \
             patch("routes.weather.save_user_location"), \
             patch("routes.weather.list_farms", return_value=[{"id": 4, "state": "Maharashtra", "district": "Pune"}]), \
             patch("routes.weather.list_fields", return_value=[{"id": 5, "soil_type": "loam", "drainage_condition": "good"}]), \
             patch("routes.weather.list_crops", return_value=[{"id": 6, "crop_name": "Potato", "current_stage": "tuberization"}]), \
             patch("routes.weather.create_risk_prediction") as prediction:
            response = client.post("/api/weather/risk", json={"latitude": 19, "longitude": 73, "weather": weather_payload})
        self.assertEqual(response.status_code, 200, response.get_json())
        risk = response.get_json()["risks"][0]
        heat = next(item for item in risk["hazards"] if item["hazard"] == "HEAT_STRESS")
        self.assertEqual(heat["evaluation_status"], "trigger_detected")
        self.assertEqual(heat["triggered_rules"][0]["threshold"], 20)
        self.assertEqual(heat["risk_index"], 50)
        self.assertEqual(heat["risk_index_details"]["exposed_observations"], 1)
        self.assertEqual(heat["risk_index_details"]["valid_observations"], 2)
        self.assertIsNone(risk["score"])
        self.assertEqual(risk["status"], "partially_assessed")
        prediction.assert_not_called()

    def test_weather_risk_provider_failure_returns_explicit_api_error(self):
        from routes.weather import weather_bp
        app = Flask(__name__)
        app.secret_key = "test"
        app.register_blueprint(weather_bp, url_prefix="/api")
        client = app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = 3
        with patch("routes.weather.get_user", return_value={"id": 3, "location_consent_at": "consented"}), \
             patch("routes.weather.save_user_location"), \
             patch("routes.weather.forecast_weather", side_effect=RuntimeError("weather provider offline")):
            response = client.post("/api/weather/risk", json={"latitude": 19, "longitude": 73})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.get_json()["error"], "Forecast risk analysis failed.")

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


class CropWeatherRiskModelTests(unittest.TestCase):
    def model_weather(self, maximums, minimums, rainfall, humidity=60, wind=8, provider="open-meteo", stale=False):
        start = datetime(2026, 10, 15, 0)
        forecast = [
            {
                "date": (start + timedelta(days=index)).strftime("%Y-%m-%d"),
                "rainfall": rain,
                "temperature_max": maximums[index],
                "temperature_min": minimums[index],
            }
            for index, rain in enumerate(rainfall)
        ]
        hourly = [
            {
                "time": (start + timedelta(hours=index)).isoformat(timespec="minutes"),
                "temperature": (maximums[0] + minimums[0]) / 2,
                "humidity": humidity,
                "rainfall": 0,
                "wind_speed": wind,
            }
            for index in range(48)
        ]
        return {
            "provider": provider,
            "latitude": 28.4,
            "longitude": 77.1,
            "timezone": "Asia/Kolkata",
            "stale": stale,
            "forecast": forecast,
            "hourly_forecast": hourly,
        }

    def benign_weather(self):
        return self.model_weather([23, 24, 23, 24, 23], [14, 15, 14, 14, 15], [4, 0, 3, 0, 2], humidity=55)

    def hot_humid_weather(self):
        return self.model_weather([34, 35, 34, 35, 34], [20, 21, 20, 21, 20], [0, 0, 0, 0, 0], humidity=92)

    def assess(self, crop_name, weather_data, stage="vegetative"):
        from services.agriculture.weather_risk_model import assess_crop_weather_risk
        return assess_crop_weather_risk(
            {"crop_name": crop_name, "city": "Greater Noida", "state": "Uttar Pradesh", "latitude": 28.4, "longitude": 77.1},
            weather_data,
            stage,
            "Uttar Pradesh",
        )

    def test_profiles_are_crop_specific_or_category_fallback_with_provenance(self):
        expected = {
            "rice": "crop_knowledge",
            "carrot": "crop_specific_tuning",
            "broccoli": "category_default",
        }
        for crop_name, source in expected.items():
            with self.subTest(crop=crop_name):
                result = self.assess(crop_name, self.hot_humid_weather())
                self.assertEqual(result["status"], "modelled_estimate", result)
                self.assertEqual(result["profile_source"], source)
                self.assertGreater(result["risk_percent"], 0)
                self.assertLessEqual(result["risk_percent"], 100)

    def test_every_catalog_crop_receives_a_bounded_labeled_estimate(self):
        catalog = load_catalog()
        self.assertGreaterEqual(len(catalog), 150)
        weather_data = self.benign_weather()
        for crop in catalog:
            with self.subTest(crop=crop["crop_id"]):
                result = self.assess(crop["crop_id"], weather_data)
                self.assertEqual(result["status"], "modelled_estimate")
                self.assertIsInstance(result["risk_percent"], int)
                self.assertGreaterEqual(result["risk_percent"], 0)
                self.assertLessEqual(result["risk_percent"], 100)
                self.assertEqual(result["safe_percent"], 100 - result["risk_percent"])
                self.assertIn(result["level"], {"LOW", "MODERATE", "HIGH"})
                self.assertIn(result["tone"], {"low", "moderate", "high"})

    def test_score_bands_drive_colour_alert_and_safe_complement(self):
        scenarios = [self.benign_weather(), self.hot_humid_weather()]
        levels = set()
        for weather_data in scenarios:
            for crop_name in ("rice", "wheat", "spinach", "carrot", "broccoli", "tomato", "banana"):
                with self.subTest(crop=crop_name):
                    result = self.assess(crop_name, weather_data)
                    risk = result["risk_percent"]
                    levels.add(result["level"])
                    self.assertEqual(result["safe_percent"], 100 - risk)
                    if risk < 30:
                        self.assertEqual(result["level"], "LOW")
                        self.assertEqual(result["tone"], "low")
                        self.assertFalse(result["alert"])
                    elif risk < 60:
                        self.assertEqual(result["level"], "MODERATE")
                        self.assertEqual(result["tone"], "moderate")
                        self.assertTrue(result["alert"])
                        self.assertTrue(result["watch"])
                    else:
                        self.assertEqual(result["level"], "HIGH")
                        self.assertEqual(result["tone"], "high")
                        self.assertTrue(result["alert"])
        # The model must actually exercise more than one band, not just return LOW.
        self.assertEqual(levels, {"LOW", "MODERATE", "HIGH"})

    def test_hot_humid_forecast_raises_heat_and_humidity_for_sensitive_crops(self):
        result = self.assess("spinach", self.hot_humid_weather())
        factor_keys = {factor["key"] for factor in result["factors"]}
        self.assertIn("heat", factor_keys)
        self.assertIn("humidity", factor_keys)
        evidence = " ".join(factor["evidence"] for factor in result["factors"])
        self.assertIn("Forecast high reaches", evidence)
        self.assertIn("Mean humidity", evidence)
        self.assertTrue(any("heat" in action.lower() or "humid" in action.lower() or "scout" in action.lower() or "air" in action.lower()
                            for action in result["recommendations"]))

    def test_missing_stage_still_estimates_with_a_documented_limitation(self):
        result = self.assess("rice", self.hot_humid_weather(), stage=None)
        self.assertEqual(result["status"], "modelled_estimate")
        self.assertIsNone(result["growth_stage"])
        self.assertTrue(any("Growth stage was not recorded" in item for item in result["limitations"]))

    def test_demo_and_missing_weather_do_not_invent_a_percentage(self):
        demo = self.assess("rice", self.model_weather([30, 30, 30], [20, 20, 20], [0, 0, 0], provider="demo"))
        self.assertEqual(demo["status"], "insufficient_data")
        self.assertIsNone(demo["risk_percent"])
        self.assertIsNone(demo["safe_percent"])
        self.assertFalse(demo["alert"])

        missing = self.assess("rice", {})
        self.assertEqual(missing["status"], "insufficient_data")
        self.assertIsNone(missing["risk_percent"])
        self.assertIsNone(missing["safe_percent"])

    def test_result_is_explicitly_not_a_probability_and_keeps_verified_fields_separate(self):
        result = self.assess("carrot", self.hot_humid_weather())
        self.assertFalse(result["model"]["is_probability"])
        self.assertIn("not a probability of crop loss", result["summary"])
        self.assertTrue(any("not a probability" in item for item in result["limitations"]))
        self.assertNotIn("probability of crop loss", result["label"])

        verified = analyze_verified("carrot", self.hot_humid_weather(), "vegetative")
        self.assertEqual(verified["status"], "unavailable")
        self.assertIsNone(verified["risk_score"])
        self.assertEqual(verified["overall_risk"], "UNAVAILABLE")
        self.assertEqual(verified["model_assessment"]["status"], "modelled_estimate")
        self.assertIsNotNone(verified["model_assessment"]["risk_percent"])

    def test_stale_forecast_is_flagged_in_the_estimate(self):
        result = self.assess("rice", self.model_weather([30, 31, 30], [20, 21, 20], [0, 0, 0], stale=True))
        self.assertEqual(result["status"], "modelled_estimate")
        self.assertTrue(result["inputs"]["stale"])
        self.assertTrue(any("cached forecast" in item for item in result["limitations"]))

    def test_six_daily_days_plus_hourly_peak_do_not_overflow_the_heat_weights(self):
        # Seven forecast days are trimmed to six, and a hot hourly peak adds a
        # seventh heat sample. Sensitive crops (lower optimal maximums) exercise
        # that path, which previously raised IndexError and surfaced as a 404.
        weather_data = self.model_weather(
            [23, 24, 23, 24, 23, 24, 23],
            [14, 15, 14, 14, 15, 14, 15],
            [1, 0, 2, 0, 1, 0, 1],
            humidity=55,
        )
        for hour in weather_data["hourly_forecast"]:
            hour["temperature"] = 31
        for crop_name in ("wheat", "carrot", "spinach"):
            with self.subTest(crop=crop_name):
                result = self.assess(crop_name, weather_data)
                self.assertEqual(result["status"], "modelled_estimate", result)
                self.assertIsInstance(result["risk_percent"], int)
                self.assertGreaterEqual(result["risk_percent"], 0)
                self.assertLessEqual(result["risk_percent"], 100)
                self.assertIn("heat", {factor["key"] for factor in result["factors"]})

    def test_weather_risk_api_returns_a_model_percentage_for_a_crop_without_verified_rules(self):
        from routes.weather import weather_bp
        app = Flask(__name__)
        app.secret_key = "test"
        app.register_blueprint(weather_bp, url_prefix="/api")
        client = app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = 3
        forecast = self.hot_humid_weather()
        with patch("routes.weather.get_user", return_value={"id": 3, "location_consent_at": "consented"}), \
             patch("routes.weather.save_user_location"), \
             patch("routes.weather.forecast_weather", return_value=forecast), \
             patch("routes.weather.list_farms", return_value=[{"id": 4, "state": "Uttar Pradesh"}]), \
             patch("routes.weather.list_fields", return_value=[{"id": 5}]), \
             patch("routes.weather.list_crops", return_value=[{"id": 22, "crop_name": "Carrot", "current_stage": "vegetative"}]):
            response = client.post("/api/weather/risk", json={"latitude": 28.4, "longitude": 77.1})
        self.assertEqual(response.status_code, 200, response.get_json())
        risk = response.get_json()["risks"][0]
        self.assertEqual(risk["level"], "UNAVAILABLE")
        self.assertIsNone(risk["score"])
        assessment = risk["model_assessment"]
        self.assertEqual(assessment["status"], "modelled_estimate")
        self.assertIsInstance(assessment["risk_percent"], int)
        self.assertEqual(assessment["safe_percent"], 100 - assessment["risk_percent"])
        self.assertFalse(assessment["model"]["is_probability"])
        self.assertIn(assessment["level"], {"LOW", "MODERATE", "HIGH"})


if __name__ == "__main__":
    unittest.main()
