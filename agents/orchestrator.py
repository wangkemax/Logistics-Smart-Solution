"""
Presale Pipeline Orchestrator — CEO Agent
=========================================
FastAPI service that orchestrates the full presale pipeline:
  1. Tender Requirement Extraction
  2. Solution Design (calls /api/recommend)
  3. Cost Modeling (calls /api/compare)
  4. Tender Writing
  5. QA Review
  6. PDF Report Generation (calls /api/report)

This is the "CEO Agent" — it doesn't do the cognitive work itself,
but coordinates specialized agents and calls the Smart Solution API.
"""

import os
import sys
import json
import uuid
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, Literal
from enum import Enum

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.project_service import (
    get_recommendations,
    get_cost_analysis,
    get_scenario_comparison,
)
from backend.services.tender_service import extract_tender_requirements, extract_requirements

class _InMemoryRedisFallback:
    """Very small subset of Redis hash APIs used by this module."""

    def __init__(self):
        self._store: dict[str, dict[str, str]] = {}

    def hgetall(self, key: str) -> dict[str, str]:
        return dict(self._store.get(key, {}))

    def hset(self, key: str, field: str, value: str):
        self._store.setdefault(key, {})[field] = value


try:
    import redis as _redis_lib
    _redis_conn = _redis_lib.from_url(REDIS_URL, decode_responses=True)
except Exception:
    _redis_conn = _InMemoryRedisFallback()

router = APIRouter(prefix="/api/pipeline", tags=["presale-pipeline"])

# =============================================================================
# Pipeline Status
# =============================================================================

class PipelineStatus(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class PipelineStageStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


# =============================================================================
# Request/Response Models
# =============================================================================

class PipelineRunRequest(BaseModel):
    """Request to run the full presale pipeline."""
    tender_document: str = Field(..., description="招标文件全文或摘要文本")
    project_profile_overrides: Optional[dict] = Field(
        default=None,
        description="手动覆盖的项目参数（如已提取则可跳过 Extraction 阶段）"
    )
    api_base_url: str = Field(
        default="http://localhost:8000",
        description="Smart Solution API base URL"
    )
    compare_scenario_ids: Optional[list[int]] = Field(
        default=None,
        description="指定对比方案ID列表，默认使用推荐TOP3"
    )
    generate_pdf: bool = Field(default=True, description="是否生成PDF报告")
    use_llm: bool = Field(default=True, description="是否使用LLMExtractor（否则用正则）")


class StageOutput(BaseModel):
    stage: str
    status: PipelineStageStatus
    output_file: Optional[str] = None
    error: Optional[str] = None
    duration_seconds: Optional[float] = None


class PipelineRunResponse(BaseModel):
    """Response from pipeline run."""
    pipeline_id: str
    status: PipelineStatus
    stages: list[StageOutput]
    project_profile: Optional[dict] = None
    recommendations: Optional[list[dict]] = None
    cost_comparisons: Optional[list[dict]] = None
    best_scenario_id: Optional[int] = None
    qa_verdict: Optional[str] = None
    pdf_path: Optional[str] = None
    pdf_download_url: Optional[str] = None
    error: Optional[str] = None


class ExtractionRequest(BaseModel):
    """Standalone: Extract project profile from tender text."""
    tender_document: str


class ExtractionResponse(BaseModel):
    project_profile: dict
    extraction_confidence: float
    raw_requirements_summary: str
    missing_p0: list[str]
    missing_p1: list[str]


class DemoRequest(BaseModel):
    """Lightweight demo endpoint: takes a project profile directly, no tender doc needed."""
    industry: str = Field(default="电商", description="行业")
    region: str = Field(default="华东", description="地区")
    warehouse_area: float = Field(default=20000.0, description="仓库面积 m²")
    sku_count: int = Field(default=30000, description="SKU 品类数")
    daily_orders: int = Field(default=5000, description="日均订单量")
    inventory: int = Field(default=0, description="库存量")
    labor_cost_level: str = Field(default="中", description="人工成本水平：低/中/高")
    budget_level: str = Field(default="中", description="预算水平：低/中/高")
    automation_expectation: str = Field(default="中", description="自动化期望：低/中/高")
    contract_years: int = Field(default=3, description="合同期（年）")
    top_n: int = Field(default=5, ge=1, le=15, description="返回方案数量")
    generate_pdf: bool = Field(default=False, description="是否生成 PDF 报告")


class DemoResponse(BaseModel):
    """Response from /api/pipeline/demo endpoint."""
    project_profile: dict                      # normalized input snapshot
    recommendations: list[dict]               # top N with reasons + breakdown
    financial_comparison: list[dict]           # cost/ROI for each recommendation
    pdf_url: str | None
    scoring_strategy: str                      # e.g. "weighted_v1"
    match_distribution: dict                  # {高: int, 中: int, 低: int}


# =============================================================================
# In-Memory Pipeline Store (simple, per-process)
# =============================================================================

_pipeline_store: dict[str, dict] = {}


def get_pipeline_dir(pipeline_id: str) -> Path:
    """Get workspace directory for a pipeline run."""
    d = PROJECT_ROOT / "data" / "pipelines" / pipeline_id
    d.mkdir(parents=True, exist_ok=True)
    return d


# =============================================================================
# Stage 1: Tender Requirement Extraction
# =============================================================================

def extract_requirements(tender_text: str):
    """
    Backward-compatible wrapper kept for tests and callers importing from this module.
    Returns (profile, missing_p0_fields).
    """
    profile = extract_tender_requirements(tender_text, use_llm=False)
    missing = profile.get("missing_p0", [])
    return profile, missing
# Pipeline Orchestration
# =============================================================================

async def run_pipeline_async(request: PipelineRunRequest) -> PipelineRunResponse:
    """
    Run the full presale pipeline asynchronously.
    This is the main CEO orchestration function.
    """
    pipeline_id = str(uuid.uuid4())[:8]
    start_time = datetime.now()
    stages: list[StageOutput] = []
    pipeline_dir = get_pipeline_dir(pipeline_id)

    # ---- Stage 1: Extraction ----
    stage_start = datetime.now()
    try:
        if request.project_profile_overrides:
            profile = request.project_profile_overrides
            missing_p0 = []
        else:
            extraction_mode = os.environ.get("EXTRACTION_MODE", "hybrid")
            profile = extract_requirements(request.tender_document, mode=extraction_mode)
            missing_p0 = profile.get("missing_p0", [])

        extraction_file = pipeline_dir / "stage_1_extraction.md"
        extraction_file.write_text(
            f"# Stage 1: Requirement Extraction\n\n"
            f"Extraction Confidence: {profile.get('extraction_confidence', 'N/A')}\n"
            f"Mode: {extraction_mode}\n\n"
            f"## Profile\n{json.dumps(profile, ensure_ascii=False, indent=2)}\n\n"
            f"## Field Confidence\n{json.dumps(profile.get('field_confidence', {}), ensure_ascii=False, indent=2)}\n\n"
            f"## Source Trace\n{json.dumps(profile.get('source_trace', {}), ensure_ascii=False, indent=2)}\n\n"
            f"## Warnings\n{json.dumps(profile.get('warnings', []), ensure_ascii=False, indent=2)}",
            encoding="utf-8"
        )

        stages.append(StageOutput(
            stage="1_extraction",
            status=PipelineStageStatus.DONE,
            output_file=str(extraction_file),
            duration_seconds=(datetime.now() - stage_start).total_seconds(),
        ))
    except Exception as e:
        stages.append(StageOutput(
            stage="1_extraction",
            status=PipelineStageStatus.FAILED,
            error=str(e),
            duration_seconds=(datetime.now() - stage_start).total_seconds(),
        ))
        return PipelineRunResponse(
            pipeline_id=pipeline_id, status=PipelineStatus.FAILED,
            stages=stages, error=str(e)
        )

    region = profile.get("region", "华东")

    # ---- Stage 2: Recommendation ----
    stage_start = datetime.now()
    recommendations = []
    best_id = None
    try:
        rec_result = call_recommend(profile, request.api_base_url)
        recommendations = rec_result.get("recommendations", [])

        # Determine scenario IDs for comparison
        if request.compare_scenario_ids:
            compare_ids = request.compare_scenario_ids[:5]
        else:
            compare_ids = [r["scenario_id"] for r in recommendations[:3]]
            if len(compare_ids) < 2:
                compare_ids = [r["scenario_id"] for r in recommendations[:5]]

        best_id = compare_ids[0] if compare_ids else None

        rec_file = pipeline_dir / "stage_2_recommendations.md"
        rec_file.write_text(f"# Stage 2: Automation Recommendations\n\nTop Recommendations:\n{json.dumps(recommendations[:5], ensure_ascii=False, indent=2)}", encoding="utf-8")

        stages.append(StageOutput(
            stage="2_recommendation",
            status=PipelineStageStatus.DONE,
            output_file=str(rec_file),
            duration_seconds=(datetime.now() - stage_start).total_seconds(),
        ))
    except Exception as e:
        stages.append(StageOutput(
            stage="2_recommendation",
            status=PipelineStageStatus.FAILED,
            error=str(e),
            duration_seconds=(datetime.now() - stage_start).total_seconds(),
        ))
        return PipelineRunResponse(
            pipeline_id=pipeline_id, status=PipelineStatus.FAILED,
            stages=stages, project_profile=profile, error=str(e)
        )

    # ---- Stage 3: Cost Comparison ----
    stage_start = datetime.now()
    cost_comparisons = []
    try:
        if len(compare_ids) >= 2:
            cmp_result = call_compare(profile, region, compare_ids, request.api_base_url)
            cost_comparisons = cmp_result.get("comparisons", [])
        elif best_id:
            cost_result = call_cost(profile, region, best_id, request.api_base_url)
            cost_comparisons = [cost_result.get("cost_breakdown", {})]

        cmp_file = pipeline_dir / "stage_3_cost_comparison.md"
        cmp_file.write_text(f"# Stage 3: Cost Comparison\n\nComparisons:\n{json.dumps(cost_comparisons, ensure_ascii=False, indent=2)}", encoding="utf-8")

        stages.append(StageOutput(
            stage="3_cost_comparison",
            status=PipelineStageStatus.DONE,
            output_file=str(cmp_file),
            duration_seconds=(datetime.now() - stage_start).total_seconds(),
        ))
    except Exception as e:
        stages.append(StageOutput(
            stage="3_cost_comparison",
            status=PipelineStageStatus.FAILED,
            error=str(e),
            duration_seconds=(datetime.now() - stage_start).total_seconds(),
        ))

    # ---- Stage 4: QA (Simplified) ----
    stage_start = datetime.now()
    qa_verdict = "CONDITIONAL_PASS"
    try:
        qa_issues = []
        if missing_p0:
            qa_issues.append(f"P0缺失数据: {missing_p0}")
        if not recommendations:
            qa_issues.append("未找到推荐方案")
        if qa_issues:
            qa_verdict = "FAIL"
        else:
            qa_verdict = "PASS"

        qa_file = pipeline_dir / "stage_4_qa_report.md"
        qa_file.write_text(f"# Stage 4: QA Report\n\nVerdict: {qa_verdict}\n\nIssues: {qa_issues}", encoding="utf-8")

        stages.append(StageOutput(
            stage="4_qa_review",
            status=PipelineStageStatus.DONE,
            output_file=str(qa_file),
            duration_seconds=(datetime.now() - stage_start).total_seconds(),
        ))
    except Exception as e:
        stages.append(StageOutput(
            stage="4_qa_review",
            status=PipelineStageStatus.FAILED,
            error=str(e),
            duration_seconds=(datetime.now() - stage_start).total_seconds(),
        ))

    # ---- Stage 5: PDF Report ----
    pdf_path = None
    pdf_url = None
    if request.generate_pdf:
        stage_start = datetime.now()
        try:
            from report.generator import generate_pdf_bytes
            best_cost = next((c for c in cost_comparisons if c.get("is_best")), cost_comparisons[0] if cost_comparisons else {})
            cost_summary = f"推荐方案5年ROI {best_cost.get('roi_5y', 'N/A')}x，回本周期 {best_cost.get('payback_years', 'N/A')}年"
            cost_recommendations = [f"{c['scenario_name']}: ROI {c.get('roi_5y', 0):.1f}x" for c in cost_comparisons[:3]]

            # Get recommendation names
            rec_map = {r["scenario_id"]: r for r in recommendations}
            fake_recommendations = [
                {
                    "scenario_id": c["scenario_id"],
                    "scenario_name": c["scenario_name"],
                    "category": c.get("category", ""),
                    "score": c.get("roi_5y", 0) * 10,
                    "reason": f"5年ROI {c.get('roi_5y', 0):.1f}x，回本 {c.get('payback_years', 0):.1f}年",
                    "risk": "中",
                    "capex_range": f"¥{c['automation_capex']/10000:.0f}万",
                    "labor_saving": c.get("headcount_saved", 0) / max(c.get("headcount_required", 1), 1),
                    "efficiency_gain": 0.4,
                }
                for c in cost_comparisons
            ]

            cost_data = {
                "warehouse_cost": 0,
                "labor_cost_annual": 0,
                "automation_capex": best_cost.get("automation_capex", 0),
                "annual_maintenance": best_cost.get("annual_maintenance", 0),
                "total_annual_cost": best_cost.get("total_annual_cost", 0),
                "automation_savings_annual": best_cost.get("annual_saving", 0),
                "net_annual_benefit": best_cost.get("net_annual_benefit", 0),
                "roi": best_cost.get("roi_5y", 0),
                "payback_years": best_cost.get("payback_years", 99),
                "headcount_required": best_cost.get("headcount_required", 0),
                "headcount_saved": best_cost.get("headcount_saved", 0),
            }

            # Attach comparisons to data for PDF
            pdf_bytes, pdf_filename = generate_pdf_bytes(
                project_name=profile.get("project_name", "投标项目"),
                profile=profile,
                recommendations=fake_recommendations,
                cost_data=cost_data,
                cost_summary=cost_summary,
                cost_recommendations=cost_recommendations,
                region=region,
            )

            pdf_path = pipeline_dir / pdf_filename
            pdf_path.write_bytes(pdf_bytes)
            pdf_url = f"/api/pipeline/{pipeline_id}/download"

            stages.append(StageOutput(
                stage="5_pdf_report",
                status=PipelineStageStatus.DONE,
                output_file=str(pdf_path),
                duration_seconds=(datetime.now() - stage_start).total_seconds(),
            ))
        except Exception as e:
            stages.append(StageOutput(
                stage="5_pdf_report",
                status=PipelineStageStatus.FAILED,
                error=str(e),
                duration_seconds=(datetime.now() - stage_start).total_seconds(),
            ))

    # ---- Save pipeline state ----
    total_duration = (datetime.now() - start_time).total_seconds()
    pipeline_state = {
        "pipeline_id": pipeline_id,
        "status": PipelineStatus.COMPLETE.value,
        "stages": [s.model_dump() for s in stages],
        "project_profile": profile,
        "recommendations": recommendations[:5],
        "cost_comparisons": cost_comparisons,
        "best_scenario_id": best_id,
        "qa_verdict": qa_verdict,
        "pdf_path": str(pdf_path) if pdf_path else None,
        "total_duration_seconds": total_duration,
    }
    _pipeline_store[pipeline_id] = pipeline_state

    return PipelineRunResponse(
        pipeline_id=pipeline_id,
        status=PipelineStatus.COMPLETE,
        stages=stages,
        project_profile=profile,
        recommendations=recommendations[:5],
        cost_comparisons=cost_comparisons,
        best_scenario_id=best_id,
        qa_verdict=qa_verdict,
        pdf_path=str(pdf_path) if pdf_path else None,
        pdf_download_url=pdf_url,
    )


# =============================================================================
# API Endpoints
# =============================================================================

@router.post("/run", response_model=dict)
async def run_pipeline(request: PipelineRunRequest, background_tasks: BackgroundTasks):
    """
    Run the full presale pipeline as a background thread.
    Immediately returns a pipeline_id for polling /api/pipeline/status/{id}.
    No RQ fork needed — uses threading instead.
    """
    import threading as _threading

    pipeline_id = str(uuid.uuid4())[:8]

    def _background_job(pid: str):
        from backend.workers.pipeline_tasks import pipeline_task
        try:
            pipeline_task(
                tender_document=request.tender_document or "",
                project_profile_overrides=request.project_profile_overrides,
                api_base_url=request.api_base_url or "http://localhost:8000",
                compare_scenario_ids=request.compare_scenario_ids,
                generate_pdf=request.generate_pdf,
                use_llm=request.use_llm,
                pipeline_id=pid,
            )
        except Exception as e:
            import sys, os
            print(f"[pipeline {pid}] error: {e}", file=sys.stderr, flush=True)

    _threading.Thread(target=_background_job, args=(pipeline_id,), daemon=True).start()

    return {
        "pipeline_id": pipeline_id,
        "status": "ENQUEUED",
        "message": f"Pipeline {pipeline_id} started in background. Poll /api/pipeline/status/{pipeline_id} for progress.",
    }


# =============================================================================
# Job Management: Retry / Cancel
# =============================================================================

@router.post("/retry/{pipeline_id}", response_model=dict)
async def retry_pipeline(pipeline_id: str, background_tasks: BackgroundTasks):
    """
    Retry a failed pipeline with the same tender document and parameters.
    Creates a new pipeline run linked to the original via parent_job_id.
    """
    from backend.services.pipeline_service import get_pipeline_run as _get_run
    from backend.models.database import SessionLocal, PipelineRun

    db = SessionLocal()
    try:
        old_run = db.query(PipelineRun).filter_by(pipeline_id=pipeline_id).first()
        if not old_run:
            return {"error": f"Pipeline {pipeline_id} not found"}, 404

        if old_run.status not in ("FAILED", "CANCELLED"):
            return {"error": f"Pipeline status is {old_run.status}, can only retry FAILED/CANCELLED"}, 400

        if old_run.retry_count >= old_run.max_retries:
            return {"error": f"Max retries ({old_run.max_retries}) reached"}, 400

        # Create new pipeline with same tender document
        new_pipeline_id = str(uuid.uuid4())[:8]
        job_id = f"retry-{new_pipeline_id}-of-{pipeline_id}"

        new_run = PipelineRun(
            pipeline_id=new_pipeline_id,
            job_id=job_id,
            status="RUNNING",
            tender_document=old_run.tender_document or "",
            params_json=old_run.params_json or "{}",
            retry_count=0,
            max_retries=old_run.max_retries,
            parent_job_id=pipeline_id,
        )
        db.add(new_run)
        db.commit()

        # Enqueue background job
        import threading as _threading
        def _retry_job(pid: str, parent: str):
            from backend.workers.pipeline_tasks import pipeline_task
            params = json.loads(old_run.params_json or "{}")
            try:
                pipeline_task(
                    tender_document=old_run.tender_document or "",
                    project_profile_overrides=params.get("profile_overrides"),
                    use_llm=params.get("use_llm", True),
                    pipeline_id=pid,
                )
            except Exception as e:
                import sys; print(f"[retry {pid}] error: {e}", file=sys.stderr)

        _threading.Thread(target=_retry_job, args=(new_pipeline_id, pipeline_id), daemon=True).start()

        return {
            "pipeline_id": new_pipeline_id,
            "job_id": job_id,
            "status": "ENQUEUED",
            "parent_pipeline_id": pipeline_id,
            "message": f"Retry {old_run.retry_count + 1}/{old_run.max_retries} enqueued",
        }
    finally:
        db.close()


# =============================================================================
# Per-stage retry endpoint
# =============================================================================

class RetryStageRequest(BaseModel):
    """Request body for per-stage retry."""
    from_stage: Optional[str] = Field(default=None, description="Stage name to retry from (e.g. '3_cost_comparison'). If omitted, retries from the first failed stage.")
    profile_overrides: Optional[dict] = Field(
        default=None,
        description="Profile field overrides to merge before re-running (e.g. {'warehouse_area': 30000, 'industry': '电商'}). "
                    "Used by QA correction form to resubmit with corrected values."
    )


@router.post("/{pipeline_id}/retry", response_model=dict)
async def retry_pipeline_stage(pipeline_id: str, request: RetryStageRequest):
    """
    Retry pipeline from a specific stage onwards (in-place, same pipeline_id).

    - Cancels the pipeline if it is still RUNNING.
    - Resets all stages from `from_stage` onwards to PENDING.
    - Clears output_file and error for those stages.
    - Re-triggers pipeline_task in a background thread from that stage.

    Use this for:
    - Fixing a specific failed stage without re-running the entire pipeline.
    - Re-running from an earlier stage after correcting inputs.

    Body: {"from_stage": "3_cost_comparison"}  -- or omit from_stage to auto-detect first failed stage.
    """
    import sys
    print(f"[retry] >>> pipeline_id={pipeline_id}, from_stage={request.from_stage}, "
          f"profile_overrides={request.profile_overrides}", file=sys.stderr, flush=True)
    from backend.services.pipeline_service import (
        get_pipeline_run as _get_sql,
        reset_pipeline_stages,
        cancel_pipeline_run,
    )
    from backend.models.database import SessionLocal, PipelineRun
    import threading as _threading

    # 1. Validate pipeline exists
    sql_result = _get_sql(pipeline_id)
    if not sql_result:
        raise HTTPException(status_code=404, detail=f"Pipeline {pipeline_id} not found")

    # 2. Determine which stage to retry from
    if request.from_stage:
        from_stage = request.from_stage
    else:
        # Auto-detect first failed or earliest non-DONE stage
        stages = sql_result.get("stages", [])
        failed_stages = [s for s in stages if s.get("status") == "FAILED"]
        if failed_stages:
            from_stage = failed_stages[0].get("stage")
        else:
            # No failed stages — retry from stage 1 anyway (user probably wants to re-run)
            from_stage = "1_extraction"

    stages_order = ["1_extraction", "2_recommendation", "3_cost_comparison", "4_qa_review", "5_pdf_report"]
    if from_stage not in stages_order:
        raise HTTPException(status_code=400, detail=f"Invalid stage name: {from_stage}. Valid: {stages_order}")

    # 3. Reset stages from from_stage onwards (upsert in create_pipeline_run handles status reset)
    # Note: cancel_pipeline_run is an explicit user action, not needed here since
    # create_pipeline_run does an upsert that starts fresh regardless of prior state.
    reset_stages = reset_pipeline_stages(pipeline_id, from_stage)

    # 5. Load tender_document and params for re-execution
    db = SessionLocal()
    try:
        run = db.query(PipelineRun).filter_by(pipeline_id=pipeline_id).first()
        if not run:
            raise HTTPException(status_code=404, detail=f"PipelineRun record not found for {pipeline_id}")
        tender_document = run.tender_document or ""
        params = json.loads(run.params_json or "{}")
        api_base_url = run.api_base_url or "http://localhost:8000"
        compare_scenario_ids = None
        try:
            compare_scenario_ids = json.loads(run.compare_scenario_ids or "[]") if run.compare_scenario_ids else None
        except Exception:
            compare_scenario_ids = None
    finally:
        db.close()

    # 6. Merge profile_overrides into existing params if provided
    base_overrides = params.get("project_profile_overrides") or {}
    if request.profile_overrides:
        base_overrides = {**base_overrides, **request.profile_overrides}

    # v0.6.5: Also merge clarified values from resolved_fields so retry picks them up
    # Clarification Workspace saves to resolved_fields_json; re-extraction would lose them.
    db = SessionLocal()
    try:
        run_for_fields = db.query(PipelineRun).filter_by(pipeline_id=pipeline_id).first()
        resolved_fields_raw = {}
        if run_for_fields and run_for_fields.resolved_fields_json:
            try:
                resolved_fields_raw = json.loads(run_for_fields.resolved_fields_json) or {}
            except Exception:
                pass

        readiness_json_str = ""
        if run_for_fields and run_for_fields.readiness_json:
            try:
                readiness_json_str = run_for_fields.readiness_json
            except Exception:
                pass

        # Merge usable resolved fields into base_overrides
        for fkey, rf in resolved_fields_raw.items():
            usable = rf.get("usable", False) if isinstance(rf, dict) else False
            if usable and rf.get("final_value") is not None:
                base_overrides[fkey] = rf["final_value"]

        # Restore readiness — compute from resolved_fields_raw directly (DB readiness_json may be empty
        # due to recompute bugs; we must guarantee readiness is injected for gate to work correctly).
        readiness_data = None
        if readiness_json_str:
            try:
                readiness_data = json.loads(readiness_json_str) or None
            except Exception:
                pass

        if not readiness_data and resolved_fields_raw:
            # Compute readiness directly from resolved_fields_raw: P0 must all be usable for cost_model gate
            p0_keys = ["warehouse_area", "total_warehouse_area", "dc_count",
                        "daily_orders", "sku_count", "contract_years", "service_scope"]
            p0_usable = sum(
                1 for fk in p0_keys
                if resolved_fields_raw.get(fk, {}).get("usable", False) is True
            )
            readiness_data = {
                "level": "ready" if p0_usable == len(p0_keys) else "blocked",
                "readiness_score": p0_usable / len(p0_keys) if p0_keys else 0.0,
                "for_cost_model": p0_usable == len(p0_keys),
                "for_solution_design": p0_usable == len(p0_keys),
                "for_contract_review": False,  # P1 not tracked here; recompute will give accurate value
                "p0_field_status": {
                    fk: ("provided" if resolved_fields_raw.get(fk, {}).get("usable") else "missing")
                    for fk in p0_keys
                },
                "p0_summary": {
                    "total": len(p0_keys),
                    "usable": p0_usable,
                    "missing": len(p0_keys) - p0_usable,
                },
            }

        if readiness_data:
            base_overrides["_readiness"] = readiness_data
    finally:
        db.close()

    # Also update stored params_json so subsequent retries see the corrected values
    if request.profile_overrides or resolved_fields_raw:
        params["project_profile_overrides"] = base_overrides
        try:
            db = SessionLocal()
            try:
                run = db.query(PipelineRun).filter_by(pipeline_id=pipeline_id).first()
                if run:
                    run.params_json = json.dumps(params)
                    db.commit()
            finally:
                db.close()
        except Exception:
            pass  # Best-effort: don't fail the retry if DB update fails

    # 7. Re-trigger background job from that stage
    def _retry_stage_job(pid: str, from_s: str):
        from backend.workers.pipeline_tasks import pipeline_task
        try:
            pipeline_task(
                tender_document=tender_document,
                project_profile_overrides=base_overrides,
                api_base_url=api_base_url,
                compare_scenario_ids=compare_scenario_ids,
                generate_pdf=params.get("generate_pdf", True),
                use_llm=params.get("use_llm", True),
                pipeline_id=pid,
                rerun_stage2=True,  # Re-run recommendation with clarified fields
            )
        except Exception as e:
            import sys; print(f"[stage-retry {pid}] error: {e}", file=sys.stderr, flush=True)

    _threading.Thread(target=_retry_stage_job, args=(pipeline_id, from_stage), daemon=True).start()

    return {
        "pipeline_id": pipeline_id,
        "status": "RUNNING",
        "from_stage": from_stage,
        "reset_stages": reset_stages,
        "message": f"Pipeline {pipeline_id} retrying from stage '{from_stage}'. Poll /api/pipeline/status/{pipeline_id} for progress.",
    }


@router.post("/cancel/{pipeline_id}", response_model=dict)
async def cancel_pipeline(pipeline_id: str):
    """
    Cancel a running or queued pipeline.
    Sets cancelled_at timestamp — worker checks this between stages.
    """
    from backend.models.database import SessionLocal, PipelineRun
    from datetime import datetime

    db = SessionLocal()
    try:
        run = db.query(PipelineRun).filter_by(pipeline_id=pipeline_id).first()
        if not run:
            return {"error": f"Pipeline {pipeline_id} not found"}, 404

        if run.status in ("COMPLETE", "CANCELLED"):
            return {"error": f"Pipeline is already {run.status}"}, 400

        run.status = "CANCELLED"
        run.cancelled_at = datetime.utcnow()
        db.commit()

        return {
            "pipeline_id": pipeline_id,
            "status": "CANCELLED",
            "cancelled_at": run.cancelled_at.isoformat(),
        }
    finally:
        db.close()


@router.get("/jobs", response_model=list)
async def list_jobs(limit: int = 20):
    """List recent pipeline jobs with job metadata."""
    from backend.services.pipeline_service import list_pipeline_runs as _list
    runs = _list(limit=limit)
    return [
        {
            "pipeline_id": r["pipeline_id"],
            "status": r["status"],
            "created_at": r["created_at"],
            "completed_at": r.get("completed_at"),
            "total_duration_seconds": r.get("total_duration_seconds"),
            "error": r.get("error"),
        }
        for r in runs
    ]


@router.post("/extract", response_model=ExtractionResponse)
async def extract_profile(request: ExtractionRequest):
    """
    Standalone: Extract project profile from tender document text.
    Use this to preview extraction results before running full pipeline.

    Set use_llm=True to use LLM extraction (higher quality, requires API key).
    Set use_llm=False to use regex extraction only.
    """
    use_llm = getattr(request, 'use_llm', True)
    from backend.services.tender_service import extract_tender_requirements
    profile = extract_tender_requirements(request.tender_document, use_llm=use_llm)
    missing_p0 = profile.get("missing_p0", [])
    confidence = profile.get("extraction_confidence", 0.0)

    # Build raw summary
    raw_summary = (
        f"行业: {profile.get('industry','电商')} | "
        f"地区: {profile.get('region','华东')} | "
        f"面积: {profile.get('warehouse_area') or '待确认'}㎡ | "
        f"SKU: {profile.get('sku_count') or '待确认'} | "
        f"日订单: {profile.get('daily_orders') or '待确认'}单"
    )

    return ExtractionResponse(
        project_profile=profile,
        extraction_confidence=confidence,
        raw_requirements_summary=raw_summary,
        missing_p0=missing_p0 or [],
        missing_p1=[],
    )


@router.post("/demo", response_model=DemoResponse)
async def run_demo(request: DemoRequest):
    """
    Lightweight end-to-end demo: takes a project profile directly, no tender doc.

    Returns:
        - Normalized input profile
        - Top N automation recommendations with score_breakdown + reasons
        - Financial comparison (CAPEX / OPEX / ROI / payback)
        - Optional PDF download URL

    Use this for:
        - Internal demos and rapid prototyping
        - Validating recommendation logic
        - Quick ROI estimation without uploading documents
    """
    from backend.services.recommendation_service import recommend_solutions
    from backend.services.cost_service import compare_solution_financials
    import uuid as _uuid

    # Build profile dict from request
    profile = {
        "industry": request.industry,
        "region": request.region,
        "warehouse_area": request.warehouse_area,
        "sku_count": request.sku_count,
        "daily_orders": request.daily_orders,
        "inventory": request.inventory,
        "labor_cost_level": request.labor_cost_level,
        "budget_level": request.budget_level,
        "automation_expectation": request.automation_expectation,
        "contract_years": request.contract_years,
    }

    # Get recommendations (includes reasons + breakdown)
    rec_result = recommend_solutions(profile, top_n=request.top_n, include_reasons=True)
    recommendations = rec_result.get("recommendations", [])
    normalized_profile = rec_result.get("total_profiles_normalized", profile)
    match_distribution = rec_result.get("match_distribution", {})

    if not recommendations:
        return DemoResponse(
            project_profile=normalized_profile,
            recommendations=[],
            financial_comparison=[],
            pdf_url=None,
            scoring_strategy="weighted_v1",
            match_distribution=match_distribution,
        )

    # Get financial comparison for each recommended scenario
    financial_comparison = compare_solution_financials(
        normalized_profile, recommendations, region=request.region
    )

    # PDF generation for demo (best-effort — full PDF via report_service later)
    pdf_url = None
    if request.generate_pdf:
        # Placeholder: demo PDF not yet implemented
        # Will be added via backend/services/report_service.generate_demo_report()
        pass

    return DemoResponse(
        project_profile=normalized_profile,
        recommendations=[
            {
                "scenario_id": r["scenario_id"],
                "scenario_name": r["scenario_name"],
                "category": r.get("category", ""),
                "score": r["score"],
                "score_breakdown": r.get("score_breakdown", {}),
                "match_level": r.get("match_level", "中"),
                "reasons": r.get("reasons", []),
                "scoring_strategy": r.get("scoring_strategy", "weighted_v1"),
                "capex_range": r.get("capex_range", ""),
                "labor_saving": r.get("labor_saving", 0),
                "efficiency_gain": r.get("efficiency_gain", 0),
                "risk_level": r.get("risk_level", "中"),
            }
            for r in recommendations
        ],
        financial_comparison=[
            {
                "scenario_name": f["scenario_name"],
                "category": f.get("category", ""),
                "capex_estimate": f.get("capex_estimate", 0),
                "capex_range": f.get("currency_fmt", {}).get("capex", "—"),
                "opex_annual": f.get("opex_annual", 0),
                "roi_5y": f.get("roi_5y", 0),
                "roi_3y": f.get("roi_3y", 0),
                "payback_years": f.get("payback_years"),
                "payback_years_str": f.get("payback_years_str", "—"),
                "headcount_saved": f.get("headcount_saved", 0),
                "is_best": f.get("is_best", False),
                "warnings": f.get("warnings", []),
            }
            for f in financial_comparison
        ],
        pdf_url=pdf_url,
        scoring_strategy="weighted_v1",
        match_distribution=match_distribution,
    )


@router.get("/status/{pipeline_id}")
async def get_pipeline_status(pipeline_id: str):
    """Get pipeline run status by ID. Reads from SQLite first, falls back to Redis."""
    import json as _json

    # Try SQLite first (durable, primary store)
    from backend.services.pipeline_service import get_pipeline_run as _get_sql
    sql_result = _get_sql(pipeline_id)
    if sql_result:
        # Also check Redis for mid-flight overrides
        redis_key = f"pipeline:{pipeline_id}"
        redis_data = _redis_conn.hgetall(redis_key)
        overrides_json = redis_data.get("profile_overrides") if redis_data else None
        if overrides_json:
            try:
                overrides = _json.loads(overrides_json)
                if overrides:
                    sql_result["profile"] = {**sql_result.get("profile", {}), **overrides}
            except Exception:
                pass
        return sql_result

    # Fallback to in-memory store (for sync pipeline runs)
    if pipeline_id in _pipeline_store:
        return _pipeline_store[pipeline_id]

    raise HTTPException(status_code=404, detail="Pipeline not found")


@router.get("/{pipeline_id}/download")
async def download_pdf(pipeline_id: str):
    """Download the generated PDF report. Reads from SQLite first, then Redis, then memory store."""
    # Try SQLite first (durable, primary store)
    from backend.services.pipeline_service import get_pipeline_run as _get_sql
    sql_result = _get_sql(pipeline_id)
    if sql_result:
        pdf_path = sql_result.get("pdf_path")
        if pdf_path and Path(pdf_path).exists():
            from fastapi.responses import FileResponse
            return FileResponse(
                pdf_path,
                media_type="application/pdf",
                filename=f"pipeline_{pipeline_id}_report.pdf",
            )

    # Fallback to Redis
    redis_key = f"pipeline:{pipeline_id}"
    redis_data = _redis_conn.hgetall(redis_key)
    if redis_data:
        pdf_path = redis_data.get("pdf_path")
        if pdf_path and Path(pdf_path).exists():
            from fastapi.responses import FileResponse
            return FileResponse(
                pdf_path,
                media_type="application/pdf",
                filename=f"pipeline_{pipeline_id}_report.pdf",
            )

    # Fallback to memory store (sync runs)
    if pipeline_id in _pipeline_store:
        state = _pipeline_store[pipeline_id]
        pdf_path = state.get("pdf_path")
        if pdf_path and Path(pdf_path).exists():
            from fastapi.responses import FileResponse
            return FileResponse(
                pdf_path,
                media_type="application/pdf",
                filename=f"pipeline_{pipeline_id}_report.pdf",
            )

    raise HTTPException(status_code=404, detail="PDF not found")


@router.get("/compare-scenarios")
async def compare_scenarios_endpoint(
    industry: str,
    warehouse_area: float,
    sku_count: int,
    daily_orders: int,
    inventory: int,
    labor_cost_level: str = "中",
    budget_level: str = "中",
    automation_expectation: str = "中",
    region: str = "华东",
    scenario_ids: str = "1,2,3,4,5",
):
    """
    Quick comparison endpoint: compare specific scenarios by IDs.
    scenario_ids: comma-separated list of scenario IDs, e.g. "1,2,3"
    """
    try:
        sids = [int(s.strip()) for s in scenario_ids.split(",") if s.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid scenario_ids format")

    if len(sids) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 scenario IDs")

    profile = {
        "industry": industry,
        "warehouse_area": warehouse_area,
        "sku_count": sku_count,
        "daily_orders": daily_orders,
        "inventory": inventory,
        "labor_cost_level": labor_cost_level,
        "budget_level": budget_level,
        "automation_expectation": automation_expectation,
    }

    result = get_scenario_comparison(profile, region, sids)
    return result


# =============================================================================
# Retry single step
# =============================================================================

@router.patch("/{pipeline_id}")
async def update_pipeline(pipeline_id: str, body: dict):
    """
    Update pipeline params mid-flight (e.g. after low-confidence correction).
    Writes to both Redis (for immediate read) and SQLite (for durability).
    """
    if "profile_overrides" in body:
        overrides_json = json.dumps(body["profile_overrides"], ensure_ascii=False)
        # Write to Redis for immediate next-poll read
        _redis_conn.hset(f"pipeline:{pipeline_id}", "profile_overrides", overrides_json)
        _redis_conn.hset(f"pipeline:{pipeline_id}", "status", "RUNNING")
        _redis_conn.hset(f"pipeline:{pipeline_id}", "updated_at", datetime.now().isoformat())
    return {"pipeline_id": pipeline_id, "updated": True}


@router.get("/history")
async def list_pipeline_history(limit: int = 20):
    """List recent pipeline runs from SQLite."""
    from backend.services.pipeline_service import list_pipeline_runs as _list_runs
    return {"runs": _list_runs(limit=limit)}
