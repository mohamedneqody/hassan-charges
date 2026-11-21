"""Formatting helpers and Plotly charts for the dashboard."""
from __future__ import annotations

import plotly.graph_objects as go
import pandas as pd

from src.analysis.comparison import CURRENCY, DAYS, PERCENT, RATIO, MetricRow
from src.dashboard.design_system import (
    DANGER,
    DANGER_SOFT,
    DISABLED_INK,
    INDIGO_SOFT,
    INK,
    INK_BODY,
    LINE,
    PRIMARY,
    SUCCESS,
    SURFACE,
    TRACK_BG,
    WARNING,
)

# Light-theme palette aligned with design_system.py (v9 Premium Light FinTech)
PREV_COLOR = INDIGO_SOFT  # soft indigo — previous year
CURR_COLOR = PRIMARY      # #6255E7 — current year
POS_COLOR = SUCCESS       # #16A34A
NEG_COLOR = DANGER        # #DC2626
GRID_COLOR = TRACK_BG
TEXT_COLOR = INK_BODY

_FONT = dict(
    family="'IBM Plex Sans Arabic', Cairo, Inter, 'Segoe UI', Arial, sans-serif",
    size=13,
    color=TEXT_COLOR,
)


# ---------------------------------------------------------------------------
# Value formatting
# ---------------------------------------------------------------------------

def humanize(value: float, scale: int = 1) -> str:
    """1,180,000 -> 1.18M  (K / M / B abbreviations).

    `scale` = the PRINTED unit factor discovered from the statement header
    (e.g. 1000 when the statement says "in EGP Thousands"): the stored
    value is printed thousands, so the display multiplies by the scale to
    show the ACTUAL currency amount (27,730,150 thousand EGP -> 27.73B,
    i.e. 27.73 مليار — never the misleading "27.73M"). Default scale=1
    keeps every legacy caller and test unchanged."""
    abs_v = abs(value) * scale
    scaled = value * scale
    for divisor, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs_v >= divisor:
            num = scaled / divisor
            text = f"{num:.2f}".rstrip("0").rstrip(".")
            return f"{text}{suffix}"
    if abs_v >= 100:
        return f"{scaled:,.0f}"
    return f"{scaled:,.2f}".rstrip("0").rstrip(".")


UNIT_WORDS_AR = {"B": "مليار", "M": "مليون", "K": "ألف"}


def _ar_words(h: str) -> str:
    """27.73B -> 27.73 مليار (the unified Arabic display of the unit chain)."""
    for suf, word in UNIT_WORDS_AR.items():
        if h.endswith(suf):
            return f"{h[:-len(suf)]} {word}"
    return h


def fmt_value_ar(value: float | None, kind: str, currency: str = "$",
                 scale: int = 1) -> str:
    """fmt_value with the printed-unit scale and Arabic magnitude words —
    the report tables and the Gemini payload share this so a number can
    never read as millions in one place and billions in another."""
    if value is None:
        # المواصفة (تدقيق حديد عز — إصلاح 3/8): القيمة الناقصة تظهر "N/A"
        # الكنسي مع سببها في قسم Missing Data — لا صياغة عربية بديلة.
        return "N/A"
    if kind == CURRENCY:
        return f"{currency}{_ar_words(humanize(value, scale))}"
    return fmt_value(value, kind, currency)


def fmt_signed_ar(value: float | None, kind: str, currency: str = "$",
                  scale: int = 1) -> str:
    if value is None:
        return "غير متوفر"
    if kind == CURRENCY:
        sign = "+" if value > 0 else ""
        return f"{currency}{sign}{_ar_words(humanize(value, scale))}"
    return fmt_signed(value, kind, currency)


def fmt_value(value: float | None, kind: str, currency: str = "$") -> str:
    if value is None:
        return "غير متوفر"
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
        return "غير متوفر"
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
    return "غير متوفر" if value is None else f"{'+' if value > 0 else ''}{value:.1f}%"


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------

def _layout(fig: go.Figure, title: str, y_title: str) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, font=dict(size=15, color=INK)),
        yaxis_title=y_title,
        barmode="group",
        template="plotly_white",
        font=_FONT,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        margin=dict(t=70, b=42, l=50, r=30),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor=SURFACE,
            bordercolor=LINE,
            font=dict(
                family="'IBM Plex Sans Arabic', Cairo, Inter, 'Segoe UI', sans-serif",
                size=13,
                color=INK,
            ),
        ),
    )
    fig.update_yaxes(
        gridcolor=GRID_COLOR,
        zerolinecolor="#CBD5E1",
        zerolinewidth=1,
        showline=False,
        ticksuffix=" ",
        automargin=True,
    )
    fig.update_xaxes(showline=True, linecolor=LINE, ticksuffix=" ", automargin=True)
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
    kind: str = CURRENCY,
) -> go.Figure:
    fig = go.Figure()
    fig.add_bar(
        name=str(prev_year),
        x=labels,
        y=prev_vals,
        marker_color=PREV_COLOR,
        text=[fmt_value(v, kind, currency) for v in prev_vals],
        textposition="outside",
    )
    fig.add_bar(
        name=str(curr_year),
        x=labels,
        y=curr_vals,
        marker_color=CURR_COLOR,
        text=[fmt_value(v, kind, currency) for v in curr_vals],
        textposition="outside",
    )
    if reference:
        fig.add_hline(
            y=reference["y"],
            line_dash="dash",
            line_color=WARNING,
            annotation_text=reference["label"],
            annotation_position="right top",
        )
    return _layout(fig, title, y_title)


def currency_chart(
    title: str, label: str, prev_year: int, curr_year: int,
    prev_value: float | None, curr_value: float | None, currency: str,
) -> go.Figure:
    return _bar_pair(
        [label], [prev_value], [curr_value], prev_year, curr_year, currency,
        title, "المبلغ", kind=CURRENCY,
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
    fig.add_hline(y=1.0, line_dash="dash", line_color=WARNING,
                  annotation_text="حد الأمان 1.0x", annotation_position="right top")
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
    fig.add_hline(y=0, line_color=DISABLED_INK, line_width=1)
    return _layout(fig, "التدفقات النقدية حسب النشاط", "المبلغ")


def health_gauge(score, lang: str = "ar") -> go.Figure:
    """Half-circle gauge for the Financial Health Score (0-100)."""
    is_ar = lang != "en"
    lbl = score.label_ar if is_ar else score.label_en
    title_txt = (
        f"مؤشر الصحة المالية — {lbl}"
        if is_ar
        else f"Financial Health Score — {lbl}"
    )
    val = float(score.total) if score.total is not None else 0.0
    bar_color = SUCCESS if val >= 60 else (WARNING if val >= 40 else (PRIMARY if val >= 25 else NEG_COLOR))
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=val,
            domain=dict(x=[0.08, 0.92], y=[0.14, 0.86]),
            number=dict(
                suffix="/100",
                font=dict(size=36, family="'IBM Plex Sans Arabic', Inter, sans-serif", color=INK),
                valueformat=".0f",
            ),
            gauge=dict(
                axis=dict(
                    range=[0, 100],
                    tickwidth=1,
                    tickcolor="#CBD5E1",
                    tickvals=[0, 20, 40, 60, 80, 100],
                ),
                bar=dict(color=bar_color, thickness=0.32),
                bgcolor="#F8FAFC",
                borderwidth=1,
                bordercolor=LINE,
                steps=[
                    dict(range=[0, 40], color=DANGER_SOFT),
                    dict(range=[40, 60], color="#FEF3C7"),
                    dict(range=[60, 80], color="#D1FAE5"),
                    dict(range=[80, 100], color="#A7F3D0"),
                ],
                threshold=dict(line=dict(color=INK, width=2), thickness=0.75, value=80),
            ),
        )
    )
    fig.update_layout(
        title=dict(
            text=title_txt,
            font=dict(size=15, color=INK),
            x=0.5,
            xanchor="center",
        ),
        template="plotly_white",
        font=_FONT,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=55, b=25, l=30, r=30),
        height=300,
    )
    return fig


def trend_scatter(rows: list[MetricRow], prev_year: int, curr_year: int, lang: str = "ar") -> go.Figure | None:
    """Horizontal change chart: relative % change per metric, colored by status."""
    is_ar = lang != "en"
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
        y=[(r.label_ar or r.label) if is_ar else r.label for r in data],
        x=[r.change_pct for r in data],
        orientation="h", marker_color=colors,
        text=[fmt_signed_pct(r.change_pct) for r in data],
        textposition="outside",
    )
    fig.update_layout(
        title=dict(
            text=(
                f"التغير النسبي {prev_year} ← {curr_year} (%)"
                if is_ar
                else f"Relative Change {prev_year} → {curr_year} (%)"
            ),
            font=dict(size=15, color=INK),
        ),
        template="plotly_white", font=_FONT,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis_title="التغير %" if is_ar else "Change %",
        margin=dict(t=70, b=42, l=50, r=30), height=max(300, 42 * len(data) + 90),
        hoverlabel=dict(
            bgcolor=SURFACE, bordercolor=LINE,
            font=dict(
                family="'IBM Plex Sans Arabic', Cairo, Inter, 'Segoe UI', Arial, sans-serif",
                size=13,
                color=INK,
            ),
        ),
    )
    fig.update_yaxes(automargin=True)
    fig.add_vline(x=0, line_color=DISABLED_INK, line_width=1)
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
