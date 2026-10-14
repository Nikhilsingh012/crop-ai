def compute_risk(crop, growth_stage, humidity, temperature, rainfall, wind, soil_type=None, season=None, location=None):
    score = 0
    reasons = []
    crop_name = (crop or "").lower()

    if humidity is not None and humidity >= 80:
        score += 35
        reasons.append("High Humidity may favor fungal disease.")
    elif humidity is not None and humidity >= 65:
        score += 15
        reasons.append("Moderate-to-high humidity needs monitoring.")
    if rainfall is not None and rainfall >= 40:
        score += 30
        reasons.append("Recent rainfall may increase leaf wetness and disease pressure.")
    elif rainfall is not None and rainfall >= 15:
        score += 10
        reasons.append("Recent rainfall is a moderate risk factor.")
    if temperature is not None and 22 <= temperature <= 32:
        score += 15
        reasons.append("Temperature is within a range favorable to several crop diseases.")
    if growth_stage and growth_stage.lower() in {"flowering", "fruit/grain development"}:
        score += 15
        reasons.append("The current growth stage can be sensitive to disease and weather stress.")
    if wind is not None and wind >= 35:
        score += 10
        reasons.append("Strong wind can increase physical stress and spread of some pathogens.")
    if crop_name == "tomato" and humidity is not None and humidity >= 80:
        score += 10
        reasons.append("Tomato foliage should be monitored closely under humid conditions.")

    level = "CRITICAL" if score >= 110 else "HIGH" if score >= 60 else "MEDIUM" if score >= 30 else "LOW"
    return {
        "level": level,
        "score": min(score, 100),
        "reasons": reasons or ["No major risk factors were provided."],
        "context": {"crop": crop, "growth_stage": growth_stage, "season": season, "location": location, "soil_type": soil_type},
    }