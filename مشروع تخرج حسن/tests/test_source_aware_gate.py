# -*- coding: utf-8 -*-
"""Source-Aware Quality Gate tests (بوابة إسناد المصدر — المهمة 1).

The old gate treated a directly-read Excel cell like an uncorroborated OCR
read: Exact 54/54 yet Decisive 0/54. VERIFIED_SOURCE_EXACT now documents a
faithful TRANSFER from a digital source — granted ONLY on the full evidence
checklist, never for a correct number on the wrong row, the wrong year, a
merged cell, a scaled unit, a flipped sign, or a non-amount type. And the
grant is a transfer proof, never an economic-correctness claim.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

PROJ = Path(__file__).resolve().parents[1]

from src.extraction.normalizer import extract_year  # noqa: E402
from src.extraction.provenance import (  # noqa: E402
    SOURCE_NATIVE_SPREADSHEET_CELL, SOURCE_SCANNED_OCR, CellEvidence,
    evaluate_source_evidence, file_sha256, sniff_consolidation,
    sniff_scale_words,
)

SAMPLE = PROJ / "sample_data/sample_financials.xlsx"


def _good_ev(**over) -> CellEvidence:
    base = dict(
        source=SOURCE_NATIVE_SPREADSHEET_CELL,
        file_sha256="a" * 64, file_name="stmt.xlsx",
        sheet="Balance Sheet", cell_address="C5",
        label_text="Total Liabilities", year=2026, data_type="value",
    )
    base.update(over)
    return CellEvidence(**base)


# ── the checklist ───────────────────────────────────────────────────────────

def test_full_evidence_is_eligible():
    ok, fails = evaluate_source_evidence(_good_ev(), expected_year=2026)
    assert ok and fails == []


def test_missing_hash_sheet_address_label_year_blocks():
    for removed in ("file_sha256", "sheet", "cell_address", "label_text",
                    "year"):
        ev = _good_ev()
        setattr(ev, removed, None)
        ok, fails = evaluate_source_evidence(ev, expected_year=2026)
        assert not ok and fails, removed


def test_year_mismatch_blocks():
    ok, fails = evaluate_source_evidence(_good_ev(year=2021), expected_year=2026)
    assert not ok and any("لا تطابق" in f for f in fails)


def test_merged_cell_blocks():
    ok, fails = evaluate_source_evidence(_good_ev(is_merged=True),
                                         expected_year=2026)
    assert not ok and any("مدمجة" in f for f in fails)


def test_text_and_percent_types_block():
    for t in ("text", "percent"):
        ok, fails = evaluate_source_evidence(_good_ev(data_type=t),
                                             expected_year=2026)
        assert not ok and any("نوع البيانات" in f for f in fails)


def test_scaled_unit_blocks():
    ok, fails = evaluate_source_evidence(_good_ev(unit_hint="مليون"),
                                         expected_year=2026)
    assert not ok and any("وحدة القياس" in f for f in fails)


def test_flipped_negative_sign_blocks():
    ok, fails = evaluate_source_evidence(_good_ev(sign_normalized=True),
                                         expected_year=2026)
    assert not ok and any("الإشارة السالبة" in f for f in fails)


def test_cached_formula_is_eligible_WITH_disclosure():
    ev = _good_ev(data_type="formula_cached", cached_formula=True)
    ok, fails = evaluate_source_evidence(ev, expected_year=2026)
    assert ok and fails == []
    from src.extraction.provenance import evidence_reason
    assert "cached" in evidence_reason(ev)      # staleness disclosed


def test_non_digital_source_never_eligible():
    ok, fails = evaluate_source_evidence(_good_ev(source=SOURCE_SCANNED_OCR),
                                         expected_year=2026)
    assert not ok and any("رقميًا" in f for f in fails)


# ── label/field consistency: a correct number on the WRONG row ─────────────

def test_wrong_field_label_is_never_promoted():
    """Evidence says «Total Assets» but the capture landed under revenue —
    the decision log must NOT grant source-exact (numerically-right /
    semantically-wrong)."""
    from src.extraction.normalizer import FinancialData, _source_exact

    d = FinancialData()
    d.extraction_source = SOURCE_NATIVE_SPREADSHEET_CELL
    d.values["revenue"] = {2026: 1_650_000.0}
    d.candidates["revenue"] = {2026: [(1_650_000.0, 0)]}
    d.cell_provenance[("revenue", 2026)] = _good_ev(
        label_text="Total Assets", year=2026).as_dict()
    ok, ev, fails = _source_exact(d, "revenue", 2026)
    assert not ok and any("الصف الخطأ" in f for f in fails)


def test_matching_label_maps_through():
    from src.extraction.normalizer import FinancialData, _source_exact

    d = FinancialData()
    d.values["total_liabilities"] = {2026: 850_000.0}
    d.candidates["total_liabilities"] = {2026: [(850_000.0, 0)]}
    d.cell_provenance[("total_liabilities", 2026)] = _good_ev().as_dict()
    ok, _ev, fails = _source_exact(d, "total_liabilities", 2026)
    assert ok and fails == []


# ── end-to-end: the digital workbook becomes decisive, honestly ────────────

def test_excel_end_to_end_source_exact():
    from src.analysis.financial_gate import decisive_values
    from src.extraction.file_parsers import load_financial_data
    from src.extraction.normalizer import build_decision_log

    raw = SAMPLE.read_bytes()
    d = load_financial_data(SAMPLE.name, raw)
    assert d.extraction_source == "NATIVE_SPREADSHEET_CELL"
    assert len(d.cell_provenance) == 54
    dl = build_decision_log(d)
    statuses = {e["status"] for e in dl}
    assert "VERIFIED_SOURCE_EXACT" in statuses
    assert all(e["source"] == "NATIVE_SPREADSHEET_CELL" for e in dl)
    ev = d.cell_provenance[("net_income", 2026)]
    assert ev["file_sha256"] == file_sha256(raw)
    assert ev["sheet"] == "Income Statement"
    assert ev["cell_address"] and ev["label_text"] == "Net Income"
    dv = decisive_values(d)
    assert all(v["usable_decisive"] for v in dv.values())
    assert len(dv) == 54


def test_decision_log_reason_disclaims_economic_truth():
    from src.extraction.file_parsers import load_financial_data
    from src.extraction.normalizer import build_decision_log

    d = load_financial_data(SAMPLE.name, SAMPLE.read_bytes())
    e = next(e for e in build_decision_log(d)
             if e["field"] == "total_liabilities" and e["year"] == 2026)
    assert "ليس إثبات صحة القيمة اقتصاديًا" in e["reason"]
    assert "بصمة الملف" in e["reason"] and "خلية" in e["reason"]


def test_consolidation_and_scale_sniffers():
    assert sniff_consolidation("القوائم المالية المستقلة 2022") == "standalone"
    assert sniff_consolidation("Consolidated financial statements") == "consolidated"
    assert sniff_consolidation("Anything else") is None
    assert sniff_scale_words("الأرقام بالآلاف من الجنيه") == "آلاف"
    assert sniff_scale_words("in millions of EGP") == "million"
    assert sniff_scale_words("plain numbers") is None


# ── metrics: critical-field coverage + no loosening for scans ──────────────

def test_critical_field_coverage_metric():
    from src.extraction.human_review import separated_metrics

    rows = [
        {"field": "revenue", "final_status": "VERIFIED_SOURCE_EXACT",
         "exact_value": True},
        {"field": "net_income", "final_status": "CONFLICT",
         "exact_value": True},
        {"field": "total_liabilities", "final_status": "VERIFIED_HUMAN",
         "exact_value": True},
        {"field": "inventory", "final_status": "VERIFIED_SOURCE_EXACT",
         "exact_value": True},          # NOT critical — ignored
    ]
    sep = separated_metrics(rows, human_log=PROJ / "cell_evidence/none.json",
                            log_integrity=(False, "NO_KEY"))
    # critical allowed: revenue (source-exact) + total_liabilities (human,
    # but the chain is broken → NOT trusted → still counts by STATUS here;
    # human trust is a separate metric)
    assert sep["critical_field_coverage"] == round(2 / 3, 3)
    assert sep["human_assisted_verified_coverage"] == 0.0  # untrusted chain


def test_scanned_pdf_gate_not_loosened():
    """The scanned document's per-cell statuses produce the SAME gate
    partition as before — source-awareness never loosened the OCR path."""
    from src.extraction.human_review import separated_metrics

    rows = json.loads((PROJ / "cell_evidence/per_cell_strict.json")
                      .read_text(encoding="utf-8"))
    sep = separated_metrics(rows, human_log=PROJ / "cell_evidence/none.json",
                            log_integrity=(False, "NO_KEY"))
    assert sep["gate_partition"] == {"usable": 0, "not_decisive": 10,
                                     "missing": 1}
    assert sep["automatic_decisive_coverage"] == 0.0
    # critical fields for the scanned doc: all blocked
    assert sep["critical_field_coverage"] == 0.0


# ── generic pdf text-layer parsing rules (real-document regressions) ───────

def test_pdf_text_lines_ragged_tables_never_crash():
    """A statement of financial position with THREE year columns followed by
    a P&L with TWO used to crash the whole extraction (pandas column-count
    error) — different year sets now become separate frames."""
    from src.extraction.file_parsers import _parse_pdf_text_lines

    lines = [
        "Total assets 42 219 047 998 42 329 153 379 34 715 086 686",
        "30 June 2025 30 June 2024 30 June 2023",
        "Total assets 42 219 047 998 42 329 153 379 34 715 086 686",
        "Operating revenue 22 915 657 021 18 527 811 974",
        "30 June 2025 30 June 2024",
        "Net profit for the year 9 352 763 248 13 476 733 123",
    ]
    frames = _parse_pdf_text_lines(lines)      # must not raise
    assert len(frames) >= 1
    assert all(len(set(len(r) for r in f.itertuples(index=False))) == 1
               for f in frames)                # no ragged frame


def test_pdf_text_lines_note_references_are_not_values():
    """IFRS rows lead with the note number — «Operating revenue (32) 22 915
    657 021 …»: the parenthesized (32) is a REFERENCE, not a negative value.
    Before the fix it hijacked the first year column."""
    from src.extraction.file_parsers import _parse_pdf_text_lines

    frames = _parse_pdf_text_lines([
        "30 June 2025 30 June 2024",
        "Operating revenue (32) 22 915 657 021 18 527 811 974",
        "Income tax expense (42) (2 583 771 838) (3 631 829 544)",
    ])
    df = frames[0]
    rev = df[df["Line Item"].str.contains("Operating revenue", na=False)]
    assert int(rev[2025].iloc[0]) == 22_915_657_021      # not -32
    tax = df[df["Line Item"].str.contains("Income tax", na=False)]
    assert int(tax[2025].iloc[0]) == -2_583_771_838      # real negative kept


def test_pdf_text_lines_prose_years_never_become_headers():
    """Tax-dispute prose («July 2005 to December 2009», «Law No. 196 of 2008
    … 117 of 2014») spans distant years — a comparison header holds RECENT
    adjacent fiscal years."""
    from src.extraction.file_parsers import _parse_pdf_text_lines

    frames = _parse_pdf_text_lines([
        "b- For the period from July 2005 to December 2009, disputes.",
        "by Law No. 196 of 2008 and amended by Law No. 117 of 2014.",
        "30 June 2025 30 June 2024",
        "Net profit for the year 9 352 763 248 13 476 733 123",
    ])
    df = frames[0]
    years = {c for c in df.columns if extract_year(c) is not None}
    assert years == {2025, 2024}
    assert 2005 not in years and 2008 not in years and 2014 not in years
