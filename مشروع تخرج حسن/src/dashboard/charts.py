"""Formatting helpers and Plotly charts for the dashboard."""
from __future__ import annotations

import plotly.graph_objects as go
import pandas as pd

from src.analysis.comparison import CURRENCY, DAYS, PERCENT, RATIO, MetricRow

# Light-theme palette (indigo design system, see dashboard/theme.py)
PREV_COLOR = "#a5b4fc"   # indigo-300 — previous year
CURR_COLOR = "#4f46e5"   # indigo-600 — current year
POS_COLOR = "#059669"
NEG_COLOR = "#e11d48"
GRID_COLOR = "#eef2f7"
TEXT_COLOR = "#334155"

_FONT = dict(family="Inter, 'Segoe UI', Arial, sans-serif", size=13, color=TEXT_COLOR)


# ---------------------------------------------------------------------------
# Value formatting
# ---------------------------------------------------------------------------

def humanize(value: float) -> str:
    """1,180,000 -> 1.18M  (K / M / B abbreviations)."""
    abs_v = abs(value)
    for divisor, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs_v >= divisor:
            num = value / divisor
            text = f"{num:.2f}".rstrip("0").rstrip(".")
            return f"{text}{suffix}"
    if abs_v >= 100:
        return f"{value:,.0f}"
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def fmt_value(value: float | None, kind: str, currency: str = "$") -> str:
    if value is None:
        return "N/A"
    if kind == CURRENCY:
        return f"{currency}{humanize(value)}"
    if kind == PERCENT:
        return f"{value:.1f}%"
    if kind == RATIO:
        return f"{value:.2f}x"
    if kind == DAYS:
        return f"{value:,.0f} days"
    return f"{value:,.2f}"


def fmt_signed(value: float | None, kind: str, currency: str = "$") -> str:
    if value is None:
        return "N/A"
    sign = "+" if value > 0 else ""
    if kind == CURRENCY:
        return f"{sign}{currency}{humanize(value)}"
    if kind == PERCENT:
        return f"{sign}{value:.1f}pp"
    if kind == RATIO:
        return f"{sign}{value:.2f}x"
    if kind == DAYS:
        return f"{sign}{value:,.0f} days"
    return f"{sign}{value:,.2f}"


def fmt_signed_pct(value: float | None) -> str:
    return "N/A" if value is None else f"{'+' if value > 0 else ''}{value:.1f}%"


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------

def _layout(fig: go.Figure, title: str, y_title: str) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, font=dict(size=16, color="#0f172a")),
        yaxis_title=y_title,
        barmode="group",
        template="plotly_white",
        font=_FONT,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        margin=dict(t=70, b=40, l=50, r=30),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor="#ffffff", bordercolor="#e2e8f0",
            font=dict(family="Inter, Segoe UI, sans-serif", size=13, color="#0f172a"),
        ),
    )
    fig.update_yaxes(
        gridcolor=GRID_COLOR, zerolinecolor="#cbd5e1", zerolinewidth=1,
        showline=False, ticksuffix=" ",
    )
    fig.update_xaxes(showline=True, linecolor="#e2e8f0", ticksuffix=" ")
    return fig


def _bar_pair(
    labels: list[str],
    prev_vals: list[float | None],
    curr_vals: list[float | None],
    prev_year: int,
    curr_year: int,
    currency: str,
    title: str,
    y_title: str,
    reference: dict | None = None,
) -> go.Figure:
    fig = go.Figure()
    fig.add_bar(
        name=str(prev_year), x=labels, y=prev_vals,
        marker_color=PREV_COLOR,
        text=[fmt_value(v, CURRENCY if currency == "$" and y_title.startswith("Amount") else (
            PERCENT if y_title.startswith("Percent") else RATIO
        ), currency) for v in prev_vals],
        textposition="outside",
    )
    fig.add_bar(
        name=str(curr_year), x=labels, y=curr_vals,
        marker_color=CURR_COLOR,
        text=[fmt_value(v, PERCENT if y_title.startswith("Percent") else (
            RATIO if y_title.startswith("Ratio") else CURRENCY
        ), currency) for v in curr_vals],
        textposition="outside",
    )
    if reference:
        fig.add_hline(
            y=reference["y"], line_dash="dash", line_color="#d97706",
            annotation_text=reference["label"], annotation_position="right top",
        )
    return _layout(fig, title, y_title)


def currency_chart(
    title: str, label: str, prev_year: int, curr_year: int,
    prev_value: float | None, curr_value: float | None, currency: str,
) -> go.Figure:
    return _bar_pair(
        [label], [prev_value], [curr_value], prev_year, curr_year, currency,
        title, "المبلغ",
    )


def margins_chart(
    rows_by_key: dict[str, MetricRow], prev_year: int, curr_year: int, currency: str
) -> go.Figure:
    labels, prev_vals, curr_vals = [], [], []
    for key, display in [("gross_margin", "هامش مجمل الربح"), ("operating_margin", "هامش الربح التشغيلي"), ("net_margin", "هامش صافي الربح")]:
        row = rows_by_key.get(key)
        labels.append(display)
        prev_vals.append(row.previous if row else None)
        curr_vals.append(row.current if row else None)
    fig = go.Figure()
    fig.add_bar(name=str(prev_year), x=labels, y=prev_vals, marker_color=PREV_COLOR,
                text=[fmt_value(v, PERCENT) for v in prev_vals], textposition="outside")
    fig.add_bar(name=str(curr_year), x=labels, y=curr_vals, marker_color=CURR_COLOR,
                text=[fmt_value(v, PERCENT) for v in curr_vals], textposition="outside")
    return _layout(fig, "هوامش الربحية — السنة السابقة مقابل الحالية", "نسبة %")


def returns_chart(
    rows_by_key: dict[str, MetricRow], prev_year: int, curr_year: int
) -> go.Figure:
    labels, prev_vals, curr_vals = ["العائد على الأصول", "العائد على الملكية"], [], []
    for key in ("roa", "roe"):
        row = rows_by_key.get(key)
        prev_vals.append(row.previous if row else None)
        curr_vals.append(row.current if row else None)
    fig = go.Figure()
    fig.add_bar(name=str(prev_year), x=labels, y=prev_vals, marker_color=PREV_COLOR,
                text=[fmt_value(v, PERCENT) for v in prev_vals], textposition="outside")
    fig.add_bar(name=str(curr_year), x=labels, y=curr_vals, marker_color=CURR_COLOR,
                text=[fmt_value(v, PERCENT) for v in curr_vals], textposition="outside")
    return _layout(fig, "العائد على الأصول وحقوق الملكية", "نسبة %")


def liquidity_chart(
    rows_by_key: dict[str, MetricRow], prev_year: int, curr_year: int
) -> go.Figure:
    labels, prev_vals, curr_vals = ["النسبة الجارية", "النسبة السريعة"], [], []
    for key in ("current_ratio", "quick_ratio"):
        row = rows_by_key.get(key)
        prev_vals.append(row.previous if row else None)
        curr_vals.append(row.current if row else None)
    fig = go.Figure()
    fig.add_bar(name=str(prev_year), x=labels, y=prev_vals, marker_color=PREV_COLOR,
                text=[fmt_value(v, RATIO) for v in prev_vals], textposition="outside")
    fig.add_bar(name=str(curr_year), x=labels, y=curr_vals, marker_color=CURR_COLOR,
                text=[fmt_value(v, RATIO) for v in curr_vals], textposition="outside")
    fig.add_hline(y=1.0, line_dash="dash", line_color="#d97706",
                  annotation_text="1.0x safety threshold", annotation_position="right top")
    return _layout(fig, "نسب السيولة", "مضاعف (x)")


def leverage_chart(
    rows_by_key: dict[str, MetricRow], prev_year: int, curr_year: int
) -> go.Figure:
    labels, prev_vals, curr_vals = ["الدين إلى حقوق الملكية", "الالتزامات إلى الأصول"], [], []
    for key in ("debt_to_equity", "debt_ratio"):
        row = rows_by_key.get(key)
        prev_vals.append(row.previous if row else None)
        curr_vals.append(row.current if row else None)
    fig = go.Figure()
    fig.add_bar(name=str(prev_year), x=labels, y=prev_vals, marker_color=PREV_COLOR,
                text=[fmt_value(v, RATIO) for v in prev_vals], textposition="outside")
    fig.add_bar(name=str(curr_year), x=labels, y=curr_vals, marker_color=CURR_COLOR,
                text=[fmt_value(v, RATIO) for v in curr_vals], textposition="outside")
    return _layout(fig, "نسب المديونية", "مضاعف (x)")


def efficiency_chart(
    rows_by_key: dict[str, MetricRow], prev_year: int, curr_year: int
) -> go.Figure:
    labels, prev_vals, curr_vals = ["دوران الأصول", "دوران المخزون"], [], []
    for key in ("asset_turnover", "inventory_turnover"):
        row = rows_by_key.get(key)
        prev_vals.append(row.previous if row else None)
        curr_vals.append(row.current if row else None)
    fig = go.Figure()
    fig.add_bar(name=str(prev_year), x=labels, y=prev_vals, marker_color=PREV_COLOR,
                text=[fmt_value(v, RATIO) for v in prev_vals], textposition="outside")
    fig.add_bar(name=str(curr_year), x=labels, y=curr_vals, marker_color=CURR_COLOR,
                text=[fmt_value(v, RATIO) for v in curr_vals], textposition="outside")
    return _layout(fig, "الكفاءة التشغيلية — معدلات الدوران", "مرة سنوياً (x)")


def cashflow_chart(
    rows_by_key: dict[str, MetricRow], prev_year: int, curr_year: int, currency: str
) -> go.Figure:
    labels, prev_vals, curr_vals = [], [], []
    for key, display in [
        ("operating_cash_flow", "تشغيلية"),
        ("investing_cash_flow", "استثمارية"),
        ("financing_cash_flow", "تمويلية"),
    ]:
        row = rows_by_key.get(key)
        labels.append(display)
        prev_vals.append(row.previous if row else None)
        curr_vals.append(row.current if row else None)
    fig = go.Figure()
    fig.add_bar(name=str(prev_year), x=labels, y=prev_vals, marker_color=PREV_COLOR,
                text=[fmt_value(v, CURRENCY, currency) for v in prev_vals], textposition="outside")
    fig.add_bar(name=str(curr_year), x=labels, y=curr_vals, marker_color=CURR_COLOR,
                text=[fmt_value(v, CURRENCY, currency) for v in curr_vals], textposition="outside")
    fig.add_hline(y=0, line_color="#94a3b8", line_width=1)
    return _layout(fig, "التدفقات النقدية حسب النشاط", "المبلغ")


def health_gauge(score) -> go.Figure:
    """Half-circle gauge for the Financial Health Score (0-100)."""
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=score.total if score.total is not None else 0,
            number=dict(font=dict(size=44, family="Inter, Segoe UI, sans-serif", color="#0f172a"),
                        valueformat=".0f"),
            gauge=dict(
                axis=dict(range=[0, 100], tickwidth=1, tickcolor="#cbd5e1"),
                bar=dict(color="#4f46e5", thickness=0.28),
                steps=[
                    dict(range=[0, 40], color="#fee2e2"),
                    dict(range=[40, 60], color="#fef3c7"),
                    dict(range=[60, 80], color="#d1fae5"),
                    dict(range=[80, 100], color="#a7f3d0"),
                ],
                threshold=dict(line=dict(color="#0f172a", width=2), value=80),
            ),
        )
    )
    fig.update_layout(
        title=dict(text=f"مؤشر الصحة المالية — {score.label}", font=dict(size=15, color="#0f172a"),
                   x=0.5, xanchor="center"),
        template="plotly_white", font=_FONT,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=60, b=10, l=25, r=25), height=230,
    )
    return fig


def trend_scatter(rows: list[MetricRow], prev_year: int, curr_year: int) -> go.Figure | None:
    """Horizontal change chart: relative % change per metric, colored by status."""
    data = [
        r for r in rows
        if r.change_pct is not None and r.change_pct != 0 and r.previous is not None
    ]
    if not data:
        return None
    data = sorted(data, key=lambda r: r.change_pct)
    colors = [POS_COLOR if r.status == "Positive" else NEG_COLOR for r in data]
    fig = go.Figure()
    fig.add_bar(
        y=[r.label for r in data], x=[r.change_pct for r in data],
        orientation="h", marker_color=colors,
        text=[fmt_signed_pct(r.change_pct) for r in data],
        textposition="outside",
    )
    fig.update_layout(
        title=dict(text=f"التغير النسبي {prev_year} ← {curr_year} (%)", font=dict(size=16, color="#0f172a")),
        template="plotly_white", font=_FONT,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis_title="التغير %",
        margin=dict(t=70, b=40, l=50, r=30), height=max(300, 42 * len(data) + 90),
        hoverlabel=dict(
            bgcolor="#ffffff", bordercolor="#e2e8f0",
            font=dict(family="Inter, Segoe UI, sans-serif", size=13, color="#0f172a"),
        ),
    )
    fig.add_vline(x=0, line_color="#94a3b8", line_width=1)
    return fig


def styled_comparison_table(
    rows: list[MetricRow], prev_year: int, curr_year: int, currency: str
) -> pd.DataFrame:
    """Display-ready DataFrame with formatted strings (used for CSV export)."""
    records = []
    for r in rows:
        records.append(
            {
                "Category": r.category,
                "Metric": r.label,
                str(prev_year): fmt_value(r.previous, r.kind, currency),
                str(curr_year): fmt_value(r.current, r.kind, currency),
                "Change": fmt_signed(r.change, r.kind, currency),
                "Change %": fmt_signed_pct(r.change_pct),
                "Status": r.status,
                "Trend": (f"{r.trend_symbol} {r.trend}") if r.trend != "N/A" else "N/A",
            }
        )
    return pd.DataFrame(records)
