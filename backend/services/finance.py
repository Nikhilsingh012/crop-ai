"""Unit-safe transparent accounting calculations for farm expense and sale records."""
from decimal import Decimal, InvalidOperation

QUINTALS_PER_UNIT = {"kg": Decimal("0.01"), "quintal": Decimal("1"), "tonne": Decimal("10")}
MONEY = Decimal("0.01")


def _money(value):
    return value.quantize(MONEY)


class FinanceInputError(ValueError):
    pass


def decimal_value(value, field, *, minimum=Decimal("0"), strictly_greater=False):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise FinanceInputError(f"{field} must be a valid number.")
    if not number.is_finite() or (number <= minimum if strictly_greater else number < minimum):
        raise FinanceInputError(f"{field} is outside the allowed range.")
    return number


def quantity_unit(value, field="quantity_unit"):
    unit = str(value or "").strip().lower()
    if unit not in QUINTALS_PER_UNIT:
        raise FinanceInputError(f"{field} must be kg, quintal, or tonne.")
    return unit


def quantity_in_quintals(quantity, unit):
    return Decimal(str(quantity)) * QUINTALS_PER_UNIT[quantity_unit(unit)]


def price_per_quintal(unit_price, price_unit):
    return Decimal(str(unit_price)) / QUINTALS_PER_UNIT[quantity_unit(price_unit, "price_unit")]


def calculate_finance(expenses, sales, expected_quantity=None, expected_unit=None, yield_change_percent=0, price_change_percent=0):
    yield_change_percent = decimal_value(yield_change_percent, "yield_change_percent", minimum=Decimal(-100))
    price_change_percent = decimal_value(price_change_percent, "price_change_percent", minimum=Decimal(-100))
    if yield_change_percent > 500 or price_change_percent > 500:
        raise FinanceInputError("Scenario changes must be between -100% and 500%.")
    expense_total = sum((Decimal(str(row["amount"])) for row in expenses), Decimal(0))
    gross_revenue = Decimal(0)
    selling_costs = Decimal(0)
    recorded_quantity = Decimal(0)
    weighted_quintal_revenue = Decimal(0)
    groups = {}
    for row in expenses:
        key = (row.get("crop_id"), row.get("crop_name") or "Unassigned", row.get("season") or "Unspecified")
        group = groups.setdefault(key, {"expenses": Decimal(0), "gross_revenue": Decimal(0), "selling_costs": Decimal(0), "quantity_quintals": Decimal(0), "area_acres": row.get("area_acres")})
        group["expenses"] += Decimal(str(row["amount"]))
    for row in sales:
        quantity = Decimal(str(row["quantity"]))
        amount = Decimal(str(row["unit_price"]))
        price_unit = row.get("price_unit") or row["quantity_unit"]
        gross = quantity * (QUINTALS_PER_UNIT[quantity_unit(row["quantity_unit"])] / QUINTALS_PER_UNIT[quantity_unit(price_unit, "price_unit")]) * amount
        qtl = quantity_in_quintals(quantity, row["quantity_unit"])
        cost = Decimal(str(row.get("selling_cost") or 0))
        gross_revenue += gross
        selling_costs += cost
        recorded_quantity += qtl
        weighted_quintal_revenue += gross
        key = (row.get("crop_id"), row.get("crop_name") or "Unassigned", row.get("season") or "Unspecified")
        group = groups.setdefault(key, {"expenses": Decimal(0), "gross_revenue": Decimal(0), "selling_costs": Decimal(0), "quantity_quintals": Decimal(0), "area_acres": row.get("area_acres")})
        group["gross_revenue"] += gross
        group["selling_costs"] += cost
        group["quantity_quintals"] += qtl
    breakdown = []
    for (crop_id, crop_name, season), group in groups.items():
        area = Decimal(str(group["area_acres"])) if group.get("area_acres") is not None else None
        cost_per_acre = group["expenses"] / area if area and area > 0 else None
        cost_per_quintal = group["expenses"] / group["quantity_quintals"] if group["quantity_quintals"] > 0 else None
        breakdown.append({"crop_id": crop_id, "crop": crop_name, "season": season, "expenses": _money(group["expenses"]), "gross_revenue": _money(group["gross_revenue"]), "selling_costs": _money(group["selling_costs"]), "net_return": _money(group["gross_revenue"] - group["selling_costs"] - group["expenses"]), "quantity_quintals": group["quantity_quintals"], "area_acres": area, "cost_per_acre": _money(cost_per_acre) if cost_per_acre is not None else None, "cost_per_quintal": _money(cost_per_quintal) if cost_per_quintal is not None else None})
    result = {"currency": "INR", "expenses": _money(expense_total), "gross_revenue": _money(gross_revenue), "selling_costs": _money(selling_costs), "net_return": _money(gross_revenue - selling_costs - expense_total), "recorded_sale_quantity_quintals": recorded_quantity, "break_even_price_per_quintal": None, "break_even_status": "expected_saleable_output_required", "breakdown": breakdown}
    if expected_quantity is not None:
        unit = quantity_unit(expected_unit)
        expected_qtl = quantity_in_quintals(expected_quantity, unit)
        if expected_qtl <= 0:
            raise FinanceInputError("expected_quantity must be greater than zero.")
        basis = expense_total + selling_costs
        result["break_even_price_per_quintal"] = _money(basis / expected_qtl)
        result["break_even_status"] = "available"
        avg_price = weighted_quintal_revenue / recorded_quantity if recorded_quantity > 0 else None
        yield_change = yield_change_percent / Decimal(100)
        price_change = price_change_percent / Decimal(100)
        scenario_qtl = expected_qtl * (Decimal(1) + yield_change)
        scenario_price = avg_price * (Decimal(1) + price_change) if avg_price is not None else None
        result["scenario"] = {"assumptions": {"expected_quantity": Decimal(str(expected_quantity)), "quantity_unit": unit, "yield_change_percent": Decimal(str(yield_change_percent)), "price_change_percent": Decimal(str(price_change_percent)), "base_price_source": "weighted average of recorded sales" if avg_price is not None else "unavailable"}, "expected_quantity_quintals": scenario_qtl, "scenario_price_per_quintal": _money(scenario_price) if scenario_price is not None else None, "estimated_net_return": _money(scenario_qtl * scenario_price - basis) if scenario_price is not None and scenario_qtl > 0 else None, "status": "available" if scenario_price is not None and scenario_qtl > 0 else "incomplete_missing_recorded_sale_price"}
    return result
