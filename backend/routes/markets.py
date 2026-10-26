from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from collections import defaultdict, deque
import os
import threading
import time
from flask import Blueprint, jsonify, request

from authz import current_user_id, forbidden, unauthorized
from db import connection
from db import get_user
from services.market_data import MarketDataError, SOURCE_URL, fetch_records
from services.market_estimate import calculate_gross_values, decimal_strings, parse_quantity
from services.market_ingest import refresh
from services.market_forecast import forecast_from_history
from services.market_analytics import trend_summary

markets_bp = Blueprint("markets", __name__)
ENAM_URL = "https://www.enam.gov.in/web/dashboard/trade-data"
# Freshness is derived at read time so that cached rows age naturally even if
# the scheduled importer has not run again since the observation was ingested.
FIELDS = "id,provider,commodity,variety,grade,state,district,mandi,observed_on,minimum_price,modal_price,maximum_price,arrival_quantity,arrival_unit,price_unit,source_url,source_updated_at,fetched_at,CASE WHEN observed_on >= CURRENT_DATE - 2 THEN 'fresh' ELSE 'stale' END AS freshness"
FILTERS = {"commodity": "commodity", "variety": "variety", "grade": "grade", "state": "state", "district": "district", "mandi": "mandi"}
_quote_requests = defaultdict(deque)
_quote_lock = threading.Lock()
_STATE_ALIASES = {"gujrat": "Gujarat", "orissa": "Odisha"}


def _canonical_feed_label(value):
    """Normalize common case and spelling variations to feed labels."""
    cleaned = value.strip()
    if not cleaned:
        return cleaned
    return _STATE_ALIASES.get(cleaned.casefold(), cleaned.title())


def _quote_rate_limited():
    now = time.monotonic()
    address = request.remote_addr or "unknown"
    limit = max(1, min(120, int(os.getenv("MARKET_QUERY_RATE_LIMIT_PER_MINUTE", "20"))))
    with _quote_lock:
        recent = _quote_requests[address]
        while recent and now - recent[0] >= 60:
            recent.popleft()
        if len(recent) >= limit:
            return True, max(1, int(60 - (now - recent[0])))
        recent.append(now)
    return False, 0


def _stored_market_records(commodity, state="", district="", market="", variety=""):
    """Read the latest stored AGMARKNET observations for one commodity.

    The daily feed is ingested into PostgreSQL so the Mandi page stays usable
    when data.gov.in is rate-limited, slow, or temporarily offline. Exact
    case-insensitive matching keeps results comparable with the live query.
    """
    clauses = ["provider = 'data.gov.in/AGMARKNET'", "LOWER(commodity) = LOWER(%s)"]
    values = [commodity]
    for column, value in (("state", state), ("district", district), ("mandi", market), ("variety", variety)):
        if value:
            clauses.append(f"LOWER({column}) = LOWER(%s)")
            values.append(value)
    with connection() as conn:
        rows = conn.execute(
            "SELECT commodity,variety,grade,state,district,mandi,observed_on,minimum_price,"
            "modal_price,maximum_price,price_unit,source_url,fetched_at "
            f"FROM market_prices WHERE {' AND '.join(clauses)} "
            "ORDER BY observed_on DESC, fetched_at DESC LIMIT 20000",
            values,
        ).fetchall()
    today = date.today()
    return [{
        "provider": "data.gov.in/AGMARKNET",
        "commodity": row["commodity"], "variety": row["variety"], "grade": row["grade"],
        "state": row["state"], "district": row["district"], "mandi": row["mandi"],
        "observed_on": row["observed_on"], "minimum_price": row["minimum_price"],
        "modal_price": row["modal_price"], "maximum_price": row["maximum_price"],
        "price_unit": row["price_unit"], "source_url": row["source_url"],
        "fetched_at": row["fetched_at"],
        "freshness": "fresh" if (today - row["observed_on"]).days <= 2 else "stale",
    } for row in rows]


@markets_bp.get("/markets/estimate")
def estimate():
    """Use stored AGMARKNET observations, then the live provider as a fallback."""
    commodity = _canonical_feed_label(request.args.get("commodity", ""))
    state = _canonical_feed_label(request.args.get("state", ""))
    district = _canonical_feed_label(request.args.get("district", ""))
    market = _canonical_feed_label(request.args.get("market", ""))
    variety = _canonical_feed_label(request.args.get("variety", ""))
    if not commodity:
        return jsonify({"error": "commodity is required."}), 400
    if any(len(value) > 120 for value in (commodity, state, district, market, variety)):
        return jsonify({"error": "Crop and location fields must be 120 characters or fewer."}), 400
    try:
        quantity, quantity_kg = parse_quantity(request.args.get("quantity", ""), request.args.get("unit", ""))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    limited, retry_after = _quote_rate_limited()
    if limited:
        response = jsonify({"error": "Market price refresh limit reached. Wait a moment before trying again."})
        response.headers["Retry-After"] = str(retry_after)
        return response, 429

    matched = []
    served_from = "stored"
    try:
        matched = _stored_market_records(commodity, state, district, market, variety)
    except Exception:
        matched = []

    if not matched:
        served_from = "live"
        try:
            provider_filters = {"commodity": commodity}
            if state:
                provider_filters["state"] = state
            if district:
                provider_filters["district"] = district
            if market:
                provider_filters["market"] = market
            if variety:
                provider_filters["variety"] = variety
            provider_records = fetch_records(
                filters=provider_filters,
                max_records=max(1, min(100000, int(os.getenv("MARKET_QUERY_MAX_RECORDS", "10000")))),
            )
        except (MarketDataError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 502
        except Exception:
            return jsonify({"error": "The market data provider is temporarily unavailable. Please try again later."}), 502

        def same(left, right):
            return str(left or "").strip().casefold() == str(right or "").strip().casefold()

        matched = [record for record in provider_records if same(record["commodity"], commodity)
                   and (not state or same(record["state"], state))
                   and (not district or same(record["district"], district))]
        if market:
            matched = [record for record in matched if same(record["mandi"], market)]
        if variety:
            matched = [record for record in matched if same(record["variety"], variety)]

    # Collapse exact duplicate feed rows. If identical market/day/grain rows
    # disagree on prices, omit that ambiguous group instead of guessing.
    grouped = {}
    ambiguous = set()
    for record in matched:
        key = (record["commodity"].casefold(), (record["variety"] or "").casefold(), (record["grade"] or "").casefold(), record["state"].casefold(), record["district"].casefold(), record["mandi"].casefold(), record["observed_on"])
        prices = (record["minimum_price"], record["modal_price"], record["maximum_price"])
        if key in grouped and grouped[key][0] != prices:
            ambiguous.add(key)
        else:
            grouped[key] = (prices, record)
    unambiguous = [value[1] for key, value in grouped.items() if key not in ambiguous]
    # Compare the latest available observation for each market/grain, not a
    # mix of historical dates returned in the provider's daily resource.
    latest_by_market_grain = {}
    for record in unambiguous:
        key = (record["mandi"].casefold(), (record["variety"] or "").casefold(), (record["grade"] or "").casefold())
        if key not in latest_by_market_grain or record["observed_on"] > latest_by_market_grain[key]["observed_on"]:
            latest_by_market_grain[key] = record
    records = list(latest_by_market_grain.values())
    if not records:
        message = "No unambiguous reported prices matched this crop and location. Check the spelling or try another variety or mandi."
        return jsonify({
            "status": "empty", "provider": "data.gov.in AGMARKNET", "source_url": SOURCE_URL,
            "served_from": served_from,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "query": {"commodity": commodity, "state": state or None, "district": district or None, "market": market or None, "variety": variety or None, "quantity": format(quantity, "f"), "unit": request.args.get("unit"), "quantity_kg": format(quantity_kg, "f")},
            "comparison_note": None, "message": message, "items": [],
            "price_note": "No matching reported prices were returned, so no harvest value was estimated.",
        }), 200, {"Cache-Control": "no-store"}

    quantity_wire = format(quantity, "f")
    results = []
    for record in records:
        values = calculate_gross_values(quantity_kg, record["minimum_price"], record["modal_price"], record["maximum_price"])
        results.append({
            "commodity": record["commodity"], "variety": record["variety"], "grade": record["grade"],
            "state": record["state"], "district": record["district"], "market": record["mandi"],
            "reporting_date": record["observed_on"].isoformat(),
            "minimum_price": str(record["minimum_price"]) if record["minimum_price"] is not None else None,
            "modal_price": str(record["modal_price"]) if record["modal_price"] is not None else None,
            "maximum_price": str(record["maximum_price"]) if record["maximum_price"] is not None else None,
            "source_price_unit": record["price_unit"], "source": record["provider"],
            "source_url": record["source_url"], "fetched_at": record["fetched_at"].isoformat(),
            "freshness": record["freshness"], "stale": record["freshness"] == "stale",
            "quantity": quantity_wire, "quantity_unit": request.args.get("unit"),
            "quantity_kg": format(quantity_kg, "f"), "normalized_price_unit": "INR/kg",
            **decimal_strings(values),
        })
    results.sort(key=lambda row: (row["modal_price"] is not None, Decimal(row["modal_price"] or "0")), reverse=True)
    varieties = {row["variety"] for row in results if row["variety"]}
    grades = {row["grade"] for row in results if row["grade"]}
    reporting_dates = {row["reporting_date"] for row in results}
    comparison_note = None
    if len(varieties) > 1 or len(grades) > 1:
        comparison_note = "Results include multiple varieties or grades and may not be directly comparable. Markets may also report on different dates. The highest modal price does not account for transport, quality requirements, or selling conditions."
    elif len(reporting_dates) > 1:
        comparison_note = "Markets reported on different dates, so the figures may not be directly comparable. The highest modal price does not account for transport, quality requirements, or selling conditions."
    return jsonify({
        "status": "available", "provider": "data.gov.in AGMARKNET", "source_url": SOURCE_URL,
        "served_from": served_from,
        "retrieved_at": max(row["fetched_at"] for row in results),
        "query": {"commodity": commodity, "state": state or None, "district": district or None, "market": market or None, "variety": variety or None, "quantity": quantity_wire, "unit": request.args.get("unit"), "quantity_kg": format(quantity_kg, "f")},
        "comparison_note": comparison_note,
        "items": results,
        "price_note": "Gross estimates use reported INR/quintal prices and do not deduct costs. Modal-price estimates are unavailable when the provider has no modal price.",
    }), 200, {"Cache-Control": "no-store"}


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
    state = request.args.get("state", "").strip()
    district = request.args.get("district", "").strip()
    if len(state) > 120 or len(district) > 120:
        return jsonify({"error": "Location filters must be 120 characters or fewer."}), 400
    try:
        with connection() as conn:
            commodities = conn.execute("SELECT DISTINCT commodity FROM market_prices ORDER BY commodity LIMIT 2000").fetchall()
            states = conn.execute("SELECT DISTINCT state FROM market_prices WHERE state IS NOT NULL ORDER BY state LIMIT 1000").fetchall()
            varieties = conn.execute("SELECT DISTINCT variety FROM market_prices WHERE variety IS NOT NULL ORDER BY variety LIMIT 2000").fetchall()
            grades = conn.execute("SELECT DISTINCT grade FROM market_prices WHERE grade IS NOT NULL ORDER BY grade LIMIT 500").fetchall()
            location_conditions, location_values = [], []
            if state:
                location_conditions.append("state ILIKE %s")
                location_values.append(state)
            if district:
                location_conditions.append("district ILIKE %s")
                location_values.append(district)
            location_where = " AND ".join(location_conditions) or "TRUE"
            districts = conn.execute(f"SELECT DISTINCT district FROM market_prices WHERE district IS NOT NULL AND {('state ILIKE %s' if state else 'TRUE')} ORDER BY district LIMIT 1500", [state] if state else []).fetchall()
            markets = conn.execute(f"SELECT DISTINCT mandi FROM market_prices WHERE mandi IS NOT NULL AND {location_where} ORDER BY mandi LIMIT 2000", location_values).fetchall()
            coverage = conn.execute("SELECT COUNT(*) AS records, MAX(observed_on) AS newest_observation, MAX(fetched_at) AS last_fetched FROM market_prices WHERE provider='data.gov.in/AGMARKNET'").fetchone()
        coverage = _json_rows([coverage])[0] if coverage else {}
        return jsonify({
            "commodities": [r["commodity"] for r in commodities],
            "states": [r["state"] for r in states],
            "districts": [r["district"] for r in districts],
            "markets": [r["mandi"] for r in markets],
            "varieties": [r["variety"] for r in varieties],
            "grades": [r["grade"] for r in grades],
            "coverage": coverage,
            "status": "available" if commodities else "empty",
        })
    except Exception:
        return jsonify({"error": "Market filter options are unavailable."}), 503
