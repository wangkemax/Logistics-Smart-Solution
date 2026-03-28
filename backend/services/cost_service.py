"""
Cost Service
===========
Service layer for financial calculations: CAPEX, OPEX, ROI, payback, headcount.

Responsibilities:
  1. Single scenario financial calculation
  2. Batch comparison across multiple scenarios
  3. Safe division / NaN / rounding guards
  4. Normalized numeric output for UI / PDF / reports

Called by:
  - pipeline_tasks.py (Stage 3)
  - /api/cost and /api/compare endpoints
  - Future: Agent, CLI
"""

from typing import Optional, Any
from backend.engines.cost_engine import (
    calculate_costs as engine_calculate_costs,
    compare_scenarios as engine_compare_scenarios,
    load_cost_parameters,
)
from backend.engines.automation_engine import normalize_profile


# ---- Cost parameter normalization ----

def normalize_cost_parameters(cost_params: dict) -> dict:
    """
    Normalize cost parameters to internal standard field names.

    Ensures all downstream calculations read from a consistent schema:
      - labor_cost_per_person_year  (internal standard)
      - labor                      (alias, preserved for backward compat)

    Returns a copy — never mutates the input.
    """
    cost_params = cost_params or {}
    warnings = []

    # Resolve labor_cost_per_person_year: prefer explicit field, fall back to "labor" alias
    labor = (
        cost_params.get("labor_cost_per_person_year")
        or cost_params.get("labor")
    )
    if labor is None:
        labor = 100000
        warnings.append("labor_cost_per_person_year missing; fallback to default 100000")

    return {
        **cost_params,
        "labor_cost_per_person_year": labor,
        "labor": labor,                              # keep alias for any legacy reads
        "_warnings": warnings,
    }


# ---- Safe numeric helpers ----

def _safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Division with zero-guard."""
    if denominator == 0:
        return default
    return numerator / denominator


def _round2(x: Optional[float]) -> float:
    """Round to 2 decimal places, default to 0."""
    if x is None:
        return 0.0
    return round(float(x), 2)


def _fmt_currency(x: Optional[float]) -> str:
    """Format as Chinese currency string."""
    if x is None or x <= 0:
        return "¥0"
    if x >= 100000000:
        return f"¥{x/100000000:.1f}亿"
    if x >= 10000:
        return f"¥{x/10000:.0f}万"
    return f"¥{x:,.0f}"


# ---- Normalize scenario bounds (safe defaults) ----

def _safe_scenario(scenario: dict) -> dict:
    """Ensure scenario has safe numeric defaults."""
    return {
        **scenario,
        "capex_min": scenario.get("capex_min") if scenario.get("capex_min") is not None else 0,
        "capex_max": scenario.get("capex_max") if scenario.get("capex_max") is not None else 999999999,
        "labor_saving": scenario.get("labor_saving") or 0,
        "efficiency_gain": scenario.get("efficiency_gain") or 0,
    }


# ---- Single scenario financial calculation ----

def calculate_solution_financials(
    profile: dict,
    scenario: dict,
    region: str = "华东",
) -> dict:
    """
    Calculate detailed financials for a single automation scenario.

    Args:
        profile: Project profile dict
        scenario: Single scenario dict (from recommendation_service output)
        region: Cost parameter region

    Returns:
        {
            "scenario_id": int,
            "scenario_name": str,
            "category": str,
            "capex_estimate": float,
            "opex_annual": float,
            "annual_labor_saving": float,
            "annual_efficiency_saving": float,
            "net_annual_benefit": float,
            "roi_5y": float,
            "roi_3y": float,
            "payback_years": float,
            "payback_years_str": str,
            "headcount_saved": float,
            "headcount_required": int,
            "total_annual_cost": float,
            "is_best": bool,
            "warnings": list[str],
            "currency_fmt": {...},
        }
    """
    profile = normalize_profile(profile)
    scenario = _safe_scenario(scenario)
    raw_params = load_cost_parameters(region)
    cost_params = normalize_cost_parameters(raw_params)

    # Extract scenario values
    scenario_id = scenario.get("scenario_id")
    scenario_name = scenario.get("scenario_name", "未知方案")
    category = scenario.get("category", "")
    labor_saving_ratio = scenario.get("labor_saving", 0)
    efficiency_gain_ratio = scenario.get("efficiency_gain", 0)
    risk_level = scenario.get("risk_level", "中")

    # CAPEX estimate (mid-point of range)
    capex_min = scenario.get("capex_min", 0)
    capex_max = scenario.get("capex_max", 999999999)
    capex_estimate = (capex_min + capex_max) / 2 if capex_max > capex_min else capex_min

    # Labor savings
    labor_cost_multiplier = {"低": 0.8, "中": 1.0, "高": 1.2}.get(profile.get("labor_cost_level", "中"), 1.0)
    labor_cost_per_person = cost_params["labor_cost_per_person_year"] * labor_cost_multiplier
    base_headcount = _estimate_headcount(profile)
    headcount_saved = base_headcount * labor_saving_ratio
    annual_labor_saving = headcount_saved * labor_cost_per_person

    # Efficiency gain value (estimate as labor-hours equivalent)
    daily_orders = profile.get("daily_orders", 0)
    efficiency_saving_hours = daily_orders * efficiency_gain_ratio * 0.01  # rough estimate
    annual_efficiency_saving = efficiency_saving_hours * cost_params["labor_cost_per_person_year"]

    # OPEX (annual maintenance, ~8% of CAPEX for automation systems)
    opex_annual = capex_estimate * 0.08

    # Net annual benefit
    net_annual_benefit = annual_labor_saving + annual_efficiency_saving - opex_annual

    # ROI calculations
    roi_5y = _safe_div(net_annual_benefit * 5, capex_estimate)
    roi_3y = _safe_div(net_annual_benefit * 3, capex_estimate)

    # Payback period
    payback_years = _safe_div(capex_estimate, net_annual_benefit) if net_annual_benefit > 0 else None

    # Headcount required (remaining after automation)
    headcount_required = max(1, int(round(base_headcount * (1 - labor_saving_ratio))))

    # Warnings for edge cases
    warnings = []
    if capex_estimate <= 0:
        warnings.append("CAPEX估值无效（设备投资为0）")
    if net_annual_benefit <= 0:
        warnings.append("年净收益为负或零，方案经济性不足")
    if payback_years and payback_years > 10:
        warnings.append(f"回本周期较长（{payback_years:.1f}年），建议重新评估")
    if risk_level == "高":
        warnings.append("方案风险等级为高，建议分阶段实施")

    return {
        "scenario_id": scenario_id,
        "scenario_name": scenario_name,
        "category": category,
        "capex_estimate": _round2(capex_estimate),
        "opex_annual": _round2(opex_annual),
        "annual_labor_saving": _round2(annual_labor_saving),
        "annual_efficiency_saving": _round2(annual_efficiency_saving),
        "net_annual_benefit": _round2(net_annual_benefit),
        "roi_5y": _round2(roi_5y),
        "roi_3y": _round2(roi_3y),
        "payback_years": _round2(payback_years) if payback_years else None,
        "payback_years_str": f"{payback_years:.1f}年" if payback_years else "无法计算",
        "headcount_saved": _round2(headcount_saved),
        "headcount_required": headcount_required,
        "total_annual_cost": _round2(opex_annual + base_headcount * labor_cost_per_person * (1 - labor_saving_ratio)),
        "is_best": False,
        "warnings": warnings,
        "currency_fmt": {
            "capex": _fmt_currency(capex_estimate),
            "opex_annual": _fmt_currency(opex_annual),
            "annual_saving": _fmt_currency(net_annual_benefit),
            "payback": f"{payback_years:.1f}年" if payback_years else "—",
        },
    }


def _estimate_headcount(profile: dict) -> int:
    """Estimate warehouse headcount using orders ÷ manual efficiency rate.
    Mirrors the cost_engine logic so both services use the same baseline.
    manual baseline = 150 orders/person/day
    Minimum 1 to avoid div-by-zero in downstream calculations.
    """
    daily_orders = profile.get("daily_orders") or 0
    base_hc = max(1, int(daily_orders / 150))
    return max(1, base_hc)


# ---- Batch comparison ----

def compare_solution_financials(
    profile: dict,
    scenarios: list[dict],
    region: str = "华东",
) -> list[dict]:
    """
    Calculate and compare financials for multiple scenarios.

    Args:
        profile: Project profile dict
        scenarios: List of scenario dicts (from recommendation_service)
        region: Cost parameter region

    Returns:
        List of financial results, sorted by ROI desc, with is_best flag on top.
    """
    if not scenarios:
        return []

    results = []
    for scenario in scenarios:
        try:
            result = calculate_solution_financials(profile, scenario, region)
            results.append(result)
        except Exception:
            # Skip scenarios that fail financial calc — don't crash the whole batch
            continue

    if not results:
        return []

    # Sort by 5-year ROI desc
    results.sort(key=lambda x: x["roi_5y"] or 0, reverse=True)

    # Mark best
    results[0]["is_best"] = True

    return results


# ---- Backward-compatible wrappers ----

def get_cost_analysis(profile_dict: dict, region: str = "华东",
                      selected_scenario_id: int = None) -> dict:
    """Legacy wrapper for existing API callers."""
    cost_data = engine_calculate_costs(profile_dict, region, selected_scenario_id)
    from backend.engines.cost_engine import generate_cost_summary, generate_cost_recommendations
    return {
        "cost_breakdown": cost_data,
        "summary": generate_cost_summary(cost_data),
        "recommendations": generate_cost_recommendations(cost_data, profile_dict),
    }


def get_scenario_comparison(profile_dict: dict, region: str,
                            scenario_ids: list) -> dict:
    """Legacy wrapper for existing API callers."""
    comparisons = engine_compare_scenarios(profile_dict, region, scenario_ids)
    best = next((c for c in comparisons if c.get("is_best")), None)
    best_id = best["scenario_id"] if best else None
    normalized = normalize_profile(profile_dict)
    industry = normalized.get("industry", "")

    if best:
        best_name = best["scenario_name"]
        roi_5y = best.get("roi_5y") or 0
        payback = best.get("payback_years") or 0
        summary = (
            f"基于{industry}行业的运营特征，在{len(comparisons)}个方案中，"
            f"【{best_name}】综合表现最优：5年ROI {roi_5y:.1f}x，回本周期 {payback:.1f}年，"
            f"建议作为首选方案。"
        )
    else:
        summary = f"未能生成有效对比结果，请检查所选方案ID是否正确。"

    return {
        "comparisons": comparisons,
        "best_scenario_id": best_id,
        "analysis_summary": summary,
    }
