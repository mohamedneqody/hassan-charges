#!/usr/bin/env python3
"""Benchmark orchestrator for Indra OCR (CPU only).

For every core count N in --core-list and every repeat:
  - spawns scripts/bench_child.py pinned to N *physical* cores via
    taskset -c 0-(2N-1)  (this CPU has 2 logical CPUs per physical core,
    verified with lscpu -e), collecting load/warmup/infer timings and
    CPU/RAM samples into benchmarks/runs/*.json;
  - once per core count, runs the official CLI end-to-end the same way
    (the wall time a real user sees) and saves its JSONL output.

Writes benchmarks/results.csv with one row per measurement. No numbers are
invented: every value comes from a executed run.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJ = Path(os.environ["INDRA_BENCH_PROJ"]) if os.environ.get("INDRA_BENCH_PROJ") else Path(__file__).resolve().parents[1]
VENV_BIN = Path.home() / "indra-ocr-bench" / ".venv" / "bin"


def cli_run(args, cores: int, cpus: str, runs_dir: Path) -> dict:
    out_jsonl = runs_dir / f"cli_c{cores}.jsonl"
    cmd = [
        "taskset", "-c", cpus, str(VENV_BIN / "indra-ocr"),
        args.pdf, "--mode", args.mode, "--cores", str(cores),
        "--format", "json", "--timings",
    ]
    t0 = time.perf_counter()
    r = subprocess.run(cmd, capture_output=True, text=True)
    wall = time.perf_counter() - t0
    out_jsonl.write_text(r.stdout, encoding="utf-8")
    (runs_dir / f"cli_c{cores}.stderr").write_text(r.stderr, encoding="utf-8")
    pages_ok = 0
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                if json.loads(line).get("source") != "error":
                    pages_ok += 1
            except json.JSONDecodeError:
                pass
    return {"pages_ok": pages_ok, "wall_s": round(wall, 3), "rc": r.returncode}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--core-list", default="1,2,4,8")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--pdf", default=str(PROJ / "test_data" / "pdfs" / "bench_40p.pdf"))
    ap.add_argument("--warmup-pdf", default=str(PROJ / "test_data" / "pdfs" / "warmup_1p.pdf"))
    ap.add_argument("--mode", default="ocr")
    ap.add_argument("--skip-cli", action="store_true")
    args = ap.parse_args()

    runs_dir = PROJ / "benchmarks" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    csv_path = PROJ / "benchmarks" / "results.csv"
    rows: list[dict] = []

    for cores in [int(c) for c in args.core_list.split(",") if c.strip()]:
        cpus = f"0-{2 * cores - 1}"  # logical pairs -> physical cores
        for rep in range(1, args.repeats + 1):
            out_json = runs_dir / f"api_c{cores}_r{rep}.json"
            pre_t = time.time()
            cmd = [
                "taskset", "-c", cpus, str(VENV_BIN / "python"),
                str(PROJ / "scripts" / "bench_child.py"),
                "--pdf", args.pdf, "--warmup-pdf", args.warmup_pdf,
                "--cores", str(cores), "--mode", args.mode, "--out", str(out_json),
            ]
            t0 = time.perf_counter()
            r = subprocess.run(cmd, capture_output=True, text=True)
            proc_wall = time.perf_counter() - t0
            if r.returncode != 0:
                print(f"CHILD FAILED cores={cores} rep={rep}\n{r.stderr[-2000:]}", file=sys.stderr)
                rows.append({
                    "kind": "api", "cores": cores, "repeat": rep, "status": "failed",
                    "process_wall_s": round(proc_wall, 3),
                    "ts": datetime.now(timezone.utc).isoformat(),
                })
                continue
            d = json.loads(out_json.read_text(encoding="utf-8"))
            boot_s = round(d["boot_wall_t"] - pre_t, 3)
            row = {
                "kind": "api", "cores": cores, "repeat": rep, "status": "ok",
                "affinity_cores": d["affinity_cores"],
                "boot_s": boot_s,
                "import_s": d["import_s"],
                "load_s": d["load_s"],
                "warmup_s": d["warmup_s"],
                "infer_wall_s": d["run1"]["wall_s"],
                "pps_wall": d["run1"]["pps_wall"],
                "pages_ok": d["run1"]["pages_ok"],
                "page_ms_mean": d["run1"]["page_ms_mean"],
                "page_ms_median": d["run1"]["page_ms_median"],
                "page_ms_p95": d["run1"]["page_ms_p95"],
                "infer2_wall_s": d["run2"]["wall_s"],
                "pps_wall_warm": d["run2"]["pps_wall"],
                "cpu_sys_avg_pct": d["resources_infer"]["cpu_sys_avg_pct"],
                "cpu_tree_avg_pct": d["resources_infer"]["cpu_tree_avg_pct"],
                "rss_peak_mb": d["resources_infer"]["rss_peak_mb"],
                "process_wall_s": round(proc_wall, 3),
                "ts": d["ts"],
            }
            rows.append(row)
            print(
                f"api cores={cores} rep={rep}: load={row['load_s']}s warmup={row['warmup_s']}s "
                f"infer={row['infer_wall_s']}s pps={row['pps_wall']} "
                f"(warm {row['pps_wall_warm']}) cpu={row['cpu_tree_avg_pct']}% rss={row['rss_peak_mb']}MB",
                flush=True,
            )
        if not args.skip_cli:
            c = cli_run(args, cores, cpus, runs_dir)
            rows.append({
                "kind": "cli", "cores": cores, "repeat": 0, "status": "ok" if c["rc"] == 0 else "failed",
                "pages_ok": c["pages_ok"], "process_wall_s": c["wall_s"],
                "pps_wall": round(c["pages_ok"] / c["wall_s"], 3) if c["wall_s"] > 0 else None,
                "ts": datetime.now(timezone.utc).isoformat(),
            })
            print(f"cli cores={cores}: wall={c['wall_s']}s pages_ok={c['pages_ok']}", flush=True)

    fields = sorted({k for r in rows for k in r})
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {csv_path} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
