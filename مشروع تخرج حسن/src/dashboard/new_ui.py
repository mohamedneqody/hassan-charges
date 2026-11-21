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
            item = matched[-1] if matched else bbox[-1]
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

    page_no = int(pages[0])
    bbox = cell.get("bbox")
    img, crop = _cached_evidence_images(raw, current_sha, page_no, bbox)
    col_page, col_crop = st.columns([3, 2])
    with col_page:
        if img:
            st.image(img, caption=f"{_t('evidence')} — p{page_no}")
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
        names = ", ".join(sorted({e["field"] for e in vm["pending"]})[:8])
        st.warning(
            f"{_T['pending'][lang]}: {pending_cells} — {names}"
            + (", ..." if pending_cells > 8 else "")
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

    for c in visible:
        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([2.2, 1.5, 1.6, 1.0])
            disp_lbl = c["label"] if is_ar else c.get("label_en", c["label"])
            with col1:
                st.markdown(f"**{esc(disp_lbl)}** · {esc(c['year'])}")
                if c["raw_label"] and c["raw_label"] != c["label"]:
                    st.caption(
                        ("كما قُرئت: " if is_ar else "as read: ")
                        + str(c["raw_label"])
                    )
            with col2:
                val_txt = (
                    cell_value_display(c["value"], vm["unit_scale"], vm["currency"])
                    if is_ar
                    else (
                        "N/A"
                        if c["value"] is None
                        else f"{vm['currency']}{humanize(c['value'], vm['unit_scale'])}"
                    )
                )
                st.markdown(
                    f'<span class="fs-num"><bdi dir="ltr">{esc(val_txt)}</bdi></span>',
                    unsafe_allow_html=True,
                )
            with col3:
                if c["reviewed"]:
                    st.markdown(
                        "✓ " + ("موثق بشريًا" if is_ar else "human-attested")
                    )
                gate_lbl = (
                    c["gate_label"]
                    if is_ar
                    else _GATE_EN.get(c["gate"], c["gate_label"])
                )
                st.markdown(
                    gate_badge(c["gate"], gate_lbl),
                    unsafe_allow_html=True,
                )
            with col4:
                if st.button(
                    _T["open_evidence"][lang],
                    key=f"ev-{c['field']}-{c['year']}",
                    use_container_width=True,
                ):
                    st.session_state["ev_cell"] = c
            if c["reason"] and c["gate"] != "use":
                st.caption(
                    ("السبب: " if is_ar else "reason: ") + str(c["reason"])
                )

    ev = st.session_state.get("ev_cell")
    if ev:
        with st.expander(_T["evidence"][lang], expanded=True):
            evidence_block(ev, raw, vm["doc_sha"])
    else:
        render_empty_state(
            "معاينة دليل المصدر" if is_ar else "Source evidence preview",
            "لم تُختر خانة للمعاينة بعد."
            if is_ar
            else "No cell selected for inspection yet.",
            icon="🔍",
            next_step="اضغط زر «الدليل» بجانب أي خانة لعرض الصفحة الأصلية وقصاصة الرقم."
            if is_ar
            else "Click Evidence next to any row to inspect its source page & crop.",
        )


def sec_metrics(vm: dict) -> None:
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


def sec_health(vm: dict, results: dict) -> None:
    from src.analysis.score import compute_health_score
    from src.dashboard import charts

    lang = _lang()
    is_ar = lang != "en"
    st.subheader(_T["health"][lang])
    blocked = {e["field"] for e in vm["pending"]}
    hs = compute_health_score(results["curr_metrics"], blocked_fields=blocked)

    st.markdown(build_health_html(hs, lang=lang), unsafe_allow_html=True)

    if hs.total is not None:
        with st.expander(
            "عرض المقياس البصري (Gauge) وسياسة التغطية"
            if is_ar
            else "Show visual gauge & coverage policy",
            expanded=False,
        ):
            st.plotly_chart(charts.health_gauge(hs, lang=lang), use_container_width=True)
            if getattr(hs, "policy", ""):
                st.caption(hs.policy)
    else:
        if getattr(hs, "policy", ""):
            st.caption(hs.policy)
        st.caption(
            "قيم هذه الأركان تحمل حالة «يحتاج مراجعة» أو «غير متوفر» في تبويب القوائم — لا تُحسب درجة إجمالية من مدخلات غير موثقة."
            if is_ar
            else "Critical pillar inputs are unverified or missing — no total score is issued."
        )


def sec_insights(vm: dict, analysis) -> None:
    """رؤى Gemini مصنفة من اتجاه المؤشر المحسوب — تدعم التعليق القاعدي الحتمي عند تعذر Gemini."""
    lang = _lang()
    is_ar = lang != "en"
    st.subheader(_T["insights"][lang])
    if vm["pending_count"]:
        st.warning(_T["provisional"][lang])

    if analysis is None:
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
            results["verification_status"] = vm["verification"]
            currency = st.session_state.get("currency", "$")
            payload = build_gemini_payload(results, currency)
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

    if not is_ai_ok:
        reason = getattr(analysis, "error", "") or ""
        st.warning(
            (
                f"تعذّر الاتصال بـ Gemini ({reason}) — يُعرض التفسير القاعدي الحتمي المحسوب في Python دون تدخل ذكاء اصطناعي."
                if is_ar
                else f"Gemini unavailable ({reason}) — showing deterministic rule-based commentary computed in Python."
            )
        )
    else:
        st.caption(
            f"model: {analysis.model} · {len(analysis.ratio_comments)} "
            + (
                "تعليقًا — كل رقم متتبع لأصل محسوب في Python"
                if is_ar
                else "comments — every number traces to a Python computation"
            )
        )

    results_ctx = st.session_state.get("results") or {"rows": []}
    cats = categorized_insights(results_ctx, analysis)

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
            cards_html.append(
                f'<div class="fs-insight-card {card_cls}">'
                f'<div class="fs-insight-head">'
                f'<span class="fs-insight-title">{esc(item["metric"])}</span>'
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
    blocked = {e["field"] for e in vm["pending"]}
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
    """طابور مراجعة حي من سجل القرار — غير الحاسمة فقط، قصاصات من
    بايتات المستند نفسه، بلا GT (مع التخزين المؤقت للجلسة)."""
    import pypdfium2 as pdfium
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
    try:
        for e in vm["pending"]:
            field, year = e["field"], e["year"]
            pages = e.get("pages") or []
            if not pages:
                continue
            page_no = int(pages[0])
            if page_no < 1 or page_no > len(pdf):
                continue
            page_png = target_dir / f"live_page_{page_no}.png"
            if not page_png.exists():
                pdf[page_no - 1].render(scale=2.0).to_pil().save(page_png, "PNG")
            bbox = (results.get("candidate_bbox") or {}).get(f"{field}|{year}")
            crop_png = None
            if bbox:
                try:
                    img = pdf[page_no - 1].render(scale=3.0).to_pil().convert("RGB")
                    coords = _extract_bbox_coords(bbox, page_no, img.width, img.height, 3.0)
                    if coords:
                        x0, y0, x1, y1 = coords
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
            queue.append(
                {
                    "packet_id": f"live|{field}|{page_no}|{year}",
                    "field": field,
                    "page": page_no,
                    "year": year,
                    "status": e.get("status"),
                    "crop_image": str(crop_png) if crop_png else None,
                    "page_image": str(page_png),
                    "date_header_image": None,
                    "label_text": e.get("source") or "",
                    "bbox_rel": None,
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
                        "year_header_available": False,
                        "label_available": True,
                        "context_complete": False,
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
    st.caption(
        "سياق الخانة الحي بلا ترويسة سنة مقصوصة — سلسلة المراجعة تسمح بالرفض فقط هنا (قاعدة السياق الكامل، بلا تجاوز)."
        if is_ar
        else "Live context has no cropped year header — reject-only."
    )
    pkt = st.selectbox(
        "الخانة" if is_ar else "Cell",
        queue,
        format_func=lambda p: f"{p['field']} · {p['year']} · p{p['page']}",
    )
    col_a, col_b = st.columns(2)
    with col_a:
        if Path(pkt["page_image"]).exists():
            st.image(pkt["page_image"], caption=f"page {pkt['page']}")
    with col_b:
        if pkt["crop_image"] and Path(pkt["crop_image"]).exists():
            st.image(pkt["crop_image"])
        else:
            render_empty_state(
                "لا قصاصة (بلا bbox)" if is_ar else "No crop (no bbox)",
                "هذه الخانة مسجلة بالصفحة دون قصاصة محددة — الرفض فقط متاح."
                if is_ar
                else "No bounding box crop recorded — reject-only mode.",
                icon="🖼️",
            )
    conf = {}
    st.markdown(
        "**" + ("التأكيدات الأربعة للرفض" if is_ar else "The four reject confirmations") + "**"
    )
    for k in CONFIRMATION_KEYS:
        if k == "value":
            continue
        conf[k] = st.checkbox(
            CONFIRMATION_LABELS_AR.get(k, k), key=f"conf-{doc_sha}-{pkt['packet_id']}-{k}"
        )
    reason = st.text_area(
        "سبب الرفض (يسجل في السلسلة الموقعة)"
        if is_ar
        else "Reject reason (recorded in the signed chain)",
        "",
    )
    c1, c2 = st.columns(2)
    reviewer = c1.text_input("اسم المراجع" if is_ar else "Reviewer", "")
    credential = c2.text_input("PIN", type="password")
    if st.button(
        "تسجيل الرفض في السلسلة" if is_ar else "Record rejection",
        type="primary",
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
                    reviewer=reviewer,
                    credential=credential,
                    log_path=log_path,
                    decision_note=reason.strip(),
                    confirmations={**conf, "value": False},
                )
                st.success(
                    "سُجل الرفض في السلسلة الموقعة — حساب المراجع ليس مراجعة إنتاجية."
                    if is_ar
                    else "Rejection recorded — not a production review."
                )
                st.caption(f"seq={rec.get('seq')} · hash={str(rec.get('record_hash'))[:16]}")
            except Exception as exc:
                st.error(f"رفض السلسلة: {exc}" if is_ar else f"Chain refused: {exc}")


def render(results: dict, analysis, raw: bytes | None) -> None:
    """نقطة دخول الواجهة — تستدعى من app.py."""
    lang = st.session_state.get("ui_lang", "ar")
    is_ar = lang != "en"
    vm = build_view_model(results, st.session_state.get("currency", "$"))

    with st.sidebar:
        st.markdown("### " + ("لوحة التحكم" if is_ar else "Control Panel"))
        if st.button("English / عربي", use_container_width=True):
            st.session_state["ui_lang"] = "en" if lang == "ar" else "ar"
            st.rerun()
        if st.button(_T["classic"][lang], use_container_width=True, type="primary"):
            st.session_state["ui_mode"] = "classic"
            st.session_state["ui_mode_classic_toggle"] = True
            st.rerun()
        st.divider()
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
        ]
    )
    with tabs[0]:
        sec_overview(vm, results)
    with tabs[1]:
        sec_statements(vm, raw)
    with tabs[2]:
        sec_metrics(vm)
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
