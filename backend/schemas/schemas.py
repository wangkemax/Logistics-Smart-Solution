from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class ProjectProfileBase(BaseModel):
    project_name: Optional[str] = "未命名项目"
    industry: str = Field(..., description="行业: 电商/3PL/零售/制造/快递/医药/食品")
    warehouse_area: float = Field(..., gt=0, description="仓库面积(平方米)")
    sku_count: int = Field(..., gt=0, description="SKU数量")
    daily_orders: int = Field(..., gt=0, description="日均订单量")
    inventory: int = Field(..., gt=0, description="库存量(件)")
    labor_cost_level: str = Field(default="中", description="人工成本水平: 低/中/高")
    budget_level: str = Field(default="中", description="预算水平: 低/中/高")
    automation_expectation: str = Field(default="中", description="自动化期望: 低/中/高")


class ProjectProfileCreate(ProjectProfileBase):
    pass


class ProjectProfileResponse(ProjectProfileBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class RecommendationRequest(BaseModel):
    industry: str
    warehouse_area: float
    sku_count: int
    daily_orders: int
    inventory: int
    labor_cost_level: str = "中"
    budget_level: str = "中"
    automation_expectation: str = "中"


class ScenarioRecommendation(BaseModel):
    scenario_id: int
    scenario_name: str
    category: str
    score: float
    reason: str
    risk: str
    capex_range: str
    labor_saving: float
    efficiency_gain: float


class RecommendationResponse(BaseModel):
    recommendations: List[ScenarioRecommendation]
    top_recommendation: str
    analysis_summary: str


class CostRequest(BaseModel):
    industry: str
    warehouse_area: float
    sku_count: int
    daily_orders: int
    inventory: int
    labor_cost_level: str = "中"
    budget_level: str = "中"
    automation_expectation: str = "中"
    region: str = "华东"
    selected_scenario_id: Optional[int] = None


class CostBreakdown(BaseModel):
    warehouse_cost: float
    labor_cost_annual: float
    automation_capex: float
    annual_maintenance: float
    total_annual_cost: float
    automation_savings_annual: float
    net_annual_benefit: float
    roi: float
    payback_years: float
    headcount_required: int
    headcount_saved: int


class CostResponse(BaseModel):
    cost_breakdown: CostBreakdown
    summary: str
    recommendations: List[str]
