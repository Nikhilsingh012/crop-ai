"""Conservative daily checklist generation from farmer crop context and existing care-plan rules."""
from services.care_plan import build_care_plan


def daily_actions(crop, user_type="farmer", recent_weather_alerts=None):
    plan = build_care_plan(crop, user_type)
    actions = [{
        "title": f"{crop.get('crop_name', 'Crop')}: {recommendation[:100]}",
        "recommendation": recommendation,
        "reason": plan["summary"],
        "priority": "normal",
        "evidence_quality": "limited",
        "source_references": [],
        "validity_days": 1,
        "plan_type": "general_observation_and_recordkeeping",
    } for recommendation in plan["today"]]
    for alert in recent_weather_alerts or []:
        title = str(alert.get("title") or "Weather risk alert")[:120]
        actions.append({
            "title": f"Refresh weather: {title}"[:160],
            "recommendation": "Refresh the local forecast and review this recent weather alert before changing farm inputs. Forecast conditions can change.",
            "reason": "A forecast alert was recorded for this crop within the last 24 hours; the alert itself is not a verified crop-specific instruction.",
            "priority": "high" if str(alert.get("severity", "")).upper() in {"HIGH", "SEVERE"} else "normal",
            "evidence_quality": "limited",
            "source_references": [{"type": "weather_alert", "id": alert.get("id")}],
            "validity_days": 1,
            "plan_type": "recent_weather_alert_review",
        })
    return actions
