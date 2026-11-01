import pypdfium2 as pdfium
import os, sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

pdf_dir = r"عرض_المتحدثين"
speakers = [
    "المتحدث_1_الفكرة.pdf",
    "المتحدث_2_القصة.pdf",
    "المتحدث_3_المشاكل.pdf",
    "المتحدث_4_الحلول.pdf",
    "المتحدث_5_الأثر.pdf",
    "المتحدث_6_محرك_القراءة.pdf",
    "المتحدث_7_محرك_التحليل.pdf",
    "المتحدث_8_الختام.pdf"
]

# Required checks in PDF text
required_tokens = [
    ("1. بطاقة دورك وفكرة الدور", ["دوره", "دورك", "سطور"]),
    ("2. نص الإلقاء التفصيلي", ["اإللقاء", "التفصيلي"]),
    ("3. إزاي اتعمل — الشرح التقني", ["اتعمل", "التقني"]),
    ("4. أدلتك الرقمية", ["أدلتك", "الرقمية"]),
    ("5. أسئلة اللجنة المتوقعة", ["اللجنة", "أسئلة"]),
    ("6. نصائح العرض", ["نصائح"]),
    ("7. جملة التسليم الحرفية", ["تسليم"])
]

all_passed = True
for s in speakers:
    p = os.path.join(pdf_dir, s)
    if not os.path.exists(p):
        print(f"MISSING: {s}")
        all_passed = False
        continue
    
    doc = pdfium.PdfDocument(p)
    full_text = ""
    for page in doc:
        full_text += page.get_textpage().get_text_range() + "\n"
    
    size_kb = round(os.path.getsize(p) / 1024)
    print(f"\n==========================================")
    print(f"=== {s} ({len(doc)} pages, {size_kb} KB, {len(full_text)} chars)")
    print(f"==========================================")
    
    if len(doc) < 4:
        print(f"  [FAIL] Page count too low: {len(doc)}")
        all_passed = False
    
    for title, tokens in required_tokens:
        found = any(token in full_text for token in tokens)
        status = "PASS" if found else "FAIL"
        if not found:
            all_passed = False
        print(f"  [{status}] {title}")

print("\nFinal PDF Check Result:", "ALL PASS" if all_passed else "SOME FAILED")
if not all_passed:
    exit(1)
