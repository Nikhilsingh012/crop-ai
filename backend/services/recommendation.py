from services.crop_knowledge import list_crop_knowledge


def recommend_crops(state=None, season=None, soil_ph=None, water_availability=None):
    recommendations = []
    normalized_state = (state or "").strip().lower()
    normalized_season = (season or "").strip().lower()
    normalized_water = (water_availability or "").strip().lower()

    for crop in list_crop_knowledge():
        score = 0
        reasons = []
        if normalized_state and any(normalized_state == item.lower() for item in crop["states"]):
            score += 3
            reasons.append(f"listed for {state}")
        if normalized_season and normalized_season in {item.lower() for item in crop["seasons"]}:
            score += 2
            reasons.append(f"fits {season} season")
        if soil_ph is not None and crop["soil_ph"][0] <= float(soil_ph) <= crop["soil_ph"][1]:
            score += 2
            reasons.append("soil pH is within the baseline range")
        if normalized_water and normalized_water == crop["water_need"]:
            score += 1
            reasons.append("water need matches the supplied availability")
        if score:
            recommendations.append({"crop": crop["crop_name"], "score": score, "reasons": reasons})

    return sorted(recommendations, key=lambda item: item["score"], reverse=True)