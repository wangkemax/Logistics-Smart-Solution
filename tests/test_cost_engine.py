import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.engines.cost_engine import (
    calculate_costs,
    calculate_warehouse_slots,
    calculate_headcount,
    calculate_roi,
    generate_cost_summary,
)


class TestWarehouseSlots:
    def test_basic_slot_calculation(self):
        slots = calculate_warehouse_slots(40000, pallet_density=4)
        assert slots == 10000

    def test_minimum_one_slot(self):
        slots = calculate_warehouse_slots(1, pallet_density=4)
        assert slots >= 1

    def test_high_inventory(self):
        slots = calculate_warehouse_slots(1000000, pallet_density=4)
        assert slots == 250000


class TestHeadcount:
    def test_manual_headcount(self):
        count = calculate_headcount(1500, "manual")
        # 1500 orders / 150 per person = 10 picking + 30% overhead = 13
        assert count > 0
        assert count >= 10

    def test_auto_needs_fewer_people(self):
        manual = calculate_headcount(3000, "manual")
        auto = calculate_headcount(3000, "full_auto")
        assert auto < manual

    def test_minimum_headcount(self):
        count = calculate_headcount(10, "manual")
        assert count >= 1


class TestROI:
    def test_positive_roi(self):
        roi = calculate_roi(
            labor_saving_annual=500000,
            maintenance_cost_annual=100000,
            capex=1000000,
            years=5,
        )
        assert roi > 0
        assert roi == pytest.approx(2.0, abs=0.01)

    def test_zero_capex_returns_zero(self):
        roi = calculate_roi(500000, 100000, 0)
        assert roi == 0.0

    def test_roi_proportional_to_years(self):
        roi_5y = calculate_roi(500000, 100000, 1000000, years=5)
        roi_10y = calculate_roi(500000, 100000, 1000000, years=10)
        assert roi_10y > roi_5y


class TestCostCalculation:
    def setup_method(self):
        self.base_profile = {
            "industry": "电商",
            "warehouse_area": 20000,
            "sku_count": 30000,
            "daily_orders": 5000,
            "inventory": 500000,
            "labor_cost_level": "中",
            "budget_level": "中",
            "automation_expectation": "中",
        }

    def test_returns_all_required_keys(self):
        result = calculate_costs(self.base_profile)
        required_keys = [
            "warehouse_cost", "labor_cost_annual", "automation_capex",
            "annual_maintenance", "total_annual_cost", "automation_savings_annual",
            "net_annual_benefit", "roi", "payback_years", "headcount_required",
            "headcount_saved",
        ]
        for key in required_keys:
            assert key in result, f"Missing key: {key}"

    def test_warehouse_cost_positive(self):
        result = calculate_costs(self.base_profile)
        assert result["warehouse_cost"] > 0

    def test_roi_positive_for_medium_budget(self):
        result = calculate_costs(self.base_profile)
        assert result["roi"] >= 0

    def test_high_labor_cost_increases_savings(self):
        low_profile = {**self.base_profile, "labor_cost_level": "低"}
        high_profile = {**self.base_profile, "labor_cost_level": "高"}

        low_result = calculate_costs(low_profile)
        high_result = calculate_costs(high_profile)

        assert high_result["automation_savings_annual"] > low_result["automation_savings_annual"]

    def test_scenario_id_affects_capex(self):
        default_result = calculate_costs(self.base_profile)
        amr_result = calculate_costs(self.base_profile, selected_scenario_id=1)
        gtp_result = calculate_costs(self.base_profile, selected_scenario_id=2)

        # AMR (1.25M) < GTP (5M) capex
        assert amr_result["automation_capex"] < gtp_result["automation_capex"]

    def test_larger_warehouse_higher_cost(self):
        small = calculate_costs({**self.base_profile, "warehouse_area": 5000})
        large = calculate_costs({**self.base_profile, "warehouse_area": 50000})
        assert large["warehouse_cost"] > small["warehouse_cost"]


class TestCostSummary:
    def test_summary_contains_key_info(self):
        cost_data = {
            "automation_capex": 2000000,
            "automation_savings_annual": 500000,
            "roi": 2.5,
            "payback_years": 3.0,
        }
        summary = generate_cost_summary(cost_data)
        assert "万" in summary
        assert "ROI" in summary
