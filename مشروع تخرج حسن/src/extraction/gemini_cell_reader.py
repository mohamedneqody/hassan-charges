# -*- coding: utf-8 -*-
"""Gemini as the SECOND, independent reader for individual cell crops.

Used ONLY after local OCR provably failed on that crop (dates, garbled
cells) — one small crop per call, never a whole-document re-extraction.

Every call returns the structured schema below, is validated against it,
and is logged (model, latency, tokens, attempts, failures). Quota/auth
failures are recorded as read_status=BLOCKED — never invented, never
retried past the key pool. The model's self-reported confidence is stored
but never treated as proof on its own: the result must still agree with
the reference (GT value, printed identity, or a second read) before any
value is promoted.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

SCHEMA_FIELDS = ("raw_text", "normalized_value", "year", "read_status",
                 "confidence", "bbox", "evidence_reference", "model_name")
READ_STATUSES = ("READ", "UNREADABLE", "BLOCKED")

_PROMPT = """أنت قارئ أرقام حرفي (literal OCR reader) لمقتطعة من قوائم مالية
مصرية ممسوحة ضوئيًا. اقرأ {what} المطبوع في الصورة حرفيًا فقط:
- أعد النص كما هو مطبوع بالأرقام الهندية أو اللاتينية كما تظهر.
- فك الفواصل والتجميع فقط؛ لا تُشتق ولا تحسب ولا تخمن أي رقم.
- إن لم يكن الرقم واضحًا بما يكفي للقراءة الحرفية الكاملة أعد
  read_status=UNREADABLE — ممنوع إكمال أرقام ناقصة.
- السياق (للمساعدة فقط، لا تقرأ منه): البند «{label}»، السنة {year}.
أعد JSON بالمفاتيح: raw_text (نص)، normalized_value (رقم أو null)،
year (رقم أو null)، read_status (READ أو UNREADABLE)، confidence (0-1)،
notes (نص قصير)."""


def _keys() -> list[str]:
    import os

    import src.config  # noqa: F401  (import runs load_dotenv)
    raw = os.environ.get("GEMINI_API_KEYS") or os.environ.get("GEMINI_API_KEY") or ""
    return [k.strip() for k in raw.split(",") if k.strip()]


def build_pairs(keys: list[str], models: list[str],
                preferred: str | None = None) -> list[tuple[str, str]]:
    """The (key, model) attempt order: the requested model first (if any),
    then the configured rotation — keys interleaved round-robin per model so
    one exhausted model never starves the others. Free quotas are PER MODEL,
    so switching models on a 429/503 doubles-to-quintuples the allowance
    (20 req × 5 models × 7 keys = up to 700 reads/pool instead of 140)."""
    seen: list[str] = []
    for m in ([preferred] if preferred else []) + models:
        if m and m not in seen:
            seen.append(m)
    pairs: list[tuple[str, str]] = []
    for m in seen:
        for k in keys:
            pairs.append((k, m))
    return pairs


def _model_list() -> list[str]:
    """All configured models (GEMINI_MODELS) sorted by speed rank, falling back to DEFAULT_MODELS."""
    import os

    import src.config  # noqa: F401  (import runs load_dotenv)
    from src.ai.key_pool import DEFAULT_MODELS, MODEL_RANK, MODEL_RANK_DEFAULT

    raw = os.environ.get("GEMINI_MODELS", "")
    models = [m.strip() for m in raw.split(",") if m.strip()] or list(DEFAULT_MODELS)
    return sorted(models, key=lambda m: (-MODEL_RANK.get(m, MODEL_RANK_DEFAULT), m))


def read_crop(png: bytes, label: str, year: int | None, what: str,
              model: str | None = None,
              bbox: list | None = None) -> dict:
    """One structured read of one crop. Schema-validated; BLOCKED on
    quota/auth/absent-keys with the failure reason recorded. Rotates over
    EVERY configured (key, model) pair — a 429/503 on one model moves the
    call to the next model (per-model quotas), a bad key is skipped."""
    from src.ai.gemini_agent import classify_gemini_error
    from src.config import GEMINI_MODEL

    result = {
        "raw_text": "", "normalized_value": None, "year": year,
        "read_status": "BLOCKED", "confidence": None,
        # geometry-documented bbox (from the spatial locator / Indra
        # Line.box, relative to the ORIGINAL page render) — never overwritten
        # by the model; whatever the MODEL proposes goes to model_bbox.
        "bbox": list(bbox) if bbox else None,
        "bbox_source": "geometry" if bbox else None,
        "model_bbox": None,
        "evidence_reference": "", "model_name": model or GEMINI_MODEL,
        "notes": "", "latency_ms": None, "attempts": 0, "failure": "",
        "usage": None,  # token usage captured from the response when present
    }
    keys = _keys()
    if not keys:
        result["failure"] = "no GEMINI_API_KEYS configured"
        return result
    prompt = _PROMPT.format(what=what, label=label, year=year or "غير محدد")
    try:
        from google import genai
        from google.genai import types

        from src.ai.key_pool import (
            adapt_config_for_model,
            get_genai_client,
            mark_thinking_budget_unsupported,
        )

        content = [
            prompt,
            types.Part.from_bytes(data=png, mime_type="image/png"),
        ]
        cfg = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.0,
            max_output_tokens=512,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
        pairs = build_pairs(keys, _model_list(), preferred=model)
        failures: list[str] = []
        dead_keys: set[str] = set()
        dead_models: set[str] = set()
        for key, model_name in pairs:
            if key in dead_keys or model_name in dead_models:
                continue                      # auth-rejected key or 404 model — skip fast
            result["attempts"] += 1
            t0 = time.perf_counter()
            try:
                client = get_genai_client(key, timeout_ms=20_000)
                eff_cfg = adapt_config_for_model(cfg, model_name)
                try:
                    resp = client.models.generate_content(
                        model=model_name, contents=content, config=eff_cfg,
                    )
                except Exception as exc_inner:
                    low_i = str(exc_inner).lower()
                    if (
                        getattr(eff_cfg, "thinking_config", None) is not None
                        and ("400" in low_i or "invalid_argument" in low_i)
                    ):
                        mark_thinking_budget_unsupported(model_name)
                        resp = client.models.generate_content(
                            model=model_name,
                            contents=content,
                            config=adapt_config_for_model(cfg, model_name),
                        )
                    else:
                        raise
                result["latency_ms"] = int((time.perf_counter() - t0) * 1000)
                u = getattr(resp, "usage_metadata", None)
                if u is not None:
                    result["usage"] = {
                        "input_tokens": getattr(u, "prompt_token_count", None),
                        "output_tokens": getattr(u, "candidates_token_count", None),
                        "total_tokens": getattr(u, "total_token_count", None),
                        "cost": None,  # no price table in-repo; tokens only
                    }
                result["model_name"] = model_name   # the model that answered
                return _validate(result, resp.text or "", label, what)
            except Exception as exc:  # noqa: BLE001 — every failure recorded
                kind = classify_gemini_error(exc)
                failures.append(f"{model_name}/{kind}: {str(exc)[:120]}")
                if kind == "auth":
                    dead_keys.add(key)        # this key is bad for EVERY model
                    continue
                if kind == "model":
                    dead_models.add(model_name)
                    continue
                # quota (429) or transient (503/504): switch immediately (< 1s)
                continue
        result["failure"] = "; ".join(failures) or "unknown"
        result["notes"] = "BLOCKED — recorded, not retried past the pool"
        return result
    except Exception as exc:  # noqa: BLE001
        result["failure"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        return result


def _validate(result: dict, text: str, label: str, what: str) -> dict:
    """Schema validation: enum check, type coercion, no silent coercion of
    garbage into a value."""
    result["raw_text"] = text[:400]
    try:
        data = json.loads(text.strip().strip("`"))
    except Exception:
        result["read_status"] = "UNREADABLE"
        result["notes"] = "response was not valid JSON (schema violation)"
        return result
    if not isinstance(data, dict) or "read_status" not in data:
        result["read_status"] = "UNREADABLE"
        result["notes"] = "schema violation: missing read_status"
        return result
    status = data.get("read_status")
    if status not in ("READ", "UNREADABLE"):
        result["read_status"] = "UNREADABLE"
        result["notes"] = f"schema violation: read_status={status!r}"
        return result
    result["read_status"] = status
    result["raw_text"] = str(data.get("raw_text") or "")[:200]
    val = data.get("normalized_value")
    result["normalized_value"] = float(val) if isinstance(val, (int, float)) else None
    yr = data.get("year")
    result["year"] = int(yr) if isinstance(yr, (int, float)) and 2000 <= int(yr) <= 2099 else None
    conf = data.get("confidence")
    result["confidence"] = float(conf) if isinstance(conf, (int, float)) else None
    if data.get("bbox") is not None and isinstance(data.get("bbox"), list):
        # the model's proposal is RECORDED, never substituted for geometry
        result["model_bbox"] = data["bbox"][:4]
        result["notes"] = (str(data.get("notes") or "") +
                           " | model proposed a bbox — geometry kept")[:200]
    result["notes"] = str(data.get("notes") or "")[:200]
    return result


def read_batch(jobs: list[dict]) -> list[dict]:
    """jobs: [{evidence_reference, png, label, year, what}] → validated reads."""
    out = []
    for job in jobs:
        res = read_crop(job["png"], job["label"], job.get("year"), job["what"],
                        bbox=job.get("bbox"))
        res["evidence_reference"] = job["evidence_reference"]
        out.append(res)
        print(f"  {job['evidence_reference']}: {res['read_status']} "
              f"raw={res['raw_text'][:40]!r} val={res['normalized_value']} "
              f"yr={res['year']} {('fail=' + res['failure'][:60]) if res['failure'] else ''}")
    return out


def save(reads: list[dict], path: Path) -> None:
    path.write_text(json.dumps(reads, ensure_ascii=False, indent=1),
                    encoding="utf-8")
