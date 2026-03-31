"""
Tender Requirement Extraction Service
=====================================
Unified extraction layer: LLM (primary) + regex (fallback).

Architecture:
  tender_service.py  ←  extraction logic (service layer)
        ↓
  llm_extractor.py  ←  LLM API calls (MiniMax / OpenAI)

This service is called by:
  - orchestrator.py (pipeline Stage 1)
  - /api/pipeline/extract endpoint
  - agents (future)
"""

import re
import os
import sys
from typing import Optional
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.llm_extractor import extract_requirements_llm
from backend.services.tender_understanding import analyze_and_extract


# =============================================================================
# Regex-based extraction (fallback / quick preview)
# =============================================================================

# New 5-level industry system (v0.8+)
_INDUSTRY_MAP = {
    "AUTOMOTIVE":    ["汽车", "汽车零部件", "汽车整车", "主机厂", "JIT", "JIS", "产线配套", "SKD", "CKD"],
    "ELECTRONICS":   ["电子信息", "消费电子", "ICT", "EMS", "VMI", "电子元器件"],
    "FMCG":          ["电商", "电子商务", "天猫", "京东", "淘宝", "拼多多", "抖音电商", "零售", "商超", "便利店", "快消", "高频周转"],
    "MANUFACTURING": ["制造", "生产商", "工厂", "制造业", "工业制造", "工业品"],
    "GENERIC_3PL":   ["3PL", "第三方物流", "物流外包", "货运代理", "快递", "速运", "快运"],
}


_REGION_MAP = {
    "华东": ["上海", "江苏", "浙江", "安徽", "华东"],
    "华南": ["广东", "广西", "海南", "华南"],
    "华北": ["北京", "天津", "河北", "华北"],
    "华中": ["湖北", "湖南", "河南", "华中"],
    "西部": ["四川", "重庆", "陕西", "西部", "新疆", "甘肃"],
}


def extract_with_regex(text: str) -> dict:
    """Lightweight regex-based extraction (fallback when LLM unavailable)."""
    profile = {
        "project_name": "待确认",
        "client_name": "待确认",
        "industry": "GENERIC_3PL",
        "region": "华东",
        "warehouse_area": None,
        "sku_count": None,
        "daily_orders": None,
        "inventory": None,
        "labor_cost_level": "中",
        "budget_level": "中",
        "automation_expectation": "中",
        "contract_years": None,
        "go_live_date": "待确认",
        "extraction_confidence": 0.35,
        "missing_p0": [],
        "missing_p1": ["project_name", "client_name", "go_live_date"],
    }

    # Industry
    for industry, keywords in _INDUSTRY_MAP.items():
        if any(kw in text for kw in keywords):
            profile["industry"] = industry
            break

    # Region
    for region, keywords in _REGION_MAP.items():
        if any(kw in text for kw in keywords):
            profile["region"] = region
            break

    # Warehouse area
    for pat in [r"(\d[\d,\.]*)\s*(?:平米|㎡|平方米)", r"面积[是为约：:\s]*(\d[\d,\.]*)"]:
        m = re.search(pat, text)
        if m:
            profile["warehouse_area"] = float(m.group(1).replace(",", ""))
            break

    # SKU
    m = re.search(r"SKU(?:数量|数|量)?[是为约：:\s]*(\d[\d,\.]*)", text, re.IGNORECASE)
    if not m:
        m = re.search(r"(\d[\d,\.]*)\s*(?:SKU|种|品类)", text, re.IGNORECASE)
    if m:
        profile["sku_count"] = int(float(m.group(1).replace(",", "")))

    # Daily orders — handle "日订单", "日均订单", "日收件", "日出货" etc.
    for pat in [
        r"日[均]?(?:订单|订单量|收件|出货|收贷|处理|均)[为是约]?[：:\s]*(\d[\d,]*)",
        r"日[出进]?(?:货|件|单)[量为]?[：:\s]*(\d[\d,]*)",
        r"日[均]?[订单件][量为]?[为是约]?[：:\s]*(\d[\d,]*)",
        r"(\d[\d,]+)\s*(?:单|票|件)/(?:天|日)",
    ]:
        m = re.search(pat, text)
        if m:
            profile["daily_orders"] = int(float(m.group(1).replace(",", "")))
            break

    # Inventory
    m = re.search(r"库存(?:量)?[为是约：:\s]*(\d[\d,\.]*)", text)
    if m:
        profile["inventory"] = int(float(m.group(1).replace(",", "")))

    # Contract years
    m = re.search(r"合同(?:期|期限)?[为是约]?\s*(\d+)\s*年", text)
    if m:
        profile["contract_years"] = int(m.group(1))

    # Budget
    for level, keywords in [("高", ["高预算", "预算高", "预算充足"]),
        ("中", ["中档", "中等", "预算中"]),
        ("低", ["低预算", "预算紧张", "预算有限", "控制在"])]:
        if any(kw in text for kw in keywords):
            profile["budget_level"] = level
            break

    # Labor cost
    for level, keywords in [("高", ["人工成本高", "人工贵"]), ("中", ["人工成本中", "人工中等"]), ("低", ["人工成本低", "人工便宜"])]:
        if any(kw in text for kw in keywords):
            profile["labor_cost_level"] = level
            break

    # Missing P0 detection
    missing = []
    if not profile["warehouse_area"]:
        missing.append("warehouse_area")
    if not profile["sku_count"]:
        missing.append("sku_count")
    if not profile["daily_orders"]:
        missing.append("daily_orders")
    profile["missing_p0"] = missing

    return profile


# =============================================================================
# LLM-based extraction (primary, high quality)
# =============================================================================

def extract_with_llm(text: str, use_llm: bool = True) -> tuple[dict, list, float]:
    """
    Extract using LLM (MiniMax M2.7-highspeed).
    Returns (profile_dict, missing_p0, confidence).
    """
    if not use_llm:
        profile = extract_with_regex(text)
        return profile, profile["missing_p0"], profile["extraction_confidence"]

    try:
        profile, missing_p0, confidence = extract_requirements_llm(text, use_llm=True)
        return profile, missing_p0, confidence
    except Exception as e:
        # LLM failed — fall back to regex silently
        import sys; print(f"[tender_service] LLM extraction failed: {e}, falling back to regex", file=sys.stderr)
        profile = extract_with_regex(text)
        return profile, profile["missing_p0"], profile["extraction_confidence"]


# =============================================================================
# Unified extraction API
# =============================================================================

def extract_tender_requirements(
    text: str,
    use_llm: bool = True,
    min_confidence: float = 0.70,
) -> dict:
    """
    Main entry point for tender requirement extraction.

    Args:
        text: raw tender document text
        use_llm: whether to use LLM (True = high quality, False = regex only)
        min_confidence: if LLM confidence below this, supplement with regex

    Returns:
        profile dict with all standard fields, plus:
        - extraction_confidence: 0.0-1.0
        - missing_p0: list of missing critical fields
        - missing_p1: list of missing secondary fields
    """
    profile, missing_p0, confidence = extract_with_llm(text, use_llm=use_llm)

    # If LLM confidence is low, merge with regex result
    if use_llm and confidence < min_confidence:
        regex_profile = extract_with_regex(text)
        # Merge: prefer LLM, fill gaps with regex
        for key in ["warehouse_area", "sku_count", "daily_orders", "industry", "region"]:
            if not profile.get(key):
                profile[key] = regex_profile.get(key)
        # Re-detect missing P0 after merge
        still_missing = [k for k in ["warehouse_area", "sku_count", "daily_orders"] if not profile.get(k)]
        profile["missing_p0"] = still_missing if still_missing else missing_p0
        profile["extraction_confidence"] = max(confidence, 0.50)
        profile["extraction_method"] = "llm+regex_merge"
    else:
        profile["extraction_method"] = "llm" if use_llm else "regex"

    # Always ensure standard keys exist
    for key in ["project_name", "client_name", "industry", "region",
                "warehouse_area", "sku_count", "daily_orders", "inventory",
                "labor_cost_level", "budget_level", "automation_expectation",
                "contract_years", "go_live_date"]:
        profile.setdefault(key, None if key in ["warehouse_area", "sku_count", "daily_orders", "contract_years"] else
                          ("待确认" if key in ["project_name", "client_name", "go_live_date"] else "中"))

    return profile


# =============================================================================
# Unified extraction entry point (Task 2)
# =============================================================================

_NUMERIC_FIELDS = ["warehouse_area", "sku_count", "daily_orders", "inventory"]
_SEMANTIC_FIELDS = ["industry", "region", "labor_cost_level", "budget_level", "automation_expectation"]
_STANDARD_KEYS = [
    "project_name", "client_name", "industry", "region",
    "warehouse_area", "sku_count", "daily_orders", "inventory",
    "labor_cost_level", "budget_level", "automation_expectation",
    "contract_years", "go_live_date",
]
_MISSING_P0_KEYS = ["warehouse_area", "sku_count", "daily_orders"]
_MISSING_P1_KEYS = ["project_name", "client_name", "go_live_date"]


def _merge_extraction_results(rule_result: dict, llm_result: dict) -> dict:
    """
    Merge rule and LLM extraction results using priority rules:
      - Numeric fields: prefer rule if non-None, else llm
      - Semantic fields: prefer llm
      - source_trace marks each field's origin
      - extraction_confidence = max(rule_conf, llm_conf)
      - missing_p0/p1: union of both
      - warnings: concatenated
    """
    warnings = list(rule_result.get("warnings", [])) + list(llm_result.get("warnings", []))

    rule_conf = rule_result.get("extraction_confidence", 0.35)
    llm_conf = llm_result.get("extraction_confidence", 0.5)
    extraction_confidence = max(rule_conf, llm_conf)

    field_confidence: dict = {}
    source_trace: dict = {}

    # Numeric fields — rule first, llm fills gaps
    for key in _NUMERIC_FIELDS:
        rule_val = rule_result.get(key)
        llm_val = llm_result.get(key)
        if rule_val is not None:
            field_confidence[key] = rule_conf
            source_trace[key] = "rule"
        elif llm_val is not None:
            field_confidence[key] = llm_conf
            source_trace[key] = "llm"
        else:
            field_confidence[key] = rule_conf
            source_trace[key] = "default"

    # Semantic fields — llm first, rule fills gaps
    for key in _SEMANTIC_FIELDS:
        llm_val = llm_result.get(key)
        rule_val = rule_result.get(key)
        llm_default = "中"
        rule_default = "中"
        if llm_val and llm_val != llm_default:
            field_confidence[key] = llm_conf
            source_trace[key] = "llm"
        elif rule_val and rule_val != rule_default:
            field_confidence[key] = rule_conf
            source_trace[key] = "rule"
        else:
            field_confidence[key] = llm_conf
            source_trace[key] = "default"

    # Missing P0 — union
    missing_p0 = list(
        set(rule_result.get("missing_p0", [])) | set(llm_result.get("missing_data_P0", llm_result.get("missing_p0", [])))
    )
    # Missing P1 — union
    missing_p1 = list(
        set(rule_result.get("missing_p1", [])) | set(llm_result.get("missing_p1", []))
    )

    # Contract years — prefer rule, then llm
    contract_years = rule_result.get("contract_years") or llm_result.get("contract_years")
    field_confidence["contract_years"] = rule_conf if rule_result.get("contract_years") else llm_conf
    source_trace["contract_years"] = "rule" if rule_result.get("contract_years") else ("llm" if llm_result.get("contract_years") else "default")

    # Project/client/go_live_date — llm preferred, rule fallback
    for key in ["project_name", "client_name", "go_live_date"]:
        llm_val = llm_result.get(key)
        rule_val = rule_result.get(key)
        if llm_val and llm_val != "待确认":
            field_confidence[key] = llm_conf
            source_trace[key] = "llm"
        elif rule_val and rule_val != "待确认":
            field_confidence[key] = rule_conf
            source_trace[key] = "rule"
        else:
            field_confidence[key] = llm_conf
            source_trace[key] = "default"

    return {
        "extraction_confidence": extraction_confidence,
        "field_confidence": field_confidence,
        "source_trace": source_trace,
        "missing_p0": missing_p0,
        "missing_p1": missing_p1,
        "warnings": warnings,
        "raw_rule_result": rule_result,
        "raw_llm_result": llm_result,
    }


def _build_profile_from_result(result: dict, source: str) -> dict:
    """Build a flat profile dict from an extraction result dict."""
    profile = {key: result.get(key) for key in _STANDARD_KEYS}
    profile["warnings"] = result.get("warnings", [])
    profile["extraction_method"] = source
    # Fill defaults
    for key in _STANDARD_KEYS:
        if profile.get(key) is None:
            if key in _MISSING_P0_KEYS:
                profile[key] = None
            elif key in _MISSING_P1_KEYS:
                profile[key] = "待确认"
            elif key in _NUMERIC_FIELDS:
                profile[key] = None
            else:
                profile[key] = "中"
    return profile


def _ensure_standard_keys(profile: dict):
    """Ensure all standard keys exist in profile, filling defaults."""
    for key in _STANDARD_KEYS:
        if profile.get(key) is None:
            if key in _MISSING_P0_KEYS:
                profile[key] = None
            elif key in _MISSING_P1_KEYS:
                profile[key] = "待确认"
            elif key in _NUMERIC_FIELDS:
                profile[key] = None
            else:
                profile[key] = "中"


def extract_requirements(
    text: str,
    mode: str = "hybrid",
    project_context: Optional[dict] = None,
    fallback_to_rule: bool = True,
) -> dict:
    """
    Unified tender requirement extraction entry point.

    Args:
        text: raw tender document text
        mode: "rule_only" | "llm_only" | "hybrid" (default)
        project_context: optional dict with contextual hints
        fallback_to_rule: if True and LLM fails, fall back to rule result

    Returns dict with keys:
      industry, warehouse_area, sku_count, daily_orders, inventory,
      labor_cost_level, budget_level, automation_expectation, region,
      missing_p0, missing_p1,
      extraction_confidence,
      field_confidence: dict[field_name -> float],
      source_trace: dict[field_name -> "rule" | "llm" | "merged" | "default"],
      warnings: list[str],
      raw_rule_result: dict (only in hybrid mode),
      raw_llm_result: dict  (only in hybrid mode),
    """
    import sys

    if mode == "rule_only":
        rule_result = extract_with_regex(text)
        rule_result["warnings"] = []
        profile = _build_profile_from_result(rule_result, source="regex")
        _ensure_standard_keys(profile)
        # field_confidence: all fields from rule with rule confidence
        rule_conf = rule_result.get("extraction_confidence", 0.35)
        field_confidence = {key: rule_conf for key in _STANDARD_KEYS}
        source_trace = {key: "rule" for key in _STANDARD_KEYS}
        return {
            **profile,
            "extraction_confidence": rule_conf,
            "field_confidence": field_confidence,
            "source_trace": source_trace,
            "warnings": [],
        }

    elif mode == "llm_only":
        try:
            profile_raw, missing_p0, llm_conf = extract_requirements_llm(text, use_llm=True)
            llm_result = profile_raw
            llm_result["warnings"] = []
            llm_result["missing_data_P0"] = missing_p0
        except Exception as e:
            print(f"[tender_service] LLM extraction failed: {e}", file=sys.stderr)
            if fallback_to_rule:
                warnings = [f"LLM extraction failed, fell back to rule: {e}"]
                rule_result = extract_with_regex(text)
                rule_result["warnings"] = warnings
                profile = _build_profile_from_result(rule_result, source="regex")
                _ensure_standard_keys(profile)
                rule_conf = rule_result.get("extraction_confidence", 0.35)
                field_confidence = {key: rule_conf for key in _STANDARD_KEYS}
                source_trace = {key: "rule" for key in _STANDARD_KEYS}
                return {
                    **profile,
                    "extraction_confidence": rule_conf,
                    "field_confidence": field_confidence,
                    "source_trace": source_trace,
                    "warnings": warnings,
                }
            else:
                raise

        profile = _build_profile_from_result(llm_result, source="llm")
        _ensure_standard_keys(profile)
        field_confidence = {key: llm_conf for key in _STANDARD_KEYS}
        source_trace = {key: "llm" for key in _STANDARD_KEYS}
        return {
            **profile,
            "extraction_confidence": llm_conf,
            "field_confidence": field_confidence,
            "source_trace": source_trace,
            "warnings": llm_result.get("warnings", []),
        }

    elif mode == "hybrid":
        # Step 1: rule extraction
        rule_result = extract_with_regex(text)
        rule_result["warnings"] = []
        rule_conf = rule_result.get("extraction_confidence", 0.35)

        # Step 2: LLM extraction
        try:
            profile_raw, missing_p0, llm_conf = extract_requirements_llm(text, use_llm=True)
            llm_result = profile_raw
            llm_result["warnings"] = []
            llm_result["missing_data_P0"] = missing_p0
        except Exception as e:
            print(f"[tender_service] Hybrid LLM step failed: {e}, falling back to rule", file=sys.stderr)
            warnings = [f"LLM extraction failed in hybrid mode, rule only: {e}"]
            rule_result["warnings"] = warnings
            profile = _build_profile_from_result(rule_result, source="regex")
            _ensure_standard_keys(profile)
            field_confidence = {key: rule_conf for key in _STANDARD_KEYS}
            source_trace = {key: "rule" for key in _STANDARD_KEYS}
            return {
                **profile,
                "extraction_confidence": rule_conf,
                "field_confidence": field_confidence,
                "source_trace": source_trace,
                "warnings": warnings,
            }

        # Step 3: merge
        merge_result = _merge_extraction_results(rule_result, llm_result)

        # Build final profile from merge result
        profile = {}
        for key in _STANDARD_KEYS:
            rule_val = rule_result.get(key)
            llm_val = llm_result.get(key)

            if key in _NUMERIC_FIELDS:
                profile[key] = rule_val if rule_val is not None else llm_val
            elif key in _SEMANTIC_FIELDS:
                llm_default = "中"
                profile[key] = (llm_val if (llm_val and llm_val != llm_default) else
                                 (rule_val if (rule_val and rule_val != "中") else llm_val))
            elif key == "contract_years":
                profile[key] = rule_val if rule_val is not None else llm_val
            elif key in _MISSING_P1_KEYS:
                profile[key] = (llm_val if (llm_val and llm_val != "待确认") else
                                 (rule_val if (rule_val and rule_val != "待确认") else "待确认"))
            else:
                profile[key] = llm_val if llm_val is not None else rule_val

        _ensure_standard_keys(profile)

        return {
            **profile,
            "extraction_confidence": merge_result["extraction_confidence"],
            "field_confidence": merge_result["field_confidence"],
            "source_trace": merge_result["source_trace"],
            "missing_p0": merge_result["missing_p0"],
            "missing_p1": merge_result["missing_p1"],
            "warnings": merge_result["warnings"],
            "raw_rule_result": merge_result["raw_rule_result"],
            "raw_llm_result": merge_result["raw_llm_result"],
        }

    elif mode == "analysis":
        # Two-phase: tender deep analysis + structured normalization
        # Returns a unified result with canonical v0.2 keys:
        #   mode, analysis_result (full analysis), normalized_fields (field traces),
        #   summary (critical_missing_count, cost_model_ready, ...),
        #   plus underscore-prefixed fields for backward compat.
        try:
            result = analyze_and_extract(text)

            # Build normalized_fields dict from field objects (value/status/priority/...)
            normalized_fields = {}
            for key, val in result.items():
                if key.startswith("_") or key.startswith("analysis_") or key in (
                    "critical_missing_items", "important_missing_items",
                    "clarification_questions", "readiness", "quality_scores", "meta",
                ):
                    continue
                if isinstance(val, dict) and "value" in val and "status" in val:
                    normalized_fields[key] = val

            # Build summary dict
            readiness = result.get("readiness") or {}
            qs = result.get("quality_scores") or {}
            summary = {
                "critical_missing_count": len(result.get("critical_missing_items") or []),
                "important_missing_count": len(result.get("important_missing_items") or []),
                "clarification_questions_count": len(result.get("clarification_questions") or []),
                "cost_model_ready": readiness.get("for_cost_model", True),
                "solution_design_ready": readiness.get("for_solution_design", True),
                "contract_review_ready": readiness.get("for_contract_review", True),
                "readiness_score": qs.get("readiness_score", 0.0),
            }

            # Flatten scalar values for backward compat with existing callers
            # IMPORTANT: preserve field dict objects (status/value/basis) — they are needed
            # by downstream cost_model_input builder for accurate readiness computation.
            flat = {}
            for key, val in result.items():
                if key.startswith("_"):
                    continue
                if isinstance(val, dict) and "value" in val:
                    # Keep field dict intact (not just the scalar) so that downstream
                    # can read status/source_basis and compute readiness accurately.
                    flat[key] = val  # preserve full field object
                else:
                    flat[key] = val

            # Attach the full analysis result + summary + meta (underscore-prefixed)
            flat["_analysis_report"] = result.get("_analysis_report", "")
            flat["_structured"] = result.get("_structured", {})
            flat["_raw_llm_response"] = result.get("_raw_llm_response", "")
            flat["_clarification_questions"] = result.get("clarification_questions", [])
            flat["_quality_score"] = result.get("quality_scores", {})
            flat["_downstream_input"] = result.get("_downstream_input", {})
            flat["_readiness"] = readiness
            flat["_field_traces"] = normalized_fields

            # Unified v0.2 return keys (Max's suggestion #4)
            flat["_analysis_result"] = {
                "analysis_markdown": result.get("analysis_markdown", ""),
                "analysis_sections": result.get("analysis_sections", {}),
                "critical_missing_items": result.get("critical_missing_items", []),
                "important_missing_items": result.get("important_missing_items", []),
                "clarification_questions": result.get("clarification_questions", []),
                "risks": result.get("_quality_score", {}).get("risks", []),
                "ambiguities": result.get("_quality_score", {}).get("ambiguities", []),
                "downstream_hints": result.get("_downstream_input", {}),
            }
            flat["_summary"] = summary
            flat["_meta"] = result.get("meta", {})

            return flat
        except Exception as e:
            print(f"[tender_service] Analysis mode failed: {e}", file=sys.stderr)
            if fallback_to_rule:
                warnings = [f"Tender analysis failed, fell back to rule: {e}"]
                rule_result = extract_with_regex(text)
                rule_result["warnings"] = warnings
                profile = _build_profile_from_result(rule_result, source="regex")
                _ensure_standard_keys(profile)
                rule_conf = rule_result.get("extraction_confidence", 0.35)
                field_confidence = {key: rule_conf for key in _STANDARD_KEYS}
                source_trace = {key: "rule" for key in _STANDARD_KEYS}
                return {
                    **profile,
                    "extraction_confidence": rule_conf,
                    "field_confidence": field_confidence,
                    "source_trace": source_trace,
                    "warnings": warnings,
                }
            else:
                raise

    else:
        raise ValueError(f"Unknown extraction mode: {mode!r}. Must be one of: rule_only, llm_only, hybrid, analysis")
