"""Small, explicit Indian agriculture knowledge seed for the recommendation baseline."""

CROP_KNOWLEDGE = {
    "tomato": {
        "crop_name": "Tomato",
        "scientific_name": "Solanum lycopersicum",
        "seasons": ["Kharif", "Rabi"],
        "growth_duration_days": 120,
        "temperature_c": [18, 30],
        "soil_ph": [6.0, 7.5],
        "water_need": "medium",
        "states": ["Maharashtra", "Karnataka", "Uttar Pradesh", "Andhra Pradesh"],
        "disease_risk_conditions": ["high humidity", "leaf wetness", "warm temperatures"],
    },
    "wheat": {
        "crop_name": "Wheat",
        "scientific_name": "Triticum aestivum",
        "seasons": ["Rabi"],
        "growth_duration_days": 140,
        "temperature_c": [10, 25],
        "soil_ph": [6.0, 7.5],
        "water_need": "medium",
        "states": ["Punjab", "Haryana", "Uttar Pradesh", "Madhya Pradesh"],
        "disease_risk_conditions": ["cool humid weather", "standing water"],
    },
    "rice": {
        "crop_name": "Rice",
        "scientific_name": "Oryza sativa",
        "seasons": ["Kharif"],
        "growth_duration_days": 135,
        "temperature_c": [20, 35],
        "soil_ph": [5.5, 7.0],
        "water_need": "high",
        "states": ["West Bengal", "Odisha", "Andhra Pradesh", "Tamil Nadu"],
        "disease_risk_conditions": ["high humidity", "prolonged leaf wetness"],
    },
    "potato": {
        "crop_name": "Potato",
        "scientific_name": "Solanum tuberosum",
        "seasons": ["Rabi"],
        "growth_duration_days": 100,
        "temperature_c": [15, 25],
        "soil_ph": [5.0, 6.5],
        "water_need": "medium",
        "states": ["Uttar Pradesh", "West Bengal", "Bihar", "Gujarat"],
        "disease_risk_conditions": ["cool humid weather", "waterlogged soil"],
    },
}


def list_crop_knowledge():
    return list(CROP_KNOWLEDGE.values())


def get_crop_knowledge(crop_name):
    return CROP_KNOWLEDGE.get((crop_name or "").strip().lower())