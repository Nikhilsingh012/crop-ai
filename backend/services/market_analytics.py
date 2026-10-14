from datetime import date, timedelta


def trend_summary(points):
    latest_day = date.fromisoformat(points[-1]["date"]) if points else None
    result = {"daily_change": None, "7_day": None, "30_day": None}
    adjacent_days = (
        len(points) > 1
        and latest_day - date.fromisoformat(points[-2]["date"]) == timedelta(days=1)
    )
    if adjacent_days and points[-2]["modal_price"]:
        result["daily_change"] = round((points[-1]["modal_price"] / points[-2]["modal_price"] - 1) * 100, 2)
    for window, label in ((7, "7_day"), (30, "30_day")):
        recent = [p["modal_price"] for p in points if latest_day and latest_day - timedelta(days=window - 1) <= date.fromisoformat(p["date"]) <= latest_day]
        prior = [p["modal_price"] for p in points if latest_day and latest_day - timedelta(days=2 * window - 1) <= date.fromisoformat(p["date"]) < latest_day - timedelta(days=window - 1)]
        if recent and prior and sum(prior):
            result[label] = round((sum(recent) / len(recent) / (sum(prior) / len(prior)) - 1) * 100, 2)
    return result
