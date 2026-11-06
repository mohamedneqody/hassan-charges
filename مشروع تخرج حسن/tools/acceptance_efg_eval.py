# -*- coding: utf-8 -*-
"""ACCEPTANCE holdout run #1 — EFG Holding FY2024 (شركة مصرية رابعة).

FROZEN PROTOCOL: the code, matching rules and parameters are FROZEN at
commit f6172ab. This script runs the pipeline ONCE on the full PDF (55
pages, no trimming) and scores against the frozen visual GT. NOTHING is
tuned on this document — errors are reported with their stage, never fixed
here. Zero API calls (born-digital PDF → the native text path).

Output: cell_evidence/acceptance_efg_results.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ))

DOC = PROJ / "independent_docs/efg_holdout/efg_standalone_fy2024.pdf"
GT = json.loads((PROJ / "independent_docs/efg_holdout/gt_efg_frozen.json")
                .read_text(encoding="utf-8"))

CRITICAL = {"revenue", "net_income", "total_assets", "total_liabilities",
            "equity", "operating_cash_flow", "current_assets",
            "current_liabilities"}


def main() -> dict:
    from src.analysis.financial_gate import decide
    from src.extraction.file_parsers import load_financial_data
    from src.extraction.normalizer import build_decision_log

    raw = DOC.read_bytes()
    t0 = time.time()
    data = load_financial_data(DOC.name, raw)          # NO fast_mode needed
    elapsed = time.time() - t0
    dl = {(e["field"], e["year"]): e for e in build_decision_log(data)}
    years_detected = sorted(data.years)

    # profile for the record
    try:
        from src.extraction.document_profiler import profile_pdf
        import pdfplumber

        with pdfplumber.open(io.BytesIO(raw)) if False else None:
            pass
    except Exception:
        pass

    rows = []
    for y in ("2024", "2023"):
        for field, meta in GT["cells"][y].items():
            y_i = int(y)
            gt_v = float(meta["value"])
            captured = data.values.get(field, {}).get(y_i)
            entry = dl.get((field, y_i))
            status = entry["status"] if entry else "NOT_CAPTURED"
            gate = decide(status)
            mag_ok = (captured is not None
                      and abs(abs(captured) - abs(gt_v))
                      <= max(1000.0, 1e-6 * abs(gt_v)))
            signed = mag_ok and ((captured >= 0) == (gt_v >= 0))
            rows.append({
                "field": field, "year": y_i, "gt": gt_v,
                "captured": captured, "status": status, "gate": gate,
                "source": entry["source"] if entry else None,
                "magnitude_match": mag_ok, "signed_exact": signed,
                "false_accept": gate in ("use", "use_disclosed")
                and not mag_ok,
            })

    def rate(num: int, den: int) -> float | None:
        return round(num / den, 3) if den else None

    n = len(rows)
    allowed = [r for r in rows if r["gate"] in ("use", "use_disclosed")]
    gated = [r for r in rows if r["gate"] == "not_decisive"]
    crit_rows = [r for r in rows if r["field"] in CRITICAL]
    crit_ok = [r for r in crit_rows if r["gate"] in ("use", "use_disclosed")
               and r["magnitude_match"]]

    out = {
        "acceptance_holdout": True,
        "document": DOC.name,
        "sha256": GT["sha256"],
        "company": GT["company"],
        "scope_declaration": GT["scope"],
        "frozen_code": "f6172ab — no code/rules/param changes during the test",
        "gt_protocol": GT["gt_built_by"] + "; all printed, zero derived",
        "gt_cells": n,
        "run": {"seconds": round(elapsed, 1)},
        "years": {"detected": years_detected, "expected": [2023, 2024],
                  "ok": sorted(years_detected)[-2:] == [2023, 2024]},
        "captured": sum(1 for r in rows if r["captured"] is not None),
        "signed_exact_match_accuracy": rate(
            sum(1 for r in rows if r["signed_exact"]), n),
        "magnitude_only_match_accuracy": rate(
            sum(1 for r in rows if r["magnitude_match"]), n),
        "missing": sum(1 for r in rows if r["captured"] is None),
        "automatic_decisive_coverage": rate(len(allowed), n),
        "false_accepted_count": sum(1 for r in allowed
                                    if not r["magnitude_match"]),
        "far": rate(sum(1 for r in allowed if not r["magnitude_match"]),
                    len(allowed)),
        "critical_field_coverage": rate(len(crit_ok), len(crit_rows)),
        "source_mix": {},
        "metrics_definitions": {
            "signed_exact": "field + year + printed sign + value",
            "denominators": "signed/missing/critical over n=28 (14 fields x "
                            "2 years); FAR over the decisive count",
        },
        "rows": rows,
    }
    for r in rows:
        if r["source"]:
            out["source_mix"][r["source"]] = \
                out["source_mix"].get(r["source"], 0) + 1
    try:
        out["document_profile"] = data.document_profile
    except Exception:
        pass

    dst = PROJ / "cell_evidence/acceptance_efg_results.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    slim = {k: v for k, v in out.items() if k != "rows"}
    print(json.dumps(slim, ensure_ascii=False, indent=1))
    print(f"artifact: {dst}")
    return out


if __name__ == "__main__":
    main()
