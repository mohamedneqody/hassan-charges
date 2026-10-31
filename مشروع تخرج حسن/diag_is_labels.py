"""Free local diagnosis: which printed income-statement labels exist on the
2022 pages (via Indra OCR markdown, zero API) — feeds the alias additions."""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import indra_ocr
import pypdfium2 as pdfium

from src.extraction.local_ocr import _page_markdown

PDF = Path(__file__).resolve().parent / "القوائم المالية المستقلة 2022.pdf"

KEYS = ("ربح", "تشغيل", "ضريبة", "ضريبه", "إهلاك", "اهلاك", "إستهلاك", "استهلاك",
        "بيع", "تسويق", "اداري", "إداري", "تكلفة", "تكلفه", "مجمل", "تمويل",
        "فوائد", "استحقاق", "مخصص", "قائمة الدخل", "قائمه الدخل")

doc = pdfium.PdfDocument(str(PDF))
conv = indra_ocr.load(threads=4)

for idx in range(2, 12):  # document pages 3..12
    page = doc[idx]
    bmp = page.render(scale=2.0)
    buf = io.BytesIO()
    bmp.to_pil().save(buf, format="PNG")
    md = _page_markdown(conv, buf.getvalue()) or ""
    hits = [ln.strip() for ln in md.splitlines()
            if any(k in ln for k in KEYS) and len(ln.strip()) > 3]
    if hits:
        print(f"--- صفحة {idx + 1} ---")
        for h in hits[:16]:
            print("  ", h[:120])
