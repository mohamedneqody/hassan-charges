"""Advanced deterministic analysis: DuPont decomposition + Altman Z''-score.

Everything here is computed in Python from YearMetrics — no AI involved.
Both tools degrade to explicit N/A with a missing-components list when the
source file lacks a required line item (same honest-missing philosophy as
the rest of the system).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.analysis.calculator import YearMetrics, safe_div


# ---------------------------------------------------------------------------
# DuPont: ROE = Net Margin × Asset Turnover × Financial Leverage
# ---------------------------------------------------------------------------

@dataclass
class DuPont:
    net_margin_pct: float | None = None      # NI / Revenue (×100)
    asset_turnover: float | None = None      # Revenue / average assets
    equity_multiplier: float | None = None   # average assets / average equity
    implied_roe_pct: float | None = None     # product of the three
    direct_roe_pct: float | None = None      # NI / average equity (cross-check)
    reconciles: bool | None = None           # |implied − direct| within 0.5pp
    missing: list[str] = field(default_factory=list)


def dupont_analysis(curr: YearMetrics, prev: YearMetrics | None = None) -> DuPont:
    """3-factor DuPont on the current year (average balances, consistent with
    the calculator's ROE definition)."""

    def avg_of(field_name: str) -> float | None:
        cur = getattr(curr, field_name, None)
        pv = getattr(prev, field_name, None) if prev is not None else None
        if cur is None:
            return None
        return (pv + cur) / 2 if pv is not None else cur

    avg_assets = avg_of("total_assets")
    avg_equity = avg_of("equity")

    missing = []
    if curr.revenue is None:
        missing.append("revenue")
    if curr.net_income is None:
        missing.append("net_income")
    if avg_assets is None:
        missing.append("total_assets (two-year average)")
    if avg_equity is None:
        missing.append("equity (two-year average)")

    d = DuPont(missing=missing)
    if missing:
        return d

    d.net_margin_pct = safe_div(curr.net_income, curr.revenue) * 100
    d.asset_turnover = safe_div(curr.revenue, avg_assets)
    d.equity_multiplier = safe_div(avg_assets, avg_equity)
    d.direct_roe_pct = safe_div(curr.net_income, avg_equity) * 100
    if None not in (d.net_margin_pct, d.asset_turnover, d.equity_multiplier):
        d.implied_roe_pct = (d.net_margin_pct / 100) * d.asset_turnover * d.equity_multiplier * 100
    if None not in (d.implied_roe_pct, d.direct_roe_pct):
        d.reconciles = abs(d.implied_roe_pct - d.direct_roe_pct) <= 0.5
    return d


# ---------------------------------------------------------------------------
# Altman Z''-score (emerging-markets / non-manufacturer variant)
# Z'' = 6.56·(WC/TA) + 3.26·(RE/TA) + 6.72·(EBIT/TA) + 1.05·(Book Equity/TL)
# Zones (Altman 2012): > 2.6 safe · 1.1–2.6 grey · < 1.1 distress
# ---------------------------------------------------------------------------

@dataclass
class AltmanZ:
    score: float | None = None
    zone: str = ""            # "safe" | "grey" | "distress"
    components: list[tuple[str, float | None]] = field(default_factory=list)  # (label, part)
    missing: list[str] = field(default_factory=list)

    @property
    def zone_ar(self) -> str:
        return {"safe": "منطقة أمان", "grey": "منطقة رمادية", "distress": "منطقة ضيق"}.get(self.zone, "")


def altman_z(curr: YearMetrics) -> AltmanZ:
    z = AltmanZ()
    ta = curr.total_assets
    ebit = curr.operating_income

    missing = []
    if ta is None:
        missing.append("total_assets")
    if curr.current_assets is None or curr.current_liabilities is None:
        missing.append("current_assets / current_liabilities")
    if curr.retained_earnings is None:
        missing.append("retained_earnings (أرباح مرحلة)")
    if ebit is None:
        missing.append("operating_income (EBIT)")
    if curr.equity is None:
        missing.append("equity")
    if curr.total_liabilities is None:
        missing.append("total_liabilities")
    if missing:
        z.missing = missing
        return z

    wc = curr.current_assets - curr.current_liabilities
    parts = [
        ("رأس المال العامل ÷ إجمالي الأصول × 6.56", 6.56 * safe_div(wc, ta)),
        ("الأرباح المرحلة ÷ إجمالي الأصول × 3.26", 3.26 * safe_div(curr.retained_earnings, ta)),
        ("الربح التشغيلي (EBIT) ÷ إجمالي الأصول × 6.72", 6.72 * safe_div(ebit, ta)),
        ("حقوق الملكية ÷ إجمالي الالتزامات × 1.05", 1.05 * safe_div(curr.equity, curr.total_liabilities)),
    ]
    z.components = parts
    if any(p is None for _, p in parts):
        z.missing = ["one or more components divided by zero"]
        return z
    z.score = sum(p for _, p in parts)  # type: ignore[arg-type]
    z.zone = "safe" if z.score > 2.6 else ("distress" if z.score < 1.1 else "grey")
    return z
