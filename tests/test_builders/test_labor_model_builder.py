"""
A层: labor_model_builder 单元测试
==========================================

Tests:
  1. AUTOMOTIVE → has line_side_team and tooling_team
  2. FMCG → no automotive-specific roles
  3. MANUFACTURING → no automotive roles
  4. GENERIC_3PL → baseline roles only
  5. industry parameter affects headcount
"""

import pytest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.schemas.base_solution_schema import ScaleTier
from backend.solution.section_builders.labor_model_builder import build_labor_model


class TestAutomotiveLaborRoles:
    """AUTOMOTIVE industry → automotive-specific labor roles."""

    @pytest.fixture
    def lm_auto(self):
        return build_labor_model(
            warehouse_area=35_000.0,
            daily_orders=5_000.0,
            service_scope={"outbound": {"picking": True}},
            region="华东",
            labor_cost_level="中",
            scale_tier=ScaleTier.L,
            industry="AUTOMOTIVE",
        )

    def test_has_line_side_team(self, lm_auto):
        roles = lm_auto.headcount_by_role or {}
        assert "line_side_team" in roles, \
            f"Expected line_side_team for AUTOMOTIVE, got roles: {list(roles.keys())}"

    def test_has_tooling_team(self, lm_auto):
        roles = lm_auto.headcount_by_role or {}
        assert "tooling_team" in roles, \
            f"Expected tooling_team for AUTOMOTIVE, got roles: {list(roles.keys())}"


class TestNonAutomotiveLaborRoles:
    """Non-automotive industries must NOT have automotive roles."""

    @pytest.fixture
    def lm_fgcu(self):
        return build_labor_model(
            warehouse_area=28_000.0, daily_orders=8_000.0,
            service_scope={"outbound": {"picking": True}},
            region="华东", labor_cost_level="中",
            scale_tier=ScaleTier.L, industry="FMCG",
        )

    @pytest.fixture
    def lm_mfg(self):
        return build_labor_model(
            warehouse_area=8_000.0, daily_orders=1_500.0,
            service_scope={"outbound": {"picking": True}},
            region="华中", labor_cost_level="中",
            scale_tier=ScaleTier.M, industry="MANUFACTURING",
        )

    @pytest.fixture
    def lm_3pl(self):
        return build_labor_model(
            warehouse_area=6_000.0, daily_orders=1_000.0,
            service_scope={"outbound": {"picking": True}},
            region="西部", labor_cost_level="中",
            scale_tier=ScaleTier.S, industry="GENERIC_3PL",
        )

    def test_fgcu_no_automotive_roles(self, lm_fgcu):
        roles = lm_fgcu.headcount_by_role or {}
        assert "line_side_team" not in roles
        assert "tooling_team" not in roles

    def test_mfg_no_automotive_roles(self, lm_mfg):
        roles = lm_mfg.headcount_by_role or {}
        assert "line_side_team" not in roles
        assert "tooling_team" not in roles

    def test_3pl_no_automotive_roles(self, lm_3pl):
        roles = lm_3pl.headcount_by_role or {}
        assert "line_side_team" not in roles
        assert "tooling_team" not in roles


class TestElectronicsLaborRoles:
    """ELECTRONICS → no automotive roles, has basic roles."""

    @pytest.fixture
    def lm_elec(self):
        return build_labor_model(
            warehouse_area=12_000.0, daily_orders=3_000.0,
            service_scope={"outbound": {"picking": True}},
            region="华南", labor_cost_level="高",
            scale_tier=ScaleTier.M, industry="ELECTRONICS",
        )

    def test_has_basic_roles(self, lm_elec):
        roles = lm_elec.headcount_by_role or {}
        assert "picking_team" in roles, f"Expected picking_team, got {list(roles.keys())}"

    def test_no_automotive_roles(self, lm_elec):
        roles = lm_elec.headcount_by_role or {}
        assert "line_side_team" not in roles
        assert "tooling_team" not in roles


class TestLaborCostByIndustry:
    """Labor cost per person month scales with region factor."""

    def test_region_factor_applied(self):
        """HIGH region_cost + 中 labor_cost_level → higher monthly cost."""
        lm_east = build_labor_model(
            warehouse_area=10_000.0, daily_orders=2_000.0,
            service_scope={}, region="华东",
            labor_cost_level="中", scale_tier=ScaleTier.M,
            industry="GENERIC_3PL",
        )
        lm_north = build_labor_model(
            warehouse_area=10_000.0, daily_orders=2_000.0,
            service_scope={}, region="华北",
            labor_cost_level="中", scale_tier=ScaleTier.M,
            industry="GENERIC_3PL",
        )
        # 华北 factor=1.05 > 华东 factor=1.0 → higher cost
        assert lm_north.labor_cost_per_person_month > lm_east.labor_cost_per_person_month
