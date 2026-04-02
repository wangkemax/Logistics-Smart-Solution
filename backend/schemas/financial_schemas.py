from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional


class FinancialInput(BaseModel):
    """财务测算输入"""
    workspace_id: str

    # CAPEX 来自 equipment_service
    equipment_capex_min: float = 0
    equipment_capex_max: float = 0

    # OPEX 输入（来自 assumption 或 downstream_input）
    headcount_reduction: int = 0  # 减少人数
    avg_labor_cost_per_person: float = 0  # 人均年成本（万元）
    warehouse_area_sqm: float = 0  # 仓库面积
    warehouse_cost_per_sqm: float = 0  # 元/m²/年
    utility_cost_per_sqm: float = 0  # 水电元/m²/年
    maintenance_rate: float = 0.02  # 维保费率（设备CAPEX的%）

    # 收益
    annual_throughput_revenue: float = 0  # 年吞吐量提升收益（万元）

    # 合同参数
    contract_years: int = 5
    discount_rate: float = 0.08


class FinancialResult(BaseModel):
    """财务测算结果"""
    workspace_id: str
    snapshot_version: int

    # CAPEX
    equipment_capex_min: float
    equipment_capex_max: float
    capex_total_min: float
    capex_total_max: float

    # OPEX
    opex_labor: float
    opex_warehouse: float
    opex_utility: float
    opex_maintenance: float
    opex_other: float
    opex_total: float

    # 收益
    revenue_labor_saving: float
    revenue_throughput_improvement: float
    revenue_total: float

    # ROI 指标
    net_annual_benefit: float
    roi_5y: float
    payback_years: float
    irr: float

    # 现金流量
    cashflow_years: list[float] = Field(default_factory=list)  # [Y1, Y2, Y3, Y4, Y5]

    # 解读文本
    summary_text: str = ""  # LLM 可读的摘要
