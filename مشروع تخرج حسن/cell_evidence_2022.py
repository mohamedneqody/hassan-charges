# -*- coding: utf-8 -*-
"""Cell-Level evidence packages for the UNSTABLE fields — local only (zero API).

For each unstable field: locate its printed row band on the source page via
generic label keywords, save the band crop + local Indra text + the system's
captured value into cell_evidence/<field>.json + <field>_band.png.
The live Gemini re-read of each band is PENDING_API_QUOTA (one cheap call per
band when quota returns) — not claimed as tested.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.extraction.cell_evidence import locate_row_band_by_text

PROJ = Path(__file__).resolve().parent
PAGES = {5: "eval_pages/page_5.png", 6: "eval_pages/page_6.png", 9: "eval_pages/page_9.png"}
OUT = PROJ / "cell_evidence"
OUT.mkdir(exist_ok=True)

# الحقول غير المستقرة → الصفحة + كلمات البند العامة (بلا أي أرقام شركة)
TARGETS = [
    ("short_term_debt", "التسهيلات البنكية", 5, ["تسهيلات", "بنوك"]),
    ("current_portion_lt_debt", "أقساط القروض المتداولة", 5, ["أقساط", "اقساط"]),
    ("long_term_debt", "القروض غير المتداولة", 5, ["قروض طويله", "قروض طويلة"]),
    ("non_current_lease_liabilities", "التأجير غير المتداول", 5, ["تأجير تمويلي"]),
    ("current_lease_liabilities", "التأجير المتداول", 5, ["تأجير تمويلي مستحقه", "تأجير تمويلي مستحقة"]),
    ("revenue", "الإيرادات", 6, ["المبيعات", "مبيعات"]),
    ("net_income", "صافي أرباح العام", 6, ["صافي", "أرباح", "عام"]),
    ("income_tax_expense", "ضريبة الدخل", 6, ["ضريبة", "عام"]),
    ("total_liabilities", "إجمالي الالتزامات المتداولة", 5, ["المتداولة"]),
    ("operating_cash_flow", "صافي التدفق التشغيلي", 9, ["التشغيل"]),
]

results = {}
for field, ar_name, page, keywords in TARGETS:
    png_path = PROJ / PAGES[page]
    if not png_path.exists():
        print(f"SKIP {field}: page render missing")
        continue
    bands = locate_row_band_by_text(png_path.read_bytes(), keywords)
    hits = []
    for b in bands[:2]:
        snippet = " ⏎ ".join(
            ln.strip() for ln in b.text.splitlines() if ln.strip()
        )[:260]
        hits.append({"y": [b.y0, b.y1], "keywords": b.matched_keywords, "text": snippet})
        (OUT / f"{field}_p{page}_y{b.y0}.png").write_bytes(b.crop_png)
    results[field] = {"ar_name": ar_name, "page": page, "bands": hits}
    print(f"{field:28s} page {page}: {len(hits)} band(s) matched {b.matched_keywords if bands else []}")

(OUT / "unstable_fields_evidence.json").write_text(
    json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8"
)
print("saved cell_evidence/unstable_fields_evidence.json")
