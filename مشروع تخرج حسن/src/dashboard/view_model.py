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
    "use": ("موثق — يدخل الحساب الرسمي", "ok"),
    "use_disclosed": ("موثق (معلن) — يدخل الحساب الرسمي", "ok"),
    "not_decisive": ("يحتاج مراجعة — يدخل المؤشرات (محجوب عن الدرجة الرسمية)", "pend"),
    "missing": ("غير ملتقطة", "miss"),
}

FIELD_ORDER = [
    "revenue", "cost_of_revenue", "gross_profit", "other_operating_income",
    "selling_expenses", "admin_expenses", "other_operating_expenses", "operating_income",
    "finance_income", "interest_expense", "fx_gain_loss", "dividends_from_subsidiaries",
    "pretax_income", "income_tax_expense", "net_income",
    "fixed_assets", "projects_under_construction", "investments_in_subsidiaries",
    "other_investments", "deferred_tax_assets", "non_current_assets",
    "inventory", "accounts_receivable", "other_receivables", "supplier_advances", "cash",
    "current_assets", "total_assets", "accounts_payable", "customer_advances",
    "other_payables", "provisions",
    "bank_overdraft", "short_term_credit_facilities", "short_term_debt",
    "current_portion_lt_debt", "current_lease_liabilities", "current_liabilities",
    "long_term_debt", "long_term_notes_payable", "non_current_lease_liabilities",
    "deferred_tax_liabilities", "non_current_liabilities",
    "total_liabilities", "total_debt",
    "capital", "treasury_shares", "reserves", "asset_revaluation_reserve",
    "retained_earnings", "equity",
    "operating_cash_flow", "investing_cash_flow", "financing_cash_flow", "capex",
]


def _gate_of(status: str) -> str:
    d = decide(status)
    return d if d in ("use", "use_disclosed") else (
        "missing" if status == "MISSING" else "not_decisive")


def resolve_cell_bbox(
    bbox_map: dict | None,
    field: str,
    year,
    pages: list | None = None,
):
    """Return exact bbox for (field, year), or fall back to a sibling-year
    full-row horizontal strip on the same statement page when available."""
    if not isinstance(bbox_map, dict):
        return None
    direct = bbox_map.get(f"{field}|{year}")
    if direct:
        return direct
    prefix = f"{field}|"
    page_set = {int(p) for p in (pages or []) if str(p).isdigit()}
    for k, val in bbox_map.items():
        if not k.startswith(prefix) or not val:
            continue
        item = val[0] if isinstance(val, list) and val else val
        if isinstance(item, dict):
            pg = item.get("page")
            if page_set and pg is not None and int(pg) not in page_set:
                continue
            coords = item.get("bbox_px") or item.get("bbox") or item.get("box")
            if coords and len(coords) >= 4:
                return {
                    "page": pg if pg is not None else (next(iter(page_set)) if page_set else None),
                    "bbox_px": list(coords[:4]),
                    "render_scale": item.get("render_scale") or 2.0,
                    "row_band": True,
                }
        elif isinstance(item, (list, tuple)) and len(item) >= 4:
            return {
                "page": next(iter(page_set)) if page_set else None,
                "bbox": list(item[:4]),
                "row_band": True,
            }
    return None


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
        cand_pages = e.get("pages") or []
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
            "pages": cand_pages,
            "reason": e.get("reason") or "",
            "candidates": e.get("candidates") or [],
            "winner_layers": e.get("winner_layers"),
            "bbox": resolve_cell_bbox(bbox, field, year, cand_pages),
            "reviewed": bool((results.get("human_reviews") or {})
                             .get(f"{field}|{year}")),
        })
    rows.sort(key=lambda r: (FIELD_ORDER.index(r["field"])
                             if r["field"] in FIELD_ORDER else 99,
                             -r["year"]))
    return rows


_OPTIONAL_DISCLOSURE_INPUTS = {
    "rd_pct": "rd_expenses",
}


def build_view_model(results: dict, currency: str = "$") -> dict:
    """نموذج العرض الكامل: ميتا + صفوف الخانات + صفوف المؤشرات بحالة
    التحقق (أسوأ حالة لمدخلات كل مؤشر — نفس ما تعرضه Excel)."""
    dec_log = results.get("decision_log") or []
    verif = dict(verification_labels(dec_log))
    captured_fields = {
        e.get("field") for e in dec_log if e.get("field") and e.get("final") is not None
    }
    cells = cell_rows(results)
    metric_rows = []
    for r in results.get("rows", []):
        opt_input = _OPTIONAL_DISCLOSURE_INPUTS.get(r.key)
        is_not_disclosed = bool(
            opt_input
            and r.previous is None
            and r.current is None
            and opt_input not in captured_fields
        )
        if is_not_disclosed:
            verif[r.key] = "غير مفصح بالقوائم"
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
            "not_disclosed": is_not_disclosed,
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
        "quota_interrupted": bool(results.get("quota_interrupted")),
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

    # 1) تغطية البوابة (تمييز واضح بين القوائم الأساسية وإجمالي البنود التفصيلية)
    total = vm["cell_count"]
    dec = vm["decisive_count"]
    _core_set = {
        "revenue", "cost_of_revenue", "gross_profit", "operating_income",
        "pretax_income", "net_income", "total_assets", "current_assets",
        "non_current_assets", "total_liabilities", "current_liabilities",
        "non_current_liabilities", "equity", "cash", "operating_cash_flow",
        "investing_cash_flow", "financing_cash_flow",
    }
    core_cells = [c for c in (vm.get("cells") or []) if c.get("field") in _core_set]
    core_dec = sum(1 for c in core_cells if c.get("gate") in ("use", "use_disclosed"))
    core_tot = len(core_cells)
    if total:
        pct_cov = round(dec / total * 100)
        core_pct = round(core_dec / core_tot * 100) if core_tot else pct_cov
        if dec >= total:
            facts.append(
                f"تغطية التوثيق: {dec} من {total} خانة حاسمة "
                f"({pct_cov}%) — جميع الخانات معتمدة بالكامل دون خانات معلقة."
                if is_ar
                else f"Verification coverage: {dec} of {total} decisive cells "
                f"({pct_cov}%) — all cells verified with zero pending items."
            )
        else:
            core_note_ar = (
                f"القوائم الأساسية الموثّقة: {core_dec}/{core_tot} ({core_pct}%) · "
                if core_tot else ""
            )
            core_note_en = (
                f"Core statements verified: {core_dec}/{core_tot} ({core_pct}%) · "
                if core_tot else ""
            )
            facts.append(
                f"{core_note_ar}إجمالي كل الخانات (شاملة الإيضاحات التفصيلية): {dec} من {total} "
                f"({pct_cov}%) — المتبقي متاح للمراجعة البشرية بالدليل المصوّر."
                if is_ar
                else f"{core_note_en}All cells (incl. sub-notes): {dec} of {total} "
                f"({pct_cov}%) — remaining items available for human review."
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
            facts.append(f"نسبة الدين {curr.debt_ratio:.2f} — {state} الحد الإرشادي العام (أقل من 0.50).")
        else:
            state = "within" if curr.debt_ratio < 0.5 else "above"
            facts.append(f"Debt ratio {curr.debt_ratio:.2f} — {state} the < 0.50 general guideline.")

    # 4) الدرجة الصحية أو سبب الحجب (تطابق تام مع تبويب الدرجة الصحية: حجب السنة الحالية فقط)
    blocked = {
        e["field"] for e in vm["pending"]
        if e.get("field")
        and (curr_year is None or e.get("year") in (None, curr_year) or str(e.get("year")) == str(curr_year))
    }
    hs = compute_health_score(curr, blocked_fields=blocked)
    if hs.total is not None:
        lbl = hs.label_ar if is_ar else hs.label_en
        score_int = int(round(hs.total))
        facts.append(
            f"الدرجة الصحية: {score_int}/100 ({lbl})."
            if is_ar
            else f"Health score: {score_int}/100 ({lbl})."
        )
    else:
        sep = "، " if is_ar else ", "
        blocked_names = sep.join((p.name_ar if is_ar else p.name_en) for p in hs.pillars if p.score is None) or "—"
        facts.append(
            f"الدرجة الصحية محجوبة وفق سياسة تغطية البيانات — أركان ناقصة: {blocked_names}."
            if is_ar
            else f"Health score refused under data-coverage policy — missing pillars: {blocked_names}."
        )

    # 5) المؤشرات غير القابلة للحساب مقابل البنود الاختيارية غير المفصح عنها بالقوائم
    captured_fields_ov = {
        e.get("field") for e in (results.get("decision_log") or [])
        if e.get("field") and e.get("final") is not None
    }
    na_missing: list[str] = []
    na_optional: list[str] = []
    for r in rows.values():
        if r.previous is not None or r.current is not None:
            continue
        disp = (r.label_ar or r.label) if is_ar else r.label
        opt_f = _OPTIONAL_DISCLOSURE_INPUTS.get(r.key)
        if opt_f and opt_f not in captured_fields_ov:
            na_optional.append(disp)
        else:
            na_missing.append(disp)
    if na_missing:
        if is_ar:
            facts.append(
                f"مؤشرات غير قابلة للحساب لعدم توفر مدخلاتها ({len(na_missing)}): "
                + "، ".join(na_missing[:8]) + ("، …" if len(na_missing) > 8 else "") + "."
            )
        else:
            facts.append(
                f"Metrics unavailable due to missing inputs ({len(na_missing)}): "
                + ", ".join(na_missing[:8]) + (", …" if len(na_missing) > 8 else "") + "."
            )
    elif rows:
        if is_ar:
            opt_tail = (
                f" (بنود اختيارية غير مفصح عنها بقوائم الشركة ولا تنطبق: {'، '.join(na_optional)})"
                if na_optional else ""
            )
            facts.append(f"تغطية المؤشرات المالية القابلة للحساب من القوائم: 100% مكتملة{opt_tail}.")
        else:
            opt_tail = (
                f" (optional items not disclosed in statements: {', '.join(na_optional)})"
                if na_optional else ""
            )
            facts.append(f"Computable financial ratio coverage: 100% complete{opt_tail}.")
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
