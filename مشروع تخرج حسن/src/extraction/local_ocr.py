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

import os
import re
from dataclasses import dataclass

AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

# digit groups with separators, e.g. "١٦,٦٦٥,٩١٩,٨٧٨" / "1,171,231,651"
_NUM_RUN = re.compile(r"[\d٠-٩۰-۹][\d٠-٩۰-۹,\.\u066b\u066c\u060c\s]*[\d٠-٩۰-۹]")
_MIN_DIGITS = 4  # ignore note refs like (11), years, small ints


@dataclass
class LocalPageRead:
    page: int            # document page number
    has_table: bool      # <table markup found in the markdown
    digits: set[str]     # normalized digit strings (>= 4 digits) seen on page
    text_len: int
    cf_hint: bool = False  # markdown mentions the cash-flow statement
    markdown: str = ""     # full page markdown (reused by notes_text & unit detection)


_CF_MARKERS = ("التدفقات النقديه", "التدفقات النقدية", "انشطه تشغيليه", "أنشطة تشغيلية")


def indra_available() -> bool:
    try:
        import indra_ocr  # noqa: F401

        return True
    except Exception:
        return False


def _digits_from_markdown(md: str) -> set[str]:
    from src.extraction.ocr_sanitizer import ocr_digit_sanitizer

    out = set()
    for tok in _NUM_RUN.findall(md or ""):
        d = re.sub(r"\D", "", tok.translate(AR_DIGITS))
        if len(d) >= _MIN_DIGITS:
            out.add(d)
        for v in ocr_digit_sanitizer(tok):
            s = f"{abs(v):.0f}"
            if len(s) >= _MIN_DIGITS:
                out.add(s)
    return out


import threading as _threading

_SHARED_CONV_LOCK = _threading.Lock()
_SHARED_CONV = None


def _is_cloud_host() -> bool:
    """Detect memory-constrained hosted containers (Streamlit Community Cloud ~2.7GB)."""
    return (
        os.path.exists("/mount/src")
        or os.getenv("HOME") == "/home/adminuser"
        or bool(os.getenv("STREAMLIT_SHARING_MODE"))
    )


def get_shared_converter():
    """Return a single process-wide Indra ONNX converter (~550MB) to prevent
    multi-instance OOM crashes on Streamlit Cloud and save load time."""
    global _SHARED_CONV
    with _SHARED_CONV_LOCK:
        if _SHARED_CONV is None:
            import indra_ocr

            _SHARED_CONV = indra_ocr.load()
        return _SHARED_CONV


def _default_workers() -> int:
    """LOCAL_OCR_WORKERS env override (default 4 locally, ALWAYS 1 on Streamlit Cloud).
    Each worker holds its own ONNX converter ≈ 500-800MB RAM — 4 workers peak ≈ 2.8GB
    and OOM-kill Streamlit Community Cloud containers."""
    env_val = os.getenv("LOCAL_OCR_WORKERS")
    if env_val is not None and env_val.strip():
        try:
            w = max(1, int(env_val.strip()))
            return 1 if _is_cloud_host() else w
        except (TypeError, ValueError):
            pass
    return 1 if _is_cloud_host() else 4


def read_pages(pngs: dict[int, bytes], workers: int | None = None) -> dict[int, LocalPageRead] | None:
    """OCR rendered page PNGs locally. Uses the shared singleton converter when
    workers == 1 (Streamlit Cloud low-RAM mode) or thread-local converters when
    workers > 1 on local desktops."""
    if not pngs or not indra_available():
        return None
    if workers is None:
        workers = _default_workers()
    try:
        import gc
        import threading
        from concurrent.futures import ThreadPoolExecutor

        items = list(pngs.items())
        reads: dict[int, LocalPageRead] = {}

        if workers <= 1 or len(items) <= 1:
            conv = get_shared_converter()
            for page, png in items:
                with _SHARED_CONV_LOCK:
                    md = _page_markdown(conv, png)
                if md is None:
                    continue
                reads[page] = LocalPageRead(
                    page=page,
                    has_table="<table" in md.lower(),
                    digits=_digits_from_markdown(md),
                    text_len=len(md),
                    cf_hint=any(m in md for m in _CF_MARKERS),
                    markdown=md,
                )
            gc.collect()
            return reads or None

        import indra_ocr

        tls = threading.local()

        def _conv():
            conv = getattr(tls, "conv", None)
            if conv is None:
                conv = indra_ocr.load()
                tls.conv = conv
            return conv

        def _one(item: tuple[int, bytes]) -> tuple[int, str | None]:
            page, png = item
            return page, _page_markdown(_conv(), png)

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
                    markdown=md,
                )
        return reads or None
    except Exception:
        return None


def _page_markdown(conv, png: bytes) -> str | None:
    """Markdown for one page image via a temp file; None on any failure.
    Downscales huge scans (>1600px) before ONNX inference so giant 10MB PDFs
    never trigger onnxruntime `bad allocation` or OOM on Streamlit Cloud."""
    import io
    import tempfile
    from pathlib import Path

    safe_png = png
    try:
        from PIL import Image

        im = Image.open(io.BytesIO(png))
        w, h = im.size
        if max(w, h) > 1600:
            scale = 1600.0 / max(w, h)
            im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, format="PNG")
            safe_png = buf.getvalue()
    except Exception:
        safe_png = png

    with tempfile.TemporaryDirectory(prefix="indra_") as td:
        p = Path(td) / "page.png"
        p.write_bytes(safe_png)
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


def capture_notes_text(raw: bytes, workers: int | None = None) -> dict[int, str] | None:
    """Read every page's TEXT locally with Indra (free) — feeds the notes RAG.

    Called AFTER the vision sweep so it never competes for quota: pure local
    CPU. Pages are rendered here in the main thread (pdfium is not
    thread-safe) then read in parallel workers with thread-local converters.
    Returns {page_number: markdown} or None on any failure.
    """
    if not indra_available():
        return None
    if workers is None:
        workers = _default_workers()
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

        if workers <= 1 or len(pngs) <= 1:
            import gc

            conv = get_shared_converter()
            out: dict[int, str] = {}
            for page, png in pngs.items():
                with _SHARED_CONV_LOCK:
                    md = _page_markdown(conv, png)
                if md and md.strip():
                    out[page] = md
            gc.collect()
            return out or None

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

        out = {}
        with ThreadPoolExecutor(max_workers=max(1, min(workers, len(items)))) as ex:
            for page, md in ex.map(_one, items):
                if md and md.strip():
                    out[page] = md
        return out or None
    except Exception:
        return None
