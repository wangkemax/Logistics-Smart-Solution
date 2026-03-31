"""
base_solution_schema.py — v0.8 Base Solution JSON Schema
==========================================================

Three-layer solution architecture:
  Layer 1: Base Solution    — operation mode, process design, labor model, KPI, system boundary
  Layer 2: Improvement      — process optimisation, efficiency gains
  Layer 3: Automation       — AMR/AGV/AS/RS fit judgment, ROI

This module defines only the Layer-1 (Base Solution) schema.

Schema designed for: backend/schemas/base_solution_schema.py
Adapter:            backend/solution/base_solution_input_adapter.py
Architecture doc:   docs/architecture/base_solution_architecture.md

All fields serialisable to JSON.  All optional fields have explicit defaults.
Confidence field tracks solution completeness based on input quality.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# Enums
# =============================================================================


class OperationModeEnum(str, Enum):
    """Known operation-mode candidates. Extensible via registry."""

    STANDARD_WAREHOUSE = "standard_warehouse"          # 标准仓配
    COLD_CHAIN = "cold_chain"                          # 冷链
    BONDED_WAREHOUSE = "bonded_warehouse"              # 保税
    HIGH_VALUE = "high_value"                          # 高价值货
    ECOMMERCE_FULFILLMENT = "ecommerce_fulfillment"    # 电商履约
    THIRD_PARTY_LOGISTICS = "third_party_logistics"   # 3PL
    MANUFACTURING_WIP = "manufacturing_wip"            # 制造在制品
    EXPRESS_SORTING = "express_sorting"                # 快递分拣
    OMNI_CHANNEL = "omni_channel"                      # 全渠道
    PHARMA = "pharma"                                  # 医药
    FOOD = "food"                                      # 食品
    FRESH = "fresh"                                    # 生鲜


class ComplexityLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class ConfidenceLevel(str, Enum):
    """Solution completeness based on input quality.

    - HIGH:    All P0 + P1 present; P2 fields are extracted (not defaulted)
    - MEDIUM:  All P0 present; at least one P1 or P2 defaulted (generate but be conservative)
    - LOW:     Any P0 missing → should have been blocked upstream (BLOCK risk)
    - UNKNOWN: Adapter not yet run or input was empty dict
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class ScaleTier(str, Enum):
    """Facility scale tier derived from warehouse_area."""

    XS = "xs"      # < 1,000 sqm
    S  = "s"       # 1,000 – 5,000 sqm
    M  = "m"       # 5,000 – 20,000 sqm
    L  = "l"       # 20,000 – 50,000 sqm
    XL = "xl"      # > 50,000 sqm


class LaborCostLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Region(str, Enum):
    EAST_CHINA    = "华东"
    SOUTH_CHINA   = "华南"
    NORTH_CHINA   = "华北"
    CENTRAL_CHINA = "华中"
    WEST_CHINA    = "西部"
    NORTHEAST     = "东北"


class Industry(str, Enum):
    ECOMMERCE    = "电商"
    TPL          = "3PL"
    RETAIL       = "零售"
    MANUFACTURE  = "制造"
    EXPRESS      = "快递"
    PHARMA       = "医药"
    FOOD         = "食品"
    FRESH        = "生鲜"


# =============================================================================
# Sub-section: OperationMode
# =============================================================================


class OperationMode(BaseModel):
    """
    Layer-1 operation mode definition.

    Derived from: industry + service_scope + warehouse_area
    Feeds into:   process_design, labor_model
    """

    mode_name: OperationModeEnum = Field(
        description="运营模式枚举值"
    )
    label: str = Field(
        description="运营模式中文标签，如 '标准仓配运营模式'"
    )
    description: str = Field(
        default="",
        description="运营模式一句话描述"
    )
    applicable_conditions: list[str] = Field(
        default_factory=list,
        description="适用该模式的条件清单（从 industry / service_scope / scale_tier 推导）"
    )
    core_activities: list[str] = Field(
        default_factory=list,
        description="该模式下的核心作业活动清单"
    )
    scale_tier: Optional[str] = Field(
        default=None,
        description="仓储规模等级（XS/S/M/L/XL），由 warehouse_area 推导"
    )
    # Derived from P2-aware lookups (region → cost index, industry → overhead factor)
    region_cost_index: float = Field(
        default=1.0,
        description="区域成本指数（华东 = 1.0，参考值：华南 0.95，华北 1.05 …）"
    )
    industry_overhead_factor: float = Field(
        default=1.0,
        description="行业附加系数（电商 = 1.0，医药 1.2，冷链 1.3 …）"
    )


# =============================================================================
# Sub-section: ProcessDesign
# =============================================================================


class ProcessStage(BaseModel):
    """
    A single stage within the end-to-end process.
    One entry per service_scope entry that is True.
    """

    stage_key: str = Field(
        description="阶段键名，如 'inbound_receiving', 'outbound_picking'"
    )
    stage_name: str = Field(
        description="阶段中文名称，如 '入库收货'"
    )
    enabled: bool = Field(
        default=True,
        description="该阶段是否在当前 service_scope 中启用"
    )
    activities: list[str] = Field(
        default_factory=list,
        description="该阶段包含的作业活动列表（步骤级）"
    )
    handoff: str = Field(
        default="",
        description="与下一阶段的交接说明（人或系统）"
    )
    sla: Optional[str] = Field(
        default=None,
        description="该阶段的 SLA 承诺，如 '4h 内完成质检'，缺失表示未定义 SLA"
    )
    sla_hours: Optional[float] = Field(
        default=None,
        description="SLA 小时数（数值，方便计算）"
    )
    kpis: list[str] = Field(
        default_factory=list,
        description="该阶段关联的 KPI 名称列表"
    )
    roles_involved: list[str] = Field(
        default_factory=list,
        description="涉及的角色/团队列表"
    )


class ProcessDesign(BaseModel):
    """
    Full end-to-end process design, one ProcessStage per enabled service.
    Ordered by actual flow: inbound → storage → outbound → value_added → support.
    """

    stages: list[ProcessStage] = Field(
        default_factory=list,
        description="所有启用阶段的列表（按作业顺序排列）"
    )
    flow_diagram_label: str = Field(
        default="",
        description="流程图节点标签序列，用于前端渲染流程图"
    )
    narrative: str = Field(
        default="",
        description="流程设计中文叙述文字"
    )


# =============================================================================
# Sub-section: LaborModel
# =============================================================================


class LaborModel(BaseModel):
    """
    Labour staffing model derived from scale_tier + service_scope + region.

    Input dependencies:
      - P0: warehouse_area, daily_orders, service_scope
      - P2: region (→ labor_cost_adjustment_factor), labor_cost_level (→ labor_cost_per_person_month)
    """

    headcount_by_role: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "各角色人数，键名为角色键（如 receiving_team, picking_team），"
            "值为月均人数。 由 scale_tier + service_scope + labor_cost_level 推导。"
        )
    )
    shift_structure: str = Field(
        default="",
        description="班次结构，如 '两班倒（白班/夜班）' 或 '三班倒（8h×3）'"
    )
    working_hours_per_day: float = Field(
        default=16.0,
        description="每日运营小时数（默认 16h，两班）"
    )
    labor_cost_per_person_month: float = Field(
        default=0.0,
        description="单人月均人工成本（元），由 labor_cost_level + region 推导"
    )
    labor_cost_per_month: float = Field(
        default=0.0,
        description="月均总人工成本（元）= sum(headcount) × labor_cost_per_person_month"
    )
    annual_labor_cost: float = Field(
        default=0.0,
        description="年人工成本（元）= labor_cost_per_month × 12"
    )
    labor_cost_adjustment_factor: float = Field(
        default=1.0,
        description="区域人工成本调整系数（华东 = 1.0；华北 ~1.05；华南 ~0.95）"
    )
    narrative: str = Field(
        default="",
        description="人工模型中文叙述"
    )


# =============================================================================
# Sub-section: KPIFramework
# =============================================================================


class KPIItem(BaseModel):
    """A single KPI definition."""

    kpi_key: str = Field(description="KPI 唯一键名，如 'inbound_uptime'")
    name: str = Field(description="KPI 中文名称")
    target: str = Field(default="", description="目标值或口径说明")
    target_numeric: Optional[float] = Field(
        default=None,
        description="数值型目标（方便计算），无则 None"
    )
    unit: str = Field(default="", description="单位，如 '%'、'件/小时'、'小时'")
    measurement_method: str = Field(
        default="",
        description="数据获取/计算方式"
    )
    measurement_frequency: str = Field(
        default="monthly",
        description="测量频率: daily / weekly / monthly / quarterly"
    )
    is_sla_candidate: bool = Field(
        default=False,
        description="是否可作为 SLA 承诺指标"
    )
    is_contractual: bool = Field(
        default=False,
        description="是否为合同承诺指标（由 kpi_targets 输入推导）"
    )


class KPIFramework(BaseModel):
    """
    KPI framework covering all service categories.

    Input dependencies:
      - P1: kpi_targets (for contractual flags)
      - P0: service_scope (for which categories to include)
    """

    operational_kpis: list[KPIItem] = Field(
        default_factory=list,
        description="所有运营 KPI 条目"
    )
    target_values: dict[str, str] = Field(
        default_factory=dict,
        description="KPI 键 → 目标值 的快速查询字典"
    )
    measurement_frequency: str = Field(
        default="monthly",
        description="默认测量频率（当条目未单独指定时）"
    )
    narrative: str = Field(
        default="",
        description="KPI 框架中文叙述"
    )


# =============================================================================
# Sub-section: SystemBoundary
# =============================================================================


class SystemBoundary(BaseModel):
    """
    System / scope boundary definition.

    Explicitly lists what is inside, what is outside, and integration points.
    Derived from: service_scope + automation_expectation + budget_level
    """

    included: list[str] = Field(
        default_factory=list,
        description="方案范围内的设施/系统/服务列表"
    )
    excluded: list[str] = Field(
        default_factory=list,
        description="明确排除在方案范围之外的项目"
    )
    integration_points: list[str] = Field(
        default_factory=list,
        description="需要集成的外部系统或接口（如 WMS / ERP / 客户系统）"
    )
    narrative: str = Field(
        default="",
        description="系统边界中文叙述"
    )


# =============================================================================
# Sub-section: RiskProfile
# =============================================================================


class RiskItem(BaseModel):
    """A single risk entry."""

    risk_id: str = Field(description="风险编号，如 'R-01'")
    category: str = Field(
        description="风险类别: service_boundary / data_quality / process_handoff / "
                    "labor_availability / equipment_reliability / regulatory"
    )
    description: str = Field(default="", description="风险描述")
    severity: str = Field(
        default="medium",
        description="严重程度: high / medium / low"
    )
    likelihood: str = Field(
        default="medium",
        description="发生可能性: high / medium / low"
    )
    mitigation: list[str] = Field(
        default_factory=list,
        description="缓解措施列表"
    )


class RiskProfile(BaseModel):
    """
    Risk profile for the base solution.

    Risks are derived from: industry, region, service_scope, labor_cost_level.
    """

    risks: list[RiskItem] = Field(default_factory=list)
    narrative: str = Field(default="", description="风险概述中文叙述")


# =============================================================================
# Sub-section: ImplementationStrategy
# =============================================================================


class ImplementationPhase(BaseModel):
    """A single implementation phase."""

    phase: str = Field(description="阶段编号，如 'Phase 1'")
    name: str = Field(description="阶段名称")
    focus: str = Field(description="阶段重点")
    key_actions: list[str] = Field(default_factory=list)
    duration_months: int = Field(default=3, ge=1, le=24)
    gate_criteria: list[str] = Field(
        default_factory=list,
        description="阶段验收门槛（门禁条件）"
    )


class ImplementationStrategy(BaseModel):
    """
    Implementation roadmap.

    Complexity derived from: warehouse_area, service_scope, dc_count
    Timeline derived from: contract_years (must fit within contract period)
    """

    phases: list[ImplementationPhase] = Field(default_factory=list)
    timeline_months: int = Field(
        default=12,
        ge=1,
        le=60,
        description="总实施周期（月）"
    )
    complexity: ComplexityLevel = Field(
        default=ComplexityLevel.MEDIUM,
        description="实施复杂度"
    )
    go_live_target: Optional[str] = Field(
        default=None,
        description="目标上线日期（YYYY-MM），从 go_live_date 输入或推算"
    )
    narrative: str = Field(default="", description="实施策略中文叙述")


# =============================================================================
# Input Field Source Tracking
# =============================================================================


class InputFieldSource(BaseModel):
    """
    Tracks the provenance of a single schema field.

    Added to every BaseSolution so downstream consumers know
    whether a value came from extraction, default, or manual input.
    """

    schema_field: str = Field(description="Schema 字段名")
    source_type: str = Field(
        description="来源类型: manual / extracted / defaulted / computed"
    )
    source_input_key: Optional[str] = Field(
        default=None,
        description="来自哪个输入字段（如 'region'）"
    )
    was_p2_default: bool = Field(
        default=False,
        description="该字段是否使用了 P2 默认值（需在 UI 上 ⚠️ 标注）"
    )
    confidence_impact: str = Field(
        default="none",
        description="对整体 confidence 的影响: high / medium / low / none"
    )


# =============================================================================
# Top-level: BaseSolution
# =============================================================================


class BaseSolution(BaseModel):
    """
    Layer-1 (Base Solution) schema — the foundational operational blueprint.

    Generated by: base_solution_generator.py  (LLM-based, after this adapter layer)
    Consumed by:
        - Layer-2 Improvement Solution (receives process_design + labor_model)
        - Layer-3 Automation Solution   (receives system_boundary + ROI targets)
        - API / Frontend / PDF exporter

    Input contract requirements:
      Required (may use P2 defaults): industry, region, warehouse_area, daily_orders,
                                       sku_count, labor_cost_level, budget_level,
                                       service_scope
      Optional: kpi_targets, automation_expectation, go_live_date, peak_factor,
                inventory, penalty_rules

    Confidence scoring:
      HIGH   — all P0 present, all P2 fields extracted (not defaulted), kpi_targets present
      MEDIUM — all P0 present, at least one P2 field defaulted
      LOW    — any P0 missing (should have been blocked upstream)
      UNKNOWN — empty input
    """

    # ── Identity ────────────────────────────────────────────────────────────
    solution_id: str = Field(
        description="方案唯一 ID，格式: BS-{project_id}-{timestamp}"
    )
    solution_type: Literal["base"] = Field(
        default="base",
        description="固定为 'base'，区分于 improvement / automation 两层"
    )
    version: str = Field(
        default="1.0",
        description="方案版本号，语义化版本控制"
    )

    # ── Core Sub-sections ───────────────────────────────────────────────────
    operation_mode: OperationMode = Field(
        description="运营模式定义"
    )
    process_design: ProcessDesign = Field(
        description="端到端流程设计"
    )
    labor_model: LaborModel = Field(
        description="人工 staffing 模型"
    )
    kpi_framework: KPIFramework = Field(
        description="KPI 框架"
    )
    system_boundary: SystemBoundary = Field(
        description="系统/服务边界定义"
    )
    risk_profile: RiskProfile = Field(
        description="风险档案"
    )
    implementation_strategy: ImplementationStrategy = Field(
        description="实施策略与阶段"
    )

    # ── Derived / Generated ─────────────────────────────────────────────────
    narrative: str = Field(
        default="",
        description="由 LLM 从以上结构化字段生成的中文叙述文字（不直接编辑）"
    )

    # ── Quality Tracking ─────────────────────────────────────────────────────
    confidence: ConfidenceLevel = Field(
        default=ConfidenceLevel.UNKNOWN,
        description="方案完整度等级，基于输入质量计算"
    )
    confidence_factors: dict[str, str] = Field(
        default_factory=dict,
        description="各 confidence 等级的影响因子详情"
    )
    input_field_sources: list[InputFieldSource] = Field(
        default_factory=list,
        description="每个 schema 字段的来源追溯列表"
    )
    missing_p0_fields: list[str] = Field(
        default_factory=list,
        description="缺失的 P0 字段列表（仅当 confidence != HIGH 时有值）"
    )
    defaulted_p2_fields: list[str] = Field(
        default_factory=list,
        description="使用了 P2 默认值的字段列表（需在 UI 上 ⚠️ 标注）"
    )

    # ── Metadata ─────────────────────────────────────────────────────────────
    project_id: Optional[str] = Field(
        default=None,
        description="关联的 pipeline_id"
    )
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="生成时间 ISO-8601"
    )
    generator_version: str = Field(
        default="0.8",
        description="生成器版本号"
    )

    model_config = ConfigDict(
        use_enum_values=True,
        extra="allow",
        json_encoders={datetime: lambda v: v.isoformat()},
    )



