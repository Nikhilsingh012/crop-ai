from datetime import date, datetime, timedelta
from decimal import Decimal
from flask import Blueprint, jsonify, request

from authz import current_user_id, forbidden, unauthorized
from db import connection
from db import get_user
from services.market_data import MarketDataError, SOURCE_URL
from services.market_ingest import refresh
from services.market_forecast import forecast_from_history
from services.market_analytics import trend_summary

markets_bp = Blueprint("markets", __name__)
ENAM_URL = "https://www.enam.gov.in/web/dashboard/trade-data"
# Freshness is derived at read time so that cached rows age naturally even if
# the scheduled importer has not run again since the observation was ingested.
FIELDS = "id,provider,commodity,variety,grade,state,district,mandi,observed_on,minimum_price,modal_price,maximum_price,arrival_quantity,arrival_unit,price_unit,source_url,source_updated_at,fetched_at,CASE WHEN observed_on >= CURRENT_DATE - 2 THEN 'fresh' ELSE 'stale' END AS freshness"
FILTERS = {"commodity": "commodity", "variety": "variety", "grade": "grade", "state": "state", "district": "district", "mandi": "mandi"}


def _filters():
    clauses, values = [], []
    for arg, col in FILTERS.items():
        value = request.args.get(arg, "").strip()
        if len(value) > 120:
            raise ValueError(f"{arg} filter is too long")
        if value:
            if arg == "mandi":
                clauses.append("LOWER(mandi) = LOWER(%s)")
                values.append(value)
            else:
                clauses.append(f"{col} ILIKE %s")
                values.append(f"%{value}%")
    for arg, op in (("date_from", ">="), ("date_to", "<=")):
        value = request.args.get(arg)
        if value:
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError(f"{arg} must use YYYY-MM-DD") from exc
            clauses.append(f"observed_on {op} %s")
            values.append(value)
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    if date_from and date_to and date_from > date_to:
        raise ValueError("date_from must be on or before date_to")
    return (" AND ".join(clauses) or "TRUE"), values


def _page():
    try:
        page = int(request.args.get("page", "1"))
        per_page = int(request.args.get("per_page", "50"))
    except ValueError as exc:
        raise ValueError("page and per_page must be integers") from exc
    if page < 1 or not 1 <= per_page <= 200:
        raise ValueError("page must be positive and per_page must be between 1 and 200")
    return page, per_page


def _select(conn, where, values, limit=None):
    sql = f"SELECT {FIELDS} FROM market_prices WHERE {where} ORDER BY observed_on DESC, fetched_at DESC"
    if limit is not None:
        sql += " LIMIT %s"
        values = [*values, limit]
    return conn.execute(sql, values).fetchall()


def _json_rows(rows):
    """Return stable ISO dates and safe JSON scalar types for database rows."""
    result = []
    for row in rows:
        item = dict(row)
        for key, value in item.items():
            if isinstance(value, datetime):
                item[key] = value.isoformat()
            elif isinstance(value, date):
                item[key] = value.isoformat()
            elif isinstance(value, Decimal):
                item[key] = str(value)
        result.append(item)
    return result


@markets_bp.get("/markets/prices")
def prices():
    try:
        where, values = _filters()
        page, per_page = _page()
        with connection() as conn:
            total = conn.execute(f"SELECT COUNT(*) AS n FROM market_prices WHERE {where}", values).fetchone()["n"]
            rows = conn.execute(f"SELECT {FIELDS} FROM market_prices WHERE {where} ORDER BY observed_on DESC, fetched_at DESC LIMIT %s OFFSET %s", [*values, per_page, (page - 1) * per_page]).fetchall()
        return jsonify({"items": _json_rows(rows), "page": page, "per_page": per_page, "total": total, "status": "available" if total else "empty", "price_note": "Observed wholesale market prices; not a guaranteed farm-gate price or MSP."})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        return jsonify({"error": "Market database is unavailable."}), 503


@markets_bp.get("/markets/history")
def history():
    try:
        where, values = _filters()
        page, per_page = _page()
        with connection() as conn:
            total = conn.execute(f"SELECT COUNT(*) AS n FROM market_prices WHERE {where}", values).fetchone()["n"]
            rows = conn.execute(f"SELECT {FIELDS} FROM market_prices WHERE {where} ORDER BY observed_on, fetched_at LIMIT %s OFFSET %s", [*values, per_page, (page - 1) * per_page]).fetchall()
        return jsonify({"items": _json_rows(rows), "page": page, "per_page": per_page, "total": total, "status": "available" if rows else "empty", "price_unit": rows[0]["price_unit"] if rows else "INR/quintal"})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        return jsonify({"error": "Market history is unavailable."}), 503


@markets_bp.get("/markets/forecast")
def forecast():
    try:
        where, values = _filters()
        if not request.args.get("commodity", "").strip() or not request.args.get("mandi", "").strip():
            return jsonify({"status": "insufficient_history", "message": "Select a commodity and mandi to evaluate a comparable price history"})
        with connection() as conn:
            rows = conn.execute(f"SELECT observed_on,AVG(modal_price) AS modal_price FROM market_prices WHERE {where} AND modal_price IS NOT NULL GROUP BY observed_on ORDER BY observed_on", values).fetchall()
        return jsonify(forecast_from_history(rows))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        return jsonify({"error": "Market forecast is unavailable."}), 503


@markets_bp.get("/markets/trends")
def trends():
    try:
        where, values = _filters()
        if not request.args.get("commodity", "").strip() or not request.args.get("mandi", "").strip():
            return jsonify({"status": "selection_required", "points": [], "changes_percent": {"daily_change": None, "7_day": None, "30_day": None}, "seasonal_comparison": None, "seasonal_status": "insufficient_history", "message": "Select a commodity and mandi to compare observations from the same market."})
        with connection() as conn:
            rows = _select(conn, where, values, limit=5000)
        grain = {(r["variety"], r["grade"], r["price_unit"]) for r in rows}
        if len(grain) > 1:
            return jsonify({"status": "selection_required", "points": [], "changes_percent": {"daily_change": None, "7_day": None, "30_day": None}, "seasonal_comparison": None, "seasonal_status": "insufficient_history", "message": "Select one variety and grade to keep the history comparable."})
        by_day = {}
        for row in rows:
            by_day.setdefault(row["observed_on"], []).append(row)
        points = []
        for day in sorted(by_day):
            vals = [float(r["modal_price"]) for r in by_day[day] if r["modal_price"] is not None]
            if vals:
                points.append({"date": day.isoformat(), "modal_price": round(sum(vals) / len(vals), 2)})
        changes = trend_summary(points)
        seasonal = None
        if points:
            newest = date.fromisoformat(points[-1]["date"])
            candidates = [(abs((date.fromisoformat(p["date"]) - (newest - timedelta(days=365))).days), p) for p in points[:-1] if 350 <= (newest - date.fromisoformat(p["date"])).days <= 380]
            if candidates:
                _, prior = min(candidates, key=lambda item: item[0])
                if prior["modal_price"]:
                    seasonal = {"comparison_date": prior["date"], "change_percent": round((points[-1]["modal_price"] / prior["modal_price"] - 1) * 100, 2), "method": "nearest observation 350–380 days earlier"}
        return jsonify({"status": "available" if points else "empty", "points": points, "changes_percent": changes, "seasonal_comparison": seasonal, "seasonal_status": "available" if seasonal else "insufficient_history", "method": "Mean modal price per observed date for selected comparable grain and mandi"})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        return jsonify({"error": "Market trend calculation is unavailable."}), 503


@markets_bp.post("/markets/compare")
def compare():
    body = request.get_json(silent=True) or {}
    commodity = str(body.get("commodity", "")).strip()
    if not commodity or len(commodity) > 120:
        return jsonify({"error": "A valid commodity is required"}), 400
    filters = {key: str(body.get(key, "")).strip() for key in ("variety", "grade", "state", "district")}
    if any(len(value) > 120 for value in filters.values()):
        return jsonify({"error": "Filters are too long"}), 400
    clauses = ["commodity ILIKE %s", "modal_price IS NOT NULL"]
    values = [f"%{commodity}%"]
    for column, value in filters.items():
        if value:
            clauses.append(f"{column} ILIKE %s")
            values.append(f"%{value}%")
    for arg, operator in (("date_from", ">="), ("date_to", "<=")):
        value = str(body.get(arg, "")).strip()
        if value:
            try: date.fromisoformat(value)
            except ValueError: return jsonify({"error": f"{arg} must use YYYY-MM-DD"}), 400
            clauses.append(f"observed_on {operator} %s")
            values.append(value)
    try:
        with connection() as conn:
            rows = conn.execute(f"SELECT {FIELDS} FROM market_prices WHERE {' AND '.join(clauses)} ORDER BY observed_on DESC LIMIT 1000", values).fetchall()
        grains = {(row["variety"], row["grade"], row["price_unit"]) for row in rows}
        if len(grains) > 1:
            return jsonify({"items": [], "status": "selection_required", "message": "Select one variety and grade before ranking comparable mandis."})
        by_date = {}
        for row in rows:
            by_date.setdefault(row["observed_on"], {}).setdefault(row["mandi"], row)
        shared_dates = [day for day, markets in by_date.items() if len(markets) >= 2]
        ranked = sorted(by_date[max(shared_dates)].values(), key=lambda r: float(r["modal_price"])) if shared_dates else []
        return jsonify({"items": _json_rows(ranked), "status": "available" if ranked else "empty", "comparison_note": "Mandis are ranked only on their latest shared observation date, for the selected matching commodity, variety, grade and unit."})
    except Exception:
        return jsonify({"error": "Comparable mandi prices are unavailable."}), 503


@markets_bp.get("/markets/status")
def status():
    try:
        with connection() as conn:
            summary = conn.execute("SELECT COUNT(*) AS records, MAX(observed_on) AS newest_observation, MAX(fetched_at) AS last_fetched FROM market_prices WHERE provider='data.gov.in/AGMARKNET'").fetchone()
            run = conn.execute("SELECT status,started_at,completed_at,records_fetched,records_upserted,latest_observed_on,error_message FROM market_ingestion_runs ORDER BY id DESC LIMIT 1").fetchone()
        import os
        normalized_summary = _json_rows([summary])[0]
        normalized_run = _json_rows([run])[0] if run else None
        return jsonify({"provider": "data.gov.in AGMARKNET", "configured": bool(os.getenv("DATA_GOV_IN_API_KEY", "").strip()), "records": normalized_summary["records"], "newest_observation": normalized_summary["newest_observation"], "last_fetched": normalized_summary["last_fetched"], "last_ingestion": normalized_run, "source_url": SOURCE_URL, "e_nam": {"automated_api_verified": False, "official_reference_url": ENAM_URL}, "refresh": {"method": "manual/scheduled backend command", "command": "python -m services.market_ingest (from backend/)"}, "freshness_policy": "Fresh means observed within 2 calendar days; status is recalculated from the observation date at read time."})
    except Exception:
        return jsonify({"error": "Market status is unavailable."}), 503


@markets_bp.post("/markets/sync")
def sync():
    user_id = current_user_id()
    if user_id is None:
        return unauthorized()
    user = get_user(user_id)
    if user is None or not user.get("is_admin"):
        return forbidden()
    try:
        return jsonify(refresh())
    except MarketDataError as exc:
        return jsonify({"error": str(exc), "status": "failed"}), 502
    except Exception:
        return jsonify({"error": "Market sync failed; inspect the backend ingestion log.", "status": "failed"}), 503


@markets_bp.get("/markets/options")
def options():
    try:
        with connection() as conn:
            commodities = conn.execute("SELECT DISTINCT commodity FROM market_prices ORDER BY commodity LIMIT 2000").fetchall()
            states = conn.execute("SELECT DISTINCT state FROM market_prices WHERE state IS NOT NULL ORDER BY state LIMIT 1000").fetchall()
            varieties = conn.execute("SELECT DISTINCT variety FROM market_prices WHERE variety IS NOT NULL ORDER BY variety LIMIT 2000").fetchall()
            grades = conn.execute("SELECT DISTINCT grade FROM market_prices WHERE grade IS NOT NULL ORDER BY grade LIMIT 500").fetchall()
        return jsonify({"commodities": [r["commodity"] for r in commodities], "states": [r["state"] for r in states], "varieties": [r["variety"] for r in varieties], "grades": [r["grade"] for r in grades]})
    except Exception:
        return jsonify({"error": "Market filter options are unavailable."}), 503
