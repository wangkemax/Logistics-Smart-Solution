"""
LLM Tender Requirement Extractor
==============================
Extracts structured project profile from tender documents using:
1. MiniMax API (if API key available in env or .env)
2. OpenAI-compatible API (if OPENAI_API_KEY set)
3. Enhanced regex fallback with field-level confidence scoring

Usage:
    profile, missing_p0, confidence = extract_requirements_llm(tender_text)
"""

import os
import re
import json
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# =============================================================================
# Field importance weights for overall confidence calculation
# =============================================================================
FIELD_WEIGHTS = {
    "warehouse_area": 3,
    "sku_count": 3,
    "daily_orders": 3,
    "inventory": 2,
    "labor_cost_level": 2,
    "budget_level": 2,
    "automation_expectation": 2,
    "contract_years": 1,
    "go_live_date": 1,
    "industry": 2,
    "region": 2,
    "project_name": 1,
    "client_name": 1,
}
TOTAL_WEIGHT = sum(FIELD_WEIGHTS.values())


# =============================================================================
# Regex pattern collections for each field
# Each tuple: (compiled_pattern, description)
# =============================================================================

_WAREHOUSE_AREA_PATTERNS = [
    (re.compile(r'(\d[\d,\.]*)\s*(?:平米|㎡|平方米|m²|sqm)', re.I), 'area_sqm_direct'),
    (re.compile(r'(?:仓库|仓储|物流|配送|库房|厂房|作业|货架)?[面面]积[是为约：:\s]*(\d[\d,\.]*)', re.I), 'area_prefix'),
    (re.compile(r'(\d[\d,\.]*)\s*(?:平方|平方米|平米|㎡)', re.I), 'area_sqm_suffix'),
    (re.compile(r'(?:总|建筑|使用)?[面面]积[为是约]?\s*(\d[\d,\.]*)', re.I), 'area_total'),
    (re.compile(r'(\d+)\s*-\s*(\d+)\s*(?:平米|㎡|平方米)', re.I), 'area_range'),
    (re.compile(r'(?:约|大概|大约|近)?(\d[\d,\.]*)\s*(?:千|万)?平米', re.I), 'area_thousands'),
    (re.compile(r'(?:仓储|仓库|库房|物流中心)[面面]积[为是约]?\s*(\d[\d,\.]*)', re.I), 'area_explicit'),
    (re.compile(r'(\d[\d,\.]*)\s*坪', re.I), 'area_ping'),
]

_SKU_COUNT_PATTERNS = [
    (re.compile(r'SKU[：:\s]*(?:数量|数|量)?[是为约]?\s*(\d[\d,\.]*)', re.I), 'sku_direct'),
    (re.compile(r'sku[：:\s]*(?:数量|数|量)?[是为约]?\s*(\d[\d,\.]*)', re.I), 'sku_lowercase'),
    (re.compile(r'商品[种种类品][数数量][为是约]?[：:\s]*(\d[\d,\.]*)', re.I), 'sku_goods'),
    (re.compile(r'(\d[\d,\.]*)\s*(?:种|品|sku|SKU|品类|品种)', re.I), 'sku_suffix'),
    (re.compile(r'(?:SKU|sku)[^0-9]*(\d{1,3}(?:,\d{3})+(?:\.\d+)?)', re.I), 'sku_formatted'),
    (re.compile(r'(\d[\d,\.]*)\s*(?:万|千)?(?:个)?(?:SKU|sku|单品|商品)', re.I), 'sku_with_unit'),
    (re.compile(r'单品[数数量][为是约]?[：:\s]*(\d[\d,\.]*)', re.I), 'sku_single'),
    (re.compile(r'产品[种种类][数数量][为是约]?[：:\s]*(\d[\d,\.]*)', re.I), 'sku_product'),
]

_DAILY_ORDERS_PATTERNS = [
    (re.compile(r'日[均]?(?:订单|订单量|票)[为是约]?[：:\s]*(\d[\d,\.]*)', re.I), 'orders_daily'),
    (re.compile(r'日[均]?[收件][量为]?[为是约]?[：:\s]*(\d[\d,\.]*)', re.I), 'orders_inbound'),
    (re.compile(r'日[均]?[出货件][量为]?[为是约]?[：:\s]*(\d[\d,\.]*)', re.I), 'orders_outbound'),
    (re.compile(r'日[均]?[进][货件][量为]?[为是约]?[：:\s]*(\d[\d,\.]*)', re.I), 'orders_inout'),
    (re.compile(r'日[均]?(?:处理|操作|完成)[量为]?[为是约]?[：:\s]*(\d[\d,\.]*)', re.I), 'orders_processing'),
    (re.compile(r'日[均]?[吞吐][吐量][为是约]?[：:\s]*(\d[\d,\.]*)', re.I), 'orders_throughput'),
    (re.compile(r'(\d[\d,\.]*)\s*(?:单|票|件|单量|票量)/(?:天|日|每日)', re.I), 'orders_perday'),
    (re.compile(r'(?:日均|日|每天)[订单件票][为是约]?\s*(\d[\d,\.]*)', re.I), 'orders_explicit'),
    (re.compile(r'(?:出货|出库|发货|配送|派送)[量为]?[为是约]?[：:\s]*(\d[\d,\.]*)', re.I), 'orders_shipping'),
]

_INVENTORY_PATTERNS = [
    # "库存容量约50万件" — capacity followed by value with unit multiplier
    (re.compile(r'库[存]?容[量约]*[为是约]?\s*[：:\s]*(\d[\d,\.]*)\s*(?:万|千|百)?(?:件|个|箱|托|单元|单位)', re.I), 'inv_cap_val'),
    # "库存量约50万件" — 容量 with units multiplier
    (re.compile(r'库[存储][量][为是约]?\s*[：:\s]*(\d[\d,\.]*)\s*(?:万|千|百)?(?:件|个|箱|托|单元|单位)', re.I), 'inv_liang_val'),
    # "库存约50万件" — 库 + 存 + 约 + value with unit
    (re.compile(r'库[存储][约]?\s*[：:\s]*(\d[\d,\.]*)\s*(?:万|千|百)?(?:件|个|箱|托|单元|单位)', re.I), 'inv_ku_val'),
    # "约50万件" or "50万件" — bare number with unit multiplier, at start of a phrase
    (re.compile(r'[约]?\s*[：:\s]*(\d[\d,\.]*)\s*(?:万|千|百)?(?:件|个|箱|托|单元|单位)', re.I), 'inv_bare_val'),
    # "库存量50" — without unit multiplier
    (re.compile(r'库[存储][量][为是约]?\s*[：:\s]*(\d[\d,\.]*)', re.I), 'inv_liang'),
    # "库存容量50" — without unit
    (re.compile(r'库[存]?容[量][为是约]?\s*[：:\s]*(\d[\d,\.]*)', re.I), 'inv_capacity'),
    # "库存品件数" style
    (re.compile(r'库[存品]件[数数量][为是约]?\s*[：:\s]*(\d[\d,\.]*)', re.I), 'inv_pieces'),
    # "在库量50"
    (re.compile(r'在[库][存]?[货]?[量][为是约]?\s*[：:\s]*(\d[\d,\.]*)', re.I), 'inv_onhand'),
    # "50万件" bare with unit
    (re.compile(r'(\d[\d,\.]*)\s*(?:万|千|百)?(?:件|个|箱|托|单元|单位)', re.I), 'inv_units'),
]

_LABOR_COST_LEVEL_PATTERNS = [
    (re.compile(r'人工成本(低|便)', re.I), 'labor_low_1'),
    (re.compile(r'人工(便宜|低廉|成本低|费用低)', re.I), 'labor_low_2'),
    (re.compile(r'劳务成本低', re.I), 'labor_low_3'),
    (re.compile(r'用工成本低', re.I), 'labor_low_4'),
    (re.compile(r'(低|便).*人工成本', re.I), 'labor_low_5'),
    (re.compile(r'人工成本(中|等|平)', re.I), 'labor_mid_1'),
    (re.compile(r'人工(中等|一般|普通|费用中)', re.I), 'labor_mid_2'),
    (re.compile(r'工资水平(中等|中等偏)', re.I), 'labor_mid_3'),
    (re.compile(r'劳务成本中', re.I), 'labor_mid_4'),
    (re.compile(r'(中).*人工成本', re.I), 'labor_mid_5'),
    (re.compile(r'人工成本(高|昂|贵)', re.I), 'labor_high_1'),
    (re.compile(r'人工(贵|高|成本高|费用高)', re.I), 'labor_high_2'),
    (re.compile(r'工资水平(高|较高)', re.I), 'labor_high_3'),
    (re.compile(r'劳务成本高', re.I), 'labor_high_4'),
    (re.compile(r'(高|贵).*人工成本', re.I), 'labor_high_5'),
]

_BUDGET_LEVEL_PATTERNS = [
    (re.compile(r'预[算期][为是约]?[：:\s]*(高)', re.I), 'budget_high_1'),
    (re.compile(r'(?:高|充足|充裕|宽裕).*预[算期]', re.I), 'budget_high_2'),
    (re.compile(r'预算(充足|充裕|宽裕|高)', re.I), 'budget_high_3'),
    (re.compile(r'投[资入][为是约]?[：:\s]*(高)', re.I), 'budget_high_4'),
    (re.compile(r'投资[预算][为是约]?[：:\s]*(高)', re.I), 'budget_high_5'),
    (re.compile(r'预[算期][为是约]?[：:\s]*(中)', re.I), 'budget_mid_1'),
    (re.compile(r'(?:中|中档|中等|适中|一般).*预[算期]', re.I), 'budget_mid_2'),
    (re.compile(r'预算(中|中档|中等|适中|一般)', re.I), 'budget_mid_3'),
    (re.compile(r'投[资入][为是约]?[：:\s]*(中)', re.I), 'budget_mid_4'),
    (re.compile(r'预[算期][为是约]?[：:\s]*(低|紧)', re.I), 'budget_low_1'),
    (re.compile(r'(?:低|紧张|有限|受限|控制).*预[算期]', re.I), 'budget_low_2'),
    (re.compile(r'预算(紧张|有限|受限|控制|低)', re.I), 'budget_low_3'),
    (re.compile(r'投[资入][为是约]?[：:\s]*(低|紧)', re.I), 'budget_low_4'),
    (re.compile(r'成本[控制预算][为是约]?[：:\s]*(低|紧)', re.I), 'budget_low_5'),
]

_AUTOMATION_EXPECTATION_PATTERNS = [
    (re.compile(r'自动化(程?度)?(低|弱)', re.I), 'auto_low_1'),
    (re.compile(r'(低|弱).*自动化', re.I), 'auto_low_2'),
    (re.compile(r'半自动[化机]', re.I), 'auto_low_3'),
    (re.compile(r'(?:手工|人工作业|人工作|人工操作)为主', re.I), 'auto_low_4'),
    (re.compile(r'智能化(程?度)?(低|弱)', re.I), 'auto_low_5'),
    (re.compile(r'自动化(程?度)?(中|一般|适)', re.I), 'auto_mid_1'),
    (re.compile(r'(?:中|一般|适度|适中).*自动化', re.I), 'auto_mid_2'),
    (re.compile(r'部分[自动智能]化', re.I), 'auto_mid_3'),
    (re.compile(r'[自动智能]化[+加]人[工配]', re.I), 'auto_mid_4'),
    (re.compile(r'人机[结合配][作协]', re.I), 'auto_mid_5'),
    (re.compile(r'自动化(程?度)?(高|强)', re.I), 'auto_high_1'),
    (re.compile(r'(?:高|强|高度|强).*自动化', re.I), 'auto_high_2'),
    (re.compile(r'全[面]?自动[化机]', re.I), 'auto_high_3'),
    (re.compile(r'无[人操作]化', re.I), 'auto_high_4'),
    (re.compile(r'[无少]人[仓配]库', re.I), 'auto_high_5'),
    (re.compile(r'(?:智能|智慧)[化库配]', re.I), 'auto_high_6'),
    (re.compile(r'[数字智慧]化[仓配物]', re.I), 'auto_high_7'),
]

_GO_LIVE_DATE_PATTERNS = [
    (re.compile(r'(\d{4})[年/\-.](\d{1,2})(?:月)?'), 'date_ymd'),
    (re.compile(r'(\d{4})年(\d{1,2})月'), 'date_ym'),
    (re.compile(r'(?:预计?|计划|目标|期望)?(?:上线|投运|交付|使用|启动|开始)[为是]?[：:\s]*(\d{4})[年/\-.](\d{1,2})', re.I), 'date_planned'),
    (re.compile(r'(?:预计?|计划)?(?:交付|投产|启动|开始)[为是]?[：:\s]*(\d{4})[年/\-.](\d{1,2})', re.I), 'date_delivery'),
    (re.compile(r'(\d{4})[年/\-.](\d{1,2})[月/\-.](\d{1,2})'), 'date_ymd_full'),
    (re.compile(r'(?:Q([1-4]))\s*(\d{4})'), 'date_quarter'),
    (re.compile(r'(\d{4})年第([一二三四])季度'), 'date_cn_quarter'),
    (re.compile(r'(?:年前?|近)?(\d{1,2})个月内?'), 'date_months'),
]

_INDUSTRY_PATTERNS = [
    (re.compile(r'电商|电子商务|天猫|京东|淘宝|拼多多|抖音电商|小红书|唯品会', re.I), 'ind_ecommerce'),
    (re.compile(r'3PL|第三方物流|物流外包|货运代理', re.I), 'ind_3pl'),
    (re.compile(r'零售|商超|便利店|百货|购物中心|超市|大卖场', re.I), 'ind_retail'),
    (re.compile(r'制造|生产商|工厂|制造业|生产型', re.I), 'ind_mfg'),
    (re.compile(r'快递|速运|快运|落地配', re.I), 'ind_express'),
    (re.compile(r'医药|制药|医疗|医疗器械|药品', re.I), 'ind_pharma'),
    (re.compile(r'食品|饮料|乳制品|调味品|烘焙', re.I), 'ind_food'),
    (re.compile(r'生鲜|冷链|农产品|水产|果蔬', re.I), 'ind_fresh'),
]

_REGION_PATTERNS = [
    (re.compile(r'华东|Shanghai|Jiangsu|Zhejiang|Anhui', re.I), 'reg_east'),
    (re.compile(r'华南|广东|广西|海南|Guangdong|Guangxi|Hainan', re.I), 'reg_south'),
    (re.compile(r'华北|北京|天津|河北|Beijing|Tianjin|Hebei', re.I), 'reg_north'),
    (re.compile(r'华中|湖北|湖南|河南|Hubei|Hunan|Henan', re.I), 'reg_central'),
    (re.compile(r'西部|四川|重庆|陕西|新疆|甘肃|Chongqing|Shaanxi', re.I), 'reg_west'),
    (re.compile(r'东北|辽宁|吉林|黑龙江|Liaoning|Jilin|Heilongjiang', re.I), 'reg_ne'),
]

_CONTRACT_YEARS_PATTERNS = [
    (re.compile(r'合[同约](?:期|期限)?[为是约]?\s*(\d+)\s*(?:年|个月)', re.I), 'ct_years_1'),
    (re.compile(r'合作?期限[为是约]?\s*(\d+)\s*(?:年|个月)', re.I), 'ct_years_2'),
    (re.compile(r'合同期[限年][为是约]?\s*(\d+)', re.I), 'ct_years_3'),
    (re.compile(r'(\d+)\s*年[合合][同约]', re.I), 'ct_years_4'),
    (re.compile(r'(?:租|托管|运营)(?:期|限)[为是约]?\s*(\d+)\s*(?:年|个月)', re.I), 'ct_years_5'),
    (re.compile(r'((?:长)?期)?合同[为是约]?\s*(\d+)\s*(?:年|个月)', re.I), 'ct_years_6'),
]

# Map from field name -> list of (compiled_pattern, description)
FIELD_PATTERN_MAP = {
    "warehouse_area": _WAREHOUSE_AREA_PATTERNS,
    "sku_count": _SKU_COUNT_PATTERNS,
    "daily_orders": _DAILY_ORDERS_PATTERNS,
    "inventory": _INVENTORY_PATTERNS,
    "labor_cost_level": _LABOR_COST_LEVEL_PATTERNS,
    "budget_level": _BUDGET_LEVEL_PATTERNS,
    "automation_expectation": _AUTOMATION_EXPECTATION_PATTERNS,
    "go_live_date": _GO_LIVE_DATE_PATTERNS,
    "industry": _INDUSTRY_PATTERNS,
    "region": _REGION_PATTERNS,
    "contract_years": _CONTRACT_YEARS_PATTERNS,
}


# =============================================================================
# Prompt templates
# =============================================================================

EXTRACTION_PROMPT = '''You are a logistics presale Tender Requirement Extractor.

Tender Document:
{tender_text}

Extract a complete project profile as JSON. Return ONLY the JSON object, no explanation.
Fields:
- project_name: 项目名称 or "待确认"
- client_name: 客户名称 or "待确认"
- industry: 电商/3PL/零售/制造/快递/医药/食品/生鲜
- region: 华东/华南/华北/华中/西部
- warehouse_area: number (sqm)
- sku_count: number
- daily_orders: number
- inventory: number (units)
- labor_cost_level: 低/中/高
- budget_level: 低/中/高
- automation_expectation: 低/中/高
- contract_years: number (e.g. 3 or 5)
- go_live_date: YYYY-MM or "待确认"
- missing_data_P0: string[] (blocking missing fields)
- missing_data_P1: string[] (important but non-blocking)
- extraction_confidence: number 0.0-1.0
- raw_requirements_summary: string (2-3 sentences)
- field_confidence: object (optional, map field_name -> 0.0-1.0 if you can self-assess)

If a field cannot be determined, use null.
Return ONLY valid JSON.
'''


# =============================================================================
# MiniMax API
# =============================================================================

def _get_minimax_token() -> Optional[str]:
    """Get a valid MiniMax access token from the OpenClaw gateway."""
    try:
        import subprocess
        result = subprocess.run(
            ['openclaw', 'gateway', 'token', '--help'],
            capture_output=True, text=True, timeout=5
        )
        if 'token' not in result.stdout.lower():
            return None
    except Exception:
        pass
    return None


def _call_minimax_llm(prompt: str, timeout: int = 30) -> Optional[dict]:
    """Call MiniMax or OpenAI API for LLM extraction."""
    api_key = os.getenv('MINIMAX_API_KEY') or os.getenv('OPENAI_API_KEY')
    if not api_key:
        try:
            env_path = PROJECT_ROOT / ".env"
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        if k == "MINIMAX_API_KEY" and not v.startswith("your"):
                            os.environ[k] = v
                api_key = os.getenv("MINIMAX_API_KEY")
        except Exception:
            pass
    if not api_key:
        return None

    base_url = 'https://api.minimaxi.com/anthropic'
    model = 'MiniMax-M2.7-highspeed'
    if not api_key.startswith('sk-api-'):
        base_url = 'https://api.openai.com/v1'
        model = 'gpt-4o-mini'

    import urllib.request
    payload = {
        'model': model,
        'max_tokens': 1024,
        'messages': [{'role': 'user', 'content': prompt}]
    }
    req_url = f'{base_url}/v1/messages'
    req = urllib.request.Request(
        req_url,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'anthropic-version': '2023-06-01',
        },
        method='POST'
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read())
            content_list = result.get('content', [])
            if isinstance(content_list, list):
                text = '\n'.join(b.get('text', '') for b in content_list if b.get('type') == 'text')
            else:
                text = content_list
            return _parse_json_response(text)
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        print(f'[LLM] HTTP {e.code} body: {body}')
        return None
    except Exception as e:
        print(f'[LLM] API call failed: {e}')
        return None


# =============================================================================
# JSON parsing helpers
# =============================================================================

def _parse_json_response(text: str) -> Optional[dict]:
    """Parse JSON from LLM response, handling markdown code blocks."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            candidate = match.group(0)
            parsed = json.loads(candidate)
            if isinstance(parsed, dict) and 'industry' in parsed:
                return parsed
        except json.JSONDecodeError:
            pass
    return None


# =============================================================================
# Field-level confidence scoring helpers
# =============================================================================

def _run_field_patterns(text: str, patterns: list) -> tuple[int, int, str, list, str]:
    """
    Run a list of (compiled_regex, description) patterns against text and count matches.

    Args:
        text: The document text to search
        patterns: List of (compiled_regex, description) tuples

    Returns:
        (matched_count, total_patterns, first_match_value, list of matched_descriptions, full_match_text)
        full_match_text is the m.group(0) of the first match, used to detect units like 万/千/百.
    """
    matched = 0
    first_value = None
    descriptions = []
    full_match_text = ''
    for compiled_pat, desc in patterns:
        m = compiled_pat.search(text)
        if m:
            matched += 1
            descriptions.append(desc)
            if first_value is None:
                full_match_text = m.group(0)
                if m.lastindex and m.lastindex >= 1:
                    # Join all capture groups for multi-group patterns (e.g., YYYY年MM月)
                    parts = [m.group(i).strip() for i in range(1, m.lastindex + 1) if m.group(i)]
                    if parts:
                        first_value = ''.join(parts)
                    else:
                        first_value = full_match_text
                else:
                    first_value = full_match_text
    return matched, len(patterns), first_value, descriptions, full_match_text


def _extract_with_patterns(text: str) -> tuple[dict, dict, list]:
    """
    Run all field patterns against text and return field values, confidences, and warnings.

    Args:
        text: Raw tender document text

    Returns:
        (field_values_dict, field_confidence_dict, extraction_warnings)

    Each field's confidence = matched_patterns / total_patterns_for_that_field.
    Warnings are added for fields with 0 < confidence < 0.3 (low signal, high noise risk).
    """
    field_values = {}
    field_confidence = {}
    warnings = []

    for field_name, patterns in FIELD_PATTERN_MAP.items():
        matched, total, value, descriptions, full_match = _run_field_patterns(text, patterns)
        confidence = matched / total if total > 0 else 0.0
        field_confidence[field_name] = confidence

        if value is not None:
            # Detect unit multipliers from the full match text (captures surrounding context too)
            has_multiplier = bool(re.search(r'[万千百]', full_match)) if full_match else False
            parsed = _parse_pattern_value(field_name, value, descriptions, full_match, has_multiplier)
            field_values[field_name] = parsed
        else:
            field_values[field_name] = None

        if 0 < confidence < 0.3:
            warnings.append(
                f"Field '{field_name}' has low confidence ({confidence:.0%}), "
                f"value may be unreliable"
            )

    return field_values, field_confidence, warnings


def _parse_pattern_value(field_name: str, value: str, descriptions: list,
                          full_match_text: str = '', has_multiplier: bool = False) -> Optional:
    """
    Parse a matched regex value to the appropriate Python type for a given field.

    Args:
        field_name: Name of the field being parsed
        value: Raw matched string value (captured group, just the number)
        descriptions: List of pattern descriptions that matched (for level inference)
        full_match_text: The full regex match text (including units like 万/千/百)
        has_multiplier: Whether the full_match_text contains a multiplier unit

    Returns:
        Parsed value in the appropriate type (int, float, str, or None)
    """
    numeric_fields = {"warehouse_area", "sku_count", "daily_orders", "inventory"}
    level_fields = {"labor_cost_level", "budget_level", "automation_expectation"}

    if field_name in numeric_fields:
        try:
            multiplier = 1
            if has_multiplier:
                # Check full_match_text (not value) for the unit multiplier
                if bool(re.search(r'万', full_match_text)):
                    multiplier = 10000
                elif bool(re.search(r'千', full_match_text)):
                    multiplier = 1000
                elif bool(re.search(r'百', full_match_text)):
                    multiplier = 100
            cleaned = value.replace(",", "")
            cleaned = re.sub(r'[^\d.]', '', cleaned)
            return int(float(cleaned) * multiplier)
        except (ValueError, AttributeError, TypeError):
            try:
                return int(float(re.sub(r'[^\d.]', '', value)))
            except (ValueError, TypeError):
                return None

    elif field_name in level_fields:
        return _infer_level_from_descriptions(field_name, descriptions)

    elif field_name == "contract_years":
        try:
            years = int(float(re.sub(r'[^\d]', '', str(value))))
            if 1 <= years <= 20:
                return years
            return None
        except (ValueError, TypeError):
            return None

    elif field_name == "industry":
        return _infer_industry_from_descriptions(descriptions)

    elif field_name == "region":
        return _infer_region_from_descriptions(descriptions)

    elif field_name == "go_live_date":
        return _parse_go_live_date(value)

    return value


def _infer_level_from_descriptions(field_name: str, descriptions: list) -> Optional[str]:
    """Infer low/mid/high level from pattern descriptions."""
    if field_name == "labor_cost_level":
        if any("low" in d for d in descriptions):
            return "低"
        if any("mid" in d for d in descriptions):
            return "中"
        if any("high" in d for d in descriptions):
            return "高"
    elif field_name == "budget_level":
        if any("high" in d for d in descriptions):
            return "高"
        if any("mid" in d for d in descriptions):
            return "中"
        if any("low" in d for d in descriptions):
            return "低"
    elif field_name == "automation_expectation":
        if any("low" in d for d in descriptions):
            return "低"
        if any("mid" in d for d in descriptions):
            return "中"
        if any("high" in d for d in descriptions):
            return "高"
    return None


def _infer_industry_from_descriptions(descriptions: list) -> Optional[str]:
    """Infer industry from matched pattern descriptions."""
    name_map = {
        "ind_ecommerce": "电商",
        "ind_3pl": "3PL",
        "ind_retail": "零售",
        "ind_mfg": "制造",
        "ind_express": "快递",
        "ind_pharma": "医药",
        "ind_food": "食品",
        "ind_fresh": "生鲜",
    }
    for desc in descriptions:
        for key, val in name_map.items():
            if key in desc:
                return val
    return None


def _infer_region_from_descriptions(descriptions: list) -> Optional[str]:
    """Infer region from matched pattern descriptions."""
    name_map = {
        "reg_east": "华东",
        "reg_south": "华南",
        "reg_north": "华北",
        "reg_central": "华中",
        "reg_west": "西部",
        "reg_ne": "东北",
    }
    for desc in descriptions:
        for key, val in name_map.items():
            if key in desc:
                return val
    return None


def _parse_go_live_date(value: str) -> str:
    """
    Parse a go_live_date match into YYYY-MM format string.

    Args:
        value: Raw matched string — may be "YYYY年MM月", "YYYY年MM", or "20266" (joined year+month)

    Returns:
        YYYY-MM string or original value if parsing fails
    """
    try:
        # Try standard format: YYYY年MM月 or YYYY-MM or YYYY/MM
        m = re.match(r'(\d{4})[年/\-.](\d{1,2})', value)
        if m:
            year, month = m.group(1), m.group(2)
            return f"{year}-{int(month):02d}"
        # Try joined format: "20266" (year=2026, month=6) or "202606"
        if re.match(r'^\d{5,8}$', value):
            if len(value) == 5:  # YYYY + M (e.g., "20266")
                year = value[:4]
                month = value[4]
                return f"{year}-{int(month):02d}"
            elif len(value) == 6:  # YYYYM or YYYYMM
                year = value[:4]
                month = value[4:]
                return f"{year}-{int(month):02d}"
    except (ValueError, TypeError):
        pass
    return value


def _calculate_weighted_confidence(
    field_confidence: dict,
    field_values: dict,
) -> float:
    """
    Calculate overall weighted confidence across all profile fields.

    Args:
        field_confidence: dict mapping field_name -> confidence 0.0-1.0
        field_values: dict mapping field_name -> extracted value (None = not found)

    Returns:
        Overall confidence score 0.0-1.0, a weighted average where fields
        with values contribute their pattern-match confidence scaled by importance weight.
    """
    total_score = 0.0
    for field, weight in FIELD_WEIGHTS.items():
        conf = field_confidence.get(field, 0.0)
        value = field_values.get(field)
        if value is not None:
            total_score += conf * weight
    return min(total_score / TOTAL_WEIGHT, 1.0)


def _calculate_filled_confidence(profile: dict) -> float:
    """
    Calculate confidence based on what fraction of fields are filled.

    This is a simpler fallback when pattern-based confidence is not available.
    A field is considered "filled" if its value is not None and not "待确认".
    """
    count_filled = 0
    count_total = 0
    for field in FIELD_WEIGHTS:
        if field in ("project_name", "client_name", "go_live_date"):
            # These are secondary fields
            continue
        count_total += 1
        val = profile.get(field)
        if val is not None and val != "待确认":
            count_filled += 1
    return min(count_filled / max(count_total, 1), 1.0)


def _generate_extraction_warnings(
    profile: dict,
    field_confidence: dict,
    field_values: dict,
) -> list:
    """
    Generate warnings for fields that were guessed or have low confidence.

    Args:
        profile: The profile dict being returned
        field_confidence: Per-field confidence scores
        field_values: Values extracted by regex patterns

    Returns:
        List of warning strings for fields that were filled by fallback logic
        rather than being explicitly stated in the document.
    """
    warnings = []
    low_confidence_fields = [
        fname for fname, conf in field_confidence.items()
        if 0 < conf < 0.3 and field_values.get(fname) is not None
    ]
    for fname in low_confidence_fields:
        warnings.append(
            f"Field '{fname}' has low pattern-match confidence "
            f"({field_confidence[fname]:.0%}), value may be a partial match"
        )
    return warnings


# =============================================================================
# Enhanced regex extraction (fallback + complement)
# =============================================================================

def _extract_with_regex(text: str) -> tuple[dict, list, float]:
    """
    Enhanced regex-based extraction with field-level confidence scoring.
    Used as fallback when LLM is unavailable, or to fill missing fields.

    Returns:
        (profile_dict, missing_p0_list, confidence_score)
    """
    from backend.services.tender_service import extract_with_regex as _regex_extract
    regex_profile = _regex_extract(text)

    # Run pattern-based extraction for confidence scoring
    field_values, field_confidence, pattern_warnings = _extract_with_patterns(text)

    # Merge pattern-extracted values with regex results
    # Prefer pattern values when they are more specific (e.g., "500000" vs "50")
    for key in field_values:
        if field_values[key] is not None:
            regex_val = regex_profile.get(key)
            # Use pattern value if regex didn't find it, or if pattern is more granular
            if regex_val is None:
                regex_profile[key] = field_values[key]
            elif key == 'inventory' and field_values[key] != regex_val:
                # inventory might have unit multipliers (万件) — prefer the more specific value
                regex_profile[key] = field_values[key]
            elif key == 'go_live_date' and field_values[key] not in (None, '待确认'):
                regex_profile[key] = field_values[key]

    # Compute weighted confidence
    confidence = _calculate_weighted_confidence(field_confidence, field_values)
    if confidence == 0.0:
        # Fallback to simple filled-field count
        confidence = _calculate_filled_confidence(regex_profile)

    regex_profile['extraction_confidence'] = confidence
    regex_profile['field_confidence'] = field_confidence
    regex_profile['extraction_warnings'] = pattern_warnings

    missing_p0 = regex_profile.get("missing_p0", [])
    return regex_profile, missing_p0, confidence


# =============================================================================
# Main extraction function
# =============================================================================

def extract_requirements_llm(
    tender_text: str,
    use_llm: bool = True,
) -> tuple[dict, list, float]:
    """
    Extract structured project profile from tender document.

    Args:
        tender_text: Raw tender document text
        use_llm: If True, try LLM first then fallback. If False, use regex only.

    Returns:
        (profile_dict, missing_p0_list, confidence_score)

    The returned profile dict includes additional keys beyond the basic fields:
        - field_confidence: dict mapping field_name -> 0.0-1.0
        - extraction_warnings: list[str] of low-confidence field warnings
        - extraction_method: "llm", "regex", or "llm+regex"

    The API is backward compatible: the first three return values are the same
    as before (profile, missing_p0, confidence).
    """
    if not tender_text or len(tender_text.strip()) < 20:
        return _extract_with_regex('')

    # Run pattern extraction in parallel to get confidence scores
    field_values, field_confidence, pattern_warnings = _extract_with_patterns(tender_text)

    if use_llm:
        prompt = EXTRACTION_PROMPT.format(tender_text=tender_text[:8000])
        llm_result = _call_minimax_llm(prompt)

        if llm_result:
            llm_conf = llm_result.get('extraction_confidence') or 0.5
            missing_p0 = llm_result.get('missing_data_P0') or []
            llm_field_conf = llm_result.get('field_confidence', {})

            profile = {
                'project_name': llm_result.get('project_name') or '待确认',
                'client_name': llm_result.get('client_name') or '待确认',
                'industry': llm_result.get('industry') or field_values.get('industry') or '电商',
                'region': llm_result.get('region') or field_values.get('region') or '华东',
                'warehouse_area': llm_result.get('warehouse_area') or field_values.get('warehouse_area'),
                'sku_count': llm_result.get('sku_count') or field_values.get('sku_count'),
                'daily_orders': llm_result.get('daily_orders') or field_values.get('daily_orders'),
                'inventory': llm_result.get('inventory') or field_values.get('inventory'),
                'labor_cost_level': llm_result.get('labor_cost_level') or field_values.get('labor_cost_level') or '中',
                'budget_level': llm_result.get('budget_level') or field_values.get('budget_level') or '中',
                'automation_expectation': llm_result.get('automation_expectation') or field_values.get('automation_expectation') or '中',
                'contract_years': llm_result.get('contract_years') or field_values.get('contract_years') or 3,
                'go_live_date': llm_result.get('go_live_date') or field_values.get('go_live_date') or '待确认',
                'extraction_confidence': llm_conf,
                'missing_data_P0': missing_p0,
            }

            # Fill any remaining None fields with regex extraction
            _fill_missing_fields(tender_text, profile, field_values)

            # Compute per-field confidence:
            # For fields filled by LLM: use LLM confidence (from llm_field_conf or overall llm_conf)
            # For fields filled by regex: use field_confidence from pattern matching
            final_field_confidence = {}
            for fname in FIELD_WEIGHTS:
                if fname in llm_field_conf:
                    final_field_confidence[fname] = llm_field_conf[fname]
                elif profile.get(fname) is not None and fname in field_values and field_values.get(fname) == profile.get(fname):
                    # Field was filled by regex pattern matching
                    final_field_confidence[fname] = field_confidence.get(fname, 0.0)
                elif profile.get(fname) is not None:
                    # Field was filled by LLM
                    final_field_confidence[fname] = llm_conf
                else:
                    # Field not filled
                    final_field_confidence[fname] = field_confidence.get(fname, 0.0)

            # Merge pattern warnings with any LLM-provided warnings
            extraction_warnings = list(pattern_warnings)
            if llm_result.get('warnings'):
                extraction_warnings.extend(llm_result.get('warnings'))

            # Add warning for fields that were filled by guess/default
            for fname, val in profile.items():
                if fname in FIELD_WEIGHTS and val is not None:
                    conf = final_field_confidence.get(fname, 0.0)
                    if conf < 0.3 and val not in ('待确认', '中', '低', '高'):
                        extraction_warnings.append(
                            f"Field '{fname}' has low confidence ({conf:.0%}), "
                            f"value '{val}' may be unreliable"
                        )

            # Compute overall weighted confidence
            overall_conf = _calculate_weighted_confidence(final_field_confidence, profile)

            # Ensure profile has field_confidence and extraction_warnings
            profile['field_confidence'] = final_field_confidence
            profile['extraction_warnings'] = extraction_warnings
            profile['extraction_method'] = 'llm'
            profile['extraction_confidence'] = overall_conf

            print(f'[LLM Extractor] LLM extraction success, confidence={overall_conf:.0%}')
            return profile, missing_p0, overall_conf

    # LLM failed or use_llm=False — fall back to enhanced regex
    regex_profile, missing_p0, regex_conf = _extract_with_regex(tender_text)
    return regex_profile, missing_p0, regex_conf


def _fill_missing_fields(text: str, profile: dict, field_values: dict):
    """
    Fill None fields in profile using expanded pattern extraction.

    This is called after LLM extraction to catch any fields the LLM didn't fill.
    Uses _extract_with_patterns results (passed as field_values) plus
    additional fallback patterns for fields that need special parsing.

    Args:
        text: Raw tender document text
        profile: Profile dict being built (may have None values)
        field_values: Already-extracted field values from _extract_with_patterns
    """
    # --- warehouse_area ---
    if profile.get('warehouse_area') is None:
        if field_values.get('warehouse_area') is not None:
            profile['warehouse_area'] = field_values['warehouse_area']
        else:
            # Try range patterns like "5000-8000平米"
            for pat in [
                r'(\d[\d,\.]*)\s*-\s*(\d[\d,\.]*)\s*(?:平米|㎡|平方米)',
                r'(?:约|大概)?(\d[\d,\.]*)\s*(?:千|万)?平米',
            ]:
                m = re.search(pat, text)
                if m:
                    try:
                        vals = [float(re.sub(r'[^\d.]', '', g)) for g in m.groups() if g]
                        if len(vals) == 2:
                            profile['warehouse_area'] = int(sum(vals) / 2)
                        else:
                            profile['warehouse_area'] = int(vals[0])
                        break
                    except (ValueError, IndexError):
                        pass

    # --- sku_count ---
    if profile.get('sku_count') is None:
        if field_values.get('sku_count') is not None:
            profile['sku_count'] = field_values['sku_count']

    # --- daily_orders ---
    if profile.get('daily_orders') is None:
        if field_values.get('daily_orders') is not None:
            profile['daily_orders'] = field_values['daily_orders']

    # --- inventory ---
    if profile.get('inventory') is None:
        if field_values.get('inventory') is not None:
            profile['inventory'] = field_values['inventory']

    # --- labor_cost_level ---
    if profile.get('labor_cost_level') in (None, '中'):
        if field_values.get('labor_cost_level') is not None:
            profile['labor_cost_level'] = field_values['labor_cost_level']
        else:
            # Additional patterns for labor cost
            for level, patterns in [
                ("低", [r'人工成本低', r'人工便宜', r'劳务成本低', r'用工成本低']),
                ("高", [r'人工成本高', r'人工贵', r'劳务成本高', r'用工成本高']),
            ]:
                if any(re.search(p, text) for p in patterns):
                    profile['labor_cost_level'] = level
                    break

    # --- budget_level ---
    if profile.get('budget_level') in (None, '中'):
        if field_values.get('budget_level') is not None:
            profile['budget_level'] = field_values['budget_level']
        else:
            for level, patterns in [
                ("高", [r'预算高', r'预算充足', r'预算充裕', r'高预算']),
                ("低", [r'预算低', r'预算紧张', r'预算有限', r'低预算']),
            ]:
                if any(re.search(p, text) for p in patterns):
                    profile['budget_level'] = level
                    break

    # --- automation_expectation ---
    if profile.get('automation_expectation') in (None, '中'):
        if field_values.get('automation_expectation') is not None:
            profile['automation_expectation'] = field_values['automation_expectation']
        else:
            for level, patterns in [
                ("高", [r'全自动化', r'无人仓', r'智能化', r'高度自动化', r'自动化程度高']),
                ("低", [r'半自动', r'手工为主', r'自动化程度低', r'人工作业']),
            ]:
                if any(re.search(p, text) for p in patterns):
                    profile['automation_expectation'] = level
                    break

    # --- contract_years ---
    if profile.get('contract_years') is None or profile.get('contract_years') == '待确认':
        if field_values.get('contract_years') is not None:
            profile['contract_years'] = field_values['contract_years']
        else:
            for pat in [
                r'合[同约]期[限年]?[为是约]?\s*(\d+)\s*(?:年|个月)',
                r'合作?期限[为是约]?\s*(\d+)\s*(?:年|个月)',
                r'合同期[限年][为是约]?\s*(\d+)',
                r'(\d+)\s*年[合合][同约]',
            ]:
                m = re.search(pat, text)
                if m:
                    try:
                        val = int(m.group(1))
                        if 1 <= val <= 20:
                            profile['contract_years'] = val
                            break
                    except (ValueError, IndexError):
                        pass

    # --- go_live_date ---
    if profile.get('go_live_date') == '待确认' or profile.get('go_live_date') is None:
        if field_values.get('go_live_date') is not None:
            profile['go_live_date'] = field_values['go_live_date']
        else:
            for pat in [
                r'(?:预计?|计划|目标)?[上线投运交付使用][为是]?[：:\s]*(\d{4})[年/\-.](\d{1,2})',
                r'(?:预计?|计划)?[交付|投产|启动][为是]?[：:\s]*(\d{4})[年/\-.](\d{1,2})',
                r'(\d{4})年(\d{1,2})月',
            ]:
                m = re.search(pat, text)
                if m:
                    try:
                        year, month = m.group(1), m.group(2)
                        profile['go_live_date'] = f"{year}-{int(month):02d}"
                        break
                    except (ValueError, IndexError):
                        pass

    # --- industry ---
    if profile.get('industry') in (None, '电商'):
        if field_values.get('industry') is not None:
            profile['industry'] = field_values['industry']

    # --- region ---
    if profile.get('region') in (None, '华东'):
        if field_values.get('region') is not None:
            profile['region'] = field_values['region']