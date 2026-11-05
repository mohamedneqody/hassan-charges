# -*- coding: utf-8 -*-
"""HOLDOUT evaluation — Telecom Egypt (المهمة 6: عينة استقطاب لمرة واحدة).

FROZEN PROTOCOL — this script runs the committed pipeline ONCE on a third
Egyptian company never used during development. Everything was frozen
before this run: extraction code, profiler thresholds, routing budgets,
matching rules, metric definitions (see metrics_definitions below), and the
GT protocol (visual page reading, frozen JSON). If this run's errors ever
motivate a code change, this sample is reclassified as a DEVELOPMENT set
and a NEW holdout must be chosen — its numbers are then never called
independent again.

Source type: SCANNED PDF with NO text layer (all 30 pages) → the
production dispatch routes it to the vision path (the pipeline's designed
route for scans). fast_mode=on (one sweep). Vision governed by the key
pool's rotation — per-model quotas, no flag needed for the SCANNED
dispatch (that path predates this round).

Output: cell_evidence/holdout_te_results.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ))

DOC = PROJ / "independent_docs/te_holdout/te_standalone_h1_2024.pdf"
GT = json.loads(
    (PROJ / "independent_docs/te_holdout/gt_te_frozen.json")
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
    data = load_financial_data(DOC.name, raw, fast_mode=True)
    elapsed = time.time() - t0
    dl = {(e["field"], e["year"]): e for e in build_decision_log(data)}
    years_detected = sorted(data.years)

    rows = []
    for y, meta_by_field in (("2024", GT["cells"]["2024"]),
                             ("2023", GT["cells"]["2023"])):
        y = int(y)
        for field, meta in meta_by_field.items():
            gt_v = float(meta["value"])
            captured = data.values.get(field, {}).get(y)
            entry = dl.get((field, y))
            status = entry["status"] if entry else "NOT_CAPTURED"
            gate = decide(status)
            mag_ok = (captured is not None
                      and abs(abs(captured) - abs(gt_v))
                      <= max(1000.0, 1e-6 * abs(gt_v)))   # unit = thousands
            sign_ok = mag_ok and ((captured >= 0) == (gt_v >= 0))
            rows.append({
                "field": field, "year": y, "gt": gt_v,
                "captured": captured,
                "status": status, "gate": gate,
                "source": entry["source"] if entry else None,
                "magnitude_match": mag_ok, "signed_exact": sign_ok,
                "false_accept": (gate in ("use", "use_disclosed")
                                 and not mag_ok),
            })

    def rate(num: int, den: int) -> float | None:
        return round(num / den, 3) if den else None

    n = len(rows)
    allowed = [r for r in rows if r["gate"] in ("use", "use_disclosed")]
    gated = [r for r in rows if r["gate"] == "not_decisive"]
    mapped = [r for r in rows if r["status"] != "NOT_CAPTURED"]
    mag_exact = sum(1 for r in rows if r["magnitude_match"])
    signed_exact = sum(1 for r in rows if r["signed_exact"])
    false_accepts = [r for r in allowed if not r["magnitude_match"]]
    crit_rows = [r for r in rows if r["field"] in CRITICAL]
    crit_ok = [r for r in crit_rows if r["gate"] in ("use", "use_disclosed")
               and r["magnitude_match"]]

    out = {
        "holdout": True,
        "document": DOC.name,
        "sha256": GT["sha256"],
        "company": GT["company"],
        "source_type": "SCANNED_PDF_NO_TEXT_LAYER",
        "scope_declaration": GT["scope"],
        "gt_protocol": "visual reading of rendered pages, frozen before the "
                       "run, never used in extraction decisions; zero GT "
                       "cells derived — all 34 printed lines",
        "run": {"seconds": round(elapsed, 1), "fast_mode": True},
        "gt_cells": n,
        "years": {"detected": years_detected, "expected": [2023, 2024],
                  "ok": sorted(years_detected)[-2:] == [2023, 2024]},
        "field_mapping_rate": rate(len(mapped), n),
        "signed_exact_match_accuracy": rate(signed_exact, n),
        "magnitude_only_match_accuracy": rate(mag_exact, n),
        "automatic_decisive_coverage": rate(len(allowed), n),
        "end_to_end_accuracy": rate(
            sum(1 for r in allowed if r["magnitude_match"]), n),
        "false_acceptance_rate": rate(len(false_accepts), len(allowed)),
        "false_acceptances": [
            {"field": r["field"], "year": r["year"], "gt": r["gt"],
             "captured": r["captured"], "status": r["status"]}
            for r in false_accepts],
        "correct_values_blocked": sum(1 for r in gated if r["magnitude_match"]),
        "wrong_values_blocked": sum(1 for r in gated
                                    if not r["magnitude_match"]),
        "critical_field_coverage": rate(len(crit_ok), len(crit_rows)),
        "human_assisted_coverage": 0.0,
        "source_mix": {},
        "metrics_definitions": {
            "signed_exact": "field + year + printed sign + value",
            "magnitude_only": "absolute value only — reported SEPARATELY, "
                              "never folded into signed-exact",
            "false_acceptance_rate": "decisive-and-wrong / decisive",
            "end_to_end": "decisive AND magnitude-correct",
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

    dst = PROJ / "cell_evidence/holdout_te_results.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    slim = {k: v for k, v in out.items() if k not in ("rows",)}
    print(json.dumps(slim, ensure_ascii=False, indent=1))
    print(f"artifact: {dst}")
    return out


if __name__ == "__main__":
    main()
