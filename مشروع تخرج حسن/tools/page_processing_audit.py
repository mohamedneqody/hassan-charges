# -*- coding: utf-8 -*-
"""Per-page processing audit (المهمة 1): for EVERY page of a document,
which route actually processed it — PDF text layer, local OCR, Vision —
or was it skipped, and why. Uses the FROZEN code paths."""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ))

from src.extraction.file_parsers import _parse_pdf_text_lines  # noqa: E402
from src.extraction.normalizer import parse_table_full, match_field  # noqa: E402

DOCS = {
    "EFG (born-digital, text path)":
        PROJ / "independent_docs/efg_holdout/efg_standalone_fy2024.pdf",
    "TE (pure scan, vision/local path)":
        PROJ / "independent_docs/te_holdout/te_standalone_h1_2024.pdf",
}
VISION_MAX_PAGES = 40


def audit_text_pages(pdf) -> list[dict]:
    """The native text path AS PRODUCTION uses it: extract_text lines ->
    _parse_pdf_text_lines -> parse_table_full (all pages — no cap)."""
    import pdfplumber

    rows = []
    with pdfplumber.open(io.BytesIO(raw_bytes(pdf))) as pdf2:
        for i, page in enumerate(pdf2.pages):
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            captured_fields = 0
            frames = []
            try:
                frames = _parse_pdf_text_lines(text.splitlines())
            except Exception:
                frames = []
            for fr in frames:
                try:
                    result, caps = parse_table_full(fr)
                    captured_fields += len(caps)
                except Exception:
                    pass
            rows.append({
                "page": i + 1, "route": "PDF_TEXT",
                "chars_text": len(text),
                "fields_captured": captured_fields,
                "status": "processed (text layer)"
                if captured_fields else "processed — no mappable rows",
            })
    return rows


def raw_bytes(pdf_path: Path) -> bytes:
    return pdf_path.read_bytes()


def audit_scan_pages(pdf_path: Path) -> list[dict]:
    """The scan path: VISION_MAX_PAGES cap + local Indra read per page."""
    import pypdfium2 as pdfium

    import indra_ocr

    from src.extraction.local_ocr import indra_available, _page_markdown

    pdf = pdfium.PdfDocument(str(pdf_path))
    total = len(pdf)
    rows = []
    conv = indra_ocr.load() if indra_available() else None
    for i in range(total):
        pno = i + 1
        if pno > VISION_MAX_PAGES:
            rows.append({"page": pno, "route": "SKIPPED",
                         "why": f"page {pno} > VISION_MAX_PAGES="
                                f"{VISION_MAX_PAGES} (render cap)",
                         "tables": 0, "fields_captured": 0})
            continue
        buf = io.BytesIO()
        pdf[i].render(scale=2.0).to_pil().convert("RGB").save(buf, format="PNG")
        png = buf.getvalue()
        md = ""
        if conv is not None:
            try:
                md = _page_markdown(conv, png) or ""
            except Exception:
                md = ""
        try:
            stripped = re.sub(r"<[^>]+>", " ", md)
            frames = _parse_pdf_text_lines(stripped.splitlines()) \
                if stripped.strip() else []
            fields = 0
            for fr in frames:
                try:
                    result, caps = parse_table_full(fr)
                    fields += len(caps)
                except Exception:
                    pass
        except Exception:
            fields = 0
        rows.append({
            "page": pno,
            "route": "VISION_SWEEP (+ local OCR read)",
            "tables": len(frames) if md.strip() else 0,
            "fields_captured": fields,
            "chars_md": len(md),
            "status": "processed (vision sweep; local markdown "
                      f"{len(md)} chars)" if md.strip()
            else "processed — vision returned no readable text",
        })
    return rows


def main() -> None:
    out = {}
    for name, path in DOCS.items():
        raw = path.read_bytes()
        import pypdfium2 as pdfium

        total = len(pdfium.PdfDocument(str(path)))
        if name.startswith("EFG"):
            rows = audit_text_pages(path)
        else:
            rows = audit_scan_pages(path)
        processed = sum(1 for r in rows if "processed" in r["status"])
        skipped = sum(1 for r in rows if r["route"] == "SKIPPED")
        with_fields = sum(1 for r in rows if r.get("fields_captured"))
        out[name] = {
            "document": str(path.name), "pages_total": total,
            "processed": processed, "skipped": skipped,
            "pages_with_captured_fields": with_fields,
            "cap_note": ("no cap on the text path — every page processed"
                         if name.startswith("EFG") else
                         f"VISION_MAX_PAGES={VISION_MAX_PAGES}: pages "
                         f"{VISION_MAX_PAGES + 1}-{total} would be skipped "
                         "IF the vision path ran (TE is 30 pages — inside "
                         "the cap)"),
            "per_page": rows,
        }
        print(f"== {name}: {total} pages | processed {processed} | "
              f"skipped {skipped} | with fields {with_fields}")
        for r in rows[:8]:
            print("  ", {k: r[k] for k in ("page", "route", "fields_captured",
                                           "status") if k in r})
        if len(rows) > 8:
            print(f"   … +{len(rows) - 8} more pages")
    dst = PROJ / "cell_evidence/page_processing_audit.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"artifact: {dst}")


if __name__ == "__main__":
    main()
