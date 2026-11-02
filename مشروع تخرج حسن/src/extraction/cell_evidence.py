# -*- coding: utf-8 -*-
"""Cell-Level Evidence (الخانة المقتطعة) — locate and package row-level evidence
from a scanned statement page WITHOUT any API calls.

Method: the page is split into overlapping horizontal bands; each band is read
locally with Indra OCR (free) and matched against the wanted row-label
keywords. The matching band becomes the evidence package: its y-range, its
crop image, its raw local text — ready for a focused live re-read when quota
allows (PENDING_API_QUOTA), and as visual proof of what the document prints.

No company-specific values: the caller supplies generic label keywords.
"""
from __future__ import annotations

import io
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

AR2EN = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


@dataclass
class RowBand:
    y0: int
    y1: int
    text: str
    crop_png: bytes
    matched_keywords: list = field(default_factory=list)


def _band_crop(page_png: bytes, y0f: float, y1f: float) -> bytes:
    import cv2
    import numpy as np

    arr = np.frombuffer(page_png, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return page_png
    h = img.shape[0]
    band = img[max(0, int(h * y0f)):min(h, int(h * y1f))]
    ok, jpeg = cv2.imencode(".png", band)
    return jpeg.tobytes() if ok else page_png


def _band_text(conv, page_png: bytes, y0f: float, y1f: float) -> str | None:
    """Render+OCR one horizontal band via the caller's Indra converter."""
    import cv2
    import numpy as np

    arr = np.frombuffer(page_png, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    h = img.shape[0]
    band = img[max(0, int(h * y0f)):min(h, int(h * y1f))]
    ok, png = cv2.imencode(".png", band)
    if not ok:
        return None
    from src.extraction.local_ocr import _page_markdown

    return _page_markdown(conv, png.tobytes())


def locate_row_band_by_text(page_png: bytes, keywords: list[str],
                            n_bands: int = 40, overlap: float = 0.5,
                            workers: int = 4) -> list[RowBand]:
    """Split the page into overlapping horizontal bands, read each locally with
    Indra (free), and return the bands whose text contains ANY keyword — those
    are the printed rows the caller is looking for. Pure-local: zero API."""
    import cv2
    import numpy as np

    from src.extraction.local_ocr import indra_available, _page_markdown
    import indra_ocr

    if not indra_available():
        return []
    arr = np.frombuffer(page_png, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return []
    H = img.shape[0]
    step = (1.0 / n_bands)
    ov = step * overlap
    spans = []
    y = 0.0
    while y < 1.0:
        spans.append((y, min(y + step + ov, 1.0)))
        y += step
    tls = threading.local()

    def _conv():
        conv = getattr(tls, "conv", None)
        if conv is None:
            conv = indra_ocr.load()
            tls.conv = conv
        return conv

    def _one(span):
        y0f, y1f = span
        return span, _band_text(_conv(), page_png, y0f, y1f)

    out: list[RowBand] = []
    seen_texts = set()
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(spans)))) as ex:
        for (y0f, y1f), md in ex.map(_one, spans):
            if not md:
                continue
            low = md.translate(AR2EN)
            matched = [k for k in keywords if k in low]
            if not matched:
                continue
            crop = _band_crop(page_png, y0f, y1f)
            key = (round(y0f, 3), matched[0])
            if key in seen_texts:
                continue
            seen_texts.add(key)
            out.append(RowBand(
                y0=int(H * y0f), y1=int(H * y1f), text=md,
                crop_png=crop, matched_keywords=matched,
            ))
    return out
