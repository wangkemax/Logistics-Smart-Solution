"""
Tests for the PDF report generator.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from report.generator import (
    build_report_data,
    render_html,
    generate_pdf,
    generate_pdf_filename,
    WEASYPRINT_AVAILABLE,
)


SAMPLE_PROFILE = {
    "industry": "电商",
    "warehouse_area": 20000,
    "sku_count": 30000,
    "daily_orders": 5000,
    "inventory": 500000,
    "labor_cost_level": "中",
    "budget_level": "中",
    "automation_expectation": "中",
}

SAMPLE_RECOMMENDATIONS = [
    {
        "scenario_id": 1,
        "scenario_name": "AMR拣选辅助",
        "category": "移动机器人",
        "score": 78.5,
        "reason": "适合电商行业，SKU多，效率提升明显",
        "risk": "中",
        "capex_range": "¥50万-¥200万",
        "labor_saving": 0.30,
        "efficiency_gain": 0.40,
    },
    {
        "scenario_id": 2,
        "scenario_name": "GTP货到人系统",
        "category": "货到人",
        "score": 72.0,
        "reason": "高SKU场景适合货到人方案",
        "risk": "高",
        "capex_range": "¥200万-¥800万",
        "labor_saving": 0.50,
        "efficiency_gain": 0.60,
    },
]

SAMPLE_COST = {
    "warehouse_cost": 12000000,
    "labor_cost_annual": 4800000,
    "automation_capex": 1250000,
    "annual_maintenance": 62500,
    "total_annual_cost": 17225000,
    "automation_savings_annual": 450000,
    "net_annual_benefit": 387500,
    "roi": 1.55,
    "payback_years": 3.2,
    "headcount_required": 35,
    "headcount_saved": 12,
}

SAMPLE_SUMMARY = "项目预计总投资125万元，5年ROI达到1.55x，预计回本周期3.2年。"
SAMPLE_COST_RECS = ["ROI表现良好，建议推进", "回本周期适中，可优先考虑"]


class TestBuildReportData:
    def test_build_report_data_creates_valid_structure(self):
        data = build_report_data(
            project_name="测试项目",
            profile=SAMPLE_PROFILE,
            recommendations=SAMPLE_RECOMMENDATIONS,
            cost_data=SAMPLE_COST,
            cost_summary=SAMPLE_SUMMARY,
            cost_recommendations=SAMPLE_COST_RECS,
            region="华东",
        )

        assert data["project_name"] == "测试项目"
        assert data["profile"]["industry"] == "电商"
        assert data["profile"]["region"] == "华东"
        assert len(data["recommendations"]) == 2
        assert data["recommendations"][0]["scenario_name"] == "AMR拣选辅助"
        assert data["cost"]["roi"] == 1.55

    def test_recommendations_limited_to_top_3(self):
        many_recs = [
            {**SAMPLE_RECOMMENDATIONS[0], "scenario_id": i}
            for i in range(10)
        ]
        data = build_report_data(
            project_name="测试",
            profile=SAMPLE_PROFILE,
            recommendations=many_recs,
            cost_data=SAMPLE_COST,
            cost_summary=SAMPLE_SUMMARY,
            cost_recommendations=SAMPLE_COST_RECS,
        )
        assert len(data["recommendations"]) == 3


class TestRenderHtml:
    def test_render_html_produces_non_empty_html(self):
        data = build_report_data(
            project_name="测试项目",
            profile=SAMPLE_PROFILE,
            recommendations=SAMPLE_RECOMMENDATIONS,
            cost_data=SAMPLE_COST,
            cost_summary=SAMPLE_SUMMARY,
            cost_recommendations=SAMPLE_COST_RECS,
        )
        html = render_html(data)
        assert len(html) > 1000
        assert "<html" in html
        assert "AMR拣选辅助" in html
        assert "电商" in html


class TestPdfFilename:
    def test_filename_contains_project_name(self):
        filename = generate_pdf_filename("我的测试项目")
        assert "我的测试项目" in filename or "我的测试项目".replace(" ", "_") in filename
        assert filename.endswith(".pdf")

    def test_filename_is_unique_per_call(self):
        import time
        time.sleep(1.1)  # Wait for timestamp to advance
        f1 = generate_pdf_filename("同一项目")
        f2 = generate_pdf_filename("同一项目")
        # Timestamps should differ after 1+ second
        assert f1 != f2


class TestPdfGeneration:
    @classmethod
    def setup_class(cls):
        # Skip if WeasyPrint not available
        if not WEASYPRINT_AVAILABLE:
            import pytest
            pytest.skip("WeasyPrint not installed")

    def test_generate_pdf_creates_file(self, tmp_path):
        output = generate_pdf(
            project_name="单元测试项目",
            profile=SAMPLE_PROFILE,
            recommendations=SAMPLE_RECOMMENDATIONS,
            cost_data=SAMPLE_COST,
            cost_summary=SAMPLE_SUMMARY,
            cost_recommendations=SAMPLE_COST_RECS,
            region="华东",
        )
        assert Path(output).exists()
        assert Path(output).stat().st_size > 10000  # at least 10KB

    def test_generate_pdf_returns_absolute_path(self):
        output = generate_pdf(
            project_name="路径测试",
            profile=SAMPLE_PROFILE,
            recommendations=SAMPLE_RECOMMENDATIONS,
            cost_data=SAMPLE_COST,
            cost_summary=SAMPLE_SUMMARY,
            cost_recommendations=SAMPLE_COST_RECS,
        )
        assert Path(output).is_absolute()
