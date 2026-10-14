import json
from datetime import date, datetime, timezone

from flask import Blueprint, jsonify, request

from authz import current_user_id, unauthorized
from db import (
    create_alert,
    create_crop_event,
    create_risk_prediction,
    create_soil_record,
    create_weather_record,
    get_owned_crop,
    get_owned_field,
    get_owned_user_crop,
    list_crop_risks,
    list_alerts,
    list_crop_events,
    list_risk_predictions,
    list_soil_records,
    list_weather_records,
    mark_alert_read_owned,
    list_user_alerts,
    connection,
)
from services.lifecycle import estimate_lifecycle
from services.health_score import composite_health_score
from services.irrigation import recommend_irrigation
from services.care_plan import build_care_plan
from services.risk_engine import compute_risk
from services.crop_risk_service import run_crop_risk_analysis

insights_bp = Blueprint("insights", __name__)


def _payload():
    return request.get_json(silent=True) or {}


def _required(payload, fields):
    return next((field for field in fields if payload.get(field) in (None, "")), None)


def _crop_or_404(crop_id):
    user_id = current_user_id()
    if user_id is None:
        return None, unauthorized()
    crop = get_owned_crop(crop_id, user_id)
    if crop is None:
        return None, (jsonify({"error": "Crop not found."}), 404)
    return crop, None


def _field_or_404(field_id):
    user_id = current_user_id()
    if user_id is None:
        return None, unauthorized()
    field = get_owned_field(field_id, user_id)
    if field is None:
        return None, (jsonify({"error": "Field not found."}), 404)
    return field, None


@insights_bp.route("/fields/<int:field_id>/soil", methods=["GET", "POST"])
def field_soil(field_id):
    field, error = _field_or_404(field_id)
    if error:
        return error
    if request.method == "GET":
        return jsonify({"items": list_soil_records(field_id)})
    payload = _payload()
    payload["field_id"] = field_id
    keys = ("field_id", "ph", "nitrogen", "phosphorus", "potassium", "sulphur", "zinc", "iron", "copper", "manganese", "boron", "electrical_conductivity", "organic_carbon")
    return jsonify(create_soil_record({key: payload[key] for key in keys if key in payload})), 201


@insights_bp.route("/crops/<int:crop_id>/events", methods=["GET", "POST"])
def crop_events(crop_id):
    crop, error = _crop_or_404(crop_id)
    if error:
        return error
    if request.method == "GET":
        return jsonify({"items": list_crop_events(crop_id)})
    payload = _payload()
    missing = _required(payload, ["event_type", "event_date"])
    if missing:
        return jsonify({"error": f"'{missing}' is required."}), 400
    payload["crop_id"] = crop_id
    keys = ("crop_id", "event_type", "event_date", "notes")
    return jsonify(create_crop_event({key: payload[key] for key in keys if key in payload})), 201


@insights_bp.route("/fields/<int:field_id>/weather", methods=["GET", "POST"])
def field_weather(field_id):
    field, error = _field_or_404(field_id)
    if error:
        return error
    if request.method == "GET":
        return jsonify({"items": list_weather_records(field_id)})
    payload = _payload()
    if not payload.get("recorded_at"):
        return jsonify({"error": "'recorded_at' is required."}), 400
    payload["field_id"] = field_id
    keys = ("field_id", "recorded_at", "temperature", "humidity", "rainfall", "wind_speed")
    return jsonify(create_weather_record({key: payload[key] for key in keys if key in payload})), 201


@insights_bp.get("/crops/<int:crop_id>/lifecycle")
def crop_lifecycle(crop_id):
    crop, error = _crop_or_404(crop_id)
    if error:
        return error
    return jsonify(estimate_lifecycle(crop))


@insights_bp.get("/crops/<int:crop_id>/calendar")
def crop_calendar(crop_id):
    crop, error = _crop_or_404(crop_id)
    if error:
        return error
    return jsonify(estimate_lifecycle(crop))


@insights_bp.get("/crops/<int:crop_id>/harvest-window")
def crop_harvest_window(crop_id):
    crop, error = _crop_or_404(crop_id)
    if error:
        return error
    lifecycle = estimate_lifecycle(crop)
    return jsonify({
        "status": lifecycle["status"],
        "expected_harvest_date": lifecycle["expected_harvest_date"],
        "days_until_harvest": lifecycle["days_until_harvest"],
        "confidence": "farmer_entered_date" if lifecycle["expected_harvest_date"] else "unavailable",
        "estimated_date_range": None,
        "planning_note": "This is a farmer-entered planning date, not a crop-duration forecast. A verified crop- and variety-specific maturity source is not configured, so CropAI does not invent a date range.",
        "limitations": lifecycle["limitations"],
    })


@insights_bp.post("/advisories/harvest-window")
def save_harvest_planning_date():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or set(payload) - {"crop_id", "expected_harvest_date"}:
        return jsonify({"error": "Provide crop_id and optional expected_harvest_date only."}), 400
    try:
        crop_id = int(payload.get("crop_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "crop_id must be a positive integer."}), 400
    if crop_id < 1:
        return jsonify({"error": "crop_id must be a positive integer."}), 400
    crop, error = _crop_or_404(crop_id)
    if error:
        return error
    expected_date = payload.get("expected_harvest_date", crop.get("expected_harvest_date"))
    if expected_date is not None:
        try:
            expected_date = date.fromisoformat(str(expected_date)).isoformat()
        except ValueError:
            return jsonify({"error": "expected_harvest_date must use YYYY-MM-DD or null."}), 400
    user_id = current_user_id()
    try:
        with connection() as conn:
            if "expected_harvest_date" in payload:
                crop = conn.execute("UPDATE crops SET expected_harvest_date=%s WHERE id=%s RETURNING *", (expected_date, crop_id)).fetchone()
            lifecycle = estimate_lifecycle(crop)
            result = {
                "status": lifecycle["status"],
                "expected_harvest_date": lifecycle["expected_harvest_date"],
                "days_until_harvest": lifecycle["days_until_harvest"],
                "confidence": "farmer_entered_date" if lifecycle["expected_harvest_date"] else "unavailable",
                "estimated_date_range": None,
                "planning_note": "This is a farmer-entered planning date, not a crop-duration forecast. A verified crop- and variety-specific maturity source is not configured, so CropAI does not invent a date range.",
                "limitations": lifecycle["limitations"],
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
            conn.execute("INSERT INTO advisory_records(user_id,crop_id,advisory_type,inputs,result,source_references,evidence_quality) VALUES(%s,%s,'harvest',%s::jsonb,%s::jsonb,%s::jsonb,'limited')", (user_id,crop_id,json.dumps({"expected_harvest_date":expected_date}),json.dumps(result),json.dumps([{"type":"farmer_input","field":"expected_harvest_date"}]) if expected_date else "[]"))
        return jsonify(result)
    except Exception:
        return jsonify({"error": "Harvest planning information could not be saved."}), 503


@insights_bp.get("/crops/<int:crop_id>/care-plan")
def crop_care_plan(crop_id):
    crop, error = _crop_or_404(crop_id)
    if error:
        return error
    return jsonify(build_care_plan(crop, request.args.get("user_type", "farmer")))


@insights_bp.route("/crops/<int:crop_id>/irrigation", methods=["GET", "POST"])
def crop_irrigation(crop_id):
    crop, error = _crop_or_404(crop_id)
    if error:
        return error
    payload = dict(request.args) if request.method == "GET" else request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "A JSON object is required."}), 400
    allowed = {"soil_type", "rainfall", "temperature", "forecast_rainfall", "soil_moisture_status"}
    if set(payload) - allowed:
        return jsonify({"error": "Unsupported irrigation input."}), 400
    try:
        result = recommend_irrigation(crop["crop_name"], crop.get("current_stage"), **payload)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    if request.method == "POST":
        try:
            with connection() as conn:
                conn.execute("INSERT INTO advisory_records(user_id,crop_id,advisory_type,inputs,result,source_references,evidence_quality,valid_until) VALUES(%s,%s,'irrigation',%s::jsonb,%s::jsonb,%s::jsonb,%s,NOW()+INTERVAL '1 day')", (current_user_id(),crop_id,json.dumps(payload),json.dumps(result),json.dumps(result["source_references"]),"limited" if result["evidence_quality"]=="user_input" else "insufficient"))
        except Exception:
            return jsonify({"error": "Irrigation advisory could not be saved."}), 503
    return jsonify(result)


@insights_bp.post("/advisories/irrigation")
def create_irrigation_advisory():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "A JSON object is required."}), 400
    try:
        crop_id = int(payload.get("crop_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "crop_id must be a positive integer."}), 400
    if crop_id < 1:
        return jsonify({"error": "crop_id must be a positive integer."}), 400
    crop, error = _crop_or_404(crop_id)
    if error:
        return error
    body = {key:value for key,value in payload.items() if key != "crop_id"}
    if set(body) - {"soil_type", "rainfall", "temperature", "forecast_rainfall", "soil_moisture_status"}:
        return jsonify({"error": "Unsupported irrigation input."}), 400
    try:
        result = recommend_irrigation(crop["crop_name"],crop.get("current_stage"),**body)
        with connection() as conn:
            conn.execute("INSERT INTO advisory_records(user_id,crop_id,advisory_type,inputs,result,source_references,evidence_quality,valid_until) VALUES(%s,%s,'irrigation',%s::jsonb,%s::jsonb,%s::jsonb,%s,NOW()+INTERVAL '1 day')", (current_user_id(),crop_id,json.dumps(body),json.dumps(result),json.dumps(result["source_references"]),"limited" if result["evidence_quality"]=="user_input" else "insufficient"))
        return jsonify(result), 201
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception:
        return jsonify({"error": "Irrigation advisory could not be saved."}), 503


@insights_bp.get("/irrigation-advice/<int:crop_id>")
def irrigation_advice(crop_id):
    return crop_irrigation(crop_id)


@insights_bp.post("/crops/<int:crop_id>/health")
def crop_health(crop_id):
    crop, error = _crop_or_404(crop_id)
    if error:
        return error
    payload = _payload()
    return jsonify(composite_health_score(**{key: payload[key] for key in ("risk_level", "soil_ph", "rainfall", "temperature") if key in payload}))


@insights_bp.route("/crops/<int:crop_id>/risk", methods=["GET", "POST"])
def crop_risk(crop_id):
    user_id = current_user_id()
    if user_id is None:
        return unauthorized()
    user_crop = get_owned_user_crop(crop_id, user_id)
    if user_crop is not None:
        if request.method == "GET":
            return jsonify({"items": list_crop_risks(crop_id)})
        try:
            return jsonify(run_crop_risk_analysis(crop_id, force=True)), 201
        except LookupError as error:
            return jsonify({"error": str(error)}), 404
        except Exception as error:
            return jsonify({"error": "Risk analysis is temporarily unavailable.", "details": str(error)}), 502
    crop, error = _crop_or_404(crop_id)
    if error:
        return error
    if request.method == "GET":
        return jsonify({"items": list_risk_predictions(crop_id)})

    payload = _payload()
    lifecycle = estimate_lifecycle(crop)
    result = compute_risk(
        crop=crop["crop_name"],
        growth_stage=crop.get("current_stage") or lifecycle["stage"],
        humidity=payload.get("humidity"),
        temperature=payload.get("temperature"),
        rainfall=payload.get("rainfall"),
        wind=payload.get("wind_speed"),
        soil_type=payload.get("soil_type"),
        season=crop.get("season"),
        location=payload.get("location"),
    )
    prediction = create_risk_prediction(
        {
            "crop_id": crop_id,
            "risk_type": "disease_weather",
            "risk_level": result["level"],
            "score": result["score"],
            "reasons": result["reasons"],
        }
    )
    severity = {"CRITICAL": "RED", "HIGH": "RED", "MEDIUM": "YELLOW", "LOW": "GREEN"}[result["level"]]
    alert = create_alert(
        {
            "crop_id": crop_id,
            "alert_type": "risk_prediction",
            "severity": severity,
            "title": f"{crop['crop_name']} risk estimated as {result['level']}",
            "message": " ".join(result["reasons"]),
        }
    )
    return jsonify({"prediction": prediction, "alert": alert, "explanation": result}), 201


@insights_bp.get("/alerts")
def alerts():
    user_id = current_user_id()
    if user_id is None:
        return unauthorized()
    return jsonify({"items": list_user_alerts(user_id)})


@insights_bp.get("/crops/<int:crop_id>/alerts")
def crop_alerts(crop_id):
    crop, error = _crop_or_404(crop_id)
    if error:
        return error
    return jsonify({"items": list_alerts(crop_id)})


@insights_bp.route("/alerts/<int:alert_id>/read", methods=["POST", "PATCH"])
def read_alert(alert_id):
    user_id = current_user_id()
    if user_id is None:
        return unauthorized()
    alert = mark_alert_read_owned(alert_id, user_id)
    if alert is None:
        return jsonify({"error": "Alert not found."}), 404
    return jsonify(alert)
