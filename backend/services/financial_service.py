"""backend/services/financial_service.py — v1.2 Financial Modeler"""
from __future__ import annotations
from backend.schemas.financial_schemas import FinancialInput, FinancialResult
from backend.models.financial_models import FinancialSnapshot
from backend.models.database import SessionLocal


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

        # 2. OPEX 计算
        opex_labor = inp.headcount_reduction * inp.avg_labor_cost_per_person
        opex_warehouse = inp.warehouse_area_sqm * inp.warehouse_cost_per_sqm
        opex_utility = inp.warehouse_area_sqm * inp.utility_cost_per_sqm
        opex_maintenance = (inp.equipment_capex_min + inp.equipment_capex_max) / 2 * inp.maintenance_rate
        opex_total = opex_labor + opex_warehouse + opex_utility + opex_maintenance

        # 3. 收益
        revenue_labor_saving = opex_labor  # 人力节省 = OPEX人力减少
        revenue_throughput_improvement = inp.annual_throughput_revenue
        revenue_total = revenue_labor_saving + revenue_throughput_improvement

        # 4. 年净收益
        net_annual_benefit = revenue_total - opex_total

        # 5. Payback（年）
        avg_capex = (capex_total_min + capex_total_max) / 2
        if net_annual_benefit > 0:
            payback_years = avg_capex / net_annual_benefit
        else:
            payback_years = 999.0  # 无法回收

        # 6. 5年ROI
        total_net_benefit_5y = net_annual_benefit * inp.contract_years
        roi_5y = (total_net_benefit_5y - avg_capex) / avg_capex * 100 if avg_capex > 0 else 0

        # 7. IRR（简化算法：牛顿法迭代）
        irr = self._calculate_irr(
            cashflows=[-avg_capex] + [net_annual_benefit] * inp.contract_years,
            guess=0.1,
        )

        # 8. 现金流量表
        cashflow_years = []
        for year in range(1, inp.contract_years + 1):
            if year == 1:
                cf = -avg_capex + net_annual_benefit  # 首年含CAPEX
            else:
                cf = net_annual_benefit
            cashflow_years.append(round(cf, 2))

        # 9. 生成摘要文本
        summary_text = self._generate_summary(
            roi_5y=roi_5y,
            payback_years=payback_years,
            irr=irr,
            capex_total=avg_capex,
            net_annual_benefit=net_annual_benefit,
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
            roi_5y=round(roi_5y, 1),
            payback_years=round(payback_years, 1),
            irr=round(irr * 100, 1),  # 转为百分比
            cashflow_years=cashflow_years,
            summary_text=summary_text,
        )

    def _calculate_irr(self, cashflows: list[float], guess: float = 0.1, tolerance: float = 1e-6, max_iter: int = 1000) -> float:
        """
        简化 IRR 计算：牛顿法迭代。
        找到使 NPV=0 的折现率。
        """
        rate = guess
        for _ in range(max_iter):
            npv = sum(cf / (1 + rate) ** t for t, cf in enumerate(cashflows))
            d_npv = sum(-t * cf / (1 + rate) ** (t + 1) for t, cf in enumerate(cashflows))
            if abs(d_npv) < 1e-12:
                break
            rate_new = rate - npv / d_npv
            if abs(rate_new - rate) < tolerance:
                return rate_new
            rate = rate_new
        return rate

    def _generate_summary(
        self,
        roi_5y: float,
        payback_years: float,
        irr: float,
        capex_total: float,
        net_annual_benefit: float,
    ) -> str:
        """生成 LLM 可读的财务摘要"""
        if payback_years >= 999:
            return "投资无法在合同期内回收，建议优化方案或重新评估假设。"

        roi_status = "优秀" if roi_5y > 100 else "良好" if roi_5y > 50 else "一般"

        return (
            f"本方案总投资约{capex_total:.0f}万元，"
            f"年净收益约{net_annual_benefit:.0f}万元，"
            f"投资回收期{payback_years:.1f}年，"
            f"5年ROI{roi_5y:.0f}%，"
            f"内部收益率{irr * 100:.1f}%，"
            f"整体{roi_status}。"
        )

    def save_snapshot(self, result: FinancialResult, workspace_id: str, snapshot_version: int) -> FinancialSnapshot:
        """保存财务快照到数据库"""
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
