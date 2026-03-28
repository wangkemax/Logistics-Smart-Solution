"""
FastAPI Report Generation Endpoint
POST /api/report — Generate PDF proposal report
"""

import os
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse
from urllib.parse import quote
from pydantic import BaseModel, Field

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.services.project_service import get_recommendations, get_cost_analysis
from report.generator import generate_pdf, generate_pdf_bytes, WEASYPRINT_AVAILABLE


router = APIRouter(prefix="/api", tags=["report"])

# Absolute path to report generator
REPORT_MODULE = Path(__file__).parent.parent.parent / "report"
sys.path.insert(0, str(REPORT_MODULE.parent))


class ReportRequest(BaseModel):
    """Request body for PDF report generation."""
    project_name: str = Field(default="投标项目", description="项目名称")
    industry: str = Field(default="电商", description="行业类型")
    warehouse_area: float = Field(default=20000.0, description="仓库面积 (平方米)")
    sku_count: int = Field(default=30000, description="SKU数量")
    daily_orders: int = Field(default=5000, description="日均订单量")
    inventory: int = Field(default=500000, description="库存量")
    labor_cost_level: str = Field(default="中", description="人工成本水平")
    budget_level: str = Field(default="中", description="自动化预算")
    automation_expectation: str = Field(default="中", description="自动化期望")
    region: str = Field(default="华东", description="所在区域")
    selected_scenario_id: Optional[int] = Field(default=None, description="指定方案ID")
    company_name: str = Field(default="飞力达物流", description="报告编制单位名称")
    language: str = Field(default="cn", description="报告语言: cn=中文, en=英文")


class ReportCompareRequest(BaseModel):
    """Request body for PDF comparison report."""
    project_name: str = Field(default="多方案对比", description="项目名称")
    industry: str = Field(default="电商")
    warehouse_area: float = Field(default=20000.0)
    sku_count: int = Field(default=30000)
    daily_orders: int = Field(default=5000)
    inventory: int = Field(default=500000)
    labor_cost_level: str = Field(default="中")
    budget_level: str = Field(default="中")
    automation_expectation: str = Field(default="中")
    region: str = Field(default="华东")
    scenario_ids: str = Field(default="", description="逗号分隔的方案ID，如 '1,2,3'")


@router.post("/report")
def generate_proposal_report(request: ReportRequest):
    """
    Generate a PDF proposal report for the given project parameters.

    Returns the PDF file as a downloadable attachment.
    """
    if not WEASYPRINT_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=(
                "PDF generation is not available. "
                "Jinja2 is required. Install: pip install jinja2 weasyprint"
            ),
        )

    # Build project profile
    profile = {
        "industry": request.industry,
        "warehouse_area": request.warehouse_area,
        "sku_count": request.sku_count,
        "daily_orders": request.daily_orders,
        "inventory": request.inventory,
        "labor_cost_level": request.labor_cost_level,
        "budget_level": request.budget_level,
        "automation_expectation": request.automation_expectation,
    }

    # Get recommendations and cost analysis
    rec_result = get_recommendations(profile)
    recommendations = rec_result.get("recommendations", [])

    cost_result = get_cost_analysis(profile, request.region, request.selected_scenario_id)
    cost_data = cost_result.get("cost_breakdown", {})
    cost_summary = cost_result.get("summary", "")
    cost_recommendations = cost_result.get("recommendations", [])

    # Generate PDF
    try:
        pdf_bytes, filename = generate_pdf_bytes(
            project_name=request.project_name,
            profile=profile,
            recommendations=recommendations,
            cost_data=cost_data,
            cost_summary=cost_summary,
            cost_recommendations=cost_recommendations,
            region=request.region,
            company_name=request.company_name,
            language=request.language,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{quote(filename, safe="")}"'
        },
    )


@router.get("/report/check")
def check_report_capability():
    """Check if PDF generation is available."""
    return {
        "pdf_available": WEASYPRINT_AVAILABLE,
        "weasyprint": WEASYPRINT_AVAILABLE,
        "message": (
            "PDF generation ready" if WEASYPRINT_AVAILABLE
            else "Install jinja2 and weasyprint to enable PDF generation"
        ),
    }


@router.post("/report/compare")
def generate_compare_report(request: ReportCompareRequest):
    """Generate a PDF comparison report for multiple automation scenarios."""
    if not WEASYPRINT_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Install jinja2 and weasyprint to enable PDF generation",
        )

    try:
        sid_list = [int(s.strip()) for s in request.scenario_ids.split(",") if s.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid scenario_ids format")

    if len(sid_list) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 scenario IDs")

    profile = {
        "industry": request.industry,
        "warehouse_area": request.warehouse_area,
        "sku_count": request.sku_count,
        "daily_orders": request.daily_orders,
        "inventory": request.inventory,
        "labor_cost_level": request.labor_cost_level,
        "budget_level": request.budget_level,
        "automation_expectation": request.automation_expectation,
    }

    from backend.services.project_service import get_scenario_comparison
    cmp_result = get_scenario_comparison(profile, request.region, sid_list)
    comparisons = cmp_result.get("comparisons", [])

    # Build a minimal fake "recommendations" list from comparison data
    fake_recommendations = [
        {
            "scenario_id": c["scenario_id"],
            "scenario_name": c["scenario_name"],
            "category": c["category"],
            "score": c["roi_5y"] * 20,  # approximate score from ROI
            "reason": f"5年ROI {c['roi_5y']:.1f}x，回本周期 {c['payback_years']:.1f}年",
            "risk": "中",
            "capex_range": f"¥{c['automation_capex']/10000:.0f}万",
            "labor_saving": c["headcount_saved"] / max(c["headcount_required"], 1),
            "efficiency_gain": 0.4,
        }
        for c in comparisons
    ]

    # Use best scenario for cost_data
    best = next((c for c in comparisons if c.get("is_best")), comparisons[0] if comparisons else {})
    cost_data = {
        "warehouse_cost": 0, "labor_cost_annual": 0,
        "automation_capex": best.get("automation_capex", 0),
        "annual_maintenance": best.get("annual_maintenance", 0),
        "total_annual_cost": best.get("total_annual_cost", 0),
        "automation_savings_annual": best.get("annual_saving", 0),
        "net_annual_benefit": best.get("net_annual_benefit", 0),
        "roi": best.get("roi_5y", 0),
        "payback_years": best.get("payback_years", 99),
        "headcount_required": best.get("headcount_required", 0),
        "headcount_saved": best.get("headcount_saved", 0),
    }

    try:
        pdf_bytes, filename = generate_pdf_bytes(
            project_name=f"{request.project_name}（多方案对比）",
            profile=profile,
            recommendations=fake_recommendations,
            cost_data=cost_data,
            cost_summary=cmp_result.get("analysis_summary", ""),
            cost_recommendations=[f"{c['scenario_name']}: ROI {c.get('roi_5y', 0):.1f}x" for c in comparisons],
            region=request.region,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{quote(filename, safe="")}"'},
    )
