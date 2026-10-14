from services.crop_knowledge import get_crop_knowledge
from services.lifecycle import estimate_lifecycle


def build_care_plan(crop, user_type="farmer"):
    knowledge = get_crop_knowledge(crop.get("crop_name")) or {}
    lifecycle = estimate_lifecycle(crop)
    crop_name = crop.get("crop_name", "this crop")
    stage = lifecycle["stage"]
    is_gardener = user_type == "gardener"
    water_need = knowledge.get("water_need", "field moisture")
    risk_conditions = knowledge.get("disease_risk_conditions", [])

    return {
        "crop": crop_name,
        "mode": "home gardener" if is_gardener else "farmer",
        "stage": stage,
        "days_since_sowing": lifecycle["days_since_sowing"],
        "title": f"{crop_name} care plan",
        "summary": f"Focus on steady {stage.lower()} care and inspect the plant before changing inputs.",
        "today": [
            f"Inspect new leaves, stems, and the soil around the {crop_name.lower()}.",
            f"Use a {water_need}-water approach and check soil moisture before watering.",
            "Record unusual symptoms or weather stress in the crop diary.",
        ],
        "watch_for": risk_conditions or ["wilting, unusual spots, discoloration, or pest activity"],
        "next_step": f"The next estimated stage is {lifecycle['next_stage'] or 'harvest'}." if lifecycle["next_stage"] else "Review harvest readiness locally.",
        "context_note": "For a home garden, also check pot drainage, sunlight, and plant spacing." if is_gardener else "For a farm field, compare this plan with local extension guidance and field observations.",
        "safety": "This is decision support, not a diagnosis. Confirm disease and treatment with a local agriculture expert before applying chemicals.",
    }