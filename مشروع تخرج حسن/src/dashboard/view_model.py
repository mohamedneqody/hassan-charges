# -*- coding: utf-8 -*-
"""الـAdapter المحدود بين نتائج الـPipeline وواجهة Streamlit الجديدة (v5).

قراءة فقط: يحول نتائج run_pipeline إلى صفوف عرض (قيمة، قرار بوابة، مصدر،
وحدة، صفحة، bbox) دون أن يغيّر أي قرار مالي أو يضيف استنتاجًا. التمييز
المحوري الذي تفرضه المراجعة: حالة الصف تأتي من **قرار بوابة الاعتماد
النهائي** (financial_gate.decide على حالة سجل القرار) — لا من حالة
المرشحين وحدها: VERIFIED_EXACT في سجل المرشحين قد يصبح CONFLICT/UNVERIFIED
بعد حراس البوابة (تعارض الإشارة، التطابق الهوائي، المصدر الواحد) —
الواجهة تعرض قرار البوابة الأخير وحده.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
if str(PROJ) not in sys.path:
    sys.path.insert(0, str(PROJ))

from src.analysis.comparison import CATEGORY_AR, LABELS_AR  # noqa: E402
from src.analysis.financial_gate import decide, verification_labels  # noqa: E402

# قرار البوابة → (التسمية العربية، الصنف اللوني)
GATE_LABELS = {
    "use": ("موثق — يدخل الحساب", "ok"),
    "use_disclosed": ("موثق (معلن) — يدخل الحساب", "ok"),
    "not_decisive": ("يحتاج مراجعة — محجوب عن الحسم", "pend"),
    "missing": ("غير ملتقطة", "miss"),
}

FIELD_ORDER = [
    "revenue", "cost_of_revenue", "gross_profit", "operating_income",
    "pretax_income", "income_tax_expense", "net_income",
    "fixed_assets", "inventory", "accounts_receivable", "cash",
    "current_assets", "total_assets", "accounts_payable",
    "current_liabilities", "total_liabilities", "equity",
    "operating_cash_flow", "investing_cash_flow", "financing_cash_flow",
]


def _gate_of(status: str) -> str:
    d = decide(status)
    return d if d in ("use", "use_disclosed") else (
        "missing" if status == "MISSING" else "not_decisive")


def cell_rows(results: dict) -> list[dict]:
    """صف لكل (بند، سنة) في سجل القرار — قرار البوابة هو المعروض."""
    log = results.get("decision_log") or []
    bbox = results.get("candidate_bbox") or {}
    labels = results.get("candidate_labels") or {}
    rows = []
    for e in log:
        field, year = e["field"], e["year"]
        gate = _gate_of(e.get("status", "MISSING"))
        label = LABELS_AR.get(field, field)
        raw = labels.get(f"{field}|{year}") or ""
        raw_label = raw[-1] if isinstance(raw, list) and raw else raw
        rows.append({
            "field": field,
            "label": label,
            "label_en": field.replace("_", " ").title(),
            "raw_label": raw_label,
            "year": year,
            "value": e.get("final"),
            "status": e.get("status"),
            "gate": gate,
            "gate_label": GATE_LABELS[gate][0],
            "gate_kind": GATE_LABELS[gate][1],
            "source": e.get("source") or "—",
            "pages": e.get("pages") or [],
            "reason": e.get("reason") or "",
            "candidates": e.get("candidates") or [],
            "winner_layers": e.get("winner_layers"),
            "bbox": bbox.get(f"{field}|{year}"),
            "reviewed": bool((results.get("human_reviews") or {})
                             .get(f"{field}|{year}")),
        })
    rows.sort(key=lambda r: (FIELD_ORDER.index(r["field"])
                             if r["field"] in FIELD_ORDER else 99,
                             -r["year"]))
    return rows


def build_view_model(results: dict, currency: str = "$") -> dict:
    """نموذج العرض الكامل: ميتا + صفوف الخانات + صفوف المؤشرات بحالة
    التحقق (أسوأ حالة لمدخلات كل مؤشر — نفس ما تعرضه Excel)."""
    verif = verification_labels(results.get("decision_log") or [])
    cells = cell_rows(results)
    metric_rows = []
    for r in results.get("rows", []):
        metric_rows.append({
            "key": r.key,
            "label": r.label_ar or r.label,
            "label_en": r.label,
            "category": r.category,
            "category_ar": CATEGORY_AR.get(r.category, r.category),
            "kind": r.kind,
            "prev": r.previous, "curr": r.current, "change": r.change,
            "change_pct": r.change_pct, "status": r.status,
            "trend": r.trend_symbol,
            "verif": verif.get(r.key, "—"),
        })
    pending = [e for e in (results.get("decision_log") or [])
               if _gate_of(e.get("status", "MISSING")) in
               ("not_decisive", "missing")]
    return {
        "company": results.get("company") or "—",
        "file_name": results.get("file_name") or "—",
        "prev_year": results.get("prev_year"),
        "curr_year": results.get("curr_year"),
        "unit_scale": int(results.get("unit_scale") or 1),
        "unit_note": results.get("unit_note") or "",
        "currency": currency or results.get("currency_hint") or "$",
        "doc_sha": results.get("document_sha256_16") or "",
        "profile": (results.get("notes") or [])[0:2],
        "cells": cells,
        "cell_count": len(cells),
        "decisive_count": sum(1 for c in cells
                              if c["gate"] in ("use", "use_disclosed")),
        "pending": pending,
        "pending_count": len(pending),
        "metrics": metric_rows,
        "verification": verif,
        "notes_text": results.get("notes_text") or {},
        "human_reviews": results.get("human_reviews") or {},
        "formal_certificate": results.get("formal_certificate") or None,
    }


def cell_value_display(value: float | None, unit_scale: int,
                       currency: str) -> str:
    """القيمة الفعلية (المطبوع × مقياس الترويسة) بنص عربي موحد."""
    from src.dashboard.charts import fmt_value_ar

    return fmt_value_ar(value, "currency", currency, unit_scale)


def executive_summary(results: dict, vm: dict, lang: str = "ar") -> list[str]:
    """الملخص التنفيذي — حقائق محسوبة فقط من نتائج التشغيل الحي.
    لا استنتاج ولا قيمة مفقودة تُختلق؛ غير المتاح يُعلن."""
    from src.analysis.score import compute_health_score
    from src.dashboard.charts import humanize

    facts: list[str] = []
    is_ar = lang != "en"
    curr_year = vm["curr_year"]
    prev_year = vm["prev_year"]
    sc = vm["unit_scale"]
    cur = vm["currency"]
    curr = results["curr_metrics"]

    def _cur_txt(val: float) -> str:
        return cell_value_display(val, sc, cur) if is_ar else f"{cur}{humanize(val, sc)}"

    # 1) تغطية البوابة
    total = vm["cell_count"]
    dec = vm["decisive_count"]
    if total:
        pct_cov = round(dec / total * 100)
        facts.append(
            f"تغطية التوثيق: {dec} من {total} خانة حاسمة "
            f"({pct_cov}%) — الباقي يحتاج مراجعة بشرية قبل الاعتماد النهائي."
            if is_ar
            else f"Verification coverage: {dec} of {total} decisive cells "
            f"({pct_cov}%) — remaining cells require human review before final sign-off."
        )

    # 2) الإيراد والربح (إن توفرا)
    rows = {r.key: r for r in results.get("rows", [])}
    rev = rows.get("revenue")
    if rev and rev.current is not None:
        pct = f" ({rev.change_pct:+.1f}%)" if rev.change_pct is not None else ""
        if rev.change is None:
            facts.append(
                f"الإيرادات {curr_year}: {_cur_txt(rev.current)}."
                if is_ar
                else f"Revenue {curr_year}: {_cur_txt(rev.current)}."
            )
        elif is_ar:
            direction = "ارتفاع" if rev.change > 0 else ("انخفاض" if rev.change < 0 else "استقرار")
            facts.append(f"الإيرادات {curr_year}: {_cur_txt(rev.current)} — {direction} عن {prev_year}{pct}.")
        else:
            direction = "up" if rev.change > 0 else ("down" if rev.change < 0 else "unchanged")
            facts.append(f"Revenue {curr_year}: {_cur_txt(rev.current)} — {direction} vs {prev_year}{pct}.")
    ni = rows.get("net_income")
    if ni and ni.current is not None:
        pct = f" ({ni.change_pct:+.1f}%)" if ni.change_pct is not None else ""
        if ni.change is None:
            facts.append(
                f"صافي الربح {curr_year}: {_cur_txt(ni.current)}."
                if is_ar
                else f"Net income {curr_year}: {_cur_txt(ni.current)}."
            )
        elif is_ar:
            direction = "ارتفاع" if ni.change > 0 else ("انخفاض" if ni.change < 0 else "استقرار")
            facts.append(f"صافي الربح {curr_year}: {_cur_txt(ni.current)} — {direction}{pct}.")
        else:
            direction = "up" if ni.change > 0 else ("down" if ni.change < 0 else "unchanged")
            facts.append(f"Net income {curr_year}: {_cur_txt(ni.current)} — {direction}{pct}.")

    # 3) السيولة والمديونية مقابل المعايير العامة
    if curr.current_ratio is not None:
        if is_ar:
            state = ("أعلى من" if curr.current_ratio >= 2.0 else
                     "أدنى من" if curr.current_ratio < 1.0 else "قريبة من")
            facts.append(f"نسبة التداول {curr.current_ratio:.2f}x — {state} الحد الإرشادي العام (2.00x).")
        else:
            state = ("above" if curr.current_ratio >= 2.0 else
                     "below" if curr.current_ratio < 1.0 else "near")
            facts.append(f"Current ratio {curr.current_ratio:.2f}x — {state} the 2.00x general guideline.")
    if curr.debt_ratio is not None:
        if is_ar:
            state = "داخل" if curr.debt_ratio < 0.5 else "أعلى من"
            facts.append(f"نسبة الدين {curr.debt_ratio:.2f} — {state} الحد الإرشادي العام (< 0.50).")
        else:
            state = "within" if curr.debt_ratio < 0.5 else "above"
            facts.append(f"Debt ratio {curr.debt_ratio:.2f} — {state} the < 0.50 general guideline.")

    # 4) الدرجة الصحية أو سبب الحجب
    blocked = {e["field"] for e in vm["pending"]}
    hs = compute_health_score(curr, blocked_fields=blocked)
    if hs.total is not None:
        lbl = hs.label_ar if is_ar else hs.label_en
        facts.append(
            f"الدرجة الصحية: {hs.total:.0f}/100 ({lbl})."
            if is_ar
            else f"Health score: {hs.total:.0f}/100 ({lbl})."
        )
    else:
        sep = "، " if is_ar else ", "
        blocked_names = sep.join((p.name_ar if is_ar else p.name_en) for p in hs.pillars if p.score is None) or "—"
        facts.append(
            f"الدرجة الصحية محجوبة وفق سياسة تغطية البيانات — أركان ناقصة: {blocked_names}."
            if is_ar
            else f"Health score refused under data-coverage policy — missing pillars: {blocked_names}."
        )

    # 5) المؤشرات غير القابلة للحساب — معلنة
    na = [(r.label_ar or r.label) if is_ar else r.label for r in rows.values()
          if r.previous is None and r.current is None]
    if na:
        if is_ar:
            facts.append(
                f"مؤشرات غير قابلة للحساب لعدم توفر مدخلاتها ({len(na)}): "
                + "، ".join(na[:8]) + ("، …" if len(na) > 8 else "") + "."
            )
        else:
            facts.append(
                f"Metrics unavailable due to missing inputs ({len(na)}): "
                + ", ".join(na[:8]) + (", …" if len(na) > 8 else "") + "."
            )
    return facts


def categorized_insights(results: dict, analysis) -> dict:
    """تصنيف تعليقات التحليل من اتجاه المؤشر المحسوب — تصنيف من البيانات
    لا من نبرة النص: تحسّن → نقاط قوة، تراجع → نقاط ضعف، والتوصيات
    قائمة بذاتها. يعمل لنتائج Gemini وللتعليق القاعدي الحتمي عند غياب API."""
    out = {"strengths": [], "weaknesses": [], "neutral": [],
           "recommendations": []}
    if analysis is None:
        return out
    comments = getattr(analysis, "ratio_comments", None) or []
    recs = getattr(analysis, "recommendations", None) or []
    if not (getattr(analysis, "ok", False) or comments or recs):
        return out
    trend_by_metric = {}
    ar_by_metric = {}
    for r in list(results.get("rows", [])) + list(results.get("growth_rows", [])):
        name = r.label_ar or r.label
        trend_by_metric[name] = r.status
        trend_by_metric[r.label] = r.status
        trend_by_metric[r.key] = r.status
        ar_by_metric[r.label] = name
        ar_by_metric[r.key] = name
        ar_by_metric[name] = name
    eff_cur = (results.get("currency_hint") or "").strip()

    def _norm_cur(txt: str) -> str:
        s = str(txt or "")
        if eff_cur and eff_cur != "$":
            import re as _re
            s = _re.sub(r"\$(?=[+-]?\d)", f"{eff_cur} ", s)
        return s

    for metric, text in comments:
        status = trend_by_metric.get(metric)
        disp_metric = ar_by_metric.get(metric, metric)
        item = {"metric": disp_metric, "metric_en": metric, "text": _norm_cur(text),
                "status": status or "Neutral"}
        if status == "Positive":
            out["strengths"].append(item)
        elif status == "Negative":
            out["weaknesses"].append(item)
        else:
            out["neutral"].append(item)
    for action, text in recs:
        out["recommendations"].append({"metric": _norm_cur(action), "text": _norm_cur(text)})
    return out


def report_memo(results: dict, key: str, builder):
    """تقارير تُبنى مرة واحدة لكل مستند وحالة تحقق وعملة.

    المفتاح يربط هاش المستند + عدد المراجعات البشرية + الحقول المحجوبة + العملة + نوع التقرير
    حتى لا تتسرب تقارير مستند سابق أو عملة سابقة أو حالة بوابة قديمة عند رفع ملف جديد.
    """
    import hashlib
    import streamlit as st

    doc_id = (
        results.get("document_sha256_16")
        or f"{results.get('file_name', '')}|{results.get('company', '')}|{results.get('curr_year', '')}"
    )
    reviews_n = len(results.get("human_reviews") or {})
    blocked_sig = hashlib.sha1(
        "|".join(sorted(str(x) for x in (results.get("blocked_fields") or []))).encode("utf-8")
    ).hexdigest()[:8]
    currency = st.session_state.get("currency", results.get("currency_hint") or "$")
    memo_key = f"{doc_id}|{reviews_n}|{blocked_sig}|{currency}|{key}"
    memo = st.session_state.setdefault("_report_memo", {})
    if memo_key not in memo:
        memo[memo_key] = builder()
    return memo[memo_key]
