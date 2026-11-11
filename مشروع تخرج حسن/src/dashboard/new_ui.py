# -*- coding: utf-8 -*-
"""الواجهة الجديدة (v5) — دمج تدريجي لتصميم mvp_preview.html في Streamlit.

قواعد صارمة من التفويض:
- مكونات Streamlit حقيقية متصلة بنتائج الـPipeline الحي — لا HTML مضمّن
  ولا أرقام مجمدة في الكود (الديمو في وضعه الموسوم الخاص به فقط).
- كل قيمة تُعرض بحالتها من قرار بوابة الاعتماد النهائي (decide) لا من
  حالة المرشحين — عبر src/dashboard/view_model.py (قراءة فقط).
- محركات OCR/المحلل/الحاسبة/البوابة/RAG/Gemini تُستهلك بواجهاتها الحالية —
  لا إعادة بناء ولا Adapter يغيّر قرارًا ماليًا.
- المصدر: صفحة المستند الأصلية + bbox حقيقي + فحص هاش المستند قبل العرض،
  ولا يُعرض أبدًا دليل من مستند آخر.
- المراجعة البشرية عبر سلسلة HMAC الموجودة (apply_review) — حساب
  test-reviewer ليس مراجعة إنتاجية، والسياق الناقص = رفض فقط (قاعدة
  السلسلة نفسها، بلا تجاوز).
"""
from __future__ import annotations

import hashlib
import io
import os
import sys
import tempfile
from pathlib import Path

import streamlit as st

PROJ = Path(__file__).resolve().parents[2]
if str(PROJ) not in sys.path:
    sys.path.insert(0, str(PROJ))

from src.dashboard.view_model import (  # noqa: E402
    build_view_model, cell_value_display,
)

_T = {
    "title": {"ar": "📊 محلل القوائم المالية", "en": "📊 Financial Statement Analyzer"},
    "new_ui": {"ar": "الواجهة الجديدة — تجريبية", "en": "New UI — experimental"},
    "classic": {"ar": "عودة للواجهة الكلاسيكية", "en": "Back to classic UI"},
    "lang_btn": {"ar": "English / عربي", "en": "عربي / English"},
    "dash": {"ar": "🏠 لوحة القيادة", "en": "🏠 Dashboard"},
    "stmts": {"ar": "📋 القوائم والخانات", "en": "📋 Statements & Cells"},
    "kpi": {"ar": "📈 المؤشرات المالية", "en": "📈 Financial Metrics"},
    "health": {"ar": "❤️ الدرجة الصحية", "en": "❤️ Health Score"},
    "gemini": {"ar": "✦ تفسير Gemini", "en": "✦ Gemini Analysis"},
    "chat": {"ar": "💬 محادثة المستند (RAG)", "en": "💬 Document Chat (RAG)"},
    "review": {"ar": "✍️ مراجعة بشرية", "en": "✍️ Human Review"},
    "reports": {"ar": "📄 التقارير", "en": "📄 Reports"},
    "evidence": {"ar": "🔍 دليل المصدر", "en": "🔍 Source Evidence"},
    "unit": {"ar": "وحدة القوائم", "en": "Statement unit"},
    "doc_sha": {"ar": "بصمة المستند", "en": "Document hash"},
    "gate": {"ar": "قرار البوابة", "en": "Gate decision"},
    "source": {"ar": "المصدر", "en": "Source"},
    "page": {"ar": "الصفحة", "en": "Page"},
    "value": {"ar": "القيمة", "en": "Value"},
    "year": {"ar": "السنة", "en": "Year"},
    "field": {"ar": "البند", "en": "Field"},
    "decisive": {"ar": "خانات حاسمة", "en": "Decisive cells"},
    "pending": {"ar": "بانتظار مراجعة", "en": "Awaiting review"},
    "provisional": {
        "ar": "⚠ تحليل تجريبي غير معتمد — مولد من قيم حالتها «يحتاج مراجعة»؛"
              " تُقرأ كمؤشرات استكشافية، ليست حكمًا نهائيًا.",
        "en": "⚠ Provisional, non-authoritative analysis — generated from"
              " values whose gate status is needs-review; exploratory"
              " indicators, not a final verdict."},
    "health_refused": {"ar": "الدرجة الصحية محجوبة", "en": "Health Score refused"},
    "no_analysis": {"ar": "لا يوجد تحليل Gemini — السبب:", "en": "No Gemini analysis — reason:"},
    "review_disabled": {
        "ar": "المراجعة البشرية معطلة — تتطلب REVIEWERS_FILE وREVIEW_HMAC_KEY في .env "
              "(حساب test-reviewer ليس مراجعة إنتاجية).",
        "en": "Human review disabled — requires REVIEWERS_FILE and "
              "REVIEW_HMAC_KEY in .env (test-reviewer is NOT production review)."},
    "reject_only": {
        "ar": "سياق الخانة غير مكتمل (ترويسة سنة مطبوعة غير متاحة في التشغيل الحي) "
              "— سلسلة المراجعة تسمح بالرفض فقط هنا؛ الاعتماد/التصحيح يتطلب سياقًا كاملًا.",
        "en": "Cell context incomplete (no printed year header available in a"
              " live run) — the chain allows reject-only here; attest/correct"
              " require full context."},
    "open_evidence": {"ar": "🔍 فتح الدليل", "en": "🔍 Open evidence"},
    "reports_pdf_missing": {
        "ar": "إنتاج PDF غير متاح — LibreOffice غير مثبت على هذا الجهاز "
              "(المسار المتوقع: C:/Program Files/LibreOffice). إصدار Excel وHTML يعملان.",
        "en": "PDF production unavailable — LibreOffice not installed. "
              "Excel and HTML still work."},
}


def _t(key: str) -> str:
    lang = st.session_state.get("ui_lang", "ar")
    return _T.get(key, {}).get(lang, key)


def inject_direction() -> None:
    lang = st.session_state.get("ui_lang", "ar")
    d = "rtl" if lang == "ar" else "ltr"
    st.markdown(
        f"""
        <style>
          div.stApp {{ direction: {d}; }}
          section[data-testid="stSidebar"] {{ direction: {d}; }}
          .stTabs [data-baseweb="tab-list"] {{ gap: 4px; flex-wrap: wrap; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ── Source evidence (المهمة 5) ──────────────────────────────────────────
def _render_page_with_bbox(raw: bytes, page_no: int, bbox):
    """صفحة المستند الأصلية + رسم مستطيل bbox الحقيقي إن وُجد وتوافق أبعاده."""
    import pypdfium2 as pdfium
    from PIL import Image, ImageDraw

    pdf = pdfium.PdfDocument(io.BytesIO(raw))
    if page_no < 1 or page_no > len(pdf):
        return None
    img = pdf[page_no - 1].render(scale=2.0).to_pil().convert("RGB")
    if bbox:
        try:
            x0, y0, x1, y1 = [float(v) for v in bbox[:4]]
            # bbox بإحداثيات بكسل مسح Indra — نقيسها على أبعاد الصفحة المعروضة:
            # إن تجاوزت الأبعاد نقيس proportionally على أكبر إحداثية
            sx = sy = 1.0
            if max(x1, y1) > 1.5 and (max(x1, y1) > img.width or
                                       max(y1, y1) > img.height):
                sx = img.width / max(x1, y1, 1)
                sy = img.height / max(y1, y1, 1)
            d = ImageDraw.Draw(img)
            d.rectangle([x0 * sx, y0 * sy, x1 * sx, y1 * sy],
                        outline="#e11d48", width=4)
        except Exception:
            pass  # bbox غير صالح هندسيًا — تعرض الصفحة بلا مستطيل (بصدق)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _render_crop(raw: bytes, page_no: int, bbox):
    """قصاصة الخانة (بكسل حقيقي) من الصفحة الأصلية."""
    import pypdfium2 as pdfium
    from PIL import Image

    if not bbox:
        return None
    pdf = pdfium.PdfDocument(io.BytesIO(raw))
    if page_no < 1 or page_no > len(pdf):
        return None
    img = pdf[page_no - 1].render(scale=3.0).to_pil().convert("RGB")
    try:
        x0, y0, x1, y1 = [float(v) for v in bbox[:4]]
        if max(x1, y1) > 1.5 and (max(x1, y1) > img.width or
                                   max(y1, y1) > img.height):
            sx = img.width / max(x1, y1, 1)
            sy = img.height / max(y1, y1, 1)
            x0, x1, y0, y1 = x0 * sx, x1 * sx, y0 * sy, y1 * sy
        pad = 6
        crop = img.crop((max(0, int(x0) - pad), max(0, int(y0) - pad),
                         min(img.width, int(x1) + pad),
                         min(img.height, int(y1) + pad)))
        buf = io.BytesIO()
        crop.save(buf, "PNG")
        return buf.getvalue()
    except Exception:
        return None


def evidence_block(cell: dict, raw: bytes | None, doc_sha: str) -> None:
    """دليل المصدر لخانة واحدة — بفحص الهاش ومنع المستندات الأجنبية."""
    lang = st.session_state.get("ui_lang", "ar")
    st.markdown(f"#### {_t('evidence')} — {cell['label']} · "
                f"{cell['year']}")
    if raw is None:
        st.info("بايتات المستند الأصلي غير محفوظة في هذه الجلسة — أعد رفع "
                "الملف لعرض الدليل." if lang == "ar" else
                "Original bytes not in this session — re-upload to view.")
        return
    # فحص هاش المستند: الدليل يُعرض فقط لبايتات نفس المستند الذي استُخرجت منه
    current_sha = hashlib.sha256(raw).hexdigest()[:16]
    if doc_sha and current_sha != doc_sha:
        st.error("بصمة المستند الحالي لا تطابق بصمة الاستخراج — منع عرض "
                 "دليل من مستند آخر." if lang == "ar" else
                 "Document hash mismatch — cross-document evidence blocked.")
        return
    st.caption(f"{_t('doc_sha')}: `{current_sha}` ✓")
    pages = cell.get("pages") or []
    if not pages:
        st.info("لا توجد صفحة مصدر مسجلة لهذه الخانة في سجل القرار."
                if lang == "ar" else "No source page recorded for this cell.")
        return
    page_no = int(pages[0])
    st.markdown(f"{_t('page')}: **{page_no}** · {_t('source')}: "
                f"`{cell.get('source', '—')}`")
    bbox = cell.get("bbox")
    bbox = bbox[0] if isinstance(bbox, list) and bbox and \
        isinstance(bbox[0], list) else bbox
    col_page, col_crop = st.columns([3, 2])
    page_img = _render_page_with_bbox(raw, page_no, bbox)
    with col_page:
        if page_img:
            st.image(page_img, caption=f"صفحة {page_no} + bbox" if lang == "ar"
                     else f"page {page_no} + bbox")
        else:
            st.info("تعذر عرض الصفحة.")
    with col_crop:
        crop = _render_crop(raw, page_no, bbox) if bbox else None
        if crop:
            st.image(crop, caption="القصاصة (بكسل حقيقي)" if lang == "ar"
                     else "Crop (real pixels)")
        else:
            st.info("لا إحداثيات bbox لهذه الخانة (مستند نصي رقمي) — القصاصة "
                    "غير متاحة والصفحة معروضة."
                    if lang == "ar" else
                    "No bbox for this cell (digital text PDF) — crop "
                    "unavailable, page shown.")


# ── Sections ────────────────────────────────────────────────────────────
def _kpi_cards(vm: dict) -> None:
    lang = st.session_state.get("ui_lang", "ar")
    curr = vm["currency"]
    sc = vm["unit_scale"]
    rows = {r["key"]: r for r in vm["metrics"]}
    cards = [
        ("revenue", "الإيرادات" if lang == "ar" else "Revenue"),
        ("net_income", "صافي الربح" if lang == "ar" else "Net income"),
        ("total_assets", "إجمالي الأصول" if lang == "ar" else "Total assets"),
        ("debt_ratio", "نسبة الدين" if lang == "ar" else "Debt ratio"),
    ]
    cols = st.columns(4)
    for col, (key, label) in zip(cols, cards):
        r = rows.get(key)
        with col:
            if r is None or (r["curr"] is None and r["prev"] is None):
                st.metric(label, "N/A",
                          help="مؤشر غير قابل للحساب — مدخلاته غير كافية"
                          if lang == "ar" else "Not computable — inputs missing")
                continue
            val = cell_value_display(r["curr"], sc, curr) \
                if r["kind"] == "currency" else (
                f"{r['curr']:.1f}%" if r["kind"] == "percent"
                else f"{r['curr']:.2f}x" if r["kind"] == "ratio"
                else f"{r['curr']:,.2f}")
            st.metric(label, val)
            if r["verif"] and r["verif"] != "—":
                st.caption(r["verif"])


def sec_dashboard(vm: dict) -> None:
    lang = st.session_state.get("ui_lang", "ar")
    st.subheader(_T["dash"][lang])
    _kpi_cards(vm)
    c1, c2, c3 = st.columns(3)
    c1.metric(_t("decisive"), vm["decisive_count"])
    c2.metric(_t("pending"), vm["pending_count"],
              delta=None if vm["pending_count"] == 0 else "⚠",
              delta_color="off")
    c3.metric(_t("field"), vm["cell_count"])
    with st.expander(_t("unit") + " · " + _t("doc_sha"), expanded=False):
        st.write(f"{_t('unit')}: {vm['unit_note'] or '—'}")
        st.write(f"{_t('doc_sha')}: `{vm['doc_sha']}`")
        for n in vm["profile"]:
            st.caption(n)
    if vm["pending_count"]:
        st.warning(f"{_t('pending')}: {vm['pending_count']} — "
                   + (", ".join(sorted({e['field'] for e in vm['pending']}))[:90]))


def sec_statements(vm: dict, raw: bytes | None) -> None:
    lang = st.session_state.get("ui_lang", "ar")
    st.subheader(_T["stmts"][lang])
    st.caption("كل خانة بحالتها من قرار بوابة الاعتماد النهائي — لا من حالة "
               "المرشحين." if lang == "ar" else
               "Each cell shows its FINAL gate decision — not the raw "
               "candidate state.")
    for c in vm["cells"]:
        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([2.2, 1.6, 1.4, 1.2])
            with col1:
                st.markdown(f"**{c['label']}** · {c['year']}")
                if c["raw_label"] and c["raw_label"] != c["label"]:
                    st.caption(f"كما قُرئت: {c['raw_label']}" if lang == "ar"
                               else f"as read: {c['raw_label']}")
            with col2:
                st.markdown(f"**{cell_value_display(c['value'], vm['unit_scale'], vm['currency'])}**")
            with col3:
                kind = c["gate_kind"]
                icon = {"ok": "🟢", "pend": "🟡", "miss": "⚪"}.get(kind, "⚪")
                st.markdown(f"{icon} {c['gate_label']}"
                            + (" ✓ بشري" if lang == "ar" else " ✓ human")
                            if c["reviewed"] else f"{icon} {c['gate_label']}")
            with col4:
                if st.button(_t("open_evidence"), key=f"ev-{c['field']}-{c['year']}",
                             use_container_width=True):
                    st.session_state["ev_cell"] = c
            if c["reason"] and c["gate"] != "use":
                st.caption(f"السبب: {c['reason']}" if lang == "ar"
                           else f"reason: {c['reason']}")
    ev = st.session_state.get("ev_cell")
    if ev:
        with st.expander(_t("evidence"), expanded=True):
            evidence_block(ev, raw, vm["doc_sha"])


def sec_metrics(vm: dict) -> None:
    lang = st.session_state.get("ui_lang", "ar")
    st.subheader(_T["kpi"][lang])
    import pandas as pd

    rows = []
    for r in vm["metrics"]:
        sc = vm["unit_scale"]
        fmt = (lambda v: cell_value_display(v, sc, vm["currency"])
               if r["kind"] == "currency" else
               (f"{v:.1f}%" if r["kind"] == "percent" else
                (f"{v:.2f}x" if r["kind"] == "ratio" else f"{v:,.2f}")))
        rows.append({
            "المؤشر" if lang == "ar" else "Metric": r["label"],
            "السنة السابقة" if lang == "ar" else "Prev": fmt(r["prev"])
            if r["prev"] is not None else "N/A",
            "السنة الحالية" if lang == "ar" else "Curr": fmt(r["curr"])
            if r["curr"] is not None else "N/A",
            "التغير %" if lang == "ar" else "Change %": f"{r['change_pct']:+.1f}%"
            if r["change_pct"] is not None else "—",
            "حالة التحقق" if lang == "ar" else "Verification": r["verif"] or "—",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def sec_health(vm: dict, results: dict) -> None:
    lang = st.session_state.get("ui_lang", "ar")
    st.subheader(_T["health"][lang])
    from src.analysis.score import compute_health_score

    blocked = {e["field"] for e in vm["pending"]}
    hs = compute_health_score(results["curr_metrics"], blocked_fields=blocked)
    if hs.total is not None:
        st.metric("Health Score", f"{hs.total:.0f}/100",
                  delta=hs.label, delta_color="off")
        chips = " · ".join(f"{p.name}: "
                           + ("—" if p.score is None else f"{p.score:.0f}")
                           for p in hs.pillars)
        st.caption(chips)
    else:
        st.error(f"**{_T['health_refused'][lang]}** — "
                 + (getattr(hs, "policy", "") or ""))
        blocked_names = "، ".join(sorted(blocked)) or "—"
        st.caption("المدخلات المحجوبة: " + blocked_names if lang == "ar"
                   else "Blocked inputs: " + blocked_names)


def sec_gemini(vm: dict, analysis) -> None:
    lang = st.session_state.get("ui_lang", "ar")
    st.subheader(_T["gemini"][lang])
    if vm["pending_count"]:
        st.warning(_T["provisional"][lang])
    if analysis is not None and getattr(analysis, "ok", False):
        st.caption(f"model: {analysis.model} · "
                   f"{len(analysis.ratio_comments)} "
                   + ("تعليقًا" if lang == "ar" else "comments"))
        for metric, text in analysis.ratio_comments:
            with st.container(border=True):
                st.markdown(f"**{metric}**")
                st.write(text)
        if analysis.recommendations:
            st.markdown("### " + ("التوصيات" if lang == "ar" else "Recommendations"))
            for action, text in analysis.recommendations:
                with st.container(border=True):
                    st.markdown(f"**{action}**")
                    st.write(text)
    else:
        reason = getattr(analysis, "error", "") or "—"
        st.info(f"{_T['no_analysis'][lang]} {reason}")


def sec_reports(vm: dict, results: dict, analysis) -> None:
    lang = st.session_state.get("ui_lang", "ar")
    st.subheader(_T["reports"][lang])
    from src.dashboard.excel_report import build_excel_report
    from src.dashboard.report import build_html_report
    from src.analysis.score import compute_health_score

    blocked = {e["field"] for e in vm["pending"]}
    results["verification_status"] = vm["verification"]
    results["blocked_fields"] = sorted(blocked)
    hs = compute_health_score(results["curr_metrics"], blocked_fields=blocked)
    xlsx = build_excel_report(results)
    st.download_button("⬇️ Excel (.xlsx)", xlsx,
                       file_name=f"{vm['company'][:24]}_analysis.xlsx",
                       use_container_width=True)
    html = build_html_report(results, analysis, hs, currency=vm["currency"])
    st.download_button("⬇️ HTML", html.encode("utf-8"),
                       file_name=f"{vm['company'][:24]}_report.html",
                       mime="text/html", use_container_width=True)
    soffice = Path(r"C:\Program Files\LibreOffice\program\soffice.exe")
    if not soffice.exists():
        st.info(_T["reports_pdf_missing"][lang])
        return
    if st.button("⬇️ " + ("إنتاج PDF" if lang == "ar" else "Produce PDF"),
                 use_container_width=True):
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            print_html = Path(td) / "report_print.html"
            print_html.write_text(
                build_html_report(results, analysis, hs, currency=vm["currency"],
                                  print_safe=True), encoding="utf-8")
            with st.spinner("LibreOffice…"):
                subprocess.run([str(soffice), "--headless", "--convert-to",
                                "pdf", "--outdir", td, str(print_html)],
                               capture_output=True, timeout=240)
            pdf = Path(td) / "report_print.pdf"
            if pdf.exists():
                st.download_button("⬇️ PDF", pdf.read_bytes(),
                                   file_name=f"{vm['company'][:24]}_report.pdf",
                                   mime="application/pdf")
            else:
                st.error("فشل تحويل PDF — راجع تثبيت LibreOffice."
                         if lang == "ar" else "PDF conversion failed.")


def _build_live_queue(vm: dict, results: dict, raw: bytes,
                      crops_dir: Path) -> list[dict]:
    """طابور مراجعة حي من سجل القرار — الحزم غير الحاسمة فقط، قصاصات
    حقيقية من بايتات المستند نفسه، بلا أي GT."""
    from src.extraction.human_review import EXTRACTION_VERSION, _sha256_file
    import pypdfium2 as pdfium
    from PIL import Image

    crops_dir.mkdir(parents=True, exist_ok=True)
    pdf = pdfium.PdfDocument(io.BytesIO(raw))
    doc_sha = hashlib.sha256(raw).hexdigest()
    queue = []
    for e in vm["pending"]:
        field, year = e["field"], e["year"]
        pages = e.get("pages") or []
        if not pages:
            continue
        page_no = int(pages[0])
        if page_no < 1 or page_no > len(pdf):
            continue
        page_png = crops_dir / f"live_page_{page_no}.png"
        if not page_png.exists():
            pdf[page_no - 1].render(scale=2.0).to_pil().save(page_png, "PNG")
        bbox = (results.get("candidate_bbox") or {}).get(f"{field}|{year}")
        bbox0 = bbox[0] if isinstance(bbox, list) and bbox and \
            isinstance(bbox[0], list) else bbox
        crop_png = None
        if bbox0:
            try:
                img = pdf[page_no - 1].render(scale=3.0).to_pil().convert("RGB")
                x0, y0, x1, y1 = [float(v) for v in bbox0[:4]]
                if max(x1, y1) > 1.5 and (max(x1, y1) > img.width or
                                           max(y1, y1) > img.height):
                    sx, sy = img.width / max(x1, y1, 1), img.height / max(y1, y1, 1)
                    x0, x1, y0, y1 = x0 * sx, x1 * sx, y0 * sy, y1 * sy
                crop = img.crop((max(0, int(x0) - 6), max(0, int(y0) - 6),
                                 min(img.width, int(x1) + 6),
                                 min(img.height, int(y1) + 6)))
                crop_png = crops_dir / f"live_{field}_{year}_crop.png"
                crop.save(crop_png, "PNG")
            except Exception:
                crop_png = None
        queue.append({
            "packet_id": f"live|{field}|{page_no}|{year}",
            "field": field, "page": page_no, "year": year,
            "status": e.get("status"),
            "crop_image": str(crop_png) if crop_png else None,
            "page_image": str(page_png),
            "date_header_image": None,
            "label_text": e.get("source") or "",
            "bbox_rel": None,
            "machine_selected": e.get("final"),
            "readings": {"detection_line": (e.get("candidates") or [])[:4],
                          "crop_variants": []},
            "conflict_reason": e.get("reason") or "",
            "source_pdf": results.get("file_name"),
            "pdf_sha256": doc_sha,
            "page_image_sha256": _sha256_file(page_png),
            "crop_sha256": _sha256_file(crop_png) if crop_png else None,
            "extraction_version": EXTRACTION_VERSION,
            # السياق الحي بلا ترويسة سنة مطبوعة مقصوصة — السلسلة تفرض
            # الرفض-فقط (قاعدة المنتج نفسها، لا تجاوز)
            "context": {"year_header_available": False,
                         "label_available": True,
                         "context_complete": False},
            "confirmations": {k: False for k in
                              ("document", "field", "year", "position",
                               "value")},
            "decision": None,
        })
    return queue


def sec_review(vm: dict, results: dict, raw: bytes | None) -> None:
    lang = st.session_state.get("ui_lang", "ar")
    st.subheader(_T["review"][lang])
    if not (os.environ.get("REVIEWERS_FILE") or os.environ.get("REVIEWERS")):
        st.info(_T["review_disabled"][lang])
        return
    if raw is None:
        st.info("بايتات المستند غير محفوظة في الجلسة — لا يمكن بناء أدلة "
                "المراجعة." if lang == "ar" else
                "Document bytes not in session — cannot build evidence.")
        return
    from src.extraction.human_review import (  # noqa: E402
        CONFIRMATION_LABELS_AR, CONFIRMATION_KEYS, apply_review,
        verify_log_integrity,
    )

    ok, bad = verify_log_integrity()
    if not ok:
        st.error(f"سجل المراجعات تالف (seq={bad}) — المراجعة مرفوضة."
                 if lang == "ar" else f"Review log broken (seq={bad}).")
        return
    crops_dir = Path(tempfile.gettempdir()) / "live_review_crops"
    # بناء الطابور مكلف (رندر صفحات + قصاصات pdfium لكل خانة) — يُخزَّن
    # في حالة الجلسة keyed ببصمة المستند وعدد المعلقة، ولا يُعاد إلا عند
    # تغيّرهما (كل إعادة رسم كانت تعيد الرندر — عيب كشفه اختبار الرحلة)
    qkey = f"{vm['doc_sha']}|{vm['pending_count']}"
    if st.session_state.get("live_queue_key") != qkey             or not st.session_state.get("live_queue"):
        st.session_state["live_queue"] = _build_live_queue(
            vm, results, raw, crops_dir)
        st.session_state["live_queue_key"] = qkey
    queue = st.session_state["live_queue"]
    if not queue:
        st.success("لا خانات بانتظار مراجعة — كل الخانات حاسمة أو بلا صفحة "
                   "مصدر." if lang == "ar" else "No cells awaiting review.")
        return
    st.caption(_T["reject_only"][lang])
    pkt = st.selectbox(
        "الخانة" if lang == "ar" else "Cell",
        queue,
        format_func=lambda p: f"{p['field']} · {p['year']} · ص{p['page']}"
        if lang == "ar" else f"{p['field']} · {p['year']} · p{p['page']}")
    col_a, col_b = st.columns(2)
    with col_a:
        page_img = Path(pkt["page_image"])
        if page_img.exists():
            st.image(str(page_img), caption=f"صفحة {pkt['page']}"
                     if lang == "ar" else f"page {pkt['page']}")
    with col_b:
        if pkt["crop_image"] and Path(pkt["crop_image"]).exists():
            st.image(pkt["crop_image"], caption="القصاصة" if lang == "ar"
                     else "crop")
        else:
            st.info("لا قصاصة (بلا bbox) — الرفض متاح فقط."
                    if lang == "ar" else "No crop (no bbox) — reject only.")
    st.markdown("**التأكيدات الأربعة للرفض**" if lang == "ar"
                else "**The four reject confirmations**")
    conf = {}
    for k in CONFIRMATION_KEYS:
        if k == "value":
            continue
        conf[k] = st.checkbox(CONFIRMATION_LABELS_AR.get(k, k),
                              key=f"conf-{pkt['packet_id']}-{k}")
    reason = st.text_area("سبب الرفض (يُسجل في السلسلة)"
                          if lang == "ar" else
                          "Reject reason (recorded in the chain)", "")
    c1, c2 = st.columns(2)
    reviewer = c1.text_input("اسم المراجع" if lang == "ar" else "Reviewer", "")
    credential = c2.text_input("PIN", type="password")
    if st.button("🗑️ تسجيل الرفض في السلسلة"
                 if lang == "ar" else "Record rejection in the chain",
                 type="primary", use_container_width=True):
        if not all(conf[k] for k in conf):
            st.error("أكّد العناصر الأربعة أولًا (المستند، البند، السنة، "
                     "الموضع)." if lang == "ar" else
                     "Confirm the four elements first.")
        elif not reason.strip():
            st.error("سبب الرفض مطلوب." if lang == "ar" else
                     "A reject reason is required.")
        else:
            try:
                rec = apply_review(
                    queue, pkt["packet_id"], approved_value=None,
                    reviewer=reviewer, credential=credential,
                    decision_note=reason.strip(),
                    confirmations={**conf, "value": False})
                st.success("سُجل الرفض في سلسلة HMAC الموقعة ✓ — "
                           "حساب المراجع هنا ليس مراجعة إنتاجية."
                           if lang == "ar" else
                           "Rejection recorded in the signed chain ✓ — "
                           "not a production review.")
                st.caption(f"seq={rec.get('seq')} · "
                           f"hash={str(rec.get('record_hash'))[:16]}")
            except Exception as exc:
                st.error(f"رفض السلسلة: {exc}" if lang == "ar" else
                         f"Chain refused: {exc}")


# ── Entry ───────────────────────────────────────────────────────────────
def render(results: dict, analysis, raw: bytes | None) -> None:
    """نقطة دخول الواجهة الجديدة — تستدعى من app.py عند تفعيل الوضع."""
    inject_direction()
    vm = build_view_model(results, st.session_state.get("currency", "$"))
    with st.sidebar:
        st.markdown(f"### {_t('title')}")
        st.markdown(f"🧪 **{_t('new_ui')}**")
        st.caption(f"{vm['company']} · {vm['file_name']}")
        col1, col2 = st.columns(2)
        if col1.button(_t("lang_btn"), use_container_width=True):
            st.session_state["ui_lang"] = ("en" if
                                           st.session_state.get("ui_lang", "ar")
                                           == "ar" else "ar")
            st.rerun()
        if col2.button(_t("classic"), use_container_width=True,
                       type="primary"):
            st.session_state["ui_mode"] = "classic"
            # أطفئ ويدجت الكلاسيكية المخزنة — وإلا استعاد حالته القديمة
            # (True) عند ظهوره وسحب الجلسة عائدة فورًا (فخ دورة الحياة)
            st.session_state["ui_mode_new_toggle"] = False
            st.rerun()
        st.caption(f"{_t('unit')}: {vm['unit_note'] or '—'}\n\n"
                   f"{_t('doc_sha')}: `{vm['doc_sha']}`")
        if st.button("🔄 " + ("تحليل جديد" if st.session_state.get("ui_lang", "ar")
                              == "ar" else "New analysis"),
                     use_container_width=True):
            for k in ("results", "analysis", "raw_bytes", "ev_cell"):
                st.session_state.pop(k, None)
            st.rerun()
    tabs = st.tabs([_t("dash"), _t("stmts"), _t("kpi"), _t("health"),
                    _t("gemini"), _t("chat"), _t("review"), _t("reports")])
    with tabs[0]:
        sec_dashboard(vm)
    with tabs[1]:
        sec_statements(vm, raw)
    with tabs[2]:
        sec_metrics(vm)
    with tabs[3]:
        sec_health(vm, results)
    with tabs[4]:
        sec_gemini(vm, analysis)
    with tabs[5]:
        # إعادة استخدام واجهة RAG الكلاسيكية كما هي — لا إعادة بناء
        from app import notes_screen

        notes_screen(results)
    with tabs[6]:
        sec_review(vm, results, raw)
    with tabs[7]:
        sec_reports(vm, results, analysis)
