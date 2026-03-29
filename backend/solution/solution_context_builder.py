"""
solution_context_builder.py — v0.7 Base Solution Generator
=======================================================

Build a unified solution_context from project state.
This context is the single input for all section builders.

Responsibility:
  Aggregate data from:
    - PipelineRun (project info, analysis_sections)
    - resolved_fields
    - operation_profile (if derived)
    - downstream_input (cost mode, source/assumed inputs)
    - clarification_tasks

No business logic here — only data aggregation.
"""

import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def build_solution_context(
    pipeline_id: str,
    project_name: Optional[str] = None,
    industry: Optional[str] = None,
    region: Optional[str] = None,
    analysis_sections: Optional[dict] = None,
    resolved_fields: Optional[dict] = None,
    operation_profile: Optional[dict] = None,
    downstream_input: Optional[dict] = None,
    clarification_tasks: Optional[dict] = None,
) -> dict:
    """
    Build a unified solution_context dict from all available inputs.

    This is the canonical input for all section builders.
    All keys are guaranteed to exist (empty defaults if not available).
    """
    # ---- Resolve core fields from resolved_fields ----
    resolved = resolved_fields or {}

    def get_resolved(key, default=None):
        rf = resolved.get(key)
        if rf is None:
            return default
        if hasattr(rf, "final_value"):
            return rf.final_value if rf.usable else default
        if isinstance(rf, dict):
            return rf.get("final_value", default) if rf.get("usable") else default
        return default

    # ---- Extract from operation_profile ----
    op = operation_profile or {}
    labor_modules = op.get("labor_modules", {}) or {}
    process_modules = op.get("process_modules", {}) or {}
    service_scope_from_op = get_resolved("service_scope")

    # ---- Extract from downstream_input ----
    di = downstream_input or {}
    cost_mode = di.get("recommended_mode", "unknown")
    mode_reason = di.get("mode_reason", "")
    p0_summary = di.get("p0_summary", {})
    p1_summary = di.get("p1_summary", {})
    source_inputs = di.get("source_inputs", {}) or {}
    assumed_inputs = di.get("assumed_inputs", {}) or {}
    blocking_reasons = di.get("blocking_reasons", [])

    # ---- Build service_scope from resolved or operation_profile ----
    # Prefer the structured dict from operation_profile/service_scope
    effective_service_scope = service_scope_from_op
    if effective_service_scope is None:
        effective_service_scope = {}

    # ---- Count confirmed vs assumed fields ----
    confirmed_fields = {k for k, v in source_inputs.items()}
    assumed_field_keys = set(assumed_inputs.keys())

    # ---- Collect all available info into context ----
    context = {
        # Identification
        "pipeline_id": pipeline_id,
        "project_name": project_name or get_resolved("project_name") or "待定项目",
        "industry": industry or get_resolved("industry") or "未知",
        "region": region or get_resolved("region") or "未知",

        # Operation profile
        "operation_type": op.get("operation_type", "unknown"),
        "complexity_level": op.get("service_complexity_level", "unknown"),
        "complexity_score": op.get("service_complexity_score", 0),
        "operation_narrative": op.get("operation_narrative", ""),

        # Labor & process modules
        "labor_modules": labor_modules if isinstance(labor_modules, dict) else {},
        "process_modules": process_modules if isinstance(process_modules, dict) else {},

        # Service scope
        "service_scope": effective_service_scope if isinstance(effective_service_scope, dict) else {},

        # Cost model status
        "cost_mode": cost_mode,
        "mode_reason": mode_reason,
        "p0_summary": p0_summary,
        "p1_summary": p1_summary,
        "source_inputs": source_inputs,
        "assumed_inputs": assumed_inputs,
        "blocking_reasons": blocking_reasons,

        # Confirmed vs assumed
        "confirmed_field_count": len(confirmed_fields),
        "assumed_field_count": len(assumed_field_keys),
        "total_known_fields": len(confirmed_fields) + len(assumed_field_keys),

        # Analysis sections (raw text for reference)
        "analysis_sections": analysis_sections or {},

        # Clarification tasks
        "clarification_tasks": clarification_tasks or {},

        # Metadata
        "has_operation_profile": bool(op),
        "has_service_scope": bool(effective_service_scope),
        "has_process_modules": bool(process_modules),
    }

    return context
