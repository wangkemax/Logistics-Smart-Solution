"""
Task API — persistent task tracking for pipeline runs.
Provides task list, task detail, and task cancellation endpoints.
"""

import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.services.pipeline_service import (
    list_pipeline_runs,
    get_pipeline_run,
)
from backend.models.database import SessionLocal, PipelineRun

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TaskListItem(BaseModel):
    """Summary of a single task for list display."""
    task_id: str
    created_at: Optional[str]
    status: str
    industry: Optional[str]
    region: Optional[str]
    confidence: Optional[float]
    verdict: Optional[str]
    best_scenario: Optional[str]
    roi_5y: Optional[float]
    payback_years: Optional[float]
    capex_estimate: Optional[float]
    error: Optional[str]
    total_duration_seconds: Optional[float]
    completed_at: Optional[str]
    pdf_url: Optional[str]

    class Config:
        from_attributes = True


class TaskDetail(BaseModel):
    """Full task record including all metadata."""
    task_id: str
    status: str
    created_at: Optional[str]
    completed_at: Optional[str]
    total_duration_seconds: Optional[float]
    error: Optional[str]
    industry: Optional[str]
    region: Optional[str]
    confidence: Optional[float]
    verdict: Optional[str]
    best_scenario: Optional[str]
    roi_5y: Optional[float]
    payback_years: Optional[float]
    capex_estimate: Optional[float]
    api_base_url: Optional[str]
    compare_scenario_ids: list
    pdf_url: Optional[str]
    retry_count: int
    max_retries: int
    stages: list

    class Config:
        from_attributes = True


@router.get("", response_model=list[TaskListItem])
def list_tasks(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = Query(default=None, description="Filter by status: RUNNING, COMPLETE, FAILED, CANCELLED"),
):
    """
    List recent pipeline tasks with pagination.

    Returns task summaries including pipeline_id, created_at, status,
    profile summary (industry, region), confidence, and verdict.
    """
    runs = list_pipeline_runs(limit=limit, offset=offset, status=status)
    tasks = []
    for r in runs:
        summary = r.get("result_summary") or {}
        tasks.append(TaskListItem(
            task_id=r["pipeline_id"],
            created_at=r["created_at"],
            status=r["status"],
            industry=summary.get("industry"),
            region=summary.get("region"),
            confidence=summary.get("confidence"),
            verdict=summary.get("verdict"),
            best_scenario=summary.get("best_scenario"),
            roi_5y=summary.get("roi_5y"),
            payback_years=summary.get("payback_years"),
            capex_estimate=summary.get("capex_estimate"),
            error=r.get("error"),
            total_duration_seconds=r.get("total_duration_seconds"),
            completed_at=r.get("completed_at"),
            pdf_url=r.get("pdf_url"),
        ))
    return tasks


@router.get("/{task_id}", response_model=TaskDetail)
def get_task(task_id: str):
    """
    Get full task record by task_id (pipeline_id).
    Returns status, profile summary, stages, and result data.
    """
    run = get_pipeline_run(task_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    summary = run.get("profile", {}) if isinstance(run.get("profile"), dict) else {}
    result_summary = {}

    # Try parsing result_summary JSON stored in the run
    db = SessionLocal()
    try:
        db_run = db.query(PipelineRun).filter_by(pipeline_id=task_id).first()
        if db_run and db_run.result_summary:
            import json as _json
            result_summary = _json.loads(db_run.result_summary) or {}
    finally:
        db.close()

    return TaskDetail(
        task_id=task_id,
        status=run.get("status", "UNKNOWN"),
        created_at=run.get("created_at"),
        completed_at=run.get("completed_at"),
        total_duration_seconds=run.get("total_duration_seconds"),
        error=run.get("error"),
        industry=result_summary.get("industry") or summary.get("industry"),
        region=result_summary.get("region") or summary.get("region"),
        confidence=result_summary.get("confidence") or summary.get("extraction_confidence"),
        verdict=result_summary.get("verdict") or run.get("qa_verdict"),
        best_scenario=result_summary.get("best_scenario"),
        roi_5y=result_summary.get("roi_5y"),
        payback_years=result_summary.get("payback_years"),
        capex_estimate=result_summary.get("capex_estimate"),
        api_base_url=run.get("api_base_url"),
        compare_scenario_ids=run.get("compare_scenario_ids") or [],
        pdf_url=run.get("pdf_download_url") or run.get("pdf_url"),
        retry_count=0,
        max_retries=2,
        stages=run.get("stages", []),
    )


@router.delete("/{task_id}")
def delete_task(task_id: str):
    """
    Cancel and delete a task (pipeline run).
    Sets status to CANCELLED rather than hard-deleting to preserve audit trail.
    """
    from datetime import datetime as _dt

    db = SessionLocal()
    try:
        run = db.query(PipelineRun).filter_by(pipeline_id=task_id).first()
        if not run:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        if run.status in ("COMPLETE", "CANCELLED"):
            # Already terminal — return current state without modification
            return {
                "task_id": task_id,
                "status": run.status,
                "message": f"Task is already {run.status}, no action taken",
            }

        run.status = "CANCELLED"
        run.cancelled_at = _dt.utcnow()
        db.commit()

        return {
            "task_id": task_id,
            "status": "CANCELLED",
            "cancelled_at": run.cancelled_at.isoformat(),
            "message": "Task cancelled successfully",
        }
    finally:
        db.close()
