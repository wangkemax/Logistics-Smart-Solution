"""backend/api/proposal_api.py FastAPI routes for Proposal Section Generator"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from backend.services.proposal_engine import ProposalEngine
from backend.services.proposal_section_generator import ProposalSectionGenerator
from backend.services.workspace_manager import WorkspaceManager
from backend.schemas.proposal_schemas import (
    ProposalGenerationRequest,
    ProposalSections,
)

router = APIRouter(prefix="/proposals", tags=["proposals"])

_engine = ProposalEngine()
_section_gen = ProposalSectionGenerator()
_ws_manager = WorkspaceManager()


@router.post("/generate", response_model=ProposalSections)
def generate_proposal(request: ProposalGenerationRequest):
    """
    生成提案文本。
    根据 workspace_id 拉取 WorkspaceContext，生成指定 sections。
    """
    try:
        return _engine.generate_proposal(
            workspace_id=request.workspace_id,
            sections=request.sections,
            language=request.language,
            style=request.style,
            override_prompts=request.override_prompts,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workspaces/{workspace_id}/preview/{section_key}")
def preview_section(
    workspace_id: str,
    section_key: str,
    language: str = "cn",
):
    """
    预览单个章节（快速测试用）。
    直接从 workspace context 生成单个 section，不走完整 proposal 流程。
    """
    try:
        workspace = _ws_manager.build_workspace_context(workspace_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    try:
        section_output = _section_gen.generate_section(
            workspace=workspace,
            section_key=section_key,
            language=language,
        )
        return {
            "workspace_id": workspace_id,
            "section_key": section_key,
            "title": section_output.title,
            "content": section_output.content,
            "version_id": section_output.version_id,
            "tokens_used": section_output.tokens_used,
            "generated_at": section_output.generated_at,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
