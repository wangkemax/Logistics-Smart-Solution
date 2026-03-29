# =============================================================================
# Tender Understanding Service — Phase 1: Deep Analysis + Structured Extraction
# =============================================================================
#
# Architecture (Two-Phase):
#   Phase 1A — analyze_tender_document()
#       Raw tender text → Markdown analysis report + structured JSON
#   Phase 1B — normalize_extracted_fields()
#       Structured JSON → Standard profile schema with source tracking
#
# Key principles:
#   - NEVER guess values
#   - NEVER use regex fallback for core extraction
#   - NEVER default empty fields to "中" or any other value
#   - Missing data → "未提供" / "待确认" / None
#   - All derived values → source_trace: "derived" + explanation
#
# Reference: Logistics-Presale-AI-Team/agents/requirement-extractor.yaml
# Reference: Logistics-Presale-AI-Team/tender-analysis/requirement-extract.md
# =============================================================================

import os
import re
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Fixed Section Contract — 13 Sections (strict order, no drifting)
# =============================================================================
#
# The Markdown report MUST follow this exact section structure.
# Each section is numbered and has fixed sub-items.
# This is the "section contract" — LLM must fill every section.
#
# =============================================================================

_FIXED_SECTION_CONTRACT = """
## 1. 项目概览

- **招标方**: [客户名称，未提供则写"未提供"]
- **客户名称**: [招标方名称，未提供则写"未提供"]
- **合同期**: [描述合同期限，未提供则写"未提供"]
- **招标流程**: [招标/议价/竞争性谈判等，未提供则写"未提供"]
- **标的范围**: [10个DC仓储及配送服务等，未提供则写"未提供"]
- **付款账期**: [天数+条件，未提供则写"未提供"]
- **税率要求**: [9%/6%等，未提供则写"未提供"]

## 2. 服务范围

### 2.1 仓储服务
[列出所有仓储相关服务，每项一行，如无则写"未提供"]

### 2.2 配送服务
[列出所有配送相关服务，每项一行，如无则写"未提供"]

### 2.3 增值服务
[列出所有增值服务（如贴标/组包/退货处理等），如无则写"未提供"]

## 3. 仓库 / DC 信息

[表格，列：| 代码 | 名称 | 面积(㎡) | 日均处理能力 | 备注 |]
[每个DC一行，无DC信息则写"未提供"]

## 4. 业务流程要求

### 4.1 入库流程
[描述入库要求，未提供则写"未提供"]

### 4.2 出库流程
[描述出库要求，未提供则写"未提供"]

### 4.3 退货与逆向物流
[描述退货处理要求，未提供则写"未提供"]

## 5. 系统与接口要求

### 5.1 必备系统
[列出客户要求的系统，如WMS/SAP/TMS等，未提供则写"未提供"]

### 5.2 数据对接要求
[描述API/数据格式要求，未提供则写"未提供"]

## 6. 人员与运营要求

### 6.1 人员资质要求
[描述叉车证/健康证等要求，未提供则写"未提供"]

### 6.2 设备要求
[描述叉车/车辆/托盘等要求，未提供则写"未提供"]

### 6.3 旺季运营要求
[描述CNY/节假日扩产要求，未提供则写"未提供"]

## 7. KPI / SLA 要求

[表格，列：| 指标 | 目标值 | 考核维度 | 数据来源 | 惩罚机制 |]
[每项KPI一行，无KPI则写"未提供"]

## 8. 商务与报价相关

### 8.1 报价结构要求
[描述报价构成（仓租/力资/配送等），未提供则写"未提供"]

### 8.2 报价约束
[如不得低于市场价/最多2位小数等，未提供则写"未提供"]

### 8.3 增值服务定价
[如贴标费/翻箱费等，未提供则写"未提供"]

## 9. 合同周期与里程碑

### 9.1 合同年限
[年数，未提供则写"未提供"]

### 9.2 关键里程碑
[如上线日期/评估节点等，未提供则写"未提供"]

### 9.3 终止条款
[描述终止条件，未提供则写"未提供"]

## 10. 强制条款 / 否决项

[列出所有强制条款（如仓库不可分包/必须电动叉车等），格式：| 编号 | 条款 | 说明 |，无则写"未提供"]

## 11. 风险与歧义

### 11.1 不明确条款
[格式：| 原文 | 问题说明 |，无则写"无"]

### 11.2 矛盾条款
[格式：| 条款A | 条款B | 矛盾说明 |，无则写"无"]

## 12. 缺失信息与待确认项

### 12.1 缺失定量数据
[列出需要但文档中未提供的数据项，每项一行]

### 12.2 推断项（需标注"推断"）
[格式：| 推断项 | 依据 | 置信度 |，无则写"无"]

## 13. 给下游模块的建议输入

### 13.1 投标策略模块输入
[描述关键投标策略建议]

### 13.2 成本测算模块输入
[描述成本测算边界条件]

### 13.3 合同审核模块输入
[描述合同审核重点]

### 13.4 KPI达标方案模块输入
[描述KPI达标保障建议]
"""


# =============================================================================
# Structured JSON Schema (mirrors the 13 sections)
# =============================================================================

_ANALYSIS_PROMPT = (
    "你是一家专业的物流投标需求分析专家。\n\n"
    "你的任务：仔细阅读招标文件，依次完成以下两步。\n\n"
    "===\n\n"
    "【第一步】：按固定格式输出Markdown分析报告。\n\n"
    "必须严格按照以下13个section顺序写作，不得跳过任何section，不得改变顺序：\n\n"
    + _FIXED_SECTION_CONTRACT.strip() + "\n\n"
    "===\n\n"
    "【第二步】：在Markdown之后，输出以下JSON（不得省略任何键）：\n\n"
    "```json\n"
    "{\n"
    '  "s1_project_overview": {\n'
    '    "client_name": "招标方名称",\n'
    '    "contract_period": "合同期描述",\n'
    '    "bid_scope": "标的范围",\n'
    '    "payment_days": "付款账期天数或null",\n'
    '    "tax_note": "税率说明"\n'
    "  },\n"
    '  "s2_service_scope": {\n'
    '    "warehousing": ["仓储服务列表或[]"],\n'
    '    "distribution": ["配送服务列表或[]"],\n'
    '    "value_added": ["增值服务列表或[]"]\n'
    "  },\n"
    '  "s3_warehouse_dc_list": [\n'
    '    {"code": "DC代码", "name": "DC名称", "area_sqm": "数字或null", "daily_capacity": "数字或null", "notes": "备注"}\n'
    "  ],\n"
    '  "s4_business_process": {\n'
    '    "inbound": "入库流程描述或null",\n'
    '    "outbound": "出库流程描述或null",\n'
    '    "returns": "退货逆向物流描述或null"\n'
    "  },\n"
    '  "s5_systems": {\n'
    '    "required_systems": ["系统列表或[]"],\n'
    '    "integration_requirements": "数据对接要求或null"\n'
    "  },\n"
    '  "s6_operations": {\n'
    '    "staff_requirements": "人员资质要求或null",\n'
    '    "equipment_requirements": "设备要求或null",\n'
    '    "peak_season_notes": "旺季运营要求或null"\n'
    "  },\n"
    '  "s7_kpi_sla": [\n'
    '    {"indicator": "指标", "target": "目标值", "dimension": "考核维度", "data_source": "数据来源", "penalty": "惩罚机制"}\n'
    "  ],\n"
    '  "s8_commercial": {\n'
    '    "pricing_structure": "报价结构要求或null",\n'
    '    "pricing_constraints": "报价约束或null",\n'
    '    "value_added_pricing": "增值服务定价或null"\n'
    "  },\n"
    '  "s9_contract": {\n'
    '    "contract_years": "合同年数数字或null",\n'
    '    "milestones": "关键里程碑或null",\n'
    '    "termination_clauses": "终止条款或null"\n'
    "  },\n"
    '  "s10_mandatory_clauses": [\n'
    '    {"code": "M1", "clause": "条款内容", "description": "说明"}\n'
    "  ],\n"
    '  "s11_risks": {\n'
    '    "unclear_clauses": [{"clause": "原文", "question": "问题"}],\n'
    '    "conflicting_clauses": [{"clause_a": "条款A", "clause_b": "条款B", "conflict": "矛盾"}]\n'
    "  },\n"
    '  "s12_missing": {\n'
    '    "missing_quantitative_data": ["缺失数据项"],\n'
    '    "assumptions": [{"item": "推断项", "basis": "依据", "confidence": "高/中/低"}]\n'
    "  },\n"
    '  "s13_downstream_inputs": {\n'
    '    "bid_strategy": "给投标策略模块的输入",\n'
    '    "cost_boundary": "给成本测算模块的边界条件",\n'
    '    "contract_review": "给合同审核模块的重点",\n'
    '    "kpi_plan": "给KPI达标方案模块的输入"\n'
    "  }\n"
    "}\n"
    "```\n\n"
    "===\n\n"
    "【核心原则】（必须严格遵守）：\n\n"
    "1. **不得编造**：文档中没有的信息，写\"未提供\"或null，不得猜测具体数值。\n"
    "2. **不得默认补值**：关键数字字段（面积/订单量/SKU等），文档没有就写null，不要填任何估计值。\n"
    "3. **推断项必须标注**：凡基于上下文推断的值，在s12_missing.assumptions中列出，注明\"推断\"及置信度。\n"
    "4. **矛盾必须列出**：文档中有矛盾之处（如合同年限前后矛盾），必须在s11_risks.conflicting_clauses中列出。\n"
    "5. **Markdown必须覆盖全部13个section**：即使某section无内容，也必须写出section标题并注明\"未提供\"。\n"
    "6. **先Markdown后JSON**：必须先完整输出Markdown，再输出JSON，不要跳过Markdown。\n\n"
    "===\n\n"
    "【招标文件正文】：\n\n"
    "---\n"
    "{tender_text}\n"
    "---\n\n"
    "请严格按上述要求输出。"
)


# =============================================================================
# MiniMax API
# =============================================================================

def _get_api_key() -> Optional[str]:
    """Get API key from environment or .env file."""
    api_key = os.getenv("MINIMAX_API_KEY") or os.getenv("OPENAI_API_KEY")
    if api_key:
        return api_key
    try:
        env_path = PROJECT_ROOT / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if k in ("MINIMAX_API_KEY", "OPENAI_API_KEY") and not v.startswith("your"):
                        os.environ[k] = v
                        return v
    except Exception:
        pass
    return None


def _call_llm(prompt: str, timeout: int = 45) -> Optional[dict]:
    """Call LLM API and parse the response."""
    api_key = _get_api_key()
    if not api_key:
        print("[tender_understanding] No API key found")
        return None

    base_url = "https://api.minimaxi.com/anthropic"
    model = "MiniMax-M2.7-highspeed"
    if not api_key.startswith("sk-api-"):
        base_url = "https://api.openai.com/v1"
        model = "gpt-4o-mini"

    import urllib.request

    payload = {
        "model": model,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}]
    }
    req = urllib.request.Request(
        f"{base_url}/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read())
            content_list = result.get("content", [])
            if isinstance(content_list, list):
                text = "\n".join(
                    b.get("text", "") for b in content_list if b.get("type") == "text"
                )
            else:
                text = str(content_list)
            return {"raw": text.strip()}
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        print(f"[tender_understanding] HTTP {e.code}: {body}")
        return None
    except Exception as e:
        print(f"[tender_understanding] LLM call failed: {e}")
        return None


def _parse_analysis_response(raw_text: str) -> tuple[str, dict]:
    """
    Parse the LLM response into markdown report and structured JSON.
    Returns (markdown_report, structured_dict).
    """
    # Try JSON code block first
    code_block_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw_text)
    if code_block_match:
        try:
            json_str = code_block_match.group(1).strip()
            structured = json.loads(json_str)
            if isinstance(structured, dict):
                markdown_content = raw_text[:code_block_match.start()].strip()
                return markdown_content, structured
        except json.JSONDecodeError:
            pass

    # Try bare { ... } as fallback
    bare_match = re.search(r"\{[\s\S]*\}", raw_text)
    if bare_match:
        try:
            structured = json.loads(bare_match.group(0))
            if isinstance(structured, dict):
                markdown_content = raw_text[:bare_match.start()].strip()
                return markdown_content, structured
        except json.JSONDecodeError:
            pass

    return raw_text.strip(), {"_parse_error": "JSON extraction failed"}


# =============================================================================
# Phase 1A: Deep Tender Analysis
# =============================================================================

def analyze_tender_document(tender_text: str) -> dict:
    """
    Phase 1A: Analyze raw tender document → Markdown report (13-section fixed) + structured JSON.

    Args:
        tender_text: Raw tender text (PDF/DOCX extracted or manual)

    Returns:
        dict with keys:
            analysis_report: str (Markdown, 13-section fixed structure)
            structured: dict (s1_s13 structured JSON from LLM)
            extraction_metadata: dict (confidence, missing_p0, missing_p1, timestamp)
            raw_llm_response: str (original response)
    """
    if not tender_text or len(tender_text.strip()) < 20:
        return _empty_analysis_result()

    # Keep last 12000 chars to fit context window
    truncated = tender_text[-12000:] if len(tender_text) > 12000 else tender_text
    prompt = _ANALYSIS_PROMPT.format(tender_text=truncated)
    llm_result = _call_llm(prompt)

    if llm_result is None:
        print("[tender_understanding] LLM call failed, returning empty result")
        return _empty_analysis_result()

    raw_text = llm_result.get("raw", "")
    markdown_report, structured = _parse_analysis_response(raw_text)
    metadata = _build_extraction_metadata(structured)

    return {
        "analysis_report": markdown_report,
        "structured": structured,
        "extraction_metadata": metadata,
        "raw_llm_response": raw_text,
    }


def _empty_analysis_result() -> dict:
    """Return an empty result when input is invalid or LLM fails."""
    return {
        "analysis_report": (
            "**分析未能完成**：招标文件内容过短或解析失败，"
            "请提供更完整的招标文件。"
        ),
        "structured": {},
        "extraction_metadata": {
            "confidence": 0.0,
            "missing_p0": ["招标文件内容缺失"],
            "missing_p1": [],
            "analysis_timestamp": datetime.now().isoformat(),
        },
        "raw_llm_response": "",
    }


def _build_extraction_metadata(structured: dict) -> dict:
    """Build extraction metadata from structured JSON."""
    missing_p0 = []
    missing_p1 = []

    if isinstance(structured, dict):
        # P0: blocking items
        dc_list = structured.get("s3_warehouse_dc_list", [])
        traffic = structured.get("s4_business_process", {})
        if not dc_list or dc_list == []:
            missing_p0.append("DC仓库明细")
        if not traffic or not traffic.get("outbound"):
            missing_p0.append("日出库量/订单量")

        # P1: important but non-blocking
        if not structured.get("s7_kpi_sla"):
            missing_p1.append("KPI/SLA要求")
        if not structured.get("s10_mandatory_clauses"):
            missing_p1.append("强制条款清单")
        if not structured.get("s8_commercial", {}).get("pricing_structure"):
            missing_p1.append("报价结构要求")

    # Confidence based on completeness of 13 sections
    section_keys = [
        "s1_project_overview", "s2_service_scope", "s3_warehouse_dc_list",
        "s4_business_process", "s5_systems", "s6_operations",
        "s7_kpi_sla", "s8_commercial", "s9_contract",
        "s10_mandatory_clauses", "s11_risks", "s12_missing", "s13_downstream_inputs"
    ]
    filled = 0
    for key in section_keys:
        val = structured.get(key)
        if val not in (None, {}, [], "", "未提供"):
            filled += 1
    confidence = filled / len(section_keys) if section_keys else 0.0

    return {
        "confidence": min(confidence, 1.0),
        "missing_p0": missing_p0,
        "missing_p1": missing_p1,
        "analysis_timestamp": datetime.now().isoformat(),
    }


# =============================================================================
# Phase 1B: Structured Field Normalization with Source Tracking
# =============================================================================

def normalize_extracted_fields(analysis_result: dict) -> dict:
    """
    Phase 1B: Normalize structured analysis into standard profile fields.

    Each field carries:
      - value:         the scalar value (or None)
      - status:        "explicit" | "inferred" | "partial" | "missing" | "ambiguous"
      - source_basis:  human-readable explanation of how the value was determined
      - section:       which of the 13 report sections this field came from

    Status definitions:
      explicit    — 文件明确写明，有原文/数据支撑
      inferred    — 上下文可合理推断，非明确写明
      partial     — 有部分信息但不完整（如只有总数无明细）
      missing     — 完全未提供
      ambiguous   — 有提及但存在歧义或冲突（如同一条款前后矛盾）

    Args:
        analysis_result: Output from analyze_tender_document()

    Returns:
        Standard profile dict. Each traced field: {value, status, source_basis, section}.
        Metadata fields (extraction_confidence, missing_p0, missing_p1) are scalars.
    """
    structured = analysis_result.get("structured", {})
    metadata = analysis_result.get("extraction_metadata", {})

    def fld(value, status: str, source_basis: str, section: str = "") -> dict:
        return {"value": value, "status": status, "source_basis": source_basis, "section": section}

    # All statuses: explicit | inferred | partial | missing | ambiguous
    profile = {
        "warehouse_area":         fld(None, "missing", "文档未提供仓库面积", ""),
        "sku_count":             fld(None, "missing", "文档未提供SKU数量", ""),
        "daily_orders":          fld(None, "missing", "文档未提供日订单量", ""),
        "inventory":             fld(None, "missing", "文档未提供库存量", ""),
        "labor_cost_level":     fld(None, "missing", "文档未提供人工成本水平", ""),
        "budget_level":         fld(None, "missing", "文档未提供预算水平", ""),
        "automation_expectation":fld(None, "missing", "文档未提供自动化期望", ""),
        "contract_years":       fld(None, "missing", "文档未提供合同年限", ""),
        "industry":              fld(None, "missing", "文档未提供行业信息", ""),
        "region":               fld(None, "missing", "文档未提供地区信息", ""),
        "go_live_date":         fld(None, "missing", "文档未提供上线日期", ""),
        "dc_count":             fld(None, "missing", "文档未提供DC数量", ""),
        "total_warehouse_area":  fld(None, "missing", "文档未提供总仓库面积", ""),
        "service_scope":         fld([], "missing", "文档未提供服务范围明细", ""),
        "kpi_targets":           fld({}, "missing", "文档未提供KPI指标", ""),
        "penalty_rules":        fld([], "missing", "文档未提供惩罚机制", ""),
        "peak_factor":           fld(None, "missing", "文档未提供高峰系数", ""),
        # Metadata (scalar)
        "extraction_confidence": metadata.get("confidence", 0.0),
        "missing_p0": metadata.get("missing_p0", []),
        "missing_p1": metadata.get("missing_p1", []),
        "analysis_report": analysis_result.get("analysis_report", ""),
    }

    # === s3: DC list → warehouse_area, dc_count ===
    dc_list = structured.get("s3_warehouse_dc_list", [])
    if isinstance(dc_list, list) and len(dc_list) > 0:
        areas = []
        for dc in dc_list:
            if isinstance(dc, dict) and dc.get("area_sqm") is not None:
                try:
                    areas.append(int(float(dc["area_sqm"])))
                except (ValueError, TypeError):
                    pass
        if areas:
            total = sum(areas)
            all_have_area = all(
                isinstance(dc.get("area_sqm"), (int, float)) and dc.get("area_sqm") is not None
                for dc in dc_list if isinstance(dc, dict)
            )
            status = "explicit" if all_have_area else "partial"
            basis = (f"从s3_warehouse_dc_list提取，共{len(dc_list)}个DC，"
                     f"{len(areas)}个有面积数据，总计{total}平米")
            profile["total_warehouse_area"] = fld(total, status, basis, "仓库/DC信息")
            profile["warehouse_area"] = fld(total, status, basis, "仓库/DC信息")
            profile["dc_count"] = fld(len(dc_list), "explicit",
                f"从s3_warehouse_dc_list明确提取，共{len(dc_list)}个DC", "仓库/DC信息")

    # === s2: Service scope ===
    svc = structured.get("s2_service_scope", {})
    if isinstance(svc, dict):
        all_services = []
        for key in ("warehousing", "distribution", "value_added"):
            items = svc.get(key, [])
            if isinstance(items, list):
                all_services.extend(items)
        if all_services:
            unique = list(set(all_services))
            profile["service_scope"] = fld(unique, "explicit",
                f"从s2_service_scope提取，{len(unique)}项服务", "服务范围")

    # === s9: Contract years ===
    contract = structured.get("s9_contract", {})
    s11_risks = structured.get("s11_risks", {})
    if isinstance(contract, dict) and contract.get("contract_years") is not None:
        cy = contract["contract_years"]
        # Check for conflicting clauses about contract years
        conflicting = []
        if isinstance(s11_risks.get("conflicting_clauses"), list):
            for c in s11_risks["conflicting_clauses"]:
                if isinstance(c, dict) and any(k in str(c) for k in ("合同", "年限", "期")):
                    conflicting.append(str(c))
        if conflicting:
            profile["contract_years"] = fld(None, "ambiguous",
                f"s9_contract有值但s11_risks发现冲突: {conflicting[0]}", "合同周期与里程碑")
        elif isinstance(cy, (int, float)) and 1 <= cy <= 20:
            profile["contract_years"] = fld(int(cy), "explicit",
                f"从s9_contract.contract_years明确提取，合同期{int(cy)}年", "合同周期与里程碑")
        elif isinstance(cy, str) and cy not in ("未提供", ""):
            m = re.search(r"(\d+)\s*年", cy)
            if m:
                profile["contract_years"] = fld(int(m.group(1)), "inferred",
                    f"从s9_contract.contract_years字符串解析: '{cy}'", "合同周期与里程碑")

    # === s7: KPI targets + daily orders from KPI ===
    kpi_list = structured.get("s7_kpi_sla", [])
    if isinstance(kpi_list, list) and kpi_list:
        kpi_dict = {}
        for kpi in kpi_list:
            if isinstance(kpi, dict) and kpi.get("indicator"):
                kpi_dict[kpi["indicator"]] = {
                    "target": kpi.get("target"),
                    "penalty": kpi.get("penalty", "无明确惩罚"),
                }
        if kpi_dict:
            profile["kpi_targets"] = fld(kpi_dict, "explicit",
                f"从s7_kpi_sla提取，共{len(kpi_dict)}项KPI", "KPI/SLA要求")
            for kpi in kpi_list:
                indicator = kpi.get("indicator", "")
                if any(k in indicator for k in ("日出库", "日均", "日订单", "出库量", "订单量")):
                    target = kpi.get("target")
                    if target is not None:
                        try:
                            num = int(float(re.sub(r"[^\d.]", "", str(target))))
                            if num > 0:
                                profile["daily_orders"] = fld(num, "inferred",
                                    f"从s7_kpi_sla指标'{indicator}'推断，目标值: {target}", "KPI/SLA要求")
                                break
                        except (ValueError, TypeError):
                            pass

    # === s10: Mandatory clauses → penalty_rules ===
    mandatory = structured.get("s10_mandatory_clauses", [])
    if isinstance(mandatory, list) and mandatory:
        clauses = [m.get("clause", "") for m in mandatory
                   if isinstance(m, dict) and m.get("clause")]
        if clauses:
            profile["penalty_rules"] = fld(clauses, "explicit",
                f"从s10_mandatory_clauses提取，共{len(clauses)}条强制条款", "强制条款/否决项")

    # === s6: Peak season → peak_factor ===
    ops = structured.get("s6_operations", {})
    if isinstance(ops, dict) and ops.get("peak_season_notes"):
        notes = str(ops["peak_season_notes"])
        if notes not in ("未提供", ""):
            m = re.search(r"(\d+(?:\.\d+)?)\s*[~-]?(?:(?:~|～)?(\d+(?:\.\d+)?))?\s*倍", notes)
            if m:
                profile["peak_factor"] = fld(float(m.group(1)), "inferred",
                    f"从s6_operations.peak_season_notes推断高峰系数: '{notes}'", "人员与运营要求")

    # === s12: Assumptions → derived/inferred fields ===
    s12 = structured.get("s12_missing", {})
    if isinstance(s12, dict):
        assumptions = s12.get("assumptions", [])
        for ass in assumptions:
            if isinstance(ass, dict):
                item = ass.get("item", "")
                basis = ass.get("basis", "")
                confidence = ass.get("confidence", "低")
                if any(k in item for k in ("面积", "area", "仓储")):
                    m2 = re.search(r"(\d+)", item)
                    if m2:
                        status = "inferred" if confidence in ("高", "中") else "partial"
                        profile["warehouse_area"] = fld(int(m2.group(1)), status,
                            f"s12_missing假设: {item}，依据: {basis}，置信度: {confidence}", "缺失信息与待确认项")
                elif any(k in item for k in ("订单", "日均", "日出库", "出货")):
                    m2 = re.search(r"(\d+)", item)
                    if m2:
                        status = "inferred" if confidence in ("高", "中") else "partial"
                        profile["daily_orders"] = fld(int(m2.group(1)), status,
                            f"s12_missing假设: {item}，依据: {basis}，置信度: {confidence}", "缺失信息与待确认项")

    return profile


# =============================================================================
# Phase 2: Generate Clarification Questions from Missing/Ambiguous Fields
# =============================================================================

def generate_clarification_questions(profile: dict, structured: dict = None) -> list[dict]:
    """
    Convert missing/ambiguous/partial fields into actionable clarification questions.

    Each question has:
      - question:    str  — the question to ask the client
      - field:       str  — which field this relates to
      - severity:    str  — P0 (blocking) | P1 (important) | P2 (nice-to-have)
      - reason:      str  — why this is needed
      - suggested_answer_format: str — what kind of answer we expect

    Args:
        profile:      normalized profile dict from normalize_extracted_fields()
        structured:  optional structured JSON from analyze_tender_document()

    Returns:
        list of question dicts, sorted by severity (P0 first)
    """
    questions = []
    traces = profile.get("_field_traces", {})
    if isinstance(profile, dict) and "_field_traces" not in profile:
        # In analysis mode, the traces are in _field_traces; if not, use profile itself
        traces = profile

    def add_question(field: str, question: str, severity: str,
                     reason: str, suggested_format: str):
        questions.append({
            "field": field,
            "question": question,
            "severity": severity,
            "reason": reason,
            "suggested_answer_format": suggested_format,
        })

    # --- Missing P0 fields ---
    missing_p0 = profile.get("missing_p0", [])
    if "DC仓库明细" in missing_p0:
        add_question(
            "dc_count / warehouse_area",
            "请确认本项目实际覆盖的仓库/DC数量及各仓库所在城市/地区。",
            "P0",
            "下游成本测算和ROI模型需要准确的仓网规模",
            "例：'共5个DC，分别位于上海、广州、武汉、成都、北京，总面积约8万平方米'"
        )
    if "日出库量/订单量" in missing_p0:
        add_question(
            "daily_orders",
            "请确认项目日出库量/日均订单量统计口径：是否按自然日？峰值和均值分别是多少？",
            "P0",
            "自动化方案选型和人力测算依赖订单量数据",
            "例：'日均出库约8000件，旺季峰值约20000件，按自然日统计'"
        )
    if "SKU总数" in missing_p0:
        add_question(
            "sku_count",
            "请确认SKU总数及ABC分类占比（快速流转/中速/慢速）。",
            "P0",
            "自动化设备选型（AS/RS vs AMR）依赖SKU周转特性",
            "例：'总计约30000个SKU，A类（20%）占80%出货量，B/C类占20%'"
        )

    # --- Missing P1 fields ---
    missing_p1 = profile.get("missing_p1", [])
    if "KPI/SLA要求" in missing_p1:
        add_question(
            "kpi_targets",
            "请提供完整的KPI指标清单（含目标值、考核维度、数据来源及惩罚机制）。",
            "P1",
            "方案设计必须匹配客户KPI要求，惩罚机制影响风险测算",
            "例：'库存准确率≥99.9%，准时送达率≥99.5%，每降低0.1%罚款X元'"
        )
    if "强制条款清单" in missing_p1:
        add_question(
            "penalty_rules",
            "请提供完整的强制条款清单（含否决项），以便在方案设计阶段提前规避。",
            "P1",
            "某些自动化方案可能在强制条款下不可行，需尽早识别",
            "例：'仓库必须为丙二类以上消防资质，叉车必须为电动'"
        )
    if "报价结构要求" in missing_p1:
        add_question(
            "service_scope / pricing_structure",
            "请确认报价结构：是按仓储面积报价，还是按订单量/件报价，或是混合报价？",
            "P1",
            "成本模型和方案推荐依赖报价结构假设",
            "例：'仓租+力资分开报，仓租元/平米/月，力资元/件或元/立方'"
        )

    # --- Fields with ambiguous status ---
    for field_name, entry in traces.items():
        if not isinstance(entry, dict):
            continue
        status = entry.get("status", "")
        if status == "ambiguous":
            basis = entry.get("source_basis", "")
            add_question(
                field_name,
                f"招标文件在【{field_name}】上存在歧义或冲突：{basis}。请甲方明确实际要求。",
                "P0",
                "歧义不澄清会导致方案设计方向错误",
                "请给出唯一明确的要求"
            )
        elif status == "partial":
            basis = entry.get("source_basis", "")
            add_question(
                field_name,
                f"招标文件在【{field_name}】上只提供了部分信息：{basis}。请补充完整数据。",
                "P1",
                "部分数据不足以支撑准确的自动化方案设计",
                "请提供完整明细数据（不仅是汇总数）"
            )

    # --- Specific field-level clarification ---
    # Contract years ambiguity
    contract_entry = traces.get("contract_years", {})
    if isinstance(contract_entry, dict) and contract_entry.get("status") == "ambiguous":
        add_question(
            "contract_years",
            "招标文件关于合同年限存在矛盾（SOW写1年，报价模板写2年）。请确认实际合同期限。",
            "P0",
            "合同年限直接影响ROI测算和设备折旧模型",
            "例：'确认合同期为1年，即2026.05.01-2027.04.30'"
        )

    # Peak factor
    peak_entry = traces.get("peak_factor", {})
    if isinstance(peak_entry, dict) and peak_entry.get("status") in ("missing", "partial"):
        add_question(
            "peak_factor",
            "请确认旺季（CNY/618/双11等）订单峰值是平时的多少倍？持续多长时间？",
            "P1",
            "旺季扩产方案和临时仓需求依赖高峰系数",
            "例：'CNY期间约3-4倍，持续约30天；618/双11约2倍，持续约15天'"
        )

    # Service scope
    svc_entry = traces.get("service_scope", {})
    if isinstance(svc_entry, dict):
        svc_val = svc_entry.get("value", [])
        if svc_entry.get("status") == "missing" or not svc_val:
            add_question(
                "service_scope",
                "请确认是否需要承接以下增值服务：VMI管理/退货处理/贴标组套/越库配送/温控存储？",
                "P1",
                "增值服务直接影响方案设计和人力配置",
                "例：'需要退货处理和贴标服务，VMI不需要'"
            )

    # Inventory
    inv_entry = traces.get("inventory", {})
    if isinstance(inv_entry, dict) and inv_entry.get("status") in ("missing", "partial"):
        add_question(
            "inventory",
            "请确认平均库存量和库存峰值分别是多少？是否涉及VMI仓？",
            "P1",
            "库容规划和货架选型依赖库存数据",
            "例：'平均库存约50万件，峰值约80万件，含VMI 10万件'"
        )

    # --- Sort by severity: P0 > P1 > P2 ---
    severity_order = {"P0": 0, "P1": 1, "P2": 2}
    questions.sort(key=lambda q: severity_order.get(q["severity"], 9))
    return questions


# =============================================================================
# Combined entry point
# =============================================================================

def analyze_and_extract(tender_text: str) -> dict:
    """
    Full two-phase extraction: analyze then normalize.

    Returns:
        - Traced profile dict (each field: {value, status, source_basis, section})
        - _analysis_report: full Markdown (str)
        - _structured: structured JSON from LLM (dict)
        - _clarification_questions: list of {question, field, severity, ...} (list)
        - _raw_llm_response: raw LLM text (str)
    """
    analysis_result = analyze_tender_document(tender_text)
    profile = normalize_extracted_fields(analysis_result)

    # Attach analysis outputs
    profile["_analysis_report"] = analysis_result["analysis_report"]
    profile["_structured"] = analysis_result["structured"]
    profile["_raw_llm_response"] = analysis_result["raw_llm_response"]

    # Generate clarification questions
    profile["_clarification_questions"] = generate_clarification_questions(
        profile, analysis_result.get("structured", {})
    )

    return profile

# Legacy flat-field accessors (backward compatibility)
# =============================================================================

def normalize_extracted_fields_flat(analysis_result: dict) -> dict:
    """
    Same as normalize_extracted_fields() but returns flat scalar values
    for backward compatibility with existing code.

    For fields that were "derived", the value is returned as-is.
    For fields with no value, None is returned.
    Use the full dict for source tracking.
    """
    traced = normalize_extracted_fields(analysis_result)
    flat = {}
    for key, entry in traced.items():
        if isinstance(entry, dict) and "value" in entry:
            flat[key] = entry["value"]
        else:
            flat[key] = entry
    return flat


# =============================================================================
# Combined entry point
# =============================================================================

def analyze_and_extract(tender_text: str) -> dict:
    """
    Full two-phase extraction: analyze then normalize.

    Main entry point called by pipeline_tasks.py Stage 1.

    Returns:
        dict with normalized profile fields (each containing value + source_trace),
        plus:
            _analysis_report: full Markdown analysis (str)
            _structured: structured JSON from LLM (dict)
            _raw_llm_response: raw LLM text output (str)
    """
    # Phase 1A: Deep analysis
    analysis_result = analyze_tender_document(tender_text)

    # Phase 1B: Normalize with source tracking
    profile = normalize_extracted_fields(analysis_result)

    # Attach full analysis for downstream use
    profile["_analysis_report"] = analysis_result["analysis_report"]
    profile["_structured"] = analysis_result["structured"]
    profile["_raw_llm_response"] = analysis_result["raw_llm_response"]

    return profile
