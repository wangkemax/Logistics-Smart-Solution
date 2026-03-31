"""
Shared pytest fixtures for Base Solution regression tests.
=========================================================

Provides project_state fixtures for each of the 5 industry verticals.
Each fixture is a P0-complete input to adapt_project_state().

P0 fields required by adapt_project_state gate:
  warehouse_area, total_warehouse_area, dc_count, daily_orders,
  sku_count, contract_years, service_scope
"""

import pytest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ─── P0-complete Industry Fixtures ─────────────────────────────────────────

@pytest.fixture
def F_AUTOMOTIVE():
    """AUTOMOTIVE — 汽车产线配套，JIT/JIS，35,000 sqm，2 DC，华东。"""
    return {
        "project_name": "华道汽车零部件 JIT 供料项目",
        "client_name": "华道汽车零部件（上海）有限公司",
        "industry": "AUTOMOTIVE",
        "region": "华东",
        "warehouse_area": 35_000.0,
        "total_warehouse_area": 35_000.0,
        "dc_count": 2,
        "daily_orders": 5_000.0,
        "sku_count": 8_000,
        "contract_years": 3,
        "service_scope": {
            "inbound":  {"receiving": True, "quality_check": True, "putaway": True},
            "outbound": {"picking": True, "packing": True, "loading": True, "shipping": True},
            "storage":  {"pallet_storage": True, "bin_storage": True},
            "value_added": {"kitting": False, "repack": False, "return_handling": False},
            "support":  {"system_integration": True},
        },
    }


@pytest.fixture
def F_ELECTRONICS():
    """ELECTRONICS — 电子 VMI Hub，12,000 sqm，1 DC，华南。"""
    return {
        "project_name": "鹏辉电子 VMI Hub 运营项目",
        "client_name": "鹏辉电子科技（深圳）有限公司",
        "industry": "ELECTRONICS",
        "region": "华南",
        "warehouse_area": 12_000.0,
        "total_warehouse_area": 12_000.0,
        "dc_count": 1,
        "daily_orders": 3_000.0,
        "sku_count": 5_000,
        "contract_years": 3,
        "service_scope": {
            "inbound":  {"receiving": True, "quality_check": True, "putaway": True},
            "outbound": {"picking": True, "packing": True, "loading": True, "shipping": True},
            "storage":  {"pallet_storage": True, "bin_storage": True},
            "value_added": {"kitting": False, "repack": False, "return_handling": False},
            "support":  {"system_integration": True},
        },
    }


@pytest.fixture
def F_FMCG():
    """FMCG — 快消高周转，28,000 sqm，1 DC，华东。"""
    return {
        "project_name": "明光零售配送中心运营项目",
        "client_name": "明光供应链管理有限公司",
        "industry": "FMCG",
        "region": "华东",
        "warehouse_area": 28_000.0,
        "total_warehouse_area": 28_000.0,
        "dc_count": 1,
        "daily_orders": 12_000.0,
        "sku_count": 10_000,
        "contract_years": 3,
        "service_scope": {
            "inbound":  {"receiving": True, "quality_check": True, "putaway": True},
            "outbound": {"picking": True, "packing": True, "loading": True, "shipping": True},
            "storage":  {"pallet_storage": True, "bin_storage": False},
            "value_added": {"kitting": False, "repack": True, "return_handling": True},
            "support":  {"system_integration": False},
        },
    }


@pytest.fixture
def F_MANUFACTURING():
    """MANUFACTURING — 一般制造，8,000 sqm，1 DC，华中。"""
    return {
        "project_name": "中工制造 WIP 仓储项目",
        "client_name": "中工重型装备制造有限公司",
        "industry": "MANUFACTURING",
        "region": "华中",
        "warehouse_area": 8_000.0,
        "total_warehouse_area": 8_000.0,
        "dc_count": 1,
        "daily_orders": 1_500.0,
        "sku_count": 3_000,
        "contract_years": 3,
        "service_scope": {
            "inbound":  {"receiving": True, "quality_check": True, "putaway": True},
            "outbound": {"picking": True, "packing": False, "loading": True, "shipping": True},
            "storage":  {"pallet_storage": True, "bin_storage": True},
            "value_added": {"kitting": False, "repack": False, "return_handling": False},
            "support":  {"system_integration": True},
        },
    }


@pytest.fixture
def F_GENERIC_3PL():
    """GENERIC_3PL — 兜底，混合型，6,000 sqm，1 DC，西部。"""
    return {
        "project_name": "通用物流代管项目",
        "client_name": "通远物流有限公司",
        "industry": "GENERIC_3PL",
        "region": "西部",
        "warehouse_area": 6_000.0,
        "total_warehouse_area": 6_000.0,
        "dc_count": 1,
        "daily_orders": 1_000.0,
        "sku_count": 2_000,
        "contract_years": 3,
        "service_scope": {
            "inbound":  {"receiving": True, "quality_check": False, "putaway": True},
            "outbound": {"picking": True, "packing": False, "loading": True, "shipping": True},
            "storage":  {"pallet_storage": True, "bin_storage": False},
            "value_added": {"kitting": False, "repack": False, "return_handling": False},
            "support":  {"system_integration": False},
        },
    }


# ─── Shared Helpers ──────────────────────────────────────────────────────

def adapt_and_generate(project_state):
    """
    Run adapt_project_state → generate_base_solution.
    Returns (adapter_output, base_solution_model).
    """
    from backend.solution.base_solution_input_adapter import adapt_project_state
    from backend.solution.base_solution_generator import generate_base_solution

    adapter_out = adapt_project_state(project_state)
    base_solution = generate_base_solution(
        project_id=project_state.get("project_name", "test"),
        project_state=adapter_out,
    )
    return adapter_out, base_solution


def serialize(bs):
    """
    Serialize BaseSolution model to dict via model_dump().
    Returns dict representation of BaseSolution.
    """
    if hasattr(bs, 'model_dump'):
        return bs.model_dump()
    return bs
