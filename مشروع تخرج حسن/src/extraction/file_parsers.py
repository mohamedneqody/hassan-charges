"""File readers: turn uploaded bytes into DataFrames for the normalizer.

Supported: .csv, .xlsx, .xls (pandas + openpyxl/xlrd), .pdf (pdfplumber).
PDF parsing tries embedded tables first, then falls back to text lines.
"""
from __future__ import annotations

import io
import re

import pandas as pd

from src.exceptions import EmptyFileError, ExtractionError, UnsupportedFormatError
from src.extraction.normalizer import (
    FinancialData,
    extract_year,
    merge_parsed,
    parse_number,
    parse_table,
    parse_table_full,
    reconcile,
)


def _currency_hint_from_frames(frames: list[pd.DataFrame]) -> str | None:
    """Scan string cells for a currency keyword (جنيه / EGP / ريال / دولار...)."""
    from src.extraction.vision_ocr import _currency_hint

    seen = 0
    for frame in frames:
        for cell in frame.astype(str).values.ravel():
            low = str(cell).lower()
            for keyword in ("جنيه", "ج.م", "egp", "ريال", "دولار", "درهم", "دينار", "يورو"):
                if keyword in low:
                    hint = _currency_hint(low)
                    if hint:
                        return hint
            seen += 1
            if seen > 4000:  # bounded scan
                return None
    return None


# Cells that mention شركة but are statement/document titles, not a name.
_COMPANY_BLOCKLIST = ("القوائم", "الميزانية", "قائمة", "تقرير", "الملحق", "الإيضاحات")


def _company_hint_from_frames(frames: list[pd.DataFrame]) -> str | None:
    """First cell that looks like a company name (شركة / لشركة …).

    The study needs the REAL company identity, not the file name — EGX
    disclosures print «شركة …» in a header cell of the first sheet/page.
    """
    seen = 0
    for frame in frames:
        for cell in frame.astype(str).values.ravel():
            text = " ".join(str(cell).split())
            if "شركة" in text and 10 <= len(text) <= 90:
                if not any(block in text for block in _COMPANY_BLOCKLIST):
                    return text
            seen += 1
            if seen > 4000:  # bounded scan
                return None
    return None

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Adaptive routing helpers (المهمة 3 — source-aware document routing)
# ---------------------------------------------------------------------------

# budgets (frozen policy parameters — documented, never unlimited)
LOCAL_REREAD_MAX_PAGES = 12
VISION_FALLBACK_DEFAULT_MAX_PAGES = 6


def _profile_pdf_bytes(raw: bytes):
    """Document Source Profiler over the raw PDF bytes (None on failure)."""
    try:
        import pdfplumber

        from src.extraction.document_profiler import profile_pdf

        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            return profile_pdf(pdf)
    except Exception:
        return None


def _adaptive_local_reread(raw: bytes, profile, notes: list[str]) -> tuple[
        list[dict[int, dict[str, float]]], list[list[dict]]]:
    """Free Spatial-Local-OCR re-read of the WORST-profiled pages (a layer
    genuinely independent from the embedded text). Pure-local: zero API."""
    out_parts: list[dict[int, dict[str, float]]] = []
    out_caps: list[list[dict]] = []
    try:
        import threading
        from concurrent.futures import ThreadPoolExecutor

        import indra_ocr
        import pypdfium2 as pdfium

        from src.extraction.document_profiler import worst_text_pages
        from src.extraction.local_ocr import indra_available

        if not indra_available():
            notes.append("Adaptive routing: local Indra OCR unavailable — "
                         "local re-read skipped.")
            return out_parts, out_caps
        pages = worst_text_pages(profile, budget=LOCAL_REREAD_MAX_PAGES)
        pdf = pdfium.PdfDocument(io.BytesIO(raw))
        pngs: dict[int, bytes] = {}
        for pno in pages:
            if pno - 1 < len(pdf):
                pngs[pno] = pdf[pno - 1].render(scale=2.0).to_pil().tobytes()
        tls = threading.local()

        def _conv():
            conv = getattr(tls, "conv", None)
            if conv is None:
                conv = indra_ocr.load()
                tls.conv = conv
            return conv

        from src.extraction.local_ocr import _page_markdown

        def _read(item: tuple[int, bytes]):
            pno, png = item
            return pno, _page_markdown(_conv(), png)

        md: dict[int, str | None] = {}
        for _attempt in range(2):              # the local model load is
            try:                               # occasionally flaky (OpenBLAS)
                md = {}
                with ThreadPoolExecutor(max_workers=4) as ex:
                    for pno, text in ex.map(_read, pngs.items()):
                        md[pno] = text
                break
            except Exception as exc:
                if _attempt == 1:
                    notes.append(f"Local re-read failed twice: {exc}")
        for pno in pages:
            text = md.get(pno)
            if not text:
                continue
            try:
                frames = _parse_pdf_text_lines(text.splitlines())
            except Exception:
                continue
            for frame in frames:
                try:
                    result, caps = parse_table_full(frame)
                except Exception:
                    continue
                if result:
                    out_parts.append(result)
                    out_caps.append(caps)
        notes.append(
            f"Adaptive routing: local spatial re-read of {len(pages)} "
            f"worst-text pages → {len(out_parts)} extra tables (layer "
            "local_ocr, zero API).")
    except Exception as exc:
        notes.append(f"Adaptive local re-read failed: {type(exc).__name__}: "
                     f"{str(exc)[:120]}")
    return out_parts, out_caps


# ── وحدة الطباعة (المهمة 1 من جولة الإصلاح) ─────────────────────────────
# القوائم تطبع ترويسة الوحدة («in EGP Thousands» / «بآلاف الجنيهات» /
# «L.E. '000» / «EGP millions»). القيم المخزنة تبقى كما طُبعت حرفيًا؛
# المقياس المكتشف يستخدم للعرض فقط، والدليل يُسجل في unit_note.
_UNIT_HEADER_RULES: list[tuple[str, int, str]] = [
    (r"\begp\s+thousands\b", 1000,
     "جميع القيم بآلاف الجنيهات (in EGP Thousands) — من ترويسة القائمة"),
    (r"\begp\W{0,2}0{3}\b", 1000,
     "وحدة الطباعة EGP ‘000 — من ترويسة القائمة"),
    (r"\bl\.?e\.?\s*[‘’’]?\s*0{3}\b", 1000,
     "وحدة الطباعة L.E. ‘000 — من ترويسة القائمة"),
    (r"بآلاف\s+الجنيهات|قيم.*?بآلاف", 1000,
     "وحدة الطباعة: بآلاف الجنيهات — من ترويسة القائمة"),
    (r"بالآلاف", 1000, "وحدة الطباعة: بالآلاف — من ترويسة القائمة"),
    (r"\begp\s+millions\b", 1_000_000,
     "جميع القيم بملايين الجنيهات (in EGP millions) — من ترويسة القائمة"),
    (r"بملايين\s+الجنيهات", 1_000_000,
     "وحدة الطباعة: بملايين الجنيهات — من ترويسة القائمة"),
]


def detect_printed_unit(texts) -> tuple[int, str]:
    """Scan page texts for the printed unit header. Returns (scale, note);
    (1, "") when nothing printed — the display then treats values as units."""
    import re as _re
    for text in texts:
        if not text:
            continue
        for pattern, scale, note in _UNIT_HEADER_RULES:
            if _re.search(pattern, text, _re.IGNORECASE):
                return scale, note
    return 1, ""


def _apply_printed_unit(data, raw: bytes, notes: list[str]) -> None:
    """Detect + attach the printed unit on an extracted FinancialData.
    Sources, in order: the captured notes_text, then a cheap pdfplumber
    read of the first pages (where statement headers live)."""
    texts = [t for t in (getattr(data, "notes_text", {}) or {}).values()]
    if not texts:
        try:
            import pdfplumber
            import io as _io
            with pdfplumber.open(_io.BytesIO(raw)) as pdf:
                texts = [(pg.extract_text() or "")
                         for pg in pdf.pages[:4]]
        except Exception:
            texts = []
    scale, unit_note = detect_printed_unit(texts)
    data.unit_scale = scale
    data.unit_note = unit_note
    if scale != 1:
        notes.append(
            f"وحدة الطباعة: القيم المخزنة كما طُبعت ({unit_note}) — العرض "
            f"يضربها في {scale} لإظهار القيمة الفعلية. لا تغيير في القيم "
            "المخزنة ولا في قواعد المطابقة.")


def _vision_fallback(raw: bytes, profile, notes: list[str]):
    """Focused vision re-read — GOVERNED: requires ENABLE_VISION_FALLBACK=1,
    a usable key pool, and stays inside VISION_FALLBACK_MAX_PAGES. When the
    flag is off or the pool is empty the run continues locally and the
    BLOCKED decision is recorded (never key-rotating past service limits)."""
    import os

    if os.getenv("ENABLE_VISION_FALLBACK") != "1":
        notes.append("Vision fallback BLOCKED: ENABLE_VISION_FALLBACK flag "
                     "is off — continuing with local layers only.")
        return None
    try:
        from src.ai.gemini_agent import get_pool

        pool = get_pool()
        if not pool.has_usable_pairs():
            notes.append("Vision fallback BLOCKED: no usable (key, model) "
                         "pairs in the pool — continuing locally.")
            return None
        budget = int(os.getenv("VISION_FALLBACK_MAX_PAGES",
                               str(VISION_FALLBACK_DEFAULT_MAX_PAGES)))
        from src.extraction.document_profiler import worst_text_pages
        from src.extraction.vision_ocr import extract_via_vision

        pages = worst_text_pages(profile, budget=budget)
        page_range = (min(pages) - 1, max(pages))
        notes.append(f"Vision fallback: {len(pages)} pages (budget "
                     f"{budget}) via the governed pool, fast_mode.")
        return extract_via_vision(raw, [], page_range=page_range,
                                  fast_mode=True)
    except Exception as exc:
        notes.append(f"Vision fallback failed (BLOCKED): "
                     f"{type(exc).__name__}: {str(exc)[:140]}")
        return None


def _financialdata_to_parts(data) -> tuple[
        list[dict[int, dict[str, float]]], list[list[dict]]]:
    """Flatten a FinancialData's captured values back into (parts, captures)
    so the adaptive merge can route its candidates through merge_parsed with
    the right layer metadata."""
    part: dict[int, dict[str, float]] = {}
    caps: list[dict] = []
    for field, by_year in (getattr(data, "candidates", {}) or {}).items():
        for year, cands in by_year.items():
            if cands:
                v = cands[0][0]
                if v is not None:
                    part.setdefault(year, {})[field] = v
                    caps.append({"field": field, "year": year,
                                 "value": v, "label_text": "",
                                 "row": None, "col": None,
                                 "transposed": False})
    return ([part] if part else []), (caps if part else [])


def _adaptive_local_reread_scan(raw: bytes, notes: list[str]) -> tuple[
        list[dict[int, dict[str, float]]], list[list[dict]], dict,
        dict[int, bytes]]:
    """Local re-read for PURE scans (no text layer): the first
    LOCAL_REREAD_MAX_PAGES pages through local Indra OCR (zero API) — the
    degradation path when the vision layer is BLOCKED."""
    out_parts: list[dict[int, dict[str, float]]] = []
    out_caps: list[list[dict]] = []
    out_sources: dict[str, list[int]] = {}
    try:
        import threading
        from concurrent.futures import ThreadPoolExecutor

        import indra_ocr
        import pypdfium2 as pdfium

        from src.extraction.local_ocr import indra_available, _page_markdown

        if not indra_available():
            notes.append("Local-only degradation impossible: local Indra "
                         "OCR unavailable.")
            return out_parts, out_caps, out_sources, {}
        pdf = pdfium.PdfDocument(io.BytesIO(raw))
        pages = list(range(1, min(len(pdf), LOCAL_REREAD_MAX_PAGES) + 1))
        import io as _io

        pngs: dict[int, bytes] = {}
        for p in pages:
            if p - 1 < len(pdf):
                buf = _io.BytesIO()
                pdf[p - 1].render(scale=2.0).to_pil().convert("RGB")                     .save(buf, format="PNG")           # ENCODED png — the
                pngs[p] = buf.getvalue()               # reader needs a file

        tls = threading.local()

        def _conv():
            conv = getattr(tls, "conv", None)
            if conv is None:
                conv = indra_ocr.load()
                tls.conv = conv
            return conv

        def _read(item: tuple[int, bytes]):
            pno, png = item
            return pno, _page_markdown(_conv(), png)

        md: dict[int, str | None] = {}
        for _attempt in range(2):              # the local model load is
            try:                               # occasionally flaky (OpenBLAS)
                md = {}
                with ThreadPoolExecutor(max_workers=4) as ex:
                    for pno, text in ex.map(_read, pngs.items()):
                        md[pno] = text
                break
            except Exception as exc:
                if _attempt == 1:
                    notes.append(f"Local re-read failed twice: {exc}")
        import re as _tag_re

        for pno in pages:
            text = md.get(pno)
            if not text:
                continue
            # Indra's markdown wraps tables in HTML tags — the tag words
            # («tr», «th», «colspan») would be counted as label words and
            # the year header rejected. Strip the tags; cell boundaries
            # become plain spaces and the line parser sees clean rows.
            text = _tag_re.sub(r"<[^>]+>", " ", text)
            try:
                frames = _parse_pdf_text_lines(text.splitlines())
            except Exception:
                continue
            for frame in frames:
                try:
                    result, caps = parse_table_full(frame)
                except Exception:
                    continue
                if result:
                    out_parts.append(result)
                    out_caps.append(caps)
                    for cap in caps:     # page provenance for the focused pass
                        f = cap.get("field")
                        if f:
                            out_sources.setdefault(f, [])
                            if pno not in out_sources[f]:
                                out_sources[f].append(pno)
        notes.append(
            f"Local-only degradation: Indra re-read of pages {pages[0]}-"
            f"{pages[-1]} → {len(out_parts)} tables (layer local_ocr, zero "
            "API) — values stay GATED until a trusted layer or a human "
            "review confirms them.")
    except Exception as exc:
        notes.append(f"Local-only degradation failed: {type(exc).__name__}: "
                     f"{str(exc)[:120]}")
    return out_parts, out_caps, out_sources, locals().get("pngs", {}) or {}


def load_financial_data(file_name: str, raw: bytes, progress_cb=None, page_range=None, fast_mode: bool = False) -> FinancialData:
    """Main entry: bytes -> canonical FinancialData. Raises AppError subclasses.
    `fast_mode` (scanned PDFs only) skips the paid verification layers —
    one sweep, ~half the calls, for initial triage of many files."""
    ext = "." + file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    if ext not in {".pdf", ".csv", ".xlsx", ".xls"}:
        raise UnsupportedFormatError()
    if not raw:
        raise EmptyFileError()

    from src.extraction.provenance import (
        SOURCE_NATIVE_PDF_TEXT, SOURCE_NATIVE_SPREADSHEET_CELL,
        SOURCE_SCANNED_OCR,
    )

    pdf_profile = None
    if ext == ".pdf":
        # Scanned PDF? Skip pdfplumber entirely — extracting tables/text from
        # a scan yields nothing and only adds seconds before the vision path.
        from src.extraction.vision_ocr import extract_via_vision, is_scanned_pdf

        if is_scanned_pdf(file_name, raw):
            try:
                return extract_via_vision(raw, [], progress_cb=progress_cb,
                                          page_range=page_range,
                                          fast_mode=fast_mode)
            except Exception as exc:
                # Adaptive-routing completion (المهمة 3): when the vision
                # layer is unavailable (quota/503/no pool) the run CONTINUES
                # LOCALLY with BLOCKED recorded — a pure scan must not kill
                # the whole extraction. Values stay gated (no trusted layer).
                notes = [f"Vision path BLOCKED: {type(exc).__name__}: "
                         f"{str(exc)[:160]}"]
                from src.extraction.document_profiler import (
                    DocumentProfile, KIND_SCANNED_NO_TEXT,
                )
                pdf_profile = DocumentProfile(
                    kind=KIND_SCANNED_NO_TEXT, pages_total=0,
                    pages_with_text=0, quality_score=0.0,
                    text_layer_trusted=False)
                local_parts, local_caps, local_sources, local_pngs =                     _adaptive_local_reread_scan(raw, notes)
                if not local_parts:
                    raise
                data = merge_parsed(local_parts, notes,
                                    captures_per_part=local_caps,
                                    part_layers=["local_ocr"] * len(local_parts))
                data.document_profile = pdf_profile.as_dict()
                data.extraction_source = SOURCE_SCANNED_OCR
                data.field_sources = local_sources
                reconcile(data)
                # the focused local pass applies here too: cross-cell band
                # reads strengthen/contradict within the SAME layer, so no
                # attestation is possible (single layer) — candidates only
                try:
                    from src.extraction.vision_ocr import (
                        _focused_local_cell_verification,
                    )

                    _focused_local_cell_verification(
                        data, raw,
                        getattr(data, "field_sources", {}) or {},
                        {"years": sorted(data.years)},
                        sorted(local_pngs), list(local_pngs.values()), notes)
                except Exception:
                    pass
                return data
        frames, notes = _load_pdf(raw)
        pdf_profile = _profile_pdf_bytes(raw)
    elif ext == ".csv":
        frames, notes = _load_csv(raw)
        named_frames = [("CSV", f) for f in frames]
        from src.extraction.provenance import file_sha256 as _sha
        evidence_bundle: dict | None = {"file_sha256": _sha(raw), "cell_meta": {}}
    else:
        named_frames, notes, evidence_bundle = _load_excel_with_evidence(raw, ext)
        frames = [f for _name, f in named_frames]

    from src.extraction.provenance import (
        CellEvidence, sniff_consolidation, sniff_scale_words,
    )

    try:
        import openpyxl  # noqa: F401  (column-letter helper below)
    except Exception:  # pragma: no cover
        openpyxl = None

    parts: list[dict[int, dict[str, float]]] = []
    captures_per_part: list[list[dict]] = []
    part_layers: list[str] = []
    evidences: list[dict] = []
    if ext == ".pdf":
        for frame in frames:
            try:
                result, caps = parse_table_full(frame)
                parts.append(result)
                captures_per_part.append(caps)
                part_layers.append("text")
            except Exception as exc:  # a broken table must not kill the run
                notes.append(f"Skipped an unparseable table: {exc}")
    else:
        for sheet_name, frame in named_frames:
            try:
                result, captures = parse_table_full(frame)
            except Exception as exc:  # a broken table must not kill the run
                notes.append(f"Skipped an unparseable table: {exc}")
                continue
            parts.append(result)
            meta = (evidence_bundle or {}).get("cell_meta", {}).get(
                sheet_name, {})
            band = _sheet_band_text(frame)
            for cap in captures:
                if cap.get("transposed"):
                    # rotated layout: the address mapping degrades — record
                    # the source but let the checklist refuse the address
                    ev = CellEvidence(
                        source=SOURCE_NATIVE_SPREADSHEET_CELL,
                        file_sha256=(evidence_bundle or {}).get("file_sha256"),
                        file_name=file_name, sheet=sheet_name or None,
                        cell_address=None, label_text=cap["label_text"],
                        year=cap["year"],
                        data_type=("formula_cached" if meta.get(
                            (cap["row"], cap["col"]), {}).get("data_type")
                            == "formula_cached" else "value"),
                        unit_hint=sniff_scale_words(band),
                        consolidation=sniff_consolidation(band),
                        extra={"transposed": True},
                    )
                else:
                    m = meta.get((cap["row"], cap["col"]), {})
                    data_type = m.get("data_type", "value")
                    ev = CellEvidence(
                        source=SOURCE_NATIVE_SPREADSHEET_CELL,
                        file_sha256=(evidence_bundle or {}).get("file_sha256"),
                        file_name=file_name, sheet=sheet_name or None,
                        cell_address=(
                            f"{openpyxl.utils.get_column_letter(cap['col'])}"
                            f"{cap['row']}")
                        if cap["col"] and cap["row"] else None,
                        label_text=cap["label_text"], year=cap["year"],
                        data_type=data_type,
                        cached_formula=bool(m.get("cached_formula")),
                        unit_hint=sniff_scale_words(band),
                        consolidation=sniff_consolidation(band),
                        extra={"number_format": m.get("number_format")},
                    )
                evidences.append({**ev.as_dict(),
                                  "field": cap["field"], "year": cap["year"]})

    if not parts and ext == ".pdf":
        # No text/tables at all → scanned PDF: render → OpenCV cleanup →
        # Gemini vision OCR, into the same matching + reconciliation pipeline.
        from src.extraction.vision_ocr import extract_via_vision

        return extract_via_vision(raw, notes, progress_cb=progress_cb,
                                  page_range=page_range, fast_mode=fast_mode)

    if not parts:
        raise ExtractionError("no readable tables were found.")

    # ── Adaptive extraction routing (التوجيه التكيفي — المهمة 3) ────────────
    # The profiler decides whether the text layer may auto-decide values.
    # Untrusted layer → (1) values stay gated, (2) the WORST pages get a
    # free local Indra re-read (a genuinely different layer whose agreement
    # with anything counts), (3) focused vision ONLY behind the
    # ENABLE_VISION_FALLBACK flag, a page budget and a usable key pool —
    # never unlimited, never key-rotating past service limits. When vision
    # is unavailable the run CONTINUES locally and records BLOCKED.
    pdf_profile = pdf_profile if ext == ".pdf" else None
    if ext == ".pdf" and pdf_profile is not None:
        data_profile = pdf_profile.as_dict()
        notes.append(
            f"Document profile: {pdf_profile.kind} — text quality "
            f"{pdf_profile.quality_score:.2f} (magnitude validity "
            f"{pdf_profile.metrics.get('magnitude_validity', 0):.2f}, "
            f"continuity {pdf_profile.metrics.get('number_group_continuity', 0):.2f}) "
            f"→ text layer {'TRUSTED' if pdf_profile.text_layer_trusted else 'NOT trusted'}")
        if not pdf_profile.text_layer_trusted:
            local_parts, local_caps = _adaptive_local_reread(raw, pdf_profile,
                                                             notes)
            parts.extend(local_parts)
            captures_per_part.extend(local_caps)
            part_layers.extend(["local_ocr"] * len(local_parts))
            vision_data = _vision_fallback(raw, pdf_profile, notes)
            if vision_data is not None:
                # the vision reading is the ONLY trusted layer here — its
                # candidates go FIRST so first-wins prefers them
                v_parts, v_caps = _financialdata_to_parts(vision_data)
                parts = v_parts + parts
                captures_per_part = v_caps + captures_per_part
                part_layers = ["vision"] * len(v_parts) + part_layers
    else:
        data_profile = {}

    data = merge_parsed(parts, notes, evidences=evidences,
                        captures_per_part=captures_per_part,
                        part_layers=part_layers)
    if ext == ".pdf":
        # UNKNOWN source is UNTRUSTED by default (المهمة 6): a PDF whose
        # profiling failed gets no trust — its values stay on the gated
        # ladder until a layer proves otherwise
        data.document_profile = data_profile or {
            "kind": "UNKNOWN_PDF", "text_layer_trusted": False,
            "note": "profiling failed — untrusted by default"}
        data.extraction_source = (SOURCE_NATIVE_PDF_TEXT
                                  if data_profile.get("text_layer_trusted")
                                  else SOURCE_SCANNED_OCR)
    else:
        data.document_profile = {"kind": "NATIVE_SPREADSHEET",
                                 "text_layer_trusted": False,
                                 "note": "spreadsheet values are decided by "
                                         "the VERIFIED_SOURCE_EXACT evidence "
                                         "checklist, not by layer trust"}
        data.extraction_source = SOURCE_NATIVE_SPREADSHEET_CELL
    reconcile(data)
    data.currency_hint = _currency_hint_from_frames(frames)
    data.company_hint = _company_hint_from_frames(frames)
    _apply_printed_unit(data, raw, notes)
    return data


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

def _load_csv(raw: bytes) -> tuple[list[pd.DataFrame], list[str]]:
    notes: list[str] = []
    text: str | None = None
    for encoding in ("utf-8-sig", "cp1256", "latin-1"):
        try:
            text = raw.decode(encoding)
            if encoding != "utf-8-sig":
                notes.append(f"File decoded using {encoding} encoding.")
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ExtractionError("could not decode the CSV file.")

    # Parse rows with the csv module (handles quoted commas) and pad ragged
    # rows so title lines like "Income Statement" don't crash the reader —
    # real files stack several statements with titles in one CSV.
    import csv as _csv

    rows = [
        row for row in _csv.reader(io.StringIO(text))
        if any(str(cell).strip() for cell in row)
    ]
    if not rows:
        raise ExtractionError("no data rows were found in the CSV.")
    width = max(len(row) for row in rows)
    padded = [row + [None] * (width - len(row)) for row in rows]
    df = pd.DataFrame(padded, dtype=object)
    return [df], notes


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------

def _load_excel(raw: bytes, ext: str) -> tuple[list[pd.DataFrame], list[str]]:
    notes: list[str] = []
    try:
        sheets = pd.read_excel(
            io.BytesIO(raw), sheet_name=None, header=None, dtype=object, engine=None
        )
    except Exception as exc:
        raise ExtractionError(f"could not open the Excel file ({exc}).") from exc

    frames = [df for df in sheets.values() if not df.empty]
    if len(frames) > 1:
        notes.append(f"Parsed {len(frames)} sheets and merged their data.")
    return frames, notes


def _load_excel_with_evidence(
    raw: bytes, ext: str,
) -> tuple[list[tuple[str, pd.DataFrame]], list[str], dict]:
    """_load_excel + the verifiable source evidence (المهمة 1):
    per-sheet {(row, col) -> {data_type, is_merged, number_format}} from
    openpyxl (formula cells = the STORED cache value, flagged), plus the
    file sha256 — so each captured value can cite WHERE it came from."""
    from src.extraction.provenance import file_sha256 as _sha

    notes: list[str] = []
    frames: list[tuple[str, pd.DataFrame]] = []
    try:
        sheets = pd.read_excel(
            io.BytesIO(raw), sheet_name=None, header=None, dtype=object, engine=None
        )
    except Exception as exc:
        raise ExtractionError(f"could not open the Excel file ({exc}).") from exc

    cell_meta: dict[str, dict[tuple[int, int], dict]] = {}
    try:
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True)
        for ws in wb.worksheets:
            meta: dict[tuple[int, int], dict] = {}
            merged = list(ws.merged_cells.ranges)
            for row in ws.iter_rows():
                for c in row:
                    entry: dict = {}
                    if c.value is not None:
                        if c.data_type == "f":
                            entry["data_type"] = "formula_cached"
                            entry["cached_formula"] = True
                        entry["number_format"] = c.number_format
                    entry["is_merged"] = any(
                        c.coordinate in rng for rng in merged)
                    meta[(c.row, c.column)] = entry
            cell_meta[ws.title] = meta
    except Exception as exc:
        # .xls or a reader failure: evidence degrades honestly (no formula /
        # merged flags), the sheet/address/label evidence still applies
        notes.append(f"openpyxl provenance index unavailable: {exc}")

    for name, df in sheets.items():
        if not df.empty:
            frames.append((str(name), df))
    if len(frames) > 1:
        notes.append(f"Parsed {len(frames)} sheets and merged their data.")
    bundle = {"file_sha256": _sha(raw), "cell_meta": cell_meta}
    return frames, notes, bundle


def _sheet_band_text(df: pd.DataFrame, upto: int = 6) -> str:
    """The title/header band above the table — scale words and the
    consolidation scope are sniffed here, not guessed."""
    band = df.head(upto).astype(str).values.ravel()
    return " ".join(str(x) for x in band[:200])


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

# Grouped numbers (1,000,000 / 1 000 000) or plain digits, optional decimals,
# optional parentheses (negative) and percent sign.
_NUMBER_TOKEN = re.compile(
    r"\(?\s*-?\s*(?:\d{1,3}(?:[,\s]\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*\)?%?"
)


def _load_pdf(raw: bytes) -> tuple[list[pd.DataFrame], list[str]]:
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover
        raise ExtractionError("pdfplumber is not installed.") from exc

    notes: list[str] = []
    frames: list[pd.DataFrame] = []
    text_lines: list[str] = []
    try:
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables():
                    if table:
                        frames.append(pd.DataFrame(table, dtype=object))
                text = page.extract_text() or ""
                text_lines.extend(line for line in text.splitlines() if line.strip())
    except Exception as exc:
        raise ExtractionError(f"could not read the PDF ({exc}).") from exc

    # Prefer structured tables; use raw text lines only when tables yield nothing.
    if frames and any(parse_table(f) for f in frames):
        notes.append("Data extracted from PDF tables.")
        return frames, notes

    parsed = _parse_pdf_text_lines(text_lines)
    if parsed:
        notes.append("Data extracted from PDF text (no tables detected).")
        return parsed, notes
    return frames, notes  # nothing from text either; let structuring report empty


def _looks_like_year_header(line: str, years: list[int]) -> bool:
    """Structural header test — position-in-table proxies, NO absolute year
    floor (a 2005 historical document is supported)."""
    if len(years) < 2 or max(years) - min(years) > 6:
        return False
    alpha_words = re.findall(r"[A-Za-z؀-ۿ]{2,}", line)
    if len(alpha_words) > 6:
        return False                      # prose, not a header
    tokens = re.split(r"\s+", line)
    year_positions = [i for i, t in enumerate(tokens)
                      if extract_year(t) is not None]
    if len(year_positions) < len(set(years)):
        return False                      # some year never stands alone
    for a, b in zip(year_positions, year_positions[1:]):
        if b - a - 1 > 4:                 # too many words between years
            return False
    return True


from src.extraction.normalizer import (  # noqa: E402
    _CURRENT_SECTION_FIELDS, _NONCURRENT_SECTION_FIELDS, match_field,
)


def _parse_pdf_text_lines(lines: list[str]) -> list[pd.DataFrame]:
    """Fallback for text-only PDFs.

    A line containing >= 2 years is treated as the column header; following
    'Label  number  number' lines are mapped against the active years.
    Tables with DIFFERENT year sets become SEPARATE frames (a statement of
    financial position with 3 year columns followed by a P&L with 2 must
    never be merged into one DataFrame — ragged rows used to crash the
    whole extraction with a pandas column-count error).
    """
    frames: list[pd.DataFrame] = []
    rows: list[list[object]] = []
    active_years: list[int] = []
    # Statement-section context (المهمة: repeated same-label rows —
    # «Creditors and other credit balances» prints under BOTH the non-current
    # AND the current liabilities sections; the section header above the row
    # disambiguates where the number belongs)
    section: str | None = None

    def _flush() -> None:
        nonlocal rows
        if not rows:
            return
        width = len(rows[0])
        norm = [(r + [None] * (width - len(r)))[:width] for r in rows]
        frames.append(pd.DataFrame(norm[1:], columns=norm[0], dtype=object))
        rows = []

    for line in lines:
        years = [extract_year(tok) for tok in re.split(r"\s+", line) if extract_year(tok)]
        if sum(y is not None for y in years) >= 2:
            new_years = [y for y in years if y is not None]
            # Structural year-header rule (المهمة 4 — no absolute year floor:
            # a 2005/2010 historical statement is perfectly valid). A line is
            # a comparison header when the years are STRUCTURALLY header-like:
            #   - all year tokens are standalone (not embedded in longer
            #     numbers like Law No. 117 of 2014 → «117» is not a year but
            #     «2014» inside a law reference still appears standalone, so
            #     the prose tests below carry the weight)
            #   - the years are adjacent fiscal columns (span ≤ 6 — a
            #     balance sheet may show 3 columns; income statement 2; both
            #     independently supported)
            #   - the line is SHORT (≤ 8 alphabetic words) — headers are
            #     «30 June 2025 30 June 2024», never a sentence
            #   - few tokens sit BETWEEN consecutive years (prose such as
            #     «… 2008 and amended by Law No. 117 of 2014» interleaves
            #     many words; headers interleave none)
            # Note-section year enumerations fail the length/gap tests and
            # never become column headers, whatever their year values are.
            if not _looks_like_year_header(line, new_years):
                continue
            if active_years and new_years != active_years:
                _flush()   # a new year set → a new table, never merge ragged
            active_years = new_years
            rows.append(["Line Item"] + active_years)
            continue
        if not active_years:
            continue
        low_line = line.lower()
        if "non current" in low_line or "non-current" in low_line:
            if "liabilities" in low_line:
                section = "non-current-liabilities"
            elif "assets" in low_line:
                section = "non-current-assets"
        elif "current" in low_line:
            if "liabilities" in low_line:
                section = "current-liabilities"
            elif "assets" in low_line:
                section = "current-assets"
        atoms = [(m.group(0), m.group(0).startswith("("))
                 for m in _NUMBER_TOKEN.finditer(line)]
        numbers = [n for n in (parse_number(t) for t, _p in atoms)
                   if n is not None]
        # IFRS statement rows lead with the Note reference — «Operating
        # revenue (32) 22 915 657 021 …»: the parenthesized small integer is
        # a NOTE NUMBER, not a (negative) value. Drop LEADING parenthesized
        # atoms ≤ 999 whenever the line carries more numbers after them.
        while (len(atoms) > 1 and len(numbers) > 1 and atoms[0][1]
               and numbers and abs(numbers[0]) <= 999):
            atoms = atoms[1:]
            numbers = numbers[1:]
        if not numbers:
            continue
        label = _NUMBER_TOKEN.sub(" ", line).strip(" -–—.:") or None
        if label is None or not numbers:
            continue
        canonical = match_field(label)
        if canonical is not None:
            # section contradiction: a CURRENT-section field captured under
            # the NON-CURRENT section (or the reverse) is a different
            # printed line — the row is skipped, never mis-captured
            if section == "non-current-liabilities" and canonical in (
                    _CURRENT_SECTION_FIELDS):
                continue
            if section == "current-liabilities" and canonical in (
                    _NONCURRENT_SECTION_FIELDS):
                continue
        # Keep at most as many numbers as active year columns.
        rows.append([label] + numbers[: len(active_years)])

    _flush()
    return frames
