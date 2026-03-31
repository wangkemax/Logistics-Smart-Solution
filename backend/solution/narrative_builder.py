"""
narrative_builder.py — v0.8
============================
Template-driven narrative generation for BaseSolution.

v1 strategy: template concatenation (no LLM).
Each section narrative is a markdown fragment assembled from structured fields.

Future (v2): lightweight LLM polish pass over templates.
The LLM must ONLY consume structured fields, never re-infer business facts.
"""

from __future__ import annotations

from backend.schemas.base_solution_schema import BaseSolution


def build_narrative(base_solution: BaseSolution) -> str:
    """
    Generate the complete narrative for a BaseSolution.

    Template-based: assembles markdown from structured fields.
    No LLM calls in v1.

    Parameters
    ----------
    base_solution : BaseSolution
        Fully-populated BaseSolution object.

    Returns
    -------
    str
        Markdown narrative.
    """
    sections = [
        _build_executive_summary(base_solution),
        _build_operation_mode_narrative(base_solution),
        _build_process_design_narrative(base_solution),
        _build_labor_model_narrative(base_solution),
        _build_kpi_framework_narrative(base_solution),
        _build_system_boundary_narrative(base_solution),
        _build_risk_profile_narrative(base_solution),
        _build_implementation_strategy_narrative(base_solution),
    ]
    return "\n\n".join(s for s in sections if s)


def _build_executive_summary(bs: BaseSolution) -> str:
    """Executive summary section."""
    conf = bs.confidence.value if hasattr(bs.confidence, 'value') else bs.confidence
    tier = bs.operation_mode.scale_tier if hasattr(bs.operation_mode, 'scale_tier') else ""

    summary_parts = [
        f"## 方案概述",
        "",
        f"本方案基于 **{bs.operation_mode.label}** 为核心运营框架，"
        f"针对 **{_area_label(bs.labor_model)}** 规模的仓储运营场景设计。",
        "",
        f"**运营模式：** {bs.operation_mode.label}",
        f"**仓储规模：** {_area_label(bs.labor_model)}",
        f"**服务范围：** {len(bs.process_design.stages)} 个作业环节",
        f"**方案置信度：** {conf}",
    ]

    if bs.defaulted_p2_fields:
        defaulted = ", ".join(bs.defaulted_p2_fields)
        summary_parts.extend([
            "",
            f"> ⚠️ **数据说明：** 以下字段基于系统默认值（{defaulted}），建议通过 Clarification Workspace 确认真实值，以提升方案精度。",
        ])

    return "\n".join(summary_parts)


def _area_label(labor_model) -> str:
    # Rough estimation from annual_labor_cost — this is a display label only
    annual = getattr(labor_model, 'annual_labor_cost', 0) or 0
    if annual == 0:
        return "待评估"
    monthly = annual / 12
    if monthly < 200_000:
        return "小规模"
    elif monthly < 800_000:
        return "中等规模"
    else:
        return "大规模"


def _build_operation_mode_narrative(bs: BaseSolution) -> str:
    """Operation mode section narrative."""
    om = bs.operation_mode

    parts = [
        "## 运营模式",
        "",
        f"### {om.label}",
        "",
        om.description or f"本项目采用 {om.label} 作为核心运营模式。",
    ]

    if om.applicable_conditions:
        parts.append("")
        parts.append("**适用条件：**")
        for cond in om.applicable_conditions:
            parts.append(f"- {cond}")

    if om.core_activities:
        parts.append("")
        parts.append("**核心作业活动：**")
        for act in om.core_activities[:8]:
            parts.append(f"- {act}")
        if len(om.core_activities) > 8:
            parts.append(f"- 其他 {len(om.core_activities) - 8} 项活动...")

    parts.append("")
    parts.append(f"**区域成本指数：** {om.region_cost_index:.2f}（华东 = 1.00）")
    parts.append(f"**行业附加系数：** {om.industry_overhead_factor:.2f}")

    return "\n".join(parts)


def _build_process_design_narrative(bs: BaseSolution) -> str:
    """Process design section narrative."""
    pd = bs.process_design

    parts = [
        "## 流程设计",
        "",
        f"**整体流程：** {pd.flow_diagram_label or '暂无完整流程定义'}",
        "",
    ]

    for stage in pd.stages:
        if not stage.enabled:
            continue

        sla_str = f"（SLA: {stage.sla}）" if stage.sla else ""

        stage_parts = [f"### {stage.stage_name} {sla_str}"]
        if stage.activities:
            for act in stage.activities[:5]:
                stage_parts.append(f"- {act}")
        if stage.handoff:
            stage_parts.append(f"**交接：** {stage.handoff}")
        if stage.kpis:
            kpis_str = " / ".join(stage.kpis)
            stage_parts.append(f"**KPI：** {kpis_str}")

        parts.append("")
        parts.extend(stage_parts)

    return "\n".join(parts)


def _build_labor_model_narrative(bs: BaseSolution) -> str:
    """Labor model section narrative."""
    lm = bs.labor_model

    parts = [
        "## 人工配置模型",
        "",
        f"**班次结构：** {lm.shift_structure}",
        f"**日运营时长：** {lm.working_hours_per_day:.0f} 小时",
        "",
        "**岗位配置（人）：**",
    ]

    for role_key, count in sorted(lm.headcount_by_role.items()):
        if count > 0:
            role_label = _role_label(role_key)
            parts.append(f"- {role_label}：{count} 人")

    parts.append("")
    parts.append(f"**单人月均成本：** ¥{lm.labor_cost_per_person_month:,.0f} 元/月")
    parts.append(f"**月均人工总成本：** ¥{lm.labor_cost_per_month:,.0f} 元/月")
    parts.append(f"**年人工成本：** ¥{lm.annual_labor_cost:,.0f} 元/年")
    parts.append(f"**区域调整系数：** {lm.labor_cost_adjustment_factor:.2f}（华东 = 1.00）")

    return "\n".join(parts)


def _build_kpi_framework_narrative(bs: BaseSolution) -> str:
    """KPI framework section narrative."""
    kf = bs.kpi_framework

    if not kf.operational_kpis:
        return ""

    parts = [
        "## KPI 框架",
        "",
        "**核心运营指标：**",
    ]

    for kpi in kf.operational_kpis:
        contractual_marker = " [合同承诺]" if kpi.is_contractual else ""
        sla_marker = " ⭐ SLA" if kpi.is_sla_candidate else ""
        parts.append(
            f"- **{kpi.name}**：目标 {kpi.target}（{kpi.unit}）"
            f"{contractual_marker}{sla_marker}"
        )

    return "\n".join(parts)


def _build_system_boundary_narrative(bs: BaseSolution) -> str:
    """System boundary section narrative."""
    sb = bs.system_boundary

    if not sb.included and not sb.excluded:
        return ""

    parts = ["## 系统边界", ""]

    if sb.included:
        parts.append("**方案范围内：**")
        for item in sb.included:
            parts.append(f"- {item}")

    if sb.excluded:
        parts.append("")
        parts.append("**明确排除：**")
        for item in sb.excluded:
            parts.append(f"- ~~{item}~~")

    if sb.integration_points:
        parts.append("")
        parts.append("**系统集成点：**")
        for point in sb.integration_points:
            parts.append(f"- {point}")

    return "\n".join(parts)


def _build_risk_profile_narrative(bs: BaseSolution) -> str:
    """Risk profile section narrative."""
    rp = bs.risk_profile

    if not rp.risks:
        return ""

    parts = ["## 风险档案", ""]

    for risk in rp.risks:
        severity_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(risk.severity, "⚪")
        parts.append(
            f"{severity_icon} **{risk.risk_id} [{risk.severity.upper()}]** {risk.description}"
        )
        if risk.mitigation:
            for mit in risk.mitigation:
                parts.append(f"   - 缓解：{mit}")

    return "\n".join(parts)


def _build_implementation_strategy_narrative(bs: BaseSolution) -> str:
    """Implementation strategy section narrative."""
    impl = bs.implementation_strategy

    parts = [
        "## 实施策略",
        "",
        f"**实施周期：** {impl.timeline_months} 个月（{impl.complexity.value if hasattr(impl.complexity, 'value') else impl.complexity} 复杂度）",
    ]

    if impl.go_live_target:
        parts.append(f"**目标上线日期：** {impl.go_live_target}")

    for phase in impl.phases:
        parts.append("")
        parts.append(f"### {phase.phase}: {phase.name}")
        parts.append(f"**重点：** {phase.focus}")
        parts.append(f"**周期：** {phase.duration_months} 个月")
        if phase.gate_criteria:
            parts.append("**门禁条件：**")
            for gate in phase.gate_criteria:
                parts.append(f"- {gate}")

    return "\n".join(parts)


def _role_label(role_key: str) -> str:
    return {
        "receiving_team": "收货团队",
        "picking_team": "拣选团队",
        "loading_team": "装车团队",
        "support_team": "支持团队",
        "va_team": "增值加工团队",
        "qc_team": "质检团队",
        "return_team": "退货处理团队",
        "it_support": "IT 支持",
    }.get(role_key, role_key)
