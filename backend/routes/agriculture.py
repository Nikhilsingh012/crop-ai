from flask import Blueprint, jsonify, request

from authz import current_user_id, forbidden, unauthorized
from db import (
    create_crop,
    create_farm,
    create_field,
    create_user_crop,
    delete_crop,
    delete_farm,
    delete_field,
    delete_user,
    get_owned_crop,
    get_owned_farm,
    get_owned_field,
    get_user,
    list_crops,
    list_farms,
    list_fields,
    update_crop,
    update_farm,
    update_field,
    update_user,
)
from services.crop_catalog import resolve_crop

agriculture_bp = Blueprint("agriculture", __name__)


def _payload():
    return request.get_json(silent=True) or {}


def _required(payload, fields):
    return next((field for field in fields if payload.get(field) in (None, "")), None)


def _result(record, status=200):
    if record is None:
        return jsonify({"error": "Resource not found."}), 404
    return jsonify(record), status


def _removed(delete_function, record_id):
    if delete_function(record_id) is None:
        return jsonify({"error": "Resource not found."}), 404
    return jsonify({"deleted": True, "id": record_id})


def _user():
    user_id = current_user_id()
    if user_id is None:
        return None, unauthorized()
    user = get_user(user_id)
    if user is None:
        return None, unauthorized()
    return user, None


@agriculture_bp.get("/users")
def users():
    user, error = _user()
    if error:
        return error
    return jsonify({"items": [{key: user.get(key) for key in ("id", "name", "email", "user_type")} ]})


@agriculture_bp.post("/users")
def create_user_route():
    return jsonify({"error": "Use /api/auth/register to create a password-protected account."}), 410


@agriculture_bp.route("/users/<int:user_id>", methods=["GET", "PATCH", "DELETE"])
def user_detail(user_id):
    user, error = _user()
    if error:
        return error
    if user["id"] != user_id:
        return forbidden()
    if request.method == "GET":
        return jsonify({key: user.get(key) for key in ("id", "name", "email", "user_type", "state", "district", "preferred_language")})
    if request.method == "DELETE":
        return _removed(delete_user, user_id)
    payload = _payload()
    if "user_type" in payload and payload["user_type"] not in {"farmer", "gardener"}:
        return jsonify({"error": "user_type must be 'farmer' or 'gardener'."}), 400
    return _result(update_user(user_id, payload))


@agriculture_bp.get("/users/<int:user_id>/farms")
def user_farms(user_id):
    user, error = _user()
    if error:
        return error
    if user["id"] != user_id:
        return forbidden()
    return jsonify({"items": list_farms(user_id)})


@agriculture_bp.post("/farms")
def create_farm_route():
    payload = _payload()
    user, error = _user()
    if error:
        return error
    missing = _required(payload, ["name"])
    if missing:
        return jsonify({"error": f"'{missing}' is required."}), 400
    keys = ("name", "location", "state", "district", "area_acres", "area_amount", "area_unit", "irrigation_method", "notes")
    values = {key: payload[key] for key in keys if key in payload}
    values["user_id"] = user["id"]
    return _result(create_farm(values), 201)


@agriculture_bp.route("/farms/<int:farm_id>", methods=["GET", "PATCH", "DELETE"])
def farm_detail(farm_id):
    user, error = _user()
    if error:
        return error
    farm = get_owned_farm(farm_id, user["id"])
    if farm is None:
        return jsonify({"error": "Farm not found."}), 404
    if request.method == "GET":
        return jsonify(farm)
    if request.method == "DELETE":
        return _removed(delete_farm, farm_id)
    return _result(update_farm(farm_id, _payload()))


@agriculture_bp.get("/farms/<int:farm_id>/fields")
def farm_fields(farm_id):
    user, error = _user()
    if error:
        return error
    if get_owned_farm(farm_id, user["id"]) is None:
        return jsonify({"error": "Farm not found."}), 404
    return jsonify({"items": list_fields(farm_id)})


@agriculture_bp.post("/fields")
def create_field_route():
    payload = _payload()
    user, error = _user()
    if error:
        return error
    missing = _required(payload, ["farm_id", "name"])
    if missing:
        return jsonify({"error": f"'{missing}' is required."}), 400
    if get_owned_farm(payload["farm_id"], user["id"]) is None:
        return jsonify({"error": "Farm not found."}), 404
    keys = ("farm_id", "name", "area_acres", "soil_type", "irrigation_type", "notes")
    return _result(create_field({key: payload[key] for key in keys if key in payload}), 201)


@agriculture_bp.route("/fields/<int:field_id>", methods=["GET", "PATCH", "DELETE"])
def field_detail(field_id):
    user, error = _user()
    if error:
        return error
    field = get_owned_field(field_id, user["id"])
    if field is None:
        return jsonify({"error": "Field not found."}), 404
    if request.method == "GET":
        return jsonify(field)
    if request.method == "DELETE":
        return _removed(delete_field, field_id)
    return _result(update_field(field_id, _payload()))


@agriculture_bp.get("/fields/<int:field_id>/crops")
def field_crops(field_id):
    user, error = _user()
    if error:
        return error
    if get_owned_field(field_id, user["id"]) is None:
        return jsonify({"error": "Field not found."}), 404
    return jsonify({"items": list_crops(field_id)})


@agriculture_bp.post("/crops")
def create_crop_route():
    payload = _payload()
    user, error = _user()
    if error:
        return error
    if not payload.get("field_id"):
        try:
            latitude = float(payload.get("latitude"))
            longitude = float(payload.get("longitude"))
        except (TypeError, ValueError):
            return jsonify({"error": "field_id or valid latitude and longitude are required."}), 400
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            return jsonify({"error": "Latitude or longitude is outside the valid range."}), 400
        if not payload.get("crop_name"):
            return jsonify({"error": "'crop_name' is required."}), 400
        resolved, candidates = resolve_crop(payload["crop_name"])
        if not resolved:
            return jsonify({"error": "Crop name is ambiguous." if candidates else "Crop is not in the crop catalog.", "candidates": candidates}), 400
        values = {key: payload[key] for key in ("crop_name", "variety", "city", "state", "country", "planting_date", "growth_stage") if key in payload}
        values["user_id"] = user["id"]
        values["mode"] = user.get("user_type", "farmer")
        values["crop_name"] = resolved["canonical_name"]
        values.update({"latitude": latitude, "longitude": longitude})
        return _result(create_user_crop(values), 201)
    missing = _required(payload, ["field_id", "crop_name"])
    if missing:
        return jsonify({"error": f"'{missing}' is required."}), 400
    if get_owned_field(payload["field_id"], user["id"]) is None:
        return jsonify({"error": "Field not found."}), 404
    resolved, candidates = resolve_crop(payload["crop_name"])
    if not resolved:
        return jsonify({"error": "Crop name is ambiguous." if candidates else "Crop is not in the crop catalog.", "candidates": candidates}), 400
    keys = ("field_id", "crop_name", "variety", "season", "sowing_date", "expected_harvest_date", "current_stage", "status", "notes")
    values = {key: payload[key] for key in keys if key in payload}
    values["crop_name"] = resolved["canonical_name"]
    return _result(create_crop(values), 201)


@agriculture_bp.route("/crops/<int:crop_id>", methods=["GET", "PATCH", "DELETE"])
def crop_detail(crop_id):
    user, error = _user()
    if error:
        return error
    crop = get_owned_crop(crop_id, user["id"])
    if crop is None:
        return jsonify({"error": "Crop not found."}), 404
    if request.method == "GET":
        return jsonify(crop)
    if request.method == "DELETE":
        return _removed(delete_crop, crop_id)
    return _result(update_crop(crop_id, _payload()))
