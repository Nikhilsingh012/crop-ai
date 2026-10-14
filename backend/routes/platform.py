"""Evidence-aware platform APIs for plans, farm economics and official scheme entry points."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256

from flask import Blueprint, jsonify, request
import json
from psycopg.types.json import Jsonb

from authz import current_user_id, unauthorized
from db import connection
from services.finance import FinanceInputError, calculate_finance, decimal_value, quantity_unit
from services.action_plan import daily_actions
from services.scheme_matcher import match_scheme

platform_bp = Blueprint("platform", __name__)

def _user():
    user_id = current_user_id()
    return user_id, None if user_id else unauthorized()


def _db_error(error):
    return jsonify({"error": "The database is unavailable; this request was not saved.", "code": "database_unavailable"}), 503


def _safe(value):
    if isinstance(value, Decimal): return str(value)
    if isinstance(value, (date, datetime)): return value.isoformat()
    if isinstance(value, dict): return {key: _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)): return [_safe(item) for item in value]
    return value


@platform_bp.get("/schemes")
def schemes():
    """Search the maintained scheme registry; do not synthesize current status."""
    query = request.args.get("q", "").strip()
    level = request.args.get("level", "").strip().lower()
    state = request.args.get("state", "").strip()
    verification = request.args.get("verification_status", "").strip().lower()
    app_status = request.args.get("application_status", "").strip().lower()
    if len(query) > 120 or len(state) > 100:
        return jsonify({"error": "Search filters are too long."}), 400
    if level and level not in {"central", "state"}:
        return jsonify({"error": "level must be central or state."}), 400
    if verification and verification not in {"verified", "stale", "unverified"}:
        return jsonify({"error": "Unsupported verification_status."}), 400
    if app_status and app_status not in {"open", "closed", "continuous", "unknown"}:
        return jsonify({"error": "Unsupported application_status."}), 400
    try:
        page = int(request.args.get("page", "1")); per_page = int(request.args.get("per_page", "20"))
    except ValueError:
        return jsonify({"error": "page and per_page must be integers."}), 400
    if page < 1 or not 1 <= per_page <= 100:
        return jsonify({"error": "page must be positive and per_page between 1 and 100."}), 400
    clauses, values = [], []
    verification_expr = "CASE WHEN verification_status='verified' AND (last_checked_at IS NULL OR last_checked_at < NOW() - INTERVAL '180 days') THEN 'stale' ELSE verification_status END"
    for col, value in (("government_level", level), ("application_status", app_status)):
        if value:
            clauses.append(f"{col}=%s"); values.append(value)
    if verification:
        clauses.append(f"{verification_expr}=%s"); values.append(verification)
    if query:
        clauses.append("(official_name ILIKE %s OR COALESCE(description,'') ILIKE %s)")
        values.extend((f"%{query}%", f"%{query}%"))
    if state:
        clauses.append("(state_scope IS NULL OR EXISTS (SELECT 1 FROM unnest(state_scope) scope_name WHERE scope_name ILIKE %s))")
        values.append(state)
    where = " AND ".join(clauses) or "TRUE"
    fields = f"scheme_id,official_name,government_level,state_scope,official_source_url,official_application_url,description,eligibility_rules,exclusion_rules,benefit_description,document_checklist,application_procedure,application_open_date,deadline,date_precision,application_status,source_published_at,last_checked_at,{verification_expr} AS verification_status,evidence_notes,updated_at"
    try:
        with connection() as conn:
            total = conn.execute(f"SELECT COUNT(*) AS n FROM schemes WHERE {where}", values).fetchone()["n"]
            rows = conn.execute(f"SELECT {fields} FROM schemes WHERE {where} ORDER BY official_name LIMIT %s OFFSET %s", [*values, per_page, (page-1)*per_page]).fetchall()
        items = []
        for row in rows:
            item = _safe(row)
            item["level"] = item["government_level"]
            item["url"] = item["official_source_url"]
            items.append(item)
        return jsonify({"items": items, "page": page, "per_page": per_page, "total": total})
    except Exception as exc:
        return _db_error(exc)


@platform_bp.get("/schemes/<scheme_id>")
def scheme_detail(scheme_id):
    if len(scheme_id) > 80:
        return jsonify({"error": "Invalid scheme identifier."}), 400
    try:
        with connection() as conn:
            row = conn.execute("SELECT scheme_id,official_name,government_level,state_scope,official_source_url,official_application_url,description,eligibility_rules,exclusion_rules,benefit_description,document_checklist,application_procedure,application_open_date,deadline,date_precision,application_status,source_published_at,last_checked_at,CASE WHEN verification_status='verified' AND (last_checked_at IS NULL OR last_checked_at < NOW() - INTERVAL '180 days') THEN 'stale' ELSE verification_status END AS verification_status,evidence_notes,updated_at FROM schemes WHERE scheme_id=%s", (scheme_id,)).fetchone()
            updates = conn.execute("SELECT id,changed_fields,previous_values,current_values,evidence_url,recorded_at FROM scheme_updates WHERE scheme_id=%s ORDER BY recorded_at DESC LIMIT 20", (scheme_id,)).fetchall() if row else []
        if not row:
            return jsonify({"error": "Scheme not found."}), 404
        return jsonify({"scheme": _safe(row), "updates": _safe(updates)})
    except Exception as exc:
        return _db_error(exc)


@platform_bp.get("/schemes/updates")
def scheme_updates():
    try:
        page = int(request.args.get("page", "1")); per_page = int(request.args.get("per_page", "20"))
    except ValueError:
        return jsonify({"error": "page and per_page must be integers."}), 400
    if page < 1 or not 1 <= per_page <= 100:
        return jsonify({"error": "page must be positive and per_page between 1 and 100."}), 400
    try:
        with connection() as conn:
            rows = conn.execute("SELECT u.id,u.scheme_id,s.official_name,u.changed_fields,u.previous_values,u.current_values,u.evidence_url,u.recorded_at FROM scheme_updates u JOIN schemes s USING(scheme_id) ORDER BY u.recorded_at DESC LIMIT %s OFFSET %s", (per_page, (page-1)*per_page)).fetchall()
            total = conn.execute("SELECT COUNT(*) AS n FROM scheme_updates").fetchone()["n"]
        return jsonify({"items": _safe(rows), "page": page, "per_page": per_page, "total": total})
    except Exception as exc:
        return _db_error(exc)


@platform_bp.get("/schemes/deadlines")
def scheme_deadlines():
    try:
        with connection() as conn:
            rows = conn.execute("SELECT scheme_id,official_name,deadline,date_precision,application_status,verification_status,last_checked_at,official_application_url FROM schemes WHERE deadline IS NOT NULL AND verification_status='verified' AND last_checked_at>=NOW()-INTERVAL '180 days' AND deadline>=CURRENT_DATE ORDER BY deadline,official_name LIMIT 200").fetchall()
        return jsonify({"items": _safe(rows), "note": "Only future deadlines from verified records are listed. An empty list means no verified upcoming deadline is recorded."})
    except Exception as exc:
        return _db_error(exc)


@platform_bp.route("/schemes/saved", methods=["GET", "POST"])
def saved_schemes():
    user_id, error = _user()
    if error: return error
    p = request.get_json(silent=True) or {}
    try:
        with connection() as conn:
            if request.method == "GET":
                rows=conn.execute("SELECT s.scheme_id,s.official_name,s.official_source_url,s.application_status,s.verification_status,ss.checklist_state,ss.saved_at FROM saved_schemes ss JOIN schemes s USING(scheme_id) WHERE ss.user_id=%s ORDER BY ss.saved_at DESC",(user_id,)).fetchall()
                return jsonify({"items":_safe(rows)})
            scheme_id=p.get("scheme_id")
            if not isinstance(scheme_id,str) or len(scheme_id)>80: return jsonify({"error":"scheme_id is required."}),400
            if not conn.execute("SELECT 1 FROM schemes WHERE scheme_id=%s",(scheme_id,)).fetchone(): return jsonify({"error":"Scheme not found."}),404
            row=conn.execute("INSERT INTO saved_schemes(user_id,scheme_id) VALUES(%s,%s) ON CONFLICT(user_id,scheme_id) DO UPDATE SET saved_at=NOW() RETURNING scheme_id,saved_at",(user_id,scheme_id)).fetchone()
        return jsonify(_safe(row)),201
    except Exception as exc: return _db_error(exc)


@platform_bp.delete("/schemes/saved/<scheme_id>")
def unsave_scheme(scheme_id):
    user_id,error=_user()
    if error: return error
    try:
        with connection() as conn:
            count=conn.execute("DELETE FROM saved_schemes WHERE user_id=%s AND scheme_id=%s",(user_id,scheme_id)).rowcount
        return ("",204) if count else (jsonify({"error":"Saved scheme not found."}),404)
    except Exception as exc: return _db_error(exc)


@platform_bp.post("/schemes/match")
def match_schemes():
    user_id, error = _user()
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict) or set(payload) - {"answers"}:
        return jsonify({"error": "Only self-reported answers may be provided."}), 400
    answers = payload.get("answers", {})
    if not isinstance(answers, dict) or len(answers) > 100:
        return jsonify({"error": "answers must be an object with at most 100 fields."}), 400
    if any(not isinstance(key, str) or len(key) > 100 or (value is not None and not isinstance(value, bool)) for key, value in answers.items()):
        return jsonify({"error": "Each answer must be a boolean or null."}), 400
    try:
        with connection() as conn:
            user = conn.execute("SELECT state,district,user_type FROM users WHERE id=%s", (user_id,)).fetchone()
            rows = conn.execute("SELECT scheme_id,official_name,official_source_url,official_application_url,eligibility_rules,exclusion_rules,state_scope,deadline,application_status,verification_status,last_checked_at FROM schemes ORDER BY official_name").fetchall()
    except Exception as exc:
        return _db_error(exc)
    screening = [match_scheme(row, answers, user["state"] if user else None) for row in rows]
    return jsonify({"status": "available" if screening else "unavailable", "results": screening, "summary": "Screening uses verified published rules and only the answers you supplied. It is not an approval or benefit guarantee; confirm with the official authority.", "answers_saved": False})


@platform_bp.patch("/schemes/saved/<scheme_id>")
def update_saved_scheme(scheme_id):
    user_id, error = _user()
    if error: return error
    payload = request.get_json(silent=True) or {}
    checklist = payload.get("checklist_state")
    if set(payload) != {"checklist_state"} or not isinstance(checklist, dict) or len(checklist) > 100:
        return jsonify({"error": "checklist_state must be an object with at most 100 entries."}), 400
    if any(not isinstance(key, str) or not key.strip() or len(key) > 160 or not isinstance(value, bool) for key, value in checklist.items()):
        return jsonify({"error": "Checklist entries need a short label and a true/false value."}), 400
    try:
        with connection() as conn:
            row = conn.execute("UPDATE saved_schemes SET checklist_state=checklist_state || %s::jsonb WHERE user_id=%s AND scheme_id=%s RETURNING scheme_id,checklist_state,saved_at", (json.dumps(checklist), user_id, scheme_id)).fetchone()
        return (jsonify(_safe(row)), 200) if row else (jsonify({"error": "Save this scheme before updating its checklist."}), 404)
    except Exception as exc:
        return _db_error(exc)


@platform_bp.get("/tasks")
def tasks():
    user_id, error = _user()
    if error:
        return error
    try:
        with connection() as conn:
            rows = conn.execute("SELECT id, farm_id, crop_id, title, recommendation, priority, due_date, reason, source_references, evidence_quality, valid_until, state, feedback, created_at FROM farm_tasks WHERE user_id=%s ORDER BY (state='open') DESC, due_date NULLS LAST, created_at DESC", (user_id,)).fetchall()
        return jsonify({"items": _safe(rows)})
    except Exception as exc:
        return _db_error(exc)


@platform_bp.get("/farm/actions/today")
def daily_action_plan():
    user_id,error=_user()
    if error: return error
    today=datetime.now(timezone.utc).date()
    try:
        with connection() as conn:
            user=conn.execute("SELECT user_type FROM users WHERE id=%s",(user_id,)).fetchone()
            crops=conn.execute("SELECT c.id AS crop_id,c.crop_name,c.variety,c.season,c.sowing_date,c.expected_harvest_date,c.current_stage,c.status,fm.id AS farm_id,fm.name AS farm_name,fi.area_acres,fi.soil_type,fi.irrigation_type FROM crops c JOIN fields fi ON fi.id=c.field_id JOIN farms fm ON fm.id=fi.farm_id WHERE fm.user_id=%s AND c.status='active' ORDER BY c.id",(user_id,)).fetchall()
            recent_alerts=conn.execute("""SELECT a.id,a.crop_id,a.title,a.severity,a.created_at FROM alerts a
                JOIN crops c ON c.id=a.crop_id JOIN fields fi ON fi.id=c.field_id JOIN farms fm ON fm.id=fi.farm_id
                WHERE fm.user_id=%s AND c.status='active' AND a.alert_type='forecast_weather'
                  AND a.created_at>=NOW()-INTERVAL '24 hours' ORDER BY a.created_at DESC""",(user_id,)).fetchall()
            alerts_by_crop={}
            for alert in recent_alerts:
                alerts_by_crop.setdefault(alert["crop_id"],[]).append(alert)
            generated=0
            for crop in crops:
                for action in daily_actions(crop,user["user_type"] if user else "farmer",alerts_by_crop.get(crop["crop_id"])):
                    generated_by="recent_weather_alert" if action["plan_type"]=="recent_weather_alert_review" else "crop_care_rules"
                    inserted=conn.execute("""INSERT INTO farm_tasks(user_id,farm_id,crop_id,title,recommendation,priority,due_date,reason,source_references,evidence_quality,valid_until,plan_date,generated_by)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT(user_id,crop_id,plan_date,title) WHERE plan_date IS NOT NULL AND crop_id IS NOT NULL DO NOTHING RETURNING id""",
                        (user_id,crop["farm_id"],crop["crop_id"],action["title"],action["recommendation"],action["priority"],today,action["reason"],Jsonb(action["source_references"]),action["evidence_quality"],datetime.now(timezone.utc)+timedelta(days=action["validity_days"]),today,generated_by)).fetchone()
                    generated += bool(inserted)
            deadlines=conn.execute("""SELECT DISTINCT s.scheme_id,s.official_name,s.deadline,s.date_precision,s.application_status,
                    s.official_application_url,s.state_scope,s.last_checked_at
                FROM schemes s WHERE s.verification_status='verified' AND s.last_checked_at>=NOW()-INTERVAL '180 days'
                  AND s.deadline BETWEEN CURRENT_DATE AND CURRENT_DATE+30
                  AND s.application_status<>'closed'
                  AND (s.government_level='central' OR s.state_scope IS NULL OR cardinality(s.state_scope)=0
                    OR EXISTS (SELECT 1 FROM farms fm WHERE fm.user_id=%s AND fm.state=ANY(s.state_scope)))
                ORDER BY s.deadline,s.official_name""",(user_id,)).fetchall()
            rows=conn.execute("SELECT id,farm_id,crop_id,title,recommendation,priority,due_date,reason,source_references,evidence_quality,valid_until,state,feedback,generated_by,plan_date,created_at FROM farm_tasks WHERE user_id=%s AND (plan_date=%s OR (plan_date IS NULL AND (due_date=%s OR state='open'))) ORDER BY (state='open') DESC,priority DESC,created_at DESC",(user_id,today,today)).fetchall()
        return jsonify({"status":"available" if rows or deadlines else "no_crops","date":today.isoformat(),"generated_count":generated,"items":_safe(rows),"scheme_deadlines":_safe(deadlines),"notice":"General checks and recent weather-alert review prompts use limited evidence. Scheme deadlines are included only when verified, recently checked, upcoming within 30 days, and in scope for this farmer. Refresh weather before acting on an alert."})
    except Exception as exc:
        return _db_error(exc)


def _action_state(task_id,state):
    user_id,error=_user()
    if error:return error
    payload=request.get_json(silent=True) or {}
    feedback=payload.get("feedback")
    if feedback is not None and (not isinstance(feedback,str) or len(feedback)>1000):
        return jsonify({"error":"feedback must be text under 1,000 characters."}),400
    try:
        with connection() as conn:
            row=conn.execute("UPDATE farm_tasks SET state=%s,feedback=%s,updated_at=NOW() WHERE id=%s AND user_id=%s AND state='open' RETURNING id,farm_id,crop_id,title,state,feedback,updated_at",(state,feedback,task_id,user_id)).fetchone()
            existing=conn.execute("SELECT state FROM farm_tasks WHERE id=%s AND user_id=%s",(task_id,user_id)).fetchone() if row is None else None
        if row:return jsonify(_safe(row)),200
        if existing:return jsonify({"error":f"Action is already {existing['state']}."}),409
        return jsonify({"error":"Action not found."}),404
    except Exception:
        return jsonify({"error":"Farm action could not be updated."}),503


@platform_bp.post("/farm/actions/<int:task_id>/complete")
def complete_daily_action(task_id):
    return _action_state(task_id,"completed")


@platform_bp.post("/farm/actions/<int:task_id>/dismiss")
def dismiss_daily_action(task_id):
    return _action_state(task_id,"dismissed")


@platform_bp.post("/tasks")
def create_task():
    user_id, error = _user()
    if error:
        return error
    p = request.get_json(silent=True) or {}
    title, recommendation = p.get("title"), p.get("recommendation")
    if not isinstance(title, str) or not title.strip() or len(title) > 160 or not isinstance(recommendation, str) or not recommendation.strip() or len(recommendation) > 2000:
        return jsonify({"error": "title and recommendation are required (within allowed lengths)."}), 400
    if p.get("priority", "normal") not in {"low", "normal", "high"}:
        return jsonify({"error": "Unsupported task priority."}), 400
    due_date = p.get("due_date")
    if due_date:
        try: date.fromisoformat(due_date)
        except (TypeError, ValueError): return jsonify({"error": "due_date must use YYYY-MM-DD."}), 400
    try:
        with connection() as conn:
            if p.get("farm_id") is not None and not conn.execute("SELECT 1 FROM farms WHERE id=%s AND user_id=%s", (p["farm_id"], user_id)).fetchone():
                return jsonify({"error": "Farm not found."}), 404
            if p.get("crop_id") is not None and not conn.execute("SELECT 1 FROM crops c JOIN fields f ON f.id=c.field_id JOIN farms fm ON fm.id=f.farm_id WHERE c.id=%s AND fm.user_id=%s", (p["crop_id"], user_id)).fetchone():
                return jsonify({"error": "Crop not found."}), 404
            row = conn.execute("INSERT INTO farm_tasks(user_id,farm_id,crop_id,title,recommendation,priority,due_date,reason,evidence_quality) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'user_input') RETURNING id,title,recommendation,priority,due_date,state,created_at", (user_id,p.get("farm_id"),p.get("crop_id"),title.strip(),recommendation.strip(),p.get("priority","normal"),due_date,p.get("reason"))).fetchone()
        return jsonify(_safe(row)), 201
    except Exception as exc:
        return _db_error(exc)


@platform_bp.patch("/tasks/<int:task_id>")
def update_task(task_id):
    user_id, error = _user()
    if error: return error
    p = request.get_json(silent=True) or {}
    state = p.get("state")
    if state not in {"completed", "dismissed", "open"}: return jsonify({"error": "state must be open, completed, or dismissed."}), 400
    try:
        with connection() as conn:
            row = conn.execute("UPDATE farm_tasks SET state=%s, feedback=%s, updated_at=NOW() WHERE id=%s AND user_id=%s RETURNING id,state,feedback,updated_at", (state,p.get("feedback"),task_id,user_id)).fetchone()
        return (jsonify(row), 200) if row else (jsonify({"error":"Task not found."}),404)
    except Exception as exc: return _db_error(exc)


ECONOMICS = {
    "expenses": ("farm_expenses", {"category", "description", "amount", "incurred_on", "farm_id", "crop_id", "season", "quantity", "quantity_unit"}),
    "sales": ("farm_sales", {"quantity", "quantity_unit", "price_unit", "unit_price", "sold_on", "farm_id", "crop_id", "season", "selling_cost", "notes"}),
}

EXPENSE_CATEGORIES = {"seeds", "fertilizer", "crop_protection", "labor", "machinery", "irrigation", "equipment_rental", "transport", "other"}


def _finance_values(kind, payload, current=None):
    allowed = ECONOMICS[kind][1]
    if set(payload) - allowed:
        raise FinanceInputError("Unsupported field.")
    merged = {**(current or {}), **payload}
    required = ("category", "description", "amount", "incurred_on") if kind == "expenses" else ("quantity", "quantity_unit", "unit_price", "sold_on")
    if any(merged.get(key) in (None, "") for key in required):
        raise FinanceInputError("Required fields are missing.")
    if kind == "expenses":
        if merged["category"] not in EXPENSE_CATEGORIES:
            raise FinanceInputError("Unsupported expense category.")
        if not isinstance(merged["description"], str) or not merged["description"].strip() or len(merged["description"]) > 500:
            raise FinanceInputError("description is required and must be under 500 characters.")
        merged["amount"] = decimal_value(merged["amount"], "amount")
        if merged.get("quantity") not in (None, ""):
            merged["quantity"] = decimal_value(merged["quantity"], "quantity")
        if merged.get("quantity_unit") not in (None, ""):
            merged["quantity_unit"] = quantity_unit(merged["quantity_unit"])
    else:
        merged["quantity"] = decimal_value(merged["quantity"], "quantity", strictly_greater=True)
        merged["unit_price"] = decimal_value(merged["unit_price"], "unit_price")
        merged["selling_cost"] = decimal_value(merged.get("selling_cost", 0), "selling_cost")
        merged["quantity_unit"] = quantity_unit(merged["quantity_unit"])
        merged["price_unit"] = quantity_unit(merged.get("price_unit") or merged["quantity_unit"], "price_unit")
        if merged.get("notes") is not None and (not isinstance(merged["notes"], str) or len(merged["notes"]) > 1000):
            raise FinanceInputError("notes must be text under 1,000 characters.")
    date_field = "incurred_on" if kind == "expenses" else "sold_on"
    try:
        date.fromisoformat(str(merged[date_field]))
    except (TypeError, ValueError):
        raise FinanceInputError(f"{date_field} must use YYYY-MM-DD.")
    if merged.get("season") is not None and (not isinstance(merged["season"], str) or len(merged["season"]) > 80):
        raise FinanceInputError("season must be text under 80 characters.")
    return merged


def _validate_finance_links(conn, user_id, values):
    farm_id, crop_id = values.get("farm_id"), values.get("crop_id")
    if farm_id is not None and not conn.execute("SELECT 1 FROM farms WHERE id=%s AND user_id=%s", (farm_id, user_id)).fetchone():
        return "Farm not found."
    if crop_id is not None:
        crop = conn.execute("SELECT f.farm_id FROM crops c JOIN fields f ON f.id=c.field_id JOIN farms fm ON fm.id=f.farm_id WHERE c.id=%s AND fm.user_id=%s", (crop_id, user_id)).fetchone()
        if not crop:
            return "Crop not found."
        if farm_id is not None and crop["farm_id"] != farm_id:
            return "The selected crop does not belong to the selected farm."
    return None


@platform_bp.route("/farm/<kind>", methods=["GET", "POST"])
def economics(kind):
    if kind not in ECONOMICS: return jsonify({"error":"Unknown record type."}),404
    user_id, error = _user()
    if error: return error
    table, allowed = ECONOMICS[kind]
    date_column = "incurred_on" if kind == "expenses" else "sold_on"
    if request.method == "GET":
        clauses, values = ["user_id=%s"], [user_id]
        for name in ("farm_id", "crop_id"):
            raw = request.args.get(name)
            if raw:
                try: identifier = int(raw)
                except ValueError: return jsonify({"error": f"{name} must be a positive integer."}),400
                if identifier < 1: return jsonify({"error": f"{name} must be a positive integer."}),400
                clauses.append(f"{name}=%s"); values.append(identifier)
        season = request.args.get("season", "").strip()
        if len(season) > 80: return jsonify({"error":"season filter is too long."}),400
        if season: clauses.append("season=%s"); values.append(season)
        for name, operator in (("date_from", ">="), ("date_to", "<=")):
            value=request.args.get(name)
            if value:
                try: date.fromisoformat(value)
                except ValueError: return jsonify({"error":f"{name} must use YYYY-MM-DD."}),400
                clauses.append(f"{date_column}{operator}%s"); values.append(value)
        try:
            page=int(request.args.get("page","1")); per_page=int(request.args.get("per_page","100"))
        except ValueError: return jsonify({"error":"page and per_page must be integers."}),400
        if page<1 or not 1<=per_page<=200: return jsonify({"error":"page must be positive and per_page must be between 1 and 200."}),400
        try:
            with connection() as conn:
                where=" AND ".join(clauses)
                total=conn.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE {where}",values).fetchone()["n"]
                rows = conn.execute(f"SELECT * FROM {table} WHERE {where} ORDER BY {date_column} DESC,created_at DESC LIMIT %s OFFSET %s", [*values,per_page,(page-1)*per_page]).fetchall()
            return jsonify({"items": _safe(rows),"page":page,"per_page":per_page,"total":total})
        except Exception as exc: return _db_error(exc)
    p = request.get_json(silent=True) or {}
    try:
        if not isinstance(p,dict): raise FinanceInputError("Request body must be a JSON object.")
        p=_finance_values(kind,p)
    except FinanceInputError as exc: return jsonify({"error":str(exc)}),400
    try:
        with connection() as conn:
            link_error=_validate_finance_links(conn,user_id,p)
            if link_error: return jsonify({"error":link_error}),404
            columns=["user_id",*p.keys()]
            row=conn.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join(['%s']*len(columns))}) RETURNING *",[user_id,*p.values()]).fetchone()
        return jsonify(_safe(row)),201
    except Exception as exc: return _db_error(exc)


@platform_bp.route("/farm/<kind>/<int:record_id>", methods=["PUT", "PATCH", "DELETE"])
def finance_record(kind, record_id):
    if kind not in ECONOMICS: return jsonify({"error":"Unknown record type."}),404
    user_id,error=_user()
    if error: return error
    table,allowed=ECONOMICS[kind]
    try:
        with connection() as conn:
            current=conn.execute(f"SELECT * FROM {table} WHERE id=%s AND user_id=%s",(record_id,user_id)).fetchone()
            if current is None: return jsonify({"error":"Record not found."}),404
            if request.method=="DELETE":
                conn.execute(f"DELETE FROM {table} WHERE id=%s AND user_id=%s",(record_id,user_id))
                return ("",204)
            payload=request.get_json(silent=True)
            if not isinstance(payload,dict): return jsonify({"error":"Request body must be a JSON object."}),400
            try: values=_finance_values(kind,payload,current)
            except FinanceInputError as exc: return jsonify({"error":str(exc)}),400
            link_error=_validate_finance_links(conn,user_id,values)
            if link_error: return jsonify({"error":link_error}),404
            update_values={key:values[key] for key in allowed if key in values}
            if not update_values: return jsonify(_safe(current))
            assignments=", ".join(f"{key}=%s" for key in update_values)
            row=conn.execute(f"UPDATE {table} SET {assignments},updated_at=NOW() WHERE id=%s AND user_id=%s RETURNING *",[*update_values.values(),record_id,user_id]).fetchone()
        return jsonify(_safe(row))
    except Exception:
        return jsonify({"error":"Financial record could not be updated."}),503


@platform_bp.get("/farm/profit-summary")
def profit_summary():
    user_id, error = _user()
    if error: return error
    clauses=[]
    filter_values=[]
    for name in ("farm_id","crop_id"):
        raw=request.args.get(name)
        if raw:
            try: identifier=int(raw)
            except ValueError: return jsonify({"error":f"{name} must be a positive integer."}),400
            if identifier<1: return jsonify({"error":f"{name} must be a positive integer."}),400
            clauses.append((f"{{alias}}.{name}=%s",identifier))
    season=request.args.get("season","").strip()
    if len(season)>80: return jsonify({"error":"season filter is too long."}),400
    if season: clauses.append(("COALESCE({alias}.season,c.season)=%s",season))
    for name,operator in (("date_from",">="),("date_to","<=")):
        value=request.args.get(name)
        if value:
            try: date.fromisoformat(value)
            except ValueError: return jsonify({"error":f"{name} must use YYYY-MM-DD."}),400
            clauses.append((f"{{alias}}.{{date_column}}{operator}%s",value))
    expected=None
    expected_unit=None
    yield_change=Decimal(0)
    price_change=Decimal(0)
    try:
        if request.args.get("expected_quantity") not in (None,""):
            expected=decimal_value(request.args["expected_quantity"],"expected_quantity",strictly_greater=True)
            expected_unit=quantity_unit(request.args.get("expected_quantity_unit","quintal"),"expected_quantity_unit")
        yield_change=decimal_value(request.args.get("yield_change_percent",0),"yield_change_percent",minimum=Decimal(-100))
        price_change=decimal_value(request.args.get("price_change_percent",0),"price_change_percent",minimum=Decimal(-100))
        if yield_change>500 or price_change>500: raise FinanceInputError("Scenario changes must be between -100% and 500%.")
    except FinanceInputError as exc: return jsonify({"error":str(exc)}),400

    def where_for(alias,date_column):
        parts=[f"{alias}.user_id=%s"]
        values=[user_id]
        for template,value in clauses:
            parts.append(template.format(alias=alias,date_column=date_column));values.append(value)
        return " AND ".join(parts),values
    try:
        with connection() as conn:
            expense_where,expense_args=where_for("e","incurred_on")
            sales_where,sales_args=where_for("s","sold_on")
            expense_rows=conn.execute(f"SELECT e.amount,e.crop_id,COALESCE(c.crop_name,'Unassigned') AS crop_name,COALESCE(e.season,c.season) AS season,COALESCE(NULLIF(f.area_acres,0),NULLIF(fm.area_acres,0),CASE WHEN fm.area_amount IS NOT NULL THEN fm.area_amount*CASE WHEN fm.area_unit='hectare' THEN 2.47105 ELSE 1 END END) AS area_acres FROM farm_expenses e LEFT JOIN crops c ON c.id=e.crop_id LEFT JOIN fields f ON f.id=c.field_id LEFT JOIN farms fm ON fm.id=COALESCE(e.farm_id,f.farm_id) WHERE {expense_where}",expense_args).fetchall()
            sale_rows=conn.execute(f"SELECT s.quantity,s.quantity_unit,s.price_unit,s.unit_price,s.selling_cost,s.crop_id,COALESCE(c.crop_name,'Unassigned') AS crop_name,COALESCE(s.season,c.season) AS season,COALESCE(NULLIF(f.area_acres,0),NULLIF(fm.area_acres,0),CASE WHEN fm.area_amount IS NOT NULL THEN fm.area_amount*CASE WHEN fm.area_unit='hectare' THEN 2.47105 ELSE 1 END END) AS area_acres FROM farm_sales s LEFT JOIN crops c ON c.id=s.crop_id LEFT JOIN fields f ON f.id=c.field_id LEFT JOIN farms fm ON fm.id=COALESCE(s.farm_id,f.farm_id) WHERE {sales_where}",sales_args).fetchall()
        result=calculate_finance(expense_rows,sale_rows,expected,expected_unit,yield_change,price_change)
        result["note"]="Recorded transactions only. Scenario outputs use the submitted yield assumption and recorded weighted sale price; they are estimates, not a yield or price forecast. Break-even is shown only when expected saleable quantity is supplied."
        return jsonify(_safe(result))
    except Exception as exc: return _db_error(exc)


@platform_bp.route("/farm/diary",methods=["GET","POST"])
def diary():
    user_id,error=_user()
    if error: return error
    p=request.get_json(silent=True) or {}
    try:
        with connection() as conn:
            if request.method=="GET":
                rows=conn.execute("SELECT id,farm_id,crop_id,entry_date,entry_type,notes,created_at FROM farm_diary_entries WHERE user_id=%s ORDER BY entry_date DESC,created_at DESC LIMIT 300",(user_id,)).fetchall()
                return jsonify({"items":_safe(rows)})
            notes=p.get("notes")
            if not isinstance(notes,str) or not notes.strip() or len(notes)>4000: return jsonify({"error":"Diary notes are required and must be under 4,000 characters."}),400
            if p.get("farm_id") is not None and not conn.execute("SELECT 1 FROM farms WHERE id=%s AND user_id=%s",(p["farm_id"],user_id)).fetchone(): return jsonify({"error":"Farm not found."}),404
            if p.get("crop_id") is not None and not conn.execute("SELECT 1 FROM crops c JOIN fields f ON f.id=c.field_id JOIN farms fm ON fm.id=f.farm_id WHERE c.id=%s AND fm.user_id=%s",(p["crop_id"],user_id)).fetchone(): return jsonify({"error":"Crop not found."}),404
            row=conn.execute("INSERT INTO farm_diary_entries(user_id,farm_id,crop_id,entry_date,entry_type,notes) VALUES(%s,%s,%s,COALESCE(%s::date,CURRENT_DATE),%s,%s) RETURNING id,farm_id,crop_id,entry_date,entry_type,notes,created_at",(user_id,p.get("farm_id"),p.get("crop_id"),p.get("entry_date"),p.get("entry_type","note"),notes.strip())).fetchone()
        return jsonify(_safe(row)),201
    except Exception as exc: return _db_error(exc)


@platform_bp.post("/disease-reports")
def create_disease_report():
    user_id,error=_user()
    if error: return error
    p=request.get_json(silent=True) or {}
    if p.get("consent_to_aggregate") is not True: return jsonify({"error":"Explicit consent is required to contribute a coarse regional report."}),400
    required=("crop_name","symptom_category","state","district")
    if any(not isinstance(p.get(k),str) or not p[k].strip() or len(p[k])>120 for k in required): return jsonify({"error":"Crop, symptom category, state, and district are required."}),400
    key=sha256("|".join(p[k].strip().casefold() for k in required).encode()).hexdigest()
    try:
        with connection() as conn:
            row=conn.execute("INSERT INTO disease_reports(user_id,crop_name,symptom_category,state,district,growth_stage,consent_to_aggregate,report_dedupe_key) VALUES(%s,%s,%s,%s,%s,%s,TRUE,%s) ON CONFLICT(user_id,report_dedupe_key) WHERE report_dedupe_key IS NOT NULL DO UPDATE SET report_date=CURRENT_DATE RETURNING id,verification_status,report_date",(user_id,*[p[k].strip() for k in required],p.get("growth_stage"),key)).fetchone()
        return jsonify({**_safe(row),"notice":"Community signals are reports, not confirmed diagnoses."}),201
    except Exception as exc: return _db_error(exc)


@platform_bp.get("/regional-disease-alerts")
def regional_disease_alerts():
    state=request.args.get("state","").strip()
    district=request.args.get("district","").strip()
    if not state or not district: return jsonify({"items":[],"status":"location_required"})
    try:
        with connection() as conn:
            rows=conn.execute("SELECT crop_name,symptom_category,state,district,COUNT(*) AS report_count,'community_signal' AS status,MAX(report_date) AS latest_report FROM disease_reports WHERE state ILIKE %s AND district ILIKE %s AND consent_to_aggregate=TRUE AND verification_status IN ('unverified','under_review','expert_reviewed') AND expires_at>NOW() AND report_date>=CURRENT_DATE-INTERVAL '14 days' GROUP BY crop_name,symptom_category,state,district HAVING COUNT(*)>=5 ORDER BY latest_report DESC",(state,district)).fetchall()
        return jsonify({"items":_safe(rows),"minimum_reports":5,"note":"Community signals are not confirmed diagnoses."})
    except Exception as exc: return _db_error(exc)


@platform_bp.get("/market-prices")
def market_prices():
    commodity=request.args.get("commodity","").strip()
    state=request.args.get("state","").strip()
    district=request.args.get("district","").strip()
    if not commodity: return jsonify({"items":[],"status":"commodity_required"})
    try:
        with connection() as conn:
            rows=conn.execute("SELECT provider,commodity,variety,state,district,mandi,observed_on,minimum_price,modal_price,maximum_price,arrival_quantity,arrival_unit,price_unit,source_url,source_updated_at,fetched_at,freshness FROM market_prices WHERE commodity ILIKE %s AND (%s='' OR state ILIKE %s) AND (%s='' OR district ILIKE %s) ORDER BY observed_on DESC LIMIT 100",(commodity,state,state,district,district)).fetchall()
        return jsonify({"items":_safe(rows),"status":"available" if rows else "unavailable","note":"Only source-attributed ingested observations are listed; no live market provider is configured."})
    except Exception as exc: return _db_error(exc)
