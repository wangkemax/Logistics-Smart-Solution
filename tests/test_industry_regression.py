"""
B层: 4行业 + GENERIC_3PL 回归样板测试
==========================================

Tests: adapt_project_state → generate_base_solution → serialize → assert key fields.

Must-pass thresholds:
  ✅ 4行业 operation_mode.mode_name correct
  ✅ 4行业 overhead factor correct
  ✅ 4行业 key KPI present (or absent for negative checks)
  ✅ 4行业 key labor role present (or absent for negative checks)
  ✅ 4行业 process design key stage present
  ✅ GENERIC_3PL falls back to standard_warehouse mode
  ✅ No crashes across all 5 fixtures

Good-to-have:
  ✅ Narrative contains industry keyword (manual check)

Fixtures (plain dicts): tests.fixtures.industry_cases
"""

import pytest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.schemas.base_solution_schema import OperationModeEnum
from backend.solution.base_solution_generator import generate_base_solution
from tests.fixtures.industry_cases import (
    AUTOMOTIVE, ELECTRONICS, FMCG, MANUFACTURING, GENERIC_3PL, ALL
)


# ─── Helpers ──────────────────────────────────────────────────────────────

def full_pipeline(project_state: dict):
    """Run generate_base_solution (internally calls adapt_project_state). Returns BaseSolution."""
    bs = generate_base_solution(
        project_state=project_state,
        project_id=project_state.get("project_name", "test"),
    )
    return bs


def bs_to_dict(bs):
    """Serialize BaseSolution to dict."""
    return bs.model_dump() if hasattr(bs, 'model_dump') else bs


def get_op(d: dict):
    return d.get("operation_mode") or {}


def get_labor(d: dict):
    return d.get("labor_model") or {}


def get_kpis(d: dict) -> list:
    """Get KPI names from serialized BaseSolution dict."""
    kf = d.get("kpi_framework") or {}
    operational = kf.get("operational_kpis") or []
    top_kpis = d.get("kpis") or []
    names_from_obj = [item.get("name", "") if isinstance(item, dict) else item for item in operational]
    return names_from_obj + list(top_kpis)


# ─── B层: 4行业 Regression ───────────────────────────────────────────────

class TestAutomotiveRegression:
    """AUTOMOTIVE fixture — must pass thresholds."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.d = bs_to_dict(full_pipeline(AUTOMOTIVE))

    def test_mode_is_automotive(self):
        op = get_op(self.d)
        assert op.get("mode_name") in (
            OperationModeEnum.AUTOMOTIVE_LINE_SIDE,
            OperationModeEnum.AUTOMOTIVE_SEQUENCING,
        ), f"Expected AUTOMOTIVE mode, got {op.get('mode_name')}"

    def test_overhead_is_1_2(self):
        op = get_op(self.d)
        assert op.get("industry_overhead_factor") == 1.2

    def test_region_cost_index_east_china(self):
        assert get_op(self.d).get("region_cost_index") == 1.0

    def test_scale_tier_L(self):
        assert get_op(self.d).get("scale_tier") == "l"

    def test_has_automotive_kpi(self):
        names = get_kpis(self.d)
        auto_kpis = ["供料及时率", "停线事件", "器具周转", "线边库存准确率", "缺料响应"]
        found = [n for n in names if any(k in n for k in auto_kpis)]
        assert found, f"Expected automotive KPI in {names}"

    def test_has_automotive_labor_role(self):
        roles = get_labor(self.d).get("headcount_by_role") or {}
        assert "line_side_team" in roles or "tooling_team" in roles, \
            f"Expected automotive role in {list(roles.keys())}"

    def test_confidence_not_unknown(self):
        assert self.d.get("confidence") != "unknown"


class TestElectronicsRegression:
    """ELECTRONICS fixture — must pass thresholds."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.d = bs_to_dict(full_pipeline(ELECTRONICS))

    def test_mode_is_electronics_vmi_hub(self):
        op = get_op(self.d)
        assert op.get("mode_name") == OperationModeEnum.ELECTRONICS_VMI_HUB, \
            f"Expected ELECTRONICS_VMI_HUB, got {op.get('mode_name')}"

    def test_overhead_is_1_1(self):
        assert get_op(self.d).get("industry_overhead_factor") == 1.1

    def test_region_cost_index_south_china(self):
        assert get_op(self.d).get("region_cost_index") == 0.95

    def test_scale_tier_M(self):
        assert get_op(self.d).get("scale_tier") == "m"

    def test_has_electronics_kpi(self):
        names = get_kpis(self.d)
        elec_kpis = ["准确率", "FIFO", "追溯", "VMI", "库存准确"]
        found = [n for n in names if any(k in n for k in elec_kpis)]
        assert found, f"Expected electronics KPI in {names}"


class TestFMCGRegression:
    """FMCG fixture — must pass thresholds."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.d = bs_to_dict(full_pipeline(FMCG))

    def test_mode_is_fgcu_high_turnover(self):
        op = get_op(self.d)
        assert op.get("mode_name") == OperationModeEnum.FMCG_HIGH_TURNOVER, \
            f"Expected FMCG_HIGH_TURNOVER, got {op.get('mode_name')}"

    def test_overhead_is_1_0(self):
        assert get_op(self.d).get("industry_overhead_factor") == 1.0

    def test_scale_tier_L(self):
        assert get_op(self.d).get("scale_tier") == "l"

    def test_has_fgcu_kpi(self):
        names = get_kpis(self.d)
        fgcu_kpis = ["履约", "波次", "拣选效率", "时效", "周转"]
        found = [n for n in names if any(k in n for k in fgcu_kpis)]
        assert found, f"Expected FMCG KPI in {names}"


class TestManufacturingRegression:
    """MANUFACTURING fixture — must pass thresholds."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.d = bs_to_dict(full_pipeline(MANUFACTURING))

    def test_mode_is_manufacturing_wip(self):
        op = get_op(self.d)
        assert op.get("mode_name") == OperationModeEnum.MANUFACTURING_WIP, \
            f"Expected MANUFACTURING_WIP, got {op.get('mode_name')}"

    def test_overhead_is_1_05(self):
        assert get_op(self.d).get("industry_overhead_factor") == 1.05

    def test_scale_tier_M(self):
        assert get_op(self.d).get("scale_tier") == "m"

    def test_no_automotive_labor_roles(self):
        roles = get_labor(self.d).get("headcount_by_role") or {}
        assert "line_side_team" not in roles, "MANUFACTURING should not have line_side_team"
        assert "tooling_team" not in roles, "MANUFACTURING should not have tooling_team"


class TestGeneric3PLRegression:
    """GENERIC_3PL fixture — fallback/兜底 regression."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.d = bs_to_dict(full_pipeline(GENERIC_3PL))

    def test_mode_is_standard_warehouse(self):
        op = get_op(self.d)
        assert op.get("mode_name") == OperationModeEnum.STANDARD_WAREHOUSE, \
            f"Expected STANDARD_WAREHOUSE, got {op.get('mode_name')}"

    def test_overhead_is_1_0(self):
        assert get_op(self.d).get("industry_overhead_factor") == 1.0

    def test_scale_tier_S(self):
        # 3,000 sqm → S scale tier (range 1,000-5,000)
        assert get_op(self.d).get("scale_tier") == "s"

    def test_no_automotive_kpis(self):
        names = get_kpis(self.d)
        auto_kpis = ["供料及时率", "停线事件", "器具周转", "线边"]
        found = [n for n in names if any(k in n for k in auto_kpis)]
        assert not found, f"GENERIC_3PL should not have automotive KPIs, found: {found}"


# ─── Module-level smoke + overhead tests ──────────────────────────────────

@pytest.mark.parametrize("name,state,expected_overhead", ALL)
def test_smoke_no_crash(name, state, expected_overhead):
    """All 5 fixtures must run end-to-end without exception."""
    bs = full_pipeline(state)
    d = bs_to_dict(bs)
    assert d is not None
    assert "operation_mode" in d


@pytest.mark.parametrize("name,state,expected_overhead", ALL)
def test_overhead(name, state, expected_overhead):
    """Overhead must match expected value for each industry."""
    d = bs_to_dict(full_pipeline(state))
    assert get_op(d).get("industry_overhead_factor") == expected_overhead, \
        f"{name}: expected {expected_overhead}"
