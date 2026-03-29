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
from starlette.responses import Response

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

@router.get("/base/{pipeline_id}/markdown")
def get_base_solution_markdown(pipeline_id: str, db: Session = Depends(get_db)):
    """
    Export the base solution as formatted Markdown.
    Useful for sharing, printing, or further document generation.
    """
    run = db.query(PipelineRun).filter_by(pipeline_id=pipeline_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Pipeline not found: {pipeline_id}")
    if not run.base_solution_json:
        raise HTTPException(status_code=404, detail="No base solution found for this pipeline")

    try:
        sol = json.loads(run.base_solution_json)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=500, detail="Failed to parse stored solution")

    ns = sol.get("narrative_sections", {})
    pf = sol.get("project_fit", {})
    sd = sol.get("service_design", {})
    od = sol.get("organization_design", {})
    pd = sol.get("process_design", {})
    kf = sol.get("kpi_framework", {})
    impl = sol.get("implementation_focus", {})
    rc = sol.get("risk_and_controls", {})
    cml = sol.get("cost_model_linkage", {})

    OP_TYPE_LABELS = {
        "warehouse_distribution": "仓配一体化", "cold_chain": "冷链仓储",
        "bonded_warehouse_distribution": "保税仓配", "distribution_only": "纯配送",
        "warehouse_inbound_only": "仓储入库", "warehouse_outbound_only": "仓储出库",
        "value_added_services": "增值服务", "custom": "综合物流", "unknown": "待定",
    }
    COST_MODE_LABELS = {"blocked": "🔴 阻塞", "range_estimate": "🟡 区间估算", "full_calc": "🟢 完整测算", "unknown": "❓ 未知"}
    sev_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}

    lines = [
        f"# 🧩 基础仓配运营方案",
        f"",
        f"**方案ID：** {sol.get('solution_id','')}",
        f"**生成时间：** {sol.get('generated_at','')[:10]}",
        f"**运营类型：** {OP_TYPE_LABELS.get(pf.get('operation_type',''), pf.get('operation_type',''))}",
        f"**复杂度：** {pf.get('complexity_level','')} ({pf.get('complexity_score',0)}/20)",
        f"**成本模式：** {COST_MODE_LABELS.get(cml.get('current_mode',''), cml.get('current_mode',''))}",
        f"",
        f"---",
        f"",
        f"## 📋 方案摘要",
        f"",
        f"{ns.get('executive_summary', sol.get('summary',''))}",
        f"",
    ]

    # Service Design
    if sd.get("included_services"):
        lines += ["---", "", "## 📦 服务范围设计", ""]
        svc_by_cat = {}
        for svc in sd.get("included_services", []):
            svc_by_cat.setdefault(svc.get("category", ""), []).append(svc.get("label", ""))
        CAT_EMOJI = {"inbound": "📥", "storage": "📦", "outbound": "📤", "value_added": "🔧", "support": "⚙️"}
        for cat, svcs in svc_by_cat.items():
            emoji = CAT_EMOJI.get(cat, "📌")
            lines.append(f"### {emoji} {cat.upper()}")
            for s in svcs:
                lines.append(f"- {s}")
            lines.append("")
        if sd.get("excluded_or_unconfirmed"):
            lines += ["**⚠️ 未纳入/未确认服务：**", ""]
            for s in sd.get("excluded_or_unconfirmed", [])[:10]:
                lines.append(f"- {s}")
            lines.append("")

    # Organization Design
    if od.get("team_modules"):
        lines += ["---", "", "## 🧑‍🤝‍🧑 组织模块设计", ""]
        for tm in od.get("team_modules", []):
            lines.append(f"### ✅ {tm.get('label', tm.get('module_key',''))}")
            for r in tm.get("primary_responsibilities", [])[:3]:
                lines.append(f"- {r}")
            lines.append("")

    # Process Design
    if pd.get("processes"):
        PROC_EMOJI = {
            "receiving_process": "📥", "outbound_process": "📤",
            "storage_management": "📦", "return_process": "↩️",
            "va_process": "🔧", "temperature_control": "❄️",
            "support_process": "⚙️",
        }
        lines += ["---", "", "## 🔄 核心流程设计", ""]
        for proc in pd.get("processes", []):
            emoji = PROC_EMOJI.get(proc.get("process_key", ""), "📌")
            lines.append(f"### {emoji} {proc.get('label', proc.get('process_key',''))} — {proc.get('step_count',0)}步")
            if proc.get("description"):
                lines.append(f"_{proc.get('description')}_")
            for step in proc.get("steps", [])[:8]:
                lines.append(f"- `{step.get('step_id','')}` {step.get('label','—')} → {step.get('role','—')}")
            if len(proc.get("steps", [])) > 8:
                lines.append(f"_...共{proc.get('step_count',0)}步_")
            lines.append("")

    # KPI Framework
    kpi_groups = [
        ("📥 入库KPI", kf.get("inbound_kpis", [])),
        ("📤 出库KPI", kf.get("outbound_kpis", [])),
        ("📦 库内KPI", kf.get("inventory_kpis", [])),
        ("⚙️ 支持KPI", kf.get("support_kpis", [])),
    ]
    has_kpis = any(v for _, v in kpi_groups)
    if has_kpis:
        lines += ["---", "", "## 📊 KPI 框架", ""]
        for gname, kpis in kpi_groups:
            if kpis:
                lines.append(f"### {gname}")
                for kpi in kpis:
                    sla = " 🏆" if kpi.get("is_sla_candidate") else ""
                    lines.append(f"- `{kpi.get('name','—')}` = {kpi.get('target','—')}{sla}")
                lines.append("")

    # Implementation
    if impl.get("phases"):
        lines += ["---", "", "## 🚀 实施阶段", ""]
        for ph in impl.get("phases", []):
            lines.append(f"### {ph.get('phase','Phase')} — {ph.get('name','—')} (~{ph.get('duration_months',0)}个月)")
            lines.append(f"*{ph.get('focus','—')}*")
            for a in ph.get("key_actions", [])[:5]:
                lines.append(f"- {a}")
            lines.append("")

    # Risk
    if rc.get("risks"):
        lines += ["---", "", "## ⚠️ 风险与控制", ""]
        for rk in rc.get("risks", []):
            emoji = sev_emoji.get(rk.get("severity", ""), "⚪")
            lines.append(f"### {emoji} {rk.get('risk_id','R-?')} — {rk.get('description','—')[:50]}")
            lines.append(f"- **类别：** {rk.get('category','—')}")
            lines.append(f"- **控制措施：** {rk.get('control_measure','—')}")
            lines.append(f"- **缓解动作：** {rk.get('mitigation_action','—')}")
            lines.append("")

    # Cost Model Linkage
    if cml.get("current_mode"):
        lines += ["---", "", "## 💰 成本测算衔接", ""]
        lines.append(f"**当前模式：** {cml.get('mode_explanation','')}")
        if cml.get("missing_for_full_calc"):
            lines.append("")
            lines.append("**进入完整测算还需：**")
            for m in cml.get("missing_for_full_calc", []):
                lines.append(f"- {m}")
        if cml.get("assumptions_used"):
            lines.append("")
            lines.append(f"**当前假设项：** {len(cml.get('assumptions_used',[]))}项")
        if cml.get("narrative"):
            lines.append("")
            lines.append(f"_{cml.get('narrative')}_")

    lines += ["", "---", "", f"_由 Logistics Smart Solution v0.7 自动生成 | {sol.get('generated_at','')[:10]}_"]
    return Response(content="\n".join(lines), media_type="text/markdown; charset=utf-8")


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
