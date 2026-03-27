from sqlalchemy.orm import Session
from backend.models.database import Project, Solution
from backend.schemas.schemas import ProjectProfileCreate
from backend.engines.automation_engine import recommend_automation
from backend.engines.cost_engine import calculate_costs, generate_cost_summary, generate_cost_recommendations
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
    industry = profile_dict.get("industry", "")
    sku = profile_dict.get("sku_count", 0)
    orders = profile_dict.get("daily_orders", 0)

    sku_desc = "高SKU" if sku > 10000 else "低SKU"
    order_desc = "高订单量" if orders > 2000 else "低订单量"

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
