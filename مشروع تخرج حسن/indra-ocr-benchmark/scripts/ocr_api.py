#!/usr/bin/env python3
"""Local HTTP API wrapping Indra OCR — for any local HTTP client.

Loads the model ONCE at startup and keeps it in memory, so every request pays
only inference time (~0.2-0.5s per page) instead of the ~1-7s cold start the
CLI pays per invocation.

Start (WSL):   ~/indra-ocr-bench/.venv/bin/python scripts/ocr_api.py --port 8000
Health:        curl http://localhost:8000/health
OCR a file:    curl -F "file=@scan.pdf" -F mode=auto http://localhost:8000/ocr

Requests are serialized with a lock (one local client at a time is the
design target). No authentication: keep the port local, do not expose it to
your network or the internet.
"""
from __future__ import annotations

import argparse
import tempfile
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import indra_ocr
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile

ARGS: argparse.Namespace = argparse.Namespace(port=8000, host="0.0.0.0", threads=4, dpi=200.0)
STATE: dict = {"conv": None, "load_s": None}
LOCK = threading.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    t0 = time.perf_counter()
    STATE["conv"] = indra_ocr.load(threads=ARGS.threads, mode="auto", dpi=ARGS.dpi)
    STATE["load_s"] = round(time.perf_counter() - t0, 3)
    print(f"model loaded in {STATE['load_s']}s (threads={ARGS.threads}, dpi={ARGS.dpi})")
    yield
    STATE.clear()


app = FastAPI(title="Indra OCR local API", version=indra_ocr.__version__, lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model": "indra-ocr",
        "version": indra_ocr.__version__,
        "threads": ARGS.threads,
        "dpi": ARGS.dpi,
        "model_load_s": STATE.get("load_s"),
    }


@app.post("/ocr")
async def ocr(
    file: UploadFile = File(...),
    mode: str = Form("auto"),
    max_pages: int = Form(0),
    include_boxes: bool = Form(False),
):
    if mode not in ("auto", "ocr", "text"):
        raise HTTPException(400, f"mode must be auto|ocr|text, not {mode!r}")
    suffix = Path(file.filename or "").suffix or ".bin"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(await file.read())
        tmp.close()
        t0 = time.perf_counter()
        with LOCK:
            try:
                results = list(STATE["conv"].convert(tmp.name, max_pages=max_pages))
            except indra_ocr.InputError as e:
                raise HTTPException(400, str(e))
        elapsed = round(time.perf_counter() - t0, 3)
        pages = []
        for idx, page in results:
            entry = {
                "page": idx,
                "source": page.source,
                "rotation": page.rotation,
                "note": page.note,
                "text": page.text,
                "markdown": page.markdown,
                "total_ms": round(page.timings.get("total_ms", 0.0), 1),
            }
            if include_boxes:
                entry["lines"] = [
                    {"box": ln.box, "text": ln.text, "conf": round(ln.conf, 4)}
                    for ln in page.lines
                ]
            pages.append(entry)
        return {
            "file": file.filename,
            "mode": mode,
            "pages": pages,
            "pages_ok": sum(1 for p in pages if p["source"] != "error"),
            "elapsed_s": elapsed,
        }
    finally:
        Path(tmp.name).unlink(missing_ok=True)


def main() -> None:
    global ARGS
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8900)
    ap.add_argument("--threads", type=int, default=4, help="cores for the model (4 recommended on this machine)")
    ap.add_argument("--dpi", type=float, default=200.0)
    ARGS = ap.parse_args()
    uvicorn.run(app, host=ARGS.host, port=ARGS.port, log_level="info")


if __name__ == "__main__":
    main()
