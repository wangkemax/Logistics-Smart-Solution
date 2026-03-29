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


def create_pipeline_run(pipeline_id: str, tender_document: str = "", params_json: dict = None,
                        tender_document_hash: str = None, api_base_url: str = None,
                        compare_scenario_ids: list = None) -> PipelineRun:
    """
    Create or update (upsert) a pipeline run record.
    
    For retry: uses existing pipeline_id, replaces all mutable fields,
    preserves immutable fields (created_at, parent_job_id).
    """
    import hashlib
    init_pipeline_db()
    db = SessionLocal()
    try:
        doc_hash = tender_document_hash
        if doc_hash is None and tender_document:
            doc_hash = hashlib.sha256(tender_document.encode()).hexdigest()[:16]

        existing = db.query(PipelineRun).filter_by(pipeline_id=pipeline_id).first()
        if existing:
            # Upsert: update mutable fields, keep created_at and parent_job_id
            existing.status = "RUNNING"
            existing.tender_document = tender_document or ""
            existing.tender_document_hash = doc_hash
            existing.params_json = json.dumps(params_json or {}, ensure_ascii=False)
            existing.api_base_url = api_base_url
            existing.compare_scenario_ids = (
                json.dumps(compare_scenario_ids or [], ensure_ascii=False)
                if compare_scenario_ids is not None else None
            )
            existing.completed_at = None
            existing.cancelled_at = None
            existing.error = None
            existing.pdf_path = None
            existing.pdf_url = None
            existing.profile_json = "{}"
            existing.recommendations_json = "[]"
            existing.comparisons_json = "[]"
            existing.qa_verdict = ""
            existing.total_duration_seconds = None
            db.commit()
            db.refresh(existing)
            return existing

        run = PipelineRun(
            pipeline_id=pipeline_id,
            status="RUNNING",
            tender_document=tender_document or "",
            tender_document_hash=doc_hash,
            params_json=json.dumps(params_json or {}, ensure_ascii=False),
            api_base_url=api_base_url,
            compare_scenario_ids=json.dumps(compare_scenario_ids or [], ensure_ascii=False) if compare_scenario_ids is not None else None,
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
                      total_duration_seconds: float = None,
                      result_summary: dict = None,
                      # Stage 1: Tender Understanding fields
                      analysis_markdown: str = None,
                      normalized_fields_json: dict = None,
                      missing_items_json: dict = None,
                      clarification_questions_json: list = None,
                      quality_score_json: dict = None,
                      pipeline_gate_json: dict = None):
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
            # Stage 1: Tender Understanding
            if analysis_markdown is not None:
                run.analysis_markdown = analysis_markdown
            if normalized_fields_json is not None:
                run.normalized_fields_json = json.dumps(normalized_fields_json, ensure_ascii=False)
            if missing_items_json is not None:
                run.missing_items_json = json.dumps(missing_items_json, ensure_ascii=False)
            if clarification_questions_json is not None:
                run.clarification_questions_json = json.dumps(clarification_questions_json, ensure_ascii=False)
            if quality_score_json is not None:
                run.quality_score_json = json.dumps(quality_score_json, ensure_ascii=False)
            if pipeline_gate_json is not None:
                run.pipeline_gate_json = json.dumps(pipeline_gate_json, ensure_ascii=False)
            if status in ("COMPLETE", "FAILED"):
                run.completed_at = datetime.utcnow()
            # Build result_summary for task list UI if not provided
            if result_summary is None and profile_json and recommendations_json:
                try:
                    recs = recommendations_json if isinstance(recommendations_json, list) else json.loads(recommendations_json or "[]")
                    prof = profile_json if isinstance(profile_json, dict) else json.loads(profile_json or "{}")
                    comps = comparisons_json if isinstance(comparisons_json, list) else json.loads(comparisons_json or "[]")
                    best = next((c for c in comps if c.get("is_best")), comps[0] if comps else {})
                    conf = prof.get("extraction_confidence") or 0.0
                    result_summary = {
                        "industry": prof.get("industry", "—"),
                        "region": prof.get("region", "—"),
                        "confidence": conf,
                        "verdict": qa_verdict or "",
                        "best_scenario": best.get("scenario_name", "—") if best else "—",
                        "roi_5y": best.get("roi_5y") if best else None,
                        "payback_years": best.get("payback_years") if best else None,
                        "capex_estimate": best.get("capex_estimate") if best else None,
                    }
                except Exception:
                    result_summary = None
            if result_summary is not None:
                run.result_summary = json.dumps(result_summary, ensure_ascii=False)
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

        result = {
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
        # Extract qa_issues from the QA stage's extra for convenience
        for s in stages:
            if s.stage_name == "4_qa_review":
                extra = json.loads(s.extra_json or "{}")
                result["qa_issues"] = extra.get("qa_issues", [])
                break

        # Stage 1: Tender Understanding new fields
        if run.analysis_markdown:
            result["analysis_markdown"] = run.analysis_markdown
        if run.normalized_fields_json:
            result["normalized_fields"] = json.loads(run.normalized_fields_json)
        if run.missing_items_json:
            result["missing_items"] = json.loads(run.missing_items_json)
        if run.clarification_questions_json:
            result["clarification_questions"] = json.loads(run.clarification_questions_json)
        if run.quality_score_json:
            result["quality_score"] = json.loads(run.quality_score_json)
        if run.pipeline_gate_json:
            result["pipeline_gate"] = json.loads(run.pipeline_gate_json)

        return result
    finally:
        db.close()


def list_pipeline_runs(limit: int = 20, offset: int = 0, status: str = None) -> list:
    """List recent pipeline runs with richer task metadata."""
    db = SessionLocal()
    try:
        query = db.query(PipelineRun)
        if status:
            query = query.filter(PipelineRun.status == status)
        runs = query.order_by(PipelineRun.created_at.desc()).offset(offset).limit(limit).all()
        return [
            {
                "pipeline_id": r.pipeline_id,
                "status": r.status,
                "qa_verdict": r.qa_verdict or "",
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "total_duration_seconds": r.total_duration_seconds,
                "error": r.error,
                # Extended fields for task list UI
                "tender_document_hash": r.tender_document_hash,
                "api_base_url": r.api_base_url,
                "compare_scenario_ids": json.loads(r.compare_scenario_ids or "[]") if r.compare_scenario_ids else [],
                "result_summary": json.loads(r.result_summary) if r.result_summary else None,
                "retry_count": r.retry_count,
                "max_retries": r.max_retries,
                "pdf_url": r.pdf_url,
            }
            for r in runs
        ]
    finally:
        db.close()


def reset_pipeline_stages(pipeline_id: str, from_stage: str) -> list[str]:
    """
    Reset all stages from `from_stage` onwards to PENDING.
    Clears output_file, error, duration_seconds for those stages.
    Returns list of stage names that were reset.
    """
    init_pipeline_db()
    db = SessionLocal()
    try:
        stages_order = ["1_extraction", "2_recommendation", "3_cost_comparison", "4_qa_review", "5_pdf_report"]
        try:
            from_idx = stages_order.index(from_stage)
        except ValueError:
            from_idx = 0
        stages_to_reset = stages_order[from_idx:]

        reset_stages = []
        for stage_name in stages_to_reset:
            stage = db.query(PipelineStage).filter_by(
                pipeline_id=pipeline_id, stage_name=stage_name
            ).first()
            if stage:
                stage.status = "PENDING"
                stage.error = None
                stage.duration_seconds = None
                stage.output_file = None
                stage.extra_json = "{}"
                stage.updated_at = datetime.utcnow()
                reset_stages.append(stage_name)

        # Also reset the overall pipeline run status to RUNNING
        run = db.query(PipelineRun).filter_by(pipeline_id=pipeline_id).first()
        if run:
            run.status = "RUNNING"
            run.completed_at = None
            run.error = None

        db.commit()
        return reset_stages
    finally:
        db.close()


def cancel_pipeline_run(pipeline_id: str) -> bool:
    """Cancel a pipeline run if it is still running."""
    init_pipeline_db()
    db = SessionLocal()
    try:
        run = db.query(PipelineRun).filter_by(pipeline_id=pipeline_id).first()
        if run and run.status == "RUNNING":
            run.status = "CANCELLED"
            run.cancelled_at = datetime.utcnow()
            db.commit()
            return True
        return False
    finally:
        db.close()
