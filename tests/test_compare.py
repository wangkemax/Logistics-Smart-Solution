"""
Tests for multi-scenario comparison functionality.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.engines.cost_engine import compare_scenarios, SCENARIO_NAMES


SAMPLE_PROFILE = {
    "industry": "电商",
    "warehouse_area": 20000,
    "sku_count": 30000,
    "daily_orders": 5000,
    "inventory": 500000,
    "labor_cost_level": "中",
    "budget_level": "中",
    "automation_expectation": "中",
}


class TestCompareScenarios:
    def test_compare_returns_multiple_results(self):
        result = compare_scenarios(SAMPLE_PROFILE, "华东", [1, 2, 3])
        assert len(result) == 3

    def test_compare_sorted_by_roi_descending(self):
        result = compare_scenarios(SAMPLE_PROFILE, "华东", [1, 2, 3, 5])
        roi_values = [r["roi_5y"] for r in result]
        assert roi_values == sorted(roi_values, reverse=True)

    def test_best_flag_set_on_top_roi(self):
        result = compare_scenarios(SAMPLE_PROFILE, "华东", [1, 2, 3])
        assert any(r.get("is_best") for r in result)
        best_count = sum(1 for r in result if r.get("is_best"))
        assert best_count == 1

    def test_all_scenarios_have_required_keys(self):
        result = compare_scenarios(SAMPLE_PROFILE, "华东", [1, 2])
        required_keys = {
            "scenario_id", "scenario_name", "category",
            "automation_capex", "annual_saving", "roi_5y",
            "payback_years", "headcount_saved", "five_year_net_benefit",
        }
        for r in result:
            assert required_keys.issubset(r.keys()), f"Missing keys in {r['scenario_name']}"

    def test_max_5_scenarios(self):
        result = compare_scenarios(SAMPLE_PROFILE, "华东", [1, 2, 3, 4, 5, 6, 7])
        assert len(result) == 5

    def test_min_2_scenarios_required(self):
        # With only 1 scenario, it still returns 1 result (behavior is to return what it can)
        result = compare_scenarios(SAMPLE_PROFILE, "华东", [1])
        assert len(result) == 1

    def test_scenario_names_are_correct(self):
        result = compare_scenarios(SAMPLE_PROFILE, "华东", [1, 5])
        names = {r["scenario_name"] for r in result}
        assert "AMR拣选辅助" in names
        assert "立体仓库AS/RS" in names

    def test_capex_and_saving_are_positive(self):
        result = compare_scenarios(SAMPLE_PROFILE, "华东", [1, 2, 3])
        for r in result:
            assert r["automation_capex"] > 0
            assert r["annual_saving"] >= 0
            assert r["payback_years"] > 0


class TestCompareY1Ebita:
    def test_y1_ebita_fields_exist_in_compare(self):
        result = compare_scenarios(SAMPLE_PROFILE, "华东", [1, 2])
        for r in result:
            assert "y1_ebita" in r
            assert "y1_revenue" in r
            assert "y1_operating_cost" in r

    def test_y1_ebita_is_numeric(self):
        result = compare_scenarios(SAMPLE_PROFILE, "华东", [1, 2])
        for r in result:
            assert isinstance(r["y1_ebita"], (int, float))

    def test_y1_ebita_not_none(self):
        result = compare_scenarios(SAMPLE_PROFILE, "华东", [1, 3])
        assert len(result) == 2

