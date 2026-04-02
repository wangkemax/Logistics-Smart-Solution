"""backend/models/equipment_models.py — v1.1 Equipment Database SQLAlchemy models"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text

from backend.models.database import Base


class Equipment(Base):
    """设备库表（Fact Store，回答"是什么"和"多少钱"）"""

    __tablename__ = "equipment"

    id = Column(Integer, primary_key=True, index=True)

    # 设备分类
    equipment_type = Column(String(30), nullable=False, index=True)  # AMR / GTP / ASRS / Shuttle / Conveyor / Sorter
    model_name = Column(String(100), nullable=False)  # 型号名
    manufacturer = Column(String(100), default="")

    # CAPEX（万元）
    capex_min = Column(Float, nullable=False)   # 最低单价（万元）
    capex_max = Column(Float, nullable=False)   # 最高单价（万元）

    # 性能参数
    throughput_unit = Column(String(20), default="pos/hr")  # 吞吐量单位
    throughput_value = Column(Float, nullable=False)  # 典型吞吐量
    payload_kg = Column(Float, nullable=False)  # 额定载重（kg）
    max_speed_mps = Column(Float, nullable=False)  # 最大速度（m/s）

    # 能耗与可靠性
    power_kw = Column(Float, nullable=False)  # 功率（kW）
    mtbf_hours = Column(Float, nullable=False)  # 平均故障间隔（小时）
    maintenance_cost_pa = Column(Float, nullable=False)  # 年维保成本（万元）

    # 空间
    footprint_sqm = Column(Float, nullable=False)  # 单机占地面积（m²）

    # 版本控制（与 Assumption Governance 体系对齐）
    version_id = Column(Integer, default=1)
    effective_date = Column(DateTime, default=datetime.utcnow)
    deprecated_at = Column(DateTime, nullable=True)

    # 元数据
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text, default="")
