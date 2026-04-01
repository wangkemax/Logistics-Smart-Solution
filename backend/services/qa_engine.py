"""
QA Rules Engine v2
===================
Replaces naive QA logic with a declarative rule engine.

Rule categories:
  1. Field Rules    — missing / invalid profile fields
  2. ROI Rules      — financial sanity checks on cost_comparisons
  3. Constraint Rules — conflict detection between requirements and solution

Verdict logic (by priority):
  FAIL               ← any P0 blocking rule fires
  CONDITIONAL_PASS   ← P1 warning rules fire (but no P0)
  PASS               ← only P2 / info rules, or clean
"""

import os
import re
from typing import Optional


# ---- Field value accessor (same as cost_service) ----

def _fv(profile: dict, key: str, default=None):
    """Safely extract field value from profile supporting both raw values and field objects."""
    val = profile.get(key, default)
    if isinstance(val, dict) and "value" in val:
        return val["value"]
    return val if val is not None else default


# =============================================================================
# QAIssue
# =============================================================================

class QAIssue:
    """
    Attributes:
        severity:   P0 (blocking / FAIL) | P1 (warning / CONDITIONAL_PASS) | P2 (info)
        field:      Affected profile/solution field name (or "general")
        rule:       Rule name string (used for deduplication & debugging)
        message:    Human-readable Chinese message
        suggested_fix: What value to fill in, or where to find it
        blocking:   True = FAIL if not resolved, False = CONDITIONAL_PASS
    """
    def __init__(
        self,
        severity: str,
        field: str,
        rule: str,
        message: str,
        suggested_fix: str,
        blocking: bool,
    ):
        if severity not in ("P0", "P1", "P2"):
            raise ValueError(f"Invalid severity: {severity}")
        self.severity = severity
        self.field = field
        self.rule = rule
        self.message = message
        self.suggested_fix = suggested_fix
        self.blocking = blocking

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "field": self.field,
            "rule": self.rule,
            "message": self.message,
            "suggested_fix": self.suggested_fix,
            "blocking": self.blocking,
        }

    def __repr__(self):
        return f"QAIssue({self.severity}, {self.rule}, {self.message!r})"


# =============================================================================
# Helper utilities
# =============================================================================

def _has_pattern(text: str, keywords: list[str]) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(kw.lower() in t for kw in keywords)


def _safe_float(val, default=None):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


# =============================================================================
# 1. FIELD RULES — missing / invalid input fields
# =============================================================================

_FIELD_RULES: list[dict] = [
    {
        "rule": "warehouse_area_missing",
        "field": "warehouse_area",
        "severity": "P0",
        "condition": lambda p: not p.get("warehouse_area"),
        "message": "仓库面积未填写，无法评估自动化规模",
        "suggested_fix": "请客户提供仓库面积（平方米）",
        "blocking": True,
    },
    {
        "rule": "sku_count_missing",
        "field": "sku_count",
        "severity": "P0",
        "condition": lambda p: not p.get("sku_count"),
        "message": "SKU数量未填写，无法匹配场景",
        "suggested_fix": "请客户提供SKU总数或主要品类数量",
        "blocking": True,
    },
    {
        "rule": "daily_orders_missing",
        "field": "daily_orders",
        "severity": "P0",
        "condition": lambda p: not p.get("daily_orders"),
        "message": "日订单量未填写，无法计算ROI",
        "suggested_fix": "请客户提供日均订单量或峰值订单量",
        "blocking": True,
    },
    {
        "rule": "industry_missing",
        "field": "industry",
        "severity": "P0",
        "condition": lambda p: not p.get("industry"),
        "message": "行业未填写，无法匹配场景库",
        "suggested_fix": "请客户提供所属行业（如电商、3PL、零售、制造等）",
        "blocking": True,
    },
    {
        "rule": "region_missing",
        "field": "region",
        "severity": "P0",
        "condition": lambda p: not p.get("region"),
        "message": "地区未填写，无法匹配成本参数",
        "suggested_fix": "请客户提供项目所在地区（华东/华南/华北/华中/西部等）",
        "blocking": True,
    },
    {
        "rule": "no_recommendations",
        "field": "general",
        "severity": "P0",
        "condition": lambda p, recs: not recs,
        "message": "未匹配到任何推荐场景，请检查输入参数",
        "suggested_fix": "请补充行业、仓库面积、日订单量等关键参数后重新提取",
        "blocking": True,
    },
    {
        "rule": "budget_level_missing",
        "field": "budget_level",
        "severity": "P0",
        "condition": lambda p: p.get("budget_level") in ("待确认", None, ""),
        "message": "预算等级未确认，无法计算ROI",
        "suggested_fix": "请客户提供预算区间或等级（低/中/高）",
        "blocking": True,
    },
    {
        "rule": "labor_cost_level_missing",
        "field": "labor_cost_level",
        "severity": "P0",
        "condition": lambda p: p.get("labor_cost_level") in ("待确认", None, ""),
        "message": "人工成本等级未确认，ROI计算可能有偏差",
        "suggested_fix": "请客户提供当地月平均工资或人工成本等级（低/中/高）",
        "blocking": True,
    },
    # P1 — warnings
    {
        "rule": "contract_years_too_short",
        "field": "contract_years",
        "severity": "P1",
        "condition": lambda p: (
            p.get("contract_years") is not None
            and _safe_float(p["contract_years"], 0) < 3
        ),
        "message": "合同期过短（<3年），可能影响ROI",
        "suggested_fix": "建议合同期≥3年以保障自动化投资回报",
        "blocking": False,
    },
    {
        "rule": "extraction_confidence_low",
        "field": "extraction_confidence",
        "severity": "P1",
        "condition": lambda p: (
            p.get("extraction_confidence") is not None
            and _safe_float(p["extraction_confidence"], 1.0) < 0.65
        ),
        "message": "提取置信度过低，数据可能不准确",
        "suggested_fix": "请客户确认关键参数（仓库面积、日订单量、行业）是否准确",
        "blocking": False,
    },
    {
        "rule": "go_live_date_missing",
        "field": "go_live_date",
        "severity": "P1",
        "condition": lambda p: p.get("go_live_date") in ("待确认", None, ""),
        "message": "预计上线时间未确认",
        "suggested_fix": "请客户提供预计上线时间（年月）",
        "blocking": False,
    },
    {
        "rule": "automation_expectation_missing",
        "field": "automation_expectation",
        "severity": "P2",
        "condition": lambda p: p.get("automation_expectation") in ("待确认", None, ""),
        "message": "自动化期望未明确",
        "suggested_fix": "请客户提供自动化期望（减少人工/提升效率/降低成本）",
        "blocking": False,
    },
    {
        "rule": "inventory_missing",
        "field": "inventory",
        "severity": "P2",
        "condition": lambda p: not p.get("inventory"),
        "message": "库存量未填写，部分场景匹配可能不准确",
        "suggested_fix": "请客户提供预计库存量或库存周转天数",
        "blocking": False,
    },
]


# =============================================================================
# 2. ROI RULES — financial sanity checks
# =============================================================================

ROI_RULES: list[dict] = [
    {
        "rule": "roi_too_high",
        "severity": "P1",
        "condition": lambda c: (
            _safe_float(c.get("roi_5y"), 0) > 5.0   # > 500% in 5 years
        ),
        "message": "ROI > 500%，可能存在参数异常（如人工节省估算过高）",
        "suggested_fix": "请确认人工节省/效率提升参数是否合理",
        "blocking": False,
    },
    {
        "rule": "payback_too_fast",
        "severity": "P1",
        "condition": lambda c: (
            0 < _safe_float(c.get("payback_years"), 999) < 0.5
        ),
        "message": "回本周期 < 6个月，可能不合理",
        "suggested_fix": "请确认年节省金额和投资额计算是否正确",
        "blocking": False,
    },
    {
        "rule": "payback_too_long",
        "severity": "P1",
        "condition": lambda c: (
            _safe_float(c.get("payback_years"), 0) > 8.0
        ),
        "message": "回本周期 > 8年，长期投资风险较高",
        "suggested_fix": "请评估是否应提高预算选择更高效的方案，或延长合同期",
        "blocking": False,
    },
    {
        "rule": "negative_annual_saving",
        "severity": "P0",
        "condition": lambda c: (
            _safe_float(c.get("net_annual_benefit"), 0) <= 0
        ),
        "message": "自动化净年度收益为负，方案不经济",
        "suggested_fix": "请降低自动化预算或选择更适配的场景",
        "blocking": True,
    },
    {
        "rule": "roi_negative",
        "severity": "P0",
        "condition": lambda c: (
            _safe_float(c.get("roi_5y"), 0) <= 0
        ),
        "message": "5年ROI为负或零，方案无投资价值",
        "suggested_fix": "请重新选择自动化场景或调整参数",
        "blocking": True,
    },
    {
        "rule": "capex_zero",
        "field": "capex_estimate",
        "severity": "P0",
        "condition": lambda c: (
            _safe_float(c.get("capex_estimate"), -1) <= 0
        ),
        "message": "自动化投资为零，无实际意义",
        "suggested_fix": "请填写自动化投资预算（万元）",
        "blocking": True,
    },
    {
        "rule": "y1_ebita_highly_negative",
        "severity": "P1",
        "condition": lambda c: (
            _safe_float(c.get("y1_ebita"), 0) < -0.5  # < -50% of capex
        ),
        "message": "第一年EBITA严重亏损，需确认初期投入是否合理",
        "suggested_fix": "请确认第一年运维成本和初期建设费用",
        "blocking": False,
    },
]


# =============================================================================
# 3. CONSTRAINT CONFLICT MATRIX
# =============================================================================

CONFLICT_RULES: list[dict] = [
    # (constraint_keyword, solution_type, message)
    {
        "rule": "fifo_drive_in_conflict",
        "constraint_kw": "strict_fifo",
        "solution_type": "drive_in_rack",
        "severity": "P0",
        "message": "严格FIFO要求与Drive-in货架不兼容（后进先出风险）",
        "suggested_fix": "请选择重力货架、输送线或AS/RS等支持FIFO的方案",
        "blocking": True,
    },
    {
        "rule": "low_capex_asrs_conflict",
        "constraint_kw": "low_capex",
        "solution_type": "asrs",
        "severity": "P0",
        "message": "AS/RS属高资本支出方案，与低预算要求冲突",
        "suggested_fix": "请提高预算至500万以上，或选择AMR/输送线等中等投资方案",
        "blocking": True,
    },
    {
        "rule": "low_capex_shuttle_conflict",
        "constraint_kw": "low_capex",
        "solution_type": "shuttle",
        "severity": "P0",
        "message": "Shuttle系统CAPEX较高，与低预算要求冲突",
        "suggested_fix": "请提高预算或选择AMR/输送线等较低投资方案",
        "blocking": True,
    },
    {
        "rule": "high_throughput_manual_conflict",
        "constraint_kw": "high_throughput",
        "solution_type": "manual_picking",
        "severity": "P0",
        "message": "人工拣选无法满足高吞吐量要求",
        "suggested_fix": "请选择输送分拣线、交叉带分拣机或AS/RS等高效方案",
        "blocking": True,
    },
    {
        "rule": "small_warehouse_shuttle_conflict",
        "constraint_kw": "small_warehouse",
        "solution_type": "shuttle",
        "severity": "P1",
        "message": "Shuttle系统对仓库净高和面积有较高要求",
        "suggested_fix": "请确认仓库净高≥9m、面积≥3000㎡，否则建议选择AMR方案",
        "blocking": False,
    },
    {
        "rule": "cold_chain_no_asrs_conflict",
        "constraint_kw": "cold_chain",
        "solution_type": "manual_picking",
        "severity": "P1",
        "message": "冷链场景不应选择人工拣选方案",
        "suggested_fix": "请选择冷链专用AS/RS、穿梭车或自动包装线",
        "blocking": False,
    },
    {
        "rule": "dg_handling_no_capability_conflict",
        "constraint_kw": "dg_handling",
        "solution_type": "standard_storage",
        "severity": "P0",
        "message": "涉及危险品但方案不具备DG处理资质",
        "suggested_fix": "请确认方案包含DG仓储资质和特殊处理措施",
        "blocking": True,
    },
    {
        "rule": "net_height_insufficient_asrs",
        "constraint_kw": "low_net_height",
        "solution_type": "asrs",
        "severity": "P1",
        "message": "净高不足，AS/RS立体仓库对净高要求≥9m",
        "suggested_fix": "请确认仓库净高≥9m，或选择低层立体货架方案",
        "blocking": False,
    },
    {
        "rule": "multi_temperature_cold_chain",
        "constraint_kw": "multi_temp",
        "solution_type": "single_temp_rack",
        "severity": "P1",
        "message": "多温区需求与单温区存储方案冲突",
        "suggested_fix": "请选择支持多温区的冷库方案（常温/冷冻/冷藏分区）",
        "blocking": False,
    },
]


# =============================================================================
# Rule Runners
# =============================================================================

def _run_field_rules(profile: dict, recommendations: list) -> list[QAIssue]:
    issues = []
    for r in _FIELD_RULES:
        try:
            cond = r["condition"]
            fires = cond(profile, recommendations) if cond.__code__.co_argcount >= 2 else cond(profile)
        except Exception:
            fires = False
        if fires:
            issues.append(QAIssue(
                severity=r["severity"],
                field=r["field"],
                rule=r["rule"],
                message=r["message"],
                suggested_fix=r["suggested_fix"],
                blocking=r["blocking"],
            ))
    return issues


def _run_roi_rules(cost_comparisons: list) -> list[QAIssue]:
    """Run ROI financial sanity rules against each cost comparison result."""
    issues = []
    seen_rules = set()
    for comp in cost_comparisons:
        for r in ROI_RULES:
            rule_name = r["rule"]
            if rule_name in seen_rules:
                continue  # deduplicate across comparisons
            try:
                fires = r["condition"](comp)
            except Exception:
                fires = False
            if fires:
                issues.append(QAIssue(
                    severity=r["severity"],
                    field=comp.get("scenario_name", "cost_comparison"),
                    rule=rule_name,
                    message=r["message"],
                    suggested_fix=r["suggested_fix"],
                    blocking=r["blocking"],
                ))
                seen_rules.add(rule_name)
    return issues


def _run_constraint_rules(profile: dict, recommendations: list) -> list[QAIssue]:
    """
    Detect conflicts between requirements profile constraints and recommended solution types.
    """
    issues = []
    # Build constraint keywords from profile
    constraint_keys: set[str] = set()
    # Detect from text fields
    industry = _fv(profile, "industry", "")
    if industry and industry in ("医药", "医疗"):
        constraint_keys.add("pharmaceutical")
    if industry and industry in ("食品", "生鲜", "冷链"):
        constraint_keys.add("cold_chain")
    if _fv(profile, "dg_handling"):
        constraint_keys.add("dg_handling")
    net_height = _fv(profile, "net_height")
    if net_height is not None and _safe_float(net_height, 99) < 9:
        constraint_keys.add("low_net_height")
    warehouse_area = _fv(profile, "warehouse_area")
    if warehouse_area is not None and _safe_float(warehouse_area, 99999) < 3000:
        constraint_keys.add("small_warehouse")
    daily_orders = _fv(profile, "daily_orders")
    if daily_orders is not None and _safe_float(daily_orders, 0) > 5000:
        constraint_keys.add("high_throughput")
    budget = _fv(profile, "budget_level", "")
    if budget == "低":
        constraint_keys.add("low_capex")
    if _fv(profile, "strict_fifo"):
        constraint_keys.add("strict_fifo")
    temp_range = _fv(profile, "temperature_range")
    if temp_range and "," in str(temp_range):
        constraint_keys.add("multi_temp")

    for rec in recommendations:
        solution_type = rec.get("category", "").lower()
        for r in CONFLICT_RULES:
            if r["constraint_kw"] in constraint_keys and r["solution_type"] == solution_type:
                issues.append(QAIssue(
                    severity=r["severity"],
                    field="constraint_conflict",
                    rule=r["rule"],
                    message=r["message"],
                    suggested_fix=r["suggested_fix"],
                    blocking=r["blocking"],
                ))
    return issues


# =============================================================================
# Assumption QA (v0.9)
# =============================================================================

def validate_assumptions(
    assumptions: list,
    industry: str,
    current_date=None,
):
    """
    Validate a list of AssumptionSchema objects against business rules.
    Returns an AssumptionQAResult from backend.schemas.assumption_schemas.
    """
    from backend.schemas.assumption_schemas import QAIssue as AQAIssue, AssumptionQAResult
    import datetime as dt

    if current_date is None:
        current_date = dt.datetime.utcnow()

    issues = []
    p1_count = 0
    auto_fields = set()
    labor_fields = set()

    for a in assumptions:
        fk = a.get("field_key", "")
        conf = float(a.get("confidence", 0.5))
        val = str(a.get("value", ""))
        rule = str(a.get("rule", ""))
        eff_date = a.get("effective_date")

        # Rule 1: Confidence check
        if conf < 0.5:
            issues.append(AQAIssue(
                rule="low_confidence",
                severity="warning",
                message=f"字段 [{fk}] 假设置信度仅 {conf:.0%}，建议优先补录真实数据",
                field_key=fk,
            ))

        # Rule 3: P1 field count
        if fk in ("sku_count", "daily_orders", "inventory", "labor_cost_level", "peak_factor", "budget_level"):
            p1_count += 1

        # Rule 5: Mutual exclusion detection
        if fk == "automation_expectation":
            auto_fields.add(val)
        if fk == "labor_cost_level":
            labor_fields.add(val.lower())

        # Rule 6: Temporal effectiveness
        if eff_date:
            try:
                if isinstance(eff_date, str):
                    eff_date = dt.datetime.fromisoformat(eff_date.replace("Z", "+00:00"))
                age_days = (current_date - eff_date.replace(tzinfo=None)).days
                if age_days > 180:
                    issues.append(AQAIssue(
                        rule="stale_assumption",
                        severity="warning",
                        message=f"字段 [{fk}] 假设来自 {age_days} 天前（>180天），可能已失效",
                        field_key=fk,
                    ))
            except Exception:
                pass

        # Rule 7: Unit/numeric sanity check
        numeric_fields = {"sku_count", "daily_orders", "inventory", "peak_factor"}
        if fk in numeric_fields:
            try:
                num_val = float(val)
                if fk == "peak_factor" and (num_val < 1.0 or num_val > 5.0):
                    issues.append(AQAIssue(
                        rule="unrealistic_value",
                        severity="warning",
                        message=f"字段 [{fk}] 峰值系数 {num_val} 不合理（应在 1.0~5.0 之间）",
                        field_key=fk,
                    ))
                elif fk == "sku_count" and num_val < 10:
                    issues.append(AQAIssue(
                        rule="unrealistic_value",
                        severity="warning",
                        message=f"字段 [{fk}] SKU数量 {num_val} 过小，请核实",
                        field_key=fk,
                    ))
            except (ValueError, TypeError):
                pass

        # Rule 4: Cross-industry check
        if industry not in ("AUTOMOTIVE", "*") and "汽车行业" in rule:
            issues.append(AQAIssue(
                rule="cross_industry_benchmark",
                severity="error",
                message=f"项目行业为 [{industry}]，但使用了汽车行业基准：{rule}",
                field_key=fk,
            ))
        if industry not in ("FMCG", "*") and "快消" in rule:
            issues.append(AQAIssue(
                rule="cross_industry_benchmark",
                severity="error",
                message=f"项目行业为 [{industry}]，但使用了快消行业基准：{rule}",
                field_key=fk,
            ))
        if industry not in ("ELECTRONICS", "*") and "电子行业" in rule:
            issues.append(AQAIssue(
                rule="cross_industry_benchmark",
                severity="error",
                message=f"项目行业为 [{industry}]，但使用了电子行业基准：{rule}",
                field_key=fk,
            ))

    # Rule 3: Multiple P1 fields assumed
    if p1_count >= 3:
        issues.append(AQAIssue(
            rule="too_many_p1_assumptions",
            severity="note",
            message=f"当前有 {p1_count} 个P1字段采用业务假设，建议优先补录以提升方案精度",
            field_key="general",
        ))

    # Rule 5: Mutual exclusion
    if auto_fields and labor_fields:
        has_high_auto = any("自动" in s or "高" in s or "全" in s for s in auto_fields)
        has_low_labor = any("低" in s for s in labor_fields)
        if has_high_auto and has_low_labor:
            issues.append(AQAIssue(
                rule="mutual_exclusion",
                severity="error",
                message="假设全自动化方案的同时又假设低人工成本等级，两者逻辑互斥",
                field_key="general",
            ))

    # Compute overall confidence
    avg_conf = (
        sum(float(a.get("confidence", 0.5)) for a in assumptions) / len(assumptions)
        if assumptions else 1.0
    )
    error_count = sum(1 for i in issues if i.severity == "error")

    return AssumptionQAResult(
        passed=error_count == 0,
        issues=issues,
        overall_confidence=avg_conf,
    )


# =============================================================================
# Main QA Runner
# =============================================================================

def run_qa(
    profile: dict,
    recommendations: list,
    tender_text: str = "",
    cost_comparisons: list = None,
) -> tuple[str, list[dict]]:
    """
    Run all QA rule categories and return verdict + issues.

    Args:
        profile:           Project profile dict
        recommendations:   List of recommended scenarios
        tender_text:       Raw tender text (for text-based detection)
        cost_comparisons:  List of cost comparison dicts (for ROI rules)

    Returns:
        (verdict, issues): verdict ∈ {"PASS", "CONDITIONAL_PASS", "FAIL"}
                           issues sorted: P0 → P1 → P2
    """
    cost_comparisons = cost_comparisons or []
    issues: list[QAIssue] = []

    # 1. Field rules
    issues += _run_field_rules(profile, recommendations)

    # 2. ROI rules
    if cost_comparisons:
        issues += _run_roi_rules(cost_comparisons)

    # 3. Constraint conflict rules
    issues += _run_constraint_rules(profile, recommendations)

    # Text-based P0 rules (insurance + DG from tender text)
    issues += _text_based_p0_rules(profile, tender_text)

    # v0.9: Assumption-level QA
    _assumption_results = validate_assumptions(
        assumptions=profile.get("_assumptions", []),
        industry=profile.get("industry", ""),
    )
    # Convert assumption QA issues to qa_engine QAIssue and merge
    for a_issue in _assumption_results.issues:
        sev = "P0" if a_issue.severity == "error" else "P1" if a_issue.severity == "warning" else "P2"
        blocking = a_issue.severity == "error"
        issues.append(QAIssue(
            severity=sev,
            field=a_issue.field_key or "general",
            rule=a_issue.rule,
            message=a_issue.message,
            suggested_fix="",
            blocking=blocking,
        ))

    # Sort: P0 → P1 → P2
    sev_order = {"P0": 0, "P1": 1, "P2": 2}
    issues.sort(key=lambda i: (sev_order[i.severity], i.field))

    # Verdict
    if any(i.severity == "P0" for i in issues):
        verdict = "FAIL"
    elif any(i.severity == "P1" for i in issues):
        verdict = "CONDITIONAL_PASS"
    else:
        verdict = "PASS"

    return verdict, [i.to_dict() for i in issues]


def _text_based_p0_rules(profile: dict, tender_text: str) -> list[QAIssue]:
    """Rules that detect P0 issues from raw tender text."""
    issues = []

    if not _fv(profile, "insurance_budget"):
        if _has_pattern(tender_text, ["保险", "保费", "投保", "承保", "货运险", "财产险"]):
            issues.append(QAIssue(
                severity="P0", field="insurance_budget", rule="insurance_budget_missing",
                message="保险条款存在但未提供保险预算",
                suggested_fix="请客户提供年度保险预算或说明保险要求",
                blocking=True,
            ))

    if not _fv(profile, "dg_handling"):
        if _has_pattern(tender_text, [
            "危险品", "DG", "hazardous", "易燃", "易爆", "有毒", "腐蚀",
            "放射性", "化工品", "危化品", "CLASS", "UN number",
        ]):
            issues.append(QAIssue(
                severity="P0", field="dg_handling", rule="dg_handling_missing",
                message="涉及危险品处理，但未提供DG处理方案",
                suggested_fix="请客户提供危险品等级、DG处理资质要求、特殊仓储条件",
                blocking=True,
            ))

    return issues


# =============================================================================
# UI Formatting
# =============================================================================

def format_issues_for_ui(issues: list[dict]) -> list[dict]:
    """
    Enrich issues list with severity label/icon/color for frontend display.

    Frontend format:
        {
          "severity": "P0",
          "severity_label": "❌ P0",
          "severity_color": "#dc2626",
          "severity_bg": "#fef2f2",
          "field": "...",
          "rule": "...",
          "message": "...",
          "suggested_fix": "...",
          "blocking": True,
        }
    """
    cfg = {
        "P0": {"label": "❌ P0", "color": "#dc2626", "bg": "#fef2f2"},
        "P1": {"label": "⚠️ P1", "color": "#d97706", "bg": "#fffbeb"},
        "P2": {"label": "ℹ️ P2", "color": "#2563eb", "bg": "#eff6ff"},
    }
    result = []
    for issue in issues:
        c = cfg.get(issue.get("severity", "P2"), cfg["P2"])
        result.append({
            **issue,
            "severity_label": c["label"],
            "severity_color": c["color"],
            "severity_bg": c["bg"],
        })
    return result


def quick_qa(profile: dict, recommendations: list) -> tuple[str, list[dict]]:
    """Shorthand without tender_text or cost_comparisons."""
    return run_qa(profile, recommendations, tender_text="", cost_comparisons=[])
