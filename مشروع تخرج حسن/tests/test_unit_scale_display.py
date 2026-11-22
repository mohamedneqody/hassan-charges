# -*- coding: utf-8 -*-
"""سلسلة وحدة الطباعة (المهمة 1 من جولة إصلاح المراجعة): the printed-unit
chain — header detection, scale-aware display, Arabic magnitude words —
so a value printed in EGP Thousands can never display as "27.73M" when it
is really 27.73 billion. Stored values stay PRINTED; only display scales."""
from __future__ import annotations

import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ))

from src.analysis.comparison import CURRENCY, PERCENT  # noqa: E402
from src.dashboard.charts import (  # noqa: E402
    fmt_signed_ar, fmt_value, fmt_value_ar, humanize,
)
from src.extraction.file_parsers import (  # noqa: E402
    _UNIT_HEADER_RULES, detect_printed_unit,
)


# ── humanize: legacy behavior unchanged at scale=1 ──────────────────────
def test_humanize_legacy_unchanged():
    assert humanize(1180000) == "1.18M"
    assert humanize(27730150) == "27.73M"          # the OLD misleading form
    assert humanize(999) == "999"
    assert humanize(-1200) == "-1.2K"


# ── humanize + scale: printed thousands -> actual currency ──────────────
def test_humanize_scale_thousands_to_billions():
    # TE revenue 2024: printed 27,730,150 (thousands) = 27.73B actual
    assert humanize(27730150, scale=1000) == "27.73B"
    assert humanize(8670000, scale=1000) == "8.67B"
    # a small printed value: 450 thousand = 450K actual
    assert humanize(450, scale=1000) == "450K"
    # sub-million actual stays readable
    assert humanize(120, scale=1000) == "120K"


def test_humanize_scale_negative_and_millions_unit():
    assert humanize(-1272749, scale=1000) == "-1.27B"
    # a statement printed "in EGP millions": 150 printed = 150M actual
    assert humanize(150, scale=1_000_000) == "150M"


# ── Arabic magnitude words: one display language everywhere ────────────
def test_fmt_value_ar_maps_magnitudes():
    assert fmt_value_ar(27730150, CURRENCY, "ج.م", 1000) == "ج.م27.73 مليار"
    assert fmt_value_ar(2773015, CURRENCY, "ج.م", 1000) == "ج.م2.77 مليار"
    assert fmt_value_ar(450000, CURRENCY, "ج.م", 1000) == "ج.م450 مليون"
    assert fmt_value_ar(450, CURRENCY, "ج.م", 1000) == "ج.م450 ألف"


def test_fmt_signed_ar_keeps_sign():
    assert fmt_signed_ar(-1272749, CURRENCY, "ج.م", 1000) == "-ج.م1.27 مليار"
    assert fmt_signed_ar(1272749, CURRENCY, "ج.م", 1000) == "+ج.م1.27 مليار"


def test_fmt_value_ar_passes_noncurrency_through():
    assert fmt_value_ar(15.9, PERCENT, "ج.م", 1000) == "15.9%"
    assert fmt_value_ar(None, CURRENCY, "ج.م", 1000) == "N/A"


def test_fmt_value_legacy_ignores_scale():
    # fmt_value (non-Arabic) keeps its signature for charts/legacy callers
    assert fmt_value(27730150, CURRENCY, "$") == "$27.73M"


# ── detection: the printed header is the ONLY proof of the unit ────────
def test_detect_printed_unit_headers():
    assert detect_printed_unit(
        ["All values are in EGP Thousands unless otherwise stated"])[0] == 1000
    assert detect_printed_unit(["(EGP' 000)"])[0] == 1000
    assert detect_printed_unit(["EGP 000"])[0] == 1000
    assert detect_printed_unit(["amounts in L.E. 000"])[0] == 1000
    assert detect_printed_unit(
        ["القوائم المالية مقدمة بآلاف الجنيهات المصرية"])[0] == 1000
    assert detect_printed_unit(["in EGP millions"])[0] == 1_000_000
    assert detect_printed_unit(["بملايين الجنيهات"])[0] == 1_000_000


def test_detect_printed_unit_absent_means_one():
    assert detect_printed_unit(["no unit header here"]) == (1, "")
    assert detect_printed_unit(["December 2024 total 1,234"]) == (1, "")
    assert detect_printed_unit([]) == (1, "")


def test_unit_rules_carry_evidence_notes():
    # every rule must name its evidence — the verification log quotes it
    for pattern, scale, note in _UNIT_HEADER_RULES:
        assert scale in (1000, 1_000_000)
        assert note.strip()


# ── FinancialData carries the unit without touching stored values ──────
def test_financial_data_unit_defaults():
    from src.extraction.normalizer import FinancialData

    d = FinancialData()
    assert d.unit_scale == 1 and d.unit_note == ""
    d.unit_scale = 1000
    d.values.setdefault("revenue", {})[2024] = 27730150.0
    assert d.values["revenue"][2024] == 27730150.0   # stored PRINTED


# ── report + excel honor the scale end-to-end ──────────────────────────
def _results_with_scale(scale: int) -> dict:
    from src.analysis import calculator as C
    from src.analysis.comparison import build_comparison
    from src.analysis.score import compute_health_score

    values = {
        "revenue": {2023: 21900000000 / 1000, 2024: 27730150000 / 1000},
        "net_income": {2023: 5720000000 / 1000, 2024: 4420000000 / 1000},
        "total_assets": {2023: 40000000000 / 1000, 2024: 42000000000 / 1000},
        "total_liabilities": {2023: 30000000000 / 1000,
                              2024: 31000000000 / 1000},
        "total_equity": {2023: 10000000000 / 1000, 2024: 11000000000 / 1000},
    }
    prev = C.compute_year_metrics(2023, values)
    curr = C.compute_year_metrics(2024, values, prev_year=2023)
    rows = build_comparison(prev, curr)
    return {"company": "T", "file_name": "t.pdf", "prev_year": 2023,
            "curr_year": 2024, "prev_metrics": prev, "curr_metrics": curr,
            "rows": rows, "growth_rows": [], "notes": [], "missing": [],
            "currency_hint": "ج.م", "unit_scale": scale,
            "unit_note": "جميع القيم بآلاف الجنيهات",
            "verification_status": {}}


def test_report_html_shows_billions_not_m():
    from src.ai.gemini_agent import AIAnalysis
    from src.analysis.score import compute_health_score
    from src.dashboard.report import build_html_report

    res = _results_with_scale(1000)
    html = build_html_report(res, AIAnalysis(ok=False),
                             compute_health_score(res["curr_metrics"]),
                             currency="ج.م")
    # print cells join number+word with NBSP (LibreOffice can't split it)
    assert "27.73\u00a0مليار" in html     # the unified correct display
    assert "27.73M" not in html           # the misleading form is gone
    assert "وحدة القوائم: جميع القيم بآلاف الجنيهات" in html


def test_report_html_without_scale_uses_arabic_words():
    from src.ai.gemini_agent import AIAnalysis
    from src.analysis.score import compute_health_score
    from src.dashboard.report import build_html_report

    res = _results_with_scale(1)
    html = build_html_report(res, AIAnalysis(ok=False),
                             compute_health_score(res["curr_metrics"]),
                             currency="ج.م")
    # the Arabic report NEVER shows a bare "M" — at scale 1 the value IS
    # 27.73 million units and the Arabic word says so explicitly (NBSP-joined)
    assert "27.73\u00a0مليون" in html
    assert "27.73M" not in html


def test_excel_currency_cells_carry_actual_amounts():
    import io

    from openpyxl import load_workbook

    from src.dashboard.excel_report import build_excel_report

    res = _results_with_scale(1000)
    wb = load_workbook(io.BytesIO(build_excel_report(res)))
    ws = wb["المؤشرات"]
    header = [c.value for c in ws[1]]
    assert header[-1] == "حالة التحقق"    # the 9th column (المهمة 3)
    assert len(header) == 9
    # find the revenue row: current-year cell must be the ACTUAL 27.73B
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[0] and "الإيرادات" in str(row[0]):
            assert row[3] == 27_730_150_000  # printed × 1000, as a NUMBER
            break
    else:
        raise AssertionError("revenue row not found in the metrics sheet")


def test_gemini_payload_quotes_actual_units():
    from src.pipeline import build_gemini_payload

    res = _results_with_scale(1000)
    payload = build_gemini_payload(res, currency="ج.م")
    rev = next(m for m in payload["metrics"] if m.get("metric")
               and "الإيرادات" in str(m["metric"]))
    assert "27.73 مليار" in rev["current"]
    assert "M" not in rev["current"]
