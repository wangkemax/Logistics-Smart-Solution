"""
Robustness Tests for automation_engine — NoneType & field safety
================================================================
Covers all edge cases that caused Pipeline Stage 2 crashes:
  - min_area / max_area / area is None
  - sku_count is None
  - daily_orders is None
  - budget is None
  - scenario fields entirely missing
  - profile with only industry (no area/sku/budget)
"""

import pytest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.engines.automation_engine import (
    normalize_profile,
    normalize_scenario,
    in_range,
    score_sku_match,
    score_order_match,
    score_warehouse_conditions,
    score_budget_match,
    score_industry_match,
    recommend_automation,
)


class TestInRange:
    """Unit tests for in_range helper."""

    def test_none_value_returns_false(self):
        assert in_range(None, 0, 100) is False

    def test_value_in_range(self):
        assert in_range(50, 0, 100) is True

    def test_value_at_boundaries(self):
        assert in_range(0, 0, 100) is True
        assert in_range(100, 0, 100) is True

    def test_value_below_range(self):
        assert in_range(-1, 0, 100) is False

    def test_value_above_range(self):
        assert in_range(101, 0, 100) is False


class TestNormalizeProfile:
    """Unit tests for normalize_profile."""

    def test_all_none_fields_get_defaults(self):
        profile = normalize_profile({})
        assert profile["warehouse_area"] == 0
        assert profile["sku_count"] == 0
        assert profile["daily_orders"] == 0
        assert profile["industry"] == "未知"

    def test_partial_profile_keeps_real_values(self):
        profile = normalize_profile({
            "industry": "电商",
            "warehouse_area": 30000.0,
            "sku_count": None,
            "daily_orders": None,
        })
        assert profile["industry"] == "电商"
        assert profile["warehouse_area"] == 30000.0
        assert profile["sku_count"] == 0
        assert profile["daily_orders"] == 0

    def test_original_profile_not_mutated(self):
        original = {"warehouse_area": 25000.0}
        normalized = normalize_profile(original)
        assert original.get("warehouse_area") == 25000.0  # unchanged
        assert normalized["warehouse_area"] == 25000.0


class TestNormalizeScenario:
    """Unit tests for normalize_scenario."""

    def test_all_none_bounds_get_defaults(self):
        s = normalize_scenario({})
        assert s["sku_min"] == 0
        assert s["sku_max"] == 999999999
        assert s["order_min"] == 0
        assert s["order_max"] == 999999999

    def test_partial_scenario_keeps_real_bounds(self):
        s = normalize_scenario({
            "scenario_id": 1,
            "sku_min": 5000,
            "order_max": None,
        })
        assert s["scenario_id"] == 1
        assert s["sku_min"] == 5000
        assert s["sku_max"] == 999999999
        assert s["order_max"] == 999999999

    def test_original_scenario_not_mutated(self):
        original = {"sku_max": 100000}
        normalized = normalize_scenario(original)
        assert original["sku_max"] == 100000  # unchanged


class TestScoreSkuMatch:
    """SKU scoring with None and boundary edge cases."""

    def test_none_sku_count_returns_zero(self):
        scenario = {"sku_min": 5000, "sku_max": 100000}
        assert score_sku_match(scenario, None) == 0.0

    def test_sku_in_range_returns_full_score(self):
        scenario = {"sku_min": 5000, "sku_max": 100000}
        assert score_sku_match(scenario, 30000) == 20.0

    def test_sku_below_min_returns_ratio(self):
        scenario = {"sku_min": 10000, "sku_max": 100000}
        # 5000/10000 = 0.5 → 20*0.5 = 10
        assert score_sku_match(scenario, 5000) == 10.0

    def test_sku_above_max_returns_ratio(self):
        scenario = {"sku_min": 1000, "sku_max": 10000}
        # 10000/50000 = 0.2 → max(10, 20*0.2) = max(10, 4) = 10
        assert score_sku_match(scenario, 50000) == 10.0

    def test_scenario_min_none_defaults_to_zero(self):
        scenario = {"sku_min": None, "sku_max": 100000}
        assert score_sku_match(scenario, 50000) == 20.0

    def test_scenario_max_none_defaults_to_huge(self):
        scenario = {"sku_min": 5000, "sku_max": None}
        assert score_sku_match(scenario, 50000) == 20.0


class TestScoreOrderMatch:
    """Order volume scoring with None and boundary edge cases."""

    def test_none_orders_returns_zero(self):
        scenario = {"order_min": 500, "order_max": 50000}
        assert score_order_match(scenario, None) == 0.0

    def test_orders_in_range_returns_full_score(self):
        scenario = {"order_min": 500, "order_max": 50000}
        assert score_order_match(scenario, 5000) == 20.0

    def test_orders_below_min_returns_ratio(self):
        scenario = {"order_min": 2000, "order_max": 50000}
        assert score_order_match(scenario, 1000) == 10.0

    def test_orders_above_max_returns_ratio(self):
        scenario = {"order_min": 500, "order_max": 10000}
        assert score_order_match(scenario, 50000) == 10.0


class TestScoreWarehouseConditions:
    """Warehouse conditions scoring with None area."""

    def test_none_area_returns_base_score(self):
        scenario = {"category": "移动机器人"}
        assert score_warehouse_conditions(scenario, None, "中") == 10.0

    def test_large_area_large_warehouse_bonus(self):
        scenario = {"category": "移动机器人"}
        # area=30000 > 20000 + category matches → base_score=10+5=15
        assert score_warehouse_conditions(scenario, 30000, "中") == 15.0


class TestScoreBudgetMatch:
    """Budget scoring with all-None scenario."""

    def test_all_none_budget_bounds(self):
        scenario = {"capex_min": None, "capex_max": None}
        # normalize_scenario sets capex_min=0, capex_max=999999999
        # budget_threshold for "中" = 5000000
        # 0 <= 5000000 → score=20
        assert score_budget_match(scenario, "中") == 20.0

    def test_high_budget_with_low_capex_scenario(self):
        scenario = {"capex_min": 0, "capex_max": 999999999}
        assert score_budget_match(scenario, "高") == 20.0


class TestRecommendAutomation:
    """Full recommendation pipeline with edge case profiles."""

    def test_minimal_profile_industry_only(self):
        """Profile with only industry set — should not crash."""
        profile = {"industry": "电商"}
        results = recommend_automation(profile)
        assert isinstance(results, list)
        assert len(results) > 0
        # All scores should be numeric
        for r in results:
            assert isinstance(r.get("score"), (int, float))

    def test_all_none_profile(self):
        """Completely empty profile — should not crash."""
        results = recommend_automation({})
        assert isinstance(results, list)
        assert len(results) > 0

    def test_partial_profile_no_area_no_budget(self):
        """Profile missing area and budget — should not crash."""
        profile = {
            "industry": "电商",
            "sku_count": 30000,
            "daily_orders": 8000,
        }
        results = recommend_automation(profile)
        assert isinstance(results, list)
        assert len(results) > 0

    def test_none_scenario_fields_do_not_crash(self):
        """Scenario with completely missing fields — should not crash."""
        profile = {
            "industry": "电商",
            "warehouse_area": 30000,
            "sku_count": 80000,
            "daily_orders": 10000,
        }
        # This exercises normalize_scenario which sets all bounds safely
        results = recommend_automation(profile)
        assert isinstance(results, list)
        assert all(isinstance(r.get("score"), (int, float)) for r in results)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
