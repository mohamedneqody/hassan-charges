"""What-if sensitivity analysis — deterministic, Python-only.

Replays the P&L under simple shocks and recomputes the headline ratios.
Balance-sheet items are held FIXED (a revenue shock does not instantly change
assets/equity) — every scenario states its assumptions in the UI captions,
and nothing is ever invented: a scenario that lacks its inputs degrades to an
honest N/A row.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.analysis.calculator import YearMetrics, safe_div


@dataclass
class Scenario:
    name: str
    assumption: str
    revenue: float | None
    net_income: float | None
    net_margin_pct: float | None
    roe_pct: float | None
    roa_pct: float | None


def _scale_curr(curr: YearMetrics, rev_f: float = 1.0, cogs_f: float = 1.0,
                opex_f: float = 1.0) -> tuple:
    """(revenue, net_income) under proportional shocks with everything else
    fixed: NI = GP' − |opex'| − |interest'| − |tax'|, each recomputed when its
    inputs exist; falls back to the printed NI scaled by the margin path."""
    rev = curr.revenue * rev_f if curr.revenue is not None else None
    cogs = abs(curr.cost_of_revenue) * cogs_f if curr.cost_of_revenue is not None else None
    gp = rev - cogs if (rev is not None and cogs is not None) else None
    opex = abs(curr.operating_expenses) * opex_f if curr.operating_expenses is not None else None
    oi = gp - opex if (gp is not None and opex is not None) else None
    ni = None
    if oi is not None:
        # pretax' = OI' + non-operating gap (other income / financing costs —
        # held fixed from the printed statements)
        if curr.pretax_income is not None and curr.operating_income:
            pretax = oi + (curr.pretax_income - curr.operating_income)
        else:
            pretax = oi
        ni = pretax
        if curr.income_tax_expense is not None and curr.pretax_income:
            rate = abs(curr.income_tax_expense) / curr.pretax_income
            ni -= abs(ni) * rate if ni > 0 else 0.0
    return rev, ni


def _ratios(ni: float | None, revenue: float | None, curr: YearMetrics) -> tuple:
    margin = safe_div(ni, revenue) * 100 if (ni is not None and revenue) else None
    roe = safe_div(ni, curr.equity) * 100 if (ni is not None and curr.equity) else None
    roa = safe_div(ni, curr.total_assets) * 100 if (ni is not None and curr.total_assets) else None
    return margin, roe, roa


def whatif_analysis(curr: YearMetrics) -> list[Scenario]:
    """Baseline + shock scenarios on the current year."""
    out: list[Scenario] = []

    rev0, ni0 = curr.revenue, curr.net_income
    m, e, a = _ratios(ni0, rev0, curr)
    out.append(Scenario("خط الأساس", "الأرقام كما وردت في الملف", rev0, ni0, m, e, a))

    for label, f, assump in (
        ("إيرادات −20%", 0.80, "التكاليف ثابتة"),
        ("إيرادات −10%", 0.90, "التكاليف ثابتة"),
        ("إيرادات +10%", 1.10, "التكاليف ثابتة"),
        ("إيرادات +20%", 1.20, "التكاليف ثابتة"),
    ):
        rev, ni = _scale_curr(curr, rev_f=f)
        m, e, a = _ratios(ni, rev, curr)
        out.append(Scenario(label, assump, rev, ni, m, e, a))

    # margin squeeze: costs rise faster than prices can follow
    for label, cf, of in (("تكلفة الإيرادات +10%", 1.10, 1.0), ("المصاريف التشغيلية +10%", 1.0, 1.10)):
        rev, ni = _scale_curr(curr, cogs_f=cf, opex_f=of)
        m, e, a = _ratios(ni, curr.revenue, curr)
        out.append(Scenario(label, "الإيرادات ثابتة", rev, ni, m, e, a))

    return out
