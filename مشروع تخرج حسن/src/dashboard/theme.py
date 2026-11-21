# -*- coding: utf-8 -*-
"""Unified theme wrapper and HTML component helpers for Classic & New UI.

Delegates all design tokens and CSS to `src.dashboard.design_system` so there
is a single conflict-free stylesheet injected per rerun (respecting RTL/LTR).
"""
from __future__ import annotations

import html as _html

from src.dashboard.design_system import (
    DANGER,
    DEEP,
    PRIMARY,
    SUCCESS,
    INK as _INK,
    get_design_css,
)

# Unified Design Tokens (re-exported for Classic UI callers)
BRAND = PRIMARY
BRAND_2 = DEEP
POS = SUCCESS
NEG = DANGER
INK = _INK

ESC = _html.escape

# Kept empty intentionally: all CSS is unified inside `design_system.get_design_css`
# to avoid duplicate/conflicting layers.
THEME_CSS = ""


def inject_theme(lang: str | None = None) -> None:
    """Inject the unified design-system CSS once for the active language."""
    import streamlit as st

    active_lang = lang or st.session_state.get("ui_lang", "ar")
    st.markdown(get_design_css(active_lang), unsafe_allow_html=True)


def section_title(text: str) -> None:
    import streamlit as st

    st.markdown(
        '<div class="section-title" style="display:flex;align-items:center;gap:10px;'
        'font-size:1.3rem;font-weight:800;">'
        f'<span style="width:5px;height:22px;border-radius:4px;display:inline-block;'
        f'background:linear-gradient(180deg,{BRAND},{BRAND_2});"></span>{ESC(text)}</div>',
        unsafe_allow_html=True,
    )


def kpi_card(
    label: str,
    value: str,
    delta_text: str,
    arrow: str,
    mood: str,
    accent: str,
    delay_ms: int = 0,
    tooltip: str = "",
    variant: str = "",
) -> str:
    tip = f' title="{ESC(tooltip)}"' if tooltip else ""
    extra = f" {variant}" if variant else ""
    delta_html = (
        f'<div class="kpi-delta {ESC(mood)}">{ESC(arrow)} <bdi dir="ltr">{ESC(delta_text)}</bdi></div>'
        if delta_text
        else ""
    )
    return (
        f'<div class="kpi-card{extra}" style="--accent:{ESC(accent)}; animation-delay:{delay_ms}ms"{tip}>'
        f'<div class="kpi-label">{ESC(label)}</div>'
        f'<div class="kpi-value"><bdi dir="ltr">{ESC(value)}</bdi></div>'
        f"{delta_html}"
        "</div>"
    )


def info_chip(label: str, value: str, accent: str = BRAND, delay_ms: int = 0) -> str:
    """Compact card for static facts (company, period, years)."""
    return kpi_card(label, value, "", "◆", "flat", accent, delay_ms, variant="info")


def report_card(
    title: str, icon: str, body: str, accent: str = BRAND, delay_ms: int = 0
) -> str:
    return (
        f'<div class="report-card" style="--accent:{ESC(accent)}; animation-delay:{delay_ms}ms">'
        f'<div class="rc-title"><span class="rc-ico">{icon}</span>{ESC(title)}</div>'
        f'<p dir="auto">{ESC(body)}</p>'
        "</div>"
    )


def sw_card(
    kind: str, title: str, icon: str, items: list[str], ordered: bool = False
) -> str:
    """Colored-top list card (strengths / weaknesses / risks / recommendations)."""
    if ordered:
        lis = "".join(f"<li>{ESC(i)}</li>" for i in items) or "<li><i>—</i></li>"
        body = f"<ol>{lis}</ol>"
    else:
        lis = "".join(f"<li>{ESC(i)}</li>" for i in items) or "<li><i>—</i></li>"
        body = f"<ul>{lis}</ul>"
    return (
        f'<div class="sw-card {ESC(kind)}">'
        f'<div class="rc-title"><span class="rc-ico">{icon}</span>{ESC(title)}</div>'
        f"{body}"
        "</div>"
    )


BADGE_AR = {"Positive": "إيجابي", "Negative": "سلبي", "Neutral": "محايد", "N/A": "غير متاح"}
BADGE_EN = {"Positive": "Positive", "Negative": "Negative", "Neutral": "Neutral", "N/A": "N/A"}


def badge(status: str, lang: str = "ar") -> str:
    cls = {"Positive": "pos", "Negative": "neg", "Neutral": "neu"}.get(status, "na")
    labels = BADGE_EN if lang == "en" else BADGE_AR
    return f'<span class="badge {cls}">{ESC(labels.get(status, status))}</span>'


def fin_table(
    headers: list[str],
    rows_html: list[str],
    num_cols: set[int] | None = None,
) -> str:
    """Financial table with sticky header, RTL/LTR alignment, and graceful overflow."""
    import re as _re

    if num_cols is None:
        inferred: set[int] = set()
        for row in rows_html[:5]:
            cells = _re.findall(r"<td\b([^>]*)>", row, _re.IGNORECASE)
            for idx, attrs in enumerate(cells):
                if _re.search(r'\bclass\s*=\s*["\'][^"\']*\bnum\b', attrs):
                    inferred.add(idx)
        num_cols = inferred
    th = "".join(
        f'<th class="num">{ESC(h)}</th>' if i in num_cols else f"<th>{ESC(h)}</th>"
        for i, h in enumerate(headers)
    )
    return (
        '<div class="table-wrap"><table class="fin-table">'
        f'<thead><tr>{th}</tr></thead><tbody>{"".join(rows_html)}</tbody>'
        "</table></div>"
    )
