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

    # Load resolved_fields and convert to simple project_state dict
    resolved_fields = {}
    project_state = {}
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
            # Build project_state for generate_base_solution()
            for k, rf in resolved_fields.items():
                if rf.final_value is not None:
                    project_state[k] = rf.final_value
                elif rf.usable is not False and rf.usable is not None:
                    project_state[k] = rf.usable
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
        project_state,
        project_id=pipeline_id,
        narrative=True,
    )

    # Persist to PipelineRun
    run.base_solution_json = json.dumps(serialize_solution(solution), ensure_ascii=False)
    db.commit()

    return SolutionResponse(
        pipeline_id=pipeline_id,
        solution_id=solution.solution_id,
        title=getattr(solution.operation_mode, "label", "基础运营方案"),
        summary=solution.narrative[:200] if solution.narrative else "",
        current_cost_mode=getattr(solution.confidence, "value", "unknown"),
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
    Reads new BaseSolution schema (v0.8+).
    """
    run = db.query(PipelineRun).filter_by(pipeline_id=pipeline_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    if not run.base_solution_json:
        raise HTTPException(status_code=404, detail="No base solution found for this pipeline")

    try:
        sol = json.loads(run.base_solution_json)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=500, detail="Failed to parse stored solution")

    lines: list[str] = []
    gen_ver = sol.get("generator_version", "v0.8")

    # ── Header ────────────────────────────────────────────────────────────────
    lines += [
        f"# 🧩 基础仓配运营方案",
        f"",
        f"**方案ID：** {sol.get('solution_id', '')}",
        f"**生成时间：** {sol.get('generated_at', '')[:10]}",
        f"**生成器版本：** {gen_ver}",
        "",
    ]

    # ── §1 方案摘要 ──────────────────────────────────────────────────────────
    narrative = sol.get("narrative", "")
    exec_summary = _extract_md_section(narrative, "方案概述")
    if exec_summary:
        lines += ["---", "", "## 📋 方案摘要", "", exec_summary, ""]

    # ── §2 项目画像与运营模式 ────────────────────────────────────────────────
    om = sol.get("operation_mode", {})
    if om:
        scale_tier = om.get("scale_tier", "m")
        tier_display = {
            "xs": "超小规模（<1,000㎡）", "s": "小规模（1,000-5,000㎡）",
            "m": "中等规模（5,000-20,000㎡）", "l": "大规模（20,000-50,000㎡）",
            "xl": "超大规模（>50,000㎡）"
        }.get(scale_tier, f"规模等级 {scale_tier.upper()}")

        lines += [
            "---", "", "## 🏢 项目画像与运营模式", "",
            f"### {om.get('label', om.get('mode_name', '基础运营模式'))}", "",
            om.get("description", "") or "本项目采用该运营模式作为核心框架。",
        ]
        if om.get("applicable_conditions"):
            lines.append("")
            lines.append("**适用条件：**")
            for c in om["applicable_conditions"]:
                lines.append(f"- {c}")
        if om.get("core_activities"):
            lines.append("")
            lines.append("**核心作业活动：**")
            for a in om["core_activities"][:10]:
                lines.append(f"- {a}")
            if len(om["core_activities"]) > 10:
                lines.append(f"- _...还有其他 {len(om['core_activities']) - 10} 项_")
        lines += [
            "",
            f"**仓储规模：** {tier_display}",
            f"**区域成本指数：** {om.get('region_cost_index', 1.0):.2f}（华东 = 1.00）",
            f"**行业附加系数：** {om.get('industry_overhead_factor', 1.0):.2f}",
        ]

    # ── §3 服务范围 ─────────────────────────────────────────────────────────
    pd = sol.get("process_design", {})
    sb = sol.get("system_boundary", {})
    if pd:
        stages = pd.get("stages", [])
        enabled_cats: dict[str, list] = {}
        CAT_EMOJI = {
            "inbound": "📥", "inbound_receiving": "📥", "inbound_quality_check": "📥",
            "inbound_putaway": "📥", "outbound": "📤", "outbound_picking": "📤",
            "outbound_packing": "📤", "outbound_labeling": "📤", "outbound_loading": "📤",
            "storage": "📦", "storage_management": "📦",
            "value_added": "🔧", "value_added_service": "🔧",
            "support": "⚙️", "inventory_reporting": "⚙️",
        }
        for stage in stages:
            if stage.get("enabled"):
                key = stage.get("stage_key", "unknown")
                cat = key.split("_")[0]
                if cat not in enabled_cats:
                    enabled_cats[cat] = []
                label = stage.get("stage_name", key)
                if label not in enabled_cats[cat]:
                    enabled_cats[cat].append(label)

        if enabled_cats or sb.get("included") or sb.get("excluded"):
            lines += ["---", "", "## 📦 服务范围", ""]
            for cat, names in enabled_cats.items():
                emoji = CAT_EMOJI.get(cat, "📌")
                lines.append(f"- **{emoji} {'/'.join(names)}**")
            if sb.get("included"):
                lines.append("")
                lines.append("**系统边界（方案范围内）：**")
                for inc in sb["included"]:
                    lines.append(f"  + {inc}")
            if sb.get("excluded"):
                lines.append("")
                lines.append("**系统边界（明确排除）：**")
                for exc in sb["excluded"]:
                    lines.append(f"  - ~~{exc}~~")
            if sb.get("integration_points"):
                for pt in sb["integration_points"]:
                    lines.append(f"  → {pt}")

    # ── §4 核心流程设计 ──────────────────────────────────────────────────────
    if pd:
        enabled_stages = [s for s in pd.get("stages", []) if s.get("enabled")]
        if enabled_stages:
            lines += [
                "---", "", "## 🔄 核心流程设计", "",
                f"**整体流程：** {pd.get('flow_diagram_label', '—')}", ""
            ]
            for stage in enabled_stages:
                sla_str = f"（SLA: {stage['sla']}）" if stage.get("sla") else ""
                lines.append(f"### 📌 {stage.get('stage_name', '')} {sla_str}")
                for act in (stage.get("activities") or [])[:6]:
                    lines.append(f"- {act}")
                if stage.get("handoff"):
                    lines.append(f"**交接：** {stage['handoff']}")
                if stage.get("kpis"):
                    lines.append(f"**KPI：** {' / '.join(stage['kpis'])}")
                lines.append("")

    # ── §5 基础人力模型 ─────────────────────────────────────────────────────
    lm = sol.get("labor_model", {})
    if lm:
        ROLE_DISPLAY = {
            "receiving_team": "收货团队", "picking_team": "拣选团队",
            "loading_team": "装车团队", "support_team": "支持团队",
            "va_team": "增值加工团队", "qc_team": "质检团队",
            "return_team": "退货处理团队", "it_support": "IT 支持",
        }
        lines += [
            "---", "", "## 👷 基础人力模型", "",
            f"**班次结构：** {lm.get('shift_structure', '—')}",
            f"**日运营时长：** {lm.get('working_hours_per_day', 0):.0f} 小时", ""
        ]
        lines.append("**岗位配置：**")
        for role, count in sorted(lm.get("headcount_by_role", {}).items(), key=lambda x: -x[1]):
            if count > 0:
                lines.append(f"- {ROLE_DISPLAY.get(role, role)}：{count} 人")
        lines += [
            "",
            f"**单人月均成本：** ¥{lm.get('labor_cost_per_person_month', 0):,.0f} 元/月",
            f"**月均人工总成本：** ¥{lm.get('labor_cost_per_month', 0):,.0f} 元/月",
            f"**年人工成本：** ¥{lm.get('annual_labor_cost', 0):,.0f} 元/年",
            f"**区域调整系数：** {lm.get('labor_cost_adjustment_factor', 1.0):.2f}",
        ]

    # ── §6 KPI / SLA 框架 ──────────────────────────────────────────────────
    kf = sol.get("kpi_framework", {})
    if kf:
        kpis = kf.get("operational_kpis", [])
        if kpis:
            lines += [
                "---", "", "## 📊 KPI / SLA 框架", "",
                f"**测量频率：** {kf.get('measurement_frequency', '—')}", ""
            ]
            for kpi in kpis:
                sla_flag = " 🏆 SLA" if kpi.get("is_sla_candidate") else ""
                conf_flag = " 📝 合同承诺" if kpi.get("is_contractual") else ""
                target = kpi.get("target", "—")
                unit = kpi.get("unit", "")
                name = kpi.get("name", kpi.get("kpi_key", "—"))
                method = kpi.get("measurement_method", "")
                lines.append(f"- **{name}**：{target} {unit}{sla_flag}{conf_flag}")
                if method:
                    lines.append(f"  _测量方式：{method}_")
            lines.append("")

    # ── §7 风险档案 ─────────────────────────────────────────────────────────
    rp = sol.get("risk_profile", {})
    if rp:
        risks = rp.get("risks", [])
        if risks:
            lines += ["---", "", "## ⚠️ 风险档案", ""]
            SEV_EMOJI = {"high": "🔴", "medium": "🟡", "low": "🟢"}
            SEV_LABEL = {"high": "高风险", "medium": "中风险", "low": "低风险"}
            for risk in risks:
                emoji = SEV_EMOJI.get(risk.get("severity", ""), "⚪")
                sev_lbl = SEV_LABEL.get(risk.get("severity", ""), risk.get("severity", ""))
                lines.append(f"### {emoji} {risk.get('risk_id', 'R-?')} — {sev_lbl}")
                lines.append(f"**描述：** {risk.get('description', '—')}")
                lines.append(f"**类别：** {risk.get('category', '—')}")
                if risk.get("mitigation"):
                    lines.append("**缓解措施：**")
                    for m in risk["mitigation"]:
                        lines.append(f"  - {m}")
                lines.append("")

    # ── §8 实施策略 ─────────────────────────────────────────────────────────
    impl = sol.get("implementation_strategy", {})
    if impl:
        phases = impl.get("phases", [])
        if phases:
            lines += [
                "---", "", "## 🚀 实施策略", "",
                f"**实施周期：** {impl.get('timeline_months', 0)} 个月（"
                f"复杂度：{impl.get('complexity', 'unknown')}）", ""
            ]
            if impl.get("go_live_target"):
                lines.append(f"**目标上线日期：** {impl['go_live_target']}")
                lines.append("")
            for ph in phases:
                lines.append(
                    f"### ⏱ {ph.get('phase', 'Phase')} — {ph.get('name', '—')} "
                    f"（{ph.get('duration_months', 0)} 个月）"
                )
                lines.append(f"**重点：** {ph.get('focus', '—')}")
                if ph.get("key_actions"):
                    for a in ph["key_actions"][:6]:
                        lines.append(f"- {a}")
                if ph.get("gate_criteria"):
                    lines.append("**门禁条件：**")
                    for g in ph["gate_criteria"]:
                        lines.append(f"  - {g}")
                lines.append("")

    # ── §9 输入完整度说明 ───────────────────────────────────────────────────
    defaulted_p2 = sol.get("defaulted_p2_fields", [])
    missing_p0 = sol.get("missing_p0_fields", [])
    confidence = sol.get("confidence", "unknown")
    CONF_EMOJI = {"high": "🟢", "medium": "🟡", "low": "🔴", "unknown": "⚪"}
    CONF_LABEL = {"high": "高置信", "medium": "中置信（保守表述）", "low": "低置信（阻塞风险）", "unknown": "未评估"}
    conf_emoji = CONF_EMOJI.get(confidence, "⚪")
    conf_label = CONF_LABEL.get(confidence, confidence)

    if defaulted_p2 or missing_p0 or confidence != "high":
        lines += ["---", "", "## 🔍 输入完整度说明", "",
                  f"**方案置信度：** {conf_emoji} {conf_label}", ""]
        if defaulted_p2:
            lines.append("**使用了默认值的字段（建议通过 Clarification Workspace 确认真实值）：**")
            for f in defaulted_p2:
                lines.append(f"- ⚠️ `{f}`")
            lines.append("")
            lines.append(
                "_默认值字段可能导致方案与客户实际情况有偏差。"
                "建议通过 Clarification Workspace 补录以提升方案精度。_"
            )
        elif missing_p0:
            lines.append("**缺失 P0 字段（阻断正式测算）：**")
            for f in missing_p0:
                lines.append(f"- 🔴 `{f}`")
            lines.append("")
            lines.append("_请通过 Clarification Workspace 补录缺失字段后再生成正式方案。_")
        else:
            lines.append("✅ 所有核心字段均已提供，方案置信度高。")
        lines.append("")

    # ── Footer ────────────────────────────────────────────────────────────────
    lines += ["", "---", "",
              f"_由 Logistics Smart Solution {gen_ver} 自动生成 | {sol.get('generated_at', '')[:10]}_"]
    return Response(content="\n".join(lines), media_type="text/markdown; charset=utf-8")


def _extract_md_section(narrative: str, section_heading: str) -> str:
    """Extract content under a markdown heading from a narrative string."""
    if not narrative:
        return ""
    import re
    pattern = rf"(?:^|\n)## {re.escape(section_heading)}(.*?)(?=^## |\Z)"
    m = re.search(pattern, narrative, re.DOTALL | re.MULTILINE)
    if m:
        content = m.group(1).strip()
        content = re.sub(r"^## .*$", "", content, flags=re.MULTILINE).strip()
        return content
    return narrative[:400].strip() if narrative else ""




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
