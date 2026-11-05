# -*- coding: utf-8 -*-
"""Focused OCR accuracy + independent evidence recovery tests (المهام 1، 3، 4، 5).

The TE holdout's single decisive cell (net_income 2023 VERIFIED_EXACT) had
passed through an UNSAFE exception: the vision path left document_profile
empty, so the correlated-source gate defaulted to trusted and two reads by
the SAME model of the SAME scan attested each other. These tests pin the
fixes AND the real-geometry focused pass:

  1. same-model agreement on a pure scan is an echo (downgrades);
  2. attestation needs >=2 distinct layers behind the WINNING value;
  3. the focused pass works on SEGMENT boxes (real Indra geometry): year
     header segments fix the columns, label segments define the row, number
     segments chain and join the nearest column — candidates only, with
     bbox/page/scale provenance;
  4. PNG-encoding regression: raw pixel bytes (the bug that made Indra look
     blind) are never passed as "png";
  5. the AbuQir false-acceptance replay still passes (no regression).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ))

from src.extraction.normalizer import (  # noqa: E402
    FinancialData, build_decision_log, reconcile,
)
from src.extraction.provenance import SOURCE_SCANNED_OCR  # noqa: E402


def _scan_data(layers: list[str], values: list[float],
               profile: dict | None) -> FinancialData:
    d = FinancialData()
    d.extraction_source = SOURCE_SCANNED_OCR
    d.values["net_income"] = {2023: values[0]}
    d.candidates["net_income"] = {2023: [(v, i) for i, v in
                                         enumerate(values)]}
    d.candidate_labels["net_income"] = {2023: [""] * len(values)}
    d.candidate_layers["net_income"] = {2023: layers}
    d.confidence["net_income"] = {2023: 2}
    if profile is not None:
        d.document_profile = profile
    return d


SCAN_PROFILE = {"kind": "SCANNED_NO_TEXT", "text_layer_trusted": False}


def test_vision_same_model_agreement_on_pure_scan_is_an_echo():
    """THE audited cell (net_income 2023 = 5,724,683 VERIFIED_EXACT): two
    reads by the same vision model of the same scan must NOT attest each
    other once the scan profile is attached — the cell downgrades to
    UNVERIFIED honestly."""
    d = _scan_data(["vision", "vision"], [5_724_683.0, 5_724_683.0],
                   SCAN_PROFILE)
    e = next(e for e in build_decision_log(d)
             if e["field"] == "net_income" and e["year"] == 2023)
    assert e["status"] == "UNVERIFIED"
    assert "طبقة واحدة" in e["reason"]


def test_cross_layer_agreement_attests_the_winning_value():
    d = _scan_data(["vision", "vision", "local_ocr"],
                   [5_724_683.0, 5_724_683.0, 5_724_683.0], SCAN_PROFILE)
    e = next(e for e in build_decision_log(d)
             if e["field"] == "net_income" and e["year"] == 2023)
    assert e["status"] == "VERIFIED_EXACT"      # two DISTINCT layers agree


def test_local_dissent_strips_same_layer_attestation():
    d = _scan_data(["vision", "vision", "local_ocr"],
                   [5_724_683.0, 5_724_683.0, 5_724_683_001.0], SCAN_PROFILE)
    e = next(e for e in build_decision_log(d)
             if e["field"] == "net_income" and e["year"] == 2023)
    assert e["status"] == "UNVERIFIED"


def test_winner_layers_recorded_in_vote_outcomes():
    d = _scan_data(["vision", "vision"], [5_724_683.0, 5_724_683.0],
                   SCAN_PROFILE)
    reconcile(d)
    vo = d.vote_outcomes[("net_income", 2023)]
    assert vo["winner_layers"] == ["vision"]    # the audit trail shows WHY


# ── focused local verification pass (segment geometry, المهمة 3) ───────────

from src.extraction.spatial_cells import LineBox  # noqa: E402


def _te_page5_segments() -> list[LineBox]:
    """Real-shaped Indra SEGMENT boxes (one box per printed run)."""
    return [
        LineBox(837, 322, 903, 331, "30/6/2024", 1.0),      # col 2024 cx≈870
        LineBox(1010, 322, 1090, 331, "31/12/2023", 1.0),   # col 2023 cx≈1050
        LineBox(95, 769, 178, 778, "Total Assets", 0.97),
        LineBox(580, 769, 745, 778, "169 497 056", 0.95),   # cx≈662 → 2024
        LineBox(920, 769, 1090, 778, "134 358 541", 0.95),  # cx≈1005 → 2023
        LineBox(95, 838, 200, 847, "Cash and cash equivalents", 0.97),
        LineBox(580, 838, 700, 847, "6 000 305", 0.95),     # cx≈640 → 2024
        LineBox(920, 838, 1040, 847, "10 272 954", 0.95),   # cx≈980 → 2023
    ]


def _mk_data_wrong_row() -> FinancialData:
    d = FinancialData()
    d.values["total_assets"] = {2024: 20_327_981.0,      # the wrong-row capture
                                2023: 14_964_829.0}      # 2023 also gated
    d.candidates["total_assets"] = {2024: [(20_327_981.0, 0)],
                                    2023: [(14_964_829.0, 0)]}
    d.candidate_labels["total_assets"] = {2024: ["Total Assets"],
                                          2023: ["Total Assets"]}
    d.candidate_layers["total_assets"] = {2024: ["vision"], 2023: ["vision"]}
    d.field_sources = {"total_assets": [5]}
    d.document_profile = dict(SCAN_PROFILE)
    return d


def _mk_data_correct_gated() -> FinancialData:
    d = FinancialData()
    d.values["cash"] = {2024: 6_000_305.0}
    d.candidates["cash"] = {2024: [(6_000_305.0, 0), (6_000_305.0, 1)]}
    d.candidate_labels["cash"] = {2024: ["Cash and cash equivalents"] * 2}
    d.candidate_layers["cash"] = {2024: ["vision", "vision"]}
    d.confidence["cash"] = {2024: 2}
    d.field_sources = {"cash": [5]}
    d.document_profile = dict(SCAN_PROFILE)
    return d


def test_focused_pass_segments_append_bbox_provenance():
    """The pass reads SEGMENT boxes: the wrong-row capture gains the true
    row's values as local_ocr candidates WITH bbox/page/scale provenance,
    while the stored value is never silently replaced."""
    import src.extraction.vision_ocr as VO

    d = _mk_data_wrong_row()
    notes: list[str] = []
    VO._focused_local_cell_verification(
        d, b"", d.field_sources, {"years": [2024, 2023]},
        [5], [b"png"], notes,
        line_reader=lambda png: (1240, 1754, _te_page5_segments()))
    cands = d.candidates["total_assets"][2024]
    layers = d.candidate_layers["total_assets"][2024]
    assert "local_ocr" in layers
    assert any(abs(v - 169_497_056.0) <= 1.0 for v, _o in cands)
    bbox = d.candidate_bbox["total_assets"][2024][-1]
    assert bbox["page"] == 5 and bbox["render_scale"] == 2.0
    assert bbox["bbox_px"] == [580, 769, 745, 778]     # the VALUE segment box
    assert d.values["total_assets"][2024] == 20_327_981.0   # value UNTOUCHED


def test_focused_pass_promotes_cross_layer_agreement():
    import src.extraction.vision_ocr as VO

    d = _mk_data_correct_gated()
    VO._focused_local_cell_verification(
        d, b"", d.field_sources, {"years": [2024, 2023]},
        [5], [b"png"], [],
        line_reader=lambda png: (1240, 1754, _te_page5_segments()))
    e = next(e for e in build_decision_log(d)
             if e["field"] == "cash" and e["year"] == 2024)
    assert e["status"] == "VERIFIED_EXACT"      # vision + local_ocr agree
    assert "طبقة واحدة" not in e["reason"]


def test_focused_pass_year_columns_from_header_segments():
    """Column assignment comes from the year-HEADER segment centers: the
    2024 column value AND the 2023 column value both land, each under its
    own year."""
    import src.extraction.vision_ocr as VO

    d = _mk_data_wrong_row()
    VO._focused_local_cell_verification(
        d, b"", d.field_sources, {"years": [2024, 2023]},
        [5], [b"png"], [],
        line_reader=lambda png: (1240, 1754, _te_page5_segments()))
    cands_2023 = d.candidates.get("total_assets", {}).get(2023, [])
    assert any(abs(v - 134_358_541.0) <= 1.0 for v, _o in cands_2023)


def test_focused_pass_disabled_by_flag(monkeypatch):
    import src.extraction.vision_ocr as VO

    d = _mk_data_correct_gated()
    monkeypatch.setenv("FOCUSED_LOCAL_VERIFY", "0")
    before = len(d.candidates["cash"][2024])
    VO._focused_local_cell_verification(
        d, b"", d.field_sources, {"years": [2024, 2023]},
        [5], [b"png"], [], line_reader=lambda png: (1, 1, []))
    assert len(d.candidates["cash"][2024]) == before


def test_vision_data_carries_scan_profile_and_vision_layer():
    import inspect

    import src.extraction.vision_ocr as VO

    src_txt = inspect.getsource(VO.extract_via_vision)
    assert 'part_layers=["vision"]' in src_txt
    assert "text_layer_trusted" in src_txt and "KIND_SCANNED_NO_TEXT" in src_txt
    assert "_focused_local_cell_verification" in src_txt


# ── PNG-encoding regression (the bug that made Indra look blind) ───────────

def test_degradation_renders_encoded_png_not_raw_pixels():
    """cv2.imdecode must succeed on the bytes the degradation path renders —
    raw `to_pil().tobytes()` pixels made every local read silently empty."""
    import cv2
    import numpy as np
    import io as _io
    import pypdfium2 as pdfium

    raw = (PROJ / "independent_docs/te_holdout/te_standalone_h1_2024.pdf") \
        .read_bytes()
    pdf = pdfium.PdfDocument(_io.BytesIO(raw))
    buf = _io.BytesIO()
    pdf[4].render(scale=2.0).to_pil().convert("RGB").save(buf, format="PNG")
    img = cv2.imdecode(np.frombuffer(buf.getvalue(), np.uint8),
                       cv2.IMREAD_GRAYSCALE)
    assert img is not None and img.shape[0] > 1000   # a real decodable page


def test_indra_reads_the_te_scan_when_png_is_encoded():
    """The REAL proof (المهمة 2): with a properly encoded PNG, local Indra
    reads the TE balance sheet — segments carry boxes and text."""
    import io as _io

    import pypdfium2 as pdfium

    from src.extraction.local_ocr import indra_available, _page_markdown
    from src.extraction import spatial_cells as _SC

    if not indra_available():                      # pragma: no cover
        pytest.skip("local Indra unavailable")
    raw = (PROJ / "independent_docs/te_holdout/te_standalone_h1_2024.pdf") \
        .read_bytes()
    pdf = pdfium.PdfDocument(_io.BytesIO(raw))
    buf = _io.BytesIO()
    pdf[4].render(scale=2.0).to_pil().convert("RGB").save(buf, format="PNG")
    conv = _mk_conv()
    md = _page_markdown(conv, buf.getvalue())
    assert md and len(md) > 2000                   # NOT empty
    assert "Total Assets" in md or "Total assets" in md
    assert "169" in md                             # the printed magnitude family
    _w, _h, segs = _SC.read_page_lines(conv, buf.getvalue())
    assert segs, "Page.lines must carry segments"
    assert any("Total Assets" in (s.text or "") for s in segs)
    assert any("30/6/2024" in (s.text or "") for s in segs)


def _mk_conv():
    import indra_ocr

    return indra_ocr.load()


# ── metric honesty (المهمة 7) ──────────────────────────────────────────────

def test_far_is_na_when_nothing_is_decisive():
    from src.extraction.human_review import separated_metrics

    rows = [{"field": "f", "final_status": "CONFLICT", "exact_value": True}]
    sep = separated_metrics(rows, human_log=PROJ / "cell_evidence/none.json",
                            log_integrity=(False, "NO_KEY"))
    assert sep["false_acceptance_rate"] is None       # N/A, not 0.0
    assert sep["denominators"]["allowed"] == 0        # the denominator shown
    assert sep["counts"]["false_acceptances"] == 0    # the COUNT is zero too
