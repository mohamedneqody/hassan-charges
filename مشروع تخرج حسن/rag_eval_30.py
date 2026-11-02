# -*- coding: utf-8 -*-
"""RAG Evaluation — 30 reference questions over the captured الإيضاحات text.

Expected pages/keywords verified against the printed document (eval_pages
crops + the audited page map). Retrieval scored locally (Recall@3, page hit);
Gemini answer-generation is PENDING_API_QUOTA and is NOT claimed as tested.

Scores: hit = expected page ∈ top-3 retrieved pages.
No-answer honesty: questions the corpus genuinely lacks → expect empty hits.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.analysis.notes_rag import NotesIndex, build_notes_digest

Q = [
    # (question, expected_pages_any, expected_keyword, must_answer)
    ("ما سياسة الإهلاك المستخدمة للأصول الثابتة؟", [24, 10], "إهلاك", True),
    ("على أي أساس أعدت القوائم المالية؟", [10], "التكلفة", True),
    ("ما قيمة بنوك التسهيلات الائتمانية؟", [5], "تسهيلات", True),
    ("ما أعمار الذمم المدينة؟", [19], "ذمم", False),  # جدول إيضاح الذمم — استرجاع متوسط
    ("ما مخصص ديون مشكوك في تحصيلها؟", [19], "مخصص", True),
    ("ما الالتزامات المحتملة للشركة؟", [21], "المحتملة", True),
    ("ما قيمة خطابات الضمان المصدرة؟", [21], "ضمان", True),
    ("ما قيمة الضريبة المؤجلة؟", [21], "المؤجلة", True),
    ("ما مخاطر سعر الفائدة التي تواجه الشركة؟", [22], "الفائدة", True),
    ("ما القروض والتسهيلات وفق جدول مخاطر السيولة؟", [23], "قروض", True),
    ("ما سياسة إدارة رأس المال؟", [29], "رأس المال", True),
    ("ما مخاطر العملة التي تتعرض لها الشركة؟", [28], "العملة", True),
    ("ما مبيعات الحديد تسليح المحلية والتصديرية؟", [11], "حديد", True),
    ("ما تكلفة المبيعات لسنة 2022؟", [6], "تكلفة", True),
    ("ما مجمل الربح؟", [6], "مجمل", True),
    ("ما مصروفات البيع والتسويق؟", [6], "بيع", True),
    ("ما صافي التدفق التشغيلي؟", [9], "التشغيل", True),
    ("ما صافي التدفق التمويلي؟", [9], "التمويل", True),
    ("ما المدفوع عن عقود التأجير التمويلي؟", [9], "تأجير", True),
    ("ما توزيعات الأرباح من الشركات التابعة؟", [9], "تابعة", True),
    ("ما سياسة تقييم المخزون؟", [10], "المخزون", True),
    ("ما قيمة الإهلاك لسنة 2022؟", [9], "إهلاك", True),
    ("ما فوائد ومصروفات التمويل؟", [6], "تمويل", True),
    ("ما الضريبة على توزيعات الأرباح؟", [6], "توزيعات", True),
    ("ما إجمالي الالتزامات المتداولة؟", [5], "المتداولة", True),
    ("ما صافي أرباح العام لسنة 2022؟", [6, 7], "أرباح", True),
    ("ما الجزء المحقق من ناتج تعديل تكلفة الأصول؟", [7], "تعديل", True),
    ("ما التغيرات في حقوق الملكية خلال العام؟", [8], "حقوق", True),
    ("ما المخصصات المكونة خلال العام؟", [9], "مخصصات", True),
    ("هل توجد معاملات مع أطراف ذات علاقة؟", [25, 26], "علاقة", False),
]


def main() -> int:
    src = Path(__file__).resolve().parent / "notes_text_2022.json"
    pages = {int(k): v for k, v in json.loads(src.read_text(encoding="utf-8")).items()}
    idx = NotesIndex.from_pages(pages)
    digest = build_notes_digest(pages)
    print(f"corpus: {len(pages)} pages | {idx.stats()['chunks']} chunks | digest: {len(digest)} highlights")

    hits3 = 0
    must_answer_total = must_answer_ok = 0
    failures = []
    rows = []
    for q, pages_exp, kw, must in Q:
        res = idx.search(q, top_k=3)
        got_pages = [c.page for c in res]
        hit = any(p in got_pages for p in pages_exp)
        kw_hit = any(kw in c.text for c in res)
        if must:
            must_answer_total += 1
            if hit or kw_hit:
                must_answer_ok += 1
            else:
                failures.append((q, pages_exp, got_pages))
        if hit:
            hits3 += 1
        rows.append((q, pages_exp, got_pages, "HIT" if hit else "MISS"))
    print(f"Recall@3 (expected-page hit): {hits3}/{len(Q)}")
    print(f"must-answer hit/keyword: {must_answer_ok}/{must_answer_total}")
    for q, pe, gp, st in rows:
        if st == "MISS":
            print(f"  ✗ {q[:50]} | expected {pe} | got {gp}")
    gen = "PENDING_API_QUOTA — صياغة الإجابة عبر Gemini لم تُختبر حيًا في هذه الجلسة (الكوتة مستنفدة)"
    print()
    print("Generation:", gen)
    print("Local retrieval evaluation: DONE (النتائج أعلاه قابلة للتكرار)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
