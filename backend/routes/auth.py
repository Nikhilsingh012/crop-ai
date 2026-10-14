from flask import Blueprint, jsonify, session, request
import re
from werkzeug.security import check_password_hash, generate_password_hash

from db import create_auth_user, get_user, get_user_by_email

auth_bp = Blueprint("auth", __name__)


def _public_user(user):
    return {"id": user["id"], "name": user["name"], "email": user.get("email"), "user_type": user["user_type"]}


@auth_bp.post("/auth/register")
def register():
    payload = request.get_json(silent=True) or {}
    missing = next((key for key in ("name", "email", "password") if not str(payload.get(key, "")).strip()), None)
    if missing:
        return jsonify({"error": f"'{missing}' is required."}), 400
    if not isinstance(payload["name"], str) or len(payload["name"].strip()) > 120:
        return jsonify({"error": "Name must be text and at most 120 characters."}), 400
    email = str(payload["email"]).strip().lower()
    if len(email) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return jsonify({"error": "Enter a valid email address."}), 400
    password = payload["password"]
    if not isinstance(password, str) or len(password) < 8 or len(password) > 1024:
        return jsonify({"error": "Password must be between 8 and 1024 characters."}), 400
    user_type = payload.get("user_type", "farmer")
    if user_type not in {"farmer", "gardener"}:
        return jsonify({"error": "user_type must be 'farmer' or 'gardener'."}), 400
    if get_user_by_email(email):
        return jsonify({"error": "An account with this email already exists."}), 409
    user = create_auth_user(
        {
            "name": payload["name"].strip(),
            "email": email,
            "password_hash": generate_password_hash(password),
            "user_type": user_type,
        }
    )
    session.clear()
    session["user_id"] = user["id"]
    return jsonify(_public_user(user)), 201


@auth_bp.post("/auth/login")
def login():
    payload = request.get_json(silent=True) or {}
    user = get_user_by_email(str(payload.get("email", "")).strip())
    password = payload.get("password")
    if not isinstance(password, str) or user is None or not user.get("password_hash") or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid email or password."}), 401
    session.clear()
    session["user_id"] = user["id"]
    return jsonify(_public_user(user))


@auth_bp.get("/auth/me")
def me():
    user_id = session.get("user_id")
    user = get_user(user_id) if user_id else None
    if user is None:
        return jsonify({"authenticated": False}), 200
    return jsonify({"authenticated": True, "user": _public_user(user)})


@auth_bp.post("/auth/logout")
def logout():
    session.clear()
    return jsonify({"logged_out": True})
