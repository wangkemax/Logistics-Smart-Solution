"""One cash-flow path for pipeline, /api/cost, /api/compare, and /financial/calculate.

Money is yuan. ROI is an undiscounted multiple: cumulative net benefit / CAPEX.
IRR is a percent, or None when the series does not change sign or will not converge.
The returned cash-flow list is [-capex] + [net] * years and is the series used
for IRR, NPV, and the table.
"""
from __future__ import annotations


def project_cashflows(capex: float, net_annual: float, years: int) -> list[float]:
    n = max(0, int(years))
    return [round(-float(capex), 2)] + [round(float(net_annual), 2)] * n


def npv(cashflows: list[float], discount_rate: float) -> float:
    rate = float(discount_rate)
    if rate <= -0.999999:
        return float("nan")
    total = 0.0
    for t, cf in enumerate(cashflows):
        total += cf / (1.0 + rate) ** t
    return total


def irr(cashflows: list[float]) -> float | None:
    """IRR as a decimal rate. None if non-recoverable or non-converging."""
    if len(cashflows) < 2:
        return None
    if all(cf >= 0 for cf in cashflows) or all(cf <= 0 for cf in cashflows):
        return None

    def f(rate: float) -> float:
        return sum(cf / (1.0 + rate) ** t for t, cf in enumerate(cashflows))

    lo, hi = -0.9, 1.0
    flo, fhi = f(lo), f(hi)
    for _ in range(40):
        if flo == 0:
            return lo
        if fhi == 0:
            return hi
        if flo * fhi < 0:
            break
        hi = hi * 2 if hi > 0 else 1.0
        if hi > 1e6:
            return None
        fhi = f(hi)
    else:
        return None
    if flo * fhi > 0:
        return None

    for _ in range(80):
        mid = (lo + hi) / 2.0
        fm = f(mid)
        if abs(fm) < 1e-6 or abs(hi - lo) < 1e-10:
            return mid
        if flo * fm <= 0:
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm
    return None


def irr_percent(cashflows: list[float]) -> float | None:
    rate = irr(cashflows)
    if rate is None:
        return None
    return round(rate * 100.0, 1)


def roi_multiple(net_annual: float, capex: float, years: int) -> float:
    """Undiscounted multiple: (net * years) / capex. Not a percentage."""
    if capex <= 0:
        return 0.0
    return round(float(net_annual) * int(years) / float(capex), 2)


def payback_years(capex: float, net_annual: float) -> float | None:
    if capex <= 0 or net_annual <= 0:
        return None
    return round(float(capex) / float(net_annual), 1)


def baseline_headcount(
    daily_orders: int,
    orders_per_person: int = 150,
    overhead: float = 1.3,
) -> int:
    if not daily_orders or daily_orders <= 0:
        return 1
    picking = max(1, int(daily_orders / orders_per_person))
    return max(1, int(picking * overhead))


def automation_economics(
    daily_orders: int,
    labor_cost_per_person: float,
    labor_saving_rate: float,
    capex: float,
    maintenance_rate: float,
    years: int = 5,
    discount_rate: float = 0.08,
) -> dict:
    """Labor benefit is headcount saved times salary. Maintenance is the incremental opex.

    Warehouse rent is not part of this net benefit. Efficiency is not added again
    on top of labor_saving_rate.
    """
    baseline = baseline_headcount(int(daily_orders or 0))
    saved = int(round(baseline * max(0.0, float(labor_saving_rate))))
    saved = min(saved, baseline)
    labor = saved * float(labor_cost_per_person)
    maintenance = float(capex) * float(maintenance_rate)
    net = labor - maintenance
    flows = project_cashflows(capex, net, years)
    return {
        "baseline_headcount": baseline,
        "headcount_saved": saved,
        "headcount_required": max(0, baseline - saved),
        "annual_labor_saving": round(labor, 2),
        "annual_maintenance": round(maintenance, 2),
        "annual_efficiency_saving": 0.0,
        "net_annual_benefit": round(net, 2),
        "roi": roi_multiple(net, capex, years),
        "payback_years": payback_years(capex, net),
        "cashflows": flows,
        "irr_percent": irr_percent(flows),
        "npv": round(npv(flows, discount_rate), 2),
    }
