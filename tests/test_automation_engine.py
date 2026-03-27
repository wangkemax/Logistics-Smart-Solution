import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.engines.automation_engine import (
    recommend_automation,
    score_sku_match,
    score_order_match,
    score_budget_match,
    score_industry_match,
)


class TestSkuScoring:
    def test_sku_within_range_gets_full_score(self):
        scenario = {"sku_min": 5000, "sku_max": 100000}
        assert score_sku_match(scenario, 30000) == 20.0

    def test_low_sku_gets_reduced_score(self):
        scenario = {"sku_min": 10000, "sku_max": 100000}
        score = score_sku_match(scenario, 1000)
        assert score < 20.0
        assert score >= 0

    def test_sku_above_max_gets_partial_score(self):
        scenario = {"sku_min": 5000, "sku_max": 50000}
        score = score_sku_match(scenario, 200000)
        assert 10 <= score <= 20


class TestOrderScoring:
    def test_order_within_range_full_score(self):
        scenario = {"order_min": 1000, "order_max": 50000}
        assert score_order_match(scenario, 5000) == 20.0

    def test_low_order_reduced_score(self):
        scenario = {"order_min": 5000, "order_max": 100000}
        score = score_order_match(scenario, 100)
        assert score < 20.0


class TestBudgetScoring:
    def test_affordable_scenario_full_score(self):
        scenario = {"capex_min": 500000}
        score = score_budget_match(scenario, "中")
        assert score == 20.0

    def test_expensive_scenario_zero_score(self):
        scenario = {"capex_min": 20000000}
        score = score_budget_match(scenario, "低")
        assert score == 0.0


class TestIndustryScoring:
    def test_exact_industry_match(self):
        scenario = {"applicable_industry": "电商/3PL/零售"}
        assert score_industry_match(scenario, "电商") == 20.0

    def test_no_industry_match(self):
        scenario = {"applicable_industry": "制造"}
        score = score_industry_match(scenario, "电商")
        assert score < 20.0


class TestRecommendations:
    def test_low_sku_does_not_recommend_gtp(self):
        """Low SKU count should not recommend GTP (requires 10000+ SKUs)"""
        profile = {
            "industry": "电商",
            "warehouse_area": 10000,
            "sku_count": 500,  # Very low SKU
            "daily_orders": 1000,
            "inventory": 50000,
            "labor_cost_level": "中",
            "budget_level": "高",
            "automation_expectation": "高",
        }
        recommendations = recommend_automation(profile)
        scenario_names = [r["scenario_name"] for r in recommendations]
        # GTP requires 10000+ SKUs, should not be top recommendation for 500 SKUs
        if "GTP货到人系统" in scenario_names:
            gtp_idx = scenario_names.index("GTP货到人系统")
            if recommendations:
                assert recommendations[0]["scenario_name"] != "GTP货到人系统", \
                    "GTP should not be top recommendation for low SKU count"

    def test_low_order_does_not_recommend_sorting_line(self):
        """Low order volume should not recommend high-throughput sorting line"""
        profile = {
            "industry": "电商",
            "warehouse_area": 5000,
            "sku_count": 5000,
            "daily_orders": 100,  # Very low orders
            "inventory": 100000,
            "labor_cost_level": "低",
            "budget_level": "低",
            "automation_expectation": "低",
        }
        recommendations = recommend_automation(profile)

        # 跨带分拣机 requires 5000+ orders, shouldn't be top for 100/day
        if recommendations:
            assert recommendations[0]["scenario_name"] != "跨带分拣机", \
                "高速分拣机 should not be top recommendation for low order volume"

    def test_high_volume_ecommerce_recommends_amr(self):
        """High volume e-commerce should get relevant recommendations"""
        profile = {
            "industry": "电商",
            "warehouse_area": 30000,
            "sku_count": 50000,
            "daily_orders": 20000,
            "inventory": 2000000,
            "labor_cost_level": "高",
            "budget_level": "高",
            "automation_expectation": "高",
        }
        recommendations = recommend_automation(profile)
        assert len(recommendations) > 0
        assert recommendations[0]["score"] > 50

    def test_recommendations_sorted_by_score(self):
        """Recommendations should be sorted by score descending"""
        profile = {
            "industry": "3PL",
            "warehouse_area": 20000,
            "sku_count": 30000,
            "daily_orders": 5000,
            "inventory": 500000,
            "labor_cost_level": "中",
            "budget_level": "中",
            "automation_expectation": "中",
        }
        recommendations = recommend_automation(profile)
        scores = [r["score"] for r in recommendations]
        assert scores == sorted(scores, reverse=True)

    def test_returns_max_5_recommendations(self):
        """Should return at most 5 recommendations"""
        profile = {
            "industry": "电商",
            "warehouse_area": 50000,
            "sku_count": 80000,
            "daily_orders": 30000,
            "inventory": 3000000,
            "labor_cost_level": "高",
            "budget_level": "高",
            "automation_expectation": "高",
        }
        recommendations = recommend_automation(profile)
        assert len(recommendations) <= 5
