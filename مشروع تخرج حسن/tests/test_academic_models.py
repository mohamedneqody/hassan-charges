"""Academic early-warning models: exact arithmetic on known fixtures.

Healthy and distressed companies with hand-computed expected scores, the
DuPont product identity, and the None-safety contract (missing data →
missing list, never a guessed number).
"""
from __future__ import annotations

import pytest

from src.analysis.academic_models import (
    academic_models,
    altman_z_prime,
    dupont_analysis,
    springate_score,
    zmijewski_score,
)
from src.analysis.calculator import YearMetrics


def healthy() -> YearMetrics:
    return YearMetrics(
        year=2024,
        revenue=1_000_000.0,
        operating_income=150_000.0,
        pretax_income=130_000.0,
        net_income=100_000.0,
        total_assets=600_000.0,
        current_assets=300_000.0,
        current_liabilities=150_000.0,
        total_liabilities=320_000.0,
        equity=280_000.0,
        retained_earnings=200_000.0,
        working_capital=150_000.0,
    )


def distressed() -> YearMetrics:
    return YearMetrics(
        year=2024,
        revenue=400_000.0,
        operating_income=10_000.0,
        pretax_income=-20_000.0,
        net_income=-30_000.0,
        total_assets=500_000.0,
        current_assets=150_000.0,
        current_liabilities=200_000.0,
        total_liabilities=450_000.0,
        equity=50_000.0,
        retained_earnings=-50_000.0,
        working_capital=-100_000.0,
    )


def test_altman_healthy_is_safe():
    m = altman_z_prime(healthy())
    assert m.value == pytest.approx(3.269, abs=0.01)
    assert m.zone == "safe"
    assert m.missing == []
    assert m.components["X1"] == pytest.approx(0.25, abs=1e-4)


def test_altman_distressed_is_distress():
    m = altman_z_prime(distressed())
    assert m.value == pytest.approx(0.679, abs=0.01)
    assert m.zone == "distress"


def test_springate_healthy_above_cutoff():
    # Springate (1978): 1.03*A + 3.07*B + 0.66*C + 0.40*D
    m = springate_score(healthy())
    assert m.value == pytest.approx(2.264, abs=0.01)
    assert m.zone == "safe"


def test_springate_distressed_below_cutoff():
    m = springate_score(distressed())
    assert m.value == pytest.approx(0.109, abs=0.01)
    assert m.zone == "distress"


def test_zmijewski_healthy_below_zero():
    # Zmijewski (1984): -4.336 - 4.513*(NI/TA) + 5.679*(TL/TA) + 0.004*(CA/CL)
    m = zmijewski_score(healthy())
    assert m.value == pytest.approx(-2.051, abs=0.01)
    assert "CA/CL" in m.components
    assert m.components["CA/CL"] == pytest.approx(2.0, abs=1e-4)
    assert m.zone == "risk_low"


def test_zmijewski_distressed_above_zero():
    m = zmijewski_score(distressed())
    assert m.value == pytest.approx(1.049, abs=0.01)
    assert m.components["CA/CL"] == pytest.approx(0.75, abs=1e-4)
    assert m.zone == "risk_high"


def test_dupont_product_identity():
    """The three factors must reconstruct ROE = NI / Equity exactly."""
    m = dupont_analysis(healthy())
    rebuilt = m.components["ROE_rebuilt"]
    assert rebuilt == pytest.approx(35.71, abs=0.01)
    direct = healthy().net_income / healthy().equity * 100
    assert rebuilt == pytest.approx(direct, abs=0.01)  # 2-decimal rounding
    assert m.components["AssetTurnover"] == pytest.approx(1.667, abs=0.001)
    assert m.components["EquityMultiplier"] == pytest.approx(2.143, abs=0.001)
    assert m.components["EBITMargin"] == pytest.approx(15.0, abs=0.01)


def test_dupont_leverage_warning_when_debt_driven():
    """High equity multiplier is called out in the verdict."""
    m = dupont_analysis(distressed())
    assert "الرافعة المالية" in m.verdict_ar or "Watch" in m.verdict_en


def test_missing_data_yields_missing_lists_not_guesses():
    sparse = YearMetrics(year=2024, revenue=100.0, net_income=10.0)
    results = academic_models(sparse)
    assert [m.key for m in results] == ["altman", "springate", "zmijewski", "dupont"]
    for m in results:
        assert m.value is None
        assert m.missing, f"{m.key} should report missing components"
        assert m.components == {}


def test_aggregator_order_and_bilingual_names():
    results = academic_models(healthy())
    keys = [m.key for m in results]
    assert keys == ["altman", "springate", "zmijewski", "dupont"]
    assert all(m.name for m in results)  # name resolves in the current language
    assert all(m.verdict for m in results)


def test_beneish_zero_denominators_never_raise():
    from src.analysis.redflags import beneish_m_score

    prev_z = YearMetrics(
        year=2021,
        revenue=100.0,
        gross_profit=20.0,
        accounts_receivable=0.0,
        total_assets=200.0,
        total_liabilities=0.0,
        fixed_assets=50.0,
        depreciation_amortization=0.0,
        selling_expenses=0.0,
    )
    curr_z = YearMetrics(
        year=2022,
        revenue=100.0,
        gross_profit=0.0,
        accounts_receivable=10.0,
        total_assets=200.0,
        total_liabilities=50.0,
        fixed_assets=50.0,
        depreciation_amortization=0.0,
        selling_expenses=10.0,
    )
    res = beneish_m_score(prev_z, curr_z)
    assert res.m_score is None
    assert "GMI" in res.missing
    assert "DSRI" in res.missing
    assert "LVGI" in res.missing
    assert "DEPI" in res.missing
    assert "SGAI" in res.missing
