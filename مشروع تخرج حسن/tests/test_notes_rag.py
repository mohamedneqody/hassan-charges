"""Notes RAG: Arabic TF-IDF retrieval over الإيضاحات المتممة — fixture text
with hand-verified expected pages, plus the honest edge cases."""
from __future__ import annotations

import json

import pytest

from src.analysis.notes_rag import NotesIndex, formulate_answer

PAGES = {
    10: ("سياسة الإهلاك: تُهلك الأصول الثابتة بطريقة القسط الثابت على مدى "
         "العمر الإنتاجي المقدر لكل أصل، مع مراجعة القيم المتبقية سنويًا.\n\n"
         "القروض طويلة الأجل: تشمل قرض بنك مصر بمبلغ 500 مليون جنيه يستحق "
         "خلال ثلاث سنوات، وقرض الصندوق الاجتماعي للتنمية بمبلغ 200 مليون."),
    11: ("أعمار الذمم المدينة: الذمم حتى سنة تمثل 80% من إجمالي الذمم، "
         "والمتأخرة أكثر من سنة تمثل 20% — مع مخصص ديون مشكوك في تحصيلها.\n\n"
         "المخزون: يتم تقييم المخزون بالتكلفة أو صافي القيمة البيعية أيهما "
         "أقل وفق المعايير المحاسبية."),
    12: ("الالتزامات المحتملة: توجد دعاوى قضائية جارية ضد الشركة بقيمة "
         "تقديرية 12 مليون جنيه لم تُسجل التزامًا في القوائم."),
}


@pytest.fixture(scope="module")
def idx():
    return NotesIndex.from_pages(PAGES)


def test_index_builds_chunks_per_page(idx):
    st = idx.stats()
    assert st["chunks"] >= 3
    assert st["pages"] == [10, 11, 12]


def test_search_finds_depreciation_policy_on_page_10(idx):
    hits = idx.search("ما سياسة الاهلاك المستخدمة للثابتات؟")
    assert hits, "expected at least one matching chunk"
    assert hits[0].page == 10
    assert "القسط الثابت" in hits[0].text or "قسط" in hits[0].text


def test_search_finds_loans_terms(idx):
    hits = idx.search("تفاصيل القروض طويلة الاجل ومبالغها")
    assert hits and hits[0].page == 10
    assert "بنك مصر" in hits[0].text


def test_search_finds_receivables_aging(idx):
    hits = idx.search("اعمار الذمم المدينة المتاخرة")
    assert hits and hits[0].page == 11


def test_contingencies_found_on_page_12(idx):
    hits = idx.search("الالتزامات المحتملة والدعاوى القضائية")
    assert hits and hits[0].page == 12


def test_unrelated_question_returns_empty_or_low(idx):
    hits = idx.search("حالة الطقس غدا في المريخ")
    assert all(h.score < 0.5 for h in hits)


def test_empty_corpus_returns_empty():
    assert NotesIndex.from_pages({}).search("سياسة الاهلاك") == []


def test_notes_text_json_roundtrip():
    """The cache stores notes_text — int keys must survive the roundtrip."""
    raw = {10: "نص عربي ١", 11: "نص عربي ٢"}
    blob = json.dumps({"notes_text": raw}, ensure_ascii=False)
    back = {int(k): v for k, v in json.loads(blob)["notes_text"].items()}
    assert back == raw
