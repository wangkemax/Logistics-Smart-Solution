"""
solution_api.py — v0.7 Base Solution Generator API
=============================================

POST /api/solution/base/{pipeline_id}  — Generate base solution
GET  /api/solution/base/{pipeline_id}  — Get existing base solution
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.models.database import get_db, PipelineRun
from backend.solution.base_solution_generator import generate_base_solution, serialize_solution

router = APIRouter(prefix="/api/solution", tags=["solution"])


class GenerateRequest(BaseModel):
    """Request to generate or regenerate a base solution."""
    pass  # No body needed; pipeline_id is path param


class SolutionResponse(BaseModel):
    """Response containing a base solution."""
    pipeline_id: str
    solution_id: str
    title: str
    summary: str
    current_cost_mode: str
    generated_at: str
    solution: dict  # Full BaseSolution as dict


# =============================================================================
# POST /api/solution/base/{pipeline_id}
# =============================================================================

@router.post("/base/{pipeline_id}", response_model=SolutionResponse)
def generate_base_solution_endpoint(
    pipeline_id: str,
    _body: GenerateRequest = None,
    db: Session = Depends(get_db),
):
    """
    Generate a base solution for the given pipeline.

    Reads from PipelineRun:
      - operation_profile_json
      - resolved_fields_json
      - downstream_input (reconstructed from gate/readiness)
      - analysis_sections_json
    """
    run = db.query(PipelineRun).filter_by(pipeline_id=pipeline_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Pipeline not found: {pipeline_id}")

    # Load operation_profile
    operation_profile = {}
    if run.operation_profile_json:
        try:
            operation_profile = json.loads(run.operation_profile_json)
        except (json.JSONDecodeError, TypeError):
            pass

    # Load resolved_fields
    resolved_fields = {}
    if run.resolved_fields_json:
        try:
            raw_rf = json.loads(run.resolved_fields_json)
            # Convert dict to lightweight objects with .final_value / .usable
            class _RF:
                def __init__(self, d):
                    self.final_value = d.get("final_value")
                    self.usable = d.get("usable", False)
                    self.final_status = d.get("final_status", "")
                    self.final_unit = d.get("final_unit")
                    self.source_type = d.get("source_type", "")
            resolved_fields = {k: _RF(v) for k, v in raw_rf.items()}
        except (json.JSONDecodeError, TypeError):
            pass

    # Reconstruct downstream_input from available data
    readiness_json = run.readiness_json or "{}"
    gate_json = run.pipeline_gate_json or "{}"
    try:
        readiness = json.loads(readiness_json)
        gate = json.loads(gate_json)
    except (json.JSONDecodeError, TypeError):
        readiness = {}
        gate = {}

    # Determine cost_mode from gate/readiness
    if gate.get("cost_model") == "PASS":
        cost_mode = "full_calc" if readiness.get("for_cost_model") else "range_estimate"
    else:
        cost_mode = "blocked"

    # Build a minimal downstream_input for the solution generator
    downstream_input = {
        "recommended_mode": cost_mode,
        "mode_reason": readiness.get("readiness_reason", ""),
        "p0_summary": readiness.get("p0_summary", {}),
        "p1_summary": readiness.get("p1_summary", {}),
        "source_inputs": {},
        "assumed_inputs": {},
        "blocking_reasons": [],
    }

    # Try to load normalized_fields for source_inputs
    if run.normalized_fields_json:
        try:
            nf = json.loads(run.normalized_fields_json)
            for k, v in nf.items():
                if v.get("status") == "provided":
                    downstream_input["source_inputs"][k] = v
                elif v.get("status") == "inferred":
                    downstream_input["source_inputs"][k] = v
        except (json.JSONDecodeError, TypeError):
            pass

    # Load analysis_sections
    analysis_sections = {}
    if run.analysis_sections_json:
        try:
            analysis_sections = json.loads(run.analysis_sections_json)
        except (json.JSONDecodeError, TypeError):
            pass

    # Extract project_name from analysis_sections s1
    project_name = None
    if isinstance(analysis_sections, dict):
        s1 = analysis_sections.get("s1_project_overview", {})
        if isinstance(s1, dict):
            project_name = s1.get("client_name") or s1.get("project_name")

    # Generate base solution
    solution = generate_base_solution(
        pipeline_id=pipeline_id,
        project_name=project_name,
        analysis_sections=analysis_sections,
        resolved_fields=resolved_fields,
        operation_profile=operation_profile,
        downstream_input=downstream_input,
    )

    # Persist to PipelineRun
    run.base_solution_json = json.dumps(serialize_solution(solution), ensure_ascii=False)
    db.commit()

    return SolutionResponse(
        pipeline_id=pipeline_id,
        solution_id=solution.solution_id,
        title=solution.title,
        summary=solution.summary,
        current_cost_mode=solution.input_cost_mode,
        generated_at=solution.generated_at,
        solution=serialize_solution(solution),
    )


# =============================================================================
# GET /api/solution/base/{pipeline_id}
# =============================================================================

@router.get("/base/{pipeline_id}", response_model=SolutionResponse)
def get_base_solution_endpoint(pipeline_id: str, db: Session = Depends(get_db)):
    """Retrieve an existing base solution (no regeneration)."""
    run = db.query(PipelineRun).filter_by(pipeline_id=pipeline_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Pipeline not found: {pipeline_id}")

    if not run.base_solution_json:
        raise HTTPException(status_code=404, detail="No base solution found for this pipeline")

    try:
        solution_dict = json.loads(run.base_solution_json)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=500, detail="Failed to parse stored solution")

    return SolutionResponse(
        pipeline_id=pipeline_id,
        solution_id=solution_dict.get("solution_id", ""),
        title=solution_dict.get("title", ""),
        summary=solution_dict.get("summary", ""),
        current_cost_mode=solution_dict.get("input_cost_mode", "unknown"),
        generated_at=solution_dict.get("generated_at", ""),
        solution=solution_dict,
    )
