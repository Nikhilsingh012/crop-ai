def composite_health_score(risk_level=None, soil_ph=None, rainfall=None, temperature=None):
    score = 100
    reasons = []
    risk_penalty = {"LOW": 0, "MEDIUM": 12, "HIGH": 25, "CRITICAL": 40}.get(risk_level, 0)
    if risk_penalty:
        score -= risk_penalty
        reasons.append(f"Risk estimate contributed a {risk_penalty}-point adjustment.")
    if soil_ph is not None and not 5.5 <= float(soil_ph) <= 7.5:
        score -= 10
        reasons.append("Soil pH is outside the broad baseline range.")
    if rainfall is not None and float(rainfall) >= 50:
        score -= 5
        reasons.append("Recent heavy rainfall may increase stress or disease pressure.")
    if temperature is not None and float(temperature) >= 35:
        score -= 5
        reasons.append("High temperature may increase heat stress.")
    return {"score": max(0, min(100, score)), "label": "application-level composite indicator", "reasons": reasons or ["No negative indicators were supplied."]}