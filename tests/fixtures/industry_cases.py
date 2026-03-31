"""
Industry fixture data — plain Python dicts (no pytest dependency).
==============================================================

These are P0-complete project_state dicts for regression testing.
Use directly in @pytest.mark.parametrize or as test data.

P0 fields required by adapt_project_state:
  warehouse_area, total_warehouse_area, dc_count, daily_orders,
  sku_count, contract_years, service_scope
"""

from typing import Any


def _ss(
    inbound: dict = None,
    outbound: dict = None,
    storage: dict = None,
    value_added: dict = None,
    support: dict = None,
) -> dict:
    """Helper to build service_scope dicts."""
    return {
        "inbound":  inbound  or {},
        "outbound": outbound or {},
        "storage":  storage  or {},
        "value_added": value_added or {},
        "support":  support  or {},
    }


# ─── 5 Industry Fixtures ────────────────────────────────────────────────────

AUTOMOTIVE: dict[str, Any] = {
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
    "service_scope": _ss(
        inbound={"receiving": True, "quality_check": True, "putaway": True},
        outbound={"picking": True, "packing": True, "loading": True, "shipping": True},
        storage={"pallet_storage": True, "bin_storage": True},
        value_added={"kitting": False, "repack": False, "return_handling": False},
        support={"system_integration": True},
    ),
}


ELECTRONICS: dict[str, Any] = {
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
    "service_scope": _ss(
        inbound={"receiving": True, "quality_check": True, "putaway": True},
        outbound={"picking": True, "packing": True, "loading": True, "shipping": True},
        storage={"pallet_storage": True, "bin_storage": True},
        value_added={"kitting": False, "repack": False, "return_handling": False},
        support={"system_integration": True},
    ),
}


FMCG: dict[str, Any] = {
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
    "service_scope": _ss(
        inbound={"receiving": True, "quality_check": True, "putaway": True},
        outbound={"picking": True, "packing": True, "loading": True, "shipping": True},
        storage={"pallet_storage": True, "bin_storage": False},
        value_added={"kitting": False, "repack": True, "return_handling": True},
        support={"system_integration": False},
    ),
}


MANUFACTURING: dict[str, Any] = {
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
    "service_scope": _ss(
        inbound={"receiving": True, "quality_check": True, "putaway": True},
        outbound={"picking": True, "packing": False, "loading": True, "shipping": True},
        storage={"pallet_storage": True, "bin_storage": True},
        value_added={"kitting": False, "repack": False, "return_handling": False},
        support={"system_integration": True},
    ),
}


GENERIC_3PL: dict[str, Any] = {
    "project_name": "通用物流代管项目",
    "client_name": "通远物流有限公司",
    "industry": "GENERIC_3PL",
    "region": "西部",
    "warehouse_area": 3_000.0,
    "total_warehouse_area": 3_000.0,
    "dc_count": 1,
    "daily_orders": 1_000.0,
    "sku_count": 2_000,
    "contract_years": 3,
    "service_scope": _ss(
        inbound={"receiving": True, "quality_check": False, "putaway": True},
        outbound={"picking": True, "packing": False, "loading": True, "shipping": True},
        storage={"pallet_storage": True, "bin_storage": False},
        value_added={"kitting": False, "repack": False, "return_handling": False},
        support={"system_integration": False},
    ),
}


# Ordered list for easy iteration
ALL = [
    ("AUTOMOTIVE",     AUTOMOTIVE,    1.2),
    ("ELECTRONICS",    ELECTRONICS,   1.1),
    ("FMCG",           FMCG,          1.0),
    ("MANUFACTURING",  MANUFACTURING, 1.05),
    ("GENERIC_3PL",    GENERIC_3PL,  1.0),
]
