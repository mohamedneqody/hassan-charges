# -*- coding: utf-8 -*-
"""False-acceptance root cause + adaptive routing tests (المهام 1-4، 7).

The AbuQir incident: the income-tax NOTE carried «Current income tax
1,715,662,071» twice (repeated note tables) and the majority vote let those
two echoes OUTVOTE the printed P&L «Income tax expense (3,631,829,544)» —
status VERIFIED_EXACT, false acceptance. Three general fixes, each pinned:

  1. vocabulary: tax note components/bridges/rates never map to
     income_tax_expense (the P&L total);
  2. vote independence: repeated same-(label,value) captures are ONE
     witness — echoes of one source never outvote the primary statement;
  3. correlated-source gate: when the document profiler marks the text
     layer untrusted, same-layer agreement is an echo, not an attestation.

Routing: profiler → local spatial re-read (free) → vision ONLY behind
ENABLE_VISION_FALLBACK + page budget + usable pool; otherwise BLOCKED and
the run continues locally. Historical year headers (2005/2010) are valid;
prose year enumerations never become headers.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

PROJ = Path(__file__).resolve().parents[1]

from src.extraction.file_parsers import _parse_pdf_text_lines  # noqa: E402
from src.extraction.normalizer import (  # noqa: E402
    FinancialData, build_decision_log, match_field, merge_parsed, reconcile,
)
from src.extraction.provenance import SOURCE_SCANNED_OCR  # noqa: E402


# ── 1. the incident, replayed end-to-end ───────────────────────────────────

def _abuqir_like_parts():
    """The real structure: P&L frame with the CORRECT tax, then the tax
    note's «Current income tax» row echoed by TWO note tables."""
    parts = [
        {2025: {"income_tax_expense": -2_583_771_838.0},
         2024: {"income_tax_expense": -3_631_829_544.0}},   # P&L (p6)
        {2025: {"income_tax_expense": 3_525_031_436.0},
         2024: {"income_tax_expense": 1_715_662_071.0}},    # note table A
        {2025: {"income_tax_expense": 2_131_080_131.0},
         2024: {"income_tax_expense": 1_715_662_071.0}},    # note table B
    ]
    caps = [
        [{"field": "income_tax_expense", "year": 2025, "value": -2_583_771_838.0, "label_text": "Income tax expense"},
         {"field": "income_tax_expense", "year": 2024, "value": -3_631_829_544.0, "label_text": "Income tax expense"}],
        [{"field": "income_tax_expense", "year": 2025, "value": 3_525_031_436.0, "label_text": "Current income tax"},
         {"field": "income_tax_expense", "year": 2024, "value": 1_715_662_071.0, "label_text": "Current income tax"}],
        [{"field": "income_tax_expense", "year": 2025, "value": 2_131_080_131.0, "label_text": "Current income tax"},
         {"field": "income_tax_expense", "year": 2024, "value": 1_715_662_071.0, "label_text": "Current income tax"}],
    ]
    return parts, caps


def test_note_echoes_never_outvote_the_primary_statement():
    """REGRESSION for the AbuQir tax false acceptance: two same-label echoes
    of the note component must NOT replace the P&L total."""
    parts, caps = _abuqir_like_parts()
    d = merge_parsed(parts, [], captures_per_part=caps,
                     part_layers=["text", "text", "text"])
    reconcile(d)
    # first-wins keeps the P&L value; the echoes are one witness, not two
    assert d.get("income_tax_expense", 2024) == -3_631_829_544.0
    log = {(e["field"], e["year"]): e for e in build_decision_log(d)}
    e = log[("income_tax_expense", 2024)]     # filter by year — two entries
    assert e["status"] != "VERIFIED_EXACT"
    assert any("1,715,662,071" in c for c in e["candidates"]), \
        "the dissenting echo values must stay visible in the log"


def test_note_component_labels_never_map_to_the_expense():
    """Vocabulary fix (generic IFRS): note components / OCI tax / rate rows
    are NOT the P&L income-tax expense — EN and AR."""
    for label in ("Current income tax", "Deferred income taxes",
                  "Income tax for other comprehensive income elements",
                  "Deferred tax on other comperhensive income items",
                  "Effective income tax rate",
                  "Income tax according to tax law",
                  "Income tax at income statement",
                  "Current income tax expense",
                  "ضريبة الدخل الحالية", "ضريبة الدخل المؤجلة",
                  "معدل الضريبة الفعلية"):
        assert match_field(label) != "income_tax_expense", label
    # the REAL printed lines still map (Hadid Ezz + generic IFRS)
    assert match_field("Income tax expense") == "income_tax_expense"
    assert match_field("إجمالي ضريبة الدخل عن العام") == "income_tax_expense"


def test_distinct_label_agreement_still_votes():
    """The legitimate cross-statement case is preserved: two DIFFERENT lines
    agreeing digit-exactly still outvote a disagreeing minority."""
    parts = [
        {2022: {"net_income": 1_050_737_086.0}},   # misread, first
        {2022: {"net_income": 1_056_737_086.0}},   # correct
        {2022: {"net_income": 1_056_737_086.0}},   # correct (other statement)
    ]
    caps = [
        [{"field": "net_income", "year": 2022, "value": 1_050_737_086.0,
          "label_text": "Net profit for the year"}],
        [{"field": "net_income", "year": 2022, "value": 1_056_737_086.0,
          "label_text": "Net income"}],
        [{"field": "net_income", "year": 2022, "value": 1_056_737_086.0,
          "label_text": "Profit for the year"}],
    ]
    d = merge_parsed(parts, [], captures_per_part=caps,
                     part_layers=["text", "text", "text"])
    reconcile(d)
    assert d.get("net_income", 2022) == 1_056_737_086.0   # outvoted correctly
    vo = d.vote_outcomes[("net_income", 2022)]
    assert vo["votes"] == 2            # two INDEPENDENT (label-distinct) witnesses
    assert vo["total"] == 3 and len(vo["dissent"]) == 1


# ── 2. correlated-source gate (اتفاق من المصدر المشوه نفسه) ───────────────

def _agreeing_data(profile_trusted: bool, layers: list[str]) -> FinancialData:
    d = FinancialData()
    d.extraction_source = SOURCE_SCANNED_OCR
    d.values["revenue"] = {2022: 16_600_000_000.0}
    d.candidates["revenue"] = {2022: [(16_600_000_000.0, 0),
                                      (16_600_000_000.0, 1)]}
    d.candidate_labels["revenue"] = {2022: ["Operating revenue",
                                            "Operating revenue"]}
    d.candidate_layers["revenue"] = {2022: layers}
    d.confidence["revenue"] = {2022: 2}
    if not profile_trusted:
        d.document_profile = {"text_layer_trusted": False,
                              "kind": "SEARCHABLE_SCANNED_PDF"}
    return d


def test_same_layer_agreement_on_untrusted_profile_is_not_attestation():
    d = _agreeing_data(profile_trusted=False, layers=["text", "text"])
    e = next(e for e in build_decision_log(d)
             if e["field"] == "revenue" and e["year"] == 2022)
    assert e["status"] == "UNVERIFIED"
    assert "طبقة واحدة" in e["reason"] and "صدى لمصدر واحد" in e["reason"]


def test_cross_layer_agreement_still_attests():
    d = _agreeing_data(profile_trusted=False, layers=["text", "vision"])
    e = next(e for e in build_decision_log(d)
             if e["field"] == "revenue" and e["year"] == 2022)
    assert e["status"] == "VERIFIED_EXACT"       # two DIFFERENT layers agree


def test_trusted_profile_agreement_unchanged():
    d = _agreeing_data(profile_trusted=True, layers=["text", "text"])
    e = next(e for e in build_decision_log(d)
             if e["field"] == "revenue" and e["year"] == 2022)
    assert e["status"] == "VERIFIED_EXACT"


# ── 3. document profiler (المهمة 2) ────────────────────────────────────────

def test_magnitude_pattern_and_run_splitting():
    from src.extraction.document_profiler import _MAGNITUDE_RE, _run_magnitudes

    # valid printed magnitudes
    for m in ("2 354 490 447", "42,219,047,998", "(12 470 407 550)",
              "1 250 000 000", "22 915 657 021"):
        assert _MAGNITUDE_RE.match(m), m
    # broken OCR artifacts
    for m in ("126188 707", "3511.0 467312.0", "4.41/14/1"):
        assert not _MAGNITUDE_RE.match(m), m
    # «3.0» is a well-formed decimal — the invalidity in the corrupted layer
    # is STATISTICAL (a tax of 3 pounds between billions), handled by the
    # validity ratio's >=3-significant-digit counting, not this pattern
    # two year columns = TWO magnitudes; fragments join forward
    assert _run_magnitudes(["42,219,047,998", "42,329,153,379"]) == \
        ["42,219,047,998", "42,329,153,379"]
    assert _run_magnitudes(["2", "354", "490", "447"]) == ["2 354 490 447"]
    assert _run_magnitudes(["126188", "707"]) == ["126188", "707"]


def test_profiler_classifies_native_vs_hidden_ocr():
    """Native fixture (fpdf2, comma-grouped) TRUSTED; the AbuQir hidden-OCR
    layer NOT trusted — the classification that gates the router."""
    import pdfplumber

    from src.extraction.document_profiler import profile_pdf

    with pdfplumber.open(PROJ / "eval_tmp/native_fixture.pdf") as pdf:
        native = profile_pdf(pdf)
    assert native.text_layer_trusted is True
    assert native.kind == "NATIVE_DIGITAL_PDF"
    assert native.metrics["magnitude_validity"] >= 0.9

    abuqir = json.loads((PROJ / "cell_evidence/abuqir_eval_results.json")
                        .read_text(encoding="utf-8"))
    # the recorded profile from the last full run (see routing test below)
    assert abuqir["document_profile"]["text_layer_trusted"] is False
    assert abuqir["document_profile"]["kind"] == "SEARCHABLE_SCANNED_PDF"


# ── 4. routing governance (المهمة 3) ──────────────────────────────────────

def test_vision_fallback_is_governed(tmp_path, monkeypatch):
    from src.extraction import file_parsers as FP

    notes: list[str] = []
    profile = {"per_page": [{"page": i, "chars": 100, "garbled": 0.5}
                            for i in range(1, 15)]}
    monkeypatch.delenv("ENABLE_VISION_FALLBACK", raising=False)
    assert FP._vision_fallback(b"", profile, notes) is None
    assert any("BLOCKED" in n and "flag" in n for n in notes)

    monkeypatch.setenv("ENABLE_VISION_FALLBACK", "1")
    class DeadPool:
        def has_usable_pairs(self):
            return False
    monkeypatch.setattr(FP, "_VISION_TEST_POOL", DeadPool(), raising=False)
    # pool unusable → BLOCKED (import inside the function resolves get_pool)
    import src.ai.gemini_agent as ga

    monkeypatch.setattr(ga, "get_pool", lambda: DeadPool())
    notes2: list[str] = []
    assert FP._vision_fallback(b"", profile, notes2) is None
    assert any("no usable" in n for n in notes2)


def test_abuqir_routing_end_to_end_flag_off():
    """The full adaptive route on the dev document, vision flag OFF: profile
    attached, source honestly SCANNED_OCR, nothing decisive (FAR 0), local
    re-read attempted, vision BLOCKED note present. Zero API calls."""
    from src.analysis.financial_gate import decide
    from src.extraction.file_parsers import load_financial_data
    from src.extraction.normalizer import build_decision_log

    raw = (PROJ / "independent_docs/abuqir_2023/abuqir_fs_fy2025.pdf") \
        .read_bytes()
    d = load_financial_data("abuqir_fs_fy2025.pdf", raw)
    assert d.document_profile["text_layer_trusted"] is False
    assert d.document_profile["kind"] == "SEARCHABLE_SCANNED_PDF"
    assert d.extraction_source == SOURCE_SCANNED_OCR
    notes = "\n".join(d.notes)
    assert "NOT trusted" in notes and "local spatial re-read" in notes
    assert "Vision fallback BLOCKED" in notes          # flag off → BLOCKED
    dl = build_decision_log(d)
    decisive = [e for e in dl
                if decide(e["status"]) in ("use", "use_disclosed")]
    assert decisive == []                              # nothing auto-decided
    # the incident cell: correct value captured, correctly BLOCKED
    e = next(e for e in dl if e["field"] == "income_tax_expense"
             and e["year"] == 2024)
    assert abs(e["final"] - (-3_631_829_544.0)) <= 1.0
    assert decide(e["status"]) == "not_decisive"


# ── 5. year headers: historical documents valid, prose never (المهمة 4) ───

def test_historical_year_headers_are_supported():
    """A 2005 statement MUST work — no absolute year floor."""
    frames = _parse_pdf_text_lines([
        "31 December 2005 31 December 2004",
        "Total assets 1 250 000 000 1 100 000 000",
        "Net profit 120 000 000 90 000 000",
    ])
    years = {c for c in frames[0].columns if c != "Line Item"}
    assert years == {2005, 2004}


def test_prose_year_enumerations_never_become_headers():
    frames = _parse_pdf_text_lines([
        "b- For the period from July 2005 to December 2009, disputes.",
        "by Law No. 196 of 2008 and amended by Law No. 117 of 2014.",
        "30 June 2025 30 June 2024",
        "Net profit 9 352 763 248 13 476 733 123",
    ])
    assert len(frames) == 1
    years = {c for c in frames[0].columns if c != "Line Item"}
    assert years == {2025, 2024}
    assert not (years & {2005, 2008, 2009, 2014})


def test_balance_sheet_three_columns_income_statement_two():
    """Per-table column counts stay independent (المهمة 4 — no forced
    uniform column count)."""
    frames = _parse_pdf_text_lines([
        "30 June 2025 30 June 2024 30 June 2023",
        "Total assets 42 219 047 998 42 329 153 379 34 715 086 686",
        "30 June 2025 30 June 2024",
        "Net profit 9 352 763 248 13 476 733 123",
    ])
    assert len(frames) == 2
    assert {c for c in frames[0].columns if c != "Line Item"} == \
        {2025, 2024, 2023}
    assert {c for c in frames[1].columns if c != "Line Item"} == {2025, 2024}
