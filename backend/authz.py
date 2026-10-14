"""Small shared helpers for session-based authorization."""
from flask import jsonify, session


def current_user_id():
    user_id = session.get("user_id")
    return user_id if isinstance(user_id, int) and user_id > 0 else None


def unauthorized():
    return jsonify({"error": "Sign in to access this resource."}), 401


def forbidden():
    return jsonify({"error": "You do not have access to this resource."}), 403
