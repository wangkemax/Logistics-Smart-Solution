"""tests/test_financial_service.py — v1.2 Financial Service Tests"""
from __future__ import annotations

import pytest
from backend.services.financial_service import FinancialService
from backend.schemas.financial_schemas import FinancialInput, FinancialResult


@pytest.fixture
def service():
    return FinancialService()


class TestFinancialServiceCalculate:
    def test_calculate_returns_roi_and_payback(self, service):
        """验证 ROI 和 Payback 计算正确"""
        # 合理场景：收益覆盖 OPEX
        # 成本单位: warehouse/utility_cost_per_sqm 是 万元/m²/年
        # 人力节省: 20人 × 12万 = 240万
        # 仓储: 3000m² × 0.05万/m² = 150万
        # 水电: 3000m² × 0.02万/m² = 60万
        # 维保: (200+250)/2 × 0.02 = 4.5万
        # OPEX 总计 = 454.5万
        # 吞吐量收益: 300万
        # 收益总计 = 540万
        # 年净收益 = 540 - 454.5 = 85.5万 > 0 ✓
        inp = FinancialInput(
            workspace_id="test-ws-001",
            equipment_capex_min=200.0,
            equipment_capex_max=250.0,
            headcount_reduction=20,
            avg_labor_cost_per_person=12.0,
            warehouse_area_sqm=3000,
            warehouse_cost_per_sqm=0.05,
            utility_cost_per_sqm=0.02,
            maintenance_rate=0.02,
            annual_throughput_revenue=300.0,
            contract_years=5,
            discount_rate=0.08,
        )
        result = service.calculate(inp)

        assert result.roi_5y > 0, f"ROI should be positive, got {result.roi_5y}"
        assert 0 < result.payback_years < 999, f"Payback should be reasonable, got {result.payback_years}"
        assert result.irr > 0, f"IRR should be positive, got {result.irr}"
        assert result.irr < 500, f"IRR should be realistic, got {result.irr}"
        assert len(result.summary_text) > 0

    def test_calculate_with_zero_benefit_returns_high_payback(self, service):
        """验证零收益场景处理"""
        inp = FinancialInput(
            workspace_id="test-ws-002",
            equipment_capex_min=100.0,
            equipment_capex_max=100.0,
            headcount_reduction=0,
            avg_labor_cost_per_person=0,
            warehouse_area_sqm=0,
            warehouse_cost_per_sqm=0,
            utility_cost_per_sqm=0,
            maintenance_rate=0.02,
            annual_throughput_revenue=0,
            contract_years=5,
            discount_rate=0.08,
        )
        result = service.calculate(inp)

        assert result.payback_years >= 999.0
        assert "无法在合同期内回收" in result.summary_text

    def test_irr_calculation(self, service):
        """验证 IRR 计算（现金流 NPV 验证）

        场景：avg_capex ≈ 500万（含工程+软件），年净收益 ≈ 100万+，5年
        大规模场景，确保 cashflow >> 0，避免牛顿法数值不稳定。

        验证: NPV at computed IRR ≈ 0（核心数学正确性）
        """
        inp = FinancialInput(
            workspace_id="test-irr-001",
            equipment_capex_min=400.0,
            equipment_capex_max=400.0,
            headcount_reduction=30,
            avg_labor_cost_per_person=12.0,
            warehouse_area_sqm=5000,
            warehouse_cost_per_sqm=0.05,  # 250万
            utility_cost_per_sqm=0.02,  # 100万
            maintenance_rate=0.02,  # 400*0.02=8万
            annual_throughput_revenue=400.0,
            contract_years=5,
            discount_rate=0.08,
        )
        # opex_labor=360, warehouse=250, utility=100, maintenance=8 → opex=718
        # revenue=360+400=760, net=42
        result = service.calculate(inp)

        # 验证 net_annual_benefit 为正（否则 IRR 无意义）
        assert result.net_annual_benefit > 0, f"net_annual_benefit should be positive, got {result.net_annual_benefit}"

        # 验证 IRR 数学正确：NPV at computed IRR ≈ 0
        rate = result.irr / 100.0
        avg_capex = (result.capex_total_min + result.capex_total_max) / 2
        cashflows = [-avg_capex] + [result.net_annual_benefit] * inp.contract_years
        npv_at_irr = sum(cf / (1 + rate) ** t for t, cf in enumerate(cashflows))
        # NPV at IRR 应该非常接近 0（允许误差 < 1万）
        assert abs(npv_at_irr) < 1.0, f"NPV at IRR should be ~0, got {npv_at_irr:.4f}"

    def test_cashflow_years_correct(self, service):
        """验证现金流量表正确（含首年CAPEX投入）"""
        inp = FinancialInput(
            workspace_id="test-cf-001",
            equipment_capex_min=100.0,
            equipment_capex_max=100.0,
            headcount_reduction=20,
            avg_labor_cost_per_person=10.0,
            warehouse_area_sqm=2000,
            warehouse_cost_per_sqm=0.05,
            utility_cost_per_sqm=0.01,
            maintenance_rate=0.02,
            annual_throughput_revenue=200.0,
            contract_years=5,
            discount_rate=0.08,
        )
        # opex_labor=200, warehouse=100, utility=20, maintenance=2 → opex_total=322
        # revenue=200+200=400, net=78
        result = service.calculate(inp)

        assert len(result.cashflow_years) == 5
        avg_capex = (result.capex_total_min + result.capex_total_max) / 2
        # Year 1 = -CAPEX + net_benefit
        assert result.cashflow_years[0] == pytest.approx(-avg_capex + result.net_annual_benefit, abs=0.01)
        # Years 2-5 = net_benefit (all equal)
        assert result.cashflow_years[1] == result.cashflow_years[2] == result.cashflow_years[3] == result.cashflow_years[4]
        assert result.cashflow_years[1] == pytest.approx(result.net_annual_benefit, abs=0.01)

    def test_summary_text_generated(self, service):
        """验证摘要文本非空"""
        inp = FinancialInput(
            workspace_id="test-summary-001",
            equipment_capex_min=200.0,
            equipment_capex_max=250.0,
            headcount_reduction=15,
            avg_labor_cost_per_person=12.0,
            warehouse_area_sqm=2000,
            warehouse_cost_per_sqm=0.05,
            utility_cost_per_sqm=0.02,
            maintenance_rate=0.02,
            annual_throughput_revenue=150.0,
            contract_years=5,
            discount_rate=0.08,
        )
        # opex = 180+100+40+4.5=324.5, revenue=180+150=330, net=5.5
        result = service.calculate(inp)

        assert result.summary_text != ""
        assert len(result.summary_text) > 10


class TestFinancialServiceSnapshot:
    def test_save_snapshot_persists(self, service):
        """验证快照保存到数据库"""
        from backend.models.database import engine, Base

        Base.metadata.create_all(bind=engine)

        inp = FinancialInput(
            workspace_id="test-snapshot-001",
            equipment_capex_min=200.0,
            equipment_capex_max=250.0,
            headcount_reduction=20,
            avg_labor_cost_per_person=12.0,
            warehouse_area_sqm=3000,
            warehouse_cost_per_sqm=0.05,
            utility_cost_per_sqm=0.02,
            maintenance_rate=0.02,
            annual_throughput_revenue=300.0,
            contract_years=5,
            discount_rate=0.08,
        )
        result = service.calculate(inp)

        snap = service.save_snapshot(result, workspace_id="test-snapshot-001", snapshot_version=1)

        assert snap.id is not None
        assert snap.workspace_id == "test-snapshot-001"
        assert snap.roi_5y == result.roi_5y
        assert snap.payback_years == result.payback_years
        assert snap.irr == result.irr
        assert snap.cashflow_y1 == result.cashflow_years[0]
