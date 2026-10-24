"""Range checks for numbers copied out of an RFP before they become assumptions."""
from __future__ import annotations

# Inclusive bounds. Values outside these are rejected instead of stored.
NUMERIC_RANGES = {
    "warehouse_area": (50, 2_000_000),       # m²
    "dc_count": (1, 200),
    "sku_count": (1, 5_000_000),
    "daily_orders": (1, 5_000_000),
    "peak_orders": (1, 10_000_000),
    "contract_years": (1, 30),
    "throughput_requirement": (1, 1_000_000_000),
}


def acceptable_assumption_value(field_key: str, value) -> bool:
    if field_key not in NUMERIC_RANGES:
        return True
    try:
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return False
    low, high = NUMERIC_RANGES[field_key]
    return low <= number <= high
