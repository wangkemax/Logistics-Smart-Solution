"""
LLM Tender Requirement Extractor
==============================
Extracts structured project profile from tender documents using:
1. MiniMax API (if API key available in env or .env)
2. OpenAI-compatible API (if OPENAI_API_KEY set)
3. Enhanced regex fallback

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

If a field cannot be determined, use null.
Return ONLY valid JSON.
'''


# =============================================================================
# MiniMax API (via OpenClaw gateway token exchange)
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

    # Try reading from keychain or config
    # For now, return None (will fall back)
    return None


def _call_minimax_llm(prompt: str, timeout: int = 30) -> Optional[dict]:
    """
    Call MiniMax API directly.
    Requires MINIMAX_API_KEY env var or MiniMax OAuth token.
    """
    # Load .env if API key not in environment
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
    if not api_key:
        return None

    # Detect provider
    base_url = 'https://api.minimaxi.com/anthropic'
    model = 'MiniMax-M2.7-highspeed'

    if api_key.startswith('sk-api-'):
        # MiniMax API key (starts with sk-api-)
        base_url = 'https://api.minimaxi.com/anthropic'
        model = 'MiniMax-M2.7-highspeed'
    elif 'OPENAI' in os.environ.get('MINIMAX_API_KEY', '') or (api_key or '').startswith('sk-'):
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
            # MiniMax returns content as a list of blocks: [{"type": "text", "text": "..."}, ...]
            content_list = result.get('content', [])
            if isinstance(content_list, list):
                text_blocks = [b.get('text', '') for b in content_list if b.get('type') == 'text']
                text = '\n'.join(text_blocks)
            else:
                text = content_list
            return _parse_json_response(text)
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        print(f'[LLM] HTTP {e.code} body: {body}')
        return None
    except Exception as e:
        print(f'[LLM] MiniMax API call failed: {e}')
        return None


# =============================================================================
# JSON parsing helpers
# =============================================================================

def _parse_json_response(text: str) -> Optional[dict]:
    """Parse JSON from LLM response, handling markdown code blocks."""
    text = text.strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown
    match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try finding raw JSON object
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            # Validate it's actually JSON by checking for required fields
            candidate = match.group(0)
            parsed = json.loads(candidate)
            if isinstance(parsed, dict) and 'industry' in parsed:
                return parsed
        except json.JSONDecodeError:
            pass

    return None


# =============================================================================
# Enhanced regex extraction (fallback + complement)
# =============================================================================

def _extract_with_regex(text: str) -> tuple[dict, list, float]:
    """
    Enhanced regex-based extraction with higher confidence.
    Used as fallback when LLM is unavailable, or to fill missing fields.
    """
    from agents.orchestrator import extract_requirements as base_extract

    profile, missing_p0 = base_extract(text)
    confidence = profile.get('extraction_confidence', 0)

    # Post-process: try to fill None fields with additional patterns
    _fill_missing_fields(text, profile)

    # Re-calculate confidence based on filled fields
    filled = sum(1 for v in profile.values()
                 if v is not None and v != '待确认' and v != [])
    total_fields = 12  # core fields
    confidence = min(filled / total_fields, 1.0)
    profile['extraction_confidence'] = confidence

    return profile, missing_p0, confidence


def _fill_missing_fields(text: str, profile: dict):
    """Fill None fields using additional patterns."""
    # Try to find SKU with various patterns
    if profile.get('sku_count') is None:
        for pattern in [
            r'SKU[：:\s]*(\d[\d,]*)',
            r'sku[：:\s]*(\d[\d,]*)',
            r'商品[种类品类][：:\s]*(\d[\d,]*)',
            r'(\d[\d,]+)\s*(?:种|品|sku|SKU)',
        ]:
            m = re.search(pattern, text)
            if m:
                try:
                    profile['sku_count'] = int(re.sub(r'[^\d]', '', m.group(1)))
                    break
                except (ValueError, IndexError):
                    pass

    # Try to find daily orders
    if profile.get('daily_orders') is None:
        for pattern in [
            r'日均[订单票件量][：:\s]*(\d[\d,]*)',
            r'日处理[订单量][：:\s]*(\d[\d,]*)',
            r'日[出进][货库][量：:\s]*(\d[\d,]*)',
            r'(\d[\d,]+)\s*(?:单|票|件)/[天日]',
        ]:
            m = re.search(pattern, text)
            if m:
                try:
                    profile['daily_orders'] = int(re.sub(r'[^\d]', '', m.group(1)))
                    break
                except (ValueError, IndexError):
                    pass

    # Try to find inventory
    if profile.get('inventory') is None:
        for pattern in [
            r'库[存储][量容][：:\s]*(\d[\d,]*)',
            r'库[存品]件[数：:\s]*(\d[\d,]*)',
            r'在[库存][货物][量：:\s]*(\d[\d,]*)',
        ]:
            m = re.search(pattern, text)
            if m:
                try:
                    profile['inventory'] = int(re.sub(r'[^\d]', '', m.group(1)))
                    break
                except (ValueError, IndexError):
                    pass

    # Try to find contract years
    if profile.get('contract_years') is None or profile.get('contract_years') == '待确认':
        for pattern in [
            r'合[同约]期[限年][：:\s]*(\d+)',
            r'合同[期年][限：:\s]*(\d+)\s*(?:年|个月)',
            r'(\d+)\s*年[合合][同约]',
        ]:
            m = re.search(pattern, text)
            if m:
                try:
                    val = int(m.group(1))
                    if 1 <= val <= 10:
                        profile['contract_years'] = val
                        break
                except (ValueError, IndexError):
                    pass

    # Try to find budget level
    if profile.get('budget_level') == '中' and profile.get('labor_cost_level') == '中':
        for pattern in [
            r'预[算期][：:\s]*([低中高])',
            r'投[资入][：:\s]*([低中高])',
            r'预算[等水][：:\s]*([低中高])',
        ]:
            m = re.search(pattern, text)
            if m:
                level = m.group(1)
                if level in ['低', '中', '高']:
                    profile['budget_level'] = level
                    break


# =============================================================================
# Main extraction function
# =============================================================================

def extract_requirements_llm(tender_text: str, use_llm: bool = True) -> tuple[dict, list, float]:
    """
    Extract structured project profile from tender document.

    Args:
        tender_text: Raw tender document text
        use_llm: If True, try LLM first then fallback. If False, use regex only.

    Returns:
        (profile_dict, missing_p0_list, confidence_score)
    """
    if not tender_text or len(tender_text.strip()) < 20:
        return _extract_with_regex('')

    # Try LLM extraction first
    if use_llm:
        prompt = EXTRACTION_PROMPT.format(tender_text=tender_text[:8000])
        llm_result = _call_minimax_llm(prompt)

        if llm_result:
            confidence = llm_result.get('extraction_confidence') or 0.5
            missing_p0 = llm_result.get('missing_data_P0') or []

            profile = {
                'project_name': llm_result.get('project_name') or '待确认',
                'client_name': llm_result.get('client_name') or '待确认',
                'industry': llm_result.get('industry') or '电商',
                'region': llm_result.get('region') or '华东',
                'warehouse_area': llm_result.get('warehouse_area'),
                'sku_count': llm_result.get('sku_count'),
                'daily_orders': llm_result.get('daily_orders'),
                'inventory': llm_result.get('inventory'),
                'labor_cost_level': llm_result.get('labor_cost_level') or '中',
                'budget_level': llm_result.get('budget_level') or '中',
                'automation_expectation': llm_result.get('automation_expectation') or '中',
                'contract_years': llm_result.get('contract_years') or 3,
                'go_live_date': llm_result.get('go_live_date') or '待确认',
                'extraction_confidence': confidence,
                'missing_data_P0': missing_p0,
            }

            # Fill missing None fields with enhanced regex
            _fill_missing_fields(tender_text, profile)

            # Re-calculate confidence
            filled = sum(
                1 for k, v in profile.items()
                if k not in ('extraction_confidence', 'missing_data_P0', 'project_name', 'client_name', 'go_live_date')
                and v is not None and v != '待确认'
            )
            profile['extraction_confidence'] = min(filled / 10, 1.0)

            print(f'[LLM Extractor] LLM extraction success, confidence={profile["extraction_confidence"]:.0%}')
            return profile, missing_p0, profile['extraction_confidence']

    # Fallback to enhanced regex
    return _extract_with_regex(tender_text)
