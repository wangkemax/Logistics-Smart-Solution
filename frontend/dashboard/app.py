import streamlit as st
import requests
import json
import os
import pandas as pd
import plotly.graph_objects as go

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
    .main-header { font-size: 2.5rem; font-weight: bold; color: #1f4e79;
                   text-align: center; padding: 1rem 0; border-bottom: 3px solid #2196f3;
                   margin-bottom: 2rem; }
    .risk-low  { color: #4caf50; font-weight: bold; }
    .risk-mid  { color: #ff9800; font-weight: bold; }
    .risk-high { color: #f44336; font-weight: bold; }
    .best-badge { background: #27ae60; color: white; padding: 2px 10px;
                  border-radius: 10px; font-size: 10pt; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header">🏭 物流自动化预售AI系统</div>', unsafe_allow_html=True)
st.markdown("##### 智能推荐仓储自动化方案 · 精准测算投资回报")

# ---- Helper Functions ----
def call_api(url, payload, timeout=30):
    try:
        resp = requests.post(f"{API_BASE_URL}{url}", json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json(), None
    except requests.exceptions.ConnectionError:
        return None, "无法连接到后端服务，请确保后端已启动 (uvicorn backend.main:app)"
    except Exception as e:
        return None, f"API调用失败: {e}"

def call_compare_api(payload):
    return call_api("/api/compare", payload)

def render_score_gauge(score):
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
    fig = go.Figure(data=[go.Bar(x=labels, y=values, marker_color=colors,
                                   text=[f"¥{v:.0f}万" for v in values], textposition="auto")])
    fig.update_layout(title="年度成本构成 (万元)", yaxis_title="金额 (万元)",
                      height=300, margin=dict(l=10, r=10, t=40, b=10))
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
                      yaxis_title="金额 (万元)", height=300,
                      margin=dict(l=10, r=10, t=40, b=10))
    return fig

def render_compare_bar_chart(comparisons):
    """Render grouped bar chart comparing CAPEX and annual savings across scenarios."""
    names = [c["scenario_name"][:8] for c in comparisons]
    capex = [c["automation_capex"] / 10000 for c in comparisons]
    savings = [c["annual_saving"] / 10000 for c in comparisons]
    fig = go.Figure(data=[
        go.Bar(name="自动化投资 (万)", x=names, y=capex, marker_color="#ef5350"),
        go.Bar(name="年节省人工 (万)", x=names, y=savings, marker_color="#4caf50"),
    ])
    fig.update_layout(barmode="group", title="方案投资与年节省对比 (万元)",
                      yaxis_title="金额 (万元)", height=300,
                      margin=dict(l=10, r=10, t=40, b=10))
    return fig

def render_compare_radar(comparisons):
    """Render radar chart comparing normalized KPIs across scenarios."""
    categories = ["5年ROI", "回本周期(逆向)", "年节省(万)", "人工节省"]
    # Normalize each metric to 0-100 scale
    max_roi = max(c["roi_5y"] for c in comparisons) or 1
    max_payback = max(c["payback_years"] for c in comparisons) or 1
    max_saving = max(c["annual_saving"] for c in comparisons) or 1
    max_hc = max(c["headcount_saved"] for c in comparisons) or 1

    traces = []
    colors = ["#2196f3", "#4caf50", "#ff9800", "#9c27b0", "#f44336"]
    for i, c in enumerate(comparisons[:5]):
        values = [
            (c["roi_5y"] / max_roi) * 100,
            (1 - c["payback_years"] / max_payback) * 100,
            (c["annual_saving"] / max_saving) * 100,
            (c["headcount_saved"] / max_hc) * 100,
            100,  # close the polygon
        ]
        rad_labels = ["5年ROI", "回本周期", "年节省", "人工节省", ""]
        traces.append(go.Scatterpolar(
            r=values, theta=rad_labels,
            name=c["scenario_name"][:8],
            fill="toself" if i == 0 else None,
            line=dict(color=colors[i % len(colors)]),
        ))
    fig = go.Figure(data=traces)
    fig.update_layout(title="多方案综合指标雷达图",
                      polar=dict(radialaxis=dict(range=[0, 100])),
                      height=320, margin=dict(l=10, r=10, t=40, b=10))
    return fig

def render_compare_roi_chart(comparisons):
    """Render horizontal bar chart for ROI comparison."""
    sorted_comps = sorted(comparisons, key=lambda x: x["roi_5y"], reverse=True)
    names = [c["scenario_name"][:10] for c in sorted_comps]
    roi_5y = [c["roi_5y"] for c in sorted_comps]
    colors = ["#27ae60" if c.get("is_best") else "#95a5a6" for c in sorted_comps]
    fig = go.Figure(data=[go.Bar(
        y=names, x=roi_5y, orientation="h",
        marker_color=colors, text=[f"{r:.1f}x" for r in roi_5y], textposition="auto",
    )])
    fig.update_layout(title="5年ROI倍数对比", xaxis_title="ROI (倍)",
                     height=max(200, len(comparisons) * 60),
                     margin=dict(l=10, r=10, t=40, b=10))
    return fig

# ---- Sidebar ----
with st.sidebar:
    st.header("🏭 Logistics Smart Solution")

    app_mode = st.radio(
        "选择功能模式",
        options=["📋 方案生成", "⚖️ 多方案对比"],
        index=0,
        help="方案生成：推荐最优方案并生成PDF\n多方案对比：横向对比2-5个方案的ROI与成本",
    )

    st.divider()

    # ---- Mode 1: Single Scenario ----
    single_submitted = False
    compare_submitted = False

    if app_mode == "📋 方案生成":
        st.subheader("📋 项目信息输入")

        with st.form("project_form"):
            project_name = st.text_input("项目名称", value="新建项目-001", placeholder="请输入项目名称")
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

    # ---- Mode 2: Multi-Scenario Comparison ----
    else:
        st.subheader("⚖️ 多方案对比")

        with st.form("compare_form"):
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
                (1, "AMR拣选辅助"),     (2, "GTP货到人系统"),   (3, "输送分拣线"),
                (4, "自动贴标系统"),    (5, "立体仓库AS/RS"),   (6, "自动化输送线"),
                (7, "视觉识别质检"),    (8, "拆码垛机器人"),     (9, "WMS仓储管理系统"),
                (10, "AGV搬运系统"),   (11, "自动包装线"),     (12, "冷链自动化仓储"),
                (13, "跨带分拣机"),    (14, "货架式密集存储"),  (15, "自动化退货处理"),
            ]
            selected_scenario_labels = st.multiselect(
                "勾选要对比的方案",
                options=[label for _, label in ALL_SCENARIOS],
                default=["AMR拣选辅助", "GTP货到人系统", "输送分拣线"],
                help="选择2-5个方案进行横向对比",
            )
            selected_scenario_ids = [sid for sid, label in ALL_SCENARIOS if label in selected_scenario_labels]

            compare_submitted = st.form_submit_button("⚖️ 开始对比",
                                                     use_container_width=True, type="primary")

# =============================================================================
# MAIN CONTENT: Mode 1 — Single Scenario
# =============================================================================
if app_mode == "📋 方案生成" and single_submitted:
    profile = {
        "industry": industry, "warehouse_area": float(warehouse_area),
        "sku_count": int(sku_count), "daily_orders": int(daily_orders),
        "inventory": int(inventory), "labor_cost_level": labor_cost_level,
        "budget_level": budget_level, "automation_expectation": automation_expectation,
    }

    with st.spinner("AI正在分析您的项目需求..."):
        rec_result, err1 = call_api("/api/recommend", profile)
        scenario_id = rec_result["recommendations"][0]["scenario_id"] if rec_result and rec_result["recommendations"] else None
        cost_result, err2 = call_api("/api/cost", {**profile, "region": region, "selected_scenario_id": scenario_id})

    if err1:
        st.error(err1)
    elif err2:
        st.error(err2)
    elif rec_result and cost_result:
        st.success(f"✅ 方案生成完成 | 项目: {project_name} | 行业: {industry} | 地区: {region}")

        tab1, tab2, tab3 = st.tabs(["🎯 方案推荐", "💰 成本分析", "📊 综合报告"])

        with tab1:
            st.subheader("自动化场景推荐")
            st.info(rec_result.get("analysis_summary", ""))
            recommendations = rec_result.get("recommendations", [])

            if recommendations:
                top = recommendations[0]
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("首选方案", top["scenario_name"])
                col2.metric("匹配评分", f"{top['score']:.0f}/100")
                col3.metric("人工节省", f"{int(top['labor_saving']*100)}%")
                col4.metric("效率提升", f"{int(top['efficiency_gain']*100)}%")
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
                            st.plotly_chart(render_score_gauge(rec["score"]), use_container_width=True)
            else:
                st.warning("未找到匹配的自动化方案，请调整项目参数")

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
            col_chart1, col_chart2 = st.columns(2)
            with col_chart1:
                st.plotly_chart(render_cost_chart(cost_data), use_container_width=True)
            with col_chart2:
                st.plotly_chart(render_roi_chart(cost_data), use_container_width=True)

            st.subheader("优化建议")
            for rec_text in cost_result.get("recommendations", []):
                st.markdown(f"- {rec_text}")

        with tab3:
            st.subheader("项目综合报告")
            top_rec = rec_result["recommendations"][0] if rec_result["recommendations"] else {}
            cost_d = cost_result["cost_breakdown"]

            st.markdown(f"""
## {project_name} — 仓储自动化解决方案摘要

### 项目基本信息
| 参数 | 数值 |
|------|------|
| 行业 | {industry} |
| 仓库面积 | {warehouse_area:,} ㎡ |
| SKU数量 | {sku_count:,} |
| 日均订单量 | {daily_orders:,} 单/天 |
| 库存量 | {inventory:,} 件 |

### 推荐方案
**首选方案**: {top_rec.get('scenario_name', 'N/A')}
{top_rec.get('reason', '')}
**风险提示**: {top_rec.get('risk', '')}

### 投资回报摘要
- **自动化投资**: ¥{cost_d['automation_capex']/10000:.0f}万元
- **年节省人工**: ¥{cost_d['automation_savings_annual']/10000:.1f}万元
- **净年度收益**: ¥{cost_d['net_annual_benefit']/10000:.1f}万元
- **5年投资回报**: {cost_d['roi']:.1f}倍
- **回本周期**: {cost_d['payback_years']:.1f}年
- **预计减少人员**: {cost_d['headcount_saved']}人
""")
            st.divider()

            # JSON export
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

            # PDF export
            if st.button("📄 生成并下载PDF方案报告", type="primary", use_container_width=True):
                with st.spinner("正在生成PDF报告..."):
                    pdf_payload = {
                        "project_name": project_name, "industry": industry,
                        "warehouse_area": float(warehouse_area), "sku_count": int(sku_count),
                        "daily_orders": int(daily_orders), "inventory": int(inventory),
                        "labor_cost_level": labor_cost_level, "budget_level": budget_level,
                        "automation_expectation": automation_expectation, "region": region,
                    }
                    resp, err = None, None
                    try:
                        resp = requests.post(f"{API_BASE_URL}/api/report",
                                              json=pdf_payload, timeout=60)
                    except Exception as e:
                        err = str(e)
                    if err:
                        st.error(f"连接错误: {err}")
                    elif resp is None:
                        st.error("后端未响应")
                    elif resp.status_code == 200:
                        st.success("✅ PDF报告已生成！")
                        st.download_button("⬇️ 点击下载PDF方案建议书",
                                           data=resp.content,
                                           file_name=f"{project_name}_方案建议书.pdf",
                                           mime="application/pdf")
                    elif resp.status_code == 503:
                        st.error("PDF服务暂不可用，请确保后端已安装 jinja2 和 weasyprint")
                    else:
                        st.error(f"生成失败: {resp.status_code}")

# =============================================================================
# MAIN CONTENT: Mode 2 — Multi-Scenario Comparison
# =============================================================================
elif app_mode == "⚖️ 多方案对比":
    if compare_submitted:
        if len(selected_scenario_ids) < 2:
            st.error("请至少选择2个方案进行对比")
        else:
            profile_cmp = {
                "industry": industry_cmp, "warehouse_area": float(warehouse_area_cmp),
                "sku_count": int(sku_count_cmp), "daily_orders": int(daily_orders_cmp),
                "inventory": int(inventory_cmp), "labor_cost_level": labor_cost_level_cmp,
                "budget_level": budget_level_cmp, "automation_expectation": "中",
            }
            payload = {**profile_cmp, "region": region_cmp, "scenario_ids": selected_scenario_ids}

            with st.spinner("正在计算多方案ROI对比..."):
                cmp_result, err = call_compare_api(payload)

            if err:
                st.error(err)
            elif cmp_result:
                comparisons = cmp_result.get("comparisons", [])
                best_id = cmp_result.get("best_scenario_id")

                st.success(f"✅ 对比完成 | 项目: {project_name_cmp} | {len(comparisons)}个方案 | 最佳: "
                           f"{next((c['scenario_name'] for c in comparisons if c['scenario_id']==best_id), 'N/A')}")

                st.info(cmp_result.get("analysis_summary", ""))

                # ---- Comparison Summary Table ----
                st.subheader("📊 方案对比总览")
                rows = []
                for c in comparisons:
                    rows.append({
                        "方案": (c["scenario_name"] + " ✅") if c["is_best"] else c["scenario_name"],
                        "类别": c["category"],
                        "投资 (万)": f"{c['automation_capex']/10000:.0f}",
                        "年节省 (万)": f"{c['annual_saving']/10000:.1f}",
                        "年维护 (万)": f"{c['annual_maintenance']/10000:.1f}",
                        "净年收益 (万)": f"{c['net_annual_benefit']/10000:.1f}",
                        "5年ROI": f"{c['roi_5y']:.1f}x",
                        "回本周期": f"{c['payback_years']:.1f}年",
                        "省人数": f"{c['headcount_saved']}人",
                    })
                df = pd.DataFrame(rows)
                st.dataframe(df, use_container_width=True, hide_index=True)

                st.divider()

                # ---- KPI Row ----
                col1, col2, col3, col4 = st.columns(4)
                best = next((c for c in comparisons if c.get("is_best")), comparisons[0] if comparisons else {})
                col1.metric("🥇 最佳方案", best.get("scenario_name", "—"))
                col2.metric("5年ROI", best.get("roi_5y", 0))
                col3.metric("回本周期", f"{best.get('payback_years', 0):.1f}年")
                col4.metric("年节省", f"{best.get('annual_saving', 0)/10000:.1f}万")

                st.divider()

                # ---- Charts ----
                st.subheader("📈 可视化对比")
                tab_chart1, tab_chart2, tab_chart3 = st.tabs(["投资与年节省", "5年ROI对比", "综合雷达图"])

                with tab_chart1:
                    st.plotly_chart(render_compare_bar_chart(comparisons), use_container_width=True)

                with tab_chart2:
                    st.plotly_chart(render_compare_roi_chart(comparisons), use_container_width=True)

                with tab_chart3:
                    st.plotly_chart(render_compare_radar(comparisons), use_container_width=True)

                st.divider()

                # ---- Detailed Comparison Table ----
                st.subheader("📋 详细参数对比")
                detail_rows = []
                for c in comparisons:
                    detail_rows.append({
                        "方案": c["scenario_name"],
                        "类别": c["category"],
                        "自动化投资": f"¥{c['automation_capex']/10000:.0f}万",
                        "年节省人工": f"¥{c['annual_saving']/10000:.1f}万",
                        "5年累计净收益": f"¥{c['five_year_net_benefit']/10000:.1f}万",
                        "5年ROI": f"{c['roi_5y']:.1f}x",
                        "回本周期": f"{c['payback_years']:.1f}年",
                        "节省人数/总人数": f"{c['headcount_saved']}/{c['headcount_required']}",
                    })
                st.dataframe(pd.DataFrame(detail_rows), use_container_width=True, hide_index=True)

    else:
        # Empty state for comparison mode
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
        all_scenarios_df = pd.DataFrame({
            "ID": [s[0] for s in ALL_SCENARIOS],
            "方案名称": [s[1] for s in ALL_SCENARIOS],
            "类别": ["移动机器人","货到人","输送分拣","自动化辅助","立体仓库","输送系统",
                     "视觉检测","搬运机器人","软件系统","移动机器人","包装自动化","冷链系统",
                     "高速分拣","密集存储","逆向物流"],
            "人工节省": ["30%","50%","40%","20%","60%","30%","25%","45%","15%","40%","35%","50%","55%","20%","30%"],
        })
        st.dataframe(all_scenarios_df, use_container_width=True, hide_index=True)

# =============================================================================
# Welcome Screen (neither mode submitted)
# =============================================================================
else:
    if app_mode == "📋 方案生成":
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
