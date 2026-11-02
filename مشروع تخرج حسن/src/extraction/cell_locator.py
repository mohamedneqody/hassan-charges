# -*- coding: utf-8 -*-
"""Cell-Level Table Localization (تحديد الخانة المالية على الصفحة) — OpenCV.

Given a rendered statement-page image, detect the table grid (horizontal row
separators + vertical column separators) via morphology, then locate a target
field's CELL: the intersection of its row band and year column band, with the
Arabic label cell in the same row (RTL: labels rightmost, year columns extend
leftward — 2022 rightmost numeric column for a two-year statement).

All boxes are RELATIVE (0-1 of page width/height) so they survive any render
resolution; pixel crops are derived per requested scale. Numeric cell reads
use the LOCAL Indra engine (free) — a weak second opinion for digits whose
authoritative re-read is PENDING_API_QUOTA.

No document-specific coordinates: everything is detected from the image.
"""
from __future__ import annotations

import io
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import cv2
import numpy as np

AR2EN = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


@dataclass(frozen=True)
class Box:
    """Relative box (0-1)."""
    x0: float
    y0: float
    x1: float
    y1: float

    def crop(self, img) -> np.ndarray:
        h, w = img.shape[:2]
        return img[int(self.y0 * h):int(self.y1 * h), int(self.x0 * w):int(self.x1 * w)]


@dataclass
class RowInfo:
    index: int
    band: Box            # full-width row band
    label_box: Box       # rightmost column (Arabic label)
    label_text: str      # local Indra read of the label cell


@dataclass
class CellEvidence:
    field: str
    page: int
    document_sha256: str
    statement_type: str
    year: int
    label_ar: str
    label_box: Box | None
    row_box: Box | None
    year_columns: dict            # year -> Box (numeric column band)
    cell_boxes: dict              # year -> Box (the cell for THIS field)
    cell_crops: dict              # year -> png bytes
    context_crop: bytes | None    # row band incl. label + all year columns
    ocr_raw: dict                 # year -> raw local text of the cell
    normalized: dict              # year -> float (parsed)
    label_matched: bool
    status: str                   # LOCATED | LABEL_UNMATCHED | NO_GRID | AMBIGUOUS
    reason: str
    candidates: list = field(default_factory=list)


def _gray(page_png: bytes):
    arr = np.frombuffer(page_png, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)


def detect_grid(page_png: bytes, min_row_h: float = 0.008,
                min_col_w: float = 0.02) -> tuple[list[Box], list[Box]]:
    """Detect row bands (between horizontal separators) and column bands
    (between vertical separators) in RELATIVE coordinates. Returns
    (row_boxes, col_boxes) as full-width/full-height bands respectively."""
    img = _gray(page_png)
    if img is None:
        return [], []
    H, W = img.shape[:2]
    _, bw = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # horizontal separators
    kh = cv2.getStructuringElement(cv2.MORPH_RECT, (int(W * 0.30), 1))
    horiz = cv2.morphologyEx(bw, cv2.MORPH_OPEN, kh)
    hys = np.where(horiz.sum(axis=1) > 255 * W * 0.25)[0]
    # vertical separators
    kv = cv2.getStructuringElement(cv2.MORPH_RECT, (1, int(H * 0.12)))
    vert = cv2.morphologyEx(bw, cv2.MORPH_OPEN, kv)
    vxs = np.where(vert.sum(axis=0) > 255 * H * 0.10)[0]

    def collapse(ids, min_gap):
        groups = []
        for i in ids:
            if groups and i - groups[-1][-1] <= min_gap:
                groups[-1].append(i)
            else:
                groups.append([i])
        return [int(np.mean(g)) for g in groups]

    hlines = collapse(list(hys), 6)
    vlines = collapse(list(vxs), 6)

    rows = []
    for a, b in zip(hlines, hlines[1:]):
        if (b - a) / H >= min_row_h:
            rows.append(Box(0.0, a / H, 1.0, b / H))
    cols = []
    for a, b in zip(vlines, vlines[1:]):
        if (b - a) / W >= min_col_w:
            cols.append(Box(a / W, 0.0, b / W, 1.0))
    return rows, cols


def _cell_read(conv, img, box: Box) -> str | None:
    from src.extraction.local_ocr import _page_markdown

    crop = box.crop(img)
    ok, png = cv2.imencode(".png", crop)
    if not ok:
        return None
    return _page_markdown(conv, png.tobytes())


def locate_cells(page_png: bytes, label_keywords: list[str],
                 year_order: tuple = ("2022", "2021"),
                 rows: list[Box] | None = None,
                 cols: list[Box] | None = None,
                 conv_workers: int = 2) -> dict:
    """Localize the target row and its year cells on the page.

    label_keywords: generic Arabic fragments of the row label (e.g.
    ["تسهيلات", "بنوك"]). RTL: the label column is the RIGHTMOST column band;
    year columns extend leftward in `year_order`.

    Returns {"rows": [RowInfo...], "matched": RowInfo|None, "cells": {...}}.
    The numeric cell reads are LOCAL Indra (weak for digits) — recorded as
    raw reads; the authoritative re-read is PENDING_API_QUOTA.
    """
    img = _gray(page_png)
    if img is None:
        return {"error": "undecodable page"}
    if rows is None or cols is None:
        rows, cols = detect_grid(page_png)
    if not rows or not cols:
        return {"error": "no grid detected", "rows": rows, "cols": cols}

    # RTL: label column = the widest band whose x1 is rightmost
    label_col = max(cols, key=lambda b: b.x1 - b.x0 if False else b.x1)
    numeric_cols = sorted([b for b in cols if b is not label_col],
                          key=lambda b: -b.x1)  # rightmost numeric = first year
    year_cols = dict(zip(year_order, numeric_cols))

    tls = threading.local()

    def _conv():
        import indra_ocr

        conv = getattr(tls, "conv", None)
        if conv is None:
            conv = indra_ocr.load()
            tls.conv = conv
        return conv

    def _read_row_label(row: RowInfo):
        crop = row.label_box.crop(img)
        return _cell_read(_conv(), img, row.label_box)

    matched = None
    row_infos: list[RowInfo] = []
    W, H = img.shape[1], img.shape[0]

    def _spawn_read(row):
        return row

    # Indra-read every row's label cell (bounded by row count)
    with ThreadPoolExecutor(max_workers=conv_workers) as ex:
        futs = []
        for i, rb in enumerate(rows):
            ri = RowInfo(index=i, band=rb,
                         label_box=Box(rb.x1 - min(0.42, rb.x1 - rb.x0), rb.y0,
                                       rb.x1, rb.y1),
                         label_text="")
            futs.append((ri, ex.submit(_cell_read, _conv(), img, ri.label_box)))
        for ri, fut in futs:
            try:
                txt = fut.result() or ""
            except Exception:
                txt = ""
            ri.label_text = (txt or "").strip()
            row_infos.append(ri)

    for ri in row_infos:
        low = ri.label_text
        if any(k in low for k in label_keywords):
            matched = ri
            break

    cells = {}
    if matched is not None:
        for year, cb in year_cols.items():
            box = Box(cb.x0, matched.band.y0, cb.x1, matched.band.y1)
            cells[year] = {"box": box, "raw": _cell_read(_conv(), img, box)}

    return {"rows": row_infos, "matched": matched, "cells": cells,
            "year_cols": year_cols}
