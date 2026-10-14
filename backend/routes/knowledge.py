from flask import Blueprint, jsonify, request
from authz import current_user_id, unauthorized, forbidden
from db import get_user

from db import create_feedback, list_feedback
from services.crop_knowledge import get_crop_knowledge, list_crop_knowledge
from services.recommendation import recommend_crops

knowledge_bp = Blueprint("knowledge", __name__)


@knowledge_bp.get("/knowledge/crops")
def crop_knowledge():
    crop_name = request.args.get("crop")
    if crop_name:
        crop = get_crop_knowledge(crop_name)
        if crop is None:
            return jsonify({"error": "Crop knowledge is not available in the seed dataset."}), 404
        return jsonify(crop)
    return jsonify({"items": list_crop_knowledge()})


@knowledge_bp.post("/recommendations/crops")
def crop_recommendations():
    payload = request.get_json(silent=True) or {}
    return jsonify({"items": recommend_crops(**{key: payload[key] for key in ("state", "season", "soil_ph", "water_availability") if key in payload})})


@knowledge_bp.route("/feedback", methods=["GET", "POST"])
def feedback():
    if request.method == "GET":
        user_id = current_user_id()
        if not user_id:
            return unauthorized()
        user = get_user(user_id)
        if not user or not user.get("is_admin"):
            return forbidden()
        return jsonify({"items": list_feedback()})
    payload = request.get_json(silent=True) or {}
    required = next((key for key in ("feedback_type", "rating") if payload.get(key) in (None, "")), None)
    if required:
        return jsonify({"error": f"'{required}' is required."}), 400
    if payload["rating"] not in {"yes", "no", "correct", "incorrect", "not_sure"}:
        return jsonify({"error": "Unsupported feedback rating."}), 400
    values = {key: payload[key] for key in ("feedback_type", "reference_id", "rating", "notes") if key in payload}
    return jsonify(create_feedback(values)), 201
