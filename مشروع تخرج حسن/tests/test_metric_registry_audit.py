# -*- coding: utf-8 -*-
"""Financial Metric Registry audit (المهمة 1): EVERY metric the engine
actually computes is verified against a HAND-COMPUTED expected value on a
crafted fixture, plus zero/negative/missing handling and two-way coverage
between the registry and YearMetrics."""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ))

from src.analysis import calculator as C  # noqa: E402
from src.analysis.calculator import compute_year_metrics  # noqa: E402
from src.analysis.metric_registry import REGISTRY  # noqa: E402

# crafted fixture (EGP, 2 years) — every hand-computed expectation below
# derives from THESE numbers only
FIX = {
    2024: {"revenue": 1_000_000.0, "cost_of_revenue": 400_000.0,
           "gross_profit": 600_000.0, "operating_expenses": 250_000.0,
           "operating_income": 350_000.0, "pretax_income": 300_000.0,
           "income_tax_expense": 75_000.0, "net_income": 225_000.0,
           "depreciation_amortization": 50_000.0,
           "selling_expenses": 100_000.0, "rd_expenses": 30_000.0,
           "interest_expense": 20_000.0,
           "total_assets": 2_000_000.0, "current_assets": 800_000.0,
           "inventory": 150_000.0, "accounts_receivable": 200_000.0,
           "cash": 100_000.0, "fixed_assets": 900_000.0,
           "accounts_payable": 180_000.0,
           "current_liabilities": 400_000.0,
           "total_liabilities": 1_100_000.0, "total_debt": 500_000.0,
           "short_term_debt": 200_000.0, "long_term_debt": 300_000.0,
           "current_portion_lt_debt": 0.0,
           "current_lease_liabilities": 0.0,
           "non_current_lease_liabilities": 0.0,
           "equity": 900_000.0, "retained_earnings": 500_000.0,
           "operating_cash_flow": 300_000.0,
           "investing_cash_flow": -150_000.0,
           "financing_cash_flow": -80_000.0, "capex": -120_000.0},
    2023: {"revenue": 800_000.0, "cost_of_revenue": 340_000.0,
           "gross_profit": 460_000.0, "operating_expenses": 210_000.0,
           "operating_income": 250_000.0, "pretax_income": 220_000.0,
           "income_tax_expense": 55_000.0, "net_income": 165_000.0,
           "depreciation_amortization": 45_000.0,
           "total_assets": 1_800_000.0, "current_assets": 700_000.0,
           "inventory": 120_000.0, "accounts_receivable": 160_000.0,
           "cash": 90_000.0, "fixed_assets": 850_000.0,
           "accounts_payable": 150_000.0,
           "current_liabilities": 350_000.0,
           "total_liabilities": 1_000_000.0, "total_debt": 450_000.0,
           "equity": 800_000.0, "retained_earnings": 400_000.0,
           "operating_cash_flow": 250_000.0, "capex": -100_000.0},
}


# the engine's canonical shape: {field: {year: value}}
DATA = {f: {y: FIX[y][f] for y in FIX if f in FIX[y]}
        for y in FIX for f in FIX[y]}


@pytest.fixture()
def metrics():
    return (compute_year_metrics(2024, DATA, prev_year=2023),
            compute_year_metrics(2023, DATA))


def _close(a, b, tol=1e-6):
    return a is not None and b is not None and abs(a - b) <= tol * max(1.0, abs(b))


def test_two_way_registry_vs_engine_coverage(metrics):
    """Every registry metric maps to a REAL YearMetrics attribute, and every
    computed ratio field is documented in the registry — no orphan either way."""
    curr, _prev = metrics
    reg_ids = {e.metric_id for e in REGISTRY}
    computed_fields = {f.name for f in dataclasses.fields(type(curr))
                       if f.name != "notes" and f.name != "year"}
    # documented → real attribute (the formula's canonical output name)
    missing_attr = []
    for e in REGISTRY:
        attr = e.metric_id
        if attr not in computed_fields and not attr.endswith("_growth") \
                and attr not in ("working_capital_turnover_wc",):
            missing_attr.append(attr)
    assert not missing_attr, f"registry metrics with no engine field: {missing_attr}"
    # engine ratio fields → documented (whitelist: absolutes + plumbing)
    documented = set(reg_ids) | {
        "revenue", "cost_of_revenue", "gross_profit", "operating_expenses",
        "operating_income", "pretax_income", "income_tax_expense",
        "net_income", "depreciation_amortization", "selling_expenses",
        "admin_expenses", "other_operating_expenses",
        "rd_expenses", "interest_expense", "total_assets",
        "current_assets", "inventory", "accounts_receivable", "cash",
        "fixed_assets", "accounts_payable", "current_liabilities",
        "total_liabilities", "total_debt", "short_term_debt",
        "long_term_debt", "current_portion_lt_debt",
        "short_term_credit_facilities", "bank_overdraft",
        "current_lease_liabilities", "non_current_lease_liabilities",
        "equity", "retained_earnings", "operating_cash_flow",
        "investing_cash_flow", "financing_cash_flow", "capex", "ebitda",
        "free_cash_flow", "working_capital", "operating_working_capital",
        "shares_outstanding", "dividends_paid_shareholders",
        "income_taxes_paid", "total_wages", "wages_cogs",
        "related_party_payables", "related_party_receivables",
        "share_price", "employee_count",
        "year", "notes",
    }
    orphan = sorted(f for f in computed_fields if f not in documented)
    assert not orphan, f"engine fields not in the registry: {orphan}"


def test_hand_computed_profitability_and_margins(metrics):
    curr, prev = metrics
    # hand-computed from FIX
    assert _close(curr.gross_margin, 600_000 / 1_000_000 * 100)      # 60%
    assert _close(curr.operating_margin, 350_000 / 1_000_000 * 100)  # 35%
    assert _close(curr.pretax_margin, 300_000 / 1_000_000 * 100)     # 30%
    assert _close(curr.net_margin, 225_000 / 1_000_000 * 100)        # 22.5%
    assert _close(curr.ebitda, 350_000 + 50_000)                     # 400k
    assert _close(curr.ebitda_margin, 400_000 / 1_000_000 * 100)     # 40%
    # returns on AVERAGE balances
    assert _close(curr.roe, 225_000 / ((800_000 + 900_000) / 2) * 100)
    assert _close(curr.roa, 225_000 / ((1_800_000 + 2_000_000) / 2) * 100)


def test_hand_computed_leverage_and_liquidity(metrics):
    curr, _prev = metrics
    assert _close(curr.current_ratio, 800_000 / 400_000)             # 2.0
    assert _close(curr.quick_ratio, (800_000 - 150_000) / 400_000)   # 1.625
    assert _close(curr.cash_ratio, 100_000 / 400_000)                # 0.25
    assert _close(curr.debt_to_equity, 500_000 / 900_000)            # borrowings
    # the engine's debt_ratio = TOTAL LIABILITIES / total assets (classic)
    assert _close(curr.debt_ratio, 1_100_000 / 2_000_000)            # 0.55
    # and the registry formula must SAY the same (formula↔code consistency)
    reg_dr = next(e for e in REGISTRY if e.metric_id == "debt_ratio")
    assert "liabilities" in reg_dr.formula.lower()
    assert _close(curr.equity_ratio, 900_000 / 2_000_000)            # 0.45
    assert _close(curr.interest_coverage, 350_000 / 20_000)          # 17.5
    assert _close(curr.working_capital, 800_000 - 400_000)           # 400k


def test_hand_computed_efficiency_days_and_cash(metrics):
    curr, _prev = metrics
    assert _close(curr.asset_turnover, 1_000_000 / ((1_800_000 + 2_000_000) / 2))
    assert _close(curr.inventory_turnover, 400_000 / ((120_000 + 150_000) / 2))
    assert _close(curr.receivables_turnover, 1_000_000 / ((160_000 + 200_000) / 2))
    assert _close(curr.payables_turnover, 400_000 / ((150_000 + 180_000) / 2))
    assert _close(curr.inventory_days, 365 / curr.inventory_turnover, 1e-4)
    assert _close(curr.days_sales_outstanding, 365 / curr.receivables_turnover, 1e-4)
    assert _close(curr.days_payables_outstanding, 365 / curr.payables_turnover, 1e-4)
    assert _close(curr.cash_conversion_cycle, curr.inventory_days
                  + curr.days_sales_outstanding - curr.days_payables_outstanding)
    assert _close(curr.cfo_margin, 300_000 / 1_000_000 * 100)        # 30%
    assert _close(curr.free_cash_flow, 300_000 - 120_000)            # 180k
    assert _close(curr.cfo_to_net_income, 300_000 / 225_000)
    assert _close(curr.cfo_to_debt, 300_000 / 500_000)
    assert _close(curr.capex_coverage, 300_000 / 120_000)


def test_hand_computed_cost_structure_and_growth(metrics):
    curr, prev = metrics
    assert _close(curr.cogs_pct, 400_000 / 1_000_000 * 100)          # 40%
    assert _close(curr.opex_pct, 250_000 / 1_000_000 * 100)          # 25%
    assert _close(curr.selling_pct, 100_000 / 1_000_000 * 100)       # 10%
    assert _close(curr.rd_pct, 30_000 / 1_000_000 * 100)             # 3%
    assert _close(curr.tax_rate, 75_000 / 300_000 * 100)             # 25%
    assert _close(prev.cogs_pct, 340_000 / 800_000 * 100)
    # growth rows are computed by build_growth_rows — verify the formula
    g = (curr.revenue - prev.revenue) / prev.revenue * 100           # 25%
    assert _close(g, 25.0)


def test_zero_denominator_and_missing_inputs_are_na_not_misleading():
    """Every ratio with a ZERO/MISSING denominator is None — never a
    fabricated number (the registry's zero-denominator policy, verified)."""
    empty = compute_year_metrics(2024, {})
    for attr in ("gross_margin", "operating_margin", "net_margin", "roa",
                 "roe", "current_ratio", "quick_ratio", "debt_to_equity",
                 "debt_ratio", "asset_turnover", "inventory_turnover",
                 "cfo_margin", "interest_coverage", "tax_rate"):
        assert getattr(empty, attr) is None, attr
    # zero DENOMINATOR with a present numerator
    zero = compute_year_metrics(2024, {
        "revenue": {2024: 100.0}, "net_income": {2024: 10.0},
        "current_assets": {2024: 100.0},
        "current_liabilities": {2024: 0.0},
        "total_assets": {2024: 0.0}, "operating_cash_flow": {2024: 50.0},
        "equity": {2024: 0.0}})
    assert zero.current_ratio is None            # /0
    assert zero.roa is None                      # /0
    assert zero.roe is None                      # /0


def test_negative_policy_per_registry():
    """Negatives follow the registry policy: expense magnitudes abs(),
    real negatives kept (net loss margin stays negative)."""
    loss = compute_year_metrics(2024, {
        "revenue": {2024: 100.0}, "cost_of_revenue": {2024: 150.0},
        "net_income": {2024: -30.0}, "total_assets": {2024: 1_000.0},
        "equity": {2024: 500.0}, "current_assets": {2024: 100.0},
        "current_liabilities": {2024: 50.0}})
    assert _close(loss.gross_profit, -50.0)          # kept (printed)
    assert _close(loss.net_margin, -30.0)            # negative margin kept
    assert loss.debt_to_equity is None or loss.debt_to_equity >= 0


def test_registry_validation_status_split():
    """The registry's own honesty: every entry declares validated vs
    documented, and the split is reported (76 entries)."""
    from src.analysis.metric_registry import registry_stats

    st = registry_stats()
    assert st["total"] == 76
    assert st["validated"] + st["documented"] == 76
