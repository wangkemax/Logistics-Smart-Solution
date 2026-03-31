"""
A层: operation_mode_builder 单元测试
==========================================

Tests:
  1. industry → correct OperationModeEnum
  2. industry → correct INDUSTRY_OVERHEAD_FACTOR
  3. region → correct REGION_COST_INDEX
  4. build_operation_mode returns correct scale_tier labels
"""

import pytest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.schemas.base_solution_schema import OperationModeEnum, ScaleTier
from backend.solution.section_builders.operation_mode_builder import (
    build_operation_mode,
    INDUSTRY_OVERHEAD_FACTOR,
    INDUSTRY_OPERATION_MODES,
    REGION_COST_INDEX,
)


class TestIndustryToOperationMode:
    """industry → OperationModeEnum mapping tests."""

    @pytest.mark.parametrize("industry,expected_modes", [
        ("AUTOMOTIVE",    [OperationModeEnum.AUTOMOTIVE_LINE_SIDE]),
        ("ELECTRONICS",   [OperationModeEnum.ELECTRONICS_VMI_HUB]),
        ("FMCG",         [OperationModeEnum.FMCG_HIGH_TURNOVER]),
        ("MANUFACTURING", [OperationModeEnum.MANUFACTURING_WIP]),
        ("GENERIC_3PL",  [OperationModeEnum.STANDARD_WAREHOUSE]),
    ])
    def test_industry_returns_correct_primary_mode(self, industry, expected_modes):
        """Primary mode candidate must be correct for each industry."""
        result = build_operation_mode(
            industry=industry,
            service_scope={},
            warehouse_area=10_000.0,
            region="华东",
            dc_count=1,
            scale_tier=ScaleTier.M,
        )
        primary = result.mode_name
        assert primary in expected_modes, \
            f"industry={industry}: expected {expected_modes}, got {primary}"


class TestIndustryOverheadFactor:
    """INDUSTRY_OVERHEAD_FACTOR values."""

    def test_automotive_highest(self):
        assert INDUSTRY_OVERHEAD_FACTOR.get("AUTOMOTIVE") == 1.2

    def test_electronics_high(self):
        assert INDUSTRY_OVERHEAD_FACTOR.get("ELECTRONICS") == 1.1

    def test_fgcu_baseline(self):
        assert INDUSTRY_OVERHEAD_FACTOR.get("FMCG") == 1.0

    def test_manufacturing_slight_premium(self):
        assert INDUSTRY_OVERHEAD_FACTOR.get("MANUFACTURING") == 1.05

    def test_generic_3pl_baseline(self):
        assert INDUSTRY_OVERHEAD_FACTOR.get("GENERIC_3PL") == 1.0

    @pytest.mark.parametrize("industry,expected", [
        ("AUTOMOTIVE",    1.2),
        ("ELECTRONICS",   1.1),
        ("FMCG",         1.0),
        ("MANUFACTURING", 1.05),
        ("GENERIC_3PL",  1.0),
    ])
    def test_overhead_values(self, industry, expected):
        assert INDUSTRY_OVERHEAD_FACTOR.get(industry) == expected


class TestRegionCostIndex:
    """Region → cost index."""

    @pytest.mark.parametrize("region,expected", [
        ("华东", 1.00),
        ("华南", 0.95),
        ("华北", 1.05),
        ("华中", 0.98),
        ("西部", 0.92),
        ("东北", 1.00),
    ])
    def test_region_cost_index(self, region, expected):
        assert REGION_COST_INDEX.get(region) == expected, \
            f"region={region}: expected {expected}"


class TestScaleTierOutput:
    """Scale tier → label/size mapping."""

    @pytest.mark.parametrize("sqm,tier", [
        (60_000, ScaleTier.XL),
        (35_000, ScaleTier.L),
        (12_000, ScaleTier.M),
        (3_000,  ScaleTier.S),
        (500,    ScaleTier.XS),
    ])
    def test_scale_tier_mapping(self, sqm, tier):
        result = build_operation_mode(
            industry="FMCG",
            service_scope={},
            warehouse_area=sqm,
            region="华东",
            dc_count=1,
            scale_tier=tier,
        )
        assert result.scale_tier == tier.value, \
            f"{sqm} sqm → expected {tier.value}, got {result.scale_tier}"
