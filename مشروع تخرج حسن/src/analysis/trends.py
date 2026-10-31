"""Multi-year trend analysis (تحليل الاتجاهات عبر السنوات) — deterministic, zero API.

The pipeline computes YearMetrics for EVERY fiscal year present in the
document; this module reads those series. A metric needs >= 3 data points to
be a trend at all (two points are the existing two-year comparison, not a
trend — no double counting).

- CAGR = (last/first)^(1/(n−1)) − 1, only when first > 0 (a negative or zero
  base makes a growth rate meaningless).
- Reading: continuous improvement / continuous decline / zigzag, judged from
  the metric's own higher/lower-is-better direction.
- Danger streaks: 3+ consecutive adverse years are flagged (falling margins
  or returns, rising leverage).
"""
from __future__ import annotations

from dataclasses import dataclass

from src.analysis.calculator import YearMetrics

TREND_METRICS = [
    # (YearMetrics attr, label AR, kind, higher_is_better)
    ("revenue", "الإيرادات", "currency", True),
    ("net_income", "صافي الربح", "currency", True),
    ("net_margin", "هامش صافي الربح", "percent", True),
    ("roe", "العائد على حقوق الملكية", "percent", True),
    ("current_ratio", "النسبة الجارية", "ratio", True),
    ("debt_to_equity", "الدين/حقوق الملكية", "ratio", False),
]

MIN_POINTS = 3
DANGER_STREAK = 3


@dataclass
class TrendRow:
    key: str
    label: str
    kind: str
    higher_is_better: bool
    series: list[tuple[int, float]]
    cagr_pct: float | None
    reading: str
    warning: str = ""


def _cagr(first: float, last: float, steps: int) -> float | None:
    if first <= 0 or steps <= 0:
        return None
    return ((last / first) ** (1.0 / steps) - 1.0) * 100


def format_series(kind: str, series: list[tuple[int, float]]) -> str:
    def f(v: float) -> str:
        if kind == "currency":
            return f"{v:,.0f}"
        if kind == "percent":
            return f"{v:.1f}%"
        return f"{v:.2f}x"

    return " → ".join(f(v) for _, v in series)


def year_trends(metrics_by_year: dict[int, YearMetrics]) -> list[TrendRow]:
    """One TrendRow per metric with >= MIN_POINTS yearly values, in
    TREND_METRICS order."""
    rows: list[TrendRow] = []
    for key, label, kind, hib in TREND_METRICS:
        series = [
            (y, v) for y, m in sorted(metrics_by_year.items())
            if (v := getattr(m, key, None)) is not None
        ]
        if len(series) < MIN_POINTS:
            continue
        best_run = adverse_run = cur_good = cur_adverse = 0
        for (_y1, v1), (_y2, v2) in zip(series, series[1:]):
            if v2 == v1:
                cur_good = cur_adverse = 0
                continue
            if (v2 > v1) if hib else (v2 < v1):
                cur_good += 1
                cur_adverse = 0
            else:
                cur_adverse += 1
                cur_good = 0
            best_run = max(best_run, cur_good)
            adverse_run = max(adverse_run, cur_adverse)

        if best_run >= 2 and adverse_run == 0:
            reading = f"تحسن متواصل على {best_run} خطوات متتالية"
        elif adverse_run >= 2 and best_run == 0:
            reading = f"تراجع متواصل على {adverse_run} خطوات متتالية"
        else:
            reading = "متذبذب بين تحسن وتراجع"

        warning = ""
        if adverse_run >= DANGER_STREAK:
            warning = f"⚠ استمرار في الاتجاه الضار {adverse_run} سنوات متتالية — يستدعي المراجعة"

        steps = len(series) - 1
        c = _cagr(series[0][1], series[-1][1], steps)
        rows.append(TrendRow(
            key, label, kind, hib, series,
            None if c is None else round(c, 2), reading, warning,
        ))
    return rows
