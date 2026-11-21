"""Persistent on-disk caches — the demo-day insurance.

Extraction (the expensive part: render → triage → Gemini vision → verify)
is keyed by sha1(file bytes) + file name + page range; the AI commentary is
keyed by sha1 of the payload JSON. A cache hit replays the stored result with
ZERO API calls, so:

- re-uploading a file after a server restart is instant and free;
- the thesis defense demo works offline — a Google 503 storm on stage
  cannot touch an already-solved file;
- the batch mode only ever pays for files never solved before.

Cache lives in `cache/` under the project root. «🧹 مسح الكاش المحلي» in the
sidebar wipes it (extraction + analysis) and the next run re-extracts fresh.
"""
from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # src/extraction/… → project root
CACHE_DIR = PROJECT_ROOT / "cache"
SEED_CACHE_DIR = PROJECT_ROOT / "data" / "seed_cache"
CACHE_SCHEMA_VERSION = 2

_LOCK = threading.Lock()


def _sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()[:16]


def extraction_key(file_name: str, raw: bytes, page_range, fast_mode: bool = False) -> str:
    return "|".join([_sha1(raw), file_name, str(page_range), "fast" if fast_mode else "full"])


def analysis_key(payload: dict) -> str:
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return _sha1(blob.encode("utf-8"))


def _read(cache_sub: str, key: str) -> dict | None:
    path = CACHE_DIR / cache_sub / f"{key.replace('|', '__')}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write(cache_sub: str, key: str, payload: dict) -> None:
    d = CACHE_DIR / cache_sub
    try:
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{key.replace('|', '__')}.json"
        with _LOCK:
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass  # caching must never break an analysis


def load_cached_extraction(key: str) -> dict | None:
    res = _read("extraction", key)
    if CACHE_DIR == PROJECT_ROOT / "cache":
        seed_path = SEED_CACHE_DIR / f"{key.replace('|', '__')}.json"
        if not seed_path.exists() and SEED_CACHE_DIR.exists():
            sha_prefix = key.split("|", 1)[0]
            mode_suffix = "__fast.json" if key.endswith("|fast") else "__full.json"
            matches = list(SEED_CACHE_DIR.glob(f"{sha_prefix}__*{mode_suffix}"))
            if matches:
                seed_path = matches[0]
        if seed_path.exists() and (res is None or int(res.get("cache_schema") or 0) < CACHE_SCHEMA_VERSION):
            try:
                seed_data = json.loads(seed_path.read_text(encoding="utf-8"))
                _write("extraction", key, seed_data)
                return seed_data
            except Exception:
                pass
    return res


def store_extraction(key: str, payload: dict) -> None:
    if isinstance(payload, dict) and "cache_schema" not in payload:
        payload = {**payload, "cache_schema": CACHE_SCHEMA_VERSION}
    _write("extraction", key, payload)


def load_cached_analysis(key: str) -> dict | None:
    return _read("analysis", key)


def store_analysis(key: str, payload: dict) -> None:
    _write("analysis", key, payload)


def clear_all_caches() -> int:
    """Delete every cached file (extraction + analysis). Returns count."""
    n = 0
    for sub in ("extraction", "analysis"):
        d = CACHE_DIR / sub
        if not d.exists():
            continue
        for path in d.glob("*.json"):
            try:
                path.unlink()
                n += 1
            except OSError:
                pass
    return n
