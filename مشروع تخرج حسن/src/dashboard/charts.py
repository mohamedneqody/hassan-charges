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
        if value < 0:
            return f"-{currency}{_ar_words(humanize(abs(value), scale))}"
        return f"{currency}{_ar_words(humanize(value, scale))}"
    return fmt_value(value, kind, currency)


def fmt_signed_ar(value: float | None, kind: str, currency: str = "$",
                  scale: int = 1) -> str:
    if value is None:
        return "غير متوفر"
    if kind == CURRENCY:
        if value < 0:
            return f"-{currency}{_ar_words(humanize(abs(value), scale))}"
        sign = "+" if value > 0 else ""
        return f"{sign}{currency}{_ar_words(humanize(value, scale))}"
    return fmt_signed(value, kind, currency)


def fmt_value(value: float | None, kind: str, currency: str = "$") -> str:
    if value is None:
        return "غير متوفر"
    if kind == CURRENCY:
        if value < 0:
            return f"-{currency}{humanize(abs(value))}"
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

def _layout(fig: go.Figure, title: str, y_title: str, height: int = 340) -> go.Figure:
    fig.update_layout(
        title=dict(
            text=title,
            font=dict(size=15, color=INK, family="'IBM Plex Sans Arabic', Cairo, Inter, sans-serif"),
            x=0.5,
            xanchor="center",
        ),
        yaxis_title=y_title,
        barmode="group",
        bargap=0.26,
        bargroupgap=0.10,
        template="plotly_white",
        font=_FONT,
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(248,250,252,0.55)",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
            bgcolor="rgba(255,255,255,0.8)",
        ),
        margin=dict(t=76, b=42, l=50, r=28),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor="#0F172A",
            bordercolor="#334155",
            font=dict(
                family="'IBM Plex Sans Arabic', Cairo, Inter, 'Segoe UI', sans-serif",
                size=12.5,
                color="#F8FAFC",
            ),
        ),
    )
    fig.update_yaxes(
        gridcolor=GRID_COLOR,
        griddash="dot",
        zerolinecolor="#CBD5E1",
        zerolinewidth=1.2,
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
                  annotation_text="حد الأمان (1.0)", annotation_position="top left")
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
    rows_by_key: dict[str, MetricRow],
    prev_year: int,
    curr_year: int,
    currency: str,
    scale: int = 1,
    lang: str = "ar",
) -> go.Figure:
    is_ar = lang != "en"
    labels, prev_vals, curr_vals = [], [], []
    for key, display in [
        ("operating_cash_flow", "تشغيلية" if is_ar else "Operating"),
        ("investing_cash_flow", "استثمارية" if is_ar else "Investing"),
        ("financing_cash_flow", "تمويلية" if is_ar else "Financing"),
    ]:
        row = rows_by_key.get(key)
        labels.append(display)
        pv = row.previous if row else None
        cv = row.current if row else None
        prev_vals.append(pv * scale if pv is not None else None)
        curr_vals.append(cv * scale if cv is not None else None)

    def _cf_txt(v):
        if v is None:
            return "—"
        return fmt_value_ar(v, CURRENCY, currency, scale=1) if is_ar else fmt_value(v, CURRENCY, currency)

    fig = go.Figure()
    fig.add_bar(name=str(prev_year), x=labels, y=prev_vals, marker_color=PREV_COLOR,
                text=[_cf_txt(v) for v in prev_vals], textposition="outside")
    fig.add_bar(name=str(curr_year), x=labels, y=curr_vals, marker_color=CURR_COLOR,
                text=[_cf_txt(v) for v in curr_vals], textposition="outside")
    fig.add_hline(y=0, line_color=DISABLED_INK, line_width=1)
    title = "التدفقات النقدية حسب النشاط" if is_ar else "Cash Flows by Activity"
    y_lbl = currency if currency else ("المبلغ" if is_ar else "Amount")
    return _layout(fig, title, y_lbl)


def health_gauge(score, lang: str = "ar") -> go.Figure:
    """Half-circle gauge for the Financial Health Score (0-100)."""
    is_ar = lang != "en"
    lbl = score.label_ar if is_ar else score.label_en
    title_txt = (
        f"مؤشر الصحة المالية — {lbl}"
        if is_ar
        else f"Financial Health Score — {lbl}"
    )
    val = int(round(float(score.total))) if score.total is not None else 0
    bar_color = SUCCESS if val >= 60 else (WARNING if val >= 40 else (PRIMARY if val >= 25 else NEG_COLOR))
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=val,
            domain=dict(x=[0.11, 0.89], y=[0.14, 0.86]),
            number=dict(
                suffix="/100",
                font=dict(size=34, family="'IBM Plex Sans Arabic', Inter, sans-serif", color=INK),
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
        margin=dict(t=58, b=30, l=42, r=42),
        height=345,
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


# ---------------------------------------------------------------------------
# Executive Visual Charts (v9.20 — Overview, Health Radar, Growth & Insights)
# ---------------------------------------------------------------------------

def income_summary_chart(
    prev_m,
    curr_m,
    prev_year: int,
    curr_year: int,
    currency: str = "$",
    scale: int = 1,
    lang: str = "ar",
) -> go.Figure | None:
    """Grouped bar chart of the 4 core Income Statement stages across two years."""
    is_ar = lang != "en"
    items = [
        ("revenue", "الإيرادات" if is_ar else "Revenue"),
        ("gross_profit", "مجمل الربح" if is_ar else "Gross Profit"),
        ("operating_income", "الربح التشغيلي" if is_ar else "Operating Income"),
        ("net_income", "صافي الربح" if is_ar else "Net Income"),
    ]
    labels, p_vals, c_vals = [], [], []
    for attr, lbl in items:
        pv = getattr(prev_m, attr, None) if prev_m is not None else None
        cv = getattr(curr_m, attr, None) if curr_m is not None else None
        if pv is None and cv is None:
            continue
        labels.append(lbl)
        p_vals.append(pv * scale if pv is not None else None)
        c_vals.append(cv * scale if cv is not None else None)
    if not labels:
        return None

    def _lbl_fmt(v):
        if v is None:
            return ""
        return fmt_value_ar(v, CURRENCY, currency, scale=1) if is_ar else fmt_value(v, CURRENCY, currency)

    fig = go.Figure()
    fig.add_bar(
        name=str(prev_year),
        x=labels,
        y=p_vals,
        marker=dict(color="#94A3B8", line=dict(width=0)),
        text=[_lbl_fmt(v) for v in p_vals],
        textposition="outside",
        cliponaxis=False,
        textfont=dict(size=10.5, color="#475569"),
    )
    fig.add_bar(
        name=str(curr_year),
        x=labels,
        y=c_vals,
        marker=dict(color="#4F46E5", line=dict(width=0)),
        text=[_lbl_fmt(v) for v in c_vals],
        textposition="outside",
        cliponaxis=False,
        textfont=dict(size=10.5, color="#1E1B4B"),
    )
    title = (
        f"أداء قائمة الدخل ({prev_year} — {curr_year})"
        if is_ar
        else f"Income Statement ({prev_year} vs {curr_year})"
    )
    fig = _layout(fig, title, "", height=370)
    fig.update_layout(
        legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="center", x=0.5, font=dict(size=12)),
        margin=dict(t=58, b=72, l=50, r=20),
    )
    return fig


def balance_structure_chart(
    prev_m,
    curr_m,
    prev_year: int,
    curr_year: int,
    currency: str = "$",
    scale: int = 1,
    lang: str = "ar",
) -> go.Figure | None:
    """Stacked bar chart comparing Capital Structure (Equity vs Current/Non-Current Liabilities)."""
    is_ar = lang != "en"
    years_lbl = [str(prev_year), str(curr_year)]

    def _g(m, attr):
        v = getattr(m, attr, None) if m is not None else None
        return abs(v) * scale if v is not None else None

    eq_vals = [_g(prev_m, "equity"), _g(curr_m, "equity")]
    cl_vals = [_g(prev_m, "current_liabilities"), _g(curr_m, "current_liabilities")]
    tl_vals = [_g(prev_m, "total_liabilities"), _g(curr_m, "total_liabilities")]
    ncl_vals = []
    for tl, cl in zip(tl_vals, cl_vals):
        if tl is not None and cl is not None and tl >= cl:
            ncl_vals.append(tl - cl)
        else:
            ncl_vals.append(None)

    if all(v is None for v in eq_vals + cl_vals + tl_vals):
        return None

    def _lbl_fmt(v):
        if v is None or v == 0:
            return ""
        return fmt_value_ar(v, CURRENCY, currency, scale=1) if is_ar else fmt_value(v, CURRENCY, currency)

    fig = go.Figure()
    if any(v is not None for v in eq_vals):
        fig.add_bar(
            name="حقوق الملكية" if is_ar else "Equity",
            x=years_lbl,
            y=eq_vals,
            marker_color="#10B981",
            text=[_lbl_fmt(v) for v in eq_vals],
            textposition="inside",
            insidetextfont=dict(color="#FFFFFF", size=11),
        )
    if any(v is not None for v in cl_vals):
        fig.add_bar(
            name="التزامات متداولة" if is_ar else "Current Liabilities",
            x=years_lbl,
            y=cl_vals,
            marker_color="#F59E0B",
            text=[_lbl_fmt(v) for v in cl_vals],
            textposition="inside",
            insidetextfont=dict(color="#FFFFFF", size=11),
        )
    if any(v is not None and v > 0 for v in ncl_vals):
        fig.add_bar(
            name="التزامات غير متداولة" if is_ar else "Non-Current Liabilities",
            x=years_lbl,
            y=ncl_vals,
            marker_color="#6366F1",
            text=[_lbl_fmt(v) for v in ncl_vals],
            textposition="inside",
            insidetextfont=dict(color="#FFFFFF", size=11),
        )
    elif any(v is not None for v in tl_vals) and all(v is None for v in cl_vals):
        fig.add_bar(
            name="إجمالي الالتزامات" if is_ar else "Total Liabilities",
            x=years_lbl,
            y=tl_vals,
            marker_color="#F59E0B",
            text=[_lbl_fmt(v) for v in tl_vals],
            textposition="inside",
            insidetextfont=dict(color="#FFFFFF", size=11),
        )

    title = (
        f"هيكل التمويل ({prev_year} — {curr_year})"
        if is_ar
        else f"Capital Structure ({prev_year} vs {curr_year})"
    )
    fig = _layout(fig, title, "", height=370)
    fig.update_layout(
        barmode="stack",
        legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="center", x=0.5, font=dict(size=11.5)),
        margin=dict(t=58, b=72, l=50, r=20),
    )
    return fig


def health_radar_chart(score, lang: str = "ar") -> go.Figure | None:
    """Radar / Spider chart comparing the 4 Financial Health Pillars against a 70/100 benchmark."""
    pillars = list(getattr(score, "pillars", None) or [])
    valid = [p for p in pillars if getattr(p, "score", None) is not None]
    if len(valid) < 3:
        return None
    is_ar = lang != "en"
    names = [p.name_ar if is_ar else p.name for p in valid]
    vals = [float(p.score) for p in valid]
    # Close the radar loop
    theta = names + [names[0]]
    r_vals = vals + [vals[0]]
    r_bench = [70.0] * len(theta)

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=r_bench,
        theta=theta,
        name="المعيار المستهدف (70)" if is_ar else "Benchmark (70)",
        line=dict(color="#94A3B8", width=1.8, dash="dash"),
        fill="none",
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatterpolar(
        r=r_vals,
        theta=theta,
        name="أداء الشركة" if is_ar else "Company Score",
        fill="toself",
        fillcolor="rgba(79, 70, 229, 0.22)",
        line=dict(color="#4F46E5", width=2.6),
        marker=dict(size=7, color="#4F46E5"),
        hovertemplate="%{theta}: <b>%{r:.1f}/100</b><extra></extra>",
    ))
    fig.update_layout(
        title=dict(
            text="توازن أركان الصحة المالية" if is_ar else "Financial Health Pillar Balance",
            font=dict(size=15, color=INK),
            x=0.5,
            xanchor="center",
        ),
        polar=dict(
            bgcolor="rgba(248,250,252,0.7)",
            radialaxis=dict(
                visible=True,
                range=[0, 100],
                tickvals=[25, 50, 75, 100],
                gridcolor="#E2E8F0",
                tickfont=dict(size=10, color="#64748B"),
            ),
            angularaxis=dict(
                gridcolor="#E2E8F0",
                tickfont=dict(size=11.5, color=INK),
            ),
        ),
        font=_FONT,
        paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="top", y=-0.20, xanchor="center", x=0.5),
        margin=dict(t=58, b=76, l=82, r=82),
        height=345,
    )
    return fig


def growth_bar_chart(
    growth_rows: list,
    curr_year: int | None = None,
    lang: str = "ar",
) -> go.Figure | None:
    """Diverging horizontal bar chart of YoY growth percentages (green positive, red negative)."""
    is_ar = lang != "en"
    items = []
    for gr in (growth_rows or []):
        val = getattr(gr, "current", None)
        if val is None:
            continue
        lbl = getattr(gr, "label_ar", None) if is_ar else getattr(gr, "label", None)
        items.append((lbl or getattr(gr, "key", ""), float(val)))
    if not items:
        return None
    items.sort(key=lambda x: x[1])
    labels = [x[0] for x in items]
    vals = [x[1] for x in items]
    colors = ["#10B981" if v >= 0 else "#EF4444" for v in vals]

    fig = go.Figure(go.Bar(
        x=vals,
        y=labels,
        orientation="h",
        marker_color=colors,
        text=[f"{'+' if v > 0 else ''}{v:.1f}%" for v in vals],
        textposition="outside",
        cliponaxis=False,
        textfont=dict(size=11.5, color=INK),
        hovertemplate="%{y}: <b>%{x:+.1f}%</b><extra></extra>",
    ))
    yr_s = f" ({curr_year})" if curr_year else ""
    title = f"معدلات النمو السنوي{yr_s}" if is_ar else f"Year-over-Year Growth{yr_s}"
    fig = _layout(fig, title, "", height=max(300, 46 * len(items) + 100))
    min_v, max_v = min(vals), max(vals)
    lo = min(0.0, min_v) * 1.25 if min_v < 0 else 0.0
    hi = max(0.0, max_v) * 1.25 if max_v > 0 else 5.0
    fig.update_layout(
        xaxis_title="نسبة النمو %" if is_ar else "Growth %",
        showlegend=False,
        margin=dict(t=60, b=46, l=24, r=78),
    )
    fig.update_xaxes(range=[lo, hi], automargin=True)
    fig.update_yaxes(automargin=True)
    fig.add_vline(x=0, line_color="#94A3B8", line_width=1.4)
    return fig


def insights_donut_chart(
    n_pos: int,
    n_neg: int,
    n_neu: int,
    lang: str = "ar",
) -> go.Figure | None:
    """Compact donut chart summarizing strengths vs weaknesses vs neutral signals."""
    total = n_pos + n_neg + n_neu
    if total == 0:
        return None
    is_ar = lang != "en"
    labels = (
        ["نقاط القوة", "نقاط الضعف", "مؤشرات مستقرة"]
        if is_ar
        else ["Strengths", "Weaknesses", "Neutral"]
    )
    vals = [n_pos, n_neg, n_neu]
    colors = ["#10B981", "#EF4444", "#94A3B8"]

    fig = go.Figure(go.Pie(
        labels=labels,
        values=vals,
        hole=0.62,
        marker=dict(colors=colors, line=dict(color="#FFFFFF", width=2)),
        textinfo="value+percent",
        textfont=dict(size=11.5),
        hovertemplate="%{label}: <b>%{value}</b> (%{percent})<extra></extra>",
    ))
    fig.update_layout(
        font=_FONT,
        paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="top", y=-0.06, xanchor="center", x=0.5, font=dict(size=11.5)),
        margin=dict(t=16, b=72, l=16, r=16),
        height=280,
        annotations=[dict(
            text=f"<b>{total}</b><br>{'رؤية' if is_ar else 'Signals'}",
            x=0.5, y=0.5, font_size=13, showarrow=False, font=dict(color=INK),
        )],
    )
    return fig
