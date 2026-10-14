"""General forecast signals that do not imply crop-specific risk scores."""
import math


IMD_RAINFALL_SOURCE = "https://mausam.imd.gov.in/imd_latest/contents/pdf/forecasting_sop.pdf"


def rainfall_signals(forecast):
    """Flag forecast-day rainfall in IMD's heavy-rain ranges.

    IMD's ranges describe 24-hour station rainfall observations. Forecast-day
    accumulation windows can differ, so these are exposure signals, not IMD
    warnings or crop-specific risk assessments.
    """
    signals = []
    for day in forecast or []:
        try:
            amount = float(day.get("rainfall"))
        except (AttributeError, TypeError, ValueError):
            continue
        if not math.isfinite(amount) or amount < 64.5:
            continue
        if amount >= 204.5:
            category = "extremely heavy"
            range_text = "204.5 mm or more"
        elif amount >= 115.6:
            category = "very heavy"
            range_text = "115.6–204.4 mm"
        else:
            category = "heavy"
            range_text = "64.5–115.5 mm"
        signals.append({
            "date": day.get("date"),
            "rainfall_mm": round(amount, 1),
            "category": category,
            "title": f"{category.title()} daily rainfall forecast",
            "explanation": (
                f"Forecast-day rainfall is {amount:.1f} mm, within the IMD {category} rainfall range "
                f"({range_text}). Forecast-day timing may differ from IMD's 24-hour station observation. "
                "This is a general weather exposure signal, not an official warning or a crop-specific risk score."
            ),
            "recommended_action": "Check local IMD alerts and field drainage conditions; avoid field work during unsafe weather.",
            "source": "India Meteorological Department rainfall categories",
            "source_url": IMD_RAINFALL_SOURCE,
        })
    return signals
