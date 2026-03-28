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


# =============================================================================
# Regex-based extraction (fallback / quick preview)
# =============================================================================

_INDUSTRY_MAP = {
    "电商": ["电商", "电子商务", "天猫", "京东", "淘宝", "拼多多", "抖音电商"],
    "3PL": ["3PL", "第三方物流", "物流外包", "货运代理"],
    "零售": ["零售", "商超", "便利店", "百货", "购物中心"],
    "制造": ["制造", "生产商", "工厂", "制造业"],
    "快递": ["快递", "速运", "快运", "落地配"],
    "医药": ["医药", "制药", "医疗", "医疗器械"],
    "食品": ["食品", "饮料", "乳制品", "调味品"],
    "生鲜": ["生鲜", "冷链", "农产品", "水产"],
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
        "industry": "电商",
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
    m = re.search(r"SKU[是为约：:\s]*(\d[\d,\.]*)", text)
    if not m:
        m = re.search(r"(\d[\d,\.]*)\s*(?:SKU|种|品类)", text)
    if m:
        profile["sku_count"] = int(float(m.group(1).replace(",", "")))

    # Daily orders
    for pat in [r"日[均]?[订单件][量为]?[是约]?\s*(\d[\d,\.]*)", r"(\d[\d,\.]*)\s*(?:单|件)/[天日]"]:
        m = re.search(pat, text)
        if m:
            profile["daily_orders"] = int(float(m.group(1).replace(",", "")))
            break

    # Inventory
    m = re.search(r"库存[量为]?\s*(\d[\d,\.]*)", text)
    if m:
        profile["inventory"] = int(float(m.group(1).replace(",", "")))

    # Contract years
    m = re.search(r"合同[期为]?\s*(\d)\s*年", text)
    if m:
        profile["contract_years"] = int(m.group(1))

    # Budget
    for level, keywords in [("高", ["高预算", "预算高", "预算充足"]), ("中", ["中档", "中等", "预算中"]), ("低", ["低预算", "预算紧张"])]:
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
    if not profile["contract_years"]:
        missing.append("contract_years")
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
