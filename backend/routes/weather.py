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
from services.weather.weather_service import WeatherProviderError
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
    # Never turn a client-marked stale/cache fallback into a fresh observation.
    # Returning None makes the route request a new server-side forecast instead.
    if value.get("stale") is True or value.get("cache") == "stale_fallback":
        return None
    try:
        if isinstance(value.get("latitude"), bool) or not isinstance(value.get("latitude"), (int, float)):
            return None
        if isinstance(value.get("longitude"), bool) or not isinstance(value.get("longitude"), (int, float)):
            return None
        forecast_latitude = float(value["latitude"])
        forecast_longitude = float(value["longitude"])
        if not math.isfinite(forecast_latitude) or not math.isfinite(forecast_longitude):
            return None
        forecast = value["forecast"]
        if abs(forecast_latitude - latitude) > 0.1 or abs(forecast_longitude - longitude) > 0.1:
            return None
        if not isinstance(forecast, list) or len(forecast) < 2:
            return None

        def number(raw, minimum=None, maximum=None):
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise ValueError("Weather values must be numeric JSON values.")
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
            normalized = {"date": day["date"], "rainfall": number(day.get("rainfall"), 0) if day.get("rainfall") is not None else None}
            for key in ("temperature_max", "temperature_min"):
                if day.get(key) is not None:
                    normalized[key] = number(day[key], -100, 70)
            if day.get("precipitation_probability") is not None:
                normalized["precipitation_probability"] = number(day["precipitation_probability"], 0, 100)
            daily.append(normalized)
        hourly = []
        raw_hourly = value.get("hourly_forecast", [])
        if not isinstance(raw_hourly, list):
            return None
        for hour in raw_hourly[:200]:
            if not isinstance(hour, dict) or not isinstance(hour.get("time"), str):
                return None
            normalized = {"time": hour["time"]}
            for key, minimum, maximum in (("rainfall", 0, None), ("temperature", -100, 70), ("humidity", 0, 100), ("wind_speed", 0, 500), ("wind_gust", 0, 600), ("precipitation_probability", 0, 100)):
                if hour.get(key) is not None:
                    normalized[key] = number(hour[key], minimum, maximum)
                else:
                    normalized[key] = None
            hourly.append(normalized)

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
            "forecast_issued_at": value.get("forecast_issued_at"),
            "retrieved_at": value.get("retrieved_at"),
            "stale": False,
            "forecast_resolution": "hourly" if hourly else "daily",
            "forecast": daily,
            "hourly_forecast": hourly,
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
    except WeatherProviderError as error:
        return jsonify({"error": f"Weather provider unavailable: {error.provider_error}", "provider_status": error.provider_status, "provider_error": error.provider_error}), 502
    except Exception as error:
        return jsonify({"error": "Weather provider unavailable.", "provider_error": f"Weather provider request failed ({type(error).__name__})."}), 502


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
        hourly_forecast = weather.get("hourly_forecast", [])
        forecast_reference = weather.get("forecast_issued_at")
        if isinstance(forecast_reference, str):
            current_hour = forecast_reference[:13]
            hourly_forecast = [hour for hour in hourly_forecast if isinstance(hour, dict) and isinstance(hour.get("time"), str) and hour["time"][:13] > current_hour]
        next_48_hours = hourly_forecast[:48]
        rainfall_values = [hour.get("rainfall") for hour in next_48_hours]
        if len(next_48_hours) == 48 and all(value is not None for value in rainfall_values):
            expected_rainfall = round(sum(rainfall_values), 1)
            risk_window_hours = 48
            risk_resolution = "hourly"
        else:
            daily_window = weather.get("forecast", [])[:2]
            daily_rainfall = [day.get("rainfall") for day in daily_window]
            expected_rainfall = round(sum(daily_rainfall), 1) if len(daily_window) == 2 and all(value is not None for value in daily_rainfall) else None
            risk_window_hours = None
            risk_resolution = "daily_estimate"
        weather = {**weather, "hourly_forecast": next_48_hours, "forecast_resolution": risk_resolution if risk_resolution == "hourly" else "daily_estimate"}
        risks = []
        for farm in list_farms(user_id):
            for field in list_fields(farm["id"]):
                for crop in list_crops(field["id"]):
                    crop_context = {
                        **crop,
                        "state": farm.get("state"),
                        "district": farm.get("district"),
                        "soil_type": field.get("soil_type"),
                        "drainage_condition": field.get("drainage_condition"),
                        "irrigation_availability": field.get("irrigation_type") or farm.get("irrigation_method"),
                        "latitude": latitude,
                        "longitude": longitude,
                    }
                    # KALP's wheat indicator needs five consecutive daily Tmax
                    # records. Keep the public weather response intact while
                    # passing the source-defined window to the crop evaluator.
                    risk_weather = {**weather, "forecast": weather.get("forecast", [])[:5], "hourly_forecast": next_48_hours}
                    risk = analyze_forecast(
                        crop=crop_context,
                        weather=risk_weather,
                        knowledge=get_document(crop["crop_name"]),
                        growth_stage=crop.get("current_stage"),
                        region=farm.get("state"),
                    )
                    reasons = [item["explanation"] for item in risk.get("alerts", [])]
                    reasons.extend(risk.get("limitations", []))
                    reasons.extend(risk.get("evidence", []))
                    risk_level = risk["overall_risk"]
                    risk_score = risk.get("risk_score")

                    prediction = None
                    if risk_score is not None:
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
                            "state": farm.get("state"),
                            "district": farm.get("district"),
                            "level": risk_level if risk_score is not None else ("PARTIAL" if risk.get("status") == "partially_assessed" else "UNAVAILABLE"),
                            "score": risk_score,
                            "status": risk.get("status", "unavailable" if risk_score is None else "assessed"),
                            "knowledge_status": risk.get("knowledge_status", "LIMITED"),
                            "summary": risk.get("summary"),
                            "limitations": risk.get("limitations", []),
                            "hazards": risk.get("hazards", []),
                            "model_assessment": risk.get("model_assessment"),
                            "missing_inputs": risk.get("missing_inputs", []),
                            "weather_observations": risk.get("weather_observations", {}),
                            "expected_rainfall": expected_rainfall,
                            "risk_window_hours": risk_window_hours,
                            "risk_resolution": risk_resolution,
                            "reasons": reasons,
                            "prediction": prediction,
                            "alert": alert,
                        }
                    )
        return jsonify({"location": payload.get("location"), "weather": weather, "weather_signals": weather_signals, "risks": risks, "official_advisory_url": "https://mausam.imd.gov.in/responsive/agromet_adv_ser_district_current_en.php"})
    except Exception as error:
        return jsonify({"error": "Forecast risk analysis failed.", "details": str(error)}), 502
