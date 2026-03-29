"""
solution_schema.py — v0.7 Base Solution Generator
===============================================

Pydantic schemas for the BaseSolution object and all sub-sections.
Designed to be read by: API layer, frontend, future exporters.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# Sub-section Schemas
# =============================================================================


class ProjectFit(BaseModel):
    """How well the project fits known templates and what category it falls into."""
    operation_type: str = Field(description="运营类型: warehouse_distribution / cold_chain / bonded / ...")
    complexity_level: str = Field(description="复杂度等级: low / medium / high")
    complexity_score: int = Field(description="复杂度评分 0-20")
    service_scope_summary: str = Field(description="服务范围一句话总结")
    fit_reason: str = Field(description="为何判定为该运营类型")


class IncludedService(BaseModel):
    """A single confirmed service item."""
    category: str = Field(description="服务类别: inbound/storage/outbound/value_added/support")
    service_key: str = Field(description="服务键名: receiving / picking / ...")
    label: str = Field(description="服务中文标签")
    confirmed: bool = Field(default=True, description="是否已确认")


class ServiceDesign(BaseModel):
    """Section 2: Service Scope Design."""
    included_services: list[IncludedService] = Field(
        default_factory=list,
        description="已确认纳入的服务项"
    )
    excluded_or_unconfirmed: list[str] = Field(
        default_factory=list,
        description="未纳入或未确认的服务项"
    )
    service_boundary_notes: list[str] = Field(
        default_factory=list,
        description="服务边界说明"
    )
    narrative: str = Field(default="", description="服务范围设计中文描述")


class RoleSummary(BaseModel):
    """A single role/team module."""
    module_key: str = Field(description="模块键名: receiving_team / picking_team / ...")
    label: str = Field(description="模块中文标签")
    primary_responsibilities: list[str] = Field(default_factory=list)
    handoff_to: list[str] = Field(default_factory=list, description="交接给哪些模块")


class OrganizationDesign(BaseModel):
    """Section 3: Organization & Team Design."""
    team_modules: list[RoleSummary] = Field(default_factory=list)
    staffing_logic: str = Field(default="", description="人员配置逻辑说明")
    narrative: str = Field(default="", description="组织设计中文描述")


class ProcessDesignItem(BaseModel):
    """A single process module."""
    process_key: str = Field(description="流程键名: receiving_process / outbound_process / ...")
    label: str = Field(description="流程中文标签")
    description: str = Field(description="流程一句话描述")
    step_count: int = Field(description="步骤总数")
    key_control_points: list[str] = Field(default_factory=list, description="关键控制点")
    handoff_points: list[str] = Field(default_factory=list, description="关键交接点")
    kpis: list[str] = Field(default_factory=list, description="流程KPI列表")
    narrative: str = Field(default="", description="流程设计中文描述")


class ProcessDesign(BaseModel):
    """Section 4: Core Process Design."""
    processes: list[ProcessDesignItem] = Field(default_factory=list)
    overall_process_narrative: str = Field(default="", description="整体流程设计描述")


class KPIItem(BaseModel):
    """A single KPI."""
    name: str = Field(description="KPI名称")
    target: str = Field(description="目标值/口径说明")
    measurement_method: str = Field(description="测量方式")
    is_sla_candidate: bool = Field(default=False, description="是否可作为SLA承诺指标")


class KPIFramework(BaseModel):
    """Section 5: KPI Framework Design."""
    inbound_kpis: list[KPIItem] = Field(default_factory=list)
    outbound_kpis: list[KPIItem] = Field(default_factory=list)
    inventory_kpis: list[KPIItem] = Field(default_factory=list)
    support_kpis: list[KPIItem] = Field(default_factory=list)
    narrative: str = Field(default="", description="KPI框架中文描述")


class ImplementationPhase(BaseModel):
    """A single implementation phase."""
    phase: str = Field(description="阶段编号: Phase 1 / Phase 2 / Phase 3")
    name: str = Field(description="阶段名称")
    focus: str = Field(description="阶段重点")
    key_actions: list[str] = Field(default_factory=list, description="关键动作")
    duration_months: int = Field(default=3, description="预计持续月数")


class ImplementationFocus(BaseModel):
    """Section 6: Implementation Focus."""
    phases: list[ImplementationPhase] = Field(default_factory=list)
    narrative: str = Field(default="", description="实施建议中文描述")


class RiskItem(BaseModel):
    """A single risk."""
    risk_id: str = Field(description="风险编号: R-01")
    category: str = Field(description="风险类别: 服务边界/数据完整/流程衔接/KPI口径/人员组织")
    description: str = Field(description="风险描述")
    severity: str = Field(description="严重程度: high / medium / low")
    control_measure: str = Field(description="控制措施")
    mitigation_action: str = Field(description="缓解动作")


class RiskAndControls(BaseModel):
    """Section 7: Risk & Control Recommendations."""
    risks: list[RiskItem] = Field(default_factory=list)
    narrative: str = Field(default="", description="风险控制中文描述")


class CostModelLinkage(BaseModel):
    """Section 8: Cost Model Linkage."""
    current_mode: str = Field(description="当前测算模式: blocked / range_estimate / full_calc")
    mode_explanation: str = Field(description="当前模式说明")
    cost_boundary_summary: str = Field(description="成本边界说明")
    missing_for_full_calc: list[str] = Field(
        default_factory=list,
        description="进入full_calc还缺的字段"
    )
    assumptions_used: list[dict] = Field(
        default_factory=list,
        description="当前使用的假设字段"
    )
    narrative: str = Field(default="", description="成本衔接说明")


class NarrativeSections(BaseModel):
    """All narrative text sections for the solution."""
    executive_summary: str = Field(default="", description="执行摘要")
    service_solution_text: str = Field(default="", description="服务方案文本")
    process_solution_text: str = Field(default="", description="流程方案文本")
    kpi_text: str = Field(default="", description="KPI框架文本")
    risk_text: str = Field(default="", description="风险控制文本")


# =============================================================================
# Top-level BaseSolution
# =============================================================================


class BaseSolution(BaseModel):
    """
    Complete Base Solution for a project.

    Generated by: base_solution_generator.py
    Consumed by: API layer, frontend, future exporters
    """
    solution_id: str = Field(description="方案ID: base_solution_v1")
    solution_type: str = Field(default="base_solution")
    project_id: str = Field(description="关联的pipeline_id")

    # Metadata
    title: str = Field(default="基础仓配运营方案")
    summary: str = Field(default="", description="方案执行摘要")
    generated_at: str = Field(description="生成时间 ISO-8601")

    # Core sections
    project_fit: ProjectFit = Field(description="项目定位与适配")
    service_design: ServiceDesign = Field(description="服务范围设计")
    organization_design: OrganizationDesign = Field(description="组织与团队设计")
    process_design: ProcessDesign = Field(description="核心流程设计")
    kpi_framework: KPIFramework = Field(description="KPI框架设计")
    implementation_focus: ImplementationFocus = Field(description="实施重点")
    risk_and_controls: RiskAndControls = Field(description="风险与控制")
    cost_model_linkage: CostModelLinkage = Field(description="成本测算衔接")

    # Narrative text
    narrative_sections: NarrativeSections = Field(
        default_factory=NarrativeSections,
        description="所有中文业务表述文本"
    )

    # Traceability
    derived_from_fields: list[str] = Field(
        default_factory=list,
        description="生成所依据的字段来源"
    )
    derived_from_service_scope: bool = Field(
        default=False,
        description="是否基于结构化service_scope"
    )
    derived_from_operation_profile: bool = Field(
        default=False,
        description="是否基于operation_profile"
    )
    input_cost_mode: str = Field(
        default="unknown",
        description="生成时的cost_mode"
    )
    assumptions_in_solution: int = Field(
        default=0,
        description="方案中使用的假设项数量"
    )

    model_config = ConfigDict(extra="allow")
