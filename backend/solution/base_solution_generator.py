"""
base_solution_generator.py — v0.8
=================================
Main orchestrator for Base Solution generation.

Flow:
    project_state (Input Contract v1)
        → adapt_project_state()          [adapter: fills structural fields]
        → Section Builders               [refine each sub-section]
        → Assemble BaseSolution
        → build_narrative()              [template-based v1]
        → BaseSolution (with narrative)

Usage:
    from backend.solution.base_solution_generator import generate_base_solution
    base_solution = generate_base_solution(project_state, project_id="abc123")
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from backend.schemas.base_solution_schema import (
    BaseSolution,
    ComplexityLevel,
    ConfidenceLevel,
    ImplementationPhase,
    ImplementationStrategy,
    InputFieldSource,
    OperationModeEnum,
    RiskItem,
    RiskProfile,
    ScaleTier,
    SystemBoundary,
)
from backend.solution.base_solution_input_adapter import (
    adapt_project_state,
    InputError,
    P2_DEFAULTS,
    REGION_COST_INDEX,
)
from backend.solution.section_builders import (
    build_operation_mode,
    build_process_design,
    build_labor_model,
    build_kpi_framework,
)
from backend.solution.narrative_builder import build_narrative


# ── Scale tier helpers (mirrors adapter) ─────────────────────────────────────

SCALE_TIER_RANGES = [
    (50_000, float("inf"), ScaleTier.XL),
    (20_000, 50_000,      ScaleTier.L),
    (5_000,  20_000,      ScaleTier.M),
    (1_000,  5_000,       ScaleTier.S),
    (0,      1_000,       ScaleTier.XS),
]

SCALE_TIER_COMPLEXITY = {
    ScaleTier.XS: ComplexityLevel.LOW,
    ScaleTier.S:  ComplexityLevel.LOW,
    ScaleTier.M:  ComplexityLevel.MEDIUM,
    ScaleTier.L:  ComplexityLevel.HIGH,
    ScaleTier.XL: ComplexityLevel.HIGH,
}

SHIFT_BY_SCALE = {
    ScaleTier.XS: "一班制（8小时/天）",
    ScaleTier.S:  "一班制为主（10小时/天）",
    ScaleTier.M:  "两班倒（白班 7:00-19:00 / 夜班 19:00-7:00）",
    ScaleTier.L:  "两班倒 + 周末值班（7天运营）",
    ScaleTier.XL: "三班倒（8小时×3班）或 24h 连续运营",
}


def _derive_scale_tier(warehouse_area: float | None) -> ScaleTier:
    if warehouse_area is None:
        return ScaleTier.M
    for lo, hi, tier in SCALE_TIER_RANGES:
        if lo <= warehouse_area < hi:
            return tier
    return ScaleTier.XL


# ── System boundary builder (inline, v1) ────────────────────────────────────

def _build_system_boundary(resolved: dict[str, Any]) -> SystemBoundary:
    service_scope = resolved.get("service_scope", {})
    included = ["仓库设施", "WMS 系统", "基础设施运维"]
    excluded = ["客户 ERP 系统对接（除非明确约定）", "退货货值理赔（按合同约定处理）"]
    integration_points = ["客户订单系统（API / EDI）"]

    if service_scope.get("support", {}).get("system_integration"):
        integration_points.append("客户 ERP / SAP（已约定）")
    else:
        integration_points.append("客户 ERP / SAP（待确认）")

    scope_parts = []
    for cat, services in service_scope.items():
        if isinstance(services, dict):
            enabled = [k for k, v in services.items() if v]
            if enabled:
                scope_parts.append(f"{cat}: {', '.join(enabled)}")

    return SystemBoundary(
        included=included,
        excluded=excluded,
        integration_points=integration_points,
        narrative="",
    )


# ── Risk profile builder (inline, v1) ──────────────────────────────────────

def _build_risk_profile(resolved: dict[str, Any]) -> RiskProfile:
    industry = resolved.get("industry", "GENERIC_3PL")
    region = resolved.get("region", "华东")
    labor_cost_level = resolved.get("labor_cost_level", "中")
    risks: list[RiskItem] = []

    if region in ("华东", "华南"):
        risks.append(RiskItem(
            risk_id="R-01",
            category="labor_availability",
            description=f"{region}地区旺季可能出现临时工招募困难，影响峰值期间运营",
            severity="medium",
            likelihood="medium",
            mitigation=["提前与劳务公司签订框架协议", "建立灵活用工池"],
        ))

    if labor_cost_level == "高":
        risks.append(RiskItem(
            risk_id="R-02",
            category="cost_control",
            description="高人工成本地区，人力成本超支风险较高",
            severity="high",
            likelihood="high",
            mitigation=["引入局部自动化降低对人工的依赖", "优化排班减少无效工时"],
        ))

    if industry == "AUTOMOTIVE":
        risks.append(RiskItem(
            risk_id="R-AUTO-01",
            category="line_stop_risk",
            description="汽车产线 JIT/JIS 供料要求高，缺料可直接导致停线",
            severity="high",
            likelihood="medium",
            mitigation=["建立双仓安全库存", "配置缺料应急响应流程", "实时监控库存水位"],
        ))
        risks.append(RiskItem(
            risk_id="R-AUTO-02",
            category="tooling_management",
            description="器具（周转箱/料架）流转丢失或损坏影响产线节拍",
            severity="medium",
            likelihood="medium",
            mitigation=["器具条码追踪", "建立器具回收考核机制", "配置备用器具池"],
        ))

    if industry == "ELECTRONICS":
        risks.append(RiskItem(
            risk_id="R-ELEC-01",
            category="high_value_risk",
            description="高价值电子元器件丢失/损坏赔偿金额高",
            severity="high",
            likelihood="low",
            mitigation=["全程视频监控", "高价值品专区管理", "全程条码追溯"],
        ))

    risks.append(RiskItem(
        risk_id="R-05",
        category="process_handoff",
        description="跨团队交接环节可能出现信息丢失或延误",
        severity="medium",
        likelihood="low",
        mitigation=["明确交接标准和记录节点", "通过 WMS 实时跟踪作业状态"],
    ))

    return RiskProfile(risks=risks, narrative="")


# ── Implementation strategy builder (inline, v1) ────────────────────────────

def _build_implementation_strategy(
    resolved: dict[str, Any],
    scale_tier: ScaleTier,
) -> ImplementationStrategy:
    contract_years = resolved.get("contract_years", 3) or 3
    go_live_date = resolved.get("go_live_date")

    timeline_by_tier = {
        ScaleTier.XS: 3, ScaleTier.S: 6, ScaleTier.M: 9,
        ScaleTier.L: 12, ScaleTier.XL: 18,
    }
    timeline_months = min(
        timeline_by_tier.get(scale_tier, 9),
        max(6, int(contract_years) * 12 - 2),
    )

    p1 = min(3, max(1, timeline_months // 3))
    p2 = min(3, max(1, timeline_months // 3))
    p3 = max(1, timeline_months - p1 - p2)

    phases = [
        ImplementationPhase(
            phase="Phase 1",
            name="基础准备",
            focus="团队组建 + 流程确认 + 设施验收",
            key_actions=["运营团队招聘与培训", "WMS 系统部署", "设备入场安装", "流程 SOP 编制"],
            duration_months=p1,
            gate_criteria=["团队到岗率 ≥ 90%", "WMS 系统上线", "设备调试完成"],
        ),
        ImplementationPhase(
            phase="Phase 2",
            name="试运营",
            focus="小规模试运行 + 问题修复",
            key_actions=["降负荷试运营（30% 容量）", "KPI 基线测定", "异常流程优化"],
            duration_months=p2,
            gate_criteria=["试运营 30 天零重大事故", "主要 KPI 达到目标 80%"],
        ),
        ImplementationPhase(
            phase="Phase 3",
            name="正式运营",
            focus="全容量正式运营 + 持续优化",
            key_actions=["全容量运营", "KPI 正式考核", "季度复盘与优化"],
            duration_months=p3,
            gate_criteria=["全流程稳定运行 30 天", "所有 SLA 指标达标"],
        ),
    ]

    return ImplementationStrategy(
        phases=phases,
        timeline_months=timeline_months,
        complexity=SCALE_TIER_COMPLEXITY.get(scale_tier, ComplexityLevel.MEDIUM),
        go_live_target=go_live_date if go_live_date else None,
        narrative="",
    )


# ── Main entry point ────────────────────────────────────────────────────────

def generate_base_solution(
    project_state: dict[str, Any],
    *,
    project_id: Optional[str] = None,
    narrative: bool = True,
) -> BaseSolution:
    """
    Generate a BaseSolution from a project_state dict.

    Parameters
    ----------
    project_state : dict
        Must conform to project_state_input_contract_v1.md.
        P0 fields must be present (raises InputError if missing).
    project_id : str, optional
        Pipeline/project ID for linkage.
    narrative : bool
        If True, generates narrative from structured fields (template-based, v1).

    Returns
    -------
    BaseSolution
        Fully populated with all sub-sections and narrative.

    Raises
    ------
    InputError
        If P0 fields are missing from project_state.
    """
    if not project_state or not any(project_state.values()):
        return _build_empty_solution(project_id)

    # Step 1: Adapter — resolve fields, apply P2 defaults, compute confidence
    base = adapt_project_state(project_state, project_id=project_id)
    resolved = _get_resolved_fields(project_state)

    # Step 2: Derive scale tier
    scale_tier = _derive_scale_tier(resolved.get("warehouse_area"))

    # Step 3: Section builders (override adapter's defaults with richer data)
    op_mode = build_operation_mode(
        industry=resolved.get("industry", "电商"),
        service_scope=resolved.get("service_scope", {}),
        warehouse_area=resolved.get("warehouse_area") or 0,
        region=resolved.get("region", "华东"),
        dc_count=int(resolved.get("dc_count") or 1),
        scale_tier=scale_tier,
        automation_expectation=resolved.get("automation_expectation", "中"),
    )

    process_design = build_process_design(
        service_scope=resolved.get("service_scope", {}),
        region=resolved.get("region", "华东"),
        industry=resolved.get("industry", "电商"),
    )

    labor_model = build_labor_model(
        warehouse_area=resolved.get("warehouse_area") or 0,
        daily_orders=resolved.get("daily_orders") or 0,
        service_scope=resolved.get("service_scope", {}),
        region=resolved.get("region", "华东"),
        labor_cost_level=resolved.get("labor_cost_level", "中"),
        scale_tier=scale_tier,
        industry=resolved.get("industry", "GENERIC_3PL"),
    )

    kpi_framework = build_kpi_framework(
        service_scope=resolved.get("service_scope", {}),
        kpi_targets=resolved.get("kpi_targets"),
        industry=resolved.get("industry", "GENERIC_3PL"),
        region=resolved.get("region", "华东"),
        labor_cost_level=resolved.get("labor_cost_level", "中"),
    )

    # Step 4: Inline builders (system boundary, risk, implementation)
    system_boundary = _build_system_boundary(resolved)
    risk_profile = _build_risk_profile(resolved)
    implementation_strategy = _build_implementation_strategy(resolved, scale_tier)

    # Step 5: Assemble — build new BaseSolution (overrides adapter defaults)
    confidence = base.confidence
    confidence_factors = base.confidence_factors
    defaulted_p2 = base.defaulted_p2_fields

    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    pid_part = f"{project_id[:8]}" if project_id else "unknown"

    bs = BaseSolution(
        solution_id=f"BS-{pid_part}-{ts}",
        solution_type="base",
        version="1.0",
        project_id=project_id,
        operation_mode=op_mode,
        process_design=process_design,
        labor_model=labor_model,
        kpi_framework=kpi_framework,
        system_boundary=system_boundary,
        risk_profile=risk_profile,
        implementation_strategy=implementation_strategy,
        narrative="",  # filled below
        confidence=confidence,
        confidence_factors=confidence_factors,
        input_field_sources=list(base.input_field_sources),
        missing_p0_fields=base.missing_p0_fields or [],
        defaulted_p2_fields=defaulted_p2,
        generated_at=datetime.now(timezone.utc).isoformat(),
        generator_version="0.8",
    )

    # Step 6: Narrative (template-based, v1)
    if narrative:
        bs.narrative = build_narrative(bs)

    return bs


def _get_resolved_fields(project_state: dict[str, Any]) -> dict[str, Any]:
    """Resolve project_state with P2 defaults applied (mirrors adapter logic)."""
    resolved = dict(project_state)
    for key, default in P2_DEFAULTS.items():
        if resolved.get(key) is None:
            resolved[key] = default
    return resolved


def _build_empty_solution(project_id: Optional[str]) -> BaseSolution:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    pid_part = f"{project_id[:8]}" if project_id else "unknown"
    return BaseSolution(
        solution_id=f"BS-{pid_part}-{ts}",
        solution_type="base",
        version="1.0",
        project_id=project_id,
        operation_mode=build_operation_mode(
            industry="电商",
            service_scope={},
            warehouse_area=0,
            region="华东",
            dc_count=1,
            scale_tier=ScaleTier.M,
        ),
        process_design=build_process_design(service_scope={}),
        labor_model=build_labor_model(
            warehouse_area=0,
            daily_orders=0,
            service_scope={},
            region="华东",
            labor_cost_level="中",
            scale_tier=ScaleTier.M,
        ),
        kpi_framework=build_kpi_framework(service_scope={}),
        system_boundary=SystemBoundary(included=[], excluded=[], integration_points=[]),
        risk_profile=RiskProfile(risks=[]),
        implementation_strategy=ImplementationStrategy(
            phases=[], timeline_months=0, complexity=ComplexityLevel.UNKNOWN,
        ),
        narrative="",
        confidence=ConfidenceLevel.UNKNOWN,
        confidence_factors={"input": "empty project_state"},
        input_field_sources=[],
        generated_at=datetime.now(timezone.utc).isoformat(),
        generator_version="0.8",
    )


def serialize_solution(solution: BaseSolution) -> dict:
    """Serialize a BaseSolution to a dict (for JSON storage / API responses)."""
    return solution.model_dump(mode="json")
