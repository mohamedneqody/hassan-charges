# -*- coding: utf-8 -*-
"""Real-document benchmark (المهمة 5) — Telecom Egypt, SAME images, SAME GT.

Routes compared:
  A  Full-page LOCAL OCR only     (degradation path, focused pass OFF)
  B  A + FOCUSED LOCAL CELL OCR   (degradation path, focused pass ON)
  C  Vision REPLAY                (the frozen d010bd8 holdout artifact — a
      PAST live run, not re-executed; labeled as replay, never compared to
      a live run as if equal)

Per cell: Correct Field | Correct Row | Correct Year | Correct BBox |
Signed Exact | Verification Status | Decisive. NO GT is used during
extraction — GT only scores afterwards.

Output: cell_evidence/te_local_benchmark.json
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ))

PDF = PROJ / "independent_docs/te_holdout/te_standalone_h1_2024.pdf"
GT = json.loads((PROJ / "independent_docs/te_holdout/gt_te_frozen.json")
                .read_text(encoding="utf-8"))
YEARS = ("2024", "2023")


def _run(route: str, focused: bool) -> dict:
    from src.analysis.financial_gate import decide
    from src.extraction.file_parsers import load_financial_data

    raw = PDF.read_bytes()
    old = os.environ.get("FOCUSED_LOCAL_VERIFY")
    os.environ["FOCUSED_LOCAL_VERIFY"] = "1" if focused else "0"
    t0 = time.time()
    try:
        data = load_financial_data(PDF.name, raw, fast_mode=True)
        dl = {(e["field"], e["year"]): e
              for e in __import__("src.extraction.normalizer",
                                  fromlist=["build_decision_log"])
              .build_decision_log(data)}
        cells = {}
        for f in data.candidates:
            for y in data.candidates[f]:
                e = dl.get((f, y))
                layers = sorted(set(data.candidate_layers.get(f, {}).get(y, [])))
                bbox = data.candidate_bbox.get(f, {}).get(y)
                cells[f"{f}|{y}"] = {
                    "captured": data.values.get(f, {}).get(y),
                    "status": e["status"] if e else None,
                    "gate": decide(e["status"]) if e else "missing",
                    "source": e["source"] if e else None,
                    "layers": layers,
                    "local_bbox": (bbox[-1] if bbox else None),
                }
        out = {"seconds": round(time.time() - t0, 1), "cells": cells,
               "notes_tail": [n for n in data.notes
                              if "Focused" in n or "Local-only" in n][:4]}
    finally:
        if old is None:
            os.environ.pop("FOCUSED_LOCAL_VERIFY", None)
        else:
            os.environ["FOCUSED_LOCAL_VERIFY"] = old
    return out


def _score(cells: dict) -> dict:
    """GT scoring AFTER extraction — never during candidate selection."""
    per_cell = []
    for y in YEARS:
        for f, m in GT["cells"][y].items():
            key = f"{f}|{int(y)}"
            c = cells.get(key)
            gt_v = float(m["value"])
            cap = c["captured"] if c else None
            signed = (cap is not None
                      and abs(cap - gt_v) <= max(1000.0, 1e-6 * abs(gt_v)))
            mag = (cap is not None
                   and abs(abs(cap) - abs(gt_v)) <= max(1000.0,
                                                        1e-6 * abs(gt_v)))
            per_cell.append({
                "field": f, "year": int(y), "gt": gt_v,
                "captured": cap,
                "correct_field": c is not None,
                "correct_row": mag,     # value from the RIGHT printed row
                "correct_year": c is not None and int(y) in
                (int(k.split("|")[1]) for k in cells if k.startswith(f + "|")),
                "correct_bbox": bool(c and c.get("local_bbox")),
                "signed_exact": signed,
                "magnitude_only": mag and not signed,
                "status": c["status"] if c else "NOT_CAPTURED",
                "gate": c["gate"] if c else "missing",
                "decisive": c["gate"] in ("use", "use_disclosed") if c else False,
            })
    n = len(per_cell)
    allowed = [r for r in per_cell if r["decisive"]]
    return {
        "gt_cells": n,
        "captured": sum(1 for r in per_cell if r["captured"] is not None),
        "field_mapping_rate": round(sum(1 for r in per_cell
                                        if r["correct_field"]) / n, 3),
        "signed_exact_match_accuracy": round(sum(1 for r in per_cell
                                                 if r["signed_exact"]) / n, 3),
        "automatic_decisive_coverage": round(len(allowed) / n, 3),
        "false_acceptances": sum(1 for r in allowed if not r["correct_row"]),
        "far": (round(sum(1 for r in allowed if not r["correct_row"])
                      / len(allowed), 3) if allowed else None),
        "correct_blocked": sum(1 for r in per_cell
                               if r["correct_row"] and not r["decisive"]),
        "wrong_blocked": sum(1 for r in per_cell
                             if not r["correct_row"]
                             and r["captured"] is not None
                             and not r["decisive"]),
        "missing": sum(1 for r in per_cell if r["captured"] is None),
        "with_bbox": sum(1 for r in per_cell if r["correct_bbox"]),
        "per_cell": per_cell,
    }


def main() -> None:
    print("route A: full-page local OCR (focused OFF)…")
    a = _run("A", focused=False)
    print("  seconds:", a["seconds"])
    print("route B: + focused local cell OCR (focused ON)…")
    b = _run("B", focused=True)
    print("  seconds:", b["seconds"])

    frozen = json.loads((PROJ / "cell_evidence/holdout_te_results.json")
                        .read_text(encoding="utf-8"))
    c_cells = {f"{r['field']}|{r['year']}":
               {"captured": r["captured"], "status": r["status"],
                "gate": r["gate"], "source": r["source"], "layers": None,
                "local_bbox": None}
               for r in frozen["rows"]}

    out = {
        "document": PDF.name,
        "sha256": GT["sha256"],
        "same_images_same_gt": True,
        "no_gt_in_selection": "GT used only for scoring afterwards",
        "A_fullpage_local": {**_score(a["cells"]),
                             "seconds": a["seconds"],
                             "notes": a["notes_tail"]},
        "B_focused_local": {**_score(b["cells"]),
                            "seconds": b["seconds"],
                            "notes": b["notes_tail"]},
        "C_vision_REPLAY_frozen": {**_score(c_cells),
                                   "seconds": frozen["run"]["seconds"],
                                   "note": "REPLAY of the d010bd8 live run "
                                           "(frozen artifact) — NOT a live "
                                           "run; never compared as equal "
                                           "to live"},
        "A_cells": a["cells"], "B_cells": b["cells"],
    }
    dst = PROJ / "cell_evidence/te_local_benchmark.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    for route in ("A_fullpage_local", "B_focused_local",
                  "C_vision_REPLAY_frozen"):
        m = out[route]
        print(f"{route:24s} signed={m['signed_exact_match_accuracy']} "
              f"decisive={m['automatic_decisive_coverage']} "
              f"captured={m['captured']}/{m['gt_cells']} "
              f"FA={m['false_acceptances']} "
              f"correct_blocked={m['correct_blocked']} "
              f"missing={m['missing']} with_bbox={m['with_bbox']}")
    print(f"artifact: {dst}")


if __name__ == "__main__":
    main()
