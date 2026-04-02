"""backend/services/equipment_service.py — v1.1 Equipment Database Service"""
from __future__ import annotations

from typing import Optional

from backend.models.equipment_models import Equipment
from backend.models.database import SessionLocal
from backend.schemas.equipment_schemas import (
    EquipmentSchema,
    EquipmentQuery,
    EquipmentMatchResult,
)


class EquipmentService:
    """
    设备库服务（Fact Store）。
    职责：回答"是什么"和"多少钱"。

    与 Scenario Engine 解耦，通过 DI 联动：
    scenario_engine 调用 get_equipment(type="Shuttle", min_throughput=200)
    拿到 EquipmentSchema 列表后自行计算设备数量。
    """

    def get_equipment(
        self,
        equipment_type: str | None = None,
        min_throughput: float | None = None,
        min_payload_kg: float | None = None,
        max_capex: float | None = None,
    ) -> list[EquipmentSchema]:
        """
        查询符合条件的设备列表。

        实现：
        1. 构建 SQLAlchemy 查询
        2. 过滤 is_active=True
        3. 按 equipment_type + throughput + payload 过滤
        4. 返回 EquipmentSchema 列表
        """
        db = SessionLocal()
        try:
            query = db.query(Equipment).filter(Equipment.is_active == True)
            if equipment_type:
                query = query.filter(Equipment.equipment_type == equipment_type)
            if min_throughput is not None:
                query = query.filter(Equipment.throughput_value >= min_throughput)
            if min_payload_kg is not None:
                query = query.filter(Equipment.payload_kg >= min_payload_kg)
            if max_capex is not None:
                query = query.filter(Equipment.capex_max <= max_capex)
            results = query.order_by(Equipment.throughput_value.desc()).all()
            return [EquipmentSchema.model_validate(r) for r in results]
        finally:
            db.close()

    def get_equipment_by_id(self, equipment_id: int) -> EquipmentSchema | None:
        """根据 ID 获取单个设备"""
        db = SessionLocal()
        try:
            result = (
                db.query(Equipment)
                .filter(Equipment.id == equipment_id, Equipment.is_active == True)
                .first()
            )
            if not result:
                return None
            return EquipmentSchema.model_validate(result)
        finally:
            db.close()

    def estimate_capex(
        self,
        equipment_type: str,
        quantity: int,
        throughput_target: float | None = None,
    ) -> dict:
        """
        估算指定类型设备的总 CAPEX。

        实现：
        1. 查符合 throughput_target 的设备（或该类型所有设备）
        2. 取 capex_min / capex_max 作为估算单价范围
        3. 返回 {min, max} 范围
        """
        db = SessionLocal()
        try:
            query = db.query(Equipment).filter(
                Equipment.equipment_type == equipment_type,
                Equipment.is_active == True,
            )
            if throughput_target is not None:
                # 取吞吐量不低于目标的设备
                query = query.filter(Equipment.throughput_value >= throughput_target)
            results = query.order_by(Equipment.throughput_value.desc()).all()
            if not results:
                return {"min": 0.0, "max": 0.0, "unit_count": 0}
            min_total = sum(r.capex_min * quantity for r in results)
            max_total = sum(r.capex_max * quantity for r in results)
            return {
                "min": round(min_total, 2),
                "max": round(max_total, 2),
                "unit_count": len(results),
            }
        finally:
            db.close()

    def match_equipment_for_scenario(
        self,
        equipment_type: str,
        throughput_target: float,
        payload_min: float | None = None,
    ) -> list[EquipmentMatchResult]:
        """
        为指定场景匹配最合适的设备。
        按吞吐量最接近度排序，返回匹配结果列表。

        实现：
        1. get_equipment() 查所有该类型设备
        2. 计算每个设备的 match_score = 1 - abs(throughput - target) / max(throughput, target)
        3. 估算每台设备的 CAPEX
        4. 排序并返回 EquipmentMatchResult 列表
        """
        db = SessionLocal()
        try:
            query = db.query(Equipment).filter(
                Equipment.equipment_type == equipment_type,
                Equipment.is_active == True,
            )
            if payload_min is not None:
                query = query.filter(Equipment.payload_kg >= payload_min)
            results = query.order_by(Equipment.throughput_value.desc()).all()

            matches = []
            for r in results:
                # 计算匹配度
                if throughput_target > 0 and r.throughput_value > 0:
                    score = 1 - abs(r.throughput_value - throughput_target) / max(
                        r.throughput_value, throughput_target
                    )
                    score = max(0.0, min(1.0, score))
                else:
                    score = 0.0

                # 估算单台 CAPEX（取 capex_max 作为估算）
                capex_estimate = r.capex_max

                matches.append(
                    EquipmentMatchResult(
                        equipment=EquipmentSchema.model_validate(r),
                        match_score=round(score, 4),
                        capex_estimate=capex_estimate,
                    )
                )

            # 按 match_score 降序排序
            matches.sort(key=lambda x: x.match_score, reverse=True)
            return matches
        finally:
            db.close()
