import os
import secrets
import threading
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ModuleNotFoundError:
    pass

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

from db import init_db
from routes.agriculture import agriculture_bp
from routes.auth import auth_bp
from routes.admin import admin_bp
from routes.chat import chat_bp
from routes.crop_intelligence import crop_intelligence_bp
from routes.health import health_bp
from routes.farmer_profile import farmer_profile_bp
from routes.history import history_bp
from routes.insights import insights_bp
from routes.knowledge import knowledge_bp
from routes.location import location_bp
from routes.markets import markets_bp
from routes.prediction import prediction_bp
from routes.platform import platform_bp
from routes.weather import weather_bp

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FRONTEND_DIST = os.path.join(ROOT_DIR, "frontend", "dist")
app = Flask(__name__)
secret_key = os.getenv("FLASK_SECRET_KEY")
production = os.getenv("FLASK_ENV", "development").lower() == "production"
if production and not secret_key:
    raise RuntimeError("FLASK_SECRET_KEY must be set in production.")
app.config["SECRET_KEY"] = secret_key or secrets.token_urlsafe(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("FLASK_ENV", "development").lower() == "production"
CORS(app, resources={r"/api/*": {"origins": "*"}})
app.register_blueprint(health_bp, url_prefix="/api")
app.register_blueprint(farmer_profile_bp, url_prefix="/api")
app.register_blueprint(agriculture_bp, url_prefix="/api")
app.register_blueprint(auth_bp, url_prefix="/api")
app.register_blueprint(admin_bp, url_prefix="/api")
app.register_blueprint(prediction_bp, url_prefix="/api")
app.register_blueprint(chat_bp, url_prefix="/api")
app.register_blueprint(crop_intelligence_bp, url_prefix="/api")
app.register_blueprint(history_bp, url_prefix="/api")
app.register_blueprint(insights_bp, url_prefix="/api")
app.register_blueprint(knowledge_bp, url_prefix="/api")
app.register_blueprint(location_bp, url_prefix="/api")
app.register_blueprint(weather_bp, url_prefix="/api")
app.register_blueprint(platform_bp, url_prefix="/api")
app.register_blueprint(markets_bp, url_prefix="/api")

def _auto_ingest_market_data():
    """Keep the mandi table stocked without a manual shell command.

    Runs once at startup in a background thread: imports official data.gov.in
    prices when the table is empty, and refreshes them when older than 24 hours.
    """
    if not os.getenv("DATA_GOV_IN_API_KEY", "").strip():
        return
    try:
        from db import connection
        from services.market_ingest import refresh
        with connection() as conn:
            fresh = conn.execute(
                "SELECT 1 FROM market_prices WHERE provider='data.gov.in/AGMARKNET' "
                "AND fetched_at > NOW() - INTERVAL '24 hours' LIMIT 1"
            ).fetchone()
        if fresh:
            return
        result = refresh()
        app.logger.info("Market data auto-ingested: %s", result)
    except Exception as error:
        app.logger.warning("Market data auto-ingest skipped: %s", error)


try:
    init_db()
except Exception as error:
    app.logger.warning("Database initialization deferred: %s", error)
else:
    threading.Thread(target=_auto_ingest_market_data, daemon=True, name="market-ingest").start()


@app.get("/")
def index():
    if os.path.exists(os.path.join(FRONTEND_DIST, "index.html")):
        return send_from_directory(FRONTEND_DIST, "index.html")
    return send_from_directory(ROOT_DIR, "index.html")


@app.get("/assets/<path:filename>")
def frontend_assets(filename):
    if not os.path.exists(FRONTEND_DIST):
        return jsonify({"error": "Frontend build is not available."}), 404
    return send_from_directory(os.path.join(FRONTEND_DIST, "assets"), filename)


@app.get("/<path:path>")
def frontend_route(path):
    if path.startswith("api/"):
        return jsonify({"error": "API route not found."}), 404
    candidate = os.path.join(FRONTEND_DIST, path)
    if os.path.isfile(candidate):
        return send_from_directory(FRONTEND_DIST, path)
    return index()


if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true",
    )
