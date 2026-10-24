from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional


class FinancialInput(BaseModel):
    """财务测算输入"""
    workspace_id: str

    # CAPEX 来自 equipment_service
    equipment_capex_min: float = 0
    equipment_capex_max: float = 0

    # 金额单位一律为元，与 data/cost_parameters.csv 一致。
    headcount_reduction: int = 0  # 减少人数（收益，不计入 OPEX）
    avg_labor_cost_per_person: float = 0  # 人均年成本（元/年）
    warehouse_area_sqm: float = 0  # 仓库面积
    warehouse_cost_per_sqm: float = 0  # 租金，元/m²/年（只列示，不从净收益中扣除）
    utility_cost_per_sqm: float = 0  # 水电，元/m²/年（增量运营成本）
    maintenance_rate: float = 0.02  # 维保费率，乘以设备 CAPEX

    # 收益
    annual_throughput_revenue: float = 0  # 年吞吐量提升收益（元）

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

    # ROI 指标。roi_5y 是合同期累计净收益 / CAPEX 的倍数（x），不是百分比。
    net_annual_benefit: float
    roi_5y: float
    payback_years: Optional[float] = None
    irr: Optional[float] = None  # 百分比；无法回收或不收敛时为 null
    npv: float = 0  # 按 discount_rate 对 [-capex]+[净收益]*年 折现
    discount_rate: float = 0.08
    contract_years: int = 5

    # 现金流量：下标 0 是 t=0 的 -CAPEX，其后每年为净收益。IRR/NPV 使用同一序列。
    cashflow_years: list[float] = Field(default_factory=list)

    # 解读文本
    summary_text: str = ""  # LLM 可读的摘要
