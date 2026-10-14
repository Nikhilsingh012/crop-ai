from flask import Blueprint, jsonify, request

from authz import current_user_id, forbidden, unauthorized
from db import connection, get_user, summary_counts
from services.source_monitor import SOURCES, check_official_sources

admin_bp = Blueprint("admin", __name__)


@admin_bp.get("/admin/summary")
def admin_summary():
    user_id = current_user_id()
    if user_id is None:
        return unauthorized()
    user = get_user(user_id)
    if user is None or not user.get("is_admin"):
        return forbidden()
    return jsonify({"metrics": summary_counts(), "note": "Model accuracy metrics are not reported until evaluation data exists."})


def _admin_id():
    user_id = current_user_id()
    if user_id is None:
        return None, unauthorized()
    user = get_user(user_id)
    if user is None or not user.get("is_admin"):
        return None, forbidden()
    return user_id, None


@admin_bp.get("/admin/source-runs")
def source_runs():
    _, error = _admin_id()
    if error:
        return error
    try:
        with connection() as conn:
            rows = conn.execute("SELECT source_key,started_at,finished_at,result,error_code,records_seen,details FROM source_runs ORDER BY started_at DESC LIMIT 100").fetchall()
        return jsonify({"items": rows})
    except Exception:
        return jsonify({"error":"Source run history is unavailable."}),503


@admin_bp.post("/admin/sources/check")
def check_sources():
    _, error = _admin_id()
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    keys = payload.get("source_keys")
    if keys is not None and (not isinstance(keys,list) or not all(isinstance(key,str) for key in keys)):
        return jsonify({"error":"source_keys must be a list of allowlisted source keys."}),400
    try:
        return jsonify({"items":check_official_sources(keys),"note":"Content changes are flagged for human review; source-page changes do not automatically update scheme eligibility or deadlines."})
    except ValueError as error:
        return jsonify({"error":str(error)}),400
    except Exception:
        return jsonify({"error":"Source check could not be completed."}),503
