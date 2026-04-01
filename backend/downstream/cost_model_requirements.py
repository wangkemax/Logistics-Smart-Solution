"""
downstream/cost_model_requirements.py — Cost Model Field Priority Schema
=====================================================================

Defines which fields the Cost Model Agent needs, organized by priority:
  P0: Blocking — no full calculation if any P0 field is missing/ambiguous
  P1: Important — range estimate allowed if missing, but must be explicit
  P2: Optimization — missing does not block, only reduces precision

Version: v0.2
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CostFieldRequirement:
    """
    Describes how the Cost Model Agent should handle a specific field.
    """
    field_key: str                           # canonical field key in normalized_fields
    display_name: str                         # human-readable name
    priority: str                             # P0 | P1 | P2
    assumption_allowed: bool                 # can Cost Model use a fallback assumption?
    assumption_rule: str                      # description of acceptable assumption
    usable_statuses: list[str]               # which statuses allow direct use
    clarification_template: str               # question template when missing
    unit: str = ""
    impact_on_cost: str = ""                 # what cost component this field affects


COST_MODEL_REQUIREMENTS: list[CostFieldRequirement] = [
    # ========================================================================
    # P0 — Blocking fields: required for any formal cost calculation
    # ========================================================================
    CostFieldRequirement(
        field_key="dc_count",
        display_name="DC/仓库数量",
        priority="P0",
        assumption_allowed=False,
        assumption_rule="禁止假设：DC数量决定网络结构，必须以招标文件为准",
        usable_statuses=["explicit"],
        clarification_template="请确认本项目实际覆盖的DC/仓库数量及所在城市：",
        unit="个",
        impact_on_cost="网络结构决定仓租总额、设备投入、人员配置",
    ),
    CostFieldRequirement(
        field_key="warehouse_area",
        display_name="仓库总面积",
        priority="P0",
        assumption_allowed=False,
        assumption_rule="禁止假设：仓库面积是仓租和布局测算的基础",
        usable_statuses=["explicit", "partial"],
        clarification_template="请确认各仓库的具体面积（平方米）及是否有分期入驻计划：",
        unit="平方米",
        impact_on_cost="仓租、设备投入（货架/叉车）、布局方案",
    ),
    CostFieldRequirement(
        field_key="daily_orders",
        display_name="日均出库量",
        priority="P0",
        assumption_allowed=False,
        assumption_rule="禁止假设：日均出库量是人力、产能、设备选型的核心参数",
        usable_statuses=["explicit"],
        clarification_template="请确认日出库量统计口径（自然日/工作日）及旺季峰值倍数：",
        unit="件/单",
        impact_on_cost="人力配置、分拣设备产能、峰值产能设计",
    ),
    CostFieldRequirement(
        field_key="contract_years",
        display_name="合同年限",
        priority="P0",
        assumption_allowed=False,
        assumption_rule="合同年限决定ROI和设备折旧摊销年限",
        usable_statuses=["explicit"],
        clarification_template="请确认合同期限是固定3年还是有续约机制（3+2年）：",
        unit="年",
        impact_on_cost="ROI/IRR测算、设备折旧年限、现金流规划",
    ),
    CostFieldRequirement(
        field_key="service_scope",
        display_name="服务范围矩阵",
        priority="P0",
        assumption_allowed=False,
        assumption_rule="服务范围决定成本结构和报价策略，必须完整明确",
        usable_statuses=["explicit"],
        clarification_template="请从以下服务矩阵中勾选本项目实际包含的服务项：",
        unit="",
        impact_on_cost="OPEX结构、报价策略、合同条款、人员配置、设备选型",
    ),

    # ========================================================================
    # P1 — Important fields: range estimate allowed if missing
    # ========================================================================
    CostFieldRequirement(
        field_key="sku_count",
        display_name="SKU总数",
        priority="P1",
        assumption_allowed=True,
        assumption_rule="若缺失，可按月均出货量 ÷ SKU均值（约15-20件/SKU/月）反推，但须注明估算依据",
        usable_statuses=["explicit", "inferred"],
        clarification_template="请确认投标SKU品类数量及ABC分类占比（如有）：",
        unit="个",
        impact_on_cost="拆零比例、库位规划、人员培训复杂度",
    ),
    CostFieldRequirement(
        field_key="inventory",
        display_name="平均库存量",
        priority="P1",
        assumption_allowed=True,
        assumption_rule="若缺失，可按日出库量 × 平均在库天数（约7-10天）估算",
        usable_statuses=["explicit", "inferred"],
        clarification_template="请确认平均库存量和峰值库存量，以及是否含VMI：",
        unit="件/板",
        impact_on_cost="库位规划、库存持有成本、峰值产能",
    ),
    CostFieldRequirement(
        field_key="peak_factor",
        display_name="高峰系数",
        priority="P1",
        assumption_allowed=True,
        assumption_rule="若缺失，默认取1.5（旺季约为日均1.5倍），可按行业标准调整",
        usable_statuses=["explicit", "inferred"],
        clarification_template="请确认旺季日均出库量相对于平日的峰值倍数：",
        unit="倍",
        impact_on_cost="峰值产能设计、临时人力储备、设备利用率",
    ),
    CostFieldRequirement(
        field_key="labor_cost_level",
        display_name="人工成本水平",
        priority="P1",
        assumption_allowed=True,
        assumption_rule="若缺失，可按地区平均工资水平估算（华东约800-1200元/人/月），并注明假设",
        usable_statuses=["explicit", "inferred"],
        clarification_template="请确认项目所在地区的人员月均工资水平（含社保）：",
        unit="元/人/月",
        impact_on_cost="人力成本测算、OPEX年度对比",
    ),
    CostFieldRequirement(
        field_key="kpi_targets",
        display_name="KPI考核指标",
        priority="P1",
        assumption_allowed=False,
        assumption_rule="KPI影响惩罚成本和服务承诺，缺失时不得假设，必须从招标文件获取",
        usable_statuses=["explicit"],
        clarification_template="请提供完整的KPI指标列表（含目标值、考核维度、数据来源和惩罚机制）：",
        unit="",
        impact_on_cost="风险准备金、服务承诺成本、合规成本",
    ),
    CostFieldRequirement(
        field_key="penalty_rules",
        display_name="强制条款/惩罚机制",
        priority="P1",
        assumption_allowed=False,
        assumption_rule="强制条款影响合同可行性，缺失时禁止正式报价",
        usable_statuses=["explicit"],
        clarification_template="请提供招标文件中的强制条款清单及否决项：",
        unit="",
        impact_on_cost="合同可行性、风险敞口、报价上限",
    ),
    CostFieldRequirement(
        field_key="automation_expectation",
        display_name="自动化期望/水平",
        priority="P1",
        assumption_allowed=True,
        assumption_rule="若缺失，默认按人工方案（无自动化设备投入）计算，附说明",
        usable_statuses=["explicit", "inferred"],
        clarification_template="请确认客户对自动化水平的期望（高位货架/AGV/AMR/交叉带分拣等）：",
        unit="",
        impact_on_cost="CAPEX规模、设备选型、运维成本",
    ),

    # ========================================================================
    # P2 — Optimization fields: missing does not block any calculation
    # ========================================================================
    CostFieldRequirement(
        field_key="industry",
        display_name="行业",
        priority="P2",
        assumption_allowed=True,
        assumption_rule="行业信息用于参数校准，缺失不影响计算，仅影响展示说明",
        usable_statuses=["explicit", "inferred"],
        clarification_template="请确认客户所在行业：",
        unit="",
        impact_on_cost="参数校准、ROI展示说明",
    ),
    CostFieldRequirement(
        field_key="region",
        display_name="项目地区",
        priority="P2",
        assumption_allowed=True,
        assumption_rule="地区用于成本参数选择，缺失时默认华东",
        usable_statuses=["explicit", "inferred"],
        clarification_template="请确认项目所在主要城市/地区：",
        unit="",
        impact_on_cost="地区人工成本、仓租水平、地区调整系数",
    ),
    CostFieldRequirement(
        field_key="go_live_date",
        display_name="上线日期",
        priority="P2",
        assumption_allowed=True,
        assumption_rule="上线日期用于现金流规划，缺失时按合同起始日估算",
        usable_statuses=["explicit", "inferred"],
        clarification_template="请确认合同约定的系统/仓库上线日期（Go-Live）：",
        unit="",
        impact_on_cost="现金流规划、实施周期安排",
    ),
    CostFieldRequirement(
        field_key="budget_level",
        display_name="预算水平",
        priority="P2",
        assumption_allowed=True,
        assumption_rule="预算信息供参考，缺失不影响计算",
        usable_statuses=["explicit", "inferred"],
        clarification_template="请确认客户预算范围（如果有）：",
        unit="元",
        impact_on_cost="方案筛选参考、报价上限参考",
    ),
]


# Index by field_key for O(1) lookup
FIELD_REQUIREMENTS: dict[str, CostFieldRequirement] = {
    req.field_key: req for req in COST_MODEL_REQUIREMENTS
}

P0_FIELDS = [req.field_key for req in COST_MODEL_REQUIREMENTS if req.priority == "P0"]
P1_FIELDS = [req.field_key for req in COST_MODEL_REQUIREMENTS if req.priority == "P1"]
P2_FIELDS = [req.field_key for req in COST_MODEL_REQUIREMENTS if req.priority == "P2"]

# DEPRECATED v0.9: Use backend.services.parameter_service.get_assumption_defaults() instead.
# This dict is kept for backward compatibility with downstream_input_builder
# until full migration is complete.
# Assumption fallback rules for P1 fields
ASSUMPTION_TEMPLATES: dict[str, str] = {
    "sku_count": "按月均出货量÷15件/SKU/月估算（行业均值）",
    "inventory": "按日出库量×8天估算（行业平均在库天数）",
    "peak_factor": "默认取1.5倍（CNY旺季参考值），可调整",
    "labor_cost_level": "按华东地区平均工资水平估算（约8000-10000元/人/月）",
    "automation_expectation": "默认人工方案（无自动化设备），无CAPEX",
    "industry": "默认通用制造业参数",
    "region": "默认华东地区",
    "go_live_date": "默认按合同起始日",
    "budget_level": "按市场参考价估算",
}
