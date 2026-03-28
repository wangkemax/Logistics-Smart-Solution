from sqlalchemy.orm import Session
from backend.models.database import Project, Solution
from backend.schemas.schemas import ProjectProfileCreate
from backend.engines.automation_engine import recommend_automation
from backend.engines.cost_engine import (
    calculate_costs, generate_cost_summary, generate_cost_recommendations,
    compare_scenarios as engine_compare_scenarios, SCENARIO_NAMES
)
import json


def create_project(db: Session, project_data: ProjectProfileCreate) -> Project:
    """Create a new project in the database."""
    db_project = Project(
        project_name=project_data.project_name,
        industry=project_data.industry,
        warehouse_area=project_data.warehouse_area,
        sku_count=project_data.sku_count,
        daily_orders=project_data.daily_orders,
        inventory=project_data.inventory,
        labor_cost_level=project_data.labor_cost_level,
        budget_level=project_data.budget_level,
        automation_expectation=project_data.automation_expectation,
    )
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project


def get_project(db: Session, project_id: int) -> Project:
    return db.query(Project).filter(Project.id == project_id).first()


def get_recommendations(profile_dict: dict) -> dict:
    """Get automation recommendations for a project profile."""
    recommendations = recommend_automation(profile_dict)

    top = recommendations[0] if recommendations else None
    top_name = top["scenario_name"] if top else "暂无推荐"

    # Generate analysis summary
    industry = profile_dict.get("industry", "") or "未知"
    sku = profile_dict.get("sku_count") or 0
    orders = profile_dict.get("daily_orders") or 0

    sku_desc = "高SKU" if sku and sku > 10000 else "低SKU"
    order_desc = "高订单量" if orders and orders > 2000 else "低订单量"

    summary = (
        f"基于{industry}行业特征，{sku_desc}({sku:,} SKU)和{order_desc}({orders:,}单/天)的运营特点，"
        f"系统推荐优先考虑{top_name}方案。"
    )

    return {
        "recommendations": recommendations,
        "top_recommendation": top_name,
        "analysis_summary": summary,
    }


def get_cost_analysis(profile_dict: dict, region: str = "华东",
                       selected_scenario_id: int = None) -> dict:
    """Get cost analysis for a project."""
    cost_data = calculate_costs(profile_dict, region, selected_scenario_id)
    summary = generate_cost_summary(cost_data)
    recommendations = generate_cost_recommendations(cost_data, profile_dict)

    return {
        "cost_breakdown": cost_data,
        "summary": summary,
        "recommendations": recommendations,
    }


def get_scenario_comparison(profile_dict: dict, region: str,
                             scenario_ids: list) -> dict:
    """Compare multiple automation scenarios side by side."""
    comparisons = engine_compare_scenarios(profile_dict, region, scenario_ids)

    best = next((c for c in comparisons if c.get("is_best")), None)
    best_id = best["scenario_id"] if best else None

    # Generate analysis summary
    industry = profile_dict.get("industry", "")
    if best:
        best_name = best["scenario_name"]
        roi_5y = best["roi_5y"]
        payback = best["payback_years"]
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
