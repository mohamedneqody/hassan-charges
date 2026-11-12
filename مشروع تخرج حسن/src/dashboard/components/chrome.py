# -*- coding: utf-8 -*-
"""مكونات الواجهة المشتركة (v6) — الهيدر المضغوط والشريط الجانبي والحالات.

كل مكون يقرأ من نتائج الـPipeline/نموذج العرض فقط — لا بيانات مصطنعة،
ولا أزرار شكلية: كل عنصر تفاعلي موصول بمنطق قائم.
"""
from __future__ import annotations

import streamlit as st

from src.dashboard.design_system import (
    DANGER, MUTED, PRIMARY, SECONDARY, SUCCESS, WARNING,
)


def esc(v) -> str:
    import html

    return html.escape(str(v))


def render_header(product: str = "وكيل تحليل بيانات مالية ذكي",
                  subtitle: str = "Financial Intelligence") -> None:
    """هيدر مضغوط واحد: الهوية + حالة الموديل + معلومات الملف الحالي.
    لا hero ضخم — صف واحد يحمل هوية المنتج."""
    lang = st.session_state.get("ui_lang", "ar")
    analysis = st.session_state.get("analysis")
    results = st.session_state.get("results")

    model_chip = ""
    if analysis is not None and getattr(analysis, "ok", False):
        model = getattr(analysis, "model", "")
        model_chip = (f'<span class="fs-pill">'
                      f'<span class="fs-dot" style="background:{SUCCESS}"></span>'
                      f'{esc(model)}</span>')
    elif st.session_state.get("gemini_available") is False:
        model_chip = (f'<span class="fs-pill">'
                      f'<span class="fs-dot" style="background:{WARNING}"></span>'
                      f'{"Gemini — خارج الحصة" if lang == "ar" else "Gemini — quota"}</span>')
    else:
        model_chip = (f'<span class="fs-pill">'
                      f'<span class="fs-dot" style="background:{MUTED}"></span>'
                      f'{"جاهز للتحليل" if lang == "ar" else "Ready"}</span>')

    file_chip = ""
    if results:
        fname = esc(results.get("file_name", ""))
        file_chip = f'<span class="fs-pill">📄 {fname}</span>'

    st.markdown(
        f'<div class="fs-header">'
        f'<div class="fs-brand">'
        f'<div class="fs-logo">🤖</div>'
        f'<div><div class="fs-brand-name">{esc(product)}</div>'
        f'<div class="fs-brand-sub">{esc(subtitle)}</div></div>'
        f'</div>'
        f'<div class="fs-header-meta">{model_chip}{file_chip}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_empty_state(title: str, body: str, icon: str = "📄") -> None:
    st.markdown(
        f'<div class="fs-state empty">'
        f'<div class="fs-state-ico">{icon}</div>'
        f'<div class="fs-state-title">{esc(title)}</div>'
        f'<div class="fs-state-body">{esc(body)}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_error_state(title: str, body: str) -> None:
    st.markdown(
        f'<div class="fs-state error">'
        f'<div class="fs-state-title">⚠ {esc(title)}</div>'
        f'<div class="fs-state-body">{esc(body)}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_success_state(title: str, body: str) -> None:
    st.markdown(
        f'<div class="fs-state success">'
        f'<div class="fs-state-title">✓ {esc(title)}</div>'
        f'<div class="fs-state-body">{esc(body)}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def gate_badge(gate: str, label: str) -> str:
    """شارة قرار البوابة — ألوان الحالات الأربع دون أي تزيين زائد."""
    kind = {"use": "ok", "use_disclosed": "ok",
            "not_decisive": "pend", "missing": "miss"}.get(gate, "bad")
    return f'<span class="fs-gate {kind}">{esc(label)}</span>'


def kpi_card(label: str, value: str, delta: str = "", mood: str = "flat",
             tooltip: str = "") -> str:
    """بطاقة KPI واحدة بأرقام جدولية — القيمة تأتي من نتائج محسوبة فقط."""
    tip = f' title="{esc(tooltip)}"' if tooltip else ""
    delta_html = (f'<div class="fs-kpi-delta {mood}">{esc(delta)}</div>'
                  if delta else "")
    return (
        f'<div class="fs-kpi"{tip}>'
        f'<div class="fs-kpi-label">{esc(label)}</div>'
        f'<div class="fs-kpi-value">{esc(value)}</div>'
        f'{delta_html}</div>'
    )
