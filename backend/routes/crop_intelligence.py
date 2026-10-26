from flask import Blueprint, jsonify, request, session

from authz import current_user_id, unauthorized
from db import create_user_crop, get_owned_crop, get_owned_user_crop, list_crop_risks, list_user_crops, update_user_crop
from services.crop_risk_service import run_crop_risk_analysis
from services.crop_catalog import load_catalog
from services.agriculture.crop_risk_engine import load_verified_rules, normalize_stage, _region_matches
from services.agriculture.crop_risk_coverage import build_coverage_report
from services.crop_catalog import resolve_crop
from services.rag.knowledge_loader import get_document, load_documents
from services.weather.weather_service import WeatherProviderError

crop_intelligence_bp = Blueprint("crop_intelligence", __name__)


def _coordinates(payload):
    try:
        latitude, longitude = float(payload.get("latitude")), float(payload.get("longitude"))
    except (TypeError, ValueError):
        raise ValueError("Valid latitude and longitude are required.")
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("Latitude or longitude is outside the valid range.")
    return latitude, longitude


def _current_user_crop(crop_id):
    user_id = current_user_id()
    if user_id is None:
        return None, unauthorized()
    crop = get_owned_user_crop(crop_id, user_id)
    if crop is None:
        return None, (jsonify({"error": "Crop not found."}), 404)
    return crop, None


@crop_intelligence_bp.get("/crops")
def crops():
    user_id = current_user_id()
    if user_id is None:
        return unauthorized()
    return jsonify({"items": list_user_crops(user_id)})


@crop_intelligence_bp.get("/crop-knowledge")
def crop_knowledge():
    return jsonify({"items": [{"crop": item["crop"], "crop_id": item.get("crop_id"), "knowledge_status": item.get("knowledge_status", "LIMITED"), "source": item.get("source"), **({"optimal_temperature_c": item.get("optimal_temperature_c")} if item.get("threshold_evidence_status") == "verified" else {})} for item in load_documents()]})


@crop_intelligence_bp.get("/crop-catalog")
def crop_catalog():
    rules_by_crop = {}
    coverage_by_crop = {item["crop_id"]: item for item in build_coverage_report()["crops"]}
    for rule in load_verified_rules():
        rules_by_crop.setdefault(rule["crop_id"], []).append(rule)
    items = []
    for crop in load_catalog():
        rules = rules_by_crop.get(crop["crop_id"], [])
        items.append({
            **crop,
            "knowledge_status": "PARTIAL" if rules else "LIMITED",
            "verified_hazards": sorted({rule["hazard_type"] for rule in rules}),
            "verified_stages": sorted({stage for rule in rules for stage in (rule["growth_stage"] if isinstance(rule["growth_stage"], list) else [rule["growth_stage"]])}),
            "verified_regions": sorted({region for rule in rules for region in (rule["region"] if isinstance(rule["region"], list) else [rule["region"]])}),
            "verified_rule_count": len(rules),
            "verified_rule_count_by_hazard": {hazard: count for hazard, count in coverage_by_crop.get(crop["crop_id"], {}).get("rule_count_by_hazard", {}).items() if count and all(rule.get("verification_status") == "verified" for rule in rules if rule.get("hazard_type") == hazard)},
            "rules_without_evaluator": coverage_by_crop.get(crop["crop_id"], {}).get("rules_without_evaluator", []),
            "rule_coverage": "partial" if rules else "none",
        })
    return jsonify({"items": items})


@crop_intelligence_bp.get("/crop-risk-coverage")
def crop_risk_coverage():
    report = build_coverage_report()
    crop_name = request.args.get("crop")
    state = request.args.get("state")
    stage = request.args.get("stage")
    if crop_name:
        canonical, candidates = resolve_crop(crop_name)
        if canonical is None:
            return jsonify({"error": "Crop is unknown or ambiguous.", "candidates": candidates}), 400
        report["crops"] = [row for row in report["crops"] if row["crop_id"] == canonical["crop_id"]]
        matching = []
        for rule in load_verified_rules():
            if rule.get("crop_id") != canonical["crop_id"]:
                continue
            rule_stages = rule.get("growth_stage", "all")
            rule_stages = rule_stages if isinstance(rule_stages, list) else [rule_stages]
            rule_regions = rule.get("region", "India")
            rule_regions = rule_regions if isinstance(rule_regions, list) else [rule_regions]
            stage_ok = not stage or "all" in [normalize_stage(value) for value in rule_stages] or normalize_stage(stage) in [normalize_stage(value) for value in rule_stages]
            region_ok = not state or _region_matches(rule_regions, state)
            if stage_ok and region_ok:
                matching.append(rule)
        report["applicable_rule_ids"] = [rule.get("rule_id") for rule in matching]
        report["applicable_hazard_families"] = sorted({rule.get("hazard_type") for rule in matching})
        report["requested_context"] = {key: value for key, value in (("state", state), ("stage", stage)) if value}
    return jsonify(report)


@crop_intelligence_bp.get("/crops/<int:crop_id>/weather")
def crop_weather(crop_id):
    crop, error = _current_user_crop(crop_id)
    if error:
        return error
    try:
        return jsonify(run_crop_risk_analysis(crop_id)["weather"])
    except Exception as error:
        return jsonify({"error": "Weather data is temporarily unavailable.", "details": str(error)}), 502


@crop_intelligence_bp.get("/crops/<int:crop_id>/alerts")
def crop_alerts(crop_id):
    from db import list_alerts, list_user_crop_alerts
    crop, error = _current_user_crop(crop_id)
    if error and error[1] == 401:
        return error
    if crop is not None:
        return jsonify({"items": list_user_crop_alerts(crop_id)})
    user_id = current_user_id()
    if get_owned_crop(crop_id, user_id) is None:
        return jsonify({"error": "Crop not found."}), 404
    return jsonify({"items": list_alerts(crop_id)})


@crop_intelligence_bp.post("/crops/<int:crop_id>/analyze")
def analyze(crop_id):
    crop, error = _current_user_crop(crop_id)
    if error:
        return error
    try:
        payload = request.get_json(silent=True) or {}
        browser_weather = None
        if isinstance(payload.get("weather"), dict):
            # Reuse the browser's already-fetched live forecast when it matches
            # this saved crop. The shared validator rejects stale or malformed data.
            from routes.weather import _browser_forecast
            browser_weather = _browser_forecast(payload["weather"], crop.get("latitude"), crop.get("longitude"))
        return jsonify(run_crop_risk_analysis(crop["id"], force=True, weather_override=browser_weather))
    except LookupError as error:
        return jsonify({"error": str(error)}), 404
    except WeatherProviderError as error:
        return jsonify({"error": f"Risk analysis unavailable: {error.provider_error}", "provider_status": error.provider_status, "provider_error": error.provider_error}), 502
    except Exception as error:
        return jsonify({"error": "Risk analysis is temporarily unavailable.", "details": f"Analysis failed ({type(error).__name__})."}), 502


@crop_intelligence_bp.patch("/crops/<int:crop_id>/context")
def update_crop_context(crop_id):
    crop, error = _current_user_crop(crop_id)
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    values = {key: payload[key].strip() if isinstance(payload[key], str) else payload[key]
              for key in ("growth_stage", "state", "country") if key in payload}
    if not values:
        return jsonify({"error": "At least one crop-context field is required."}), 400
    if any(value is not None and not isinstance(value, str) for value in values.values()):
        return jsonify({"error": "Crop stage, state and country must be text or null."}), 400
    return jsonify(update_user_crop(crop_id, values))
