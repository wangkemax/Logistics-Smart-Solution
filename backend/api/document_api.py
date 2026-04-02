"""backend/api/document_api.py FastAPI routes for Document Assembly & Export v1.0"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend.services.document_renderer import DocumentRenderer
from backend.services.pitch_renderer import PitchRenderer
from backend.services.proposal_engine import ProposalEngine
from backend.services.workspace_manager import WorkspaceManager
from pydantic import BaseModel


router = APIRouter(prefix="/documents", tags=["documents"])

_renderer = DocumentRenderer()
_pitch_renderer = PitchRenderer()
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


# ─── v1.4 PPT Export Routes ──────────────────────────────────────────────────

class PptxExportRequest(BaseModel):
    """PPTX 导出请求 payload"""
    workspace_id: str
    format: str = "pptx"  # pptx | markdown
    theme: str = "default"  # default | minimal | gaussian


@router.post("/export/pptx")
def export_pptx(request: PptxExportRequest):
    """
    导出为 PPTX（通过 Marp Markdown 中间格式）。

    流程：
    1. 获取/生成 ProposalSections
    2. PitchRenderer.render_marp_markdown()
    3. 调用 marp-cli 将 Markdown 渲染为 PPTX
    4. 返回文件（优先）或 Markdown（降级）
    """
    # 1. 获取 proposal
    proposal = _proposal_engine.get_latest_proposal(request.workspace_id)
    if not proposal:
        raise HTTPException(
            status_code=404,
            detail="Proposal not found. Please generate a proposal first via POST /proposals/generate.",
        )

    # 2. 渲染为 Marp Markdown
    marp_md = _pitch_renderer.render_marp_markdown(
        proposal,
        company_name="飞力达物流",
        theme=request.theme,
    )

    # 3. 尝试调用 marp-cli 渲染为 PPTX
    import subprocess
    import tempfile
    import os

    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(marp_md)
            md_path = f.name

        output_dir = tempfile.mkdtemp()
        result = subprocess.run(
            ["npx", "marp", md_path, "--pptx", "--output", output_dir],
            capture_output=True,
            text=True,
            timeout=60,
        )

        pptx_files = [f for f in os.listdir(output_dir) if f.endswith(".pptx")]
        if pptx_files:
            pptx_path = os.path.join(output_dir, pptx_files[0])
            return FileResponse(
                pptx_path,
                media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                filename=f"pitch_{request.workspace_id[:8]}.pptx",
            )
    except Exception:
        # marp-cli 不可用或调用失败，优雅降级为返回 Markdown
        pass
    finally:
        # 清理临时文件
        if "md_path" in dir() and os.path.exists(md_path):
            os.unlink(md_path)

    # 降级：返回 Markdown
    return {
        "format": "markdown",
        "content": marp_md,
        "workspace_id": request.workspace_id,
        "note": "marp-cli not available, returning Markdown. Use @marp-team/marp-cli to enable PPTX export.",
    }


@router.get("/workspaces/{workspace_id}/preview/pptx")
def preview_pptx_markdown(workspace_id: str, theme: str = "default"):
    """
    预览 Marp Markdown（用于调试或前端自行渲染）。

    返回完整的 Marp Markdown，可用于：
    - 本地 marp-cli 渲染：npx marp --pptx preview.md
    - 前端 reveal.js / Marp 在线渲染
    """
    proposal = _proposal_engine.get_latest_proposal(workspace_id)
    if not proposal:
        raise HTTPException(
            status_code=404,
            detail="Proposal not found. Please generate a proposal first via POST /proposals/generate.",
        )

    marp_md = _pitch_renderer.render_marp_markdown(
        proposal,
        company_name="飞力达物流",
        theme=theme,
    )

    return {
        "workspace_id": workspace_id,
        "theme": theme,
        "markdown": marp_md,
        "line_count": len(marp_md.splitlines()),
    }
