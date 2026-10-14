import math

from flask import Blueprint, jsonify, request, session

from db import (
    create_alert,
    create_risk_prediction,
    find_recent_alert,
    get_user,
    list_crops,
    list_farms,
    list_fields,
    save_user_location,
)
from services.agriculture.crop_risk_engine import analyze_forecast
from services.rag.knowledge_loader import get_document
from services.weather import current_weather, forecast_weather
from services.weather_signals import rainfall_signals

weather_bp = Blueprint("weather", __name__)


def _coordinates():
    payload = request.args
    try:
        latitude = float(payload.get("latitude"))
        longitude = float(payload.get("longitude"))
    except (TypeError, ValueError):
        raise ValueError("Valid latitude and longitude are required.")
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("Latitude or longitude is outside the valid range.")
    return latitude, longitude


def _browser_forecast(value, latitude, longitude):
    """Accept a normalized Open-Meteo forecast fetched by the user's browser."""
    if not isinstance(value, dict) or value.get("provider") != "open-meteo":
        return None
    try:
        forecast_latitude = float(value["latitude"])
        forecast_longitude = float(value["longitude"])
        forecast = value["forecast"]
        if abs(forecast_latitude - latitude) > 0.1 or abs(forecast_longitude - longitude) > 0.1:
            return None
        if not isinstance(forecast, list) or len(forecast) < 2:
            return None

        def number(raw, minimum=None, maximum=None):
            parsed = float(raw)
            if not math.isfinite(parsed):
                raise ValueError("Weather values must be finite numbers.")
            if minimum is not None and parsed < minimum or maximum is not None and parsed > maximum:
                raise ValueError("Weather value is outside its valid range.")
            return parsed

        daily = []
        for day in forecast:
            if not isinstance(day, dict) or not isinstance(day.get("date"), str):
                return None
            normalized = {"date": day["date"], "rainfall": number(day.get("rainfall", 0), 0)}
            for key in ("temperature_max", "temperature_min"):
                if day.get(key) is not None:
                    normalized[key] = number(day[key], -100, 70)
            if day.get("precipitation_probability") is not None:
                normalized["precipitation_probability"] = number(day["precipitation_probability"], 0, 100)
            daily.append(normalized)

        def current(key, minimum=None, maximum=None):
            return number(value[key], minimum, maximum) if value.get(key) is not None else None

        return {
            "provider": "open-meteo",
            "configured": True,
            "latitude": forecast_latitude,
            "longitude": forecast_longitude,
            "timezone": value.get("timezone"),
            "temperature": current("temperature", -100, 70),
            "humidity": current("humidity", 0, 100),
            "rainfall": current("rainfall", 0),
            "wind_speed": current("wind_speed", 0, 500),
            "precipitation_probability": current("precipitation_probability", 0, 100),
            "forecast": daily,
        }
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


@weather_bp.get("/weather")
def weather_by_coordinates():
    try:
        latitude, longitude = _coordinates()
        return jsonify(forecast_weather(latitude, longitude))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception as error:
        return jsonify({"error": "Weather provider unavailable.", "details": str(error)}), 502


@weather_bp.get("/weather/current")
def weather_current():
    location = request.args.get("location", "")
    if not location.strip():
        return jsonify({"error": "location is required."}), 400
    try:
        return jsonify(current_weather(location))
    except Exception as error:
        return jsonify({"error": "Weather provider unavailable.", "details": str(error)}), 502


@weather_bp.post("/weather/risk")
def weather_risk():
    user_id = session.get("user_id")
    user = get_user(user_id) if user_id else None
    if user is None:
        return jsonify({"error": "Sign in before checking crop weather risk."}), 401
    if not user.get("location_consent_at"):
        return jsonify({"error": "Allow location saving in your profile before creating saved crop weather risks."}), 403

    payload = request.get_json(silent=True) or {}
    try:
        latitude = float(payload.get("latitude"))
        longitude = float(payload.get("longitude"))
    except (TypeError, ValueError):
        return jsonify({"error": "Valid latitude and longitude are required."}), 400
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return jsonify({"error": "Latitude or longitude is outside the valid range."}), 400

    try:
        save_user_location(user_id, {
            "latitude": latitude,
            "longitude": longitude,
            "location_name": payload.get("location"),
            "accuracy": payload.get("accuracy"),
        })
        weather = _browser_forecast(payload.get("weather"), latitude, longitude)
        if weather is None:
            weather = forecast_weather(latitude, longitude)
        weather_signals = rainfall_signals(weather.get("forecast"))
        next_48_hours = weather.get("forecast", [])[:2]
        expected_rainfall = round(sum(float(day.get("rainfall") or 0) for day in next_48_hours), 1)
        risks = []
        for farm in list_farms(user_id):
            for field in list_fields(farm["id"]):
                for crop in list_crops(field["id"]):
                    risk_weather = {**weather, "forecast": next_48_hours}
                    risk = analyze_forecast(
                        crop=crop,
                        weather=risk_weather,
                        knowledge=get_document(crop["crop_name"]),
                        growth_stage=crop.get("current_stage"),
                    )
                    reasons = [item["explanation"] for item in risk.get("alerts", [])]
                    reasons.extend(risk.get("limitations", []))
                    reasons.extend(risk.get("evidence", []))
                    risk_level = risk["overall_risk"]
                    risk_score = risk.get("risk_score")

                    prediction = create_risk_prediction(
                        {
                            "crop_id": crop["id"],
                            "risk_type": "forecast_weather",
                            "risk_level": risk_level,
                            "score": risk_score,
                            "reasons": reasons,
                        }
                    )
                    alert = None
                    for risk_alert in risk.get("alerts", []):
                        severity = risk_alert["severity"]
                        title = risk_alert["title"]
                        alert = find_recent_alert(crop["id"], "forecast_weather", title)
                        if alert is None:
                            alert = create_alert({
                                "crop_id": crop["id"],
                                "alert_type": "forecast_weather",
                                "severity": severity,
                                "title": title,
                                "message": risk_alert["explanation"],
                            })
                    risks.append(
                        {
                            "crop": crop["crop_name"],
                            "crop_id": crop["id"],
                            "level": risk_level,
                            "score": risk_score,
                            "knowledge_status": risk.get("knowledge_status", "LIMITED"),
                            "summary": risk.get("summary"),
                            "limitations": risk.get("limitations", []),
                            "weather_observations": risk.get("weather_observations", {}),
                            "expected_rainfall": expected_rainfall,
                            "risk_window_hours": 48,
                            "reasons": reasons,
                            "prediction": prediction,
                            "alert": alert,
                        }
                    )
        return jsonify({"location": payload.get("location"), "weather": weather, "weather_signals": weather_signals, "risks": risks})
    except Exception as error:
        return jsonify({"error": "Forecast risk analysis failed.", "details": str(error)}), 502
