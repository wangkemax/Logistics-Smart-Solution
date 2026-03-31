"""
Cost Service
===========
Service layer for financial calculations: CAPEX, OPEX, ROI, payback, headcount.

Responsibilities:
  1. Single scenario financial calculation
  2. Batch comparison across multiple scenarios
  3. Safe division / NaN / rounding guards
  4. Normalized numeric output for UI / PDF / reports
  5. Three operating modes: full_calc / range_estimate / blocked

Called by:
  - pipeline_tasks.py (Stage 3)
  - /api/cost and /api/compare endpoints
  - Future: Agent, CLI

v0.2 CHANGE: Cost Model Agent must now consume downstream_input from
  downstream_input_builder.build_cost_model_input().
  It is the ONLY entry point — direct profile field access is deprecated.
"""

import sys
import traceback
from typing import Optional, Any
from backend.engines.cost_engine import (
    calculate_costs as engine_calculate_costs,
    compare_scenarios as engine_compare_scenarios,
    load_cost_parameters,
)
from backend.engines.automation_engine import normalize_profile


# ---- Field value accessor ----

def _fv(profile: dict, key: str, default=None):
    """
    Safely extract a field value from a profile that may use field objects.

    Handles both legacy raw values and new field object format:
      - profile[key] = 8000           → returns 8000
      - profile[key] = {value: 8000, ...}  → returns 8000
      - profile[key] = None            → returns default
    """
    val = profile.get(key, default)
    if isinstance(val, dict) and "value" in val:
        return val["value"]
    return val if val is not None else default


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
    downstream_input: dict = None,
) -> dict:
    # Defensive: normalize region if passed as field dict ({"value": "华东", ...})
    if isinstance(region, dict):
        region = region.get("value") or region.get("region") or "华东"
    """
    Calculate detailed financials for a single automation scenario.

    v0.2: Accepts downstream_input (from build_cost_model_input()) as the
    authoritative source of field values and usability decisions.
    The three operating modes:

    - full_calc:   All P0 fields provided → normal precise calculation
    - range_estimate: P0 fields complete, P1 missing → best/base/worst estimate
    - blocked:     P0 fields missing/ambiguous → returns mode info, no calc

    Args:
        profile: Project profile dict (legacy, used only if downstream_input absent)
        scenario: Single scenario dict (from recommendation_service output)
        region: Cost parameter region
        downstream_input: Optional downstream_input.cost_model dict.
                        If provided, used instead of raw profile fields.

    Returns:
        {
            "scenario_id": int,
            "scenario_name": str,
            "category": str,
            "calculation_mode": "full_calc" | "range_estimate" | "blocked",
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
            # v0.2 new fields:
            "input_source": {"field_name": "provided" | "assumed" | "blocked"},
            "assumptions_used": list[dict],   # [{field, value, assumption}]
            "downstream_input_meta": {...},
        }
    """
    profile = normalize_profile(profile)
    scenario = _safe_scenario(scenario)
    raw_params = load_cost_parameters(region)
    cost_params = normalize_cost_parameters(raw_params)

    # ---- v0.2: Determine calculation mode from downstream_input ----
    downstream_meta = None
    input_source = {}      # field_key → "provided" | "assumed" | "blocked"
    assumptions_used = []  # list of {field, value, assumption}
    calc_mode = "full_calc"

    if downstream_input is not None:
        downstream_meta = {
            "level": downstream_input.get("readiness", {}).get("level", "unknown"),
            "recommended_mode": downstream_input.get("recommended_mode", "full_calc"),
            "mode_reason": downstream_input.get("mode_reason", ""),
            "p0_summary": downstream_input.get("p0_summary", {}),
            "p1_summary": downstream_input.get("p1_summary", {}),
            "blocking_reasons": downstream_input.get("blocking_reasons", []),
        }
        calc_mode = downstream_input.get("recommended_mode", "full_calc")

        if calc_mode == "blocked":
            blocking_reasons = downstream_input.get("blocking_reasons", [])
            return {
                "scenario_id": scenario.get("scenario_id"),
                "scenario_name": scenario.get("scenario_name", "未知方案"),
                "category": scenario.get("category", ""),
                "calculation_mode": "blocked",
                "capex_estimate": None,
                "opex_annual": None,
                "annual_labor_saving": None,
                "annual_efficiency_saving": None,
                "net_annual_benefit": None,
                "roi_5y": None,
                "roi_3y": None,
                "payback_years": None,
                "payback_years_str": "无法计算（P0字段缺失/歧义）",
                "headcount_saved": None,
                "headcount_required": None,
                "total_annual_cost": None,
                "is_best": False,
                "warnings": ["P0关键字段缺失或歧义，禁止正式成本测算。需先澄清。"],
                "currency_fmt": {"capex": "—", "opex_annual": "—", "annual_saving": "—", "payback": "—"},
                "input_source": {},
                "assumptions_used": [],
                "downstream_input_meta": downstream_meta,
                "blocking_reasons": blocking_reasons,
                "clarification_questions": downstream_input.get("clarification_questions", []),
                "assumptions_template": downstream_input.get("assumptions_template", []),
            }

    # ---- Extract scenario values ----
    scenario_id = scenario.get("scenario_id")
    scenario_name = scenario.get("scenario_name", "未知方案")
    category = scenario.get("category", "")
    labor_saving_ratio = scenario.get("labor_saving", 0)
    efficiency_gain_ratio = scenario.get("efficiency_gain", 0)
    risk_level = scenario.get("risk_level", "中")

    # CAPEX estimate (mid-point of range, or capital_cost_per_sqm * area for AUTO scenarios)
    capex_min = scenario.get("capex_min", 0) or 0
    capex_max = scenario.get("capex_max", 0) or 0
    capital_cost_per_sqm = scenario.get("capital_cost_per_sqm") or 0
    if capital_cost_per_sqm > 0 and (capex_min == 0 and capex_max == 0):
        # AUTO-style scenarios: compute from capital_cost_per_sqm * warehouse_area
        # Extract warehouse_area from profile (may be field dict or plain value)
        wa = profile.get("warehouse_area", 10000)
        if isinstance(wa, dict):
            wa = wa.get("value") or wa.get("fallback_value") or 10000
        try:
            warehouse_area_val = float(wa)
        except (TypeError, ValueError):
            warehouse_area_val = 10000.0
        capex_estimate = capital_cost_per_sqm * warehouse_area_val
    elif capex_max > capex_min:
        capex_estimate = (capex_min + capex_max) / 2
    else:
        capex_estimate = capex_max or capex_min or 0

    # ---- Field value resolution (downstream_input or legacy profile) ----
    def _resolved_val(field_key: str, default=None):
        """
        Resolve field value from downstream_input or legacy profile.

        Updates input_source and assumptions_used as side effects.
        Returns (value, source_tag).
        """
        if downstream_input is not None:
            req_inputs = downstream_input.get("required_inputs", {})
            inp = req_inputs.get(field_key, {})
            if inp.get("usable"):
                status = inp.get("status", "provided")
                val = inp.get("value", default)
                if val is None:
                    # Try fallback value for assumed inputs
                    val = inp.get("fallback_value", default)
                    if inp.get("fallback_value") is not None:
                        input_source[field_key] = "assumed"
                        assumptions_used.append({
                            "field": field_key,
                            "value": val,
                            "assumption": inp.get("fallback_assumption", inp.get("assumption_rule", "")),
                        })
                    else:
                        input_source[field_key] = "provided"
                else:
                    if status in ("provided", "inferred"):
                        input_source[field_key] = "provided"
                    else:
                        input_source[field_key] = status
                return val, input_source[field_key]
            else:
                input_source[field_key] = "blocked"
                return default, "blocked"

        # Legacy fallback
        val = _fv(profile, field_key, default)
        input_source[field_key] = "provided" if val is not None else "blocked"
        return val, input_source[field_key]

    # ---- Core calculations with resolved values ----
    labor_cost_multiplier = {"低": 0.8, "中": 1.0, "高": 1.2}.get(
        _resolved_val("labor_cost_level", "中")[0], 1.0
    )
    labor_cost_per_person = cost_params["labor_cost_per_person_year"] * labor_cost_multiplier

    daily_orders, _ = _resolved_val("daily_orders", 0)
    base_headcount = max(1, int(daily_orders / 150)) if daily_orders else 1

    headcount_saved = base_headcount * labor_saving_ratio
    annual_labor_saving = headcount_saved * labor_cost_per_person

    efficiency_saving_hours = (daily_orders or 0) * efficiency_gain_ratio * 0.01
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

    # Warnings
    warnings = []
    if capex_estimate <= 0:
        warnings.append("CAPEX估值无效（设备投资为0）")
    if net_annual_benefit <= 0:
        warnings.append("年净收益为负或零，方案经济性不足")
    if payback_years and payback_years > 10:
        warnings.append(f"回本周期较长（{payback_years:.1f}年），建议重新评估")
    if risk_level == "高":
        warnings.append("方案风险等级为高，建议分阶段实施")
    if calc_mode == "range_estimate":
        warnings.append("⚠️ 当前为区间估算模式，部分数据为假设值，不可作为正式报价依据")
        warnings.append("  假设项：" + ", ".join(a["field"] for a in assumptions_used) if assumptions_used else "")
    if any(v == "blocked" for v in input_source.values()):
        blocked_fields = [k for k, v in input_source.items() if v == "blocked"]
        warnings.append(f"⚠️ 以下字段无法使用（blocked）: {', '.join(blocked_fields)}")

    # Mode-specific note
    mode_label = {"full_calc": "正式测算", "range_estimate": "区间估算", "blocked": "已阻塞"}.get(calc_mode, "")
    if mode_label:
        warnings.append(f"计算模式: {mode_label}")

    return {
        "scenario_id": scenario_id,
        "scenario_name": scenario_name,
        "category": category,
        "calculation_mode": calc_mode,
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
        # Y1 EBITA fields
        "y1_revenue": _round2(annual_labor_saving + annual_efficiency_saving),
        "y1_operating_cost": _round2(opex_annual),
        "y1_ebita": _round2(net_annual_benefit),
        "currency_fmt": {
            "capex": _fmt_currency(capex_estimate),
            "opex_annual": _fmt_currency(opex_annual),
            "annual_saving": _fmt_currency(net_annual_benefit),
            "payback": f"{payback_years:.1f}年" if payback_years else "—",
        },
        # v0.2 new fields
        "input_source": input_source,
        "assumptions_used": assumptions_used,
        "downstream_input_meta": downstream_meta,
    }


def _estimate_headcount(profile: dict) -> int:
    """Estimate warehouse headcount using orders ÷ manual efficiency rate.
    Mirrors the cost_engine logic so both services use the same baseline.
    manual baseline = 150 orders/person/day
    Minimum 1 to avoid div-by-zero in downstream calculations.
    """
    daily_orders = _fv(profile, "daily_orders") or 0
    base_hc = max(1, int(daily_orders / 150))
    return max(1, base_hc)


# ---- Batch comparison ----

def compare_solution_financials(
    profile: dict,
    scenarios: list[dict],
    region: str = "华东",
    downstream_input: dict = None,
) -> list[dict]:
    """
    Calculate and compare financials for multiple scenarios.

    Args:
        profile: Project profile dict
        scenarios: List of scenario dicts (from recommendation_service)
        region: Cost parameter region
        downstream_input: Optional downstream_input.cost_model dict.
                        If provided, passed to each calculate_solution_financials call.

    Returns:
        List of financial results, sorted by ROI desc, with is_best flag on top.
        Blocked scenarios are included with calculation_mode="blocked".
    """
    if not scenarios:
        return []

    results = []
    for scenario in scenarios:
        try:
            result = calculate_solution_financials(profile, scenario, region, downstream_input)
            results.append(result)
        except Exception as e:
            # Skip scenarios that fail financial calc — don't crash the whole batch
            print(f"[cost_service] scenario {scenario.get('scenario_id')} calc failed: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            continue

    if not results:
        return []

    # Sort: blocked scenarios last, then by ROI desc
    def _sort_key(r):
        if r.get("calculation_mode") == "blocked":
            return (-1, 0)  # blocked go last
        return (0, -(r.get("roi_5y") or 0))
    results.sort(key=_sort_key)

    # Mark best (skip blocked scenarios)
    for r in results:
        if r.get("calculation_mode") != "blocked":
            r["is_best"] = True
            break

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
