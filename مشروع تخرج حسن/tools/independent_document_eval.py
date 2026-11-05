# -*- coding: utf-8 -*-
"""P1 — independent-document evaluation (تجربة المستند المستقل).

Target: sample_data/sample_financials.xlsx — a born-digital English workbook
for a DIFFERENT (sample) company with a DIFFERENT format (3 structured
sheets, FY2025/FY2026, negative capex). ZERO Hadid-Ezz artifacts are used:
the extraction runs through the production pipeline exactly as any upload
would, with NO logic adjustments and no tuning on this document.

Ground truth is the workbook itself (born-digital: the printed numbers ARE
the answer key), mapped by a hard-coded table below — deliberately NOT the
production matcher, so field-mapping is measured, not assumed.

Honest scope note (سجل بصدق): this is a synthetic demo workbook, not a real
company's published statement. It exercises format/label/year generalization
of the text pipeline; it does NOT prove OCR generalization on a scanned
Arabic document. No image evidence exists for a born-digital file, so the
human-assisted coverage is measured as 0/N (the review chain is
image-evidence-based and no packets apply).

Measures: Field Mapping, Year Assignment, Exact Match, Automatic Verified
Coverage, False Acceptance Rate, End-to-End Accuracy, Human-Assisted
Coverage. Artifact: cell_evidence/independent_doc_results.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ))

XLSX = PROJ / "sample_data/sample_financials.xlsx"

# hard-coded GT mapping (a-priori, independent of the production matcher)
GT_MAP = {
    "Revenue": "revenue",
    "Cost of Revenue": "cost_of_revenue",
    "Gross Profit": "gross_profit",
    "Selling Expenses": "selling_expenses",
    "Research and Development": "rd_expenses",
    "Operating Expenses": "operating_expenses",
    "Operating Income": "operating_income",
    "Interest Expense": "interest_expense",
    "Income Before Tax": "pretax_income",
    "Income Tax Expense": "income_tax_expense",
    "Net Income": "net_income",
    "Depreciation and Amortization": "depreciation_amortization",
    "Total Assets": "total_assets",
    "Cash and Cash Equivalents": "cash",
    "Accounts Receivable": "accounts_receivable",
    "Current Assets": "current_assets",
    "Inventory": "inventory",
    "Net Fixed Assets": "fixed_assets",
    "Accounts Payable": "accounts_payable",
    "Total Liabilities": "total_liabilities",
    "Current Liabilities": "current_liabilities",
    "Total Debt": "total_debt",
    "Shareholders Equity": "equity",
    "Operating Cash Flow": "operating_cash_flow",
    "Capital Expenditure": "capex",
    "Investing Cash Flow": "investing_cash_flow",
    "Financing Cash Flow": "financing_cash_flow",
}
YEARS = {"FY2025": 2025, "FY2026": 2026}


def ground_truth() -> dict[tuple[str, int], float]:
    from openpyxl import load_workbook

    wb = load_workbook(XLSX)
    gt: dict[tuple[str, int], float] = {}
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            label = row[0]
            if not isinstance(label, str) or label not in GT_MAP:
                continue
            for col, fy in ((1, "FY2025"), (2, "FY2026")):
                v = row[col] if len(row) > col else None
                if isinstance(v, (int, float)):
                    gt[(GT_MAP[label], YEARS[fy])] = float(v)
    return gt


def main() -> dict:
    from src.analysis.financial_gate import decide
    from src.extraction.file_parsers import load_financial_data
    from src.extraction.normalizer import build_decision_log
    from src.pipeline import run_pipeline

    gt = ground_truth()
    n = len(gt)
    raw = XLSX.read_bytes()

    # the extraction runs EXACTLY as a user upload would — no overrides
    data = load_financial_data(XLSX.name, raw)
    # and the FULL pipeline (ratios → metrics) must complete on this document
    pipeline_results = run_pipeline(XLSX.name, raw,
                                    company="Sample Manufacturing Co",
                                    fast_mode=True)
    assert pipeline_results["curr_metrics"].year == 2026

    # ── year assignment ──
    years_detected = sorted(data.years)
    year_assignment_ok = years_detected == [2025, 2026]

    # ── decision log statuses per GT cell ──
    dl = {(e["field"], e["year"]): e for e in build_decision_log(data)}
    rows = []
    for (f, y), gt_v in sorted(gt.items()):
        captured = data.values.get(f, {}).get(y)
        entry = dl.get((f, y))
        status = entry["status"] if entry else "NOT_CAPTURED"
        verdict = decide(status)
        rows.append({
            "field": f, "year": y, "gt": gt_v,
            "captured": captured,
            "status": status, "gate": verdict,
            "exact": (captured is not None
                      and abs(captured - gt_v) <= max(1.0, 1e-6 * abs(gt_v))),
        })

    def rate(num: int, den: int) -> float | None:
        return round(num / den, 3) if den else None

    mapped = sum(1 for r in rows if r["status"] != "NOT_CAPTURED")
    allowed = [r for r in rows if r["gate"] in ("use", "use_disclosed")]
    gated = [r for r in rows if r["gate"] == "not_decisive"]
    missing = [r for r in rows if r["gate"] == "missing"]
    exact = sum(1 for r in rows if r["exact"])
    allowed_wrong = sum(1 for r in allowed if not r["exact"])
    e2e = sum(1 for r in allowed if r["exact"])

    out = {
        "document": str(XLSX.name),
        "scope_note": "born-digital synthetic sample workbook — different "
                      "company AND format; proves text-pipeline "
                      "generalization only, NOT scanned-Arabic OCR",
        "gt_cells": n,
        "field_mapping_rate": rate(mapped, n),
        "year_assignment": {"detected": years_detected,
                            "expected": [2025, 2026],
                            "ok": year_assignment_ok},
        "automatic_exact_match_accuracy": rate(exact, n),
        "automatic_decisive_coverage": rate(len(allowed), n),
        "false_acceptance_rate": rate(allowed_wrong, len(allowed)),
        "false_acceptances": allowed_wrong,
        "correct_values_blocked": sum(1 for r in gated if r["exact"]),
        "wrong_values_blocked": sum(1 for r in gated if not r["exact"]),
        "missing_values": len(missing),
        "end_to_end_accuracy": rate(e2e, n),
        "human_assisted_coverage": 0.0,
        "human_assisted_note": "no image evidence exists for a born-digital "
                               "file — the review chain is crop-based and no "
                               "packets apply (0/N, not N/A)",
        "gate_partition": {"usable": len(allowed), "not_decisive": len(gated),
                           "missing": len(missing)},
        "rows": rows,
    }
    out_path = PROJ / "cell_evidence/independent_doc_results.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "rows"},
                     ensure_ascii=False, indent=1))
    print(f"artifact: {out_path}")
    return out


if __name__ == "__main__":
    main()
