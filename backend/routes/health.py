from flask import Blueprint, jsonify
from db import connection

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health_check():
    try:
        with connection() as conn:
            conn.execute("SELECT 1")
        database = "ok"
    except Exception:
        database = "unavailable"
    return jsonify({"status": "ok", "service": "crop-disease-ai", "database": database})
