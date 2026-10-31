"""Headless full-pipeline self-test on the real 29-page 2022 file.

Runs the exact production path (vision extraction + verify passes, no page
range, thorough mode) and dumps everything needed for an honest evaluation
to selftest_2022_results.json. Zero Streamlit. Progress printed live.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

PROJ = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJ))

import src.config  # noqa: F401  (loads .env with the real keys)
from src.analysis.academic_models import academic_models
from src.pipeline import run_pipeline
from src.analysis.redflags import beneish_m_score, red_flag_analysis
from src.analysis.score import compute_health_score

PDF = PROJ / "القوائم المالية المستقلة 2022.pdf"
OUT = PROJ / "selftest_2022_results.json"

FIELDS = [
    "revenue", "net_income", "operating_cash_flow", "total_assets",
    "total_liabilities", "current_assets", "current_liabilities", "equity",
    "retained_earnings", "working_capital", "fixed_assets", "inventory",
    "accounts_receivable", "cash", "gross_profit", "operating_income",
    "pretax_income", "depreciation_amortization", "short_term_debt",
    "long_term_debt", "total_debt", "capex", "free_cash_flow",
    "financing_cash_flow", "investing_cash_flow", "income_tax_expense",
    "debt_ratio", "equity_ratio", "financial_leverage", "asset_turnover",
    "net_margin", "roe", "roa", "current_ratio", "interest_coverage",
]


def mdump(m) -> dict:
    return {k: getattr(m, k) for k in FIELDS if getattr(m, k, None) is not None}


def cb(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main() -> int:
    raw = PDF.read_bytes()
    t0 = time.perf_counter()
    try:
        r = run_pipeline(PDF.name, raw, "شركة", progress_cb=cb)
    except Exception as e:  # noqa: BLE001
        print(f"PIPELINE FAILED: {type(e).__name__}: {e}", flush=True)
        return 1
    elapsed = time.perf_counter() - t0
    print(f"[{time.strftime('%H:%M:%S')}] pipeline done in {elapsed:.0f}s", flush=True)

    from src.analysis.peers import detect_anomalies
    try:
        from src.analysis.portfolio import load_records
        records = load_records()
    except Exception:
        records = []

    curr = r["curr_metrics"]
    prev = r["prev_metrics"]
    flags = red_flag_analysis(prev, curr)
    hs = compute_health_score(curr)
    bn = beneish_m_score(prev, curr)
    acad = academic_models(curr)
    anomalies = detect_anomalies(curr, r["company"], r["curr_year"], records=records)

    out = {
        "elapsed_s": round(elapsed, 1),
        "company": r["company"],
        "currency_hint": r.get("currency_hint"),
        "years": r["metric_years_available"],
        "prev_year": r["prev_year"],
        "curr_year": r["curr_year"],
        "prev": mdump(prev),
        "curr": mdump(curr),
        "rows_count": len(r["rows"]),
        "missing": r["missing"],
        "notes": r["notes"],
        "confidence": r.get("confidence") or {},
        "library_records": len(records),
        "health": {"total": hs.total, "label": hs.label,
                   "pillars": {p.key: p.score for p in hs.pillars}},
        "red_flags": [{"name": f.name, "severity": f.severity, "detail": f.detail} for f in flags],
        "beneish": {"m_score": bn.m_score, "zone": bn.zone,
                    "missing": bn.missing, "components": bn.components},
        "academic": [{"key": m.key, "value": m.value, "zone": m.zone,
                      "verdict": m.verdict, "missing": m.missing,
                      "components": m.components} for m in acad],
        "anomalies": [{"metric": a.metric, "label": a.label, "z": a.z,
                       "verdict": a.verdict} for a in anomalies],
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"saved {OUT.name}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
