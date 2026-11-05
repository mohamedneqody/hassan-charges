# -*- coding: utf-8 -*-
"""Focused OCR accuracy + evidence recovery tests (المهام 1، 3، 4، 5).

The TE holdout's single decisive cell (net_income 2023 VERIFIED_EXACT) had
passed through an UNSAFE exception: the vision path left document_profile
EMPTY, so the correlated-source gate defaulted to trusted and two reads by
the SAME model of the SAME scan attested each other. These tests pin:

  1. the vision path now marks its layer honestly ("vision") and attaches a
     scan profile (text_layer_trusted=False) — same-layer agreement on a
     pure scan is an echo and downgrades;
  2. attestation needs ≥2 distinct layers behind the WINNING value — a
     local dissent strips a same-layer pair's false attestation, and
     cross-layer agreement attests;
  3. the focused local pass appends local_ocr CANDIDATES from row bands
     (never silent replacements) and works on the degradation path too;
  4. the AbuQir false-acceptance replay still passes (no regression).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ))

from src.extraction.normalizer import (  # noqa: E402
    FinancialData, build_decision_log, merge_parsed, reconcile,
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
    """A local band read that DISAGREES leaves the winning value backed by
    ONE layer → downgraded (the wrong-row capture loses its false
    attestation but is never silently replaced)."""
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


# ── focused local verification pass (المهمة 3) ─────────────────────────────

class _FakeBand:
    def __init__(self, text: str):
        self.text = text
        self.y0 = self.y1 = 0
        self.crop_png = b""


def test_focused_pass_appends_local_candidates_and_never_replaces(
        monkeypatch):
    """The pass appends local_ocr candidates from the located row band; a
    correct capture gains a cross-layer attestation; the WRONG value is
    never overwritten by the local read — the vote/gate decide."""
    import src.extraction.vision_ocr as VO

    d = FinancialData()
    d.values["total_assets"] = {2024: 20_327_981.0}      # wrong-row capture
    d.candidates["total_assets"] = {2024: [(20_327_981.0, 0)]}
    d.candidate_labels["total_assets"] = {2024: ["Total assets"]}
    d.candidate_layers["total_assets"] = {2024: ["vision"]}
    d.field_sources = {"total_assets": [5]}
    d.document_profile = dict(SCAN_PROFILE)

    monkeypatch.setenv("FOCUSED_LOCAL_VERIFY", "1")

    from src.extraction.spatial_cells import LineBox

    def fake_lines(conv, png):
        # two year columns at page x≈700 and x≈900; the printed row below
        return [
            LineBox(650, 100, 950, 130, "30/6/2024  31/12/2023", 0.9),
            LineBox(300, 200, 950, 230,
                    "Total assets          169 497 056    134 358 541", 0.9),
        ]

    monkeypatch.setattr("src.extraction.spatial_cells.read_page_lines",
                        fake_lines)   # belt: module-level patch
    reader = lambda png: (1347, 1743, fake_lines(None, png))

    VO._focused_local_cell_verification(
        d, b"", d.field_sources, {"years": [2024, 2023]},
        [5], [b"png"], [], line_reader=reader)
    cands = d.candidates["total_assets"][2024]
    layers = d.candidate_layers["total_assets"][2024]
    assert "local_ocr" in layers
    assert (169_497_056.0, cands[-1][1]) in cands      # candidate APPENDED
    assert d.values["total_assets"][2024] == 20_327_981.0   # value UNTOUCHED


def test_focused_pass_promotes_cross_layer_agreement(monkeypatch):
    """When the vision capture was CORRECT and the local band agrees, the
    cell attests honestly through the normal vote + gate."""
    import src.extraction.vision_ocr as VO

    d = FinancialData()
    d.values["cash"] = {2024: 6_000_305.0}
    d.candidates["cash"] = {2024: [(6_000_305.0, 0), (6_000_305.0, 1)]}
    d.candidate_labels["cash"] = {2024: ["Cash and cash equivalents",
                                         "Cash and cash equivalents"]}
    d.candidate_layers["cash"] = {2024: ["vision", "vision"]}
    d.confidence["cash"] = {2024: 2}
    d.field_sources = {"cash": [5]}
    d.document_profile = dict(SCAN_PROFILE)

    monkeypatch.setenv("FOCUSED_LOCAL_VERIFY", "1")

    from src.extraction.spatial_cells import LineBox

    def fake_lines(conv, png):
        return [
            LineBox(650, 100, 950, 130, "30/6/2024  31/12/2023", 0.9),
            LineBox(250, 200, 950, 230,
                    "Cash and cash equivalents   6 000 305   10 272 954",
                    0.9),
        ]

    monkeypatch.setattr("src.extraction.spatial_cells.read_page_lines",
                        fake_lines)   # belt: module-level patch
    reader = lambda png: (1347, 1743, fake_lines(None, png))

    VO._focused_local_cell_verification(
        d, b"", d.field_sources, {"years": [2024, 2023]},
        [5], [b"png"], [], line_reader=reader)
    e = next(e for e in build_decision_log(d)
             if e["field"] == "cash" and e["year"] == 2024)
    assert e["status"] == "VERIFIED_EXACT"      # vision + local_ocr agree
    assert "طبقة واحدة" not in e["reason"]


def test_focused_pass_disabled_by_flag(monkeypatch):
    import src.extraction.vision_ocr as VO

    d = FinancialData()
    d.candidates["cash"] = {2024: [(6_000_305.0, 0)]}
    monkeypatch.setenv("FOCUSED_LOCAL_VERIFY", "0")
    before = len(d.candidates["cash"][2024])
    VO._focused_local_cell_verification(
        d, b"", {}, {"years": [2024]}, [], [], [])
    assert len(d.candidates["cash"][2024]) == before   # no candidates added


def test_vision_data_carries_scan_profile_and_vision_layer():
    """The unsafe exception is closed: extract_via_vision's data must carry
    a scan profile (text_layer_trusted=False) and its candidates must be
    labelled layer=vision (source-level inspection of the wiring)."""
    import inspect

    import src.extraction.vision_ocr as VO

    src_txt = inspect.getsource(VO.extract_via_vision)
    assert 'part_layers=["vision"]' in src_txt
    assert "text_layer_trusted" in src_txt and "KIND_SCANNED_NO_TEXT" in src_txt
    assert "_focused_local_cell_verification" in src_txt


# ── metric honesty (المهمة 6) ──────────────────────────────────────────────

def test_far_is_na_when_nothing_is_decisive():
    from src.extraction.human_review import separated_metrics

    rows = [{"field": "f", "final_status": "CONFLICT", "exact_value": True}]
    sep = separated_metrics(rows, human_log=PROJ / "cell_evidence/none.json",
                            log_integrity=(False, "NO_KEY"))
    assert sep["false_acceptance_rate"] is None       # N/A, not 0.0
    assert sep["denominators"]["allowed"] == 0        # the denominator shown
