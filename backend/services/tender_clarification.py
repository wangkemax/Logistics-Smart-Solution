"""
tender_clarification.py — Clarification Question Generation
=====================================================

Exposes:
  - generate_clarification_questions(profile, structured=None, question_id_start=1)
    → list[dict] of rich question objects

Version: v0.2
"""
from backend.services.tender_schema import (
    FIELD_REGISTRY, resolve_missing_label, get_suggested_answer_format,
)


# =============================================================================
# Question templates per field key
# =============================================================================
_QUESTION_TEMPLATES = {
    "dc_count": {
        "question": "请确认本项目实际覆盖的仓库DC数量及各仓库所在城市或地区。",
        "why_it_matters": "下游成本测算和ROI模型需要准确的仓网规模，是所有方案设计的基础。",
        "example": "共5个DC，分别位于上海、广州、武汉、成都、北京，总面积约8万平方米",
    },
    "daily_orders": {
        "question": "请确认日出库量或日均订单量的统计口径：是否按自然日？峰值和均值分别是多少？",
        "why_it_matters": "自动化方案选型和人力测算依赖订单量数据，口径不同导致方案差异巨大。",
        "example": "日均出库约8000件，旺季峰值约20000件，按自然日统计",
    },
    "warehouse_area": {
        "question": "请确认各仓库的具体面积（平方米），如分期入驻请说明各期面积规划。",
        "why_it_matters": "仓库面积是测算仓租、设备投资和布局方案的核心参数。",
        "example": "一期共6万平方米，其中上海仓3万、广州仓2万、武汉仓1万",
    },
    "sku_count": {
        "question": "请确认投标SKU的品类结构，包括ABC分类占比和各自的数量级。",
        "why_it_matters": "SKU结构决定存储方式（阁楼货架vs地堆）、拆零比例和人员配置。",
        "example": "共12000个SKU，其中A类2000个（占60%销量），B类3000个，C类7000个",
    },
    "inventory": {
        "question": "请确认平均库存量和峰值库存量，以及是否涉及VMI模式。",
        "why_it_matters": "库存量影响库位规划和峰值产能设计，VMI比例影响操作复杂度。",
        "example": "平均库存50万板，峰值80万板，含20% VMI",
    },
    "contract_years": {
        "question": "请确认合同期限及是否有分期解锁条款或续约机制。",
        "why_it_matters": "合同期决定分摊年限和ROI测算逻辑。",
        "example": "3+2年，前3年锁定，后2年视KPI达成情况续约",
    },
    "service_scope": {
        "question": "请确认本次投标的服务范围：仓储、末端配送、增值服务（贴标/组包等）各自的报价结构要求。",
        "why_it_matters": "服务范围决定成本结构和报价策略。",
        "example": "含仓储（元/平米/月）、出库配送（元/件）、贴标组包（元/件）三项",
    },
    "kpi_targets": {
        "question": "请提供完整的KPI考核指标列表，包含目标值、考核维度、数据来源和对应的惩罚规则。",
        "why_it_matters": "KPI是方案设计和合同审核的基础，缺失则无法量化服务承诺。",
        "example": "准确率≥99.5%，以客户WMS数据为准，低于99%罚合同额2%/次",
    },
    "penalty_rules": {
        "question": "请提供招标文件中的强制条款和否决项清单，以便评估方案可行性。",
        "why_it_matters": "强制条款直接影响方案可行性和风险测算，必须在设计阶段识别。",
        "example": "必须具备医疗器械仓资质；连续3次KPI不达标可解除合同",
    },
    "peak_factor": {
        "question": "请确认旺季峰值量级及高峰期持续时长，以便测算产能储备。",
        "why_it_matters": "旺季产能设计影响设备选型和人力储备规划。",
        "example": "双11期间峰值约平时3倍，持续约15天",
    },
    "automation_expectation": {
        "question": "请确认客户对自动化程度的期望或要求（货架/AGV/AMR/交叉带分拣机等）。",
        "why_it_matters": "自动化期望直接影响投资规模和ROI。",
        "example": "期望高位货架+AGV，暂不考虑AMR",
    },
}


def generate_clarification_questions(
    profile: dict,
    structured=None,
    question_id_start: int = 1,
) -> list[dict]:
    """
    Generate structured clarification questions from missing / ambiguous / partial fields.

    Each question is a self-contained object:
      - id: sortable question ID (Q-001, Q-002, ...)
      - field_key / display_name
      - severity: P0 | P1
      - question: the question text
      - why_it_matters: why this field matters
      - impact: downstream modules affected
      - suggested_answer_format
      - example_answer
      - rejected_answer_patterns: answers that are not acceptable
      - tracking fields: status, answered_value, answered_at, ...
    """
    qs = []
    q_counter = question_id_start

    def next_id():
        nonlocal q_counter
        cid = f"Q-{q_counter:03d}"
        q_counter += 1
        return cid

    def add_q(
        field_key: str,
        severity: str,
        question: str,
        why_it_matters: str,
        fmt: str,
        example: str,
        field_obj: dict = None,
        source_section: str = "",
        snippet: str = "",
        rejected: list = None,
    ):
        fdef = FIELD_REGISTRY.get(field_key)
        qs.append({
            "id": next_id(),
            "field_key": field_key,
            "display_name": fdef.display_name if fdef else (field_key or "通用"),
            "severity": severity,
            "question": question,
            "why_it_matters": why_it_matters,
            "impact": fdef.impact if fdef else [],
            "suggested_answer_format": fmt,
            "example_answer": example,
            "rejected_answer_patterns": rejected or [
                "暂时无法提供", "待定", "视情况而定", "TBD", "暂无"
            ],
            "source_field_object": field_obj,
            "source_section": source_section,
            "source_text_snippet": snippet[:200] if snippet else "",
            # Tracking (fillable by external system)
            "status": "pending",
            "answered_value": None,
            "answered_at": None,
            "answered_by": None,
            "notes": "",
        })

    m0 = profile.get("missing_p0", [])
    m1 = profile.get("missing_p1", [])
    traces = profile.get("_field_traces", profile)

    # ---- P0: missing fields ----
    for label in m0:
        fkey = resolve_missing_label(label)
        if not fkey:
            fkey = label
        template = _QUESTION_TEMPLATES.get(fkey, {})
        add_q(
            field_key=fkey,
            severity="P0",
            question=template.get("question", f"请提供「{label}」的具体数据。"),
            why_it_matters=template.get("why_it_matters", "该字段影响下游成本测算和方案设计。"),
            fmt=get_suggested_answer_format(fkey),
            example=template.get("example", "请提供具体数值"),
            field_obj=traces.get(fkey),
            source_section="s3_warehouse_dc_list" if fkey in ("dc_count", "warehouse_area") else "s7_kpi_sla",
            snippet=str(traces.get(fkey, {}).get("source_basis", "")),
        )

    # ---- P1: missing fields ----
    for label in m1:
        fkey = resolve_missing_label(label)
        if not fkey:
            fkey = label
        template = _QUESTION_TEMPLATES.get(fkey, {})
        add_q(
            field_key=fkey,
            severity="P1",
            question=template.get("question", f"请提供「{label}」的具体信息。"),
            why_it_matters=template.get("why_it_matters", "该字段影响下游方案设计和合同审核。"),
            fmt=get_suggested_answer_format(fkey),
            example=template.get("example", "请提供具体信息"),
            field_obj=traces.get(fkey),
            source_section="s2_service_scope",
            snippet=str(traces.get(fkey, {}).get("source_basis", "")),
        )

    # ---- Ambiguous fields (status == ambiguous) ----
    for fkey, fobj in traces.items():
        if isinstance(fobj, dict) and fobj.get("status") == "ambiguous":
            add_q(
                field_key=fkey,
                severity="P0",
                question=f"招标文件对「{FIELD_REGISTRY.get(fkey).display_name if FIELD_REGISTRY.get(fkey) else fkey}」存在歧义描述，请确认准确口径。",
                why_it_matters="歧义字段若不澄清会导致方案和报价出现重大偏差。",
                fmt=get_suggested_answer_format(fkey),
                example="以正文第3.2条为准，删去附件第5条中的矛盾描述",
                field_obj=fobj,
                source_section=fobj.get("section", ""),
                snippet=fobj.get("source_basis", ""),
                rejected=["以附件为准", "以正文为准（请注明具体条款）"],
            )

    # Sort: P0 first, then P1, by field_key
    priority_order = {"P0": 0, "P1": 1, "P2": 2}
    qs.sort(key=lambda q: (priority_order.get(q.get("severity", "P1"), 9), q.get("field_key", "")))

    return qs
