"""
operation_profile_service.py — v0.6.5 Operation Model Derivation
=============================================================

Derive structured operation_profile from structured service_scope matrix.

Single responsibility: service_scope → operation_profile
No cost calculations here — only derivation logic.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.schemas.schemas import OperationProfile, LaborModules
from backend.services.process_templates import build_process_modules


# =============================================================================
# Complexity Scoring Rules
# =============================================================================

COMPLEXITY_SCORING = {
    # Per service item in service_scope matrix
    "base_per_item": 1,
    # Additional weight for value-added complexity
    "value_added_bonus": 2,   # kitting, repack, light_assembly, cycle_count
    "temperature_control_bonus": 2,
    "system_integration_bonus": 1,
    "return_handling_bonus": 1,
}

# Complexity level thresholds
COMPLEXITY_LEVELS = [
    ("low", 0, 5),
    ("medium", 6, 10),
    ("high", 11, 999),
]


def calculate_service_complexity(service_scope: dict) -> tuple[int, str]:
    """
    Calculate service complexity score and level from service_scope matrix.

    Scoring rules:
      - Each selected service: +1
      - value_added category bonus: +1 per item in value_added
      - temperature_control: +2
      - system_integration: +1
      - return_handling: +1

    Returns: (score: int, level: str)
    """
    if not isinstance(service_scope, dict):
        return 0, "low"

    score = 0
    va_bonus_keys = {"kitting", "repack", "light_assembly", "cycle_count"}

    for category, services in service_scope.items():
        if not isinstance(services, dict):
            continue
        for svc_key, selected in services.items():
            if not selected:
                continue
            score += COMPLEXITY_SCORING["base_per_item"]
            if svc_key == "temperature_control":
                score += COMPLEXITY_SCORING["temperature_control_bonus"]
            elif svc_key == "system_integration":
                score += COMPLEXITY_SCORING["system_integration_bonus"]
            elif svc_key == "return_handling":
                score += COMPLEXITY_SCORING["return_handling_bonus"]
            elif svc_key in va_bonus_keys:
                score += COMPLEXITY_SCORING["value_added_bonus"]

    # Determine level
    level = "low"
    for name, lo, hi in COMPLEXITY_LEVELS:
        if lo <= score <= hi:
            level = name
            break

    return score, level


# =============================================================================
# Operation Type Derivation
# =============================================================================

def derive_operation_type(service_scope: dict) -> str:
    """
    Derive operation_type string from service_scope matrix.

    Categories:
      - cold_chain: temperature_control == True
      - bonded_warehouse: bonded_storage == True
      - warehouse_distribution: has both inbound/outbound
      - warehouse_only: inbound/outbound present but no distribution
      - distribution_only: outbound only, no significant storage
      - custom: fallback
    """
    if not isinstance(service_scope, dict):
        return "custom"

    # Collect selected services flat
    selected = []
    for cat, svcs in service_scope.items():
        if isinstance(svcs, dict):
            selected.extend(k for k, v in svcs.items() if v)

    has_inbound = bool(set(selected) & {"receiving", "unloading", "quality_check", "putaway"})
    has_outbound = bool(set(selected) & {"picking", "packing", "shipping", "loading", "labeling"})
    has_storage = bool(set(selected) & {"pallet_storage", "bin_storage"})
    has_tc = "temperature_control" in selected
    has_bonded = "bonded_storage" in selected
    has_va = bool(set(selected) & {"kitting", "repack", "light_assembly", "return_handling", "cycle_count"})

    # Cold chain takes priority
    if has_tc:
        return "cold_chain"

    # Bonded + distribution
    if has_bonded and (has_inbound or has_outbound):
        return "bonded_warehouse_distribution"

    # Both inbound and outbound = full warehouse distribution
    if has_inbound and has_outbound:
        if has_storage:
            return "warehouse_distribution"
        return "distribution_only"

    # Only one side
    if has_inbound:
        return "warehouse_inbound_only"
    if has_outbound:
        return "warehouse_outbound_only"

    # VA services only
    if has_va:
        return "value_added_services"

    return "custom"


# =============================================================================
# Labor Modules Derivation
# =============================================================================

SERVICE_TO_LABOR_MODULE = {
    "receiving": "receiving_team",
    "putaway": "putaway_team",
    "picking": "picking_team",
    "packing": "packing_team",
    "loading": "loading_team",
    "return_handling": "return_processing_team",
    "cycle_count": "inventory_control_team",
    # inventory_reporting maps to inventory_control_team
    "inventory_reporting": "inventory_control_team",
}


def derive_labor_modules(service_scope: dict) -> LaborModules:
    """
    Derive which labor modules are required from service_scope matrix.

    Each labor module = True if any of its constituent services are selected.
    """
    if not isinstance(service_scope, dict):
        return LaborModules()

    selected_services = set()
    for cat, svcs in service_scope.items():
        if isinstance(svcs, dict):
            selected_services.update(k for k, v in svcs.items() if v)

    # Map selected services to labor modules
    active_modules = {
        labor_mod
        for svc, labor_mod in SERVICE_TO_LABOR_MODULE.items()
        if svc in selected_services
    }

    kwargs = {mod: True for mod in active_modules}
    return LaborModules(**kwargs)


# =============================================================================
# Operation Narrative Generation
# =============================================================================

CATEGORY_LABELS = {
    "inbound": "入库作业",
    "storage": "存储管理",
    "outbound": "出库作业",
    "value_added": "增值服务",
    "support": "支持服务",
}

SERVICE_LABELS = {
    "receiving": "收货",
    "unloading": "卸货",
    "quality_check": "质检",
    "putaway": "上架",
    "pallet_storage": "托盘存储",
    "bin_storage": "Bin位存储",
    "temperature_control": "温控管理",
    "bonded_storage": "保税仓储",
    "picking": "拣选",
    "packing": "包装",
    "labeling": "贴标",
    "loading": "装车",
    "shipping": "发运",
    "kitting": "组合装配(Kitting)",
    "repack": "拆箱换装",
    "light_assembly": "轻装配",
    "return_handling": "退货处理",
    "cycle_count": "库存盘点",
    "inventory_reporting": "库存报表",
    "system_integration": "系统对接",
    "data_reporting": "数据报告",
}


def generate_operation_narrative(
    service_scope: dict,
    operation_type: str,
    complexity_level: str,
    complexity_score: int,
) -> str:
    """
    Generate a human-readable operation narrative from service_scope.

    Structure:
      1. Scope summary (which categories are present)
      2. Core services per category
      3. Complexity assessment
    """
    if not isinstance(service_scope, dict):
        return "服务范围未提供，无法生成运营描述。"

    # Build active categories and services
    active_categories = []
    active_services_by_cat = {}

    for cat_key, cat_info in service_scope.items():
        if not isinstance(cat_info, dict):
            continue
        selected = [k for k, v in cat_info.items() if v]
        if selected:
            active_categories.append(cat_key)
            active_services_by_cat[cat_key] = selected

    if not active_categories:
        return "服务范围未提供，无法生成运营描述。"

    # Category summary
    cat_names = [CATEGORY_LABELS.get(c, c) for c in active_categories]
    scope_intro = "、".join(cat_names)

    # Core services per category
    service_parts = []
    for cat_key in active_categories:
        svcs = active_services_by_cat.get(cat_key, [])
        labels = [SERVICE_LABELS.get(s, s) for s in svcs]
        if labels:
            cat_label = CATEGORY_LABELS.get(cat_key, cat_key)
            service_parts.append(f"{cat_label}包括{''.join(labels)}")

    services_text = "，".join(service_parts) + "。"

    # Operation type description
    OP_TYPE_MAP = {
        "cold_chain": "冷链仓储运营",
        "bonded_warehouse_distribution": "保税仓储+配送运营",
        "warehouse_distribution": "仓配一体化运营",
        "distribution_only": "纯配送运营",
        "warehouse_inbound_only": "仓储入库运营",
        "warehouse_outbound_only": "仓储出库运营",
        "value_added_services": "增值服务运营",
        "custom": "综合物流运营",
    }
    op_type_label = OP_TYPE_MAP.get(operation_type, "综合物流运营")

    # Complexity description
    LEVEL_LABEL = {
        "low": "较低复杂度",
        "medium": "中等复杂度",
        "high": "较高复杂度",
    }
    complexity_label = LEVEL_LABEL.get(complexity_level, "中等复杂度")

    # Assemble narrative
    narrative = (
        f"本项目为{op_type_label}场景，服务范围覆盖{scope_intro}。"
        f"{services_text}"
        f"整体属于{complexity_label}（综合评分{complexity_score}/20），"
        f"适合采用标准化运营流程配合适当的自动化设备提升效率。"
    )

    return narrative


# =============================================================================
# Main Derivation Function
# =============================================================================

def derive_operation_profile(service_scope: dict) -> OperationProfile:
    """
    Derive a complete OperationProfile from structured service_scope matrix.

    This is the canonical entry point for operation model derivation.
    All downstream consumers (cost_model, solution_design) read from this.

    Args:
        service_scope: Structured service matrix from Clarification or extraction.
                       Format: {category: {service_key: bool}}

    Returns:
        OperationProfile with all derived fields populated.
    """
    if not isinstance(service_scope, dict):
        # Return a minimal placeholder
        return OperationProfile(
            operation_type="unknown",
            inbound_required=False,
            outbound_required=False,
            value_added_required=False,
            support_required=False,
            temperature_control_required=False,
            return_flow_required=False,
            bonded_warehouse_required=False,
            service_complexity_score=0,
            service_complexity_level="low",
            labor_modules=LaborModules(),
            operation_narrative="服务范围未提供，无法生成运营模型。",
            process_modules={},
            derived_from_fields=["service_scope"],
        )

    # Collect selected services
    selected = {}
    for cat, svcs in service_scope.items():
        if isinstance(svcs, dict):
            selected[cat] = [k for k, v in svcs.items() if v]

    # Required modules
    flat_selected = [s for svcs in selected.values() for s in svcs]
    inbound_required = bool(set(flat_selected) & {"receiving", "unloading", "quality_check", "putaway"})
    outbound_required = bool(set(flat_selected) & {"picking", "packing", "loading", "shipping", "labeling"})
    value_added_required = bool(set(flat_selected) & {"kitting", "repack", "light_assembly", "return_handling", "cycle_count"})
    support_required = bool(set(flat_selected) & {"inventory_reporting", "system_integration", "data_reporting"})
    temperature_control_required = "temperature_control" in flat_selected
    return_flow_required = "return_handling" in flat_selected
    bonded_warehouse_required = "bonded_storage" in flat_selected

    # Derived fields
    complexity_score, complexity_level = calculate_service_complexity(service_scope)
    operation_type = derive_operation_type(service_scope)
    labor_modules = derive_labor_modules(service_scope)
    operation_narrative = generate_operation_narrative(
        service_scope, operation_type, complexity_level, complexity_score
    )

    # v0.6.6: Derive process_modules from active labor modules
    labor_modules_dict = labor_modules.model_dump()
    process_modules = build_process_modules(
        labor_modules=labor_modules_dict,
        value_added_required=value_added_required,
        temperature_control_required=temperature_control_required,
        support_required=support_required,
    )

    return OperationProfile(
        operation_type=operation_type,
        inbound_required=inbound_required,
        outbound_required=outbound_required,
        value_added_required=value_added_required,
        support_required=support_required,
        temperature_control_required=temperature_control_required,
        return_flow_required=return_flow_required,
        bonded_warehouse_required=bonded_warehouse_required,
        service_complexity_score=complexity_score,
        service_complexity_level=complexity_level,
        labor_modules=labor_modules,
        operation_narrative=operation_narrative,
        process_modules=process_modules,
        derived_from_fields=["service_scope"],
    )
