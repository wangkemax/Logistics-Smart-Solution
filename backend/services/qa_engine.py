"""
QA Rules Engine
===============
Replaces the naive QA logic in pipeline_tasks.py (Stage 4).
Provides P0/P1/P2 severity classification with suggested fixes and field attribution.
"""

import os
import re
from typing import Optional

# =============================================================================
# QAIssue structure
# =============================================================================

class QAIssue:
    """
    Represents a single QA issue with severity, field, message, fix, and blocking flag.

    Attributes:
        severity:  P0 (blocking), P1 (warning), P2 (info)
        field:     Which profile field is affected (or "general" / "tender_text")
        message:   Human-readable Chinese message
        suggested_fix: What value to fill in, or where to find it
        blocking:  True = FAIL if not resolved, False = CONDITIONAL_PASS
    """

    def __init__(
        self,
        severity: str,
        field: str,
        message: str,
        suggested_fix: str,
        blocking: bool,
    ):
        if severity not in ("P0", "P1", "P2"):
            raise ValueError(f"Invalid severity: {severity}")
        self.severity = severity
        self.field = field
        self.message = message
        self.suggested_fix = suggested_fix
        self.blocking = blocking

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "field": self.field,
            "message": self.message,
            "suggested_fix": self.suggested_fix,
            "blocking": self.blocking,
        }

    def __repr__(self):
        return f"QAIssue({self.severity}, {self.field}, {self.message!r}, blocking={self.blocking})"


# =============================================================================
# Helper: text-based detection patterns
# =============================================================================

def _has_pattern(text: str, keywords: list[str]) -> bool:
    """Return True if any keyword appears in text (case-insensitive)."""
    if not text:
        return False
    t = text.lower()
    return any(kw.lower() in t for kw in keywords)


# =============================================================================
# P0 Rules — Blocking (triggers FAIL)
# =============================================================================

def _rule_warehouse_area_missing(profile: dict) -> Optional[QAIssue]:
    if not profile.get("warehouse_area"):
        return QAIssue(
            severity="P0",
            field="warehouse_area",
            message="仓库面积未填写，无法评估自动化规模",
            suggested_fix="请客户提供仓库面积（平方米）",
            blocking=True,
        )
    return None


def _rule_sku_count_missing(profile: dict) -> Optional[QAIssue]:
    if not profile.get("sku_count"):
        return QAIssue(
            severity="P0",
            field="sku_count",
            message="SKU数量未填写，无法匹配场景",
            suggested_fix="请客户提供SKU总数或主要品类数量",
            blocking=True,
        )
    return None


def _rule_daily_orders_missing(profile: dict) -> Optional[QAIssue]:
    if not profile.get("daily_orders"):
        return QAIssue(
            severity="P0",
            field="daily_orders",
            message="日订单量未填写，无法计算ROI",
            suggested_fix="请客户提供日均订单量或峰值订单量",
            blocking=True,
        )
    return None


def _rule_industry_missing(profile: dict) -> Optional[QAIssue]:
    if not profile.get("industry"):
        return QAIssue(
            severity="P0",
            field="industry",
            message="行业未填写，无法匹配场景库",
            suggested_fix="请客户提供所属行业（如电商、3PL、零售、制造等）",
            blocking=True,
        )
    return None


def _rule_region_missing(profile: dict) -> Optional[QAIssue]:
    if not profile.get("region"):
        return QAIssue(
            severity="P0",
            field="region",
            message="地区未填写，无法匹配成本参数",
            suggested_fix="请客户提供项目所在地区（华东/华南/华北/华中/西部等）",
            blocking=True,
        )
    return None


def _rule_no_recommendations(recommendations: list) -> Optional[QAIssue]:
    if not recommendations:
        return QAIssue(
            severity="P0",
            field="general",
            message="未匹配到任何推荐场景，请检查输入参数",
            suggested_fix="请补充行业、仓库面积、日订单量等关键参数后重新提取",
            blocking=True,
        )
    return None


def _rule_insurance_budget_missing(profile: dict, tender_text: str) -> Optional[QAIssue]:
    """
    Detect insurance_budget from tender_text if not already in profile.
    Triggers when insurance-related keywords appear in the tender text.
    """
    if profile.get("insurance_budget"):
        return None

    INSURANCE_KEYWORDS = ["保险", "保费", "投保", "承保", "理赔", "货运险", "财产险"]
    if not _has_pattern(tender_text, INSURANCE_KEYWORDS):
        return None

    return QAIssue(
        severity="P0",
        field="insurance_budget",
        message="保险预算未明确，请客户提供",
        suggested_fix="请客户提供年度保险预算或是否需要投保说明",
        blocking=True,
    )


def _rule_dg_handling_missing(profile: dict, tender_text: str) -> Optional[QAIssue]:
    """
    Triggers when hazardous materials (DG / dangerous goods) are mentioned
    in tender_text but dg_handling is not specified in profile.
    """
    if profile.get("dg_handling"):
        return None

    DG_KEYWORDS = [
        "危险品", "DG", " hazardous", "易燃", "易爆", "有毒", "腐蚀",
        "放射性", "化工品", "危化品", "CLASS", "UN number",
    ]
    if not _has_pattern(tender_text, DG_KEYWORDS):
        return None

    return QAIssue(
        severity="P0",
        field="dg_handling",
        message="涉及危险品处理，但未提供DG处理方案",
        suggested_fix="请客户提供危险品等级、DG处理资质要求、特殊仓储条件",
        blocking=True,
    )


# =============================================================================
# P1 Rules — Warning (triggers CONDITIONAL_PASS)
# =============================================================================

def _rule_budget_level_unconfirmed(profile: dict) -> Optional[QAIssue]:
    if profile.get("budget_level") in ("待确认", None, ""):
        return QAIssue(
            severity="P1",
            field="budget_level",
            message="预算等级未确认，ROI计算可能有偏差",
            suggested_fix="请客户提供预算区间（如 500-1000万）或预算等级（低/中/高）",
            blocking=False,
        )
    return None


def _rule_labor_cost_level_unconfirmed(profile: dict) -> Optional[QAIssue]:
    if profile.get("labor_cost_level") in ("待确认", None, ""):
        return QAIssue(
            severity="P1",
            field="labor_cost_level",
            message="人工成本等级未确认，ROI计算可能有偏差",
            suggested_fix="请客户提供当地月平均工资或人工成本等级（低/中/高）",
            blocking=False,
        )
    return None


def _rule_contract_years_short(profile: dict) -> Optional[QAIssue]:
    years = profile.get("contract_years")
    try:
        years_val = int(years)
    except (TypeError, ValueError):
        # If it's a string like "待确认" or missing, treat as missing
        return QAIssue(
            severity="P1",
            field="contract_years",
            message="合同期未填写或过短（<3年），可能影响ROI",
            suggested_fix="请客户提供合同期限（年），建议≥3年以保障ROI",
            blocking=False,
        )
    if years_val < 3:
        return QAIssue(
            severity="P1",
            field="contract_years",
            message=f"合同期过短（{years_val}年 < 3年），可能影响ROI",
            suggested_fix="建议合同期≥3年，如确需短合同请注明原因",
            blocking=False,
        )
    return None


def _rule_go_live_date_unconfirmed(profile: dict) -> Optional[QAIssue]:
    if profile.get("go_live_date") in ("待确认", None, ""):
        return QAIssue(
            severity="P1",
            field="go_live_date",
            message="预计上线时间未确认",
            suggested_fix="请客户提供预计上线时间（年月）",
            blocking=False,
        )
    return None


def _rule_extraction_confidence_low(profile: dict) -> Optional[QAIssue]:
    confidence = profile.get("extraction_confidence")
    if confidence is None:
        return None  # Not applicable if not set
    try:
        conf_val = float(confidence)
    except (TypeError, ValueError):
        return None

    # Strictness varies by extraction mode
    threshold = 0.65
    extraction_mode = os.environ.get("EXTRACTION_MODE", "hybrid")
    if extraction_mode == "regex":
        threshold = 0.55  # More lenient since regex is limited

    if conf_val < threshold:
        return QAIssue(
            severity="P1",
            field="extraction_confidence",
            message=f"提取置信度过低（{conf_val:.0%}），数据可能不准确",
            suggested_fix="请客户确认关键参数（仓库面积、日订单量、行业、预算）是否准确",
            blocking=False,
        )
    return None


def _rule_net_height_missing(profile: dict, tender_text: str) -> Optional[QAIssue]:
    """
    Triggers when net height (净高) is mentioned in tender_text
    but not captured in the profile.
    """
    NET_HEIGHT_KEYWORDS = ["净高", "层高", "货架高度", "梁下高度", "clear height"]
    if not _has_pattern(tender_text, NET_HEIGHT_KEYWORDS):
        return None
    if profile.get("net_height") or profile.get("ceiling_height"):
        return None
    return QAIssue(
        severity="P1",
        field="net_height",
        message="净高未填写，立体库方案可能受限",
        suggested_fix="请客户提供仓库净高（米），用于评估立体货架方案适用性",
        blocking=False,
    )


def _rule_security_requirements_unconfirmed(profile: dict, tender_text: str) -> Optional[QAIssue]:
    """
    Triggers when security-related requirements (安保要求) are found in tender text.
    """
    SECURITY_KEYWORDS = ["安保", "保安", "监控系统", "门禁", "周界防范", "Security", "CCTV"]
    if not _has_pattern(tender_text, SECURITY_KEYWORDS):
        return None
    if profile.get("security_requirements") not in ("待确认", None, ""):
        return None
    return QAIssue(
        severity="P1",
        field="security_requirements",
        message="安保要求未确认",
        suggested_fix="请客户提供安保等级要求、是否需要视频监控、门禁系统等",
        blocking=False,
    )


def _rule_cold_chain_no_temp_data(profile: dict, tender_text: str) -> Optional[QAIssue]:
    """
    Triggers when cold chain (冷链) is indicated by industry or tender text
    but no temperature control data is provided.
    """
    industry = profile.get("industry", "")
    COLD_INDUSTRIES = ["医药", "医疗", "食品", "生鲜", "冷链", "乳制品", "冷冻", "冷藏"]
    is_cold_industry = any(cold in industry for cold in COLD_INDUSTRIES)
    is_cold_text = _has_pattern(tender_text, ["冷链", "冷藏", "冷冻", "温控", "冷库", "制冷"])

    if not (is_cold_industry or is_cold_text):
        return None

    # Check for temperature data
    if profile.get("temperature_range") or profile.get("temp_min") or profile.get("temp_max"):
        return None

    return QAIssue(
        severity="P1",
        field="temperature_range",
        message="冷链需求但未提供温控参数",
        suggested_fix="请提供温度范围要求（如 2-8°C 或 -18°C 冷冻），用于选型冷链设备",
        blocking=False,
    )


# =============================================================================
# P2 Rules — Info (no verdict impact)
# =============================================================================

def _rule_automation_expectation_unconfirmed(profile: dict) -> Optional[QAIssue]:
    if profile.get("automation_expectation") in ("待确认", None, ""):
        return QAIssue(
            severity="P2",
            field="automation_expectation",
            message="自动化期望未明确",
            suggested_fix="请客户提供自动化期望（如 减少人工、提升效率、降低成本）",
            blocking=False,
        )
    return None


def _rule_inventory_missing(profile: dict) -> Optional[QAIssue]:
    if not profile.get("inventory"):
        return QAIssue(
            severity="P2",
            field="inventory",
            message="库存量未填写，部分场景匹配可能不准确",
            suggested_fix="请客户提供预计库存量或库存周转天数",
            blocking=False,
        )
    return None


def _rule_client_name_unconfirmed(profile: dict) -> Optional[QAIssue]:
    if profile.get("client_name") in ("待确认", None, ""):
        return QAIssue(
            severity="P2",
            field="client_name",
            message="客户名称待确认",
            suggested_fix="请客户提供客户/项目名称",
            blocking=False,
        )
    return None


# =============================================================================
# Strict mode for regex extraction
# =============================================================================

def _is_regex_mode() -> bool:
    return os.environ.get("EXTRACTION_MODE", "hybrid") == "regex"


# =============================================================================
# Main QA runner
# =============================================================================

def run_qa(
    profile: dict,
    recommendations: list,
    tender_text: str = "",
) -> tuple[str, list[dict]]:
    """
    Run all P0/P1/P2 QA rules against the profile and recommendations.

    Args:
        profile:          Extracted project profile dict
        recommendations:  List of recommended scenario dicts
        tender_text:      Raw tender document text (optional, for text-based detection)

    Returns:
        tuple[verdict, issues]:
            verdict:  "PASS" | "CONDITIONAL_PASS" | "FAIL"
            issues:   List of QAIssue dicts sorted: P0 → P1 → P2
    """
    issues: list[QAIssue] = []

    extraction_mode = os.environ.get("EXTRACTION_MODE", "hybrid")
    is_regex = extraction_mode == "regex"

    # ---- P0 Rules ----
    p0_rules = [
        _rule_warehouse_area_missing,
        _rule_sku_count_missing,
        _rule_daily_orders_missing,
        _rule_industry_missing,
        _rule_region_missing,
        _rule_no_recommendations,
    ]

    for rule in p0_rules:
        if rule == _rule_no_recommendations:
            issue = rule(recommendations)
        else:
            issue = rule(profile)
        if issue:
            issues.append(issue)

    # Text-based P0 rules (insurance + DG)
    for rule in [_rule_insurance_budget_missing, _rule_dg_handling_missing]:
        issue = rule(profile, tender_text)
        if issue:
            issues.append(issue)

    # ---- P1 Rules ----
    p1_rules = [
        _rule_budget_level_unconfirmed,
        _rule_labor_cost_level_unconfirmed,
        _rule_go_live_date_unconfirmed,
        _rule_extraction_confidence_low,
        _rule_net_height_missing,
        _rule_security_requirements_unconfirmed,
        _rule_cold_chain_no_temp_data,
    ]

    for rule in p1_rules:
        if rule == _rule_go_live_date_unconfirmed:
            issue = rule(profile)
        elif rule == _rule_contract_years_short:
            issue = rule(profile)
        elif rule == _rule_extraction_confidence_low:
            issue = rule(profile)
        elif rule == _rule_net_height_missing:
            issue = rule(profile, tender_text)
        elif rule == _rule_security_requirements_unconfirmed:
            issue = rule(profile, tender_text)
        elif rule == _rule_cold_chain_no_temp_data:
            issue = rule(profile, tender_text)
        else:
            issue = rule(profile)
        if issue:
            issues.append(issue)

    # Contract years is a P1 only when present but short
    # Only add if not already added via the generic unconfirmed path
    contract_years = profile.get("contract_years")
    if contract_years is not None:
        try:
            if int(contract_years) < 3:
                # Already handled in _rule_contract_years_short which we call above
                pass
        except (TypeError, ValueError):
            # Non-numeric treated as unconfirmed already
            pass

    # In regex mode, apply stricter thresholds for P1 rules
    if is_regex:
        # Lower confidence threshold override (already handled in rule, but add note)
        # Force unconfirmed fields to P0 in regex mode for budget/labor
        for field, label in [
            ("budget_level", "预算等级"),
            ("labor_cost_level", "人工成本等级"),
        ]:
            val = profile.get(field)
            if val in ("待确认", None, ""):
                issues.append(QAIssue(
                    severity="P0",
                    field=field,
                    message=f"{label}未确认（regex模式），无法计算ROI",
                    suggested_fix=f"请客户提供{label}或切换LLM提取模式",
                    blocking=True,
                ))

    # ---- P2 Rules ----
    p2_rules = [
        _rule_automation_expectation_unconfirmed,
        _rule_inventory_missing,
        _rule_client_name_unconfirmed,
    ]
    for rule in p2_rules:
        issue = rule(profile)
        if issue:
            issues.append(issue)

    # ---- Sort: P0 → P1 → P2, then by field name ----
    severity_order = {"P0": 0, "P1": 1, "P2": 2}
    issues.sort(key=lambda i: (severity_order[i.severity], i.field))

    # ---- Determine verdict ----
    has_p0 = any(i.severity == "P0" for i in issues)
    has_p1 = any(i.severity == "P1" for i in issues)

    if has_p0:
        verdict = "FAIL"
    elif has_p1:
        verdict = "CONDITIONAL_PASS"
    else:
        verdict = "PASS"

    return verdict, [i.to_dict() for i in issues]


# =============================================================================
# UI formatting helper
# =============================================================================

def format_issues_for_ui(issues: list[dict]) -> list[dict]:
    """
    Convert issues list to frontend-expected format with severity icons and labels.

    Frontend format:
    {
        "severity": "P0" | "P1" | "P2",
        "severity_label": "❌ P0" | "⚠️ P1" | "ℹ️ P2",
        "severity_color": "#dc2626" | "#d97706" | "#2563eb",
        "field": "...",
        "message": "...",
        "suggested_fix": "...",
        "blocking": True | False,
    }
    """
    SEVERITY_CONFIG = {
        "P0": {
            "label": "❌ P0",
            "color": "#dc2626",  # red-600
            "bg": "#fef2f2",     # red-50
        },
        "P1": {
            "label": "⚠️ P1",
            "color": "#d97706",  # amber-600
            "bg": "#fffbeb",     # amber-50
        },
        "P2": {
            "label": "ℹ️ P2",
            "color": "#2563eb",  # blue-600
            "bg": "#eff6ff",     # blue-50
        },
    }

    formatted = []
    for issue in issues:
        sev = issue.get("severity", "P2")
        cfg = SEVERITY_CONFIG.get(sev, SEVERITY_CONFIG["P2"])
        formatted.append({
            **issue,
            "severity_label": cfg["label"],
            "severity_color": cfg["color"],
            "severity_bg": cfg["bg"],
        })
    return formatted


# =============================================================================
# Convenience: quick QA check
# =============================================================================

def quick_qa(profile: dict, recommendations: list) -> tuple[str, list[dict]]:
    """
    Shorthand for run_qa without tender_text.
    Useful for testing and simple calls.
    """
    return run_qa(profile, recommendations, tender_text="")
