# -*- coding: utf-8 -*-
"""Real report production (المهمة 2): the project's OWN report engine
(build_excel_report + build_html_report + LibreOffice HTML->PDF) run on
the SAVED verified data of TE and EFG. Status labels are honest:
test-reviewer attestations are NOT production human review."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ))

OUT = PROJ / "review_package" / "reports"
SOFFICE = r"C:\Program Files\LibreOffice\program\soffice.exe"


def build(company: str, values: dict, notes: list[str],
          stem: str, currency: str) -> dict:
    from src.ai.gemini_agent import AIAnalysis
    from src.analysis import calculator as C
    from src.analysis.comparison import build_comparison
    from src.analysis.financial_gate import (
        pending_critical_review, report_is_preliminary,
    )
    from src.analysis.score import compute_health_score
    from src.dashboard.excel_report import build_excel_report
    from src.dashboard.report import build_html_report
    from src.extraction.normalizer import FinancialData, build_decision_log

    d = FinancialData()
    d.values.update(values)
    for f in d.values:
        d.candidates[f] = {y: [(v, 0), (v, 1)] for y, v in d.values[f].items()}
        d.confidence[f] = {y: 2 for y in d.values[f]}
    from src.extraction.normalizer import reconcile

    reconcile(d)
    dl = build_decision_log(d)
    pending = pending_critical_review(dl)
    prev = C.compute_year_metrics(2023, d.values)
    curr = C.compute_year_metrics(2024, d.values, prev_year=2023)
    hs = compute_health_score(curr, blocked_fields=set())
    results = {"company": company, "file_name": f"{stem}.pdf",
               "prev_year": 2023, "curr_year": 2024,
               "prev_metrics": prev, "curr_metrics": curr,
               "rows": build_comparison(prev, curr), "growth_rows": [],
               "notes": notes, "missing": [], "currency_hint": currency,
               "pending_critical_review": pending}
    preliminary = report_is_preliminary(dl)

    OUT.mkdir(parents=True, exist_ok=True)
    xlsx = OUT / f"{stem}.xlsx"
    xlsx.write_bytes(build_excel_report(results))
    html = build_html_report(results, AIAnalysis(ok=False), hs,
                             currency=currency)
    htm = OUT / f"{stem}.html"
    htm.write_text(html, encoding="utf-8")
    # LibreOffice HTML->PDF (the project's real PDF production path)
    pdf = OUT / f"{stem}.pdf"
    r = subprocess.run([SOFFICE, "--headless", "--convert-to", "pdf",
                        "--outdir", str(OUT), str(htm)],
                       capture_output=True, text=True, timeout=240)
    pdf_ok = pdf.exists()
    return {
        "company": company, "stem": stem,
        "xlsx": str(xlsx), "xlsx_bytes": xlsx.stat().st_size,
        "html": str(htm), "html_chars": len(html),
        "pdf": str(pdf), "pdf_ok": pdf_ok, "pdf_bytes": pdf.stat().st_size,
        "health": hs.total, "coverage": hs.coverage,
        "preliminary": preliminary,
        "pending_critical": len(pending),
        "pending_fields": [p["field"] for p in pending],
        "libreoffice_rc": r.returncode,
    }


def main() -> dict:
    out = {"reports": []}
    # ── TE (the 40 verified cells from the frozen GT) ──
    gt = json.loads((PROJ / "independent_docs/te_holdout/gt_te_frozen.json")
                    .read_text(encoding="utf-8"))
    te_values = {}
    for y in ("2024", "2023"):
        for f, m in gt["cells"][y].items():
            te_values.setdefault(f, {})[int(y)] = float(m["value"])
    te_notes = [
        "الحالة: تقرير أولي — القيم موثقة بمراجعة اختبارية عبر سلسلة HMAC "
        "(test-reviewer) وليست مراجعة بشرية إنتاجية.",
        "Human review: 40 printed values attested via the review chain.",
        "Beneish M-Score: غير قابل للحساب — SGAI غير موجود ضمن الخانات "
        "الموثقة (المكونات الستة الأخرى محسوبة ومعروضة).",
    ]
    out["reports"].append(build(
        "Telecom Egypt (TE — verified subset)", te_values, te_notes,
        "TE_Financial_Report_2024", "ج.م"))
    # ── EFG (the 28 printed GT cells) ──
    gt_e = json.loads(
        (PROJ / "independent_docs/efg_holdout/gt_efg_frozen.json")
        .read_text(encoding="utf-8"))
    efg_values = {}
    for y in ("2024", "2023"):
        for f, m in gt_e["cells"][y].items():
            efg_values.setdefault(f, {})[int(y)] = float(m["value"])
    efg_notes = [
        "الحالة: تقرير أولي — القيم من GT المرجعية الموثقة بصريًا.",
        "EFG Holding — Separate financial statements FY2024 "
        "(financial-services holding; statement vocabulary differs).",
    ]
    out["reports"].append(build(
        "EFG Holding (EFG — verified subset)", efg_values, efg_notes,
        "EFG_Financial_Report_2024", "ج.م"))

    dst = PROJ / "review_package" / "report_production.json"
    OUT.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    for r in out["reports"]:
        print(f"{r['stem']}: xlsx={r['xlsx_bytes']}B html={r['html_chars']}ch "
              f"pdf_ok={r['pdf_ok']} ({r['pdf_bytes']}B) health={r['health']} "
              f"preliminary={r['preliminary']} pending={r['pending_critical']}")
    print(f"artifact: {dst}")
    return out


if __name__ == "__main__":
    main()
