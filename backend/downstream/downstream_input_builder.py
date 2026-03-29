"""
downstream/downstream_input_builder.py — Build Downstream Input Packages
====================================================================

Responsibilities (per Max v0.2 plan):
  1. Field mapping — normalize_extracted → cost_model field names
  2. Usability determination — provided / ambiguous / missing / inferred → usable
  3. Conflict detection — wrap cross-field conflicts with candidate_values + sources
  4. Clarification question generation — from missing/ambiguous P0 and P1 fields
  5. Assumption templates — for P1 fields where range_estimate is allowed

Produces the canonical `downstream_input.cost_model` object consumed by the
Cost Model Agent. This is the ONLY entry point for downstream agents.

Version: v0.2
"""
import json
from typing import Optional
from backend.services.tender_schema import FIELD_REGISTRY
from backend.services.tender_readiness import compute_readiness
from backend.downstream.cost_model_requirements import (
    COST_MODEL_REQUIREMENTS,
    FIELD_REQUIREMENTS,
    P0_FIELDS,
    P1_FIELDS,
    ASSUMPTION_TEMPLATES,
    CostFieldRequirement,
)


# =============================================================================
# Main builder
# =============================================================================

def build_cost_model_input(
    analyzer_result: dict,
    normalized_fields: dict = None,
) -> dict:
    """
    Build the cost_model downstream input from an analyzer result.

    This is the canonical entry point for the Cost Model Agent.
    No downstream agent should read from raw profile fields — only from
    the object returned by this function.

    Args:
        analyzer_result: Full output from analyze_and_extract().
                         Contains: normalized_fields, readiness, critical_missing_items,
                         important_missing_items, clarification_questions, analysis_sections.
        normalized_fields: Optional explicit normalized_fields dict.
                          If None, reads from analyzer_result["normalized_fields"].

    Returns:
        {
            "readiness": {
                "level": "ready" | "partial_ready" | "blocked",
                "reason": str,
                "cost_model_ready": bool,
            },
            "required_inputs": {
                <field_key>: {
                    "value": Any,
                    "status": "provided" | "ambiguous" | "missing" | "inferred",
                    "priority": "P0" | "P1" | "P2",
                    "source_basis": str,
                    "source_section": str,
                    "usable": bool,
                    "usable_reason": str,
                    "assumption_allowed": bool,
                    "assumption_rule": str | None,
                    "fallback_value": Any | None,
                    "fallback_assumption": str | None,
                    "clarification_needed": bool,
                    "clarification_question": str | None,
                    "impact": str,          # impact_on_cost description
                    "unit": str,
                }
            },
            "recommended_mode": "full_calc" | "range_estimate" | "blocked",
            "mode_reason": str,
            "p0_summary": {
                "total": int,
                "provided": int,
                "missing": int,
                "ambiguous": int,
                "inferred": int,
            },
            "p1_summary": {
                "total": int,
                "provided": int,
                "missing": int,
                "ambiguous": int,
            },
            "source_inputs": dict,    # fields with status "provided" or "inferred"
            "assumed_inputs": dict,   # P1 fields with fallback values applied
            "unusable_fields": list,  # fields that cannot be used in any calculation
            "clarification_questions": list[dict],
            "assumptions_template": list[dict],   # acceptable assumption list for range_estimate
            "blocking_reasons": list[str],
        }
    """
    nf = normalized_fields or analyzer_result.get("normalized_fields", {})
    readiness_result = analyzer_result.get("readiness") or {}
    critical_missing = analyzer_result.get("critical_missing_items", [])
    important_missing = analyzer_result.get("important_missing_items", [])
    clar_questions = analyzer_result.get("clarification_questions", [])
    analysis_sections = analyzer_result.get("analysis_sections", {})

    # ---- Build required_inputs for each cost model field ----
    required_inputs = {}
    source_inputs = {}     # provided / explicitly inferred fields
    assumed_inputs = {}     # P1 fields where we apply fallback
    unusable_fields = []    # fields with ambiguous or missing P0 status

    clar_question_map = {q.get("field_key"): q for q in clar_questions}

    blocking_reasons = []

    for req in COST_MODEL_REQUIREMENTS:
        fkey = req.field_key
        entry = nf.get(fkey, {})
        status_raw = _get_status(entry, req)
        usable, usable_reason = _determine_usable(status_raw, req)
        clar_q = clar_question_map.get(fkey)
        fallback_val, fallback_rule = _get_fallback(status_raw, req, entry)

        req_input = {
            "value": entry.get("value") if status_raw != "missing" else None,
            "status": status_raw,
            "priority": req.priority,
            "source_basis": entry.get("source_basis", "未提供来源依据") if isinstance(entry, dict) else "",
            "source_section": entry.get("section", "") if isinstance(entry, dict) else "",
            "usable": usable,
            "usable_reason": usable_reason,
            "assumption_allowed": req.assumption_allowed,
            "assumption_rule": req.assumption_rule if req.assumption_allowed else None,
            "fallback_value": fallback_val,
            "fallback_assumption": fallback_rule,
            "clarification_needed": (status_raw in ("missing", "ambiguous") and
                                     req.priority in ("P0", "P1")),
            "clarification_question": clar_q.get("question") if clar_q else (
                req.clarification_template if status_raw in ("missing", "ambiguous") else None
            ),
            "impact": req.impact_on_cost,
            "unit": req.unit,
        }

        required_inputs[fkey] = req_input

        # Categorize
        if status_raw in ("provided", "inferred"):
            source_inputs[fkey] = req_input
        elif req.assumption_allowed and fallback_val is not None:
            assumed_inputs[fkey] = req_input
        elif not usable and req.priority == "P0":
            unusable_fields.append(fkey)

    # ---- Compute P0/P1 summaries ----
    p0_summary = _summarize(P0_FIELDS, required_inputs)
    p1_summary = _summarize(P1_FIELDS, required_inputs)

    # ---- Blocking reasons ----
    for fkey in unusable_fields:
        req = FIELD_REQUIREMENTS.get(fkey)
        if req:
            blocking_reasons.append(
                f"P0字段「{req.display_name}」状态为{required_inputs[fkey]['status']}，禁止进入正式成本测算"
            )

    # ---- Readiness level ----
    if unusable_fields:
        readiness_level = "blocked"
        readiness_reason = f"{len(unusable_fields)}个P0关键字段不可用，禁止正式成本测算"
        recommended_mode = "blocked"
        mode_reason = "存在P0字段缺失或歧义，必须先澄清"
    elif p1_summary["missing"] > 0 or p1_summary["ambiguous"] > 0:
        readiness_level = "partial_ready"
        readiness_reason = "P0字段完整，可进行区间估算；P1字段存在缺失，建议澄清"
        recommended_mode = "range_estimate"
        mode_reason = "P0字段完整但P1字段有缺失，仅允许区间估算"
    else:
        readiness_level = "ready"
        readiness_reason = "所有P0字段已提供，可进行正式成本测算"
        recommended_mode = "full_calc"
        mode_reason = "关键字段完整，可进入正式成本测算"

    # ---- Clarification questions ----
    blocking_clar = [
        {
            "field_key": fkey,
            "display_name": required_inputs[fkey]["priority"].replace("P0","P0阻塞").replace("P1","P1重要"),
            "question": required_inputs[fkey]["clarification_question"],
            "priority": required_inputs[fkey]["priority"],
            "impact": required_inputs[fkey]["impact"],
            "suggested_answer_format": clar_q.get("suggested_answer_format", "")
            if (clar_q := clar_question_map.get(fkey)) else "",
        }
        for fkey in unusable_fields
        if required_inputs[fkey].get("clarification_question")
    ]

    # ---- Assumptions template (for range_estimate mode) ----
    assumptions_template = []
    for fkey in P1_FIELDS:
        req = FIELD_REQUIREMENTS.get(fkey)
        inp = required_inputs.get(fkey, {})
        if req and req.assumption_allowed and inp.get("clarification_needed"):
            assumptions_template.append({
                "field_key": fkey,
                "display_name": req.display_name,
                "fallback_value": inp.get("fallback_value"),
                "fallback_assumption": inp.get("fallback_assumption"),
                "fallback_rule": req.assumption_rule,
                "unit": req.unit,
                "impact": req.impact_on_cost,
                "question": inp.get("clarification_question"),
            })

    return {
        "readiness": {
            "level": readiness_level,
            "reason": readiness_reason,
            "cost_model_ready": readiness_level == "ready",
            "solution_design_ready": readiness_result.get("for_solution_design", False),
            "contract_review_ready": readiness_result.get("for_contract_review", False),
        },
        "required_inputs": required_inputs,
        "recommended_mode": recommended_mode,
        "mode_reason": mode_reason,
        "p0_summary": p0_summary,
        "p1_summary": p1_summary,
        "source_inputs": source_inputs,
        "assumed_inputs": assumed_inputs,
        "unusable_fields": unusable_fields,
        "clarification_questions": blocking_clar,
        "assumptions_template": assumptions_template,
        "blocking_reasons": blocking_reasons,
    }


# =============================================================================
# Helpers
# =============================================================================

def _get_status(entry, req: CostFieldRequirement) -> str:
    """
    Map normalized field status to downstream usability status.

    Normalized status: explicit | inferred | partial | missing | ambiguous
    Downstream status:  provided | inferred | missing | ambiguous
    """
    if not isinstance(entry, dict):
        return "missing"
    status = entry.get("status", "missing")

    # Map explicit → provided (explicit is the gold standard)
    if status == "explicit":
        return "provided"
    return status


def _determine_usable(status: str, req: CostFieldRequirement) -> tuple[bool, str]:
    """Determine if a field is usable for cost calculation."""
    if status == "provided":
        return True, "字段值明确来自招标文件，可直接使用"
    elif status == "inferred":
        if req.priority == "P0":
            return False, f"P0字段推断值不得用于正式测算，必须从原文明确获取"
        return True, "推断值可用于估算，但须标注推断来源"
    elif status == "partial":
        if req.priority == "P0":
            return False, f"P0字段仅部分提供，禁止用于正式测算"
        return True, "部分数据可用，但精度有限"
    elif status == "ambiguous":
        return False, f"字段存在歧义（{req.impact_on_cost}），禁止用于任何精确计算"
    elif status == "missing":
        if req.assumption_allowed:
            return True, f"字段缺失但允许假设，可进行区间估算：{req.assumption_rule}"
        return False, f"P0关键字段缺失且不允许假设，必须先澄清"
    return False, f"未知状态: {status}"


def _get_fallback(status: str, req: CostFieldRequirement, entry: dict) -> tuple:
    """
    Get fallback value and assumption text for a field.
    Returns (fallback_value, fallback_assumption_text) or (None, None).
    """
    if status in ("provided", "inferred"):
        return None, None

    if not req.assumption_allowed:
        return None, None

    # P1 fields get fallback from ASSUMPTION_TEMPLATES
    if req.field_key in ASSUMPTION_TEMPLATES:
        assumption_text = ASSUMPTION_TEMPLATES[req.field_key]
        # For sku_count and inventory, try to derive from available fields
        val = entry.get("value") if isinstance(entry, dict) else None
        if val is None:
            val = _derive_fallback_value(req.field_key, entry)
        return val, assumption_text

    return None, None


def _derive_fallback_value(field_key: str, entry: dict) -> Optional:
    """
    Attempt to derive a fallback value from related fields in the entry.

    For example, if inventory is missing but daily_orders is available,
    derive inventory ≈ daily_orders * 8 (8 days average).
    """
    # These are simple heuristics — the Cost Model Agent should still
    # explicitly label these as assumed inputs
    return None


def _summarize(field_keys: list, required_inputs: dict) -> dict:
    """Compute P0 or P1 field status summary."""
    total = len(field_keys)
    provided = sum(1 for k in field_keys
                  if required_inputs.get(k, {}).get("status") == "provided")
    missing = sum(1 for k in field_keys
                  if required_inputs.get(k, {}).get("status") == "missing")
    ambiguous = sum(1 for k in field_keys
                    if required_inputs.get(k, {}).get("status") == "ambiguous")
    inferred = sum(1 for k in field_keys
                    if required_inputs.get(k, {}).get("status") == "inferred")
    return {
        "total": total,
        "provided": provided,
        "missing": missing,
        "ambiguous": ambiguous,
        "inferred": inferred,
        "usable": provided + inferred,
    }


# =============================================================================
# Convenience: build all downstream inputs (cost_model, solution_design, contract)
# =============================================================================

def build_all_downstream_inputs(analyzer_result: dict) -> dict:
    """
    Build all downstream input packages from a single analyzer result.

    Currently returns: cost_model
    Future: solution_design, contract_review, tender_writer
    """
    cost_model = build_cost_model_input(analyzer_result)
    return {
        "cost_model": cost_model,
        "meta": {
            "analysis_version": analyzer_result.get("meta", {}).get("analysis_version", "v0.2"),
            "prompt_version": analyzer_result.get("meta", {}).get("prompt_version", "unknown"),
            "generated_at": analyzer_result.get("meta", {}).get("generated_at", ""),
        }
    }
