"""backend/api/workspace_api.py FastAPI routes for Workspace Context API v1.0"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from backend.services.workspace_manager import WorkspaceManager
from backend.schemas.workspace_schemas import (
    WorkspaceCreate,
    WorkspaceSchema,
    WorkspaceContext,
    RefreshSnapshotPayload,
    WorkspaceUpdate,
)


router = APIRouter(prefix="/workspaces", tags=["workspace"])
_wm = WorkspaceManager()


@router.post("", response_model=WorkspaceSchema)
def create_workspace(payload: WorkspaceCreate) -> WorkspaceSchema:
    """创建新 Workspace."""
    workspace = _wm.create_workspace(
        pipeline_id=payload.pipeline_id,
        project_name=payload.project_name,
        industry=payload.industry,
        region=payload.region,
    )
    return _wm._to_schema(workspace)


@router.get("/{workspace_id}", response_model=WorkspaceSchema)
def get_workspace(workspace_id: str) -> WorkspaceSchema:
    """根据 workspace_id 获取 Workspace."""
    workspace = _wm.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail=f"Workspace not found: {workspace_id}")
    return _wm._to_schema(workspace)


@router.post("/{workspace_id}/refresh", response_model=WorkspaceSchema)
def refresh_snapshot(workspace_id: str, body: RefreshSnapshotPayload) -> WorkspaceSchema:
    """
    重新拉取 v0.7 Base Solution + v0.9 Assumptions，生成新的 context_json。
    snapshot_version += 1，is_dirty = True。
    """
    workspace = _wm.refresh_snapshot(
        workspace_id=workspace_id,
        base_solution_json=body.base_solution_json,
        assumption_list=body.assumption_list,
        downstream_input=body.downstream_input,
    )
    return _wm._to_schema(workspace)


@router.patch("/{workspace_id}/fields", response_model=WorkspaceSchema)
def update_context_field(
    workspace_id: str,
    field_path: str,
    value: Any,
) -> WorkspaceSchema:
    """用户在 Workspace UI 中直接修改某个字段，标记为 dirty."""
    try:
        workspace = _wm.update_context_field(workspace_id, field_path, value)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _wm._to_schema(workspace)


@router.post("/{workspace_id}/finalize", response_model=WorkspaceSchema)
def finalize_workspace(workspace_id: str) -> WorkspaceSchema:
    """最终化 Workspace，锁定快照，is_dirty = False，status = finalized."""
    try:
        workspace = _wm.finalize_workspace(workspace_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _wm._to_schema(workspace)


@router.get("/{workspace_id}/context", response_model=WorkspaceContext)
def get_workspace_context(workspace_id: str) -> WorkspaceContext:
    """
    将 Workspace 的 context_json 解析为 WorkspaceContext Pydantic 模型。
    这是 proposal_engine.py 的核心输入。
    """
    try:
        return _wm.build_workspace_context(workspace_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("", response_model=list[WorkspaceSchema])
def list_workspaces(
    pipeline_id: str | None = None,
    status: str | None = None,
) -> list[WorkspaceSchema]:
    """列出 Workspace，支持按 pipeline_id 和 status 过滤."""
    workspaces = _wm.list_workspaces(pipeline_id=pipeline_id, status=status)
    return [_wm._to_schema(w) for w in workspaces]
