import json
import logging
import os
from datetime import datetime, timezone

from db import create_alert, get_user_crop, latest_crop_risk, save_crop_risk, save_weather_snapshot
from services.agriculture.crop_risk_engine import analyze_forecast
from services.rag.knowledge_loader import get_document
from services.rag.retriever import retrieve
from services.crop_catalog import resolve_crop
from services.weather.weather_service import get_weather

logger = logging.getLogger(__name__)


def _llm_explanation(result, crop, weather, knowledge):
    if not os.getenv("GEMINI_API_KEY") or knowledge is None:
        return result
    try:
        from services.gemini import _request
        context = {"crop": crop["crop_name"], "location": {"city": crop.get("city"), "state": crop.get("state")}, "weather": weather, "risk_engine": result, "knowledge": knowledge}
        text = _request([{"text": "Return valid JSON only with summary and alerts. Explain this structured agricultural risk without changing scores, inventing weather or thresholds, claiming disease certainty, or giving pesticide doses. Context: " + json.dumps(context)}])
        parsed = json.loads((text or "").replace("```json", "").replace("```", "").strip())
        if isinstance(parsed, dict):
            result["summary"] = parsed.get("summary", result["summary"])
            logger.info("Validated LLM risk explanation crop_id=%s", crop["id"])
    except Exception as error:
        logger.warning("LLM risk explanation unavailable: %s", type(error).__name__)
    return result


def run_crop_risk_analysis(crop_id, force=False):
    crop = get_user_crop(crop_id)
    if crop is None:
        raise LookupError("Crop not found.")
    knowledge = get_document(crop["crop_name"])
    weather = get_weather(crop["latitude"], crop["longitude"], force=force)
    retrieved = retrieve(crop["crop_name"], f"{crop.get('growth_stage') or ''} {crop.get('state') or ''} weather risk India", region=crop.get("state"), stage=crop.get("growth_stage"))
    logger.info("Crop retrieved crop_id=%s; RAG retrieval count=%s; weather cache=%s", crop_id, len(retrieved), weather.get("cache"))
    result = _llm_explanation(analyze_forecast(crop, weather, knowledge, crop.get("growth_stage")), crop, weather, knowledge)
    if result.get("risk_score") is None and result.get("knowledge_status") == "LIMITED":
        result["summary"] = "Weather observations are available; crop-specific thresholds are not verified, so no crop risk score was calculated."
        result["limitations"] = [
            item for item in result.get("limitations", [])
            if "verified crop-specific thresholds are unavailable" not in item.lower()
        ] or ["Crop-specific thresholds have no verified source. Weather rules are not regionally or growth-stage calibrated."]
    catalog, _ = resolve_crop(crop["crop_name"])
    result["crop_id"] = catalog["crop_id"] if catalog else None
    result["crop_name"] = catalog["canonical_name"] if catalog else crop["crop_name"]
    result["location"] = {key: crop.get(key) for key in ("city", "state", "latitude", "longitude") if crop.get(key) is not None}
    result["analyzed_at"] = datetime.now(timezone.utc).isoformat()
    result["retrieved_sources"] = [{key: item["metadata"].get(key) for key in ("source", "source_url", "region", "stage", "risk_type", "crop_id") if item["metadata"].get(key)} for item in retrieved]
    if result.get("knowledge_status") != "LIMITED" and not result["retrieved_sources"]:
        result.setdefault("limitations", []).append("No crop-specific source document matched this query; available legacy rules are not independently verified.")
    previous = latest_crop_risk(crop_id)
    previous_alerts = (previous or {}).get("result", {}).get("alerts", []) if previous else []
    save_weather_snapshot(crop_id, weather)
    saved = save_crop_risk(crop_id, result)
    for alert in result["alerts"]:
        if not any(item.get("title") == alert["title"] and item.get("severity") == alert["severity"] for item in previous_alerts):
            create_alert({"user_crop_id": crop_id, "alert_type": alert["risk_type"].lower(), "severity": alert["severity"], "title": alert["title"], "message": alert["explanation"]})
    logger.info("Risk score crop_id=%s score=%s", crop_id, result["risk_score"])
    return {"crop": crop, "weather": weather, "risk": result, "stored": saved}
