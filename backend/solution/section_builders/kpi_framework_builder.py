"""
kpi_framework_builder.py — v0.8
=================================
Builds KPIFramework section for BaseSolution.
Generates a structured KPI framework from service_scope and kpi_targets input.
"""

from __future__ import annotations

from backend.schemas.base_solution_schema import KPIFramework, KPIItem


def build_kpi_framework(
    *,
    service_scope: dict,
    kpi_targets: dict = None,
    industry: str = "电商",
    region: str = "华东",
    labor_cost_level: str = "中",
) -> KPIFramework:
    """
    Build KPIFramework from service_scope and optional kpi_targets input.

    Parameters
    ----------
    service_scope : dict
        service scope dict
    kpi_targets : dict, optional
        Structured KPI targets from project_state (e.g. {"库存准确率": {"target": "≥99.9%", ...}})
    industry : str
        e.g. "电商", "3PL" — used for industry-specific KPI naming
    region : str
        e.g. "华东"
    labor_cost_level : str
        "低" / "中" / "高" — used for labor-related KPI context

    Returns
    -------
    KPIFramework
    """
    kpi_targets = kpi_targets or {}
    kpis: list[KPIItem] = []
    contractual_kpis = _extract_contractual_kpis(kpi_targets)

    inbound = service_scope.get("inbound", {})
    outbound = service_scope.get("outbound", {})
    storage = service_scope.get("storage", {})
    va = service_scope.get("value_added", {})

    # ── INBOUND KPIs ──────────────────────────────────────────────────────
    if any(inbound.values()):
        kpis.extend([
            _make_kpi(
                "inbound_uptime",
                "入库及时率",
                _target(kpi_targets, "入库履约率", "≥99%"),
                "%",
                "WMS 收货时间戳统计",
                "daily",
                is_sla_candidate=True,
                contractual_kpis=contractual_kpis,
            ),
            _make_kpi(
                "inbound_accuracy",
                "入库准确率",
                _target(kpi_targets, "入库准确率", "≥99.5%"),
                "%",
                "WMS 上架确认数 vs 收货数",
                "daily",
                is_sla_candidate=True,
                contractual_kpis=contractual_kpis,
            ),
            _make_kpi(
                "inbound_damage_rate",
                "货损率",
                _target(kpi_targets, "货损率", "≤0.1%"),
                "%",
                "破损件数 / 收货总件数",
                "monthly",
                is_sla_candidate=False,
                contractual_kpis=contractual_kpis,
            ),
        ])

    # ── STORAGE KPIs ─────────────────────────────────────────────────────
    if storage and any(storage.values()):
        kpis.extend([
            _make_kpi(
                "inventory_accuracy",
                "库存准确率",
                _target(kpi_targets, "库存准确率", "≥99.9%"),
                "%",
                "定期盘点差异 / 总库存件数",
                "monthly",
                is_sla_candidate=False,
                contractual_kpis=contractual_kpis,
            ),
            _make_kpi(
                "inventory_turnover_days",
                "库存周转天数",
                _target(kpi_targets, "库存周转天数", "待确认"),
                "天",
                "平均库存量 / 日均出库量",
                "monthly",
                is_sla_candidate=False,
                contractual_kpis=contractual_kpis,
            ),
        ])

    # ── OUTBOUND KPIs ────────────────────────────────────────────────────
    if any(outbound.values()):
        kpis.extend([
            _make_kpi(
                "outbound_fulfillment_rate",
                "订单履约率",
                _target(kpi_targets, "出库履约率", "≥99%"),
                "%",
                "当日实际发货订单数 / 当日应发货总订单数",
                "daily",
                is_sla_candidate=True,
                contractual_kpis=contractual_kpis,
            ),
            _make_kpi(
                "outbound_accuracy",
                "出库准确率",
                _target(kpi_targets, "出库准确率", "≥99.9%"),
                "%",
                "WMS 出库扫描校验",
                "daily",
                is_sla_candidate=True,
                contractual_kpis=contractual_kpis,
            ),
            _make_kpi(
                "outbound_timeliness",
                "出库准时率",
                _target(kpi_targets, "出库准时率", "≥98%"),
                "%",
                "截单时间前完成出库的比例",
                "daily",
                is_sla_candidate=True,
                contractual_kpis=contractual_kpis,
            ),
        ])

    # ── VALUE ADDED KPIs ─────────────────────────────────────────────────
    if va and any(va.values()):
        kpis.extend([
            _make_kpi(
                "va_fulfillment_rate",
                "流通加工履约率",
                _target(kpi_targets, "流通加工履约率", "≥98%"),
                "%",
                "实际完成加工单数 / 计划加工单数",
                "daily",
                is_sla_candidate=False,
                contractual_kpis=contractual_kpis,
            ),
            _make_kpi(
                "va_quality_rate",
                "加工合格率",
                _target(kpi_targets, "加工合格率", "≥99%"),
                "%",
                "加工合格件数 / 加工总件数",
                "monthly",
                is_sla_candidate=False,
                contractual_kpis=contractual_kpis,
            ),
        ])

    # ── GENERAL KPIs (always included) ───────────────────────────────────
    kpis.extend([
        _make_kpi(
            "order_response_time",
            "异常订单响应时间",
            _target(kpi_targets, "异常订单响应", "≤2小时"),
            "小时",
            "异常发生到响应处理完成的平均时间",
            "daily",
            is_sla_candidate=True,
            contractual_kpis=contractual_kpis,
        ),
        _make_kpi(
            "system_uptime",
            "系统可用率",
            _target(kpi_targets, "系统可用率", "≥99.5%"),
            "%",
            "WMS 系统正常可用时间 / 总运营时间",
            "monthly",
            is_sla_candidate=False,
            contractual_kpis=contractual_kpis,
        ),
    ])

    target_values = {kpi.kpi_key: kpi.target for kpi in kpis if kpi.target}

    return KPIFramework(
        operational_kpis=kpis,
        target_values=target_values,
        measurement_frequency="daily",
        narrative="",
    )


def _make_kpi(
    kpi_key: str,
    name: str,
    target: str,
    unit: str,
    measurement_method: str,
    measurement_frequency: str,
    *,
    is_sla_candidate: bool,
    contractual_kpis: set,
) -> KPIItem:
    return KPIItem(
        kpi_key=kpi_key,
        name=name,
        target=target,
        target_numeric=_parse_numeric_target(target),
        unit=unit,
        measurement_method=measurement_method,
        measurement_frequency=measurement_frequency,
        is_sla_candidate=is_sla_candidate,
        is_contractual=name in contractual_kpis,
    )


def _target(
    kpi_targets: dict,
    key: str,
    default: str,
) -> str:
    """Get target value from kpi_targets dict, return default if missing."""
    if not kpi_targets:
        return default
    entry = kpi_targets.get(key, {})
    if isinstance(entry, dict):
        return entry.get("target", default)
    if isinstance(entry, str):
        return entry
    return default


def _parse_numeric_target(target: str) -> float | None:
    """Try to extract numeric value from a target string like '≥99.9%'."""
    import re
    m = re.search(r"([>=<]*)([0-9.]+)", target)
    if m:
        try:
            return float(m.group(2))
        except ValueError:
            return None
    return None


def _extract_contractual_kpis(kpi_targets: dict) -> set:
    """Extract KPI names that are explicitly mentioned in kpi_targets input."""
    if not kpi_targets:
        return set()
    # kpi_targets may have entries like {"入库准确率": {"target": "≥99.9%", "penalty": "..."}}
    return {k for k, v in kpi_targets.items() if isinstance(v, dict)}
