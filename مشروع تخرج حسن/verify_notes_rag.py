"""Live local verification (zero API quota): capture notes text from the real
2022 file with Indra, build the RAG index, ask REAL questions, and print the
retrieved sources — the proof that the system now READS the الإيضاحات."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.analysis.notes_rag import NotesIndex, formulate_answer
from src.extraction.local_ocr import capture_notes_text

PDF = Path(__file__).resolve().parent / "القوائم المالية المستقلة 2022.pdf"
OUT = Path(__file__).resolve().parent / "notes_text_2022.json"

raw = PDF.read_bytes()
t0 = time.perf_counter()
pages = capture_notes_text(raw)
elapsed = time.perf_counter() - t0
if not pages:
    print("FAILED: local notes capture returned nothing")
    sys.exit(1)
print(f"captured {len(pages)}/29 pages locally in {elapsed:.0f}s (zero API calls)")
OUT.write_text(json.dumps(pages, ensure_ascii=False, indent=1), encoding="utf-8")

idx = NotesIndex.from_pages(pages)
st = idx.stats()
print(f"index: {st['chunks']} chunks over {len(st['pages'])} pages")

QUESTIONS = [
    "ما سياسة الإهلاك المستخدمة؟",
    "تفاصيل القروض طويلة الأجل والالتزامات التأجيرية",
    "أعمار الذمم المدينة",
    "الالتزامات المحتملة والدعاوى القضائية",
]

for q in QUESTIONS:
    print("\n" + "=" * 90)
    print("سؤال:", q)
    hits = idx.search(q, top_k=3)
    if not hits:
        print("  (لا مقاطع مطابقة)")
        continue
    for c in hits:
        snippet = c.text.replace("\n", " ⏎ ")[:220]
        print(f"  [صفحة {c.page} | {c.score:.3f}] {snippet}...")
    answer = formulate_answer(q, hits, company="شركة حديد عز")
    if answer:
        print("  ── إجابة Gemini (مقتبسة بالمصدر) ──")
        for line in answer.splitlines()[:8]:
            print("   ", line[:150])

print("\nDONE — notes_text saved to", OUT.name)
