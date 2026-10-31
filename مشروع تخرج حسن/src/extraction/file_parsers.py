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

def load_financial_data(file_name: str, raw: bytes, progress_cb=None, page_range=None, fast_mode: bool = False) -> FinancialData:
    """Main entry: bytes -> canonical FinancialData. Raises AppError subclasses.
    `fast_mode` (scanned PDFs only) skips the paid verification layers —
    one sweep, ~half the calls, for initial triage of many files."""
    ext = "." + file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    if ext not in {".pdf", ".csv", ".xlsx", ".xls"}:
        raise UnsupportedFormatError()
    if not raw:
        raise EmptyFileError()

    if ext == ".pdf":
        # Scanned PDF? Skip pdfplumber entirely — extracting tables/text from
        # a scan yields nothing and only adds seconds before the vision path.
        from src.extraction.vision_ocr import extract_via_vision, is_scanned_pdf

        if is_scanned_pdf(file_name, raw):
            return extract_via_vision(raw, [], progress_cb=progress_cb,
                                      page_range=page_range, fast_mode=fast_mode)
        frames, notes = _load_pdf(raw)
    elif ext == ".csv":
        frames, notes = _load_csv(raw)
    else:
        frames, notes = _load_excel(raw, ext)

    parts: list[dict[int, dict[str, float]]] = []
    for frame in frames:
        try:
            parts.append(parse_table(frame))
        except Exception as exc:  # a broken table must not kill the run
            notes.append(f"Skipped an unparseable table: {exc}")

    if not parts and ext == ".pdf":
        # No text/tables at all → scanned PDF: render → OpenCV cleanup →
        # Gemini vision OCR, into the same matching + reconciliation pipeline.
        from src.extraction.vision_ocr import extract_via_vision

        return extract_via_vision(raw, notes, progress_cb=progress_cb,
                                  page_range=page_range, fast_mode=fast_mode)

    if not parts:
        raise ExtractionError("no readable tables were found.")

    data = merge_parsed(parts, notes)
    reconcile(data)
    data.currency_hint = _currency_hint_from_frames(frames)
    data.company_hint = _company_hint_from_frames(frames)
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


def _parse_pdf_text_lines(lines: list[str]) -> list[pd.DataFrame]:
    """Fallback for text-only PDFs.

    A line containing >= 2 years is treated as the column header; following
    'Label  number  number' lines are mapped against the active years.
    """
    rows: list[list[object]] = []
    active_years: list[int] = []
    for line in lines:
        years = [extract_year(tok) for tok in re.split(r"\s+", line) if extract_year(tok)]
        if sum(y is not None for y in years) >= 2:
            active_years = [y for y in years if y is not None]
            rows.append(["Line Item"] + active_years)
            continue
        if not active_years:
            continue
        numbers = [parse_number(tok) for tok in _NUMBER_TOKEN.findall(line)]
        numbers = [n for n in numbers if n is not None]
        if not numbers:
            continue
        label = _NUMBER_TOKEN.sub(" ", line).strip(" -–—.:") or None
        if label is None or not numbers:
            continue
        # Keep at most as many numbers as active year columns.
        rows.append([label] + numbers[: len(active_years)])

    if not rows:
        return []
    return [pd.DataFrame(rows[1:], columns=rows[0], dtype=object)]
