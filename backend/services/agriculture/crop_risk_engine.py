LEVELS = ((81, "SEVERE"), (61, "HIGH"), (41, "MODERATE"), (21, "WATCH"), (0, "LOW"))


def level_for(score):
    return next(level for threshold, level in LEVELS if score >= threshold)


def analyze_forecast(crop, weather, knowledge, growth_stage=None):
    registry_entry = crop_by_id(knowledge.get("crop_id")) if knowledge else None
    if knowledge is None or knowledge.get("threshold_evidence_status") != "verified":
        forecast = weather.get("forecast") or []
        rainfall = [float(day.get("rainfall") or 0) for day in forecast]
        peak_rainfall = max(rainfall, default=0)
        wet_days = sum(1 for amount in rainfall if amount >= 5)
        observations = {
            "forecast_rainfall_mm": round(sum(rainfall), 1),
            "peak_daily_rainfall_mm": round(peak_rainfall, 1),
            "wet_days": wet_days,
            "humidity_percent": weather.get("humidity"),
            "temperature_c": weather.get("temperature"),
            "wind_speed_kmh": weather.get("wind_speed"),
        }
        status = registry_entry.get("knowledge_status", "LIMITED") if registry_entry else "LIMITED"
        return {"overall_risk": "WATCH", "risk_score": None, "alerts": [], "summary": "Weather observations are available; crop-specific thresholds are not verified, so no crop risk score was calculated.", "knowledge_status": status, "limitations": ["Crop-specific thresholds have no verified source. Weather rules are not regionally or growth-stage calibrated."], "evidence": [f"Forecast rainfall: {observations['forecast_rainfall_mm']:.1f} mm over {len(forecast)} days.", f"Peak daily rainfall: {observations['peak_daily_rainfall_mm']:.1f} mm; wet days: {observations['wet_days']}."] , "weather_observations": observations}
    forecast = weather.get("forecast") or []
    rain = [float(day.get("rainfall") or 0) for day in forecast]
    humidity = float(weather.get("humidity") or 0)
    temperature = float(weather.get("temperature") or 0)
    wind = float(weather.get("wind_speed") or 0)
    consecutive_wet = 0
    longest_wet = 0
    for amount in rain:
        consecutive_wet = consecutive_wet + 1 if amount >= 5 else 0
        longest_wet = max(longest_wet, consecutive_wet)
    total_rain = sum(rain)
    max_rain = max(rain, default=0)
    alerts = []

    def add(risk_type, score, title, expected, impact, actions, monitor, reasons):
        score = max(0, min(100, round(score)))
        if score >= 21:
            alerts.append({"risk_type":risk_type,"severity":level_for(score),"title":title,"expected_time":expected,"explanation":reasons[0],"possible_impact":impact,"recommended_actions":actions,"monitor":monitor,"confidence":None,"score":score,"evidence":[*reasons, knowledge.get("source", "Crop knowledge record")],"weather_evidence":{"total_forecast_rainfall_mm":round(total_rain,1),"peak_daily_rainfall_mm":round(max_rain,1),"wet_days":longest_wet},"crop_knowledge_evidence":knowledge.get("source")})

    supported = set(registry_entry.get("supported_risk_types", [])) if registry_entry else set()
    rain_score = (max_rain / max(float(knowledge.get("heavy_rain_mm", 50)), 1)) * 42 + longest_wet * 7
    if "EXCESSIVE_RAINFALL" in supported:
        add("EXCESSIVE_RAINFALL", rain_score, "Heavy rainfall may affect your crop", f"Around {next((i + 1 for i, amount in enumerate(rain) if amount >= knowledge.get('heavy_rain_mm', 50)), 2)} days", "Waterlogging, nutrient loss, or crop lodging may increase depending on drainage and growth stage.", knowledge.get("preventive_actions", []), knowledge.get("warning_signs", []), [f"Forecast rainfall peaks near {max_rain:.0f} mm and may be followed by {longest_wet} wet days."])
    if "WATERLOGGING" in supported:
        saturation_score = max(0, total_rain - float(knowledge.get("heavy_rain_mm", 50))) * float(knowledge.get("waterlogging_sensitivity", 0.5))
        add("WATERLOGGING", saturation_score, "Prolonged rain may saturate the field", "Across the forecast period", "Field saturation depends on local drainage, soil and irrigation; inspect low areas after rain.", knowledge.get("preventive_actions", []), knowledge.get("warning_signs", []), [f"Forecast accumulation is {total_rain:.0f} mm; field drainage conditions were not provided."])
    humidity_score = max(0, humidity - knowledge.get("humidity_threshold", 80)) * 2.5 + longest_wet * 8
    if "HIGH_HUMIDITY" in supported:
        add("HIGH_HUMIDITY", humidity_score, "Wet and humid conditions need monitoring", "Over the next few days", "Continuous leaf wetness may increase the chance of weather-associated disease; this does not confirm disease.", knowledge.get("preventive_actions", []), knowledge.get("warning_signs", []), [f"Humidity is {humidity:.0f}% with {longest_wet} consecutive wet days."])
    heat_score = max(0, temperature - knowledge.get("heat_threshold_c", 40)) * 8
    if "HEAT_STRESS" in supported:
        add("HEAT_STRESS", heat_score, "Heat stress may increase", "Today and during hot forecast days", "Heat can increase water demand and affect flowering or grain/fruit development.", ["Check soil moisture early in the day."], ["Leaf rolling, wilting, flower drop"], [f"Temperature is {temperature:.1f} C; the configured crop threshold is {knowledge.get('heat_threshold_c')} C."])
    if "COLD_STRESS" in supported:
        lows = [float(day["temperature_min"]) for day in forecast if day.get("temperature_min") is not None]
        threshold = knowledge.get("cold_threshold_c")
        if lows and threshold is not None:
            minimum = min(lows)
            cold_score = max(0, float(threshold) - minimum) * 8
            add("COLD_STRESS", cold_score, "Cold conditions may stress your crop", "During the forecast cold period", "Sensitivity varies by crop stage and local acclimation; protect vulnerable growth where advised.", knowledge.get("preventive_actions", []), knowledge.get("warning_signs", []), [f"Forecast minimum is {minimum:.1f} C; the configured threshold is {threshold} C."])
    wind_score = max(0, wind - knowledge.get("wind_threshold_kmh", 45)) * 2
    if "STRONG_WIND" in supported:
        add("STRONG_WIND", wind_score, "Strong wind may stress plants", "During the windy period", "Lodging, broken branches, or flower drop may occur in exposed crops.", ["Check supports where practical."], ["Leaning stems, broken branches"], [f"Wind is {wind:.0f} km/h."])
    overall = max([item["score"] for item in alerts] + [0])
    if not supported:
        return {"overall_risk": "WATCH", "risk_score": None, "alerts": [], "summary": "Weather data is available, but the crop record does not contain supported risk rules for a reliable assessment.", "knowledge_status": "LIMITED", "limitations": ["No crop-specific weather risk rules are available."], "evidence": [f"Forecast rainfall: {total_rain:.1f} mm."]}
    status = registry_entry.get("knowledge_status", "PARTIAL") if registry_entry else "LIMITED"
    return {"overall_risk":level_for(overall),"risk_score":overall,"alerts":alerts,"knowledge_status":status,"limitations":["Available crop rules are partial, use unverified project thresholds, and are not calibrated by region or growth stage."] if status != "FULL" else [],"summary":("Weather conditions may increase risk; inspect the crop and follow the actions below." if alerts else "No supported weather trigger was detected; crop-specific knowledge remains partial."),"evidence":[f"Forecast total rainfall: {total_rain:.1f} mm.",f"Current humidity: {humidity:.0f}%.",knowledge.get("source", "Crop knowledge document.")]}
from services.crop_catalog import crop_by_id

