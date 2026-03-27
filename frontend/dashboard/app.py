import streamlit as st
import requests
import json
import os
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(
    page_title="物流预售AI系统",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f4e79;
        text-align: center;
        padding: 1rem 0;
        border-bottom: 3px solid #2196f3;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: #f8f9fa;
        border-radius: 10px;
        padding: 1rem;
        border-left: 4px solid #2196f3;
    }
    .recommendation-card {
        background: white;
        border-radius: 10px;
        padding: 1.5rem;
        border: 1px solid #e0e0e0;
        margin-bottom: 1rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .score-badge {
        background: #2196f3;
        color: white;
        border-radius: 20px;
        padding: 0.3rem 0.8rem;
        font-weight: bold;
    }
    .risk-low { color: #4caf50; font-weight: bold; }
    .risk-mid { color: #ff9800; font-weight: bold; }
    .risk-high { color: #f44336; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header">🏭 物流自动化预售AI系统</div>', unsafe_allow_html=True)
st.markdown("##### 智能推荐仓储自动化方案 · 精准测算投资回报")


def call_recommend_api(profile):
    try:
        response = requests.post(f"{API_BASE_URL}/api/recommend", json=profile, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        st.error("无法连接到后端服务，请确保后端已启动 (python -m uvicorn backend.main:app)")
        return None
    except Exception as e:
        st.error(f"API调用失败: {str(e)}")
        return None


def call_cost_api(profile, region, scenario_id=None):
    try:
        payload = {**profile, "region": region}
        if scenario_id:
            payload["selected_scenario_id"] = scenario_id
        response = requests.post(f"{API_BASE_URL}/api/cost", json=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        st.error("无法连接到后端服务")
        return None
    except Exception as e:
        st.error(f"成本计算失败: {str(e)}")
        return None


def render_score_gauge(score):
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
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
            "threshold": {
                "line": {"color": "red", "width": 4},
                "thickness": 0.75,
                "value": 70,
            },
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

    fig = go.Figure(data=[
        go.Bar(
            x=labels,
            y=values,
            marker_color=colors,
            text=[f"¥{v:.0f}万" for v in values],
            textposition="auto",
        )
    ])
    fig.update_layout(
        title="年度成本构成 (万元)",
        yaxis_title="金额 (万元)",
        height=300,
        margin=dict(l=10, r=10, t=40, b=10),
    )
    return fig


def render_roi_chart(cost_data):
    capex = cost_data["automation_capex"] / 10000
    annual_saving = cost_data["automation_savings_annual"] / 10000
    annual_cost = cost_data["annual_maintenance"] / 10000

    years = list(range(0, 8))
    cumulative_benefit = [max(0, (annual_saving - annual_cost) * y - capex) for y in years]
    cumulative_investment = [capex] * len(years)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=years, y=cumulative_benefit,
        mode="lines+markers", name="累计净收益",
        line=dict(color="#4caf50", width=3),
    ))
    fig.add_trace(go.Scatter(
        x=years, y=cumulative_investment,
        mode="lines", name="投资额",
        line=dict(color="#f44336", width=2, dash="dash"),
    ))
    fig.add_hline(y=0, line_dash="dot", line_color="gray")
    fig.update_layout(
        title="投资回报趋势 (万元)",
        xaxis_title="年份",
        yaxis_title="金额 (万元)",
        height=300,
        margin=dict(l=10, r=10, t=40, b=10),
    )
    return fig


# ============================================================
# SIDEBAR - Input Form
# ============================================================
with st.sidebar:
    st.header("📋 项目信息输入")

    with st.form("project_form"):
        st.subheader("基本信息")
        project_name = st.text_input("项目名称", value="新建项目-001", placeholder="请输入项目名称")

        industry = st.selectbox(
            "行业类型",
            options=["电商", "3PL", "零售", "制造", "快递", "医药", "食品", "生鲜"],
            index=0,
        )

        region = st.selectbox(
            "所在区域",
            options=["华东", "华南", "华北", "华中", "西部"],
            index=0,
        )

        st.subheader("仓库参数")
        warehouse_area = st.number_input(
            "仓库面积 (㎡)", min_value=500, max_value=500000,
            value=20000, step=1000,
        )

        sku_count = st.number_input(
            "SKU数量", min_value=100, max_value=1000000,
            value=30000, step=1000,
        )

        daily_orders = st.number_input(
            "日均订单量", min_value=50, max_value=500000,
            value=5000, step=100,
        )

        inventory = st.number_input(
            "库存量 (件)", min_value=1000, max_value=10000000,
            value=500000, step=10000,
        )

        st.subheader("成本与预算")
        labor_cost_level = st.select_slider(
            "人工成本水平",
            options=["低", "中", "高"],
            value="中",
        )

        budget_level = st.select_slider(
            "自动化预算",
            options=["低", "中", "高"],
            value="中",
        )

        automation_expectation = st.select_slider(
            "自动化期望程度",
            options=["低", "中", "高"],
            value="中",
        )

        submitted = st.form_submit_button(
            "🚀 生成解决方案",
            use_container_width=True,
            type="primary",
        )

# ============================================================
# MAIN CONTENT
# ============================================================
if submitted:
    profile = {
        "industry": industry,
        "warehouse_area": float(warehouse_area),
        "sku_count": int(sku_count),
        "daily_orders": int(daily_orders),
        "inventory": int(inventory),
        "labor_cost_level": labor_cost_level,
        "budget_level": budget_level,
        "automation_expectation": automation_expectation,
    }

    with st.spinner("AI正在分析您的项目需求..."):
        rec_result = call_recommend_api(profile)
        cost_result = call_cost_api(
            profile, region,
            scenario_id=rec_result["recommendations"][0]["scenario_id"] if rec_result and rec_result["recommendations"] else None
        )

    if rec_result and cost_result:
        # Summary banner
        st.success(f"✅ 方案生成完成 | 项目: {project_name} | 行业: {industry} | 地区: {region}")

        tab1, tab2, tab3 = st.tabs(["🎯 方案推荐", "💰 成本分析", "📊 综合报告"])

        # ---- Tab 1: Recommendations ----
        with tab1:
            st.subheader("自动化场景推荐")
            st.info(rec_result.get("analysis_summary", ""))

            recommendations = rec_result.get("recommendations", [])

            if recommendations:
                # Top recommendation highlight
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

        # ---- Tab 2: Cost Analysis ----
        with tab2:
            st.subheader("成本与ROI分析")

            cost_data = cost_result["cost_breakdown"]
            st.info(cost_result.get("summary", ""))

            # Key metrics
            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("总投资", f"¥{cost_data['automation_capex']/10000:.0f}万")
            col2.metric("年节省人工", f"¥{cost_data['automation_savings_annual']/10000:.1f}万")
            col3.metric("5年ROI", f"{cost_data['roi']:.1f}x")
            col4.metric("回本周期", f"{cost_data['payback_years']:.1f}年")
            col5.metric("节省人数", f"{cost_data['headcount_saved']}人")

            st.divider()

            col_chart1, col_chart2 = st.columns(2)
            with col_chart1:
                st.plotly_chart(render_cost_chart(cost_data), use_container_width=True)
            with col_chart2:
                st.plotly_chart(render_roi_chart(cost_data), use_container_width=True)

            st.subheader("优化建议")
            for rec_text in cost_result.get("recommendations", []):
                st.markdown(f"- {rec_text}")

        # ---- Tab 3: Summary Report ----
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

### 实施建议
{chr(10).join(['- ' + r for r in cost_result.get('recommendations', [])])}
            """)

            # Export button (simulated)
            report_data = {
                "project_name": project_name,
                "profile": profile,
                "recommendations": rec_result.get("recommendations", []),
                "cost_breakdown": cost_result.get("cost_breakdown", {}),
                "summary": cost_result.get("summary", ""),
            }
            st.download_button(
                "📥 下载JSON报告",
                data=json.dumps(report_data, ensure_ascii=False, indent=2),
                file_name=f"{project_name}_solution.json",
                mime="application/json",
            )

else:
    # Welcome screen
    st.markdown("""
    <div style="text-align: center; padding: 3rem; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                border-radius: 15px; color: white; margin: 2rem 0;">
        <h2>欢迎使用物流自动化预售AI系统</h2>
        <p style="font-size: 1.1rem; margin: 1rem 0;">
            在左侧填写项目信息，点击"生成解决方案"即可获得：
        </p>
        <div style="display: flex; justify-content: space-around; margin: 2rem 0;">
            <div>🎯<br><b>智能推荐</b><br>匹配最优自动化方案</div>
            <div>💰<br><b>成本分析</b><br>精准测算投资回报</div>
            <div>📊<br><b>综合报告</b><br>一键生成解决方案摘要</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Show sample scenarios
    st.subheader("📚 支持的自动化场景")
    scenarios_data = {
        "方案类型": ["AMR移动机器人", "GTP货到人系统", "输送分拣线", "立体仓库AS/RS", "跨带分拣机"],
        "适用行业": ["电商/3PL/零售", "电商/3PL", "电商/快递/零售", "制造/3PL/医药", "快递/电商"],
        "人工节省": ["30%", "50%", "40%", "60%", "55%"],
        "效率提升": ["40%", "60%", "50%", "70%", "65%"],
        "投资规模": ["50-200万", "200-800万", "100-500万", "500-2000万", "300-1000万"],
    }
    st.dataframe(pd.DataFrame(scenarios_data), use_container_width=True, hide_index=True)
