"""
Pipeline persistence service — writes pipeline state to SQLite.
Replaces Redis-only storage for durable records.
"""
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.models.database import SessionLocal, PipelineRun, PipelineStage


def init_pipeline_db():
    """Create tables if they don't exist."""
    from backend.models.database import Base, engine
    Base.metadata.create_all(bind=engine)


def create_pipeline_run(pipeline_id: str, tender_document: str = "", params_json: dict = None) -> PipelineRun:
    """Create a new pipeline run record."""
    init_pipeline_db()
    db = SessionLocal()
    try:
        run = PipelineRun(
            pipeline_id=pipeline_id,
            status="RUNNING",
            tender_document=tender_document or "",
            params_json=json.dumps(params_json or {}, ensure_ascii=False),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run
    finally:
        db.close()


def create_stage(pipeline_id: str, stage_name: str) -> PipelineStage:
    """Create or update a stage record."""
    init_pipeline_db()
    db = SessionLocal()
    try:
        # Upsert: update if exists, create if not
        stage = db.query(PipelineStage).filter_by(
            pipeline_id=pipeline_id, stage_name=stage_name
        ).first()
        if stage:
            stage.status = "RUNNING"
            stage.updated_at = datetime.utcnow()
        else:
            stage = PipelineStage(
                pipeline_id=pipeline_id,
                stage_name=stage_name,
                status="RUNNING",
            )
            db.add(stage)
        db.commit()
        db.refresh(stage)
        return stage
    finally:
        db.close()


def update_stage(pipeline_id: str, stage_name: str, status: str,
                 error: str = None, duration_seconds: float = None,
                 output_file: str = None, extra: dict = None):
    """Update stage status and metadata."""
    db = SessionLocal()
    try:
        stage = db.query(PipelineStage).filter_by(
            pipeline_id=pipeline_id, stage_name=stage_name
        ).first()
        if stage:
            stage.status = status
            if error is not None:
                stage.error = error
            if duration_seconds is not None:
                stage.duration_seconds = duration_seconds
            if output_file is not None:
                stage.output_file = output_file
            if extra is not None:
                stage.extra_json = json.dumps(extra, ensure_ascii=False)
            stage.updated_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()


def complete_pipeline(pipeline_id: str, status: str,
                      profile_json: dict = None,
                      recommendations_json: list = None,
                      comparisons_json: list = None,
                      qa_verdict: str = "",
                      pdf_path: str = None,
                      pdf_url: str = None,
                      error: str = None,
                      total_duration_seconds: float = None):
    """Mark pipeline as complete or failed."""
    db = SessionLocal()
    try:
        run = db.query(PipelineRun).filter_by(pipeline_id=pipeline_id).first()
        if run:
            run.status = status
            if profile_json is not None:
                run.profile_json = json.dumps(profile_json, ensure_ascii=False)
            if recommendations_json is not None:
                run.recommendations_json = json.dumps(recommendations_json, ensure_ascii=False)
            if comparisons_json is not None:
                run.comparisons_json = json.dumps(comparisons_json, ensure_ascii=False)
            run.qa_verdict = qa_verdict or ""
            run.pdf_path = pdf_path
            run.pdf_url = pdf_url
            run.error = error
            run.total_duration_seconds = total_duration_seconds
            if status in ("COMPLETE", "FAILED"):
                run.completed_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()


def get_pipeline_run(pipeline_id: str) -> Optional[dict]:
    """Get full pipeline state from SQLite."""
    db = SessionLocal()
    try:
        run = db.query(PipelineRun).filter_by(pipeline_id=pipeline_id).first()
        if not run:
            return None

        stages = db.query(PipelineStage).filter_by(pipeline_id=pipeline_id).order_by(PipelineStage.id).all()

        return {
            "pipeline_id": pipeline_id,
            "status": run.status,
            "profile": json.loads(run.profile_json or "{}"),
            "recommendations": json.loads(run.recommendations_json or "[]"),
            "comparisons": json.loads(run.comparisons_json or "[]"),
            "qa_verdict": run.qa_verdict or "",
            "pdf_path": run.pdf_path,
            "pdf_download_url": run.pdf_url,
            "error": run.error,
            "total_duration_seconds": run.total_duration_seconds,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "stages": [
                {
                    "stage": s.stage_name,
                    "status": s.status,
                    "error": s.error,
                    "duration_seconds": s.duration_seconds,
                    "output_file": s.output_file,
                    "extra": json.loads(s.extra_json or "{}"),
                }
                for s in stages
            ],
        }
    finally:
        db.close()


def list_pipeline_runs(limit: int = 20) -> list:
    """List recent pipeline runs."""
    db = SessionLocal()
    try:
        runs = db.query(PipelineRun).order_by(PipelineRun.created_at.desc()).limit(limit).all()
        return [
            {
                "pipeline_id": r.pipeline_id,
                "status": r.status,
                "qa_verdict": r.qa_verdict or "",
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "total_duration_seconds": r.total_duration_seconds,
                "error": r.error,
            }
            for r in runs
        ]
    finally:
        db.close()
