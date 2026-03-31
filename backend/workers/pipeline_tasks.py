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
    get_cost_analysis,
    get_scenario_comparison,
)
from backend.services.recommendation_service import recommend_solutions
from backend.services.cost_service import compare_solution_financials
from backend.services.qa_engine import run_qa, format_issues_for_ui
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


class PipelineCancelled(Exception):
    """Raised when pipeline is cancelled mid-execution."""
    pass


def _check_cancelled(pipeline_id: str):
    """Raise PipelineCancelled if pipeline was cancelled. Call between stages."""
    from backend.models.database import SessionLocal, PipelineRun
    db = SessionLocal()
    try:
        run = db.query(PipelineRun).filter_by(pipeline_id=pipeline_id).first()
        if run and run.status == "CANCELLED":
            raise PipelineCancelled(f"Pipeline {pipeline_id} was cancelled")
    finally:
        db.close()


def _set_status(pipeline_id: str, status: str, **kwargs):
    """Set overall pipeline status in SQLite."""
    pass  # Status is updated by complete_pipeline


def pipeline_task(tender_document: str, project_profile_overrides: dict = None, use_llm: bool = True,
                  api_base_url: str = "http://localhost:8000",
                  compare_scenario_ids: list = None,
                  generate_pdf: bool = True,
                  pipeline_id: str = None,
                  rerun_stage2: bool = False) -> dict:
    """
    Main RQ pipeline task. Runs stages sequentially, updating Redis at each step.
    Returns the final pipeline state dict.
    """
    pipeline_id = pipeline_id or str(uuid.uuid4())[:8]
    start_time = datetime.now()
    pipeline_dir = _get_pipeline_dir(pipeline_id)

    # Init SQLite state — create pipeline run + all stage records
    import hashlib
    doc_hash = hashlib.sha256(tender_document.encode()).hexdigest()[:16] if tender_document else None
    create_pipeline_run(
        pipeline_id=pipeline_id,
        tender_document=tender_document or "",
        params_json={
            "api_base_url": api_base_url,
            "compare_scenario_ids": compare_scenario_ids,
            "generate_pdf": generate_pdf,
        },
        tender_document_hash=doc_hash,
        api_base_url=api_base_url,
        compare_scenario_ids=compare_scenario_ids,
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
    # Stage 1 outputs — initialized here so they are always available in complete_pipeline
    analysis_report = ""
    structured = {}
    clarification_questions = []
    quality_score = {}
    field_traces = {}  # normalized fields with status/source_basis/priority/impact
    downstream_input = {}  # hints for downstream stages
    analysis_meta = {}    # v0.2 meta: {analysis_version, prompt_version, generated_at}
    analysis_sections = {}  # 13-dimension section texts
    _overrides_gate_applied = False  # set True when if-branch sets pipeline_gate from _readiness

    # ---- Stage 1: Extraction ----
    stage_start = datetime.now()
    _update_stage(pipeline_id, "1_extraction", "RUNNING")

    pipeline_gate = {"cost_model": "PASS", "solution_design": "PASS",
                    "contract_review": "PASS", "blocking_items": [], "readiness_summary": "就绪"}

    try:
        if project_profile_overrides:
            profile = project_profile_overrides
            missing_p0 = []

            # Read readiness from base_overrides (injected by retry_pipeline_stage orchestrator).
            # This tells us whether cost_model gate should PASS or BLOCK without re-running LLM extraction.
            new_readiness = profile.pop("_readiness", {}) or {}
            if new_readiness:
                readiness_score_val = new_readiness.get("readiness_score")
                pipeline_gate = {
                    "cost_model": "PASS" if new_readiness.get("for_cost_model") else "BLOCK",
                    "solution_design": "PASS" if new_readiness.get("for_solution_design") else "WARN",
                    "contract_review": "PASS" if new_readiness.get("for_contract_review") else "BLOCK",
                    "blocking_items": new_readiness.get("blocked_reasons", []) or [],
                    "readiness_score": readiness_score_val,
                    "p0_field_status": new_readiness.get("p0_field_status", {}),
                    "blocked_reasons": new_readiness.get("blocked_reasons", []),
                    "network_estimation": "PASS",
                    "kpi_gate": "PASS",
                    "kpi_warn_message": "",
                    "readiness_summary": f"readiness_score={readiness_score_val}",
                }
                # Store back so downstream can still read it
                profile["_readiness"] = new_readiness
                _overrides_gate_applied = True

            # Write a minimal stage_1 file so stage 1 shows DONE
            analysis_report = ""
            structured = {}
            quality_score = {}
            clarification_questions = []
            extraction_file = pipeline_dir / "stage_1_extraction.md"
            extraction_file.write_text(
                f"# Stage 1: Requirement Extraction (from Clarification overrides)\n\n"
                f"## Normalized Profile\n\n```json\n{json.dumps(profile, ensure_ascii=False, indent=2)}\n```\n\n"
                f"## Missing P0\n\nNone (all P0 fields resolved via Clarification)\n",
                encoding="utf-8"
            )
            _update_stage(pipeline_id, "1_extraction", "DONE",
                          output_file=str(extraction_file),
                          duration_seconds=(datetime.now() - stage_start).total_seconds(),
                          extra={
                              "quality_score": {},
                              "missing_p0": [],
                              "readiness_summary": "from Clarification overrides",
                          })

            # ---- Build downstream_input for stage 3 from Clarification overrides ----
            # profile has scalar values; build normalized_fields so cost engine can read field status.
            from backend.services.tender_schema import get_p0_fields, get_p1_fields
            p0_keys = get_p0_fields()
            p1_keys = get_p1_fields()
            p0_field_status = (new_readiness.get("p0_field_status") or {}) if new_readiness else {}
            normalized_fields = {}
            for fk, fv in profile.items():
                if fk.startswith("_"):
                    continue
                if fk in p0_keys or fk in p1_keys:
                    status = p0_field_status.get(fk) or ("provided" if fv is not None else "missing")
                    normalized_fields[fk] = {
                        "field_name": fk,
                        "value": fv,
                        "status": status,
                        "priority": "P0" if fk in p0_keys else "P1",
                        "source_section": "Clarification补录",
                        "usable": status in ("provided", "inferred", "explicit"),
                    }
            # Build analyzer_result for downstream_input_builder
            analyzer_result_for_downstream = {
                "normalized_fields": normalized_fields,
                "readiness": new_readiness or {},
                "critical_missing_items": [],
                "important_missing_items": [],
                "clarification_questions": [],
                "analysis_sections": {},
            }
            from backend.downstream.downstream_input_builder import build_cost_model_input
            downstream_input = build_cost_model_input(analyzer_result=analyzer_result_for_downstream)

            # Load recommendations — either from file (fast path) or re-run Stage 2 with new profile
            recommendations = []
            compare_ids = []
            best_id = None
            try:
                if rerun_stage2:
                    # Re-run recommendation engine with the clarified profile
                    stage2_start = datetime.now()
                    _update_stage(pipeline_id, "2_recommendation", "RUNNING")
                    try:
                        rec_result = recommend_solutions(profile, top_n=5, include_reasons=True)
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
                            f"# Stage 2: Automation Recommendations (re-run with Clarification overrides)\n\n"
                            f"Top Recommendations:\n{json.dumps(recommendations[:5], ensure_ascii=False, indent=2)}",
                            encoding="utf-8"
                        )
                        _update_stage(pipeline_id, "2_recommendation", "DONE",
                                      output_file=str(rec_file),
                                      duration_seconds=(datetime.now() - stage2_start).total_seconds(),
                                      extra={"recommendations": recommendations[:5],
                                             "best_scenario_id": best_id,
                                             "source": "rerun_with_clarification"})
                    except Exception as e2:
                        _update_stage(pipeline_id, "2_recommendation", "FAILED",
                                      error=str(e2), duration_seconds=0)
                        complete_pipeline(pipeline_id, "FAILED", error=str(e2))
                        return {"pipeline_id": pipeline_id, "status": "FAILED", "error": str(e2)}
                else:
                    # Load from original stage_2 file (no re-run)
                    rec_file = pipeline_dir / "stage_2_recommendations.md"
                    if rec_file.exists():
                        import re
                        text = rec_file.read_text(encoding="utf-8")
                        m = re.search(r"Top Recommendations:\s*(\[)", text)
                        if m:
                            json_start = text.index("[", m.start())
                            recommendations = json.loads(text[json_start:])
                            compare_ids = [r["scenario_id"] for r in recommendations[:3]] if recommendations else []
                            best_id = compare_ids[0] if compare_ids else None
                    _update_stage(pipeline_id, "2_recommendation", "DONE",
                                  output_file=str(rec_file),
                                  duration_seconds=0,
                                  extra={"recommendations": recommendations[:5] if recommendations else [],
                                         "best_scenario_id": best_id,
                                         "source": "loaded_from_original_stage2_file"})
            except Exception:
                pass  # Fall back to empty

            # Stages 1+2 are already DONE; stages 3+4+5 use corrected profile/downstream_input
            region = profile.get("region", "华东")
            cost_comparisons = []
            qa_verdict = "CONDITIONAL_PASS"
            pdf_path = None
            pdf_url = None
            stage_start = datetime.now()
            _update_stage(pipeline_id, "3_cost_comparison", "RUNNING")
            try:
                if compare_ids and len(compare_ids) >= 2:
                    scenario_list = [r for r in recommendations if r.get("scenario_id") in compare_ids]
                    cost_comparisons = compare_solution_financials(
                        profile, scenario_list, region, downstream_input=downstream_input
                    )
                elif best_id:
                    cost_result = get_cost_analysis(profile, region, best_id)
                    cost_comparisons = [cost_result.get("cost_breakdown", {})]

                cmp_file = pipeline_dir / "stage_3_cost_comparison.md"
                cmp_file.write_text(
                    f"# Stage 3: Cost Comparison (retry with Clarification overrides)\n\n"
                    f"Comparisons:\n{json.dumps(cost_comparisons, ensure_ascii=False, indent=2)}",
                    encoding="utf-8"
                )
                _update_stage(pipeline_id, "3_cost_comparison", "DONE",
                              output_file=str(cmp_file),
                              duration_seconds=(datetime.now() - stage_start).total_seconds(),
                              extra={"cost_comparisons": cost_comparisons})
            except Exception as e:
                _update_stage(pipeline_id, "3_cost_comparison", "FAILED",
                              error=str(e), duration_seconds=0)
                complete_pipeline(pipeline_id, "FAILED", error=str(e))
                return {"pipeline_id": pipeline_id, "status": "FAILED", "error": str(e)}

            # Stage 4: QA
            stage_start = datetime.now()
            _update_stage(pipeline_id, "4_qa_review", "RUNNING")
            try:
                qa_verdict, qa_issues = run_qa(profile, recommendations, tender_document, cost_comparisons)
                qa_issues_ui = format_issues_for_ui(qa_issues)
                qa_file = pipeline_dir / "stage_4_qa_report.md"
                qa_file.write_text(
                    f"# Stage 4: QA Report\n\nVerdict: {qa_verdict}\n\nIssues:\n"
                    + "\n".join(f"- [{i['severity']}] {i['field']}: {i['message']}" for i in qa_issues),
                    encoding="utf-8"
                )
                _update_stage(pipeline_id, "4_qa_review", "DONE",
                              output_file=str(qa_file),
                              duration_seconds=(datetime.now() - stage_start).total_seconds(),
                              extra={"qa_verdict": qa_verdict, "qa_issues": qa_issues, "qa_issues_ui": qa_issues_ui})
            except Exception as e:
                _update_stage(pipeline_id, "4_qa_review", "FAILED",
                              error=str(e), duration_seconds=0)
                complete_pipeline(pipeline_id, "FAILED", error=str(e))
                return {"pipeline_id": pipeline_id, "status": "FAILED", "error": str(e)}

            # Stage 5: PDF Report
            stage_start = datetime.now()
            _update_stage(pipeline_id, "5_pdf_report", "RUNNING")
            try:
                from report.generator import generate_pdf_bytes

                best_cost = next(
                    (c for c in cost_comparisons if c.get("is_best")),
                    cost_comparisons[0] if cost_comparisons else {}
                )
                cost_summary = (f"推荐方案5年ROI {best_cost.get('roi_5y', 'N/A')}x，"
                                f"回本周期 {(best_cost.get('payback_years') or 'N/A')}年")
                cost_recommendations = [
                    f"{c['scenario_name']}: ROI {(c.get('roi_5y') or 0):.1f}x"
                    for c in cost_comparisons[:3]
                ]
                fake_recommendations = [
                    {
                        "scenario_id": c["scenario_id"],
                        "scenario_name": c["scenario_name"],
                        "category": c.get("category", ""),
                        "score": (c.get("roi_5y") or 0) * 10,
                        "reason": f"5年ROI {c.get('roi_5y', 0):.1f}x，回本 {c.get('payback_years', 0):.1f}年",
                        "risk": "中",
                        "capex_range": f"¥{int((c.get('capex_estimate') or 0)/10000)}万",
                        "labor_saving": (c.get("headcount_saved") or 0) / max(c.get("headcount_required") or 1, 1),
                        "efficiency_gain": 0.4,
                    }
                    for c in cost_comparisons
                ]
                cost_data = {
                    "warehouse_cost": 0,
                    "labor_cost_annual": 0,
                    "automation_capex": best_cost.get("capex_estimate") or 0,
                    "annual_maintenance": best_cost.get("annual_maintenance") or 0,
                    "total_annual_cost": best_cost.get("total_annual_cost") or 0,
                    "automation_savings_annual": best_cost.get("net_annual_benefit") or 0,
                    "net_annual_benefit": best_cost.get("net_annual_benefit") or 0,
                    "roi": best_cost.get("roi_5y") or 0,
                    "payback_years": best_cost.get("payback_years") or 99,
                    "headcount_required": best_cost.get("headcount_required") or 0,
                    "headcount_saved": best_cost.get("headcount_saved") or 0,
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
                              error=str(e), duration_seconds=0)
                pdf_path = None
                pdf_url = None

            complete_pipeline(pipeline_id, "COMPLETE", qa_verdict=qa_verdict,
                             profile_json=dict(profile),
                             recommendations_json=recommendations[:5] if recommendations else [],
                             comparisons_json=cost_comparisons,
                             pdf_path=str(pdf_path) if pdf_path else None,
                             pdf_url=pdf_url,
                             pipeline_gate_json=pipeline_gate)
            return {"pipeline_id": pipeline_id, "status": "COMPLETE",
                    "qa_verdict": qa_verdict, "pdf_url": pdf_url}
        else:
            # Use two-phase tender understanding (analysis + normalization)
            from backend.services.tender_service import extract_requirements
            extraction_mode = os.environ.get("EXTRACTION_MODE", "analysis")
            profile = extract_requirements(tender_document, mode=extraction_mode)

            missing_p0 = profile.get("missing_p0", []) or [
                k for k, v in (profile.get("_field_traces") or {}).items()
                if isinstance(v, dict) and v.get("priority") == "P0" and v.get("status") in ("missing", "ambiguous")
            ]

            # Extract all new analysis outputs from the full result
            analysis_report = profile.pop("_analysis_report", "")
            structured = profile.pop("_structured", {})
            raw_llm = profile.pop("_raw_llm_response", "")
            clarification_questions = profile.pop("_clarification_questions", [])
            quality_score = profile.pop("_quality_score", {})
            downstream_input = profile.pop("_downstream_input", {})
            field_traces = profile.pop("_field_traces", {})
            analysis_meta = profile.pop("_meta", {})
            analysis_result = profile.pop("_analysis_result", {})
            summary = profile.pop("_summary", {})

            # analysis_sections: the 13-dimension section texts for downstream use
            analysis_sections = (
                analysis_result.get("analysis_sections") or
                profile.get("analysis_sections") or
                {}
            )

            # Re-attach analysis context to profile so downstream stages can read it
            # (services receive profile dict; we add these so they have the full picture)
            profile["_analysis_sections"] = analysis_sections
            profile["_downstream_input"] = downstream_input
            profile["_analysis_meta"] = analysis_meta

            # Pipeline Gate: read from new _readiness (v0.2) with old quality_score fallback
            # New: profile._readiness = {for_cost_model, for_solution_design, ...}
            # Old: quality_score.readiness = {cost_model_ready, ...}
            new_readiness = profile.pop("_readiness", {}) or {}
            old_readiness = (quality_score or {}).get("readiness", {}) or {}

            # Prefer new keys; fall back to old for backward compat
            gate_cost_ok = new_readiness.get("for_cost_model", old_readiness.get("cost_model_ready", False))
            gate_solution_ok = new_readiness.get("for_solution_design", old_readiness.get("solution_design_ready", False))
            gate_contract_ok = new_readiness.get("for_contract_review", old_readiness.get("contract_review_ready", False))
            readiness_summary = (
                new_readiness.get("readiness_score", 0.0) if new_readiness else
                old_readiness.get("summary", "就绪")
            )
            # blocked_reasons (new) takes priority; fall back to missing_p0 (old)
            blocked_reasons = new_readiness.get("blocked_reasons", []) or old_readiness.get("blocking_items", [])
            if not missing_p0:
                missing_p0 = blocked_reasons or []

            # Prefer new keys; fall back to old for backward compat
            gate_cost_ok = new_readiness.get("for_cost_model", old_readiness.get("cost_model_ready", False))
            gate_solution_ok = new_readiness.get("for_solution_design", old_readiness.get("solution_design_ready", False))
            gate_contract_ok = new_readiness.get("for_contract_review", old_readiness.get("contract_review_ready", False))
            readiness_summary = (
                new_readiness.get("readiness_score", 0.0) if new_readiness else
                old_readiness.get("summary", "就绪")
            )
            # blocked_reasons (new) takes priority; fall back to missing_p0 (old)
            blocked_reasons = new_readiness.get("blocked_reasons", []) or old_readiness.get("blocking_items", [])
            if not missing_p0:
                missing_p0 = blocked_reasons or []

            pipeline_gate = {
                "cost_model": "PASS" if gate_cost_ok else "BLOCK",
                "solution_design": "PASS" if gate_solution_ok else "WARN",
                "contract_review": "PASS" if gate_contract_ok else "BLOCK",
                "blocking_items": missing_p0 or [],
                "readiness_score": new_readiness.get("readiness_score") if new_readiness else None,
                "p0_field_status": new_readiness.get("p0_field_status", {}) if new_readiness else {},
                "blocked_reasons": blocked_reasons,
            }

        extraction_file = pipeline_dir / "stage_1_extraction.md"
        extraction_file.write_text(
            f"# Stage 1: Requirement Extraction\n\n"
            f"## Analysis Report\n\n{analysis_report}\n\n"
            f"## Normalized Profile\n\n```json\n{json.dumps(profile, ensure_ascii=False, indent=2)}\n```\n\n"
            f"## Structured JSON\n\n```json\n{json.dumps(structured, ensure_ascii=False, indent=2)}\n```\n\n"
            f"## Quality Score\n\n```json\n{json.dumps(quality_score, ensure_ascii=False, indent=2)}\n```\n\n"
            f"## Clarification Questions\n\n" + "\n".join(
                f"- [{q.get('severity','?')}] {q.get('question','')}" 
                for q in (clarification_questions or [])
            ) + "\n\n"
            f"## Missing P0 (Blocking)\n\n" + ("\n".join(f"- {x}" for x in (missing_p0 or [])) or "None"),
            encoding="utf-8"
        )
        _update_stage(pipeline_id, "1_extraction", "DONE",
                      output_file=str(extraction_file),
                      duration_seconds=(datetime.now() - stage_start).total_seconds(),
                      extra={
                          "quality_score": quality_score,
                          "missing_p0": missing_p0 or [],
                          "readiness_summary": (quality_score.get("readiness", {}) or {}).get("summary", ""),
                      })

        # ---- Pipeline Gate: check if ready for downstream stages ----
        # Skip if already set by the if-branch (retry path with Clarification overrides)
        if not _overrides_gate_applied:
            # Max's suggestion #3: richer gate logic with specific blocking rules
            #   • P0 missing → BLOCK cost_model + network estimation
            #   • KPI/SLA missing → WARN solution_design (保守表述)
            #   • dc_count / warehouse_area missing → BLOCK network cost estimation
            readiness = (quality_score or {}).get("readiness", {}) or profile.get("readiness") or profile.get("_readiness") or {}
            gate_cost_ok = readiness.get("for_cost_model", False)
            gate_solution_ok = readiness.get("for_solution_design", False)
            gate_contract_ok = readiness.get("for_contract_review", False)

            # Deep-dive gate: determine cost_model mode based on P0 field completeness
            # PASS: all 4 core P0 fields are explicit/inferred
            # RANGE: critical fields (dc_count, warehouse_area) present but secondary missing
            # BLOCK: at least one critical field is missing/ambiguous
            p0_core_blocking = []  # critical P0: dc_count, warehouse_area
            p0_secondary_missing = []  # secondary P0: daily_orders, sku_count
            # Use field_traces (normalized_fields with status) not profile (raw scalars)
            _traces = field_traces or {}
            if isinstance(profile, dict):
                for field, key in [("dc_count", "dc_count"), ("warehouse_area", "warehouse_area"),
                                    ("daily_orders", "daily_orders"), ("sku_count", "sku_count")]:
                    entry = _traces.get(key, {})
                    status = entry.get("status", "missing") if isinstance(entry, dict) else "missing"
                    if status in ("missing", "ambiguous"):
                        if field in ("dc_count", "warehouse_area"):
                            p0_core_blocking.append(key)
                        else:
                            p0_secondary_missing.append(key)

            if p0_core_blocking:
                cost_model_mode = "BLOCK"
            elif p0_secondary_missing:
                cost_model_mode = "RANGE"  # secondary missing → range estimate
            else:
                cost_model_mode = "PASS"   # all P0 present → full calculation

            # KPI gate: warn but allow progression
            kpi_entry = _traces.get("kpi_targets", {})
            kpi_status = kpi_entry.get("status", "missing") if isinstance(kpi_entry, dict) else "missing"
            kpi_gate = "WARN" if kpi_status in ("missing",) else "PASS"
            kpi_warn_message = ""
            if kpi_gate == "WARN":
                kpi_warn_message = "KPI/SLA缺失，方案设计阶段服务承诺须保守表述，建议在澄清后补充"

            # Store gate results for downstream reference
            pipeline_gate = {
                "cost_model": cost_model_mode,
                "solution_design": "PASS" if gate_solution_ok else "WARN",
                "contract_review": "PASS" if gate_contract_ok else "BLOCK",
                "kpi_gate": kpi_gate,
                "blocking_items": p0_core_blocking or p0_secondary_missing or [],
                "core_blocking_fields": p0_core_blocking,
                "secondary_missing_fields": p0_secondary_missing,
                "readiness_summary": readiness.get("summary", ""),
                "kpi_warn_message": kpi_warn_message,
            }
    except PipelineCancelled:
        _update_stage(pipeline_id, "1_extraction", "CANCELLED",
                      duration_seconds=(datetime.now() - stage_start).total_seconds())
        complete_pipeline(pipeline_id, "CANCELLED")
        return {"pipeline_id": pipeline_id, "status": "CANCELLED"}
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
        # Use new recommendation service (includes reasons, match_level, normalized input)
        rec_result = recommend_solutions(profile, top_n=5, include_reasons=True)
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
    except PipelineCancelled:
        _update_stage(pipeline_id, "2_recommendation", "CANCELLED",
                      duration_seconds=(datetime.now() - stage_start).total_seconds())
        complete_pipeline(pipeline_id, "CANCELLED")
        return {"pipeline_id": pipeline_id, "status": "CANCELLED"}

    # ---- Cost Model Gate: Block/RANGE/PASS based on P0 field completeness ----
    cost_mode = pipeline_gate.get("cost_model")
    if cost_mode == "BLOCK":
        blocking_fields = pipeline_gate.get("blocking_items", missing_p0 or [])
        core_blocking = pipeline_gate.get("core_blocking_fields", [])
        secondary_missing = pipeline_gate.get("secondary_missing_fields", [])
        if core_blocking:
            gate_detail = (
                f"无法进入成本测算，原因：关键P0字段缺失 {core_blocking}。"
                f"请在澄清后补充。"
            )
        else:
            gate_detail = (
                f"可进入成本测算（区间估算模式），原因：{', '.join(secondary_missing)} 字段缺失。"
                f"系统将输出best/base/worst三档估算。"
            )
        _update_stage(pipeline_id, "3_cost_comparison", "BLOCKED",
                      error=gate_detail,
                      duration_seconds=0,
                      extra={
                          "gate": "cost_model",
                          "blocking_fields": core_blocking,
                          "secondary_missing_fields": secondary_missing,
                          "kpi_warn": pipeline_gate.get("kpi_warn_message", ""),
                          "gate_detail": gate_detail,
                      })
        cost_comparisons = []
        best_id = None
        qa_verdict = "GATE_BLOCKED"
        _update_stage(pipeline_id, "4_qa_review", "SKIPPED",
                      error="Skipped due to cost_model gate BLOCK")
        _update_stage(pipeline_id, "5_pdf_report", "SKIPPED",
                      error="Skipped due to cost_model gate BLOCK")
        total_duration = (datetime.now() - start_time).total_seconds()
        p0_summary = readiness.get("p0_field_status", {}) if isinstance(readiness, dict) else {}
        p0_provided = sum(1 for v in p0_summary.values() if v in ("explicit", "inferred"))
        result_summary = {
            "industry": profile.get("industry") if isinstance(profile, dict) else "—",
            "region": profile.get("region") if isinstance(profile, dict) else "—",
            "confidence": 0.0,
            "verdict": "GATE_BLOCKED",
            "best_scenario": "—",
            "roi_5y": None,
            "payback_years": None,
            "capex_estimate": None,
            "calculation_mode": "blocked",
            "gate_blocked_reason": gate_detail,
            "blocking_items": core_blocking or blocking_fields,
            "kpi_warn": pipeline_gate.get("kpi_warn_message", ""),
            "downstream_input_meta": {
                "recommended_mode": "blocked",
                "mode_reason": gate_detail[:120],
                "level": "blocked",
                "p0_summary": {"total": len(p0_summary), "provided": p0_provided, "missing": len(core_blocking), "ambiguous": 0},
                "p1_summary": {"total": 0, "provided": 0, "missing": len(secondary_missing), "ambiguous": 0},
                "blocking_reasons": core_blocking,
                "clarification_questions_count": 0,
            },
        }
        complete_pipeline(
            pipeline_id=pipeline_id,
            status="COMPLETE",
            profile_json=dict(profile) if isinstance(profile, dict) else {},
            recommendations_json=recommendations[:5] if recommendations else [],
            comparisons_json=[],
            qa_verdict="GATE_BLOCKED",
            pipeline_gate_json=pipeline_gate,
            total_duration_seconds=total_duration,
            result_summary=result_summary,
            # Stage 1: Tender Understanding v0.2 — store all analysis even if gate blocked
            analysis_markdown=analysis_report,
            analysis_sections_json=analysis_sections,
            normalized_fields_json=field_traces,
            missing_items_json={"p0": missing_p0 or [], "p1": [k for k, v in (field_traces or {}).items() if isinstance(v, dict) and v.get("priority") == "P1" and v.get("status") in ("missing", "ambiguous")]},
            clarification_questions_json=clarification_questions or [],
            quality_score_json=quality_score or {},
            readiness_json=profile.get("readiness") or profile.get("_readiness") or {},
            analysis_version="v0.2",
            prompt_version="tender_understanding_v0.2",
            model_name="MiniMax-M2.7-highspeed",
        )
        return {
            "pipeline_id": pipeline_id,
            "status": "COMPLETE",
            "project_profile": dict(profile) if isinstance(profile, dict) else {},
            "recommendations": recommendations[:5] if recommendations else [],
            "cost_comparisons": [],
            "qa_verdict": "GATE_BLOCKED",
            "gate": pipeline_gate,
            "gate_detail": gate_detail,
            "total_duration_seconds": total_duration,
        }

    elif cost_mode == "RANGE":
        # Proceed to stage 3 but flag downstream to use range_estimate mode
        blocking_fields = pipeline_gate.get("secondary_missing_fields", [])
        gate_detail = (
            f"进入成本测算（区间估算模式）：{', '.join(blocking_fields)} 字段缺失。"
            f"系统将输出best/base/worst三档估算，供决策参考。"
        )
        # Inject range_estimate mode into downstream_input so cost service knows
        if isinstance(profile, dict):
            profile["recommended_mode"] = "range_estimate"
            profile["_range_blocked_fields"] = blocking_fields
        print(f"[pipeline] cost_model gate RANGE — {gate_detail}")

    # ---- Stage 3: Cost Comparison ----
    stage_start = datetime.now()
    _update_stage(pipeline_id, "3_cost_comparison", "RUNNING")
    try:
        # Build cost_model_input from analyzer result — this is the ONLY way
        # Cost Model Agent reads from downstream_input; bypass = silent fabrication
        cost_model_input = None
        try:
            from backend.downstream.downstream_input_builder import build_cost_model_input
            cost_model_input = build_cost_model_input(profile)
            # Override mode if pipeline gate set RANGE (allow range_estimate even if builder says blocked)
            if cost_mode == "RANGE" and cost_model_input:
                cost_model_input["recommended_mode"] = "range_estimate"
                cost_model_input["mode_reason"] = (
                    f"Pipeline gate允许区间估算模式：{pipeline_gate.get('secondary_missing_fields', [])} 缺失。"
                    f"系统将输出best/base/worst三档估算。"
                )
        except Exception:
            pass  # Fall back to legacy calculation without downstream_input

        if len(compare_ids) >= 2:
            # Use new cost service for batch comparison (with downstream_input for gating)
            scenario_list = [r for r in recommendations if r.get("scenario_id") in compare_ids]
            cost_comparisons = compare_solution_financials(
                profile, scenario_list, region, downstream_input=cost_model_input
            )
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
        qa_verdict, qa_issues = run_qa(profile, recommendations, tender_document, cost_comparisons)
        qa_issues_ui = format_issues_for_ui(qa_issues)

        qa_file = pipeline_dir / "stage_4_qa_report.md"
        qa_file.write_text(
            f"# Stage 4: QA Report\n\nVerdict: {qa_verdict}\n\nIssues:\n"
            + "\n".join(f"- [{i['severity']}] {i['field']}: {i['message']}" for i in qa_issues),
            encoding="utf-8"
        )
        _update_stage(pipeline_id, "4_qa_review", "DONE",
                      output_file=str(qa_file),
                      duration_seconds=(datetime.now() - stage_start).total_seconds(),
                      extra={"qa_verdict": qa_verdict, "qa_issues": qa_issues, "qa_issues_ui": qa_issues_ui})
    except Exception as e:
        _update_stage(pipeline_id, "4_qa_review", "FAILED",
                      error=str(e),
                      duration_seconds=(datetime.now() - stage_start).total_seconds())
        complete_pipeline(pipeline_id, "FAILED", error=str(e))
        return {"pipeline_id": pipeline_id, "status": "FAILED", "error": str(e)}
    except PipelineCancelled:
        _update_stage(pipeline_id, "4_qa_review", "CANCELLED",
                      duration_seconds=(datetime.now() - stage_start).total_seconds())
        complete_pipeline(pipeline_id, "CANCELLED")
        return {"pipeline_id": pipeline_id, "status": "CANCELLED"}

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
                            f"回本周期 {(best_cost.get('payback_years') or 'N/A')}年")
            cost_recommendations = [
                f"{c['scenario_name']}: ROI {(c.get('roi_5y') or 0):.1f}x"
                for c in cost_comparisons[:3]
            ]

            fake_recommendations = [
                {
                    "scenario_id": c["scenario_id"],
                    "scenario_name": c["scenario_name"],
                    "category": c.get("category", ""),
                    "score": (c.get("roi_5y") or 0) * 10,
                    "reason": f"5年ROI {c.get('roi_5y') or 0:.1f}x，回本 {c.get('payback_years') or 0:.1f}年",
                    "risk": "中",
                    "capex_range": f"¥{int((c.get('capex_estimate') or 0)/10000)}万",
                    "labor_saving": (c.get("headcount_saved") or 0) / max(c.get("headcount_required") or 1, 1),
                    "efficiency_gain": 0.4,
                }
                for c in cost_comparisons
            ]

            cost_data = {
                "warehouse_cost": 0,
                "labor_cost_annual": 0,
                "automation_capex": best_cost.get("capex_estimate") or 0,
                "annual_maintenance": best_cost.get("annual_maintenance") or 0,
                "total_annual_cost": best_cost.get("total_annual_cost") or 0,
                "automation_savings_annual": best_cost.get("net_annual_benefit") or 0,
                "net_annual_benefit": best_cost.get("net_annual_benefit") or 0,
                "roi": best_cost.get("roi_5y") or 0,
                "payback_years": best_cost.get("payback_years") or 99,
                "headcount_required": best_cost.get("headcount_required") or 0,
                "headcount_saved": best_cost.get("headcount_saved") or 0,
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
    best_cost = next((c for c in cost_comparisons if c.get("is_best")), cost_comparisons[0] if cost_comparisons else {})

    # Build downstream_input_meta from cost_model_input for frontend display
    downstream_meta_for_summary = {}
    if cost_model_input:
        dm = cost_model_input.get("readiness", {})
        downstream_meta_for_summary = {
            "recommended_mode": cost_model_input.get("recommended_mode", "unknown"),
            "mode_reason": cost_model_input.get("mode_reason", ""),
            "level": dm.get("level", "unknown"),
            "cost_model_ready": dm.get("cost_model_ready", False),
            "p0_summary": cost_model_input.get("p0_summary", {}),
            "p1_summary": cost_model_input.get("p1_summary", {}),
            "blocking_reasons": cost_model_input.get("blocking_reasons", []),
            "clarification_questions_count": len(cost_model_input.get("clarification_questions", [])),
        }

    result_summary = {
        "industry": profile.get("industry", "—"),
        "region": region,
        "confidence": profile.get("extraction_confidence") or 0.0,
        "verdict": qa_verdict,
        "best_scenario": best_cost.get("scenario_name", "—") if best_cost else "—",
        "roi_5y": best_cost.get("roi_5y") if best_cost else None,
        "payback_years": best_cost.get("payback_years") if best_cost else None,
        "capex_estimate": best_cost.get("capex_estimate") if best_cost else None,
        "calculation_mode": best_cost.get("calculation_mode") if best_cost else None,
        "input_source": best_cost.get("input_source", {}) if best_cost else {},
        "assumptions_used": best_cost.get("assumptions_used", []) if best_cost else [],
        "downstream_input_meta": downstream_meta_for_summary,
    }
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
        result_summary=result_summary,
        # Stage 1: Tender Understanding v0.2
        analysis_markdown=analysis_report,
        analysis_sections_json=analysis_sections,
        normalized_fields_json=field_traces,
        missing_items_json={
            "p0": missing_p0 or [],
            "p1": [k for k, v in (field_traces or {}).items() if isinstance(v, dict) and v.get("priority") == "P1" and v.get("status") in ("missing", "ambiguous")],
        },
        clarification_questions_json=clarification_questions or [],
        quality_score_json=quality_score or {},
        readiness_json=profile.get("readiness") or profile.get("_readiness") or {},
        pipeline_gate_json=pipeline_gate,
        analysis_version="v0.2",
        prompt_version="tender_understanding_v0.2",
        model_name="MiniMax-M2.7-highspeed",
    )

    return {
        "pipeline_id": pipeline_id,
        "status": "COMPLETE",
        "project_profile": profile,
        "recommendations": recommendations[:5],
        "cost_comparisons": cost_comparisons,
        "best_scenario_id": best_id,
        "qa_verdict": qa_verdict,
        "gate": pipeline_gate,
        "analysis_meta": analysis_meta,
        # v0.2: Cost Model downstream input (for frontend readiness card)
        "downstream_input": cost_model_input,
        "downstream_input_meta": downstream_meta_for_summary,
        "required_inputs": (cost_model_input.get("required_inputs", {})
                            if cost_model_input else {}),
        "unusable_fields": (cost_model_input.get("unusable_fields", [])
                            if cost_model_input else []),
        "clarification_questions": (cost_model_input.get("clarification_questions", [])
                                  if cost_model_input else []),
        "pdf_path": str(pdf_path) if pdf_path else None,
        "pdf_download_url": pdf_url,
        "total_duration_seconds": total_duration,
    }
