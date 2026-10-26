"""Deterministic market-price conversions and gross-value calculations."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


CENT = Decimal("0.01")
PER_KG = Decimal("0.0001")
MAX_QUANTITY = Decimal("1000000000")


def parse_quantity(value, unit):
    if unit not in {"kg", "quintal"}:
        raise ValueError("unit must be kg or quintal")
    try:
        quantity = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError):
        raise ValueError("quantity must be a valid positive number") from None
    if not quantity.is_finite() or quantity <= 0 or quantity > MAX_QUANTITY:
        raise ValueError("quantity must be greater than zero and no more than 1,000,000,000")
    quantity_kg = quantity * (Decimal("100") if unit == "quintal" else Decimal("1"))
    return quantity, quantity_kg


def _money(value):
    if value is None:
        return None
    return (Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP))


def calculate_gross_values(quantity_kg, minimum_price, modal_price, maximum_price):
    """Calculate estimates from INR/quintal prices; missing values stay missing."""
    quantity_kg = Decimal(quantity_kg)

    def value_for(price):
        if price is None:
            return None
        rupees_per_kg = Decimal(price) / Decimal("100")
        return _money(quantity_kg * rupees_per_kg)

    return {
        "minimum_price_per_kg": (Decimal(minimum_price) / 100).quantize(PER_KG) if minimum_price is not None else None,
        "modal_price_per_kg": (Decimal(modal_price) / 100).quantize(PER_KG) if modal_price is not None else None,
        "maximum_price_per_kg": (Decimal(maximum_price) / 100).quantize(PER_KG) if maximum_price is not None else None,
        "minimum_value": value_for(minimum_price),
        "expected_value": value_for(modal_price),
        "maximum_value": value_for(maximum_price),
    }


def decimal_strings(values):
    return {key: None if value is None else format(value, ".4f" if key.endswith("_per_kg") else ".2f") for key, value in values.items()}
