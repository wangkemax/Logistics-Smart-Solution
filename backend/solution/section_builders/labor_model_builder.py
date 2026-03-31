"""
labor_model_builder.py — v0.8
==============================
Builds LaborModel section for BaseSolution.
Rule-of-thumb headcount estimation per scale tier + service scope,
with region cost index and labor cost level adjustment.
"""

from __future__ import annotations

import math
from backend.schemas.base_solution_schema import LaborModel, ScaleTier


# Region → labor cost adjustment factor (华东 = 1.0 baseline)
REGION_COST_INDEX: dict[str, float] = {
    "华东": 1.00,
    "华南": 0.95,
    "华北": 1.05,
    "华中": 0.98,
    "西部": 0.92,
    "东北": 1.00,
}

# Labor cost level → base monthly cost per person (元/月) in 华东 baseline
LABOR_COST_PER_PERSON_MONTH: dict[str, float] = {
    "低": 4500.0,
    "中": 6500.0,
    "高": 9000.0,
}

# Scale tier → base headcount per role
_HEADCOUNT_BASE: dict[ScaleTier, dict[str, int]] = {
    ScaleTier.XS: {
        "receiving_team": 2,
        "picking_team": 3,
        "loading_team": 1,
        "support_team": 1,
    },
    ScaleTier.S: {
        "receiving_team": 4,
        "picking_team": 6,
        "loading_team": 2,
        "support_team": 2,
    },
    ScaleTier.M: {
        "receiving_team": 8,
        "picking_team": 12,
        "loading_team": 4,
        "support_team": 3,
    },
    ScaleTier.L: {
        "receiving_team": 15,
        "picking_team": 25,
        "loading_team": 8,
        "support_team": 5,
    },
    ScaleTier.XL: {
        "receiving_team": 25,
        "picking_team": 40,
        "loading_team": 15,
        "support_team": 8,
    },
}

# Typical daily orders per scale tier
_TYPICAL_ORDERS: dict[ScaleTier, float] = {
    ScaleTier.XS: 500,
    ScaleTier.S:  2000,
    ScaleTier.M:  8000,
    ScaleTier.L:  25000,
    ScaleTier.XL: 60000,
}

# Shift structure by scale tier
SHIFT_BY_SCALE: dict[ScaleTier, str] = {
    ScaleTier.XS: "一班制（8小时/天）",
    ScaleTier.S:  "一班制为主（10小时/天）",
    ScaleTier.M:  "两班倒（白班 7:00-19:00 / 夜班 19:00-7:00）",
    ScaleTier.L:  "两班倒 + 周末值班（7天运营）",
    ScaleTier.XL: "三班倒（8小时×3班）或 24h 连续运营",
}

# Working hours per day by scale tier
WORKING_HOURS_BY_SCALE: dict[ScaleTier, float] = {
    ScaleTier.XS: 8.0,
    ScaleTier.S:  10.0,
    ScaleTier.M:  16.0,
    ScaleTier.L:  22.0,
    ScaleTier.XL: 24.0,
}

# Role labels in Chinese
_ROLE_LABELS: dict[str, str] = {
    "receiving_team": "收货团队",
    "picking_team": "拣选团队",
    "loading_team": "装车团队",
    "support_team": "支持团队",
    "va_team": "增值加工团队",
    "qc_team": "质检团队",
    "return_team": "退货处理团队",
    "it_support": "IT 支持",
    "line_side_team": "线边配送团队",
    "tooling_team": "器具管理团队",
}


def build_labor_model(
    *,
    warehouse_area: float,
    daily_orders: float,
    service_scope: dict,
    region: str,
    labor_cost_level: str,
    scale_tier: ScaleTier,
    industry: str = "GENERIC_3PL",
) -> LaborModel:
    """
    Build LaborModel from resolved project fields.

    Uses rule-of-thumb estimation based on scale tier.
    Headcount scales with daily_orders ratio when orders exceed typical volume.

    Parameters
    ----------
    warehouse_area : float
        in sqm
    daily_orders : float
        orders per day
    service_scope : dict
        service scope dict
    region : str
        e.g. "华东"
    labor_cost_level : str
        "低" / "中" / "高"
    scale_tier : ScaleTier

    Returns
    -------
    LaborModel
    """
    region_factor = REGION_COST_INDEX.get(region, 1.0)
    base_cost = LABOR_COST_PER_PERSON_MONTH.get(labor_cost_level, 6500.0)
    adjusted_cost_per_person = base_cost * region_factor

    # Base headcount by role
    headcount = dict(_HEADCOUNT_BASE.get(scale_tier, _HEADCOUNT_BASE[ScaleTier.M]))

    # Scale headcount if daily_orders >> typical
    typical_orders = _TYPICAL_ORDERS.get(scale_tier, 8000)
    if daily_orders and daily_orders > 0:
        ratio = daily_orders / typical_orders
        if ratio > 1.5:
            # Scale up proportionally for peak volumes
            scale_factor = min(ratio, 3.0)  # cap at 3x to avoid unrealistic numbers
            for role in headcount:
                headcount[role] = int(math.ceil(headcount[role] * scale_factor))

    # Add roles based on service scope and industry
    va = service_scope.get("value_added", {})
    if va.get("kitting") or va.get("repack") or va.get("light_assembly"):
        headcount["va_team"] = headcount.get("va_team", 0) + 3

    if va.get("return_handling"):
        headcount["return_team"] = headcount.get("return_team", 0) + 2

    inbound = service_scope.get("inbound", {})
    if inbound.get("quality_check"):
        headcount["qc_team"] = headcount.get("qc_team", 0) + 2

    support = service_scope.get("support", {})
    if support.get("system_integration"):
        headcount["it_support"] = headcount.get("it_support", 0) + 1

    # Automotive-specific roles
    # industry comes from resolved fields, normalized above
    industry = kwargs.get("industry", "GENERIC_3PL")
    if industry == "AUTOMOTIVE":
        # Automotive adds line-side feeding,器具 management, sequencing
        headcount["line_side_team"] = headcount.get("line_side_team", 0) + 4
        headcount["tooling_team"] = headcount.get("tooling_team", 0) + 2

    # Total monthly labor cost
    total_monthly = sum(headcount.values()) * adjusted_cost_per_person

    return LaborModel(
        headcount_by_role=headcount,
        shift_structure=SHIFT_BY_SCALE.get(scale_tier, "两班倒"),
        working_hours_per_day=WORKING_HOURS_BY_SCALE.get(scale_tier, 16.0),
        labor_cost_per_person_month=adjusted_cost_per_person,
        labor_cost_per_month=total_monthly,
        annual_labor_cost=total_monthly * 12,
        labor_cost_adjustment_factor=region_factor,
        narrative="",
    )
