#!/usr/bin/env python3
"""One benchmark child process: a single measurement run.

Phases (all timed separately):
  import   - importing indra_ocr (interpreter start is measured by the parent)
  load     - indra_ocr.load(): model init in this process
  warmup   - OCR of a 1-page PDF, results discarded
  infer    - convert_many() over the benchmark PDF (worker pool, per-page
             timings taken from Page.timings)
  infer2   - identical second run (warm OS caches) for hot-run comparison

CPU/RAM sampling (psutil, 10 Hz) covers this process and all children
(the convert_many worker processes). The parent pins this process to the
wanted cores with taskset; sched_getaffinity is recorded as proof.

Run from benchmark.py, never directly. spawn-safe (guarded main).
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import threading
import time
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--warmup-pdf", required=True)
    ap.add_argument("--cores", type=int, required=True)
    ap.add_argument("--mode", default="ocr")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    import psutil

    proc = psutil.Process()
    boot_wall_t = time.time()  # parent compares against its own pre-spawn stamp

    phase = ["boot"]
    stop = threading.Event()
    samples: list[tuple[str, float, float, float]] = []

    def sampler() -> None:
        psutil.cpu_percent(None)
        proc.cpu_percent(None)
        for c in proc.children(recursive=True):
            try:
                c.cpu_percent(None)
            except psutil.Error:  # noqa: F821
                pass
        while not stop.is_set():
            cpu_sys = psutil.cpu_percent(interval=0.1)
            try:
                kids = proc.children(recursive=True)
                cpu_tree = proc.cpu_percent(None) + sum(
                    c.cpu_percent(None) for c in kids
                )
                rss = proc.memory_info().rss + sum(
                    c.memory_info().rss for c in kids
                )
            except Exception:  # noqa: BLE001  (worker exited mid-sample)
                cpu_tree, rss = 0.0, 0
            samples.append((phase[0], cpu_sys, cpu_tree, rss / 1048576.0))

    th = threading.Thread(target=sampler, daemon=True)
    th.start()

    t0 = time.perf_counter()
    import indra_ocr  # noqa: E402
    t_import = time.perf_counter() - t0

    t0 = time.perf_counter()
    conv = indra_ocr.load(threads=args.cores, mode=args.mode, dpi=200.0)
    t_load = time.perf_counter() - t0

    phase[0] = "warmup"
    t0 = time.perf_counter()
    list(conv.convert(args.warmup_pdf))
    t_warmup = time.perf_counter() - t0

    def pooled_run(tag: str) -> dict:
        phase[0] = tag
        t0 = time.perf_counter()
        results = list(
            indra_ocr.convert_many([args.pdf], cores=args.cores, mode=args.mode, dpi=200.0)
        )
        wall = time.perf_counter() - t0
        pages = []
        for _path, res in results:
            if isinstance(res, Exception):
                pages = []
                return {"error": str(res)}
            pages.extend(res)
        page_ms = [float(p.timings.get("total_ms", 0.0)) for _, p in pages]
        sources: dict[str, int] = {}
        for _, p in pages:
            sources[p.source] = sources.get(p.source, 0) + 1
        ok = sum(1 for _, p in pages if p.source != "error")
        sorted_ms = sorted(page_ms)
        p95 = sorted_ms[min(len(sorted_ms) - 1, int(0.95 * (len(sorted_ms) - 1)))] if sorted_ms else 0.0
        return {
            "wall_s": round(wall, 4),
            "pages_total": len(pages),
            "pages_ok": ok,
            "page_sources": sources,
            "page_ms_mean": round(statistics.fmean(page_ms), 1) if page_ms else None,
            "page_ms_median": round(statistics.median(page_ms), 1) if page_ms else None,
            "page_ms_p95": round(p95, 1) if page_ms else None,
            "page_ms_sum_s": round(sum(page_ms) / 1000.0, 3) if page_ms else None,
            "pps_wall": round(ok / wall, 3) if wall > 0 else None,
        }

    run1 = pooled_run("infer")
    run2 = pooled_run("infer2")

    phase[0] = "idle"
    stop.set()
    th.join()

    def phase_stats(names: list[str]) -> dict:
        sel = [s for s in samples if s[0] in names]
        if not sel:
            return {"cpu_sys_avg_pct": None, "cpu_tree_avg_pct": None, "rss_peak_mb": None}
        return {
            "cpu_sys_avg_pct": round(sum(s[1] for s in sel) / len(sel), 1),
            "cpu_tree_avg_pct": round(sum(s[2] for s in sel) / len(sel), 1),
            "rss_peak_mb": round(max(s[3] for s in sel), 1),
        }

    out = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "boot_wall_t": boot_wall_t,
        "cores_arg": args.cores,
        "affinity_cores": len(os.sched_getaffinity(0)),
        "mode": args.mode,
        "import_s": round(t_import, 4),
        "load_s": round(t_load, 4),
        "warmup_s": round(t_warmup, 4),
        "run1": run1,
        "run2": run2,
        "resources_infer": phase_stats(["infer", "infer2"]),
        "resources_whole": phase_stats([s[0] for s in set(x[0] for x in samples)]),
    }
    Path(args.out).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "cores": args.cores, "run1": run1, "run2": run2}))


if __name__ == "__main__":
    main()
