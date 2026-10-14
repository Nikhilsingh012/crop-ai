from flask import Blueprint, jsonify, request, session

from db import delete_user_location, get_user, get_user_location, save_user_location, set_location_consent

location_bp = Blueprint("location", __name__)


def _current_user():
    user_id = session.get("user_id")
    return user_id if user_id and get_user(user_id) else None


@location_bp.route("/location", methods=["GET", "POST", "DELETE"])
def location():
    user_id = _current_user()
    if user_id is None:
        return jsonify({"error": "Sign in before managing your location."}), 401
    if request.method == "GET":
        return jsonify(get_user_location(user_id) or {})
    if request.method == "DELETE":
        delete_user_location(user_id)
        set_location_consent(user_id, False)
        return jsonify({"deleted": True})
    user = get_user(user_id)
    if not user or not user.get("location_consent_at"):
        return jsonify({"error": "Save location consent before storing coordinates."}), 403

    payload = request.get_json(silent=True) or {}
    try:
        latitude = float(payload["latitude"])
        longitude = float(payload["longitude"])
        accuracy = float(payload["accuracy"]) if payload.get("accuracy") is not None else None
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "Valid latitude and longitude are required."}), 400
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return jsonify({"error": "Latitude or longitude is outside the valid range."}), 400
    return jsonify(save_user_location(user_id, {
        "latitude": latitude,
        "longitude": longitude,
        "location_name": payload.get("location_name"),
        "accuracy": accuracy,
    })), 200
