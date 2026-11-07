# -*- coding: utf-8 -*-
"""Gemini analysis audit (المهمة 4) + report consistency (المهمة 5).

Gemini side: the recommendation/comment auditors drop any number Python
never computed; the payload DISCLOSES missing/blocked data; years are
pinned. Report side: Excel, HTML and the PDF-source HTML agree on the
headline numbers and the preliminary/verified labeling."""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ))

from src.ai.gemini_agent import (  # noqa: E402
    AIAnalysis, _audit_comments, _audit_recommendations, _float_tokens,
    _global_allowed_numbers, build_payload,
)
from src.pipeline import build_gemini_payload  # noqa: E402


def _payload() -> dict:
    """A small payload mirroring the TE shape (values Python computed)."""
    return build_payload(
        company="TE",
        prev_year=2023,
        curr_year=2024,
        metrics=[
            {"key": "revenue", "metric": "Revenue", "name": "Revenue",
             "previous": 21_899_104.0, "current": 27_727_014.0,
             "value": 27_727_014.0, "change_pct": 26.6},
            {"key": "current_ratio", "metric": "Current Ratio",
             "name": "Current Ratio",
             "previous": 0.57, "current": 0.43, "value": 0.43,
             "change_pct": -24.0},
        ],
        missing_data=["current_assets (blocked: conflicting reads)",
                      "operating_cash_flow (blocked: single read)"],
        extraction_notes=["Human review pending on 2 cells."],
        notes_highlights="",
    )


def test_hallucinated_recommendation_number_is_dropped():
    payload = _payload()
    analysis = AIAnalysis(ok=True, ratio_comments=[], recommendations=[
        ("Consider the strong 26.6% revenue growth", "Revenue +26.6%"),
        ("The company will reach 7,777,777 EGP cash next year",
         "Projection 7,777,777"),
    ])
    audited = _audit_recommendations(analysis, payload)
    assert len(audited.recommendations) == 1
    assert "26.6" in audited.recommendations[0][0]


def test_provided_number_recommendation_survives():
    payload = _payload()
    analysis = AIAnalysis(ok=True, ratio_comments=[], recommendations=[
        ("Liquidity is below the 1.0 guideline", "Current Ratio 0.43"),
    ])
    audited = _audit_recommendations(analysis, payload)
    assert len(audited.recommendations) == 1


def test_hallucinated_comment_number_is_flagged_as_suspect():
    """The comment auditor FLAGS any comment quoting a number Python never
    provided — _repair_comments then re-asks Gemini for exactly those
    metrics (the drop happens there; the gate is this detection)."""
    payload = _payload()
    analysis = AIAnalysis(ok=True,
                          ratio_comments=[("Revenue", "grew 26.6% to 27.7M"),
                                          ("Cash", "jumped 77,777%")],
                          recommendations=[])
    missing, suspects = _audit_comments(analysis, payload)
    assert ("Cash", "jumped 77,777%") in suspects
    assert not any(s[0] == "Revenue" for s in suspects)
    # the repair pass targets missing ∪ suspects — Cash enters via suspects
    assert "Current Ratio" in missing               # the skipped real metric


def test_payload_discloses_blocked_data():
    """missing_data travels INTO the prompt — Gemini can never claim the
    blocked cells are confirmed values (they are named as blocked)."""
    payload = _payload()
    assert "current_assets" in json_or_str(payload["missing_data"])
    assert "blocked" in json_or_str(payload["missing_data"])


def json_or_str(v):
    import json

    return json.dumps(v, ensure_ascii=False)


def test_years_are_pinned_in_the_payload():
    payload = _payload()
    assert payload["analysis_period"]["previous_year"] == 2023
    assert payload["analysis_period"]["current_year"] == 2024


# ── Report consistency (المهمة 5) ──────────────────────────────────────────

def test_excel_html_report_consistency_on_headline_numbers():
    """Excel and HTML generated from the SAME results must agree on the
    company, period, health score and the human-review trail."""
    from src.analysis import calculator as C
    from src.analysis.comparison import build_comparison
    from src.analysis.financial_gate import (
        pending_critical_review, report_is_preliminary,
    )
    from src.analysis.score import compute_health_score
    from src.dashboard.excel_report import build_excel_report
    from src.dashboard.report import build_html_report
    from src.extraction.normalizer import FinancialData, reconcile
    from openpyxl import load_workbook

    d = FinancialData()
    d.values.update({
        "revenue": {2023: 21_899_104.0, 2024: 27_727_014.0},
        "net_income": {2023: 426_886.0, 2024: 4_416_350.0},
        "total_assets": {2023: 19_041_842.0, 2024: 25_284_931.0},
        "total_liabilities": {2023: 7_835_622.0, 2024: 14_541_406.0},
        "equity": {2023: 11_206_220.0, 2024: 10_743_525.0},
        "current_assets": {2023: 10_929_877.0, 2024: 15_164_132.0},
        "current_liabilities": {2023: 7_040_571.0, 2024: 12_670_105.0},
        "operating_cash_flow": {2024: 11_329_526.0},
    })
    for f in d.values:
        d.candidates[f] = {y: [(v, 0), (v, 1)]
                           for y, v in d.values[f].items()}
        d.confidence[f] = {y: 2 for y in d.values[f]}
    reconcile(d)
    prev = C.compute_year_metrics(2023, d.values)
    curr = C.compute_year_metrics(2024, d.values, prev_year=2023)
    dv_pending = pending_critical_review(
        [e for e in __import__("src.extraction.normalizer",
                               fromlist=["build_decision_log"])
         .build_decision_log(d)])
    hs = compute_health_score(curr, blocked_fields=set())
    results = {"company": "TE (consistency test)",
               "file_name": "te.pdf", "prev_year": 2023, "curr_year": 2024,
               "prev_metrics": prev, "curr_metrics": curr,
               "rows": build_comparison(prev, curr), "growth_rows": [],
               "notes": d.notes, "missing": [], "currency_hint": "ج.م",
               "pending_critical_review": dv_pending}
    wb = load_workbook(io.BytesIO(build_excel_report(results)))
    flat = {r[0].value: r[1].value for r in wb["ملخص"].iter_rows(min_row=2)
            if r[0].value}
    assert flat["الدرجة الصحية (0-100)"] == pytest.approx(hs.total, abs=0.11)
    html = build_html_report(results, AIAnalysis(ok=False), hs, currency="ج.م")
    assert "TE (consistency test)" in html
    assert str(hs.total) in html or f"{hs.total:.0f}" in html
    # the preliminary/final flag is driven by the SAME pending list
    assert ("preliminary" in html.lower() or "أولي" in html) == bool(
        dv_pending)


def test_pdf_export_path_exists_and_agrees():
    """The PDF pipeline (export_analysis_pdf) renders the SAME numbers —
    verified on the HTML it consumes (the PDF is the HTML print)."""
    from src.dashboard.report import build_html_report
    from src.ai.gemini_agent import AIAnalysis
    from src.analysis.score import compute_health_score
    from src.analysis import calculator as C

    hs = compute_health_score(C.compute_year_metrics(2024, {
        "revenue": {2024: 100.0}, "net_income": {2024: 10.0},
        "total_assets": {2024: 1_000.0}, "equity": {2024: 500.0},
        "current_assets": {2024: 200.0},
        "current_liabilities": {2024: 100.0}}))
    html = build_html_report(
        {"company": "X", "prev_year": 2023, "curr_year": 2024, "rows": [],
         "missing": [], "notes": [], "pending_critical_review": []},
        AIAnalysis(ok=False), hs, currency="$")
    assert str(hs.total) in html or f"{hs.total:.0f}" in html
