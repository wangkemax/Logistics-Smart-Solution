"""tests/test_workspace_manager.py Unit tests for WorkspaceManager v1.0"""
from __future__ import annotations

import json
import uuid
import pytest

from backend.models.database import Base, engine, SessionLocal
from backend.models.workspace_models import Workspace
from backend.services.workspace_manager import WorkspaceManager


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh in-memory DB for each test."""
    # Use in-memory SQLite per test
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def wm(db_session):
    """WorkspaceManager with test DB session patched."""
    manager = WorkspaceManager()
    # Patch SessionLocal to use test session for this manager instance
    import backend.services.workspace_manager as wm_module
    wm_module.SessionLocal = type("T", (), {"__enter__": lambda s: db_session, "__exit__": lambda s, *a: None, "__call__": lambda s: db_session})()
    return manager


class TestWorkspaceManager:
    """Tests for WorkspaceManager."""

    def test_create_workspace(self, db_session):
        """创建 Workspace，验证 snapshot_version=1, is_dirty=True."""
        import backend.services.workspace_manager as wm_module
        wm_module.SessionLocal = type("T", (), {
            "__enter__": lambda s: db_session,
            "__exit__": lambda s, *a: None,
            "__call__": lambda s: db_session,
        })()

        manager = WorkspaceManager()
        pipeline_id = str(uuid.uuid4())

        workspace = manager.create_workspace(
            pipeline_id=pipeline_id,
            project_name="Test Project",
            industry="FMCG",
            region="华东",
        )

        assert workspace.workspace_id is not None
        assert workspace.pipeline_id == pipeline_id
        assert workspace.project_name == "Test Project"
        assert workspace.industry == "FMCG"
        assert workspace.region == "华东"
        assert workspace.snapshot_version == 1
        assert workspace.is_dirty is True
        assert workspace.status == "active"
        assert workspace.context_json == "{}"

    def test_get_workspace(self, db_session):
        """测试 get_workspace 返回正确的 Workspace."""
        import backend.services.workspace_manager as wm_module
        wm_module.SessionLocal = type("T", (), {
            "__enter__": lambda s: db_session,
            "__exit__": lambda s, *a: None,
            "__call__": lambda s: db_session,
        })()

        manager = WorkspaceManager()
        pipeline_id = str(uuid.uuid4())

        created = manager.create_workspace(pipeline_id=pipeline_id, project_name="Get Test")
        retrieved = manager.get_workspace(created.workspace_id)

        assert retrieved is not None
        assert retrieved.workspace_id == created.workspace_id
        assert retrieved.project_name == "Get Test"

    def test_get_workspace_not_found(self, db_session):
        """测试 get_workspace 对不存在的 ID 返回 None."""
        import backend.services.workspace_manager as wm_module
        wm_module.SessionLocal = type("T", (), {
            "__enter__": lambda s: db_session,
            "__exit__": lambda s, *a: None,
            "__call__": lambda s: db_session,
        })()

        manager = WorkspaceManager()
        result = manager.get_workspace(str(uuid.uuid4()))
        assert result is None

    def test_refresh_snapshot_increments_version(self, db_session):
        """两次 refresh_snapshot，验证 snapshot_version 从 1 变成 2."""
        import backend.services.workspace_manager as wm_module
        wm_module.SessionLocal = type("T", (), {
            "__enter__": lambda s: db_session,
            "__exit__": lambda s, *a: None,
            "__call__": lambda s: db_session,
        })()

        manager = WorkspaceManager()
        pipeline_id = str(uuid.uuid4())

        workspace = manager.create_workspace(pipeline_id=pipeline_id)
        assert workspace.snapshot_version == 1

        base_solution = {
            "operation_type": "3PL",
            "complexity_level": "medium",
            "complexity_score": 60,
            "operation_narrative": "Test narrative",
            "labor_modules": {"拣选": "半自动"},
            "process_modules": {},
            "service_scope": {},
            "analysis_sections": {},
        }
        assumptions = [
            {"field_key": "labor_cost", "value": "5000", "is_overridden": False},
            {"field_key": "warehouse_rent", "value": "30", "is_overridden": True},
        ]
        downstream = {"cost_mode": "opex", "roi_summary": {}}

        # First refresh
        w1 = manager.refresh_snapshot(
            workspace_id=workspace.workspace_id,
            base_solution_json=base_solution,
            assumption_list=assumptions,
            downstream_input=downstream,
        )
        assert w1.snapshot_version == 2
        assert w1.is_dirty is True

        # Second refresh
        base_solution["complexity_score"] = 70
        w2 = manager.refresh_snapshot(
            workspace_id=workspace.workspace_id,
            base_solution_json=base_solution,
            assumption_list=assumptions,
            downstream_input=downstream,
        )
        assert w2.snapshot_version == 3
        assert w2.is_dirty is True

        # Verify assumptions split correctly
        ctx = json.loads(w2.context_json)
        assert len(ctx["active_assumptions"]) == 1
        assert len(ctx["overridden_assumptions"]) == 1

    def test_build_workspace_context(self, db_session):
        """验证 context_json 能正确解析为 WorkspaceContext."""
        import backend.services.workspace_manager as wm_module
        wm_module.SessionLocal = type("T", (), {
            "__enter__": lambda s: db_session,
            "__exit__": lambda s, *a: None,
            "__call__": lambda s: db_session,
        })()

        manager = WorkspaceManager()
        pipeline_id = str(uuid.uuid4())

        workspace = manager.create_workspace(
            pipeline_id=pipeline_id,
            project_name="Context Test",
            industry="AUTOMOTIVE",
            region="华东",
        )

        base_solution = {
            "operation_type": "JIT",
            "complexity_level": "high",
            "complexity_score": 85,
            "operation_narrative": "High complexity automotive JIT",
            "labor_modules": {"拆零": "自动"},
            "process_modules": {"入库": "标准化"},
            "service_scope": {"inbound": {"receiving": True}},
            "analysis_sections": {"section_1": "text"},
        }
        assumptions = [
            {"field_key": "avg_salary", "value": "8000", "is_overridden": False},
        ]
        downstream = {
            "cost_mode": "capex",
            "roi_summary": {"roi": "15%", "payback": "3年"},
        }

        manager.refresh_snapshot(
            workspace_id=workspace.workspace_id,
            base_solution_json=base_solution,
            assumption_list=assumptions,
            downstream_input=downstream,
        )

        ctx = manager.build_workspace_context(workspace.workspace_id)

        assert ctx.workspace_id == workspace.workspace_id
        assert ctx.pipeline_id == pipeline_id
        assert ctx.project_name == "Context Test"
        assert ctx.industry == "AUTOMOTIVE"
        assert ctx.operation_type == "JIT"
        assert ctx.complexity_level == "high"
        assert ctx.complexity_score == 85
        assert ctx.operation_narrative == "High complexity automotive JIT"
        assert ctx.labor_modules == {"拆零": "自动"}
        assert ctx.active_assumptions == assumptions
        assert ctx.cost_mode == "capex"
        assert ctx.roi_summary == {"roi": "15%", "payback": "3年"}
        assert ctx.snapshot_version == 2
        assert ctx.is_dirty is True

    def test_finalize_clears_dirty(self, db_session):
        """finalize 后 is_dirty=False, status='finalized'."""
        import backend.services.workspace_manager as wm_module
        wm_module.SessionLocal = type("T", (), {
            "__enter__": lambda s: db_session,
            "__exit__": lambda s, *a: None,
            "__call__": lambda s: db_session,
        })()

        manager = WorkspaceManager()
        pipeline_id = str(uuid.uuid4())

        workspace = manager.create_workspace(pipeline_id=pipeline_id)
        assert workspace.is_dirty is True
        assert workspace.status == "active"

        finalized = manager.finalize_workspace(workspace.workspace_id)

        assert finalized.is_dirty is False
        assert finalized.status == "finalized"
        assert finalized.finalized_at is not None

        # Context should also be updated
        ctx = json.loads(finalized.context_json)
        assert ctx["is_dirty"] is False
        assert ctx["status"] == "finalized"

    def test_update_context_field(self, db_session):
        """update_context_field 更新字段并标记 dirty."""
        import backend.services.workspace_manager as wm_module
        wm_module.SessionLocal = type("T", (), {
            "__enter__": lambda s: db_session,
            "__exit__": lambda s, *a: None,
            "__call__": lambda s: db_session,
        })()

        manager = WorkspaceManager()
        pipeline_id = str(uuid.uuid4())

        workspace = manager.create_workspace(pipeline_id=pipeline_id, project_name="Old Name")
        assert workspace.is_dirty is True

        # Simulate a snapshot so context_json is not empty
        base_solution = {"operation_type": "3PL"}
        manager.refresh_snapshot(
            workspace_id=workspace.workspace_id,
            base_solution_json=base_solution,
            assumption_list=[],
            downstream_input={},
        )

        updated = manager.update_context_field(
            workspace_id=workspace.workspace_id,
            field_path="project_name",
            value="New Name",
        )

        assert updated.project_name == "New Name"
        assert updated.is_dirty is True

        ctx = json.loads(updated.context_json)
        assert ctx["project_name"] == "New Name"
        assert ctx["is_dirty"] is True

    def test_list_workspaces_filters(self, db_session):
        """测试 list_workspaces 按 pipeline_id 和 status 过滤."""
        import backend.services.workspace_manager as wm_module
        wm_module.SessionLocal = type("T", (), {
            "__enter__": lambda s: db_session,
            "__exit__": lambda s, *a: None,
            "__call__": lambda s: db_session,
        })()

        manager = WorkspaceManager()
        pipeline_a = str(uuid.uuid4())
        pipeline_b = str(uuid.uuid4())

        w1 = manager.create_workspace(pipeline_id=pipeline_a, project_name="W1")
        w2 = manager.create_workspace(pipeline_id=pipeline_a, project_name="W2")
        w3 = manager.create_workspace(pipeline_id=pipeline_b, project_name="W3")

        # Filter by pipeline_id
        list_a = manager.list_workspaces(pipeline_id=pipeline_a)
        assert len(list_a) == 2

        list_b = manager.list_workspaces(pipeline_id=pipeline_b)
        assert len(list_b) == 1

        # Finalize one
        manager.finalize_workspace(w1.workspace_id)

        # Filter by status
        active_list = manager.list_workspaces(status="active")
        assert all(w.status == "active" for w in active_list)

        finalized_list = manager.list_workspaces(status="finalized")
        assert all(w.status == "finalized" for w in finalized_list)

    def test_refresh_snapshot_merges_downstream_input(self, db_session):
        """验证 downstream_input 的 cost_mode 和 roi_summary 被正确合并."""
        import backend.services.workspace_manager as wm_module
        wm_module.SessionLocal = type("T", (), {
            "__enter__": lambda s: db_session,
            "__exit__": lambda s, *a: None,
            "__call__": lambda s: db_session,
        })()

        manager = WorkspaceManager()
        workspace = manager.create_workspace(pipeline_id=str(uuid.uuid4()))

        manager.refresh_snapshot(
            workspace_id=workspace.workspace_id,
            base_solution_json={"operation_type": "3PL"},
            assumption_list=[],
            downstream_input={
                "cost_mode": "opex",
                "roi_summary": {"irr": "12%", "npv": "5M"},
                "assumption_qa_warnings": ["labor_cost may be underestimated"],
            },
        )

        ctx = manager.build_workspace_context(workspace.workspace_id)
        assert ctx.cost_mode == "opex"
        assert ctx.roi_summary == {"irr": "12%", "npv": "5M"}
        assert ctx.assumption_qa_warnings == ["labor_cost may be underestimated"]
