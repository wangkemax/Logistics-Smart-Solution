"""backend/api/equipment_api.py — v1.1 Equipment Database FastAPI routes"""
from fastapi import APIRouter, HTTPException

from backend.services.equipment_service import EquipmentService
from backend.schemas.equipment_schemas import (
    EquipmentSchema,
    EquipmentMatchResult,
)

router = APIRouter(prefix="/equipment", tags=["equipment"])
_service = EquipmentService()


@router.get("/types")
def list_equipment_types():
    """列出所有设备类型"""
    return ["AMR", "GTP", "ASRS", "Shuttle", "Conveyor", "Sorter"]


@router.get("/", response_model=list[EquipmentSchema])
def list_equipment(
    equipment_type: str | None = None,
    min_throughput: float | None = None,
    min_payload_kg: float | None = None,
    max_capex: float | None = None,
):
    return _service.get_equipment(
        equipment_type=equipment_type,
        min_throughput=min_throughput,
        min_payload_kg=min_payload_kg,
        max_capex=max_capex,
    )


@router.get("/{equipment_id}", response_model=EquipmentSchema)
def get_equipment(equipment_id: int):
    result = _service.get_equipment_by_id(equipment_id)
    if not result:
        raise HTTPException(status_code=404, detail="Equipment not found")
    return result


@router.get("/estimate/capex")
def estimate_capex(
    equipment_type: str,
    quantity: int,
    throughput_target: float | None = None,
):
    return _service.estimate_capex(equipment_type, quantity, throughput_target)


@router.get("/match/{equipment_type}", response_model=list[EquipmentMatchResult])
def match_equipment(
    equipment_type: str,
    throughput_target: float,
    payload_min: float | None = None,
):
    return _service.match_equipment_for_scenario(
        equipment_type, throughput_target, payload_min
    )
