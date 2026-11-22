# -*- coding: utf-8 -*-
"""FinSight AI — واجهة Streamlit الرئيسية (v9.1): تصميم FinTech فاتح احترافي
متصل بالـPipeline الحي.

المبادئ الصارمة:
- مكونات قابلة لإعادة الاستخدام من components/chrome.py + نظام تصميم موحد في design_system.py.
- لا مساس بمنطق الأرقام أو دلالات حالات سجل التحقق (حاسمة / تحتاج مراجعة / مفقود).
- عربي RTL أولًا مع دعم تبديل كامل إلى EN-LTR.
- الجداول المخصصة للعربي (HTML RTL برؤوس ملتصقة وأرقام معزولة) — بلا st.dataframe.
- كل الحالات مصممة: فارغ / انتظار / خطأ / بيانات جزئية / نجاح.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sys
import tempfile
from pathlib import Path

import streamlit as st

PROJ = Path(__file__).resolve().parents[2]
if str(PROJ) not in sys.path:
    sys.path.insert(0, str(PROJ))

from src.dashboard.charts import fmt_value, humanize  # noqa: E402
from src.dashboard.components.chrome import (  # noqa: E402
    build_health_html,
    build_metrics_table_html,
    esc,
    gate_badge,
    isolate_bidi_html,
    kpi_card,
    render_empty_state,
    render_error_state,
    render_header,
    render_success_state,
    stat_card,
    verification_badge_info,
)
from src.dashboard.view_model import (  # noqa: E402
    build_view_model,
    categorized_insights,
    cell_value_display,
    executive_summary,
    report_memo,
)

_T = {
    "overview": {"ar": "نظرة عامة", "en": "Overview"},
    "statements": {"ar": "القوائم والخانات", "en": "Statements & Cells"},
    "metrics": {"ar": "المؤشرات المالية", "en": "Financial Metrics"},
    "health": {"ar": "الدرجة الصحية", "en": "Health Score"},
    "insights": {"ar": "رؤى Gemini", "en": "AI Insights"},
    "chat": {"ar": "محادثة المستند", "en": "Document Chat"},
    "review": {"ar": "مراجعة بشرية", "en": "Human Review"},
    "reports": {"ar": "التقارير", "en": "Reports"},
    "portfolio": {"ar": "مقارنة الشركات", "en": "Companies"},
    "new_analysis": {"ar": "تحليل جديد", "en": "New Analysis"},
    "classic": {"ar": "الواجهة الكلاسيكية", "en": "Classic UI"},
    "summary": {"ar": "الملخص التنفيذي", "en": "Executive Summary"},
    "gate_title": {"ar": "حالة التوثيق", "en": "Verification status"},
    "pending": {"ar": "بانتظار المراجعة", "en": "Awaiting review"},
    "provisional": {
        "ar": "تحليل تجريبي غير معتمد — مولد من قيم حالتها «يحتاج "
              "مراجعة»؛ يُقرأ كمؤشرات استكشافية وليس حكمًا نهائيًا.",
        "en": "Provisional, non-authoritative analysis — generated from "
              "needs-review values; exploratory, not a final verdict.",
    },
    "evidence": {"ar": "دليل المصدر", "en": "Source evidence"},
    "open_evidence": {"ar": "الدليل", "en": "Evidence"},
    "unit": {"ar": "وحدة القوائم", "en": "Statement unit"},
    "doc_sha": {"ar": "بصمة المستند", "en": "Document hash"},
    "strengths": {"ar": "نقاط القوة", "en": "Strengths"},
    "weaknesses": {"ar": "نقاط الضعف والمخاطر", "en": "Weaknesses & risks"},
    "neutral": {"ar": "مؤشرات مستقرة", "en": "Stable metrics"},
    "recommendations": {"ar": "التوصيات", "en": "Recommendations"},
    "health_refused": {
        "ar": "الدرجة الصحية محجوبة",
        "en": "Health Score refused",
    },
}

_GATE_EN = {
    "use": "Verified — decisive",
    "use_disclosed": "Verified (disclosed) — decisive",
    "not_decisive": "Needs review — blocked",
    "missing": "Not captured",
}


def _t(key: str) -> str:
    lang = st.session_state.get("ui_lang", "ar")
    return _T.get(key, {}).get(lang, key)


def _lang() -> str:
    return st.session_state.get("ui_lang", "ar")


def _extract_bbox_coords(
    bbox, page_no: int, img_w: int, img_h: int, target_scale: float
) -> tuple[float, float, float, float] | None:
    """Normalize any candidate_bbox shape (list, nested list, or dict with bbox_px)
    to pixel coordinates matching an image rendered at `target_scale`."""
    if not bbox:
        return None
    item = bbox
    if isinstance(bbox, list):
        if not bbox:
            return None
        if isinstance(bbox[0], dict):
            matched = [b for b in bbox if b.get("page") == page_no]
            item = matched[0] if matched else bbox[0]
        elif isinstance(bbox[0], list):
            item = bbox[0]

    if isinstance(item, dict):
        coords = item.get("bbox_px") or item.get("bbox") or item.get("box")
        if not coords or len(coords) < 4:
            return None
        rscale = float(item.get("render_scale") or 2.0) or 2.0
        x0, y0, x1, y1 = [float(v) * (target_scale / rscale) for v in coords[:4]]
        return (x0, y0, x1, y1)

    if isinstance(item, (list, tuple)) and len(item) >= 4:
        x0, y0, x1, y1 = [float(v) for v in item[:4]]
        if max(abs(x0), abs(y0), abs(x1), abs(y1)) <= 1.05:
            return (x0 * img_w, y0 * img_h, x1 * img_w, y1 * img_h)
        if x1 > img_w or y1 > img_h:
            sx = img_w / max(x1, img_w, 1.0)
            sy = img_h / max(y1, img_h, 1.0)
            return (x0 * sx, y0 * sy, x1 * sx, y1 * sy)
        return (x0, y0, x1, y1)
    return None


def _is_pdf_bytes(raw: bytes | None) -> bool:
    return bool(raw and raw.lstrip()[:5].startswith(b"%PDF-"))


def _render_page_with_bbox(raw: bytes, page_no: int, bbox) -> bytes | None:
    import pypdfium2 as pdfium
    from PIL import ImageDraw

    if not _is_pdf_bytes(raw):
        return None
    target_scale = 2.0
    try:
        pdf = pdfium.PdfDocument(io.BytesIO(raw))
    except Exception:
        return None
    try:
        if page_no < 1 or page_no > len(pdf):
            return None
        img = pdf[page_no - 1].render(scale=target_scale).to_pil().convert("RGB")
    finally:
        pdf.close()
    coords = _extract_bbox_coords(bbox, page_no, img.width, img.height, target_scale)
    if coords:
        try:
            x0, y0, x1, y1 = coords
            d = ImageDraw.Draw(img)
            d.rectangle([x0, y0, x1, y1], outline="#DC2626", width=4)
        except Exception:
            pass
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _render_crop(raw: bytes, page_no: int, bbox) -> bytes | None:
    import pypdfium2 as pdfium

    if not bbox or not _is_pdf_bytes(raw):
        return None
    target_scale = 3.0
    try:
        pdf = pdfium.PdfDocument(io.BytesIO(raw))
    except Exception:
        return None
    try:
        if page_no < 1 or page_no > len(pdf):
            return None
        img = pdf[page_no - 1].render(scale=target_scale).to_pil().convert("RGB")
    finally:
        pdf.close()
    coords = _extract_bbox_coords(bbox, page_no, img.width, img.height, target_scale)
    if not coords:
        return None
    try:
        x0, y0, x1, y1 = coords
        pad = 8
        crop = img.crop(
            (
                max(0, int(x0) - pad),
                max(0, int(y0) - pad),
                min(img.width, int(x1) + pad),
                min(img.height, int(y1) + pad),
            )
        )
        buf = io.BytesIO()
        crop.save(buf, "PNG")
        return buf.getvalue()
    except Exception:
        return None


def _cached_evidence_images(
    raw: bytes, doc_sha: str, page_no: int, bbox
) -> tuple[bytes | None, bytes | None]:
    """Session-cache rendered PNG bytes per (doc_sha, page_no, bbox) to avoid
    re-rasterizing PDF pages on every Streamlit rerun."""
    bbox_key = json.dumps(bbox, sort_keys=True, default=str) if bbox else "none"
    cache_key = f"{doc_sha}|{page_no}|{bbox_key}"
    cache: dict = st.session_state.setdefault("_ev_img_cache", {})
    if cache_key not in cache:
        if len(cache) >= 12:
            cache.pop(next(iter(cache)))
        page_img = _render_page_with_bbox(raw, page_no, bbox)
        crop_img = _render_crop(raw, page_no, bbox) if bbox else None
        cache[cache_key] = (page_img, crop_img)
    return cache[cache_key]


def evidence_block(cell: dict, raw: bytes | None, doc_sha: str) -> None:
    """دليل المصدر: فحص هاش المستند + الصفحة الأصلية + bbox + القصاصة.
    لا يعرض دليل من مستند آخر أبدًا."""
    lang = _lang()
    is_ar = lang != "en"
    lbl = cell["label"] if is_ar else cell.get("label_en", cell["label"])
    st.markdown(f"**{_t('evidence')} — {lbl} · {cell['year']}**")

    if raw is None:
        render_empty_state(
            "بايتات المستند غير متوفرة" if is_ar else "Document bytes unavailable",
            "بايتات المستند غير محفوظة في الجلسة الحالية (مثل حالة التحميل من الكاش)."
            if is_ar
            else "Original document bytes are not in the active session.",
            icon="📎",
            next_step="أعد رفع الملف من «تحليل جديد» لمعاينة صورة الصفحة الأصلية."
            if is_ar
            else "Re-upload the file via New Analysis to preview source pages.",
        )
        return

    current_sha = hashlib.sha256(raw).hexdigest()[:16]
    if doc_sha and current_sha != doc_sha:
        render_error_state(
            "عدم تطابق بصمة المستند" if is_ar else "Document hash mismatch",
            "بصمة المستند لا تطابق بصمة الاستخراج — الدليل محجوب حفاظًا على سلامة التدقيق."
            if is_ar
            else "Document hash does not match extraction provenance — evidence blocked.",
            next_step="أعد رفع الملف الأصلي عبر «تحليل جديد»."
            if is_ar
            else "Re-upload the original file via New Analysis.",
        )
        return

    st.caption(f"{_t('doc_sha')}: `{current_sha}` ✓")
    pages = cell.get("pages") or []
    if not pages:
        render_empty_state(
            "لا صفحة مصدر مسجلة" if is_ar else "No source page recorded",
            "استخراج رقمي/نصي مباشر من الجدول دون إسناد صفحة مصوّرة."
            if is_ar
            else "Captured from digital table/text without scanned page coordinates.",
            icon="📄",
            next_step="راجع حقل «المصدر» في تفاصيل الخانة أو ملف Excel/CSV الأصلي."
            if is_ar
            else "Check the original spreadsheet or text source for this cell.",
        )
        return

    bbox = cell.get("bbox")
    bbox_page = None
    if isinstance(bbox, list) and bbox and isinstance(bbox[0], dict):
        bbox_page = bbox[0].get("page")
    elif isinstance(bbox, dict):
        bbox_page = bbox.get("page")
    page_no = int(bbox_page) if bbox_page else int(pages[0])
    img, crop = _cached_evidence_images(raw, current_sha, page_no, bbox)
    col_page, col_crop = st.columns([3, 2])
    with col_page:
        if img:
            st.image(img, caption=f"{_t('evidence')} — {'صفحة' if is_ar else 'p'}{page_no}")
        else:
            render_empty_state(
                "تعذّر عرض الصفحة" if is_ar else "Page render unavailable",
                f"الصفحة {page_no} غير موجودة في ملف PDF أو الملف ليس بصيغة PDF."
                if is_ar
                else f"Page {page_no} could not be rendered from this file.",
                icon="🖼️",
            )
    with col_crop:
        if crop:
            st.image(crop, caption="القصاصة المركّزة" if is_ar else "Focused crop")
        elif bbox is None:
            render_empty_state(
                "لا توجد إحداثيات قصّ (bbox)" if is_ar else "No bounding-box crop",
                "مستند نصي رقمي أو قراءة صفحة كاملة دون إحداثيات موضعية للخانة."
                if is_ar
                else "Digital text PDF or full-page capture without box coordinates.",
                icon="🔍",
            )


def sec_overview(vm: dict, results: dict) -> None:
    """اللوحة الرئيسية: الملخص التنفيذي (حقائق فقط) + بطاقات KPI موحدة + حالة البوابة."""
    lang = _lang()
    is_ar = lang != "en"

    co_name = vm.get("company") or results.get("company") or results.get("file_name") or ""
    p_yr, c_yr = vm.get("prev_year"), vm.get("curr_year")
    period_str = f"{p_yr} → {c_yr}" if (p_yr and c_yr) else str(c_yr or "")
    if co_name or period_str:
        st.markdown(
            f'<div class="report-card" style="--accent:var(--fs-primary);margin-bottom:12px;'
            f'display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">'
            f'<div><b style="font-size:1.08rem;">🏢 {esc(str(co_name))}</b></div>'
            f'<div style="color:var(--fs-muted);font-weight:600;">'
            f'📅 {("الفترة المالية:" if is_ar else "Fiscal period:")} <bdi dir="ltr">{esc(period_str)}</bdi>'
            f' &nbsp;·&nbsp; 💱 {esc(str(vm.get("currency") or ""))}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )

    st.subheader(_T["summary"][lang])
    facts = executive_summary(results, vm, lang=lang)
    if facts:
        items_html = "".join(f'<li dir="auto">{isolate_bidi_html(f)}</li>' for f in facts)
        st.markdown(
            f'<div class="report-card" style="--accent:var(--fs-primary)">'
            f'<ul style="margin:0;padding-inline-start:20px;">{items_html}</ul>'
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        render_empty_state(
            "لا تتوفر حقائق ملخصة بعد" if is_ar else "No executive summary yet",
            "لم يتم استخراج مؤشرات كافية لتلخيص وضع الشركة."
            if is_ar
            else "Not enough metrics were extracted to summarize.",
            icon="📋",
            next_step="افحص تبويب «القوائم والخانات» للتحقق من القيم الملتقطة."
            if is_ar
            else "Inspect the Statements & Cells tab to review captured figures.",
        )

    st.divider()
    st.subheader("📌 " + ("مؤشرات رئيسية" if is_ar else "Key indicators"))
    curr_year = vm["curr_year"]
    rows = {r.key: r for r in results.get("rows", [])}
    sc, cur = vm["unit_scale"], vm["currency"]

    def fmt_card_val(v: float | None, kind: str) -> str:
        if v is None:
            return "N/A"
        if kind == "currency":
            return (
                cell_value_display(v, sc, cur)
                if is_ar
                else f"{cur}{humanize(v, sc)}"
            )
        return fmt_value(v, kind, cur)

    def delta_of(key: str) -> tuple[str, str]:
        r = rows.get(key)
        if r is None or r.change_pct is None:
            return "", "flat"
        if r.status == "Positive":
            mood = "up"
        elif r.status == "Negative":
            mood = "down"
        else:
            mood = "flat"
        return f"{r.change_pct:+.1f}%", mood

    cards = [
        ("الإيرادات" if is_ar else "Revenue", "revenue", "currency"),
        ("صافي الربح" if is_ar else "Net profit", "net_income", "currency"),
        ("إجمالي الأصول" if is_ar else "Total assets", "total_assets", "currency"),
        ("نسبة التداول" if is_ar else "Current ratio", "current_ratio", "ratio"),
        ("نسبة الدين" if is_ar else "Debt ratio", "debt_ratio", "ratio"),
        ("هامش صافي الربح" if is_ar else "Net margin", "net_margin", "percent"),
    ]

    cards_html = []
    prev_m = results.get("prev_metrics")
    curr_m = results.get("curr_metrics")
    for label, key, kind in cards:
        r = rows.get(key)
        verif_raw = vm["verification"].get(key, "")
        g_kind, g_glyph, g_lbl = verification_badge_info(verif_raw, lang)
        if r is not None and (r.previous is not None or r.current is not None):
            curr_val = r.current
            d_txt, mood = delta_of(key)
        elif curr_m is not None and (
            getattr(curr_m, key, None) is not None
            or getattr(prev_m, key, None) is not None
        ):
            curr_val = getattr(curr_m, key, None)
            prev_val = getattr(prev_m, key, None)
            if curr_val is not None and prev_val not in (None, 0):
                pct = (curr_val - prev_val) / abs(prev_val) * 100
                d_txt = f"{pct:+.1f}%"
                mood = "up" if pct > 0 else ("down" if pct < 0 else "flat")
            else:
                d_txt, mood = "", "flat"
        else:
            na_txt = "مؤشر غير قابل للحساب" if is_ar else "Not computable"
            cards_html.append(
                kpi_card(
                    label,
                    "N/A",
                    delta="",
                    mood="na",
                    tooltip=verif_raw,
                    year=curr_year,
                    explanation=na_txt,
                    gate_kind=g_kind,
                    gate_glyph=g_glyph,
                    gate_label=g_lbl,
                )
            )
            continue
        val = fmt_card_val(curr_val, kind)
        if curr_val is None:
            explain = "لا تتوفر قيمة لهذه السنة" if is_ar else "Unavailable for current year"
        elif d_txt:
            explain = f"مقارنة بـ {vm['prev_year']}" if is_ar else f"vs {vm['prev_year']}"
        else:
            explain = (
                "لا تتوفر مقارنة بالسنة السابقة"
                if is_ar
                else "No prior-year comparison"
            )
        cards_html.append(
            kpi_card(
                label,
                val,
                delta=d_txt,
                mood=mood,
                tooltip=verif_raw,
                year=curr_year,
                explanation=explain,
                gate_kind=g_kind,
                gate_glyph=g_glyph,
                gate_label=g_lbl,
            )
        )

    st.markdown(
        f'<div class="fs-kpi-grid">{"".join(cards_html)}</div>',
        unsafe_allow_html=True,
    )

    _render_overview_visuals_and_table(vm, results, is_ar, lang)

    st.divider()
    total_cells = vm["cell_count"]
    decisive_cells = vm["decisive_count"]
    pending_cells = vm["pending_count"]
    cov_pct = round(decisive_cells / total_cells * 100) if total_cells else 0

    summary_cards = [
        stat_card(
            _T["gate_title"][lang] + (" — خانات حاسمة" if is_ar else " — decisive"),
            f"{decisive_cells}/{total_cells}",
            subtext=(
                f"تغطية الاعتماد الآلي/الموثق: {cov_pct}%"
                if is_ar
                else f"Decisive verification coverage: {cov_pct}%"
            ),
            gate_kind="ok" if pending_cells == 0 and total_cells > 0 else "pend",
            gate_label=(
                ("مكتملة" if is_ar else "Complete")
                if pending_cells == 0 and total_cells > 0
                else ("تحت المراجعة" if is_ar else "Partial")
            ),
        ),
        stat_card(
            _T["pending"][lang],
            str(pending_cells),
            subtext=(
                "خانات محجوبة عن الحسم النهائي"
                if is_ar
                else "Cells blocked from final verdict"
            ),
            gate_kind="ok" if pending_cells == 0 else "pend",
            gate_label=(
                ("صفر معلق" if is_ar else "None pending")
                if pending_cells == 0
                else ("تحتاج مراجعة" if is_ar else "Needs review")
            ),
        ),
        stat_card(
            _T["unit"][lang],
            f"x{vm['unit_scale']}",
            subtext=vm["unit_note"]
            or ("الوحدة المطبوعة القياسية (1:1)" if is_ar else "Standard printed scale (1:1)"),
            gate_kind="ok",
            gate_label="مضبوطة" if is_ar else "Scale locked",
        ),
    ]
    st.markdown(
        f'<div class="fs-stats-grid">{"".join(summary_cards)}</div>',
        unsafe_allow_html=True,
    )

    if pending_cells:
        from src.analysis.comparison import LABELS_AR as _OV_LBL

        raw_fields = sorted({e["field"] for e in vm["pending"]})
        disp_fields = [_OV_LBL.get(f, f) if is_ar else f for f in raw_fields[:8]]
        sep = "، " if is_ar else ", "
        names = sep.join(disp_fields)
        st.warning(
            f"{_T['pending'][lang]}: {pending_cells} — {names}"
            + ((sep + "…") if len(raw_fields) > 8 else "")
        )

    _render_formal_certificate(vm, is_ar)


def _sec_banner(title: str, subtitle: str = "") -> None:
    """Render a clean executive section banner with accent border."""
    sub_html = f'<span class="fs-sec-banner-sub">{esc(subtitle)}</span>' if subtitle else ""
    st.markdown(
        f'<div class="fs-sec-banner">'
        f'<div class="fs-sec-banner-title">{esc(title)}</div>'
        f'{sub_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_overview_visuals_and_table(vm: dict, results: dict, is_ar: bool, lang: str) -> None:
    """v9.20 Executive Visual Dashboard (charts) + category-banded Financial Statements summary table."""
    from src.dashboard import charts

    prev_m = results.get("prev_metrics")
    curr_m = results.get("curr_metrics")
    if prev_m is None and curr_m is None:
        return

    prev_y = vm.get("prev_year")
    curr_y = vm.get("curr_year")
    sc = vm.get("unit_scale") or 1
    cur = vm.get("currency") or "$"

    # 1. Interactive Executive Visual Charts (Income Performance + Capital Structure)
    fig_inc = charts.income_summary_chart(
        prev_m, curr_m, prev_y, curr_y, currency=cur, scale=sc, lang=lang
    )
    fig_bal = charts.balance_structure_chart(
        prev_m, curr_m, prev_y, curr_y, currency=cur, scale=sc, lang=lang
    )
    if fig_inc is not None or fig_bal is not None:
        _sec_banner(
            "📊 اللوحة البصرية التنفيذية" if is_ar else "📊 Executive Visual Snapshot",
            (
                f"مقارنة الأداء التشغيلي وهيكل التمويل ({prev_y} مقابل {curr_y})"
                if is_ar
                else f"Operating performance & capital structure ({prev_y} vs {curr_y})"
            ),
        )
        _cfg = {"displayModeBar": False}
        if fig_inc is not None and fig_bal is not None:
            c_left, c_right = st.columns(2)
            with c_left:
                st.plotly_chart(fig_inc, use_container_width=True, key="ov_income_chart", config=_cfg)
            with c_right:
                st.plotly_chart(fig_bal, use_container_width=True, key="ov_balance_chart", config=_cfg)
        elif fig_inc is not None:
            st.plotly_chart(fig_inc, use_container_width=True, key="ov_income_chart", config=_cfg)
        else:
            st.plotly_chart(fig_bal, use_container_width=True, key="ov_balance_chart", config=_cfg)

    # 2. Executive Financial Statements Summary Table (Category-banded RTL HTML)
    sections = [
        (
            "📈 قائمة الدخل" if is_ar else "📈 Income Statement",
            [
                ("revenue", "الإيرادات" if is_ar else "Revenue", True),
                ("cost_of_goods_sold", "تكلفة الإيرادات" if is_ar else "Cost of Goods Sold", False),
                ("gross_profit", "مجمل الربح" if is_ar else "Gross Profit", True),
                ("operating_income", "الربح التشغيلي" if is_ar else "Operating Income", True),
                ("ebitda", "الأرباح قبل الفوائد والضرائب والإهلاك (EBITDA)" if is_ar else "EBITDA", True),
                ("net_income", "صافي الربح" if is_ar else "Net Income", True),
            ],
        ),
        (
            "🏦 قائمة المركز المالي" if is_ar else "🏦 Balance Sheet",
            [
                ("total_assets", "إجمالي الأصول" if is_ar else "Total Assets", True),
                ("current_assets", "الأصول المتداولة" if is_ar else "Current Assets", True),
                ("cash", "النقد وما في حكمه" if is_ar else "Cash & Equivalents", True),
                ("total_liabilities", "إجمالي الالتزامات" if is_ar else "Total Liabilities", False),
                ("current_liabilities", "الالتزامات المتداولة" if is_ar else "Current Liabilities", False),
                ("total_debt", "إجمالي الديون (شاملاً التأجير)" if is_ar else "Total Debt (incl. leases)", False),
                ("equity", "إجمالي حقوق الملكية" if is_ar else "Total Equity", True),
            ],
        ),
        (
            "💧 قائمة التدفقات النقدية" if is_ar else "💧 Cash Flows",
            [
                ("operating_cash_flow", "التدفق النقدي التشغيلي" if is_ar else "Operating Cash Flow", True),
                ("investing_cash_flow", "التدفق النقدي الاستثماري" if is_ar else "Investing Cash Flow", None),
                ("financing_cash_flow", "التدفق النقدي التمويلي" if is_ar else "Financing Cash Flow", None),
                ("free_cash_flow", "التدفق النقدي الحر (FCF)" if is_ar else "Free Cash Flow (FCF)", True),
            ],
        ),
    ]

    def _fmt_money(v: float | None) -> str:
        if v is None:
            return "—"
        txt = cell_value_display(v, sc, cur) if is_ar else f"{cur}{humanize(v, sc)}"
        return f'<bdi dir="ltr">{esc(txt)}</bdi>'

    body_rows: list[str] = []
    for sec_title, items in sections:
        sec_rows: list[str] = []
        for attr, lbl, higher_good in items:
            pv = getattr(prev_m, attr, None) if prev_m is not None else None
            cv = getattr(curr_m, attr, None) if curr_m is not None else None
            if pv is None and cv is None:
                continue
            if pv not in (None, 0) and cv is not None:
                pct = (cv - pv) / abs(pv) * 100.0
                arrow = "▲" if pct > 0.05 else ("▼" if pct < -0.05 else "•")
                if higher_good is None or abs(pct) <= 0.05:
                    pill_cls = "flat"
                elif (pct > 0) == higher_good:
                    pill_cls = "up"
                else:
                    pill_cls = "down"
                delta_html = (
                    f'<span class="fs-delta-pill {pill_cls}">'
                    f'{arrow} <bdi dir="ltr">{pct:+.1f}%</bdi></span>'
                )
            else:
                delta_html = '<span class="fs-delta-pill flat">—</span>'
            is_bold = attr in ("revenue", "net_income", "total_assets", "equity", "operating_cash_flow")
            lbl_html = f"<b>{esc(lbl)}</b>" if is_bold else esc(lbl)
            sec_rows.append(
                f"<tr>"
                f"<td>{lbl_html}</td>"
                f'<td class="num">{_fmt_money(pv)}</td>'
                f'<td class="num">{"<b>" + _fmt_money(cv) + "</b>" if is_bold else _fmt_money(cv)}</td>'
                f'<td class="num">{delta_html}</td>'
                f"</tr>"
            )
        if sec_rows:
            body_rows.append(f'<tr class="fs-cat-divider"><td colspan="4">{esc(sec_title)}</td></tr>')
            body_rows.extend(sec_rows)

    if body_rows:
        _sec_banner(
            "📑 الملخص التنفيذي للقوائم المالية" if is_ar else "📑 Executive Financial Statements Summary",
            (
                "أهم بنود الدخل والمركز المالي والتدفقات النقدية مع نسب التغير السنوي"
                if is_ar
                else "Core Income, Balance Sheet & Cash Flow line items with YoY changes"
            ),
        )
        h_item = "البند المالي" if is_ar else "Line Item"
        h_chg = "التغير السنوي" if is_ar else "YoY Change"
        table_html = (
            '<div class="fin-table-wrap"><table class="fin-table">'
            f'<thead><tr><th>{esc(h_item)}</th><th class="num">{esc(str(prev_y))}</th>'
            f'<th class="num">{esc(str(curr_y))}</th><th class="num">{esc(h_chg)}</th></tr></thead>'
            f'<tbody>{"".join(body_rows)}</tbody>'
            "</table></div>"
        )
        st.markdown(table_html, unsafe_allow_html=True)


def _render_formal_certificate(vm: dict, is_ar: bool) -> None:
    """Render the Z3 SMT Formal Verification Certificate & Policy Proofs card."""
    import html as _html

    cert = vm.get("formal_certificate")
    if not isinstance(cert, dict):
        return
    _h = _html.escape

    status = cert.get("status") or "PARTIALLY_PROVEN"
    cert_id = cert.get("certificate_id") or "—"
    engine = cert.get("solver_engine") or "Z3 SMT Solver"
    passed = int(cert.get("passed_axioms") or 0)
    failed = int(cert.get("failed_axioms") or 0)
    checked = int(cert.get("total_checked") or 0)
    summary_ar = cert.get("summary_ar") or ""
    repairs = cert.get("repair_history") or []
    accepted_repairs = [r for r in repairs if r.get("accepted")]

    if status == "PROVEN_CONSISTENT":
        badge_bg, badge_fg, badge_bd = "#ECFDF5", "#047857", "#A7F3D0"
        badge_txt = "مُثبت رياضياً (Z3)" if is_ar else "Formally Proven (Z3)"
        border_accent = "#10B981"
    elif status == "VIOLATIONS_DETECTED":
        badge_bg, badge_fg, badge_bd = "#FEF2F2", "#B91C1C", "#FECACA"
        badge_txt = f"{failed} خرق محاسبي مكتشف" if is_ar else f"{failed} Violation(s) Detected"
        border_accent = "#EF4444"
    else:
        badge_bg, badge_fg, badge_bd = "#FFFBEB", "#B45309", "#FDE68A"
        badge_txt = "تحقق جزئي" if is_ar else "Partially Proven"
        border_accent = "#F59E0B"

    title = (
        "شهادة التحقق الرياضي الرسمي (Z3 SMT Certificate)"
        if is_ar
        else "Formal Verification Certificate (Z3 SMT)"
    )
    repair_chip = ""
    if accepted_repairs:
        r_lbl = (
            f"🛠️ {len(accepted_repairs)} تصحيح معتمد بحلقة Z3"
            if is_ar
            else f"🛠️ {len(accepted_repairs)} Z3-verified repair(s)"
        )
        repair_chip = (
            f'<span style="background:#EEF2FF;color:#4338CA;border:1px solid #C7D2FE;'
            f'border-radius:999px;padding:3px 10px;font-size:12px;font-weight:700;">'
            f'{_h(r_lbl)}</span>'
        )

    st.markdown(
        f'<div class="fs-card" style="border-right:4px solid {border_accent};margin-top:14px;">'
        f'<div style="display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:10px;margin-bottom:8px;">'
        f'<div style="font-size:16px;font-weight:800;color:#0F172A;">🛡️ {_h(title)}</div>'
        f'<div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center;">'
        f'<span style="background:{badge_bg};color:{badge_fg};border:1px solid {badge_bd};'
        f'border-radius:999px;padding:3px 11px;font-size:12px;font-weight:700;">{_h(badge_txt)}</span>'
        f'{repair_chip}'
        f'<span style="background:#F8FAFC;color:#475569;border:1px solid #E2E8F0;'
        f'border-radius:999px;padding:3px 10px;font-size:11.5px;font-family:monospace;">'
        f'{_h(cert_id)} · {passed}/{checked}</span>'
        f'</div></div>'
        f'<div style="font-size:13.5px;color:#334155;line-height:1.65;">{_h(summary_ar)}</div>'
        f'<div style="font-size:11.5px;color:#64748B;margin-top:6px;">'
        f'المحرك الرسمي: <code>{_h(engine)}</code> — نمط «محلّل ذكاء اصطناعي غير موثوق + مُدقّق شهادة حتمي».'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    axioms = [a for a in (cert.get("axioms") or []) if a.get("status") != "SKIPPED"]
    if axioms:
        exp_lbl = (
            f"عرض تفاصيل القيود المحاسبية المفحوصة ({passed}/{checked} مُثبت)"
            if is_ar
            else f"View checked accounting axioms ({passed}/{checked} proven)"
        )
        with st.expander(exp_lbl, expanded=(failed > 0)):
            rows_html = []
            for ax in axioms:
                ok = ax.get("status") == "PROVEN"
                st_badge = (
                    '<span style="color:#047857;font-weight:700;">✅ مُثبت</span>'
                    if ok
                    else '<span style="color:#B91C1C;font-weight:700;">❌ خرق</span>'
                )
                lhs_s = f"{ax['lhs']:,.0f}" if isinstance(ax.get("lhs"), (int, float)) else "—"
                rhs_s = f"{ax['rhs']:,.0f}" if isinstance(ax.get("rhs"), (int, float)) else "—"
                res_s = f"{ax['residual']:+,.0f}" if isinstance(ax.get("residual"), (int, float)) else "—"
                rows_html.append(
                    "<tr>"
                    f"<td>{_h(str(ax.get('year', '')))}</td>"
                    f"<td><strong>{_h(ax.get('name_ar') if is_ar else ax.get('name_en', ''))}</strong>"
                    f"<div style='font-size:11px;color:#64748B;direction:ltr;text-align:right;'>{_h(ax.get('formula', ''))}</div></td>"
                    f"<td class='num'>{lhs_s}</td>"
                    f"<td class='num'>{rhs_s}</td>"
                    f"<td class='num'>{res_s}</td>"
                    f"<td>{st_badge}</td>"
                    "</tr>"
                )
            st.markdown(
                '<div class="fin-table-wrap"><table class="fin-table">'
                '<thead><tr>'
                f'<th>{"السنة" if is_ar else "Year"}</th>'
                f'<th>{"القيد المحاسبي" if is_ar else "Axiom"}</th>'
                f'<th>{"الطرف الأيمن" if is_ar else "LHS"}</th>'
                f'<th>{"الطرف الأيسر" if is_ar else "RHS"}</th>'
                f'<th>{"الفارق" if is_ar else "Residual"}</th>'
                f'<th>{"الحكم" if is_ar else "Verdict"}</th>'
                '</tr></thead><tbody>'
                + "".join(rows_html)
                + '</tbody></table></div>',
                unsafe_allow_html=True,
            )

            diags = cert.get("fault_diagnoses") or []
            if diags:
                st.markdown("**🔍 تشخيص Z3 لأصغر مجموعة تعارض (Unsat Core):**")
                for dg in diags[:5]:
                    st.warning(dg.get("reason_ar") or "")

            if repairs:
                st.markdown("**🔁 سجل حلقة التصحيح الحتمية (Z3 → AI Feedback Loop):**")
                for rp in repairs:
                    if rp.get("accepted"):
                        st.success(f"جولة {rp.get('round_no')} (ص{rp.get('page_number')}): {rp.get('reason_ar')}")
                    else:
                        st.info(f"جولة {rp.get('round_no')} (ص{rp.get('page_number')}): {rp.get('reason_ar')}")

    theorems = cert.get("policy_theorems") or []
    if theorems:
        proven_t = sum(1 for t in theorems if t.get("status") == "PROVEN")
        th_lbl = (
            f"براهين سياسات الحوكمة بـ Z3 ({proven_t}/{len(theorems)} نظرية مُثبتة رياضياً)"
            if is_ar
            else f"Z3 Formal Policy Proofs ({proven_t}/{len(theorems)} proven)"
        )
        with st.expander(th_lbl, expanded=False):
            th_rows = []
            for th in theorems:
                ok_t = th.get("status") == "PROVEN"
                s_tag = (
                    '<span style="color:#047857;font-weight:700;">✅ PROVEN (unsat)</span>'
                    if ok_t
                    else '<span style="color:#B91C1C;font-weight:700;">❌ FAILED</span>'
                )
                th_rows.append(
                    "<tr>"
                    f"<td><strong>{_h(th.get('name_ar') if is_ar else th.get('name_en', ''))}</strong>"
                    f"<div style='font-size:11.5px;color:#475569;margin-top:2px;'>{_h(th.get('statement_ar', ''))}</div></td>"
                    f"<td style='direction:ltr;font-family:monospace;font-size:11.5px;'>{_h(th.get('smt_property', ''))}</td>"
                    f"<td>{s_tag}</td>"
                    "</tr>"
                )
            st.markdown(
                '<div class="fin-table-wrap"><table class="fin-table">'
                '<thead><tr>'
                f'<th>{"النظرية / قاعدة الحوكمة" if is_ar else "Policy Theorem"}</th>'
                f'<th>{"الصيغة المنطقية" if is_ar else "Formal Property"}</th>'
                f'<th>{"حكم Z3" if is_ar else "Z3 Verdict"}</th>'
                '</tr></thead><tbody>'
                + "".join(th_rows)
                + '</tbody></table></div>',
                unsafe_allow_html=True,
            )


def sec_statements(vm: dict, raw: bytes | None) -> None:
    lang = _lang()
    is_ar = lang != "en"

    st.subheader(_T["statements"][lang])
    st.caption(
        "كل خانة بقرار بوابة الاعتماد النهائي — لا حالة المرشحين."
        if is_ar
        else "Each cell shows its FINAL gate decision."
    )

    cells = vm.get("cells") or []
    if not cells:
        render_empty_state(
            "لا توجد خانات في سجل القرار" if is_ar else "No cells in decision log",
            "لم يلتقط المحرك بنود قوائم مالية مسجلة في هذا المستند."
            if is_ar
            else "No financial statement cells were recorded for this document.",
            icon="📑",
            next_step="تأكد من صحة الملف المرفوع أو نطاق الصفحات ثم أعد التحليل."
            if is_ar
            else "Check the uploaded file or page range and re-run analysis.",
        )
        return

    f_col1, f_col2 = st.columns([1.2, 1.8])
    with f_col1:
        gate_opts = (
            ["الكل", "موثقة", "تحتاج مراجعة", "غير ملتقطة"]
            if is_ar
            else ["All", "Verified", "Needs review", "Missing"]
        )
        sel_gate = st.selectbox(
            "تصفية حسب قرار البوابة" if is_ar else "Filter by gate decision",
            gate_opts,
            key="stmt_gate_filter",
        )
    with f_col2:
        q = st.text_input(
            "بحث عن بند" if is_ar else "Search cell",
            placeholder="مثال: الإيرادات أو revenue..." if is_ar else "e.g. revenue or assets...",
            key="stmt_search",
        ).strip().lower()

    gate_map = {
        "موثقة": ("use", "use_disclosed"),
        "Verified": ("use", "use_disclosed"),
        "تحتاج مراجعة": ("not_decisive",),
        "Needs review": ("not_decisive",),
        "غير ملتقطة": ("missing",),
        "Missing": ("missing",),
    }

    visible = []
    for c in cells:
        allowed = gate_map.get(sel_gate)
        if allowed and c["gate"] not in allowed:
            continue
        disp_lbl = c["label"] if is_ar else c.get("label_en", c["label"])
        if q and q not in disp_lbl.lower() and q not in c["field"].lower() and q not in str(c.get("raw_label", "")).lower():
            continue
        visible.append(c)

    if not visible:
        render_empty_state(
            "لا توجد خانات مطابقة للبحث" if is_ar else "No matching cells",
            "لم تتطابق أي خانة مع معايير التصفية المختارة."
            if is_ar
            else "No statement cells match the active filter.",
            icon="🔎",
            next_step="أعد تعيين التصفية إلى «الكل» أو امسح نص البحث."
            if is_ar
            else "Reset the gate filter to All or clear the search box.",
        )
        return

    ev = st.session_state.get("ev_cell")
    if ev:
        with st.container(border=True):
            ev_h1, ev_h2 = st.columns([5.0, 1.2])
            with ev_h1:
                st.markdown(f"#### 🔍 {_T['evidence'][lang]} — **{esc(str(ev.get('label', '')))}** · `{esc(str(ev.get('year', '')))}`")
            with ev_h2:
                if st.button("✖ إغلاق" if is_ar else "✖ Close", key="close_ev_top", use_container_width=True):
                    st.session_state.pop("ev_cell", None)
                    st.rerun()
            evidence_block(ev, raw, vm["doc_sha"])
    else:
        render_empty_state(
            "معاينة دليل المصدر" if is_ar else "Source evidence preview",
            "لم تُختر خانة للمعاينة بعد."
            if is_ar
            else "No cell selected for inspection yet.",
            icon="🔍",
            next_step="اضغط زر «الدليل» بجانب أي خانة لعرض الصفحة الأصلية وقصاصة الرقم هنا في أعلى التبويب."
            if is_ar
            else "Click Evidence next to any row to inspect its source page & crop right here at the top.",
        )

    for c in visible:
        with st.container(border=True):
            col_main, col_btn = st.columns([5.2, 1.0])
            disp_lbl = c["label"] if is_ar else c.get("label_en", c["label"])
            val_txt = (
                cell_value_display(c["value"], vm["unit_scale"], vm["currency"])
                if is_ar
                else (
                    "N/A"
                    if c["value"] is None
                    else f"{vm['currency']}{humanize(c['value'], vm['unit_scale'])}"
                )
            )
            gate_lbl = (
                c["gate_label"]
                if is_ar
                else _GATE_EN.get(c["gate"], c["gate_label"])
            )
            row_tone = (
                "is-ok"
                if c["gate"] in ("use", "use_disclosed")
                else ("is-miss" if c["gate"] == "missing" else "is-pend")
            )
            rev_tag = (
                f' <span class="fs-gate ok">✓ {"موثق بشريًا" if is_ar else "human-attested"}</span>'
                if c["reviewed"]
                else ""
            )
            raw_sub = (
                f' <span style="font-size:.78rem;color:var(--fs-muted);font-weight:500;">'
                f'({("كما قُرئت: " if is_ar else "as read: ") + esc(str(c["raw_label"]))})</span>'
                if (c["raw_label"] and c["raw_label"] != c["label"])
                else ""
            )
            reason_html = ""
            if c["reason"] and c["gate"] != "use":
                clean_reason = (
                    str(c["reason"])
                    .replace("(['vision'])", "(طبقة الرؤية الذكية)")
                    .replace("['vision']", "طبقة الرؤية الذكية")
                    .replace("(['local_ocr'])", "(طبقة القراءة المحلية)")
                    .replace("['local_ocr']", "طبقة القراءة المحلية")
                )
                reason_html = (
                    f'<div class="fs-stmt-reason">'
                    f'ℹ️ <b>{"السبب:" if is_ar else "Reason:"}</b> {esc(clean_reason)}'
                    f"</div>"
                )
            with col_main:
                st.markdown(
                    f'<div class="fs-stmt-row {row_tone}">'
                    f'<div class="fs-stmt-title">'
                    f'<span>{esc(disp_lbl)}</span>'
                    f'<span class="fs-stmt-year"><bdi dir="ltr">{esc(c["year"])}</bdi></span>'
                    f"{raw_sub}"
                    f"</div>"
                    f'<div style="display:flex;align-items:center;flex-wrap:wrap;gap:10px;">'
                    f'<span class="fs-stmt-val"><bdi dir="ltr">{esc(val_txt)}</bdi></span>'
                    f"{rev_tag}"
                    f'{gate_badge(c["gate"], gate_lbl)}'
                    f"</div>"
                    f"</div>"
                    f"{reason_html}",
                    unsafe_allow_html=True,
                )
            with col_btn:
                if st.button(
                    _T["open_evidence"][lang],
                    key=f"ev-{c['field']}-{c['year']}",
                    use_container_width=True,
                ):
                    st.session_state["ev_cell"] = c
                    st.rerun()


def _render_metrics_charts_suite(vm: dict, res_obj: dict, is_ar: bool, lang: str) -> None:
    """v9.20 Interactive 4-tab Plotly charts suite for Financial Metrics."""
    from src.dashboard import charts

    by_key = res_obj.get("rows_by_key") or {
        r.key: r for r in (res_obj.get("rows") or []) if hasattr(r, "key")
    }
    growth_rows = res_obj.get("growth_rows") or []
    all_rows = res_obj.get("rows") or []
    if not by_key and not growth_rows:
        return

    prev_y = vm.get("prev_year")
    curr_y = vm.get("curr_year")
    cur = vm.get("currency") or "$"
    sc = vm.get("unit_scale") or 1
    _cfg = {"displayModeBar": False}

    def _has_vals(keys: tuple[str, ...]) -> bool:
        for k in keys:
            r = by_key.get(k)
            if r is not None and (r.previous is not None or r.current is not None):
                return True
        return False

    has_margins = _has_vals(("gross_margin", "operating_margin", "net_margin"))
    has_returns = _has_vals(("roa", "roe"))
    has_liq = _has_vals(("current_ratio", "quick_ratio"))
    has_lev = _has_vals(("debt_to_equity", "debt_ratio"))
    has_cf = _has_vals(("operating_cash_flow", "investing_cash_flow", "financing_cash_flow"))
    has_eff = _has_vals(("asset_turnover", "inventory_turnover"))
    fig_growth = charts.growth_bar_chart(growth_rows, curr_year=curr_y, lang=lang)
    fig_trend = None
    if fig_growth is None and all_rows:
        fig_trend = charts.trend_scatter(all_rows, prev_y, curr_y, lang=lang)

    if not any((has_margins, has_returns, has_liq, has_lev, has_cf, has_eff, fig_growth, fig_trend)):
        return

    _sec_banner(
        "📊 الرسوم البيانية التفاعلية للمؤشرات المالية"
        if is_ar
        else "📊 Interactive Financial Ratio Charts",
        (
            f"مقارنة بصرية تفاعلية بين {prev_y} و{curr_y} عبر محاور الربحية والسيولة والمديونية والنمو"
            if is_ar
            else f"Interactive visual comparison ({prev_y} vs {curr_y}) across profitability, liquidity, leverage & growth"
        ),
    )

    tab_labels = (
        [
            "💰 الربحية والعوائد",
            "💧 السيولة والمديونية",
            "⚡ التدفقات والكفاءة",
            "🚀 النمو السنوي",
        ]
        if is_ar
        else [
            "💰 Profitability & Returns",
            "💧 Liquidity & Leverage",
            "⚡ Cash Flows & Efficiency",
            "🚀 YoY Growth",
        ]
    )
    ct1, ct2, ct3, ct4 = st.tabs(tab_labels)

    with ct1:
        if has_margins and has_returns:
            c_l, c_r = st.columns(2)
            with c_l:
                st.plotly_chart(
                    charts.margins_chart(by_key, prev_y, curr_y, cur),
                    use_container_width=True,
                    key="m_margins_chart",
                    config=_cfg,
                )
            with c_r:
                st.plotly_chart(
                    charts.returns_chart(by_key, prev_y, curr_y),
                    use_container_width=True,
                    key="m_returns_chart",
                    config=_cfg,
                )
        elif has_margins:
            st.plotly_chart(
                charts.margins_chart(by_key, prev_y, curr_y, cur),
                use_container_width=True,
                key="m_margins_chart",
                config=_cfg,
            )
        elif has_returns:
            st.plotly_chart(
                charts.returns_chart(by_key, prev_y, curr_y),
                use_container_width=True,
                key="m_returns_chart",
                config=_cfg,
            )
        else:
            st.info("لا تتوفر بيانات ربحية كافية للرسم." if is_ar else "Insufficient profitability data.")

    with ct2:
        if has_liq and has_lev:
            c_l, c_r = st.columns(2)
            with c_l:
                st.plotly_chart(
                    charts.liquidity_chart(by_key, prev_y, curr_y),
                    use_container_width=True,
                    key="m_liquidity_chart",
                    config=_cfg,
                )
            with c_r:
                st.plotly_chart(
                    charts.leverage_chart(by_key, prev_y, curr_y),
                    use_container_width=True,
                    key="m_leverage_chart",
                    config=_cfg,
                )
        elif has_liq:
            st.plotly_chart(
                charts.liquidity_chart(by_key, prev_y, curr_y),
                use_container_width=True,
                key="m_liquidity_chart",
                config=_cfg,
            )
        elif has_lev:
            st.plotly_chart(
                charts.leverage_chart(by_key, prev_y, curr_y),
                use_container_width=True,
                key="m_leverage_chart",
                config=_cfg,
            )
        else:
            st.info("لا تتوفر بيانات سيولة أو مديونية كافية للرسم." if is_ar else "Insufficient liquidity/leverage data.")

    with ct3:
        if has_cf and has_eff:
            c_l, c_r = st.columns(2)
            with c_l:
                st.plotly_chart(
                    charts.cashflow_chart(by_key, prev_y, curr_y, cur, scale=sc, lang=lang),
                    use_container_width=True,
                    key="m_cashflow_chart",
                    config=_cfg,
                )
            with c_r:
                st.plotly_chart(
                    charts.efficiency_chart(by_key, prev_y, curr_y),
                    use_container_width=True,
                    key="m_efficiency_chart",
                    config=_cfg,
                )
        elif has_cf:
            st.plotly_chart(
                charts.cashflow_chart(by_key, prev_y, curr_y, cur, scale=sc, lang=lang),
                use_container_width=True,
                key="m_cashflow_chart",
                config=_cfg,
            )
        elif has_eff:
            st.plotly_chart(
                charts.efficiency_chart(by_key, prev_y, curr_y),
                use_container_width=True,
                key="m_efficiency_chart",
                config=_cfg,
            )
        else:
            st.info("لا تتوفر بيانات تدفقات أو كفاءة كافية للرسم." if is_ar else "Insufficient cash flow/efficiency data.")

    with ct4:
        if fig_growth is not None:
            st.plotly_chart(fig_growth, use_container_width=True, key="m_growth_chart", config=_cfg)
        elif fig_trend is not None:
            st.plotly_chart(fig_trend, use_container_width=True, key="m_trend_chart", config=_cfg)
        else:
            st.info("لا تتوفر معدلات نمو سنوي للعرض." if is_ar else "No YoY growth data available.")


def sec_metrics(vm: dict, results: dict | None = None) -> None:
    """Custom RTL/LTR HTML metrics table with sticky headers, filters & badges."""
    lang = _lang()
    is_ar = lang != "en"

    st.subheader(_T["metrics"][lang])
    metrics_rows = vm.get("metrics") or []
    if not metrics_rows:
        render_empty_state(
            "لا توجد مؤشرات محسوبة" if is_ar else "No computed metrics",
            "لم تتوفر بيانات كافية لحساب نسب المقارنة بين السنتين."
            if is_ar
            else "Not enough inputs were available to compute comparison ratios.",
            icon="📊",
            next_step="راجع الخانات الملتقطة في تبويب «القوائم والخانات»."
            if is_ar
            else "Review extracted cells in Statements & Cells.",
        )
        return

    res_obj_charts = results or st.session_state.get("results") or {}
    _render_metrics_charts_suite(vm, res_obj_charts, is_ar, lang)

    _sec_banner(
        "📋 جدول النسب والمؤشرات المالية الكامل"
        if is_ar
        else "📋 Complete Financial Ratios Table",
        (
            "قابل للتصفية حسب الفئة أو حالة التوثيق مع عزل رقمي دقيق"
            if is_ar
            else "Filterable by category, verification status, or search term"
        ),
    )

    all_cats: list[str] = []
    for r in metrics_rows:
        c_lbl = r.get("category_ar") if is_ar else r.get("category")
        if c_lbl and c_lbl not in all_cats:
            all_cats.append(c_lbl)

    c1, c2, c3 = st.columns([1.2, 1.2, 1.4])
    with c1:
        cat_default = "كل الفئات" if is_ar else "All categories"
        sel_cat = st.selectbox(
            "الفئة" if is_ar else "Category",
            [cat_default] + all_cats,
            key="metrics_cat_filter",
        )
    with c2:
        ver_opts = (
            [("all", "كل حالات التحقق"), ("ok", "موثق فقط"), ("pend", "يحتاج مراجعة / تعارض"), ("miss", "غير متوفر")]
            if is_ar
            else [("all", "All verification states"), ("ok", "Verified only"), ("pend", "Needs review / conflict"), ("miss", "Unavailable")]
        )
        sel_ver_lbl = st.selectbox(
            "حالة التحقق" if is_ar else "Verification",
            [lbl for _, lbl in ver_opts],
            key="metrics_verif_filter",
        )
        sel_ver = next((code for code, lbl in ver_opts if lbl == sel_ver_lbl), "all")
    with c3:
        query = st.text_input(
            "بحث في المؤشرات" if is_ar else "Search metrics",
            placeholder="مثال: ROE أو السيولة..." if is_ar else "e.g. ROE or margin...",
            key="metrics_search_query",
        )

    table_html, count = build_metrics_table_html(
        metrics_rows,
        prev_year=vm["prev_year"],
        curr_year=vm["curr_year"],
        unit_scale=vm["unit_scale"],
        currency=vm["currency"],
        lang=lang,
        filter_cat=sel_cat,
        filter_verif=sel_ver,
        query=query,
    )
    if count == 0:
        render_empty_state(
            "لا توجد مؤشرات مطابقة للتصفية" if is_ar else "No matching metrics",
            "لم يتطابق أي مؤشر مع الفئة أو حالة التحقق أو نص البحث المحدد."
            if is_ar
            else "No metric matches the current category, verification filter, or query.",
            icon="🔎",
            next_step=f"اختر «كل الفئات» و«كل حالات التحقق» وامسح البحث لعرض الـ{len(metrics_rows)} مؤشرًا."
            if is_ar
            else f"Reset filters to All and clear the search box to view all {len(metrics_rows)} metrics.",
        )
        return

    st.caption(
        f"عرض {count} من أصل {len(metrics_rows)} مؤشر — الأرقام مضبوطة بوحدة المستند وحالة التحقق تعكس أسوأ مدخل."
        if is_ar
        else f"Showing {count} of {len(metrics_rows)} metrics — verification reflects the worst input."
    )
    st.markdown(table_html, unsafe_allow_html=True)

    res_obj = results or st.session_state.get("results") or {}
    curr_m = res_obj.get("curr_metrics")
    prev_m = res_obj.get("prev_metrics")
    if curr_m is not None:
        from src.analysis.academic_models import academic_models
        from src.analysis.redflags import SEVERITY_ICON, beneish_m_score, red_flag_analysis
        from src.dashboard import theme

        st.divider()
        st.subheader("🎓 " + ("النماذج الأكاديمية للإنذار المبكر" if is_ar else "Academic Early-Warning Models"))
        from src.analysis.comparison import LABELS_AR as _ACAD_LBL

        _comp_ar_map = {
            "NetMargin": "هامش الصافي%",
            "AssetTurnover": "دوران الأصول",
            "EquityMultiplier": "مضاعف الملكية",
            "ROE_rebuilt": "العائد على الملكية%",
            "TaxBurden": "عبء الضريبة",
            "InterestBurden": "عبء الفوائد",
            "EBITMargin": "هامش التشغيل%",
            "NI/TA": "صافي الربح/الأصول",
            "TL/TA": "الالتزامات/الأصول",
            "CA/CL": "أصول/خصوم متداولة",
        "CL/CA": "خصوم/أصول متداولة",
        }
        acad_rows = []
        for m in academic_models(curr_m):
            if m.value is not None:
                comp_chips = "".join(
                    f'<span class="fs-detail-chip">'
                    f'{esc(_comp_ar_map.get(k, k) if is_ar else k)}: '
                    f'<b><bdi dir="ltr">{v:g}</bdi></b></span>'
                    for k, v in m.components.items()
                )
                acad_rows.append(
                    "<tr>"
                    f"<td><b>{esc(m.icon + ' ' + m.name)}</b></td>"
                    f"<td class='num'><b><bdi dir='ltr'>{m.value:g}</bdi></b></td>"
                    f"<td>{esc(m.verdict)}</td>"
                    f"<td><div class='fs-pillar-details'>{comp_chips}</div></td>"
                    "</tr>"
                )
            else:
                miss_names = [_ACAD_LBL.get(f, f) if is_ar else f for f in m.missing]
                sep_m = "، " if is_ar else ", "
                acad_rows.append(
                    "<tr>"
                    f"<td><b>{esc(m.name)}</b></td>"
                    "<td class='num'>—</td>"
                    f"<td>{'غير محسوب — بيانات ناقصة: ' if is_ar else 'Missing inputs: '}{esc(sep_m.join(miss_names))}</td>"
                    "<td>—</td>"
                    "</tr>"
                )
        st.markdown(
            theme.fin_table(
                ["النموذج", "القيمة", "الحكم", "المكوّنات"] if is_ar else ["Model", "Value", "Verdict", "Components"],
                acad_rows,
            ),
            unsafe_allow_html=True,
        )

        if prev_m is not None:
            st.divider()
            st.subheader("⚠️ " + ("الأعلام الحمراء ونموذج Beneish M-Score" if is_ar else "Red Flags & Beneish M-Score"))
            bn = beneish_m_score(prev_m, curr_m)
            if bn.m_score is not None:
                zone_icon = {"grey_above": "🟠", "grey": "🟡", "clean": "🟢"}.get(bn.zone, "")
                st.markdown(
                    f"**Beneish M-Score:** <span style='font-size:1.1rem;'><b><bdi dir='ltr'>{bn.m_score:.2f}</bdi></b></span> "
                    f"{zone_icon} {esc(bn.verdict)}",
                    unsafe_allow_html=True,
                )
                st.caption(
                    ("المكوّنات: " if is_ar else "Components: ")
                    + " · ".join(f"{k}={v:.2f}" for k, v in bn.components.items())
                )
            flags = red_flag_analysis(prev_m, curr_m)
            if flags:
                flag_rows = [
                    "<tr>"
                    f"<td><b>{esc(SEVERITY_ICON[fl.severity] + ' ' + fl.name)}</b></td>"
                    f"<td>{esc(fl.detail)}</td>"
                    "</tr>"
                    for fl in flags
                ]
                st.markdown(
                    theme.fin_table(["المؤشر", "الدليل الرقمي"] if is_ar else ["Flag", "Evidence"], flag_rows),
                    unsafe_allow_html=True,
                )


def _health_blocked_fields(vm: dict, results: dict) -> set[str]:
    """Fields blocked for the current-year Official Health Score."""
    curr_yr = results.get("curr_year")
    return {
        e["field"]
        for e in (vm.get("pending") or [])
        if e.get("field")
        and (curr_yr is None or e.get("year") in (None, curr_yr) or str(e.get("year")) == str(curr_yr))
    }


def sec_health(vm: dict, results: dict) -> None:
    from src.analysis.score import compute_health_score
    from src.dashboard import charts

    lang = _lang()
    is_ar = lang != "en"
    st.subheader(_T["health"][lang])
    blocked = _health_blocked_fields(vm, results)
    hs = compute_health_score(results["curr_metrics"], blocked_fields=blocked)

    if hs.total is not None:
        st.markdown(build_health_html(hs, lang=lang), unsafe_allow_html=True)
        _cfg = {"displayModeBar": False}
        fig_rad = charts.health_radar_chart(hs, lang=lang)
        _sec_banner(
            "🎯 التمثيل البصري لمؤشر الصحة المالية"
            if is_ar
            else "🎯 Financial Health Visual Profile",
            (
                "المقياس العام وتوازن الأركان الأربعة مقارنة بالمعيار المستهدف (70/100)"
                if is_ar
                else "Overall score gauge and 4-pillar balance vs target benchmark (70/100)"
            ),
        )
        if fig_rad is not None:
            hc1, hc2 = st.columns(2)
            with hc1:
                st.plotly_chart(
                    charts.health_gauge(hs, lang=lang),
                    use_container_width=True,
                    key="health_gauge_official",
                    config=_cfg,
                )
            with hc2:
                st.plotly_chart(
                    fig_rad,
                    use_container_width=True,
                    key="health_radar_official",
                    config=_cfg,
                )
        else:
            st.plotly_chart(
                charts.health_gauge(hs, lang=lang),
                use_container_width=True,
                key="health_gauge_official",
                config=_cfg,
            )
        if getattr(hs, "policy", ""):
            st.caption(hs.policy)
        return

    hs_est = compute_health_score(results["curr_metrics"], blocked_fields=None)
    if hs_est.total is not None:
        st.warning(
            "🛡️ **الدرجة الصحية الرسمية محجوبة وفق سياسة تغطية البيانات** (مدخلات السيولة/المديونية بانتظار المراجعة البشرية — لا تُصدَّر كدرجة معتمدة في التقارير النهائية). "
            "يُعرض أدناه **تقدير استكشافي تجريبي غير معتمد** محسوب من القيم الأولية الملتقطة لفهم الصورة المبدئية فقط؛ "
            "ولاعتماد الدرجة الرسمية راجع الخانات الحرجة في تبويب «مراجعة بشرية»."
            if is_ar
            else "🛡️ **Official Health Score is refused under the data-coverage policy** (critical liquidity/leverage inputs are pending human review and are not exported as an approved score). "
            "Below is an **unofficial exploratory estimate** computed from preliminary extracted values for preview only; verify critical cells in Human Review to unlock the official score."
        )
        st.markdown(build_health_html(hs_est, lang=lang), unsafe_allow_html=True)
        _cfg = {"displayModeBar": False}
        fig_rad_est = charts.health_radar_chart(hs_est, lang=lang)
        if fig_rad_est is not None:
            hc1, hc2 = st.columns(2)
            with hc1:
                st.plotly_chart(
                    charts.health_gauge(hs_est, lang=lang),
                    use_container_width=True,
                    key="health_gauge_exploratory",
                    config=_cfg,
                )
            with hc2:
                st.plotly_chart(
                    fig_rad_est,
                    use_container_width=True,
                    key="health_radar_exploratory",
                    config=_cfg,
                )
        else:
            st.plotly_chart(
                charts.health_gauge(hs_est, lang=lang),
                use_container_width=True,
                key="health_gauge_exploratory",
                config=_cfg,
            )
        with st.expander(
            "🛡️ عرض تفاصيل حجب الدرجة الرسمية وفق بوابة الصدق"
            if is_ar
            else "🛡️ Official Honesty-Gate refusal details",
            expanded=False,
        ):
            st.markdown(build_health_html(hs, lang=lang), unsafe_allow_html=True)
            if getattr(hs, "policy", ""):
                st.caption(hs.policy)
    else:
        st.markdown(build_health_html(hs, lang=lang), unsafe_allow_html=True)
        if getattr(hs, "policy", ""):
            st.caption(hs.policy)
        st.caption(
            "قيم هذه الأركان غير متوفرة في المستند — لا تُحسب درجة إجمالية."
            if is_ar
            else "Critical pillar inputs are missing — no total score can be computed."
        )


def sec_insights(vm: dict, analysis) -> None:
    """رؤى Gemini مصنفة من اتجاه المؤشر المحسوب — تدعم التعليق القاعدي الحتمي عند تعذر Gemini."""
    lang = _lang()
    is_ar = lang != "en"
    st.subheader(_T["insights"][lang])

    if analysis is None:
        if vm["pending_count"]:
            st.warning(_T["provisional"][lang])
        render_empty_state(
            "التعليق التحليلي مؤجل (الوضع السريع)"
            if is_ar
            else "Analytical commentary deferred (Fast mode)",
            "تم استخراج الأرقام وحساب النسب فورًا؛ اضغط أدناه لتوليد التعليق والتوصيات الآن."
            if is_ar
            else "Numbers and ratios are ready; click below to generate commentary now.",
            icon="⚡",
            next_step="اضغط «توليد التعليق التحليلي» (يستغرق حتى دقيقة)."
            if is_ar
            else "Click Generate commentary (takes up to a minute).",
        )
        if st.button(
            "⚡ توليد التعليق التحليلي" if is_ar else "⚡ Generate commentary",
            key="gen_commentary",
            type="primary",
        ):
            from src.ai.gemini_agent import AIAnalysis, analyze_financials
            from src.analysis.narrative import build_fallback_narrative, build_recommendations
            from src.extraction.result_cache import (
                analysis_key,
                load_cached_analysis,
                store_analysis,
            )
            from src.pipeline import build_gemini_payload

            results = st.session_state.get("results") or {}
            currency = results.get("currency_hint") or st.session_state.get("currency", "$")
            payload = build_gemini_payload(
                {**results, "verification_status": vm["verification"]}, currency
            )
            if len(payload.get("metrics") or []) < 4:
                payload = build_gemini_payload(
                    {k: v for k, v in results.items() if k != "verification_status"},
                    currency,
                )
            dkey = analysis_key(payload)
            cached_a = load_cached_analysis(dkey)
            if cached_a is not None:
                analysis = AIAnalysis(
                    ok=bool(cached_a["ok"]),
                    ratio_comments=[tuple(x) for x in cached_a["ratio_comments"]],
                    recommendations=[tuple(x) for x in cached_a["recommendations"]],
                    error=str(cached_a.get("error") or ""),
                    model=str(cached_a.get("model") or ""),
                )
                if not analysis.ratio_comments:
                    analysis = build_fallback_narrative(results, analysis)
            else:
                with st.spinner(
                    "جارٍ توليد التعليق التحليلي…"
                    if is_ar
                    else "Generating analytical commentary..."
                ):
                    analysis = analyze_financials(payload)
                    if not analysis.ok or not analysis.ratio_comments:
                        analysis = build_fallback_narrative(results, analysis)
                    else:
                        if len(analysis.ratio_comments) < 6:
                            fb = build_fallback_narrative(results, analysis)
                            seen_m = {m for m, _ in analysis.ratio_comments}
                            for m, c in fb.ratio_comments:
                                if m not in seen_m:
                                    analysis.ratio_comments.append((m, c))
                                    seen_m.add(m)
                        if len(analysis.recommendations) < 3:
                            existing = {a for a, _ in analysis.recommendations}
                            for action, evidence in build_recommendations(results):
                                if len(analysis.recommendations) >= 5:
                                    break
                                if action not in existing:
                                    analysis.recommendations.append((action, evidence))
                                    existing.add(action)
                    if analysis.ok:
                        store_analysis(
                            dkey,
                            {
                                "ok": analysis.ok,
                                "ratio_comments": [list(x) for x in analysis.ratio_comments],
                                "recommendations": [list(x) for x in analysis.recommendations],
                                "error": analysis.error,
                                "model": analysis.model,
                            },
                        )
            st.session_state["analysis"] = analysis
            st.rerun()
        return

    results_ctx = st.session_state.get("results") or {"rows": []}
    if results_ctx.get("rows") and len(getattr(analysis, "ratio_comments", None) or []) < 4:
        from src.analysis.narrative import build_fallback_narrative, build_recommendations

        fb = build_fallback_narrative(results_ctx, analysis)
        if not getattr(analysis, "ratio_comments", None):
            analysis = fb
        else:
            seen_m = {m for m, _ in analysis.ratio_comments}
            for m, c in fb.ratio_comments:
                if m not in seen_m:
                    analysis.ratio_comments.append((m, c))
                    seen_m.add(m)
            if len(getattr(analysis, "recommendations", None) or []) < 3:
                existing = {a for a, _ in (analysis.recommendations or [])}
                for action, evidence in build_recommendations(results_ctx):
                    if len(analysis.recommendations) >= 5:
                        break
                    if action not in existing:
                        analysis.recommendations.append((action, evidence))
                        existing.add(action)

    is_ai_ok = bool(getattr(analysis, "ok", False))
    has_comments = bool(getattr(analysis, "ratio_comments", []))
    has_recs = bool(getattr(analysis, "recommendations", []))

    if not is_ai_ok and not (has_comments or has_recs):
        reason = getattr(analysis, "error", "") or "—"
        render_error_state(
            "لا يتوفر تعليق تحليلي" if is_ar else "No analytical commentary",
            ("تعذّر توليد تحليل Gemini — السبب: " if is_ar else "Gemini analysis unavailable — reason: ")
            + str(reason),
            next_step="أضف مفتاح GEMINI_API_KEYS في ملف ‎.env أو أعد المحاولة لاحقًا."
            if is_ar
            else "Configure GEMINI_API_KEYS in .env or try again later.",
        )
        return

    notice_parts = []
    if vm["pending_count"]:
        notice_parts.append(_T["provisional"][lang])
    if not is_ai_ok:
        reason = str(getattr(analysis, "error", "") or "")
        low_r = reason.lower()
        if any(k in low_r for k in ("429", "resource_exhausted", "quota", "exhausted")):
            friendly = (
                "انتهت حصة Gemini المجانية لهذا اليوم (أضف مفتاح API جديدًا في Secrets أو انتظر تجدد الحصة)"
                if is_ar
                else "Gemini free quota is exhausted for today"
            )
        elif any(k in low_r for k in ("504", "deadline", "timeout", "503", "unavailable")):
            friendly = (
                "تأخر استجابة خدمة Gemini مؤقتًا (504/503)"
                if is_ar
                else "Gemini timed out temporarily (504/503)"
            )
        else:
            friendly = "تعذّر الاتصال بـ Gemini" if is_ar else "Gemini is unavailable"
        notice_parts.append(
            f"{friendly} — يُعرض التفسير القاعدي الحتمي المحسوب في Python (كل رقم متتبع لأصله)."
            if is_ar
            else f"{friendly} — showing deterministic Python rule-based commentary."
        )
    if notice_parts:
        st.warning(" · ".join(notice_parts))
    if is_ai_ok:
        st.caption(
            (f"النموذج: {analysis.model} · {len(analysis.ratio_comments)} " if is_ar else f"model: {analysis.model} · {len(analysis.ratio_comments)} ")
            + (
                "تعليقًا من Gemini — كل رقم متتبع لأصل محسوب في Python"
                if is_ar
                else "Gemini comments — every number traces to a Python computation"
            )
        )

    from src.dashboard import charts

    results_ctx = st.session_state.get("results") or {"rows": []}
    cats = categorized_insights(results_ctx, analysis)

    n_pos = len(cats["strengths"])
    n_neg = len(cats["weaknesses"])
    n_neu = len(cats["neutral"])
    n_rec = len(cats["recommendations"])

    pills_html = (
        '<div style="display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 12px 0;">'
        f'<span class="fs-gate ok">● {esc(_T["strengths"][lang])}: {n_pos}</span>'
        f'<span class="fs-gate bad">▲ {esc(_T["weaknesses"][lang])}: {n_neg}</span>'
        f'<span class="fs-gate miss">◆ {esc(_T["neutral"][lang])}: {n_neu}</span>'
        f'<span class="fs-gate ok">🧭 {esc(_T["recommendations"][lang])}: {n_rec}</span>'
        "</div>"
    )
    fig_donut = charts.insights_donut_chart(n_pos, n_neg, n_neu, lang=lang)
    if fig_donut is not None:
        ic_left, ic_right = st.columns([1.45, 1.0])
        with ic_left:
            _sec_banner(
                "🧠 توزيع الإشارات والتوصيات التحليلية"
                if is_ar
                else "🧠 Analytical Signals & Action Distribution",
                (
                    "تصنيف تلقائي لنقاط القوة والمخاطر والمؤشرات المستقرة بناءً على الاتجاه الفعلي للأرقام"
                    if is_ar
                    else "Auto-classified strengths, risks & stable signals grounded in actual computed deltas"
                ),
            )
            st.markdown(pills_html, unsafe_allow_html=True)
        with ic_right:
            st.plotly_chart(
                fig_donut,
                use_container_width=True,
                key="insights_donut_chart",
                config={"displayModeBar": False},
            )
    else:
        st.markdown(pills_html, unsafe_allow_html=True)

    groups = [
        (_T["strengths"][lang], cats["strengths"], "is-pos", "ok", "●"),
        (_T["weaknesses"][lang], cats["weaknesses"], "is-neg", "bad", "▲"),
        (_T["neutral"][lang], cats["neutral"], "is-neu", "miss", "◆"),
    ]
    for title, items, card_cls, badge_cls, glyph in groups:
        if not items:
            continue
        st.markdown(f"#### {title} ({len(items)})")
        cards_html = []
        for item in items:
            st_raw = item.get("status", "Neutral")
            st_lbl = (
                {"Positive": "إيجابي", "Negative": "سلبي", "Neutral": "محايد"}.get(
                    st_raw, st_raw
                )
                if is_ar
                else st_raw
            )
            disp_title = item["metric"] if is_ar else item.get("metric_en", item["metric"])
            cards_html.append(
                f'<div class="fs-insight-card {card_cls}">'
                f'<div class="fs-insight-head">'
                f'<span class="fs-insight-title">{esc(disp_title)}</span>'
                f'<span class="fs-gate {badge_cls}">{glyph} {esc(st_lbl)}</span>'
                f"</div>"
                f'<div class="fs-insight-body" dir="auto">{isolate_bidi_html(item["text"])}</div>'
                f"</div>"
            )
        st.markdown(
            f'<div class="fs-insight-grid">{"".join(cards_html)}</div>',
            unsafe_allow_html=True,
        )

    if cats["recommendations"]:
        st.markdown(
            f"#### {_T['recommendations'][lang]} ({len(cats['recommendations'])})"
        )
        rec_cards = []
        for idx, item in enumerate(cats["recommendations"], 1):
            ev_txt = item.get("text") or ""
            ev_html = (
                f'<div class="rec-evidence" dir="auto">📎 {isolate_bidi_html(ev_txt)}</div>'
                if ev_txt
                else ""
            )
            rec_cards.append(
                f'<div class="fs-insight-card is-rec">'
                f'<div class="fs-insight-head">'
                f'<span class="fs-insight-title">{idx}. {esc(item["metric"])}</span>'
                f'<span class="fs-gate ok">🧭 {"توصية" if is_ar else "Action"}</span>'
                f"</div>"
                f"{ev_html}"
                f"</div>"
            )
        st.markdown(
            f'<div class="fs-insight-grid">{"".join(rec_cards)}</div>',
            unsafe_allow_html=True,
        )


def sec_reports(vm: dict, results: dict, analysis) -> None:
    from src.analysis.score import compute_health_score
    from src.dashboard.excel_report import build_excel_report
    from src.dashboard.report import build_html_report

    lang = _lang()
    is_ar = lang != "en"
    st.subheader(_T["reports"][lang])
    blocked = _health_blocked_fields(vm, results)
    results["verification_status"] = vm["verification"]
    results["blocked_fields"] = sorted(blocked)
    hs = compute_health_score(results["curr_metrics"], blocked_fields=blocked)
    c1, c2 = st.columns(2)
    with c1:
        xlsx = report_memo(results, "xlsx", lambda: build_excel_report(results))
        st.download_button(
            "⬇️ Excel (.xlsx)" if is_ar else "⬇️ Download Excel (.xlsx)",
            xlsx,
            file_name=f"FinSight_{results.get('curr_year')}_analysis.xlsx",
            use_container_width=True,
        )
        st.caption(
            "الملخص · المؤشرات · الجداول · أثر المراجعة"
            if is_ar
            else "Summary · metrics · statements · review trail"
        )
    with c2:
        from src.ai.gemini_agent import AIAnalysis

        safe_analysis = (
            analysis if analysis is not None else AIAnalysis(ok=False, error="")
        )
        html_key = (
            f"html|{bool(getattr(analysis, 'ok', False))}|{len(getattr(analysis, 'ratio_comments', []) or [])}"
            if analysis is not None
            else "html_deferred"
        )
        html_doc = report_memo(
            results,
            html_key,
            lambda: build_html_report(
                results, safe_analysis, hs, currency=vm["currency"]
            ),
        )
        st.download_button(
            "⬇️ HTML" if is_ar else "⬇️ Download HTML",
            html_doc.encode("utf-8"),
            file_name=f"FinSight_{results.get('curr_year')}_report.html",
            mime="text/html",
            use_container_width=True,
        )
        st.caption(
            "نفس الأرقام مع علم أولي/نهائي — جاهز للطباعة PDF من المتصفح"
            if is_ar
            else "Same numbers with preliminary/final flag — browser print-to-PDF ready"
        )
    import shutil as _shutil

    soffice = Path(os.environ.get("SOFFICE_PATH")
                   or _shutil.which("soffice")
                   or r"C:\Program Files\LibreOffice\program\soffice.exe")
    if not soffice.exists():
        render_empty_state(
            "تصدير PDF المباشر غير متاح" if is_ar else "Direct PDF export unavailable",
            "برنامج LibreOffice غير مثبت على هذا الجهاز؛ يمكنك تصدير Excel وHTML (قابل للطباعة إلى PDF مباشرة عبر Ctrl+P)."
            if is_ar
            else "LibreOffice is not installed; Excel and printable HTML reports are available above.",
            icon="🖨️",
            next_step="افتح ملف HTML في المتصفح واضغط Ctrl+P للحفظ بصيغة PDF."
            if is_ar
            else "Open the downloaded HTML in any browser and press Ctrl+P to save as PDF.",
        )
        return
    if st.button("📄 توليد PDF عبر LibreOffice" if is_ar else "📄 Generate PDF", use_container_width=True):
        import subprocess

        with tempfile.TemporaryDirectory() as td:
            print_html = Path(td) / "report_print.html"
            print_html.write_text(
                build_html_report(
                    results, safe_analysis, hs, currency=vm["currency"], print_safe=True
                ),
                encoding="utf-8",
            )
            with st.spinner("LibreOffice..."):
                subprocess.run(
                    [str(soffice), "--headless", "--convert-to", "pdf", "--outdir", td, str(print_html)],
                    capture_output=True,
                    timeout=240,
                )
            pdf = Path(td) / "report_print.pdf"
            if pdf.exists():
                st.download_button(
                    "⬇️ تحميل PDF" if is_ar else "⬇️ Download PDF",
                    pdf.read_bytes(),
                    file_name=f"FinSight_{results.get('curr_year')}_report.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
            else:
                render_error_state(
                    "فشل تحويل PDF" if is_ar else "PDF conversion failed",
                    "تعذّر على LibreOffice تحويل ملف HTML إلى PDF."
                    if is_ar
                    else "LibreOffice could not convert the HTML report to PDF.",
                    next_step="استخدم تنزيل HTML ثم الطباعة من المتصفح (Ctrl+P)."
                    if is_ar
                    else "Download HTML and print to PDF from your browser.",
                )


def _safe_doc_sha(doc_sha: str | None, raw: bytes) -> str:
    """Validated document fingerprint for isolating per-document review artifacts."""
    candidate = str(doc_sha or "").strip()
    if candidate and re.fullmatch(r"[A-Za-z0-9_-]+", candidate):
        return candidate
    return hashlib.sha256(raw).hexdigest()[:16]


def _queue_signature(vm: dict, results: dict) -> str:
    """Stable digest of pending queue entries and bounding boxes."""
    pending_sig = [
        [
            e.get("field"),
            e.get("year"),
            e.get("pages") or [],
            e.get("status"),
            e.get("final"),
        ]
        for e in (vm.get("pending") or [])
    ]
    payload = json.dumps(
        {"pending": pending_sig, "bbox": results.get("candidate_bbox") or {}},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _build_live_queue(
    vm: dict, results: dict, raw: bytes, crops_dir: Path
) -> list[dict]:
    """طابور مراجعة حي من سجل القرار — غير الحاسمة فقط، قصاصات + ترويسة
    السنوات من بايتات المستند نفسه، بلا GT (مع التخزين المؤقت للجلسة)."""
    import pypdfium2 as pdfium
    from src.analysis.comparison import LABELS_AR
    from src.extraction.human_review import EXTRACTION_VERSION, _sha256_file  # noqa: E402

    if not _is_pdf_bytes(raw):
        return []
    try:
        pdf = pdfium.PdfDocument(io.BytesIO(raw))
    except Exception:
        return []
    doc_id = _safe_doc_sha(vm.get("doc_sha"), raw)
    target_dir = crops_dir if crops_dir.name == doc_id else crops_dir / doc_id
    target_dir.mkdir(parents=True, exist_ok=True)
    doc_sha = hashlib.sha256(raw).hexdigest()
    queue = []
    curr_yr = results.get("curr_year")
    _prio = (
        "current_assets", "current_liabilities", "inventory",
        "total_assets", "total_liabilities", "equity",
        "net_income", "operating_cash_flow", "total_debt",
        "revenue", "long_term_debt", "short_term_credit_facilities", "cash",
    )
    _rank = {f: i for i, f in enumerate(_prio)}
    pending_sorted = sorted(
        vm["pending"],
        key=lambda e: (
            0 if (curr_yr is not None and str(e.get("year")) == str(curr_yr)) else 1,
            _rank.get(e["field"], 99),
            str(e.get("year")),
        ),
    )
    try:
        for e in pending_sorted:
            field, year = e["field"], e["year"]
            pages = e.get("pages") or []
            if not pages:
                continue
            bbox = (results.get("candidate_bbox") or {}).get(f"{field}|{year}")
            bbox_page = None
            if isinstance(bbox, list) and bbox and isinstance(bbox[0], dict):
                bbox_page = bbox[0].get("page")
            elif isinstance(bbox, dict):
                bbox_page = bbox.get("page")
            page_no = int(bbox_page) if bbox_page else int(pages[0])
            if page_no < 1 or page_no > len(pdf):
                continue
            page_png = target_dir / f"live_page_{page_no}.png"
            date_hdr_png = target_dir / f"live_date_header_{page_no}.png"
            if not page_png.exists() or not date_hdr_png.exists():
                page_pil = pdf[page_no - 1].render(scale=2.0).to_pil().convert("RGB")
                if not page_png.exists():
                    page_pil.save(page_png, "PNG")
                if not date_hdr_png.exists():
                    hdr_h = max(40, int(page_pil.height * 0.22))
                    page_pil.crop((0, 0, page_pil.width, hdr_h)).save(date_hdr_png, "PNG")
            crop_png = None
            bbox_rel = None
            if bbox:
                try:
                    img = pdf[page_no - 1].render(scale=3.0).to_pil().convert("RGB")
                    coords = _extract_bbox_coords(bbox, page_no, img.width, img.height, 3.0)
                    if coords:
                        x0, y0, x1, y1 = coords
                        bbox_rel = [
                            round(x0 / max(img.width, 1), 4),
                            round(y0 / max(img.height, 1), 4),
                            round(x1 / max(img.width, 1), 4),
                            round(y1 / max(img.height, 1), 4),
                        ]
                        crop = img.crop(
                            (
                                max(0, int(x0) - 6),
                                max(0, int(y0) - 6),
                                min(img.width, int(x1) + 6),
                                min(img.height, int(y1) + 6),
                            )
                        )
                        safe_field = re.sub(r"[^A-Za-z0-9_-]", "_", str(field))
                        safe_year = re.sub(r"[^A-Za-z0-9_-]", "_", str(year))
                        crop_png = target_dir / f"live_{safe_field}_{safe_year}_crop.png"
                        crop.save(crop_png, "PNG")
                except Exception:
                    crop_png = None
            raw_lbl = (results.get("candidate_labels") or {}).get(f"{field}|{year}")
            if isinstance(raw_lbl, list) and raw_lbl:
                raw_lbl = raw_lbl[0]
            label_text = str(raw_lbl or LABELS_AR.get(field, field) or field)
            hdr_ok = date_hdr_png.exists()
            ctx_complete = bool(crop_png and hdr_ok and label_text)
            queue.append(
                {
                    "packet_id": f"live|{field}|{page_no}|{year}",
                    "field": field,
                    "page": page_no,
                    "year": year,
                    "status": e.get("status"),
                    "crop_image": str(crop_png) if crop_png else None,
                    "page_image": str(page_png),
                    "date_header_image": str(date_hdr_png) if hdr_ok else None,
                    "label_text": label_text,
                    "bbox_rel": bbox_rel,
                    "machine_selected": e.get("final"),
                    "readings": {
                        "detection_line": (e.get("candidates") or [])[:4],
                        "crop_variants": [],
                    },
                    "conflict_reason": e.get("reason") or "",
                    "source_pdf": results.get("file_name"),
                    "pdf_sha256": doc_sha,
                    "page_image_sha256": _sha256_file(page_png),
                    "crop_sha256": _sha256_file(crop_png) if crop_png else None,
                    "extraction_version": EXTRACTION_VERSION,
                    "context": {
                        "year_header_available": hdr_ok,
                        "label_available": bool(label_text),
                        "context_complete": ctx_complete,
                    },
                    "confirmations": {
                        k: False for k in ("document", "field", "year", "position", "value")
                    },
                    "decision": None,
                }
            )
    finally:
        pdf.close()
    return queue


def _apply_human_approval_to_results(
    results: dict, field: str, year: int, approved_value: float, rec: dict
) -> None:
    """Promote a human-attested cell inside session `results` and recompute
    metrics/rows if the reviewer corrected the value."""
    from src.analysis.calculator import compute_year_metrics
    from src.analysis.comparison import build_comparison, growth_metrics

    val_f = float(approved_value)
    yr_i = int(year)
    changed_val = False
    for entry in results.get("decision_log") or []:
        if entry.get("field") == field and str(entry.get("year")) == str(yr_i):
            old_v = entry.get("final")
            if old_v is None or abs(float(old_v) - val_f) > 1.0:
                changed_val = True
            entry["status"] = rec.get("status", "VERIFIED_HUMAN")
            entry["final"] = val_f
            entry["reason"] = (
                f"إقرار بشري موثق — المراجع {rec.get('reviewer')} في {rec.get('timestamp')} "
                f"(seq={rec.get('seq')} · HMAC-SHA256)"
            )
    hr = results.setdefault("human_reviews", {})
    hr[f"{field}|{yr_i}"] = dict(rec)

    if changed_val:
        prev_y = results.get("prev_year")
        curr_y = results.get("curr_year")
        vals_map: dict[str, dict[int, float]] = {}
        for entry in results.get("decision_log") or []:
            f_e = entry.get("field")
            y_e = entry.get("year")
            v_e = entry.get("final")
            if f_e and y_e is not None and v_e is not None:
                vals_map.setdefault(f_e, {})[int(y_e)] = float(v_e)
        vals_map.setdefault(field, {})[yr_i] = val_f
        if prev_y is not None and curr_y is not None:
            pm = compute_year_metrics(int(prev_y), vals_map, prev_year=None)
            cm = compute_year_metrics(int(curr_y), vals_map, prev_year=int(prev_y))
            rows = build_comparison(pm, cm)
            g_rows = growth_metrics(pm, cm)
            results["prev_metrics"] = pm
            results["curr_metrics"] = cm
            results["rows"] = rows
            results["growth_rows"] = g_rows
            results["rows_by_key"] = {x.key: x for x in rows}


def sec_review(vm: dict, results: dict, raw: bytes | None) -> None:
    from src.extraction import human_review  # noqa: E402
    from src.extraction.human_review import (  # noqa: E402
        CONFIRMATION_KEYS,
        CONFIRMATION_LABELS_AR,
        apply_review,
        verify_log_integrity,
    )

    lang = _lang()
    is_ar = lang != "en"
    st.subheader(_T["review"][lang])
    if not (os.environ.get("REVIEWERS_FILE") or os.environ.get("REVIEWERS")) and not os.environ.get("PYTEST_CURRENT_TEST"):
        _def_rf = Path(__file__).resolve().parents[2] / "data" / "default_reviewers.json"
        if _def_rf.exists():
            os.environ["REVIEWERS_FILE"] = str(_def_rf)
        if not os.environ.get("REVIEW_HMAC_KEY"):
            os.environ["REVIEW_HMAC_KEY"] = "finsight-cloud-instance-hmac-key-2026"
    if not (os.environ.get("REVIEWERS_FILE") or os.environ.get("REVIEWERS")):
        render_empty_state(
            "المراجعة البشرية غير مفعّلة" if is_ar else "Human review disabled",
            "تتطلب المراجعة الموقّعة إعداد سجل مراجعين (REVIEWERS_FILE) ومفتاح توقيع (REVIEW_HMAC_KEY) في ‎.env أو Streamlit Secrets."
            if is_ar
            else "Signed human review requires REVIEWERS_FILE and REVIEW_HMAC_KEY in .env or Streamlit Secrets.",
            icon="🔐",
            next_step="أضف إعدادات المراجعين في ‎.env أو Streamlit Secrets ثم أعد تشغيل التطبيق."
            if is_ar
            else "Add reviewer credentials in .env or Streamlit Secrets and restart the app.",
        )
        return
    if raw is None:
        render_empty_state(
            "بايتات المستند غير متوفرة" if is_ar else "Document bytes unavailable",
            "المراجعة البشرية تتطلب وجود بايتات المستند الأصلية في الجلسة لعرض الصفحة والقصاصة."
            if is_ar
            else "Document bytes are not stored in the current session.",
            icon="📄",
            next_step="أعد رفع الملف عبر «تحليل جديد»."
            if is_ar
            else "Re-upload the file via New Analysis.",
        )
        return
    if not _is_pdf_bytes(raw):
        render_empty_state(
            "المراجعة المصوّرة لملفات PDF فقط" if is_ar else "Visual review is for PDF files only",
            "هذا المستند بصيغة جدول بيانات أو نص (CSV/Excel) وليس PDF مصوّرًا."
            if is_ar
            else "This file is a spreadsheet/CSV rather than a scanned PDF document.",
            icon="📊",
            next_step="راجع تفاصيل القيم ومصادرها في تبويب «القوائم والخانات»."
            if is_ar
            else "Inspect cell values and sources in the Statements & Cells tab.",
        )
        return
    current_sha = hashlib.sha256(raw).hexdigest()[:16]
    vm_doc_sha = str(vm.get("doc_sha") or "").strip()
    if vm_doc_sha and current_sha != vm_doc_sha:
        render_error_state(
            "عدم تطابق بصمة المستند" if is_ar else "Document hash mismatch",
            "بصمة المستند لا تطابق بصمة الاستخراج — المراجعة محجوبة حفاظًا على سلامة التدقيق."
            if is_ar
            else "Document hash does not match extraction provenance — review blocked.",
            next_step="أعد رفع الملف الأصلي عبر «تحليل جديد»."
            if is_ar
            else "Re-upload the original file via New Analysis.",
        )
        return
    env_log = os.environ.get("REVIEW_LOG_PATH")
    log_path = Path(env_log) if env_log else human_review.REVIEW_LOG
    ok, bad = verify_log_integrity(log_path)
    if not ok:
        render_error_state(
            "سجل المراجعات تالف" if is_ar else "Review log integrity failed",
            (f"تم رصد خلل في سلسلة المراجعات (seq={bad}) — المراجعة مرفوضة."
             if is_ar else f"Review log chain broken (seq={bad})."),
            next_step="تحقق من ملف سجل المراجعات ومفتاح التوقيع قبل المتابعة."
            if is_ar
            else "Inspect the review log and HMAC key before continuing.",
        )
        return
    doc_sha = _safe_doc_sha(vm_doc_sha or current_sha, raw)
    crops_dir = Path(tempfile.gettempdir()) / "live_review_crops" / doc_sha
    qkey = f"{doc_sha}|{_queue_signature(vm, results)}"
    if "live_queue" not in st.session_state or st.session_state.get("live_queue_key") != qkey:
        st.session_state["live_queue"] = _build_live_queue(vm, results, raw, crops_dir)
        st.session_state["live_queue_key"] = qkey
    queue = st.session_state["live_queue"]
    if not queue:
        render_success_state(
            "لا توجد خانات بانتظار المراجعة" if is_ar else "No cells awaiting review",
            "كل الخانات إما حاسمة أو بلا صفحة مصدر مصوّرة مسجلة."
            if is_ar
            else "All cells are either decisive or have no scanned page source.",
            next_step="يمكنك المتابعة إلى تبويب «التقارير» لتصدير النتائج."
            if is_ar
            else "Proceed to the Reports tab to export results.",
        )
        return
    # Live Health Score Unlock Progress Tracker for current fiscal year
    from src.analysis.comparison import LABELS_AR as _REV_LBL

    curr_yr = results.get("curr_year")
    _crit_fields = (
        "current_assets", "current_liabilities", "inventory",
        "total_assets", "total_liabilities", "equity",
        "net_income", "operating_cash_flow",
    )
    _blocked_curr = _health_blocked_fields(vm, results)
    _crit_rem = [f for f in _crit_fields if f in _blocked_curr]
    if _crit_rem and curr_yr is not None:
        chips = "".join(
            f'<span class="fs-gate {"ok" if f not in _blocked_curr else "pend"}" style="margin:2px;">'
            f'{"✓" if f not in _blocked_curr else "◐"} {esc(_REV_LBL.get(f, f))}</span>'
            for f in _crit_fields
        )
        st.markdown(
            f'<div class="report-card" style="--accent:var(--fs-primary);margin-bottom:12px;">'
            f'<div style="font-weight:700;margin-bottom:6px;">'
            f'🔓 {("لفتح الدرجة الصحية الرسمية المعتمدة لعام " + str(curr_yr) + f" — متبقي {len(_crit_rem)} من {len(_crit_fields)} خانات حرجة:" if is_ar else f"Unlock Official {curr_yr} Health Score — {len(_crit_rem)} of {len(_crit_fields)} critical cells remaining:")}'
            f'</div><div style="display:flex;flex-wrap:wrap;gap:6px;">{chips}</div></div>',
            unsafe_allow_html=True,
        )

    pkt = st.selectbox(
        "الخانة" if is_ar else "Cell",
        queue,
        format_func=lambda p: (
            f"{_REV_LBL.get(p['field'], p['field'])} · {p['year']} · صفحة {p['page']}"
            if is_ar
            else f"{p['field']} · {p['year']} · p{p['page']}"
        ),
    )
    ctx_ok = bool((pkt.get("context") or {}).get("context_complete"))
    if ctx_ok:
        st.caption(
            "سياق الخانة مكتمل (صورة الصفحة + ترويسة السنوات + قصاصة الخلية) — يمكنك الاعتماد (VERIFIED_HUMAN) بتوقيع HMAC-SHA256 أو الرفض."
            if is_ar
            else "Complete cell context (page + year header + cell crop) — both VERIFIED_HUMAN approval and rejection are enabled."
        )
    else:
        st.caption(
            "سياق الخانة الحي بلا قصاصة محددة — سلسلة المراجعة تسمح بالرفض فقط هنا (قاعدة السياق الكامل، بلا تجاوز)."
            if is_ar
            else "Live context incomplete (no cell crop) — reject-only."
        )
    col_a, col_b = st.columns(2)
    with col_a:
        if Path(pkt["page_image"]).exists():
            st.image(
                pkt["page_image"],
                caption=f"صفحة {pkt['page']}" if is_ar else f"page {pkt['page']}",
            )
    with col_b:
        if pkt.get("date_header_image") and Path(pkt["date_header_image"]).exists():
            st.image(
                pkt["date_header_image"],
                caption="ترويسة السنوات والعملة (أعلى الصفحة)" if is_ar else "Year & currency header",
            )
        if pkt["crop_image"] and Path(pkt["crop_image"]).exists():
            st.image(
                pkt["crop_image"],
                caption="قصاصة الخلية" if is_ar else "Focused cell crop",
            )
        else:
            render_empty_state(
                "لا قصاصة (بلا bbox)" if is_ar else "No crop (no bbox)",
                "هذه الخانة مسجلة بالصفحة دون قصاصة محددة — الرفض فقط متاح."
                if is_ar
                else "No bounding box crop recorded — reject-only mode.",
                icon="🖼️",
            )
        msel = pkt.get("machine_selected")
        if msel is not None:
            st.markdown(
                f"**{('القيمة المستخرجة آليًا:' if is_ar else 'Machine value:')}** "
                f"`{msel:,.0f}`"
            )
    conf = {}
    st.markdown(
        "**"
        + (
            "التأكيدات المطلوبة قبل التوقيع"
            if is_ar
            else "Required confirmations before signing"
        )
        + "**"
    )
    for k in CONFIRMATION_KEYS:
        if k == "value":
            continue
        conf[k] = st.checkbox(
            CONFIRMATION_LABELS_AR.get(k, k), key=f"conf-{doc_sha}-{pkt['packet_id']}-{k}"
        )
    conf_val = False
    val_str = ""
    if ctx_ok:
        conf_val = st.checkbox(
            CONFIRMATION_LABELS_AR.get("value", "القيمة الرقمية الصحيحة"),
            key=f"confval-{doc_sha}-{pkt['packet_id']}-value",
        )
        default_v = "" if pkt.get("machine_selected") is None else f"{pkt['machine_selected']:,.0f}"
        val_str = st.text_input(
            "القيمة المعتمدة (أبقها كما هي أو صحّحها من القصاصة)"
            if is_ar
            else "Approved value (keep or correct from crop)",
            value=default_v,
            key=f"val-{doc_sha}-{pkt['packet_id']}",
        )
    reason = st.text_area(
        "سبب الرفض أو ملاحظة الاعتماد (يسجل في السلسلة الموقعة)"
        if is_ar
        else "Reject reason or approval note (recorded in the signed chain)",
        "",
    )
    saved_sess = st.session_state.get("review_session") or {}
    c1, c2 = st.columns(2)
    reviewer = c1.text_input(
        "اسم المراجع" if is_ar else "Reviewer",
        saved_sess.get("reviewer", ""),
    )
    credential = c2.text_input(
        "PIN",
        type="password",
        help="الرمز السري للمراجع" if is_ar else "Reviewer PIN",
    )
    if saved_sess.get("token") and saved_sess.get("reviewer") == reviewer and not credential:
        st.caption(
            f"🔑 جلسة مراجع نشطة ({saved_sess['reviewer']}) — يمكنك الاعتماد مباشرة بدون إعادة إدخال PIN."
            if is_ar
            else f"🔑 Active reviewer session ({saved_sess['reviewer']}) — PIN not needed again."
        )

    def _auth_kwargs() -> dict:
        if credential:
            return {"reviewer": reviewer, "credential": credential}
        if saved_sess.get("token") and saved_sess.get("reviewer") == reviewer:
            return {"reviewer": reviewer, "session_token": saved_sess["token"]}
        return {"reviewer": reviewer, "credential": credential}

    if ctx_ok:
        if st.button(
            "✅ اعتماد القيمة رسميًا (VERIFIED_HUMAN)"
            if is_ar
            else "✅ Approve value (VERIFIED_HUMAN)",
            type="primary",
            use_container_width=True,
            key=f"approve-btn-{doc_sha}-{pkt['packet_id']}",
        ):
            if not (all(conf[k] for k in conf) and conf_val):
                st.error(
                    "الاعتماد يتطلب تأكيد العناصر الخمسة جميعها أولًا."
                    if is_ar
                    else "Approval requires all five confirmations."
                )
            else:
                from src.extraction.normalizer import parse_number

                parsed_v = parse_number(val_str)
                if parsed_v is None:
                    st.error(
                        "أدخل قيمة رقمية صالحة للاعتماد."
                        if is_ar
                        else "Enter a valid numeric value."
                    )
                else:
                    try:
                        rec = apply_review(
                            queue,
                            pkt["packet_id"],
                            approved_value=float(parsed_v),
                            log_path=log_path,
                            decision_note=(reason.strip() or "اعتماد بشري موثق من القصاصة وترويسة السنوات"),
                            confirmations={**conf, "value": True},
                            **_auth_kwargs(),
                        )
                        if credential and reviewer:
                            try:
                                tok = human_review.authenticate(reviewer, credential)
                                tok_str = tok["token"] if isinstance(tok, dict) else str(tok)
                                st.session_state["review_session"] = {
                                    "reviewer": reviewer,
                                    "token": tok_str,
                                }
                            except Exception:
                                pass
                        _apply_human_approval_to_results(
                            results, pkt["field"], int(pkt["year"]), float(parsed_v), rec
                        )
                        try:
                            from src.analysis.portfolio import record_from_results, save_record

                            save_record(record_from_results(results))
                        except Exception:
                            pass
                        st.session_state.pop("live_queue", None)
                        st.session_state.pop("live_queue_key", None)
                        st.session_state.pop("_report_memo", None)
                        st.success(
                            f"✅ تم اعتماد {_REV_LBL.get(pkt['field'], pkt['field'])} ({pkt['year']}) رسميًا في السلسلة الموقعة (رقم={rec.get('seq')})."
                            if is_ar
                            else f"✅ Approved {pkt['field']} ({pkt['year']}) in signed chain (seq={rec.get('seq')})."
                        )
                        st.rerun()
                    except Exception as exc:
                        st.error(f"رفض السلسلة: {exc}" if is_ar else f"Chain refused: {exc}")

    if st.button(
        "تسجيل الرفض في السلسلة" if is_ar else "Record rejection",
        type="secondary" if ctx_ok else "primary",
        use_container_width=True,
    ):
        if not all(conf[k] for k in conf):
            st.error("أكد العناصر الأربعة أولًا." if is_ar else "Confirm the four elements first.")
        elif not reason.strip():
            st.error("سبب الرفض مطلوب." if is_ar else "A reason is required.")
        else:
            try:
                rec = apply_review(
                    queue,
                    pkt["packet_id"],
                    approved_value=None,
                    log_path=log_path,
                    decision_note=reason.strip(),
                    confirmations={**conf, "value": False},
                    **_auth_kwargs(),
                )
                st.success(
                    "سُجل الرفض في السلسلة الموقعة."
                    if is_ar
                    else "Rejection recorded in signed chain."
                )
                st.caption(f"seq={rec.get('seq')} · hash={str(rec.get('record_hash'))[:16]}")
            except Exception as exc:
                st.error(f"رفض السلسلة: {exc}" if is_ar else f"Chain refused: {exc}")


# ---------------------------------------------------------------------------
# Tab 9: سجل ومقارنة الشركات (مكتبة الدراسة التطبيقية — تراكمية لكل ملف يُرفع)
# ---------------------------------------------------------------------------

def _fmt_port_num(val: float | None, suffix: str = "", decimals: int = 1) -> str:
    if val is None:
        return "—"
    return f"{val:,.{decimals}f}{suffix}"


def _build_portfolio_table_html(
    records: list,
    active_company: str = "",
    active_year: int | None = None,
    lang: str = "ar",
) -> str:
    """RTL/LTR custom HTML comparison table across analyzed companies (no st.dataframe)."""
    is_ar = lang != "en"
    headers = (
        [
            "#", "الشركة", "الفترة", "الإيرادات", "صافي الربح",
            "هامش صافي %", "ROE %", "النسبة الجارية", "الدين / الملكية",
            "الدرجة الصحية", "Altman Z″",
        ]
        if is_ar
        else [
            "#", "Company", "Period", "Revenue", "Net Income",
            "Net Margin %", "ROE %", "Current Ratio", "D/E",
            "Health Score", "Altman Z″",
        ]
    )
    rows_html: list[str] = []
    for idx, r in enumerate(records, 1):
        is_active = (
            bool(active_company)
            and r.company.strip().lower() == active_company.strip().lower()
            and (active_year is None or r.curr_year == active_year)
        )
        cur_badge = (
            f' <span class="badge badge-pass">{"الحالية" if is_ar else "Active"}</span>'
            if is_active
            else ""
        )
        rev_s = fmt_value(r.revenue, "currency", r.currency) if r.revenue is not None else "—"
        ni_s = fmt_value(r.net_income, "currency", r.currency) if r.net_income is not None else "—"
        nm_s = _fmt_port_num(r.net_margin_pct, "%", 1)
        roe_s = _fmt_port_num(r.roe_pct, "%", 1)
        cr_s = _fmt_port_num(r.current_ratio, "x", 2)
        de_s = _fmt_port_num(r.debt_to_equity, "x", 2)
        if r.health_total is not None:
            hl_cell = f'<bdi dir="ltr"><b>{r.health_total:.0f}/100</b></bdi>'
        else:
            hl_cell = (
                f'<span class="badge badge-warn">{"محجوبة" if is_ar else "Refused"}</span>'
            )
        if r.altman_score is not None:
            zone_txt = f" {esc(r.altman_zone)}" if r.altman_zone else ""
            alt_cell = f'<bdi dir="ltr">{r.altman_score:.2f}</bdi>{zone_txt}'
        else:
            alt_cell = "—"
        period_s = f"{r.prev_year} → {r.curr_year}"
        row_style = ' style="background:var(--fs-row-hover);font-weight:600;"' if is_active else ""
        rows_html.append(
            f"<tr{row_style}>"
            f'<td class="num"><bdi dir="ltr">{idx}</bdi></td>'
            f"<td><b>{esc(r.company)}</b>{cur_badge}</td>"
            f'<td class="num"><bdi dir="ltr">{esc(period_s)}</bdi></td>'
            f'<td class="num"><bdi dir="ltr">{esc(rev_s)}</bdi></td>'
            f'<td class="num"><bdi dir="ltr">{esc(ni_s)}</bdi></td>'
            f'<td class="num"><bdi dir="ltr">{esc(nm_s)}</bdi></td>'
            f'<td class="num"><bdi dir="ltr">{esc(roe_s)}</bdi></td>'
            f'<td class="num"><bdi dir="ltr">{esc(cr_s)}</bdi></td>'
            f'<td class="num"><bdi dir="ltr">{esc(de_s)}</bdi></td>'
            f"<td>{hl_cell}</td>"
            f"<td>{alt_cell}</td>"
            "</tr>"
        )
    num_idx = {0, 2, 3, 4, 5, 6, 7, 8}
    th_html = "".join(
        f'<th class="num">{esc(h)}</th>' if i in num_idx else f"<th>{esc(h)}</th>"
        for i, h in enumerate(headers)
    )
    return (
        '<div class="table-wrap">'
        '<table class="fin-table">'
        f"<thead><tr>{th_html}</tr></thead>"
        f'<tbody>{"".join(rows_html)}</tbody>'
        "</table></div>"
    )


def _build_portfolio_excel(records: list, lang: str = "ar") -> bytes:
    """Build a styled Excel (.xlsx) workbook comparing all saved companies."""
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill

    is_ar = lang != "en"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "مقارنة الشركات" if is_ar else "Companies Comparison"
    if is_ar:
        ws.views.sheetView[0].rightToLeft = True

    headers = (
        [
            "الشركة", "السنة السابقة", "السنة الحالية", "العملة",
            "الإيرادات", "صافي الربح", "هامش صافي الربح %",
            "ROE %", "ROA %", "النسبة الجارية", "الدين / حقوق الملكية",
            "دوران الأصول", "الدرجة الصحية (/100)", "التصنيف الصحي",
            "Altman Z″", "منطقة Altman", "اسم الملف", "تاريخ الحفظ",
        ]
        if is_ar
        else [
            "Company", "Prev Year", "Curr Year", "Currency",
            "Revenue", "Net Income", "Net Margin %",
            "ROE %", "ROA %", "Current Ratio", "Debt / Equity",
            "Asset Turnover", "Health Score (/100)", "Health Label",
            "Altman Z″", "Altman Zone", "File Name", "Saved At",
        ]
    )
    ws.append(headers)
    head_fill = PatternFill(start_color="4F46E5", end_color="4F46E5", fill_type="solid")
    head_font = Font(bold=True, color="FFFFFF")
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = head_fill
        cell.font = head_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for r in records:
        ws.append([
            r.company, r.prev_year, r.curr_year, r.currency,
            r.revenue, r.net_income, r.net_margin_pct,
            r.roe_pct, r.roa_pct, r.current_ratio, r.debt_to_equity,
            r.asset_turnover, r.health_total, r.health_label,
            r.altman_score, r.altman_zone, r.file_name, r.saved_at,
        ])

    for col in ws.columns:
        max_len = max((len(str(c.value or "")) for c in col), default=8)
        ws.column_dimensions[col[0].column_letter].width = min(max(max_len + 4, 12), 34)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def sec_portfolio(vm: dict, results: dict) -> None:
    """سجل ومقارنة الشركات: يحفظ كل ملف يُحلّل تلقائياً ويبني جدول مقارنة ورسماً وتقريراً مجمّعاً."""
    import pandas as pd
    import plotly.graph_objects as go

    from src.analysis.portfolio import (
        clear_library,
        load_records,
        record_from_results,
        save_record,
    )
    from src.dashboard import design_system as DS
    from src.dashboard.study_report import build_study_report

    lang = st.session_state.get("ui_lang", "ar")
    is_ar = lang != "en"

    # Ensure the currently viewed company is persisted in the library
    if results and results.get("curr_metrics") is not None:
        try:
            save_record(record_from_results(results))
        except Exception:
            pass

    st.markdown(
        '<div class="sec-h">'
        + ("📚 سجل ومقارنة الشركات (مكتبة الدراسة)" if is_ar else "📚 Companies Portfolio & Comparison")
        + "</div>",
        unsafe_allow_html=True,
    )
    st.caption(
        "كل ملف تحلّله لوحده يُحفَظ هنا تلقائيًا (باسم الشركة وسنتها) — ارفع ملفات الشركات واحدًا تلو الآخر "
        "لتبني جدول المقارنة والرسوم وتقرير الدراسة التطبيقية المجمّع تلقائيًا وبلا أي طلبات API إضافية."
        if is_ar
        else "Every analyzed file is saved here automatically (keyed by company + year). Upload companies one by one "
             "to build the cross-company table, comparison charts, and unified study report with zero extra API calls."
    )

    records = load_records()
    if not records:
        render_empty_state(
            "مكتبة الشركات فارغة بعد" if is_ar else "Companies library is empty",
            "كل شركة تُحلّل بنجاح تُحفَظ هنا تلقائيًا لبناء جدول مقارنة الشركات."
            if is_ar
            else "Every successfully analyzed company is saved here automatically.",
            icon="📚",
            next_step="ارفع قوائم أول شركة وستظهر هنا تلقائيًا." if is_ar else "Analyze your first file to populate the library.",
        )
        return

    if len(records) == 1:
        st.info(
            "📌 تم حفظ أول شركة في السجل! ارفع الملف التالي عبر «تحليل جديد» من الشريط الجانبي "
            "وستُضاف الشركات تلقائياً جنباً إلى جنب للمقارنة (حتى 20+ شركة)."
            if is_ar
            else "📌 First company saved! Upload your next file via «New Analysis» in the sidebar to compare multiple companies side-by-side."
        )

    # Top KPI summary cards
    health_vals = [r.health_total for r in records if r.health_total is not None]
    avg_health = f"{sum(health_vals) / len(health_vals):.1f}/100" if health_vals else ("محجوبة" if is_ar else "Refused")
    nm_recs = [r for r in records if r.net_margin_pct is not None]
    best_nm = max(nm_recs, key=lambda x: x.net_margin_pct) if nm_recs else None
    roe_recs = [r for r in records if r.roe_pct is not None]
    best_roe = max(roe_recs, key=lambda x: x.roe_pct) if roe_recs else None

    kpi_html = (
        '<div class="kpi-grid">'
        + stat_card(
            "الشركات المحلّلة" if is_ar else "Analyzed Companies",
            f"{len(records)}",
            "تراكمي تلقائي لكل ملف" if is_ar else "Auto-accumulated per file",
        )
        + stat_card(
            "متوسط الدرجة الصحية" if is_ar else "Avg. Health Score",
            avg_health,
            (
                f"{len(health_vals)}/{len(records)} بدرجة رسمية"
                if is_ar
                else f"{len(health_vals)}/{len(records)} official"
            ),
        )
        + stat_card(
            "أعلى هامش صافي ربح" if is_ar else "Top Net Margin",
            f"{best_nm.net_margin_pct:.1f}%" if best_nm else "—",
            f"{best_nm.company} ({best_nm.curr_year})" if best_nm else "—",
        )
        + stat_card(
            "أعلى عائد ملكية (ROE)" if is_ar else "Top ROE",
            f"{best_roe.roe_pct:.1f}%" if best_roe else "—",
            f"{best_roe.company} ({best_roe.curr_year})" if best_roe else "—",
        )
        + "</div>"
    )
    st.markdown(kpi_html, unsafe_allow_html=True)

    # Sort + search controls
    sort_options = (
        {
            "الاسم (أبجدي)": lambda r: (r.company.lower(), r.curr_year),
            "الدرجة الصحية (الأعلى)": lambda r: (-(r.health_total if r.health_total is not None else -1e9), r.company),
            "الإيرادات (الأعلى)": lambda r: (-(r.revenue if r.revenue is not None else -1e18), r.company),
            "هامش صافي الربح (الأعلى)": lambda r: (-(r.net_margin_pct if r.net_margin_pct is not None else -1e9), r.company),
            "العائد على الملكية ROE (الأعلى)": lambda r: (-(r.roe_pct if r.roe_pct is not None else -1e9), r.company),
            "النسبة الجارية (الأعلى)": lambda r: (-(r.current_ratio if r.current_ratio is not None else -1e9), r.company),
            "Altman Z″ (الأعلى)": lambda r: (-(r.altman_score if r.altman_score is not None else -1e9), r.company),
        }
        if is_ar
        else {
            "Name (A–Z)": lambda r: (r.company.lower(), r.curr_year),
            "Health Score (High→Low)": lambda r: (-(r.health_total if r.health_total is not None else -1e9), r.company),
            "Revenue (High→Low)": lambda r: (-(r.revenue if r.revenue is not None else -1e18), r.company),
            "Net Margin (High→Low)": lambda r: (-(r.net_margin_pct if r.net_margin_pct is not None else -1e9), r.company),
            "ROE (High→Low)": lambda r: (-(r.roe_pct if r.roe_pct is not None else -1e9), r.company),
            "Current Ratio (High→Low)": lambda r: (-(r.current_ratio if r.current_ratio is not None else -1e9), r.company),
            "Altman Z″ (High→Low)": lambda r: (-(r.altman_score if r.altman_score is not None else -1e9), r.company),
        }
    )
    c_sort, c_search = st.columns([2, 2])
    with c_sort:
        sort_lbl = st.selectbox(
            "الترتيب حسب" if is_ar else "Sort by",
            list(sort_options.keys()),
            key="portfolio_sort_by",
        )
    with c_search:
        q_co = st.text_input(
            "بحث باسم الشركة" if is_ar else "Filter by company",
            value="",
            key="portfolio_search_co",
        ).strip().lower()

    shown = [r for r in records if not q_co or q_co in r.company.lower() or q_co in r.file_name.lower()]
    shown = sorted(shown, key=sort_options[sort_lbl])

    active_co = str(vm.get("company") or results.get("company") or "")
    active_yr = results.get("curr_year")
    st.markdown(
        _build_portfolio_table_html(shown, active_company=active_co, active_year=active_yr, lang=lang),
        unsafe_allow_html=True,
    )

    # Interactive comparison chart
    chart_metrics = (
        {
            "العائد على حقوق الملكية ROE (%)": ("roe_pct", "%"),
            "هامش صافي الربح (%)": ("net_margin_pct", "%"),
            "العائد على الأصول ROA (%)": ("roa_pct", "%"),
            "الدرجة الصحية (/100)": ("health_total", ""),
            "النسبة الجارية (x)": ("current_ratio", "x"),
            "الدين إلى حقوق الملكية (x)": ("debt_to_equity", "x"),
            "Altman Z″": ("altman_score", ""),
        }
        if is_ar
        else {
            "Return on Equity ROE (%)": ("roe_pct", "%"),
            "Net Profit Margin (%)": ("net_margin_pct", "%"),
            "Return on Assets ROA (%)": ("roa_pct", "%"),
            "Health Score (/100)": ("health_total", ""),
            "Current Ratio (x)": ("current_ratio", "x"),
            "Debt to Equity (x)": ("debt_to_equity", "x"),
            "Altman Z″": ("altman_score", ""),
        }
    )
    chosen_metric_lbl = st.selectbox(
        "📊 مؤشر الرسم البياني المقارن" if is_ar else "📊 Comparison Chart Metric",
        list(chart_metrics.keys()),
        key="portfolio_chart_metric",
    )
    attr_name, unit_sfx = chart_metrics[chosen_metric_lbl]
    plotted = [r for r in shown if getattr(r, attr_name, None) is not None]
    if plotted:
        x_labels = [f"{r.company} ({r.curr_year})" for r in plotted]
        y_vals = [float(getattr(r, attr_name)) for r in plotted]
        bar_colors = [
            DS.SUCCESS
            if (active_co and r.company.strip().lower() == active_co.strip().lower() and r.curr_year == active_yr)
            else DS.PRIMARY
            for r in plotted
        ]
        fig = go.Figure(
            go.Bar(
                x=x_labels,
                y=y_vals,
                marker_color=bar_colors,
                text=[f"{v:.2f}{unit_sfx}" if unit_sfx == "x" else f"{v:.1f}{unit_sfx}" for v in y_vals],
                textposition="outside",
            )
        )
        fig.update_layout(
            title=chosen_metric_lbl,
            xaxis_title="",
            yaxis_title=unit_sfx or chosen_metric_lbl,
            height=370,
            margin=dict(l=16, r=16, t=50, b=24),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption(
            "لا توجد قيم متاحة لهذا المؤشر بين الشركات المسجّلة بعد."
            if is_ar
            else "No values available for this metric across saved companies yet."
        )

    # Export row: Excel + CSV + HTML Study Report + Reset
    df_csv = pd.DataFrame([
        {
            "الشركة": r.company,
            "السنة السابقة": r.prev_year,
            "السنة الحالية": r.curr_year,
            "العملة": r.currency,
            "الإيرادات": r.revenue,
            "صافي الربح": r.net_income,
            "هامش صافي %": r.net_margin_pct,
            "ROE %": r.roe_pct,
            "ROA %": r.roa_pct,
            "النسبة الجارية": r.current_ratio,
            "الدين/حقوق الملكية": r.debt_to_equity,
            "دوران الأصول": r.asset_turnover,
            "الدرجة الصحية": r.health_total,
            "Altman Z": r.altman_score,
            "منطقة Altman": r.altman_zone,
            "الملف": r.file_name,
        }
        for r in shown
    ])

    col_xl, col_csv, col_html, col_clr = st.columns([2, 2, 2, 1.5])
    with col_xl:
        try:
            xl_bytes = _build_portfolio_excel(shown, lang=lang)
            st.download_button(
                "📊 تصدير Excel مجمّع" if is_ar else "📊 Export Excel (.xlsx)",
                data=xl_bytes,
                file_name="companies_comparison.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key="dl_portfolio_xlsx",
            )
        except Exception:
            pass
    with col_csv:
        st.download_button(
            "⬇️ تصدير CSV" if is_ar else "⬇️ Export CSV",
            data=df_csv.to_csv(index=False).encode("utf-8-sig"),
            file_name="companies_comparison.csv",
            mime="text/csv",
            use_container_width=True,
            key="dl_portfolio_csv",
        )
    with col_html:
        st.download_button(
            "📄 تقرير الدراسة (HTML ← PDF)" if is_ar else "📄 Study Report (HTML)",
            data=build_study_report(shown),
            file_name="study_report.html",
            mime="text/html",
            use_container_width=True,
            key="dl_portfolio_html",
        )
    with col_clr:
        if st.button(
            "🗑️ مسح السجل" if is_ar else "🗑️ Clear Library",
            use_container_width=True,
            key="btn_clear_portfolio_new_ui",
        ):
            if st.session_state.get("confirm_clear_library"):
                clear_library()
                st.session_state["confirm_clear_library"] = False
                st.rerun()
            else:
                st.session_state["confirm_clear_library"] = True
                st.warning(
                    "اضغط «مسح السجل» مرة ثانية للتأكيد."
                    if is_ar
                    else "Click Clear Library again to confirm."
                )


def render(results: dict, analysis, raw: bytes | None) -> None:
    """نقطة دخول الواجهة — تستدعى من app.py."""
    lang = st.session_state.get("ui_lang", "ar")
    is_ar = lang != "en"
    vm = build_view_model(results, st.session_state.get("currency", "$"))

    with st.sidebar:
        st.markdown("### " + ("لوحة التحكم" if is_ar else "Control Panel"))
        curr_val = st.text_input(
            "رمز العملة" if is_ar else "Currency symbol",
            value=st.session_state.get("currency", "$"),
            max_chars=4,
            key="new_ui_currency_input",
        )
        st.session_state["currency"] = curr_val.strip() or "$"
        vm["currency"] = st.session_state["currency"]

        st.caption(f"{vm['file_name']}")
        st.caption(f"{_T['unit'][lang]}: {vm['unit_note'] or '-'}")
        st.caption(f"{_T['doc_sha'][lang]}: `{vm['doc_sha']}`")
        from src.dashboard.notes_ar import note_ar

        for n in vm["profile"][:2]:
            st.caption(note_ar(n) if is_ar else str(n))
        st.divider()
        try:
            from src.ai.gemini_agent import get_pool, reset_pool

            _ps = get_pool().status()
            _n_keys = _ps.get("active_keys", 0)
            _tot_keys = _ps.get("total_keys", 0)
            _u_pairs = _ps.get("usable_pairs", 0)
            _t_pairs = _ps.get("total_pairs", 0)
            _est_rem = _ps.get("est_remaining_quota", _u_pairs * 20)
            _est_tot = _ps.get("est_daily_quota", _t_pairs * 20)
            _exp_title = (
                f"🔑 مسبح Gemini ({_n_keys}/{_tot_keys} · {_u_pairs}/{_t_pairs} زوج)"
                if is_ar
                else f"🔑 Gemini Pool ({_n_keys}/{_tot_keys} · {_u_pairs}/{_t_pairs} pairs)"
            )
            with st.expander(_exp_title, expanded=False):
                _sw = _ps.get("last_switch_ms")
                _sw_s = (
                    (f" · ⚡ تبديل: {_sw}ms" if is_ar else f" · ⚡ switch: {_sw}ms")
                    if _sw is not None
                    else ""
                )
                st.caption(
                    (
                        f"الحصة المقدّرة: ~{_est_rem} / {_est_tot} طلب/يوم (20 × {_t_pairs} زوج)\n\n"
                        f"ناجح: {_ps.get('total_ok_calls', 0)} · مستنفد يومي: {_ps.get('depleted_pairs', 0)} · "
                        f"تبريد دقيقة: {_ps.get('rpm_cooling_pairs', 0)}{_sw_s}"
                    )
                    if is_ar
                    else (
                        f"Est. quota: ~{_est_rem} / {_est_tot} req/day (20 × {_t_pairs} pairs)\n\n"
                        f"OK: {_ps.get('total_ok_calls', 0)} · Daily depleted: {_ps.get('depleted_pairs', 0)} · "
                        f"RPM cooling: {_ps.get('rpm_cooling_pairs', 0)}{_sw_s}"
                    )
                )
                for _idx_m, _rm in enumerate(_ps.get("model_ranking") or [], 1):
                    _cool_tag = " ❄️" if _rm.get("cooling") else ""
                    _lat_tag = f" · {_rm['avg_s']}s" if _rm.get("avg_s") is not None else ""
                    st.caption(
                        f"{_idx_m}. `{_rm['model']}` — ✓{_rm['ok']} / ✗{_rm['fail']}{_lat_tag}{_cool_tag}"
                    )
                _active_models = _ps.get("models") or []
                if len(_active_models) < 7 or "gemini-flash-lite-latest" not in _active_models:
                    if st.button(
                        "⚡ تفعيل أسرع 7 موديلات (980 طلب/يوم)" if is_ar else "⚡ Activate 7 fastest models",
                        use_container_width=True,
                        key="new_ui_activate_fast7_btn",
                    ):
                        from src.ai.key_pool import DEFAULT_MODELS

                        os.environ["GEMINI_MODELS"] = ",".join(DEFAULT_MODELS)
                        reset_pool()
                        st.rerun()
                if st.button(
                    "🔄 إعادة ضبط مسبح المفاتيح" if is_ar else "🔄 Reset key pool",
                    use_container_width=True,
                    key="new_ui_reset_pool_btn",
                ):
                    reset_pool()
                    st.rerun()
        except Exception:
            pass
        if st.button(_T["new_analysis"][lang], use_container_width=True):
            for k in (
                "results",
                "analysis",
                "raw_bytes",
                "ev_cell",
                "live_queue",
                "live_queue_key",
                "_report_memo",
                "_ev_img_cache",
                "new_ui_currency_input",
                "currency",
                "stmt_gate_filter",
                "stmt_search",
                "metrics_cat_filter",
                "metrics_verif_filter",
                "metrics_search_query",
                "confirm_clear_cache",
                "confirm_clear_library",
            ):
                st.session_state.pop(k, None)
            for k in [k for k in st.session_state if str(k).startswith("conf-")]:
                st.session_state.pop(k, None)
            st.rerun()
        if st.button("🧹 مسح الكاش المحلي" if is_ar else "🧹 Clear local cache", use_container_width=True):
            from src.extraction.result_cache import clear_all_caches
            clear_all_caches()
            for k in ("results", "analysis", "raw_bytes", "ev_cell", "live_queue", "live_queue_key", "_report_memo", "_ev_img_cache"):
                st.session_state.pop(k, None)
            st.rerun()
        with st.expander("⚙️ خيارات العرض واللغة" if is_ar else "⚙️ View & Language", expanded=False):
            if st.button(_T["classic"][lang], use_container_width=True, type="primary"):
                st.session_state["ui_mode"] = "classic"
                st.session_state["ui_mode_classic_toggle"] = True
                st.rerun()
            if st.button("English / عربي", use_container_width=True):
                st.session_state["ui_lang"] = "en" if lang == "ar" else "ar"
                st.rerun()

    render_header()

    tabs = st.tabs(
        [
            _T["overview"][lang],
            _T["statements"][lang],
            _T["metrics"][lang],
            _T["health"][lang],
            _T["insights"][lang],
            _T["chat"][lang],
            _T["review"][lang],
            _T["reports"][lang],
            _T["portfolio"][lang],
        ]
    )
    with tabs[0]:
        sec_overview(vm, results)
    with tabs[1]:
        sec_statements(vm, raw)
    with tabs[2]:
        sec_metrics(vm, results)
    with tabs[3]:
        sec_health(vm, results)
    with tabs[4]:
        sec_insights(vm, analysis)
    with tabs[5]:
        from app import notes_screen

        notes_screen(results)
    with tabs[6]:
        sec_review(vm, results, raw)
    with tabs[7]:
        sec_reports(vm, results, analysis)
    with tabs[8]:
        sec_portfolio(vm, results)
