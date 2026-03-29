"""
base_solution_generator.py — v0.7 Base Solution Generator
==================================================

Main orchestrator for the Base Solution Generator.

Flow:
  1. Build solution_context from inputs
  2. Generate all 8 structured sections
  3. Generate narrative text from structured sections
  4. Assemble into BaseSolution
  5. Return

Single entry point: generate_base_solution(context: dict) -> BaseSolution
"""

import sys
import json
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.solution.solution_schema import BaseSolution
from backend.solution.solution_context_builder import build_solution_context
from backend.solution.solution_section_builders import (
    build_project_fit,
    build_service_design,
    build_organization_design,
    build_process_design,
    build_kpi_framework,
    build_implementation_focus,
    build_risk_and_controls,
    build_cost_model_linkage,
)
from backend.solution.solution_narrative_builder import build_narrative_sections


def generate_base_solution(
    pipeline_id: str,
    project_name: str = None,
    industry: str = None,
    region: str = None,
    analysis_sections: dict = None,
    resolved_fields: dict = None,
    operation_profile: dict = None,
    downstream_input: dict = None,
    clarification_tasks: dict = None,
) -> BaseSolution:
    """
    Main entry point for generating a Base Solution.

    All inputs are optional — the context builder fills in defaults.
    A project with minimal inputs will still return a valid BaseSolution
    (with caveats/notes about missing data).
    """
    # ---- Step 1: Build unified context ----
    context = build_solution_context(
        pipeline_id=pipeline_id,
        project_name=project_name,
        industry=industry,
        region=region,
        analysis_sections=analysis_sections,
        resolved_fields=resolved_fields,
        operation_profile=operation_profile,
        downstream_input=downstream_input,
        clarification_tasks=clarification_tasks,
    )

    # ---- Step 2: Generate all structured sections ----
    project_fit = build_project_fit(context)
    service_design = build_service_design(context)
    organization_design = build_organization_design(context)
    process_design = build_process_design(context)
    kpi_framework = build_kpi_framework(context)
    implementation_focus = build_implementation_focus(context)
    risk_and_controls = build_risk_and_controls(context)  # Note: returns RiskAndControls
    cost_model_linkage = build_cost_model_linkage(context)

    # ---- Step 3: Generate narrative text from structured data ----
    cost_mode = context.get("cost_mode", "unknown")
    narrative_sections = build_narrative_sections(
        project_fit=project_fit,
        service_design=service_design,
        organization_design=organization_design,
        process_design=process_design,
        kpi_framework=kpi_framework,
        implementation_focus=implementation_focus,
        risk_and_controls=risk_and_controls,
        cost_model_linkage=cost_model_linkage,
        cost_mode=cost_mode,
    )

    # ---- Step 4: Assemble into BaseSolution ----
    now = datetime.now(timezone.utc).isoformat()

    # Count assumptions used in solution
    assumptions_in_solution = len(cost_model_linkage.assumptions_used)

    solution = BaseSolution(
        solution_id=f"{pipeline_id}_base_solution_v1",
        solution_type="base_solution",
        project_id=pipeline_id,
        title="基础仓配运营方案",
        summary=narrative_sections.executive_summary[:200],
        generated_at=now,
        project_fit=project_fit,
        service_design=service_design,
        organization_design=organization_design,
        process_design=process_design,
        kpi_framework=kpi_framework,
        implementation_focus=implementation_focus,
        risk_and_controls=risk_and_controls,
        cost_model_linkage=cost_model_linkage,
        narrative_sections=narrative_sections,
        derived_from_fields=[
            "service_scope",
            "operation_profile",
            "labor_modules",
            "process_modules",
            "downstream_input",
            "resolved_fields",
        ],
        derived_from_service_scope=context.get("has_service_scope", False),
        derived_from_operation_profile=context.get("has_operation_profile", False),
        input_cost_mode=cost_mode,
        assumptions_in_solution=assumptions_in_solution,
    )

    return solution


def serialize_solution(solution: BaseSolution) -> dict:
    """Serialize a BaseSolution to a dict (for JSON storage)."""
    return solution.model_dump(mode="json")
