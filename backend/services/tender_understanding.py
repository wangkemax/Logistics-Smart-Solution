# Tender Understanding Service
import os, re, json, sys
from pathlib import Path
from datetime import datetime
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Field Registry — Canonical field metadata
# =============================================================================
"""
Field Registry
==============
All extractable fields are defined here with their canonical metadata.
This is the single source of truth for:
  - Field display names and descriptions
  - Priority (P0/P1/P2) and downstream impact
  - Mapping between tender section labels and field keys
  - Missing item label → field key resolution
Usage:
  from backend.services.tender_understanding import FIELD_REGISTRY
  field = FIELD_REGISTRY.get("warehouse_area")
  print(field.display_name)  # "仓库面积"
  print(field.priority)       # "P0"
  print(field.impact)         # ["cost_model", "roi_analysis", ...]
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FieldDef:
    key: str                       # canonical field key, e.g. "warehouse_area"
    display_name: str              # human-readable Chinese name
    priority: str = "P2"           # P0 | P1 | P2
    impact: list = field(default_factory=list)   # downstream modules
    tender_sections: list = field(default_factory=list)  # which s1-s13 this maps to
    missing_item_labels: list = field(default_factory=list)  # alternative labels used in missing_p0/missing_p1
    description: str = ""          # what this field represents
    expected_type: str = "any"     # int | float | str | list | dict | bool
    validation_rules: str = ""     # e.g. "must be positive", "must be 1-20 years"


FIELD_REGISTRY: dict[str, FieldDef] = {
    # --- P0: blocking fields (required for cost model) ---
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
    # --- P1: important fields ---
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
        priority="P1",
        impact=["cost_model", "roi_analysis", "investment_plan"],
        tender_sections=["s9_contract", "s11_risks"],
        missing_item_labels=["合同期限", "合同期", "合作年限"],
        description="合同期长度（年）",
        expected_type="int",
        validation_rules="must be 1-20",
    ),
    "service_scope": FieldDef(
        key="service_scope",
        display_name="服务范围明细",
        priority="P1",
        impact=["solution_design", "cost_model", "automation_selection"],
        tender_sections=["s2_service_scope"],
        missing_item_labels=["服务范围", "报价结构要求", "业务范围"],
        description="仓储/配送/增值服务具体项目清单",
        expected_type="list",
        validation_rules="at least 1 item",
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
    # --- P2: nice-to-have ---
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


def resolve_missing_label(label: str) -> Optional[str]:
    """Map a missing item display label to its canonical field key, or None."""
    for fdef in FIELD_REGISTRY.values():
        if label in fdef.missing_item_labels:
            return fdef.key
    return None


def get_p0_fields() -> list[str]:
    return [k for k, f in FIELD_REGISTRY.items() if f.priority == "P0"]


def get_field_def(key: str) -> Optional[FieldDef]:
    return FIELD_REGISTRY.get(key)


def validate_field_object(key: str, obj: dict) -> list[dict]:
    """Validate a field object has all required keys + reasonable values. Returns errors."""
    errors = []
    required_keys = {"value", "status", "source_basis", "section", "priority", "impact"}
    actual_keys = set(obj.keys())
    missing = required_keys - actual_keys
    if missing:
        errors.append({"field": key, "severity": "ERROR", "message": "missing keys: " + ", ".join(missing)})
    fdef = FIELD_REGISTRY.get(key)
    if fdef and obj.get("value") is not None:
        # Type check
        expected = fdef.expected_type
        val = obj["value"]
        if expected == "int" and not isinstance(val, int):
            if not (isinstance(val, float) and val.is_integer()):
                errors.append({"field": key, "severity": "WARN", "message": f"expected int, got {type(val).__name__}"})
        elif expected == "float" and not isinstance(val, (int, float)):
            errors.append({"field": key, "severity": "WARN", "message": f"expected float, got {type(val).__name__}"})
        # Range check
        if key == "contract_years" and isinstance(val, (int, float)):
            if not (1 <= val <= 20):
                errors.append({"field": key, "severity": "WARN", "message": f"contract_years {val} outside [1,20] range"})
        if key in ("daily_orders", "warehouse_area", "dc_count", "sku_count") and isinstance(val, (int, float)):
            if val <= 0:
                errors.append({"field": key, "severity": "WARN", "message": f"{key} must be positive, got {val}"})
    return errors


# =============================================================================
_FIXED_SECTIONS = """
## 1. 项目概览
- 招标方: [客户名称，未提供则写"未提供"]
- 合同期: [合同期限，未提供则写"未提供"]
- 标的范围: [标的范围，未提供则写"未提供"]
- 付款账期: [天数+条件，未提供则写"未提供"]

## 2. 服务范围
- 仓储服务 [每项一行，如无则写"未提供"]
- 配送服务 [每项一行，如无则写"未提供"]
- 增值服务 [如贴标/组包/退货处理等，如无则写"未提供"]

## 3. 仓库DC信息
[表格: 代码 | 名称 | 面积 | 日均处理能力 | 备注]

## 4. 业务流程要求
- 入库流程 [未提供则写"未提供"]
- 出库流程 [未提供则写"未提供"]
- 退货与逆向物流 [未提供则写"未提供"]

## 5. 系统与接口要求
- 必备系统 [WMS/SAP/TMS等，未提供则写"未提供"]
- 数据对接要求 [API/格式要求，未提供则写"未提供"]

## 6. 人员与运营要求
- 人员资质要求 [叉车证/健康证等，未提供则写"未提供"]
- 旺季运营要求 [CNY/节假日扩产要求，未提供则写"未提供"]

## 7. KPI/SLA要求
[表格: 指标 | 目标值 | 考核维度 | 惩罚机制]

## 8. 商务与报价相关
- 报价结构要求 [未提供则写"未提供"]
- 报价约束 [未提供则写"未提供"]

## 9. 合同周期与里程碑
- 合同年限 [年数，未提供则写"未提供"]
- 关键里程碑 [未提供则写"未提供"]

## 10. 强制条款否决项
[表格: 编号 | 条款 | 说明，无则写"未提供"]

## 11. 风险与歧义
- 不明确条款 [原文+问题，无则写"无"]
- 矛盾条款 [条款A vs 条款B，无则写"无"]

## 12. 缺失信息与待确认项
- 缺失定量数据 [每项一行]
- 推断项须标注 [推断项 | 依据 | 置信度]

## 13. 给下游模块的建议输入
[描述给投标策略/成本测算/合同审核/KPI方案模块的输入]
"""

_ANALYSIS_PROMPT = (
    "你是一家专业的物流投标需求分析专家。\n\n"
    "【第一步】按以下13个section顺序输出Markdown分析报告，必须覆盖全部section，无内容也要写标题+未提供：\n\n"
    + _FIXED_SECTIONS.strip() + "\n\n"
    "【第二步】在Markdown之后输出JSON（不得省略任何键）：\n\n"
    "```json\n"
    '{\n'
    '  "s1_project_overview": {"client_name":"","contract_period":"","bid_scope":"","payment_days":null,"tax_note":""},\n'
    '  "s2_service_scope": {"warehousing":[],"distribution":[],"value_added":[]},\n'
    '  "s3_warehouse_dc_list": [{"code":"","name":"","area_sqm":null,"daily_capacity":null,"notes":""}],\n'
    '  "s4_business_process": {"inbound":null,"outbound":null,"returns":null},\n'
    '  "s5_systems": {"required_systems":[],"integration_requirements":null},\n'
    '  "s6_operations": {"staff_requirements":null,"equipment_requirements":null,"peak_season_notes":null},\n'
    '  "s7_kpi_sla": [{"indicator":"","target":"","dimension":"","data_source":"","penalty":""}],\n'
    '  "s8_commercial": {"pricing_structure":null,"pricing_constraints":null,"value_added_pricing":null},\n'
    '  "s9_contract": {"contract_years":null,"milestones":null,"termination_clauses":null},\n'
    '  "s10_mandatory_clauses": [{"code":"","clause":"","description":""}],\n'
    '  "s11_risks": {"unclear_clauses":[],"conflicting_clauses":[]},\n'
    '  "s12_missing": {"missing_quantitative_data":[],"assumptions":[]},\n'
    '  "s13_downstream_inputs": {"bid_strategy":"","cost_boundary":"","contract_review":"","kpi_plan":""}\n'
    "}\n"
    "```\n\n"
    "原则：1.不得编造 2.不得默认补值(null/未提供) 3.推断项须标注 4.矛盾条款须列入s11 5.先Markdown后JSON\n\n"
    "招标文件：\n---\n{tender_text}\n---"
)

def _get_api_key():
    key = os.getenv("MINIMAX_API_KEY") or os.getenv("OPENAI_API_KEY")
    if key:
        return key
    try:
        for line in (PROJECT_ROOT / ".env").read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if k in ("MINIMAX_API_KEY", "OPENAI_API_KEY") and not v.startswith("your"):
                    os.environ[k] = v
                    return v
    except Exception:
        pass
    return None

def _call_llm(prompt, timeout=45):
    key = _get_api_key()
    if not key:
        return None
    url = "https://api.minimaxi.com/anthropic/v1/messages"
    model = "MiniMax-M2.7-highspeed"
    if not key.startswith("sk-api-"):
        url = "https://api.openai.com/v1/messages"
        model = "gpt-4o-mini"
    import urllib.request
    req = urllib.request.Request(
        url,
        data=json.dumps({"model": model, "max_tokens": 4096,
                         "messages": [{"role": "user", "content": prompt}]}).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                 "anthropic-version": "2023-06-01"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read())
            content = result.get("content", [])
            if isinstance(content, list):
                text = "\n".join(b.get("text", "") for b in content if b.get("type") == "text")
            else:
                text = str(content)
            return {"raw": text.strip()}
    except Exception as e:
        print("[tender_understanding] LLM call failed: " + str(e))
        return None

def _parse_response(raw):
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if m:
        try:
            data = json.loads(m.group(1).strip())
            if isinstance(data, dict):
                return raw[:m.start()].strip(), data
        except json.JSONDecodeError:
            pass
    bare = re.search(r"\{[\s\S]*\}", raw)
    if bare:
        try:
            data = json.loads(bare.group(0))
            if isinstance(data, dict):
                return raw[:bare.start()].strip(), data
        except json.JSONDecodeError:
            pass
    return raw.strip(), {"_parse_error": "JSON extraction failed"}

def analyze_tender_document(text):
    if not text or len(text.strip()) < 20:
        return _empty_result()
    text = text[-12000:] if len(text) > 12000 else text
    result = _call_llm(_ANALYSIS_PROMPT.format(tender_text=text))
    if result is None:
        return _empty_result()
    report, structured = _parse_response(result["raw"])
    meta = _build_metadata(structured)
    return {"analysis_report": report, "structured": structured,
            "extraction_metadata": meta, "raw_llm_response": result["raw"]}

def _empty_result():
    return {
        "analysis_report": "**分析未能完成**：招标文件内容过短或解析失败。",
        "structured": {},
        "extraction_metadata": {"confidence": 0.0, "missing_p0": ["招标文件内容缺失"], "missing_p1": []},
        "raw_llm_response": ""
    }

def _build_metadata(s):
    m0, m1 = [], []
    if isinstance(s, dict):
        if not s.get("s3_warehouse_dc_list"):
            m0.append("DC仓库明细")
        if not s.get("s4_business_process", {}).get("outbound"):
            m0.append("日出库量/订单量")
        if not s.get("s7_kpi_sla"):
            m1.append("KPI/SLA要求")
        if not s.get("s10_mandatory_clauses"):
            m1.append("强制条款清单")
    sects = ["s1_project_overview","s2_service_scope","s3_warehouse_dc_list",
             "s4_business_process","s5_systems","s6_operations","s7_kpi_sla",
             "s8_commercial","s9_contract","s10_mandatory_clauses",
             "s11_risks","s12_missing","s13_downstream_inputs"]
    filled = sum(1 for x in sects if s.get(x) and s.get(x) not in ({},[],""))
    return {"confidence": filled/len(sects), "missing_p0": m0, "missing_p1": m1,
            "analysis_timestamp": datetime.now().isoformat()}

# =============================================================================
# Schema Contract — defines expected types/ranges for each s-key in LLM JSON output
# =============================================================================
_SCHEMA_CONTRACT = {
    "s1_project_overview":    {"type": dict, "required_keys": ["client_name","contract_period"]},
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
# Field Name Mapping — s-key → normalized field extraction rules
# =============================================================================
_FIELD_MAP = {
    # s-key: {target_field: {extract_from_key, transform, unit, range_check}}
    "s3_warehouse_dc_list": {
        "dc_count":            {"keys": [], "count": True},
        "total_warehouse_area": {"keys": ["area_sqm"], "op": "sum", "unit": "sqm"},
        "warehouse_area":       {"keys": ["area_sqm"], "op": "sum", "unit": "sqm"},
    },
    "s2_service_scope": {
        "service_scope": {"keys": ["warehousing","distribution","value_added"], "op": "merge_unique"},
    },
    "s9_contract": {
        "contract_years": {"keys": ["contract_years"], "type": int, "range": (1, 20)},
    },
    "s7_kpi_sla": {
        "kpi_targets": {"keys": [], "kpi_list": True},
        "daily_orders": {"keys": ["indicator","target"], "op": "extract_orders"},
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
# Cross-field consistency rules — checked during normalization
# =============================================================================
_CONSISTENCY_RULES = [
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


def _validate_structured_json(structured: dict) -> list[dict]:
    """
    Validate LLM output against schema contract before normalization.
    Returns list of validation errors (empty = valid).
    Each error: {section, expected, actual, severity}
    """
    errors = []
    if not isinstance(structured, dict):
        return [{"section": "root", "expected": "dict", "actual": type(structured).__name__,
                 "severity": "ERROR", "message": "LLM output is not a JSON object"}]

    for s_key, contract in _SCHEMA_CONTRACT.items():
        value = structured.get(s_key)
        expected_type = contract["type"]

        # Type check
        if value is None:
            # Accept None if allow_empty is set (for list fields)
            if contract.get("allow_empty") and expected_type == list:
                continue
            errors.append({
                "section": s_key, "expected": expected_type.__name__,
                "actual": "null", "severity": "WARN",
                "message": f"{s_key} is missing or null"
            })
            continue

        if not isinstance(value, expected_type):
            errors.append({
                "section": s_key, "expected": expected_type.__name__,
                "actual": type(value).__name__, "severity": "ERROR",
                "message": f"{s_key} should be {expected_type.__name__}, got {type(value).__name__}"
            })
            continue

        # Item type check for lists
        if expected_type == list:
            item_type = contract.get("item_type")
            if item_type and item_type == dict:
                for i, item in enumerate(value):
                    if not isinstance(item, dict):
                        errors.append({
                            "section": s_key, "expected": f"list[dict], item[{i}]",
                            "actual": type(item).__name__, "severity": "ERROR",
                            "message": f"{s_key}[{i}] should be dict"
                        })

        # Required keys for dicts
        required_keys = contract.get("required_keys", [])
        for rk in required_keys:
            if not isinstance(value, dict) or rk not in value:
                errors.append({
                    "section": s_key, "expected": f"key '{rk}' present",
                    "actual": "missing", "severity": "WARN",
                    "message": f"{s_key} missing required key '{rk}'"
                })

    # Check for unexpected keys
    expected_keys = set(_SCHEMA_CONTRACT.keys())
    actual_keys = set(structured.keys())
    extra = actual_keys - expected_keys
    for k in extra:
        errors.append({
            "section": k, "expected": "not in schema",
            "actual": "present", "severity": "INFO",
            "message": f"Unexpected key '{k}' in LLM output (ignored)"
        })

    return errors


# =============================================================================
# Schema Validation + Field Map
# =============================================================================
_SCHEMA_CONTRACT = {
    "s1_project_overview":    {"type": "dict"},
    "s2_service_scope":     {"type": "dict"},
    "s3_warehouse_dc_list": {"type": "list"},
    "s4_business_process":   {"type": "dict"},
    "s5_systems":           {"type": "dict"},
    "s6_operations":        {"type": "dict"},
    "s7_kpi_sla":           {"type": "list"},
    "s8_commercial":         {"type": "dict"},
    "s9_contract":          {"type": "dict"},
    "s10_mandatory_clauses": {"type": "list"},
    "s11_risks":           {"type": "dict"},
    "s12_missing":          {"type": "dict"},
    "s13_downstream_inputs": {"type": "dict"},
}

def _validate_structured_json(structured):
    errors = []
    if not isinstance(structured, dict):
        return [{"section": "root", "error": "LLM output is not a JSON object", "severity": "ERROR"}]
    for key, spec in _SCHEMA_CONTRACT.items():
        value = structured.get(key)
        expected = spec["type"]
        if value is None:
            continue
        if expected == "list" and not isinstance(value, list):
            errors.append({"section": key, "error": "should be list, got " + type(value).__name__, "severity": "ERROR"})
        elif expected == "dict" and not isinstance(value, dict):
            errors.append({"section": key, "error": "should be dict, got " + type(value).__name__, "severity": "ERROR"})
    return errors


# New normalize_extracted_fields with schema validation + field priority/impact

_SCHEMA_CONTRACT = {
    "s1_project_overview":    {"type": "dict"},
    "s2_service_scope":     {"type": "dict"},
    "s3_warehouse_dc_list": {"type": "list"},
    "s4_business_process":   {"type": "dict"},
    "s5_systems":           {"type": "dict"},
    "s6_operations":        {"type": "dict"},
    "s7_kpi_sla":           {"type": "list"},
    "s8_commercial":         {"type": "dict"},
    "s9_contract":          {"type": "dict"},
    "s10_mandatory_clauses": {"type": "list"},
    "s11_risks":           {"type": "dict"},
    "s12_missing":          {"type": "dict"},
    "s13_downstream_inputs": {"type": "dict"},
}

def _validate_structured_json(structured):
    errors = []
    if not isinstance(structured, dict):
        return [{"section": "root", "error": "LLM output is not a JSON object", "severity": "ERROR"}]
    for key, spec in _SCHEMA_CONTRACT.items():
        value = structured.get(key)
        expected = spec["type"]
        if value is None:
            continue
        if expected == "list" and not isinstance(value, list):
            errors.append({"section": key, "error": "should be list, got " + type(value).__name__, "severity": "ERROR"})
        elif expected == "dict" and not isinstance(value, dict):
            errors.append({"section": key, "error": "should be dict, got " + type(value).__name__, "severity": "ERROR"})
    return errors


# New normalize_extracted_fields with schema validation + field priority/impact

_SCHEMA_CONTRACT = {
    "s1_project_overview":    {"type": "dict"},
    "s2_service_scope":     {"type": "dict"},
    "s3_warehouse_dc_list": {"type": "list"},
    "s4_business_process":   {"type": "dict"},
    "s5_systems":           {"type": "dict"},
    "s6_operations":        {"type": "dict"},
    "s7_kpi_sla":           {"type": "list"},
    "s8_commercial":         {"type": "dict"},
    "s9_contract":          {"type": "dict"},
    "s10_mandatory_clauses": {"type": "list"},
    "s11_risks":           {"type": "dict"},
    "s12_missing":          {"type": "dict"},
    "s13_downstream_inputs": {"type": "dict"},
}

def _validate_structured_json(structured):
    errors = []
    if not isinstance(structured, dict):
        return [{"section": "root", "error": "LLM output is not a JSON object", "severity": "ERROR"}]
    for key, spec in _SCHEMA_CONTRACT.items():
        value = structured.get(key)
        expected = spec["type"]
        if value is None:
            continue
        if expected == "list" and not isinstance(value, list):
            errors.append({"section": key, "error": "should be list, got " + type(value).__name__, "severity": "ERROR"})
        elif expected == "dict" and not isinstance(value, dict):
            errors.append({"section": key, "error": "should be dict, got " + type(value).__name__, "severity": "ERROR"})
    return errors


def normalize_extracted_fields(analysis_result):
    s = analysis_result.get("structured", {})
    meta = analysis_result.get("extraction_metadata", {})

    schema_errors = _validate_structured_json(s)

    def fld(value, status, basis, section="", priority="P2", impact=None):
        return {"value": value, "status": status, "source_basis": basis,
                "section": section, "priority": priority, "impact": impact or []}

    p = {
        "warehouse_area":          fld(None,"missing","文档未提供仓库面积","","P0",["cost_model","roi_analysis","layout_design","investment_plan"]),
        "dc_count":             fld(None,"missing","文档未提供DC数量","","P0",["cost_model","layout_design","investment_plan"]),
        "daily_orders":          fld(None,"missing","文档未提供日订单量","","P0",["cost_model","labor_plan","layout_design"]),
        "sku_count":             fld(None,"missing","文档未提供SKU数量","","P0",["layout_design","automation_selection","labor_plan"]),
        "inventory":             fld(None,"missing","文档未提供库存量","","P1",["layout_design","investment_plan","capacity_plan"]),
        "automation_expectation": fld(None,"missing","文档未提供自动化期望","","P1",["automation_selection","solution_design"]),
        "contract_years":        fld(None,"missing","文档未提供合同年限","","P1",["cost_model","roi_analysis","investment_plan"]),
        "service_scope":          fld([],"missing","文档未提供服务范围明细","","P1",["solution_design","cost_model","automation_selection"]),
        "kpi_targets":          fld({},"missing","文档未提供KPI指标","","P1",["solution_design","contract_review","risk_assessment"]),
        "penalty_rules":          fld([],"missing","文档未提供惩罚机制","","P1",["contract_review","risk_assessment"]),
        "peak_factor":            fld(None,"missing","文档未提供高峰系数","","P1",["layout_design","labor_plan","capacity_plan"]),
        "labor_cost_level":      fld(None,"missing","文档未提供人工成本水平","","P2",["cost_model","labor_plan"]),
        "budget_level":          fld(None,"missing","文档未提供预算水平","","P2",["cost_model","roi_analysis"]),
        "industry":             fld(None,"missing","文档未提供行业信息","","P2",[]),
        "region":              fld(None,"missing","文档未提供地区信息","","P2",[]),
        "go_live_date":        fld(None,"missing","文档未提供上线日期","","P2",["project_plan"]),
        "total_warehouse_area":  fld(None,"missing","文档未提供总仓库面积","","P0",["cost_model","layout_design","investment_plan"]),
        "extraction_confidence": meta.get("confidence", 0.0),
        "missing_p0": meta.get("missing_p0", []),
        "missing_p1": meta.get("missing_p1", []),
        "analysis_report": analysis_result.get("analysis_report", ""),
        "_schema_validation_errors": schema_errors,
    }

    dcs = s.get("s3_warehouse_dc_list", [])
    if isinstance(dcs, list) and dcs:
        areas = []
        for dc in dcs:
            if isinstance(dc, dict) and dc.get("area_sqm") is not None:
                try:
                    areas.append(int(float(dc["area_sqm"])))
                except:
                    pass
        if areas:
            total = sum(areas)
            all_have = all(
                (isinstance(dc.get("area_sqm"), (int, float)) and dc.get("area_sqm") is not None
                 for dc in dcs if isinstance(dc, dict))
            )
            status = "explicit" if all_have else "partial"
            basis = "从s3_warehouse_dc_list提取，共" + str(len(dcs)) + "个仓库，" + str(len(areas)) + "个有面积，总计" + str(total) + "平米"
            p["total_warehouse_area"] = fld(total, status, basis, "仓库DC信息", "P0", ["cost_model","layout_design","investment_plan"])
            p["warehouse_area"] = fld(total, status, basis, "仓库DC信息", "P0", ["cost_model","roi_analysis","layout_design","investment_plan"])
            p["dc_count"] = fld(len(dcs), "explicit", "从s3_warehouse_dc_list明确提取，共" + str(len(dcs)) + "个DC", "仓库DC信息", "P0", ["cost_model","layout_design","investment_plan"])

    svc = s.get("s2_service_scope", {})
    if isinstance(svc, dict):
        all_svc = []
        for key in ("warehousing", "distribution", "value_added"):
            items = svc.get(key, [])
            if isinstance(items, list):
                all_svc.extend(items)
        if all_svc:
            uniq = list(set(all_svc))
            p["service_scope"] = fld(uniq, "explicit", "从s2_service_scope提取，共" + str(len(uniq)) + "项服务", "服务范围", "P1", ["solution_design","cost_model","automation_selection"])

    c9 = s.get("s9_contract", {})
    c11 = s.get("s11_risks", {})
    if isinstance(c9, dict) and c9.get("contract_years") is not None:
        cy = c9["contract_years"]
        conflicts = []
        if isinstance(c11, dict):
            for c in c11.get("conflicting_clauses", []):
                if isinstance(c, dict) and any(x in str(c) for x in ("合同", "年限", "期")):
                    conflicts.append(str(c))
        if conflicts:
            p["contract_years"] = fld(None, "ambiguous", "s9有值但s11发现冲突: " + conflicts[0], "合同周期与里程碑", "P1", ["cost_model","roi_analysis","investment_plan"])
        elif isinstance(cy, (int, float)) and 1 <= cy <= 20:
            p["contract_years"] = fld(int(cy), "explicit", "从s9_contract.contract_years明确提取，合同期" + str(int(cy)) + "年", "合同周期与里程碑", "P1", ["cost_model","roi_analysis","investment_plan"])
        elif isinstance(cy, str) and cy not in ("未提供", ""):
            m = re.search(r"(\d+)\s*年", cy)
            if m:
                p["contract_years"] = fld(int(m.group(1)), "inferred", "从s9_contract.contract_years字符串解析: " + cy, "合同周期与里程碑", "P1", ["cost_model","roi_analysis"])

    kpis = s.get("s7_kpi_sla", [])
    if isinstance(kpis, list) and kpis:
        kd = {}
        for kpi in kpis:
            if isinstance(kpi, dict) and kpi.get("indicator"):
                kd[kpi["indicator"]] = {"target": kpi.get("target"), "penalty": kpi.get("penalty", "无明确惩罚")}
        if kd:
            p["kpi_targets"] = fld(kd, "explicit", "从s7_kpi_sla提取，共" + str(len(kd)) + "项KPI", "KPI/SLA要求", "P1", ["solution_design","contract_review","risk_assessment"])
            for kpi in kpis:
                ind = kpi.get("indicator", "")
                if any(x in ind for x in ("日出库", "日均", "日订单", "出库量", "订单量")):
                    tgt = kpi.get("target")
                    if tgt is not None:
                        try:
                            cleaned = re.sub(r"[^\d.]", "", str(tgt))
                            num = int(float(cleaned))
                            if num > 0:
                                p["daily_orders"] = fld(num, "inferred", "从s7_kpi_sla指标" + ind + "推断，目标值: " + str(tgt), "KPI/SLA要求", "P0", ["cost_model","labor_plan","layout_design"])
                                break
                        except:
                            pass

    mc = s.get("s10_mandatory_clauses", [])
    if isinstance(mc, list) and mc:
        clauses = [m.get("clause", "") for m in mc if isinstance(m, dict) and m.get("clause")]
        if clauses:
            p["penalty_rules"] = fld(clauses, "explicit", "从s10_mandatory_clauses提取，共" + str(len(clauses)) + "条强制条款", "强制条款否决项", "P1", ["contract_review","risk_assessment"])

    ops = s.get("s6_operations", {})
    if isinstance(ops, dict) and ops.get("peak_season_notes"):
        notes = str(ops["peak_season_notes"])
        if notes not in ("未提供", ""):
            m = re.search(r"(\d+(?:\.\d+)?)\s*[~-]?(?:(?:~|～)?(\d+(?:\.\d+)?))?\s*倍", notes)
            if m:
                p["peak_factor"] = fld(float(m.group(1)), "inferred", "从s6_operations.peak_season_notes推断高峰系数: " + notes, "人员与运营要求", "P1", ["layout_design","labor_plan","capacity_plan"])

    s12 = s.get("s12_missing", {})
    if isinstance(s12, dict):
        for ass in s12.get("assumptions", []):
            if isinstance(ass, dict):
                item = ass.get("item", "")
                basis = ass.get("basis", "")
                conf = ass.get("confidence", "低")
                status = "inferred" if conf in ("高", "中") else "partial"
                if any(x in item for x in ("面积", "area")):
                    m2 = re.search(r"(\d+)", item)
                    if m2:
                        p["warehouse_area"] = fld(int(m2.group(1)), status, "s12_missing假设: " + item + "，依据: " + basis + "，置信度: " + conf, "缺失信息与待确认项", "P0", ["cost_model","layout_design"])
                elif any(x in item for x in ("订单", "日均", "日出库")):
                    m2 = re.search(r"(\d+)", item)
                    if m2:
                        p["daily_orders"] = fld(int(m2.group(1)), status, "s12_missing假设: " + item + "，依据: " + basis + "，置信度: " + conf, "缺失信息与待确认项", "P0", ["cost_model","labor_plan"])

    return p

def compute_analysis_quality_score(profile):
    traces = profile.get("_field_traces", {})
    if not traces:
        traces = {k: v for k, v in profile.items()
                 if isinstance(v, dict) and "status" in v and "value" in v and not k.startswith("_")}

    def has_val(name):
        e = traces.get(name, {})
        return isinstance(e, dict) and e.get("value") is not None

    p0 = ["warehouse_area","dc_count","daily_orders","sku_count"]
    p1 = ["contract_years","kpi_targets","service_scope","peak_factor","penalty_rules"]

    p0_cov = sum(1 for f in p0 if has_val(f)) / len(p0)
    p1_cov = sum(1 for f in p1 if has_val(f)) / len(p1)

    all_traced = [v for v in traces.values() if isinstance(v, dict) and "status" in v]
    n = max(len(all_traced), 1)
    counts = {"explicit":0,"inferred":0,"partial":0,"missing":0,"ambiguous":0}
    for v in all_traced:
        st = v.get("status","missing")
        if st in counts: counts[st] += 1

    cost_ok = all(has_val(f) for f in ["warehouse_area","dc_count","daily_orders"])
    sol_ok  = cost_ok and has_val("service_scope")
    ctr_ok  = has_val("penalty_rules")
    m0 = profile.get("missing_p0", [])

    parts = []
    if not cost_ok:
        parts.append("成本测算阻塞(" + str(sum(1 for f in p0 if not has_val(f))) + "项)")
    if not sol_ok:
        parts.append("方案设计部分可行(" + str(sum(1 for f in p1 if not has_val(f))) + "项待澄清)")
    if ctr_ok:
        parts.append("合同审核可行")
    if m0:
        parts.append(str(len(m0)) + "项P0待澄清")
    summary = "，".join(parts) if parts else "可进入下一阶段"

    return {
        "completeness": {
            "p0_coverage": round(p0_cov, 3),
            "p1_coverage": round(p1_cov, 3),
            "total_score": round((p0_cov + p1_cov) / 2, 3),
        },
        "evidence": {k: round(v/n, 3) for k, v in counts.items()},
        "readiness": {
            "cost_model_ready": cost_ok,
            "solution_design_ready": sol_ok,
            "contract_review_ready": ctr_ok,
            "blocking_items": m0,
            "summary": summary,
        },
    }

def build_downstream_input(profile, structured=None, quality_score=None):
    """
    Build the canonical downstream input from an extracted profile.

    Adds:
    - Field metadata from FIELD_REGISTRY (display_name, description, validation_rules)
    - Per-field validation errors
    - Resolved missing item → field key mapping
    - Schema validation errors from normalization
    """
    normalized = {}
    field_errors = {}   # field_key → list of validation errors

    for k, v in profile.items():
        if k.startswith("_") or k in ("extraction_confidence", "missing_p0", "missing_p1",
                                         "analysis_report", "_field_traces"):
            continue
        if isinstance(v, dict) and "value" in v:
            # Enrich with registry metadata
            fdef = FIELD_REGISTRY.get(k)
            enriched = dict(v)  # copy
            if fdef:
                enriched["display_name"] = fdef.display_name
                enriched["description"] = fdef.description
                enriched["validation_rules"] = fdef.validation_rules
                enriched["expected_type"] = fdef.expected_type
            normalized[k] = enriched
            # Validate this field
            errs = validate_field_object(k, v)
            if errs:
                field_errors[k] = errs

    qs = quality_score or compute_analysis_quality_score(profile)

    # Resolve missing_p0 / missing_p1 labels to field objects
    def resolve_to_field_objs(label_list):
        result = []
        for label in label_list:
            fkey = resolve_missing_label(label)
            fdef = FIELD_REGISTRY.get(fkey) if fkey else None
            result.append({
                "original_label": label,
                "field_key": fkey,
                "display_name": fdef.display_name if fdef else label,
                "priority": fdef.priority if fdef else "?",
                "impact": fdef.impact if fdef else [],
                "description": fdef.description if fdef else "",
            })
        return result

    return {
        "tender_analysis_markdown": profile.get("analysis_report", ""),
        "normalized_fields": normalized,          # {field_key: field_object}
        "field_validation_errors": field_errors,  # {field_key: [errors]}
        "critical_missing_items": resolve_to_field_objs(profile.get("missing_p0", [])),
        "secondary_missing_items": resolve_to_field_objs(profile.get("missing_p1", [])),
        "clarification_questions": profile.get("_clarification_questions", []),
        "document_metadata": {
            "extraction_confidence": profile.get("extraction_confidence", 0.0),
            "quality_score": qs,
            "schema_validation_errors": profile.get("_schema_validation_errors", []),
            "analysis_timestamp": datetime.now().isoformat(),
            "structured_json": structured or profile.get("_structured", {}),
        }
    }

def generate_clarification_questions(profile, structured=None):
    """
    Generate clarification questions for missing / ambiguous / partial fields.

    Each question links to:
    - field_key (canonical)
    - display_name (from FIELD_REGISTRY)
    - priority (P0/P1)
    - field_object (the actual field trace)
    """
    qs = []
    traces = profile.get("_field_traces", profile)  # fall back to profile itself

    def add_q(field_key, question, severity, reason, fmt, field_obj=None):
        fdef = FIELD_REGISTRY.get(field_key) if field_key else None
        qs.append({
            "field_key": field_key,
            "display_name": fdef.display_name if fdef else field_key,
            "question": question,
            "severity": severity,
            "reason": reason,
            "suggested_answer_format": fmt,
            "priority": severity,
            "impact": fdef.impact if fdef else [],
            "field_object": field_obj,  # full trace for UI drill-down
        })

    m0 = profile.get("missing_p0", [])
    m1 = profile.get("missing_p1", [])

    # Map missing item labels → field keys using registry
    for label in m0:
        fkey = resolve_missing_label(label)
        fdef = FIELD_REGISTRY.get(fkey) if fkey else None
        if fkey == "dc_count":
            add_q(fkey, "请确认本项目实际覆盖的仓库DC数量及各仓库所在城市或地区。",
                  "P0", "下游成本测算和ROI模型需要准确的仓网规模",
                  "例：共5个DC，分别位于上海、广州、武汉、成都、北京，总面积约8万平方米")
        elif fkey == "daily_orders":
            add_q(fkey, "请确认日出库量或日均订单量的统计口径：是否按自然日？峰值和均值分别是多少？",
                  "P0", "自动化方案选型和人力测算依赖订单量数据",
                  "例：日均出库约8000件，旺季峰值约20000件，按自然日统计")
        elif fkey == "sku_count":
            add_q(fkey, "请确认SKU总数及ABC分类占比（快速流转/中速/慢速）。",
                  "P0", "自动化设备选型依赖SKU周转特性",
                  "例：总计约30000个SKU，A类占80%出货量")
        elif not fkey:
            # Unresolved label — add generic question
            add_q(None, f"招标文件缺少「{label}」信息，请补充。",
                  "P0", "下游方案设计依赖此数据",
                  "请提供具体数值或说明")

    for label in m1:
        fkey = resolve_missing_label(label)
        if fkey == "kpi_targets":
            add_q(fkey, "请提供完整的KPI指标清单（含目标值、考核维度、数据来源及惩罚机制）。",
                  "P1", "方案设计必须匹配客户KPI要求，惩罚机制影响风险测算",
                  "例：库存准确率不低于99.9%，每降低0.1%罚款X元")
        elif fkey == "penalty_rules":
            add_q(fkey, "请提供完整的强制条款清单（含否决项），以便在方案设计阶段提前规避。",
                  "P1", "某些自动化方案可能在强制条款下不可行，需尽早识别",
                  "例：仓库必须为丙二类以上消防资质，叉车必须为电动")
        elif fkey == "service_scope":
            add_q(fkey, "请确认报价结构：是按仓储面积报价，还是按订单量或件报价，或是混合报价？",
                  "P1", "成本模型和方案推荐依赖报价结构假设",
                  "例：仓租加力资分开报，仓租元每平米每月，力资元每件")

    # Iterate through field traces for ambiguous / partial fields
    for fname, entry in traces.items():
        if not isinstance(entry, dict) or fname.startswith("_"): continue
        status = entry.get("status", "")
        basis = entry.get("source_basis", "")
        fdef = FIELD_REGISTRY.get(fname)
        if status == "ambiguous":
            add_q(fname,
                  f"招标文件在「{fdef.display_name if fdef else fname}」上存在歧义或冲突：{basis}。请甲方明确实际要求。",
                  "P0", "歧义不澄清会导致方案设计方向错误",
                  "请给出唯一明确的要求", field_obj=entry)
        elif status == "partial":
            add_q(fname,
                  f"招标文件在「{fdef.display_name if fdef else fname}」上只提供了部分信息：{basis}。请补充完整数据。",
                  "P1", "部分数据不足以支撑准确的自动化方案设计",
                  "请提供完整明细数据（不仅是汇总数）", field_obj=entry)

    peak = traces.get("peak_factor", {})
    if isinstance(peak, dict) and peak.get("status") in ("missing", "partial"):
        add_q("peak_factor",
              "请确认旺季（如CNY/618/双11等）订单峰值是平时的多少倍？持续多长时间？",
              "P1", "旺季扩产方案和临时仓需求依赖高峰系数",
              "例：CNY期间约3到4倍，持续约30天", field_obj=peak)

    svc = traces.get("service_scope", {})
    if isinstance(svc, dict) and svc.get("status") == "missing":
        add_q("service_scope",
              "请确认是否需要承接以下增值服务：VMI管理、退货处理、贴标组套、越库配送或温控存储？",
              "P1", "增值服务直接影响方案设计和人力配置",
              "例：需要退货处理和贴标服务，VMI不需要", field_obj=svc)

    inv = traces.get("inventory", {})
    if isinstance(inv, dict) and inv.get("status") in ("missing", "partial"):
        add_q("inventory",
              "请确认平均库存量和库存峰值分别是多少？是否涉及VMI仓？",
              "P1", "库容规划和货架选型依赖库存数据",
              "例：平均库存约50万件，峰值约80万件，含VMI 10万件", field_obj=inv)

    qs.sort(key=lambda q: {"P0": 0, "P1": 1, "P2": 2}.get(q["severity"], 9))
    return qs

def analyze_and_extract(tender_text):
    analysis = analyze_tender_document(tender_text)
    profile  = normalize_extracted_fields(analysis)

    profile["_analysis_report"] = analysis["analysis_report"]
    profile["_structured"]      = analysis["structured"]
    profile["_raw_llm_response"] = analysis["raw_llm_response"]
    profile["_clarification_questions"] = generate_clarification_questions(
        profile, analysis.get("structured", {}))

    quality = compute_analysis_quality_score(profile)
    profile["_quality_score"] = quality
    profile["_downstream_input"] = build_downstream_input(
        profile, analysis.get("structured", {}), quality)

    return profile
