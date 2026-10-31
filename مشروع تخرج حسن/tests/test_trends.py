"""Multi-year trends: hand-computed CAGR/streak fixtures, the danger-streak
warning, honest skips (<3 points, negative CAGR base), and the pipeline
actually carrying every-year metrics."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.analysis.calculator import YearMetrics
from src.analysis.trends import format_series, year_trends
from src.pipeline import run_pipeline

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_CSV = PROJECT_ROOT / "sample_data" / "sample_financials.csv"


def metrics(year: int, **kw) -> YearMetrics:
    return YearMetrics(year=year, **kw)


def four_years() -> dict[int, YearMetrics]:
    return {
        2021: metrics(2021, revenue=100.0, net_income=12.0, net_margin=12.0,
                      roe=15.0, current_ratio=2.0, debt_to_equity=0.4),
        2022: metrics(2022, revenue=120.0, net_income=10.0, net_margin=10.0,
                      roe=13.0, current_ratio=1.6, debt_to_equity=0.6),
        2023: metrics(2023, revenue=144.0, net_income=8.0, net_margin=8.0,
                      roe=11.0, current_ratio=2.0, debt_to_equity=0.8),
        2024: metrics(2024, revenue=172.8, net_income=6.0, net_margin=6.0,
                      roe=9.0, current_ratio=1.5, debt_to_equity=1.0),
    }


def test_revenue_cagr_hand_computed():
    rows = {t.key: t for t in year_trends(four_years())}
    # 100 → 172.8 over 3 steps = exactly +20%/year
    assert rows["revenue"].cagr_pct == pytest.approx(20.0, abs=0.01)
    assert rows["revenue"].warning == ""
    assert "تحسن متواصل" in rows["revenue"].reading


def test_falling_margin_flags_danger_streak():
    rows = {t.key: t for t in year_trends(four_years())}
    t = rows["net_margin"]  # 12 → 10 → 8 → 6: three consecutive declines
    assert "تراجع متواصل" in t.reading
    assert t.warning != ""
    assert "3 سنوات" in t.warning


def test_rising_leverage_flags_danger_streak():
    rows = {t.key: t for t in year_trends(four_years())}
    t = rows["debt_to_equity"]  # 0.4 → 0.6 → 0.8 → 1.0, lower-is-better
    assert "تراجع متواصل" in t.reading
    assert t.warning != ""


def test_zigzag_has_no_streak_claims():
    m = four_years()
    m[2021] = metrics(2021, current_ratio=2.0)
    m[2022] = metrics(2022, current_ratio=1.4)
    m[2023] = metrics(2023, current_ratio=2.2)
    m[2024] = metrics(2024, current_ratio=1.5)
    rows = {t.key: t for t in year_trends(m)}
    assert rows["current_ratio"].reading.startswith("متذبذب")
    assert rows["current_ratio"].warning == ""


def test_metrics_with_fewer_than_three_points_are_skipped():
    m = four_years()
    m[2021] = metrics(2021, revenue=100.0)  # roe exists only in 2023/2024... build explicitly
    sparse = {
        2023: metrics(2023, roe=11.0),
        2024: metrics(2024, roe=9.0),
    }
    assert year_trends(sparse) == []


def test_cagr_skipped_for_negative_base():
    m = {
        2021: metrics(2021, net_income=-50.0),
        2022: metrics(2022, net_income=0.0),
        2023: metrics(2023, net_income=100.0),
    }
    rows = {t.key: t for t in year_trends(m)}
    assert rows["net_income"].cagr_pct is None


def test_format_series_by_kind():
    s = [(2021, 1_000_000.0), (2022, 1_500_000.0)]
    assert format_series("currency", s) == "1,000,000 → 1,500,000"
    assert format_series("percent", [(2021, 12.0), (2022, 9.5)]) == "12.0% → 9.5%"
    assert format_series("ratio", [(2021, 0.5), (2022, 1.0)]) == "0.50x → 1.00x"


def test_pipeline_carries_every_year_metrics():
    raw = SAMPLE_CSV.read_bytes()
    r = run_pipeline("sample_financials.csv", raw, "شركة تجريبية")
    years = set(r["metric_years_available"])
    assert set(r["all_year_metrics"]) == years
    assert r["all_year_metrics"][r["prev_year"]].revenue == r["prev_metrics"].revenue
    assert r["all_year_metrics"][r["curr_year"]].roe == r["curr_metrics"].roe
