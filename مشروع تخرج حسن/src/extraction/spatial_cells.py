# -*- coding: utf-8 -*-
"""Spatial Financial Cell Extraction — rows and year columns from REAL
coordinates, never from text order.

Indra 1.1.2 exposes one bounding box per detected line (``Line.box`` =
[x0, y0, x1, y1] in image pixels) plus its text and confidence. This module
builds the geometry on top of that:

1.  One full-page read → lines with boxes.
2.  The year-header row is FOUND, not assumed: header lines are lines whose
    entire numeric content is a year token (2021/2022, either digit system).
    The column of a year sits where ITS header sits — no "current year is on
    the right" rule. A mirrored layout is handled by construction.
3.  Each year's column x-range is derived from the two header boxes: the
    boundary between the columns is the midpoint of their centers, and each
    range runs from that boundary outward past its header (padded by the
    wider header's width).
4.  The label row is located through the PRODUCTION mapper ``match_field``
    (same aliases, same negative rules as the pipeline) — the spatial layer
    cannot map a row the production rules would reject.
5.  A cell value is any number whose line box intersects the row's y-range
    and the year column's x-range, CROSS-CHECKED by a focused second Indra
    read of the cropped cell region. Agreement → candidate confirmed;
    disagreement → CONFLICT with both values kept; nothing → UNREADABLE.
6.  Everything is stored in RELATIVE page coordinates (fractions of width /
    height) so evidence survives re-renders at other DPIs.

Honest precision level: Indra boxes are WHOLE-LINE boxes — token-level x is
not available. Column ranges are therefore accurate to the header line's
box (a header line usually holds just the year token). Where Indra merges a
whole table row into one line box, the detection pass finds nothing and the
module falls back to the focused crop read alone (status ``CROP_ONLY``),
which is still geometry-driven (the crop is the row∩column intersection) —
but its value comes from a single read and must not be trusted further
without the live per-cell vision confirmation (PENDING_API_QUOTA).

Statuses: VERIFIED_CANDIDATE (header + label + detection/crop agreement),
CROP_ONLY (crop read only), CONFLICT, UNREADABLE, NO_ROW, MULTI_ROW,
UNCONFIRMED_YEAR (no header found for that year — any value stays
untrusted), NO_COLUMN (no year headers at all).

No company-specific values live here: callers pass field names; labels and
negatives come from the production config.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

AR2EN = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_YEAR_RE = re.compile(r"(20[0-9]{2})")
_NUM_RE = re.compile(r"\d[\d,]*\.?\d*")

STATUS_VERIFIED = "VERIFIED_CANDIDATE"
STATUS_CROP_ONLY = "CROP_ONLY"
STATUS_CONFLICT = "CONFLICT"
STATUS_UNREADABLE = "UNREADABLE"
STATUS_NO_ROW = "NO_ROW"
STATUS_MULTI_ROW = "MULTI_ROW"
STATUS_NO_YEAR = "UNCONFIRMED_YEAR"
STATUS_NO_COLUMN = "NO_COLUMN"

# Provenance ladder (سلّم المصدر) — a machine read can never award itself
# the visual level: VISUALLY_VERIFIED is set ONLY via mark_visually_verified
# by review tooling / a human confirming the saved crop.
PROVENANCE_LADDER = ("OCR_READ", "VISUALLY_VERIFIED", "INFERRED",
                     "UNREADABLE", "UNVERIFIED")


def mark_visually_verified(cell: "SpatialCell", reviewer: str) -> "SpatialCell":
    """Explicitly upgrade an OCR_READ cell after a human/review pass confirmed
    the saved crop shows the value. Records WHO verified, WHEN, the value
    before, and the source crop's SHA-256 — any later change to the crop or
    value voids the review (check with review_is_valid). The extraction
    pipeline itself never sets this level; OCR/Gemini/arithmetic cannot
    self-award it."""
    import hashlib
    import time as _time

    if cell.provenance == "OCR_READ":
        crop_sha = (hashlib.sha256(cell.crop_png).hexdigest()[:16]
                    if cell.crop_png else None)
        cell.review = {
            "reviewer": reviewer,
            "timestamp": _time.strftime("%Y-%m-%dT%H:%M:%S"),
            "value_before": cell.value,
            "crop_sha256": crop_sha,
            "source_type": "OCR",
            "verification_status_before": cell.status,
        }
        cell.provenance = "VISUALLY_VERIFIED"
        cell.detail = f"[visually verified by {reviewer}] {cell.detail}"
    return cell


def review_is_valid(cell: "SpatialCell") -> bool:
    """The visual review holds only while the reviewed crop (and its value)
    are unchanged — a new crop or a different value voids it."""
    import hashlib

    rev = getattr(cell, "review", None)
    if not rev:
        return False
    if cell.crop_png is None:
        return rev.get("crop_sha256") is None
    return (hashlib.sha256(cell.crop_png).hexdigest()[:16]
            == rev.get("crop_sha256"))


@dataclass
class LineBox:
    """One OCR line with its geometry, in original image pixels."""
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    conf: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2.0

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2.0

    @property
    def height(self) -> float:
        return max(self.y1 - self.y0, 1.0)


@dataclass
class YearColumn:
    year: int
    x0: float  # relative to page width
    x1: float
    header_cx: float  # relative

    def contains(self, cx: float) -> bool:
        return self.x0 <= cx <= self.x1


@dataclass
class SpatialCell:
    field: str
    year: int
    status: str
    detail: str = ""
    provenance: str = "UNVERIFIED"   # OCR_READ | VISUALLY_VERIFIED | INFERRED | UNREADABLE | UNVERIFIED
    source_type: str = "OCR"         # OCR | GEOMETRY | DERIVED — origin, not quality
    confidence: str = "low"          # low | medium | high — set with status below
    year_source: str = "none"        # PRINTED_YEAR_READ | YEAR_INFERRED | YEAR_UNVERIFIED
    review: dict | None = None
    label_text: str = ""
    label_score: int = 0
    label_box_rel: list = field(default_factory=list)
    column_rel: list = field(default_factory=list)
    cell_bbox_rel: list = field(default_factory=list)
    detection_values: list = field(default_factory=list)   # (value, raw_token)
    crop_values: list = field(default_factory=list)        # (value, raw_token)
    value: float | None = None
    crop_png: bytes | None = None


def _digits(line_text: str) -> list[str]:
    return _YEAR_RE.findall((line_text or "").translate(AR2EN))


def read_page_lines(conv, png: bytes) -> tuple[int, int, list[LineBox]]:
    """One full-page Indra read → (page_w, page_h, lines with boxes)."""
    import tempfile
    from pathlib import Path

    import cv2
    import numpy as np

    arr = np.frombuffer(png, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return 0, 0, []
    page_h, page_w = img.shape[:2]
    with tempfile.TemporaryDirectory(prefix="indra_spatial_") as td:
        p = Path(td) / "page.png"
        p.write_bytes(png)
        for _i, pg in conv.convert(str(p)):
            lines = [
                LineBox(b.box[0], b.box[1], b.box[2], b.box[3],
                        b.text or "", float(getattr(b, "conf", 0.0) or 0.0))
                for b in (pg.lines or [])
            ]
            return page_w, page_h, lines
    return page_w, page_h, []


def _pure_year_line(ln: LineBox) -> int | None:
    """A line that IS a year header: its only number is a year token."""
    t = (ln.text or "").translate(AR2EN)
    nums = [m.group() for m in _NUM_RE.finditer(t)
            if m.group().strip(".,")]
    years = [int(y) for y in _YEAR_RE.findall(t)]
    if len(nums) == 1 and len(years) == 1 and nums[0] == str(years[0]) \
            and 2000 <= years[0] <= 2099 and len(ln.text.strip()) <= 12:
        return years[0]
    return None


def _range_from_boundary(cx: float, pad: float, boundary: float) -> tuple[float, float]:
    """The column runs from the shared boundary OUTWARD past its own header —
    whichever side the header happens to sit on."""
    if cx >= boundary:
        return (boundary, min(cx + pad, 1.0))
    return (max(cx - pad, 0.0), boundary)


def find_year_columns(
    lines: list[LineBox], page_w: float, years: tuple[int, int] = (2022, 2021),
) -> tuple[dict[int, YearColumn], str]:
    """Locate the year-header row and build each year's column x-range from
    the ACTUAL header boxes. No side assumption: whichever year sits where,
    its column follows its own header. Returns ({year: YearColumn}, detail)."""
    headers = [(ln, _pure_year_line(ln)) for ln in lines]
    headers = [(ln, y) for ln, y in headers if y in years]
    if not headers:
        return {}, "no pure year-header line found on the page"
    # Group headers by y (same visual header row): tolerance = 1.5×median h.
    med_h = sorted(ln.height for ln, _ in headers)[len(headers) // 2]
    groups: list[list[tuple[LineBox, int]]] = []
    for ln, y in headers:
        for g in groups:
            if abs(ln.cy - g[0][0].cy) <= 1.5 * med_h:
                g.append((ln, y))
                break
        else:
            groups.append([(ln, y)])
    # The table header row holds BOTH years; prefer the topmost such group.
    full = [g for g in groups if {y for _, y in g} >= set(years)]
    if not full:
        found = sorted({y for g in groups for _, y in g})
        return {}, f"year headers found ({found}) but not co-located on one row"
    g = min(full, key=lambda gg: gg[0][0].cy)
    by_year: dict[int, LineBox] = {}
    for ln, y in g:
        # keep the widest header line per year (most complete token)
        if y not in by_year or (ln.x1 - ln.x0) > (by_year[y].x1 - by_year[y].x0):
            by_year[y] = ln
    h_a, h_b = by_year[years[0]], by_year[years[1]]
    y_a, y_b = years[0], years[1]
    cx_a = h_a.cx / page_w
    cx_b = h_b.cx / page_w
    boundary = (cx_a + cx_b) / 2.0
    pad_a = (h_a.x1 - h_a.x0) / page_w * 0.75
    pad_b = (h_b.x1 - h_b.x0) / page_w * 0.75
    r_a = _range_from_boundary(cx_a, pad_a, boundary)
    r_b = _range_from_boundary(cx_b, pad_b, boundary)
    cols = {
        y_a: YearColumn(y_a, r_a[0], r_a[1], cx_a),
        y_b: YearColumn(y_b, r_b[0], r_b[1], cx_b),
    }
    return cols, (
        f"header row at y={h_a.y0:.0f}: {y_a} at rel-x {cx_a:.3f}, "
        f"{y_b} at rel-x {cx_b:.3f} ({'normal' if cx_a > cx_b else 'mirrored'} layout)"
    )


_YEAR_ANY = re.compile(r"(20[0-9]{2})")


def enhance_variants(crop_png: bytes) -> list[tuple[str, bytes]]:
    """Focused re-read variants, in preference order: original, ×3 cubic
    upscale, ×3+CLAHE contrast, ×3+adaptive threshold. A sharper image is
    NOT evidence of better OCR — the caller judges by what comes back."""
    import cv2
    import numpy as np

    arr = np.frombuffer(crop_png, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return [("orig", crop_png)]
    out = [("orig", crop_png)]
    up = cv2.resize(img, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    ok, b = cv2.imencode(".png", up)
    if ok:
        out.append(("up3", b.tobytes()))
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(up)
        ok, b = cv2.imencode(".png", clahe)
        if ok:
            out.append(("up3_clahe", b.tobytes()))
        th = cv2.adaptiveThreshold(
            up, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15)
        ok, b = cv2.imencode(".png", th)
        if ok:
            out.append(("up3_bin", b.tobytes()))
        # stronger variants for cells whose digits survive no mild treatment
        med = cv2.medianBlur(up, 3)
        ok, b = cv2.imencode(".png", med)
        if ok:
            out.append(("up3_med", b.tobytes()))
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        morph = cv2.morphologyEx(med, cv2.MORPH_CLOSE, kernel)
        ok, b = cv2.imencode(".png", morph)
        if ok:
            out.append(("up3_morph", b.tobytes()))
        up4 = cv2.resize(img, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
        ok, b = cv2.imencode(".png", up4)
        if ok:
            out.append(("up4", b.tobytes()))
    return out


def parse_date_tokens(text: str) -> tuple[int, int, int] | None:
    """One VALID printed date → (year, month, day). Accepts Arabic-Indic or
    Latin digits and d/m/y, m/d/y or y/m/d orders with / . - separators;
    REJECTS impossible day/month values (32/13/2022 and the like) — a regex
    year match alone is never sufficient."""
    t = (text or "").translate(AR2EN)
    groups = [g.strip(" .-–") for g in re.split(r"[\\/.\-–]", t)]
    nums = [int(g) for g in groups if g.isdigit() and len(g) <= 4]
    years = [n for n in nums if 2000 <= n <= 2099]
    if len(set(years)) != 1:
        return None
    year = years[0]
    rest = [n for n in nums if n != year]
    if len(rest) != 2:
        return None
    a, b = rest
    day_ok = (1 <= a <= 31 and 1 <= b <= 12) or (1 <= a <= 12 and 1 <= b <= 31)
    if not day_ok:
        return None
    # assign month/day; when both fit both roles the printed order is kept
    if 1 <= a <= 12 and 1 <= b <= 12:
        month, day = a, b
    elif a > 12:
        month, day = b, a
    else:
        month, day = a, b
    return year, month, day


def year_from_date_text(text: str) -> int | None:
    """The 4-digit year in a printed column date — any digit system, any
    day/month/year order (٣١/١٢/٢٠٢٢، 2022/12/31، ٢٠٢٢/١٢/٣١). Garbled OCR
    text ('4.41/14/1') yields None — never a guess."""
    t = (text or "").translate(AR2EN)
    years = [int(y) for y in _YEAR_ANY.findall(t)]
    if len(set(years)) == 1 and 2000 <= years[0] <= 2099:
        return years[0]
    return None


def _currency_header_lines(lines: list[LineBox]) -> list[LineBox]:
    cands = [
        ln for ln in lines
        if ln.text and not any(ch.isdigit() for ch in ln.text.translate(AR2EN))
        # «جنيه مصري» with either yeh codepoint (ي U+064A / ی U+06CC)
        and ("نيه" in ln.text or "نیه" in ln.text) and "مص" in ln.text
        and len(ln.text.strip()) <= 12
    ]
    return cands


def find_date_columns(
    conv, png: bytes, lines: list[LineBox], page_w: float, page_h: float,
    date_reader=None,
) -> tuple[dict[int, YearColumn], str]:
    """Year columns from the PRINTED column dates (31/12/2022-style) sitting
    directly above the currency column titles — real printed evidence, never
    a convention. The full-page read often garbles or EMPTIES these small
    date lines (conf 0.25–0.76 on the 2022 statements), so each date region
    gets a focused crop re-read (the crop reads proved far more accurate).
    `date_reader(png, x0, y0, x1, y1) -> str` is injectable for tests.
    A year counts as READ only when exactly one 4-digit year parses."""
    cur_cols, cur_detail = find_currency_columns(lines, page_w)
    if not cur_cols:
        return {}, f"no currency columns ({cur_detail})"
    cands = _currency_header_lines(lines)
    med_h = sorted(ln.height for ln in cands)[len(cands) // 2]
    groups: list[list[LineBox]] = []
    for ln in sorted(cands, key=lambda l: l.cy):
        for g in groups:
            if abs(ln.cy - g[0].cy) <= 1.5 * med_h:
                g.append(ln)
                break
        else:
            groups.append([ln])
    row = next((g for g in groups if len(g) >= 2), None)
    if row is None:
        return {}, "currency headers not co-located; no date row expected"
    hdr_y0 = min(ln.y0 for ln in row)
    if date_reader is None:
        def date_reader(png_, x0, y0, x1, y1):
            """Focused re-read over enhancement variants; returns the first
            variant text that parses as a VALID date, else the best raw."""
            crop = _crop(png_, x0 / page_w, y0 / page_h, x1 / page_w, y1 / page_h)
            if crop is None:
                return ""
            from src.extraction.local_ocr import _page_markdown

            best = ""
            for _name, variant in enhance_variants(crop):
                txt = _page_markdown(conv, variant) or ""
                if parse_date_tokens(txt):
                    return txt
                if txt.strip() and not best:
                    best = txt
            return best
    cols: dict[int, YearColumn] = {}
    notes = []
    for side, col in cur_cols.items():
        hdr = next((ln for ln in row
                    if abs(ln.cx / page_w - col.header_cx) < 0.08), None)
        if hdr is None:
            continue
        # the date line sits directly above its currency title
        x0 = max(col.x0 - 0.02, 0.0) * page_w
        x1 = min(col.x1 + 0.02, 1.0) * page_w
        y0 = max(hdr.y0 - 3.2 * hdr.height, 0.0)
        y1 = hdr.y0 + 0.2 * hdr.height
        raw = date_reader(png, x0, y0, x1, y1)
        yr = year_from_date_text(raw)
        notes.append(f"{side}: raw={raw.strip()[:24]!r} year={yr}")
        if yr is not None:
            cols[yr] = YearColumn(yr, col.x0, col.x1, col.header_cx)
    detail = "printed column dates [" + "; ".join(notes) + "]"
    if not cols:
        return {}, detail + " — none readable"
    return cols, detail


def find_currency_columns(
    lines: list[LineBox], page_w: float,
) -> tuple[dict[str, YearColumn], str]:
    """Columns from the ACTUAL printed currency titles («جنيه مصري» above
    each value column) — the only per-column headers this document prints.
    Returns {'right': YearColumn(year=0), 'left': ...}; the YEAR order is
    deliberately NOT decided here (no printed year labels exist — assigning
    years is a separate, explicitly declared convention, never silent)."""
    cands = [
        ln for ln in lines
        if ln.text and not any(ch.isdigit() for ch in ln.text.translate(AR2EN))
        # «جنيه مصري» with either yeh codepoint (ي U+064A / ی U+06CC)
        and ("نيه" in ln.text or "نیه" in ln.text) and "مص" in ln.text
        and len(ln.text.strip()) <= 12
    ]
    if len(cands) < 2:
        return {}, f"currency column headers found: {len(cands)} (need 2)"
    med_h = sorted(ln.height for ln in cands)[len(cands) // 2]
    # one line per column: group by y, keep the topmost row with ≥2 groups
    groups: list[list[LineBox]] = []
    for ln in sorted(cands, key=lambda l: l.cy):
        for g in groups:
            if abs(ln.cy - g[0].cy) <= 1.5 * med_h:
                g.append(ln)
                break
        else:
            groups.append([ln])
    row = next((g for g in groups if len(g) >= 2), None)
    if row is None:
        return {}, "currency headers not co-located on one row"
    row = sorted(row, key=lambda l: l.cx, reverse=True)  # rightmost first
    right, left = row[0], row[1]
    cx_r, cx_l = right.cx / page_w, left.cx / page_w
    boundary = (cx_r + cx_l) / 2.0
    pad_r = (right.x1 - right.x0) / page_w * 1.25   # value cells are wider
    pad_l = (left.x1 - left.x0) / page_w * 1.25     # than their title
    return {
        "right": YearColumn(0, _range_from_boundary(cx_r, pad_r, boundary)[0],
                            _range_from_boundary(cx_r, pad_r, boundary)[1], cx_r),
        "left": YearColumn(0, _range_from_boundary(cx_l, pad_l, boundary)[0],
                           _range_from_boundary(cx_l, pad_l, boundary)[1], cx_l),
    }, (f"currency headers at rel-x right={cx_r:.3f}, left={cx_l:.3f}; "
        "year order NOT printed — needs the declared convention")


def parse_number_tokens(text: str) -> list[tuple[float, str]]:
    """(float, raw_token) pairs — the raw token is kept so the evaluation can
    separate OCR recognition from numeric normalization. Arabic-Indic digits
    are normalized here (stage 2 of the metric ladder). Accounting parens
    («(179,626,127)») and an attached minus read as NEGATIVE values; a bare
    dash/empty cell yields nothing."""
    out: list[tuple[float, str]] = []
    t = (text or "").translate(AR2EN)
    for m in _NUM_RE.finditer(t):
        tok = m.group().strip(".,")
        if not tok:
            continue
        try:
            v = float(tok.replace(",", ""))
        except ValueError:
            continue
        # accounting negative: (token) or -token
        before = t[max(0, m.start() - 1):m.start()]
        after = t[m.end():m.end() + 1]
        if before.strip() == "(" and after.strip() == ")":
            v = -v
        elif before.strip() == "-":
            v = -v
        out.append((v, tok))
    return out


def find_label_rows(lines: list[LineBox], field: str) -> tuple[list[LineBox], int]:
    """Rows the PRODUCTION mapper assigns to `field` (same aliases, same
    negative rules as the pipeline — the spatial layer never overrides
    them). Returns (rows, best_score); score is the keyword-hit count."""
    from src.extraction.normalizer import match_field, normalize_label

    rows: list[LineBox] = []
    best = 0
    for ln in lines:
        if match_field(ln.text) == field:
            rows.append(ln)
            norm = normalize_label(ln.text) or ""
            best = max(best, len(norm))
    return rows, best


def _crop(png: bytes, x0r: float, y0r: float, x1r: float, y1r: float) -> bytes | None:
    import cv2
    import numpy as np

    arr = np.frombuffer(png, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    h, w = img.shape[:2]
    x0, x1 = max(0, int(w * x0r)), min(w, max(int(w * x1r), 1))
    y0, y1 = max(0, int(h * y0r)), min(h, max(int(h * y1r), 1))
    if x1 <= x0 or y1 <= y0:
        return None
    ok, out = cv2.imencode(".png", img[y0:y1, x0:x1])
    return out.tobytes() if ok else None


def select_candidate(cands: list[tuple[float, str, str, float]]) -> tuple[float, str]:
    """GT-free candidate scoring. cands: (value, token, source, x_offset).
    Score = digit-completeness first (truncated OCR garbles lose digits —
    the most COMPLETE read of the SAME cell region wins), then source
    priority (focused crop read above the full-page line), then spatial fit
    to the column center. Ties keep the first. The runner-up is never
    discarded — the caller records CONFLICT when distinct candidates remain.
    No ground truth is consulted at extraction time."""
    def score(c):
        v, tok, source, off = c
        digits = sum(ch.isdigit() for ch in tok)
        src_rank = 2 if source.startswith("crop") else 1
        return (digits, src_rank, -abs(off))
    best = max(cands, key=score)
    return best[0], best[2]


def extract_spatial_cell(conv, png: bytes, field: str, year: int,
                         columns: dict[int, YearColumn] | None = None,
                         columns_source: str = "year_headers") -> SpatialCell:
    """One field/year cell by geometry: label row (production rules) ∩ year
    column. Label rows are TRIALED longest-first until one yields candidates
    (a section header shares the words of the total row below it); the crop
    is re-read across enhancement variants; candidates are scored GT-free by
    digit completeness → source priority → spatial fit; a MULTI_ROW doubt
    survives resolution and is never promoted to VERIFIED."""
    cell = SpatialCell(field=field, year=year, status=STATUS_NO_COLUMN)
    page_w, page_h, lines = read_page_lines(conv, png)
    if not lines:
        cell.status = STATUS_NO_COLUMN
        cell.detail = "empty page read"
        return cell

    if columns is None:
        # printed evidence first: the column DATES above the currency titles
        cols, col_detail = find_date_columns(conv, png, lines, page_w, page_h)
        if not cols:
            cols, col_detail = find_year_columns(lines, page_w)
    else:
        cols, col_detail = columns, f"columns provided ({columns_source})"

    rows, _score = find_label_rows(lines, field)
    if not rows:
        cell.status = STATUS_NO_ROW
        cell.detail = f"no line maps to '{field}' ({col_detail})"
        return cell
    if len(rows) > 1:
        cell.detail = f"{len(rows)} rows map to '{field}'"
    # trial order: the longest label text first — «إجمالي ضريبة الدخل عن
    # العام» is more specific than the «ضريبة الدخل» section header
    rows = sorted(rows, key=lambda ln: -len(ln.text or ""))
    cell.year_source = ("printed_dates" if "dates" in (columns_source or "")
                        else "declared_convention" if columns is not None
                        else "year_headers")

    # a missing year column is an ASSIGNMENT failure, not a reading failure —
    # report it before any trial so callers can invoke the labelled fallback
    if year not in cols:
        label = rows[0]
        cell.label_text = label.text[:120]
        cell.label_box_rel = [label.x0 / page_w, label.y0 / page_h,
                              label.x1 / page_w, label.y1 / page_h]
        cell.status = STATUS_NO_YEAR
        cell.detail = f"year {year} header not found ({col_detail})"
        return cell

    from src.extraction.local_ocr import _page_markdown

    trials = []
    for ri, label in enumerate(rows):
        band = (label.y0 - 0.45 * label.height, label.y1 + 0.45 * label.height)
        detection: list[tuple[float, str, str, float]] = []
        for ln in lines:
            if not (band[0] <= ln.cy <= band[1]) or ln is label:
                continue
            cx_rel = ln.cx / page_w
            if year in cols and cols[year].contains(cx_rel):
                detection += [(v, t, "line", ln.cx / page_w - cols[year].header_cx)
                              for v, t in parse_number_tokens(ln.text)]
        detection = [d for d in detection if abs(d[0]) >= 1000]
        crop_png = None
        crop_vals: list[tuple[float, str, str, float]] = []
        if year in cols:
            col = cols[year]
            x0r, x1r = max(col.x0 - 0.01, 0.0), min(col.x1 + 0.01, 1.0)
            y0r, y1r = max(band[0], 0.0) / page_h, min(band[1], page_h) / page_h
            crop_png = _crop(png, x0r, y0r, x1r, y1r)
            if crop_png is not None:
                # enhancement variants: EVERY variant contributes candidates —
                # an early garbled orig read must not mask a complete up3 read
                for vname, variant in enhance_variants(crop_png):
                    txt = _page_markdown(conv, variant) or ""
                    crop_vals += [(v, t, f"crop:{vname}", 0.0)
                                  for v, t in parse_number_tokens(txt)
                                  if abs(v) >= 1000]
        trials.append({"label": label, "detection": detection,
                       "crop": crop_vals, "crop_png": crop_png})
    # try ALL matched rows — a section header that yields no number in its
    # own intersection is NOT a competing value. MULTI_ROW doubt = two or
    # more rows that PRODUCED candidates, not merely matched the words.
    productive = [t for t in trials if t["detection"] or t["crop"]]
    multi = len(productive) > 1
    if not productive:
        cell.status = STATUS_UNREADABLE
        cell.detail = (f"no number in any of {len(trials)} label rows' "
                       f"row∩column intersections ({col_detail})")
        return cell
    pick = productive[0]
    label = pick["label"]
    cell.label_text = label.text[:120]
    cell.label_box_rel = [label.x0 / page_w, label.y0 / page_h,
                          label.x1 / page_w, label.y1 / page_h]
    detection = pick["detection"]
    cell.detection_values = [(v, t) for v, t, _s, _o in detection]
    cell.crop_values = [(v, t) for v, t, _s, _o in pick["crop"]]
    col = cols.get(year) if year in cols else None
    cell.column_rel = [col.x0, col.x1] if col else []
    band = (label.y0 - 0.45 * label.height, label.y1 + 0.45 * label.height)
    cell.cell_bbox_rel = [max(col.x0 - 0.01, 0.0) if col else 0.0,
                          max(band[0], 0.0) / page_h,
                          min(col.x1 + 0.01, 1.0) if col else 1.0,
                          min(band[1], page_h) / page_h]
    if col is None:
        cell.status = STATUS_NO_YEAR
        cell.detail = f"year {year} header not found ({col_detail})"
        return cell
    if pick["crop_png"] is not None:
        cell.crop_png = pick["crop_png"]

    all_c = detection + pick["crop"]
    all_vals = [v for v, _t, _s, _o in all_c]
    distinct = []
    for v in all_vals:
        if not any(abs(v - d) <= max(1.0, 1e-6 * abs(v)) for d in distinct):
            distinct.append(v)
    crop_distinct = []
    for v, _t, _s, _o in pick["crop"]:
        if not any(abs(v - d) <= max(1.0, 1e-6 * abs(v)) for d in crop_distinct):
            crop_distinct.append(v)
    if not all_vals:
        cell.status = STATUS_UNREADABLE
        cell.detail = "no number in the row∩column intersection"
        return cell

    cell.value, src = select_candidate(all_c)
    if len(distinct) == 1 and detection and pick["crop"]:
        cell.status = STATUS_VERIFIED
        cell.detail = f"detection + crop read agree on {cell.value:,.0f}"
    elif len(distinct) == 1:
        cell.status = STATUS_CROP_ONLY
        cell.detail = f"single source ({src}) = {cell.value:,.0f} — needs the live per-cell confirmation"
    else:
        cell.status = STATUS_CONFLICT
        cell.detail = (f"selected {cell.value:,.0f} [{src}] vs others "
                       f"{[d for d in distinct if abs(d - cell.value) > 1][:3]} — all kept")
    if cell.value is not None:
        sel_digits = sum(ch.isdigit() for ch in str(cell.value).split(".")[0].lstrip("-"))
        if sel_digits < 6:
            cell.detail = f"short read ({sel_digits} digits) — suspect truncation; {cell.detail}"[:180]
            if cell.status in (STATUS_VERIFIED, STATUS_CROP_ONLY):
                cell.status = STATUS_UNREADABLE if cell.status == STATUS_VERIFIED                     else cell.status
                cell.provenance = "UNVERIFIED"
    if multi:
        # a MULTI_ROW doubt is structural: the value is never VERIFIED while
        # several rows claim the field, even when one produced the number
        keep = cell.status
        cell.status = STATUS_MULTI_ROW
        cell.detail = f"MULTI_ROW kept after resolution ({keep}): {cell.detail}"[:180]
    cell.provenance = {
        STATUS_VERIFIED: "OCR_READ", STATUS_CROP_ONLY: "OCR_READ",
        STATUS_CONFLICT: "UNVERIFIED",
    }.get(cell.status, "UNVERIFIED")
    # three separated dimensions: origin (source_type/provenance),
    # verification (status), confidence (agreement level)
    cell.confidence = {"VERIFIED_CANDIDATE": "high", "CROP_ONLY": "medium",
                       "CONFLICT": "low", "MULTI_ROW": "low",
                       "UNREADABLE": "low"}.get(cell.status, "low")
    return cell


def extract_page_cells(conv, png: bytes, jobs: list[tuple[str, int]]) -> dict[tuple[str, int], SpatialCell]:
    """Several (field, year) cells on one page, serially (Indra's image
    pipeline is not thread-safe; each cell does one full-page read plus one
    focused crop read)."""
    out: dict[tuple[str, int], SpatialCell] = {}
    for f, y in jobs:
        out[(f, y)] = extract_spatial_cell(conv, png, f, y)
    return out
