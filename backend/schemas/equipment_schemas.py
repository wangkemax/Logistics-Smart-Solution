"""backend/schemas/equipment_schemas.py — v1.1 Equipment Database Pydantic schemas"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator
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

    @field_validator("version_id", mode="before")
    @classmethod
    def _version_id_default(cls, value):
        if value is None:
            return 1
        return value
    is_active: bool = True
    notes: str = ""

    model_config = {"from_attributes": True}


class EquipmentQuery(BaseModel):
    """设备查询条件"""
    equipment_type: Optional[str] = None  # AMR / GTP / AS/RS / Shuttle / Conveyor / Sorter
    min_throughput: Optional[float] = None
    min_payload_kg: Optional[float] = None
    max_capex: Optional[float] = None
    is_active: bool = True


class EquipmentMatchResult(BaseModel):
    """设备匹配结果"""
    equipment: EquipmentSchema
    match_score: float = Field(ge=0.0, le=1.0)  # 0~1 匹配度
    quantity: int = 1  # ceil(target / capacity); 1 when a single unit covers
    capex_estimate: float  # 该项目估算CAPEX（万元）= capex_max * quantity
