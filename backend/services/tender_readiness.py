"""
tender_readiness.py — Downstream Readiness Assessment
=================================================

Exposes:
  - compute_readiness(profile) → dict with per-module readiness + score

Version: v0.2
"""
from backend.services.tender_schema import FIELD_REGISTRY, get_p0_fields, get_field_def


def compute_readiness(profile: dict) -> dict:
    """
    Determine downstream readiness based on P0/P1 field status.

    Returns:
        {
            "for_cost_model": bool,
            "for_solution_design": bool,
            "for_contract_review": bool,
            "for_roi_analysis": bool,
            "blocked_reasons": [str],
            "p0_field_status": {field_key: status},
            "readiness_score": float (0.0-1.0),
            "readiness_level": str,   # "ready" | "partial_ready" | "blocked"
        }
    """
    p0_fields = get_p0_fields()

    # Collect P0 field statuses
    p0_status = {}
    for fkey in p0_fields:
        entry = profile.get(fkey)
        if isinstance(entry, dict):
            p0_status[fkey] = entry.get("status", "missing")
        else:
            p0_status[fkey] = "missing"

    # ---- Cost model readiness ----
    # Requires: warehouse_area, dc_count, daily_orders (all non-missing/non-ambiguous)
    cost_blocking_fields = [
        f"{get_field_def(k).display_name if get_field_def(k) else k}（{p0_status[k]}）"
        for k in ["warehouse_area", "dc_count", "daily_orders", "sku_count"]
        if p0_status.get(k) in ("missing", "ambiguous")
    ]
    for_cost_model = len(cost_blocking_fields) == 0

    # ---- Contract review readiness ----
    penalty = profile.get("penalty_rules", {})
    penalty_status = penalty.get("status", "missing") if isinstance(penalty, dict) else "missing"
    for_contract_review = penalty_status in ("explicit", "inferred", "partial")

    # ---- Solution design readiness ----
    # Requires: service_scope OR automation_expectation (partial is ok)
    svc = profile.get("service_scope", {})
    auto = profile.get("automation_expectation", {})
    svc_status = svc.get("status", "missing") if isinstance(svc, dict) else "missing"
    auto_status = auto.get("status", "missing") if isinstance(auto, dict) else "missing"
    # partial_ready: at least one of service_scope or automation_expectation is present
    for_solution_design = svc_status not in ("missing",) or auto_status not in ("missing",)

    # ---- ROI analysis readiness ----
    cy = profile.get("contract_years", {})
    bl = profile.get("budget_level", {})
    cy_status = cy.get("status", "missing") if isinstance(cy, dict) else "missing"
    bl_status = bl.get("status", "missing") if isinstance(bl, dict) else "missing"
    for_roi_analysis = cy_status not in ("missing",) and bl_status not in ("missing",)

    # ---- Summary ----
    blocked_reasons = cost_blocking_fields.copy()
    if not for_contract_review:
        blocked_reasons.append("强制条款/惩罚机制（penalty_rules）缺失")
    if not for_solution_design:
        blocked_reasons.append("服务范围或自动化期望缺失")

    # readiness_score: fraction of P0 fields that are explicit or inferred
    p0_explicit_or_inferred = sum(
        1 for s in p0_status.values() if s in ("explicit", "inferred")
    )
    readiness_score = p0_explicit_or_inferred / max(len(p0_fields), 1)

    if for_cost_model and for_contract_review:
        readiness_level = "ready"
    elif readiness_score >= 0.3:
        readiness_level = "partial_ready"
    else:
        readiness_level = "blocked"

    return {
        "for_cost_model": for_cost_model,
        "for_solution_design": for_solution_design,
        "for_contract_review": for_contract_review,
        "for_roi_analysis": for_roi_analysis,
        "blocked_reasons": blocked_reasons,
        "p0_field_status": p0_status,
        "readiness_score": round(readiness_score, 3),
        "readiness_level": readiness_level,
    }
