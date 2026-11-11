# -*- coding: utf-8 -*-
"""FinSight AI — واجهة Streamlit النهائية (v6): تصميم FinTech فاتح
احترافي متصل بالـPipeline الحي.

المبادئ (من تفويض إعادة التصميم):
- مكونات Streamlit أصلية + HTML/CSS محدود المدى لنظام التصميم فقط.
- كل قيمة من نتائج التشغيل الحي: القيمة، السنة، الوحدة، قرار البوابة،
  المصدر، المستند. لا أرقام مجمدة ولا نتائج مختراعة.
- المحركات (OCR/المحلل/الحاسبة/البوابة/RAG/Gemini) تُستهلك بواجهاتها —
  الـAdapter (view_model.py) قراءة فقط ولا يغيّر قرارًا ماليًا.
- كل الحالات مصممة: فارغ/خطأ/معالجة/بيانات جزئية/نجاح.
- تعليقات Gemini موسومة «تحليل تجريبي غير معتمد» حين تكون المدخلات
  تحتاج مراجعة، ومصنفة من اتجاه المؤشر المحسوب (قوة/ضعف) لا من النبرة.
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
    build_view_model, cell_value_display, executive_summary,
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
    "provisional": {
        "ar": "تحليل تجريبي غير معتمد — مولد من قيم حالتها «يحتاج "
              "مراجعة»؛ يقرأ كمؤشرات استكشافية وليس حكمًا نهائيًا.",
        "en": "Provisional, non-authoritative analysis — generated from "
              "needs-review values; exploratory, not a final verdict."},
    "evidence": {"ar": "دليل المصدر", "en": "Source evidence"},
    "open_evidence": {"ar": "الدليل", "en": "Evidence"},
    "unit": {"ar": "وحدة القوائم", "en": "Statement unit"},
    "doc_sha": {"ar": "بصمة المستند", "en": "Document hash"},
    "strengths": {"ar": "نقاط القوة", "en": "Strengths"},
    "weaknesses": {"ar": "نقاط الضعف والمخاطر", "en": "Weaknesses & risks"},
    "neutral": {"ar": "مؤشرات مستقرة", "en": "Stable metrics"},
    "recommendations": {"ar": "التوصيات", "en": "Recommendations"},
    "health_refused": {"ar": "الدرجة الصحية محجوبة",
                       "en": "Health Score refused"},
}


def _t(key: str) -> str:
    lang = st.session_state.get("ui_lang", "ar")
    return _T.get(key, {}).get(lang, key)


def _lang() -> str:
    return st.session_state.get("ui_lang", "ar")


def _render_page_with_bbox(raw: bytes, page_no: int, bbox):
    import pypdfium2 as pdfium
    from PIL import Image, ImageDraw

    pdf = pdfium.PdfDocument(io.BytesIO(raw))
    if page_no < 1 or page_no > len(pdf):
        return None
    img = pdf[page_no - 1].render(scale=2.0).to_pil().convert("RGB")
    if bbox:
        try:
            x0, y0, x1, y1 = [float(v) for v in bbox[:4]]
            sx = sy = 1.0
            if max(x1, y1) > 1.5 and (max(x1, y1) > img.width or
                                       max(y1, y1) > img.height):
                sx = img.width / max(x1, y1, 1)
                sy = img.height / max(y1, y1, 1)
            d = ImageDraw.Draw(img)
            d.rectangle([x0 * sx, y0 * sy, x1 * sx, y1 * sy],
                        outline="#DC2626", width=4)
        except Exception:
            pass
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _render_crop(raw: bytes, page_no: int, bbox):
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
    """دليل المصدر: فحص هاش المستند + الصفحة الأصلية + bbox + القصاصة.
    لا يعرض دليل من مستند آخر أبدًا."""
    lang = _lang()
    st.markdown(f"**{_t('evidence')} — {cell['label']} · {cell['year']}**")
    if raw is None:
        st.info("بايتات المستند غير محفوظة في الجلسة — أعد رفع الملف."
                if lang == "ar" else "Original bytes not in session.")
        return
    current_sha = hashlib.sha256(raw).hexdigest()[:16]
    if doc_sha and current_sha != doc_sha:
        st.error("بصمة المستند لا تطابق بصمة الاستخراج — الدليل محجوب."
                 if lang == "ar" else "Document hash mismatch — blocked.")
        return
    st.caption(f"{_t('doc_sha')}: `{current_sha}` ✓")
    pages = cell.get("pages") or []
    if not pages:
        st.info("لا صفحة مصدر مسجلة لهذه الخانة (استخراج نصي بلا إسناد "
                "صفحات)." if lang == "ar" else
                "No source page recorded for this cell.")
        return
    page_no = int(pages[0])
    bbox = cell.get("bbox")
    bbox = bbox[0] if isinstance(bbox, list) and bbox and \
        isinstance(bbox[0], list) else bbox
    col_page, col_crop = st.columns([3, 2])
    with col_page:
        img = _render_page_with_bbox(raw, page_no, bbox)
        if img:
            st.image(img, caption=f"{_t('evidence')} — p{page_no}")
    with col_crop:
        crop = _render_crop(raw, page_no, bbox) if bbox else None
        if crop:
            st.image(crop, caption="crop")
        elif bbox is None:
            st.info("بلا إحداثيات bbox (مستند نصي رقمي)." if lang == "ar"
                    else "No bbox (digital text PDF).")


def sec_overview(vm: dict, results: dict) -> None:
    """اللوحة الرئيسية: الملخص التنفيذي (حقائق فقط) + KPI + حالة البوابة."""
    lang = _lang()
    st.subheader(_T["summary"][lang])
    for fact in executive_summary(results, vm):
        st.markdown(f"- {fact}")

    st.divider()
    st.subheader("KPI")
    curr_year = vm["curr_year"]
    rows = {r.key: r for r in results.get("rows", [])}
    sc, cur = vm["unit_scale"], vm["currency"]

    def fmt(v, kind):
        if v is None:
            return "N/A"
        return (cell_value_display(v, sc, cur) if kind == "currency" else
                f"{v:.1f}%" if kind == "percent" else
                f"{v:.2f}x" if kind == "ratio" else f"{v:,.2f}")

    def delta_of(key):
        r = rows.get(key)
        if r is None or r.change_pct is None:
            return "", "flat"
        mood = ("up" if (r.change or 0) > 0 and r.status != "Negative"
                else "down" if ((r.change or 0) < 0 or
                                r.status == "Negative") else "flat")
        return f"{r.change_pct:+.1f}%", mood

    cards = [
        ("الإيرادات" if lang == "ar" else "Revenue", "revenue", "currency"),
        ("صافي الربح" if lang == "ar" else "Net profit", "net_income",
         "currency"),
        ("إجمالي الأصول" if lang == "ar" else "Total assets",
         "total_assets", "currency"),
        ("نسبة التداول" if lang == "ar" else "Current ratio",
         "current_ratio", "ratio"),
        ("نسبة الدين" if lang == "ar" else "Debt ratio", "debt_ratio",
         "ratio"),
        ("هامش صافي الربح" if lang == "ar" else "Net margin",
         "net_margin", "percent"),
    ]
    cols = st.columns(3)
    for i, (label, key, kind) in enumerate(cards):
        r = rows.get(key)
        with cols[i % 3]:
            if r is None or (r.previous is None and r.current is None):
                na = "مؤشر غير قابل للحساب" if lang == "ar" else \
                    "not computable"
                st.markdown(
                    '<div class="fs-kpi"><div class="fs-kpi-label">'
                    f"{label}</div><div class=\"fs-kpi-value\">N/A</div>"
                    f'<div class="fs-kpi-delta flat">{na}</div></div>',
                    unsafe_allow_html=True)
                continue
            val = fmt(r.current, kind)
            d_txt, mood = delta_of(key)
            verif = vm["verification"].get(key, "")
            st.markdown(
                f'<div class="fs-kpi" title="{verif}">'
                f'<div class="fs-kpi-label">{label} · {curr_year}</div>'
                f'<div class="fs-kpi-value">{val}</div>'
                f'<div class="fs-kpi-delta {mood}">{d_txt or "—"}</div>'
                f"</div>", unsafe_allow_html=True)
            if verif and verif != "—":
                st.caption(verif)

    st.divider()
    c1, c2, c3 = st.columns(3)
    c1.metric(_T["gate_title"][lang] +
              (" — خانات حاسمة" if lang == "ar" else " — decisive"),
              f"{vm['decisive_count']}/{vm['cell_count']}")
    c2.metric(_T["pending"][lang] if lang == "ar" else "Awaiting review",
              vm["pending_count"])
    c3.metric(_T["unit"][lang] if lang == "ar" else "Unit",
              f"x{vm['unit_scale']}")
    if vm["pending_count"]:
        names = ", ".join(sorted({e["field"] for e in vm["pending"]})[:8])
        st.warning(f"{_T['pending'][lang] if lang == 'ar' else 'Awaiting'}: "
                   f"{vm['pending_count']} — {names}"
                   + (", ..." if vm["pending_count"] > 8 else ""))


def sec_statements(vm: dict, raw: bytes | None) -> None:
    lang = _lang()
    st.subheader(_T["statements"][lang])
    st.caption("كل خانة بقرار بوابة الاعتماد النهائي — لا حالة المرشحين."
               if lang == "ar" else
               "Each cell shows its FINAL gate decision.")
    for c in vm["cells"]:
        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([2.2, 1.6, 1.5, 1.1])
            with col1:
                st.markdown(f"**{c['label']}** · {c['year']}")
                if c["raw_label"] and c["raw_label"] != c["label"]:
                    st.caption(("كما قريت: " if lang == "ar" else "as read: ")
                               + str(c["raw_label"]))
            with col2:
                st.markdown(
                    '<span class="fs-num">'
                    + cell_value_display(c["value"], vm["unit_scale"],
                                         vm["currency"]) + "</span>",
                    unsafe_allow_html=True)
            with col3:
                if c["reviewed"]:
                    st.markdown("✓ " + ("موثق بشريًا" if lang == "ar"
                                        else "human-attested"))
                kind = {"use": "ok", "use_disclosed": "ok",
                        "not_decisive": "pend", "missing": "miss"}[c["gate"]]
                icon = {"ok": "●", "pend": "◐", "miss": "○"}.get(kind, "○")
                st.markdown(
                    f'<span class="fs-gate {kind}">{icon} '
                    f'{c["gate_label"]}</span>', unsafe_allow_html=True)
            with col4:
                if st.button(_T["open_evidence"][lang],
                             key=f"ev-{c['field']}-{c['year']}",
                             use_container_width=True):
                    st.session_state["ev_cell"] = c
            if c["reason"] and c["gate"] != "use":
                st.caption(("السبب: " if lang == "ar" else "reason: ")
                           + c["reason"])
    ev = st.session_state.get("ev_cell")
    if ev:
        with st.expander(_T["evidence"][lang], expanded=True):
            evidence_block(ev, raw, vm["doc_sha"])


def sec_metrics(vm: dict) -> None:
    import pandas as pd

    lang = _lang()
    st.subheader(_T["metrics"][lang])
    sc, cur = vm["unit_scale"], vm["currency"]
    rows = []
    for r in vm["metrics"]:
        def fmt(v):
            if v is None:
                return "N/A"
            return (cell_value_display(v, sc, cur)
                    if r["kind"] == "currency" else
                    f"{v:.1f}%" if r["kind"] == "percent" else
                    f"{v:.2f}x" if r["kind"] == "ratio" else f"{v:,.2f}")
        rows.append({
            "المؤشر" if lang == "ar" else "Metric": r["label"],
            "السنة السابقة" if lang == "ar" else "Prev": fmt(r["prev"]),
            "السنة الحالية" if lang == "ar" else "Curr": fmt(r["curr"]),
            "التغير %" if lang == "ar" else "Change %":
                f"{r['change_pct']:+.1f}%" if r["change_pct"] is not None
                else "—",
            "التقييم" if lang == "ar" else "Assessment": r["status"] or "—",
            "حالة التحقق" if lang == "ar" else "Verification":
                r["verif"] or "—",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True,
                 hide_index=True)


def sec_health(vm: dict, results: dict) -> None:
    from src.analysis.score import compute_health_score

    lang = _lang()
    st.subheader(_T["health"][lang])
    blocked = {e["field"] for e in vm["pending"]}
    hs = compute_health_score(results["curr_metrics"],
                              blocked_fields=blocked)
    if hs.total is not None:
        c1, c2 = st.columns([1, 2])
        c1.metric("Health Score", f"{hs.total:.0f}/100",
                  delta=hs.label, delta_color="off")
        c2.markdown(" · ".join(
            f"**{p.name}**: " + ("—" if p.score is None else f"{p.score:.0f}")
            for p in hs.pillars))
        if getattr(hs, "policy", ""):
            st.caption(hs.policy)
    else:
        blocked_names = "، ".join(p.name for p in hs.pillars
                                  if p.score is None) or "—"
        refused = ("السياسة ترفض الحسم عند ركيزة حرجة ناقصة — الأركان "
                   "المحجوبة: " + blocked_names if lang == "ar" else
                   "The policy refuses when a critical pillar is missing."
                   " Blocked: " + blocked_names)
        st.error(f"**{_T['health_refused'][lang]}** — {refused}")
        st.caption("قيم هذه الأركان تحمل حالة «يحتاج مراجعة» في تبويب "
                   "القوائم — لا تحسب درجة من مدخلات غير موثقة."
                   if lang == "ar" else
                   "These pillars carry needs-review inputs.")


def sec_insights(vm: dict, analysis) -> None:
    """رؤى Gemini مصنفة من اتجاه المؤشر المحسوب — بلا اختلاق."""
    lang = _lang()
    st.subheader(_T["insights"][lang])
    if vm["pending_count"]:
        st.warning(_T["provisional"][lang])
    if not (analysis is not None and getattr(analysis, "ok", False)):
        reason = getattr(analysis, "error", "") or "—"
        st.info(("لا تحليل Gemini — السبب: " if lang == "ar" else
                 "No Gemini analysis — reason: ") + reason)
        return
    st.caption(f"model: {analysis.model} · {len(analysis.ratio_comments)} "
               + ("تعليقًا — كل رقم متتبع لأصل محسوب في Python"
                  if lang == "ar" else
                  "comments — every number traces to a computation"))
    trend = {r["label"]: r["status"] for r in vm["metrics"]}
    cats = {"strengths": [], "weaknesses": [], "neutral": [],
            "recommendations": []}
    for metric, text in getattr(analysis, "ratio_comments", []):
        status = trend.get(metric, "Neutral")
        item = {"metric": metric, "text": text, "status": status}
        if status == "Positive":
            cats["strengths"].append(item)
        elif status == "Negative":
            cats["weaknesses"].append(item)
        else:
            cats["neutral"].append(item)
    for action, text in getattr(analysis, "recommendations", []):
        cats["recommendations"].append({"metric": action, "text": text})

    groups = [(_T["strengths"][lang], cats["strengths"]),
              (_T["weaknesses"][lang], cats["weaknesses"]),
              (_T["neutral"][lang], cats["neutral"])]
    for title, items in groups:
        if not items:
            continue
        st.markdown(f"#### {title} ({len(items)})")
        for item in items:
            with st.container(border=True):
                st.markdown(f"**{item['metric']}**")
                st.write(item["text"])
    if cats["recommendations"]:
        st.markdown(f"#### {_T['recommendations'][lang]} "
                    f"({len(cats['recommendations'])})")
        for item in cats["recommendations"]:
            with st.container(border=True):
                st.markdown(f"**{item['metric']}**")
                st.write(item["text"])


def sec_reports(vm: dict, results: dict, analysis) -> None:
    from src.analysis.score import compute_health_score
    from src.dashboard.excel_report import build_excel_report
    from src.dashboard.report import build_html_report

    lang = _lang()
    st.subheader(_T["reports"][lang])
    blocked = {e["field"] for e in vm["pending"]}
    results["verification_status"] = vm["verification"]
    results["blocked_fields"] = sorted(blocked)
    hs = compute_health_score(results["curr_metrics"],
                              blocked_fields=blocked)
    c1, c2 = st.columns(2)
    with c1:
        xlsx = build_excel_report(results)
        st.download_button(
            "Excel (.xlsx)", xlsx,
            file_name=f"FinSight_{results.get('curr_year')}_analysis.xlsx",
            use_container_width=True)
        st.caption("الملخص · المؤشرات · الجداول · أثر المراجعة"
                   if lang == "ar" else
                   "Summary · metrics · statements · review trail")
    with c2:
        html = build_html_report(results, analysis, hs,
                                 currency=vm["currency"])
        st.download_button(
            "HTML", html.encode("utf-8"),
            file_name=f"FinSight_{results.get('curr_year')}_report.html",
            mime="text/html", use_container_width=True)
        st.caption("نفس الأرقام مع علم أولي/نهائي"
                   if lang == "ar" else
                   "Same numbers with the preliminary/final flag")
    soffice = Path(r"C:\Program Files\LibreOffice\program\soffice.exe")
    if not soffice.exists():
        st.info("إنتاج PDF غير متاح — LibreOffice غير مثبت؛ إصدارا "
                "Excel وHTML متاحان." if lang == "ar" else
                "PDF unavailable — LibreOffice not installed.")
        return
    if st.button("PDF", use_container_width=True):
        import subprocess

        with tempfile.TemporaryDirectory() as td:
            print_html = Path(td) / "report_print.html"
            print_html.write_text(
                build_html_report(results, analysis, hs,
                                  currency=vm["currency"],
                                  print_safe=True), encoding="utf-8")
            with st.spinner("LibreOffice..."):
                subprocess.run([str(soffice), "--headless", "--convert-to",
                                "pdf", "--outdir", td, str(print_html)],
                               capture_output=True, timeout=240)
            pdf = Path(td) / "report_print.pdf"
            if pdf.exists():
                st.download_button("PDF",
                                   pdf.read_bytes(),
                                   file_name=f"FinSight_"
                                             f"{results.get('curr_year')}_report.pdf",
                                   mime="application/pdf")
            else:
                st.error("فشل تحويل PDF." if lang == "ar" else
                         "PDF conversion failed.")


def _build_live_queue(vm: dict, results: dict, raw: bytes,
                      crops_dir: Path) -> list[dict]:
    """طابور مراجعة حي من سجل القرار — غير الحاسمة فقط، قصاصات من
    بايتات المستند نفسه، بلا GT (مع التخزين المؤقت للجلسة)."""
    from src.extraction.human_review import (  # noqa: E402
        EXTRACTION_VERSION, _sha256_file,
    )
    import pypdfium2 as pdfium

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
                img = pdf[page_no - 1].render(scale=3.0).to_pil() \
                    .convert("RGB")
                x0, y0, x1, y1 = [float(v) for v in bbox0[:4]]
                if max(x1, y1) > 1.5 and (max(x1, y1) > img.width or
                                           max(y1, y1) > img.height):
                    sx, sy = (img.width / max(x1, y1, 1),
                              img.height / max(y1, y1, 1))
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
    from src.extraction.human_review import (  # noqa: E402
        CONFIRMATION_LABELS_AR, CONFIRMATION_KEYS, apply_review,
        verify_log_integrity,
    )

    lang = _lang()
    st.subheader(_T["review"][lang])
    if not (os.environ.get("REVIEWERS_FILE") or os.environ.get("REVIEWERS")):
        st.info("المراجعة البشرية معطلة — تتطلب REVIEWERS_FILE و"
                "REVIEW_HMAC_KEY في .env (حساب test-reviewer ليس مراجعة "
                "إنتاجية)." if lang == "ar" else
                "Human review disabled — requires REVIEWERS_FILE and "
                "REVIEW_HMAC_KEY (test-reviewer is NOT production review).")
        return
    if raw is None:
        st.info("بايتات المستند غير محفوظة في الجلسة." if lang == "ar"
                else "Document bytes not in session.")
        return
    ok, bad = verify_log_integrity()
    if not ok:
        st.error(f"سجل المراجعات تالف (seq={bad}) — المراجعة مرفوضة."
                 if lang == "ar" else f"Review log broken (seq={bad}).")
        return
    crops_dir = Path(tempfile.gettempdir()) / "live_review_crops"
    qkey = f"{vm['doc_sha']}|{vm['pending_count']}"
    if st.session_state.get("live_queue_key") != qkey or \
            not st.session_state.get("live_queue"):
        st.session_state["live_queue"] = _build_live_queue(
            vm, results, raw, crops_dir)
        st.session_state["live_queue_key"] = qkey
    queue = st.session_state["live_queue"]
    if not queue:
        st.success("لا خانات بانتظار مراجعة — كل الخانات إما حاسمة أو بلا "
                   "صفحة مصدر مسجلة." if lang == "ar" else
                   "No cells awaiting review.")
        return
    st.caption("سياق الخانة الحي بلا ترويسة سنة مقصوصة — سلسلة المراجعة "
               "تسمح بالرفض فقط هنا (قاعدة السياق الكامل، بلا تجاوز)."
               if lang == "ar" else
               "Live context has no cropped year header — reject-only.")
    pkt = st.selectbox(
        "الخانة" if lang == "ar" else "Cell", queue,
        format_func=lambda p: f"{p['field']} · {p['year']} · p{p['page']}")
    col_a, col_b = st.columns(2)
    with col_a:
        if Path(pkt["page_image"]).exists():
            st.image(pkt["page_image"], caption=f"page {pkt['page']}")
    with col_b:
        if pkt["crop_image"] and Path(pkt["crop_image"]).exists():
            st.image(pkt["crop_image"])
        else:
            st.info("لا قصاصة (بلا bbox) — الرفض فقط." if lang == "ar"
                    else "No crop — reject only.")
    conf = {}
    st.markdown("**" + ("التأكيدات الأربعة للرفض" if lang == "ar" else
                        "The four reject confirmations") + "**")
    for k in CONFIRMATION_KEYS:
        if k == "value":
            continue
        conf[k] = st.checkbox(CONFIRMATION_LABELS_AR.get(k, k),
                              key=f"conf-{pkt['packet_id']}-{k}")
    reason = st.text_area(
        "سبب الرفض (يسجل في السلسلة الموقعة)" if lang == "ar" else
        "Reject reason (recorded in the signed chain)", "")
    c1, c2 = st.columns(2)
    reviewer = c1.text_input("اسم المراجع" if lang == "ar" else
                             "Reviewer", "")
    credential = c2.text_input("PIN", type="password")
    if st.button("تسجيل الرفض في السلسلة" if lang == "ar" else
                 "Record rejection", type="primary",
                 use_container_width=True):
        if not all(conf[k] for k in conf):
            st.error("أكد العناصر الأربعة أولًا." if lang == "ar" else
                     "Confirm the four elements first.")
        elif not reason.strip():
            st.error("سبب الرفض مطلوب." if lang == "ar" else
                     "A reason is required.")
        else:
            try:
                rec = apply_review(
                    queue, pkt["packet_id"], approved_value=None,
                    reviewer=reviewer, credential=credential,
                    decision_note=reason.strip(),
                    confirmations={**conf, "value": False})
                st.success("سجل الرفض في السلسلة الموقعة — حساب "
                           "المراجع ليس مراجعة إنتاجية."
                           if lang == "ar" else
                           "Rejection recorded — not a production review.")
                st.caption(f"seq={rec.get('seq')} · "
                           f"hash={str(rec.get('record_hash'))[:16]}")
            except Exception as exc:
                st.error(f"رفض السلسلة: {exc}" if lang == "ar" else
                         f"Chain refused: {exc}")


def render(results: dict, analysis, raw: bytes | None) -> None:
    """نقطة دخول الواجهة — تستدعى من app.py."""
    lang = st.session_state.get("ui_lang", "ar")
    vm = build_view_model(results, st.session_state.get("currency", "$"))

    with st.sidebar:
        st.markdown("### " + ("الواجهة الجديدة — تجريبية" if lang == "ar"
                              else "New UI — experimental"))
        if st.button("English / عربي", use_container_width=True):
            st.session_state["ui_lang"] = "en" if lang == "ar" else "ar"
            st.rerun()
        if st.button(_T["classic"][lang], use_container_width=True,
                     type="primary"):
            st.session_state["ui_mode"] = "new"
            st.session_state["ui_mode_classic_toggle"] = False
            st.rerun()
        st.divider()
        st.caption(f"{vm['file_name']}")
        st.caption(f"{_T['unit'][lang]}: {vm['unit_note'] or '-'}")
        st.caption(f"{_T['doc_sha'][lang]}: `{vm['doc_sha']}`")
        st.divider()
        if st.button(_T["new_analysis"][lang], use_container_width=True):
            for k in ("results", "analysis", "raw_bytes", "ev_cell",
                      "live_queue", "live_queue_key"):
                st.session_state.pop(k, None)
            st.rerun()

    tabs = st.tabs([_T["overview"][lang], _T["statements"][lang],
                    _T["metrics"][lang], _T["health"][lang],
                    _T["insights"][lang], _T["chat"][lang],
                    _T["review"][lang], _T["reports"][lang]])
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
