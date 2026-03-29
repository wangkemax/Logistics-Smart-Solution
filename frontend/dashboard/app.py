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
            f"{API_BASE_URL}/api/pipeline/{pipeline_id}/retry/",
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

    app_mode = st.radio(
        "选择功能模式",
        options=["📋 方案生成", "⚖️ 多方案对比", "🚀 Pipeline Run"],
        index=0,
        help="方案生成：单方案推荐+PDF\n多方案对比：横向对比ROI\nPipeline Run：端到端自动投标",
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
                                    f"{API_BASE_URL}/api/pipeline/{pipeline_id}/retry/",
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
                            f"{API_BASE_URL}/api/pipeline/{pipeline_id}/retry/",
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
                total_score = compl.get("total_score", 0)
                evidence = quality_score.get("evidence", {})
                readiness_data = quality_score.get("readiness", {})

                st.markdown("**📊 分析质量评分**")
                q1, q2, q3 = st.columns(3)
                with q1:
                    st.metric("P0覆盖率", f"{p0_cov:.0%}",
                              delta="阻塞项" if p0_cov < 1.0 else "全部就绪")
                with q2:
                    st.metric("P1覆盖率", f"{p1_cov:.0%}",
                              delta="重要项" if p1_cov < 1.0 else "全部就绪")
                with q3:
                    st.metric("综合评分", f"{total_score:.0%}")

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
        st.markdown("### 📂 招标文件 & 参数")

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

        st.divider()
        st.markdown("**项目参数**")
        industry_p = st.selectbox("行业", options=["电商", "3PL", "零售", "制造", "快递", "医药", "食品", "生鲜"], index=0)
        region_p = st.selectbox("区域", options=["华东", "华南", "华北", "华中", "西部"], index=0)
        warehouse_area_p = st.number_input("面积 (㎡)", min_value=500, max_value=500000, value=20000, step=1000)
        sku_count_p = st.number_input("SKU数量", min_value=100, max_value=1000000, value=30000, step=1000)
        daily_orders_p = st.number_input("日订单", min_value=50, max_value=500000, value=5000, step=100)
        inventory_p = st.number_input("库存量", min_value=1000, max_value=10000000, value=500000, step=10000)
        labor_cost_level_p = st.select_slider("人工成本", options=["低", "中", "高"], value="中")
        budget_level_p = st.select_slider("自动化预算", options=["低", "中", "高"], value="中")
        compare_sids_str = st.text_input("对比方案ID", value="1,2,3", placeholder="1,2,3,4,5")

        st.session_state._pipeline_params = {
            "industry": industry_p, "warehouse_area": float(warehouse_area_p),
            "sku_count": int(sku_count_p), "daily_orders": int(daily_orders_p),
            "inventory": int(inventory_p), "labor_cost_level": labor_cost_level_p,
            "budget_level": budget_level_p, "region": region_p,
            "compare_sids_str": compare_sids_str,
            "tender_text": final_tender_text,
        }

        # ---- History Panel ----
        with st.expander("📋 历史任务", expanded=False):
            try:
                hist_resp = requests.get(f"{API_BASE_URL}/api/pipeline/history", timeout=5)
                if hist_resp.status_code == 200:
                    hist_data = hist_resp.json().get("runs", [])
                    if hist_data:
                        for run in hist_data[:10]:
                            pid = run.get("pipeline_id", "")
                            status = run.get("status", "")
                            verdict = run.get("qa_verdict", "") or ""
                            dur = run.get("total_duration_seconds")
                            created = run.get("created_at", "")
                            if created:
                                created = created[11:16]  # HH:MM
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
                overrides = {
                    "industry": params.get("industry", "电商"),
                    "warehouse_area": float(params.get("warehouse_area", 20000)),
                    "sku_count": int(params.get("sku_count", 30000)),
                    "daily_orders": int(params.get("daily_orders", 5000)),
                    "inventory": int(params.get("inventory", 500000)),
                    "labor_cost_level": params.get("labor_cost_level", "中"),
                    "budget_level": params.get("budget_level", "中"),
                    "automation_expectation": "中",
                    "region": params.get("region", "华东"),
                }
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
        if st.session_state.get("pipeline_state") == "done":
            comparisons = st.session_state.get("pipeline_comparisons") or []
            if not comparisons:
                # Guard: only auto-refresh once per pipeline completion
                last_refresh = st.session_state.get("_results_refresh_ts", 0)
                now_ts = int(time.time())
                if now_ts - last_refresh > 5:
                    st.session_state._results_refresh_ts = now_ts
                    st.rerun()
                else:
                    st.info("⏳ 等待 Pipeline 数据写入...")
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
                 "pipeline_risk_flags", "pipeline_retry_history"]:
        if key not in st.session_state:
            st.session_state[key] = [] if key == "pipeline_log_lines" else None

    def reset_pipeline():
        for key in ["pipeline_state", "pipeline_profile", "pipeline_recs",
                     "pipeline_comparisons", "pipeline_pdf_bytes", "pipeline_pdf_filename",
                     "pipeline_log_lines", "pipeline_pdf_url", "_pipeline_id", "_skip_correction",
                     "pipeline_stages", "pipeline_qa_verdict", "pipeline_retry_count",
                     "pipeline_risk_flags", "pipeline_retry_history"]:
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
    # =====================================================================
