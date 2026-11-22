# -*- coding: utf-8 -*-
"""مكونات الواجهة المشتركة القابلة لإعادة الاستخدام (v9.1).

كل مكون يقرأ من نتائج الـPipeline/نموذج العرض فقط — لا بيانات مصطنعة،
لا تغيير في دلالات سجل التحقق أو الحسابات، وكل المدخلات النصية مُهربة عبر esc().
"""
from __future__ import annotations

import html
import re

import streamlit as st

from src.dashboard.design_system import (
    MUTED,
    SUCCESS,
    WARNING,
)

_LOGO_SVG = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
    'aria-hidden="true">'
    '<path d="M3 3v18h18"/>'
    '<path d="M7 15l4-4 3 3 5-6"/>'
    '<circle cx="19" cy="8" r="1.5" fill="currentColor" stroke="none"/>'
    "</svg>"
)

_VERIF_EN = {
    "موثق (بشري)": "Verified (human)",
    "موثق (آلي عبر-طبقتين)": "Verified (auto · 2-layer)",
    "موثق (نقل رقمي)": "Verified (digital)",
    "موثق (آلي)": "Verified (auto)",
    "موثق (معلن — مثبت بالهوية المحاسبية)": "Verified (disclosed · identity)",
    "مشتق معلن": "Derived (disclosed)",
    "يحتاج مراجعة": "Needs review",
    "تعارض — محجوب": "Conflict — blocked",
    "غير متوفر": "Unavailable",
}


def esc(v) -> str:
    return html.escape(str(v), quote=True)


_BIDI_TOKEN_RE = re.compile(
    r"(?<![&#A-Za-z0-9_])"
    r"(?:"
    r"(?:&lt;=?|&gt;=?|[≤≥])\s*[+-]?\d+(?:[.,]\d+)*(?:[%xX]|pp|[KMB])?"
    r"|[+-]?(?:\$|€|£|EGP|SAR|USD|AED)?[+-]?\d+(?:[.,]\d+)*(?:/\d+(?:[.,]\d+)*)?(?:[%xX]|pp|[KMB])?"
    r")"
    r"(?![A-Za-z0-9_;])"
)


def isolate_bidi_html(v) -> str:
    """Escape text and wrap numeric/signed/comparison tokens in <bdi dir='ltr'>
    so RTL sentences never invert +18.0%, -8.3%, or (< 0.50)."""
    escaped = esc(v)
    return _BIDI_TOKEN_RE.sub(
        lambda m: f'<bdi dir="ltr">{m.group(0)}</bdi>', escaped
    )


def verification_badge_info(verif_text: str, lang: str = "ar") -> tuple[str, str, str]:
    """Map verification_labels() output -> (gate_kind, glyph, localized_label).

    Preserves the exact verification contract and semantic colors:
    ok (green) | pend (amber) | bad (red) | miss (muted).
    """
    raw = (verif_text or "").strip()
    if not raw or raw == "—":
        return "miss", "○", ("Unavailable" if lang == "en" else "غير متوفر")
    if raw.startswith("موثق"):
        kind, glyph = "ok", "●"
    elif raw in ("مشتق معلن", "يحتاج مراجعة"):
        kind, glyph = "pend", "◐"
    elif "تعارض" in raw or "محجوب" in raw:
        kind, glyph = "bad", "▲"
    else:
        kind, glyph = "miss", "○"
    label = _VERIF_EN.get(raw, raw) if lang == "en" else raw
    return kind, glyph, label


def render_header(
    product: str | None = None,
    subtitle: str | None = None,
) -> None:
    """Compact top bar: product identity + AI/readiness status + active document."""
    lang = st.session_state.get("ui_lang", "ar")
    if product is None:
        product = (
            "وكيل تحليل بيانات مالية ذكي"
            if lang == "ar"
            else "FinSight AI — Financial Analyzer"
        )
    if subtitle is None:
        subtitle = (
            "ذكاء مالي وتحليل القوائم · معايير المحاسبة المصرية (EAS)"
            if lang == "ar"
            else "Financial Intelligence · EAS"
        )

    analysis = st.session_state.get("analysis")
    results = st.session_state.get("results")

    if analysis is not None and getattr(analysis, "ok", False):
        model = getattr(analysis, "model", "") or "Gemini"
        model_chip = (
            f'<span class="fs-pill">'
            f'<span class="fs-dot" style="background:{SUCCESS}"></span>'
            f"{esc(model)}</span>"
        )
    elif analysis is not None and not getattr(analysis, "ok", False):
        fallback_lbl = (
            "تفسير قاعدي حتمي (Python)"
            if lang == "ar"
            else "Deterministic fallback"
        )
        model_chip = (
            f'<span class="fs-pill">'
            f'<span class="fs-dot" style="background:{WARNING}"></span>'
            f"{esc(fallback_lbl)}</span>"
        )
    elif st.session_state.get("gemini_available") is False:
        lbl = "Gemini — خارج الحصة" if lang == "ar" else "Gemini — quota"
        model_chip = (
            f'<span class="fs-pill">'
            f'<span class="fs-dot" style="background:{WARNING}"></span>'
            f"{esc(lbl)}</span>"
        )
    else:
        lbl = "جاهز للتحليل" if lang == "ar" else "Ready"
        model_chip = (
            f'<span class="fs-pill">'
            f'<span class="fs-dot" style="background:{MUTED}"></span>'
            f"{esc(lbl)}</span>"
        )

    file_chip = ""
    if results:
        fname = esc(results.get("file_name") or results.get("company") or "")
        if fname:
            file_chip = f'<span class="fs-pill">📄 <bdi dir="auto">{fname}</bdi></span>'

    st.markdown(
        f'<div class="fs-header">'
        f'<div class="fs-brand">'
        f'<div class="fs-logo">{_LOGO_SVG}</div>'
        f'<div><div class="fs-brand-name">{esc(product)}</div>'
        f'<div class="fs-brand-sub">{esc(subtitle)}</div></div>'
        f"</div>"
        f'<div class="fs-header-meta">{model_chip}{file_chip}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )


def build_state_html(
    title: str,
    body: str,
    icon: str = "📄",
    next_step: str = "",
    tone: str = "empty",
) -> str:
    """Build a designed state card: icon + title + explanation + optional next step."""
    tone_cls = tone if tone in ("empty", "error", "success", "info") else "empty"
    next_html = (
        f'<div class="fs-state-next">➜ {esc(next_step)}</div>'
        if next_step
        else ""
    )
    return (
        f'<div class="fs-state {tone_cls}">'
        f'<div class="fs-state-ico">{esc(icon)}</div>'
        f'<div class="fs-state-title">{esc(title)}</div>'
        f'<div class="fs-state-body">{esc(body)}</div>'
        f"{next_html}"
        f"</div>"
    )


def render_empty_state(
    title: str,
    body: str,
    icon: str = "📄",
    next_step: str = "",
) -> None:
    st.markdown(
        build_state_html(title, body, icon=icon, next_step=next_step, tone="empty"),
        unsafe_allow_html=True,
    )


def render_error_state(title: str, body: str, next_step: str = "") -> None:
    st.markdown(
        build_state_html(title, body, icon="⚠️", next_step=next_step, tone="error"),
        unsafe_allow_html=True,
    )


def render_success_state(title: str, body: str, next_step: str = "") -> None:
    st.markdown(
        build_state_html(title, body, icon="✓", next_step=next_step, tone="success"),
        unsafe_allow_html=True,
    )


def gate_badge(gate: str, label: str) -> str:
    """Badge for a decision-log gate status — strictly preserves the 4 gate semantics."""
    kind = {
        "use": "ok",
        "use_disclosed": "ok",
        "not_decisive": "pend",
        "missing": "miss",
    }.get(gate, "bad")
    glyph = {"ok": "●", "pend": "◐", "miss": "○"}.get(kind, "▲")
    return f'<span class="fs-gate {kind}">{glyph} {esc(label)}</span>'


def kpi_card(
    label: str,
    value: str,
    delta: str = "",
    mood: str = "flat",
    tooltip: str = "",
    *,
    year: str | int = "",
    explanation: str = "",
    gate_kind: str = "",
    gate_glyph: str = "",
    gate_label: str = "",
) -> str:
    """Unified reusable KPI card: header + big value + explanation/delta + colored status."""
    tip = f' title="{esc(tooltip)}"' if tooltip else ""
    year_html = f'<span class="fs-kpi-year">{esc(year)}</span>' if year not in ("", None) else ""
    val_cls = "fs-kpi-value is-na" if value in ("N/A", "—", "") else "fs-kpi-value"

    arrow = {"up": "▲", "down": "▼", "flat": "◆", "na": "–"}.get(mood, "")
    delta_inner = f"{arrow} <bdi dir=\"ltr\">{esc(delta)}</bdi>" if arrow and delta else esc(delta)
    delta_html = (
        f'<div class="fs-kpi-sub"><span class="fs-kpi-delta {esc(mood)}">{delta_inner}</span></div>'
        if delta
        else ""
    )
    explain_html = (
        f'<div class="fs-kpi-explain">{esc(explanation)}</div>'
        if explanation
        else ""
    )
    foot_html = ""
    if gate_label:
        g_cls = gate_kind if gate_kind in ("ok", "pend", "miss", "bad") else "miss"
        g_ico = f"{esc(gate_glyph)} " if gate_glyph else ""
        foot_html = (
            f'<div class="fs-kpi-foot">'
            f'<span class="fs-gate {g_cls}">{g_ico}{esc(gate_label)}</span>'
            f"</div>"
        )

    return (
        f'<div class="fs-kpi"{tip}>'
        f'<div class="fs-kpi-head">'
        f'<div class="fs-kpi-label">{esc(label)}</div>{year_html}'
        f"</div>"
        f'<div class="{val_cls}"><bdi dir="ltr">{esc(value)}</bdi></div>'
        f"{delta_html}"
        f"{explain_html}"
        f"{foot_html}"
        f"</div>"
    )


def stat_card(
    label: str,
    value: str,
    subtext: str = "",
    gate_kind: str = "",
    gate_label: str = "",
) -> str:
    """Compact summary stat card matching the unified card geometry."""
    return kpi_card(
        label,
        value,
        explanation=subtext,
        gate_kind=gate_kind,
        gate_glyph={"ok": "●", "pend": "◐", "miss": "○", "bad": "▲"}.get(gate_kind, ""),
        gate_label=gate_label,
    )


def _infer_stage_and_pct(msg: str, fast_mode: bool = False) -> tuple[int, int]:
    """Infer pipeline stage index (0..3) and percentage (10..100) from live progress message."""
    text = msg or ""
    if "تم الاستخراج" in text or "التعليق التحليلي" in text or "الوضع السريع" in text:
        return 3, (100 if fast_mode else 90)
    if "من الكاش المحلي" in text or "محلول قبلًا" in text:
        return 3, 94
    if "إعادة قراءة" in text:
        m_retry = re.search(r"(\d+)\s*/\s*(\d+)", text)
        if m_retry:
            done = int(m_retry.group(1))
            total = max(1, int(m_retry.group(2)))
            return 1, int(71 + min(1.0, done / total) * 4)
        return 1, 71
    if any(k in text for k in ("التحقق", "disputed", "التدفقات", "third opinion")):
        return 2, 78
    m = re.search(r"(\d+)\s+من\s+(\d+)", text)
    if m:
        done = int(m.group(1))
        total = max(1, int(m.group(2)))
        ratio = min(1.0, max(0.0, done / total))
        return 1, int(18 + ratio * 52)
    if any(k in text for k in ("triaging", "Local OCR", "الصفحة", "استخراج")):
        return 1, 22
    return 0, 10


def build_progress_html(
    filename: str,
    elapsed_str: str,
    msg: str,
    *,
    fast_mode: bool = False,
    batch_idx: int = 0,
    batch_total: int = 0,
    lang: str = "ar",
) -> str:
    """Render the styled multi-minute waiting card with timer, progress bar, and 4 stages."""
    stage_idx, pct = _infer_stage_and_pct(msg, fast_mode=fast_mode)
    is_ar = lang != "en"

    stages = (
        [
            "١. فحص المستند",
            "٢. القراءة والاستخراج",
            "٣. التحقق وبوابة الصدق",
            "٤. النسب والوضع السريع" if fast_mode else "٤. النسب ورؤى الذكاء",
        ]
        if is_ar
        else [
            "1. Document check",
            "2. Read & extract",
            "3. Gate verification",
            "4. Ratios (fast)" if fast_mode else "4. Ratios & AI",
        ]
    )

    stage_items = []
    for idx, label in enumerate(stages):
        cls = "done" if idx < stage_idx else ("active" if idx == stage_idx else "")
        dot = "✓" if idx < stage_idx else str(idx + 1)
        stage_items.append(
            f'<div class="fs-stage {cls}">'
            f'<span class="fs-stage-dot">{dot}</span>'
            f"<span>{esc(label)}</span>"
            f"</div>"
        )

    clean_elapsed = elapsed_str.replace("⏱", "").strip()
    batch_prefix = (
        f"[{batch_idx}/{batch_total}] "
        if batch_total > 1 and batch_idx > 0
        else ""
    )
    title = (
        "جارٍ التحليل المالي الموثق..."
        if is_ar
        else "Running verified financial analysis..."
    )
    pct_lbl = f"{pct}%"
    stage_lbl = (
        f"المرحلة {stage_idx + 1} من 4"
        if is_ar
        else f"Stage {stage_idx + 1} of 4"
    )
    hint = (
        "قد تستغرق الملفات الممسوحة بضع دقائق للتحقق من تطابق القوائم — التقدّم يتحدث تلقائيًا."
        if is_ar
        else "Scanned PDFs may take a few minutes for multi-layer verification — progress updates live."
    )

    display_msg = (
        msg
        if (msg and msg.strip() not in ("", "…", "..."))
        else ("جارٍ تهيئة المعالجة…" if is_ar else "Initializing analysis...")
    )

    return (
        '<div class="fs-progress-card">'
        '<div class="fs-progress-head">'
        "<div>"
        f'<div class="fs-progress-title">{esc(title)}</div>'
        f'<div class="fs-progress-file">{esc(batch_prefix)}{esc(filename)}</div>'
        "</div>"
        f'<div class="fs-timer-pill"><span class="live-dot"></span>'
        f'<span>⏱ <bdi dir="ltr">{esc(clean_elapsed)}</bdi></span></div>'
        "</div>"
        '<div class="fs-progress-meta">'
        f"<span>{esc(stage_lbl)}</span>"
        f'<span><bdi dir="ltr">{esc(pct_lbl)}</bdi></span>'
        "</div>"
        '<div class="fs-progress-track">'
        f'<div class="fs-progress-fill" style="width:{pct}%"></div>'
        "</div>"
        f'<div class="fs-stages">{"".join(stage_items)}</div>'
        f'<div class="fs-progress-msg">{esc(display_msg)}</div>'
        f'<div class="fs-progress-hint">{esc(hint)}</div>'
        "</div>"
    )


def build_health_html(hs, lang: str = "ar") -> str:
    """Render the Financial Health Score hero + 4 weighted pillar progress bars."""
    is_ar = lang != "en"
    cov_pct = round(getattr(hs, "coverage", 1.0) * 100)

    if hs.total is not None:
        label_txt = hs.label_ar if is_ar else hs.label_en
        badge_cls = (
            "ok" if hs.total >= 60 else ("pend" if hs.total >= 40 else "bad")
        )
        cov_lbl = (
            f"تغطية البيانات: {cov_pct}%"
            if is_ar
            else f"Data coverage: {cov_pct}%"
        )
        complete_txt = (
            "درجة كلية مكتملة الأركان"
            if (is_ar and hs.complete)
            else (
                "درجة جزئية (غابت ركيزة غير حرجة)"
                if is_ar
                else ("Complete 4-pillar score" if hs.complete else "Partial score")
            )
        )
        hero_html = (
            '<div class="fs-health-hero">'
            '<div class="fs-health-score-box" dir="ltr">'
            f'<span class="fs-health-num">{int(round(hs.total))}</span>'
            '<span class="fs-health-denom">/100</span>'
            "</div>"
            '<div class="fs-health-meta">'
            f'<div class="fs-health-meta-title">'
            f'<span class="fs-gate {badge_cls}">● {esc(label_txt)}</span>'
            "</div>"
            f'<div class="fs-health-meta-sub">{esc(cov_lbl)} · {esc(complete_txt)}</div>'
            "</div>"
            "</div>"
        )
    else:
        sep = "، " if is_ar else ", "
        blocked_names = (
            sep.join(
                (p.name_ar if is_ar else p.name_en)
                for p in hs.pillars
                if p.score is None
            )
            or "—"
        )
        ref_title = (
            "الدرجة الصحية محجوبة وفق سياسة تغطية البيانات"
            if is_ar
            else "Health Score refused under data-coverage policy"
        )
        ref_body = (
            f"لا تصدر درجة إجمالية عند غياب أو عدم حسم ركيزة حرجة (السيولة/المديونية) حتى لا تُخفى المخاطر. الأركان المحجوبة: {blocked_names}."
            if is_ar
            else f"No composite score is issued when a critical pillar (Liquidity/Leverage) is missing or unverified. Blocked pillars: {blocked_names}."
        )
        ref_next = (
            "الخطوة التالية: راجع الخانات غير الحاسمة في «القوائم والخانات» أو «مراجعة بشرية»."
            if is_ar
            else "Next step: resolve pending cells in Statements & Cells or Human Review."
        )
        hero_html = build_state_html(
            ref_title, ref_body, icon="🛡️", next_step=ref_next, tone="error"
        )

    _pillar_icons = {
        "liquidity": "💧",
        "leverage": "⚖️",
        "profitability": "📈",
        "cash": "💵",
    }
    pillar_cards = []
    for p in hs.pillars:
        p_ico = _pillar_icons.get(getattr(p, "key", ""), "📊")
        p_name = p.name_ar if is_ar else p.name_en
        w_txt = f"الوزن {p.weight:.0f}%" if is_ar else f"Weight {p.weight:.0f}%"
        if p.score is None:
            score_txt = "محجوب / غير متاح" if is_ar else "Blocked / N/A"
            pct = 0.0
            tone = "tone-miss"
            status_badge = (
                f'<span class="fs-gate pend">◐ {"غير محسوبة" if is_ar else "Blocked"}</span>'
            )
        else:
            score_txt = f"{p.score:.0f}/100"
            pct = max(4.0, min(100.0, float(p.score)))
            if p.score >= 75:
                tone, g_cls, g_lbl = "tone-ok", "ok", ("قوي" if is_ar else "Strong")
            elif p.score >= 50:
                tone, g_cls, g_lbl = "tone-mid", "ok", ("مستقر" if is_ar else "Stable")
            elif p.score >= 35:
                tone, g_cls, g_lbl = "tone-warn", "pend", ("يحتاج متابعة" if is_ar else "Watch")
            else:
                tone, g_cls, g_lbl = "tone-bad", "bad", ("ضعيف" if is_ar else "Weak")
            status_badge = f'<span class="fs-gate {g_cls}">● {esc(g_lbl)}</span>'

        def _loc_detail(d: str) -> str:
            if not is_ar:
                return d
            return (
                str(d)
                .replace("Quick Ratio", "السيولة السريعة")
                .replace("Debt Ratio", "نسبة المديونية")
                .replace("guideline ", "المعيار ")
                .replace(": N/A", ": غير متاح")
            )

        chips = "".join(
            f'<span class="fs-detail-chip">{esc(_loc_detail(d))}</span>' for d in (p.details or [])
        )
        details_html = f'<div class="fs-pillar-details">{chips}</div>' if chips else ""
        pillar_cards.append(
            f'<div class="fs-pillar-card {tone}">'
            '<div class="fs-pillar-head">'
            f'<span class="fs-pillar-name">{p_ico} {esc(p_name)}</span>'
            f'<span class="fs-pillar-weight">{esc(w_txt)}</span>'
            "</div>"
            '<div class="fs-pillar-score-row">'
            f'<span class="fs-pillar-score"><bdi dir="ltr">{esc(score_txt)}</bdi></span>'
            f"{status_badge}"
            "</div>"
            '<div class="fs-pillar-track">'
            f'<div class="fs-pillar-fill {tone}" style="width:{pct:.1f}%"></div>'
            "</div>"
            f"{details_html}"
            "</div>"
        )

    return f'{hero_html}<div class="fs-pillars-grid">{"".join(pillar_cards)}</div>'


def build_metrics_table_html(
    metrics_rows: list[dict],
    prev_year: int | str,
    curr_year: int | str,
    unit_scale: int,
    currency: str,
    lang: str = "ar",
    filter_cat: str = "all",
    filter_verif: str = "all",
    query: str = "",
) -> tuple[str, int]:
    """Build custom RTL/LTR financial metrics HTML table (no st.dataframe).

    Returns (html_string, visible_row_count).
    """
    from src.dashboard.charts import fmt_value, fmt_value_ar, humanize
    from src.dashboard.theme import badge as status_badge, fin_table

    is_ar = lang != "en"
    q = (query or "").strip().lower()

    def _fmt_metric_val(v: float | None, kind: str) -> str:
        if v is None:
            return "N/A"
        if kind == "currency":
            if is_ar:
                return fmt_value_ar(v, "currency", currency, unit_scale)
            return f"{currency}{humanize(v, unit_scale)}"
        return fmt_value(v, kind, currency)

    filtered = []
    for r in metrics_rows:
        cat_val = r.get("category_ar") if is_ar else r.get("category")
        if filter_cat not in ("all", "كل الفئات", "All categories") and cat_val != filter_cat:
            continue
        v_kind, v_glyph, v_lbl = verification_badge_info(r.get("verif", ""), lang)
        if filter_verif == "ok" and v_kind != "ok":
            continue
        if filter_verif == "pend" and v_kind not in ("pend", "bad"):
            continue
        if filter_verif == "miss" and v_kind != "miss":
            continue
        label_txt = (r.get("label") if is_ar else (r.get("label_en") or r.get("label"))) or ""
        if q and q not in label_txt.lower() and q not in (r.get("key") or "").lower():
            continue
        filtered.append((r, label_txt, cat_val or "—", v_kind, v_glyph, v_lbl))

    if not filtered:
        return "", 0

    prev_lbl = "—" if prev_year in (None, "") else str(prev_year)
    curr_lbl = "—" if curr_year in (None, "") else str(curr_year)
    headers = (
        ["الفئة", "المؤشر", prev_lbl, curr_lbl, "التغير %", "الاتجاه", "التقييم", "حالة التحقق"]
        if is_ar
        else ["Category", "Metric", prev_lbl, curr_lbl, "Change %", "Trend", "Assessment", "Verification"]
    )
    rows_html = []
    for r, label_txt, cat_val, v_kind, v_glyph, v_lbl in filtered:
        prev_txt = _fmt_metric_val(r.get("prev"), r.get("kind", "ratio"))
        curr_txt = _fmt_metric_val(r.get("curr"), r.get("kind", "ratio"))
        chg = r.get("change_pct")
        chg_txt = f"{chg:+.1f}%" if chg is not None else "—"
        st_name = r.get("status") or "N/A"
        chg_cls = (
            "change-pos"
            if st_name == "Positive"
            else ("change-neg" if st_name == "Negative" else "")
        )
        t_sym = r.get("trend") or "–"
        t_cls = {"▲": "trend-up", "▼": "trend-down", "→": "trend-flat"}.get(t_sym, "trend-flat")
        rows_html.append(
            "<tr>"
            f'<td class="cat">{esc(cat_val)}</td>'
            f"<td><b>{esc(label_txt)}</b></td>"
            f'<td class="num"><bdi dir="ltr">{esc(prev_txt)}</bdi></td>'
            f'<td class="num"><b><bdi dir="ltr">{esc(curr_txt)}</bdi></b></td>'
            f'<td class="num {chg_cls}"><bdi dir="ltr">{esc(chg_txt)}</bdi></td>'
            f'<td class="{t_cls}">{esc(t_sym)}</td>'
            f"<td>{status_badge(st_name, lang=lang)}</td>"
            f'<td><span class="fs-gate {v_kind}">{v_glyph} {esc(v_lbl)}</span></td>'
            "</tr>"
        )
    return fin_table(headers, rows_html, num_cols={2, 3, 4}), len(filtered)
