"""backend/api/document_api.py FastAPI routes for Document Assembly & Export v1.0"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend.services.document_renderer import DocumentRenderer
from backend.services.proposal_engine import ProposalEngine
from backend.services.workspace_manager import WorkspaceManager
from pydantic import BaseModel


router = APIRouter(prefix="/documents", tags=["documents"])

_renderer = DocumentRenderer()
_proposal_engine = ProposalEngine()
_ws_manager = WorkspaceManager()


class ExportRequest(BaseModel):
    """导出请求 payload"""
    workspace_id: str
    format: str = "docx"  # docx | markdown
    include_assumptions: bool = True


@router.post("/export")
def export_document(request: ExportRequest):
    """
    导出提案文档。

    流程：
    1. 从 proposal_engine 获取最近生成的 ProposalSections
    2. 从 workspace 获取 active_assumptions
    3. 渲染为指定格式
    4. 返回文件（.docx）或 JSON（markdown）
    """
    # 1. 获取 proposal
    proposal = _proposal_engine.get_latest_proposal(request.workspace_id)
    if not proposal:
        raise HTTPException(
            status_code=404,
            detail="Proposal not found. Please generate a proposal first via POST /proposals/generate.",
        )

    # 2. 获取 active_assumptions
    try:
        workspace = _ws_manager.build_workspace_context(request.workspace_id)
        active_assumptions = workspace.active_assumptions
    except Exception:
        active_assumptions = None

    # 3. 渲染
    if request.format == "docx":
        filepath = _renderer.render_docx(
            proposal_sections=proposal,
            include_assumptions=request.include_assumptions,
            active_assumptions=active_assumptions,
        )
        return FileResponse(
            filepath,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=f"proposal_{request.workspace_id[:8]}.docx",
        )
    elif request.format == "markdown":
        content = _renderer.render_markdown(
            proposal_sections=proposal,
            active_assumptions=active_assumptions if request.include_assumptions else None,
        )
        return {
            "content": content,
            "content_type": "text/markdown; charset=utf-8",
            "workspace_id": request.workspace_id,
        }
    else:
        raise HTTPException(
            status_code=400,
            detail="Unsupported format. Use 'docx' or 'markdown'.",
        )


@router.get("/workspaces/{workspace_id}/document")
def get_document_preview(workspace_id: str, format: str = "markdown"):
    """
    快速预览文档内容（Markdown 格式）。

    直接从 proposal_engine 缓存读取最近一次生成的 proposal，
    不重新生成，用于快速预览。
    """
    proposal = _proposal_engine.get_latest_proposal(workspace_id)
    if not proposal:
        raise HTTPException(
            status_code=404,
            detail="Proposal not found. Please generate a proposal first via POST /proposals/generate.",
        )

    # 获取 active_assumptions
    try:
        workspace = _ws_manager.build_workspace_context(workspace_id)
        active_assumptions = workspace.active_assumptions
    except Exception:
        active_assumptions = None

    if format == "markdown":
        content = _renderer.render_markdown(
            proposal_sections=proposal,
            active_assumptions=active_assumptions,
        )
        return {
            "workspace_id": workspace_id,
            "format": "markdown",
            "content": content,
        }
    else:
        raise HTTPException(
            status_code=400,
            detail="Only 'markdown' format is supported for preview.",
        )
