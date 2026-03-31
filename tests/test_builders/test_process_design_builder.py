"""
A层: process_design_builder 单元测试
==========================================

Tests:
  1. Service scope → correct stage keys present
  2. All 5 industries run without crash
  3. Automotive service scope (receiving + quality_check + picking + loading) → expected stages

Note: industry parameter is accepted but currently does not affect stage output
(industry-specific stages are a future enhancement).
"""

import pytest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.solution.section_builders.process_design_builder import build_process_design


MINIMAL_SERVICE_SCOPE = {
    "inbound":  {"receiving": True, "quality_check": False, "putaway": True},
    "outbound": {"picking": True, "packing": False, "loading": True, "shipping": True},
    "storage":  {"pallet_storage": True, "bin_storage": False},
    "value_added": {"kitting": False, "repack": False, "return_handling": False},
    "support":  {"system_integration": False},
}

FULL_SERVICE_SCOPE = {
    "inbound":  {"receiving": True, "quality_check": True, "putaway": True},
    "outbound": {"picking": True, "packing": True, "loading": True, "shipping": True},
    "storage":  {"pallet_storage": True, "bin_storage": True},
    "value_added": {"kitting": True, "repack": True, "return_handling": True},
    "support":  {"system_integration": True},
}


def _stage_keys(pd) -> list[str]:
    return [s.stage_key for s in pd.stages]


class TestProcessStagesFromServiceScope:
    """Stage keys must reflect service_scope flags."""

    def test_receiving_creates_inbound_receiving_stage(self):
        pd = build_process_design(service_scope=MINIMAL_SERVICE_SCOPE, region="华东")
        keys = _stage_keys(pd)
        assert "inbound_receiving" in keys

    def test_quality_check_creates_inbound_quality_stage(self):
        scope = {**MINIMAL_SERVICE_SCOPE, "inbound": {"receiving": True, "quality_check": True}}
        pd = build_process_design(service_scope=scope, region="华东")
        keys = _stage_keys(pd)
        assert "inbound_quality_check" in keys

    def test_picking_creates_outbound_picking_stage(self):
        pd = build_process_design(service_scope=MINIMAL_SERVICE_SCOPE, region="华东")
        keys = _stage_keys(pd)
        assert "outbound_picking" in keys

    def test_packing_creates_outbound_packing_stage(self):
        scope = {**MINIMAL_SERVICE_SCOPE, "outbound": {"picking": True, "packing": True, "loading": True}}
        pd = build_process_design(service_scope=scope, region="华东")
        keys = _stage_keys(pd)
        assert "outbound_packing" in keys

    def test_loading_creates_outbound_loading_stage(self):
        pd = build_process_design(service_scope=MINIMAL_SERVICE_SCOPE, region="华东")
        keys = _stage_keys(pd)
        assert "outbound_loading" in keys

    def test_kitting_creates_va_stage(self):
        scope = {**MINIMAL_SERVICE_SCOPE, "value_added": {"kitting": True}}
        pd = build_process_design(service_scope=scope, region="华东")
        keys = _stage_keys(pd)
        assert "value_added_service" in keys


class TestAllIndustriesNoCrash:
    """All 5 industries must run without exception."""

    @pytest.mark.parametrize("industry", [
        "AUTOMOTIVE", "ELECTRONICS", "FMCG", "MANUFACTURING", "GENERIC_3PL"
    ])
    def test_no_crash(self, industry):
        pd = build_process_design(
            service_scope=FULL_SERVICE_SCOPE,
            region="华东",
            industry=industry,
        )
        assert pd is not None
        assert len(pd.stages) > 0


class TestStageSLARegion:
    """Region should affect SLA hours (different regions have different targets)."""

    def test_sla_hours_present(self):
        pd = build_process_design(service_scope=MINIMAL_SERVICE_SCOPE, region="华东")
        stages_with_sla = [s for s in pd.stages if s.sla_hours]
        assert len(stages_with_sla) > 0, "Expected at least one stage with SLA hours"

    def test_sla_hours_different_by_region(self):
        pd_east = build_process_design(service_scope=MINIMAL_SERVICE_SCOPE, region="华东")
        pd_north = build_process_design(service_scope=MINIMAL_SERVICE_SCOPE, region="华北")
        # Both should produce valid SLA hours
        assert all(s.sla_hours for s in pd_east.stages if s.sla_hours)
        assert all(s.sla_hours for s in pd_north.stages if s.sla_hours)
