"""
A层: kpi_framework_builder 单元测试
==========================================

Tests:
  1. Automotive KPIs: 供料及时率 / 停线事件 / 器具周转 / 线边库存准确率
  2. Electronics KPIs: FIFO / 准确率 / VMI
  3. FMCG KPIs: 履约时效 / 波次拣选效率
  4. Manufacturing KPIs: 配料准确率 / 批次追溯
  5. GENERIC_3PL: no automotive KPIs
"""

import pytest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.schemas.base_solution_schema import KPIFramework
from backend.solution.section_builders.kpi_framework_builder import build_kpi_framework


def _kpi_names_from_obj(kf: KPIFramework) -> list[str]:
    """Extract KPI names from a KPIFramework object (Pydantic model)."""
    return [k.name for k in kf.operational_kpis]


def _kpi_names_from_dict(kf: dict) -> list[str]:
    """Extract KPI names from a serialized KPIFramework dict."""
    return [k.get("name", "") for k in kf.get("operational_kpis", [])]


class TestAutomotiveKPIs:
    """AUTOMOTIVE → automotive-specific KPI types."""

    @pytest.fixture
    def kf_auto(self):
        return build_kpi_framework(
            service_scope={"outbound": {"picking": True, "loading": True}},
            kpi_targets=None,
            industry="AUTOMOTIVE",
            region="华东",
            labor_cost_level="中",
        )

    def test_has_line_feed_timeliness(self, kf_auto):
        names = _kpi_names_from_obj(kf_auto)
        assert any("供料" in n or "及时率" in n for n in names), \
            f"Missing 供料及时率 KPI, got: {names}"

    def test_has_line_stop_events(self, kf_auto):
        names = _kpi_names_from_obj(kf_auto)
        assert any("停线" in n for n in names), \
            f"Missing 停线事件 KPI, got: {names}"

    def test_has_tool_turnover(self, kf_auto):
        names = _kpi_names_from_obj(kf_auto)
        assert any("器具" in n and "周转" in n for n in names), \
            f"Missing 器具周转 KPI, got: {names}"

    def test_has_line_side_inventory_accuracy(self, kf_auto):
        names = _kpi_names_from_obj(kf_auto)
        assert any("线边" in n and "准确" in n for n in names), \
            f"Missing 线边库存准确率 KPI, got: {names}"


class TestElectronicsKPIs:
    """ELECTRONICS → VMI / FIFO / accuracy KPIs."""

    @pytest.fixture
    def kf_elec(self):
        return build_kpi_framework(
            service_scope={"inbound": {"putaway": True}, "outbound": {"picking": True}},
            kpi_targets=None,
            industry="ELECTRONICS",
            region="华南",
            labor_cost_level="中",
        )

    def test_has_accuracy_kpi(self, kf_elec):
        names = _kpi_names_from_obj(kf_elec)
        assert any("准确" in n or "FIFO" in n for n in names), \
            f"Missing accuracy/FIFO KPI, got: {names}"

    def test_has_vmi_or_inventory_kpi(self, kf_elec):
        names = _kpi_names_from_obj(kf_elec)
        electronics_keywords = ["VMI", "准确率", "FIFO", "追溯", "库存"]
        found = [n for n in names if any(k in n for k in electronics_keywords)]
        assert found, f"Expected electronics KPI in {names}"


class TestFMCGKPIs:
    """FMCG → throughput / fulfillment KPIs."""

    @pytest.fixture
    def kf_fgcu(self):
        return build_kpi_framework(
            service_scope={"outbound": {"picking": True, "packing": True}},
            kpi_targets=None,
            industry="FMCG",
            region="华东",
            labor_cost_level="中",
        )

    def test_has_fulfillment_speed_kpi(self, kf_fgcu):
        names = _kpi_names_from_obj(kf_fgcu)
        fgcu_keywords = ["履约", "时效", "波次", "拣选效率", "周转"]
        found = [n for n in names if any(k in n for k in fgcu_keywords)]
        assert found, f"Expected FMCG throughput KPI in {names}"


class TestManufacturingKPIs:
    """MANUFACTURING → batching / traceability KPIs."""

    @pytest.fixture
    def kf_mfg(self):
        return build_kpi_framework(
            service_scope={"inbound": {"putaway": True}, "outbound": {"loading": True}},
            kpi_targets=None,
            industry="MANUFACTURING",
            region="华中",
            labor_cost_level="中",
        )

    def test_has_basic_warehouse_kpis(self, kf_mfg):
        """MANUFACTURING produces generic warehouse KPIs (配料/批次-specific is future work)."""
        names = _kpi_names_from_obj(kf_mfg)
        # Should have basic inbound + outbound KPIs
        basic = ["入库", "出库", "准确率", "货损"]
        found = [n for n in names if any(k in n for k in basic)]
        assert found, f"Expected basic warehouse KPIs for MANUFACTURING, got: {names}"


class TestGeneric3PLKPIs:
    """GENERIC_3PL → no automotive KPIs."""

    @pytest.fixture
    def kf_3pl(self):
        return build_kpi_framework(
            service_scope={"inbound": {"putaway": True}, "outbound": {"picking": True}},
            kpi_targets=None,
            industry="GENERIC_3PL",
            region="西部",
            labor_cost_level="中",
        )

    def test_no_automotive_kpis(self, kf_3pl):
        names = _kpi_names_from_obj(kf_3pl)
        auto_kpis = ["供料及时率", "停线事件", "器具周转", "线边库存"]
        found = [n for n in names if any(k in n for k in auto_kpis)]
        assert not found, f"GENERIC_3PL should not have automotive KPIs, found: {found}"
