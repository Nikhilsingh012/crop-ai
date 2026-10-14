from flask import Blueprint, jsonify

from authz import current_user_id, unauthorized
from db import recent_scans

history_bp = Blueprint("history", __name__)


@history_bp.get("/history")
def history():
    user_id = current_user_id()
    if user_id is None:
        return unauthorized()
    try:
        rows = recent_scans(user_id)
        return jsonify({"items": rows})
    except Exception:
        return jsonify({"error": "Database unavailable."}), 503
