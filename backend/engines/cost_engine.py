from typing import Dict, Any, Optional
import pandas as pd
import os


REGION_DEFAULTS = {
    "华东": {"rent": 600, "labor": 80000, "maintenance": 0.05, "overhead": 0.15, "density": 4},
    "华南": {"rent": 550, "labor": 75000, "maintenance": 0.05, "overhead": 0.15, "density": 4},
    "华北": {"rent": 500, "labor": 70000, "maintenance": 0.05, "overhead": 0.15, "density": 4},
    "华中": {"rent": 450, "labor": 65000, "maintenance": 0.05, "overhead": 0.15, "density": 4},
    "西部": {"rent": 400, "labor": 60000, "maintenance": 0.05, "overhead": 0.15, "density": 4},
}

LABOR_COST_MULTIPLIER = {
    "低": 0.8,
    "中": 1.0,
    "高": 1.3,
}

ORDERS_PER_PERSON_PER_DAY = {
    "manual": 150,
    "semi_auto": 300,
    "full_auto": 600,
}

SCENARIO_CAPEX_MIDPOINT = {
    1: 1250000,   # AMR
    2: 5000000,   # GTP
    3: 3000000,   # 输送分拣线
    4: 300000,    # 自动贴标
    5: 12500000,  # 立体仓库
    6: 1150000,   # 输送线
    7: 600000,    # 视觉检测
    8: 1900000,   # 拆码垛
    9: 600000,    # WMS
    10: 2500000,  # AGV
    11: 1750000,  # 包装线
    12: 9000000,  # 冷链
    13: 6500000,  # 跨带分拣
    14: 3000000,  # 密集存储
    15: 1250000,  # 退货处理
}

SCENARIO_LABOR_SAVING = {
    1: 0.30, 2: 0.50, 3: 0.40, 4: 0.20, 5: 0.60,
    6: 0.30, 7: 0.25, 8: 0.45, 9: 0.15, 10: 0.40,
    11: 0.35, 12: 0.50, 13: 0.55, 14: 0.20, 15: 0.30,
}


def load_cost_parameters(region: str = "华东") -> Dict:
    """Load cost parameters for a region."""
    csv_path = os.path.join(os.path.dirname(__file__), "../../data/cost_parameters.csv")
    csv_path = os.path.normpath(csv_path)

    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path)
        row = df[df["region"] == region]
        if not row.empty:
            r = row.iloc[0]
            return {
                "rent": r["warehouse_rent_per_sqm"],
                "labor": r["labor_cost_per_person_year"],
                "maintenance": r["equipment_maintenance_rate"],
                "overhead": r["overhead_rate"],
                "density": r["pallet_density"],
            }

    return REGION_DEFAULTS.get(region, REGION_DEFAULTS["华东"])


def calculate_warehouse_slots(inventory: int, pallet_density: float = 4) -> int:
    """库位需求 = 库存量 / 每托盘密度"""
    return max(1, int(inventory / pallet_density))


def calculate_headcount(daily_orders: int, automation_level: str = "manual") -> int:
    """人员需求 = 订单行数 / 人效"""
    efficiency = ORDERS_PER_PERSON_PER_DAY.get(automation_level, 150)
    # Factor in non-picking staff (receiving, shipping, supervision = 30% overhead)
    picking_staff = max(1, int(daily_orders / efficiency))
    total_staff = max(1, int(picking_staff * 1.3))
    return total_staff


def calculate_roi(
    labor_saving_annual: float,
    maintenance_cost_annual: float,
    capex: float,
    years: int = 5
) -> float:
    """ROI = (节省人工 - 运维成本) / 投资"""
    if capex <= 0:
        return 0.0
    net_annual_benefit = labor_saving_annual - maintenance_cost_annual
    total_benefit = net_annual_benefit * years
    roi = total_benefit / capex
    return round(roi, 2)


def calculate_costs(profile: Dict, region: str = "华东",
                    selected_scenario_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Calculate comprehensive cost breakdown.

    Args:
        profile: Project profile dict
        region: Geographic region for cost parameters
        selected_scenario_id: If specified, calculate costs for this scenario

    Returns:
        Cost breakdown dict
    """
    params = load_cost_parameters(region)

    labor_multiplier = LABOR_COST_MULTIPLIER.get(profile.get("labor_cost_level", "中"), 1.0)
    labor_cost_per_person = params["labor"] * labor_multiplier

    warehouse_area = profile.get("warehouse_area", 1000)
    warehouse_cost_annual = warehouse_area * params["rent"]

    inventory = profile.get("inventory", 10000)
    daily_orders = profile.get("daily_orders", 500)

    # Manual headcount (baseline)
    baseline_headcount = calculate_headcount(daily_orders, "manual")
    baseline_labor_cost = baseline_headcount * labor_cost_per_person

    # With automation
    automation_expectation = profile.get("automation_expectation", "中")
    if automation_expectation == "高":
        auto_level = "full_auto"
    elif automation_expectation == "中":
        auto_level = "semi_auto"
    else:
        auto_level = "manual"

    automated_headcount = calculate_headcount(daily_orders, auto_level)

    # Get scenario-specific data
    labor_saving_rate = 0.3  # default
    capex = 1000000  # default

    if selected_scenario_id and selected_scenario_id in SCENARIO_CAPEX_MIDPOINT:
        capex = SCENARIO_CAPEX_MIDPOINT[selected_scenario_id]
        labor_saving_rate = SCENARIO_LABOR_SAVING.get(selected_scenario_id, 0.3)
    else:
        # Estimate based on automation expectation and budget
        budget_level = profile.get("budget_level", "中")
        budget_map = {"低": 500000, "中": 2000000, "高": 8000000}
        capex = budget_map.get(budget_level, 2000000)

        auto_map = {"低": 0.2, "中": 0.35, "高": 0.5}
        labor_saving_rate = auto_map.get(automation_expectation, 0.35)

    # Cost calculations
    headcount_saved = max(0, baseline_headcount - automated_headcount)
    actual_labor_saving = headcount_saved * labor_cost_per_person

    # Also apply labor saving rate to remaining workforce
    additional_saving = automated_headcount * labor_cost_per_person * labor_saving_rate * 0.3
    total_labor_saving = actual_labor_saving + additional_saving

    # Automation costs
    annual_maintenance = capex * params["maintenance"]
    overhead = (warehouse_cost_annual + baseline_labor_cost) * params["overhead"]

    total_annual_cost_manual = warehouse_cost_annual + baseline_labor_cost + overhead
    automated_labor_cost = automated_headcount * labor_cost_per_person
    total_annual_cost_auto = warehouse_cost_annual + automated_labor_cost + annual_maintenance + overhead

    net_annual_benefit = total_labor_saving - annual_maintenance
    roi = calculate_roi(total_labor_saving, annual_maintenance, capex, years=5)

    payback_years = capex / max(1, net_annual_benefit) if net_annual_benefit > 0 else 99
    payback_years = min(99, round(payback_years, 1))

    return {
        "warehouse_cost": round(warehouse_cost_annual, 0),
        "labor_cost_annual": round(baseline_labor_cost, 0),
        "automation_capex": round(capex, 0),
        "annual_maintenance": round(annual_maintenance, 0),
        "total_annual_cost": round(total_annual_cost_auto, 0),
        "automation_savings_annual": round(total_labor_saving, 0),
        "net_annual_benefit": round(net_annual_benefit, 0),
        "roi": roi,
        "payback_years": payback_years,
        "headcount_required": automated_headcount,
        "headcount_saved": headcount_saved,
    }


def generate_cost_summary(cost_data: Dict) -> str:
    """Generate human-readable cost summary."""
    roi = cost_data.get("roi", 0)
    payback = cost_data.get("payback_years", 99)
    savings = cost_data.get("automation_savings_annual", 0)
    capex = cost_data.get("automation_capex", 0)

    summary_parts = [
        f"项目预计总投资 ¥{capex/10000:.0f}万元",
        f"年节省人工成本 ¥{savings/10000:.1f}万元",
        f"5年ROI达到 {roi:.1f}x",
        f"预计回本周期 {payback:.1f}年" if payback < 99 else "回本周期较长，建议重新评估方案",
    ]

    return "，".join(summary_parts) + "。"


def generate_cost_recommendations(cost_data: Dict, profile: Dict) -> list:
    """Generate actionable cost optimization recommendations."""
    recommendations = []

    roi = cost_data.get("roi", 0)
    payback = cost_data.get("payback_years", 99)
    headcount_saved = cost_data.get("headcount_saved", 0)

    if roi < 1.5:
        recommendations.append("ROI偏低，建议选择投资更小的自动化方案或分阶段实施")
    elif roi > 3:
        recommendations.append("ROI表现优秀，可考虑扩大自动化投资范围")

    if payback > 5:
        recommendations.append("回本周期超过5年，建议评估租赁方案降低初始投入")
    elif payback < 2:
        recommendations.append("回本周期短，方案经济性优良，建议尽快推进")

    if headcount_saved > 10:
        recommendations.append(f"可减少{headcount_saved}人，建议制定人员转岗培训计划")

    budget_level = profile.get("budget_level", "中")
    if budget_level == "低":
        recommendations.append("预算有限，优先考虑WMS系统或局部自动化改造")

    if not recommendations:
        recommendations.append("方案整体经济性良好，建议推进详细可行性研究")

    return recommendations
