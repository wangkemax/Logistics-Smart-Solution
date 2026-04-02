"""backend/services/proposal_section_generator.py 提案章节生成引擎"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from backend.schemas.workspace_schemas import WorkspaceContext
from backend.schemas.proposal_schemas import (
    SectionOutput,
    ProposalSections,
    ProposalGenerationRequest,
)
from backend.services.proposal_llm_service import ProposalLLMService


# =============================================================================
# Section Prompt Templates
# =============================================================================

SECTION_SYSTEM_PROMPT_CN = """你是一位资深物流解决方案顾问，负责撰写专业的投标方案文本。
你生成的所有数值必须严格引用传入的假设版本（version_id），不得自行编造数据。
如果某个数据点没有在上下文中提供，明确说明"基于待确认数据"。

输出格式：Markdown。
语言：简体中文。
风格：专业、正式、可直接交付给客户。"""

SECTION_SYSTEM_PROMPT_EN = """You are a senior logistics solutions consultant responsible for writing professional tender proposal text.
All numerical values you generate must strictly cite the passed assumption version (version_id), and must not fabricate data.
If a data point is not provided in the context, explicitly state "based on data to be confirmed".

Output format: Markdown.
Language: English.
Style: Professional, formal, ready for client delivery."""

SECTION_PROMPTS = {
    "executive_summary": {
        "title_cn": "一、执行摘要",
        "title_en": "1. Executive Summary",
        "prompt_template_cn": """基于以下项目信息，撰写执行摘要（约300字）：

项目名称：{project_name}
行业：{industry}（{region}）
运营类型：{operation_type}
复杂度：{complexity_level}（评分 {complexity_score}/20）
核心方案：{operation_narrative}
成本模式：{cost_mode}
ROI摘要：{roi_text}
服务范围：{service_scope_summary}

要求：
- 用一段话概括项目价值和核心方案
- 突出客户最关心的ROI和实施周期
- 结尾用一句话总结为什么选择本供应商""",
        "prompt_template_en": """Based on the following project information, write an executive summary (approximately 300 words):

Project Name: {project_name}
Industry: {industry} ({region})
Operation Type: {operation_type}
Complexity: {complexity_level} (Score {complexity_score}/20)
Core Solution: {operation_narrative}
Cost Model: {cost_mode}
ROI Summary: {roi_text}
Service Scope: {service_scope_summary}

Requirements:
- Summarize the project value and core solution in one paragraph
- Highlight the ROI and implementation timeline that the client cares most about
- End with one sentence explaining why choose our vendor""",
    },
    "core_solution": {
        "title_cn": "二、核心方案设计",
        "title_en": "2. Core Solution Design",
        "prompt_template_cn": """基于以下方案详情，撰写核心方案设计（约600字）：

运营类型：{operation_type}
复杂度：{complexity_level}
服务范围矩阵：
{service_scope_text}

人力模块：
{labor_modules_text}

流程设计：
{process_modules_text}

有效假设（已确认参数）：
{assumptions_text}

{equipment_text}

设备选型说明：{equipment_rationale}

成本测算模式：{cost_mode}

要求：
- 分"方案概述"和"关键设计"两个小节
- 每项设计必须引用assumption中的具体数值
- 避免模糊表述，用数据说话""",
        "prompt_template_en": """Based on the following solution details, write the core solution design (approximately 600 words):

Operation Type: {operation_type}
Complexity: {complexity_level}
Service Scope Matrix:
{service_scope_text}

Labor Modules:
{labor_modules_text}

Process Design:
{process_modules_text}

Active Assumptions (Confirmed Parameters):
{assumptions_text}

{equipment_text}

Equipment Selection Rationale: {equipment_rationale}

Cost Model: {cost_mode}

Requirements:
- Divide into "Solution Overview" and "Key Design" subsections
- Each design must cite specific values from assumptions
- Avoid vague statements, let data speak""",
    },
    "implementation_plan": {
        "title_cn": "三、实施计划",
        "title_en": "3. Implementation Plan",
        "prompt_template_cn": """基于以下信息，撰写实施计划（约400字）：

行业：{industry}
运营类型：{operation_type}
复杂度：{complexity_level}（{complexity_score}/20）
假设有效期：{effective_date_text}

要求：
- 按项目阶段撰写（需求确认→方案细化→实施部署→验收交付）
- 每阶段给出预计周期
- 说明关键里程碑
- 提及质量保障措施""",
        "prompt_template_en": """Based on the following information, write an implementation plan (approximately 400 words):

Industry: {industry}
Operation Type: {operation_type}
Complexity: {complexity_level} ({complexity_score}/20)
Assumption Effective Date: {effective_date_text}

Requirements:
- Write by project phase (Requirements Confirmation → Solution Refinement → Implementation → Acceptance)
- Give estimated duration for each phase
- Explain key milestones
- Mention quality assurance measures""",
    },
}


# =============================================================================
# Context Building Helpers
# =============================================================================

def _render_service_scope(service_scope: dict) -> str:
    """将 service_scope dict 转换为可读文本"""
    if not service_scope:
        return "（基于待确认数据）"

    lines = []
    for stage, modules in service_scope.items():
        stage_label = {
            "inbound": "入库作业",
            "outbound": "出库作业",
            "storage": "存储管理",
            "returns": "退货处理",
            "增值服务": "增值服务",
        }.get(stage, stage)

        if isinstance(modules, dict):
            items = []
            for k, v in modules.items():
                symbol = "✓" if v in (True, "true", "True", 1, "1") else "✗"
                items.append(f"{k} {symbol}")
            lines.append(f"{stage_label}：{'、'.join(items)}")
        elif isinstance(modules, list):
            items = [f"{m} ✓" for m in modules]
            lines.append(f"{stage_label}：{'、'.join(items)}")
        elif modules in (True, "true", 1):
            lines.append(f"{stage_label}：✓")

    return "；".join(lines) if lines else "（基于待确认数据）"


def _render_labor_modules(labor_modules: dict) -> str:
    """将 labor_modules dict 转换为可读文本"""
    if not labor_modules:
        return "（基于待确认数据）"

    lines = []
    for team_key, team_info in labor_modules.items():
        if isinstance(team_info, dict):
            role = team_info.get("role", team_key)
            headcount = team_info.get("headcount", team_info.get("人数", "?"))
            lines.append(f"{role}：{headcount}人")
        elif isinstance(team_info, str):
            lines.append(f"{team_key}：{team_info}")
        else:
            lines.append(f"{team_key}：{team_info}人")

    return "；".join(lines) if lines else "（基于待确认数据）"


def _render_process_modules(process_modules: dict) -> str:
    """将 process_modules dict 转换为可读文本"""
    if not process_modules:
        return "（基于待确认数据）"

    lines = []
    for proc_key, proc_info in process_modules.items():
        if isinstance(proc_info, dict):
            name = proc_info.get("name", proc_info.get("流程名称", proc_key))
            steps = proc_info.get("steps", proc_info.get("流程步骤", []))
            if isinstance(steps, list) and steps:
                step_labels = " → ".join(str(s) if isinstance(s, str) else s.get("name", str(s)) for s in steps[:5])
                lines.append(f"{name}：{step_labels}")
            else:
                lines.append(f"{name}")
        elif isinstance(proc_info, str):
            lines.append(f"{proc_key}：{proc_info}")
        else:
            lines.append(f"{proc_key}")

    return "；".join(lines) if lines else "（基于待确认数据）"


def _build_equipment_text(selected_equipment: list[dict]) -> str:
    """将 selected_equipment 转换为 prompt 可读文本"""
    if not selected_equipment:
        return "（未选定具体设备，需根据现场条件确定）"

    lines = []
    for eq in selected_equipment:
        capex_est = eq.get("_capex_estimate", 0)
        lines.append(
            f"• {eq['equipment_type']} {eq['model_name']}："
            f"吞吐量{eq['throughput_value']}{eq['throughput_unit']}，"
            f"载重{eq['payload_kg']}kg，"
            f"单机估算{capex_est}万元"
        )
    return "\n".join(lines)


def _render_assumptions(active_assumptions: list[dict]) -> str:
    """将 active_assumptions list 转换为可读文本"""
    if not active_assumptions:
        return "（暂无已确认假设，数据待补充）"

    lines = []
    for assumption in active_assumptions:
        field_key = assumption.get("field_key", "")
        value = assumption.get("value", "待确认")
        rule = assumption.get("rule", "")
        version_id = assumption.get("version_id", 1)

        if rule:
            lines.append(f"• {field_key} = {value}（依据：{rule}，版本v{version_id}）")
        else:
            lines.append(f"• {field_key} = {value}（版本v{version_id}）")

    return "\n".join(lines)


def _render_roi_summary(roi_summary: dict) -> str:
    """将 roi_summary dict 转换为 ROI 相关文本"""
    if not roi_summary:
        return "（基于待确认数据）"

    parts = []
    if roi_summary.get("roi_5y"):
        parts.append(f"5年ROI: {roi_summary['roi_5y']}")
    if roi_summary.get("payback_years"):
        parts.append(f"投资回收期: {roi_summary['payback_years']}")
    if roi_summary.get("annual_savings"):
        parts.append(f"年节省成本: {roi_summary['annual_savings']}")
    if roi_summary.get("npv"):
        parts.append(f"NPV: {roi_summary['npv']}")
    if roi_summary.get("irr"):
        parts.append(f"IRR: {roi_summary['irr']}")

    return "；".join(parts) if parts else "（基于待确认数据）"


def _get_effective_date_text(active_assumptions: list[dict]) -> str:
    """从 active_assumptions 中找最早的有效日期"""
    effective_dates = []
    for assumption in active_assumptions:
        effective_date = assumption.get("effective_date")
        if effective_date and effective_date not in ("", "待确认"):
            effective_dates.append(effective_date)

    if effective_dates:
        # 返回最早日期
        effective_dates.sort()
        return effective_dates[0]
    return "待确认"


def _build_context_text(workspace: WorkspaceContext, language: str = "cn") -> dict:
    """
    将 WorkspaceContext 转换为 prompt 填充字典。

    Args:
        workspace: WorkspaceContext 对象
        language: 语言标识，"cn" 或 "en"

    Returns:
        适合 template.format(**context) 的字典
    """
    project_name = workspace.project_name or "待确认"
    industry = workspace.industry or "待确认"
    region = workspace.region or "待确认"
    operation_type = workspace.operation_type or "待确认"
    complexity_level = workspace.complexity_level or "待确认"
    complexity_score = workspace.complexity_score or 0
    operation_narrative = workspace.operation_narrative or "待确认"
    cost_mode = workspace.cost_mode or "待确认"

    service_scope_text = _render_service_scope(workspace.service_scope)
    labor_modules_text = _render_labor_modules(workspace.labor_modules)
    process_modules_text = _render_process_modules(workspace.process_modules)
    assumptions_text = _render_assumptions(workspace.active_assumptions)
    roi_text = _render_roi_summary(workspace.roi_summary)
    effective_date_text = _get_effective_date_text(workspace.active_assumptions)

    # service_scope_summary 用于 executive_summary（简化版本）
    service_scope_summary = _render_service_scope(workspace.service_scope)
    equipment_text = _build_equipment_text(workspace.selected_equipment)

    return {
        "project_name": project_name,
        "industry": industry,
        "region": region,
        "operation_type": operation_type,
        "complexity_level": complexity_level,
        "complexity_score": complexity_score,
        "operation_narrative": operation_narrative,
        "cost_mode": cost_mode,
        "service_scope_text": service_scope_text,
        "service_scope_summary": service_scope_summary,
        "labor_modules_text": labor_modules_text,
        "process_modules_text": process_modules_text,
        "assumptions_text": assumptions_text,
        "roi_text": roi_text,
        "effective_date_text": effective_date_text,
        "equipment_text": equipment_text,
        "equipment_rationale": workspace.equipment_rationale or "",
        "equipment_capex_range": workspace.equipment_capex_range or {},
    }


# =============================================================================
# Proposal Section Generator
# =============================================================================

class ProposalSectionGenerator:
    """提案章节生成器"""

    def __init__(self):
        self.llm = ProposalLLMService()

    def generate_section(
        self,
        workspace: WorkspaceContext,
        section_key: str,
        language: str = "cn",
        override_prompt: str | None = None,
    ) -> SectionOutput:
        """
        生成单个章节。
        采用分块生成（Chunked Generation）架构——
        每个 section 独立调用 LLM，互不干扰。

        Args:
            workspace: WorkspaceContext 对象
            section_key: 章节 key，如 "executive_summary"
            language: 语言，"cn" 或 "en"
            override_prompt: 可选，覆盖默认 prompt

        Returns:
            SectionOutput 对象
        """
        # 获取 section template
        template = SECTION_PROMPTS.get(section_key)
        if not template:
            raise ValueError(f"Unknown section_key: {section_key}")

        # 构建 system prompt
        system_prompt = SECTION_SYSTEM_PROMPT_CN if language == "cn" else SECTION_SYSTEM_PROMPT_EN

        # 构建 user prompt
        context = _build_context_text(workspace, language)
        title = template["title_cn"] if language == "cn" else template["title_en"]

        if override_prompt:
            user_prompt = override_prompt.format(**context)
        else:
            prompt_key = f"prompt_template_{language}"
            prompt_template = template.get(prompt_key, template["prompt_template_cn"])
            user_prompt = prompt_template.format(**context)

        # 调用 LLM
        response_text, tokens_used = self.llm._call_llm(system_prompt, user_prompt, max_tokens=2048)

        # 确定 version_id（从 active_assumptions 中取最大 version_id）
        version_id = 1
        if workspace.active_assumptions:
            version_ids = [
                a.get("version_id", 1)
                for a in workspace.active_assumptions
                if isinstance(a, dict)
            ]
            if version_ids:
                version_id = max(version_ids)

        return SectionOutput(
            section_key=section_key,
            title=title,
            content=response_text,
            version_id=version_id,
            tokens_used=tokens_used,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    def generate_all(
        self,
        workspace: WorkspaceContext,
        request: ProposalGenerationRequest,
    ) -> ProposalSections:
        """
        批量生成多个章节。
        串行调用，每个 section 独立 LLM 调用。

        Args:
            workspace: WorkspaceContext 对象
            request: ProposalGenerationRequest 对象

        Returns:
            ProposalSections 对象
        """
        sections_to_generate = request.sections or [
            "executive_summary",
            "core_solution",
            "implementation_plan",
        ]

        generated: dict[str, SectionOutput] = {}
        total_tokens = 0

        for section_key in sections_to_generate:
            override_prompt = request.override_prompts.get(section_key)
            section_output = self.generate_section(
                workspace=workspace,
                section_key=section_key,
                language=request.language,
                override_prompt=override_prompt,
            )
            generated[section_key] = section_output
            total_tokens += section_output.tokens_used

        # 组装 ProposalSections
        now_iso = datetime.now(timezone.utc).isoformat()

        result_kwargs = dict(
            workspace_id=workspace.workspace_id,
            pipeline_id=workspace.pipeline_id,
            executive_summary=generated.get(
                "executive_summary",
                SectionOutput(section_key="executive_summary", title="一、执行摘要", content=""),
            ),
            core_solution=generated.get(
                "core_solution",
                SectionOutput(section_key="core_solution", title="二、核心方案设计", content=""),
            ),
            implementation_plan=generated.get(
                "implementation_plan",
                SectionOutput(section_key="implementation_plan", title="三、实施计划", content=""),
            ),
            total_tokens=total_tokens,
            generated_at=now_iso,
        )

        if "financial_kpi" in sections_to_generate:
            result_kwargs["financial_kpi"] = generated.get("financial_kpi")
        if "risk_analysis" in sections_to_generate:
            result_kwargs["risk_analysis"] = generated.get("risk_analysis")

        return ProposalSections(**result_kwargs)
