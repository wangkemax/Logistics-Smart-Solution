"""
Logistics Smart Solution — Streamlit Dashboard
Three modes: 方案生成 | 多方案对比 | Pipeline Run
"""

import streamlit as st
import requests
import json
import os
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

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
        cost_data["warehouse_cost"] / 10000,
        cost_data["labor_cost_annual"] / 10000,
        cost_data["annual_maintenance"] / 10000,
        cost_data["total_annual_cost"] / 10000,
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
    capex = cost_data["automation_capex"] / 10000
    annual_saving = cost_data["automation_savings_annual"] / 10000
    annual_cost = cost_data["annual_maintenance"] / 10000
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
    names = [c["scenario_name"][:8] for c in comparisons]
    capex = [c["automation_capex"] / 10000 for c in comparisons]
    savings = [c["annual_saving"] / 10000 for c in comparisons]
    fig = go.Figure(data=[
        go.Bar(name="自动化投资 (万)", x=names, y=capex, marker_color="#ef5350"),
        go.Bar(name="年节省人工 (万)", x=names, y=savings, marker_color="#4caf50"),
    ])
    fig.update_layout(barmode="group", title="投资与年节省对比 (万元)",
                      yaxis_title="金额 (万元)", height=280,
                      margin=dict(l=10, r=10, t=40, b=10))
    return fig


def render_compare_roi_chart(comparisons):
    sorted_comps = sorted(comparisons, key=lambda x: x["roi_5y"], reverse=True)
    names = [c["scenario_name"][:10] for c in sorted_comps]
    roi_5y = [c["roi_5y"] for c in sorted_comps]
    colors = ["#27ae60" if c.get("is_best") else "#95a5a6" for c in sorted_comps]
    fig = go.Figure(data=[go.Bar(
        y=names, x=roi_5y, orientation="h",
        marker_color=colors, text=[f"{r:.1f}x" for r in roi_5y], textposition="auto",
    )])
    fig.update_layout(title="5年ROI倍数对比", xaxis_title="ROI (倍)",
                     height=max(220, len(comparisons) * 60),
                     margin=dict(l=10, r=10, t=40, b=10))
    return fig


def render_compare_radar(comparisons):
    max_roi = max((c["roi_5y"] for c in comparisons), default=1)
    max_payback = max((c["payback_years"] for c in comparisons), default=1)
    max_saving = max((c["annual_saving"] for c in comparisons), default=1)
    max_hc = max((c["headcount_saved"] for c in comparisons), default=1)
    colors = ["#2196f3", "#4caf50", "#ff9800", "#9c27b0", "#f44336"]
    traces = []
    for i, c in enumerate(comparisons[:5]):
        values = [
            (c["roi_5y"] / max_roi) * 100,
            (1 - c["payback_years"] / max_payback) * 100,
            (c["annual_saving"] / max_saving) * 100,
            (c["headcount_saved"] / max_hc) * 100,
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
            reader = PdfReader(io.BytesIO(uploaded_file.read()))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        elif fname.endswith(".txt"):
            return uploaded_file.read().decode("utf-8", errors="replace")
        elif fname.endswith(".docx"):
            from docx import Document
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
                                                  use_container_width=True, type="primary")

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
                    c1.metric("首选方案", top["scenario_name"])
                    c2.metric("匹配评分", f"{top['score']:.0f}/100")
                    c3.metric("人工节省", f"{int(top['labor_saving']*100)}%")
                    c4.metric("效率提升", f"{int(top['efficiency_gain']*100)}%")
                    st.divider()
                    for i, rec in enumerate(recommendations):
                        with st.expander(
                            f"{'🥇' if i==0 else '🥈' if i==1 else '🥉' if i==2 else '📌'} "
                            f"#{i+1} {rec['scenario_name']} — 评分: {rec['score']:.0f}分",
                            expanded=(i == 0),
                        ):
                            col_a, col_b = st.columns([2, 1])
                            with col_a:
                                st.markdown(f"**类别:** {rec['category']}")
                                st.markdown(f"**推荐理由:** {rec['reason']}")
                                st.markdown(f"**风险评估:** {rec['risk']}")
                                st.markdown(f"**投资范围:** {rec['capex_range']}")
                            with col_b:
                                st.plotly_chart(render_score_gauge(rec["score"]),
                                                use_container_width=True, key=f"score_gauge_{i}")

            with tab2:
                st.subheader("成本与ROI分析")
                cost_data = cost_result["cost_breakdown"]
                st.info(cost_result.get("summary", ""))
                c1, c2, c3, c4, c5 = st.columns(5)
                c1.metric("总投资", f"¥{cost_data['automation_capex']/10000:.0f}万")
                c2.metric("年节省人工", f"¥{cost_data['automation_savings_annual']/10000:.1f}万")
                c3.metric("5年ROI", f"{cost_data['roi']:.1f}x")
                c4.metric("回本周期", f"{cost_data['payback_years']:.1f}年")
                c5.metric("节省人数", f"{cost_data['headcount_saved']}人")
                st.divider()
                cc1, cc2 = st.columns(2)
                with cc1:
                    st.plotly_chart(render_cost_chart(cost_data), use_container_width=True)
                with cc2:
                    st.plotly_chart(render_roi_chart(cost_data), use_container_width=True)
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
- 自动化投资: ¥{cost_d['automation_capex']/10000:.0f}万元
- 年节省人工: ¥{cost_d['automation_savings_annual']/10000:.1f}万元
- 净年度收益: ¥{cost_d['net_annual_benefit']/10000:.1f}万元
- 5年ROI: {cost_d['roi']:.1f}倍 | 回本周期: {cost_d['payback_years']:.1f}年
- 预计减少人员: {cost_d['headcount_saved']}人
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
                if st.button("📄 生成并下载PDF方案报告", type="primary", use_container_width=True):
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
                                                  use_container_width=True, type="primary")

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
                        "方案": ("✅ " if c.get("is_best") else "  ") + c["scenario_name"],
                        "类别": c["category"],
                        "投资 (万)": f"{c['automation_capex']/10000:.0f}",
                        "年节省 (万)": f"{c['annual_saving']/10000:.1f}",
                        "年维护 (万)": f"{c['annual_maintenance']/10000:.1f}",
                        "净年收益 (万)": f"{c['net_annual_benefit']/10000:.1f}",
                        "5年ROI": f"{c['roi_5y']:.1f}x",
                        "回本周期": f"{c['payback_years']:.1f}年",
                        "省人数": f"{c['headcount_saved']}人",
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

                # KPI row
                best = next((c for c in comparisons if c.get("is_best")), comparisons[0] if comparisons else {})
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("🥇 最佳方案", best.get("scenario_name", "—"))
                c2.metric("5年ROI", f"{best.get('roi_5y', 0):.1f}x")
                c3.metric("回本周期", f"{best.get('payback_years', 0):.1f}年")
                c4.metric("年节省", f"{best.get('annual_saving', 0)/10000:.1f}万")

                st.divider()
                st.subheader("📈 可视化对比")
                t1, t2, t3 = st.tabs(["投资与年节省", "5年ROI对比", "综合雷达图"])
                with t1:
                    st.plotly_chart(render_compare_bar_chart(comparisons), use_container_width=True)
                with t2:
                    st.plotly_chart(render_compare_roi_chart(comparisons), use_container_width=True)
                with t3:
                    st.plotly_chart(render_compare_radar(comparisons), use_container_width=True)

                st.divider()
                st.subheader("📋 详细参数")
                det = []
                for c in comparisons:
                    det.append({
                        "方案": c["scenario_name"],
                        "类别": c["category"],
                        "自动化投资": f"¥{c['automation_capex']/10000:.0f}万",
                        "5年累计净收益": f"¥{c['five_year_net_benefit']/10000:.1f}万",
                        "5年ROI": f"{c['roi_5y']:.1f}x",
                        "回本周期": f"{c['payback_years']:.1f}年",
                        "节省人数": f"{c['headcount_saved']}/{c['headcount_required']}",
                    })
                st.dataframe(pd.DataFrame(det), use_container_width=True, hide_index=True)
    else:
        _render_welcome_compare()

# =============================================================================
# Mode 3: Pipeline Run
# =============================================================================
elif app_mode == "🚀 Pipeline Run":
    st.markdown('<div class="main-header">🚀 Pipeline Run — 端到端投标方案生成</div>', unsafe_allow_html=True)

    # ---- Input Section ----
    with st.expander("📂 第一步：上传招标文件 & 填写参数", expanded=True):
        col_file, col_params = st.columns([1, 1])

        with col_file:
            st.markdown("**上传招标文件**")
            uploaded_file = st.file_uploader(
                "支持 PDF / TXT / Word (.docx)",
                type=["pdf", "txt", "docx"],
                help="上传招标文件（PDF、Word或TXT格式），系统将自动提取项目参数",
            )
            if uploaded_file:
                st.success(f"已上传: {uploaded_file.name}")
                with st.spinner("正在解析文件..."):
                    tender_text = extract_tender_text(uploaded_file)
                if tender_text and len(tender_text) > 50:
                    st.session_state.tender_text = tender_text
                    st.info(f"已提取文本长度: {len(tender_text)} 字符")
                    with st.expander("🔍 查看提取的文本（前500字）"):
                        st.text(tender_text[:500] + ("..." if len(tender_text) > 500 else ""))
                else:
                    st.warning("文件解析失败，请直接在下方填写参数")
                    st.session_state.tender_text = ""
            else:
                st.session_state.tender_text = ""

            tender_text_manual = st.text_area(
                "或直接粘贴招标文件摘要",
                placeholder="粘贴招标文件中的关键信息（面积、SKU、订单量、行业、预算等）...",
                height=120,
            )
            final_tender_text = (st.session_state.get("tender_text", "") or "") + "\n" + tender_text_manual

        with col_params:
            st.markdown("**项目参数**（可自动从文件中提取）")
            industry_p = st.selectbox("行业类型",
                options=["电商", "3PL", "零售", "制造", "快递", "医药", "食品", "生鲜"], index=0)
            region_p = st.selectbox("所在区域",
                options=["华东", "华南", "华北", "华中", "西部"], index=0)
            warehouse_area_p = st.number_input("仓库面积 (㎡)", min_value=500, max_value=500000,
                                               value=20000, step=1000)
            sku_count_p = st.number_input("SKU数量", min_value=100, max_value=1000000,
                                          value=30000, step=1000)
            daily_orders_p = st.number_input("日均订单量", min_value=50, max_value=500000,
                                               value=5000, step=100)
            inventory_p = st.number_input("库存量 (件)", min_value=1000, max_value=10000000,
                                           value=500000, step=10000)
            labor_cost_level_p = st.select_slider("人工成本水平", options=["低", "中", "高"], value="中")
            budget_level_p = st.select_slider("自动化预算", options=["低", "中", "高"], value="中")

            st.markdown("**Pipeline 配置**")
            compare_sids_str = st.text_input(
                "对比方案ID（逗号分隔）",
                value="1,2,3",
                placeholder="如: 1,2,3,4,5",
                help="留空则使用推荐TOP3方案",
            )

    # ---- Run Button ----
    run_clicked = st.button("🚀 开始运行 Pipeline",
                             type="primary",
                             use_container_width=True,
                             help="点击开始完整Pipeline：提取需求→推荐→成本→对比→PDF")

    # ---- Pipeline Execution ----
    if run_clicked:
        # Determine tender text
        pipeline_tender = final_tender_text.strip()
        if not pipeline_tender:
            st.warning("⚠️ 请上传招标文件或粘贴文本摘要")
            st.stop()

        # Parse scenario IDs
        compare_ids = None
        if compare_sids_str.strip():
            try:
                compare_ids = [int(s.strip()) for s in compare_sids_str.split(",") if s.strip()]
            except ValueError:
                st.warning("方案ID格式错误，已使用默认TOP3")
                compare_ids = None

        # ---- Step 1: Extract ----
        step_holder = st.container()
        with step_holder:
            st.markdown("---")
            st.markdown("### 📋 Pipeline 执行状态")
            render_step_status("① 需求提取 (Requirement Extraction)", "wip")

        profile_overrides = {
            "industry": industry_p,
            "warehouse_area": float(warehouse_area_p),
            "sku_count": int(sku_count_p),
            "daily_orders": int(daily_orders_p),
            "inventory": int(inventory_p),
            "labor_cost_level": labor_cost_level_p,
            "budget_level": budget_level_p,
            "automation_expectation": "中",
        }

        with st.spinner("① 正在提取项目参数..."):
            extract_resp, err1 = call_api("/api/pipeline/extract", {"tender_document": pipeline_tender}, timeout=30)

        if err1:
            with step_holder:
                render_step_status("① 需求提取", "fail", err1)
            st.stop()

        profile = extract_resp.get("project_profile", {})
        missing_p0 = extract_resp.get("missing_p0", [])
        confidence = extract_resp.get("extraction_confidence", 0)
        summary_text = extract_resp.get("raw_requirements_summary", "")
        with step_holder:
            render_step_status("① 需求提取", "done",
                              f"置信度 {confidence:.0%} | 行业: {profile.get('industry','?')} | 缺失P0: {missing_p0 or '无'}")

        # Apply overrides
        profile.update(profile_overrides)

        # Step 2: Recommend
        render_step_status("② 自动化推荐 (Solution Architect)", "wip")
        rec_result, err2 = call_api("/api/recommend", profile, timeout=30)
        if err2:
            with step_holder:
                render_step_status("② 自动化推荐", "fail", err2)
            st.stop()
        recs = rec_result.get("recommendations", [])
        with step_holder:
            render_step_status("② 自动化推荐", "done",
                              f"生成 {len(recs)} 个推荐方案 | 首选: {recs[0]['scenario_name'] if recs else 'N/A'}")

        # Step 3: Cost Comparison
        render_step_status("③ 成本与ROI计算 (Cost Model)", "wip")
        if compare_ids and len(compare_ids) >= 2:
            cmp_payload = {**profile, "region": region_p, "scenario_ids": compare_ids}
            cmp_result, err3 = call_api("/api/compare", cmp_payload, timeout=30)
            comparisons = cmp_result.get("comparisons", []) if cmp_result else []
        else:
            top3_ids = [r["scenario_id"] for r in recs[:3]]
            if len(top3_ids) >= 2:
                cmp_payload = {**profile, "region": region_p, "scenario_ids": top3_ids}
                cmp_result, err3 = call_api("/api/compare", cmp_payload, timeout=30)
                comparisons = cmp_result.get("comparisons", []) if cmp_result else []
            else:
                comparisons = []

        if comparisons:
            best_cmp = next((c for c in comparisons if c.get("is_best")), comparisons[0])
            with step_holder:
                render_step_status("③ 成本与ROI计算", "done",
                                  f"最佳方案: {best_cmp['scenario_name']} | "
                                  f"ROI: {best_cmp.get('roi_5y', 0):.1f}x | "
                                  f"回本: {best_cmp.get('payback_years', 0):.1f}年")
        else:
            with step_holder:
                render_step_status("③ 成本与ROI计算", "fail", "未能生成有效成本对比")
            st.stop()

        # Step 4: Multi-Solution Comparison
        render_step_status("④ 多方案横向对比 (Comparison Engine)", "done",
                          f"{len(comparisons)} 个方案已对比排序")

        # Step 5: PDF Generation
        render_step_status("⑤ PDF报告生成 (Report Generator)", "wip")
        pdf_bytes = None
        pdf_filename = None
        try:
            pdf_resp = requests.post(
                f"{API_BASE_URL}/api/report",
                json={
                    "project_name": profile.get("project_name", "投标项目"),
                    "industry": profile.get("industry", "电商"),
                    "warehouse_area": float(profile.get("warehouse_area", 20000)),
                    "sku_count": int(profile.get("sku_count", 30000)),
                    "daily_orders": int(profile.get("daily_orders", 5000)),
                    "inventory": int(profile.get("inventory", 500000)),
                    "labor_cost_level": profile.get("labor_cost_level", "中"),
                    "budget_level": profile.get("budget_level", "中"),
                    "automation_expectation": profile.get("automation_expectation", "中"),
                    "region": region_p,
                },
                timeout=60,
            )
            if pdf_resp.status_code == 200:
                pdf_bytes = pdf_resp.content
                pdf_filename = f"{profile.get('project_name', '投标项目')}_方案建议书.pdf"
                with step_holder:
                    render_step_status("⑤ PDF报告生成", "done", f"PDF大小: {len(pdf_bytes)/1024:.0f}KB")
            else:
                with step_holder:
                    render_step_status("⑤ PDF报告生成", "fail", f"HTTP {pdf_resp.status_code}")
        except Exception as e:
            with step_holder:
                render_step_status("⑤ PDF报告生成", "fail", str(e))

        # ---- Results Section ----
        st.markdown("---")
        st.markdown("## 📊 Pipeline 执行结果")

        # Profile summary
        with st.expander("📋 提取的项目画像", expanded=True):
            cols = st.columns(4)
            cols[0].metric("行业", profile.get("industry", "—"))
            cols[1].metric("地区", profile.get("region", "—"))
            cols[2].metric("仓库面积", f"{profile.get('warehouse_area', 0):,.0f}㎡")
            cols[3].metric("日均订单", f"{profile.get('daily_orders', 0):,}")
            cols2 = st.columns(4)
            cols2[0].metric("SKU数量", f"{profile.get('sku_count', 0):,}")
            cols2[1].metric("库存量", f"{profile.get('inventory', 0):,}")
            cols2[2].metric("预算水平", profile.get("budget_level", "—"))
            cols2[3].metric("人工成本", profile.get("labor_cost_level", "—"))

        # Comparison table
        if comparisons:
            st.subheader("⚖️ 多方案ROI对比结果")
            rows = []
            for c in comparisons:
                rows.append({
                    "方案": ("✅ " if c.get("is_best") else "  ") + c["scenario_name"],
                    "类别": c["category"],
                    "投资 (万)": f"{c['automation_capex']/10000:.0f}",
                    "年节省 (万)": f"{c['annual_saving']/10000:.1f}",
                    "5年ROI": f"{c['roi_5y']:.1f}x",
                    "回本周期": f"{c['payback_years']:.1f}年",
                    "省人数": f"{c['headcount_saved']}人",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            # KPI cards
            best = next((c for c in comparisons if c.get("is_best")), comparisons[0])
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("🥇 最佳方案", best.get("scenario_name", "—"))
            k2.metric("5年ROI", f"{best.get('roi_5y', 0):.1f}x")
            k3.metric("回本周期", f"{best.get('payback_years', 0):.1f}年")
            k4.metric("年节省", f"{best.get('annual_saving', 0)/10000:.1f}万")

            # Charts
            t1, t2, t3 = st.tabs(["📊 投资与年节省", "📈 ROI对比", "🎯 综合雷达图"])
            with t1:
                st.plotly_chart(render_compare_bar_chart(comparisons), use_container_width=True)
            with t2:
                st.plotly_chart(render_compare_roi_chart(comparisons), use_container_width=True)
            with t3:
                st.plotly_chart(render_compare_radar(comparisons), use_container_width=True)

        # Recommendations
        if recs:
            st.subheader("🎯 自动化方案推荐 (TOP 5)")
            for i, rec in enumerate(recs[:5]):
                with st.expander(
                    f"{'🥇' if i==0 else '🥈' if i==1 else '🥉' if i==2 else '📌'} "
                    f"#{i+1} {rec['scenario_name']} — {rec['score']:.0f}分",
                    expanded=(i == 0),
                ):
                    c_a, c_b = st.columns([2, 1])
                    with c_a:
                        st.markdown(f"**类别:** {rec['category']}  |  **风险:** {rec['risk']}")
                        st.markdown(f"**推荐理由:** {rec['reason']}")
                        st.markdown(f"**人工节省:** {rec['labor_saving']*100:.0f}%  |  "
                                  f"**效率提升:** {rec['efficiency_gain']*100:.0f}%  |  "
                                  f"**投资范围:** {rec['capex_range']}")
                    with c_b:
                        st.plotly_chart(render_score_gauge(rec["score"]),
                                        use_container_width=True, key=f"pipeline_score_{i}")

        # PDF Download
        if pdf_bytes:
            st.markdown("---")
            st.success("✅ Pipeline 执行完成！PDF报告已生成。")
            st.download_button(
                "📄 下载完整PDF方案建议书",
                data=pdf_bytes,
                file_name=pdf_filename,
                mime="application/pdf",
                type="primary",
                use_container_width=True,
            )
        else:
            st.warning("PDF报告未能生成，可尝试手动从『方案生成』模式导出")

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
    }), use_container_width=True, hide_index=True)


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
        "ID": [s[0] for s in [(1,"AMR拣选辅助"),(2,"GTP货到人系统"),(3,"输送分拣线"),
                      (4,"自动贴标系统"),(5,"立体仓库AS/RS"),(6,"自动化输送线"),
                      (7,"视觉识别质检"),(8,"拆码垛机器人"),(9,"WMS仓储管理系统"),
                      (10,"AGV搬运系统"),(11,"自动包装线"),(12,"冷链自动化仓储"),
                      (13,"跨带分拣机"),(14,"货架式密集存储"),(15,"自动化退货处理")]],
        "方案名称": [s[1] for s in [(1,"AMR拣选辅助"),(2,"GTP货到人系统"),(3,"输送分拣线"),
                      (4,"自动贴标系统"),(5,"立体仓库AS/RS"),(6,"自动化输送线"),
                      (7,"视觉识别质检"),(8,"拆码垛机器人"),(9,"WMS仓储管理系统"),
                      (10,"AGV搬运系统"),(11,"自动包装线"),(12,"冷链自动化仓储"),
                      (13,"跨带分拣机"),(14,"货架式密集存储"),(15,"自动化退货处理")]],
        "类别": ["移动机器人","货到人","输送分拣","自动化辅助","立体仓库","输送系统",
                 "视觉检测","搬运机器人","软件系统","移动机器人","包装自动化","冷链系统",
                 "高速分拣","密集存储","逆向物流"],
    })
    st.dataframe(all_sc, use_container_width=True, hide_index=True)