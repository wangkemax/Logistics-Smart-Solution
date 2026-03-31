"""
operation_mode_builder.py — v0.8
===============================
Builds OperationMode section for BaseSolution.
"""

from __future__ import annotations

from backend.schemas.base_solution_schema import (
    OperationMode,
    OperationModeEnum,
    ScaleTier,
)


# Maps industry → top operation mode candidates (ordered by priority)
INDUSTRY_OPERATION_MODES: dict[str, list[OperationModeEnum]] = {
    "电商":    [OperationModeEnum.ECOMMERCE_FULFILLMENT, OperationModeEnum.STANDARD_WAREHOUSE],
    "3PL":    [OperationModeEnum.THIRD_PARTY_LOGISTICS, OperationModeEnum.STANDARD_WAREHOUSE],
    "零售":    [OperationModeEnum.OMNI_CHANNEL, OperationModeEnum.STANDARD_WAREHOUSE],
    "制造":    [OperationModeEnum.MANUFACTURING_WIP, OperationModeEnum.STANDARD_WAREHOUSE],
    "快递":    [OperationModeEnum.EXPRESS_SORTING, OperationModeEnum.STANDARD_WAREHOUSE],
    "医药":    [OperationModeEnum.PHARMA, OperationModeEnum.COLD_CHAIN],
    "食品":    [OperationModeEnum.FOOD, OperationModeEnum.COLD_CHAIN],
    "生鲜":    [OperationModeEnum.FRESH, OperationModeEnum.COLD_CHAIN],
}

# Region → cost index (华东 = 1.0 baseline)
REGION_COST_INDEX: dict[str, float] = {
    "华东": 1.00,
    "华南": 0.95,
    "华北": 1.05,
    "华中": 0.98,
    "西部": 0.92,
    "东北": 1.00,
}

# Industry → overhead factor (电商 = 1.0 baseline)
INDUSTRY_OVERHEAD_FACTOR: dict[str, float] = {
    "电商": 1.00,
    "3PL":  1.05,
    "零售":  1.05,
    "制造":  1.15,
    "快递":  1.10,
    "医药":  1.25,
    "食品":  1.20,
    "生鲜":  1.30,
}

_MODE_LABELS: dict[OperationModeEnum, str] = {
    OperationModeEnum.STANDARD_WAREHOUSE:   "标准仓配运营模式",
    OperationModeEnum.COLD_CHAIN:           "冷链仓配运营模式",
    OperationModeEnum.BONDED_WAREHOUSE:      "保税仓配运营模式",
    OperationModeEnum.HIGH_VALUE:             "高价值货仓运营模式",
    OperationModeEnum.ECOMMERCE_FULFILLMENT:"电商履约运营模式",
    OperationModeEnum.THIRD_PARTY_LOGISTICS: "第三方物流运营模式",
    OperationModeEnum.MANUFACTURING_WIP:     "制造在制品仓配运营模式",
    OperationModeEnum.EXPRESS_SORTING:        "快递分拣运营模式",
    OperationModeEnum.OMNI_CHANNEL:           "全渠道零售运营模式",
    OperationModeEnum.PHARMA:                 "医药仓配运营模式",
    OperationModeEnum.FOOD:                  "食品仓配运营模式",
    OperationModeEnum.FRESH:                 "生鲜仓配运营模式",
}

_MODE_DESCRIPTIONS: dict[OperationModeEnum, str] = {
    OperationModeEnum.STANDARD_WAREHOUSE:   "提供标准化的仓储出入库、存储、分拣、配送服务，适用于多行业通用场景。",
    OperationModeEnum.ECOMMERCE_FULFILLMENT:"针对电商 B2C 业务设计，专注订单波次处理、高峰扩容能力和快速履约。",
    OperationModeEnum.THIRD_PARTY_LOGISTICS: "面向 3PL 客户，支持多货主管理、灵活计费和 KPI 报表。",
    OperationModeEnum.COLD_CHAIN:           "全程温控管理，满足冷藏冷冻商品的质量安全要求。",
    OperationModeEnum.EXPRESS_SORTING:       "面向快递快运行业，高通量分拣、路由优化、快速周转。",
    OperationModeEnum.OMNI_CHANNEL:          "支持线上线下全渠道订单统一管理，共享库存，统一履约。",
    OperationModeEnum.MANUFACTURING_WIP:     "支持制造业在制品的线边仓、周转仓管理，与产线紧密协同。",
    OperationModeEnum.HIGH_VALUE:             "高安全等级的贵重物品仓，配防盗防损和全程追溯。",
    OperationModeEnum.BONDED_WAREHOUSE:       "满足保税监管要求，支持进口商品仓储和海关清关流程。",
    OperationModeEnum.PHARMA:                "符合 GSP 规范，支持药品仓储的温湿度监控和追溯管理。",
    OperationModeEnum.FOOD:                  "满足食品仓储的卫生标准和温控要求。",
    OperationModeEnum.FRESH:                 "全程冷链，支持生鲜农产品的高效保鲜存储和快速周转。",
}


def build_operation_mode(
    *,
    industry: str,
    service_scope: dict,
    warehouse_area: float,
    region: str,
    dc_count: int,
    scale_tier: ScaleTier,
    automation_expectation: str = "中",
) -> OperationMode:
    """
    Build OperationMode section from resolved project fields.

    Parameters
    ----------
    industry : str
        e.g. "电商", "3PL", "制造"
    service_scope : dict
        service_scope dict from project_state
    warehouse_area : float
        in sqm
    region : str
        e.g. "华东"
    dc_count : int
        number of distribution centers
    scale_tier : ScaleTier
        derived from warehouse_area
    automation_expectation : str
        "低" / "中" / "高"

    Returns
    -------
    OperationMode
    """
    candidates = INDUSTRY_OPERATION_MODES.get(industry, [OperationModeEnum.STANDARD_WAREHOUSE])
    primary_mode = candidates[0]

    # Build applicable conditions
    conditions = [
        f"行业属性：{industry}",
        f"仓储规模：{scale_tier.value.upper()}（{warehouse_area:,.0f} 平方米）",
    ]
    if dc_count > 1:
        conditions.append(f"多仓联动架构（{dc_count} 个 DC）")
    if service_scope.get("inbound", {}).get("cold_chain") or industry in ("医药", "食品", "生鲜"):
        conditions.append("含冷链或温控作业需求")
    if automation_expectation == "高":
        conditions.append("客户对自动化程度期望较高")
    elif automation_expectation == "低":
        conditions.append("客户优先考虑运营灵活性，自动化期望较低")

    # Core activities by mode
    core_activities = _get_core_activities(primary_mode, service_scope)

    return OperationMode(
        mode_name=primary_mode,
        label=_MODE_LABELS.get(primary_mode, str(primary_mode.value)),
        description=_MODE_DESCRIPTIONS.get(primary_mode, ""),
        applicable_conditions=conditions,
        core_activities=core_activities,
        scale_tier=scale_tier.value if hasattr(scale_tier, 'value') else str(scale_tier),
        region_cost_index=REGION_COST_INDEX.get(region, 1.0),
        industry_overhead_factor=INDUSTRY_OVERHEAD_FACTOR.get(industry, 1.0),
    )


def _get_core_activities(mode: OperationModeEnum, service_scope: dict) -> list[str]:
    """Return core activity list based on operation mode and service scope."""
    activities: list[str] = []

    inbound = service_scope.get("inbound", {})
    outbound = service_scope.get("outbound", {})
    storage = service_scope.get("storage", {})
    va = service_scope.get("value_added", {})
    support = service_scope.get("support", {})

    if inbound.get("receiving"):
        activities.append("收货交接与数量清点")
    if inbound.get("quality_check"):
        activities.append("质量检验与合规检查")
    if inbound.get("putaway"):
        activities.append("上架存储与库位管理")
    if storage.get("pallet_storage"):
        activities.append("托盘区存储管理")
    if storage.get("bin_storage"):
        activities.append("料箱区存储管理")
    if outbound.get("picking"):
        activities.append("订单拣选与复核")
    if outbound.get("packing"):
        activities.append("包装贴标与出库准备")
    if outbound.get("loading") or outbound.get("shipping"):
        activities.append("装车出库与承运交接")
    if va.get("kitting"):
        activities.append("组合包装（Kitting）")
    if va.get("repack"):
        activities.append("换包加工（Repack）")
    if va.get("return_handling"):
        activities.append("退货处理与逆向物流")
    if support.get("inventory_reporting"):
        activities.append("库存报表与客户对账")
    if support.get("system_integration"):
        activities.append("系统对接与数据同步")

    # Deduplicate
    seen = set()
    unique = []
    for a in activities:
        if a not in seen:
            seen.add(a)
            unique.append(a)

    return unique if unique else ["标准仓储作业"]
