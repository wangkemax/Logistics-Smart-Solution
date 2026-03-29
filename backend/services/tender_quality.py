"""
tender_quality.py — Quality Scoring Logic
=========================================

Exposes:
  - compute_analysis_quality_score(profile) → completeness / evidence / readiness
  - _evidence_score(quality) → float 0-1
  - _validate_structured_json(structured) → list[errors]

Version: v0.2
"""
import re
from backend.services.tender_schema import (
    FIELD_REGISTRY, FIELD_STATUS, SECTION_NAMES, SCHEMA_CONTRACT,
    FIELD_MAP, CONSISTENCY_RULES, get_p0_fields,
)


# =============================================================================
# Schema validation — check LLM output against schema contract
# =============================================================================
def validate_structured_json(structured: dict) -> list[dict]:
    """
    Validate LLM output against schema contract before normalization.
    Returns list of validation errors (empty = valid).
    Each error: {section, expected, actual, severity, message}
    """
    errors = []
    if not isinstance(structured, dict):
        return [{"section": "root", "expected": "dict", "actual": type(structured).__name__,
                 "severity": "ERROR", "message": "LLM output is not a JSON object"}]

    for s_key, contract in SCHEMA_CONTRACT.items():
        value = structured.get(s_key)
        expected_type = contract["type"]

        if value is None:
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
                "message": f"{s_key} should be {expected_type.__name__}"
            })
            continue

        if expected_type == list:
            item_type = contract.get("item_type")
            if item_type == dict:
                for i, item in enumerate(value):
                    if not isinstance(item, dict):
                        errors.append({
                            "section": s_key, "expected": f"list[dict], item[{i}]",
                            "actual": type(item).__name__, "severity": "ERROR",
                            "message": f"{s_key}[{i}] should be dict"
                        })

        required_keys = contract.get("required_keys", [])
        for rk in required_keys:
            if not isinstance(value, dict) or rk not in value:
                errors.append({
                    "section": s_key, "expected": f"key '{rk}' present",
                    "actual": "missing", "severity": "WARN",
                    "message": f"{s_key} missing required key '{rk}'"
                })

    expected_keys = set(SCHEMA_CONTRACT.keys())
    actual_keys = set(structured.keys())
    for k in actual_keys - expected_keys:
        errors.append({
            "section": k, "expected": "not in schema",
            "actual": "present", "severity": "INFO",
            "message": f"Unexpected key '{k}' in LLM output (ignored)"
        })

    return errors


# Alias for backward compat
_validate_structured_json = validate_structured_json


# =============================================================================
# Quality score computation
# =============================================================================

def compute_analysis_quality_score(profile: dict) -> dict:
    """
    Compute three-dimensional quality scores for a tender analysis.

    Returns:
        {
          "completeness": {
            "p0_coverage": float,    # fraction of P0 fields with non-null values
            "p1_coverage": float,    # fraction of P1 fields with non-null values
            "total_score": float,    # (p0 + p1) / 2
          },
          "evidence": {
            "explicit": float,       # fraction of fields marked explicit
            "inferred": float,       # fraction marked inferred
            "partial": float,        # fraction marked partial
            "missing": float,        # fraction marked missing
            "ambiguous": float,      # fraction marked ambiguous
          },
          "readiness": {
            "cost_model_ready": bool,
            "solution_design_ready": bool,
            "contract_review_ready": bool,
            "blocking_items": [str],
            "summary": str,
          },
        }
    """
    traces = profile.get("_field_traces", {})
    if not traces:
        traces = {
            k: v for k, v in profile.items()
            if isinstance(v, dict) and "status" in v and "value" in v and not k.startswith("_")
        }

    def has_val(name):
        e = traces.get(name, {})
        return isinstance(e, dict) and e.get("value") is not None

    p0_fields = get_p0_fields()
    p1_fields = [k for k, f in FIELD_REGISTRY.items() if f.priority == "P1"]

    p0_cov = sum(1 for f in p0_fields if has_val(f)) / max(len(p0_fields), 1)
    p1_cov = sum(1 for f in p1_fields if has_val(f)) / max(len(p1_fields), 1)

    all_traced = [v for v in traces.values() if isinstance(v, dict) and "status" in v]
    n = max(len(all_traced), 1)
    counts = {"explicit": 0, "inferred": 0, "partial": 0, "missing": 0, "ambiguous": 0}
    for v in all_traced:
        st = v.get("status", "missing")
        if st in counts:
            counts[st] += 1

    # Readiness
    cost_ok = all(has_val(f) for f in ["warehouse_area", "dc_count", "daily_orders"])
    sol_ok = cost_ok and has_val("service_scope")
    ctr_ok = has_val("penalty_rules")
    m0 = profile.get("missing_p0", [])

    parts = []
    if not cost_ok:
        parts.append("成本测算阻塞(" + str(sum(1 for f in p0_fields if not has_val(f))) + "项)")
    if not sol_ok:
        parts.append("方案设计部分可行(" + str(sum(1 for f in p1_fields if not has_val(f))) + "项待澄清)")
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
        "evidence": {k: round(v / n, 3) for k, v in counts.items()},
        "readiness": {
            "cost_model_ready": cost_ok,
            "solution_design_ready": sol_ok,
            "contract_review_ready": ctr_ok,
            "blocking_items": m0,
            "summary": summary,
        },
    }


def _evidence_score(quality: dict) -> float:
    """
    Compute a 0-1 evidence score from quality dict.
    High score = most fields are explicit (not inferred/missing/ambiguous).
    """
    evidence = quality.get("evidence", {})
    total = sum(evidence.values()) if evidence else 1.0
    return evidence.get("explicit", 0) / total if total else 0.0
