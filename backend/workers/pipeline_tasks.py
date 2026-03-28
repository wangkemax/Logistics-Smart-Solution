"""
Pipeline Tasks
=============
Async pipeline tasks run in background threads.
Each stage updates SQLite for durable persistence.
"""

import os
import sys
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.project_service import (
    get_recommendations,
    get_cost_analysis,
    get_scenario_comparison,
)
from backend.services.pipeline_service import (
    create_pipeline_run,
    create_stage,
    update_stage as _sql_update_stage,
    complete_pipeline,
    get_pipeline_run,
)


def _get_pipeline_dir(pipeline_id: str) -> Path:
    d = PROJECT_ROOT / "data" / "pipelines" / pipeline_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _update_stage(pipeline_id: str, stage: str, status: str, output_file: str = None,
                  error: str = None, duration_seconds: float = None, extra: dict = None):
    """Update a single stage in SQLite."""
    _sql_update_stage(
        pipeline_id=pipeline_id,
        stage_name=stage,
        status=status,
        error=error,
        duration_seconds=duration_seconds,
        output_file=output_file,
        extra=extra,
    )


def _set_status(pipeline_id: str, status: str, **kwargs):
    """Set overall pipeline status in SQLite."""
    pass  # Status is updated by complete_pipeline


def pipeline_task(tender_document: str, project_profile_overrides: dict = None, use_llm: bool = True,
                  api_base_url: str = "http://localhost:8000",
                  compare_scenario_ids: list = None,
                  generate_pdf: bool = True,
                  pipeline_id: str = None) -> dict:
    """
    Main RQ pipeline task. Runs stages sequentially, updating Redis at each step.
    Returns the final pipeline state dict.
    """
    pipeline_id = pipeline_id or str(uuid.uuid4())[:8]
    start_time = datetime.now()
    pipeline_dir = _get_pipeline_dir(pipeline_id)

    # Init SQLite state — create pipeline run + all stage records
    create_pipeline_run(
        pipeline_id=pipeline_id,
        tender_document=tender_document or "",
        params_json={
            "api_base_url": api_base_url,
            "compare_scenario_ids": compare_scenario_ids,
            "generate_pdf": generate_pdf,
        },
    )
    for stage_name in ["1_extraction", "2_recommendation", "3_cost_comparison", "4_qa_review", "5_pdf_report"]:
        create_stage(pipeline_id, stage_name)

    profile = None
    missing_p0 = []
    recommendations = []
    cost_comparisons = []
    best_id = None
    qa_verdict = "CONDITIONAL_PASS"
    pdf_path = None
    pdf_url = None

    # ---- Stage 1: Extraction ----
    stage_start = datetime.now()
    _update_stage(pipeline_id, "1_extraction", "RUNNING")
    try:
        if project_profile_overrides:
            profile = project_profile_overrides
            missing_p0 = []
        else:
            # Import here to avoid circular
            from backend.services.llm_extractor import extract_requirements_llm
            profile, missing_p0, confidence = extract_requirements_llm(tender_document, use_llm=use_llm)

        extraction_file = pipeline_dir / "stage_1_extraction.md"
        extraction_file.write_text(
            f"# Stage 1: Requirement Extraction\n\n"
            f"Profile: {json.dumps(profile, ensure_ascii=False, indent=2)}\n\n"
            f"Missing P0: {missing_p0}",
            encoding="utf-8"
        )
        _update_stage(pipeline_id, "1_extraction", "DONE",
                      output_file=str(extraction_file),
                      duration_seconds=(datetime.now() - stage_start).total_seconds())
    except Exception as e:
        _update_stage(pipeline_id, "1_extraction", "FAILED",
                      error=str(e),
                      duration_seconds=(datetime.now() - stage_start).total_seconds())
        complete_pipeline(pipeline_id, "FAILED", error=str(e))
        return {"pipeline_id": pipeline_id, "status": "FAILED", "error": str(e)}

    # Check SQLite for mid-pipeline profile overrides (after low-confidence correction)
    stored_overrides = None  # Keep for compatibility — PATCH writes to Redis for simplicity

    region = profile.get("region", "华东")

    # ---- Stage 2: Recommendation ----
    stage_start = datetime.now()
    _update_stage(pipeline_id, "2_recommendation", "RUNNING")
    try:
        rec_result = get_recommendations(profile)
        recommendations = rec_result.get("recommendations", [])

        if compare_scenario_ids:
            compare_ids = compare_scenario_ids[:5]
        else:
            compare_ids = [r["scenario_id"] for r in recommendations[:3]]
            if len(compare_ids) < 2:
                compare_ids = [r["scenario_id"] for r in recommendations[:5]]

        best_id = compare_ids[0] if compare_ids else None

        rec_file = pipeline_dir / "stage_2_recommendations.md"
        rec_file.write_text(
            f"# Stage 2: Automation Recommendations\n\n"
            f"Top Recommendations:\n{json.dumps(recommendations[:5], ensure_ascii=False, indent=2)}",
            encoding="utf-8"
        )
        _update_stage(pipeline_id, "2_recommendation", "DONE",
                      output_file=str(rec_file),
                      duration_seconds=(datetime.now() - stage_start).total_seconds(),
                      extra={"recommendations": recommendations[:5], "best_scenario_id": best_id})
    except Exception as e:
        _update_stage(pipeline_id, "2_recommendation", "FAILED",
                      error=str(e),
                      duration_seconds=(datetime.now() - stage_start).total_seconds())
        complete_pipeline(pipeline_id, "FAILED", error=str(e))
        return {"pipeline_id": pipeline_id, "status": "FAILED", "error": str(e)}

    # ---- Stage 3: Cost Comparison ----
    stage_start = datetime.now()
    _update_stage(pipeline_id, "3_cost_comparison", "RUNNING")
    try:
        if len(compare_ids) >= 2:
            cmp_result = get_scenario_comparison(profile, region, compare_ids)
            cost_comparisons = cmp_result.get("comparisons", [])
        elif best_id:
            cost_result = get_cost_analysis(profile, region, best_id)
            cost_comparisons = [cost_result.get("cost_breakdown", {})]

        cmp_file = pipeline_dir / "stage_3_cost_comparison.md"
        cmp_file.write_text(
            f"# Stage 3: Cost Comparison\n\n"
            f"Comparisons:\n{json.dumps(cost_comparisons, ensure_ascii=False, indent=2)}",
            encoding="utf-8"
        )
        _update_stage(pipeline_id, "3_cost_comparison", "DONE",
                      output_file=str(cmp_file),
                      duration_seconds=(datetime.now() - stage_start).total_seconds(),
                      extra={"cost_comparisons": cost_comparisons})
    except Exception as e:
        _update_stage(pipeline_id, "3_cost_comparison", "FAILED",
                      error=str(e),
                      duration_seconds=(datetime.now() - stage_start).total_seconds())
        complete_pipeline(pipeline_id, "FAILED", error=str(e))
        return {"pipeline_id": pipeline_id, "status": "FAILED", "error": str(e)}

    # ---- Stage 4: QA ----
    stage_start = datetime.now()
    _update_stage(pipeline_id, "4_qa_review", "RUNNING")
    try:
        qa_issues = []
        if missing_p0:
            qa_issues.append(f"P0缺失数据: {missing_p0}")
        if not recommendations:
            qa_issues.append("未找到推荐方案")
        qa_verdict = "FAIL" if qa_issues else "PASS"

        qa_file = pipeline_dir / "stage_4_qa_report.md"
        qa_file.write_text(
            f"# Stage 4: QA Report\n\nVerdict: {qa_verdict}\n\nIssues: {qa_issues}",
            encoding="utf-8"
        )
        _update_stage(pipeline_id, "4_qa_review", "DONE",
                      output_file=str(qa_file),
                      duration_seconds=(datetime.now() - stage_start).total_seconds(),
                      extra={"qa_verdict": qa_verdict, "qa_issues": qa_issues})
    except Exception as e:
        _update_stage(pipeline_id, "4_qa_review", "FAILED",
                      error=str(e),
                      duration_seconds=(datetime.now() - stage_start).total_seconds())
        complete_pipeline(pipeline_id, "FAILED", error=str(e))
        return {"pipeline_id": pipeline_id, "status": "FAILED", "error": str(e)}

    # ---- Stage 5: PDF Report ----
    if generate_pdf:
        stage_start = datetime.now()
        _update_stage(pipeline_id, "5_pdf_report", "RUNNING")
        try:
            from report.generator import generate_pdf_bytes

            print(f"[DEBUG] cost_comparisons[0] keys: {list(cost_comparisons[0].keys()) if cost_comparisons else 'EMPTY'}")
            print(f"[DEBUG] cost_comparisons[0] headcount_saved: {cost_comparisons[0].get('headcount_saved') if cost_comparisons else 'N/A'}")
            print(f"[DEBUG] cost_comparisons[0] headcount_required: {cost_comparisons[0].get('headcount_required') if cost_comparisons else 'N/A'}")
            print(f"[DEBUG] recommendations[:1]: {recommendations[:1] if recommendations else 'EMPTY'}")

            best_cost = next(
                (c for c in cost_comparisons if c.get("is_best")),
                cost_comparisons[0] if cost_comparisons else {}
            )
            cost_summary = (f"推荐方案5年ROI {best_cost.get('roi_5y', 'N/A')}x，"
                            f"回本周期 {best_cost.get('payback_years', 'N/A')}年")
            cost_recommendations = [
                f"{c['scenario_name']}: ROI {c.get('roi_5y', 0):.1f}x"
                for c in cost_comparisons[:3]
            ]

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

            _update_stage(pipeline_id, "5_pdf_report", "DONE",
                          output_file=str(pdf_path),
                          duration_seconds=(datetime.now() - stage_start).total_seconds(),
                          extra={"pdf_path": str(pdf_path), "pdf_download_url": pdf_url})
        except Exception as e:
            _update_stage(pipeline_id, "5_pdf_report", "FAILED",
                          error=str(e),
                          duration_seconds=(datetime.now() - stage_start).total_seconds())
    else:
        _update_stage(pipeline_id, "5_pdf_report", "SKIPPED")

    # ---- Finalize ----
    total_duration = (datetime.now() - start_time).total_seconds()
    complete_pipeline(
        pipeline_id=pipeline_id,
        status="COMPLETE",
        profile_json=profile,
        recommendations_json=recommendations[:5],
        comparisons_json=cost_comparisons,
        qa_verdict=qa_verdict,
        pdf_path=str(pdf_path) if pdf_path else None,
        pdf_url=pdf_url,
        total_duration_seconds=total_duration,
    )

    return {
        "pipeline_id": pipeline_id,
        "status": "COMPLETE",
        "project_profile": profile,
        "recommendations": recommendations[:5],
        "cost_comparisons": cost_comparisons,
        "best_scenario_id": best_id,
        "qa_verdict": qa_verdict,
        "pdf_path": str(pdf_path) if pdf_path else None,
        "pdf_download_url": pdf_url,
        "total_duration_seconds": total_duration,
    }
