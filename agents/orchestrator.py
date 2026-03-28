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

import redis as _redis_lib
from rq import Queue as RQQueue

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_redis_conn = _redis_lib.from_url(REDIS_URL, decode_responses=True)
_pipeline_queue = RQQueue("pipeline", connection=_redis_conn, default_timeout="30m")

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

def extract_requirements(tender_text: str) -> dict:
    """
    Extract structured project profile from tender document text.
    Uses keyword matching + heuristics (lightweight, no LLM needed).
    For full extraction, call Tender Extractor Agent via sessions_spawn.
    """
    import re

    text = tender_text
    profile = {
        "project_name": "待确认",
        "client_name": "待确认",
        "industry": "电商",  # default
        "region": "华东",     # default
        "warehouse_area": None,
        "sku_count": None,
        "daily_orders": None,
        "inventory": None,
        "labor_cost_level": "中",
        "budget_level": "中",
        "automation_expectation": "中",
        "contract_years": 3,
        "go_live_date": "待确认",
    }

    # Industry detection
    industry_map = {
        "电商": ["电商", "电子商务", "天猫", "京东", "淘宝"],
        "3PL": ["3PL", "第三方物流", "物流外包"],
        "零售": ["零售", "商超", "便利店", "百货"],
        "制造": ["制造", "生产商", "工厂"],
        "快递": ["快递", "速运", "快运"],
        "医药": ["医药", "制药", "医疗"],
        "食品": ["食品", "饮料", "乳制品"],
        "生鲜": ["生鲜", "冷链", "农产品"],
    }
    for industry, keywords in industry_map.items():
        if any(kw in text for kw in keywords):
            profile["industry"] = industry
            break

    # Region detection
    region_map = {
        "华东": ["上海", "江苏", "浙江", "安徽", "华东"],
        "华南": ["广东", "广西", "海南", "华南"],
        "华北": ["北京", "天津", "河北", "华北"],
        "华中": ["湖北", "湖南", "河南", "华中"],
        "西部": ["四川", "重庆", "陕西", "西部", "新疆", "甘肃"],
    }
    for region, keywords in region_map.items():
        if any(kw in text for kw in keywords):
            profile["region"] = region
            break

    # Warehouse area - match patterns like "25000平方米", "面积25000平米", "25000平米"
    patterns_area = [
        r"(\d[\d,\.]*)\s*(?:平米|㎡|平方米)",
        r"面积[是为约：:\s]*(\d[\d,\.]*)",
        r"仓库[面积是为约：:\s]+(\d[\d,\.]*)",
    ]
    for p in patterns_area:
        m = re.search(p, text)
        if m:
            val = float(m.group(1).replace(",", ""))
            if 100 < val < 500000:
                profile["warehouse_area"] = val
                break

    # SKU count - must use labeled patterns (SKU/sku prefix) to avoid conflicts
    patterns_sku = [
        r"SKU[数量是为约：:\s]*(\d[\d,\.]*)",
        r"sku[数量是为约：:\s]*(\d[\d,\.]*)",
        r"品种[是为约：:\s]*(\d[\d,\.]*)",
    ]
    for p in patterns_sku:
        m = re.search(p, text)
        if m:
            val = float(m.group(1).replace(",", ""))
            if 100 < val < 5000000:
                profile["sku_count"] = int(val)
                break

    # Daily orders - labeled patterns + explicit unit patterns
    patterns_orders = [
        r"(\d[\d,\.]*)\s*(?:单|票)[/天日月]?",  # explicit unit after number
        r"日均[订单票量约为：:\s]*(\d[\d,\.]*)",
        r"订单[量为约：:\s]*(\d[\d,\.]*)",
        r"日均[为约：:\s]*(\d[\d,\.]*)",
    ]
    for p in patterns_orders:
        m = re.search(p, text)
        if m:
            val = float(m.group(1).replace(",", ""))
            if 5 < val < 5000000:
                profile["daily_orders"] = int(val)
                break

    # Inventory - must use labeled patterns to avoid conflicts with SKU
    patterns_inv = [
        r"库存[量为约：:\s]*(\d[\d,\.]*)",
        r"库容[量为约：:\s]*(\d[\d,\.]*)",
        r"存储[量为约：:\s]*(\d[\d,\.]*)",
        r"(\d[\d,\.]*)\s*件[/天日月]?",  # inventory: 1000000件
    ]
    for p in patterns_inv:
        m = re.search(p, text)
        if m:
            val = float(m.group(1).replace(",", ""))
            if 1000 < val < 100000000:
                profile["inventory"] = int(val)
                break

    # Budget level
    budget_map = {
        "低": ["100万", "50万", "有限", "紧张", "100万元"],
        "中": ["300万", "500万", "中等", "500万元"],
        "高": ["1000万", "2000万", "充足", "高预算", "1000万元"],
    }
    for level, keywords in budget_map.items():
        if any(kw in text for kw in keywords):
            profile["budget_level"] = level
            break

    # Contract years
    m = re.search(r"(\d+)\s*[+]?\s*年", text)
    if m:
        profile["contract_years"] = int(m.group(1))

    # Go-live
    m = re.search(r"(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})", text)
    if m:
        profile["go_live_date"] = m.group(1)

    # Missing data tracking
    missing_p0 = []
    for field in ["warehouse_area", "sku_count", "daily_orders"]:
        if profile.get(field) is None:
            missing_p0.append(field)

    return profile, missing_p0


# =============================================================================
# Stage 2: Call Recommendation + Cost APIs
# =============================================================================

def call_recommend(profile: dict, api_base: str) -> dict:
    """Call /api/recommend with project profile."""
    try:
        result = get_recommendations(profile)
        return result
    except Exception as e:
        raise RuntimeError(f"Recommendation API failed: {e}")


def call_compare(profile: dict, region: str, scenario_ids: list, api_base: str) -> dict:
    """Call /api/compare with project profile and scenario IDs."""
    try:
        result = get_scenario_comparison(profile, region, scenario_ids)
        return result
    except Exception as e:
        raise RuntimeError(f"Compare API failed: {e}")


def call_cost(profile: dict, region: str, scenario_id: int, api_base: str) -> dict:
    """Call /api/cost for single scenario cost."""
    try:
        result = get_cost_analysis(profile, region, scenario_id)
        return result
    except Exception as e:
        raise RuntimeError(f"Cost API failed: {e}")


# =============================================================================
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
            profile, missing_p0 = extract_requirements(request.tender_document)

        extraction_file = pipeline_dir / "stage_1_extraction.md"
        extraction_file.write_text(f"# Stage 1: Requirement Extraction\n\nProfile: {json.dumps(profile, ensure_ascii=False, indent=2)}\n\nMissing P0: {missing_p0}", encoding="utf-8")

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
async def run_pipeline(request: PipelineRunRequest):
    """
    Enqueue the full presale pipeline as an async RQ job.
    Immediately returns a pipeline_id for polling /api/pipeline/status/{id}.
    """
    from backend.workers.pipeline_tasks import pipeline_task

    # Generate pipeline_id upfront so client can poll immediately
    pipeline_id = str(uuid.uuid4())[:8]

    job = _pipeline_queue.enqueue(
        "backend.workers.pipeline_tasks.pipeline_task",
        tender_document=request.tender_document,
        project_profile_overrides=request.project_profile_overrides,
        api_base_url=request.api_base_url,
        compare_scenario_ids=request.compare_scenario_ids,
        generate_pdf=request.generate_pdf,
        pipeline_id=pipeline_id,
        job_timeout="30m",
    )

    return {
        "pipeline_id": pipeline_id,
        "job_id": job.id,
        "status": "ENQUEUED",
        "message": f"Pipeline {pipeline_id} queued. Poll /api/pipeline/status/{pipeline_id} for progress.",
    }


@router.post("/extract", response_model=ExtractionResponse)
async def extract_profile(request: ExtractionRequest):
    """
    Standalone: Extract project profile from tender document text.
    Use this to preview extraction results before running full pipeline.
    """
    profile, missing_p0 = extract_requirements(request.tender_document)

    # Build raw summary
    raw_summary = (
        f"行业: {profile['industry']} | "
        f"地区: {profile['region']} | "
        f"面积: {profile['warehouse_area'] or '待确认'}㎡ | "
        f"SKU: {profile['sku_count'] or '待确认'} | "
        f"日订单: {profile['daily_orders'] or '待确认'}单"
    )

    # Confidence: higher if more fields are populated
    populated = sum(1 for v in [
        profile.get("warehouse_area"), profile.get("sku_count"),
        profile.get("daily_orders"), profile.get("inventory")
    ] if v is not None)
    confidence = round(populated / 4 * 0.9 + 0.1, 2)

    return ExtractionResponse(
        project_profile=profile,
        extraction_confidence=confidence,
        raw_requirements_summary=raw_summary,
        missing_p0=missing_p0,
        missing_p1=[],
    )


@router.get("/status/{pipeline_id}")
async def get_pipeline_status(pipeline_id: str):
    """Get pipeline run status by ID. Reads from Redis for live updates."""
    import json as _json

    # Try Redis first
    key = f"pipeline:{pipeline_id}"
    redis_data = _redis_conn.hgetall(key)

    if redis_data:
        stages = _json.loads(redis_data.get("stages", "[]"))
        result = {
            "pipeline_id": pipeline_id,
            "status": redis_data.get("status", "UNKNOWN"),
            "stages": stages,
            "created_at": redis_data.get("created_at"),
            "updated_at": redis_data.get("updated_at"),
        }
        for field in ["project_profile", "recommendations", "cost_comparisons",
                       "best_scenario_id", "qa_verdict", "pdf_path",
                       "pdf_download_url", "total_duration_seconds", "error"]:
            if field in redis_data:
                result[field] = _json.loads(redis_data[field]) if redis_data[field].startswith(("[{", "{")) else redis_data[field]
        return result

    # Fallback to in-memory store (for sync pipeline runs)
    if pipeline_id in _pipeline_store:
        return _pipeline_store[pipeline_id]

    raise HTTPException(status_code=404, detail="Pipeline not found")


@router.get("/{pipeline_id}/download")
async def download_pdf(pipeline_id: str):
    """Download the generated PDF report."""
    if pipeline_id not in _pipeline_store:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    state = _pipeline_store[pipeline_id]
    pdf_path = state.get("pdf_path")
    if not pdf_path or not Path(pdf_path).exists():
        raise HTTPException(status_code=404, detail="PDF not found")
    from fastapi.responses import FileResponse
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"pipeline_{pipeline_id}_report.pdf",
    )


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
