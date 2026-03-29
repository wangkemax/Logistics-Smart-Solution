"""
test_operation_profile.py — v0.6.5 Regression Tests
===================================================

Tests for operation_profile derivation from service_scope matrix.

Run with:
    cd ~/Projects/logistics-presale-ai
    /opt/homebrew/bin/python3 -m pytest tests/test_operation_profile.py -v
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from backend.services.operation_profile_service import (
    derive_operation_profile,
    calculate_service_complexity,
    derive_labor_modules,
    derive_operation_type,
    generate_operation_narrative,
    SERVICE_TO_LABOR_MODULE,
    COMPLEXITY_SCORING,
)
from backend.services.process_templates import build_process_modules, get_active_processes
from backend.schemas.schemas import OperationProfile, LaborModules


# =============================================================================
# Test Helpers
# =============================================================================

def make_scope(**categories):
    """Build a service_scope dict. Values are lists of active service keys."""
    result = {}
    for cat, services in categories.items():
        if isinstance(services, dict):
            result[cat] = services
        else:
            result[cat] = {svc: True for svc in services}
    return result


# =============================================================================
# Complexity Scoring Tests
# =============================================================================

class TestComplexityScoring:
    def test_empty_scope_returns_zero(self):
        score, level = calculate_service_complexity({})
        assert score == 0
        assert level == "low"

    def test_single_service_low(self):
        scope = make_scope(inbound={"receiving": True}, storage={}, outbound={}, value_added={}, support={})
        score, level = calculate_service_complexity(scope)
        assert score == 1
        assert level == "low"

    def test_temperature_control_adds_two(self):
        scope = make_scope(
            inbound={"receiving": True},
            storage={"temperature_control": True},
            outbound={}, value_added={}, support={}
        )
        score, level = calculate_service_complexity(scope)
        # 1 (receiving) + 1 (base) + 2 (temperature_control bonus) = 4
        assert score == 4
        assert level == "low"

    def test_value_added_services_add_two_each(self):
        scope = make_scope(
            inbound={}, storage={}, outbound={},
            value_added={"kitting": True, "return_handling": True},
            support={}
        )
        score, level = calculate_service_complexity(scope)
        # kitting: base+1 + va_bonus+2 = 3
        # return_handling: base+1 + return_handling_bonus+1 = 2
        # total = 5
        assert score == 5
        assert level == "low"

    def test_complex_scope_high(self):
        scope = make_scope(
            inbound={"receiving": True, "unloading": True, "quality_check": True, "putaway": True},
            storage={"pallet_storage": True, "temperature_control": True},
            outbound={"picking": True, "packing": True, "loading": True, "shipping": True},
            value_added={"kitting": True, "return_handling": True, "cycle_count": True},
            support={"inventory_reporting": True, "system_integration": True},
        )
        score, level = calculate_service_complexity(scope)
        # base: 4+2+4+3+2 = 15
        # bonuses: tc+2, kitting+2, return+1, cycle_count+2, system_integration+1 = 8
        # total = 23 → high
        assert score == 23
        assert level == "high"

    def test_null_scope_returns_low(self):
        score, level = calculate_service_complexity(None)
        assert score == 0
        assert level == "low"


# =============================================================================
# Labor Modules Tests
# =============================================================================

class TestLaborModules:
    def test_receiving_team_active(self):
        scope = make_scope(inbound={"receiving": True}, storage={}, outbound={}, value_added={}, support={})
        lm = derive_labor_modules(scope)
        assert lm.receiving_team is True
        assert lm.picking_team is False

    def test_picking_and_packing_active(self):
        scope = make_scope(inbound={}, storage={}, outbound={"picking": True, "packing": True}, value_added={}, support={})
        lm = derive_labor_modules(scope)
        assert lm.picking_team is True
        assert lm.packing_team is True
        assert lm.loading_team is False

    def test_return_handling_maps_to_return_processing_team(self):
        scope = make_scope(inbound={}, storage={}, outbound={}, value_added={"return_handling": True}, support={})
        lm = derive_labor_modules(scope)
        assert lm.return_processing_team is True

    def test_inventory_reporting_maps_to_inventory_control_team(self):
        scope = make_scope(inbound={}, storage={}, outbound={}, value_added={}, support={"inventory_reporting": True})
        lm = derive_labor_modules(scope)
        assert lm.inventory_control_team is True

    def test_empty_scope_no_active_modules(self):
        scope = make_scope(inbound={}, storage={}, outbound={}, value_added={}, support={})
        lm = derive_labor_modules(scope)
        assert lm.receiving_team is False
        assert lm.picking_team is False
        assert lm.packing_team is False


# =============================================================================
# Operation Type Tests
# =============================================================================

class TestOperationType:
    def test_warehouse_distribution(self):
        scope = make_scope(
            inbound={"receiving": True}, storage={"pallet_storage": True},
            outbound={"picking": True}, value_added={}, support={}
        )
        assert derive_operation_type(scope) == "warehouse_distribution"

    def test_cold_chain(self):
        scope = make_scope(
            inbound={"receiving": True}, storage={"temperature_control": True},
            outbound={"picking": True}, value_added={}, support={}
        )
        assert derive_operation_type(scope) == "cold_chain"

    def test_empty_scope_returns_custom(self):
        assert derive_operation_type({}) == "custom"


# =============================================================================
# Operation Profile Full Derivation Tests
# =============================================================================

class TestOperationProfileDerivation:
    def test_full_derivation_porsche_like(self):
        """Test with a 保时捷-like service scope (warehouse distribution)."""
        scope = make_scope(
            inbound={"receiving": True, "unloading": True, "quality_check": False, "putaway": True},
            storage={"pallet_storage": True, "bin_storage": False, "temperature_control": False, "bonded_storage": False},
            outbound={"picking": True, "packing": True, "labeling": False, "loading": True, "shipping": True},
            value_added={"kitting": False, "repack": False, "light_assembly": False, "return_handling": False, "cycle_count": True},
            support={"inventory_reporting": True, "system_integration": False, "data_reporting": False},
        )
        op = derive_operation_profile(scope)

        assert isinstance(op, OperationProfile)
        assert op.operation_type == "warehouse_distribution"
        assert op.inbound_required is True
        assert op.outbound_required is True
        assert op.value_added_required is True   # cycle_count
        assert op.support_required is True       # inventory_reporting
        assert op.temperature_control_required is False
        assert op.return_flow_required is False
        assert op.service_complexity_level in ("low", "medium", "high")
        assert isinstance(op.labor_modules, LaborModules)

    def test_derive_from_empty_scope(self):
        op = derive_operation_profile({})
        assert op.operation_type == "custom"  # empty scope → custom type
        assert op.inbound_required is False
        assert op.service_complexity_score == 0
        assert op.service_complexity_level == "low"
        assert isinstance(op.labor_modules, LaborModules)

    def test_derive_from_none(self):
        op = derive_operation_profile(None)
        assert op.operation_type == "unknown"
        assert op.service_complexity_score == 0

    def test_narrative_not_empty(self):
        scope = make_scope(inbound={"receiving": True}, storage={}, outbound={"picking": True}, value_added={}, support={})
        op = derive_operation_profile(scope)
        assert len(op.operation_narrative) > 10
        assert "运营" in op.operation_narrative

    def test_narrative_empty_scope(self):
        op = derive_operation_profile({})
        assert "未提供" in op.operation_narrative


# =============================================================================
# Schema Validation Tests
# =============================================================================

class TestOperationProfileSchema:
    def test_operation_profile_serializable(self):
        scope = make_scope(inbound={"receiving": True}, storage={}, outbound={"picking": True}, value_added={}, support={})
        op = derive_operation_profile(scope)
        d = op.model_dump()
        assert isinstance(d, dict)
        assert "operation_type" in d
        assert "labor_modules" in d
        assert "service_complexity_score" in d

    def test_labor_modules_all_boolean(self):
        lm = LaborModules()
        assert isinstance(lm.receiving_team, bool)
        assert isinstance(lm.picking_team, bool)


# =============================================================================
# Process Modules Tests — v0.6.6
# =============================================================================

class TestProcessModules:
    def test_receiving_triggers_receiving_process(self):
        lm = {"receiving_team": True, "picking_team": False, "packing_team": False,
              "loading_team": False, "return_processing_team": False, "inventory_control_team": False}
        pm = build_process_modules(lm)
        assert "receiving_process" in pm
        assert pm["receiving_process"]["step_count"] == 8

    def test_picking_triggers_outbound_process(self):
        lm = {"receiving_team": False, "picking_team": True, "packing_team": False,
              "loading_team": False, "return_processing_team": False, "inventory_control_team": False}
        pm = build_process_modules(lm)
        assert "outbound_process" in pm

    def test_packing_and_loading_both_trigger_outbound(self):
        lm = {"receiving_team": False, "picking_team": False, "packing_team": True,
              "loading_team": True, "return_processing_team": False, "inventory_control_team": False}
        pm = build_process_modules(lm)
        assert "outbound_process" in pm

    def test_inventory_control_triggers_storage_management(self):
        lm = {"receiving_team": False, "picking_team": False, "packing_team": False,
              "loading_team": False, "return_processing_team": False, "inventory_control_team": True}
        pm = build_process_modules(lm)
        assert "storage_management" in pm

    def test_return_handling_triggers_return_process(self):
        lm = {"receiving_team": False, "picking_team": False, "packing_team": False,
              "loading_team": False, "return_processing_team": True, "inventory_control_team": False}
        pm = build_process_modules(lm)
        assert "return_process" in pm

    def test_value_added_flag_triggers_va_process(self):
        lm = {"receiving_team": False, "picking_team": False, "packing_team": False,
              "loading_team": False, "return_processing_team": False, "inventory_control_team": False}
        pm = build_process_modules(lm, value_added_required=True)
        assert "va_process" in pm

    def test_temperature_control_flag_triggers_tc_process(self):
        lm = {"receiving_team": False, "picking_team": False, "packing_team": False,
              "loading_team": False, "return_processing_team": False, "inventory_control_team": False}
        pm = build_process_modules(lm, temperature_control_required=True)
        assert "temperature_control" in pm

    def test_empty_labor_modules_returns_empty_processes(self):
        lm = {"receiving_team": False, "picking_team": False, "packing_team": False,
              "loading_team": False, "return_processing_team": False, "inventory_control_team": False}
        pm = build_process_modules(lm)
        assert pm == {}

    def test_full_porsche_like_scope_has_multiple_processes(self):
        lm = {"receiving_team": True, "putaway_team": True, "picking_team": True,
              "packing_team": True, "loading_team": True, "return_processing_team": False,
              "inventory_control_team": True}
        pm = build_process_modules(
            lm,
            value_added_required=True,
            temperature_control_required=False,
            support_required=True,
        )
        assert len(pm) >= 4
        assert "receiving_process" in pm
        assert "outbound_process" in pm
        assert "storage_management" in pm
        assert "va_process" in pm
        assert "support_process" in pm

    def test_process_modules_in_operation_profile(self):
        scope = make_scope(
            inbound={"receiving": True}, storage={"pallet_storage": True},
            outbound={"picking": True}, value_added={}, support={}
        )
        op = derive_operation_profile(scope)
        assert isinstance(op.process_modules, dict)
        assert "receiving_process" in op.process_modules
        assert "outbound_process" in op.process_modules


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
