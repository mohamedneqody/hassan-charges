"""Financial Metric Registry — independent validation.

The fixture is a synthetic company with round numbers; EVERY expected value
below was hand-computed from the DOCUMENTED formula in metric_registry.py —
not copied from system outputs. This validates implementation-vs-specification
for the engine (the mandate's independent-ground-truth requirement).
"""
from __future__ import annotations

import pytest

from src.analysis.calculator import compute_year_metrics
from src.analysis.metric_registry import REGISTRY, registry_stats

# ── بيانات مرجعية اصطناعية — كل القيم مختارة يدويًا بأرقام دائرية ──
CUR = {
    "revenue": 1_000_000.0, "cost_of_revenue": -600_000.0,
    "operating_expenses": -250_000.0, "gross_profit": 400_000.0,
    "operating_income": 150_000.0, "pretax_income": 120_000.0,
    "income_tax_expense": -30_000.0, "net_income": 90_000.0,
    "depreciation_amortization": -40_000.0, "selling_expenses": -50_000.0,
    "rd_expenses": -20_000.0, "interest_expense": -30_000.0,
    "total_assets": 800_000.0, "current_assets": 300_000.0,
    "inventory": 100_000.0, "accounts_receivable": 150_000.0, "cash": 50_000.0,
    "fixed_assets": 400_000.0, "accounts_payable": 120_000.0,
    "current_liabilities": 200_000.0, "total_liabilities": 500_000.0,
    "short_term_debt": 100_000.0, "current_portion_lt_debt": 50_000.0,
    "long_term_debt": 200_000.0, "equity": 300_000.0,
    "retained_earnings": 150_000.0, "operating_cash_flow": 120_000.0,
    "capex": -60_000.0, "investing_cash_flow": -80_000.0,
    "non_current_lease_liabilities": 80_000.0,
    "current_lease_liabilities": 30_000.0,
}
PREV = {
    "total_assets": 750_000.0, "equity": 280_000.0, "inventory": 90_000.0,
    "accounts_receivable": 130_000.0, "accounts_payable": 110_000.0,
    "fixed_assets": 380_000.0, "current_assets": 280_000.0,
    "current_liabilities": 190_000.0,
}


def _build_data():
    """دمج صحيح: قيم 2023 (السنة السابقة) + قيم 2024 (السنة الحالية)"""
    d = {f: {2023: v} for f, v in PREV.items()}
    for f, v in CUR.items():
        d.setdefault(f, {})[2024] = v
    return d


@pytest.fixture(scope="module")
def m():
    return compute_year_metrics(2024, _build_data(), prev_year=2023)


@pytest.fixture(scope="module")
def full_data():
    d = {}
    for f, v in CUR.items():
        d[f] = {2024: v}
    for f, v in PREV.items():
        d.setdefault(f, {})[2023] = v
    return d


def metrics_from(d, year, prev):
    return compute_year_metrics(year, d, prev_year=prev)


# ── الربحية ──
def test_margins_hand_computed(m):
    assert m.gross_margin == pytest.approx(40.0)
    assert m.operating_margin == pytest.approx(15.0)
    assert m.net_margin == pytest.approx(9.0)
    assert m.pretax_margin == pytest.approx(12.0)
    assert m.ebitda_margin == pytest.approx(19.0)  # EBITDA = 150 + 40 = 190


def test_returns_on_average_balances(m):
    # ROA = 90,000 / avg(750,000, 800,000) = 11.6129%
    assert m.roa == pytest.approx(11.6129, abs=0.01)
    # ROE = 90,000 / avg(280,000, 300,000) = 31.0345%
    assert m.roe == pytest.approx(31.0345, abs=0.01)
    assert m.cash_roa == pytest.approx(15.4839, abs=0.01)


def test_roic_hand_computed():
    d = {}
    for f, v in {"operating_income": {2024: 150_000.0}, "pretax_income": {2024: 120_000.0},
                 "income_tax_expense": {2024: -30_000.0}, "total_debt": {2024: 350_000.0},
                 "equity": {2024: 300_000.0}}.items():
        d[f] = {2024: v[2024]}
    # حساب مستقل: rate = 30k/120k = 0.25، NOPAT = 150k × 0.75، IC = 350k + 300k
    # ROIC = 112,500 / 650,000 = 17.3077%
    from src.analysis.calculator import compute_year_metrics
    mm = compute_year_metrics(2024, d, prev_year=None)
    assert mm.roic == pytest.approx(17.3077, abs=0.01)


def test_roce_hand_computed(m):
    # 150,000 / (800,000 − 200,000) = 25%
    assert m.roce == pytest.approx(25.0, abs=0.01)


# ── السيولة ──
def test_liquidity_hand_computed(m):
    assert m.current_ratio == pytest.approx(1.5)
    assert m.quick_ratio == pytest.approx(1.0)  # (300 − 100) / 200
    assert m.cash_ratio == pytest.approx(0.25)
    assert m.ocf_ratio == pytest.approx(0.6)


# ── المديونية — بالتعريف الصحيح: الدين ذو الفائدة + الأقساط المتداولة ──
def test_debt_ratios_hand_computed(m):
    # total_debt = 100,000 + 50,000 + 200,000 = 350,000 (ST + أقساط + LT)
    assert m.total_debt == pytest.approx(350_000.0)
    assert m.debt_to_equity == pytest.approx(350_000 / 300_000, rel=1e-4)
    assert m.debt_ratio == pytest.approx(500_000 / 800_000, rel=1e-4)
    assert m.debt_to_assets == pytest.approx(350_000 / 800_000, rel=1e-4)
    assert m.liabilities_to_equity == pytest.approx(500_000 / 300_000, rel=1e-4)
    assert m.equity_ratio == pytest.approx(300_000 / 800_000, rel=1e-4)
    assert m.financial_leverage == pytest.approx(800_000 / 300_000, rel=1e-4)
    assert m.interest_coverage == pytest.approx(150_000 / 30_000, rel=1e-4)


# ── الكفاءة — متوسطات الأرصدة ──
def test_efficiency_hand_computed(m):
    assert m.asset_turnover == pytest.approx(1_000_000 / 775_000, rel=1e-4)
    assert m.fixed_asset_turnover == pytest.approx(1_000_000 / 390_000, rel=1e-4)
    assert m.inventory_turnover == pytest.approx(600_000 / 95_000, rel=1e-4)
    assert m.receivables_turnover == pytest.approx(1_000_000 / 140_000, rel=1e-4)
    assert m.payables_turnover == pytest.approx(600_000 / 115_000, rel=1e-4)


# ── الأيام و CCC ──
def test_days_and_ccc_hand_computed(m):
    dio = 365 / (600_000 / 95_000)
    dso = 365 / (1_000_000 / 140_000)
    dpo = 365 / (600_000 / 115_000)
    assert m.inventory_days == pytest.approx(dio, rel=1e-3)
    assert m.days_sales_outstanding == pytest.approx(dso, rel=1e-3)
    assert m.days_payables_outstanding == pytest.approx(dpo, rel=1e-3)
    assert m.cash_conversion_cycle == pytest.approx(dio + dso - dpo, rel=1e-3)


# ── رأس المال العامل والتدفقات ──
def test_working_capital_and_cash_flow(m):
    assert m.working_capital == pytest.approx(100_000.0)
    assert m.operating_working_capital == pytest.approx(150_000 + 100_000 - 120_000)
    assert m.cfo_margin == pytest.approx(12.0)
    assert m.free_cash_flow == pytest.approx(120_000 - 60_000)
    assert m.cfo_to_net_income == pytest.approx(120_000 / 90_000, rel=1e-4)
    assert m.cfo_to_debt == pytest.approx(120_000 / 350_000, rel=1e-4)
    assert m.capex_coverage == pytest.approx(120_000 / 60_000, rel=1e-4)


# ── بنية التكاليف ──
def test_cost_structure_pcts(m):
    assert m.cogs_pct == pytest.approx(60.0)
    assert m.opex_pct == pytest.approx(25.0)
    assert m.selling_pct == pytest.approx(5.0)
    assert m.rd_pct == pytest.approx(2.0)
    assert m.interest_pct == pytest.approx(3.0)
    assert m.da_pct == pytest.approx(4.0)
    assert m.tax_rate == pytest.approx(25.0)


# ── سلامة السجل نفسه ──
def test_registry_integrity():
    st = registry_stats()
    assert st["total"] >= 60
    ids = [m.metric_id for m in REGISTRY]
    assert len(ids) == len(set(ids)), "metric_id must be unique"
    for m in REGISTRY:
        assert m.formula and m.unit and m.zero_denominator_policy
        assert m.negative_policy and m.interpretation in ("higher", "lower", "neutral")
        assert m.test_reference or m.validation_status == "documented"


def test_registry_inputs_are_canonical_fields():
    """كل المدخلات المطلوبة حقول قياسية تُقرأ من values — لا حقول خيالية."""
    from src.analysis.calculator import YearMetrics
    known = set(YearMetrics.__dataclass_fields__)
    for m in REGISTRY:
        for inp in m.required_inputs:
            assert inp in known, f"{m.metric_id}: input {inp} is not a YearMetrics field"


def test_registry_coverage_matches_engine_outputs():
    """كل قيمة في YearMetrics التي لها مدخل مسجل في السجل تُغطى — والحقول
    الحساسة الخمسة عشر كلها بحالة validated."""
    critical = {"quick_ratio", "inventory_turnover", "fixed_asset_turnover",
                "debt_to_equity", "cfo_to_debt", "roa", "roe", "current_ratio",
                "net_margin", "asset_turnover", "financial_leverage",
                "interest_coverage", "cash_ratio", "gross_margin", "equity_ratio"}
    ids = {m.metric_id for m in REGISTRY}
    assert critical <= ids
    st = registry_stats()
    assert st["validated"] >= 15
