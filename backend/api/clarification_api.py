"""
clarification_api.py — v0.6.1 Clarification Workflow API Endpoints
================================================================

POST /api/clarification/tasks/{pipeline_id}
  → Build and return current clarification task list

GET /api/clarification/tasks/{pipeline_id}
  → Get pre-computed clarification tasks (no recompute)

POST /api/clarification/inputs/{pipeline_id}
  → Save manual inputs (validate + write to DB)

POST /api/clarification/recompute/{pipeline_id}
  → Validate inputs + full recompute pipeline → new state

GET /api/clarification/inputs/{pipeline_id}
  → Get current manual inputs for a pipeline
"""

import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from backend.models.database import get_db
from backend.services.recompute_service import recompute_project_state, get_clarification_tasks
from backend.services.input_capture_service import (
    validate_batch,
    save_manual_inputs_to_pipeline,
    get_manual_inputs,
    MANUAL_INPUT_DEFINITIONS,
)
from backend.services.field_resolution_service import SOURCE_STATUS_LABELS


router = APIRouter(prefix="/api/clarification", tags=["clarification"])


# =============================================================================
# Request/Response models
# =============================================================================

class ManualInputItem(BaseModel):
    value: str | int | float
    unit: Optional[str] = None
    comment: Optional[str] = None


class SubmitManualInputsRequest(BaseModel):
    inputs: dict[str, ManualInputItem]  # {field_key: {value, unit, comment}}


class ValidationError(BaseModel):
    field_key: str
    errors: list[str]


class RecomputeResponse(BaseModel):
    success: bool
    pipeline_id: str
    message: Optional[str] = None
    recommended_mode: Optional[str] = None
    readiness: Optional[dict] = None
    changes_summary: Optional[dict] = None
    validation_errors: Optional[list[ValidationError]] = None
    clarification_tasks: Optional[dict] = None


class InputDefinitionResponse(BaseModel):
    field_key: str
    display_name: str
    input_type: str
    acceptable_units: list[str]
    required_for_p0: bool
    description: str
    unit_conversion_hint: str


# =============================================================================
# GET /api/clarification/definitions
# =============================================================================

@router.get("/definitions", response_model=list[InputDefinitionResponse])
def list_input_definitions():
    """
    List all fields that support manual input, with their types and guidance.
    Used by the frontend to render input forms.
    """
    result = []
    for fkey, defn in MANUAL_INPUT_DEFINITIONS.items():
        result.append(InputDefinitionResponse(
            field_key=fkey,
            display_name=defn.display_name,
            input_type=defn.input_type,
            acceptable_units=defn.acceptable_units,
            required_for_p0=defn.required_for_p0,
            description=defn.description,
            unit_conversion_hint=defn.unit_conversion_hint,
        ))
    return result


# =============================================================================
# GET /api/clarification/tasks/{pipeline_id}
# =============================================================================

@router.get("/tasks/{pipeline_id}")
def get_clarification_tasks_endpoint(pipeline_id: str, db: Session = Depends(get_db)):
    """
    Get current clarification tasks for a pipeline (no recompute).
    Returns pre-computed tasks if available, otherwise builds from scratch.
    """
    result = get_clarification_tasks(pipeline_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# =============================================================================
# POST /api/clarification/tasks/{pipeline_id}
# =============================================================================

@router.post("/tasks/{pipeline_id}")
def build_clarification_tasks_endpoint(pipeline_id: str, db: Session = Depends(get_db)):
    """
    Force-rebuild clarification task list from current pipeline state.
    Use this when you want to refresh tasks without submitting new inputs.
    """
    # Re-run get_clarification_tasks (which always builds fresh)
    result = get_clarification_tasks(pipeline_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# =============================================================================
# GET /api/clarification/inputs/{pipeline_id}
# =============================================================================

@router.get("/inputs/{pipeline_id}")
def get_manual_inputs_endpoint(pipeline_id: str, db: Session = Depends(get_db)):
    """
    Get all currently saved manual inputs for a pipeline.
    Returns {} if no inputs have been saved yet.
    """
    inputs = get_manual_inputs(pipeline_id, db)
    return {
        "pipeline_id": pipeline_id,
        "manual_inputs": inputs,
        "source_labels": SOURCE_STATUS_LABELS,
    }


# =============================================================================
# POST /api/clarification/inputs/{pipeline_id}
# =============================================================================

@router.post("/inputs/{pipeline_id}")
def save_manual_inputs_endpoint(
    pipeline_id: str,
    req: SubmitManualInputsRequest,
    db: Session = Depends(get_db),
):
    """
    Validate and save manual inputs WITHOUT recomputing readiness.
    Use /recompute endpoint if you also want to trigger a full state recalculation.

    Request body:
      {
        "inputs": {
          "daily_orders": {"value": 1200, "unit": "orders/day", "comment": "客户电话澄清"},
          "contract_years": {"value": 3, "comment": "以答疑文件为准"}
        }
      }
    """
    from backend.models.database import PipelineRun

    # Verify pipeline exists
    run = db.query(PipelineRun).filter_by(pipeline_id=pipeline_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Pipeline not found: {pipeline_id}")

    # Convert request to dict format
    raw_inputs = {k: {
        "value": v.value,
        "unit": v.unit,
        "comment": v.comment or "",
    } for k, v in req.inputs.items()}

    # Validate
    valid_inputs, validation_errors = validate_batch(raw_inputs)

    if validation_errors:
        return {
            "success": False,
            "pipeline_id": pipeline_id,
            "validation_errors": validation_errors,
            "message": "部分输入校验失败，请检查错误信息后重试",
        }

    if not valid_inputs:
        return {
            "success": False,
            "pipeline_id": pipeline_id,
            "message": "没有有效的输入内容",
        }

    # Save
    result = save_manual_inputs_to_pipeline(pipeline_id, valid_inputs, db)

    return {
        "success": True,
        "pipeline_id": pipeline_id,
        "saved_count": result["saved_count"],
        "saved_fields": [inp["field_key"] for inp in valid_inputs],
        "message": f"已保存 {result['saved_count']} 个字段的补录内容",
    }


# =============================================================================
# POST /api/clarification/recompute/{pipeline_id}
# =============================================================================

@router.post("/recompute/{pipeline_id}", response_model=RecomputeResponse)
def recompute_endpoint(
    pipeline_id: str,
    req: Optional[SubmitManualInputsRequest] = None,
    db: Session = Depends(get_db)):
    """
    Full Clarification Workflow闭环:
      1. Validate & save new manual inputs (if provided)
      2. Merge with existing manual inputs
      3. Resolve all fields (extracted + manual + assumed)
      4. Re-compute readiness
      5. Re-generate clarification tasks
      6. Re-build downstream_input
      7. Determine recommended_mode
      8. Write back to DB
      9. Return change summary

    This is the main action endpoint for the Clarification Workspace.

    If req.inputs is empty/null, just recomputes from existing saved manual inputs.
    """
    # Verify pipeline exists
    from backend.models.database import PipelineRun
    run = db.query(PipelineRun).filter_by(pipeline_id=pipeline_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Pipeline not found: {pipeline_id}")

    # Convert optional inputs
    new_inputs = None
    if req and req.inputs:
        new_inputs = {k: {
            "value": v.value,
            "unit": v.unit,
            "comment": v.comment or "",
        } for k, v in req.inputs.items()}

    # Run recompute
    result = recompute_project_state(pipeline_id, new_inputs)

    # Format validation errors if any
    validation_errors_formatted = None
    if not result.get("success", True) and result.get("validation_errors"):
        validation_errors_formatted = [
            ValidationError(field_key=ve["field_key"], errors=ve["errors"])
            for ve in result["validation_errors"]
        ]

    return RecomputeResponse(
        success=result.get("success", False),
        pipeline_id=pipeline_id,
        message=result.get("message"),
        recommended_mode=result.get("recommended_mode"),
        readiness=result.get("readiness"),
        changes_summary=result.get("changes_summary"),
        validation_errors=validation_errors_formatted,
        clarification_tasks=result.get("clarification_tasks"),
    )


# =============================================================================
# GET /api/clarification/status/{pipeline_id}
# =============================================================================

@router.get("/status/{pipeline_id}")
def get_clarification_status(pipeline_id: str, db: Session = Depends(get_db)):
    """
    Quick status check for a pipeline's clarification progress.
    Returns mode, readiness, and key counts — no recompute.
    """
    from backend.models.database import PipelineRun
    import json

    run = db.query(PipelineRun).filter_by(pipeline_id=pipeline_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Pipeline not found: {pipeline_id}")

    readiness = {}
    if run.readiness_json:
        try:
            readiness = json.loads(run.readiness_json)
        except (json.JSONDecodeError, TypeError):
            pass

    manual_inputs = {}
    if run.manual_inputs_json:
        try:
            manual_inputs = json.loads(run.manual_inputs_json)
        except (json.JSONDecodeError, TypeError):
            pass

    gate = {}
    if run.pipeline_gate_json:
        try:
            gate = json.loads(run.pipeline_gate_json)
        except (json.JSONDecodeError, TypeError):
            pass

    readiness_level = readiness.get("level", "unknown") if isinstance(readiness, dict) else "unknown"

    return {
        "pipeline_id": pipeline_id,
        "status": run.status,
        "current_mode": readiness_level,
        "readiness_score": readiness.get("readiness_score", 0.0) if isinstance(readiness, dict) else 0.0,
        "cost_model_gate": gate.get("cost_model", "UNKNOWN"),
        "manual_inputs_count": len(manual_inputs),
        "manual_inputs": list(manual_inputs.keys()),
    }
