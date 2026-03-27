from typing import List, Dict, Any
import pandas as pd
import os


INDUSTRY_MAPPING = {
    "电商": ["电商", "3PL", "快递"],
    "3PL": ["3PL", "电商", "零售"],
    "零售": ["零售", "电商", "3PL"],
    "制造": ["制造", "3PL"],
    "快递": ["快递", "电商"],
    "医药": ["医药", "3PL"],
    "食品": ["食品", "医药"],
    "生鲜": ["生鲜", "食品"],
}

BUDGET_THRESHOLDS = {
    "低": 1000000,
    "中": 5000000,
    "高": 20000000,
}

AUTOMATION_LEVEL_WEIGHTS = {
    "低": 0.7,
    "中": 1.0,
    "高": 1.3,
}


def load_scenarios() -> List[Dict]:
    """Load automation scenarios from CSV or return defaults."""
    csv_path = os.path.join(os.path.dirname(__file__), "../../data/automation_scenarios.csv")
    csv_path = os.path.normpath(csv_path)

    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path)
        return df.to_dict(orient="records")

    # Fallback hardcoded scenarios
    return [
        {"scenario_id": 1, "scenario_name": "AMR拣选辅助", "category": "移动机器人",
         "applicable_industry": "电商/3PL/零售", "sku_min": 5000, "sku_max": 100000,
         "order_min": 500, "order_max": 50000, "capex_min": 500000, "capex_max": 2000000,
         "labor_saving": 0.3, "efficiency_gain": 0.4, "risk_level": "中"},
        {"scenario_id": 2, "scenario_name": "GTP货到人系统", "category": "货到人",
         "applicable_industry": "电商/3PL", "sku_min": 10000, "sku_max": 200000,
         "order_min": 1000, "order_max": 100000, "capex_min": 2000000, "capex_max": 8000000,
         "labor_saving": 0.5, "efficiency_gain": 0.6, "risk_level": "高"},
        {"scenario_id": 3, "scenario_name": "输送分拣线", "category": "输送分拣",
         "applicable_industry": "电商/快递/零售", "sku_min": 1000, "sku_max": 50000,
         "order_min": 2000, "order_max": 200000, "capex_min": 1000000, "capex_max": 5000000,
         "labor_saving": 0.4, "efficiency_gain": 0.5, "risk_level": "中"},
    ]


def score_industry_match(scenario: Dict, industry: str) -> float:
    """Score based on industry match (0-20 points)."""
    applicable = scenario.get("applicable_industry", "")
    if not applicable:
        return 10.0

    applicable_list = [i.strip() for i in applicable.split("/")]

    if industry in applicable_list:
        return 20.0

    related = INDUSTRY_MAPPING.get(industry, [])
    for rel in related:
        if rel in applicable_list:
            return 12.0

    return 0.0


def score_sku_match(scenario: Dict, sku_count: int) -> float:
    """Score based on SKU count match (0-20 points)."""
    sku_min = scenario.get("sku_min", 0)
    sku_max = scenario.get("sku_max", 9999999)

    if sku_min <= sku_count <= sku_max:
        return 20.0

    if sku_count < sku_min:
        ratio = sku_count / sku_min
        return max(0, 20 * ratio)

    if sku_count > sku_max:
        ratio = sku_max / sku_count
        return max(10, 20 * ratio)

    return 0.0


def score_order_match(scenario: Dict, daily_orders: int) -> float:
    """Score based on order volume match (0-20 points)."""
    order_min = scenario.get("order_min", 0)
    order_max = scenario.get("order_max", 9999999)

    if order_min <= daily_orders <= order_max:
        return 20.0

    if daily_orders < order_min:
        ratio = daily_orders / order_min
        return max(0, 20 * ratio)

    if daily_orders > order_max:
        ratio = order_max / daily_orders
        return max(10, 20 * ratio)

    return 0.0


def score_budget_match(scenario: Dict, budget_level: str) -> float:
    """Score based on budget match (0-20 points)."""
    budget_threshold = BUDGET_THRESHOLDS.get(budget_level, 5000000)
    capex_min = scenario.get("capex_min", 0)

    if capex_min <= budget_threshold:
        return 20.0
    elif capex_min <= budget_threshold * 1.5:
        return 12.0
    elif capex_min <= budget_threshold * 2:
        return 6.0
    return 0.0


def score_warehouse_conditions(scenario: Dict, warehouse_area: float,
                                automation_expectation: str) -> float:
    """Score based on warehouse conditions and automation expectation (0-20 points)."""
    base_score = 10.0

    category = scenario.get("category", "")

    # Large warehouse benefits from certain automation
    if warehouse_area > 20000 and category in ["立体仓库", "货到人", "移动机器人"]:
        base_score += 5
    elif warehouse_area < 5000 and category in ["自动化辅助", "软件系统"]:
        base_score += 5

    # Automation expectation weight
    weight = AUTOMATION_LEVEL_WEIGHTS.get(automation_expectation, 1.0)

    risk_level = scenario.get("risk_level", "中")
    risk_adjustment = {"低": 2, "中": 0, "高": -2}.get(risk_level, 0)

    final_score = min(20, (base_score + risk_adjustment) * weight)
    return max(0, final_score)


def generate_reason(scenario: Dict, profile: Dict) -> str:
    """Generate recommendation reason text."""
    reasons = []

    industry = profile.get("industry", "")
    sku_count = profile.get("sku_count", 0)
    daily_orders = profile.get("daily_orders", 0)

    applicable = scenario.get("applicable_industry", "")
    if industry in applicable:
        reasons.append(f"适合{industry}行业")

    if sku_count > 10000:
        reasons.append("SKU数量多，需要精细化管理")
    elif sku_count < 1000:
        reasons.append("SKU数量少，系统简单易管理")

    if daily_orders > 5000:
        reasons.append("订单量大，效率提升明显")
    elif daily_orders < 500:
        reasons.append("订单量较少，投入产出需谨慎评估")

    labor_saving = scenario.get("labor_saving", 0)
    efficiency_gain = scenario.get("efficiency_gain", 0)

    if labor_saving > 0.4:
        reasons.append(f"可节省人工{int(labor_saving*100)}%")
    if efficiency_gain > 0.5:
        reasons.append(f"效率提升{int(efficiency_gain*100)}%")

    return "；".join(reasons) if reasons else "综合评估适合该场景"


def generate_risk_text(scenario: Dict, profile: Dict) -> str:
    """Generate risk assessment text."""
    risk_level = scenario.get("risk_level", "中")
    category = scenario.get("category", "")

    risk_map = {
        "低": f"{category}方案成熟度高，实施风险低，建议优先考虑",
        "中": f"{category}需要合理规划实施周期，关注系统集成复杂度",
        "高": f"{category}投资较大，需谨慎评估ROI，建议分阶段实施",
    }

    return risk_map.get(risk_level, "需要详细评估实施风险")


def recommend_automation(project_profile: Dict) -> List[Dict[str, Any]]:
    """
    Main recommendation function.

    Args:
        project_profile: Dict with keys: industry, warehouse_area, sku_count,
                         daily_orders, inventory, labor_cost_level, budget_level,
                         automation_expectation

    Returns:
        List of scenario recommendations sorted by score
    """
    scenarios = load_scenarios()
    recommendations = []

    for scenario in scenarios:
        industry_score = score_industry_match(scenario, project_profile.get("industry", ""))
        sku_score = score_sku_match(scenario, project_profile.get("sku_count", 0))
        order_score = score_order_match(scenario, project_profile.get("daily_orders", 0))
        budget_score = score_budget_match(scenario, project_profile.get("budget_level", "中"))
        warehouse_score = score_warehouse_conditions(
            scenario,
            project_profile.get("warehouse_area", 0),
            project_profile.get("automation_expectation", "中")
        )

        total_score = industry_score + sku_score + order_score + budget_score + warehouse_score
        total_score = min(100, max(0, total_score))

        if total_score < 20:
            continue

        capex_min = scenario.get("capex_min", 0)
        capex_max = scenario.get("capex_max", 0)
        capex_range = f"¥{capex_min/10000:.0f}万 - ¥{capex_max/10000:.0f}万"

        recommendations.append({
            "scenario_id": scenario.get("scenario_id"),
            "scenario_name": scenario.get("scenario_name"),
            "category": scenario.get("category"),
            "score": round(total_score, 1),
            "reason": generate_reason(scenario, project_profile),
            "risk": generate_risk_text(scenario, project_profile),
            "capex_range": capex_range,
            "labor_saving": scenario.get("labor_saving", 0),
            "efficiency_gain": scenario.get("efficiency_gain", 0),
        })

    recommendations.sort(key=lambda x: x["score"], reverse=True)
    return recommendations[:5]
