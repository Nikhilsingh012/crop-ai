"""Conservative weekly seasonal-naive baseline with chronological validation."""
from statistics import median


def walk_forward_predictions(values):
    """Yield (target_index, prediction, actual) using only earlier observations."""
    start = max(49, len(values) - 28)
    for target in range(start, len(values)):
        yield target, values[target - 7], values[target]


def forecast_from_history(history, horizon=7):
    rows = sorted(history, key=lambda row: row["observed_on"])
    # Require two complete weekly cycles plus multiple walk-forward holdouts.
    if len(rows) < 56 or horizon < 1 or horizon > 30:
        return {"status": "insufficient_history", "message": "Insufficient history for a reliable forecast"}
    if (rows[-1]["observed_on"] - rows[0]["observed_on"]).days < 55:
        return {"status": "insufficient_history", "message": "Insufficient history for a reliable forecast"}
    # This baseline uses a seven-observation lag as a seven-day seasonal lag.
    # Sparse records or missing prices break that relationship, so suppress
    # the forecast rather than silently treating separated market dates as
    # consecutive days.
    if any(row.get("modal_price") is None for row in rows):
        return {"status": "insufficient_history", "message": "Insufficient history for a reliable forecast"}
    days = [row["observed_on"] for row in rows]
    if len(set(days)) != len(days) or any((later - earlier).days != 1 for earlier, later in zip(days, days[1:])):
        return {"status": "insufficient_history", "message": "Insufficient history for a reliable forecast"}
    values = [float(row["modal_price"]) for row in rows]
    if len(values) < 56:
        return {"status": "insufficient_history", "message": "Insufficient history for a reliable forecast"}
    # Evaluate the seven-day seasonal naive forecast only against later values,
    # each prediction using observations strictly before its target date.
    errors = []
    for _, prediction, actual in walk_forward_predictions(values):
        errors.append(abs(actual - prediction))
    if len(errors) < 7:
        return {"status": "insufficient_history", "message": "Insufficient history for a reliable forecast"}
    anchor = values[-7:]
    uncertainty = median(errors) * 1.96
    points = []
    for i in range(horizon):
        value = anchor[i % 7]
        points.append({"day": i + 1, "point": round(value, 2), "lower": round(max(0, value - uncertainty), 2), "upper": round(value + uncertainty, 2)})
    mae = sum(errors) / len(errors)
    return {"status": "available", "model": "7-day seasonal naive", "backtest": {"method": "chronological walk-forward", "observations": len(errors), "mae": round(mae, 2), "uncertainty_method": "median absolute validation error × 1.96"}, "points": points, "warning": "Baseline only; market prices are uncertain and are not guaranteed."}
