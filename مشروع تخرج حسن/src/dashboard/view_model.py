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

from src.analysis.comparison import LABELS_AR  # noqa: E402
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
            "key": r.key, "label": r.label_ar or r.label, "kind": r.kind,
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
    }


def cell_value_display(value: float | None, unit_scale: int,
                       currency: str) -> str:
    """القيمة الفعلية (المطبوع × مقياس الترويسة) بنص عربي موحد."""
    from src.dashboard.charts import fmt_value_ar

    return fmt_value_ar(value, "currency", currency, unit_scale)
