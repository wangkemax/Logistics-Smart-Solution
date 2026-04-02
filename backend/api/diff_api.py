"""backend/api/diff_api.py — v1.4 Bid Scenario Diffing API"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services.workspace_diff_service import WorkspaceDiffService


router = APIRouter(prefix="/diff", tags=["diff"])
_diff_service = WorkspaceDiffService()


class DiffWorkspacesRequest(BaseModel):
    """对比两个 Workspace 的请求 payload"""
    workspace_a_id: str
    workspace_b_id: str


@router.post("/workspaces")
def diff_workspaces(request: DiffWorkspacesRequest):
    """
    对比两个 Workspace 版本的差异。

    返回：
    - workspace_a / workspace_b 元信息
    - param_diffs: 所有非嵌套字段的差异
    - cost_diffs: 财务指标差异
    - llm_analysis: 简要影响分析文本
    """
    try:
        result = _diff_service.diff(
            workspace_a_id=request.workspace_a_id,
            workspace_b_id=request.workspace_b_id,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Diff computation failed: {e}")


@router.get("/workspaces/{workspace_id}/versions")
def list_workspace_versions(workspace_id: str):
    """
    列出某 Workspace 的所有快照版本。

    当前实现返回当前版本信息。
    完整版本历史需要 WorkspaceHistory 扩展表支持。
    """
    try:
        versions = _diff_service.get_workspace_versions(workspace_id)
        return {
            "workspace_id": workspace_id,
            "versions": versions,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
