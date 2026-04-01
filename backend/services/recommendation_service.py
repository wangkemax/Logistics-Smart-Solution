"""
Recommendation Service
=====================
Service layer for automation scenario recommendations.

Responsibilities:
  1. Input normalization — normalize_profile at entry
  2. Engine delegation — call recommend_automation()
  3. Result shaping — sort, top_n, default strategy, no-result guard
  4. Explanation generation — add "reasons" to every recommendation

Called by:
  - pipeline_tasks.py (Stage 2)
  - /api/recommend endpoint
  - Future: Agent, CLI
"""

from typing import Optional
from backend.engines.automation_engine import (
    recommend_automation,
    normalize_profile,
)


# ---- Match level thresholds ----
MATCH_LEVEL_THRESHOLDS = {
    "高": 70,   # score >= 70  → 高匹配
    "中": 45,   # 45 <= score < 70 → 中匹配
    "低": 0,    # score < 45  → 低匹配
}


def _get_match_level(score: float) -> str:
    """Convert numeric score to match level label."""
    if score >= MATCH_LEVEL_THRESHOLDS["高"]:
        return "高"
    elif score >= MATCH_LEVEL_THRESHOLDS["中"]:
        return "中"
    return "低"


def _generate_reasons(scenario: dict, profile: dict, score_breakdown: dict = None) -> list[str]:
    """
    Generate human-readable reasons — highlights top contributing dimensions from score_breakdown.
    """
    reasons = []
    area = profile.get("warehouse_area", 0)
    sku = profile.get("sku_count", 0)
    orders = profile.get("daily_orders", 0)
    industry = profile.get("industry", "")
    budget = profile.get("budget_level", "中")

    top_dims = []
    if score_breakdown:
        sorted_dims = sorted(score_breakdown.items(), key=lambda x: x[1], reverse=True)
        top_dims = [d[0] for d in sorted_dims[:3] if d[1] > 0]

    # Industry match
    applicable = scenario.get("applicable_industry", "")
    if industry and industry in applicable:
        reasons.append(f"适合{industry}行业应用场景")

    # Area suitability
    if area and scenario.get("category"):
        cat = scenario.get("category", "")
        if area > 20000 and cat in ["立体仓库", "货到人", "移动机器人"]:
            reasons.append(f"大面积仓库（{area:,.0f}m²）适合{cat}方案")
        elif area < 5000 and cat in ["自动化辅助", "软件系统"]:
            reasons.append(f"小面积仓库适合轻量级{cat}方案")

    # SKU complexity
    if sku:
        if sku > 50000:
            reasons.append("SKU品类多（>5万），需要精细化管理自动化")
        elif sku > 10000:
            reasons.append(f"SKU规模（{sku:,}）处于中等复杂度，适合自动化升级")

    # Order volume
    if orders:
        if orders > 10000:
            reasons.append(f"日订单量（{orders:,}单/天）大，人工效率低，适合机器人方案")
        elif orders > 2000:
            reasons.append(f"日订单量（{orders:,}单/天）中等，可通过自动化提升效率")

    # Labor savings
    labor_saving = scenario.get("labor_saving", 0)
    if labor_saving and labor_saving > 0:
        reasons.append(f"预计可节省人工{int(labor_saving * 100)}%（{scenario.get('scenario_name', '该方案')}）")

    # Efficiency gain
    eff = scenario.get("efficiency_gain", 0)
    if eff and eff > 0:
        reasons.append(f"效率提升约{int(eff * 100)}%，缩短订单处理时间")

    # Budget alignment
    capex_min = scenario.get("capex_min", 0) or 0
    if budget == "高" and capex_min < 5000000:
        reasons.append("高预算项目，可考虑高投入高回报方案")
    elif budget == "低" and capex_min < 1000000:
        reasons.append("低预算项目，适合轻量化、渐进式自动化方案")

    # Risk level
    risk = scenario.get("risk_level", "中")
    if risk == "低":
        reasons.append("风险等级低，实施稳定性高")
    elif risk == "高":
        reasons.append("风险较高，建议分阶段实施，做好预案")

    # Highlight top contributing dimensions
    if top_dims:
        dim_labels = {"industry": "行业匹配", "area": "面积适配", "sku": "SKU复杂度",
                      "orders": "订单量匹配", "budget": "预算覆盖"}
        top_labels = [dim_labels.get(d, d) for d in top_dims if d in dim_labels]
        if top_labels:
            reasons.insert(0, f"【核心匹配因素】：{'、'.join(top_labels)}")

    # Fallback
    if not reasons:
        reasons.append(f"综合评分{int(scenario.get('score', 0))}分，满足基本适用条件")

    return reasons


def recommend_solutions(
    profile: dict,
    top_n: int = 5,
    include_reasons: bool = True,
) -> dict:
    """
    Main entry point for recommendation service.

    Args:
        profile: Raw project profile dict (may contain None values)
        top_n: Maximum number of recommendations to return
        include_reasons: Whether to generate explanation strings for each result

    Returns:
        {
            "recommendations": [  # sorted by score descending
                {
                    "scenario_id": int,
                    "scenario_name": str,
                    "category": str,
                    "score": float,
                    "match_level": str,   # "高" | "中" | "低"
                    "reasons": list[str],  # why this scenario matched
                    "input_profile_snapshot": dict,
                    # engine raw fields also included:
                    "capex_range": str,
                    "labor_saving": float,
                    "efficiency_gain": float,
                    "risk_level": str,
                },
                ...
            ],
            "total_profiles_normalized": dict,   # normalized input snapshot
            "match_distribution": {"高": int, "中": int, "低": int},
        }
    """
    # 1. Normalize input once
    # Detect field-trace format: either nested _field_traces/normalized_fields,
    # OR top-level profile values are themselves field-trace dicts.
    _top_is_ft = isinstance(profile.get("industry"), dict) and "value" in profile["industry"]
    _nf = profile.get("_field_traces") or profile.get("normalized_fields") or {}
    _has_nested_ft = bool(_nf and any(isinstance(v, dict) and "value" in v for v in _nf.values()))

    if _top_is_ft or _has_nested_ft:
        # Field-trace format: extract scalar values for recommendation engine
        normalized = {}
        scalar_keys = [
            "project_name", "client_name", "industry", "region",
            "warehouse_area", "sku_count", "daily_orders", "inventory",
            "labor_cost_level", "budget_level", "automation_expectation",
            "contract_years", "go_live_date", "dc_count",
        ]
        for key in scalar_keys:
            # Check top-level field-trace first, then nested _field_traces
            entry = profile.get(key) if _top_is_ft else None
            if not (isinstance(entry, dict) and "value" in entry):
                entry = _nf.get(key) if _has_nested_ft else None
            if isinstance(entry, dict) and "value" in entry:
                normalized[key] = entry["value"]
            else:
                normalized[key] = profile.get(key)  # fallback to raw
        _field_traces = _nf or (_top_is_ft and profile)
    else:
        normalized = normalize_profile(profile)
        _field_traces = None

    # 2. Get ranked scenarios from engine
    raw_scenarios = recommend_automation(normalized)

    # 3. No-result guard
    if not raw_scenarios:
        return {
            "recommendations": [],
            "total_profiles_normalized": normalized,
            "match_distribution": {"高": 0, "中": 0, "低": 0},
        }

    # 4. Build recommendation list with reasons
    recommendations = []
    match_counts = {"高": 0, "中": 0, "低": 0}

    for scenario in raw_scenarios:
        score = scenario.get("score", 0)
        match_level = _get_match_level(score)
        match_counts[match_level] += 1

        score_breakdown = scenario.get("score_breakdown", {})

        item = {
            "scenario_id": scenario.get("scenario_id"),
            "scenario_code": scenario.get("scenario_code"),  # may be None for legacy scenarios
            "scenario_name": scenario.get("scenario_name"),
            "category": scenario.get("category", ""),
            "score": round(score, 1),
            "score_breakdown": score_breakdown,
            "match_level": match_level,
            "input_profile_snapshot": normalized.copy(),
            "capex_range": _format_capex_range(scenario),
            "capex_min": scenario.get("capex_min", 0) or 0,
            "capex_max": scenario.get("capex_max", 0) or 999999999,
            # AUTO-style cost fields
            "capital_cost_per_sqm": scenario.get("capital_cost_per_sqm") or 0,
            "annual_savings_per_sqm": scenario.get("annual_savings_per_sqm") or 0,
            "labor_saving": scenario.get("labor_saving", 0),
            "efficiency_gain": scenario.get("efficiency_gain", 0),
            "risk_level": scenario.get("risk_level", "中"),
            "scoring_strategy": scenario.get("scoring_strategy", "weighted_v1"),
        }

        if include_reasons:
            item["reasons"] = _generate_reasons(scenario, normalized, score_breakdown)

            item["risk"] = scenario.get("risk", "") or "需要详细评估实施风险"
        recommendations.append(item)

    # 5. Apply top_n and sort by score desc
    recommendations = sorted(recommendations, key=lambda x: x["score"], reverse=True)[:top_n]

    return {
        "recommendations": recommendations,
        "total_profiles_normalized": normalized,
        "field_traces": _field_traces,   # preserved field metadata for downstream cost model
        "match_distribution": match_counts,
    }


def _format_capex_range(scenario: dict) -> str:
    """Format capex range as human-readable string."""
    capex_min = scenario.get("capex_min", 0) or 0
    capex_max = scenario.get("capex_max", 0) or 0
    if not capex_min and not capex_max:
        return "待评估"
    if capex_min and capex_max:
        return f"¥{capex_min/10000:.0f}万~¥{capex_max/10000:.0f}万"
    elif capex_min:
        return f"¥{capex_min/10000:.0f}万起"
    return f"最高¥{capex_max/10000:.0f}万"


# ---- Backward-compatible wrapper ----
def get_recommendations(profile_dict: dict) -> dict:
    """
    Legacy wrapper for existing callers (pipeline_tasks, API routes).
    Converts new format to old format for compatibility.
    """
    result = recommend_solutions(profile_dict, top_n=5, include_reasons=False)
    recs = result["recommendations"]

    top = recs[0] if recs else None
    top_name = top["scenario_name"] if top else "暂无推荐"

    normalized = result["total_profiles_normalized"]
    industry = normalized.get("industry", "未知")
    sku = normalized.get("sku_count", 0)
    orders = normalized.get("daily_orders", 0)
    sku_desc = "高SKU" if sku and sku > 10000 else "低SKU"
    order_desc = "高订单量" if orders and orders > 2000 else "低订单量"

    summary = (
        f"基于{industry}行业特征，{sku_desc}({sku:,} SKU)和{order_desc}({orders:,}单/天)的运营特点，"
        f"系统推荐优先考虑{top_name}方案。"
    )

    # Return old format for backward compat
    return {
        "recommendations": [
            {
                "scenario_id": r["scenario_id"],
                "scenario_name": r["scenario_name"],
                "category": r["category"],
                "score": r["score"],
                "reason": r.get("reasons", ["综合推荐"])[0] if r.get("reasons") else "综合推荐",
                "risk": r.get("risk_level", "中"),
                "capex_range": r.get("capex_range", ""),
                "labor_saving": r.get("labor_saving", 0),
                "efficiency_gain": r.get("efficiency_gain", 0),
            }
            for r in recs
        ],
        "top_recommendation": top_name,
        "analysis_summary": summary,
    }
