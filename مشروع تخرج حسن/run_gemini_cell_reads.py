# -*- coding: utf-8 -*-
"""Run the Gemini second-reader on the crops local OCR provably failed on.

Two modes because the environments differ:
  --build  (WSL, Indra available): build the job crops — one date region per
           currency column per page (5/6/9) + the failing cell crops saved by
           the benchmark — into cell_evidence/gemini_jobs/.
  --read   (Windows venv, google-genai + keys): read each crop through
           gemini_cell_reader.read_batch, schema-validate, log, save
           cell_evidence/gemini_reads.json. Quota/auth failures are recorded
           as BLOCKED — never invented.

Zero assertion of success without the actual responses on disk.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

PROJ = Path(__file__).resolve().parent
JOBS = PROJ / "cell_evidence" / "gemini_jobs"
PAGES = {5: "eval_pages/page_5.png", 6: "eval_pages/page_6.png", 9: "eval_pages/page_9.png"}
AR_NAMES = {
    "short_term_debt": "بنوك تسهيلات إنتمانية",
    "current_portion_lt_debt": "أقساط قروض طويلة الأجل مستحقة السداد خلال عام",
    "long_term_debt": "قروض طويلة الأجل",
    "non_current_lease_liabilities": "التزامات تأجير تمويلي غير متداولة",
    "current_lease_liabilities": "التزامات تأجير تمويلي متداولة",
    "revenue": "المبيعات (بالصافي)",
    "net_activity_profit": "صافي أرباح النشاط",
    "net_income": "صافي أرباح العام",
    "income_tax_expense": "ضريبة الدخل",
    "total_liabilities": "إجمالي الالتزامات",
    "operating_cash_flow": "صافي النقدية الناتجة من أنشطة التشغيل",
}
# the cells local OCR failed on (benchmark_abc.json, C_spatial_declared)
FAILING = [
    ("current_portion_lt_debt", 5), ("non_current_lease_liabilities", 5),
    ("current_lease_liabilities", 5), ("revenue", 6),
    ("income_tax_expense", 6), ("total_liabilities", 5),
    ("operating_cash_flow", 9),
]


def build() -> None:
    import indra_ocr
    from src.extraction import spatial_cells as SC

    conv = indra_ocr.load()
    JOBS.mkdir(exist_ok=True)
    jobs = []
    for p, rel in PAGES.items():
        png = (PROJ / rel).read_bytes()
        w, h, lines = SC.read_page_lines(conv, png)
        cols, _d = SC.find_currency_columns(lines, w)
        if not cols:
            print(f"page {p}: no currency columns")
            continue
        cands = SC._currency_header_lines(lines)
        med = sorted(l.height for l in cands)[len(cands) // 2]
        groups = []
        for ln in sorted(cands, key=lambda l: l.cy):
            for g in groups:
                if abs(ln.cy - g[0].cy) <= 1.5 * med:
                    g.append(ln)
                    break
                else:
                    continue
            else:
                groups.append([ln])
        row = next((g for g in groups if len(g) >= 2), None)
        for side, col in cols.items():
            hdr = next((ln for ln in row
                        if abs(ln.cx / w - col.header_cx) < 0.08), None)
            if hdr is None:
                continue
            crop = SC._crop(png, max(col.x0 - 0.02, 0.0),
                            max(hdr.y0 - 3.2 * hdr.height, 0.0) / h,
                            min(col.x1 + 0.02, 1.0),
                            (hdr.y0 + 0.2 * hdr.height) / h)
            name = f"date_p{p}_{side}.png"
            (JOBS / name).write_bytes(crop)
            jobs.append({"evidence_reference": f"{name}",
                         "png_file": name, "label": "تاريخ العمود",
                         "year": None, "what": "تاريخ العمود المطبوع (يوم/شهر/سنة)"})
    for field, p in FAILING:
        for f in sorted((PROJ / "cell_evidence").glob(f"spatial_{field}_p{p}_y*.png")):
            name = f"cell_{f.name}"
            (JOBS / name).write_bytes(f.read_bytes())
            jobs.append({"evidence_reference": name, "png_file": name,
                         "label": AR_NAMES[field], "year": 2022,
                         "what": "الرقم المطبوع في الخلية"})
    (JOBS / "jobs.json").write_text(
        json.dumps(jobs, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"built {len(jobs)} jobs in {JOBS}")


def read() -> None:
    from src.extraction import gemini_cell_reader as G

    jobs = json.loads((JOBS / "jobs.json").read_text(encoding="utf-8"))
    batch = []
    for j in jobs:
        png = (JOBS / j["png_file"]).read_bytes()
        batch.append({"evidence_reference": j["evidence_reference"],
                      "png": png, "label": j["label"],
                      "year": j["year"], "what": j["what"]})
    print(f"reading {len(batch)} crops with Gemini...")
    reads = G.read_batch(batch)
    G.save(reads, PROJ / "cell_evidence" / "gemini_reads.json")
    n_read = sum(1 for r in reads if r["read_status"] == "READ")
    n_blocked = sum(1 for r in reads if r["read_status"] == "BLOCKED")
    print(f"READ={n_read} UNREADABLE={len(reads) - n_read - n_blocked} "
          f"BLOCKED={n_blocked} → cell_evidence/gemini_reads.json")


if __name__ == "__main__":
    build() if "--build" in sys.argv else read()
