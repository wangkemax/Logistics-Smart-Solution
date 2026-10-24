"""backend/services/financial_service.py — v1.2 Financial Modeler"""
from __future__ import annotations
from backend.schemas.financial_schemas import FinancialInput, FinancialResult
from backend.models.financial_models import FinancialSnapshot
from backend.models.database import SessionLocal
from backend.services.financial_core import (
    irr_percent,
    npv,
    payback_years,
    project_cashflows,
    roi_multiple,
)


class FinancialService:
    """
    财务模型服务。
    职责：输入设备 CAPEX + 假设参数 → 输出 ROI/IRR/Payback/现金流量表
    """

    def calculate(self, inp: FinancialInput) -> FinancialResult:
        """
        核心计算逻辑：
        1. CAPEX 汇总：equipment + 10%工程 + 5%软件
        2. OPEX 计算：人力节省、仓储、水电、维保
        3. 年净收益 = 总收益 - OPEX
        4. 5年ROI = (5年净收益总和 - CAPEX) / CAPEX × 100%
        5. Payback = CAPEX / 年净收益
        6. IRR = 使得 NPV=0 的折现率（简化：用二次方程近似）
        7. 现金流量表：每年 [CAPEX投入, 运营收益]
        """
        # 1. CAPEX 汇总
        engineering_fee_min = inp.equipment_capex_min * 0.10
        engineering_fee_max = inp.equipment_capex_max * 0.10
        software_fee_min = inp.equipment_capex_min * 0.05
        software_fee_max = inp.equipment_capex_max * 0.05

        capex_total_min = inp.equipment_capex_min + engineering_fee_min + software_fee_min
        capex_total_max = inp.equipment_capex_max + engineering_fee_max + software_fee_max

        # 人力只作为收益。租金列示，不进入净收益，避免把存量租金当成自动化成本。
        revenue_labor_saving = inp.headcount_reduction * inp.avg_labor_cost_per_person
        opex_labor = 0.0
        opex_warehouse = inp.warehouse_area_sqm * inp.warehouse_cost_per_sqm
        opex_utility = inp.warehouse_area_sqm * inp.utility_cost_per_sqm
        avg_equipment = (inp.equipment_capex_min + inp.equipment_capex_max) / 2
        opex_maintenance = avg_equipment * inp.maintenance_rate
        opex_total = opex_utility + opex_maintenance

        revenue_throughput_improvement = inp.annual_throughput_revenue
        revenue_total = revenue_labor_saving + revenue_throughput_improvement
        net_annual_benefit = revenue_total - opex_total

        avg_capex = (capex_total_min + capex_total_max) / 2
        years = inp.contract_years
        payback = payback_years(avg_capex, net_annual_benefit)
        roi = roi_multiple(net_annual_benefit, avg_capex, years)
        cashflow_years = project_cashflows(avg_capex, net_annual_benefit, years)
        irr_pct = irr_percent(cashflow_years)
        npv_value = round(npv(cashflow_years, inp.discount_rate), 2)

        summary_text = self._generate_summary(
            roi_multiple_value=roi,
            payback=payback,
            irr_percent_value=irr_pct,
            capex_total=avg_capex,
            net_annual_benefit=net_annual_benefit,
            years=years,
        )

        return FinancialResult(
            workspace_id=inp.workspace_id,
            snapshot_version=1,
            equipment_capex_min=inp.equipment_capex_min,
            equipment_capex_max=inp.equipment_capex_max,
            capex_total_min=capex_total_min,
            capex_total_max=capex_total_max,
            opex_labor=round(opex_labor, 2),
            opex_warehouse=round(opex_warehouse, 2),
            opex_utility=round(opex_utility, 2),
            opex_maintenance=round(opex_maintenance, 2),
            opex_other=0,
            opex_total=round(opex_total, 2),
            revenue_labor_saving=round(revenue_labor_saving, 2),
            revenue_throughput_improvement=round(revenue_throughput_improvement, 2),
            revenue_total=round(revenue_total, 2),
            net_annual_benefit=round(net_annual_benefit, 2),
            roi_5y=roi,
            payback_years=payback,
            irr=irr_pct,
            npv=npv_value,
            discount_rate=inp.discount_rate,
            contract_years=years,
            cashflow_years=cashflow_years,
            summary_text=summary_text,
        )

    def _generate_summary(
        self,
        roi_multiple_value: float,
        payback: float | None,
        irr_percent_value: float | None,
        capex_total: float,
        net_annual_benefit: float,
        years: int,
    ) -> str:
        """摘要金额按万元显示，ROI 用倍数。"""
        capex_wan = capex_total / 10000
        net_wan = net_annual_benefit / 10000
        if payback is None:
            return (
                f"本方案总投资约{capex_wan:.1f}万元，"
                f"年净收益约{net_wan:.1f}万元。"
                "投资无法在合同期内回收，建议优化方案或重新评估假设。"
            )

        roi_status = "优秀" if roi_multiple_value > 2 else "良好" if roi_multiple_value > 1 else "一般"
        irr_text = f"{irr_percent_value:.1f}%" if irr_percent_value is not None else "无法计算"
        return (
            f"本方案总投资约{capex_wan:.1f}万元，"
            f"年净收益约{net_wan:.1f}万元，"
            f"投资回收期{payback:.1f}年，"
            f"{years}年ROI {roi_multiple_value:.1f}x，"
            f"内部收益率{irr_text}，"
            f"整体{roi_status}。"
        )

    def save_snapshot(self, result: FinancialResult, workspace_id: str, snapshot_version: int) -> FinancialSnapshot:
        """保存财务快照到数据库"""
        from backend.db_migrate import apply_migrations
        from backend.models.database import engine
        apply_migrations(engine)
        db = SessionLocal()
        try:
            snap = FinancialSnapshot(
                workspace_id=workspace_id,
                snapshot_version=snapshot_version,
                equipment_capex_min=result.equipment_capex_min,
                equipment_capex_max=result.equipment_capex_max,
                capex_total_min=result.capex_total_min,
                capex_total_max=result.capex_total_max,
                opex_labor=result.opex_labor,
                opex_warehouse=result.opex_warehouse,
                opex_utility=result.opex_utility,
                opex_maintenance=result.opex_maintenance,
                opex_other=result.opex_other,
                opex_total=result.opex_total,
                revenue_labor_saving=result.revenue_labor_saving,
                revenue_throughput_improvement=result.revenue_throughput_improvement,
                revenue_total=result.revenue_total,
                net_annual_benefit=result.net_annual_benefit,
                roi_5y=result.roi_5y,
                payback_years=result.payback_years,
                irr=result.irr,
                npv=result.npv,
                contract_years=result.contract_years,
                discount_rate=result.discount_rate,
                cashflow_y1=result.cashflow_years[0] if len(result.cashflow_years) > 0 else 0,
                cashflow_y2=result.cashflow_years[1] if len(result.cashflow_years) > 1 else 0,
                cashflow_y3=result.cashflow_years[2] if len(result.cashflow_years) > 2 else 0,
                cashflow_y4=result.cashflow_years[3] if len(result.cashflow_years) > 3 else 0,
                cashflow_y5=result.cashflow_years[4] if len(result.cashflow_years) > 4 else 0,
            )
            db.add(snap)
            db.commit()
            db.refresh(snap)
            return snap
        finally:
            db.close()
