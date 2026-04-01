"""backend/services/parameter_service.py Parameter library service for v0.9 — reads CSV parameter files """
from __future__ import annotations

import csv
import os
from typing import Optional

from backend.schemas.assumption_schemas import AssumptionSchema, AssumptionSourceType

# Priority weights for multi-key CSV matching
PRIORITY_WEIGHT = {"industry_region": 100, "industry_default": 80, "region_default": 50, "global": 10}

DATA_DIR = os.path.join(os.path.dirname(__file__), "../../data/parameters")


def _load_csv(filename: str) -> list[dict]:
    path = os.path.join(DATA_DIR, filename)
    rows = []
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
    return rows


def _match_score(row: dict, industry: str, region: str) -> int:
    """Compute match priority score for a CSV row."""
    row_industry = row.get("industry", "*").strip()
    row_region = row.get("region", "*").strip()

    if row_industry == "*" and row_region == "*":
        return PRIORITY_WEIGHT["global"]
    elif row_industry == industry and row_region == region:
        return PRIORITY_WEIGHT["industry_region"]
    elif row_industry == industry and row_region == "*":
        return PRIORITY_WEIGHT["industry_default"]
    elif row_industry == "*" and row_region == region:
        return PRIORITY_WEIGHT["region_default"]
    return 0


def get_assumption_defaults(
    field_key: str,
    industry: str,
    region: str = "华东",
) -> Optional[AssumptionSchema]:
    """Get default assumption for a field/industry/region combination."""
    rows = _load_csv("assumption_defaults.csv")

    candidates = []
    for row in rows:
        if row.get("field_key", "").strip() != field_key:
            continue
        score = _match_score(row, industry, region)
        if score > 0:
            confidence = float(row.get("confidence", "0.5"))
            scaled_confidence = min(confidence * score / 100, 1.0)
            candidates.append((score, row, scaled_confidence))

    if not candidates:
        return None

    candidates.sort(key=lambda x: (x[0], x[2]), reverse=True)
    _, row, scaled_conf = candidates[0]

    return AssumptionSchema(
        field_key=field_key,
        value=row.get("default_value", ""),
        rule=row.get("rule", ""),
        source="default_fallback",
        source_type=AssumptionSourceType.SYSTEM_DEFAULT.value,
        confidence=scaled_conf,
        is_overridden=False,
        validated=False,
        benchmark_ref=row.get("benchmark", ""),
    )


def get_cost_indices(region: str) -> dict:
    """Get cost indices for a region."""
    rows = _load_csv("cost_indices.csv")
    for row in rows:
        if row.get("region", "").strip() == region:
            return {
                "warehouse_rent_per_sqm": float(row.get("warehouse_rent_per_sqm", 600)),
                "labor_cost_per_person_year": float(row.get("labor_cost_per_person_year", 80000)),
                "equipment_maintenance_rate": float(row.get("equipment_maintenance_rate", 0.05)),
                "overhead_rate": float(row.get("overhead_rate", 0.15)),
                "pallet_density": float(row.get("pallet_density", 4)),
            }
    # Default to 华东
    for row in rows:
        if row.get("region", "").strip() == "华东":
            return {
                "warehouse_rent_per_sqm": float(row.get("warehouse_rent_per_sqm", 600)),
                "labor_cost_per_person_year": float(row.get("labor_cost_per_person_year", 80000)),
                "equipment_maintenance_rate": float(row.get("equipment_maintenance_rate", 0.05)),
                "overhead_rate": float(row.get("overhead_rate", 0.15)),
                "pallet_density": float(row.get("pallet_density", 4)),
            }
    # Hard fallback
    return {
        "warehouse_rent_per_sqm": 600.0,
        "labor_cost_per_person_year": 80000.0,
        "equipment_maintenance_rate": 0.05,
        "overhead_rate": 0.15,
        "pallet_density": 4.0,
    }


def get_industry_overhead(industry: str) -> float:
    """Get overhead multiplier for an industry."""
    rows = _load_csv("industry_overhead.csv")
    for row in rows:
        if row.get("industry", "").strip() == industry:
            return float(row.get("overhead", "1.0"))
    return 1.0  # Default


def get_all_defaults_for_project(
    industry: str,
    region: str,
    p1_field_keys: list[str],
) -> list[AssumptionSchema]:
    """Get all default assumptions for a project's P1 fields."""
    results = []
    for field_key in p1_field_keys:
        assumption = get_assumption_defaults(field_key, industry, region)
        if assumption:
            results.append(assumption)
    return results
