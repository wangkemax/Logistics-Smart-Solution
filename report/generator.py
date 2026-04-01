"""
Logistics Smart Solution - PDF Report Generator
Uses Jinja2 + WeasyPrint to generate professional PDF proposals.
"""

import os
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False

# Try WeasyPrint, fall back to html2pdf if not available
try:
    from weasyprint import HTML
    WEASYPRINT = True
except ImportError:
    WEASYPRINT = False

# Try chromium or wkhtmltopdf fallback
try:
    import subprocess
    WKHTMLTOPDF_AVAILABLE = subprocess.run(
        ["which", "wkhtmltopdf"], capture_output=True
    ).returncode == 0
except Exception:
    WKHTMLTOPDF_AVAILABLE = False


REPORT_DIR = Path(__file__).parent
TEMPLATE_DIR = REPORT_DIR / "templates"
CSS_PATH = REPORT_DIR / "styles" / "report.css"
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "reports"


def ensure_output_dir() -> Path:
    """Ensure the output directory exists."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR


def get_jinja_env() -> Environment:
    """Get configured Jinja2 environment."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(['html', 'xml']),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    # Expose builtins to template
    env.globals['range'] = range
    env.globals['max'] = max
    env.globals['min'] = min
    return env


def build_report_data(
    project_name: str,
    profile: Dict[str, Any],
    recommendations: list,
    cost_data: Dict[str, Any],
    cost_summary: str,
    cost_recommendations: list,
    region: str = "华东",
    company_name: str = "飞力达物流",
    language: str = "cn",
) -> Dict[str, Any]:
    """
    Build the data dictionary passed to the Jinja2 template.

    Args:
        project_name: Name of the project
        profile: Project profile dict
        recommendations: List of automation recommendations
        cost_data: Cost breakdown from cost engine
        cost_summary: Human-readable cost summary
        cost_recommendations: List of cost recommendation strings
        region: Geographic region for cost parameters
        company_name: Company name to display in report header/footer
        language: 'cn' for Chinese, 'en' for English

    Returns:
        Data dict ready for template rendering
    """
    # Unwrap field-dict values (pipeline uses field-dict format: {value, status, ...})
    _UNWRAP_KEYS = {
        "industry", "region", "warehouse_area", "total_warehouse_area",
        "daily_orders", "sku_count", "inventory", "labor_cost_level",
        "budget_level", "automation_expectation", "contract_years",
        "go_live_date", "project_name", "client_name",
    }
    _profile_flat = {}
    for k, v in profile.items():
        if isinstance(v, dict) and "value" in v:
            _profile_flat[k] = v.get("value")
        else:
            _profile_flat[k] = v
    profile = _profile_flat
    # Attach region to profile for template access
    profile["region"] = region

    report_date = datetime.now().strftime("%Y-%m-%d")

    # Build display recommendations (top 3)
    display_recs = []
    for i, rec in enumerate(recommendations[:3]):
        display_recs.append({
            "rank": i + 1,
            "scenario_id": rec.get("scenario_id"),
            "scenario_name": rec.get("scenario_name", "未知方案"),
            "category": rec.get("category", ""),
            "score": rec.get("score", 0),
            "reason": rec.get("reason", ""),
            "risk": rec.get("risk", ""),
            "capex_range": rec.get("capex_range", "待评估"),
            "labor_saving": rec.get("labor_saving", 0),
            "efficiency_gain": rec.get("efficiency_gain", 0),
        })

    # Language labels
    LANG = {
        "cn": {
            "doc_title": "仓储自动化解决方案建议书",
            "subtitle": "LOGISTICS AUTOMATION PROPOSAL",
            "section_bg": "项目背景",
            "section_analysis": "客户需求分析",
            "section_rec": "自动化场景推荐",
            "section_cost": "投资成本分析",
            "section_roi": "ROI / 投资回报分析",
            "section_plan": "项目实施规划",
            "section_risk": "风险分析与应对",
            "section_appendix": "附录",
            "section_compare": "多方案对比分析",
            "company_label": "编制单位",
            "confidential": "机密文件 · 仅供内部使用",
            "risk_low": "低",
            "risk_mid": "中",
            "risk_high": "高",
            "risk_map": {"低": "低", "中": "中", "高": "高"},
        },
        "en": {
            "doc_title": "Warehouse Automation Solution Proposal",
            "subtitle": "LOGISTICS AUTOMATION PROPOSAL",
            "section_bg": "Project Background",
            "section_analysis": "Client Requirements Analysis",
            "section_rec": "Automation Scenario Recommendations",
            "section_cost": "Investment Cost Analysis",
            "section_roi": "ROI / Investment Return Analysis",
            "section_plan": "Implementation Plan",
            "section_risk": "Risk Analysis & Mitigation",
            "section_appendix": "Appendix",
            "section_compare": "Multi-Scenario Comparison",
            "company_label": "Prepared by",
            "confidential": "Confidential · Internal Use Only",
            "risk_low": "Low",
            "risk_mid": "Medium",
            "risk_high": "High",
            "risk_map": {"低": "Low", "中": "Medium", "高": "High", "Low": "Low", "Medium": "Medium", "High": "High"},
        },
    }
    labels = LANG.get(language, LANG["cn"])

    return {
        "project_name": project_name,
        "report_date": report_date,
        "profile": profile,
        "recommendations": display_recs,
        "cost": cost_data,
        "cost_summary": cost_summary,
        "cost_recommendations": cost_recommendations,
        "company_name": company_name,
        "language": language,
        "labels": labels,
    }


def render_html(data: Dict[str, Any]) -> str:
    """
    Render the HTML content from template + data.

    Args:
        data: Report data dict

    Returns:
        Rendered HTML string
    """
    env = get_jinja_env()
    template = env.get_template("report_template.html")

    # Pass CSS path as absolute path for WeasyPrint
    css_abs = str(CSS_PATH.absolute())

    html = template.render(data=data, css_path=css_abs)
    return html


def html_to_pdf_weasyprint(html_content: str, output_path: Path) -> Path:
    """Convert HTML to PDF using WeasyPrint."""
    HTML(string=html_content).write_pdf(output_path)
    return output_path


def html_to_pdf_wkhtmltopdf(html_content: str, output_path: Path) -> Path:
    """Convert HTML to PDF using wkhtmltopdf (fallback)."""
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as f:
        f.write(html_content)
        html_file = f.name

    try:
        subprocess.run(
            [
                "wkhtmltopdf",
                "--enable-local-file-access",
                "--print-media-type",
                "--no-stop-slow-scripts",
                "--javascript-delay", "1000",
                html_file,
                str(output_path),
            ],
            check=True,
            capture_output=True,
        )
    finally:
        os.unlink(html_file)

    return output_path


def html_to_pdf_chromium(html_content: str, output_path: Path) -> Path:
    """Convert HTML to PDF using Chromium (headless, via browser tool or subprocess)."""
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as f:
        f.write(html_content)
        html_file = f.name

    try:
        # Try using chromium's headless print-to-pdf
        subprocess.run(
            [
                "chromium",
                "--headless",
                "--disable-gpu",
                "--no-sandbox",
                "--print-to-pdf=" + str(output_path),
                "--print-to-pdf-no-header",
                html_file,
            ],
            check=True,
            capture_output=True,
        )
    except FileNotFoundError:
        # Fallback: try google-chrome
        try:
            subprocess.run(
                [
                    "google-chrome",
                    "--headless",
                    "--disable-gpu",
                    "--no-sandbox",
                    "--print-to-pdf=" + str(output_path),
                    "--print-to-pdf-no-header",
                    html_file,
                ],
                check=True,
                capture_output=True,
            )
        except FileNotFoundError:
            raise RuntimeError(
                "No PDF generation tool available. "
                "Install weasyprint: pip install weasyprint"
            )
    finally:
        os.unlink(html_file)

    return output_path


def generate_pdf_filename(project_name: str) -> str:
    """Generate a unique output filename based on project name and timestamp."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c for c in project_name if c.isalnum() or c in (" ", "-", "_")).strip()
    safe_name = safe_name.replace(" ", "_")[:30]
    return f"solution_report_{safe_name}_{timestamp}.pdf"


def generate_pdf(
    project_name: str,
    profile: Dict[str, Any],
    recommendations: list,
    cost_data: Dict[str, Any],
    cost_summary: str,
    cost_recommendations: list,
    region: str = "华东",
    output_filename: Optional[str] = None,
    company_name: str = "飞力达物流",
    language: str = "cn",
) -> str:
    """
    Generate a PDF report and save it to disk.

    Args:
        project_name: Name of the project
        profile: Project profile dict
        recommendations: List of automation recommendations
        cost_data: Cost breakdown from cost engine
        cost_summary: Human-readable cost summary
        cost_recommendations: List of cost recommendation strings
        region: Geographic region
        output_filename: Custom output filename (auto-generated if None)

    Returns:
        Absolute path to the generated PDF file
    """
    if not WEASYPRINT_AVAILABLE:
        raise ImportError(
            "Jinja2 is required. Install: pip install jinja2"
        )

    # Build data and render HTML
    data = build_report_data(
        project_name, profile, recommendations,
        cost_data, cost_summary, cost_recommendations, region,
        company_name, language,
    )
    html_content = render_html(data)

    # Determine output path
    ensure_output_dir()
    if output_filename is None:
        output_filename = generate_pdf_filename(project_name)
    output_path = OUTPUT_DIR / output_filename

    # Try PDF generation methods in order of preference
    if WEASYPRINT:
        html_to_pdf_weasyprint(html_content, output_path)
    elif WKHTMLTOPDF_AVAILABLE:
        html_to_pdf_wkhtmltopdf(html_content, output_path)
    else:
        # Last resort: raise a helpful error
        raise RuntimeError(
            "No PDF generation backend available. Please install:\n"
            "  pip install weasyprint\n"
            "  # or\n"
            "  brew install wkhtmltopdf"
        )

    return str(output_path.absolute())


def generate_pdf_bytes(
    project_name: str,
    profile: Dict[str, Any],
    recommendations: list,
    cost_data: Dict[str, Any],
    cost_summary: str,
    cost_recommendations: list,
    region: str = "华东",
    company_name: str = "飞力达物流",
    language: str = "cn",
) -> tuple[bytes, str]:
    """
    Generate a PDF report and return as bytes (for API responses).

    Returns:
        Tuple of (PDF bytes, filename)
    """
    filename = generate_pdf_filename(project_name)
    output_path = ensure_output_dir() / filename

    # Build data and render HTML
    data = build_report_data(
        project_name, profile, recommendations,
        cost_data, cost_summary, cost_recommendations, region,
        company_name, language,
    )
    html_content = render_html(data)

    if WEASYPRINT:
        html_to_pdf_weasyprint(html_content, output_path)
    elif WKHTMLTOPDF_AVAILABLE:
        html_to_pdf_wkhtmltopdf(html_content, output_path)
    else:
        raise RuntimeError(
            "No PDF generation backend available. Please install weasyprint."
        )

    return output_path.read_bytes(), filename


# === CLI for testing ===
if __name__ == "__main__":
    import json
    from pathlib import Path

    # Load sample data for testing
    data_dir = Path(__file__).parent.parent / "data"
    sample_output = data_dir / "logistics_presale.db"

    # Build sample data matching the engine output format
    sample_profile = {
        "industry": "电商",
        "warehouse_area": 20000,
        "sku_count": 30000,
        "daily_orders": 5000,
        "inventory": 500000,
        "labor_cost_level": "中",
        "budget_level": "中",
        "automation_expectation": "中",
    }

    sample_recs = [
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

    sample_cost = {
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

    sample_summary = "项目预计总投资125万元，5年ROI达到1.55x，预计回本周期3.2年。"
    sample_recs_cost = [
        "ROI表现良好，建议推进",
        "回本周期适中，可优先考虑",
    ]

    print("Generating sample PDF report...")
    output_path = generate_pdf(
        project_name="测试项目-电商自动化方案",
        profile=sample_profile,
        recommendations=sample_recs,
        cost_data=sample_cost,
        cost_summary=sample_summary,
        cost_recommendations=sample_recs_cost,
        region="华东",
    )
    print(f"PDF generated: {output_path}")
