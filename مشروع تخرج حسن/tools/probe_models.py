# -*- coding: utf-8 -*-
"""مسبار الموديلات — اكتشاف ما تدعمه المفاتيح فعليًا وترتيبها قوةً وسرعةً.

شغّل:  .venv\\Scripts\\python.exe tools/probe_models.py
- يقرأ أول مفتاح من GEMINI_API_KEYS
- ListModels → الموديلات التي تدعم generateContent فعليًا
- لكل موديل مرشح: نداء مصغّر مُوقّت → متوسط الاستجابة + الحالة الآن
- يطبع جدول الترتيب + سطر GEMINI_MODELS الموصى به للصق في .env
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

import requests  # noqa: E402
from google import genai  # noqa: E402
from google.genai import types  # noqa: E402

KEYS = [k.strip() for k in (os.getenv("GEMINI_API_KEYS") or "").replace("\n", ",").split(",") if k.strip()]
KEY = KEYS[0] if KEYS else (os.getenv("GEMINI_API_KEY") or "").strip()

# مرشحو الترتيب: عائلة flash/light — pro يُعرض في القائمة لكنه يُرتب آخرًا
# (أبطأ + حصة أقل) — والاسم الحقيقي يأتي من ListModels لا من الذاكرة
PREFERRED_PATTERNS = ("flash", "lite")
EXCLUDE = ("embedding", "aqa", "imagen", "veo", "tts", "audio", "thinking-exp",
           "deprecated")


def list_models() -> list[dict]:
    r = requests.get(
        "https://generativelanguage.googleapis.com/v1beta/models",
        params={"key": KEY}, timeout=30)
    data = r.json()
    out = []
    for m in (data.get("models") or []):
        name = (m.get("name") or "").replace("models/", "")
        methods = m.get("supportedGenerationMethods") or []
        if "generateContent" in methods:
            out.append({"name": name,
                        "display": m.get("displayName", ""),
                        "limits": m.get("inputTokenLimit", "?")})
    return out


def probe_latency(model: str, attempts: int = 1) -> tuple[float | None, str]:
    """نداء مصغّر مُوقّت — يدور على المفاتيح حتى يويجد حيًا
    (429 على مفتاح لا يعني الموديل ميت — المفاتيح الأخرى قد تملك حصة)."""
    client = genai.Client(api_key=KEY,
                          http_options=types.HttpOptions(timeout=30_000))
    times = []
    last = "فشل"
    for _ in range(attempts):
        for ki, k in enumerate(KEYS):
            try:
                c = (client if k == KEY else genai.Client(
                    api_key=k, http_options=types.HttpOptions(timeout=30_000)))
                t0 = time.time()
                c.models.generate_content(
                    model=model,
                    contents="Reply with exactly: OK",
                    config=types.GenerateContentConfig(
                        max_output_tokens=8, temperature=0,
                        thinking_config=types.ThinkingConfig(
                            thinking_budget=0)))
                times.append(time.time() - t0)
                last = f"حي (مفتاح {ki + 1})"
                break
            except Exception as exc:
                last = f"{type(exc).__name__}: {str(exc)[:60]}"
    if not times:
        return None, last
    return sum(times) / len(times), last


def main() -> None:
    if not KEY:
        print("❌ لا مفتاح في .env")
        sys.exit(1)
    print(f"المفتاح المستخدم: {KEY[:6]}…{KEY[-4:]}")
    models = list_models()
    print(f"\nالموديلات الداعمة لـ generateContent: {len(models)}")
    candidates = [m for m in models
                  if not any(x in m["name"].lower() for x in EXCLUDE)]
    # الترتيب العرضي: الأحدث أولًا (أرقام أكبر في الاسم) ثم lite ثم flash
    def _sort_key(m):
        n = m["name"].lower()
        return (("lite" not in n), ("flash" in n), n)
    candidates.sort(key=_sort_key, reverse=True)

    print(f"\n{'الموديل':40s} {'الاستجابة':>10s} {'الحالة':>28s}")
    live = []
    for m in candidates[:18]:
        avg, status = probe_latency(m["name"])
        avg_s = f"{avg:5.1f}s" if avg else "  —  "
        print(f"{m['name']:40s} {avg_s:>10s} {status:>28s}")
        if avg is not None:
            live.append((m["name"], avg))
    # الترتيب النهائي: الأسرع حيًا أولًا (مع بقاء flash العام قبل lite)
    live.sort(key=lambda x: x[1] + (1.0 if "lite" in x[0] else 0.0))
    recommended = [n for n, _t in live][:5]
    print("\n=== الترتيب الحي (الأسرع استجابة أولًا) ===")
    for n, t in live:
        print(f"  {n:40s} {t:5.1f}s")
    if recommended:
        print("\n=== الصق في .env ===")
        print("GEMINI_MODELS=" + ",".join(recommended))


if __name__ == "__main__":
    main()
