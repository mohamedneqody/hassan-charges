# -*- coding: utf-8 -*-
"""Document Source Profiler (مصنِّف مصدر المستند — المهمة 2).

The mere EXISTENCE of a text layer proves nothing: a scanned page run
through a hidden OCR pass carries a text layer that is garbage
(«buQirFcrtilizcna», «126188 707») — and trusting it produced the AbuQir
false acceptance. This profiler classifies the document and measures the
text layer with TESTABLE quality signals, producing an EvidenceQualityScore
that is INDEPENDENT of any model's self-reported confidence:

  - garbled-word ratio        words with digit/letter chaos inside
  - long-number integrity     financial magnitudes kept as ONE token
  - coordinate regularity     words snap to few column x-positions
  - year-header sanity        statement pages carry date-like headers
  - image/text overlap        a full-page image UNDER the text = hidden OCR
  - number-group continuity   labels are followed by plausible magnitudes

Classes: NATIVE_DIGITAL_PDF (trusted text), SEARCHABLE_SCANNED_PDF (text
layer present, quality low → NOT trusted), SCANNED_NO_TEXT, MIXED_PDF,
NATIVE_SPREADSHEET. The score gates the adaptive router, never any model's
own confidence.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

KIND_NATIVE_DIGITAL_PDF = "NATIVE_DIGITAL_PDF"
KIND_SEARCHABLE_SCANNED_PDF = "SEARCHABLE_SCANNED_PDF"
KIND_SCANNED_NO_TEXT = "SCANNED_NO_TEXT"
KIND_MIXED_PDF = "MIXED_PDF"
KIND_NATIVE_SPREADSHEET = "NATIVE_SPREADSHEET"

# a "garbled" word: alternates letters and digits chaotically, or is a
# letter-run with no vowels at all (OCR noise like «buQirFcrtilizcna»)
_GARBLED_RE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d._/\\-]{4,}$")
_VOWELLESS_RE = re.compile(r"^[bcdfghjklmnpqrstvwxyzBCDFGHJKLMNPQRSTVWXYZ]{7,}$")
_DATEISH_RE = re.compile(
    r"(?:\d{1,2}[\s/-]?(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    r"[\w\u0600-\u06FF]*[\s/-]?\d{4})"
    r"|(?:\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})"
    r"|(?:20\d{2})"
    r"|(?:١٩\d{2}|20\d{2})", re.IGNORECASE)
# a VALID printed magnitude: 1-3 digits then 3-digit groups (space OR comma
# separated), optionally decimals/parens — «2 354 490 447», «42,219,047,998»,
# «(12 470 407 550)». A broken hidden-OCR layer fragments or merges groups:
# «126188 707», «3511.0 467312.0» fail this pattern.
_MAGNITUDE_RE = re.compile(
    r"^\(?\d{1,3}(?:[, ]\d{3})*(?:\.\d+)?\)?$")
# fonts typical of hidden OCR layers (Tesseract's invisible-text font etc.)
_OCR_FONT_HINTS = ("glyphless", "hiddenocr", "invisible", "ocr")

TRUST_THRESHOLD = 0.60


@dataclass
class PageProfile:
    page: int
    has_text: bool
    chars: int
    garbled_ratio: float = 0.0
    long_number_integrity: float = 1.0
    coordinate_regularity: float = 0.0
    dateish_header: bool = False
    image_under_text: bool = False
    number_group_continuity: float = 0.0
    ocr_font_detected: bool = False


@dataclass
class DocumentProfile:
    kind: str
    pages_total: int = 0
    pages_with_text: int = 0
    quality_score: float = 0.0
    text_layer_trusted: bool = False
    metrics: dict = field(default_factory=dict)
    per_page: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "kind": self.kind, "pages_total": self.pages_total,
            "pages_with_text": self.pages_with_text,
            "quality_score": round(self.quality_score, 3),
            "text_layer_trusted": self.text_layer_trusted,
            "metrics": {k: round(v, 3) if isinstance(v, float) else v
                        for k, v in self.metrics.items()},
            "trust_threshold": TRUST_THRESHOLD,
        }


def _page_words(page) -> list[dict]:
    try:
        return page.extract_words() or []
    except Exception:
        return []


def _run_magnitudes(tokens: list[str]) -> list[str]:
    """Split a line's numeric tokens into candidate magnitudes: 1-3 digit
    fragments merge forward into space groups («2 354 490 447»), while
    complete tokens (comma-grouped or longer) stand alone — two year
    columns side by side are TWO magnitudes, never one."""
    mags: list[str] = []
    frag: list[str] = []
    for t in tokens:
        if re.fullmatch(r"\d{1,3}", t):
            frag.append(t)
        else:
            if frag:
                mags.append(" ".join(frag))
                frag = []
            mags.append(t)
    if frag:
        mags.append(" ".join(frag))
    return mags


def profile_page(page, page_no: int) -> PageProfile:
    words = _page_words(page)
    text = " ".join(w["text"] for w in words)
    pp = PageProfile(page=page_no, has_text=bool(text.strip()),
                     chars=len(text))
    if not words:
        return pp
    alpha_words = [w["text"] for w in words
                   if re.search(r"[A-Za-z]", w["text"])]
    if alpha_words:
        garbled = sum(1 for w in alpha_words
                      if (_GARBLED_RE.match(w) or _VOWELLESS_RE.match(w)))
        pp.garbled_ratio = garbled / len(alpha_words)
    # magnitude-pattern validity: numeric token RUNS on a line must join
    # into a valid printed magnitude (1-3 digits + 3-digit groups). A
    # broken hidden-OCR layer fragments/merges groups and fails this.
    lines: dict[int, list[str]] = {}
    for w in words:
        lines.setdefault(round(w["top"]), []).append(w["text"])
    valid = invalid = 0
    for toks in lines.values():
        num_toks = [t for t in toks if re.fullmatch(r"[\d,.]+", t)]
        for m in _run_magnitudes(num_toks):
            digits = re.sub(r"\D", "", m).rstrip("0") or "0"
            if _MAGNITUDE_RE.match(m) and len(digits) >= 3:
                valid += 1
            else:
                invalid += 1
    if valid + invalid:
        pp.long_number_integrity = valid / (valid + invalid)
    # font-based hidden-OCR detection (Tesseract's GlyphLessFont & friends)
    try:
        fonts = {c.get("fontname", "") for c in (page.chars or [])}
    except Exception:
        fonts = set()
    pp.ocr_font_detected = any(
        any(h in (f or "").lower() for h in _OCR_FONT_HINTS) for f in fonts)
    # coordinate regularity: real tables snap words to few x positions
    xs = sorted(round(w["x0"] / 3) * 3 for w in words)
    if xs:
        clusters = 1
        for a, b in zip(xs, xs[1:]):
            if b - a > 6:
                clusters += 1
        pp.coordinate_regularity = min(1.0, 12 / clusters) if clusters else 0.0
    pp.dateish_header = bool(_DATEISH_RE.search(text[:600]))
    try:
        imgs = page.images or []
    except Exception:
        imgs = []
    if imgs and words:
        pw, ph = float(page.width), float(page.height)
        for im in imgs:
            x0, x1 = float(im.get("x0", 0)), float(im.get("x1", 0))
            y0, y1 = float(im.get("top", 0)), float(im.get("bottom", 0))
            if (x1 - x0) >= 0.8 * pw and (y1 - y0) >= 0.8 * ph:
                pp.image_under_text = True     # full-page image UNDER text
                break
    # number-group continuity: lines where a label is followed by a plausible
    # magnitude — the numeric RUN is joined first so space-grouped numbers
    # («42 219 047 998») count as one coherent magnitude, while stray
    # fragments («3.0 -6.0») do not.
    fin_lines = 0
    for toks in lines.values():
        num_toks = [t for t in toks[1:] if re.fullmatch(r"[\d,.()]+", t)]
        num_toks = [t.strip("()") for t in num_toks if t.strip("()")]
        for m in _run_magnitudes(num_toks):
            digits = re.sub(r"\D", "", m)
            if _MAGNITUDE_RE.match(m) and len(digits) >= 4:
                fin_lines += 1
                break
    pp.number_group_continuity = fin_lines / len(lines) if lines else 0.0
    return pp


def profile_pdf(pdf) -> DocumentProfile:
    """Profile an already-open pdfplumber document (uses .pages)."""
    try:
        pages_src = list(pdf.pages)
    except Exception:
        pages_src = []
    pages: list[PageProfile] = []
    n = len(pages_src)
    for i, page in enumerate(pages_src[:40]):   # bounded profile: first 40
        try:
            pages.append(profile_page(page, i + 1))
        except Exception:
            pages.append(PageProfile(page=i + 1, has_text=False, chars=0))
    text_pages = [p for p in pages if p.has_text]
    with_text_ratio = len(text_pages) / len(pages) if pages else 0.0
    if not text_pages:
        prof = DocumentProfile(kind=KIND_SCANNED_NO_TEXT,
                               pages_total=n, pages_with_text=0)
        prof.quality_score = 0.0
        return prof

    def mean(key: str) -> float:
        vals = [getattr(p, key) for p in text_pages]
        return sum(vals) / len(vals) if vals else 0.0

    garbled = mean("garbled_ratio")
    integrity = mean("long_number_integrity")
    coord = mean("coordinate_regularity")
    continuity = mean("number_group_continuity")
    dateish_ratio = (sum(1 for p in text_pages if p.dateish_header)
                     / len(text_pages))
    hidden_ocr_ratio = (sum(1 for p in text_pages if p.image_under_text)
                        / len(text_pages))
    ocr_font_ratio = (sum(1 for p in text_pages if p.ocr_font_detected)
                      / len(text_pages))

    quality = (
        0.35 * integrity
        + 0.25 * max(0.0, 1.0 - garbled)
        + 0.10 * coord
        + 0.10 * dateish_ratio
        + 0.10 * min(1.0, continuity * 3)
        + 0.05 * (0.0 if hidden_ocr_ratio > 0.5 else 1.0)
        + 0.05 * (0.0 if ocr_font_ratio > 0.5 else 1.0)
    )
    # trust = quality score AND the two financial-coherence floors — a
    # hidden-OCR layer with realistic pseudo-words still fragments the
    # magnitudes and scatters the number groups, and that is exactly the
    # layer that must never auto-decide values
    text_layer_trusted = (
        hidden_ocr_ratio <= 0.5 and ocr_font_ratio <= 0.5
        and quality >= TRUST_THRESHOLD
        and integrity >= 0.50          # magnitude-validity floor
        and continuity >= 0.25         # number-group-continuity floor
    )
    if with_text_ratio < 0.85:
        kind = KIND_MIXED_PDF
    elif text_layer_trusted:
        kind = KIND_NATIVE_DIGITAL_PDF
    else:
        kind = KIND_SEARCHABLE_SCANNED_PDF
    prof = DocumentProfile(
        kind=kind, pages_total=n, pages_with_text=len(text_pages),
        quality_score=quality, text_layer_trusted=text_layer_trusted,
        metrics={
            "garbled_word_ratio": garbled,
            "magnitude_validity": integrity,
            "coordinate_regularity": coord,
            "year_header_sanity": dateish_ratio,
            "image_text_overlap": hidden_ocr_ratio,
            "number_group_continuity": continuity,
            "ocr_font_ratio": ocr_font_ratio,
        },
        per_page=[{"page": p.page, "chars": p.chars,
                   "garbled": round(p.garbled_ratio, 3)} for p in pages],
    )
    return prof


def worst_text_pages(profile: DocumentProfile, budget: int = 12) -> list[int]:
    """The pages whose text is LOWEST quality (the router's local re-read
    targets), highest damage first, within the budget."""
    ranked = sorted(profile.per_page, key=lambda p: (p["garbled"], -p["chars"]))
    return [p["page"] for p in ranked[:budget]]
