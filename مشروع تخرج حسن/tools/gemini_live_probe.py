# -*- coding: utf-8 -*-
"""Live Gemini availability sweep (مسح حي لكل المفاتيح × كل النماذج).

Answers «لماذا فشل النداء؟» with evidence: one TINY request per
(key, model) pair from .env — 7 keys × GEMINI_MODELS — plus a free
models.list call per key (consumes no generate quota) to see which model
names each key can even resolve. Result: a per-pair status matrix saved to
cell_evidence/gemini_live_matrix.json.

Cost: ≤ 1 generate request per pair (35 max) with maxOutputTokens=5 —
well inside the documented 20-req/model allowance.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ))
import src.config  # noqa: F401,E402  (loads .env)
import os  # noqa: E402

BASE = "https://generativelanguage.googleapis.com/v1beta"


def _keys() -> list[str]:
    raw = os.environ.get("GEMINI_API_KEYS") or os.environ.get("GEMINI_API_KEY") or ""
    return [k.strip() for k in raw.split(",") if k.strip()]


def _models() -> list[str]:
    raw = os.environ.get("GEMINI_MODELS", "")
    return [m.strip() for m in raw.split(",") if m.strip()]


def _mask(k: str) -> str:
    return f"{k[:6]}…{k[-4:]}" if len(k) > 12 else k


def _req(url: str, body: dict | None = None, timeout: int = 30):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data,
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read()).get("error", {}).get("status", "")
        except Exception:
            detail = ""
        return e.code, detail
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:80]}"


def main() -> None:
    keys, models = _keys(), _models()
    print(f"keys={len(keys)}  models={models}")
    matrix, summary = [], {}

    for key in keys:
        masked = _mask(key)
        # free tier check: which model names can this key even resolve?
        st, body = _req(f"{BASE}/models?key={key}&pageSize=100")
        visible: set[str] = set()
        if st == 200 and isinstance(body, dict):
            for m in body.get("models", []):
                name = (m.get("name") or "").removeprefix("models/")
                visible.add(name)
        elif st:
            summary.setdefault("list_errors", []).append(f"{masked}: HTTP {st} {body}")

        for model in models:
            t0 = time.perf_counter()
            st, body = _req(
                f"{BASE}/models/{model}:generateContent?key={key}",
                {"contents": [{"parts": [{"text": "reply with exactly: OK"}]}],
                 "generationConfig": {"maxOutputTokens": 5, "temperature": 0}},
                timeout=45)
            ms = int((time.perf_counter() - t0) * 1000)
            status = ("OK" if st == 200
                      else f"HTTP_{st}" if st else "CONN_FAIL")
            if st == 200 and isinstance(body, dict):
                cand = body.get("candidates") or [{}]
                txt = (cand[0].get("content", {}).get("parts") or [{}])[0] \
                    .get("text", "").strip()
            else:
                txt = str(body)[:60]
            # can the key SEE the model in its list (free diagnostic)?
            resolved = bool(visible) and (model in visible)
            matrix.append({"key": masked, "model": model, "status": status,
                           "ms": ms, "reply": txt[:20],
                           "in_key_model_list": resolved})
            print(f"  {masked}  {model:24s} {status:10s} {ms:>5}ms "
                  f"visible={resolved}  {txt[:16]}")
            time.sleep(0.4)

    ok = sum(1 for r in matrix if r["status"] == "OK")
    by_model = {}
    for r in matrix:
        by_model.setdefault(r["model"], {"ok": 0, "total": 0})
        by_model[r["model"]]["total"] += 1
        by_model[r["model"]]["ok"] += (r["status"] == "OK")
    out = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "pairs_total": len(matrix), "pairs_ok": ok,
        "per_model": by_model,
        "note": "1 tiny request per (key, model); 'in_key_model_list' comes "
                "from the free models.list endpoint (no generate quota)",
        "matrix": matrix,
    }
    dst = PROJ / "cell_evidence/gemini_live_matrix.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n{ok}/{len(matrix)} pairs OK — matrix: {dst}")
    for m, s in by_model.items():
        print(f"  {m:24s} {s['ok']}/{s['total']} OK")


if __name__ == "__main__":
    main()
