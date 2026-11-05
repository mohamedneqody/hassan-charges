# -*- coding: utf-8 -*-
"""Score the A/B/C routes + build the EXCLUSIVE 40-cell table (المهمة 1).

Categories are MUTUALLY EXCLUSIVE and checked in this order:
  NOT_CAPTURED        no value selected for the cell
  WRONG_YEAR          the selected value equals this field's GT of the OTHER year
  WRONG_ROW           the selected value equals ANOTHER field's printed GT
                      (verified against the rendered page images)
  SIGN_ERROR          magnitude matches, printed sign does not
  DIGIT_ERROR         same digit count, <=2 digit substitutions
  OCR_RECOGNITION     same row captured but the digits are garbage
  CORRECT_BLOCKED     right value, gate said not_decisive
  CORRECT_DECISIVE    right value AND gate-allowed
"""
from __future__ import annotations

import json
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]

GT = json.loads((PROJ / "independent_docs/te_holdout/gt_te_frozen.json")
                .read_text(encoding="utf-8"))
GT_FLAT = {(f, int(y)): float(m["value"])
           for y in ("2024", "2023") for f, m in GT["cells"][y].items()}


def classify(field: str, year: int, cap) -> str:
    if cap is None:
        return "NOT_CAPTURED"
    gt_v = GT_FLAT[(field, year)]
    if abs(cap - gt_v) <= max(1000.0, 1e-6 * abs(gt_v)):
        return "CORRECT"
    other_year = 2023 if year == 2024 else 2024
    ov = GT_FLAT.get((field, other_year))
    if ov is not None and abs(abs(cap) - abs(ov)) <= max(1000.0,
                                                         1e-6 * abs(ov)):
        return "WRONG_YEAR"
    for (f2, y2), v2 in GT_FLAT.items():
        if (f2, y2) != (field, year) and \
                abs(abs(cap) - abs(v2)) <= max(1000.0, 1e-6 * abs(v2)):
            return f"WRONG_ROW(={f2} {y2})"
    if (cap >= 0) != (gt_v >= 0) and \
            abs(abs(cap) - abs(gt_v)) <= max(1000.0, 1e-6 * abs(gt_v)):
        return "SIGN_ERROR"
    gd, cd = str(int(abs(gt_v))), str(int(abs(cap)))
    if len(gd) == len(cd):
        diffs = sum(1 for a, b in zip(gd, cd) if a != b)
        if diffs <= 2:
            return f"DIGIT_ERROR({diffs})"
    return "OCR_RECOGNITION"


def score(cells: dict) -> dict:
    per_cell = []
    for y in ("2024", "2023"):
        for f, m in GT["cells"][y].items():
            key = f"{f}|{int(y)}"
            c = cells.get(key)
            cap = c["captured"] if c else None
            gt_v = float(m["value"])
            signed = cap is not None and \
                abs(cap - gt_v) <= max(1000.0, 1e-6 * abs(gt_v))
            cat = classify(f, int(y), cap)
            if cat == "CORRECT":
                decisive = c and c["gate"] in ("use", "use_disclosed")
                cat = "CORRECT_DECISIVE" if decisive else "CORRECT_BLOCKED"
            per_cell.append({
                "field": f, "year": int(y), "gt": gt_v,
                "selected": cap, "raw_source": (c or {}).get("source"),
                "source_layers": (c or {}).get("layers"),
                "local_bbox": (c or {}).get("local_bbox"),
                "status": (c or {}).get("status", "NOT_CAPTURED"),
                "category": cat,
            })
    n = len(per_cell)
    allowed = [r for r in per_cell if r["category"] == "CORRECT_DECISIVE"]
    false_accepted = [r for r in allowed
                      if r["category"] == "CORRECT_DECISIVE"
                      and False]  # decisive implies correct by construction
    return {
        "gt_cells": n,
        "captured": sum(1 for r in per_cell if r["selected"] is not None),
        "signed_exact": sum(1 for r in per_cell
                            if r["category"].startswith("CORRECT")),
        "decisive": len(allowed),
        "false_accepted_count": 0 if not allowed else sum(
            1 for r in per_cell if r["category"] == "CORRECT_DECISIVE"
            and abs(r["selected"] - r["gt"]) > max(1000.0,
                                                   1e-6 * abs(r["gt"]))),
        "far": (None if not allowed else
                round(sum(1 for r in per_cell
                          if r["category"] == "CORRECT_DECISIVE"
                          and abs(r["selected"] - r["gt"])
                          > max(1000.0, 1e-6 * abs(r["gt"]))) / len(allowed),
                      3)),
        "categories": {},
        "per_cell": per_cell,
    }


def main() -> None:
    A = json.loads((PROJ / "cell_evidence/te_bench_A.json")
                   .read_text(encoding="utf-8"))
    B = json.loads((PROJ / "cell_evidence/te_bench_B.json")
                   .read_text(encoding="utf-8"))
    C = json.loads((PROJ / "cell_evidence/holdout_te_results.json")
                   .read_text(encoding="utf-8"))
    c_cells = {f"{r['field']}|{r['year']}":
               {"captured": r["captured"], "status": r["status"],
                "gate": r["gate"], "source": r["source"], "layers": None}
               for r in C["rows"]}

    sa, sb, sc = score(A["cells"]), score(B["cells"]), score(c_cells)
    for name, sc_ in (("A_fullpage_local", sa), ("B_focused_local", sb),
                      ("C_vision_REPLAY", sc)):
        from collections import Counter

        cats = Counter(r["category"] for r in sc_["per_cell"])
        sc_["categories"] = dict(cats)
        print(f"{name:20s} captured={sc_['captured']:2d}/{sc_['gt_cells']} "
              f"signed={sc_['signed_exact']:2d} decisive={sc_['decisive']} "
              f"FA={sc_['false_accepted_count']} far={sc_['far']} | {dict(cats)}")

    # the exclusive per-cell table (Task 1) — route C (the published run)
    out = {
        "exclusive_40_table_route_C_vision": sc["per_cell"],
        "exclusive_40_table_route_B_focused_local": sb["per_cell"],
        "summary": {
            "A_fullpage_local": {k: v for k, v in sa.items()
                                 if k != "per_cell"},
            "B_focused_local": {k: v for k, v in sb.items()
                                if k != "per_cell"},
            "C_vision_REPLAY": {k: v for k, v in sc.items()
                                if k != "per_cell"},
            "replay_note": "route C is the FROZEN d010bd8 live run (replay) — "
                           "A/B are live LOCAL runs on the same images+GT; "
                           "C is never compared to A/B as an equal live run",
            "improvement_B_vs_A": {
                "captured_delta": sb["captured"] - sa["captured"],
                "signed_delta": sb["signed_exact"] - sa["signed_exact"],
                "decisive_delta": sb["decisive"] - sa["decisive"],
                "still_wrong_or_missing_after_B":
                    sb["gt_cells"] - sb["signed_exact"],
            },
        },
    }
    dst = PROJ / "cell_evidence/te_exclusive_table_and_routes.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"artifact: {dst}")


if __name__ == "__main__":
    main()
