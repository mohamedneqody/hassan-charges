"""End-to-end pipeline orchestration (no UI code — testable headlessly)."""
from __future__ import annotations

import hashlib

from src.ai.gemini_agent import build_payload
from src.analysis.calculator import compute_year_metrics
from src.analysis.comparison import (
    DECLINING,
    IMPROVING,
    STABLE,
    build_comparison,
    growth_metrics,
    missing_data_report,
)
from src.config import REPORT_LANGUAGE
from src.dashboard.charts import fmt_signed_pct, fmt_value_ar
from src.exceptions import InsufficientDataError
from src.extraction.file_parsers import load_financial_data

_ASSESSMENT = {IMPROVING: "improving", DECLINING: "declining", STABLE: "stable"}


def _numeric_direction(change: float | None) -> str | None:
    if change is None:
        return None
    if change > 0:
        return "rose"
    if change < 0:
        return "fell"
    return "stable"


def _metric_entry(row, prev_year: int, curr_year: int, currency: str,
                  scale: int = 1) -> dict | None:
    """One payload entry per metric: exact name + pre-formatted values.

    Returns None for metrics that cannot be commented on (no data).
    """
    from src.analysis.comparison import GROWTH_LABELS_AR, LABELS_AR

    if REPORT_LANGUAGE == "ar":
        name = LABELS_AR.get(row.key) or GROWTH_LABELS_AR.get(row.key) or row.label_ar or row.label
    else:
        name = row.label
    entry: dict = {"metric": name}
    if row.key.endswith("_growth"):
        # Single value spanning the two years — no previous/current pair.
        if row.current is None:
            return None
        entry["value"] = fmt_signed_pct(row.current)
        entry["period"] = f"{prev_year} -> {curr_year}"
        entry["direction"] = _numeric_direction(row.current)
    else:
        if row.previous is None or row.current is None:
            return None  # a direction needs both years
        pv = fmt_value_ar(row.previous, row.kind, currency, scale)
        cv = fmt_value_ar(row.current, row.kind, currency, scale)
        # v6 إصلاح حديد عز (إصلاح 5): صياغة لفظية صريحة تمنع انقلاب دلالة
        # الرقم في نص الموديل: السالب يُمرر بصيغة (خسارة/سالب) — الموديل
        # أسقط إشارة السالب من خسائر 2020 فتناقض التفسير مع المحرك.
        if row.kind == "currency" and row.previous is not None and row.previous < 0:
            pv += " (خسارة/سالب)"
        if row.kind == "currency" and row.current is not None and row.current < 0:
            cv += " (خسارة/سالب)"
        # المضاعفات تبقى بصيغة "0.50x" النظيفة — التكرار اللفظي "(0.50x)"
        # كان يكسر عقد الحمولة (اختبار الشكل) والحاجز بعد التوليد يقارن
        # الأرقام المررة بنص Gemini على نفس الصيغة القياسية.
        entry["previous"] = pv
        entry["current"] = cv
        entry["direction"] = _numeric_direction(row.change)
    entry["assessment"] = _ASSESSMENT.get(row.trend)
    if row.change_pct is not None:
        entry["change_pct"] = fmt_signed_pct(row.change_pct)
    return entry


def run_pipeline(file_name: str, raw: bytes, company: str, progress_cb=None, page_range=None, fast_mode: bool = False) -> dict:
    """Upload bytes -> structured results. Raises AppError subclasses with
    user-facing messages on validation or extraction failures."""
    # Persistent cache: a file solved before replays with ZERO API calls
    # (server restarts no longer re-pay; the defense demo works offline).
    from src.extraction.result_cache import (
        extraction_key,
        load_cached_extraction,
        store_extraction,
    )

    def _flatten(nested: dict) -> dict:
        """field→year→v (متداخل) أو (field, year)→v — إلى "f|y" نصيًا."""
        out = {}
        for k, v in (nested or {}).items():
            if isinstance(k, tuple) and len(k) == 2:
                out[f"{k[0]}|{k[1]}"] = v
            elif isinstance(v, dict):
                for y, vv in v.items():
                    out[f"{k}|{y}"] = vv
        return out

    key = extraction_key(file_name, raw, page_range, fast_mode)
    # v5: قرار البوابة المخزون (كاش) — None في المسار الحي
    _cached_log = None
    _cached_bbox = {}
    _cached_labels = {}
    cached = load_cached_extraction(key)
    if cached is not None:
        from src.extraction.normalizer import FinancialData

        data = FinancialData(
            values={f: {int(y): v for y, v in by_year.items()}
                    for f, by_year in cached["values"].items()},
            notes=list(cached["notes"]),
            currency_hint=cached.get("currency_hint"),
            company_hint=cached.get("company_hint"),
            confidence={f: {int(y): int(l) for y, l in by_year.items()}
                        for f, by_year in (cached.get("confidence") or {}).items()},
            notes_text={int(k): v for k, v in (cached.get("notes_text") or {}).items()},
        )
        data.field_sources = cached.get("field_sources") or {}
        # v5: استعادة وحدة الطباعة المخزنة — الكاش يحفظها لكن إعادة البناء
        # كانت تتركها 1 فتعرض TE «مليون» بدل «مليار» (كشفه اختبار الرحلة)
        data.unit_scale = int(cached.get("unit_scale") or 1)
        data.unit_note = cached.get("unit_note") or ""
        _cached_log = cached.get("decision_log") or []
        _cached_bbox = cached.get("candidate_bbox") or {}
        _cached_labels = cached.get("candidate_labels") or {}
        data.notes.append(
            "⚡ Loaded from the local cache — no API calls were spent. "
            "(Use «مسح الكاش المحلي» in the sidebar to re-extract fresh.)"
        )
        if progress_cb:
            progress_cb("ملف محلول قبلًا — تم التحميل من الكاش المحلي (صفر نداءات)")
    else:
        data = load_financial_data(file_name, raw, progress_cb=progress_cb,
                                   page_range=page_range, fast_mode=fast_mode)
        try:
            from src.extraction.normalizer import build_decision_log as _bdl

            store_extraction(key, {
                "values": data.values,
                "notes": data.notes,
                "currency_hint": data.currency_hint,
        "unit_scale": getattr(data, "unit_scale", 1),
        "unit_note": getattr(data, "unit_note", ""),
                "company_hint": data.company_hint,
                "confidence": data.confidence,
                "notes_text": data.notes_text,
                "field_sources": getattr(data, "field_sources", {}),
                "spatial_shadow": getattr(data, "spatial_shadow", None),
                "human_reviews": {
                    f"{k[0]}|{k[1]}": v for k, v
                    in (getattr(data, "human_reviews", {}) or {}).items()},
                # v5: قرار البوابة ومواضع الخانات كما حُسبت أول مرة —
                # الكاش لا يحفظ المرشحين فإعادة بناء السجل منه كانت ستعيد
                # سجلًا فارغًا (عيب كشفه اختبار الدمج الحي)
                "decision_log": _bdl(data),
                "candidate_bbox": _flatten(
                    getattr(data, "candidate_bbox", {})),
                "candidate_labels": _flatten(
                    getattr(data, "candidate_labels", {})),
            })
        except Exception as exc:
            # caching must never break the pipeline — but the failure is no
            # longer silent (a 2022 cache file was once missing for sessions
            # without any clue why).
            data.notes.append(f"cache store skipped: {type(exc).__name__}: {exc}")

    # The name printed inside the document beats the file name (the applied
    # study needs the real company identity: شركة … as the disclosure prints it).
    if getattr(data, "company_hint", None):
        company = data.company_hint

    years_pair = data.latest_two_years()
    if years_pair is None:
        raise InsufficientDataError(
            "at least two fiscal years are required, e.g. FY2025 and FY2026."
        )
    prev_year, curr_year = years_pair

    has_core = any(
        data.values.get(field_name, {}).get(prev_year) is not None
        and data.values.get(field_name, {}).get(curr_year) is not None
        for field_name in ("revenue", "net_income")
    )
    if not has_core:
        raise InsufficientDataError(
            "no Revenue or Net Income values were recognized for both years."
        )

    prev_metrics = compute_year_metrics(prev_year, data.values, prev_year=None)
    curr_metrics = compute_year_metrics(curr_year, data.values, prev_year=prev_year)

    # Every fiscal year in the document gets full metrics: trend analysis
    # needs the whole series, not just the latest two years.
    years_sorted = sorted(y for y in (data.years or []) if isinstance(y, int))
    all_year_metrics = {
        y: compute_year_metrics(
            y, data.values, prev_year=(years_sorted[i - 1] if i else None)
        )
        for i, y in enumerate(years_sorted)
    }

    rows = build_comparison(prev_metrics, curr_metrics)
    growth_rows = growth_metrics(prev_metrics, curr_metrics)

    # v5 (دمج الواجهة الجديدة): مفاتيح قراءة فقط لواجهة Streamlit الجديدة —
    # سجل القرار (أساس عمود حالة التحقق وقرار البوابة) + مواضع الخانات
    # (bbox) + تسميات المرشحين + هاش المستند. لا تغيير في أي قرار مالي:
    # كل هذه القيم مشتقة من نفس data التي بُنيت منها النتائج أعلاه.
    from src.extraction.normalizer import build_decision_log

    decision_log = _cached_log if _cached_log else build_decision_log(data)

    bbox = _cached_bbox or _flatten(getattr(data, "candidate_bbox", {}))
    labels = _cached_labels or _flatten(getattr(data, "candidate_labels", {}))

    return {
        "company": company,
        "file_name": file_name,
        "prev_year": prev_year,
        "curr_year": curr_year,
        "prev_metrics": prev_metrics,
        "curr_metrics": curr_metrics,
        "all_year_metrics": all_year_metrics,
        "rows": rows,
        "growth_rows": growth_rows,
        "rows_by_key": {r.key: r for r in rows},
        "missing": missing_data_report(
            rows + growth_rows,
            metrics_by_year={y: all_year_metrics[y]
                             for y in all_year_metrics}),
        "notes": data.notes,
        "metric_years_available": data.years,
        "currency_hint": data.currency_hint,
        "unit_scale": getattr(data, "unit_scale", 1),
        "unit_note": getattr(data, "unit_note", ""),
        "confidence": data.confidence,
        "notes_text": data.notes_text,
        "field_sources": getattr(data, "field_sources", {}),
        "spatial_shadow": getattr(data, "spatial_shadow", None),
        "human_reviews": {
            f"{k[0]}|{k[1]}": v for k, v
            in (getattr(data, "human_reviews", {}) or {}).items()},
        "decision_log": decision_log,
        "pending_critical_review": [],
        "candidate_bbox": bbox,
        "candidate_labels": labels,
        "document_sha256_16": hashlib.sha256(raw).hexdigest()[:16],
    }


def build_gemini_payload(results: dict, currency: str = "$") -> dict:
    """Payload: one pre-formatted entry per commentable metric (growth first).

    Defensive on optional keys: partial result dicts (tests, review UIs)
    must not crash the payload builder — missing metrics simply yield no
    entries instead of a KeyError.
    """
    notes = list(results.get("notes") or [])
    for m in (results.get("prev_metrics"), results.get("curr_metrics")):
        if m is not None:
            notes.extend(getattr(m, "notes", {}).values())

    from src.analysis.notes_rag import build_notes_digest

    notes_highlights = build_notes_digest(results.get("notes_text") or {})

    ordered_rows = list(results.get("growth_rows") or []) + list(results.get("rows") or [])
    metrics = []
    scale = int(results.get("unit_scale") or 1)
    # v6 إصلاح حديد عز (إصلاح 4-ب): المؤشر المحجوب (تعارض محجوب /
    # not_decisive عبر حالة تحقق أسوأ مدخلاته) لا يمر إلى Gemini إطلاقًا —
    # حديد عز: 8 مؤشرات محجوبة (Fixed Asset Turnover/DPO/CCC بسبب جدول
    # إيضاح الأصول الثابتة المشوه ص13) وصلت لبناء التوصيات 2 و3 و4.
    verif = results.get("verification_status") or {}
    blocked_markers = ("تعارض", "يحتاج مراجعة", "غير متوفر")
    for row in ordered_rows:
        v = verif.get(row.key, "")
        if any(m in v for m in blocked_markers):
            continue
        entry = _metric_entry(row, results["prev_year"], results["curr_year"],
                              currency, scale)
        if entry is not None:
            metrics.append(entry)

    return build_payload(
        company=results.get("company") or "",
        prev_year=results.get("prev_year"),
        curr_year=results.get("curr_year"),
        metrics=metrics,
        missing_data=results.get("missing") or [],
        extraction_notes=notes,
        notes_highlights=notes_highlights,
    )
