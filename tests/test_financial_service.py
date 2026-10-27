"""Financial service uses the shared cash-flow path. Amounts are yuan."""
from __future__ import annotations

import pytest
from backend.services.financial_service import FinancialService
from backend.schemas.financial_schemas import FinancialInput
from backend.services.financial_core import irr_percent, npv, project_cashflows, roi_multiple


@pytest.fixture
def service():
    return FinancialService()


def _sample(**overrides) -> FinancialInput:
    data = dict(
        workspace_id="test-ws-001",
        equipment_capex_min=2_000_000.0,
        equipment_capex_max=2_000_000.0,
        headcount_reduction=20,
        avg_labor_cost_per_person=120_000.0,
        warehouse_area_sqm=3000,
        warehouse_cost_per_sqm=600.0,
        utility_cost_per_sqm=20.0,
        maintenance_rate=0.02,
        annual_throughput_revenue=0.0,
        contract_years=5,
        discount_rate=0.08,
    )
    data.update(overrides)
    return FinancialInput(**data)


class TestFinancialServiceCalculate:
    def test_labor_is_benefit_only_and_rent_is_excluded(self, service):
        """20 people * 120000, utility and maintenance reduce net, rent does not.

        equipment 2,000,000; engineering+software 15% => capex 2,300,000
        labor benefit 2,400,000
        utility 3000 * 20 = 60,000
        maintenance 2,000,000 * 0.02 = 40,000
        net = 2,300,000
        rent 3000 * 600 = 1,800,000 is reported and not subtracted
        ROI multiple = 2,300,000 * 5 / 2,300,000 = 5.0x
        """
        result = service.calculate(_sample())
        assert result.opex_labor == 0
        assert result.revenue_labor_saving == 2_400_000
        assert result.opex_warehouse == 1_800_000
        assert result.opex_utility == 60_000
        assert result.opex_maintenance == 40_000
        assert result.net_annual_benefit == 2_300_000
        assert result.capex_total_min == pytest.approx(2_300_000)
        assert result.roi_5y == 5.0
        assert result.payback_years == 1.0
        assert "5年ROI 5.0x" in result.summary_text
        assert "万元" in result.summary_text

    def test_headcount_does_not_cancel(self, service):
        zero = service.calculate(_sample(headcount_reduction=0, annual_throughput_revenue=500_000))
        twenty = service.calculate(_sample(headcount_reduction=20, annual_throughput_revenue=500_000))
        assert twenty.net_annual_benefit - zero.net_annual_benefit == pytest.approx(2_400_000)

    def test_non_recoverable_irr_and_payback_are_null(self, service):
        result = service.calculate(
            _sample(
                equipment_capex_min=1_000_000,
                equipment_capex_max=1_000_000,
                headcount_reduction=0,
                avg_labor_cost_per_person=0,
                warehouse_area_sqm=0,
                warehouse_cost_per_sqm=0,
                utility_cost_per_sqm=0,
                maintenance_rate=0.02,
                annual_throughput_revenue=0,
            )
        )
        assert result.net_annual_benefit < 0
        assert result.payback_years is None
        assert result.irr is None
        assert "无法在合同期内回收" in result.summary_text

    def test_cashflow_matches_irr_and_discount_rate_changes_npv(self, service):
        result = service.calculate(_sample())
        assert len(result.cashflow_years) == 6
        assert result.cashflow_years[0] == pytest.approx(-2_300_000)
        assert result.cashflow_years[1] == result.net_annual_benefit
        rate = result.irr / 100.0
        flows = project_cashflows(2_300_000, result.net_annual_benefit, 5)
        assert result.cashflow_years == flows
        # IRR is published to 0.1 percentage point, so NPV is the closest of the neighboring ticks.
        center = abs(npv(result.cashflow_years, rate))
        assert center < abs(npv(result.cashflow_years, rate - 0.001))
        assert center <= abs(npv(result.cashflow_years, rate + 0.001)) + 1.0
        assert result.irr == irr_percent(flows)

        low = service.calculate(_sample(discount_rate=0.08))
        high = service.calculate(_sample(discount_rate=0.20))
        assert low.npv != high.npv
        assert low.npv == pytest.approx(npv(low.cashflow_years, 0.08), abs=0.05)
        assert high.npv < low.npv

    def test_roi_uses_contract_years(self, service):
        result = service.calculate(_sample(contract_years=10))
        expected = roi_multiple(result.net_annual_benefit, 2_300_000, 10)
        assert result.roi_5y == expected
        assert "10年ROI" in result.summary_text
        assert len(result.cashflow_years) == 11


class TestFinancialServiceSnapshot:
    def test_save_snapshot_persists(self, service):
        from backend.models.database import engine, Base

        Base.metadata.create_all(bind=engine)
        result = service.calculate(_sample(workspace_id="test-snapshot-001"))
        snap = service.save_snapshot(result, workspace_id="test-snapshot-001", snapshot_version=1)

        assert snap.id is not None
        assert snap.roi_5y == result.roi_5y
        assert snap.payback_years == result.payback_years
        assert snap.irr == result.irr
        assert snap.npv == result.npv
        assert snap.contract_years == 5
        assert snap.discount_rate == pytest.approx(0.08)
        assert snap.cashflow_y1 == result.cashflow_years[0]
