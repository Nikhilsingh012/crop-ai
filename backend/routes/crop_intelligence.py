from flask import Blueprint, jsonify, request, session

from authz import current_user_id, unauthorized
from db import create_user_crop, get_owned_crop, get_owned_user_crop, list_crop_risks, list_user_crops
from services.crop_risk_service import run_crop_risk_analysis
from services.crop_catalog import load_catalog
from services.rag.knowledge_loader import get_document, load_documents

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
    return jsonify({"items": load_catalog()})


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
        return jsonify(run_crop_risk_analysis(crop["id"], force=True))
    except LookupError as error:
        return jsonify({"error": str(error)}), 404
    except Exception as error:
        return jsonify({"error": "Risk analysis is temporarily unavailable.", "details": str(error)}), 502
