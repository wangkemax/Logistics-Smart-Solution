"""
solution_section_builders.py — v0.7 Base Solution Generator
======================================================

Structured section builders for the 8 base solution sections.

Design principles:
  - Each builder receives `context` dict only (no side effects)
  - Output is a Pydantic model matching the section schema
  - No free-form text generation — all content derived from context
  - Section structure is stable; narrative text comes from a separate pass
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.solution.solution_schema import (
    ProjectFit,
    ServiceDesign,
    IncludedService,
    OrganizationDesign,
    RoleSummary,
    ProcessDesign,
    ProcessDesignItem,
    KPIFramework,
    KPIItem,
    ImplementationFocus,
    ImplementationPhase,
    RiskAndControls,
    RiskItem,
    CostModelLinkage,
)
from backend.services.tender_schema import SERVICE_MATRIX


# =============================================================================
# Utility helpers
# =============================================================================

def _label_for_service(cat_key: str, svc_key: str) -> str:
    """Get the Chinese label for a service from SERVICE_MATRIX."""
    cat = SERVICE_MATRIX.get(cat_key, {})
    svc = cat.get("services", {}).get(svc_key, {})
    return svc.get("label", svc_key)


def _get_all_services_flat(scope: dict) -> list[tuple[str, str, bool]]:
    """Return flat list of (cat, svc_key, selected) from service_scope."""
    result = []
    if not isinstance(scope, dict):
        return result
    for cat, cat_info in scope.items():
        if isinstance(cat_info, dict):
            for svc_key, selected in cat_info.items():
                if selected:
                    result.append((cat, svc_key, bool(selected)))
    return result


# =============================================================================
# Section 1: Project Fit
# =============================================================================

def build_project_fit(context: dict) -> ProjectFit:
    """Determine how this project fits known operation patterns."""
    op_type = context.get("operation_type", "unknown")
    complexity_level = context.get("complexity_level", "low")
    complexity_score = context.get("complexity_score", 0)
    service_scope = context.get("service_scope", {})
    cost_mode = context.get("cost_mode", "unknown")

    # Summarize active service categories
    active_cats = [k for k, v in service_scope.items() if isinstance(v, dict) and any(v.values())]
    cat_labels = {
        "inbound": "入库作业",
        "storage": "存储管理",
        "outbound": "出库作业",
        "value_added": "增值服务",
        "support": "支持服务",
    }
    scope_summary = "、".join([cat_labels.get(c, c) for c in active_cats]) or "未定义"

    # Fit reason
    fit_reasons = {
        "warehouse_distribution": "同时具备入库、存储、出库全链路服务，属于典型仓配一体化运营",
        "cold_chain": "包含温度控制存储需求，需冷链专业管理能力",
        "bonded_warehouse_distribution": "含保税仓储业务，需海关监管合规能力",
        "distribution_only": "主要提供出库配送服务，仓储管理相对简单",
        "warehouse_inbound_only": "以入库作业为主，出库作业较少",
        "warehouse_outbound_only": "以出库为主，入库作业较少",
        "value_added_services": "以增值服务为核心，仓储基础服务为辅",
        "custom": "服务组合较为多样，需根据实际配置灵活设计",
        "unknown": "服务范围尚未完整定义，待补录后可重新评估",
    }
    fit_reason = fit_reasons.get(op_type, "服务范围已明确，可按标准仓配运营模式设计")

    return ProjectFit(
        operation_type=op_type,
        complexity_level=complexity_level,
        complexity_score=complexity_score,
        service_scope_summary=scope_summary,
        fit_reason=fit_reason,
    )


# =============================================================================
# Section 2: Service Design
# =============================================================================

def build_service_design(context: dict) -> ServiceDesign:
    """Build the service scope design section."""
    service_scope = context.get("service_scope", {})
    confirmed_keys = set()
    excluded_keys = []

    all_services = _get_all_services_flat(service_scope)
    included_services = []

    for cat, svc_key, selected in all_services:
        label = _label_for_service(cat, svc_key)
        confirmed_keys.add(svc_key)
        included_services.append(IncludedService(
            category=cat,
            service_key=svc_key,
            label=label,
            confirmed=True,
        ))

    # Build excluded/unconfirmed list from SERVICE_MATRIX
    for cat, cat_info in SERVICE_MATRIX.items():
        for svc_key in cat_info.get("services", {}):
            if svc_key not in confirmed_keys:
                excluded_keys.append(f"{cat_info.get('label', cat)}.{_label_for_service(cat, svc_key)}")

    # Service boundary notes
    notes = []
    if context.get("cost_mode") in ("blocked",):
        notes.append("⚠️ 服务范围尚未完整确认，方案基于当前已知服务设计，建议尽快完成澄清")
    if not included_services:
        notes.append("⚠️ 无已确认服务，实际方案待服务范围明确后生成")
    if context.get("complexity_level") == "high":
        notes.append(f"本项目服务复杂度较高（评分{context.get('complexity_score', 0)}/20），增值服务模块需重点关注")

    # Simple narrative
    svc_count = len(included_services)
    cat_labels_map = {
        "inbound": "入库作业", "storage": "存储管理",
        "outbound": "出库作业", "value_added": "增值服务", "support": "支持服务",
    }
    unique_cats = []
    seen_cats = set()
    for s in included_services:
        if s.category not in seen_cats:
            unique_cats.append(cat_labels_map.get(s.category, s.category))
            seen_cats.add(s.category)
    if unique_cats:
        cat_labels_text = "、".join(unique_cats)
        scope_part = f"覆盖{cat_labels_text}等类别。"
    else:
        scope_part = "暂无已确认服务。"
    narrative = (
        f"本项目已确认包含 {svc_count} 项具体服务，{scope_part}"
        f"{' '.join(notes) if notes else '服务边界清晰，可进入方案详细设计。'}"
    )

    return ServiceDesign(
        included_services=included_services,
        excluded_or_unconfirmed=excluded_keys[:20],  # Cap at 20
        service_boundary_notes=notes,
        narrative=narrative,
    )


# =============================================================================
# Section 3: Organization Design
# =============================================================================

MODULE_LABELS = {
    "receiving_team": "收货组",
    "putaway_team": "上架组",
    "picking_team": "拣选组",
    "packing_team": "包装组",
    "loading_team": "装车队",
    "return_processing_team": "退货处理组",
    "inventory_control_team": "库存管控组",
}

MODULE_RESPONSIBILITIES = {
    "receiving_team": ["车辆到达登记", "卸货作业", "数量验收", "单据归档"],
    "putaway_team": ["库位分配", "上架执行", "库位确认"],
    "picking_team": ["拣货单领取", "拣选执行", "拣货确认"],
    "packing_team": ["包装作业", "贴标复核", "包装确认"],
    "loading_team": ["集货区集结", "装车执行", "发车确认"],
    "return_processing_team": ["退货接收", "退货质检", "分类处理", "退款处理"],
    "inventory_control_team": ["循环盘点", "库存报表", "补货管理", "FIFO检查"],
}

MODULE_HANDOFFS = {
    "receiving_team": ["上架组"],
    "putaway_team": ["拣选组", "库存管控组"],
    "picking_team": ["包装组"],
    "packing_team": ["装车队"],
    "loading_team": [],
    "return_processing_team": ["库存管控组"],
    "inventory_control_team": ["收货组", "拣选组"],
}


def build_organization_design(context: dict) -> OrganizationDesign:
    """Build the organization and team module design section."""
    labor_modules = context.get("labor_modules", {})
    if isinstance(labor_modules, dict):
        active = {k: v for k, v in labor_modules.items() if v}
    else:
        active = {}

    team_modules = []
    for mod_key, is_active in active.items():
        label = MODULE_LABELS.get(mod_key, mod_key)
        team_modules.append(RoleSummary(
            module_key=mod_key,
            label=label,
            primary_responsibilities=MODULE_RESPONSIBILITIES.get(mod_key, []),
            handoff_to=MODULE_HANDOFFS.get(mod_key, []),
        ))

    # Staffing logic
    mod_count = len(team_modules)
    staffing_logic = (
        f"本项目建议设立 {mod_count} 个核心作业团队模块，"
        f"覆盖收货、上架、拣选、包装、装车及库控管理等主要职能。"
        f"各模块之间按物流动_flow衔接，形成完整的仓配运营闭环。"
    )

    # Narrative
    module_names = "、".join([t.label for t in team_modules]) or "待设计"
    narrative = (
        f"建议设立 {mod_count} 个团队模块：{module_names}。"
        f"模块之间通过标准化交接单据和WMS系统联动，确保信息流与物流同步。"
        f"{staffing_logic}"
    )

    return OrganizationDesign(
        team_modules=team_modules,
        staffing_logic=staffing_logic,
        narrative=narrative,
    )


# =============================================================================
# Section 4: Process Design
# =============================================================================

PROCESS_KPI_MAP = {
    "receiving_process": ["卸货效率 (托/小时)", "验收准确率 (%)", "上架及时率 (%)", "月台占用率 (%)"],
    "outbound_process": ["拣选效率 (行/小时)", "包装准确率 (%)", "装载率 (%)", "日出库单量", "订单履约率 (%)"],
    "storage_management": ["库存准确率 (%)", "盘点差异率 (%)", "库位利用率 (%)", "FIFO合规率 (%)"],
    "return_process": ["退货处理时效 (天)", "退货原因分类准确率 (%)", "退货成本占比 (%)"],
    "va_process": ["VA作业效率 (套/小时)", "VA准确率 (%)", "VA品损耗率 (%)"],
    "temperature_control": ["温控合规率 (%)", "设备正常运行时间 (%)", "温控预警响应时间 (分钟)"],
    "support_process": ["报表准时率 (%)", "系统可用率 (%)", "数据准确率 (%)"],
}

PROCESS_CONTROL_POINTS = {
    "receiving_process": ["卸货完成时间节点", "验收签字确认", "上架库位扫描确认"],
    "outbound_process": ["拣货单生成时间", "包装完成率", "装载率达标"],
    "storage_management": ["每日巡仓记录", "盘点差异复盘", "FIFO执行检查"],
    "return_process": ["退货接收登记", "质检结果录入", "退款/扣款审批"],
    "va_process": ["VA订单释放", "组装/换装完成确认", "重新贴标核查"],
    "temperature_control": ["温湿度记录每2小时", "超温预警响应", "设备维护记录"],
    "support_process": ["报表生成截止时间", "系统接口调用日志", "数据备份验证"],
}


def build_process_design(context: dict) -> ProcessDesign:
    """Build the process design section from process_modules."""
    process_modules = context.get("process_modules", {})
    if not isinstance(process_modules, dict):
        process_modules = {}

    processes = []
    for proc_key, proc_info in process_modules.items():
        steps = proc_info.get("steps", [])
        step_count = proc_info.get("step_count", len(steps))

        processes.append(ProcessDesignItem(
            process_key=proc_key,
            label=proc_info.get("label", proc_key),
            description=proc_info.get("description", ""),
            step_count=step_count,
            key_control_points=PROCESS_CONTROL_POINTS.get(proc_key, []),
            handoff_points=_extract_handoffs(steps),
            kpis=PROCESS_KPI_MAP.get(proc_key, []),
            narrative="",
        ))

    proc_count = len(processes)
    total_steps = sum(p.step_count for p in processes)
    overall_narrative = (
        f"本项目共设计 {proc_count} 个核心运营流程，包含 {total_steps} 个标准化作业步骤。"
        f"各流程关键控制点已标注，KPI已对应设置，确保运营过程可追踪、可量化。"
    )

    return ProcessDesign(
        processes=processes,
        overall_process_narrative=overall_narrative,
    )


def _extract_handoffs(steps: list) -> list[str]:
    """Extract handoff points between roles from step list."""
    if not steps:
        return []
    # Last step of one role often hands off to first step of next
    handoffs = []
    prev_role = None
    for step in steps:
        role = step.get("role", "")
        if prev_role and role and role != prev_role:
            handoffs.append(f"{prev_role} → {role}")
        prev_role = role
    return handoffs


# =============================================================================
# Section 5: KPI Framework
# =============================================================================

DEFAULT_KPI_TARGETS = {
    "入库及时率": "≥98%",
    "入库准确率": "≥99.5%",
    "拣选准确率": "≥99.8%",
    "包装准确率": "≥99.5%",
    "装载率": "≥85%",
    "发运及时率": "≥98%",
    "库存准确率": "≥99.5%",
    "盘点差异率": "≤0.1%",
    "退货处理时效": "≤3个工作日",
    "报表准时率": "≥99%",
    "系统可用率": "≥99.5%",
}


def build_kpi_framework(context: dict) -> KPIFramework:
    """Build the KPI framework from process_modules and cost_mode."""
    process_modules = context.get("process_modules", {})
    cost_mode = context.get("cost_mode", "unknown")

    # Collect KPIs from process_modules
    inbound_kpis = []
    outbound_kpis = []
    inventory_kpis = []
    support_kpis = []

    proc_to_bucket = {
        "receiving_process": inbound_kpis,
        "outbound_process": outbound_kpis,
        "storage_management": inventory_kpis,
        "return_process": outbound_kpis,
        "va_process": outbound_kpis,
        "temperature_control": inventory_kpis,
        "support_process": support_kpis,
    }

    for proc_key, proc_info in process_modules.items():
        bucket = proc_to_bucket.get(proc_key, support_kpis)
        for kpi_name in proc_info.get("kpis", []):
            clean_name = kpi_name.replace(" (%)", "").replace(" (托/小时)", "")
            target = DEFAULT_KPI_TARGETS.get(clean_name, "待定")
            bucket.append(KPIItem(
                name=clean_name,
                target=target,
                measurement_method="WMS/系统自动统计",
                is_sla_candidate=(cost_mode in ("range_estimate", "full_calc")),
            ))

    # Ensure baseline KPIs are present
    if not inbound_kpis:
        inbound_kpis.extend([
            KPIItem(name="入库及时率", target="≥98%", measurement_method="WMS记录", is_sla_candidate=False),
            KPIItem(name="入库准确率", target="≥99.5%", measurement_method="WMS复核", is_sla_candidate=False),
        ])

    if not outbound_kpis:
        outbound_kpis.extend([
            KPIItem(name="拣选准确率", target="≥99.8%", measurement_method="WMS统计", is_sla_candidate=False),
            KPIItem(name="发运及时率", target="≥98%", measurement_method="TMS记录", is_sla_candidate=False),
        ])

    if not inventory_kpis:
        inventory_kpis.extend([
            KPIItem(name="库存准确率", target="≥99.5%", measurement_method="循环盘点", is_sla_candidate=False),
        ])

    if not support_kpis:
        support_kpis.extend([
            KPIItem(name="报表准时率", target="≥99%", measurement_method="系统日志", is_sla_candidate=False),
            KPIItem(name="系统可用率", target="≥99.5%", measurement_method="监控平台", is_sla_candidate=False),
        ])

    sla_count = sum(
        1 for kpis in [inbound_kpis, outbound_kpis, inventory_kpis, support_kpis]
        for k in kpis if k.is_sla_candidate
    )

    narrative = (
        f"本项目共设计 {len(inbound_kpis) + len(outbound_kpis) + len(inventory_kpis) + len(support_kpis)} 项运营KPI，"
        f"其中 {sla_count} 项可作为SLA承诺候选指标。"
        f"{'当前为区间估算模式，建议完成P1字段补录后收紧KPI目标值。' if cost_mode == 'range_estimate' else ''}"
    )

    return KPIFramework(
        inbound_kpis=inbound_kpis,
        outbound_kpis=outbound_kpis,
        inventory_kpis=inventory_kpis,
        support_kpis=support_kpis,
        narrative=narrative,
    )


# =============================================================================
# Section 6: Implementation Focus
# =============================================================================

def build_implementation_focus(context: dict) -> ImplementationFocus:
    """Build the implementation phases section."""
    complexity = context.get("complexity_level", "medium")
    process_count = len(context.get("process_modules", {}))
    team_count = len([k for k, v in context.get("labor_modules", {}).items() if v])

    phases = []

    if complexity in ("low", "medium"):
        phases.append(ImplementationPhase(
            phase="Phase 1",
            name="项目启动与系统切换",
            focus="完成WMS/OMS系统切换，服务范围确认，团队到位",
            key_actions=[
                "完成服务范围确认与SLA签订",
                "WMS系统配置与库位映射",
                "团队组建与培训",
                "首批货物入库验证",
            ],
            duration_months=2,
        ))
        phases.append(ImplementationPhase(
            phase="Phase 2",
            name="稳定运营",
            focus="日常运营稳定，KPI达标，异常处理机制建立",
            key_actions=[
                "日均处理量提升至目标水平",
                "KPI体系建立并月报",
                "退货处理流程跑通",
                "库内优化（库位、流程)",
            ],
            duration_months=4,
        ))
        phases.append(ImplementationPhase(
            phase="Phase 3",
            name="效率优化",
            focus="自动化导入，效率提升，成本优化",
            key_actions=[
                "自动化设备导入评估",
                "拣选效率优化",
                "库存准确率提升至99.9%+",
                "年度成本复盘",
            ],
            duration_months=6,
        ))
    else:  # high complexity
        phases.append(ImplementationPhase(
            phase="Phase 1",
            name="基础运营启动",
            focus="核心流程上线，服务范围逐步扩展",
            key_actions=[
                "确认入库+出库核心流程先行上线",
                "增值服务模块延后3个月启动",
                "WMS/OMS双系统并行",
                "团队分批到位",
            ],
            duration_months=3,
        ))
        phases.append(ImplementationPhase(
            phase="Phase 2",
            name="全流程稳定运行",
            focus="全部服务模块上线，KPI体系完善",
            key_actions=[
                "增值服务模块接入",
                "温控/退货等特殊流程跑通",
                "KPI全面监控",
                "跨部门协同机制建立",
            ],
            duration_months=5,
        ))
        phases.append(ImplementationPhase(
            phase="Phase 3",
            name="精细化运营",
            focus="自动化升级，效率行业领先",
            key_actions=[
                "自动化设备导入",
                "数字化运营平台建设",
                "ROI复盘与方案迭代",
                "行业benchmark对比",
            ],
            duration_months=8,
        ))

    total_months = sum(p.duration_months for p in phases)
    narrative = (
        f"本项目实施预计分 {len(phases)} 个阶段，总周期约 {total_months} 个月。"
        f"Phase 1 重点在于启动与切换，Phase 2 追求稳定运行，"
        f"Phase 3 侧重效率优化与自动化升级。"
    )

    return ImplementationFocus(
        phases=phases,
        narrative=narrative,
    )


# =============================================================================
# Section 7: Risk and Controls
# =============================================================================

def build_risk_and_controls(context: dict) -> RiskAndControls:
    """Build the risk and controls section."""
    cost_mode = context.get("cost_mode", "unknown")
    complexity = context.get("complexity_level", "low")
    assumptions_count = context.get("assumed_field_count", 0)
    service_scope = context.get("service_scope", {})
    active_cats = [k for k, v in service_scope.items() if isinstance(v, dict) and any(v.values())]

    risks = []
    risk_id = 1

    # Risk 1: Service boundary
    if not service_scope or len(active_cats) < 3:
        risks.append(RiskItem(
            risk_id=f"R-{risk_id:02d}",
            category="服务边界",
            description="服务范围尚未完整定义，方案设计可能存在遗漏",
            severity="high",
            control_measure="在进入正式测算前完成服务范围澄清",
            mitigation_action="参照Clarification Workspace补录service_scope",
        ))
        risk_id += 1

    # Risk 2: Data completeness
    if assumptions_count > 3:
        risks.append(RiskItem(
            risk_id=f"R-{risk_id:02d}",
            category="数据完整",
            description=f"当前有 {assumptions_count} 个字段采用业务假设，方案结论为区间估算",
            severity="medium",
            control_measure="补充P1字段以收窄假设范围",
            mitigation_action="参照Clarification Workspace补录缺失字段",
        ))
        risk_id += 1

    # Risk 3: Cost mode
    if cost_mode == "blocked":
        risks.append(RiskItem(
            risk_id=f"R-{risk_id:02d}",
            category="成本边界",
            description="当前处于blocked状态，无法进行任何形式成本测算",
            severity="high",
            control_measure="优先补录P0缺失字段",
            mitigation_action="在Clarification Workspace完成P0补录",
        ))
        risk_id += 1

    # Risk 4: High complexity
    if complexity == "high":
        risks.append(RiskItem(
            risk_id=f"R-{risk_id:02d}",
            category="流程衔接",
            description="服务复杂度较高，多流程并行时交接风险增加",
            severity="medium",
            control_measure="建立标准交接SOP，设置WMS交接确认节点",
            mitigation_action="Phase 1 优先跑通核心两流程，再扩展",
        ))
        risk_id += 1

    # Risk 5: Return handling
    if context.get("labor_modules", {}).get("return_processing_team"):
        risks.append(RiskItem(
            risk_id=f"R-{risk_id:02d}",
            category="人员组织",
            description="退货处理团队需专业培训，初期损耗率可能偏高",
            severity="medium",
            control_measure="设置退货处理专项SLA，独立KPI考核",
            mitigation_action="Phase 1 前两个月退货处理单独统计",
        ))
        risk_id += 1

    # Risk 6: KPI calibration
    if cost_mode != "full_calc":
        risks.append(RiskItem(
            risk_id=f"R-{risk_id:02d}",
            category="KPI口径",
            description="当前方案KPI目标值基于行业均值估算，非项目实测数据",
            severity="low",
            control_measure="Phase 2 稳定运行后根据实际数据调整KPI目标",
            mitigation_action="Phase 2 结束后进行KPI目标复盘",
        ))
        risk_id += 1

    # Fallback
    if not risks:
        risks.append(RiskItem(
            risk_id=f"R-{risk_id:02d}",
            category="整体评估",
            description="当前项目信息完整度较好，暂无高优先级风险",
            severity="low",
            control_measure="持续监控关键KPI，按月复盘",
            mitigation_action="月度运营复盘机制",
        ))

    narrative = (
        f"本方案共识别 {len(risks)} 项风险，其中 "
        f"{sum(1 for r in risks if r.severity == 'high')} 项高风险，"
        f"{sum(1 for r in risks if r.severity == 'medium')} 项中风险，"
        f"{sum(1 for r in risks if r.severity == 'low')} 项低风险。"
        f"{'建议优先解决高风险项后再进入正式测算。' if any(r.severity == 'high' for r in risks) else ''}"
    )

    return RiskAndControls(
        risks=risks,
        narrative=narrative,
    )


# =============================================================================
# Section 8: Cost Model Linkage
# =============================================================================

def build_cost_model_linkage(context: dict) -> CostModelLinkage:
    """Build the cost model linkage section."""
    cost_mode = context.get("cost_mode", "unknown")
    mode_reason = context.get("mode_reason", "")
    blocking_reasons = context.get("blocking_reasons", [])
    assumed_inputs = context.get("assumed_inputs", {})
    p0_summary = context.get("p0_summary", {})
    p1_summary = context.get("p1_summary", {})

    missing_p0 = p0_summary.get("missing", 0) if p0_summary else 0
    missing_p1 = p1_summary.get("missing", 0) if p1_summary else 0

    assumptions_list = [
        {
            "field": k,
            "fallback_value": v.get("fallback_value"),
            "assumption_rule": v.get("assumption_rule", "未提供"),
        }
        for k, v in assumed_inputs.items()
    ]

    mode_explanations = {
        "blocked": "当前存在P0关键字段缺失，系统无法进行任何形式的成本测算。方案结论仅供方向性参考。",
        "range_estimate": "P0字段已完整，但P1字段存在缺失。成本结论为区间估算，适用方案方向性评估。",
        "full_calc": "所有关键字段已确认。可进入正式成本测算，方案可与精确ROI联动。",
    }

    mode_explanation = mode_explanations.get(cost_mode, "成本测算模式未知")
    if mode_reason and mode_reason != mode_explanation:
        mode_explanation = f"{mode_explanation} 原因：{mode_reason}"

    missing_for_full = []
    if missing_p0 > 0:
        missing_for_full.append(f"P0字段缺失 {missing_p0} 个，需优先补录")
    if missing_p1 > 0:
        missing_for_full.append(f"P1字段缺失 {missing_p1} 个，补录后可进入full_calc")

    boundary_texts = {
        "blocked": "方案基于服务范围和组织模块设计，无成本数据支撑，结论仅供内部讨论。",
        "range_estimate": f"方案基于 {len(assumptions_list)} 项业务假设，输出为区间范围。建议在P1字段补录后将结论收紧。",
        "full_calc": "方案与成本测算联动，可直接用于投标报价决策支持。",
    }
    boundary_summary = boundary_texts.get(cost_mode, "")

    # Don't say "补录后可进入full_calc" when already in full_calc
    visible_missing = [m for m in missing_for_full if cost_mode != "full_calc" or "P0" in m]
    narrative = (
        f"当前成本测算处于「{cost_mode}」模式。{mode_explanation} "
        f"{boundary_summary}"
        f"{' '.join(visible_missing) if visible_missing else '所有关键字段已确认。'}"
    )

    return CostModelLinkage(
        current_mode=cost_mode,
        mode_explanation=mode_explanation,
        cost_boundary_summary=boundary_summary,
        missing_for_full_calc=missing_for_full,
        assumptions_used=assumptions_list,
        narrative=narrative,
    )
