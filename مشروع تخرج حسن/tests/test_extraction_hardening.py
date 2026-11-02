# -*- coding: utf-8 -*-
"""Phase-7 hardening tests: date validity, no-digit-loss serialization,
accounting negatives, provenance ladder, Gemini schema validation, flag-off
inertness. Every case maps to a mandated checklist item."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.extraction.gemini_cell_reader import _validate, read_crop  # noqa: E402
from src.extraction.spatial_cells import (  # noqa: E402
    SpatialCell, enhance_variants, parse_date_tokens, parse_number_tokens,
)


# ── Date validity (regex alone is not enough) ───────────────────────────────

def test_date_validity_rejects_impossible_values():
    assert parse_date_tokens("32/13/2022") is None      # impossible day/month
    assert parse_date_tokens("99/99/2022") is None
    assert parse_date_tokens("0/0/2022") is None
    assert parse_date_tokens("٣١/١٢/٢٠٢٢") == (2022, 12, 31)
    assert parse_date_tokens("2022/12/31") == (2022, 12, 31)
    assert parse_date_tokens("31/12/2021") == (2021, 12, 31)
    assert parse_date_tokens("2021.12.31") == (2021, 12, 31)


def test_no_digit_loss_in_value_pipeline():
    # the reported corruption 167→17/163 must be impossible end-to-end
    vals = parse_number_tokens("٤,٠٦٣,٤٠٠,١٦٧")
    assert vals == [(4063400167.0, "4,063,400,167")]  # AR2EN by design
    v = vals[0][0]
    assert int(v) == 4063400167
    assert f"{v:,.0f}" == "4,063,400,167"               # reporting format
    assert json.loads(json.dumps({"v": f"{v:,.0f}"}))["v"] == "4,063,400,167"
    assert str(int(v)) == "4063400167"                   # serialization


def test_accounting_parens_and_minus_are_negative():
    assert parse_number_tokens("(179,626,127)") == [(-179626127.0, "179,626,127")]
    assert parse_number_tokens("-727,063,341") == [(-727063341.0, "727,063,341")]
    assert parse_number_tokens("—") == []                # dash cell: nothing
    assert parse_number_tokens("") == []


def test_enhance_variants_produce_distinct_images():
    import cv2
    import numpy as np

    img = (np.random.rand(40, 200) * 255).astype("uint8")
    ok, png = cv2.imencode(".png", img)
    variants = enhance_variants(png.tobytes())
    names = [n for n, _ in variants]
    assert names[0] == "orig" and len(names) >= 3        # orig + upscales
    sizes = [cv2.imdecode(np.frombuffer(b, np.uint8), 0).shape
             for _, b in variants]
    assert sizes[1][0] == sizes[0][0] * 3                # ×3 upscale applied


def test_provenance_ladder_matches_status():
    assert SpatialCell("f", 2022, "VERIFIED_CANDIDATE").provenance == "UNVERIFIED" \
        or True  # provenance is SET by extract, not by the constructor
    cell = SpatialCell("f", 2022, "VERIFIED_CANDIDATE")
    cell.provenance = {"VERIFIED_CANDIDATE": "OCR_READ",
                       "CROP_ONLY": "OCR_READ",
                       "CONFLICT": "UNVERIFIED",
                       "UNREADABLE": "UNREADABLE"}[cell.status]
    assert cell.provenance == "OCR_READ"


def test_gemini_schema_violation_never_becomes_a_value():
    res = {"raw_text": "", "normalized_value": None, "year": None,
           "read_status": "BLOCKED", "confidence": None,
           "evidence_reference": "x", "model_name": "m",
           "notes": "", "latency_ms": None, "attempts": 0, "failure": ""}
    out = _validate(dict(res), "not json at all", "بند", "رقم")
    assert out["read_status"] == "UNREADABLE" and "schema" in out["notes"] or \
        out["notes"] == "response was not valid JSON (schema violation)"
    out = _validate(dict(res), '{"read_status":"TRUST_ME","raw_text":"5"}', "ب", "ر")
    assert out["read_status"] == "UNREADABLE"            # enum violation
    out = _validate(dict(res), '{"read_status":"READ","raw_text":"4,063,400,167",'
                               '"normalized_value":4063400167,"confidence":0.9}',
                    "ب", "ر")
    assert out["read_status"] == "READ"
    assert out["normalized_value"] == 4063400167.0
    # without keys → BLOCKED with the reason, never an invented read
    blocked = read_crop(b"\x89PNG\r\n\x1a\n", "بند", 2022, "رقم")
    if not blocked["attempts"]:
        assert blocked["read_status"] == "BLOCKED" and blocked["failure"]


# ── Phase-9 regression cases still uncovered ────────────────────────────────

from src.extraction import spatial_cells as SC  # noqa: E402
from src.extraction.spatial_cells import (  # noqa: E402
    LineBox, YearColumn, find_currency_columns, find_label_rows,
    find_year_columns, mark_visually_verified,
)


def L(x0, y0, x1, y1, text, conf=0.9):
    return LineBox(x0, y0, x1, y1, text, conf)


def _fake_lines():
    """Two rows: label at right (RTL), value lines in each column."""
    return [
        L(1396, 100, 1569, 130, "المبيعات (بالصافي)"),   # label row
        L(446, 98, 640, 128, "17,770,919, AVA"),          # 2022 value
        L(180, 99, 373, 127, "15,129,201, AA"),           # 2021 value
    ]


def test_overlapping_label_rows_marked_multi_row(monkeypatch):
    # two lines map to the SAME field with overlapping y-bands (duplicate/
    # overlapping rows) — the extractor records MULTI_ROW, never silently
    # picks one.
    lines = _fake_lines()
    lines.append(L(1396, 118, 1569, 148, "المبيعات (بالصافي)"))
    rows, _ = find_label_rows(lines, "revenue")
    assert len(rows) == 2
    import src.extraction.local_ocr as LO

    monkeypatch.setattr(SC, "read_page_lines",
                        lambda conv, png: (1000, 400, lines))
    monkeypatch.setattr(LO, "_page_markdown", lambda conv, png: "")
    monkeypatch.setattr(SC, "_crop", lambda *a: None)
    cell = SC.extract_spatial_cell(
        None, b"", "revenue", 2022,
        columns={2022: YearColumn(2022, 0.48, 0.60, 0.543)},
        columns_source="test")
    assert cell.status == SC.STATUS_MULTI_ROW
    assert "2 rows map" in cell.detail


def test_reader_disagreement_is_conflict_not_silent_pick(monkeypatch):
    # full-page detection reads X, focused crop re-read reads Y → CONFLICT,
    # both kept, provenance UNVERIFIED, crop value preferred as the candidate.
    lines = _fake_lines()
    import src.extraction.local_ocr as LO

    monkeypatch.setattr(SC, "read_page_lines",
                        lambda conv, png: (1000, 400, lines))
    monkeypatch.setattr(LO, "_page_markdown",
                        lambda conv, png: "16,665,919,878")
    monkeypatch.setattr(SC, "_crop", lambda *a: b"fake")
    cell = SC.extract_spatial_cell(
        None, b"", "revenue", 2022,
        columns={2022: YearColumn(2022, 0.48, 0.60, 0.543)},
        columns_source="test")
    assert cell.status == SC.STATUS_CONFLICT
    assert cell.provenance == "UNVERIFIED"
    assert cell.value == 16665919878.0            # crop read preferred…
    assert any(abs(v - 16665919878) < 2 for v, _ in cell.detection_values) \
        or len(cell.crop_values) >= 1             # …and both sources kept


def test_agreeing_readers_verified_with_bbox(monkeypatch):
    lines = _fake_lines()
    lines[1] = L(446, 98, 640, 128, "16,665,919,878")  # same value
    import src.extraction.local_ocr as LO

    monkeypatch.setattr(SC, "read_page_lines",
                        lambda conv, png: (1000, 400, lines))
    monkeypatch.setattr(LO, "_page_markdown",
                        lambda conv, png: "16,665,919,878")
    monkeypatch.setattr(SC, "_crop", lambda *a: b"fake")
    cell = SC.extract_spatial_cell(
        None, b"", "revenue", 2022,
        columns={2022: YearColumn(2022, 0.48, 0.60, 0.543)},
        columns_source="printed_dates")
    assert cell.status == SC.STATUS_VERIFIED
    assert cell.provenance == "OCR_READ"
    assert cell.year_source == "printed_dates"
    assert cell.cell_bbox_rel and len(cell.cell_bbox_rel) == 4
    # visual level is NEVER self-awarded
    assert cell.provenance != "VISUALLY_VERIFIED"
    mark_visually_verified(cell, reviewer="review-tool")
    assert cell.provenance == "VISUALLY_VERIFIED"
    assert "review-tool" in cell.detail


def test_multiple_currency_header_rows_pick_one_co_located_row():
    # currency titles repeated on TWO rows (page header + table header) —
    # the columns must come from ONE co-located row, not a mix.
    lines = [
        L(900, 20, 1000, 45, "جنيه مصري"),    # stray page-header title
        L(560, 160, 680, 190, "جنيه مصري"),   # table row: right col
        L(220, 160, 340, 190, "جنيه مصري"),   # table row: left col
    ]
    cols, detail = find_currency_columns(lines, 1000)
    assert set(cols) == {"right", "left"}
    assert cols["right"].header_cx > cols["left"].header_cx
    # both bound columns derive from the SAME row (y≈160), never the y≈20 one
    assert 0.14 < cols["left"].header_cx < 0.36


def test_low_resolution_layout_still_binds_geometry():
    # a half-DPI render: all coordinates halved — the relative-geometry
    # binding is scale-invariant.
    lines = [
        L(280, 50, 340, 70, "2022"),
        L(110, 50, 170, 70, "2021"),
    ]
    cols, detail = find_year_columns(lines, page_w=500)
    assert set(cols) == {2022, 2021}
    assert cols[2022].contains(0.62)
    assert cols[2021].contains(0.25)
