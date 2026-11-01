"""Optional local OCR pre-layer (Indra OCR) — page triage + number cross-check.

Zero-API-cost helper used inside the scanned-PDF vision path when `indra-ocr`
is importable in the environment. Two jobs:

1. Triage: which rendered pages contain TABLE markup — those pages are sent
   to Gemini first so the early-stop ("core statements complete") fires
   before note/signature pages ever consume quota.
2. Second opinion: digit strings read locally are compared against captured
   values; a clean local match marks a value verified without a paid call.

Never required: every entry point degrades to a silent no-op (returns None)
when the package, its models, or its CLI are unavailable or fail — the Gemini
pipeline behaves exactly as before.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

# digit groups with separators, e.g. "١٦,٦٦٥,٩١٩,٨٧٨" / "1,171,231,651"
_NUM_RUN = re.compile(r"[\d٠-٩][\d٠-٩,\.\u066c\s]*[\d٠-٩]")
_MIN_DIGITS = 4  # ignore note refs like (11), years, small ints


@dataclass
class LocalPageRead:
    page: int            # document page number
    has_table: bool      # <table markup found in the markdown
    digits: set[str]     # normalized digit strings (>= 4 digits) seen on page
    text_len: int
    cf_hint: bool = False  # markdown mentions the cash-flow statement


_CF_MARKERS = ("التدفقات النقديه", "التدفقات النقدية", "انشطه تشغيليه", "أنشطة تشغيلية")


def indra_available() -> bool:
    try:
        import indra_ocr  # noqa: F401

        return True
    except Exception:
        return False


def _digits_from_markdown(md: str) -> set[str]:
    out = set()
    for tok in _NUM_RUN.findall(md or ""):
        d = re.sub(r"\D", "", tok.translate(AR_DIGITS))
        if len(d) >= _MIN_DIGITS:
            out.add(d)
    return out


def read_pages(pngs: dict[int, bytes], workers: int = 4) -> dict[int, LocalPageRead] | None:
    """OCR rendered page PNGs locally, in parallel. Returns {page: LocalPageRead}
    or None on ANY failure (missing package, model error, timeout) — caller
    treats None as 'no local layer' and proceeds Gemini-only.

    Each worker thread owns its own converter instance: the ONNX session is
    thread-safe but the image-pipeline around it is not, and a serial loop
    cost ~2-4s per page before the first API call ever fired (22 pages ≈ a
    whole minute of local OCR). 4 workers cut that to roughly a quarter.
    """
    if not pngs or not indra_available():
        return None
    try:
        import threading
        from concurrent.futures import ThreadPoolExecutor

        import indra_ocr

        tls = threading.local()

        def _conv():
            conv = getattr(tls, "conv", None)
            if conv is None:
                conv = indra_ocr.load()
                tls.conv = conv
            return conv

        items = list(pngs.items())

        def _one(item: tuple[int, bytes]) -> tuple[int, str | None]:
            page, png = item
            return page, _page_markdown(_conv(), png)

        reads: dict[int, LocalPageRead] = {}
        with ThreadPoolExecutor(max_workers=max(1, min(workers, len(items)))) as ex:
            for page, md in ex.map(_one, items):
                if md is None:
                    continue
                reads[page] = LocalPageRead(
                    page=page,
                    has_table="<table" in md.lower(),
                    digits=_digits_from_markdown(md),
                    text_len=len(md),
                    cf_hint=any(m in md for m in _CF_MARKERS),
                )
        return reads or None
    except Exception:
        return None


def _page_markdown(conv, png: bytes) -> str | None:
    """Markdown for one page image via a temp file; None on any failure."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory(prefix="indra_") as td:
        p = Path(td) / "page.png"
        p.write_bytes(png)
        try:
            for _i, pg in conv.convert(str(p)):
                return getattr(pg, "markdown", "") or ""
        except Exception:
            return None
    return None


def confirms(reads: dict[int, LocalPageRead] | None, page: int, value: float) -> bool:
    """True when the local read of `page` contains exactly this number."""
    if not reads:
        return False
    lr = reads.get(page)
    if lr is None:
        return False
    return f"{abs(value):.0f}" in lr.digits


def capture_notes_text(raw: bytes, workers: int = 4) -> dict[int, str] | None:
    """Read every page's TEXT locally with Indra (free) — feeds the notes RAG.

    Called AFTER the vision sweep so it never competes for quota: pure local
    CPU. Pages are rendered here in the main thread (pdfium is not
    thread-safe) then read in parallel workers with thread-local converters.
    Returns {page_number: markdown} or None on any failure.
    """
    if not indra_available():
        return None
    try:
        import io
        import threading
        from concurrent.futures import ThreadPoolExecutor

        import pypdfium2 as pdfium
        import indra_ocr

        doc = pdfium.PdfDocument(io.BytesIO(raw))
        total = len(doc)
        if total == 0:
            return None
        pngs: dict[int, bytes] = {}
        for page in range(1, total + 1):
            buf = io.BytesIO()
            doc[page - 1].render(scale=1.6).to_pil().save(buf, format="PNG")
            pngs[page] = buf.getvalue()
        doc.close()

        tls = threading.local()

        def _conv():
            conv = getattr(tls, "conv", None)
            if conv is None:
                conv = indra_ocr.load()
                tls.conv = conv
            return conv

        items = list(pngs.items())

        def _one(item: tuple[int, bytes]):
            page, png = item
            return page, _page_markdown(_conv(), png)

        out: dict[int, str] = {}
        with ThreadPoolExecutor(max_workers=max(1, min(workers, len(items)))) as ex:
            for page, md in ex.map(_one, items):
                if md and md.strip():
                    out[page] = md
        return out or None
    except Exception:
        return None
