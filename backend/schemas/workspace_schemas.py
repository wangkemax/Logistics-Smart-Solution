"""backend/schemas/workspace_schemas.py Pydantic schemas for Workspace API v1.0"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceCreate(BaseModel):
    """Payload for creating a new Workspace."""
    pipeline_id: str
    project_name: str = ""
    industry: str = ""
    region: str = ""


class WorkspaceContext(BaseModel):
    """Workspace 合并后的完整上下文 — proposal_engine 的输入"""
    workspace_id: str
    pipeline_id: str
    project_name: str
    industry: str
    region: str

    # 来自 Base Solution (v0.7)
    operation_type: str = ""
    complexity_level: str = ""
    complexity_score: int = 0
    operation_narrative: str = ""
    labor_modules: dict = Field(default_factory=dict)
    process_modules: dict = Field(default_factory=dict)
    service_scope: dict = Field(default_factory=dict)
    analysis_sections: dict = Field(default_factory=dict)

    # 来自 Assumption (v0.9)
    active_assumptions: list[dict] = Field(default_factory=list)
    overridden_assumptions: list[dict] = Field(default_factory=list)
    assumption_qa_warnings: list[str] = Field(default_factory=list)

    # 元数据
    snapshot_version: int = 1
    is_dirty: bool = True
    status: str = "active"

    # Cost & ROI（从 downstream_input 传入）
    cost_mode: str = ""
    roi_summary: dict = Field(default_factory=dict)

    # 设备选型（v1.1 Scenario-Equipment DI）
    selected_equipment: list[dict] = Field(default_factory=list)
    equipment_capex_range: dict = Field(default_factory=dict)
    equipment_rationale: str = ""


class WorkspaceSchema(BaseModel):
    """Full Workspace model returned by API."""
    workspace_id: str
    pipeline_id: str
    project_name: str
    industry: str
    region: str

    base_solution_snapshot: dict = Field(default_factory=dict)
    assumption_snapshot: list[dict] = Field(default_factory=list)
    context_json: dict = Field(default_factory=dict)

    snapshot_version: int = 1
    is_dirty: bool = True
    status: str = "active"

    created_at: datetime
    updated_at: datetime
    finalized_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class RefreshSnapshotPayload(BaseModel):
    """Payload for refreshing a Workspace snapshot."""
    base_solution_json: dict = Field(default_factory=dict)
    assumption_list: list[dict] = Field(default_factory=list)
    downstream_input: dict = Field(default_factory=dict)


class WorkspaceUpdate(BaseModel):
    """Workspace 更新 payload"""
    project_name: Optional[str] = None
    industry: Optional[str] = None
    region: Optional[str] = None
    context_overrides: Optional[dict] = None  # 用户在 Workspace UI 中直接修改的字段
