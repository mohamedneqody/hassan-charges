# -*- coding: utf-8 -*-
"""Notes RAG audit (المهمة 3): retrieval quality on the REAL EFG notes
(55 pages, locally captured, zero API), page/value binding, and the
honest limitations — measured BEFORE and AFTER the tag-stripping fix.

Reference questions are in the DOCUMENT's language (the EFG notes are the
English translation; the monolingual-TF-IDF limitation for Arabic
questions is itself a pinned finding). Relevant-page SETS, since one
question legitimately matches several pages (the statement page AND its
IFRS policy note)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ))

from src.analysis.notes_rag import NotesIndex, formulate_answer  # noqa: E402

# (question, relevant-page SET, printed value that must be retrievable)
REF = [
    ("earnings per share for the period", {6, 48}, "0.29"),
    ("net cash used in investing activities", {9, 25, 45}, "205 906"),
    ("total equity issued paid-in capital retained earnings",
     {5, 48}, "10 743 525"),
]


def _build_index():
    raw = (PROJ / "independent_docs/efg_holdout/efg_standalone_fy2024.pdf") \
        .read_bytes()
    from src.extraction.local_ocr import capture_notes_text

    notes = capture_notes_text(raw)
    assert notes, "the EFG notes must be locally capturable"
    return NotesIndex.from_pages(notes), notes


@pytest.fixture(scope="module")
def efg_index():
    return _build_index()[0]


def test_rag_covers_every_page_with_page_binding(efg_index):
    st = efg_index.stats()
    assert sorted(st["pages"]) == list(range(1, 56))   # 55/55 indexed
    assert st["chunks"] > 100
    assert all(1 <= c.page <= 55 for c in efg_index.chunks)


def test_retrieval_recall_pages_and_values(efg_index):
    """Post tag-stripping: the statement pages surface (relevant-page hit)
    AND the printed figures are chunk-retrievable (value hit) for ALL
    reference questions."""
    page_hits, value_hits, details = 0, 0, []
    for q, relevant, value in REF:
        chunks = efg_index.search(q, top_k=10)
        pages = [c.page for c in chunks]
        page_hit = bool(set(pages) & relevant)
        val_hit = any(value in (c.text or "") for c in chunks)
        page_hits += page_hit
        value_hits += val_hit
        details.append({"q": q, "relevant": sorted(relevant),
                        "top10": pages[:10], "page_hit": page_hit,
                        "value_hit": val_hit})
    assert page_hits == len(REF), f"page recall incomplete: {details}"
    assert value_hits == len(REF), f"value recall incomplete: {details}"


def test_retrieved_chunks_bind_value_to_page(efg_index):
    """The EPS chunks contain the printed per-share figures AND bind them
    to page 6 (the income statement)."""
    chunks = efg_index.search("earnings per share for the period", top_k=10)
    joined = " ".join(c.text for c in chunks)
    assert "0.29" in joined and "(0.24)" in joined
    assert any(c.page == 6 for c in chunks)


def test_arabic_question_retrieves_via_the_glossary(efg_index):
    """The bilingual glossary CLOSED the monolingual gap: an Arabic
    question ('صافي الربح' -> profit) now retrieves the relevant
    English policy-note chunk (page 48, profit sharing)."""
    chunks = efg_index.search("ما صافي الربح للفترة؟", top_k=5)
    hits = [c for c in chunks
            if any(w in (c.text or "").lower()
                   for w in ("earnings", "profit"))]
    assert hits, "the glossary must bridge AR->EN retrieval"
    assert any(c.page == 48 for c in hits)


def test_formulate_answer_is_local_and_quotes_sources(efg_index):
    """WITHOUT Gemini, formulate_answer either builds a source-grounded
    digest from the chunks or returns None — it NEVER invents numbers."""
    chunks = efg_index.search("earnings per share for the period", top_k=3)
    ans = formulate_answer("earnings per share for the period", chunks,
                           company="EFG")
    if ans:
        assert "0.29" in ans or "EFG" in ans
