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
# AUTOMOTIVE checked FIRST — most specific automotive supply chain keywords
INDUSTRY_OPERATION_MODES: dict[str, list[OperationModeEnum]] = {
    "AUTOMOTIVE":    [OperationModeEnum.AUTOMOTIVE_LINE_SIDE, OperationModeEnum.AUTOMOTIVE_SEQUENCING, OperationModeEnum.STANDARD_WAREHOUSE],
    "ELECTRONICS":   [OperationModeEnum.ELECTRONICS_VMI_HUB, OperationModeEnum.STANDARD_WAREHOUSE],
    "FMCG":         [OperationModeEnum.FMCG_HIGH_TURNOVER, OperationModeEnum.OMNI_CHANNEL, OperationModeEnum.STANDARD_WAREHOUSE],
    "MANUFACTURING": [OperationModeEnum.MANUFACTURING_WIP, OperationModeEnum.STANDARD_WAREHOUSE],
    "GENERIC_3PL":  [OperationModeEnum.STANDARD_WAREHOUSE],
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
    "AUTOMOTIVE":    1.20,
    "ELECTRONICS":   1.10,
    "FMCG":         1.00,
    "MANUFACTURING": 1.05,
    "GENERIC_3PL":  1.00,
}

_MODE_LABELS: dict[OperationModeEnum, str] = {
    # Generic
    OperationModeEnum.STANDARD_WAREHOUSE:   "标准仓配运营模式",
    OperationModeEnum.COLD_CHAIN:           "冷链仓配运营模式",
    OperationModeEnum.BONDED_WAREHOUSE:      "保税仓配运营模式",
    OperationModeEnum.HIGH_VALUE:             "高价值货仓运营模式",
    # Automotive
    OperationModeEnum.AUTOMOTIVE_LINE_SIDE:   "汽车产线配套运营模式（JIT/JIS）",
    OperationModeEnum.AUTOMOTIVE_SEQUENCING:  "汽车零部件排序运营模式（SKD/CKD）",
    # Electronics
    OperationModeEnum.ELECTRONICS_VMI_HUB:    "电子 VMI Hub 运营模式",
    # FMCG
    OperationModeEnum.FMCG_HIGH_TURNOVER:      "快消高周转运营模式",
    # Manufacturing
    OperationModeEnum.MANUFACTURING_WIP:     "制造在制品仓配运营模式",
    # Omni-channel
    OperationModeEnum.OMNI_CHANNEL:           "全渠道零售运营模式",
}

_MODE_DESCRIPTIONS: dict[OperationModeEnum, str] = {
    # Generic
    OperationModeEnum.STANDARD_WAREHOUSE: (
        "提供标准化的仓储出入库、存储、分拣、配送服务，适用于多行业通用场景。"
    ),
    OperationModeEnum.COLD_CHAIN: (
        "全程温控管理，满足冷藏冷冻商品的质量安全要求。"
    ),
    OperationModeEnum.BONDED_WAREHOUSE: (
        "满足保税监管要求，支持进口商品仓储和海关清关流程。"
    ),
    OperationModeEnum.HIGH_VALUE: (
        "高安全等级的贵重物品仓，配防盗防损和全程追溯。"
    ),
    # Automotive
    OperationModeEnum.AUTOMOTIVE_LINE_SIDE: (
        "面向汽车主机厂/零部件供应商的产线配套仓储运营模式。"
        "核心特征：JIT/JIS 供料、节拍驱动、线边仓、VMI/供应商协同。"
        "重点：器具管理、缺料响应、空器具回收、工位配送准确性。"
    ),
    OperationModeEnum.AUTOMOTIVE_SEQUENCING: (
        "面向汽车零部件 Sorting/SKD/CKD 模式的仓储运营。"
        "核心特征：按工序顺序配料、sequencing 排序、组件配套组装。"
        "重点：零部件层级管理、排序准确率、换线响应、器具循环。"
    ),
    # Electronics
    OperationModeEnum.ELECTRONICS_VMI_HUB: (
        "面向电子信息/ICT/EMS 行业的 VMI（供应商管理库存）Hub 运营模式。"
        "核心特征：多供应商协同、入库即定址、FIFO 精确、VMI 计费对账。"
        "重点：高价值品追溯、批量入库管理、库存水位实时监控。"
    ),
    # FMCG
    OperationModeEnum.FMCG_HIGH_TURNOVER: (
        "面向快消品的高周转仓储运营模式。"
        "核心特征：高频波次、拣选为主、渠道补货快、峰值弹性要求高。"
        "重点：波次优化、拣选效率、高峰人力弹性、履约时效。"
    ),
    # Manufacturing
    OperationModeEnum.MANUFACTURING_WIP: (
        "支持一般制造业（非汽车）的在制品、原材料、成品仓储运营。"
        "核心特征：按工单配料、产线边仓、批量入库、库存批次管理。"
        "重点：配套生产节奏、入出库与产线协同、批次追溯。"
    ),
    # Omni-channel
    OperationModeEnum.OMNI_CHANNEL: (
        "支持线上线下全渠道订单统一管理，共享库存，统一履约。"
        "核心特征：多渠道订单归一、库存共享、差异化包装/配送。"
        "重点：库存分配策略、渠道履约优先级、全渠道 KPI 统一。"
    ),
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
    if automation_expectation == "高":
        conditions.append("客户对自动化程度期望较高")
    elif automation_expectation == "低":
        conditions.append("客户优先考虑运营灵活性，自动化期望较低")
    # Automotive-specific conditions
    if industry == "AUTOMOTIVE":
        conditions.append("汽车供应链场景：JIT/JIS 供料 + 器具管理")
    if industry == "ELECTRONICS":
        conditions.append("电子 VMI Hub 场景：多供应商协同 + 高价值品追溯")
    if industry == "FMCG":
        conditions.append("快消高周转场景：波次优化 + 峰值弹性人力")

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
