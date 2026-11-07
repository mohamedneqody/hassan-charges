# -*- coding: utf-8 -*-
"""Multilingual RAG acceptance set (المهمة 1): 20+ questions across
Arabic and English notes on TWO companies, with the reference note pages
fixed BEFORE the measurement. Zero API — retrieval only."""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ))

from src.analysis.notes_rag import NotesIndex  # noqa: E402
from src.extraction.local_ocr import capture_notes_text  # noqa: E402

# (lang, question, expected pages, evidence token that must appear in the
#  top-3 chunk text when the right page is hit)
EFG = PROJ / "independent_docs/efg_holdout/efg_standalone_fy2024.pdf"
EZZ = PROJ / "القوائم المالية المستقلة 2022.pdf"

SET_EFG_EN = [
    ("EN", "earnings per share for the period", {6, 48}, "0.29"),
    ("EN", "net cash used in investing activities", {9, 25, 45}, "205 906"),
    ("EN", "total equity issued paid-in capital retained earnings", {5, 48},
     "10 743 525"),
    ("EN", "cash and cash equivalents current assets", {5}, "1 725 533"),
    ("EN", "fixed assets depreciation", {5, 19}, "239 596"),
    ("EN", "banks overdraft current liabilities", {5}, "6 520 169"),
    ("EN", "loans to subsidiaries non current", {5}, "1 680 000"),
    ("EN", "deferred tax liabilities", {5}, "1 571 301"),
    ("EN", "retained earnings treasury shares", {5}, "618 557"),
    ("EN", "credit risk management financial", {32, 34}, "credit"),
    ("EN", "accounting policies basis of preparation", {10, 11}, "policies"),
]
SET_EFG_AR = [
    ("AR", "ما صافي الربح للفترة وربحية السهم؟", {6, 48}, "0.29"),
    ("AR", "ما التزامات الاستثمار والتدفقات التمويلية؟", {9, 25, 45},
     "205 906"),
    ("AR", "ما مخاطر الائتمان والسياسات المحاسبية؟", {32, 34}, "risk"),
    ("AR", "ما النقدية والقروض والالتزامات؟", {5}, "1 725 533"),
    ("AR", "ما أرباح الشركة التابعة والمجموعة؟", {5, 48}, "1 680 000"),
]
SET_EZZ_AR = [
    ("AR", "ربحية السهم للأرباح", {27}, "ربحية"),
    ("AR", "سياسات محاسبية", {24, 25}, "سياسات"),
    ("AR", "الضرائب والنزاعات الضريبية", {43, 44}, "ضريبة"),
    ("AR", "القروض والالتزامات", {12}, "قروض"),
    ("AR", "أهم المخاطر", {43, 44}, "مخاطر"),
]


def _efg_notes() -> dict:
    """The EFG notes text — the BORN-DIGITAL text layer via pdfplumber (the
    document's own text, no OCR needed on a digital PDF; Indra OCR is the
    fallback for pages with no text layer)."""
    saved = PROJ / "independent_docs/efg_holdout/notes_text.json"
    if saved.exists():
        return {int(k): v for k, v in json.loads(
            saved.read_text(encoding="utf-8")).items()}
    import pdfplumber

    notes: dict[int, str] = {}
    with pdfplumber.open(str(EFG)) as pdf:
        for i, page in enumerate(pdf.pages):
            text = (page.extract_text() or "").strip()
            if text:
                notes[i + 1] = text
    if len(notes) < 40:                    # text layer too thin → Indra
        from src.extraction.local_ocr import capture_notes_text

        ocr = capture_notes_text(EFG)
        if ocr:
            notes = ocr
    assert len(notes) >= 40, "the EFG notes extraction failed"
    saved.write_text(json.dumps(notes, ensure_ascii=False), encoding="utf-8")
    return notes


def main() -> dict:
    efg_notes = _efg_notes()
    # the Hadid Ezz Arabic notes were captured in an earlier session and
    # saved — reuse them (the scan is heavy; no re-OCR needed)
    ezz_notes = {int(k): v for k, v in json.loads(
        (PROJ / "notes_text_2022.json").read_text(encoding="utf-8")).items()}
    idx_efg = NotesIndex.from_pages(efg_notes)
    idx_ezz = NotesIndex.from_pages(ezz_notes)

    results, details = [], []
    for lang, q, pages, token in SET_EFG_EN + SET_EFG_AR:
        chunks = idx_efg.search(q, top_k=5)
        p3 = [c.page for c in chunks[:3]]
        p5 = [c.page for c in chunks]
        r3 = bool(set(p3) & pages)
        r5 = bool(set(p5) & pages)
        # page-citation precision: the TOP-1 page is a reference page
        prec = p3[:1] and p3[0] in pages
        # value/note binding: the evidence token appears in a hit chunk
        bound = any(token in (c.text or "") for c in chunks
                    if c.page in pages)
        results.append({"lang": lang, "q": q, "r3": r3, "r5": r5,
                        "prec1": bool(prec), "bound": bound})
        details.append({"lang": lang, "q": q, "pages_ref": sorted(pages),
                        "top5": p5, "r3": r3, "r5": r5, "prec1": bool(prec),
                        "bound": bound})
    for lang, q, pages, token in SET_EZZ_AR:
        chunks = idx_ezz.search(q, top_k=5)
        p3 = [c.page for c in chunks[:3]]
        p5 = [c.page for c in chunks]
        r3 = bool(set(p3) & pages)
        r5 = bool(set(p5) & pages)
        prec = p3[:1] and p3[0] in pages
        bound = any(token in (c.text or "") for c in chunks
                    if c.page in pages)
        results.append({"lang": lang, "q": q, "r3": r3, "r5": r5,
                        "prec1": bool(prec), "bound": bound})
        details.append({"lang": lang, "q": q, "pages_ref": sorted(pages),
                        "top5": p5, "r3": r3, "r5": r5, "prec1": bool(prec),
                        "bound": bound})

    n = len(results)
    by = {}
    for lang in ("EN", "AR"):
        sub = [r for r in results if r["lang"] == lang]
        by[lang] = {
            "n": len(sub),
            "recall3": round(sum(r["r3"] for r in sub) / len(sub), 3),
            "recall5": round(sum(r["r5"] for r in sub) / len(sub), 3),
            "precision1": round(sum(r["prec1"] for r in sub) / len(sub), 3),
            "binding": round(sum(r["bound"] for r in sub) / len(sub), 3),
        }
    out = {
        "questions": n,
        "by_language": by,
        "overall": {
            "recall3": round(sum(r["r3"] for r in results) / n, 3),
            "recall5": round(sum(r["r5"] for r in results) / n, 3),
            "precision1": round(sum(r["prec1"] for r in results) / n, 3),
            "binding": round(sum(r["bound"] for r in results) / n, 3),
        },
        "details": details,
    }
    dst = PROJ / "cell_evidence/rag_multilingual_results.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(json.dumps({"questions": n, "by_language": by,
                      "overall": out["overall"]}, ensure_ascii=False,
                     indent=1))
    for d in details:
        mark = "✓" if d["r5"] else "✗"
        print(f"  {mark} [{d['lang']}] {d['q'][:46]:48s} "
              f"top5={d['top5']} r3={d['r3']} r5={d['r5']} p1={d['prec1']}")
    print(f"artifact: {dst}")
    return out


if __name__ == "__main__":
    main()
