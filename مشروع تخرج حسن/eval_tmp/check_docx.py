import os, zipfile, xml.etree.ElementTree as ET

docs_dir = r"عرض_المتحدثين"
files = [f for f in sorted(os.listdir(docs_dir)) if f.endswith(".docx")]
print(f"Checking {len(files)} DOCX files:")

all_passed = True
for f in files:
    path = os.path.join(docs_dir, f)
    with zipfile.ZipFile(path) as z:
        tree = ET.fromstring(z.read("word/document.xml"))
        paras = []
        for p in tree.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
            text = "".join(t.text for t in p.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t") if t.text)
            if text.strip():
                paras.append(text.strip())
        
        full_text = "\n".join(paras)
        print(f"\n=== {f} ({len(paras)} paragraphs, {len(full_text)} chars) ===")
        sections = [
            ("1. ترويسة المتحدث وفكرة دوره في سطرين", "فكرة دورك في سطرين:" in full_text and ("المتحدث" in full_text)),
            ("1. الافتتاحية في سطور", "أولًا:" in full_text and "سطور" in full_text),
            ("2. نص الإلقاء التفصيلي", "ثانيًا: نص الإلقاء التفصيلي" in full_text),
            ("3. إزاي اتعمل — الشرح التقني", "ثالثًا: إزاي اتعمل" in full_text),
            ("4. أدلتك الرقمية", "رابعًا: أدلتك الرقمية" in full_text),
            ("5. أسئلة اللجنة المتوقعة", "خامسًا: أسئلة اللجنة المتوقعة" in full_text),
            ("6. نصائح العرض", "سادسًا: نصائح عرضك الخاصة" in full_text),
            ("7. جملة التسليم", "سابعًا: جملة تسليم" in full_text)
        ]
        for s_name, exists in sections:
            status = "PASS" if exists else "FAIL"
            if not exists:
                all_passed = False
            print(f"   {status} - {s_name}")

print("\nFinal DOCX Check Result:", "ALL PASS" if all_passed else "SOME FAILED")
if not all_passed:
    exit(1)
