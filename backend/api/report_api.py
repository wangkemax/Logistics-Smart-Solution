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
