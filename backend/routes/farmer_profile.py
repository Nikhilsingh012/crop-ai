from flask import Blueprint, jsonify, request

from authz import current_user_id, unauthorized
from db import get_user, set_location_consent, update_farmer_profile

farmer_profile_bp = Blueprint("farmer_profile", __name__)
LANGUAGES = {"en", "hi", "hinglish"}


def _profile(user):
    return {
        key: user.get(key)
        for key in ("id", "name", "email", "user_type", "state", "district", "preferred_language", "location_consent_at")
    }


@farmer_profile_bp.route("/farmer/profile", methods=["GET", "PUT"])
def farmer_profile():
    user_id = current_user_id()
    if user_id is None:
        return unauthorized()
    user = get_user(user_id)
    if user is None:
        return unauthorized()
    if request.method == "GET":
        return jsonify(_profile(user))

    payload = request.get_json(silent=True) or {}
    fields = {"name", "state", "district", "preferred_language"}
    if set(payload) - fields - {"location_consent"}:
        return jsonify({"error": "Unsupported profile field."}), 400
    values = {}
    for key in ("name", "state", "district"):
        if key not in payload:
            continue
        value = payload[key]
        if value is None and key != "name":
            values[key] = None
            continue
        if not isinstance(value, str) or len(value.strip()) > (120 if key == "name" else 100):
            return jsonify({"error": f"'{key}' must be text within the allowed length."}), 400
        value = value.strip()
        if key == "name" and not value:
            return jsonify({"error": "Name cannot be empty."}), 400
        values[key] = value
    if "preferred_language" in payload:
        language = payload["preferred_language"]
        if language not in LANGUAGES:
            return jsonify({"error": "preferred_language must be en, hi, or hinglish."}), 400
        values["preferred_language"] = language

    if "location_consent" in payload:
        consent = payload["location_consent"]
        if not isinstance(consent, bool):
            return jsonify({"error": "location_consent must be true or false."}), 400
        set_location_consent(user_id, consent)
    updated = update_farmer_profile(user_id, values)
    return jsonify(_profile(updated or get_user(user_id)))
