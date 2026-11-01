"""End-to-end pipeline orchestration (no UI code — testable headlessly)."""
from __future__ import annotations

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
from src.dashboard.charts import fmt_signed_pct, fmt_value
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


def _metric_entry(row, prev_year: int, curr_year: int, currency: str) -> dict | None:
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
        entry["previous"] = fmt_value(row.previous, row.kind, currency)
        entry["current"] = fmt_value(row.current, row.kind, currency)
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

    key = extraction_key(file_name, raw, page_range, fast_mode)
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
            store_extraction(key, {
                "values": data.values,
                "notes": data.notes,
                "currency_hint": data.currency_hint,
                "company_hint": data.company_hint,
                "confidence": data.confidence,
                "notes_text": data.notes_text,
                "field_sources": getattr(data, "field_sources", {}),
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
        "missing": missing_data_report(rows + growth_rows),
        "notes": data.notes,
        "metric_years_available": data.years,
        "currency_hint": data.currency_hint,
        "confidence": data.confidence,
        "notes_text": data.notes_text,
        "field_sources": getattr(data, "field_sources", {}),
    }


def build_gemini_payload(results: dict, currency: str = "$") -> dict:
    """Payload: one pre-formatted entry per commentable metric (growth first)."""
    notes = list(results["notes"])
    for m in (results["prev_metrics"], results["curr_metrics"]):
        notes.extend(m.notes.values())

    from src.analysis.notes_rag import build_notes_digest

    notes_highlights = build_notes_digest(results.get("notes_text") or {})

    ordered_rows = list(results["growth_rows"]) + list(results["rows"])
    metrics = []
    for row in ordered_rows:
        entry = _metric_entry(row, results["prev_year"], results["curr_year"], currency)
        if entry is not None:
            metrics.append(entry)

    return build_payload(
        company=results["company"],
        prev_year=results["prev_year"],
        curr_year=results["curr_year"],
        metrics=metrics,
        missing_data=results["missing"],
        extraction_notes=notes,
        notes_highlights=notes_highlights,
    )
