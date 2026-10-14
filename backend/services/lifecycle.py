from datetime import date, datetime


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value:
        return date.fromisoformat(str(value))
    return None


def estimate_lifecycle(crop, today=None):
    """Use farmer-entered dates/stage; do not infer crop duration from generic constants."""
    today = today or date.today()
    sowing_date = _as_date(crop.get("sowing_date"))
    harvest_date = _as_date(crop.get("expected_harvest_date"))
    days_since_sowing = max(0, (today - sowing_date).days) if sowing_date else None
    days_until_harvest = (harvest_date - today).days if harvest_date else None
    return {
        "stage": crop.get("current_stage") or "Unknown",
        "days_since_sowing": days_since_sowing,
        "progress_percent": None,
        "next_stage": None,
        "days_until_next_stage": None,
        "expected_harvest_date": harvest_date.isoformat() if harvest_date else None,
        "days_until_harvest": days_until_harvest,
        "status": "farmer_estimate" if harvest_date else "insufficient_data",
        "estimated": False,
        "limitations": [] if harvest_date else ["Add a locally confirmed expected harvest date; crop duration varies by variety, season, and conditions."],
    }
