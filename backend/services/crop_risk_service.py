import json
import logging
import os
from datetime import datetime, timezone

from db import create_alert, find_user_crop_alert_event, get_user_crop, latest_crop_risk, save_crop_risk, save_weather_snapshot
from services.agriculture.crop_risk_engine import analyze_forecast
from services.rag.knowledge_loader import get_document
from services.rag.retriever import retrieve
from services.crop_catalog import resolve_crop
from services.weather.weather_service import WeatherProviderError, get_weather

logger = logging.getLogger(__name__)


def _llm_explanation(result, crop, weather, knowledge):
    # Keep deterministic source-backed conclusions intact; partial assessments
    # must not be relabelled or expanded by a language model.
    if result.get("status") != "assessed" or result.get("risk_score") is None or not os.getenv("GEMINI_API_KEY") or knowledge is None:
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


def run_crop_risk_analysis(crop_id, force=False, weather_override=None):
    crop = get_user_crop(crop_id)
    if crop is None:
        raise LookupError("Crop not found.")
    knowledge = get_document(crop["crop_name"])
    if isinstance(weather_override, dict):
        weather = weather_override
    else:
        try:
            weather = get_weather(crop["latitude"], crop["longitude"], force=force)
        except WeatherProviderError as error:
            # Preserve a structured assessment with explicit missing forecast data;
            # a provider outage must not collapse the crop-risk response to an error.
            weather = {
                "provider": "open-meteo", "latitude": crop["latitude"], "longitude": crop["longitude"],
                "provider_status": "unavailable", "freshness_status": "unavailable", "stale": False,
                "provider_http_status": error.provider_status, "provider_error": error.provider_error,
                "forecast": [], "hourly_forecast": [],
            }
    retrieved = retrieve(crop["crop_name"], f"{crop.get('growth_stage') or ''} {crop.get('state') or ''} weather risk India", region=crop.get("state"), stage=crop.get("growth_stage"))
    logger.info("Crop retrieved crop_id=%s; RAG retrieval count=%s; weather cache=%s", crop_id, len(retrieved), weather.get("cache"))
    result = _llm_explanation(analyze_forecast(crop, weather, knowledge, crop.get("growth_stage"), crop.get("state")), crop, weather, knowledge)
    catalog, _ = resolve_crop(crop["crop_name"])
    result["crop_id"] = catalog["crop_id"] if catalog else None
    result["crop_name"] = catalog["canonical_name"] if catalog else crop["crop_name"]
    result["location"] = {key: crop.get(key) for key in ("city", "district", "state", "country", "latitude", "longitude")}
    result["crop_context"] = {key: crop.get(key) for key in ("variety", "planting_date", "growth_stage", "country", "soil_type", "drainage_condition", "irrigation_availability")}
    result["official_advisory_url"] = "https://mausam.imd.gov.in/responsive/agromet_adv_ser_district_current_en.php"
    result["analyzed_at"] = datetime.now(timezone.utc).isoformat()
    result["retrieved_sources"] = [{key: item["metadata"].get(key) for key in ("source", "source_url", "region", "stage", "risk_type", "crop_id") if item["metadata"].get(key)} for item in retrieved]
    if not result["retrieved_sources"]:
        result.setdefault("limitations", []).append("No matching crop, region and stage advisory document is indexed. Check current IMD district advisories.")
    previous = latest_crop_risk(crop_id)
    previous_alerts = (previous or {}).get("result", {}).get("alerts", []) if previous else []
    save_weather_snapshot(crop_id, weather)
    saved = save_crop_risk(crop_id, result)
    for alert in result["alerts"]:
        already_in_latest_result = any(item.get("title") == alert["title"] for item in previous_alerts)
        if already_in_latest_result or find_user_crop_alert_event(crop_id, alert["title"]):
            continue
        source = (alert.get("sources") or [{}])[0]
        source_url = source.get("source_url")
        evidence = f" Evidence source: {source_url}" if source_url else ""
        message = f"Expected forecast: {alert.get('expected_time')} ({alert.get('forecast_timezone') or 'UTC'}). {alert['explanation']}{evidence}"
        create_alert({"user_crop_id": crop_id, "alert_type": alert["risk_type"].lower(), "severity": alert["severity"], "title": alert["title"], "message": message})
    logger.info("Risk score crop_id=%s score=%s", crop_id, result["risk_score"])
    return {"crop": crop, "weather": weather, "risk": result, "stored": saved}
