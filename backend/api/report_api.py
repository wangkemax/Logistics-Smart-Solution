"""
FastAPI Report Generation Endpoint
POST /api/report — Generate PDF proposal report
"""

import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.services.project_service import get_recommendations, get_cost_analysis
from report.generator import generate_pdf, generate_pdf_bytes, WEASYPRINT_AVAILABLE


router = APIRouter(prefix="/api", tags=["report"])

# Absolute path to report generator
REPORT_MODULE = Path(__file__).parent.parent.parent / "report"
sys.path.insert(0, str(REPORT_MODULE.parent))


@router.post("/report")
def generate_proposal_report(
    project_name: str,
    industry: str,
    warehouse_area: float,
    sku_count: int,
    daily_orders: int,
    inventory: int,
    labor_cost_level: str = "中",
    budget_level: str = "中",
    automation_expectation: str = "中",
    region: str = "华东",
    selected_scenario_id: Optional[int] = None,
):
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
        "industry": industry,
        "warehouse_area": warehouse_area,
        "sku_count": sku_count,
        "daily_orders": daily_orders,
        "inventory": inventory,
        "labor_cost_level": labor_cost_level,
        "budget_level": budget_level,
        "automation_expectation": automation_expectation,
    }

    # Get recommendations and cost analysis
    rec_result = get_recommendations(profile)
    recommendations = rec_result.get("recommendations", [])

    cost_result = get_cost_analysis(profile, region, selected_scenario_id)
    cost_data = cost_result.get("cost_breakdown", {})
    cost_summary = cost_result.get("summary", "")
    cost_recommendations = cost_result.get("recommendations", [])

    # Generate PDF
    try:
        pdf_bytes, filename = generate_pdf_bytes(
            project_name=project_name,
            profile=profile,
            recommendations=recommendations,
            cost_data=cost_data,
            cost_summary=cost_summary,
            cost_recommendations=cost_recommendations,
            region=region,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
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
def generate_compare_report(
    project_name: str,
    industry: str,
    warehouse_area: float,
    sku_count: int,
    daily_orders: int,
    inventory: int,
    labor_cost_level: str = "中",
    budget_level: str = "中",
    automation_expectation: str = "中",
    region: str = "华东",
    scenario_ids: str = "",
):
    """
    Generate a PDF comparison report for multiple automation scenarios.

    scenario_ids: comma-separated list of scenario IDs, e.g. "1,2,3"
    """
    if not WEASYPRINT_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Install jinja2 and weasyprint to enable PDF generation",
        )

    try:
        sid_list = [int(s.strip()) for s in scenario_ids.split(",") if s.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid scenario_ids format")

    if len(sid_list) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 scenario IDs")

    profile = {
        "industry": industry,
        "warehouse_area": warehouse_area,
        "sku_count": sku_count,
        "daily_orders": daily_orders,
        "inventory": inventory,
        "labor_cost_level": labor_cost_level,
        "budget_level": budget_level,
        "automation_expectation": automation_expectation,
    }

    from backend.services.project_service import get_scenario_comparison
    cmp_result = get_scenario_comparison(profile, region, sid_list)
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
            project_name=f"{project_name}（多方案对比）",
            profile=profile,
            recommendations=fake_recommendations,
            cost_data=cost_data,
            cost_summary=cmp_result.get("analysis_summary", ""),
            cost_recommendations=[f"{c['scenario_name']}: 5年ROI {c['roi_5y']:.1f}x" for c in comparisons],
            region=region,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
