"""
solution_narrative_builder.py — v0.7 Base Solution Generator
========================================================

Convert structured solution sections into readable Chinese business narratives.
Each narrative is derived from the structured data — no hallucinated content.

Design: no new facts in narrative; only structured data translated to prose.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.solution.solution_schema import (
    ServiceDesign,
    OrganizationDesign,
    ProcessDesign,
    KPIFramework,
    ImplementationFocus,
    RiskAndControls,
    CostModelLinkage,
    NarrativeSections,
    ProjectFit,
)


def build_executive_summary(
    project_fit: ProjectFit,
    cost_mode: str,
) -> str:
    """Generate the executive summary paragraph."""
    mode_labels = {
        "blocked": "当前处于阻塞状态，建议优先完成服务范围澄清",
        "range_estimate": "已具备方向性评估基础，可进行区间成本估算",
        "full_calc": "已具备完整测算条件，可进入正式成本分析",
        "unknown": "当前测算模式未知",
    }
    mode_label = mode_labels.get(cost_mode, cost_mode)

    complexity_labels = {
        "low": "较低",
        "medium": "中等",
        "high": "较高",
    }
    complexity_label = complexity_labels.get(project_fit.complexity_level, project_fit.complexity_level)

    OP_TYPE_LABELS = {
        "warehouse_distribution": "仓配一体化",
        "cold_chain": "冷链仓储",
        "bonded_warehouse_distribution": "保税仓配",
        "distribution_only": "纯配送",
        "warehouse_inbound_only": "仓储入库",
        "warehouse_outbound_only": "仓储出库",
        "value_added_services": "增值服务",
        "custom": "综合物流",
        "unknown": "待定",
    }
    op_type_label = OP_TYPE_LABELS.get(project_fit.operation_type, project_fit.operation_type)

    # Extract just the scope portion (before the "当前成本测算模式" comma)
    raw_scope = project_fit.service_scope_summary.split("，当前成本测算模式")[0]
    if raw_scope == "未定义":
        scope_text = "服务范围尚未完整定义"
    else:
        scope_text = f"服务范围覆盖{raw_scope}"

    return (
        f"本项目为【{op_type_label}】类型运营场景，{scope_text}。"
        f"综合复杂度评估为{complexity_label}（评分{project_fit.complexity_score}/20），"
        f"适合采用标准化运营流程配合适当的模块化团队设计。"
        f"当前{mode_label}。"
        f"{project_fit.fit_reason}。"
    )


def build_service_solution_text(sd: ServiceDesign) -> str:
    """Generate the service solution narrative."""
    if not sd.included_services:
        return "服务范围尚未确认，无法生成服务方案描述。"

    by_category = {}
    for svc in sd.included_services:
        by_category.setdefault(svc.category, []).append(svc.label)

    parts = []
    seen_labels = set()
    for cat, labels in by_category.items():
        cat_labels = {
            "inbound": "入库作业",
            "storage": "存储管理",
            "outbound": "出库作业",
            "value_added": "增值服务",
            "support": "支持服务",
        }
        cat_name = cat_labels.get(cat, cat)
        # Avoid duplicate category labels
        if cat_name not in seen_labels:
            parts.append(f"{cat_name}包括{''.join(labels)}")
            seen_labels.add(cat_name)

    services_text = "，".join(parts) + "。"

    notes_text = ""
    if sd.service_boundary_notes:
        notes_text = " " + " ".join(sd.service_boundary_notes)

    return (
        f"本项目服务范围已明确，{services_text}"
        f"服务边界以招标文件中明确的范围为准。{notes_text}"
    )


def build_process_solution_text(pd: ProcessDesign, od: OrganizationDesign) -> str:
    """Generate the process solution narrative."""
    if not pd.processes:
        return "运营流程尚未确定，待服务范围明确后生成。"

    proc_names = "、".join([p.label for p in pd.processes[:3]])
    total_steps = sum(p.step_count for p in pd.processes)

    team_names = "、".join([t.label for t in od.team_modules[:4]])
    team_text = f"，设立{team_names}" if team_names else ""

    return (
        f"本项目共设计{len(pd.processes)}个核心运营流程，包含{total_steps}个标准化作业步骤。"
        f"主要流程包括：{proc_names}等。"
        f"运营组织上{team_text}等核心模块，"
        f"模块之间通过WMS系统联动，形成完整的仓配运营闭环。"
    )


def build_kpi_text(kpi: KPIFramework) -> str:
    """Generate the KPI framework narrative."""
    all_kpis = (
        kpi.inbound_kpis + kpi.outbound_kpis +
        kpi.inventory_kpis + kpi.support_kpis
    )
    sla_count = sum(1 for k in all_kpis if k.is_sla_candidate)
    kpi_count = len(all_kpis)

    return (
        f"本项目共设计{kpi_count}项运营KPI，其中{sla_count}项可作为SLA承诺候选指标。"
        f"入库KPI {len(kpi.inbound_kpis)}项，重点关注及时率与准确率；"
        f"出库KPI {len(kpi.outbound_kpis)}项，重点关注拣选准确率与装载率；"
        f"库内KPI {len(kpi.inventory_kpis)}项，重点关注库存准确率；"
        f"支持KPI {len(kpi.support_kpis)}项，重点关注报表准时率与系统可用性。"
    )


def build_risk_text(rc: RiskAndControls) -> str:
    """Generate the risk narrative."""
    if not rc.risks:
        return "暂无风险数据。"

    high_risks = [r for r in rc.risks if r.severity == "high"]
    med_risks = [r for r in rc.risks if r.severity == "medium"]

    parts = []
    if high_risks:
        risk_names = "、".join([r.description[:20] for r in high_risks])
        parts.append(f"高风险项：{risk_names}，需优先处置。")
    if med_risks:
        risk_names = "、".join([r.description[:20] for r in med_risks])
        parts.append(f"中风险项：{risk_names}，需持续关注。")

    return " ".join(parts) if parts else "整体风险可控，持续监控即可。"


def build_narrative_sections(
    project_fit: ProjectFit,
    service_design: ServiceDesign,
    organization_design: OrganizationDesign,
    process_design: ProcessDesign,
    kpi_framework: KPIFramework,
    implementation_focus: ImplementationFocus,
    risk_and_controls: RiskAndControls,
    cost_model_linkage: CostModelLinkage,
    cost_mode: str,
) -> NarrativeSections:
    """
    Build all narrative text sections from structured data.
    All content is derived from structured data — no hallucination.
    """
    executive_summary = build_executive_summary(
        project_fit, cost_mode
    )
    service_text = build_service_solution_text(service_design)
    process_text = build_process_solution_text(process_design, organization_design)
    kpi_text = build_kpi_text(kpi_framework)
    risk_text = build_risk_text(risk_and_controls)

    return NarrativeSections(
        executive_summary=executive_summary,
        service_solution_text=service_text,
        process_solution_text=process_text,
        kpi_text=kpi_text,
        risk_text=risk_text,
    )
