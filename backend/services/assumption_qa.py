"""
backend/services/assumption_qa.py
v0.9 — Dedicated assumption QA rules (delegated from qa_engine)
"""
from datetime import datetime
from backend.schemas.assumption_schemas import QAIssue, AssumptionQAResult

MUTUAL_EXCLUSION_PAIRS = [
    ("automation_expectation", "labor_cost_level"),
]

CROSS_INDUSTRY_KEYWORDS = {
    "AUTOMOTIVE": ["汽车行业", "JIT", "JIS", "SKD", "CKD"],
    "FMCG": ["快消", "高周转", "补货"],
    "ELECTRONICS": ["电子行业", "VMI", "EMS"],
}


def validate_assumption_list(
    assumptions: list,
    industry: str,
    current_date: datetime = None,
) -> AssumptionQAResult:
    """
    Standalone assumption QA function.
    Called from qa_engine or pipeline_tasks.
    """
    if current_date is None:
        current_date = datetime.utcnow()

    issues = []
    p1_count = 0

    for a in assumptions:
        field_key = a.get("field_key", "")
        confidence = float(a.get("confidence", 0.5))
        value = str(a.get("value", ""))
        rule = str(a.get("rule", ""))
        effective_date = a.get("effective_date")

        # Rule 1: Low confidence
        if confidence < 0.5:
            issues.append(QAIssue(
                rule="low_confidence",
                severity="warning",
                message=f"[{field_key}] 置信度 {confidence:.0%} < 50%，建议补录",
                field_key=field_key,
            ))

        # Rule 3: P1 field count tracking
        if field_key in ("sku_count", "daily_orders", "inventory", "labor_cost_level", "peak_factor", "budget_level"):
            p1_count += 1

        # Rule 6: Stale assumption (> 180 days)
        if effective_date:
            try:
                if isinstance(effective_date, str):
                    effective_date = datetime.fromisoformat(effective_date.replace("Z", "+00:00"))
                age_days = (current_date - effective_date.replace(tzinfo=None)).days
                if age_days > 180:
                    issues.append(QAIssue(
                        rule="stale_assumption",
                        severity="warning",
                        message=f"[{field_key}] 假设来自 {age_days} 天前，已超过6个月有效期",
                        field_key=field_key,
                    ))
            except Exception:
                pass

    # Rule 3: Multiple P1 fields assumed
    if p1_count >= 3:
        issues.append(QAIssue(
            rule="too_many_p1_assumptions",
            severity="note",
            message=f"当前有 {p1_count} 个P1字段采用业务假设，建议优先补录以提升方案精度",
            field_key="general",
        ))

    # Rule 5: Mutual exclusion
    auto_vals = [a.get("value", "") for a in assumptions if a.get("field_key") == "automation_expectation"]
    labor_vals = [a.get("value", "") for a in assumptions if a.get("field_key") == "labor_cost_level"]
    if any("自动" in v or "高" in v for v in auto_vals):
        if any("低" in v for v in labor_vals):
            issues.append(QAIssue(
                rule="mutual_exclusion",
                severity="error",
                message="全自动化方案与低人工成本等级互斥，请核实",
                field_key="general",
            ))

    # Rule 4: Cross-industry benchmark
    bad_keywords = []
    for ind, keywords in CROSS_INDUSTRY_KEYWORDS.items():
        if industry and ind not in (industry, "*"):
            bad_keywords.extend([(kw, ind) for kw in keywords])

    for a in assumptions:
        rule = str(a.get("rule", ""))
        for kw, ind in bad_keywords:
            if kw in rule:
                issues.append(QAIssue(
                    rule="cross_industry_benchmark",
                    severity="error",
                    message=f"项目行业=[{industry}]，但规则引用了 [{ind}] 的 [{kw}]，请确认",
                    field_key=a.get("field_key", ""),
                ))

    error_count = sum(1 for i in issues if i.severity == "error")
    avg_conf = sum(float(a.get("confidence", 0.5)) for a in assumptions) / max(len(assumptions), 1)

    return AssumptionQAResult(
        passed=error_count == 0,
        issues=issues,
        overall_confidence=avg_conf,
    )
