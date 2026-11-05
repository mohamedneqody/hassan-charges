# -*- coding: utf-8 -*-
"""REAL Egyptian statements evaluation — AbuQir Fertilizers (المهمة 2).

FROZEN PROTOCOL (مجمّد قبل التشغيل):
  1. GT was built by visual reading of the rendered statement pages
     (independent_docs/abuqir_2023/gt_abuqir_frozen.json) — it NEVER feeds
     extraction decisions; the pipeline runs exactly as any upload would.
  2. Extraction code is the committed pipeline — nothing tuned for this
     document. Zero API (the PDF has a text layer → the NATIVE_PDF_TEXT
     path; the text layer itself is OCR-garbled, which is the real test).
  3. Measures: year assignment, field mapping, exact match (signed AND
     magnitude-only, because expense lines print negative), decisive
     coverage by source-aware gate, false acceptances (SERIOUS: a decisive
     wrong value), abstention, critical-field coverage.
  4. Scope declared: SEPARATE statements (standalone) — never mixed with
     the consolidated set the notes also reference.

Output: cell_evidence/abuqir_eval_results.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ))

DOC = PROJ / "independent_docs/abuqir_2023/abuqir_fs_fy2025.pdf"
GT = json.loads(
    (PROJ / "independent_docs/abuqir_2023/gt_abuqir_frozen.json")
    .read_text(encoding="utf-8"))
YEAR_MAP = {"FY2025": 2025, "FY2024": 2024}

CRITICAL = {"revenue", "net_income", "total_assets", "total_liabilities",
            "total_equity", "operating_cash_flow", "current_assets",
            "current_liabilities", "equity"}


def main() -> dict:
    from src.analysis.financial_gate import decide
    from src.extraction.file_parsers import load_financial_data
    from src.extraction.normalizer import build_decision_log

    raw = DOC.read_bytes()
    data = load_financial_data(DOC.name, raw)
    dl = {(e["field"], e["year"]): e for e in build_decision_log(data)}
    years_detected = sorted(data.years)

    rows = []
    for fy, y in YEAR_MAP.items():
        for field, meta in GT["cells"][fy].items():
            gt_v = float(meta["value"])
            captured = data.values.get(field, {}).get(y)
            entry = dl.get((field, y))
            status = entry["status"] if entry else "NOT_CAPTURED"
            gate = decide(status)
            mag_ok = (captured is not None
                      and abs(abs(captured) - abs(gt_v))
                      <= max(1.0, 1e-6 * abs(gt_v)))
            sign_ok = mag_ok and ((captured >= 0) == (gt_v >= 0))
            canonical_field = field if entry else None
            rows.append({
                "field": field, "year": y, "gt": gt_v,
                "gt_note": meta.get("note", "") or meta.get("derived_gt", ""),
                "captured": captured,
                "status": status, "gate": gate,
                "source": entry["source"] if entry else None,
                "magnitude_match": mag_ok,
                "signed_exact": sign_ok,
                "false_accept": (gate in ("use", "use_disclosed")
                                 and not mag_ok),
            })

    def rate(num: int, den: int) -> float | None:
        return round(num / den, 3) if den else None

    n = len(rows)
    allowed = [r for r in rows if r["gate"] in ("use", "use_disclosed")]
    gated = [r for r in rows if r["gate"] == "not_decisive"]
    missing = [r for r in rows if r["gate"] == "missing"]
    mapped = [r for r in rows if r["status"] != "NOT_CAPTURED"]
    mag_exact = sum(1 for r in rows if r["magnitude_match"])
    signed_exact = sum(1 for r in rows if r["signed_exact"])
    false_accepts = [r for r in allowed if not r["magnitude_match"]]
    crit_rows = [r for r in rows if r["field"] in CRITICAL]
    crit_ok = [r for r in crit_rows if r["gate"] in ("use", "use_disclosed")
               and r["magnitude_match"]]

    out = {
        "document": DOC.name,
        "sha256": GT["sha256"],
        "company": GT["company"],
        "scope_declaration": GT["scope"],
        "gt_protocol": "visual reading of rendered pages, frozen before the "
                       "run, never used in extraction decisions",
        "gt_cells": n,
        "years": {"detected": years_detected, "expected": [2024, 2025],
                  "ok": years_detected == [2024, 2025]},
        "field_mapping_rate": rate(len(mapped), n),
        "automatic_exact_match_accuracy_magnitude": rate(mag_exact, n),
        "automatic_exact_match_accuracy_signed": rate(signed_exact, n),
        "automatic_decisive_coverage": rate(len(allowed), n),
        "end_to_end_accuracy_decisive_and_correct": rate(
            sum(1 for r in allowed if r["magnitude_match"]), n),
        "false_acceptance_rate": rate(len(false_accepts), len(allowed)),
        "false_acceptances": [
            {"field": r["field"], "year": r["year"], "gt": r["gt"],
             "captured": r["captured"], "status": r["status"]}
            for r in false_accepts],
        "correct_values_blocked": sum(1 for r in gated if r["magnitude_match"]),
        "wrong_values_blocked": sum(1 for r in gated if not r["magnitude_match"]),
        "missing_values": len(missing),
        "critical_field_coverage": rate(len(crit_ok), len(crit_rows)),
        "source_mix": {},
        "rows": rows,
    }
    for r in rows:
        if r["source"]:
            out["source_mix"][r["source"]] = \
                out["source_mix"].get(r["source"], 0) + 1

    # ── vision-path comparison (الموجود أصلًا — لا طبقة جديدة) ──
    # The production dispatch only reaches the vision path when the text
    # layer yields NO tables; this document has a pathological-but-nonempty
    # text layer, so the vision run is a DIRECT measurement of the existing
    # layer (statement pages only, fast_mode, live Gemini rotation).
    vision_summary: dict = {"ran": False}
    try:
        from src.extraction.normalizer import build_decision_log as _bdl
        from src.extraction.vision_ocr import extract_via_vision

        vdata = extract_via_vision(raw, [], page_range=(4, 10),
                                   fast_mode=True)
        vrows = []
        for fy, y in YEAR_MAP.items():
            for field, meta in GT["cells"][fy].items():
                gt_v = float(meta["value"])
                cap = vdata.values.get(field, {}).get(y)
                mag_ok = (cap is not None
                          and abs(abs(cap) - abs(gt_v))
                          <= max(1.0, 1e-6 * abs(gt_v)))
                vrows.append({"field": field, "year": y, "gt": gt_v,
                              "captured": cap, "magnitude_match": mag_ok})
        v_exact = sum(1 for r in vrows if r["magnitude_match"])
        v_false = [{"field": r["field"], "year": r["year"], "gt": r["gt"],
                    "captured": r["captured"]}
                   for r in vrows
                   if r["captured"] is not None and not r["magnitude_match"]]
        vision_summary = {
            "ran": True, "pages": "5-10", "fast_mode": True,
            "magnitude_exact": v_exact, "gt_cells": len(vrows),
            "rate": rate(v_exact, len(vrows)),
            "wrong_captures": v_false[:8],
            "note": "measurement run — the production dispatch keeps the "
                    "text path when ANY tables parse; auto-fallback for "
                    "pathological text layers is future work",
        }
    except Exception as exc:
        vision_summary = {"ran": False,
                          "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    out["vision_path_comparison"] = vision_summary

    dst = PROJ / "cell_evidence/abuqir_eval_results.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    slim = {k: v for k, v in out.items() if k != "rows"}
    print(json.dumps(slim, ensure_ascii=False, indent=1))
    print(f"artifact: {dst}")
    return out


if __name__ == "__main__":
    main()
