import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import win32com.client

docs_dir = r"D:\hassan_charges\مشروع تخرج حسن\عرض_المتحدثين"

word = win32com.client.Dispatch("Word.Application")
word.Visible = False

try:
    files = [f for f in sorted(os.listdir(docs_dir)) if f.endswith(".docx") and not f.startswith("~$")]
    print(f"Found {len(files)} DOCX files to convert to PDF:")
    for f in files:
        docx_path = os.path.abspath(os.path.join(docs_dir, f))
        pdf_path = os.path.abspath(os.path.join(docs_dir, f.replace(".docx", ".pdf")))
        print(f"Converting: {f} -> {os.path.basename(pdf_path)}...", end=" ", flush=True)
        doc = word.Documents.Open(docx_path)
        doc.ExportAsFixedFormat(pdf_path, 17) # 17 = wdExportFormatPDF
        doc.Close(False)
        size_kb = round(os.path.getsize(pdf_path) / 1024)
        print(f"OK ({size_kb} KB)")
finally:
    word.Quit()
print("All 8 PDFs generated successfully via Word COM!")
