"""backend/schemas/proposal_schemas.py Pydantic schemas for Proposal Section Generator v1.0"""
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional


class SectionOutput(BaseModel):
    """单个章节的生成结果"""
    section_key: str  # 例如 "executive_summary" / "core_solution" / "implementation_plan"
    title: str  # 章节标题
    content: str  # 生成的正文（Markdown 格式）
    version_id: int = 1  # 引用的 assumption version_id
    tokens_used: int = 0
    generated_at: str = ""  # ISO timestamp


class ProposalSections(BaseModel):
    """一次生成请求的所有章节"""
    workspace_id: str
    pipeline_id: str
    executive_summary: SectionOutput
    core_solution: SectionOutput
    implementation_plan: SectionOutput
    financial_kpi: Optional[SectionOutput] = None
    risk_analysis: Optional[SectionOutput] = None
    financial_summary: Optional[SectionOutput] = None  # v1.2: 财务测算摘要
    total_tokens: int = 0
    generated_at: str = ""


class ProposalGenerationRequest(BaseModel):
    """生成请求 payload"""
    workspace_id: str
    sections: list[str] = Field(
        default=["executive_summary", "core_solution", "implementation_plan"]
    )
    language: str = "cn"  # cn / en
    style: str = "formal"  # formal / concise / detailed
    override_prompts: dict[str, str] = Field(default_factory=dict)  # 可选：覆盖特定 section 的 prompt
