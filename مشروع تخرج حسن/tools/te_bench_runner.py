# -*- coding: utf-8 -*-
"""One-route runner (isolated process) for the TE local benchmark."""
import json
import os
import sys
import time
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ))

route = sys.argv[1]                    # A | B
focused = route == "B"
os.environ["FOCUSED_LOCAL_VERIFY"] = "1" if focused else "0"

from src.analysis.financial_gate import decide              # noqa: E402
from src.extraction.file_parsers import load_financial_data  # noqa: E402
from src.extraction.normalizer import build_decision_log     # noqa: E402

PDF = PROJ / "independent_docs/te_holdout/te_standalone_h1_2024.pdf"
raw = PDF.read_bytes()
t0 = time.time()
data = load_financial_data(PDF.name, raw, fast_mode=True)
elapsed = time.time() - t0
dl = {(e["field"], e["year"]): e for e in build_decision_log(data)}
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
out = {
    "route": route,
    "seconds": round(elapsed, 1),
    "cells": cells,
    "notes_tail": [n for n in data.notes
                   if "Focused" in n or "Local-only" in n][:4],
}
dst = PROJ / f"cell_evidence/te_bench_{route}.json"
dst.write_text(json.dumps(out, ensure_ascii=False, indent=1),
               encoding="utf-8")
print(f"route {route}: {elapsed:.1f}s, {len(cells)} cells -> {dst.name}")
