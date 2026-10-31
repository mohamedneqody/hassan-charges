#!/usr/bin/env python3
"""Summarize benchmark run JSONs: per-page times and parallel efficiency."""
import json
import time
from pathlib import Path

RUNS = Path.home() / "mnt_placeholder"  # replaced below
PROJ = Path("/mnt/d/hassan_charges/مشروع تخرج حسن/indra-ocr-benchmark")
RUNS = PROJ / "benchmarks" / "runs"

print(f"{'cores':>5} {'rep':>3} {'wall1':>7} {'psum_s':>7} {'pmean_ms':>8} {'pmed_ms':>8} {'p95_ms':>7} {'eff':>5}")
for c in (1, 2, 4, 8):
    for r in (1, 2, 3):
        d = json.loads((RUNS / f"api_c{c}_r{r}.json").read_text())
        r1 = d["run1"]
        eff = (r1["page_ms_sum_s"] or 0) / (r1["wall_s"] * max(c, 1))
        print(
            f"{c:>5} {r:>3} {r1['wall_s']:>7.2f} {r1['page_ms_sum_s']:>7.2f} "
            f"{r1['page_ms_mean']:>8.0f} {r1['page_ms_median']:>8.0f} {r1['page_ms_p95']:>7.0f} {eff:>5.2f}"
        )
print()
import psutil

psutil.cpu_percent(None)
time.sleep(3)
print("system idle CPU (3s sample):", f"{psutil.cpu_percent(interval=3)}%")
