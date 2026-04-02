"""tests/test_equipment_service.py — v1.1 Equipment Service 单元测试"""
from __future__ import annotations

import pytest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.models.database import Base, engine, SessionLocal
from backend.models.equipment_models import Equipment
from backend.services.equipment_service import EquipmentService


@pytest.fixture(scope="function")
def setup_db():
    """每个测试创建干净数据库表，测试后清理"""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        # 清理 equipment 表数据（不影响其他表）
        db.query(Equipment).delete()
        db.commit()


@pytest.fixture
def seed_equipment(setup_db):
    """插入测试数据"""
    db = setup_db
    items = [
        Equipment(
            equipment_type="AMR",
            model_name="AMR-500L",
            manufacturer="TestA",
            capex_min=8.0,
            capex_max=15.0,
            throughput_unit="pos/hr",
            throughput_value=80.0,
            payload_kg=500.0,
            max_speed_mps=1.5,
            power_kw=0.3,
            mtbf_hours=8000.0,
            maintenance_cost_pa=1.5,
            footprint_sqm=0.8,
            is_active=True,
        ),
        Equipment(
            equipment_type="AMR",
            model_name="AMR-1000L",
            manufacturer="TestB",
            capex_min=12.0,
            capex_max=22.0,
            throughput_unit="pos/hr",
            throughput_value=60.0,
            payload_kg=1000.0,
            max_speed_mps=1.2,
            power_kw=0.5,
            mtbf_hours=10000.0,
            maintenance_cost_pa=2.0,
            footprint_sqm=1.0,
            is_active=True,
        ),
        Equipment(
            equipment_type="Shuttle",
            model_name="SH-200",
            manufacturer="TestC",
            capex_min=20.0,
            capex_max=40.0,
            throughput_unit="pos/hr",
            throughput_value=200.0,
            payload_kg=25.0,
            max_speed_mps=3.0,
            power_kw=0.2,
            mtbf_hours=12000.0,
            maintenance_cost_pa=3.5,
            footprint_sqm=0.5,
            is_active=True,
        ),
        # 已停用设备（不应返回）
        Equipment(
            equipment_type="AMR",
            model_name="AMR-DEPRECATED",
            manufacturer="TestD",
            capex_min=5.0,
            capex_max=10.0,
            throughput_unit="pos/hr",
            throughput_value=30.0,
            payload_kg=100.0,
            max_speed_mps=1.0,
            power_kw=0.2,
            mtbf_hours=5000.0,
            maintenance_cost_pa=1.0,
            footprint_sqm=0.5,
            is_active=False,
        ),
    ]
    for item in items:
        db.add(item)
    db.commit()
    return db


class TestGetEquipment:
    def test_get_equipment_returns_active_only(self, seed_equipment):
        """只返回 is_active=True 的设备"""
        service = EquipmentService()
        results = service.get_equipment()
        assert len(results) == 3  # AMR-500L, AMR-1000L, SH-200；AMR-DEPRECATED 不在其中
        for r in results:
            assert r.is_active is True

    def test_get_equipment_filters_by_type(self, seed_equipment):
        """按 equipment_type 过滤"""
        service = EquipmentService()
        results = service.get_equipment(equipment_type="AMR")
        assert len(results) == 2
        for r in results:
            assert r.equipment_type == "AMR"

    def test_get_equipment_filters_by_min_throughput(self, seed_equipment):
        """min_throughput 过滤"""
        service = EquipmentService()
        results = service.get_equipment(equipment_type="AMR", min_throughput=70.0)
        assert len(results) == 1
        assert results[0].model_name == "AMR-500L"
        assert results[0].throughput_value == 80.0

    def test_get_equipment_filters_by_min_payload_kg(self, seed_equipment):
        """min_payload_kg 过滤"""
        service = EquipmentService()
        results = service.get_equipment(equipment_type="AMR", min_payload_kg=800.0)
        assert len(results) == 1
        assert results[0].model_name == "AMR-1000L"

    def test_get_equipment_filters_by_max_capex(self, seed_equipment):
        """max_capex 过滤"""
        service = EquipmentService()
        results = service.get_equipment(equipment_type="AMR", max_capex=20.0)
        assert len(results) == 1
        assert results[0].model_name == "AMR-500L"

    def test_get_equipment_sorted_by_throughput_desc(self, seed_equipment):
        """结果按 throughput_value 降序排列"""
        service = EquipmentService()
        results = service.get_equipment(equipment_type="AMR")
        assert results[0].throughput_value == 80.0
        assert results[1].throughput_value == 60.0


class TestGetEquipmentById:
    def test_get_equipment_by_id_returns_active(self, seed_equipment):
        """返回活跃设备"""
        service = EquipmentService()
        # AMR-500L 是第一个插入的活跃设备
        db = seed_equipment
        amr500 = db.query(Equipment).filter(Equipment.model_name == "AMR-500L").first()
        result = service.get_equipment_by_id(amr500.id)
        assert result is not None
        assert result.model_name == "AMR-500L"

    def test_get_equipment_by_id_returns_none_for_inactive(self, seed_equipment):
        """已停用设备返回 None"""
        service = EquipmentService()
        db = seed_equipment
        deprecated = (
            db.query(Equipment).filter(Equipment.model_name == "AMR-DEPRECATED").first()
        )
        result = service.get_equipment_by_id(deprecated.id)
        assert result is None


class TestEstimateCapex:
    def test_estimate_capex_returns_range(self, seed_equipment):
        """估算 CAPEX 返回 min/max 范围"""
        service = EquipmentService()
        result = service.estimate_capex(
            equipment_type="AMR", quantity=10, throughput_target=None
        )
        assert "min" in result
        assert "max" in result
        assert result["min"] > 0
        assert result["max"] > result["min"]
        assert result["unit_count"] == 2

    def test_estimate_capex_with_throughput_filter(self, seed_equipment):
        """按吞吐量目标过滤后再估算"""
        service = EquipmentService()
        result = service.estimate_capex(
            equipment_type="AMR", quantity=5, throughput_target=70.0
        )
        # 只有 AMR-500L (80pos/hr) 满足 >=70
        assert result["unit_count"] == 1
        assert result["min"] == 8.0 * 5
        assert result["max"] == 15.0 * 5

    def test_estimate_capex_unknown_type_returns_zero(self, seed_equipment):
        """未知类型返回零值"""
        service = EquipmentService()
        result = service.estimate_capex(equipment_type="NONEXISTENT", quantity=10)
        assert result["min"] == 0.0
        assert result["max"] == 0.0
        assert result["unit_count"] == 0


class TestMatchEquipment:
    def test_match_equipment_sorted_by_throughput_proximity(self, seed_equipment):
        """匹配结果按吞吐量接近度排序"""
        service = EquipmentService()
        # 目标吞吐量 70，AMR-500L=80（差10），AMR-1000L=60（差10），score 相同但顺序取决于 DB order_by
        results = service.match_equipment_for_scenario(
            equipment_type="AMR", throughput_target=70.0
        )
        assert len(results) == 2
        # score = 1 - |throughput - target| / max(throughput, target)
        # AMR-500L: 1 - 10/80 = 0.875
        # AMR-1000L: 1 - 10/60 = 0.833
        assert results[0].match_score >= results[1].match_score
        assert results[0].equipment.model_name == "AMR-500L"

    def test_match_equipment_with_payload_filter(self, seed_equipment):
        """payload_min 过滤"""
        service = EquipmentService()
        results = service.match_equipment_for_scenario(
            equipment_type="AMR", throughput_target=50.0, payload_min=800.0
        )
        assert len(results) == 1
        assert results[0].equipment.model_name == "AMR-1000L"

    def test_match_equipment_score_range(self, seed_equipment):
        """match_score 在 [0, 1] 范围内"""
        service = EquipmentService()
        results = service.match_equipment_for_scenario(
            equipment_type="Shuttle", throughput_target=200.0
        )
        assert len(results) == 1
        assert 0.0 <= results[0].match_score <= 1.0

    def test_match_equipment_capex_estimate_uses_max(self, seed_equipment):
        """capex_estimate 取 capex_max"""
        service = EquipmentService()
        results = service.match_equipment_for_scenario(
            equipment_type="AMR", throughput_target=80.0
        )
        top = results[0]
        assert top.capex_estimate == top.equipment.capex_max
