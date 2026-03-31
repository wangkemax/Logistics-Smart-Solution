"""
base_solution_input_adapter.py — v0.8 Base Solution Input Adapter
==================================================================

Pure transformation layer: project_state (Input Contract v1) → BaseSolution schema.

This module contains ZERO LLM calls — it only maps input fields to schema fields.
Solution generation (LLM calls) lives in base_solution_generator.py.

Adapter responsibility:
  1. Validate that required P0 fields are present (or raise InputError).
  2. Apply P2 defaults for missing P2 fields (record in input_field_sources).
  3. Derive computed fields: scale_tier, operation_mode candidates,
     labor_cost_per_person_month, region_cost_index, etc.
  4. Assemble a BaseSolution object conforming to base_solution_schema.py.

Usage:
    from backend.solution.base_solution_input_adapter import adapt_project_state
    from backend.schemas.base_solution_schema import BaseSolution

    base_solution = adapt_project_state(project_state)
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Optional

from backend.schemas.base_solution_schema import (
    BaseSolution,
    ConfidenceLevel,
    ComplexityLevel,
    ImplementationPhase,
    ImplementationStrategy,
    InputFieldSource,
    KPIFramework,
    KPIItem,
    LaborModel,
    OperationMode,
    OperationModeEnum,
    ProcessDesign,
    ProcessStage,
    RiskItem,
    RiskProfile,
    ScaleTier,
    SystemBoundary,
)

# =============================================================================
# Constants — P2 Default Values (mirrors project_state_input_contract_v1.md)
# =============================================================================

P2_DEFAULTS: dict[str, Any] = {
    "industry": "电商",
    "region": "华东",
    "labor_cost_level": "中",
    "budget_level": "中",
    "automation_expectation": "中",
}

P0_FIELDS: list[str] = [
    "warehouse_area",
    "total_warehouse_area",
    "dc_count",
    "daily_orders",
    "sku_count",
    "contract_years",
    "service_scope",
]

# Region → cost index (华东 = 1.0, reference baseline)
REGION_COST_INDEX: dict[str, float] = {
    "华东": 1.00,
    "华南": 0.95,
    "华北": 1.05,
    "华中": 0.98,
    "西部": 0.92,
    "东北": 1.00,
}

# Labor cost level → base monthly cost per person (元/月) in 华东
LABOR_COST_PER_PERSON_MONTH: dict[str, float] = {
    "低": 4500.0,
    "中": 6500.0,
    "高": 9000.0,
}

# Industry → overhead factor (FMCG = 1.0 baseline, v0.8 five-level system)
INDUSTRY_OVERHEAD_FACTOR: dict[str, float] = {
    "AUTOMOTIVE":    1.20,
    "ELECTRONICS":   1.10,
    "FMCG":         1.00,
    "MANUFACTURING": 1.05,
    "GENERIC_3PL":  1.00,
}

# Industry → applicable operation modes (top candidates, priority order)
# AUTOMOTIVE checked FIRST — most specific automotive supply chain keywords
INDUSTRY_OPERATION_MODES: dict[str, list[OperationModeEnum]] = {
    "AUTOMOTIVE":    [OperationModeEnum.AUTOMOTIVE_LINE_SIDE, OperationModeEnum.AUTOMOTIVE_SEQUENCING, OperationModeEnum.STANDARD_WAREHOUSE],
    "ELECTRONICS":   [OperationModeEnum.ELECTRONICS_VMI_HUB, OperationModeEnum.STANDARD_WAREHOUSE],
    "FMCG":         [OperationModeEnum.FMCG_HIGH_TURNOVER, OperationModeEnum.OMNI_CHANNEL, OperationModeEnum.STANDARD_WAREHOUSE],
    "MANUFACTURING": [OperationModeEnum.MANUFACTURING_WIP, OperationModeEnum.STANDARD_WAREHOUSE],
    "GENERIC_3PL":  [OperationModeEnum.STANDARD_WAREHOUSE],
}

# Scale tier thresholds (sqm)
SCALE_TIER_RANGES: list[tuple[float, float, ScaleTier]] = [
    (50_000, float("inf"), ScaleTier.XL),
    (20_000, 50_000,      ScaleTier.L),
    (5_000,  20_000,      ScaleTier.M),
    (1_000,  5_000,       ScaleTier.S),
    (0,      1_000,       ScaleTier.XS),
]

SCALE_TIER_COMPLEXITY: dict[ScaleTier, ComplexityLevel] = {
    ScaleTier.XS: ComplexityLevel.LOW,
    ScaleTier.S:  ComplexityLevel.LOW,
    ScaleTier.M:  ComplexityLevel.MEDIUM,
    ScaleTier.L:  ComplexityLevel.HIGH,
    ScaleTier.XL: ComplexityLevel.HIGH,
}

SHIFT_BY_SCALE: dict[ScaleTier, str] = {
    ScaleTier.XS: "一班制（8h）",
    ScaleTier.S:  "一班制为主（8h）",
    ScaleTier.M:  "两班倒（白班/夜班，各 12h）",
    ScaleTier.L:  "两班倒（12h×2，含周末值班）",
    ScaleTier.XL: "三班倒（8h×3）或 24h 连续运营",
}

WORKING_HOURS_BY_SCALE: dict[ScaleTier, float] = {
    ScaleTier.XS: 8.0,
    ScaleTier.S:  10.0,
    ScaleTier.M:  16.0,
    ScaleTier.L:  22.0,
    ScaleTier.XL: 24.0,
}

_TYPICAL_ORDERS_BY_SCALE: dict[ScaleTier, float] = {
    ScaleTier.XS: 500,
    ScaleTier.S:  2000,
    ScaleTier.M:  8000,
    ScaleTier.L:  25000,
    ScaleTier.XL: 60000,
}

_HEADCOUNT_BASE: dict[ScaleTier, dict[str, int]] = {
    ScaleTier.XS: {"receiving_team": 2, "picking_team": 3, "loading_team": 1, "support_team": 1},
    ScaleTier.S:  {"receiving_team": 4, "picking_team": 6, "loading_team": 2, "support_team": 2},
    ScaleTier.M:  {"receiving_team": 8, "picking_team": 12, "loading_team": 4, "support_team": 3},
    ScaleTier.L:  {"receiving_team": 15, "picking_team": 25, "loading_team": 8, "support_team": 5},
    ScaleTier.XL: {"receiving_team": 25, "picking_team": 40, "loading_team": 15, "support_team": 8},
}

_OP_MODE_LABELS: dict[OperationModeEnum, str] = {
    # Generic
    OperationModeEnum.STANDARD_WAREHOUSE:     "标准仓配",
    OperationModeEnum.COLD_CHAIN:              "冷链仓配",
    OperationModeEnum.BONDED_WAREHOUSE:        "保税仓配",
    OperationModeEnum.HIGH_VALUE:              "高价值货仓",
    # Automotive
    OperationModeEnum.AUTOMOTIVE_LINE_SIDE:     "汽车产线配套（JIT/JIS）",
    OperationModeEnum.AUTOMOTIVE_SEQUENCING:   "汽车零部件排序（SKD/CKD）",
    # Electronics
    OperationModeEnum.ELECTRONICS_VMI_HUB:     "电子 VMI Hub",
    # FMCG
    OperationModeEnum.FMCG_HIGH_TURNOVER:      "快消高周转",
    # Manufacturing
    OperationModeEnum.MANUFACTURING_WIP:      "制造在制品",
    # Omni-channel
    OperationModeEnum.OMNI_CHANNEL:            "全渠道零售",
}

_CORE_ACTIVITIES_BY_MODE: dict[OperationModeEnum, list[str]] = {
    # Generic
    OperationModeEnum.STANDARD_WAREHOUSE: [
        "收货入库", "质检入库", "上架存储", "订单拣选",
        "包装贴标", "出库装车", "退货处理", "库存盘点",
    ],
    OperationModeEnum.COLD_CHAIN: [
        "温控收货", "冷库存储", "冷链拣选", "保温包装", "冷链配送",
    ],
    # Automotive
    OperationModeEnum.AUTOMOTIVE_LINE_SIDE: [
        "JIT/JIS 供料", "线边仓管理", "器具配送", "空器具回收",
        "产线协同", "节拍驱动补给",
    ],
    OperationModeEnum.AUTOMOTIVE_SEQUENCING: [
        "SKD/CKD 排序配料", "工序顺序组织", "组件配套", "器具循环管理",
    ],
    # Electronics
    OperationModeEnum.ELECTRONICS_VMI_HUB: [
        "多供应商协同", "入库即定址", "FIFO 精确管理", "VMI 计费对账",
    ],
    # FMCG
    OperationModeEnum.FMCG_HIGH_TURNOVER: [
        "高频波次拣选", "门店/渠道补货", "峰值弹性人力", "快速周转",
    ],
    # Manufacturing
    OperationModeEnum.MANUFACTURING_WIP: [
        "按工单配料", "产线边仓", "批量入库", "批次追溯",
    ],
    # Omni-channel
    OperationModeEnum.OMNI_CHANNEL: [
        "多渠道订单统一管理", "库存共享", "差异化包装/配送",
    ],
}


# =============================================================================
# Custom Exceptions
# =============================================================================

class InputError(Exception):
    """Raised when required P0 fields are missing from project_state."""

    pass


# =============================================================================
# Public Adapter Function
# =============================================================================

def adapt_project_state(
    project_state: dict[str, Any],
    *,
    project_id: Optional[str] = None,
) -> BaseSolution:
    """
    Transform a project_state dict (Input Contract v1) into a BaseSolution object.

    PURE transformation — no LLM calls.

    Parameters
    ----------
    project_state : dict
        Must conform to project_state_input_contract_v1.md.
        P0 fields must be present (raises InputError if missing).
        P2 fields may be absent (defaults applied and tracked).
    project_id : str, optional
        Pipeline/project ID for linkage.

    Returns
    -------
    BaseSolution
        Conforming to backend/schemas/base_solution_schema.py.

    Raises
    ------
    InputError
        If any P0 field is missing from project_state.

    Input field requirements:
      Required (P0, BLOCK if missing):
        warehouse_area, total_warehouse_area, dc_count, daily_orders,
        sku_count, contract_years, service_scope
      Optional with default (P2):
        industry, region, labor_cost_level, budget_level, automation_expectation
      Optional (P1, affects precision):
        kpi_targets, go_live_date, peak_factor, inventory, penalty_rules
    """

    if not project_state:
        return _build_empty_solution(project_id)

    # P0 gate check
    missing_p0 = [f for f in P0_FIELDS if _is_missing(project_state.get(f))]
    if missing_p0:
        raise InputError(
            f"Missing required P0 fields (cannot build BaseSolution): {missing_p0}. "
            "Complete Clarification before generating a solution."
        )

    # Resolve fields (P2 defaults applied, sources tracked)
    resolved, field_sources, defaulted_p2 = _resolve_fields(project_state)

    # Derive computed fields
    scale_tier      = _derive_scale_tier(resolved["warehouse_area"])
    op_mode         = _derive_operation_mode(resolved, scale_tier)
    labor_model     = _derive_labor_model(resolved, scale_tier)
    process_design  = _derive_process_design(resolved)
    kpi_framework   = _derive_kpi_framework(resolved)
    system_boundary = _derive_system_boundary(resolved)
    risk_profile    = _derive_risk_profile(resolved)
    impl_strategy   = _derive_implementation_strategy(resolved, scale_tier)

    # Compute confidence
    confidence, confidence_factors = _compute_confidence(defaulted_p2, project_state)

    # Assemble
    return BaseSolution(
        solution_id=_build_solution_id(project_id),
        solution_type="base",
        version="1.0",
        project_id=project_id,
        operation_mode=op_mode,
        process_design=process_design,
        labor_model=labor_model,
        kpi_framework=kpi_framework,
        system_boundary=system_boundary,
        risk_profile=risk_profile,
        implementation_strategy=impl_strategy,
        narrative="",  # Filled by LLM in base_solution_generator.py
        confidence=confidence,
        confidence_factors=confidence_factors,
        input_field_sources=list(field_sources.values()),
        missing_p0_fields=[],
        defaulted_p2_fields=defaulted_p2,
        generated_at=datetime.now(timezone.utc).isoformat(),
        generator_version="0.8-adapter",
    )


# =============================================================================
# Internal helpers
# =============================================================================

def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (str, list, dict)) and not value:
        return True
    return False


def _resolve_fields(
    project_state: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, InputFieldSource], list[str]]:
    resolved: dict[str, Any] = {}
    field_sources: dict[str, InputFieldSource] = {}
    defaulted_p2: list[str] = []

    all_keys = set(P0_FIELDS) | set(P2_DEFAULTS.keys())

    for key in all_keys:
        raw = project_state.get(key)
        is_p2_default = False
        source_type: str

        if not _is_missing(raw):
            source_type = "extracted"
        elif key in P2_DEFAULTS:
            raw = P2_DEFAULTS[key]
            source_type = "defaulted"
            is_p2_default = True
            defaulted_p2.append(key)
        else:
            raw = None
            source_type = "missing"

        resolved[key] = raw
        field_sources[key] = InputFieldSource(
            schema_field=key,
            source_type=source_type,
            source_input_key=key,
            was_p2_default=is_p2_default,
            confidence_impact=(
                "high" if key in P0_FIELDS and raw is None
                else "medium" if is_p2_default
                else "none"
            ),
        )

    return resolved, field_sources, defaulted_p2


def _derive_scale_tier(warehouse_area: float) -> ScaleTier:
    if warehouse_area is None:
        return ScaleTier.M
    for lo, hi, tier in SCALE_TIER_RANGES:
        if lo <= warehouse_area < hi:
            return tier
    return ScaleTier.XL


def _derive_operation_mode(
    resolved: dict[str, Any],
    scale_tier: ScaleTier,
) -> OperationMode:
    industry: str = resolved.get("industry", "电商")
    service_scope: dict[str, Any] = resolved.get("service_scope", {})
    region: str = resolved.get("region", "华东")

    candidates = INDUSTRY_OPERATION_MODES.get(
        industry, [OperationModeEnum.STANDARD_WAREHOUSE]
    )
    primary_mode = candidates[0]

    conditions = [
        f"行业: {industry}",
        f"仓库规模: {scale_tier.value} ({resolved.get('warehouse_area', '?')} sqm)",
    ]
    if service_scope.get("inbound", {}).get("cold_chain") or industry in ("医药", "食品", "生鲜"):
        conditions.append("含冷链或温控需求")
    if resolved.get("dc_count", 1) > 1:
        conditions.append(f"多仓联动 ({resolved['dc_count']} 个 DC)")

    region_cost_index = REGION_COST_INDEX.get(region, 1.0)
    industry_overhead_factor = INDUSTRY_OVERHEAD_FACTOR.get(industry, 1.0)

    return OperationMode(
        mode_name=primary_mode,
        label=_OP_MODE_LABELS.get(primary_mode, primary_mode.value),
        description=f"基于{industry}行业的{_OP_MODE_LABELS.get(primary_mode, '')}模式",
        applicable_conditions=conditions,
        core_activities=_CORE_ACTIVITIES_BY_MODE.get(primary_mode, []),
        region_cost_index=region_cost_index,
        industry_overhead_factor=industry_overhead_factor,
    )


def _derive_labor_model(
    resolved: dict[str, Any],
    scale_tier: ScaleTier,
) -> LaborModel:
    region: str = resolved.get("region", "华东")
    labor_cost_level: str = resolved.get("labor_cost_level", "中")
    labor_cost_adjustment_factor = REGION_COST_INDEX.get(region, 1.0)
    base_cost = LABOR_COST_PER_PERSON_MONTH.get(labor_cost_level, 6500.0)
    adjusted_cost = base_cost * labor_cost_adjustment_factor

    service_scope: dict[str, Any] = resolved.get("service_scope", {})
    daily_orders: float = resolved.get("daily_orders", 0)

    headcount = _estimate_headcount(scale_tier, service_scope, daily_orders)
    monthly_total = sum(headcount.values()) * adjusted_cost

    return LaborModel(
        headcount_by_role=headcount,
        shift_structure=SHIFT_BY_SCALE.get(scale_tier, "两班倒"),
        working_hours_per_day=WORKING_HOURS_BY_SCALE.get(scale_tier, 16.0),
        labor_cost_per_person_month=adjusted_cost,
        labor_cost_per_month=monthly_total,
        annual_labor_cost=monthly_total * 12,
        labor_cost_adjustment_factor=labor_cost_adjustment_factor,
        narrative="",
    )


def _estimate_headcount(
    scale_tier: ScaleTier,
    service_scope: dict[str, Any],
    daily_orders: float,
) -> dict[str, int]:
    headcount = dict(_HEADCOUNT_BASE.get(scale_tier, _HEADCOUNT_BASE[ScaleTier.M]))

    if daily_orders and daily_orders > 0:
        typical = _TYPICAL_ORDERS_BY_SCALE.get(scale_tier, 5000)
        ratio = daily_orders / typical
        if ratio > 1.5:
            for role in headcount:
                headcount[role] = int(math.ceil(headcount[role] * ratio))

    if service_scope.get("value_added", {}).get("kitting") or \
       service_scope.get("value_added", {}).get("repack"):
        headcount["va_team"] = headcount.get("va_team", 0) + 3

    if service_scope.get("support", {}).get("system_integration"):
        headcount["it_support"] = headcount.get("it_support", 0) + 1

    return headcount


def _derive_process_design(
    resolved: dict[str, Any],
) -> ProcessDesign:
    service_scope: dict[str, Any] = resolved.get("service_scope", {})
    stages: list[ProcessStage] = []
    flow_labels: list[str] = []

    inbound = service_scope.get("inbound", {})
    if inbound.get("receiving") or inbound.get("unloading"):
        stages.append(ProcessStage(
            stage_key="inbound_receiving", stage_name="入库收货", enabled=True,
            activities=["车辆到达登记", "卸货", "件数清点", "外观检查"],
            handoff="交接给质检团队", sla="4h 内完成收货", sla_hours=4.0,
            kpis=["收货准时率", "货损率"], roles_involved=["receiving_team"],
        ))
        flow_labels.append("入库收货")

    if inbound.get("quality_check"):
        stages.append(ProcessStage(
            stage_key="inbound_quality_check", stage_name="质量检验", enabled=True,
            activities=["抽样质检", "合规检查", "异常登记"],
            handoff="合格品移交上架", sla="2h 内完成质检", sla_hours=2.0,
            kpis=["质检合格率", "质检及时率"],
            roles_involved=["qc_team", "receiving_team"],
        ))
        flow_labels.append("质量检验")

    if inbound.get("putaway"):
        stages.append(ProcessStage(
            stage_key="inbound_putaway", stage_name="上架存储", enabled=True,
            activities=["库位分配", "叉车上架", "WMS 确认"],
            handoff="库存记录更新", sla="8h 内完成上架", sla_hours=8.0,
            kpis=["上架准确率", "上架及时率"],
            roles_involved=["warehouse_team"],
        ))
        flow_labels.append("上架存储")

    storage = service_scope.get("storage", {})
    if storage and any(storage.values()):
        stages.append(ProcessStage(
            stage_key="storage_management", stage_name="仓储管理", enabled=True,
            activities=["巡仓", "FIFO 管理", "库存盘点", "补货触发"],
            handoff="等待出库指令", sla=None, sla_hours=None,
            kpis=["库存准确率", "库容利用率"],
            roles_involved=["warehouse_team"],
        ))
        flow_labels.append("仓储管理")

    outbound = service_scope.get("outbound", {})
    if outbound.get("picking"):
        stages.append(ProcessStage(
            stage_key="outbound_picking", stage_name="订单拣选", enabled=True,
            activities=["波次生成", "拣货路径规划", "RF 扫描", "拣货确认"],
            handoff="移交包装", sla=None,
            kpis=["拣选效率", "拣选准确率"],
            roles_involved=["picking_team"],
        ))
        flow_labels.append("订单拣选")

    if outbound.get("packing"):
        stages.append(ProcessStage(
            stage_key="outbound_packing", stage_name="包装贴标", enabled=True,
            activities=["包装材料选取", "商品装箱", "面单打印", "称重校验"],
            handoff="移交流水线", sla=None,
            kpis=["包装合格率", "包装效率"],
            roles_involved=["packing_team"],
        ))
        flow_labels.append("包装贴标")

    if outbound.get("loading") or outbound.get("shipping"):
        stages.append(ProcessStage(
            stage_key="outbound_loading", stage_name="出库装车", enabled=True,
            activities=["装车排队", "装车扫描", "交接单据", "发车确认"],
            handoff="承运商接单", sla=None,
            kpis=["装载准时率", "在途时效达标率"],
            roles_involved=["loading_team"],
        ))
        flow_labels.append("出库装车")

    va = service_scope.get("value_added", {})
    if va and any(va.values()):
        stages.append(ProcessStage(
            stage_key="value_added_service", stage_name="流通加工", enabled=True,
            activities=[k for k, v in va.items() if v],
            handoff="返回主流程", sla=None,
            kpis=["VA 准时率", "加工合格率"],
            roles_involved=["va_team"],
        ))
        flow_labels.append("流通加工")

    if va.get("return_handling"):
        stages.append(ProcessStage(
            stage_key="return_handling", stage_name="退货处理", enabled=True,
            activities=["退货接收", "质检分类", "退货上架/报废"],
            handoff="库存更新", sla=None,
            kpis=["退货处理及时率", "退货合格率"],
            roles_involved=["return_team"],
        ))
        flow_labels.append("退货处理")

    support = service_scope.get("support", {})
    if support.get("inventory_reporting"):
        stages.append(ProcessStage(
            stage_key="inventory_reporting", stage_name="库存报表与对账",
            enabled=True,
            activities=["日报生成", "库存预警", "客户对账"],
            handoff="客户确认", sla=None,
            kpis=["报表准时率", "账实一致率"],
            roles_involved=["support_team"],
        ))
        flow_labels.append("库存报表")

    return ProcessDesign(
        stages=stages,
        flow_diagram_label=" → ".join(flow_labels),
        narrative="",
    )


def _derive_kpi_framework(
    resolved: dict[str, Any],
) -> KPIFramework:
    kpi_targets: dict[str, Any] = resolved.get("kpi_targets", {})
    service_scope: dict[str, Any] = resolved.get("service_scope", {})
    contractual_targets: set[str] = set(kpi_targets.get("contractual_kpis", []))
    kpis: list[KPIItem] = []

    if service_scope.get("inbound"):
        kpis.extend([
            KPIItem(
                kpi_key="inbound_uptime", name="入库及时率",
                target="≥99%", target_numeric=99.0, unit="%",
                measurement_method="WMS 收货时间戳统计",
                measurement_frequency="daily",
                is_sla_candidate=True,
                is_contractual="入库及时率" in contractual_targets,
            ),
            KPIItem(
                kpi_key="inbound_accuracy", name="入库准确率",
                target="≥99.5%", target_numeric=99.5, unit="%",
                measurement_method="WMS 上架确认数 vs 收货数",
                measurement_frequency="daily",
                is_sla_candidate=True,
                is_contractual="入库准确率" in contractual_targets,
            ),
            KPIItem(
                kpi_key="inbound_damage_rate", name="货损率",
                target="≤0.1%", target_numeric=0.1, unit="%",
                measurement_method="破损件数 / 收货总件数",
                measurement_frequency="monthly",
                is_sla_candidate=False,
                is_contractual="货损率" in contractual_targets,
            ),
        ])

    if service_scope.get("outbound"):
        kpis.extend([
            KPIItem(
                kpi_key="outbound_fulfillment_rate", name="订单履约率",
                target="≥99%", target_numeric=99.0, unit="%",
                measurement_method="当日实际发货订单数 / 当日应发货总订单数",
                measurement_frequency="daily",
                is_sla_candidate=True,
                is_contractual="订单履约率" in contractual_targets,
            ),
            KPIItem(
                kpi_key="outbound_accuracy", name="出库准确率",
                target="≥99.9%", target_numeric=99.9, unit="%",
                measurement_method="WMS 出库扫描校验",
                measurement_frequency="daily",
                is_sla_candidate=True,
                is_contractual="出库准确率" in contractual_targets,
            ),
            KPIItem(
                kpi_key="outbound_timeliness", name="出库准时率",
                target="≥98%", target_numeric=98.0, unit="%",
                measurement_method="截单时间前完成出库的比例",
                measurement_frequency="daily",
                is_sla_candidate=True,
                is_contractual="出库准时率" in contractual_targets,
            ),
        ])

    kpis.extend([
        KPIItem(
            kpi_key="inventory_accuracy", name="库存准确率",
            target="≥99.9%", target_numeric=99.9, unit="%",
            measurement_method="定期盘点差异 / 总库存件数",
            measurement_frequency="monthly",
            is_sla_candidate=False,
            is_contractual="库存准确率" in contractual_targets,
        ),
        KPIItem(
            kpi_key="inventory_turnover", name="库存周转天数",
            target=kpi_targets.get("inventory_turnover_target", "待确认"),
            target_numeric=None, unit="天",
            measurement_method="平均库存量 / 日均出库量",
            measurement_frequency="monthly",
            is_sla_candidate=False,
            is_contractual=False,
        ),
    ])

    return KPIFramework(
        operational_kpis=kpis,
        target_values={kpi.kpi_key: kpi.target for kpi in kpis},
        measurement_frequency="daily",
        narrative="",
    )


def _derive_system_boundary(
    resolved: dict[str, Any],
) -> SystemBoundary:
    service_scope: dict[str, Any] = resolved.get("service_scope", {})
    included = ["仓库设施", "WMS 系统", "基础设施运维"]
    excluded = ["客户 ERP 系统对接（除非明确约定）", "退货货值理赔"]
    integration_points = ["客户订单系统（API/EDI）"]
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
        narrative=" | ".join(scope_parts) if scope_parts else "",
    )


def _derive_risk_profile(
    resolved: dict[str, Any],
) -> RiskProfile:
    industry: str = resolved.get("industry", "电商")
    labor_cost_level: str = resolved.get("labor_cost_level", "中")
    region: str = resolved.get("region", "华东")
    risks: list[RiskItem] = []

    if region in ("华东", "华南"):
        risks.append(RiskItem(
            risk_id="R-01", category="labor_availability",
            description=f"{region}地区旺季可能出现临时工招募困难，影响峰值期间运营",
            severity="medium", likelihood="medium",
            mitigation=["提前与劳务公司签订框架协议", "建立灵活用工池"],
        ))

    if labor_cost_level == "高":
        risks.append(RiskItem(
            risk_id="R-02", category="cost_control",
            description="高人工成本地区，人力成本超支风险较高",
            severity="high", likelihood="high",
            mitigation=["引入局部自动化降低对人工的依赖", "优化排班减少无效工时"],
        ))

    if industry == "医药":
        risks.append(RiskItem(
            risk_id="R-03", category="regulatory",
            description="医药仓需满足 GSP 合规要求，部分地区有特殊监管要求",
            severity="high", likelihood="medium",
            mitigation=["提前确认 GSP 认证要求", "配置温湿度监控系统"],
        ))

    if industry in ("生鲜", "食品"):
        risks.append(RiskItem(
            risk_id="R-04", category="temperature_control",
            description="冷链断链风险，生鲜/食品货损率可能上升",
            severity="high", likelihood="medium",
            mitigation=["全程温控监控", "配置应急冷库备用"],
        ))

    risks.append(RiskItem(
        risk_id="R-05", category="process_handoff",
        description="跨团队交接环节可能出现信息丢失或延误",
        severity="medium", likelihood="low",
        mitigation=["明确交接标准和记录节点", "通过 WMS 实时跟踪作业状态"],
    ))

    return RiskProfile(risks=risks, narrative="")


def _derive_implementation_strategy(
    resolved: dict[str, Any],
    scale_tier: ScaleTier,
) -> ImplementationStrategy:
    contract_years: int = resolved.get("contract_years", 3)
    go_live_date: Optional[str] = resolved.get("go_live_date")
    complexity = SCALE_TIER_COMPLEXITY.get(scale_tier, ComplexityLevel.MEDIUM)

    timeline_by_tier: dict[ScaleTier, int] = {
        ScaleTier.XS: 3, ScaleTier.S: 6, ScaleTier.M: 9,
        ScaleTier.L: 12, ScaleTier.XL: 18,
    }
    timeline_months = min(
        timeline_by_tier.get(scale_tier, 9),
        max(6, contract_years * 12 - 2),
    )

    phase1_dur = min(3, max(1, timeline_months // 3))
    phase2_dur = min(3, max(1, timeline_months // 3))
    phase3_dur = max(1, timeline_months - phase1_dur - phase2_dur)

    phases = [
        ImplementationPhase(
            phase="Phase 1", name="基础准备",
            focus="团队组建 + 流程确认 + 设施验收",
            key_actions=["运营团队招聘与培训", "WMS 系统部署",
                         "设备入场安装", "流程 SOP 编制"],
            duration_months=phase1_dur,
            gate_criteria=["团队到岗率 ≥ 90%", "WMS 系统上线", "设备调试完成"],
        ),
        ImplementationPhase(
            phase="Phase 2", name="试运营",
            focus="小规模试运行 + 问题修复",
            key_actions=["降负荷试运营（30% 容量）", "KPI 基线测定", "异常流程优化"],
            duration_months=phase2_dur,
            gate_criteria=["试运营 30 天零重大事故", "主要 KPI 达到目标 80%"],
        ),
        ImplementationPhase(
            phase="Phase 3", name="正式运营",
            focus="全容量正式运营 + 持续优化",
            key_actions=["全容量运营", "KPI 正式考核", "季度复盘与优化"],
            duration_months=phase3_dur,
            gate_criteria=["全流程稳定运行 30 天", "所有 SLA 指标达标"],
        ),
    ]

    return ImplementationStrategy(
        phases=phases,
        timeline_months=timeline_months,
        complexity=complexity,
        go_live_target=go_live_date,
        narrative="",
    )


def _compute_confidence(
    defaulted_p2: list[str],
    project_state: dict[str, Any],
) -> tuple[ConfidenceLevel, dict[str, str]]:
    """
    HIGH   — no P2 fields defaulted, kpi_targets present
    MEDIUM — at least one P2 field defaulted (generate but be conservative)
    LOW    — any P0 missing (BLOCK risk; should be caught upstream)
    UNKNOWN — empty project_state
    """
    factors: dict[str, str] = {}

    if not project_state or not any(project_state.values()):
        return ConfidenceLevel.UNKNOWN, {"input": "empty project_state"}

    if not defaulted_p2:
        if project_state.get("kpi_targets"):
            confidence = ConfidenceLevel.HIGH
            factors["kpi_targets"] = "present"
        else:
            confidence = ConfidenceLevel.MEDIUM
            factors["kpi_targets"] = "missing (P1); MEDIUM is appropriate"
    else:
        # P2 defaulted — generate but be conservative in narrative
        confidence = ConfidenceLevel.MEDIUM
        factors["defaulted_p2_fields"] = (
            f"{defaulted_p2} — these may not reflect actual client context; "
            "MEDIUM because solution is still generatable"
        )

    return confidence, factors


def _build_solution_id(project_id: Optional[str]) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    pid_part = f"{project_id[:8]}" if project_id else "unknown"
    return f"BS-{pid_part}-{ts}"


def _build_empty_solution(project_id: Optional[str]) -> BaseSolution:
    """Return a minimal BaseSolution for empty input."""
    return BaseSolution(
        solution_id=_build_solution_id(project_id),
        solution_type="base",
        version="1.0",
        project_id=project_id,
        operation_mode=OperationMode(
            mode_name=OperationModeEnum.STANDARD_WAREHOUSE,
            label="标准仓配",
            description="无输入数据",
            applicable_conditions=[],
            core_activities=[],
        ),
        process_design=ProcessDesign(stages=[], narrative=""),
        labor_model=LaborModel(
            headcount_by_role={},
            narrative="无输入数据",
        ),
        kpi_framework=KPIFramework(operational_kpis=[], narrative=""),
        system_boundary=SystemBoundary(narrative=""),
        risk_profile=RiskProfile(risks=[], narrative=""),
        implementation_strategy=ImplementationStrategy(
            phases=[], timeline_months=0, complexity=ComplexityLevel.UNKNOWN,
        ),
        narrative="",
        confidence=ConfidenceLevel.UNKNOWN,
        confidence_factors={"input": "empty project_state"},
        input_field_sources=[],
        generated_at=datetime.now(timezone.utc).isoformat(),
        generator_version="0.8-adapter",
    )
