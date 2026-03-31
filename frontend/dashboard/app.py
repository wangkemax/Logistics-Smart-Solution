"""
Logistics Smart Solution — Streamlit Dashboard
Three modes: 方案生成 | 多方案对比 | Pipeline Run
"""

import streamlit as st
import requests
from ui_formatters import (
    safe_div, safe_max,
        fmt_text, fmt_number, fmt_integer, fmt_currency,
        fmt_percent, fmt_years, fmt_area,
        fmt_count, fmt_delta_percent,
    )
import json
import time
import os
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

# ---- Global exception hook to debug NoneType format errors ----
import sys as _sys
import traceback as _tb
_original_excepthook = _sys.excepthook
def _debug_excepthook(exc_type, exc_val, exc_tb):
    if exc_type is TypeError and "format" in str(exc_val):
        _sys.stderr.write("!!! NoneType FORMAT ERROR !!!\n")
        _tb.print_exception(exc_type, exc_val, exc_tb, file=_sys.stderr)
        _sys.stderr.write("!!! END !!!\n")
    _original_excepthook(exc_type, exc_val, exc_tb)
_sys.excepthook = _debug_excepthook





def _render_clarification_task_editor(pipeline_id: str, tasks: list, api: str, key_prefix: str = ""):
    """Render a list of clarification tasks with input forms."""
    if not tasks:
        st.info("暂无任务")
        return

    for i, task in enumerate(tasks[:10]):
        fkey = task.get("field_key", "")
        display_name = task.get("display_name", fkey)
        task_id = task.get("question_id", f"Q-{i}")
        priority = task.get("priority", "P1")
        category = task.get("category", "missing")
        current_val = task.get("current_value")
        status = task.get("current_status", "open")
        input_type = task.get("expected_input_type", "text")
        acceptable_units = task.get("acceptable_units", [])
        blocking = task.get("blocking_impact", "")
        guidance = task.get("guidance", "")
        example = task.get("example_answer", "")

        resolved = status == "resolved"
        container = st.container()
        with container:
            pri_color = "🔴" if priority == "P0" else "🟡"
            status_icon = "✅" if resolved else "⏳"
            with st.expander(f"{pri_color} {status_icon} [{task_id}] **{display_name}**", expanded=(not resolved)):
                st.markdown(f"**问题:** {task.get('question_text', '请补充该字段')}")
                if blocking:
                    st.warning(f"⚠️ {blocking}")
                if guidance:
                    st.caption(f"💡 {guidance}")
                if example:
                    st.caption(f"📝 示例: {example}")
                if current_val:
                    st.success(f"当前值: **{current_val}**")

                if not resolved:
                    inp_key = f"cw_{key_prefix}{fkey}"
                    if input_type == "number_with_unit":
                        val_col, unit_col = st.columns([2, 1])
                        with val_col:
                            num_val = st.number_input("数值", min_value=0.0, format="%f", key=f"{inp_key}_val")
                        with unit_col:
                            unit_opts = acceptable_units if acceptable_units else ["orders/day", "月订单量", "年订单量"]
                            selected_unit = st.selectbox("单位", options=unit_opts, key=f"{inp_key}_unit")
                        comment = st.text_input("备注（可选）", key=f"{inp_key}_comment", placeholder="来源说明...")
                        if f"cw_input_{fkey}" not in st.session_state:
                            st.session_state[f"cw_input_{fkey}"] = {}
                        st.session_state[f"cw_input_{fkey}"].update({
                            "value": num_val, "unit": selected_unit, "comment": comment,
                        })

                    elif input_type == "choice":
                        choices = task.get("conflict_candidates", []) or ["低", "中", "高"]
                        chosen = st.selectbox("选择值", options=choices, key=f"{inp_key}_choice")
                        if f"cw_input_{fkey}" not in st.session_state:
                            st.session_state[f"cw_input_{fkey}"] = {}
                        st.session_state[f"cw_input_{fkey}"].update({"value": chosen})

                    elif input_type == "service_scope_matrix":
                        matrix = task.get("service_matrix", {})
                        if not matrix:
                            st.warning("服务矩阵配置缺失，请联系管理员")
                        else:
                            selected_services = {}
                            st.markdown("**请勾选本项目包含的服务项：**")
                            category_descs = {
                                "inbound": "货物从供应商到达仓库到完成上架的全过程",
                                "storage": "货物在库期间的管理与保管",
                                "outbound": "从订单下达到货物出库的全过程",
                                "value_added": "核心仓储配送以外的增值作业",
                                "support": "运营管理、数据与系统支持",
                            }
                            emoji_map = {"inbound": "📥", "storage": "📦", "outbound": "📤", "value_added": "🔧", "support": "⚙️"}
                            for cat_key, cat_info in matrix.items():
                                cat_label = cat_info.get("label", cat_key)
                                cat_desc = category_descs.get(cat_key, "")
                                services = cat_info.get("services", {})
                                emoji = emoji_map.get(cat_key, "📌")
                                with st.expander(f"**{emoji} {cat_label}**", expanded=True):
                                    if cat_desc:
                                        st.caption(cat_desc)
                                    for svc_key, svc_info in services.items():
                                        svc_label = svc_info.get("label", svc_key)
                                        checked = st.checkbox(svc_label, value=False, key=f"{inp_key}_{cat_key}_{svc_key}")
                                        selected_services[f"{cat_key}.{svc_key}"] = checked
                            structured_value = {}
                            for full_key, checked in selected_services.items():
                                cat, svc = full_key.rsplit(".", 1)
                                structured_value.setdefault(cat, {})[svc] = checked
                            if f"cw_input_{fkey}" not in st.session_state:
                                st.session_state[f"cw_input_{fkey}"] = {}
                            st.session_state[f"cw_input_{fkey}"].update({"value": structured_value})
                            total = sum(sum(v.values()) for v in structured_value.values())
                            if total > 0:
                                st.success(f"已选择 {total} 项服务")
                            else:
                                st.warning("尚未选择任何服务")

                    else:
                        # text or unknown type: show text input + mark as resolved button
                        text_val = st.text_input("补充内容", key=f"{inp_key}_text", placeholder="请输入...", value=str(current_val) if current_val else "")
                        if f"cw_input_{fkey}" not in st.session_state:
                            st.session_state[f"cw_input_{fkey}"] = {}
                        st.session_state[f"cw_input_{fkey}"].update({"value": text_val})
                        st.caption("💡 填写完毕后，点击上方「🔄 提交并重新计算」按钮，系统将更新就绪状态")
                else:
                    st.success("✅ 已解决")


def _collect_pending_inputs() -> dict:
    """Collect all pending manual inputs from session state into a dict keyed by field_key."""
    pending = {}
    for key in list(st.session_state.keys()):
        if key.startswith("cw_input_"):
            fkey = key.replace("cw_input_", "")
            data = st.session_state[key]
            if isinstance(data, dict) and data.get("value") not in (None, "", 0):
                pending[fkey] = {
                    "value": data.get("value"),
                    "unit": data.get("unit"),
                    "comment": data.get("comment", ""),
                }
    return pending


# =====================================================================
# =====================================================================

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(
    page_title="物流预售AI系统",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---- CSS ----
st.markdown("""
<style>
    .main-header { font-size: 2.2rem; font-weight: bold; color: #1f4e79;
                   text-align: center; padding: 0.8rem 0;
                   border-bottom: 3px solid #2196f3; margin-bottom: 1.5rem; }
    .risk-low  { color: #4caf50; font-weight: bold; }
    .risk-mid  { color: #ff9800; font-weight: bold; }
    .risk-high { color: #f44336; font-weight: bold; }
    .step-done  { color: #27ae60; font-weight: bold; font-size: 1.1rem; }
    .step-wip   { color: #f39c12; font-weight: bold; font-size: 1.1rem; }
    .step-fail  { color: #e74c3c; font-weight: bold; font-size: 1.1rem; }
    .best-row   { background: #d5f5e3 !important; }
    div[data-testid="stDownloadButton"] button { background-color: #27ae60; color: white; }
</style>
""", unsafe_allow_html=True)


# =============================================================================
# Helper Functions
# =============================================================================

def call_api(url, payload, timeout=60):
    try:
        resp = requests.post(f"{API_BASE_URL}{url}", json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json(), None
    except requests.exceptions.ConnectionError:
        return None, "❌ 无法连接到后端服务，请确保后端已启动 (uvicorn backend.main:app)"
    except requests.exceptions.Timeout:
        return None, "❌ 请求超时，请稍后重试"
    except Exception as e:
        return None, f"❌ API调用失败: {e}"


def render_score_gauge(score, key=None):
    # Guard against None/non-numeric score (Plotly Indicator crashes on None)
    try:
        score = float(score) if score is not None else 0
    except (TypeError, ValueError):
        score = 0
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=score,
        domain={"x": [0, 1], "y": [0, 1]},
        title={"text": "匹配评分"},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": "#2196f3"},
            "steps": [
                {"range": [0, 40], "color": "#ffcdd2"},
                {"range": [40, 70], "color": "#fff9c4"},
                {"range": [70, 100], "color": "#c8e6c9"},
            ],
        },
    ))
    fig.update_layout(height=200, margin=dict(l=10, r=10, t=30, b=10))
    return fig


def render_cost_chart(cost_data):
    labels = ["仓储成本", "人工成本", "设备维护", "年度总成本"]
    values = [
        cost_data.get("warehouse_cost", 0) / 10000,
        cost_data.get("labor_cost_annual", 0) / 10000,
        cost_data.get("annual_maintenance", 0) / 10000,
        cost_data.get("total_annual_cost", 0) / 10000,
    ]
    colors = ["#42a5f5", "#66bb6a", "#ffa726", "#ef5350"]
    fig = go.Figure(data=[go.Bar(
        x=labels, y=values, marker_color=colors,
        text=[f"¥{v:.0f}万" for v in values], textposition="auto",
    )])
    fig.update_layout(title="年度成本构成 (万元)", yaxis_title="金额 (万元)",
                      height=280, margin=dict(l=10, r=10, t=40, b=10))
    return fig


def render_roi_chart(cost_data):
    capex = cost_data.get("automation_capex", 0) / 10000
    annual_saving = cost_data.get("automation_savings_annual", 0) / 10000
    annual_cost = cost_data.get("annual_maintenance", 0) / 10000
    years = list(range(0, 8))
    cum_benefit = [max(0, (annual_saving - annual_cost) * y - capex) for y in years]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=years, y=cum_benefit, mode="lines+markers",
                              name="累计净收益", line=dict(color="#4caf50", width=3)))
    fig.add_trace(go.Scatter(x=years, y=[capex]*len(years), mode="lines",
                              name="投资额", line=dict(color="#f44336", width=2, dash="dash")))
    fig.add_hline(y=0, line_dash="dot", line_color="gray")
    fig.update_layout(title="投资回报趋势 (万元)", xaxis_title="年份",
                      yaxis_title="金额 (万元)", height=280,
                      margin=dict(l=10, r=10, t=40, b=10))
    return fig


def render_compare_bar_chart(comparisons):
    # comparisons is already sorted by weighted score
    names = [c.get("scenario_name", "—")[:8] for c in comparisons]
    capex = [c.get("capex_estimate", 0) / 10000 for c in comparisons]
    savings = [(c.get("annual_labor_saving", 0) + c.get("annual_efficiency_saving", 0)) / 10000 for c in comparisons]
    fig = go.Figure(data=[
        go.Bar(name="自动化投资 (万)", x=names, y=capex, marker_color="#ef5350"),
        go.Bar(name="年节省人工 (万)", x=names, y=savings, marker_color="#4caf50"),
    ])
    fig.update_layout(barmode="group", title="投资与年节省对比 (万元)",
                      yaxis_title="金额 (万元)", height=280,
                      margin=dict(l=10, r=10, t=40, b=10))
    return fig


def render_compare_roi_chart(comparisons):
    # comparisons is already sorted by weighted score when called from results panel
    names = [c.get("scenario_name", "—")[:10] for c in comparisons]
    roi_5y = [c.get("roi_5y") or 0 for c in comparisons]
    colors = ["#27ae60" if c.get("is_best") else "#95a5a6" for c in comparisons]
    fig = go.Figure(data=[go.Bar(
        y=names, x=roi_5y, orientation="h",
        marker_color=colors, text=[f"{(r or 0):.1f}x" for r in roi_5y], textposition="auto",
    )])
    fig.update_layout(title="5年ROI倍数对比", xaxis_title="ROI (倍)",
                     height=max(220, len(comparisons) * 60),
                     margin=dict(l=10, r=10, t=40, b=10))
    return fig


def render_compare_radar(comparisons):
    max_roi     = safe_max(c.get("roi_5y") or 0 for c in comparisons)
    max_pb      = safe_max(c.get("payback_years") or 0 for c in comparisons)
    max_saving  = safe_max((c.get("annual_labor_saving") or 0) + (c.get("annual_efficiency_saving") or 0) for c in comparisons)
    max_hc      = safe_max(c.get("headcount_saved") or 0 for c in comparisons)
    colors = ["#2196f3", "#4caf50", "#ff9800", "#9c27b0", "#f44336"]
    traces = []
    for i, c in enumerate(comparisons[:5]):
        roi     = c.get("roi_5y") or 0
        pb      = c.get("payback_years") or 0
        saving  = (c.get("annual_labor_saving") or 0) + (c.get("annual_efficiency_saving") or 0)
        hc      = c.get("headcount_saved") or 0
        values = [
            safe_div(roi,     max_roi)    * 100,
            (1 - safe_div(pb, max_pb))   * 100,
            safe_div(saving,  max_saving) * 100,
            safe_div(hc,      max_hc)     * 100,
            100,
        ]
        traces.append(go.Scatterpolar(
            r=values, theta=["5年ROI", "回本周期", "年节省", "人工节省", ""],
            name=c["scenario_name"][:8], fill="toself" if i == 0 else None,
            line=dict(color=colors[i % len(colors)]),
        ))
    fig = go.Figure(data=traces)
    fig.update_layout(title="综合指标雷达图",
                     polar=dict(radialaxis=dict(range=[0, 100])),
                     height=300, margin=dict(l=10, r=10, t=40, b=10))
    return fig


def extract_tender_text(uploaded_file) -> str:
    """Extract text from uploaded file (PDF, TXT, DOCX)."""
    if uploaded_file is None:
        return ""
    fname = uploaded_file.name.lower()
    try:
        if fname.endswith(".pdf"):
            import io
            from PyPDF2 import PdfReader
            # Reset pointer in case file was already read
            if hasattr(uploaded_file, "seek"):
                uploaded_file.seek(0)
            reader = PdfReader(io.BytesIO(uploaded_file.read()))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        elif fname.endswith(".txt"):
            return uploaded_file.read().decode("utf-8", errors="replace")
        elif fname.endswith(".docx"):
            from docx import Document
            if hasattr(uploaded_file, "seek"):
                uploaded_file.seek(0)
            doc = Document(uploaded_file)
            return "\n".join(p.text for p in doc.paragraphs)
        else:
            return uploaded_file.read().decode("utf-8", errors="replace")
    except Exception as e:
        return f"[文件解析失败: {e}]"


def render_step_status(name: str, status: str, details: str = ""):
    """Render a pipeline step with status icon."""
    icon_map = {"done": "✅", "wip": "⏳", "fail": "❌", "pending": "⬜"}
    icon = icon_map.get(status, "⬜")
    cls_map = {"done": "step-done", "wip": "step-wip", "fail": "step-fail", "pending": ""}
    cls = cls_map.get(status, "")
    st.markdown(f"**{icon} {name}**" + (f" — _{details}_" if details else ""), unsafe_allow_html=True)


# =============================================================================
# QA Correction Panel
# =============================================================================

# Field metadata: frontend label → (profile_key, widget_type, extra_kwargs)
_QA_FIELD_META = {
    "warehouse_area":          ("仓库面积",          "number",   {"min_value": 500.0,      "max_value": 500000.0,  "step": 500.0,   "format": "%.0f"}),
    "sku_count":               ("SKU数量",            "number",   {"min_value": 100.0,      "max_value": 1000000.0, "step": 1000.0,  "format": "%.0f"}),
    "daily_orders":            ("日订单量",           "number",   {"min_value": 50.0,       "max_value": 500000.0,  "step": 100.0,   "format": "%.0f"}),
    "inventory":               ("库存量",             "number",   {"min_value": 1000.0,     "max_value": 10000000.0,"step": 10000.0, "format": "%.0f"}),
    "contract_years":          ("合同年限",           "number",   {"min_value": 1.0,        "max_value": 20.0,       "step": 1.0,     "format": "%.0f"}),
    "industry":                ("行业",               "select",   {"options": ["电商", "3PL", "零售", "制造", "快递", "医药", "食品", "生鲜"]}),
    "region":                  ("地区",               "select",   {"options": ["华东", "华南", "华北", "华中", "西部"]}),
    "labor_cost_level":        ("人工成本等级",       "select",   {"options": ["低", "中", "高"]}),
    "budget_level":            ("预算等级",           "select",   {"options": ["低", "中", "高"]}),
    "automation_expectation":  ("自动化期望",         "select",   {"options": ["低", "中", "高"]}),
    "go_live_date":            ("预计上线日期",       "text",     {"placeholder": "YYYY-MM"}),
}


def _submit_qa_correction(pipeline_id: str, overrides: dict) -> tuple[bool, str]:
    """
    Submit QA correction: call POST /api/pipeline/{pipeline_id}/retry
    with from_stage=1_extraction and profile_overrides.
    Returns (success, message).
    """
    try:
        resp = requests.post(
            f"{API_BASE_URL}/api/pipeline/{pipeline_id}/retry",
            json={"from_stage": "1_extraction", "profile_overrides": overrides},
            timeout=15,
        )
        if resp.status_code == 200:
            return True, "✅ 已提交修正，Pipeline 正在重新运行…"
        else:
            return False, f"❌ 重试失败 [{resp.status_code}]: {str(resp.text or '')[:120]}"
    except Exception as e:
        return False, f"❌ 请求失败: {e}"


def _render_qa_correction_panel(pipeline_id: str, qa_verdict: str, qa_issues: list, existing_profile: dict) -> None:
    """
    Render the QA correction form when verdict is CONDITIONAL_PASS or FAIL.

    - qa_verdict: "CONDITIONAL_PASS" | "FAIL"
    - qa_issues: list of issue dicts (or strings from legacy pipelines)
    - existing_profile: current project profile dict for pre-filling values
    """
    if qa_verdict not in ("CONDITIONAL_PASS", "FAIL"):
        return

    # ---- Header warning ----
    if qa_verdict == "FAIL":
        st.error("❌ QA审核未通过，请修正以下问题后重试")
    else:
        st.warning("⚠️ QA条件通过，以下事项请确认")

    with st.expander("📝 修正 QA 问题", expanded=True):
        # ---- Build the set of fields mentioned in issues ----
        issue_fields = set()
        for issue in qa_issues:
            if isinstance(issue, dict):
                # New format: {"field": "warehouse_area", "message": "...", "severity": "high"}
                f = issue.get("field")
                if f:
                    issue_fields.add(f)
            elif isinstance(issue, str):
                # Legacy string format: "P0缺失数据: ['warehouse_area', 'sku_count']"
                for key in _QA_FIELD_META:
                    if key in issue:
                        issue_fields.add(key)

        if not issue_fields:
            st.info("无可修正字段，请使用「从指定阶段重试」手动调整输入。")
            return

        # ---- Show issue list with severity icons ----
        severity_icon_map = {
            "high":   "🔴 P0",
            "medium": "🟡 P1",
            "low":    "⚪ P2",
        }
        severity_order = ["high", "medium", "low"]

        for issue in qa_issues:
            if isinstance(issue, dict):
                sev = issue.get("severity", "low")
                icon = severity_icon_map.get(sev, "⚪")
                field_label = _QA_FIELD_META.get(issue.get("field", ""), (issue.get("field", ""),))[0]
                msg = issue.get("message", "")
                st.markdown(f"{icon} **{field_label}** — {msg}")
            elif isinstance(issue, str):
                st.markdown(f"⚪ {issue}")

        st.divider()

        # ---- Collect all QA-correctable fields (always show for convenience) ----
        # Show all fields that appear in issues + a few common ones at the top
        priority_fields = ["warehouse_area", "sku_count", "daily_orders", "inventory",
                           "industry", "region", "labor_cost_level", "budget_level",
                           "automation_expectation", "contract_years", "go_live_date"]

        collected_overrides = {}

        # Pre-fill from existing profile
        for fkey in priority_fields:
            if fkey not in _QA_FIELD_META:
                continue
            label, wtype, kwargs = _QA_FIELD_META[fkey]
            current_val = existing_profile.get(fkey)
            col1, col2 = st.columns([2, 1])
            with col1:
                if wtype == "number":
                    default_val = float(current_val) if current_val is not None else kwargs.get("min_value", 0)
                    val = st.number_input(
                        label,
                        value=default_val,
                        **kwargs,
                        key=f"qa_corr_{fkey}",
                    )
                    collected_overrides[fkey] = val
                elif wtype == "select":
                    options = kwargs["options"]
                    default_idx = 0
                    if current_val in options:
                        default_idx = options.index(current_val)
                    val = st.selectbox(
                        label,
                        options=options,
                        index=default_idx,
                        key=f"qa_corr_{fkey}",
                    )
                    collected_overrides[fkey] = val
                elif wtype == "text":
                    default_val = str(current_val) if current_val is not None else ""
                    val = st.text_input(
                        label,
                        value=default_val,
                        placeholder=kwargs.get("placeholder", ""),
                        key=f"qa_corr_{fkey}",
                    )
                    collected_overrides[fkey] = val
            with col2:
                st.markdown("")  # spacer

        st.divider()

        submit_label = "📝 修正并重试"
        submitted = st.button(submit_label, type="primary", width='stretch')

        if submitted:
            # Filter out None / empty overrides so we don't blast existing values
            clean_overrides = {k: v for k, v in collected_overrides.items()
                               if v is not None and v != ""}
            success, msg = _submit_qa_correction(pipeline_id, clean_overrides)
            if success:
                st.session_state.pipeline_state = "polling"
                st.session_state._skip_correction = False
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)


# =============================================================================
# Welcome Screens
# =============================================================================

def _render_welcome_single():
    st.markdown("""
    <div style="text-align: center; padding: 3rem;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                border-radius: 15px; color: white; margin: 2rem 0;">
        <h2>欢迎使用物流自动化预售AI系统</h2>
        <p style="font-size: 1.1rem; margin: 1rem 0;">
            在左侧填写项目信息，点击"生成解决方案"即可获得：
        </p>
        <div style="display: flex; justify-content: space-around; margin: 2rem 0;">
            <div>🎯<br><b>智能推荐</b><br>匹配最优自动化方案</div>
            <div>💰<br><b>成本分析</b><br>精准测算投资回报</div>
            <div>📊<br><b>综合报告</b><br>一键生成PDF方案</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.subheader("📚 支持的自动化场景")
    st.dataframe(pd.DataFrame({
        "方案": ["AMR移动机器人", "GTP货到人系统", "输送分拣线", "立体仓库AS/RS", "跨带分拣机"],
        "行业": ["电商/3PL/零售", "电商/3PL", "电商/快递/零售", "制造/3PL/医药", "快递/电商"],
        "人工节省": ["30%", "50%", "40%", "60%", "55%"],
        "投资规模": ["50-200万", "200-800万", "100-500万", "500-2000万", "300-1000万"],
    }), width='stretch', hide_index=True)


def _render_welcome_compare():
    st.markdown("""
    <div style="text-align: center; padding: 3rem;
                background: linear-gradient(135deg, #43a047 0%, #2e7d32 100%);
                border-radius: 15px; color: white; margin: 2rem 0;">
        <h2>⚖️ 多方案ROI对比</h2>
        <p style="font-size: 1.1rem; margin: 1rem 0;">
            在左侧选择2-5个自动化方案，系统将横向对比其<br>
            投资成本、ROI、回本周期、年节省等核心指标
        </p>
        <div style="display: flex; justify-content: space-around; margin: 2rem 0;">
            <div>📊<br><b>投资对比</b><br>CAPEX一目了然</div>
            <div>📈<br><b>ROI对比</b><br>5年回报分析</div>
            <div>🎯<br><b>推荐最佳</b><br>智能标记最优方案</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.subheader("📚 支持对比的15种自动化场景")
    all_sc = pd.DataFrame({
        "ID": [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15],
        "方案名称": ["AMR拣选辅助","GTP货到人系统","输送分拣线","自动贴标系统","立体仓库AS/RS",
                    "自动化输送线","视觉识别质检","拆码垛机器人","WMS仓储管理系统","AGV搬运系统",
                    "自动包装线","冷链自动化仓储","跨带分拣机","货架式密集存储","自动化退货处理"],
        "类别": ["移动机器人","货到人","输送分拣","自动化辅助","立体仓库","输送系统",
                 "视觉检测","搬运机器人","软件系统","移动机器人","包装自动化","冷链系统",
                 "高速分拣","密集存储","逆向物流"],
    })
    st.dataframe(all_sc, width='stretch', hide_index=True)


# =============================================================================
# Sidebar
# =============================================================================
with st.sidebar:
    st.header("🏭 Logistics Smart Solution")

    _MODES = ["📋 方案生成", "⚖️ 多方案对比", "🚀 Pipeline Run", "💬 Clarification Workspace"]
    # Use index in session_state (not keyed) so we can switch tabs programmatically
    if "_app_mode_idx" not in st.session_state:
        st.session_state._app_mode_idx = 0
    app_mode = st.radio(
        "选择功能模式",
        options=_MODES,
        index=st.session_state._app_mode_idx,
        help="方案生成：单方案推荐+PDF\n多方案对比：横向对比ROI\nPipeline Run：端到端自动投标\nClarification：补录澄清推动项目继续",
    )
    st.divider()

    # Initialize session state
    if "pipeline_results" not in st.session_state:
        st.session_state.pipeline_results = None

# =============================================================================
# Results Panel Renderer (used by Pipeline Run right column)
# =============================================================================

def _safe_best_result(results: dict) -> dict:
    """Safely extract best result from pipeline results. Returns {} if empty."""
    if not results:
        return {}
    # Backend returns "comparisons", not "financial_comparison"
    comparison = results.get("comparisons") or results.get("financial_comparison") or []
    if comparison and isinstance(comparison, list):
        for item in comparison:
            if item.get("is_best") is True:
                return item
        if comparison:
            return comparison[0]
    recs = results.get("recommendations") or []
    if recs and isinstance(recs, list):
        return recs[0]
    return {}


def _render_key_metrics(best: dict, profile: dict):
    """Render 8 key metrics using safe formatters."""
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("5年ROI", fmt_percent(best.get("roi_5y")))
    with c2:
        st.metric("回本周期", fmt_years(best.get("payback_years")))
    with c3:
        # QA verdict display — handles both string and dict issue formats
        qa_verdict = best.get("qa_verdict", "UNKNOWN")
        if qa_verdict == "PASS":
            st.success("✅ QA审核通过")
        elif qa_verdict == "CONDITIONAL_PASS":
            issues = best.get("qa_issues") or []
            st.warning("⚠️ QA条件通过 — 以下事项需确认：")
            for issue in issues:
                if isinstance(issue, dict):
                    sev = issue.get("severity", "low")
                    sev_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(sev, "⚪")
                    st.markdown(f"{sev_icon} **{issue.get('message', '')}**")
                elif isinstance(issue, str):
                    st.markdown(f"⚪ {issue}")
        elif qa_verdict == "FAIL":
            st.error("❌ QA审核未通过")
            failed_stage = best.get("last_failed_stage", "")
            retry_count = best.get("retry_count", 0)
            st.markdown(f"失败阶段：{fmt_text(failed_stage)} | 已重试：{retry_count}次")
    with c4:
        st.metric("投资额", fmt_currency(best.get("capex_estimate")))
    c5, c6, c7, c8 = st.columns(4)
    with c5:
        st.metric("节省人数", fmt_count(best.get("headcount_saved"), "人"))
    with c6:
        st.metric("年运维成本", fmt_currency(best.get("opex_annual")))
    with c7:
        st.metric("仓库面积", fmt_area(profile.get("warehouse_area")))
    with c8:
        st.metric("SKU数", fmt_count(profile.get("sku_count")))



def _render_stage_retry_section(pipeline_id: str, stages: list, key_prefix: str = "") -> None:
    """
    Render stage-by-stage breakdown with per-stage retry buttons.
    Called after pipeline completion (especially when QA FAIL or stage FAILED).
    
    Each stage row shows:
      - Stage number + name
      - Status icon (✅ done / ❌ failed / ⏳ running / ➖ skipped / ⬜ pending)
      - Duration
      - Retry button for FAILED stages
    
    Also renders a "从第X阶段重试" dropdown selector to retry from any stage.
    """
    if not stages:
        return

    stage_labels = {
        "1_extraction": "① 解析招标",
        "2_recommendation": "② 推荐引擎",
        "3_cost_comparison": "③ ROI计算",
        "4_qa_review": "④ QA审核",
        "5_pdf_report": "⑤ PDF报告",
    }

    failed_stages = [s for s in stages if s.get("status") == "FAILED"]
    has_failures = bool(failed_stages)

    with st.container():
        st.markdown("**🔁 阶段执行详情**")
        
        # ---- Per-stage rows ----
        for s in stages:
            stage_name = s.get("stage", "")
            label = stage_labels.get(stage_name) or str(stage_name) or "未知阶段"
            s_status = s.get("status", "PENDING")
            dur = s.get("duration_seconds")
            err = s.get("error")

            icon_map = {"DONE": "✅", "FAILED": "❌", "RUNNING": "⏳", "SKIPPED": "➖", "PENDING": "⬜"}
            icon = icon_map.get(s_status, "⬜")
            
            row_cols = st.columns([1, 3, 2, 1])
            with row_cols[0]:
                st.markdown(f"**{icon}**")
            with row_cols[1]:
                st.markdown(f"**{label}**")
                if err:
                    st.caption(f"⚠️ {str(err or '')[:80]}")
            with row_cols[2]:
                if dur is not None:
                    st.caption(f"⏱️ {dur:.1f}s")
                else:
                    st.caption("—")
            with row_cols[3]:
                if s_status == "FAILED":
                    retry_key = f"retry_{key_prefix}{stage_name}"
                    if st.button(f"🔄 重试", key=retry_key, help=f"重试 {label}"):
                        with st.spinner(f"正在重试 {label}..."):
                            try:
                                resp = requests.post(
                                    f"{API_BASE_URL}/api/pipeline/{pipeline_id}/retry",
                                    json={"from_stage": stage_name},
                                    timeout=10,
                                )
                                if resp.status_code == 200:
                                    result = resp.json()
                                    st.session_state.pipeline_state = "polling"
                                    st.session_state._pipeline_id = pipeline_id
                                    st.session_state._skip_correction = False
                                    st.success(f"✅ 已提交重试请求，从阶段「{label}」重新执行")
                                    st.rerun()
                                else:
                                    st.error(f"重试失败: {resp.status_code} {resp.text}")
                            except Exception as ex:
                                st.error(f"重试请求失败: {ex}")

        st.divider()

        # ---- From-stage selector ----
        st.markdown("**从指定阶段重试**")
        retry_from_c1, retry_from_c2 = st.columns([2, 1])
        
        stage_options = [(sn, stage_labels.get(sn, sn)) for sn in [
            "1_extraction", "2_recommendation", "3_cost_comparison", "4_qa_review", "5_pdf_report"
        ]]
        
        # Pre-select: first failed stage if any, else first non-DONE stage
        default_idx = 0
        for i, (sn, _) in enumerate(stage_options):
            if any(s.get("stage") == sn and s.get("status") == "FAILED" for s in stages):
                default_idx = i
                break
        
        with retry_from_c1:
            selected_stage = st.selectbox(
                "选择阶段",
                options=[sn for sn, _ in stage_options],
                format_func=lambda sn: (stage_labels.get(sn, sn) if sn else "未知阶段"),
                index=default_idx,
                key=f"from_stage_select_{key_prefix}{pipeline_id}",
                label_visibility="collapsed",
            )
        with retry_from_c2:
            retry_from_key = f"retry_from_{key_prefix}{pipeline_id}"
            if st.button("🚀 执行重试", key=retry_from_key, type="primary", width='stretch'):
                with st.spinner(f"正在从「{(stage_labels.get(selected_stage, selected_stage) if selected_stage else selected_stage or '该阶段')}」重试..."):
                    try:
                        resp = requests.post(
                            f"{API_BASE_URL}/api/pipeline/{pipeline_id}/retry",
                            json={"from_stage": selected_stage},
                            timeout=10,
                        )
                        if resp.status_code == 200:
                            result = resp.json()
                            st.session_state.pipeline_state = "polling"
                            st.session_state._pipeline_id = pipeline_id
                            st.session_state._skip_correction = False
                            reset_list = result.get("reset_stages", [])
                            st.success(f"✅ 已重置阶段: {', '.join(reset_list)}")
                            st.rerun()
                        else:
                            st.error(f"重试失败 [{resp.status_code}]: {str(resp.text or '')[:100]}")
                    except Exception as ex:
                        st.error(f"重试请求失败: {ex}")



def _render_results_panel():
    results = st.session_state.get("pipeline_result") or {}
    profile = st.session_state.get("pipeline_profile", {}) or {}
    recs = st.session_state.get("pipeline_recs", []) or []
    comparisons = st.session_state.get("pipeline_comparisons", []) or []
    state = st.session_state.get("pipeline_state", "UNKNOWN")
    best = _safe_best_result(results)

    # =============================================================================
    # Max's Enhancement #5: Pipeline Gate Banner
    # Show gate status for each downstream module before any results
    # =============================================================================
    pipeline_gate = results.get("pipeline_gate") or profile.get("_readiness") or {}
    gate_cost     = pipeline_gate.get("cost_model", "UNKNOWN")
    gate_sol      = pipeline_gate.get("solution_design", "UNKNOWN")
    gate_ctr      = pipeline_gate.get("contract_review", "UNKNOWN")
    gate_net      = pipeline_gate.get("network_estimation", "UNKNOWN")
    gate_kpi      = pipeline_gate.get("kpi_gate", "UNKNOWN")
    gate_score    = pipeline_gate.get("readiness_score")
    blocked_items = pipeline_gate.get("blocking_items") or []
    net_blocked   = pipeline_gate.get("network_blocking_fields") or []
    gate_detail   = pipeline_gate.get("gate_detail", "")
    kpi_warn      = pipeline_gate.get("kpi_warn_message", "")

    gate_icon_map = {"PASS": "✅", "WARN": "⚠️", "BLOCK": "🚫", "UNKNOWN": "❓"}
    gate_color_map = {"PASS": "green", "WARN": "yellow", "BLOCK": "red", "UNKNOWN": "gray"}

    gate_blocks = [
        ("成本测算", gate_cost, "cost_model"),
        ("网络估算", gate_net, "network_estimation"),
        ("方案设计", gate_sol, "solution_design"),
        ("合同审核", gate_ctr, "contract_review"),
        ("KPI/SLA", gate_kpi, "kpi_gate"),
    ]
    has_any_gate_warn_or_block = any(
        g[1] in ("WARN", "BLOCK") for g in gate_blocks
    )

    if gate_cost != "UNKNOWN":
        st.markdown("**🚦 阶段门禁状态**")
        gc1, gc2, gc3, gc4, gc5 = st.columns(5)
        gate_cols = [gc1, gc2, gc3, gc4, gc5]
        for (label, status, key), col in zip(gate_blocks, gate_cols):
            icon = gate_icon_map.get(status, "❓")
            with col:
                if status == "PASS":
                    st.success(f"{icon} {label}")
                elif status == "WARN":
                    st.warning(f"{icon} {label}")
                elif status == "BLOCK":
                    st.error(f"{icon} {label}")
                else:
                    st.caption(f"{icon} {label}")
        # Readiness score
        if gate_score is not None:
            score_pct = float(gate_score) * 100
            sc1, sc2 = st.columns([3, 1])
            with sc1:
                st.progress(float(gate_score), text=f"就绪度 {score_pct:.0f}%")
            with sc2:
                if gate_score >= 0.8:
                    st.success("高")
                elif gate_score >= 0.5:
                    st.warning("中")
                else:
                    st.error("低")
        # Blocking items detail
        if blocked_items:
            with st.expander(f"🚫 阻塞项详情（{len(blocked_items)}项）", expanded=False):
                for item in blocked_items:
                    st.markdown(f"- `{item}`")
        if net_blocked:
            st.caption(f"⚠️ 网络估算被阻塞：缺少 {', '.join(net_blocked)}")
        if kpi_warn:
            st.info(f"ℹ️ {kpi_warn}")
        if gate_detail:
            st.caption(f"📌 {gate_detail[:120]}")
        st.divider()

    # =============================================================================
    # Cost Model Readiness Card — v0.2.1 UI Clarity Patch
    # P2 Visual Enhancements: weighted progress bar, unified R/Y/G colors,
    # business tooltips, field status icons
    # =============================================================================
    readiness_data = results.get("readiness") or profile.get("_readiness") or {}
    downstream_input_meta = results.get("downstream_input_meta") or {}

    # Determine recommended mode
    calc_mode = "UNKNOWN"
    blocking_reasons = []
    assumptions_used = []
    clar_questions = []
    p0_summary = {}
    p1_summary = {}
    unusable_fields = []

    if downstream_input_meta:
        calc_mode = downstream_input_meta.get("recommended_mode", "UNKNOWN")
        blocking_reasons = downstream_input_meta.get("blocking_reasons", [])
        p0_summary = downstream_input_meta.get("p0_summary", {})
        p1_summary = downstream_input_meta.get("p1_summary", {})
        clar_questions = results.get("clarification_questions") or []
        assumptions_used = results.get("assumptions_used", []) or []
        unusable_fields = results.get("unusable_fields", [])
    elif readiness_data:
        cost_ready = readiness_data.get("for_cost_model", None)
        if cost_ready is True:
            calc_mode = "full_calc"
        elif cost_ready is False:
            calc_mode = "blocked"
        else:
            calc_mode = "range_estimate"

    # ---- Unified color/semantic system ----
    COLOR = {
        "full_calc":      {"hex": "#27ae60", "rgb": (39,174,96),   "label": "green",  "badge_bg": "#eafaf1"},
        "range_estimate": {"hex": "#f39c12", "rgb": (243,156,18),  "label": "yellow", "badge_bg": "#fef9e7"},
        "blocked":        {"hex": "#e74c3c", "rgb": (231,76,60),   "label": "red",    "badge_bg": "#fdecea"},
        "unknown":        {"hex": "#95a5a6", "rgb": (149,165,166), "label": "gray",   "badge_bg": "#f5f5f5"},
    }
    mode_info = COLOR.get(calc_mode, COLOR["unknown"])

    # ---- Weighted readiness score ----
    # P0 weight=50%, P1 weight=35%, P2 weight=15%
    # Score = P0_provided/P0_total*50 + P1_provided/P1_total*35 + P2_provided/P2_total*15
    p0_total = max(p0_summary.get("total", 0), 1)
    p1_total = max(p1_summary.get("total", 0), 1)
    p0_prov = p0_summary.get("provided", 0) + p0_summary.get("inferred", 0)
    p1_prov = p1_summary.get("provided", 0) + p1_summary.get("inferred", 0)
    # P2: count from inputs_to_show if available
    p2_prov = 0
    p2_total = 1
    readiness_inputs = results.get("required_inputs", {})
    if readiness_inputs:
        p2_prov = sum(1 for v in readiness_inputs.values()
                      if isinstance(v, dict) and v.get("priority") == "P2"
                      and v.get("status") in ("provided", "inferred"))
        p2_total = max(sum(1 for v in readiness_inputs.values()
                          if isinstance(v, dict) and v.get("priority") == "P2"), 1)

    weighted_score = (p0_prov / p0_total * 0.50 +
                     p1_prov / p1_total * 0.35 +
                     p2_prov / p2_total * 0.15)
    readiness_pct = max(0.0, min(1.0, weighted_score))

    # Progress bar color matches mode
    pb_color = mode_info["hex"]

    # P0/P1 counts
    p0_issues = p0_summary.get("missing", 0) + p0_summary.get("ambiguous", 0)
    p1_issues = p1_summary.get("missing", 0) + p1_summary.get("ambiguous", 0)

    # ---- Business-language blocking reasons ----
    blocking_bullets = []
    for reason in blocking_reasons:
        reason_str = str(reason)
        if "dc_count" in reason_str or "DC数量" in reason_str:
            blocking_bullets.append("📦 DC/仓库数量缺失，无法建立网络成本模型")
        elif "warehouse_area" in reason_str or "仓库面积" in reason_str:
            blocking_bullets.append("🏭 仓库面积缺失，无法测算仓租和设备投入")
        elif "daily_orders" in reason_str or "日均出库量" in reason_str:
            blocking_bullets.append("📋 日均出库量缺失，无法建立作业量模型")
        elif "contract_years" in reason_str or "合同年限" in reason_str:
            blocking_bullets.append("📄 合同年限缺失或存在冲突，无法计算ROI回本周期")
        elif "service_scope" in reason_str or "服务范围" in reason_str:
            blocking_bullets.append("⚙️ 服务范围未明确，无法确定作业成本边界")
        else:
            blocking_bullets.append(reason_str[:80])

    # ---- Mode badge labels with tooltips ----
    mode_labels = {
        "full_calc":      ("✅ 正式测算",      "关键字段齐备，可进行正式测算。\n结果可作为正式报价参考。"),
        "range_estimate": ("⚠️ 区间估算",      "关键字段齐备，但部分参数使用假设。\n结果仅适合方案方向性判断，不可作为正式报价。"),
        "blocked":        ("🚫 已阻塞",        "存在关键字段缺失或冲突，继续输出正式ROI会造成误导。\n请先完成澄清。"),
        "unknown":         ("❓ 未知",           "数据不足，无法判断当前计算模式。"),
    }
    badge_title, badge_tooltip = mode_labels.get(calc_mode, mode_labels["unknown"])
    badge_title_short = badge_title  # keep short for display

    st.markdown("**🎯 Cost Model 就绪状态**")

    # ---- Row 1: Mode badge + weighted progress bar + counts ----
    m_col, bar_col, counts_col = st.columns([1.2, 1.5, 2.3])

    # Mode badge (left)
    with m_col:
        tooltip_md = badge_tooltip.replace("\n", "  \n")
        st.markdown(
            f'<div title="{badge_tooltip}" style="background:{mode_info["badge_bg"]};'
            f'padding:10px 14px;border-radius:8px;border-left:5px solid {mode_info["hex"]};'
            f'cursor:help">'
            f'<b style="font-size:14px">{badge_title}</b><br>'
            f'<span style="font-size:12px;color:#666">'
            f'{"点击展开详情" if clar_questions else "字段完整"}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # Weighted readiness progress bar (center)
    with bar_col:
        pct_int = int(readiness_pct * 100)
        bar_label = f"{pct_int}% 就绪"
        st.markdown("&nbsp;")  # vertical align helper
        st.markdown(
            f'<div style="background:#f0f0f0;border-radius:6px;padding:2px;margin-top:4px">'
            f'<div title="P0×50% + P1×35% + P2×15%" style="background:{pb_color};'
            f'width:{pct_int}%;border-radius:5px;height:18px;line-height:18px;">'
            f'</div></div>',
            unsafe_allow_html=True,
        )
        st.caption(f"P0 {p0_prov}/{p0_total} · P1 {p1_prov}/{p1_total} · P2 {p2_prov}/{p2_total}  "
                   f"(权重 50/35/15%)")

    # Counts (right)
    with counts_col:
        c1, c2, c3 = st.columns(3)
        with c1:
            if p0_issues > 0:
                st.markdown(
                    f'<div title="P0字段为正式测算必需输入，当前缺失或存在冲突，'
                    f'禁止使用假设替代">' 
                    f'<span style="color:#e74c3c;font-weight:bold">🔴 P0 问题：{p0_issues}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                st.caption("⚠️ 禁止假设替代")
            else:
                st.success(f"✅ P0 正常")
        with c2:
            if p1_issues > 0:
                st.warning(f"🟡 P1 问题：{p1_issues}")
                st.caption("可区间估算")
            else:
                st.success(f"✅ P1 正常")
        with c3:
            n_clar = len(clar_questions)
            if n_clar > 0:
                st.info(f"📝 澄清：{n_clar}项")
            else:
                st.caption("无待澄清项")

    # ---- Row 2: Blocking reasons or assumptions summary ----
    if calc_mode == "blocked" and blocking_bullets:
        st.markdown(
            f'<div style="background:#fdecea;border-left:4px solid #e74c3c;'
            f'padding:10px 14px;border-radius:4px;margin-top:4px">'
            f'<b style="color:#c0392b">🚫 阻塞原因</b><br>'
            f'<span style="font-size:13px">'
            f"存在关键字段缺失或冲突，继续输出正式ROI会造成误导。\n"
            f"请优先完成以下澄清项：</span>"
            f'</div>',
            unsafe_allow_html=True,
        )
        for b in blocking_bullets:
            st.markdown(f"&nbsp;&nbsp;&nbsp;• {b}")
        if clar_questions:
            with st.expander(f"📝 查看全部澄清问题（{len(clar_questions)}项）", expanded=False):
                for q in clar_questions[:10]:
                    sev = q.get("severity", "P1")
                    sev_icon = "🔴" if sev == "P0" else "🟡"
                    sev_label = "P0阻塞" if sev == "P0" else "P1重要"
                    st.markdown(
                        f"{sev_icon} **[{sev_label}] {q.get('display_name', q.get('field_key', '?'))}**"
                    )
                    st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;{q.get('question', '—')}")
                    fmt = q.get("suggested_answer_format", "")
                    if fmt:
                        st.caption(f"&nbsp;&nbsp;&nbsp;&nbsp;建议格式：{fmt}")

    elif calc_mode == "range_estimate" and (assumptions_used or clar_questions):
        st.markdown(
            f'<div style="background:#fef9e7;border-left:4px solid #f39c12;'
            f'padding:10px 14px;border-radius:4px;margin-top:4px">'
            f'<b style="color:#d68910">⚠️ 使用了系统假设</b><br>'
            f'<span style="font-size:13px">'
            f"以下字段使用经验假设，结果仅适合方案方向性判断，"
            f'<b>不可作为正式报价依据</b>。</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if assumptions_used:
            for a in assumptions_used[:8]:
                fld = a.get("field", "?")
                val = a.get("value", "—")
                rule = a.get("assumption", "")[:50]
                st.markdown(
                    f"&nbsp;&nbsp;&nbsp;• `{fld}` = **{val}**"
                    f' <span style="color:#888">({rule})</span>'
                )
        if clar_questions:
            with st.expander(f"📝 建议澄清（{len(clar_questions)}项）", expanded=False):
                for q in clar_questions[:8]:
                    sev = q.get("severity", "P1")
                    sev_icon = "🔴" if sev == "P0" else "🟡"
                    st.markdown(
                        f"{sev_icon} **{q.get('display_name', q.get('field_key', '?'))}**："
                        f"{q.get('question', '—')[:70]}"
                    )

    elif calc_mode == "full_calc":
        st.markdown(
            f'<div style="background:#eafaf1;border-left:4px solid #27ae60;'
            f'padding:10px 14px;border-radius:4px;margin-top:4px">'
            f'✅ <b style="color:#27ae60">正式测算就绪</b> — '
            f'<span style="font-size:13px">所有P0字段完整，可进行正式成本测算，结果可作为正式报价参考。</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ---- Row 3: Expandable field detail (P1 enhancement with icons + colors) ----
    req_inputs = results.get("required_inputs", {})
    downstream_req = results.get("downstream_input", {}).get("required_inputs", {})
    inputs_to_show = downstream_req if downstream_req else req_inputs

    status_icon = {
        "provided":  ("✅", "#27ae60"),
        "assumed":   ("⚠️", "#f39c12"),
        "inferred":  ("🔶", "#8e44ad"),
        "missing":   ("○",  "#e74c3c"),
        "ambiguous": ("⛔", "#c0392b"),
    }
    prio_color = {"P0": "#e74c3c", "P1": "#f39c12", "P2": "#95a5a6"}

    if inputs_to_show or clar_questions:
        with st.expander("🔍 展开：字段详情与澄清问题", expanded=False):
            if inputs_to_show:
                rows = []
                for fname, finfo in inputs_to_show.items():
                    if not isinstance(finfo, dict):
                        continue
                    status  = finfo.get("status", "unknown")
                    priority = finfo.get("priority", "?")
                    usable  = finfo.get("usable", False)
                    src     = finfo.get("source_section", "")
                    impact  = finfo.get("impact", "")
                    val     = finfo.get("value")
                    src_tag = finfo.get("input_source",
                                        ("provided" if usable else "blocked"))
                    if isinstance(src_tag, bool):
                        src_tag = "provided" if usable else "blocked"

                    ico, col = status_icon.get(status,
                                status_icon.get(src_tag, ("•", "#888")))
                    pcol = prio_color.get(priority, "#888")

                    rows.append({
                        "字段": fname,
                        "值": str(val) if val is not None else "—",
                        "状态": f"**{ico}** {status}",
                        "优先级": f"<b style='color:{pcol}'>{priority}</b>",
                        "可用": "✅" if usable else "❌",
                        "来源章节": src[:30] if src else "—",
                        "影响": impact[:35] if impact else "—",
                    })
                if rows:
                    st.dataframe(
                        pd.DataFrame(rows),
                        hide_index=True,
                        width="stretch",
                        column_config={
                            "状态": st.column_config.TextColumn("状态"),
                            "优先级": st.column_config.TextColumn("优先级"),
                        },
                    )
            if clar_questions:
                st.markdown("**📝 澄清问题：**")
                for q in clar_questions:
                    sev = q.get("severity", "P1")
                    sev_icon = "🔴" if sev == "P0" else "🟡"
                    st.markdown(
                        f"{sev_icon} **{q.get('display_name', q.get('field_key', '?'))}**："
                        f"{q.get('question', '—')}"
                    )
                    fmt = q.get("suggested_answer_format", "")
                    if fmt:
                        st.caption(f"   建议格式：{fmt}")

    st.divider()

    # ---- Extraction Confidence Progress Bar ----
    extraction_confidence = profile.get("extraction_confidence")
    if extraction_confidence is not None:
        conf_val = float(extraction_confidence)
        conf_pct = conf_val * 100
        conf_color = "#27ae60" if conf_val >= 0.80 else "#f39c12" if conf_val >= 0.65 else "#e74c3c"
        st.markdown("**📊 提取置信度**")
        conf_col1, conf_col2 = st.columns([3, 1])
        with conf_col1:
            st.progress(conf_val, text=f"{conf_pct:.0f}%")
        with conf_col2:
            if conf_val >= 0.80:
                st.success("✅ 高")
            elif conf_val >= 0.65:
                st.warning("⚠️ 中")
            else:
                st.error("🔴 低")
        st.divider()

    # ---- Profile Summary Cards ----
    st.markdown("**📋 项目画像**")
    m1, m2 = st.columns(2)
    m1.metric("行业", profile.get("industry", "—"))
    m1.metric("地区", profile.get("region", "—"))
    m2.metric("面积", fmt_area(profile.get("warehouse_area")))
    m2.metric("日订单", fmt_count(profile.get("daily_orders")))
    m3, m4 = st.columns(2)
    m3.metric("SKU", fmt_count(profile.get("sku_count")))
    m3.metric("库存", fmt_count(profile.get("inventory")))
    m4.metric("预算", profile.get("budget_level", "—"))
    m4.metric("人工", profile.get("labor_cost_level", "—"))

    # ---- Analysis Markdown Report (Max Enhancement #5) ----
    # Full 13-section tender understanding report
    analysis_markdown = results.get("analysis_markdown") or profile.get("_analysis_report") or ""
    if analysis_markdown:
        with st.expander("📄 招标解析报告（13维度分析）", expanded=False):
            st.markdown(analysis_markdown)

    # ---- Enhanced Extraction Panel ----
    # Replaces the basic field_confidence table with:
    # 1. Quality score (completeness, evidence, readiness)
    # 2. P0/P1 missing items with why_blocking / why_matters
    # 3. Clarification questions with suggested answer format
    # 4. Field-level table with source/origin/priority trace
    extraction_confidence = profile.get("extraction_confidence", 0)
    field_confidence = profile.get("field_confidence", {})
    source_trace = profile.get("source_trace", {})
    warnings = profile.get("warnings", [])

    # Max Enhancement #5: Pull new structured data from pipeline_result
    quality_score    = results.get("quality_score") or profile.get("_quality_score") or {}
    missing_items    = results.get("missing_items") or {}
    clar_questions   = results.get("clarification_questions") or profile.get("_clarification_questions") or []
    normalized_fields = results.get("normalized_fields") or profile.get("_field_traces") or {}

    # Build the full extraction panel
    # Only show if there's something to show
    has_new_data = bool(quality_score or missing_items or clar_questions or normalized_fields)
    has_old_data = bool(field_confidence or warnings)

    if has_new_data or has_old_data:
        with st.expander("🔍 提取结果确认", expanded=False):
            tab_labels = []
            tab_contents = []

            # --- Tab 1: Quality Score ---
            if quality_score:
                compl = quality_score.get("completeness", {})
                p0_cov = compl.get("p0_coverage", 0)
                p1_cov = compl.get("p1_coverage", 0)
                completeness_score = compl.get("total_score", 0)
                evidence_vals = quality_score.get("evidence", {})
                readiness_vals = results.get("readiness") or readiness_data or {}
                readiness_score = readiness_vals.get("readiness_score", 0.0)

                # v0.2: three separate quality scores (not just one "综合评分")
                evidence_score = sum(v for v in evidence_vals.values()) / max(len(evidence_vals), 1)

                st.markdown("**📊 分析质量评分（三项）**")
                s1, s2, s3 = st.columns(3)
                with s1:
                    st.metric("**完整性评分**", f"{completeness_score:.0%}",
                              delta="P0+P1覆盖率" if completeness_score >= 0.8 else "部分缺失")
                with s2:
                    st.metric("**证据评分**", f"{evidence_score:.0%}",
                              delta="explicit来源" if evidence_score >= 0.6 else "含推断/缺失")
                with s3:
                    st.metric("**就绪评分**", f"{readiness_score:.0%}",
                              delta="可进入下游" if readiness_score >= 0.8 else "需澄清后进入")

                # P0/P1 coverage detail
                cov1, cov2 = st.columns(2)
                with cov1:
                    st.caption(f"P0覆盖 {p0_cov:.0%}  |  P1覆盖 {p1_cov:.0%}")

                # Evidence breakdown
                if evidence:
                    ev_rows = []
                    for k, v in evidence.items():
                        icon = {"explicit": "🔬", "inferred": "🔎", "partial": "🔶",
                                "missing": "⬜", "ambiguous": "⚠️"}.get(k, "•")
                        ev_rows.append({"状态": f"{icon} {k}", "占比": f"{v:.0%}"})
                    st.markdown("**证据来源分布**")
                    st.dataframe(pd.DataFrame(ev_rows), hide_index=True, width="stretch")

                # Readiness per downstream module
                if readiness_data:
                    st.markdown("**🚦 下游就绪状态**")
                    rd_rows = []
                    for module, ready in [
                        ("成本测算", readiness_data.get("cost_model_ready")),
                        ("方案设计", readiness_data.get("solution_design_ready")),
                        ("合同审核", readiness_data.get("contract_review_ready")),
                        ("ROI分析", readiness_data.get("roi_analysis_ready")),
                    ]:
                        status = "✅ 就绪" if ready else "❌ 阻塞"
                        rd_rows.append({"下游模块": module, "状态": status})
                    st.dataframe(pd.DataFrame(rd_rows), hide_index=True, width="stretch")

            # --- Tab 2: P0/P1 Missing Items (Max Enhancement #2) ---
            m0_items = missing_items.get("p0") if isinstance(missing_items, dict) else (missing_items or [])
            m1_items = missing_items.get("p1") if isinstance(missing_items, dict) else []

            # Also check for rich missing items from new _build_metadata
            critical_missing = quality_score.get("critical_missing_items") if quality_score else []
            important_missing = quality_score.get("important_missing_items") if quality_score else []

            if m0_items or critical_missing:
                st.markdown(f"**🔴 P0 缺失项（阻塞）**")
                if critical_missing:
                    for item in critical_missing:
                        why = item.get("why_blocking", "—")
                        impact = ", ".join(item.get("downstream_impact", [])[:3])
                        st.markdown(f"- **{item.get('display_name', item.get('field_key', '?'))}** — {why}")
                        if impact:
                            st.caption(f"  影响下游：{impact}")
                else:
                    for item in m0_items:
                        st.markdown(f"- `{item}`")
                st.divider()

            if m1_items or important_missing:
                st.markdown(f"**🟡 P1 缺失项（重要）**")
                if important_missing:
                    for item in important_missing:
                        why = item.get("why_matters", "—")
                        impact = ", ".join(item.get("downstream_impact", [])[:3])
                        st.markdown(f"- **{item.get('display_name', item.get('field_key', '?'))}** — {why}")
                        if impact:
                            st.caption(f"  影响下游：{impact}")
                else:
                    for item in m1_items:
                        st.markdown(f"- `{item}`")

            # --- Tab 3: Clarification Questions (Max Enhancement #3) ---
            if clar_questions:
                st.markdown(f"**❓ 澄清问题清单（{len(clar_questions)}项）**")
                # Sort: P0 first
                sorted_qs = sorted(clar_questions,
                                   key=lambda q: {"P0": 0, "P1": 1, "P2": 2}.get(q.get("severity", "P1"), 9))
                for q in sorted_qs[:10]:  # Show first 10
                    severity = q.get("severity", "P1")
                    icon = "🔴" if severity == "P0" else "🟡"
                    field = q.get("display_name") or q.get("field_key", "通用")
                    question = q.get("question", "—")
                    fmt = q.get("suggested_answer_format", "")
                    st.markdown(f"{icon} **{field}**：{question}")
                    if fmt:
                        st.caption(f"建议回答格式：{fmt}")
                    st.divider()
                if len(clar_questions) > 10:
                    st.caption(f"还有 {len(clar_questions) - 10} 项问题...")

            # --- Tab 4: Field-level table with full trace (Max Enhancement #2) ---
            if normalized_fields:
                st.markdown("**📋 标准化字段详情**")
                rows = []
                for fname, fobj in normalized_fields.items():
                    if not isinstance(fobj, dict):
                        continue
                    val = fobj.get("value")
                    status = fobj.get("status", "—")
                    basis = fobj.get("source_basis", "—")
                    priority = fobj.get("priority", "P2")
                    impact = fobj.get("impact", [])
                    status_icon = {"explicit": "🔬", "inferred": "🔎", "partial": "🔶",
                                   "missing": "⬜", "ambiguous": "⚠️"}.get(status, "•")
                    rows.append({
                        "字段": fname,
                        "值": str(val) if val is not None else "—",
                        "状态": f"{status_icon} {status}",
                        "优先级": priority,
                        "来源依据": basis[:60] + ("…" if len(basis) > 60 else ""),
                        "影响域": ", ".join(impact[:2]) if impact else "—",
                    })
                if rows:
                    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

            # --- Legacy field_confidence table (fallback) ---
            if field_confidence and not normalized_fields:
                st.markdown("**字段置信度（旧格式）**")
                display_keys = [
                    ("industry", "行业"), ("region", "地区"),
                    ("warehouse_area", "仓库面积"), ("daily_orders", "日订单"),
                    ("sku_count", "SKU数"), ("inventory", "库存量"),
                    ("budget_level", "预算"), ("labor_cost_level", "人工成本"),
                ]
                rows = []
                for key, label in display_keys:
                    val = profile.get(key)
                    conf = field_confidence.get(key)
                    src = source_trace.get(key, "—")
                    conf_str = f"{conf * 100:.0%}" if conf else "—"
                    src_icon = "🔤" if src == "rule" else "🤖" if src == "llm" else "🔄" if src == "merged" else "⚙️"
                    val_str = str(val) if val is not None else "—"
                    rows.append({
                        "字段": label, "提取值": val_str, "置信度": conf_str,
                        "来源": f"{src_icon} {src}"
                    })
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

            # Warnings
            if warnings:
                st.markdown("**⚠️ 警告信息**")
                for w in warnings:
                    st.warning(w)

    # ---- QA Verdict Panel ----
    qa_verdict = (
        best.get("qa_verdict") or
        results.get("qa_verdict") or
        st.session_state.get("pipeline_qa_verdict") or
        "UNKNOWN"
    )
    qa_issues = (
        best.get("qa_issues") or
        results.get("qa_issues") or
        st.session_state.get("pipeline_qa_issues") or
        []
    )
    retry_count = (
        best.get("retry_count") or
        results.get("retry_count") or
        st.session_state.get("pipeline_retry_count", 0) or
        0
    )
    retry_history = (
        best.get("retry_history") or
        results.get("retry_history") or
        st.session_state.get("pipeline_retry_history", []) or
        []
    )
    # Store qa_issues in session state for the correction panel to access
    if qa_issues and qa_verdict in ("CONDITIONAL_PASS", "FAIL"):
        st.session_state.pipeline_qa_issues = qa_issues

    # --- QA Verdict Header ---
    st.markdown("**🛡️ QA 审核**")
    v_cols = st.columns([1, 3])
    with v_cols[0]:
        if qa_verdict == "PASS":
            st.success("✔ PASS")
        elif qa_verdict == "CONDITIONAL_PASS":
            st.warning("⚠️ CONDITIONAL PASS")
        elif qa_verdict == "FAIL":
            st.error("✖ FAIL")
        else:
            st.caption(f"QA: `{qa_verdict or 'UNKNOWN'}`")
    with v_cols[1]:
        if qa_verdict == "FAIL":
            retry_history_list = st.session_state.get("pipeline_retry_history") or []
            st.caption(f"已重试：{len(retry_history_list)} 次 | 失败")
        elif qa_verdict == "CONDITIONAL_PASS":
            st.caption("有风险项，请确认后继续")
        elif qa_verdict == "PASS":
            st.caption("所有检查项通过")

    # --- QA Issues Table (P0/P1/P2) ---
    if qa_issues and isinstance(qa_issues, list):
        p0_issues = [i for i in qa_issues if i.get("severity") == "P0"]
        p1_issues = [i for i in qa_issues if i.get("severity") == "P1"]
        p2_issues = [i for i in qa_issues if i.get("severity") == "P2"]

        if p0_issues:
            with st.expander(f"🔴 P0 阻塞问题（{len(p0_issues)}项）— 必须修正", expanded=True):
                for iss in p0_issues:
                    sev_label = iss.get("severity_label") or "❌ P0"
                    field = iss.get("field", "—")
                    rule = iss.get("rule", "")
                    msg = iss.get("message", "—")
                    fix = iss.get("suggested_fix", "")
                    st.markdown(f"**{msg}**")
                    st.markdown(f"字段：`{field}` | 规则：`{rule}`")
                    if fix:
                        st.markdown(f"💡 修正建议：{fix}")
                    st.divider()

        if p1_issues:
            with st.expander(f"🟡 P1 风险项（{len(p1_issues)}项）— 建议确认", expanded=False):
                for iss in p1_issues:
                    msg = iss.get("message", "—")
                    field = iss.get("field", "—")
                    fix = iss.get("suggested_fix", "")
                    st.markdown(f"**{msg}**")
                    st.markdown(f"字段：`{field}`")
                    if fix:
                        st.markdown(f"💡 建议：{fix}")
                    st.divider()

        if p2_issues:
            with st.expander(f"🔵 P2 提示信息（{len(p2_issues)}项）", expanded=False):
                for iss in p2_issues:
                    st.markdown(f"ℹ️ {iss.get('message', '—')}")

    # ---- QA Correction Panel (CONDITIONAL_PASS / FAIL only) ----
    if qa_verdict in ("CONDITIONAL_PASS", "FAIL") and qa_issues:
        pipeline_id = st.session_state.get("_pipeline_id") or results.get("pipeline_id", "")
        if pipeline_id:
            _render_qa_correction_panel(pipeline_id, qa_verdict, qa_issues, profile)

    # ---- Retry History ----
    if retry_history:
        with st.expander("🔁 重试历史", expanded=False):
            for i, r in enumerate(retry_history):
                st.markdown(f"- #{i+1} `{r.get('stage','')}` → {r.get('reason','')[:60]}")

    # ---- ROI Comparison ----
    if comparisons:
        st.markdown("---")
        st.markdown("**⚖️ ROI 对比结果**")
        w1, w2, w3 = st.columns([2, 1, 1])
        with w1:
            w_roi = st.slider("ROI权重", 0.0, 1.0, 0.4, 0.05, key="w_roi", on_change=st.rerun)
        with w2:
            w_pb = st.slider("回本权重", 0.0, 1.0, 0.3, 0.05, key="w_pb", on_change=st.rerun)
        with w3:
            w_sv = st.slider("节省权重", 0.0, 1.0, 0.3, 0.05, key="w_sv", on_change=st.rerun)
        total_w = w_roi + w_pb + w_sv
        w_roi_n = w_roi / total_w if total_w > 0 else 0.33
        w_pb_n = w_pb / total_w if total_w > 0 else 0.33
        w_sv_n = w_sv / total_w if total_w > 0 else 0.34

        def weighted_score(c):
            # Filter None values before max — prevents TypeError: None > None
            max_roi = safe_max(x.get("roi_5y") or 0 for x in comparisons)
            max_pb = safe_max(x.get("payback_years") or 0 for x in comparisons)
            max_sv = safe_max((x.get("annual_labor_saving") or 0) + (x.get("annual_efficiency_saving") or 0) for x in comparisons)
            c_roi = c.get("roi_5y") or 0
            c_pb = c.get("payback_years") or 0
            c_sv = (c.get("annual_labor_saving") or 0) + (c.get("annual_efficiency_saving") or 0)
            return (safe_div(c_roi, max_roi))*100*w_roi_n + (1 - safe_div(c_pb, max_pb))*100*w_pb_n + safe_div(c_sv, max_sv)*100*w_sv_n

        ranked = sorted(comparisons, key=weighted_score, reverse=True)
        top_w = ranked[0]["scenario_name"] if ranked else ""

        rows = []
        for c in ranked:
            ws = weighted_score(c)
            rows.append({
                "方案": ("🥇 " if c.get("scenario_name") == top_w else "  ") + fmt_text(c.get("scenario_name", "")),
                "5年ROI": fmt_percent(c.get("roi_5y")),
                "回本(年)": fmt_years(c.get("payback_years")),
                "Y1 EBITA": fmt_currency(c.get("y1_ebita")),
                "节省(万)": fmt_currency((c.get("annual_labor_saving") or 0) + (c.get("annual_efficiency_saving") or 0)),
                "3年ROI": fmt_percent(c.get("roi_3y")),
                "省人": fmt_count(c.get("headcount_saved"), "人"),
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')

        best = next((c for c in comparisons if c.get("is_best")), comparisons[0])
        k1, k2, k3 = st.columns(3)
        k1.metric("🥇 推荐", fmt_text(best.get("scenario_name"), "—"))
        k1.metric("5年ROI", fmt_percent(best.get("roi_5y")))
        k2.metric("回本周期", fmt_years(best.get("payback_years")))
        k2.metric("Y1 EBITA", fmt_currency(best.get("y1_ebita")))
        k3.metric("年节省", fmt_currency((best.get("annual_labor_saving") or 0) + (best.get("annual_efficiency_saving") or 0)))

        t1, t2, t3 = st.tabs(["📊 投资节省", "📈 ROI", "🕸️ 雷达图"])
        with t1:
            st.plotly_chart(render_compare_bar_chart(ranked), width='stretch')
        with t2:
            st.plotly_chart(render_compare_roi_chart(ranked), width='stretch')
        with t3:
            st.plotly_chart(render_compare_radar(ranked), width='stretch')

    # ---- TOP5 Recommendations ----
    if recs:
        st.markdown("---")
        st.markdown("**🎯 TOP 5 自动化方案**")
        for i, rec in enumerate(recs[:5]):
            medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "📌"
            with st.expander(f"{medal} #{i+1} {rec.get('scenario_name', '—')} — {(rec.get('score') or 0):.0f}分", expanded=(i == 0)):
                ca, cb = st.columns([2, 1])
                with ca:
                    st.markdown(f"**类别:** {rec.get('category','—')} | **风险:** {rec.get('risk','—')}")
                    st.markdown(f"**理由:** {rec.get('reason', '—')}")
                    st.markdown(f"**人工节省:** {fmt_percent(rec.get('labor_saving'))} | "
                              f"**效率提升:** {fmt_percent(rec.get('efficiency_gain'))} | "
                              f"**投资:** {rec.get('capex_range', '—')}")
                with cb:
                    st.plotly_chart(render_score_gauge(rec.get("score", 0)), width='stretch',
                                   key=f"res_gauge_{i}")

    # ---- PDF Report (Preview + Download) ----
    st.markdown("---")
    st.markdown("**📄 PDF 方案报告**")
    pdf_url = st.session_state.get("pipeline_pdf_url")
    pdf_bytes = st.session_state.get("pipeline_pdf_bytes")

    # Fetch if not yet loaded
    if not pdf_bytes and pdf_url:
        try:
            pr = requests.get(f"{API_BASE_URL}{pdf_url}", timeout=30)
            if pr.status_code == 200:
                pdf_bytes = pr.content
        except Exception:
            pass

    pdf_col_preview, pdf_col_download = st.columns([3, 1])

    with pdf_col_preview:
        if pdf_bytes:
            import base64
            b64 = base64.b64encode(pdf_bytes).decode("utf-8")
            pdf_iframe = f"""
            <iframe src="data:application/pdf;base64,{b64}"
                    width="100%" height="720" type="application/pdf"
                    style="border:none; border-radius:8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
            </iframe>
            """
            st.markdown(pdf_iframe, unsafe_allow_html=True)
        else:
            st.info("⬆️ Pipeline 完成后 PDF 报告将显示在此")

    with pdf_col_download:
        if pdf_bytes:
            st.success("已生成")
            st.download_button(
                "⬇️ 下载 PDF",
                data=pdf_bytes,
                file_name="solution_report.pdf",
                mime="application/pdf",
                width="stretch",
            )
        else:
            st.warning("PDF未生成")


# =============================================================================
# Shared helpers (visible to all app_mode branches)
# =============================================================================
def _switch_to_pipeline_run(pid):
    """Cleanly switch to Pipeline Run tab and start polling."""
    st.session_state._app_mode_idx = 2
    st.session_state._pipeline_id = pid
    st.session_state.pipeline_state = "polling"
    st.session_state.pipeline_comparisons = None
    st.session_state.pipeline_stages = None
    st.session_state._results_refresh_ts = None
    st.session_state.cw_recompute_result = None
    st.rerun()


# =============================================================================
# Mode 1: Single Scenario
# =============================================================================
if app_mode == "📋 方案生成":
    single_submitted = False

    with st.form("project_form"):
        st.subheader("📋 项目信息输入")
        project_name = st.text_input("项目名称", value="新建项目-001")
        industry = st.selectbox("行业类型",
            options=["电商", "3PL", "零售", "制造", "快递", "医药", "食品", "生鲜"], index=0)
        region = st.selectbox("所在区域",
            options=["华东", "华南", "华北", "华中", "西部"], index=0)

        st.markdown("**仓库参数**")
        warehouse_area = st.number_input("仓库面积 (㎡)", min_value=500, max_value=500000,
                                         value=20000, step=1000)
        sku_count = st.number_input("SKU数量", min_value=100, max_value=1000000,
                                     value=30000, step=1000)
        daily_orders = st.number_input("日均订单量", min_value=50, max_value=500000,
                                       value=5000, step=100)
        inventory = st.number_input("库存量 (件)", min_value=1000, max_value=10000000,
                                     value=500000, step=10000)

        st.markdown("**成本与预算**")
        labor_cost_level = st.select_slider("人工成本水平", options=["低", "中", "高"], value="中")
        budget_level = st.select_slider("自动化预算", options=["低", "中", "高"], value="中")
        automation_expectation = st.select_slider("自动化期望", options=["低", "中", "高"], value="中")

        single_submitted = st.form_submit_button("🚀 生成解决方案",
                                                  width='stretch', type="primary")

    if single_submitted:
        profile = {
            "industry": industry, "warehouse_area": float(warehouse_area),
            "sku_count": int(sku_count), "daily_orders": int(daily_orders),
            "inventory": int(inventory), "labor_cost_level": labor_cost_level,
            "budget_level": budget_level, "automation_expectation": automation_expectation,
        }

        with st.spinner("AI正在分析您的项目需求..."):
            rec_result, err1 = call_api("/api/recommend", profile)
            scenario_id = (rec_result["recommendations"][0]["scenario_id"]
                           if rec_result and rec_result.get("recommendations") else None)
            cost_result, err2 = call_api("/api/cost",
                                          {**profile, "region": region, "selected_scenario_id": scenario_id})

        if err1:
            st.error(err1)
        elif err2:
            st.error(err2)
        elif rec_result and cost_result:
            st.success(f"✅ 方案生成完成 | {project_name} | {industry} | {region}")
            tab1, tab2, tab3 = st.tabs(["🎯 方案推荐", "💰 成本分析", "📊 综合报告"])

            with tab1:
                st.subheader("自动化场景推荐")
                st.info(rec_result.get("analysis_summary", ""))
                recommendations = rec_result.get("recommendations", [])
                if recommendations:
                    top = recommendations[0]
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("首选方案", fmt_text(top.get("scenario_name"), "—"))
                    c2.metric("匹配评分", f"{(top.get('score') or 0):.0f}/100")
                    c3.metric("人工节省", f"{int((top.get('labor_saving') or 0)*100)}%")
                    c4.metric("效率提升", f"{int((top.get('efficiency_gain') or 0)*100)}%")
                    st.divider()
                    for i, rec in enumerate(recommendations):
                        with st.expander(
                            f"{'🥇' if i==0 else '🥈' if i==1 else '🥉' if i==2 else '📌'} "
                            f"#{i+1} {rec.get('scenario_name', '—')} — 评分: {(rec.get('score') or 0):.0f}分",
                            expanded=(i == 0),
                        ):
                            col_a, col_b = st.columns([2, 1])
                            with col_a:
                                st.markdown(f"**类别:** {rec.get('category', '—')}")
                                st.markdown(f"**推荐理由:** {rec.get('reason', '—')}")
                                st.markdown(f"**风险评估:** {rec.get('risk', '—')}")
                                st.markdown(f"**投资范围:** {rec.get('capex_range', '—')}")
                            with col_b:
                                st.plotly_chart(render_score_gauge(rec.get("score", 0)),
                                                width='stretch', key=f"score_gauge_{i}")

            with tab2:
                st.subheader("成本与ROI分析")
                cost_data = cost_result["cost_breakdown"]
                st.info(cost_result.get("summary", ""))
                c1, c2, c3, c4, c5, c6 = st.columns(6)
                c1.metric("总投资", fmt_currency(safe_div(cost_data.get("automation_capex"), 10000), "¥", 0, "—") + "万")
                c2.metric("年节省人工", fmt_currency(safe_div(cost_data.get("automation_savings_annual"), 10000), "¥", 1, "—") + "万")
                c3.metric("5年ROI", fmt_number(cost_data.get('roi'), 1, '—') + 'x')
                c4.metric("回本周期", fmt_years(cost_data.get('payback_years'), 1, '—'))
                c5.metric("Y1 EBITA", fmt_currency(cost_data.get("y1_ebita")))
                c6.metric("节省人数", fmt_count(cost_data.get("headcount_saved"), "人"))
                st.divider()
                cc1, cc2 = st.columns(2)
                with cc1:
                    st.plotly_chart(render_cost_chart(cost_data), width='stretch')
                with cc2:
                    st.plotly_chart(render_roi_chart(cost_data), width='stretch')
                st.subheader("优化建议")
                for r in cost_result.get("recommendations", []):
                    st.markdown(f"- {r}")

            with tab3:
                st.subheader("项目综合报告")
                top_rec = (rec_result["recommendations"][0]
                           if rec_result.get("recommendations") else {})
                cost_d = cost_result["cost_breakdown"]
                st.markdown(f"""
**项目:** {project_name} | **行业:** {industry} | **地区:** {region}

**首选方案:** {top_rec.get('scenario_name', 'N/A')} — {top_rec.get('reason', '')}

**投资回报摘要:**
- 自动化投资: {fmt_currency(cost_d.get('automation_capex') or cost_d.get('capex_estimate'))}
- 年节省人工: ¥{fmt_number(safe_div(cost_d.get('automation_savings_annual'), 10000), 1, '—')}万元
- Y1 EBITA: {fmt_currency(cost_d.get('y1_ebita'))}
- 净年度收益: ¥{fmt_number(safe_div(cost_d.get('net_annual_benefit'), 10000), 1, '—')}万元
- 5年ROI: {fmt_number(cost_d.get('roi'), 1, '—')}倍 | 回本周期: {fmt_years(cost_d.get('payback_years'), 1, '—')}年
- 预计减少人员: {fmt_count(cost_d.get('headcount_saved'), '人')}
""")
                report_data = {
                    "project_name": project_name, "profile": profile,
                    "recommendations": rec_result.get("recommendations", []),
                    "cost_breakdown": cost_result.get("cost_breakdown", {}),
                    "summary": cost_result.get("summary", ""),
                }
                st.download_button("📥 下载JSON报告",
                                   data=json.dumps(report_data, ensure_ascii=False, indent=2),
                                   file_name=f"{project_name}_solution.json",
                                   mime="application/json")
                if st.button("📄 生成并下载PDF方案报告", type="primary", width='stretch'):
                    with st.spinner("正在生成PDF报告..."):
                        pdf_payload = {
                            "project_name": project_name, "industry": industry,
                            "warehouse_area": float(warehouse_area), "sku_count": int(sku_count),
                            "daily_orders": int(daily_orders), "inventory": int(inventory),
                            "labor_cost_level": labor_cost_level, "budget_level": budget_level,
                            "automation_expectation": automation_expectation, "region": region,
                        }
                        try:
                            resp = requests.post(f"{API_BASE_URL}/api/report",
                                                 json=pdf_payload, timeout=60)
                            if resp.status_code == 200:
                                st.success("✅ PDF报告已生成！")
                                st.download_button("⬇️ 点击下载PDF方案建议书",
                                                   data=resp.content,
                                                   file_name=f"{project_name}_方案建议书.pdf",
                                                   mime="application/pdf")
                            elif resp.status_code == 503:
                                st.error("PDF服务暂不可用，请确保后端已安装 jinja2 和 weasyprint")
                            else:
                                st.error(f"生成失败: {resp.status_code}")
                        except Exception as e:
                            st.error(f"连接错误: {e}")
    else:
        _render_welcome_single()

# =============================================================================
# Mode 2: Multi-Scenario Comparison
# =============================================================================
elif app_mode == "⚖️ 多方案对比":
    compare_submitted = False

    with st.form("compare_form"):
        st.subheader("⚖️ 多方案对比")
        project_name_cmp = st.text_input("项目名称", value="方案对比-001")
        industry_cmp = st.selectbox("行业类型",
            options=["电商", "3PL", "零售", "制造", "快递", "医药", "食品", "生鲜"], index=0)
        region_cmp = st.selectbox("所在区域",
            options=["华东", "华南", "华北", "华中", "西部"], index=0)

        st.markdown("**仓库参数**")
        warehouse_area_cmp = st.number_input("仓库面积 (㎡)", min_value=500, max_value=500000,
                                             value=20000, step=1000)
        sku_count_cmp = st.number_input("SKU数量", min_value=100, max_value=1000000,
                                         value=30000, step=1000)
        daily_orders_cmp = st.number_input("日均订单量", min_value=50, max_value=500000,
                                            value=5000, step=100)
        inventory_cmp = st.number_input("库存量 (件)", min_value=1000, max_value=10000000,
                                         value=500000, step=10000)

        st.markdown("**成本与预算**")
        labor_cost_level_cmp = st.select_slider("人工成本水平", options=["低", "中", "高"], value="中")
        budget_level_cmp = st.select_slider("自动化预算", options=["低", "中", "高"], value="中")

        st.markdown("**选择对比方案（2-5个）**")
        ALL_SCENARIOS = [
            (1, "AMR拣选辅助"),    (2, "GTP货到人系统"),   (3, "输送分拣线"),
            (4, "自动贴标系统"),   (5, "立体仓库AS/RS"),   (6, "自动化输送线"),
            (7, "视觉识别质检"),   (8, "拆码垛机器人"),    (9, "WMS仓储管理系统"),
            (10, "AGV搬运系统"),  (11, "自动包装线"),    (12, "冷链自动化仓储"),
            (13, "跨带分拣机"),   (14, "货架式密集存储"),  (15, "自动化退货处理"),
        ]
        selected_labels = st.multiselect(
            "勾选要对比的方案",
            options=[label for _, label in ALL_SCENARIOS],
            default=["AMR拣选辅助", "GTP货到人系统", "输送分拣线"],
            help="选择2-5个方案进行横向对比",
        )
        selected_ids = [sid for sid, label in ALL_SCENARIOS if label in selected_labels]
        compare_submitted = st.form_submit_button("⚖️ 开始对比",
                                                  width='stretch', type="primary")

    if compare_submitted:
        if len(selected_ids) < 2:
            st.error("请至少选择2个方案进行对比")
        else:
            profile_cmp = {
                "industry": industry_cmp, "warehouse_area": float(warehouse_area_cmp),
                "sku_count": int(sku_count_cmp), "daily_orders": int(daily_orders_cmp),
                "inventory": int(inventory_cmp), "labor_cost_level": labor_cost_level_cmp,
                "budget_level": budget_level_cmp, "automation_expectation": "中",
            }
            payload = {**profile_cmp, "region": region_cmp, "scenario_ids": selected_ids}

            with st.spinner("正在计算多方案ROI对比..."):
                cmp_result, err = call_api("/api/compare", payload)

            if err:
                st.error(err)
            elif cmp_result:
                comparisons = cmp_result.get("comparisons", [])
                best_id = cmp_result.get("best_scenario_id")
                best_name = next((c["scenario_name"] for c in comparisons if c["scenario_id"] == best_id), "N/A")
                st.success(f"✅ 对比完成 | {len(comparisons)}个方案 | 最佳: {best_name}")
                st.info(cmp_result.get("analysis_summary", ""))

                # Summary table
                st.subheader("📊 方案对比总览")
                rows = []
                for c in comparisons:
                    rows.append({
                        "方案": ("✅ " if c.get("is_best") else "  ") + fmt_text(c.get("scenario_name")),
                        "类别": fmt_text(c.get("category", "—")),
                        "投资 (万)": fmt_currency(c.get("automation_capex") or 0),
                        "年节省 (万)": fmt_currency(c.get("annual_saving") or 0),
                        "年维护 (万)": fmt_currency(c.get("annual_maintenance") or 0),
                        "净年收益 (万)": fmt_currency(c.get("net_annual_benefit") or 0),
                        "Y1 EBITA": fmt_currency(c.get("y1_ebita")),
                        "5年ROI": fmt_percent(c.get("roi_5y")),
                        "回本周期": fmt_years(c.get("payback_years")),
                        "省人数": fmt_count(c.get("headcount_saved"), "人"),
                    })
                st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)

                # KPI row
                best = next((c for c in comparisons if c.get("is_best")), comparisons[0] if comparisons else {})
                c1, c2, c3, c4, c5 = st.columns(5)
                c1.metric("🥇 最佳方案", fmt_text(best.get("scenario_name"), "—"))
                c2.metric("5年ROI", fmt_percent(best.get("roi_5y")))
                c3.metric("回本周期", fmt_years(best.get("payback_years")))
                c4.metric("Y1 EBITA", fmt_currency(best.get("y1_ebita")))
                c5.metric("年节省", fmt_currency((best.get("annual_labor_saving") or 0) + (best.get("annual_efficiency_saving") or 0)))

                st.divider()
                st.subheader("📈 可视化对比")
                t1, t2, t3 = st.tabs(["投资与年节省", "5年ROI对比", "综合雷达图"])
                with t1:
                    st.plotly_chart(render_compare_bar_chart(comparisons), width='stretch')
                with t2:
                    st.plotly_chart(render_compare_roi_chart(comparisons), width='stretch')
                with t3:
                    st.plotly_chart(render_compare_radar(comparisons), width='stretch')

                st.divider()
                st.subheader("📋 详细参数")
                det = []
                for c in comparisons:
                    det.append({
                        "方案": c.get("scenario_name", "—"),
                        "类别": c.get("category", "—"),
                        "自动化投资": "¥" + fmt_number(safe_div(c.get("automation_capex"), 10000), 0, "—") + "万",
                        "Y1 EBITA": fmt_currency(c.get("y1_ebita")),
                        "5年累计净收益": "¥" + fmt_number(safe_div(c.get("five_year_net_benefit"), 10000), 1, "—") + "万",
                        "5年ROI": fmt_number(c.get("roi_5y"), 1, "—") + "x",
                        "回本周期": fmt_years(c.get("payback_years"), 1, "—"),
                        "节省人数": f"{fmt_count(c.get('headcount_saved'), '')}/{fmt_count(c.get('headcount_required'), '')}",
                    })
                st.dataframe(pd.DataFrame(det), width='stretch', hide_index=True)
    else:
        _render_welcome_compare()

# =============================================================================
# Mode 3: Pipeline Run
# =============================================================================
elif app_mode == "🚀 Pipeline Run":
    st.markdown('<div class="main-header">🚀 Pipeline Run — 端到端投标方案生成</div>', unsafe_allow_html=True)

    # =====================================================================
    # 3-Column Layout: [Left: Input] [Center: Execution Status] [Right: Results]
    # =====================================================================
    col_left, col_center, col_right = st.columns([1, 2, 2])

    with col_left:
        st.markdown("### 📂 招标文件")

        uploaded_files = st.file_uploader(
            "上传招标文件",
            type=["pdf", "txt", "docx"],
            accept_multiple_files=True,
            help="支持 PDF / TXT / Word，多文件自动合并",
        )
        all_texts = []
        if uploaded_files:
            file_names = ", ".join(f.name for f in uploaded_files)
            st.success(f"已上传 {len(uploaded_files)} 个文件: {file_names}")
            with st.spinner("解析中..."):
                texts = []
                for f in uploaded_files:
                    t = extract_tender_text(f)
                    if t and len(t) > 20:
                        texts.append(t)
                tender_text = "\n\n--- {f.name} ---\n\n".join(texts) if texts else ""
                all_texts = texts
            if tender_text:
                total_chars = sum(len(t) for t in texts)
                st.session_state.tender_text = tender_text
                st.info(f"✅ {len(texts)}个文件，{total_chars}字符")
                with st.expander("🔍 预览文本", expanded=False):
                    preview_text = tender_text[:800] + ("..." if len(tender_text) > 800 else "")
                    # Highlight key fields
                    import re
                    highlights = {
                        "仓库面积": r"(\d+\.?\d*)\s*(㎡|平方米|平方|m2|m²)",
                        "SKU数量": r"(SKU|sku)[：:]?\s*(\d[\d,]+)",
                        "日订单": r"(日均|每天|每日)\s*订单[：:]?\s*(\d[\d,]+)",
                        "行业": r"(行业|产业)[：:]?\s*([\u4e00-\u9fa5]+)",
                    }
                    st.text(preview_text)
                    # Show detected fields
                    detected = {}
                    for field, pattern in highlights.items():
                        m = re.search(pattern, preview_text)
                        if m:
                            detected[field] = m.group(0)
                    if detected:
                        st.markdown("**🏷️ 识别到的关键字段：**")
                        dc1, dc2 = st.columns(2)
                        for idx, (field, val) in enumerate(detected.items()):
                            col = dc1 if idx % 2 == 0 else dc2
                            col.markdown(f"- **{field}**: `{val}`")
            else:
                st.warning("解析失败，请直接填参数")
                st.session_state.tender_text = ""
        else:
            st.session_state.tender_text = ""

        tender_text_manual = st.text_area(
            "或粘贴摘要",
            placeholder="粘贴关键信息（面积/SKU/订单量/行业/预算）...",
            height=80,
        )
        final_tender_text = (st.session_state.get("tender_text", "") or "").strip() + "\n" + tender_text_manual

        # ── Quick Entry Expander ──────────────────────────────────────────────
        with st.expander("⚡ 快速录入模式（覆盖标书提取字段）", expanded=False):
            st.caption("只有在此处点击启用并填写字段后，才会覆盖标书提取结果")
            quick_entry_check = st.checkbox(
                "启用快速录入（将覆盖标书提取的同名字段）",
                value=False,
                help="勾选后，显式填写的字段将覆盖标书提取结果。未填写的字段仍使用标书提取值。",
            )
            if quick_entry_check:
                industry_p = st.selectbox(
                    "行业", options=[
                        "AUTOMOTIVE（汽车/零部件）", "ELECTRONICS（电子/VMI）",
                        "FMCG（快消/零售）", "MANUFACTURING（制造）", "GENERIC_3PL（通用3PL）",
                    ], index=4,
                )
                region_p = st.selectbox("区域", options=["华东", "华南", "华北", "华中", "西部"], index=0)
                warehouse_area_p = st.number_input("面积 (㎡)", min_value=500, max_value=500000, value=20000, step=1000)
                sku_count_p = st.number_input("SKU数量", min_value=100, max_value=1000000, value=30000, step=1000)
                daily_orders_p = st.number_input("日订单", min_value=50, max_value=500000, value=5000, step=100)
                inventory_p = st.number_input("库存量（选填）", min_value=0, max_value=10000000, value=0, step=10000)
                automation_expectation_p = st.select_slider("自动化期望（选填）", options=["低", "中", "高"], value="中")
                # Normalize industry value
                industry_map = {
                    "AUTOMOTIVE（汽车/零部件）": "AUTOMOTIVE",
                    "ELECTRONICS（电子/VMI）": "ELECTRONICS",
                    "FMCG（快消/零售）": "FMCG",
                    "MANUFACTURING（制造）": "MANUFACTURING",
                    "GENERIC_3PL（通用3PL）": "GENERIC_3PL",
                }
                industry_normalized = industry_map.get(industry_p, "GENERIC_3PL")
                # Build overrides: only non-None, non-default values
                overrides = {}
                if industry_normalized:
                    overrides["industry"] = industry_normalized
                if region_p:
                    overrides["region"] = region_p
                if warehouse_area_p and warehouse_area_p > 0:
                    overrides["warehouse_area"] = float(warehouse_area_p)
                if sku_count_p and sku_count_p > 0:
                    overrides["sku_count"] = int(sku_count_p)
                if daily_orders_p and daily_orders_p > 0:
                    overrides["daily_orders"] = int(daily_orders_p)
                if inventory_p and inventory_p > 0:
                    overrides["inventory"] = int(inventory_p)
                if automation_expectation_p:
                    overrides["automation_expectation"] = automation_expectation_p

                st.session_state._pipeline_params = {
                    "tender_text": final_tender_text,
                    "quick_entry_enabled": True,
                    "quick_entry_overrides": overrides if overrides else None,
                }
            else:
                st.session_state._pipeline_params = {
                    "tender_text": final_tender_text,
                    "quick_entry_enabled": False,
                    "quick_entry_overrides": None,
                }

        # ---- History Panel ----
        with st.expander("📋 历史任务", expanded=False):
            try:
                hist_resp = requests.get(f"{API_BASE_URL}/api/pipeline/history", timeout=5)
                if hist_resp.status_code == 200:
                    hist_data = hist_resp.json().get("runs", [])
                    if hist_data:
                        # Sort newest first
                        hist_data = sorted(hist_data, key=lambda x: x.get("created_at", ""), reverse=True)
                        for run in hist_data[:15]:
                            pid = run.get("pipeline_id", "")
                            status = run.get("status", "")
                            verdict = run.get("qa_verdict", "") or ""
                            dur = run.get("total_duration_seconds")
                            created = run.get("created_at", "")
                            if created and len(created) >= 19:
                                try:
                                    from datetime import timezone, timedelta
                                    utc_dt = datetime.fromisoformat(created[:19].replace("Z", "+00:00"))
                                    cst = utc_dt + timedelta(hours=8)
                                    created = cst.strftime("%m-%d %H:%M")  # UTC+8
                                except Exception:
                                    created = created[5:16]
                            dur_str = f"{dur:.1f}s" if dur else "—"
                            icon = "✅" if status == "COMPLETE" else "❌" if status == "FAILED" else "⏳"
                            cols_h = st.columns([3, 1, 1])
                            with cols_h[0]:
                                st.caption(f"{icon} `{pid}`")
                            with cols_h[1]:
                                st.caption(f"{verdict or status}")
                            with cols_h[2]:
                                if st.button("加载", key=f"load_{pid}", width='stretch'):
                                    st.session_state._pipeline_id = pid
                                    st.session_state.pipeline_state = "done"
                                    try:
                                        full = requests.get(f"{API_BASE_URL}/api/pipeline/status/{pid}", timeout=10)
                                        if full.status_code == 200:
                                            fd = full.json()
                                            st.session_state.pipeline_result = fd
                                            st.session_state.pipeline_profile = fd.get("profile", {})
                                            st.session_state.pipeline_recs = fd.get("recommendations", [])
                                            st.session_state.pipeline_comparisons = fd.get("comparisons", [])
                                            st.session_state.pipeline_stages = fd.get("stages", [])
                                            st.session_state.pipeline_qa_verdict = fd.get("qa_verdict", "UNKNOWN")
                                            st.session_state.pipeline_qa_issues = fd.get("qa_issues", [])
                                            st.session_state.pipeline_pdf_url = fd.get("pdf_download_url")
                                            st.session_state.pipeline_pdf_bytes = None
                                            st.session_state.pipeline_retry_history = fd.get("retry_history", [])
                                            st.rerun()
                                    except Exception:
                                        st.error("无法加载任务详情，请检查后端是否运行")
                    else:
                        st.caption("暂无历史任务")
                else:
                    st.caption("无法加载历史")
            except Exception:
                st.caption("后端未启动")

    with col_center:
        st.markdown("### ⚙️ 执行状态")

        # ---- Polling UI (show when polling) ----
        if st.session_state.get("pipeline_state") == "polling":
            pipeline_id = st.session_state.get("_pipeline_id")
            status_placeholder = st.empty()
            log_placeholder = st.empty()
            correction_placeholder = st.empty()

            # Manual control buttons
            ctl1, ctl2 = st.columns([1, 1])
            with ctl1:
                if st.button("🔄 手动刷新状态", width='stretch'):
                    st.rerun()
            with ctl2:
                if st.button("⏸️ 暂停自动刷新", width='stretch'):
                    st.session_state.pipeline_state = "done"
                    st.info("已暂停自动刷新，可点击「开始运行 Pipeline」继续。")
                    st.rerun()

            try:
                resp = requests.get(f"{API_BASE_URL}/api/pipeline/status/{pipeline_id}", timeout=10)
                if resp.status_code == 404:
                    st.error(f"Pipeline {pipeline_id} 未找到")
                    st.stop()
                status_data = resp.json()
                pipeline_status = status_data.get("status", "UNKNOWN")
                stages = status_data.get("stages", [])

                stage_map = {s["stage"]: s for s in stages}

                done_count = sum(1 for s in stages if s.get("status") == "DONE")
                progress_pct = int(done_count / max(len(stages), 1) * 100)
                status_placeholder.progress(progress_pct)

                step_labels = {
                    "1_extraction": "① 解析招标",
                    "2_recommendation": "② 推荐引擎",
                    "3_cost_comparison": "③ ROI计算",
                    "4_qa_review": "④ QA审核",
                    "5_pdf_report": "⑤ PDF报告",
                }
                step_cols = st.columns(5)
                for i, (stage_name, label) in enumerate(step_labels.items()):
                    s = stage_map.get(stage_name, {})
                    s_status = s.get("status", "PENDING")
                    icon = "✅" if s_status == "DONE" else "❌" if s_status == "FAILED" else "⏳"
                    dur = s.get("duration_seconds", 0)
                    with step_cols[i]:
                        st.markdown(f"**{icon} {label}**")
                        if dur:
                            st.caption(f"  {dur:.1f}s")
                        if s.get("error"):
                            with st.expander("详情"):
                                st.text(s["error"][:200])

                log_lines = []
                for s in stages:
                    label = step_labels.get(s.get("stage", ""), s.get("stage", ""))
                    if s.get("status") == "DONE":
                        log_lines.append(f"✅ {label} 完成 ({s.get('duration_seconds') or 0:.0f}s)")
                    elif s.get("status") == "FAILED":
                        log_lines.append(f"❌ {label}: {s.get('error', '')[:80]}")
                    elif s.get("status") == "RUNNING":
                        log_lines.append(f"⏳ {label}...")
                log_placeholder.text("\n".join(log_lines[-15:]) if log_lines else "等待开始...")

                # Low-confidence correction
                s1 = stage_map.get("1_extraction", {})
                s2 = stage_map.get("2_recommendation", {})
                if s1.get("status") == "DONE" and s2.get("status") in ("PENDING", None):
                    prof = status_data.get("profile", {})
                    missing_p0 = prof.get("missing_p0", [])
                    confidence = prof.get("extraction_confidence", 0) or 0
                    if missing_p0 or confidence < 0.65:
                        correction_placeholder.warning(
                            f"⚠️ 置信度 {confidence:.0%}" + (" | P0缺失" if missing_p0 else "")
                        )
                        with correction_placeholder.form("ext_corr", clear_on_submit=False):
                            c1, c2 = st.columns(2)
                            with c1:
                                industries = ["电商", "3PL", "零售", "制造", "快递", "医药", "食品", "生鲜"]
                                ind_idx = 0
                                cur = prof.get("industry", "电商")
                                if cur in industries:
                                    ind_idx = industries.index(cur)
                                ind_c = st.selectbox("行业", industries, index=ind_idx)
                                area_c = st.number_input("面积", value=int(prof.get("warehouse_area", 20000) or 20000), step=1000)
                            with c2:
                                sku_c = st.number_input("SKU", value=int(prof.get("sku_count", 30000) or 30000), step=1000)
                                ord_c = st.number_input("日订单", value=int(prof.get("daily_orders", 5000) or 5000), step=100)
                            c3, c4 = st.columns(2)
                            with c3:
                                bud_c = st.select_slider("预算", options=["低", "中", "高"], value=prof.get("budget_level", "中"))
                            with c4:
                                lab_c = st.select_slider("人工", options=["低", "中", "高"], value=prof.get("labor_cost_level", "中"))
                            if missing_p0:
                                st.markdown(f"**⚠️ P0缺失：** {', '.join(missing_p0)}")
                            sub = st.form_submit_button("✅ 确认并继续", width='stretch', type="primary")
                            if sub:
                                overrides = {"industry": ind_c, "warehouse_area": float(area_c),
                                             "sku_count": int(sku_c), "daily_orders": int(ord_c),
                                             "labor_cost_level": lab_c, "budget_level": bud_c,
                                             "automation_expectation": "中"}
                                try:
                                    requests.patch(f"{API_BASE_URL}/api/pipeline/{pipeline_id}",
                                                   json={"profile_overrides": overrides}, timeout=10)
                                except Exception:
                                    pass
                                st.session_state._skip_correction = True
                                st.rerun()
                        st.stop()

                st.session_state._skip_correction = False

                if pipeline_status == "COMPLETE":
                    st.success("✅ Pipeline 执行完成！")
                    st.session_state.pipeline_profile = status_data.get("profile", {})
                    st.session_state.pipeline_recs = status_data.get("recommendations", [])
                    st.session_state.pipeline_comparisons = status_data.get("comparisons", [])
                    st.session_state.pipeline_pdf_url = status_data.get("pdf_download_url")
                    st.session_state.pipeline_qa_verdict = status_data.get("qa_verdict", "UNKNOWN")
                    st.session_state.pipeline_qa_issues = status_data.get("qa_issues", [])
                    st.session_state.pipeline_retry_count = status_data.get("retry_count", 0)
                    st.session_state.pipeline_risk_flags = status_data.get("risk_flags", [])
                    st.session_state.pipeline_retry_history = status_data.get("retry_history", [])
                    st.session_state.pipeline_stages = status_data.get("stages", [])
                    # Show stage breakdown with retry buttons in center column
                    _render_stage_retry_section(pipeline_id, st.session_state.pipeline_stages, key_prefix="center_")
                    st.session_state.pipeline_state = "done"
                    st.session_state.app_mode = "view_results"
                    st.rerun()
                elif pipeline_status == "FAILED":
                    st.error(f"❌ 失败: {status_data.get('error', '未知错误')}")
                    st.session_state.pipeline_stages = status_data.get("stages", [])
                    # Show stage breakdown with retry buttons in center column
                    _render_stage_retry_section(pipeline_id, st.session_state.pipeline_stages, key_prefix="center_")
                    st.session_state.pipeline_state = "done"
                    st.session_state.app_mode = "view_results"
                    st.rerun()
                else:
                    # Auto-rerun after 2s to keep polling backend status
                    time.sleep(2)
                    st.rerun()

            except requests.exceptions.ConnectionError:
                st.error("⚠️ 无法连接后端，请确保后端已启动")
                st.stop()
            except Exception as e:
                st.error(f"轮询异常: {e}")
                st.stop()

        # ---- Idle / Done: Show run button + step preview + stage breakdown ----
        if st.session_state.get("pipeline_state") in (None, "done"):
            # If we have stored stage data (from a completed pipeline), show the breakdown
            stored_stages = st.session_state.get("pipeline_stages", [])
            stored_pid = st.session_state.get("_pipeline_id")
            if stored_stages and stored_pid:
                _render_stage_retry_section(stored_pid, stored_stages, key_prefix="idle_")
                st.divider()

            # Show step preview cards
            step_info = {
                "① 解析招标": "提取面积/SKU/行业/痛点",
                "② 推荐引擎": "匹配自动化场景",
                "③ ROI计算": "成本对比 + 5年ROI",
                "④ QA审核": "质量检查 & 风险评估",
                "⑤ PDF报告": "生成专业投标方案书",
            }
            for label, desc in step_info.items():
                with st.container():
                    ic, tx = st.columns([1, 4])
                    with ic:
                        st.markdown("⬜")
                    with tx:
                        st.markdown(f"**{label}**")
                        st.caption(desc)
            st.divider()

            if st.button("🚀 开始运行 Pipeline", type="primary", width='stretch',
                         help="异步执行，不阻塞页面"):
                params = st.session_state.get("_pipeline_params", {})
                tender_text = params.get("tender_text", "") or ""
                # Only inject overrides when quick-entry mode is explicitly enabled
                quick_entry_enabled = params.get("quick_entry_enabled", False)
                overrides = params.get("quick_entry_overrides") if quick_entry_enabled else None
                try:
                    run_resp = requests.post(
                        f"{API_BASE_URL}/api/pipeline/run",
                        json={"tender_document": tender_text,
                              "project_profile_overrides": overrides,
                              "compare_scenario_ids": None,
                              "generate_pdf": True,
                              "api_base_url": API_BASE_URL},
                        timeout=15,
                    )
                    if run_resp.status_code == 200:
                        result = run_resp.json()
                        st.session_state.pipeline_state = "polling"
                        st.session_state._pipeline_id = result.get("pipeline_id")
                        st.session_state._skip_correction = False
                        st.rerun()
                    else:
                        st.error(f"启动失败: {run_resp.status_code}")
                except Exception as e:
                    st.error(f"无法连接后端: {e}")
                st.stop()

    with col_right:
        st.markdown("### 📊 执行结果")
        # Show debug if set
        if st.session_state.get("_debug_info"):
            st.code(st.session_state._debug_info)

        if st.session_state.get("pipeline_state") == "done":
            comparisons = st.session_state.get("pipeline_comparisons")
            if not comparisons:  # None or []
                # Refetch from API if pipeline may have updated after clarification
                stored_pid = st.session_state.get("_pipeline_id") or ""
                last_refresh = st.session_state.get("_results_refresh_ts") or 0
                now_ts = int(time.time())
                refetch_ok = False
                if stored_pid and now_ts - last_refresh > 3:
                    st.session_state._results_refresh_ts = now_ts
                    try:
                        resp = requests.get(f"{API}/api/pipeline/status/{stored_pid}", timeout=10)
                        if resp.ok:
                            fresh = resp.json()
                            st.session_state.pipeline_comparisons = fresh.get("comparisons")
                            st.session_state.pipeline_profile = fresh.get("profile", {})
                            st.session_state.pipeline_recs = fresh.get("recommendations", [])
                            st.session_state.pipeline_pdf_url = fresh.get("pdf_download_url")
                            st.session_state.pipeline_qa_verdict = fresh.get("qa_verdict", "UNKNOWN")
                            st.session_state.pipeline_stages = fresh.get("stages", [])
                            st.session_state.pipeline_result = fresh
                            comparisons = fresh.get("comparisons")
                            refetch_ok = True
                    except Exception:
                        pass
                if not comparisons:
                    if not refetch_ok and (not stored_pid or now_ts - last_refresh <= 3):
                        st.info("⏳ 等待 Pipeline 数据写入...")
                    else:
                        st.warning("⚠️ Pipeline 完成但无对比数据，请检查该任务的推荐方案数量或联系管理员")
            else:
                # Show stage breakdown in right column for FAILED pipelines
                stored_stages = st.session_state.get("pipeline_stages", [])
                stored_pid = st.session_state.get("_pipeline_id")
                if stored_stages:
                    _render_stage_retry_section(stored_pid, stored_stages, key_prefix="right_")
                    st.divider()
                _render_results_panel()
        elif st.session_state.get("pipeline_state") == "polling":
            st.info("⬆️ Pipeline 执行中，结果完成后将显示在此...")
        else:
            st.info("⬆️ 请先上传招标文件并运行 Pipeline，结果将在此显示")

    # =============================================================================
    # Pipeline: State Machine via session_state
    # =============================================================================
    # Initialize session state for pipeline
    for key in ["pipeline_state", "pipeline_profile", "pipeline_recs",
                 "pipeline_comparisons", "pipeline_pdf_bytes", "pipeline_pdf_filename",
                 "pipeline_log_lines", "pipeline_pdf_url", "_pipeline_id", "_skip_correction",
                 "pipeline_stages", "pipeline_qa_verdict", "pipeline_retry_count",
                 "pipeline_risk_flags", "pipeline_retry_history", "_results_refresh_ts"]:
        if key not in st.session_state:
            st.session_state[key] = [] if key == "pipeline_log_lines" else None

    def reset_pipeline():
        for key in ["pipeline_state", "pipeline_profile", "pipeline_recs",
                     "pipeline_comparisons", "pipeline_pdf_bytes", "pipeline_pdf_filename",
                     "pipeline_log_lines", "pipeline_pdf_url", "_pipeline_id", "_skip_correction",
                     "pipeline_stages", "pipeline_qa_verdict", "pipeline_retry_count",
                     "pipeline_risk_flags", "pipeline_retry_history", "_results_refresh_ts"]:
            st.session_state[key] = [] if key == "pipeline_log_lines" else None

    pipeline_state = st.session_state.get("pipeline_state")

    # ---- Reset button ----
    if st.button("🔄 重置 Pipeline", help="清除当前结果，重新开始"):
        reset_pipeline()
        st.rerun()

    # ---- Run Button ----
    if st.button("🚀 开始运行 Pipeline",
                 type="primary", width='stretch',
                 help="点击开始Pipeline：提取→推荐→ROI→对比→PDF"):
        st.session_state.pipeline_state = "polling"
        st.session_state.pipeline_log_lines = []
        tender_text = (st.session_state.get("tender_text", "") or "").strip()
        st.session_state._pipeline_params = {
            "industry": industry_p, "warehouse_area": float(warehouse_area_p),
            "sku_count": int(sku_count_p), "daily_orders": int(daily_orders_p),
            "inventory": int(inventory_p), "labor_cost_level": labor_cost_level_p,
            "budget_level": budget_level_p, "region": region_p,
            "compare_sids_str": compare_sids_str,
            "tender_text": tender_text,
        }
        st.session_state.skip_extraction = False
        st.rerun()

    # =====================================================================
    # Mode 4: Clarification Workspace
    # =====================================================================
elif app_mode == "💬 Clarification Workspace":
    st.markdown('<div class="main-header">💬 Clarification Workspace — 澄清与补录</div>', unsafe_allow_html=True)

    # Initialize session state for clarification
    for key in ["cw_pipeline_id", "cw_tasks", "cw_manual_inputs", "cw_definitions", "cw_recompute_result"]:
        if key not in st.session_state:
            st.session_state[key] = None

    API = API_BASE_URL

    # ---- Left: Task Selection & Input ----
    col_left, col_right = st.columns([1, 2])

    with col_left:
        st.markdown("### 📋 项目选择")
        st.caption("💡 时间显示北京时间(UTC+8)，最新任务在顶部 | 推荐测试 Base Solution：`13223d2c`")

        # Load list of completed pipelines
        try:
            hist_resp = requests.get(f"{API}/api/pipeline/history", timeout=5)
            if hist_resp.status_code == 200:
                hist_data = hist_resp.json().get("runs", [])
                completed = [r for r in hist_data if r.get("status") == "COMPLETE"]
                if completed:
                    # Sort newest first and show CST time (UTC+8)
                    completed_sorted = sorted(completed, key=lambda x: x.get("created_at", ""), reverse=True)
                    options = {r.get("pipeline_id", ""): r for r in completed_sorted}
                    def fmt_item(x):
                        r = options[x]
                        t = r.get("created_at", "")
                        # Convert UTC → CST (UTC+8)
                        if t and len(t) >= 19:
                            try:
                                from datetime import timedelta
                                utc_dt = datetime.fromisoformat(t[:19].replace("Z", "+00:00"))
                                cst = utc_dt + timedelta(hours=8)
                                time_str = cst.strftime("%m-%d %H:%M")  # CST
                            except Exception:
                                time_str = t[5:16]  # fallback UTC
                        else:
                            time_str = t[5:16] if t else ""
                        verdict = r.get("qa_verdict", "") or r.get("status", "")
                        return f"{time_str} | {x[:8]}… | {verdict}"
                    selected_pid = st.selectbox(
                        "选择已完成的任务（最新优先）",
                        options=list(options.keys()),
                        format_func=fmt_item,
                        index=0,
                    )
                    if selected_pid:
                        st.session_state.cw_pipeline_id = selected_pid
                else:
                    st.info("暂无已完成的任务，请先运行 Pipeline")
                    selected_pid = None
            else:
                st.error("无法加载历史任务列表")
                selected_pid = None
        except Exception:
            st.error("❌ 无法连接到后端服务")
            selected_pid = None

        st.divider()
        st.markdown("### 📊 当前状态")

        if selected_pid:
            try:
                status_resp = requests.get(f"{API}/api/clarification/status/{selected_pid}", timeout=10)
                if status_resp.status_code == 200:
                    cw_status = status_resp.json()
                    mode = cw_status.get("current_mode", "unknown")
                    score = cw_status.get("readiness_score", 0.0)
                    gate = cw_status.get("cost_model_gate", "UNKNOWN")
                    manual_count = cw_status.get("manual_inputs_count", 0)
                    manual_fields = cw_status.get("manual_inputs", [])

                    mode_colors = {"blocked": "🔴", "partial_ready": "🟡", "ready": "🟢", "full_calc": "🟢"}
                    mode_labels = {
                        "blocked": "阻塞（Blocked）",
                        "partial_ready": "区间估算（Range Estimate）",
                        "ready": "正式测算（Ready）",
                        "full_calc": "正式测算（Full Calc）",
                    }
                    st.markdown(f"**当前模式：** {mode_colors.get(mode, '⚪')} {mode_labels.get(mode, mode)}")
                    st.progress(float(score), text=f"Readiness {score:.0%}")
                    st.markdown(f"**成本测算闸门：** {'✅ PASS' if gate == 'PASS' else '🔒 BLOCK'}")
                    st.markdown(f"**已补录字段：** {manual_count}个")
                    if manual_fields:
                        with st.expander("已补录字段列表", expanded=False):
                            for f in manual_fields:
                                st.caption(f"  • {f}")
                else:
                    st.caption("⚠️ 无法加载状态")
            except Exception:
                st.caption("⚠️ 后端未启动")

        # ---- Input Definitions ----
        st.divider()
        st.markdown("### 📝 可补录字段说明")
        try:
            defs_resp = requests.get(f"{API}/api/clarification/definitions", timeout=5)
            if defs_resp.status_code == 200:
                defs = defs_resp.json()
                for d in defs[:8]:  # Show top 8
                    pri_tag = "🔴 P0" if d.get("required_for_p0") else "🟡 P1"
                    with st.expander(f"{pri_tag} **{d.get('display_name', d.get('field_key'))}**", expanded=False):
                        st.markdown(f"**字段名:** `{d.get('field_key')}`")
                        st.markdown(f"**输入类型:** {d.get('input_type')}")
                        st.markdown(f"**说明:** {d.get('description', '—')}")
                        if d.get("acceptable_units"):
                            st.markdown(f"**可接受单位:** {', '.join(d.get('acceptable_units', []))}")
                        if d.get("unit_conversion_hint"):
                            st.success(f"💡 {d.get('unit_conversion_hint')}")
            else:
                st.caption("无法加载字段定义")
        except Exception:
            st.caption("⚠️ 后端未启动")

    with col_right:
        st.markdown("### 💬 Clarification Tasks")

        if not selected_pid:
            st.info("⬅️ 请先在左侧选择一个已完成的任务")
        else:
            # Load tasks
            try:
                tasks_resp = requests.get(f"{API}/api/clarification/tasks/{selected_pid}", timeout=10)
                if tasks_resp.status_code == 200:
                    tasks_data = tasks_resp.json()
                    tasks = tasks_data.get("tasks", {})
                    summary = tasks.get("summary", {})

                    must_total = summary.get('must_total', 0)
                    resolved_count = summary.get('resolved', 0)
                    unresolved_count = must_total - resolved_count
                    st.markdown(f"**任务总数:** {summary.get('total_count', 0)}  "
                                f"**✅ 已解决:** {resolved_count}  "
                                f"**❌ 待解决:** {unresolved_count}")

                    # Tabs: Must Answer / Should Answer / Conflicts
                    tab1, tab2, tab3, tab4 = st.tabs(["🔴 必须澄清", "🟡 建议补充", "⚠️ 冲突字段", "⚠️ 假设复核"])

                    all_tasks = tasks.get("must_answer", []) + tasks.get("should_answer", []) + \
                                tasks.get("conflict_items", []) + tasks.get("assumption_review", [])
                    must_tasks = tasks.get("must_answer", [])
                    should_tasks = tasks.get("should_answer", [])
                    conflict_tasks = tasks.get("conflict_items", [])
                    assumption_tasks = tasks.get("assumption_review", [])

                    # ---- Must Answer ----
                    with tab1:
                        if not must_tasks:
                            st.success("✅ 所有P0必填项已解决！")
                        else:
                            st.markdown(f"共 **{len(must_tasks)}** 项必须澄清")
                            _render_clarification_task_editor(selected_pid, must_tasks, API, key_prefix="must_")

                    # ---- Should Answer ----
                    with tab2:
                        if not should_tasks:
                            st.info("暂无P1建议补充项")
                        else:
                            st.markdown(f"共 **{len(should_tasks)}** 项建议补充")
                            _render_clarification_task_editor(selected_pid, should_tasks, API, key_prefix="should_")

                    # ---- Conflicts ----
                    with tab3:
                        if not conflict_tasks:
                            st.success("✅ 无冲突字段")
                        else:
                            st.markdown(f"共 **{len(conflict_tasks)}** 项冲突")
                            _render_clarification_task_editor(selected_pid, conflict_tasks, API, key_prefix="conflict_")

                    # ---- Assumption Review ----
                    with tab4:
                        if not assumption_tasks:
                            st.info("暂无待复核的假设项")
                        else:
                            _render_clarification_task_editor(selected_pid, assumption_tasks, API, key_prefix="assume_")

                else:
                    st.error(f"无法加载任务列表: {tasks_resp.status_code}")
            except Exception as e:
                st.error(f"❌ 请求失败: {e}")

    # =============================================================================
    # Recompute Section (bottom) — 变化摘要卡片
    # =============================================================================
    if selected_pid:
        st.divider()
        st.markdown("### 📊 本次补录结果")

        # Check if we have a cached recompute result in session state
        cached = st.session_state.get("cw_recompute_result")
        display_result = None

        # Always show the recompute trigger button
        col_a, col_b = st.columns([1, 3])
        with col_a:
            recompute_clicked = st.button("🔄 提交并重新计算", type="primary", width="stretch")

        if recompute_clicked:
            with st.spinner("重新计算中..."):
                try:
                    pending = _collect_pending_inputs()
                    payload = {"inputs": pending}  # always include inputs (even if {})
                    recompute_resp = requests.post(
                        f"{API}/api/clarification/recompute/{selected_pid}",
                        json=payload,
                        timeout=30,
                    )

                    if recompute_resp.status_code == 200:
                        result = recompute_resp.json()
                        st.session_state.cw_recompute_result = result
                        display_result = result
                        st.rerun()
                    else:
                        st.error(f"重新计算失败: {recompute_resp.status_code}")
                        st.session_state.cw_recompute_result = None
                except Exception as e:
                    st.error(f"❌ 请求异常: {e}")
                    st.session_state.cw_recompute_result = None
        else:
            display_result = cached

        # ---- 变化摘要卡片（如果有任何结果）----
        if display_result:
            result = display_result
            changes = result.get("changes_summary") or {}
            downstream = result.get("downstream_input") or {}
            readiness = result.get("readiness") or {}

            old_mode = changes.get("old_mode", "?")
            new_mode = changes.get("new_mode", "?")
            mode_changed = changes.get("mode_changed", False)
            fields_updated = changes.get("fields_updated", [])
            remaining_p0 = changes.get("remaining_p0_count", 0)
            old_score = 0.0
            new_score = readiness.get("readiness_score", 0.0)
            blocking_reasons = downstream.get("blocking_reasons", [])

            # Mode badge
            mode_badge = {
                "blocked": "🔴 阻塞（Blocked）",
                "partial_ready": "🟡 区间估算（Range Estimate）",
                "ready": "🟢 正式测算（Ready）",
                "full_calc": "🟢 正式测算（Full Calc）",
            }

            # ---- 变化摘要4格卡片 ----
            m1, m2, m3, m4 = st.columns(4)

            with m1:
                st.metric(
                    "当前模式",
                    mode_badge.get(new_mode, new_mode),
                    delta=f"{old_mode} → {new_mode}" if mode_changed else None,
                    delta_color="normal" if mode_changed else "off",
                )

            with m2:
                st.metric(
                    "本次新增确认字段",
                    f"{len(fields_updated)}个" if fields_updated else "0个",
                    delta=", ".join(fields_updated) if fields_updated else None,
                )

            with m3:
                still_blocked = remaining_p0
                st.metric(
                    "剩余P0阻塞",
                    f"{still_blocked}个" if still_blocked > 0 else "0个 ✅",
                    delta="已解除" if still_blocked == 0 else None,
                    delta_color="normal" if still_blocked == 0 else "off",
                )

            with m4:
                st.metric(
                    "Readiness",
                    f"{new_score:.0%}",
                    delta=f"+{(new_score - old_score)*100:.0f}%" if old_score and new_score > old_score else None,
                )

            # ---- 下一步提示 ----
            if remaining_p0 > 0:
                st.info(f"📌 仍有 **{remaining_p0}** 个P0字段阻塞，请继续补录。")
                if blocking_reasons:
                    with st.expander("🔍 查看阻塞原因", expanded=False):
                        for r in blocking_reasons[:3]:
                            st.markdown(f"• {r}")
            elif new_mode == "partial_ready":
                st.success("✅ 所有P0字段已解决！可进入**区间估算**模式。建议继续补充P1字段以提升精度。")
            elif new_mode in ("ready", "full_calc"):
                st.success("🎉 项目已就绪！可进入**正式成本测算**。")

            # ---- Run Pipeline with resolved fields ----
            st.divider()
            st.markdown("#### 🚀 用补录数据重新运行 Pipeline")
            st.caption("将澄清后的字段注入 pipeline，跳过 extraction，直接运行推荐→成本→QA→PDF 阶段。")
            if st.button("🚀 运行 Pipeline（使用补录数据）", type="primary", use_container_width=True):
                st.session_state._debug_info = f"按钮点击: selected_pid={selected_pid}, cw_pipeline_id={st.session_state.get('cw_pipeline_id')}"
                with st.spinner("Pipeline 运行中，请稍候..."):
                    try:
                        # Get resolved fields from recompute result (usable ones)
                        resolved_fields = {}
                        for fkey, fval in (result.get("downstream_input", {}).get("required_inputs", {}) or {}).items():
                            if isinstance(fval, dict) and fval.get("usable") and fval.get("value") is not None:
                                resolved_fields[fkey] = fval["value"]
                        run_payload = {
                            "profile_overrides": resolved_fields,
                            "from_stage": "2_recommendation",
                        }
                        st.session_state._debug_info = f"POST /retry -> pid={selected_pid}, payload={run_payload}"
                        retry_resp = requests.post(
                            f"{API}/api/pipeline/{selected_pid}/retry",
                            json=run_payload,
                            timeout=10,
                        )
                        st.session_state._debug_info = f"POST /retry -> status={retry_resp.status_code}"
                        if retry_resp.ok:
                            _switch_to_pipeline_run(selected_pid)
                        else:
                            st.error(f"启动失败: {retry_resp.status_code} — {retry_resp.text[:200]}")
                    except Exception as e:
                        st.error(f"❌ 启动异常: {e}")
                        st.session_state._debug_info = f"异常: {e}"

            # ====================================================================
            # v0.6.3 New Panels — Downstream Explainability
            # ====================================================================

            source_inputs = downstream.get("source_inputs", {})
            assumed_inputs = downstream.get("assumed_inputs", {})
            unusable_fields = downstream.get("unusable_fields", [])
            p0_summary = downstream.get("p0_summary", {})
            p1_summary = downstream.get("p1_summary", {})

            # ---- Panel 1: Resolved Inputs Summary (always show) ----
            provided_count = len(source_inputs)
            assumed_count = len(assumed_inputs)
            unusable_count = len(unusable_fields)
            # Count from p0/p1 summaries
            p0_missing = p0_summary.get("missing", 0) if p0_summary else 0
            p1_missing = p1_summary.get("missing", 0) if p1_summary else 0
            missing_count = p0_missing + p1_missing

            st.markdown("##### 📊 字段状态总览")
            ris_col1, ris_col2, ris_col3, ris_col4 = st.columns(4)
            with ris_col1:
                st.metric("✅ 已确认 (Provided)", f"{provided_count}个",
                    help="直接来自招标文件或人工确认的字段，可直接用于测算")
            with ris_col2:
                st.metric("🔄 区间估算 (Assumed)", f"{assumed_count}个",
                    help="P1字段因缺失而采用业务假设值，结论为区间范围")
            with ris_col3:
                st.metric("⬜ 缺失 (Missing)", f"{missing_count}个",
                    help="招标文件未提供且未人工补录的字段")
            with ris_col4:
                st.metric("🚫 不可用 (Unusable)", f"{unusable_count}个",
                    help="P0字段状态为missing/ambiguous，禁止进入任何正式测算")

            st.divider()

            # ---- Panel 2: Blocking Reasons Panel (mode = blocked) ----
            if new_mode == "blocked":
                st.markdown("#####🚨 阻塞原因详情")
                st.warning("当前存在P0关键字段缺失或歧义，系统无法进入任何形式的成本测算。")

                if blocking_reasons:
                    for i, reason in enumerate(blocking_reasons, 1):
                        st.markdown(f"**{i}.** {reason}")

                if unusable_fields:
                    st.markdown("**受阻塞字段：**")
                    uf_cols = st.columns(min(len(unusable_fields), 3))
                    for idx, fkey in enumerate(unusable_fields):
                        with uf_cols[idx % 3]:
                            st.markdown(f"• `{fkey}`")
                    st.markdown("**建议：** 请回到上方「Clarification Tasks」补录这些字段的招标文件原文或人工确认值。")

                st.divider()

            # ---- Panel 3: Assumptions Used Panel (mode = range_estimate) ----
            if new_mode in ("partial_ready", "range_estimate") and assumed_inputs:
                st.markdown("##### 📐 当前业务假设（区间估算依据）")
                st.info(f"以下 **{len(assumed_inputs)}个** P1字段因缺失而采用业务假设值，最终结论为区间范围而非精确值。")

                for fkey, finfo in assumed_inputs.items():
                    with st.expander(f"🔹 `{fkey}` — 假设值: {finfo.get('value', 'N/A')}", expanded=False):
                        col_a, col_b = st.columns([1, 2])
                        with col_a:
                            st.markdown(f"**假设值:** `{finfo.get('value')}`")
                            st.markdown(f"** fallback值:** `{finfo.get('fallback_value')}`")
                            st.markdown(f"**优先级:** `{finfo.get('priority')}`")
                        with col_b:
                            st.markdown(f"**假设依据:** {finfo.get('assumption_rule', '未提供')}")
                            st.markdown(f"**影响范围:** {finfo.get('impact', '未知')}")

                st.divider()

            # ---- Panel 3b: Assumptions Template (fields that could be assumed) ----
            if new_mode in ("partial_ready", "range_estimate"):
                assumptions_template = downstream.get("assumptions_template", [])
                if assumptions_template:
                    with st.expander("💡 还可以做区间估算的字段（点击展开）", expanded=False):
                        st.caption("以下P1字段目前缺失但允许业务假设，补充后可将区间收窄：")
                        for t in assumptions_template:
                            st.markdown(f"• **{t.get('field_key')}**: {t.get('assumption_rule', '允许假设')}")

            # ---- Panel 4: Source Breakdown (provided fields detail) ----
            if source_inputs and st.toggle("📋 查看已确认字段详情", value=False, key="toggle_source_detail"):
                st.markdown("**以下字段已确认，可直接用于成本测算：**")
                for fkey, finfo in source_inputs.items():
                    pri = finfo.get("priority", "")
                    pri_emoji = {"P0": "🔴", "P1": "🟡", "P2": "🟢"}.get(pri, "⚪")
                    section = finfo.get("source_section", "—")
                    impact = finfo.get("impact", "—")
                    val = finfo.get("value")
                    st.markdown(f"{pri_emoji} **`{fkey}`** = `{val}`  |  优先级:{pri}  |  来源章节:{section}")
                    st.caption(f"   影响: {impact}")

            # ====================================================================
            # v0.6.5 New Panel — Operation Model
            # ====================================================================
            operation_profile = downstream.get("operation_profile")
            labor_modules = downstream.get("labor_modules")
            operation_narrative = downstream.get("operation_narrative")

            if operation_profile:
                st.divider()
                st.markdown("##### ⚙️ 运营模型（自动推导）")

                # Sub-panels row 1: operation type + complexity + required modules
                op_type = operation_profile.get("operation_type", "unknown")
                complexity = operation_profile.get("service_complexity_level", "unknown")
                complexity_score = operation_profile.get("service_complexity_score", 0)
                complexity_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(complexity, "⚪")

                om_col1, om_col2, om_col3 = st.columns(3)
                with om_col1:
                    OP_TYPE_LABELS = {
                        "warehouse_distribution": "仓配一体化",
                        "cold_chain": "冷链仓储",
                        "bonded_warehouse_distribution": "保税仓配",
                        "distribution_only": "纯配送",
                        "warehouse_inbound_only": "仓储入库",
                        "warehouse_outbound_only": "仓储出库",
                        "value_added_services": "增值服务",
                        "custom": "综合物流",
                    }
                    st.metric(
                        "运营类型",
                        OP_TYPE_LABELS.get(op_type, op_type),
                        help="基于服务范围矩阵自动推导的运营类型"
                    )
                with om_col2:
                    st.metric(
                        "服务复杂度",
                        f"{complexity_emoji} {complexity.title()} ({complexity_score}/20)",
                        help="综合评分：服务项数量+增值复杂度+温控+系统对接"
                    )
                with om_col3:
                    # Count required modules
                    req_modules = []
                    for mod, active in (labor_modules or {}).items():
                        if active:
                            req_modules.append(mod.replace("_team", ""))
                    st.metric(
                        "人员模块",
                        f"{len(req_modules)}个",
                        delta=", ".join(req_modules) if req_modules else None,
                        help="从服务范围推导的人员配置模块"
                    )

                # Required modules detail
                if labor_modules:
                    st.markdown("**🧑‍🔧 人员模块配置：**")
                    module_labels = {
                        "receiving_team": "收货组",
                        "putaway_team": "上架组",
                        "picking_team": "拣选组",
                        "packing_team": "包装组",
                        "loading_team": "装车队",
                        "return_processing_team": "退货处理组",
                        "inventory_control_team": "库存管控组",
                    }
                    active_mods = [m for m, v in labor_modules.items() if v]
                    inactive_mods = [m for m, v in labor_modules.items() if not v]

                    mod_cols = st.columns(min(len(labor_modules), 4))
                    for idx, (mod_key, active) in enumerate(labor_modules.items()):
                        with mod_cols[idx % 4]:
                            label = module_labels.get(mod_key, mod_key)
                            if active:
                                st.markdown(f"✅ {label}")
                            else:
                                st.markdown(f"⚪ {label}")

                # Required capabilities
                st.markdown("**📦 运营能力需求：**")
                capability_items = [
                    ("inbound_required", "📥", "入库作业"),
                    ("outbound_required", "📤", "出库作业"),
                    ("value_added_required", "🔧", "增值服务"),
                    ("support_required", "⚙️", "支持服务"),
                    ("temperature_control_required", "❄️", "温控管理"),
                    ("return_flow_required", "↩️", "退货处理"),
                ]
                cap_cols = st.columns(len(capability_items))
                for idx, (key, emoji, label) in enumerate(capability_items):
                    with cap_cols[idx]:
                        val = operation_profile.get(key, False)
                        color = "✅" if val else "⚪"
                        st.markdown(f"{color} {emoji} {label}")

                # Operation narrative
                if operation_narrative:
                    st.markdown("**📄 运营描述：**")
                    st.info(operation_narrative)

                # v0.6.6: Process Modules
                process_modules = operation_profile.get("process_modules", {})
                if process_modules:
                    st.markdown("---")
                    st.markdown("##### 📋 作业流程模型")
                    st.caption("基于服务范围自动生成的标准化作业流程（每流程含角色分工）")

                    PROCESS_LABELS = {
                        "receiving_process": "📥 入库作业流程",
                        "outbound_process": "📤 出库作业流程",
                        "storage_management": "📦 存储管理流程",
                        "return_process": "↩️ 退货处理流程",
                        "va_process": "🔧 增值服务流程",
                        "temperature_control": "❄️ 温控管理流程",
                        "support_process": "⚙️ 支持服务流程",
                    }

                    proc_expanders = st.columns(min(len(process_modules), 2))
                    for idx, (proc_key, proc_info) in enumerate(process_modules.items()):
                        with proc_expanders[idx % 2]:
                            label = PROCESS_LABELS.get(proc_key, proc_key)
                            with st.expander(f"**{label}** ({proc_info.get('step_count', 0)}步)", expanded=False):
                                st.caption(proc_info.get("description", ""))
                                # Steps
                                for step in proc_info.get("steps", []):
                                    st.markdown(
                                        f"  `{step.get('step_id', '')}` **{step.get('label', '')}**"
                                        f"  → 角色:{step.get('role', '—')}"
                                    )
                                # KPIs
                                kpis = proc_info.get("kpis", [])
                                if kpis:
                                    st.markdown("**📊 流程KPI：**")
                                    for kpi in kpis:
                                        st.markdown(f"  • {kpi}")

                    # Process summary metric
                    total_steps = sum(v.get("step_count", 0) for v in process_modules.values())
                    st.metric("流程总步骤数", f"{total_steps}步 / {len(process_modules)}个流程")
            elif new_mode in ("partial_ready", "range_estimate"):
                # Show placeholder when service_scope not yet resolved
                st.divider()
                st.markdown("##### ⚙️ 运营模型（自动推导）")
                st.info("📌 完成服务范围补录后，系统将自动推导运营模型。")

    # =============================================================================
    # v0.7.1: Base Solution Studio
    # =============================================================================
    if selected_pid:
        st.divider()
        st.markdown("### 🧩 基础方案（Base Solution Studio）")
        st.caption("基于服务范围 · 运营模型 · 成本模式自动生成 | v0.7.1")

        # Action buttons row
        sol_col1, sol_col2, sol_col3 = st.columns([1, 1, 3])
        with sol_col1:
            generate_solution_clicked = st.button("🧩 生成基础方案", type="primary", width="stretch")
        with sol_col2:
            # Markdown export button
            try:
                md_resp = requests.get(f"{API}/api/solution/base/{selected_pid}/markdown", timeout=5)
                if md_resp.status_code == 200:
                    st.download_button(
                        "📄 导出 Markdown",
                        data=md_resp.text,
                        file_name=f"base_solution_{selected_pid[:8]}.md",
                        mime="text/markdown",
                        width="stretch",
                    )
            except Exception:
                pass

        solution_data = None
        load_error = None

        # Try to load existing solution first
        try:
            existing_resp = requests.get(f"{API}/api/solution/base/{selected_pid}", timeout=10)
            if existing_resp.status_code == 200:
                solution_data = existing_resp.json()
        except Exception:
            pass

        # Generate new solution if button clicked
        if generate_solution_clicked:
            with st.spinner("正在生成基础方案..."):
                try:
                    gen_resp = requests.post(f"{API}/api/solution/base/{selected_pid}", json={}, timeout=30)
                    if gen_resp.status_code == 200:
                        solution_data = gen_resp.json()
                        st.success("✅ 基础方案生成完成")
                    else:
                        load_error = f"生成失败: {gen_resp.status_code}"
                except Exception as e:
                    load_error = f"请求异常: {e}"

        if load_error:
            st.error(load_error)

        # Show empty state if no solution yet
        if not solution_data:
            st.info("📌 点击上方「生成基础方案」或「导出 Markdown」按钮开始。")
        else:
            sol = solution_data.get("solution", {})
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
                "warehouse_distribution": "仓配一体化",
                "cold_chain": "冷链仓储",
                "bonded_warehouse_distribution": "保税仓配",
                "distribution_only": "纯配送",
                "warehouse_inbound_only": "仓储入库",
                "warehouse_outbound_only": "仓储出库",
                "value_added_services": "增值服务",
                "custom": "综合物流",
                "unknown": "待定",
            }

            st.divider()
            # A1: Summary card
            st.markdown("##### 📋 方案摘要")
            s1, s2, s3, s4 = st.columns(4)
            with s1:
                st.metric("方案名称", sol.get("title", "基础仓配运营方案"))
            with s2:
                st.metric("运营类型", OP_TYPE_LABELS.get(pf.get("operation_type", ""), pf.get("operation_type", "—")))
            with s3:
                cl = pf.get("complexity_level", "—")
                cs = pf.get("complexity_score", 0)
                st.metric("复杂度", f"{cl.title() if cl else '—'} ({cs}/20)")
            with s4:
                cm = cml.get("current_mode", "unknown")
                cm_labels = {"blocked": "🔴阻塞", "range_estimate": "🟡区间", "full_calc": "🟢完整"}
                st.metric("测算模式", cm_labels.get(cm, cm))
            st.info(ns.get("executive_summary", sol.get("summary", "正在生成..."))[:500])

            # A2: Service Design
            if sd.get("included_services"):
                st.divider()
                st.markdown("##### 📦 服务范围设计")
                svc_by_cat = {}
                for svc in sd.get("included_services", []):
                    cat = svc.get("category", "")
                    svc_by_cat.setdefault(cat, []).append(svc.get("label", ""))
                CAT_EMOJI = {"inbound": "📥", "storage": "📦", "outbound": "📤", "value_added": "🔧", "support": "⚙️"}
                for cat, svcs in svc_by_cat.items():
                    emoji = CAT_EMOJI.get(cat, "📌")
                    st.markdown(f"{emoji} **{cat.upper()}**: {', '.join(svcs)}")
                if sd.get("excluded_or_unconfirmed"):
                    with st.expander("⚠️ 未纳入/未确认服务", expanded=False):
                        for s in sd.get("excluded_or_unconfirmed", [])[:10]:
                            st.markdown(f"• {s}")
                if sd.get("narrative"):
                    st.caption(sd.get("narrative"))

            # A3: Organization Design
            if od.get("team_modules"):
                st.divider()
                st.markdown("##### 🧑‍🤝‍🧑 组织模块设计")
                mod_cols = st.columns(min(len(od.get("team_modules", [])), 4))
                for idx, tm in enumerate(od.get("team_modules", [])):
                    with mod_cols[idx % 4]:
                        st.markdown(f"✅ **{tm.get('label', tm.get('module_key', ''))}**")
                        for resp in tm.get("primary_responsibilities", [])[:2]:
                            st.caption(f"  • {resp}")
                if od.get("staffing_logic"):
                    st.caption(f"人员逻辑: {od.get('staffing_logic')}")

            # A4: Process Design
            if pd.get("processes"):
                st.divider()
                st.markdown("##### 🔄 核心流程设计")
                proc_cols = st.columns(min(len(pd.get("processes", [])), 2))
                PROC_EMOJI = {
                    "receiving_process": "📥", "outbound_process": "📤",
                    "storage_management": "📦", "return_process": "↩️",
                    "va_process": "🔧", "temperature_control": "❄️",
                    "support_process": "⚙️",
                }
                for idx, proc in enumerate(pd.get("processes", [])):
                    with proc_cols[idx % 2]:
                        emoji = PROC_EMOJI.get(proc.get("process_key", ""), "📌")
                        with st.expander(f"{emoji} **{proc.get('label', proc.get('process_key', ''))}** — {proc.get('step_count', 0)}步", expanded=False):
                            if proc.get("description"):
                                st.caption(proc.get("description"))
                            for step in proc.get("steps", [])[:6]:
                                st.markdown(f"  `{step.get('step_id','')}` {step.get('label','—')} → {step.get('role','—')}")
                            if len(proc.get("steps", [])) > 6:
                                st.caption(f"  ...共{proc.get('step_count', 0)}步")
                            if proc.get("kpis"):
                                st.markdown(f"  **KPI**: {', '.join(proc.get('kpis', [])[:3])}")

            # A5: KPI Framework
            if kf.get("inbound_kpis") or kf.get("outbound_kpis") or kf.get("inventory_kpis"):
                st.divider()
                st.markdown("##### 📊 KPI 框架")
                kpi_groups = [
                    ("📥 入库KPI", kf.get("inbound_kpis", [])),
                    ("📤 出库KPI", kf.get("outbound_kpis", [])),
                    ("📦 库内KPI", kf.get("inventory_kpis", [])),
                    ("⚙️ 支持KPI", kf.get("support_kpis", [])),
                ]
                for gname, kpis in kpi_groups:
                    if kpis:
                        st.markdown(f"**{gname}**")
                        kpi_cols = st.columns(min(len(kpis), 3))
                        for idx2, kpi in enumerate(kpis):
                            with kpi_cols[idx2 % 3]:
                                sla = "🏆" if kpi.get("is_sla_candidate") else ""
                                st.markdown(f"• `{kpi.get('name','—')}` = {kpi.get('target','—')} {sla}")

            # A6: Implementation Phases
            if impl.get("phases"):
                st.divider()
                st.markdown("##### 🚀 实施阶段")
                for ph in impl.get("phases", []):
                    with st.expander(f"**{ph.get('phase','Phase')}** — {ph.get('name','—')} (~{ph.get('duration_months', 0)}个月)", expanded=False):
                        st.markdown(f"*{ph.get('focus','—')}*")
                        for action in ph.get("key_actions", []):
                            st.markdown(f"  • {action}")

            # A7: Risks
            if rc.get("risks"):
                st.divider()
                st.markdown("##### ⚠️ 风险与控制")
                sev_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}
                for rk in rc.get("risks", []):
                    emoji = sev_emoji.get(rk.get("severity", ""), "⚪")
                    with st.expander(f"{emoji} {rk.get('risk_id','R-?')} — {rk.get('description','—')[:40]}...", expanded=False):
                        st.markdown(f"**类别:** {rk.get('category','—')}")
                        st.markdown(f"**控制措施:** {rk.get('control_measure','—')}")
                        st.markdown(f"**缓解动作:** {rk.get('mitigation_action','—')}")

            # A8: Cost Model Linkage
            if cml.get("current_mode"):
                st.divider()
                st.markdown("##### 💰 成本测算衔接")
                cm = cml.get("current_mode", "unknown")
                cm_style = {"blocked": "error", "range_estimate": "warning", "full_calc": "info"}
                st_message = getattr(st, cm_style.get(cm, "info"))
                st_message(f"**当前模式:** {cm} — {cml.get('mode_explanation', '')}")
                if cml.get("missing_for_full_calc"):
                    st.markdown("**进入完整测算还需:**")
                    for m in cml.get("missing_for_full_calc", []):
                        st.markdown(f"  • {m}")
                if cml.get("assumptions_used"):
                    st.markdown(f"**当前假设项:** {len(cml.get('assumptions_used', []))}项")
                if cml.get("narrative"):
                    st.caption(cml.get("narrative"))


# =============================================================================
# Clarification Task Editor Helper
# =============================================================================
