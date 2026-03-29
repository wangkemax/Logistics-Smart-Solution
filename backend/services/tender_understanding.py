"""
tender_understanding.py — Tender Understanding Orchestrator
=====================================================

v0.2 architecture:
  This file is the orchestrator. It imports logic from focused modules:
    - tender_schema.py:     Field registry, status enums, section contracts
    - tender_quality.py:   Quality scoring + schema validation
    - tender_readiness.py: Downstream readiness assessment
    - tender_clarification.py: Clarification question generation

Public API:
  - analyze_tender_document(text)      → raw LLM analysis
  - normalize_extracted_fields(analysis_result) → field objects
  - compute_analysis_quality_score(profile)    → quality dict
  - compute_readiness(profile)          → readiness dict
  - generate_clarification_questions(profile, structured, ...) → list[dict]
  - build_downstream_input(profile, structured, quality) → downstream dict
  - analyze_and_extract(tender_text)   → full v0.2 result

Version: v0.2
"""
import os
import re
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import from focused modules
from backend.services.tender_schema import (
    SECTION_NAMES as _SECTION_NAMES,
    SECTION_NAMES,
    FIELD_STATUS,
    get_suggested_answer_format,
)
from backend.services.tender_quality import (
    compute_analysis_quality_score,
    _evidence_score,
    _validate_structured_json,
)
from backend.services.tender_readiness import compute_readiness
from backend.services.tender_clarification import generate_clarification_questions

# Import helpers directly from tender_schema for backward compat
from backend.services.tender_schema import (
    FIELD_REGISTRY,
    resolve_missing_label,
    get_p0_fields,
    get_field_def,
    validate_field_object,
    SCHEMA_CONTRACT,
    FIELD_MAP,
    CONSISTENCY_RULES,
)

# =============================================================================
# Analysis prompt
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


# =============================================================================
# LLM utilities
# =============================================================================
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


def _parse_sections_from_markdown(report_text: str) -> dict:
    """Parse tender analysis markdown into per-section text blocks."""
    if not report_text:
        return {name: "" for name in _SECTION_NAMES}

    sections = {}
    pattern = r"(?m)^##\s*(\d+)\.\s*(.+?)\s*\n([\s\S]*?)(?=\n##\s*\d+\.|\Z)"
    for m in re.finditer(pattern, report_text):
        num = int(m.group(1))
        title = m.group(2).strip()
        body = m.group(3).strip()
        if 1 <= num <= 13:
            sections[_SECTION_NAMES[num - 1]] = body
            sections[f"s{num}_title"] = title

    for name in _SECTION_NAMES:
        if name not in sections:
            sections[name] = ""
    return sections


def _empty_result():
    empty_sections = {name: "" for name in _SECTION_NAMES}
    return {
        "analysis_report": "**分析未能完成**：招标文件内容过短或解析失败。",
        "structured": {},
        "extraction_metadata": {"confidence": 0.0, "missing_p0": ["招标文件内容缺失"], "missing_p1": []},
        "raw_llm_response": "",
        "analysis_sections": empty_sections,
    }


# =============================================================================
# Phase 1: Raw LLM Analysis
# =============================================================================
def analyze_tender_document(text: str) -> dict:
    """
    Run LLM analysis on tender text.
    Returns: {analysis_report, structured, extraction_metadata, raw_llm_response, analysis_sections}
    """
    if not text or len(text.strip()) < 20:
        return _empty_result()
    text = text[-12000:] if len(text) > 12000 else text
    result = _call_llm(_ANALYSIS_PROMPT.replace("{tender_text}", text))
    if result is None:
        return _empty_result()
    report, structured = _parse_response(result["raw"])
    meta = _build_metadata(structured)
    sections = _parse_sections_from_markdown(report)
    return {
        "analysis_report": report,
        "structured": structured,
        "extraction_metadata": meta,
        "raw_llm_response": result["raw"],
        "analysis_sections": sections,
    }


# =============================================================================
# Phase 2: Normalization (field objects)
# =============================================================================
def normalize_extracted_fields(analysis_result: dict) -> dict:
    """
    Convert structured LLM output into normalized field objects.
    Each field: {value, status, source_basis, section, priority, impact}
    """
    s = analysis_result.get("structured", {})
    meta = analysis_result.get("extraction_metadata", {})
    schema_errors = _validate_structured_json(s)

    def fld(value, status, basis, section="", priority="P2", impact=None):
        return {"value": value, "status": status, "source_basis": basis,
                "section": section, "priority": priority, "impact": impact or []}

    p = {
        "warehouse_area":           fld(None, "missing", "文档未提供仓库面积", "", "P0",
                                       ["cost_model", "roi_analysis", "layout_design", "investment_plan"]),
        "dc_count":                fld(None, "missing", "文档未提供DC数量", "", "P0",
                                       ["cost_model", "layout_design", "investment_plan"]),
        "daily_orders":            fld(None, "missing", "文档未提供日订单量", "", "P0",
                                       ["cost_model", "labor_plan", "layout_design"]),
        "sku_count":               fld(None, "missing", "文档未提供SKU数量", "", "P0",
                                       ["layout_design", "automation_selection", "labor_plan"]),
        "inventory":               fld(None, "missing", "文档未提供库存量", "", "P1",
                                       ["layout_design", "investment_plan", "capacity_plan"]),
        "automation_expectation":  fld(None, "missing", "文档未提供自动化期望", "", "P1",
                                       ["automation_selection", "solution_design"]),
        "contract_years":          fld(None, "missing", "文档未提供合同年限", "", "P1",
                                       ["cost_model", "roi_analysis", "investment_plan"]),
        "service_scope":           fld([], "missing", "文档未提供服务范围明细", "", "P1",
                                       ["solution_design", "cost_model", "automation_selection"]),
        "kpi_targets":             fld({}, "missing", "文档未提供KPI指标", "", "P1",
                                       ["solution_design", "contract_review", "risk_assessment"]),
        "penalty_rules":           fld([], "missing", "文档未提供惩罚机制", "", "P1",
                                       ["contract_review", "risk_assessment"]),
        "peak_factor":             fld(None, "missing", "文档未提供高峰系数", "", "P1",
                                       ["layout_design", "labor_plan", "capacity_plan"]),
        "labor_cost_level":         fld(None, "missing", "文档未提供人工成本水平", "", "P2",
                                       ["cost_model", "labor_plan"]),
        "budget_level":             fld(None, "missing", "文档未提供预算水平", "", "P2",
                                       ["cost_model", "roi_analysis"]),
        "industry":                fld(None, "missing", "文档未提供行业信息", "", "P2", []),
        "region":                  fld(None, "missing", "文档未提供地区信息", "", "P2", []),
        "go_live_date":            fld(None, "missing", "文档未提供上线日期", "", "P2",
                                       ["project_plan"]),
        "total_warehouse_area":    fld(None, "missing", "文档未提供总仓库面积", "", "P0",
                                       ["cost_model", "layout_design", "investment_plan"]),
        "extraction_confidence": meta.get("confidence", 0.0),
        "missing_p0": meta.get("missing_p0", []),
        "missing_p1": meta.get("missing_p1", []),
        "analysis_report": analysis_result.get("analysis_report", ""),
        "_schema_validation_errors": schema_errors,
    }

    # --- Extract from s3_warehouse_dc_list ---
    dcs = s.get("s3_warehouse_dc_list", [])
    if isinstance(dcs, list) and dcs:
        areas = []
        for dc in dcs:
            if isinstance(dc, dict) and dc.get("area_sqm") is not None:
                try:
                    areas.append(int(float(dc["area_sqm"])))
                except Exception:
                    pass
        if areas:
            total = sum(areas)
            all_have = all(
                isinstance(dc.get("area_sqm"), (int, float)) and dc.get("area_sqm") is not None
                for dc in dcs if isinstance(dc, dict)
            )
            status = "explicit" if all_have else "partial"
            basis = (f"从s3_warehouse_dc_list提取，共{len(dcs)}个仓库，"
                     f"{len(areas)}个有面积，总计{total}平米")
            p["total_warehouse_area"] = fld(total, status, basis, "仓库DC信息", "P0",
                                             ["cost_model", "layout_design", "investment_plan"])
            p["warehouse_area"] = fld(total, status, basis, "仓库DC信息", "P0",
                                      ["cost_model", "roi_analysis", "layout_design", "investment_plan"])
            p["dc_count"] = fld(len(dcs), "explicit",
                                  f"从s3_warehouse_dc_list明确提取，共{len(dcs)}个DC",
                                  "仓库DC信息", "P0",
                                  ["cost_model", "layout_design", "investment_plan"])

    # --- Extract from s2_service_scope ---
    svc = s.get("s2_service_scope", {})
    if isinstance(svc, dict):
        all_svc = []
        for key in ("warehousing", "distribution", "value_added"):
            items = svc.get(key, [])
            if isinstance(items, list):
                all_svc.extend(items)
        if all_svc:
            uniq = list(set(all_svc))
            p["service_scope"] = fld(uniq, "explicit",
                                      f"从s2_service_scope提取，共{len(uniq)}项服务",
                                      "服务范围", "P1",
                                      ["solution_design", "cost_model", "automation_selection"])

    # --- Extract from s9_contract ---
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
            p["contract_years"] = fld(None, "ambiguous",
                                       "s9有值但s11发现冲突: " + conflicts[0],
                                       "合同周期与里程碑", "P1",
                                       ["cost_model", "roi_analysis", "investment_plan"])
        elif isinstance(cy, (int, float)) and 1 <= cy <= 20:
            p["contract_years"] = fld(int(cy), "explicit",
                                      f"从s9_contract.contract_years明确提取，合同期{int(cy)}年",
                                      "合同周期与里程碑", "P1",
                                      ["cost_model", "roi_analysis", "investment_plan"])
        elif isinstance(cy, str) and cy not in ("未提供", ""):
            m = re.search(r"(\d+)\s*年", cy)
            if m:
                p["contract_years"] = fld(int(m.group(1)), "inferred",
                                          f"从s9_contract.contract_years字符串解析: " + cy,
                                          "合同周期与里程碑", "P1",
                                          ["cost_model", "roi_analysis"])

    # --- Extract from s7_kpi_sla ---
    kpis = s.get("s7_kpi_sla", [])
    if isinstance(kpis, list) and kpis:
        kd = {}
        for kpi in kpis:
            if isinstance(kpi, dict) and kpi.get("indicator"):
                kd[kpi["indicator"]] = {"target": kpi.get("target"),
                                         "penalty": kpi.get("penalty", "无明确惩罚")}
        if kd:
            p["kpi_targets"] = fld(kd, "explicit",
                                    f"从s7_kpi_sla提取，共{len(kd)}项KPI",
                                    "KPI/SLA要求", "P1",
                                    ["solution_design", "contract_review", "risk_assessment"])
            for kpi in kpis:
                ind = kpi.get("indicator", "")
                if any(x in ind for x in ("日出库", "日均", "日订单", "出库量", "订单量")):
                    tgt = kpi.get("target")
                    if tgt is not None:
                        try:
                            cleaned = re.sub(r"[^\d.]", "", str(tgt))
                            num = int(float(cleaned))
                            if num > 0:
                                p["daily_orders"] = fld(num, "inferred",
                                                          f"从s7_kpi_sla指标{ind}推断，目标值: {tgt}",
                                                          "KPI/SLA要求", "P0",
                                                          ["cost_model", "labor_plan", "layout_design"])
                                break
                        except Exception:
                            pass

    # --- Extract from s10_mandatory_clauses ---
    mc = s.get("s10_mandatory_clauses", [])
    if isinstance(mc, list) and mc:
        clauses = [m.get("clause", "") for m in mc if isinstance(m, dict) and m.get("clause")]
        if clauses:
            p["penalty_rules"] = fld(clauses, "explicit",
                                      f"从s10_mandatory_clauses提取，共{len(clauses)}条强制条款",
                                      "强制条款否决项", "P1",
                                      ["contract_review", "risk_assessment"])

    # --- Extract from s6_operations ---
    ops = s.get("s6_operations", {})
    if isinstance(ops, dict) and ops.get("peak_season_notes"):
        notes = str(ops["peak_season_notes"])
        if notes not in ("未提供", ""):
            m = re.search(r"(\d+(?:\.\d+)?)\s*[~-]?(?:(?:~|～)?(\d+(?:\.\d+)?))?\s*倍", notes)
            if m:
                p["peak_factor"] = fld(float(m.group(1)), "inferred",
                                       f"从s6_operations.peak_season_notes推断高峰系数: " + notes,
                                       "人员与运营要求", "P1",
                                       ["layout_design", "labor_plan", "capacity_plan"])

    # --- Extract from s12_missing (assumptions) ---
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
                        p["warehouse_area"] = fld(int(m2.group(1)), status,
                                                  f"s12_missing假设: {item}，依据: {basis}，置信度: {conf}",
                                                  "缺失信息与待确认项", "P0",
                                                  ["cost_model", "layout_design"])
                elif any(x in item for x in ("订单", "日均", "日出库")):
                    m2 = re.search(r"(\d+)", item)
                    if m2:
                        p["daily_orders"] = fld(int(m2.group(1)), status,
                                                  f"s12_missing假设: {item}，依据: {basis}，置信度: {conf}",
                                                  "缺失信息与待确认项", "P0",
                                                  ["cost_model", "labor_plan"])

    return p


# =============================================================================
# Build extraction metadata (called by analyze_tender_document)
# =============================================================================
def _build_metadata(s: dict) -> dict:
    """
    Build rich extraction metadata from structured LLM output.
    Returns: {confidence, missing_p0, missing_p1, critical_missing_items,
              important_missing_items, clarification_questions, risks,
              ambiguities, downstream_hints, analysis_timestamp,
              sections_filled, sections_total}
    """
    m0, m1 = [], []
    critical, important = [], []
    risks_out, ambiguities_out = [], []
    downstream_hints = {"for_cost_model": "", "for_solution_design": "",
                       "for_contract_review": "", "for_kpi_plan": ""}

    if isinstance(s, dict):
        if not s.get("s3_warehouse_dc_list"):
            m0.append("DC仓库明细")
            critical.append({
                "field_key": "dc_count", "display_name": "DC数量",
                "section": "s3_warehouse_dc_list",
                "why_blocking": "成本测算需要仓库数量和面积，缺失则无法进行网络成本估算",
                "downstream_impact": ["cost_model", "layout_design", "investment_plan"],
            })
        if not s.get("s4_business_process", {}).get("outbound"):
            m0.append("日出库量/订单量")
            critical.append({
                "field_key": "daily_orders", "display_name": "日均订单量",
                "section": "s7_kpi_sla",
                "why_blocking": "人力测算和自动化选型依赖日出库量，缺失则无法进行准确成本测算",
                "downstream_impact": ["cost_model", "labor_plan", "automation_selection"],
            })
        if not s.get("s7_kpi_sla"):
            m1.append("KPI/SLA要求")
            important.append({
                "field_key": "kpi_targets", "display_name": "KPI指标",
                "section": "s7_kpi_sla",
                "why_matters": "KPI是方案设计和合同审核的基础，缺失则无法量化服务承诺",
                "downstream_impact": ["solution_design", "contract_review", "risk_assessment"],
            })
        if not s.get("s10_mandatory_clauses"):
            m1.append("强制条款清单")
            important.append({
                "field_key": "penalty_rules", "display_name": "强制条款/惩罚机制",
                "section": "s10_mandatory_clauses",
                "why_matters": "强制条款直接影响方案可行性和风险测算，必须在设计阶段识别",
                "downstream_impact": ["contract_review", "risk_assessment"],
            })

        s11 = s.get("s11_risks", {})
        if isinstance(s11, dict):
            for clause in (s11.get("unclear_clauses") or []):
                if clause and clause not in ("无", "", "无歧义"):
                    risks_out.append({
                        "clause_text": str(clause)[:200],
                        "section": "s11_risks", "risk_type": "unclear",
                    })
            for conflict in (s11.get("conflicting_clauses") or []):
                if conflict and conflict not in ("无", "", "无矛盾"):
                    if isinstance(conflict, dict):
                        ambiguities_out.append({
                            "clause_a": str(conflict.get("clause_a", ""))[:200],
                            "clause_b": str(conflict.get("clause_b", ""))[:200],
                            "conflict_description": str(conflict.get("description", ""))[:200],
                        })
                    else:
                        ambiguities_out.append({
                            "clause_a": str(conflict)[:200], "clause_b": "",
                            "conflict_description": "条款内容存在歧义或前后矛盾",
                        })

        s13 = s.get("s13_downstream_inputs", {})
        if isinstance(s13, dict):
            downstream_hints["for_cost_model"] = s13.get("cost_boundary") or ""
            downstream_hints["for_solution_design"] = s13.get("bid_strategy") or ""
            downstream_hints["for_contract_review"] = s13.get("contract_review") or ""
            downstream_hints["for_kpi_plan"] = s13.get("kpi_plan") or ""

    sects = ["s1_project_overview", "s2_service_scope", "s3_warehouse_dc_list",
             "s4_business_process", "s5_systems", "s6_operations", "s7_kpi_sla",
             "s8_commercial", "s9_contract", "s10_mandatory_clauses",
             "s11_risks", "s12_missing", "s13_downstream_inputs"]
    filled = sum(1 for x in sects if s.get(x) and s.get(x) not in ({}, [], ""))

    return {
        "confidence": filled / len(sects) if sects else 0.0,
        "missing_p0": m0,
        "missing_p1": m1,
        "critical_missing_items": critical,
        "important_missing_items": important,
        "clarification_questions": [],  # generated by tender_clarification.py
        "risks": risks_out,
        "ambiguities": ambiguities_out,
        "downstream_hints": downstream_hints,
        "analysis_timestamp": datetime.now().isoformat(),
        "sections_filled": filled,
        "sections_total": len(sects),
    }


# =============================================================================
# Build downstream input dict
# =============================================================================
def build_downstream_input(profile: dict, structured=None, quality_score=None) -> dict:
    """
    Build canonical downstream input from extracted profile.
    Adds: field metadata, per-field validation errors, resolved missing items.
    """
    normalized = {}
    field_errors = {}

    for k, v in profile.items():
        if k.startswith("_") or k in ("extraction_confidence", "missing_p0", "missing_p1",
                                       "analysis_report", "_field_traces"):
            continue
        if isinstance(v, dict) and "value" in v:
            fdef = FIELD_REGISTRY.get(k)
            enriched = dict(v)
            if fdef:
                enriched["display_name"] = fdef.display_name
                enriched["description"] = fdef.description
                enriched["validation_rules"] = fdef.validation_rules
                enriched["expected_type"] = fdef.expected_type
            normalized[k] = enriched
            errs = validate_field_object(k, v)
            if errs:
                field_errors[k] = errs

    qs = quality_score or compute_analysis_quality_score(profile)

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
        "analysis_sections": profile.get("_analysis_sections", {}),
        "tender_analysis_markdown": profile.get("analysis_report", ""),
        "normalized_fields": normalized,
        "field_validation_errors": field_errors,
        "critical_missing_items": resolve_to_field_objs(profile.get("missing_p0", [])),
        "secondary_missing_items": resolve_to_field_objs(profile.get("missing_p1", [])),
        "clarification_questions": profile.get("_clarification_questions", []),
        "readiness": compute_readiness(profile),
        "document_metadata": {
            "extraction_confidence": profile.get("extraction_confidence", 0.0),
            "quality_score": qs,
            "schema_validation_errors": profile.get("_schema_validation_errors", []),
            "analysis_timestamp": datetime.now().isoformat(),
            "structured_json": structured or profile.get("_structured", {}),
        },
    }


# =============================================================================
# Main orchestrator
# =============================================================================
def analyze_and_extract(tender_text: str) -> dict:
    """
    Two-phase tender understanding: deep analysis + field normalization.

    Returns a unified dict containing canonical v0.2 keys:
      - analysis_markdown / analysis_sections / normalized_fields
      - critical_missing_items / important_missing_items
      - clarification_questions / readiness / quality_scores / meta
      Plus underscore-prefixed fields for backward compat.

    Version: v0.2
    """
    analysis = analyze_tender_document(tender_text)
    profile  = normalize_extracted_fields(analysis)

    profile["_analysis_report"] = analysis["analysis_report"]
    profile["_analysis_sections"] = analysis.get("analysis_sections", {})
    profile["_structured"] = analysis["structured"]
    profile["_raw_llm_response"] = analysis["raw_llm_response"]
    profile["_clarification_questions"] = generate_clarification_questions(
        profile, analysis.get("structured", {}))
    profile["_quality_score"] = compute_analysis_quality_score(profile)
    profile["_readiness"] = compute_readiness(profile)
    profile["_downstream_input"] = build_downstream_input(
        profile, analysis.get("structured", {}), profile["_quality_score"])

    quality = profile["_quality_score"]
    readiness = profile["_readiness"]

    # Canonical v0.2 top-level keys (no underscore — stable contract)
    profile["analysis_markdown"] = analysis["analysis_report"]
    profile["analysis_sections"] = analysis.get("analysis_sections", {})
    profile["critical_missing_items"] = analysis.get("extraction_metadata", {}).get("critical_missing_items", [])
    profile["important_missing_items"] = analysis.get("extraction_metadata", {}).get("important_missing_items", [])
    profile["clarification_questions"] = profile["_clarification_questions"]
    profile["readiness"] = readiness
    profile["quality_scores"] = {
        "completeness_score": quality.get("completeness", {}).get("total_score", 0.0),
        "evidence_score": _evidence_score(quality),
        "readiness_score": readiness.get("readiness_score", 0.0),
    }
    profile["meta"] = {
        "analysis_version": "v0.2",
        "prompt_version": "tender_understanding_v0.2",
        "generated_at": datetime.now().isoformat(),
        "model": (analysis.get("raw_llm_response") or "")[:80],
    }

    return profile
