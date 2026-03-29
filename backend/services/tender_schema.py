"""
tender_schema.py — Field Registry, Status Enums, Section Contracts
=================================================================

Single source of truth for:
  - Canonical field definitions (FieldDef dataclass + FIELD_REGISTRY)
  - Field status taxonomy (FIELD_STATUS)
  - 13-section name contract (_SECTION_NAMES)
  - LLM JSON schema contract (_SCHEMA_CONTRACT)
  - s-key → normalized field extraction rules (_FIELD_MAP)
  - Cross-field consistency rules (_CONSISTENCY_RULES)
  - Suggested answer formats per field key (_SUGGESTED_ANSWER_FORMAT)

Version: v0.2
"""
from dataclasses import dataclass, field
from typing import Optional


# =============================================================================
# Service Scope Matrix — v0.6.4 Structured Service Definition
# =============================================================================
SERVICE_MATRIX: dict = {
    "inbound": {
        "label": "入库作业",
        "description": "货物从供应商到达仓库到完成上架的全过程",
        "services": {
            "receiving":       {"label": "收货/收货确认",  "label_en": "receiving"},
            "unloading":       {"label": "卸货",           "label_en": "unloading"},
            "quality_check":   {"label": "质量检验",       "label_en": "quality_check"},
            "putaway":         {"label": "上架/归库",      "label_en": "putaway"},
        },
    },
    "storage": {
        "label": "存储管理",
        "description": "货物在库期间的管理与保管",
        "services": {
            "pallet_storage":    {"label": "托盘位存储",      "label_en": "pallet_storage"},
            "bin_storage":       {"label": "Bin位存储",        "label_en": "bin_storage"},
            "temperature_control":{"label": "温度控制存储",    "label_en": "temperature_control"},
            "bonded_storage":    {"label": "保税仓储",        "label_en": "bonded_storage"},
        },
    },
    "outbound": {
        "label": "出库作业",
        "description": "从订单下达到货物出库的全过程",
        "services": {
            "picking":   {"label": "拣选",   "label_en": "picking"},
            "packing":   {"label": "包装",   "label_en": "packing"},
            "labeling":  {"label": "贴标",   "label_en": "labeling"},
            "loading":   {"label": "装车",   "label_en": "loading"},
            "shipping":  {"label": "发运",   "label_en": "shipping"},
        },
    },
    "value_added": {
        "label": "增值服务",
        "description": "核心仓储配送以外的增值作业",
        "services": {
            "kitting":         {"label": "Kitting/组合装配", "label_en": "kitting"},
            "repack":          {"label": "拆箱/换装",       "label_en": "repack"},
            "light_assembly":  {"label": "轻装配",          "label_en": "light_assembly"},
            "return_handling": {"label": "退货处理",        "label_en": "return_handling"},
            "cycle_count":     {"label": "库存盘点",        "label_en": "cycle_count"},
        },
    },
    "support": {
        "label": "支持服务",
        "description": "运营管理、数据与系统支持",
        "services": {
            "inventory_reporting": {"label": "库存报表",         "label_en": "inventory_reporting"},
            "system_integration":  {"label": "系统对接",         "label_en": "system_integration"},
            "data_reporting":     {"label": "数据报告/BI",      "label_en": "data_reporting"},
        },
    },
}

# Flat list of all service keys (for validation)
ALL_SERVICE_KEYS = [
    svc_key
    for category in SERVICE_MATRIX.values()
    for svc_key in category["services"]
]


# =============================================================================
# Field Priority
# =============================================================================
FIELD_PRIORITY = {
    # P0: blocking — must be present before cost model can run
    "warehouse_area": "P0",
    "total_warehouse_area": "P0",
    "dc_count": "P0",
    "daily_orders": "P0",
    "sku_count": "P0",
    "contract_years": "P0",  # 合同年限影响ROI分摊，属于P0
    # P1: important — needed for complete solution design
    "inventory": "P1",
    "service_scope": "P0",  # 与 cost_model_requirements 同步
    "kpi_targets": "P1",
    "penalty_rules": "P1",
    "peak_factor": "P1",
    "automation_expectation": "P1",
    # P2: nice-to-have
    "labor_cost_level": "P2",
    "budget_level": "P2",
    "industry": "P2",
    "region": "P2",
    "go_live_date": "P2",
}

P0_FIELDS = [k for k, v in FIELD_PRIORITY.items() if v == "P0"]
P1_FIELDS = [k for k, v in FIELD_PRIORITY.items() if v == "P1"]


# =============================================================================
# Field Status Taxonomy (Max v0.2 suggestion #4)
# =============================================================================
FIELD_STATUS = {
    "explicit":   "文件明确给出，无歧义",
    "inferred":   "可合理推断，但未经原文明确",
    "partial":   "部分信息存在，但不完整",
    "missing":   "文档中完全未提及",
    "ambiguous": "存在冲突或歧义表述",
}

STATUS_PRIORITY = {"explicit": 0, "inferred": 1, "partial": 2, "ambiguous": 3, "missing": 4}


# =============================================================================
# Field Definitions
# =============================================================================
@dataclass
class FieldDef:
    key: str
    display_name: str
    priority: str = "P2"
    impact: list = field(default_factory=list)
    tender_sections: list = field(default_factory=list)
    missing_item_labels: list = field(default_factory=list)
    description: str = ""
    expected_type: str = "any"
    validation_rules: str = ""


FIELD_REGISTRY: dict[str, FieldDef] = {
    "warehouse_area": FieldDef(
        key="warehouse_area",
        display_name="仓库面积",
        priority="P0",
        impact=["cost_model", "roi_analysis", "layout_design", "investment_plan"],
        tender_sections=["s3_warehouse_dc_list", "s12_missing"],
        missing_item_labels=["仓库总面积", "仓库面积", "DC仓库明细", "仓储面积"],
        description="投标仓库总建筑面积（平方米）",
        expected_type="int",
        validation_rules="must be positive integer, 1000-500000 sqm typical",
    ),
    "total_warehouse_area": FieldDef(
        key="total_warehouse_area",
        display_name="仓库总面积（含公摊）",
        priority="P0",
        impact=["cost_model", "layout_design", "investment_plan"],
        tender_sections=["s3_warehouse_dc_list"],
        missing_item_labels=["总面积", "总仓库面积"],
        description="仓库总面积（含卸货区、公摊等）",
        expected_type="int",
        validation_rules="must be >= warehouse_area",
    ),
    "dc_count": FieldDef(
        key="dc_count",
        display_name="DC数量",
        priority="P0",
        impact=["cost_model", "layout_design", "investment_plan"],
        tender_sections=["s3_warehouse_dc_list"],
        missing_item_labels=["DC仓库明细", "仓库数量", "DC数量"],
        description="投标覆盖的仓库/配送中心数量",
        expected_type="int",
        validation_rules="must be positive integer",
    ),
    "daily_orders": FieldDef(
        key="daily_orders",
        display_name="日均订单/出库量",
        priority="P0",
        impact=["cost_model", "labor_plan", "layout_design"],
        tender_sections=["s7_kpi_sla", "s12_missing"],
        missing_item_labels=["日出库量/订单量", "日出库量", "日均订单量", "订单量", "日均出库量"],
        description="日均出库订单数或件数（按自然日）",
        expected_type="int",
        validation_rules="must be positive integer, typically 500-200000",
    ),
    "sku_count": FieldDef(
        key="sku_count",
        display_name="SKU总数",
        priority="P0",
        impact=["layout_design", "automation_selection", "labor_plan"],
        tender_sections=["s1_project_overview", "s12_missing"],
        missing_item_labels=["SKU总数", "SKU数量", "商品品类数"],
        description="投标SKU总量",
        expected_type="int",
        validation_rules="must be positive integer",
    ),
    "inventory": FieldDef(
        key="inventory",
        display_name="库存量",
        priority="P1",
        impact=["layout_design", "investment_plan", "capacity_plan"],
        tender_sections=["s4_business_process", "s12_missing"],
        missing_item_labels=["库存量", "库存周转", "平均库存"],
        description="平均库存量（件数或板数）",
        expected_type="int",
        validation_rules="must be positive integer",
    ),
    "contract_years": FieldDef(
        key="contract_years",
        display_name="合同年限",
        priority="P0",
        impact=["cost_model", "roi_analysis", "investment_plan"],
        tender_sections=["s9_contract", "s11_risks"],
        missing_item_labels=["合同期限", "合同期", "合作年限"],
        description="合同期长度（年）",
        expected_type="int",
        validation_rules="must be 1-20",
    ),
    "service_scope": FieldDef(
        key="service_scope",
        display_name="服务范围矩阵",
        priority="P0",
        impact=["solution_design", "cost_model", "automation_selection", "labor_model"],
        tender_sections=["s2_service_scope"],
        missing_item_labels=["服务范围", "报价结构要求", "业务范围"],
        description="入库/存储/出库/增值服务/支持服务结构化矩阵",
        expected_type="dict",
        validation_rules="每个category至少包含1项服务",
    ),
    "kpi_targets": FieldDef(
        key="kpi_targets",
        display_name="KPI指标",
        priority="P1",
        impact=["solution_design", "contract_review", "risk_assessment"],
        tender_sections=["s7_kpi_sla"],
        missing_item_labels=["KPI/SLA要求", "KPI指标", "考核指标"],
        description="KPI指标清单（含目标值和惩罚机制）",
        expected_type="dict",
        validation_rules="dict of {indicator: {target, penalty}}",
    ),
    "penalty_rules": FieldDef(
        key="penalty_rules",
        display_name="强制条款/惩罚机制",
        priority="P1",
        impact=["contract_review", "risk_assessment"],
        tender_sections=["s10_mandatory_clauses"],
        missing_item_labels=["强制条款清单", "惩罚机制", "否决项", "强制条款"],
        description="招标文件中的强制条款和惩罚规则",
        expected_type="list",
        validation_rules="list of clause strings",
    ),
    "peak_factor": FieldDef(
        key="peak_factor",
        display_name="高峰系数",
        priority="P1",
        impact=["layout_design", "labor_plan", "capacity_plan"],
        tender_sections=["s6_operations"],
        missing_item_labels=["高峰系数", "峰值倍数", "旺季系数"],
        description="高峰期出库量相对于日均的倍数",
        expected_type="float",
        validation_rules="must be >= 1.0",
    ),
    "automation_expectation": FieldDef(
        key="automation_expectation",
        display_name="自动化期望",
        priority="P1",
        impact=["automation_selection", "solution_design"],
        tender_sections=["s1_project_overview", "s5_systems"],
        missing_item_labels=["自动化程度", "自动化期望", "自动化目标"],
        description="客户对自动化水平的期望或要求",
        expected_type="str",
        validation_rules="e.g. '高位货架+AGV'",
    ),
    "labor_cost_level": FieldDef(
        key="labor_cost_level",
        display_name="人工成本水平",
        priority="P2",
        impact=["cost_model", "labor_plan"],
        tender_sections=["s8_commercial", "s6_operations"],
        missing_item_labels=["人工成本", "薪资水平", "人力成本"],
        description="当地人工/薪资水平参考",
        expected_type="str",
        validation_rules="e.g. '6000-8000元/月'",
    ),
    "budget_level": FieldDef(
        key="budget_level",
        display_name="预算水平",
        priority="P2",
        impact=["cost_model", "roi_analysis"],
        tender_sections=["s8_commercial"],
        missing_item_labels=["预算", "预算规模", "投资预算"],
        description="客户预算范围（如果有）",
        expected_type="str",
        validation_rules="e.g. '500-800万'",
    ),
    "industry": FieldDef(
        key="industry",
        display_name="行业",
        priority="P2",
        impact=[],
        tender_sections=["s1_project_overview"],
        missing_item_labels=["行业", "客户行业"],
        description="客户所在行业",
        expected_type="str",
    ),
    "region": FieldDef(
        key="region",
        display_name="地区",
        priority="P2",
        impact=[],
        tender_sections=["s1_project_overview", "s3_warehouse_dc_list"],
        missing_item_labels=["地区", "项目地区", "城市"],
        description="项目所在地区/城市",
        expected_type="str",
    ),
    "go_live_date": FieldDef(
        key="go_live_date",
        display_name="上线日期",
        priority="P2",
        impact=["project_plan"],
        tender_sections=["s9_contract"],
        missing_item_labels=["上线日期", "启动日期", "Go-Live"],
        description="合同约定的系统/仓库上线日期",
        expected_type="str",
        validation_rules="YYYY-MM-DD or 'YYYY年MM月'",
    ),
}


# =============================================================================
# Suggested answer formats per field key (used in clarification questions)
# =============================================================================
_SUGGESTED_ANSWER_FORMAT: dict[str, str] = {
    "dc_count": "数字 + 各仓库所在城市 + 面积（平方米）",
    "daily_orders": "数值 + 单位（件/单）+ 口径说明（自然日/工作日）+ 峰值倍数",
    "warehouse_area": "总面积（平方米）+ 各仓库分别面积明细",
    "sku_count": "SKU总数 + ABC分类占比（A类X%/B类Y%/C类Z%）",
    "kpi_targets": "指标名 + 目标值 + 考核维度 + 数据来源 + 惩罚规则",
    "penalty_rules": "条款内容 + 类型（否决项/惩罚项/义务项）",
    "service_scope": "报价结构说明（元/平米/月 or 元/件）+ 各服务单价区间",
    "inventory": "平均库存量 + 峰值 + 是否含VMI + VMI占比",
}


def get_suggested_answer_format(field_key: str) -> str:
    return _SUGGESTED_ANSWER_FORMAT.get(field_key, "具体数值或明细")


# =============================================================================
# Canonical 13-section names
# =============================================================================
SECTION_NAMES: list[str] = [
    "project_overview",        # 1. 项目概览
    "scope_of_work",           # 2. 服务范围
    "warehouse_network",        # 3. 仓库DC信息
    "business_process",         # 4. 业务操作流程
    "systems_and_interfaces",   # 5. 系统与接口
    "staffing_and_operation",  # 6. 人员与运营要求
    "kpi_sla",                # 7. KPI/SLA要求
    "commercial_and_pricing",  # 8. 商务与报价
    "contract_terms",           # 9. 合同周期与里程碑
    "mandatory_terms",          # 10. 强制条款否决项
    "risks_and_ambiguities",  # 11. 风险与歧义
    "missing_information",      # 12. 缺失信息与待确认项
    "downstream_guidance",     # 13. 下游指导说明
]


# =============================================================================
# Schema Contract — expected types per s-key in LLM JSON output
# =============================================================================
SCHEMA_CONTRACT: dict = {
    "s1_project_overview":    {"type": dict, "required_keys": ["client_name", "contract_period"]},
    "s2_service_scope":     {"type": dict, "required_keys": []},
    "s3_warehouse_dc_list": {"type": list, "item_type": dict, "allow_empty": True},
    "s4_business_process":   {"type": dict, "required_keys": []},
    "s5_systems":           {"type": dict, "required_keys": []},
    "s6_operations":        {"type": dict, "required_keys": []},
    "s7_kpi_sla":           {"type": list, "item_type": dict, "allow_empty": True},
    "s8_commercial":         {"type": dict, "required_keys": []},
    "s9_contract":          {"type": dict, "required_keys": []},
    "s10_mandatory_clauses": {"type": list, "item_type": dict, "allow_empty": True},
    "s11_risks":            {"type": dict, "required_keys": []},
    "s12_missing":          {"type": dict, "required_keys": []},
    "s13_downstream_inputs": {"type": dict, "required_keys": []},
}


# =============================================================================
# Field Map — s-key → normalized field extraction rules
# =============================================================================
FIELD_MAP: dict = {
    "s3_warehouse_dc_list": {
        "dc_count":             {"keys": [], "count": True},
        "total_warehouse_area": {"keys": ["area_sqm"], "op": "sum", "unit": "sqm"},
        "warehouse_area":        {"keys": ["area_sqm"], "op": "sum", "unit": "sqm"},
    },
    # v0.6.4: preserve full structure instead of flattening
    # Legacy format: {warehousing: [], distribution: [], value_added: []}
    # New format:    {inbound: [], storage: [], outbound: [], value_added: [], support: []}
    "s2_service_scope": {
        "service_scope": {"keys": [], "op": "preserve"},
    },
    "s9_contract": {
        "contract_years": {"keys": ["contract_years"], "type": int, "range": (1, 20)},
    },
    "s7_kpi_sla": {
        "kpi_targets":  {"keys": [], "kpi_list": True},
        "daily_orders": {"keys": ["indicator", "target"], "op": "extract_orders"},
    },
    "s10_mandatory_clauses": {
        "penalty_rules": {"keys": ["clause"], "op": "collect"},
    },
    "s6_operations": {
        "peak_factor": {"keys": ["peak_season_notes"], "op": "extract_factor"},
    },
    "s12_missing": {
        "_assumptions": {"keys": ["assumptions"], "op": "store"},
    },
}


# =============================================================================
# Cross-field consistency rules
# =============================================================================
CONSISTENCY_RULES: list = [
    {
        "rule": "dc_area_sum",
        "check": "total_warehouse_area",
        "fields": ["dc_count", "total_warehouse_area"],
        "condition": "dc_count > 0 AND total_warehouse_area == 0",
        "action": "mark_partial",
    },
    {
        "rule": "orders_vs_kpi",
        "check": "daily_orders",
        "fields": ["daily_orders", "kpi_targets"],
        "condition": "daily_orders has value but kpi_targets missing",
        "action": "flag_inconsistency",
    },
]


# =============================================================================
# Helper functions
# =============================================================================

def resolve_missing_label(label: str) -> Optional[str]:
    """Map a missing item display label to its canonical field key, or None."""
    for fdef in FIELD_REGISTRY.values():
        if label in fdef.missing_item_labels:
            return fdef.key
    return None


def get_p0_fields() -> list[str]:
    return [k for k, f in FIELD_REGISTRY.items() if f.priority == "P0"]


def get_p1_fields() -> list[str]:
    return [k for k, f in FIELD_REGISTRY.items() if f.priority == "P1"]


def get_field_def(key: str) -> Optional[FieldDef]:
    return FIELD_REGISTRY.get(key)


def validate_field_object(key: str, obj: dict) -> list[dict]:
    """Validate a field object has all required keys + reasonable values. Returns errors."""
    errors = []
    required_keys = {"value", "status", "source_basis", "section", "priority", "impact"}
    actual_keys = set(obj.keys())
    missing = required_keys - actual_keys
    if missing:
        errors.append({"field": key, "severity": "ERROR",
                       "message": "missing keys: " + ", ".join(missing)})
    fdef = FIELD_REGISTRY.get(key)
    if fdef and obj.get("value") is not None:
        expected = fdef.expected_type
        val = obj["value"]
        if expected == "int" and not isinstance(val, int):
            if not (isinstance(val, float) and val.is_integer()):
                errors.append({"field": key, "severity": "WARN",
                               "message": f"expected int, got {type(val).__name__}"})
        elif expected == "float" and not isinstance(val, (int, float)):
            errors.append({"field": key, "severity": "WARN",
                           "message": f"expected float, got {type(val).__name__}"})
        if key == "contract_years" and isinstance(val, (int, float)):
            if not (1 <= val <= 20):
                errors.append({"field": key, "severity": "WARN",
                               "message": f"contract_years {val} outside [1,20] range"})
        if key in ("daily_orders", "warehouse_area", "dc_count", "sku_count") and isinstance(val, (int, float)):
            if val <= 0:
                errors.append({"field": key, "severity": "WARN",
                               "message": f"{key} must be positive, got {val}"})
    return errors
