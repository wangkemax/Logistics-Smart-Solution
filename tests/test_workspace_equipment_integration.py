"""tests/test_workspace_equipment_integration.py — v1.1 Scenario-Equipment DI 集成测试"""
from __future__ import annotations

import uuid
import pytest
from unittest.mock import patch

from backend.models.database import Base
from backend.models.equipment_models import Equipment
from backend.services.workspace_manager import WorkspaceManager


def mock_session_local(db_session):
    """
    Create a mock SessionLocal that yields the test db session.
    Used only for workspace_manager SessionLocal (no nested sessions).
    """
    class MockSessionLocal:
        def __enter__(self):
            return db_session

        def __exit__(self, *args):
            pass

        def __call__(self):
            return db_session
    return MockSessionLocal()


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh in-memory DB with equipment table for each test."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    test_engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=test_engine
    )
    Base.metadata.create_all(bind=test_engine)

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def seed_equipment(db_session):
    """Seed AMR and Conveyor equipment into test DB."""
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
            equipment_type="Conveyor",
            model_name="CV-1500",
            manufacturer="TestC",
            capex_min=5.0,
            capex_max=10.0,
            throughput_unit="pos/hr",
            throughput_value=150.0,
            payload_kg=50.0,
            max_speed_mps=2.0,
            power_kw=0.8,
            mtbf_hours=12000.0,
            maintenance_cost_pa=1.0,
            footprint_sqm=0.5,
            is_active=True,
        ),
    ]
    for item in items:
        db_session.add(item)
    db_session.commit()
    return db_session


class TestInjectEquipmentSnapshot:
    """测试 _inject_equipment_snapshot 方法"""

    def _make_mock_result(self, equipment_type, model_name, throughput_value,
                          capex_min, capex_max, payload_kg=500):
        """Create a mock EquipmentMatchResult for testing."""
        from backend.schemas.equipment_schemas import (
            EquipmentSchema, EquipmentMatchResult
        )
        eq = EquipmentSchema(
            id=1,
            equipment_type=equipment_type,
            model_name=model_name,
            manufacturer="Test",
            capex_min=capex_min,
            capex_max=capex_max,
            throughput_unit="pos/hr",
            throughput_value=throughput_value,
            payload_kg=payload_kg,
            max_speed_mps=1.5,
            power_kw=0.3,
            mtbf_hours=8000,
            maintenance_cost_pa=1.5,
            footprint_sqm=0.8,
            is_active=True,
        )
        return EquipmentMatchResult(
            equipment=eq,
            match_score=0.9,
            capex_estimate=capex_max,
        )

    def test_inject_equipment_snapshot_adds_selected_equipment(
        self, db_session, seed_equipment
    ):
        """验证 refresh_snapshot 后 context_json 包含 selected_equipment"""
        import backend.services.workspace_manager as wm_module

        wm_module.SessionLocal = mock_session_local(db_session)

        amr_result = self._make_mock_result(
            "AMR", "AMR-500L", 80.0, 8.0, 15.0
        )
        conveyor_result = self._make_mock_result(
            "Conveyor", "CV-1500", 150.0, 5.0, 10.0
        )

        def mock_match(**kwargs):
            eq_type = kwargs.get("equipment_type")
            if eq_type == "AMR":
                return [amr_result]
            elif eq_type == "Conveyor":
                return [conveyor_result]
            return []

        manager = WorkspaceManager()
        manager.equipment_service.match_equipment_for_scenario = mock_match

        workspace = manager.create_workspace(pipeline_id=str(uuid.uuid4()))

        base_solution = {
            "operation_type": "warehouse_distribution",
            "complexity_level": "medium",
            "complexity_score": 60,
        }
        w = manager.refresh_snapshot(
            workspace_id=workspace.workspace_id,
            base_solution_json=base_solution,
            assumption_list=[],
            downstream_input={},
        )

        ctx = manager.build_workspace_context(workspace.workspace_id)

        assert hasattr(ctx, "selected_equipment")
        assert len(ctx.selected_equipment) > 0
        equipment_types = [e["equipment_type"] for e in ctx.selected_equipment]
        assert "AMR" in equipment_types
        assert "selected_equipment" in w.context_json

    def test_equipment_rationale_is_generated(self, db_session, seed_equipment):
        """验证 equipment_rationale 非空"""
        import backend.services.workspace_manager as wm_module

        wm_module.SessionLocal = mock_session_local(db_session)

        amr_result = self._make_mock_result(
            "AMR", "AMR-500L", 80.0, 8.0, 15.0
        )

        def mock_match(**kwargs):
            eq_type = kwargs.get("equipment_type")
            if eq_type == "AMR":
                return [amr_result]
            return []

        manager = WorkspaceManager()
        manager.equipment_service.match_equipment_for_scenario = mock_match

        workspace = manager.create_workspace(pipeline_id=str(uuid.uuid4()))

        base_solution = {
            "operation_type": "JIT线边仓",
            "complexity_level": "高复杂度",
            "complexity_score": 15,
        }
        manager.refresh_snapshot(
            workspace_id=workspace.workspace_id,
            base_solution_json=base_solution,
            assumption_list=[],
            downstream_input={},
        )

        ctx = manager.build_workspace_context(workspace.workspace_id)

        assert ctx.equipment_rationale != ""
        assert "AMR" in ctx.equipment_rationale

    def test_equipment_capex_range_is_populated(self, db_session, seed_equipment):
        """验证 equipment_capex_range 非空"""
        import backend.services.workspace_manager as wm_module

        wm_module.SessionLocal = mock_session_local(db_session)

        amr_result = self._make_mock_result(
            "AMR", "AMR-500L", 80.0, 8.0, 15.0
        )
        conveyor_result = self._make_mock_result(
            "Conveyor", "CV-1500", 150.0, 5.0, 10.0
        )

        def mock_match(**kwargs):
            eq_type = kwargs.get("equipment_type")
            if eq_type == "AMR":
                return [amr_result]
            elif eq_type == "Conveyor":
                return [conveyor_result]
            return []

        manager = WorkspaceManager()
        manager.equipment_service.match_equipment_for_scenario = mock_match

        workspace = manager.create_workspace(pipeline_id=str(uuid.uuid4()))

        base_solution = {
            "operation_type": "warehouse_distribution",
            "complexity_level": "medium",
            "complexity_score": 60,
        }
        manager.refresh_snapshot(
            workspace_id=workspace.workspace_id,
            base_solution_json=base_solution,
            assumption_list=[],
            downstream_input={},
        )

        ctx = manager.build_workspace_context(workspace.workspace_id)

        assert ctx.equipment_capex_range != {}
        assert "amr" in ctx.equipment_capex_range

    def test_unknown_operation_type_still_injects_equipment(
        self, db_session, seed_equipment
    ):
        """未知 operation_type 使用默认设备列表，不报错"""
        import backend.services.workspace_manager as wm_module

        wm_module.SessionLocal = mock_session_local(db_session)

        amr_result = self._make_mock_result(
            "AMR", "AMR-500L", 60.0, 8.0, 15.0
        )
        conveyor_result = self._make_mock_result(
            "Conveyor", "CV-1000", 100.0, 5.0, 10.0
        )

        def mock_match(**kwargs):
            eq_type = kwargs.get("equipment_type")
            if eq_type == "AMR":
                return [amr_result]
            elif eq_type == "Conveyor":
                return [conveyor_result]
            return []

        manager = WorkspaceManager()
        manager.equipment_service.match_equipment_for_scenario = mock_match

        workspace = manager.create_workspace(pipeline_id=str(uuid.uuid4()))

        base_solution = {
            "operation_type": "UNKNOWN_TYPE",
            "complexity_level": "low",
            "complexity_score": 5,
        }
        # Should not raise
        w = manager.refresh_snapshot(
            workspace_id=workspace.workspace_id,
            base_solution_json=base_solution,
            assumption_list=[],
            downstream_input={},
        )
        ctx = manager.build_workspace_context(workspace.workspace_id)
        # Default fallback: AMR + Conveyor
        assert len(ctx.selected_equipment) > 0


class TestBuildEquipmentText:
    """测试 _build_equipment_text 函数"""

    def test_build_equipment_text_formats_correctly(self):
        """验证 _build_equipment_text 输出正确格式"""
        from backend.services.proposal_section_generator import _build_equipment_text

        eq = {
            "equipment_type": "AMR",
            "model_name": "AMR-500L",
            "throughput_value": 80,
            "throughput_unit": "pos/hr",
            "payload_kg": 500,
            "_capex_estimate": 15.0,
        }
        result = _build_equipment_text([eq])

        assert "AMR" in result
        assert "AMR-500L" in result
        assert "80" in result
        assert "pos/hr" in result
        assert "500" in result
        assert "15" in result
        assert "单机估算" in result

    def test_build_equipment_text_empty_shows_placeholder(self):
        """空 selected_equipment 返回占位符文本"""
        from backend.services.proposal_section_generator import _build_equipment_text

        result = _build_equipment_text([])

        assert "未选定" in result
        assert "现场条件" in result


class TestCoreSolutionPromptEquipment:
    """测试 core_solution prompt 模板包含设备字段"""

    def test_core_solution_prompt_includes_equipment(self, mock_workspace_context):
        """验证 core_solution 的 prompt 中包含设备文本"""
        from backend.services.proposal_section_generator import (
            _build_context_text,
            SECTION_PROMPTS,
        )

        # Verify template includes equipment placeholders
        template_cn = SECTION_PROMPTS["core_solution"]["prompt_template_cn"]
        template_en = SECTION_PROMPTS["core_solution"]["prompt_template_en"]

        assert "{equipment_text}" in template_cn
        assert "{equipment_rationale}" in template_cn
        assert "{equipment_text}" in template_en
        assert "{equipment_rationale}" in template_en

    def test_build_context_text_includes_equipment_fields(
        self, mock_workspace_context
    ):
        """验证 _build_context_text 返回值包含 equipment_* 字段"""
        from backend.services.proposal_section_generator import _build_context_text

        ctx = _build_context_text(mock_workspace_context, language="cn")

        assert "equipment_text" in ctx
        assert "equipment_rationale" in ctx
        assert "equipment_capex_range" in ctx

    def test_build_context_text_equipment_fields_from_workspace_context(
        self, mock_workspace_context
    ):
        """验证 equipment_* 字段值来自 workspace context"""
        from backend.services.proposal_section_generator import _build_context_text

        # Simulate workspace context with equipment data
        mock_workspace_context.selected_equipment = [
            {
                "equipment_type": "AMR",
                "model_name": "AMR-500L",
                "throughput_value": 80,
                "throughput_unit": "pos/hr",
                "payload_kg": 500,
                "_capex_estimate": 15.0,
            }
        ]
        mock_workspace_context.equipment_rationale = (
            "AMR-AMR-500L：吞吐量80pos/hr，估算单价15万元"
        )
        mock_workspace_context.equipment_capex_range = {"amr": {"min": 8, "max": 15}}

        ctx = _build_context_text(mock_workspace_context, language="cn")

        assert "AMR-500L" in ctx["equipment_text"]
        assert "AMR" in ctx["equipment_rationale"]
        assert ctx["equipment_capex_range"]["amr"]["max"] == 15


# Re-use fixture from test_proposal_section_generator.py
@pytest.fixture
def mock_workspace_context():
    """标准的 WorkspaceContext fixture（无 QA 冲突）"""
    from backend.schemas.workspace_schemas import WorkspaceContext

    return WorkspaceContext(
        workspace_id="ws-test-001",
        pipeline_id="pipeline-001",
        project_name="华道汽车 JIT 供料项目",
        industry="AUTOMOTIVE",
        region="华东",
        operation_type="JIT线边仓",
        complexity_level="高复杂度",
        complexity_score=15,
        operation_narrative="采用DMS色带管理系统 + 电子看板，实现JIT直供上线。",
        labor_modules={
            "收货组": {"role": "收货组", "headcount": 4},
            "上架组": {"role": "上架组", "headcount": 3},
        },
        process_modules={
            "上线配送": {
                "name": "上线配送流程",
                "steps": ["工单接收", "集货", "配送至产线", "签收确认"],
            },
        },
        service_scope={
            "inbound": {"receiving": True, "quality_check": True, "putaway": True},
            "outbound": {"picking": True, "packing": True, "loading": True, "shipping": True},
        },
        analysis_sections={},
        active_assumptions=[
            {
                "field_key": "sku_count",
                "value": "8000",
                "rule": "月均出货量÷15",
                "version_id": 1,
                "effective_date": "2025-01-01",
            },
        ],
        overridden_assumptions=[],
        assumption_qa_warnings=[],
        snapshot_version=1,
        is_dirty=True,
        status="active",
        cost_mode="人天制",
        roi_summary={"roi_5y": "86.0%", "payback_years": "3.2年"},
        selected_equipment=[],
        equipment_capex_range={},
        equipment_rationale="",
    )
