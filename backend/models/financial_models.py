"""backend/models/financial_models.py — v1.2 Financial Model SQLAlchemy models"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text

from backend.models.database import Base


class FinancialSnapshot(Base):
    """
    财务快照表。
    存储每个 Workspace 版本的成本测算结果。
    """
    __tablename__ = "financial_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(String(40), index=True, nullable=False)
    snapshot_version = Column(Integer, default=1)  # 对应 workspace_snapshot_version

    # CAPEX（万元）
    equipment_capex_min = Column(Float, default=0)
    equipment_capex_max = Column(Float, default=0)
    capex_total_min = Column(Float, default=0)  # 设备+工程+软件
    capex_total_max = Column(Float, default=0)

    # OPEX（万元/年）
    opex_labor = Column(Float, default=0)  # 人力成本
    opex_warehouse = Column(Float, default=0)  # 仓储租赁
    opex_utility = Column(Float, default=0)  # 水电能耗
    opex_maintenance = Column(Float, default=0)  # 维保
    opex_other = Column(Float, default=0)
    opex_total = Column(Float, default=0)

    # 收益（万元/年）
    revenue_labor_saving = Column(Float, default=0)  # 人力节省
    revenue_throughput_improvement = Column(Float, default=0)  # 吞吐量提升收益
    revenue_total = Column(Float, default=0)

    # ROI 指标
    net_annual_benefit = Column(Float, default=0)  # 年净收益（收益-OPEX）
    roi_5y = Column(Float, default=0)  # 5年ROI
    payback_years = Column(Float, default=0)  # 投资回收期（年）
    irr = Column(Float, default=0)  # 内部收益率（%）

    # 现金流量表（简化版，5年）
    cashflow_y1 = Column(Float, default=0)
    cashflow_y2 = Column(Float, default=0)
    cashflow_y3 = Column(Float, default=0)
    cashflow_y4 = Column(Float, default=0)
    cashflow_y5 = Column(Float, default=0)

    # 元数据
    contract_years = Column(Integer, default=5)
    discount_rate = Column(Float, default=0.08)  # WACC 折现率 8%
    depreciation_years = Column(Integer, default=5)  # 折旧年限
    created_at = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text, default="")
