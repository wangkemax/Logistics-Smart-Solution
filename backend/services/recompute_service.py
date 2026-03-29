"""
recompute_service.py — Recompute Project State After Manual Input
===================================================================

Responsibility:
  The main orchestrator for the Clarification Workflow闭环.
  Called after user submits manual inputs. It:

  1. Loads original project state (from PipelineRun)
  2. Merges manual_inputs with extracted fields
  3. Runs field resolution
  4. Re-computes readiness
  5. Re-generates clarification_tasks
  6. Re-builds downstream_input
  7. Determines recommended_mode
  8. Writes all results back to PipelineRun
  9. Returns a change summary

Version: v0.6.1
"""

import json
from datetime import datetime
from typing import Optional

from backend.services.field_resolution_service import (
    resolve_all_fields,
    build_resolved_fields_summary,
    ResolvedField,
)
from backend.services.clarification_manager import (
    build_clarification_tasks,
    compute_readiness_after_inputs,
)
from backend.services.input_capture_service import (
    validate_batch,
    save_manual_inputs_to_pipeline,
    get_manual_inputs,
)
from backend.services.tender_schema import get_p0_fields, get_p1_fields
from backend.services.operation_profile_service import derive_operation_profile
from backend.downstream.downstream_input_builder import build_cost_model_input
from backend.models.database import PipelineRun, SessionLocal


def recompute_project_state(
    pipeline_id: str,
    new_manual_inputs: Optional[dict] = None,
) -> dict:
    """
    Main entry point for the Clarification Workflow闭环.

    Steps:
      1. Load original pipeline state
      2. Validate & save new manual inputs (if any)
      3. Load all manual inputs (existing + new)
      4. Resolve all fields
      5. Re-compute readiness
      6. Re-generate clarification task list
      7. Re-build downstream_input
      8. Determine recommended_mode
      9. Write back to DB
      10. Return change summary

    Args:
        pipeline_id:       Pipeline/task ID
        new_manual_inputs: New inputs from frontend {field_key: {value, unit, comment}}

    Returns:
        {
            "project_id": str,
            "resolved_fields_summary": {...},
            "readiness": {...},
            "clarification_tasks": {...},
            "downstream_input": {...},
            "recommended_mode": str,
            "changes_summary": {
                "resolved_p0_count": int,
                "remaining_p0_count": int,
                "mode_changed": bool,
                "old_mode": str,
                "new_mode": str,
                "fields_updated": list[str],
                "fields_still_blocked": list[str],
            }
        }
    """
    db = SessionLocal()
    try:
        # ---- Step 1: Load pipeline record ----
        run = db.query(PipelineRun).filter_by(pipeline_id=pipeline_id).first()
        if not run:
            raise ValueError(f"PipelineRun not found: {pipeline_id}")

        # Parse stored JSON fields
        normalized_fields = _parse_json(run.normalized_fields_json)
        readiness_old = _parse_json(run.readiness_json) or {}
        downstream_input_old = _get_downstream_input_from_run(run)
        clarification_questions = _parse_json(run.clarification_questions_json) or []
        analysis_sections = _parse_json(run.analysis_sections_json) or {}
        old_mode = readiness_old.get("level", "blocked")

        # ---- Step 2: Validate & save new manual inputs ----
        fields_updated = []
        if new_manual_inputs:
            valid_inputs, validation_errors = validate_batch(new_manual_inputs)
            if validation_errors:
                # Return early with validation errors
                return {
                    "success": False,
                    "pipeline_id": pipeline_id,
                    "validation_errors": validation_errors,
                    "message": "部分输入校验失败，请修正后重试",
                }

            if valid_inputs:
                save_manual_inputs_to_pipeline(pipeline_id, valid_inputs, db)
                fields_updated = [inp["field_key"] for inp in valid_inputs]

        # ---- Step 3: Load all manual inputs ----
        manual_inputs = get_manual_inputs(pipeline_id, db)

        # ---- Step 4: Field resolution ----
        # Get field priorities from downstream requirements
        p0_keys = get_p0_fields()
        p1_keys = get_p1_fields()

        # Build field_priorities dict for resolve_all_fields
        field_priorities = {k: "P0" for k in p0_keys}
        field_priorities.update({k: "P1" for k in p1_keys})

        resolved = resolve_all_fields(
            extracted_fields=normalized_fields or {},
            manual_inputs=manual_inputs,
            assumptions=None,  # Assumptions come from downstream_input_builder, handled below
            field_priorities=field_priorities,
        )

        resolved_summary = build_resolved_fields_summary(resolved)

        # ---- Step 5: Re-compute readiness ----
        readiness = compute_readiness_after_inputs(
            resolved_fields=resolved,
            p0_field_keys=p0_keys,
            p1_field_keys=p1_keys,
        )

        # ---- Step 6: Re-generate clarification tasks ----
        # Build a simplified downstream_input for task building
        required_inputs_simple = {}
        for fkey, rf in resolved.items():
            req = downstream_input_old.get("required_inputs", {}).get(fkey, {}) if isinstance(downstream_input_old, dict) else {}
            required_inputs_simple[fkey] = {
                "priority": rf.priority,
                "status": rf.final_status,
                "value": rf.final_value,
                "unit": rf.final_unit,
                "usable": rf.usable,
                "impact": rf.impact or req.get("impact", ""),
                "clarification_question": req.get("clarification_question") if rf.usable else (
                    f"请补充「{rf.field_key}」的具体数据（当前状态：{rf.source_type}）"
                ),
            }

        downstream_for_tasks = {
            "recommended_mode": "blocked",  # will be updated below
            "required_inputs": required_inputs_simple,
        }

        clarification_tasks = build_clarification_tasks(
            pipeline_id=pipeline_id,
            readiness=readiness,
            downstream_input=downstream_for_tasks,
            normalized_fields=normalized_fields or {},
            manual_inputs=manual_inputs,
            clarification_questions=clarification_questions,
        )

        # ---- Step 7 & 8: Re-build downstream_input & determine mode ----
        # Build resolved_as_normalized: resolved fields mapped to downstream format
        resolved_as_normalized = {}
        for fkey, rf in resolved.items():
            resolved_as_normalized[fkey] = {
                "value": rf.final_value,
                "unit": rf.final_unit,
                # Map ResolvedField to downstream format:
                # usable fields → status="provided" (downstream understands this)
                # non-usable fields → status="missing"
                "status": "provided" if rf.usable else "missing",
                "source_basis": rf.source_type,
                "section": "",
            }

        # Build analyzer_result with RESOLVED fields (not originals)
        analyzer_result = {
            "normalized_fields": resolved_as_normalized,
            "readiness": readiness,
            "critical_missing_items": [],
            "important_missing_items": [],
            "clarification_questions": clarification_questions,
            "analysis_sections": analysis_sections,
        }

        downstream_input_new = build_cost_model_input(
            analyzer_result=analyzer_result,
        )
        new_mode = downstream_input_new.get("recommended_mode", "blocked")

        # ---- Step 8b: Derive operation_profile from service_scope (v0.6.5) ----
        service_scope_resolved = None
        if "service_scope" in resolved:
            rf = resolved["service_scope"]
            if rf.usable and rf.final_value:
                service_scope_resolved = rf.final_value

        operation_profile = None
        if service_scope_resolved and isinstance(service_scope_resolved, dict):
            operation_profile = derive_operation_profile(service_scope_resolved)

        # ---- Step 9: Write back to DB ----
        run.manual_inputs_json = json.dumps(manual_inputs, ensure_ascii=False)
        run.resolved_fields_json = json.dumps(
            {k: v.to_dict() for k, v in resolved.items()}, ensure_ascii=False
        )
        run.clarification_tasks_json = json.dumps(
            clarification_tasks.to_dict(), ensure_ascii=False
        )
        run.readiness_json = json.dumps(readiness, ensure_ascii=False)
        run.pipeline_gate_json = json.dumps({
            "cost_model": "PASS" if readiness.get("for_cost_model") else "BLOCK",
            "solution_design": "PASS" if readiness.get("for_solution_design") else "BLOCK",
            "contract_review": "PASS" if readiness.get("for_contract_review") else "BLOCK",
        }, ensure_ascii=False)

        # v0.6.5: Write operation_profile
        if operation_profile is not None:
            run.operation_profile_json = json.dumps(
                operation_profile.model_dump(), ensure_ascii=False
            )

        db.commit()

        # ---- Step 10: Build change summary ----
        remaining_p0 = [
            fk for fk, rf in resolved.items()
            if isinstance(rf, ResolvedField) and not rf.usable and rf.priority == "P0"
        ]

        changes_summary = {
            "resolved_p0_count": resolved_summary["by_priority"].get("P0", {}).get("usable", 0),
            "remaining_p0_count": len(remaining_p0),
            "mode_changed": old_mode != new_mode,
            "old_mode": old_mode,
            "new_mode": new_mode,
            "fields_updated": fields_updated,
            "fields_still_blocked": remaining_p0,
        }

        # Build condensed summaries for frontend explainability panels
        si_raw = downstream_input_new.get("source_inputs", {})
        ai_raw = downstream_input_new.get("assumed_inputs", {})
        uf_raw = downstream_input_new.get("unusable_fields", [])

        source_inputs_summary = {
            k: {
                "value": v.get("value"),
                "status": v.get("status"),
                "priority": v.get("priority"),
                "source_section": v.get("source_section"),
                "impact": v.get("impact"),
            }
            for k, v in si_raw.items()
        }
        assumed_inputs_summary = {
            k: {
                "value": v.get("value"),
                "fallback_value": v.get("fallback_value"),
                "assumption_rule": v.get("assumption_rule"),
                "impact": v.get("impact"),
                "priority": v.get("priority"),
            }
            for k, v in ai_raw.items()
        }

        return {
            "success": True,
            "pipeline_id": pipeline_id,
            "resolved_fields_summary": resolved_summary,
            "readiness": readiness,
            "clarification_tasks": clarification_tasks.to_dict(),
            "downstream_input": {
                "recommended_mode": downstream_input_new.get("recommended_mode"),
                "mode_reason": downstream_input_new.get("mode_reason"),
                "p0_summary": downstream_input_new.get("p0_summary"),
                "p1_summary": downstream_input_new.get("p1_summary"),
                "blocking_reasons": downstream_input_new.get("blocking_reasons", []),
                "source_inputs": source_inputs_summary,
                "assumed_inputs": assumed_inputs_summary,
                "unusable_fields": uf_raw,
                "assumptions_template": downstream_input_new.get("assumptions_template", []),
                # v0.6.5: operation model
                "operation_profile": operation_profile.model_dump() if operation_profile else None,
                "labor_modules": operation_profile.labor_modules.model_dump() if operation_profile else None,
                "operation_narrative": operation_profile.operation_narrative if operation_profile else None,
            },
            "recommended_mode": new_mode,
            "changes_summary": changes_summary,
        }

    finally:
        db.close()


# =============================================================================
# Helpers
# =============================================================================

def _parse_json(json_str: Optional[str]) -> Optional[dict | list]:
    if not json_str:
        return None
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return None


def _get_downstream_input_from_run(run: PipelineRun) -> dict:
    """Reconstruct downstream_input from pipeline run JSON fields."""
    gate_str = run.pipeline_gate_json or "{}"
    readiness_str = run.readiness_json or "{}"

    try:
        gate = json.loads(gate_str) if gate_str else {}
        readiness = json.loads(readiness_str) if readiness_str else {}
    except (json.JSONDecodeError, TypeError):
        gate = {}
        readiness = {}

    # Try to get p0/p1 from normalized fields missing_items
    missing_items = _parse_json(run.missing_items_json) or {}
    p0_missing = missing_items.get("p0", []) if isinstance(missing_items, dict) else []
    p1_missing = missing_items.get("p1", []) if isinstance(missing_items, dict) else []

    return {
        "readiness": readiness,
        "pipeline_gate": gate,
        "p0_summary": {
            "total": len(p0_missing) + sum(1 for _ in p0_missing),
            "missing": len(p0_missing),
        },
    }


# =============================================================================
# Convenience: just get current clarification tasks (no recompute)
# =============================================================================

def get_clarification_tasks(pipeline_id: str) -> dict:
    """
    Load current clarification tasks for a pipeline without recomputing.
    """
    db = SessionLocal()
    try:
        run = db.query(PipelineRun).filter_by(pipeline_id=pipeline_id).first()
        if not run:
            return {"error": f"PipelineRun not found: {pipeline_id}"}

        # v0.6.2: Always rebuild tasks fresh (skip cache during validation phase)
        pass  # removed: was returning cached tasks, now always rebuilds

        # Build from scratch
        normalized_fields = _parse_json(run.normalized_fields_json) or {}
        readiness = _parse_json(run.readiness_json) or {}
        clarification_questions = _parse_json(run.clarification_questions_json) or []
        manual_inputs = get_manual_inputs(pipeline_id, db)
        downstream_input = _get_downstream_input_from_run(run)

        readiness_level = readiness.get("level", "blocked") if isinstance(readiness, dict) else "blocked"

        # Get readiness_score
        readiness_score = readiness.get("readiness_score", 0.0) if isinstance(readiness, dict) else 0.0

        task_list = build_clarification_tasks(
            pipeline_id=pipeline_id,
            readiness={"level": readiness_level, "readiness_score": readiness_score},
            downstream_input=downstream_input,
            normalized_fields=normalized_fields,
            manual_inputs=manual_inputs,
            clarification_questions=clarification_questions,
        )

        return {"success": True, "tasks": task_list.to_dict()}
    finally:
        db.close()
