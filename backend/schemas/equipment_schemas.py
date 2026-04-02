"""backend/schemas/equipment_schemas.py — v1.1 Equipment Database Pydantic schemas"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field
from typing import Optional


class EquipmentSchema(BaseModel):
    id: int
    equipment_type: str
    model_name: str
    manufacturer: str = ""
    capex_min: float
    capex_max: float
    throughput_unit: str = "pos/hr"
    throughput_value: float
    payload_kg: float
    max_speed_mps: float
    power_kw: float
    mtbf_hours: float
    maintenance_cost_pa: float
    footprint_sqm: float
    version_id: int = 1
    effective_date: datetime | None = None
    is_active: bool = True
    notes: str = ""

    model_config = {"from_attributes": True}


class EquipmentQuery(BaseModel):
    """设备查询条件"""
    equipment_type: Optional[str] = None  # AMR / GTP / ASRS / Shuttle / Conveyor / Sorter
    min_throughput: Optional[float] = None
    min_payload_kg: Optional[float] = None
    max_capex: Optional[float] = None
    is_active: bool = True


class EquipmentMatchResult(BaseModel):
    """设备匹配结果"""
    equipment: EquipmentSchema
    match_score: float = Field(ge=0.0, le=1.0)  # 0~1 匹配度
    capex_estimate: float  # 该项目估算CAPEX（万元）
