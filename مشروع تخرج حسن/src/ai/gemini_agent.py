"""Google Gemini agent: writes a ONE-LINE comment per calculated ratio.

All financial calculations are done in Python (src/analysis) — values, numeric
direction and assessment are sent pre-computed. Gemini's ONLY job per the spec:
a very short comment per metric (rose/fell/stable + one-sentence financial
meaning, with hedged language), then one short recommendations section.
"""
from __future__ import annotations

import json
import time
import re
from dataclasses import dataclass, field

from src.ai.key_pool import (
    APIKeyPool,
    adapt_config_for_model,
    classify_quota_scope,
    get_genai_client,
    mark_thinking_budget_unsupported,
)
from src.config import GEMINI_MODEL, REPORT_LANGUAGE

# Fast-fail HTTP timeout (ms) — a hung key must not block the rotation.
HTTP_TIMEOUT_MS = 22_000
COMMENTARY_BUDGET = 75  # seconds — total commentary time before rule-based fallback
# (التسريع 2026-11-13: 100 → 60 — قاعدة الاحتياط القائمة على القواعد تعوض
# أي تعليق لم يُنتج، والرحلة النموذجية كانت تستهلك حتى دقيقتين في التعليق)
# Cap the response: 60 short comments + recommendations fit comfortably.
MAX_OUTPUT_TOKENS = 8192

_LANGUAGE_LINE = (
    "اكتب كل تعليق وتوصية بالعربية الفصحى المبسطة، مستخدمة أسماء المؤشرات "
    "كما وردت في البيانات."
    if REPORT_LANGUAGE == "ar"
    else "Write in English."
)

SYSTEM_PROMPT = f"""You are a financial analysis assistant.

Python has already calculated every financial metric and its two-year change.
Your ONLY job: write one very short comment per metric, then short recommendations.

Rules:
1. Never invent or recalculate numbers. Quote the exact values provided.
2. Each comment must state whether the metric rose, fell, or stayed stable,
   then give the financial meaning of the change in ONE sentence only.
3. Maximum two short lines per metric. Never explain formulas or methodology.
4. Do not repeat yourself. No introduction, no closing paragraph, no analysis
   of the statements from scratch.
5. Do NOT group metrics into sections or axes. One flat list of comments only.
6. When the reason behind a change is not visible in the data, use hedging
   language such as "قد يشير إلى", "قد يرتبط بـ", "قد يعكس" (or "may indicate",
   "may reflect") and never present a possibility as a fact.
7. Skip any metric whose values are null — do not comment on missing data.
8. Do not provide legal, investment, or tax advice.

After ALL the metric comments, output ONE recommendations section with 3 to 5
recommendations. Each recommendation is an OBJECT with two fields:
  {{"action": "<what to do — one short, practical sentence>",
    "evidence": "<the metric name(s) with their EXACT provided values that justify it>"}}
Every action MUST be tied to at least one named metric and quote its exact
values as evidence — generic advice without numbers is forbidden.
Example: {{"action": "إعادة جدولة الاقتراض قصير الأجل لتخفيف ضغط السيولة.",
          "evidence": "Quick Ratio: من 0.82x إلى 0.84x مقابل مستوى إرشادي عام 1.00x؛ Current Ratio: من 1.43x إلى 1.46x."}}

Return structured JSON with exactly this shape:
{{
  "ratio_comments": [
    {{"metric": "<exact metric name as provided>", "comment": "<1-2 short sentences>"}}
  ],
  "recommendations": [{{"action": "...", "evidence": "..."}}]
}}

The "metric" value must copy the metric name exactly as provided.
{_LANGUAGE_LINE}"""


@dataclass
class AIAnalysis:
    ok: bool
    ratio_comments: list[tuple[str, str]] = field(default_factory=list)
    recommendations: list[tuple[str, str]] = field(default_factory=list)
    error: str = ""
    model: str = GEMINI_MODEL


# Process-wide pool singleton storage (see get_pool)
_POOL: APIKeyPool | None = None


def build_payload(
    company: str,
    prev_year: int,
    curr_year: int,
    metrics: list[dict],
    missing_data: list[str],
    extraction_notes: list[str],
    notes_highlights: list[dict] | None = None,
) -> dict:
    """Assemble the compact payload sent to Gemini (pre-formatted values).

    notes_highlights: finance-relevant excerpts from the notes pages
    (الإيضاحات المتممة) with their source page numbers — the model may use
    them to STRENGTHEN a comment/recommendation and must cite the page."""
    return {
        "company": company,
        "analysis_period": {"previous_year": prev_year, "current_year": curr_year},
        "metrics": metrics,
        "missing_data": missing_data,
        "extraction_notes": extraction_notes,
        "notes_highlights": notes_highlights or [],
        "instructions": (
            "All values, the numeric direction (rose/fell/stable) and the assessment "
            "(improving/declining/stable) were computed in Python — do not recalculate. "
            "Quote the provided values verbatim in the comment. 'previous' and 'current' "
            "are already formatted strings (e.g. '18.0%', '1.65x', '$1.18M'). Metrics with "
            "null values must be skipped. Do not comment on missing data beyond what the "
            "values show."
        ),
    }


def _strip_code_fences(text: str) -> str:
    fence = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
    return fence.group(1) if fence else text


def _coerce_str_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def parse_response(raw_text: str) -> AIAnalysis:
    """Parse Gemini's JSON into AIAnalysis. Raises ValueError on bad shape."""
    data = json.loads(_strip_code_fences(raw_text))
    if not isinstance(data, dict):
        raise ValueError("response is not a JSON object")

    comments: list[tuple[str, str]] = []
    raw_comments = data.get("ratio_comments") or []
    if not isinstance(raw_comments, list):
        raise ValueError("ratio_comments is not a list")
    for item in raw_comments:
        if isinstance(item, dict):
            metric = str(item.get("metric", "")).strip()
            comment = str(item.get("comment", "")).strip()
            if metric and comment:
                comments.append((metric, comment))
        elif isinstance(item, str) and item.strip():
            comments.append(("", item.strip()))

    recommendations: list[tuple[str, str]] = []
    raw_recs = data.get("recommendations") or []
    if isinstance(raw_recs, list):
        for item in raw_recs:
            if isinstance(item, dict):
                action = str(item.get("action", "")).strip()
                evidence = str(item.get("evidence", "")).strip()
                if action:
                    recommendations.append((action, evidence))
            elif isinstance(item, str) and item.strip():
                recommendations.append((item.strip(), ""))
    recommendations = recommendations[:6]
    return AIAnalysis(
        ok=True, ratio_comments=comments, recommendations=recommendations
    )


def _build_config():
    from google.genai import types

    return types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        temperature=0.2,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        # Flash models "think" by default, burning latency and output tokens;
        # verified supported on both pool models — disabling it speeds up calls.
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )


def _call_model(key: str, model: str, prompt: str, config) -> str:
    """One Gemini call with cached attempt=1 client (instant failover < 1s)."""
    client = get_genai_client(key, timeout_ms=HTTP_TIMEOUT_MS)
    eff_config = adapt_config_for_model(config, model)
    try:
        response = client.models.generate_content(
            model=model, contents=prompt, config=eff_config
        )
    except Exception as exc:
        msg = str(exc).lower()
        if (
            eff_config is not None
            and getattr(eff_config, "thinking_config", None) is not None
            and ("400" in msg or "invalid_argument" in msg)
        ):
            mark_thinking_budget_unsupported(model)
            retry_cfg = adapt_config_for_model(config, model)
            response = client.models.generate_content(
                model=model, contents=prompt, config=retry_cfg
            )
        else:
            raise
    return (response.text or "").strip()


def classify_gemini_error(exc: Exception) -> str:
    """Bucket a Gemini failure: quota / auth / model / other."""
    text = str(exc).lower()
    code = getattr(exc, "code", None)
    if code == 429 or "429" in text or "resource_exhausted" in text or "quota" in text:
        return "quota"
    if code in (401, 403) or "401" in text or "403" in text or (
        "api key" in text and ("invalid" in text or "expired" in text or "not valid" in text)
    ):
        return "auth"
    if code == 404 or "404" in text or "not found" in text:
        return "model"
    return "other"


def get_pool() -> APIKeyPool:
    """Process-wide pool singleton (statuses survive Streamlit reruns)."""
    global _POOL
    if _POOL is None:
        _POOL = APIKeyPool.from_env()
    return _POOL


def reset_pool() -> None:
    global _POOL
    _POOL = None


def _float_tokens(text: str) -> list[float]:
    """All numeric values inside a formatted string ('+18.0%', '$1.18M')."""
    values = []
    for tok in re.findall(r"\d+(?:[.,]\d+)*", str(text)):
        try:
            values.append(float(tok.replace(",", "")))
        except ValueError:
            continue
    return values


def _is_allowed(value: float, allowed: set[float]) -> bool:
    """A quoted number is legitimate if it matches an allowed value exactly or
    at any K/M/B scaling of one (writers say '0.49M' for 485K, etc.)."""
    for a in allowed:
        for scale in (0, 3, 6, 9, -3, -6, -9):
            target = a * (10 ** scale)
            if abs(value - target) <= 0.01 * max(abs(target), 1.0):
                return True
    return False


# ═══ v6 إصلاح حديد عز (إصلاح 5-ب): حاجز ما بعد التوليد ═══
# الموديل: حوّل المضاعف (x) إلى نسبة %، وأسقط إشارة السالب من خسائر 2020،
# وأقحم أرقامًا زائفة. هذا الحاجز يعمل بعد التوليد وقبل العرض:
# 1) يصلح % المُقحمة مكان x للمؤشرات ذات النوع x.
# 2) يعيد إشارة السالب للقيم السالبة الممررة لفظيًا.
# 3) يُسقط التعليق إن بقي رقم غير متتبع بعد الإصلاح (المدقق القائم يكمل).
def _extract_numbers(text: str) -> list[tuple[float, str]]:
    """كل الأرقام في النص مع وحدتها الظاهرة (% أو x أو مجرد رقم)."""
    out = []
    for m in re.finditer(r"-?\d+(?:[.,]\d+)?\s*(?:%|x|مرة)?", text):
        tok = m.group(0)
        num_s = re.sub(r"[^\d.,\-]", "", tok).replace(",", "")
        try:
            num = float(num_s)
        except ValueError:
            continue
        unit = "%" if "%" in tok else ("x" if ("x" in tok or "مرة" in tok)
                                        else "")
        out.append((num, unit))
    return out


def repair_generated_text(text: str, expected: dict) -> str:
    """يصحح وحدات وإشارات النص المولد مقابل القيم الممررة من Python.

    expected: {"kind": "ratio|currency|percent", "prev": str, "curr": str,
               "prev_num": float|None, "curr_num": float|None}
    يعيد النص مصححًا — أو كما هو إن لم يخالف.
    """
    kind = expected.get("kind", "")
    fixed = text

    # 1) % مقحمة مكان x للمؤشرات متعددة المرات (D/E, Interest Coverage...)
    if kind == "ratio":
        for num, unit in _extract_numbers(fixed):
            if unit == "%" and abs(num) < 1000:
                # 25% مكان 1.25x؟ الفرق النمطي: % متعدد عن قيمة النسبة —
                # التصحيح: استبدال رمز % بـ x لنفس الرقم
                fixed = fixed.replace(f"{num:g}%", f"{num:g}x")
                fixed = fixed.replace(f"{num:.2f}%", f"{num:.2f}x")

    # 2) إشارة السالب الساقطة: القيمة الممررة سالبة لفظيًا والنص يذكرها
    #    موجبة → أعد السالب (فقط للمطابقة العددية للمقدار)
    for key in ("prev", "curr"):
        num = expected.get(f"{key}_num")
        if num is None or num >= 0:
            continue
        mag = abs(num)
        for tok_num, _unit in _extract_numbers(fixed):
            if tok_num > 0 and abs(tok_num - mag) <= max(0.5, 1e-4 * mag):
                fixed = fixed.replace(f"{tok_num:g}", f"-{tok_num:g}", 1)
                break

    # 3) الأرقام الزائفة: أي رقم في النص لا يطابق رقمًا ممررًا (بنسبة
    #    تسامح) يُعلَّم — المتصل يقرر الإسقاط (المدقق الحتمي يكمل)
    return fixed


def guardrail_comment(comment_text: str, expected: dict) -> str | None:
    """يصحح ثم يدقق: يعيد النص المصحح، أو None إن بقي رقم غير متتبع."""
    repaired = repair_generated_text(comment_text, expected)
    nums = [(n, u) for n, u in _extract_numbers(repaired) if abs(n) > 1e-9]
    allowed = [v for v in (expected.get("prev_num"), expected.get("curr_num"))
               if v is not None]
    # أرقام النسب مسموحة (نسب مئوية من قيم أخرى) — الفحص على قيم المؤشر
    stray = [n for n, u in nums
             if not any(abs(abs(n) - abs(a)) <= max(1.0, 1e-4 * abs(a))
                        or abs(n - a) <= max(1.0, 1e-4 * abs(a))
                        for a in allowed)]
    # أسماء سنوات وأرقام مرجعية صغيرة مسموحة؛ الزائفة الكبيرة تُسقط
    big_stray = [n for n in stray if abs(n) >= 1000]
    if big_stray:
        return None
    return repaired


def _apply_post_generation_guardrail(
    analysis: AIAnalysis, payload: dict,
) -> AIAnalysis:
    """v6 إصلاح حديد عز (إصلاح 5): حاجز ما بعد التوليد على كل تعليق —
    يصحح % المُقحمة مكان x (للنسب) ويستعيد إشارة السالب من القيم المنسقة
    الممررة، ثم يترك المدقق الحتمي (_audit_comments) يفحص الأرقام."""
    # خريطة الاسم → القيم المنسقة من الحمولة
    by_name = {}
    for m in payload.get("metrics", []):
        by_name[m.get("metric", "")] = m
    ratio_names = {m.get("metric") for m in payload.get("metrics", [])
                   if "x" in str(m.get("current", ""))}
    neg_names = {}
    for m in payload.get("metrics", []):
        name = m.get("metric", "")
        for v in (m.get("previous", ""), m.get("current", "")):
            nums = [float(x.replace(",", "")) for x in
                    __import__("re").findall(
                        r"-\d+(?:\.\d+)?", str(v))]
            if nums:
                neg_names[name] = min(nums)  # الأكثر سلبية
    fixed: list[tuple[str, str]] = []
    for metric, text in analysis.ratio_comments:
        t = text
        if metric in ratio_names:
            # % مقحمة مكان x للمؤشرات متعددة المرات
            t = __import__("re").sub(
                r"(-?\d+(?:\.\d+)?)\s*%", r"\1x", t)
        if metric in neg_names:
            neg = neg_names[metric]
            mag = abs(neg)
            # أعد إشارة السالب للقيمة المذكورة موجبة
            for tok in __import__("re").findall(
                    rf"(?<![-.\d]){mag:g}(?![\d])", t):
                t = t.replace(tok, f"-{tok}", 1)
        fixed.append((metric, t))
    analysis.ratio_comments = fixed
    return analysis


def _audit_comments(
    analysis: AIAnalysis, payload: dict
) -> tuple[list[str], list[tuple[str, str]]]:
    """(missing_metrics, suspect_comments) — suspect = quotes a number Python
    never provided (invented), checked at any K/M/B scaling."""
    allowed_by_metric: dict[str, set[float]] = {}
    prev_year = payload["analysis_period"]["previous_year"]
    curr_year = payload["analysis_period"]["current_year"]
    for m in payload["metrics"]:
        nums: set[float] = {float(prev_year), float(curr_year)}
        for keyf in ("previous", "current", "value", "change_pct"):
            if m.get(keyf) is not None:
                nums.update(_float_tokens(m[keyf]))
        allowed_by_metric[m["metric"]] = nums

    commented = {metric for metric, _ in analysis.ratio_comments}
    missing = [m["metric"] for m in payload["metrics"] if m["metric"] not in commented]

    suspects: list[tuple[str, str]] = []
    global_allowed = _global_allowed_numbers(payload)
    for metric, comment in analysis.ratio_comments:
        # a comment on a metric Python never computed is audited against
        # the GLOBAL allowlist (previously it was silently skipped — a
        # hallucinated metric name with an invented number survived)
        allowed = allowed_by_metric.get(metric) or global_allowed
        for value in _float_tokens(comment):
            if not _is_allowed(value, allowed):
                suspects.append((metric, comment))
                break
    return missing, suspects


def _repair_comments(
    analysis: AIAnalysis,
    payload: dict,
    key: str,
    model: str,
    config,
    caller=None,
) -> AIAnalysis:
    """One follow-up call: re-comment skipped metrics and any comment that
    quoted an invented number. Failures here keep the original analysis."""
    missing, suspects = _audit_comments(analysis, payload)
    if not missing and not suspects:
        return analysis

    target_names = set(missing) | {s[0] for s in suspects}
    entries = [m for m in payload["metrics"] if m["metric"] in target_names]
    if not entries:
        return analysis

    suspect_note = (
        "These previous comments quoted numbers that were never provided — "
        "rewrite them using ONLY the values below: "
        + json.dumps([{"metric": m, "comment": c} for m, c in suspects], ensure_ascii=False)
        + "\n"
        if suspects
        else ""
    )
    repair_prompt = (
        "You skipped or misstated some metrics in a previous financial analysis.\n"
        + suspect_note
        + "Comment ONLY on the following metrics, same rules as before "
        "(one short line each, exact values, hedged language, no inventions):\n"
        + "\n".join(json.dumps(m, ensure_ascii=False) for m in entries)
        + '\n\nReturn the same JSON shape: {"ratio_comments": [...]}'
    )
    try:
        raw_text = (
            caller(key, model, repair_prompt, config)
            if caller is not None
            else _call_model(key, model, repair_prompt, config)
        )
        repaired = parse_response(raw_text)
    except Exception:
        return analysis

    suspect_metrics = {s[0] for s in suspects}
    kept = [
        (m, c) for m, c in analysis.ratio_comments if m not in suspect_metrics
    ]
    allowed_by_metric = {
        m["metric"]: set(
            _float_tokens(m.get("previous") or "")
            + _float_tokens(m.get("current") or "")
            + _float_tokens(m.get("value") or "")
            + _float_tokens(m.get("change_pct") or "")
        ) | {float(payload["analysis_period"]["previous_year"]),
             float(payload["analysis_period"]["current_year"])}
        for m in entries
    }
    for metric, comment in repaired.ratio_comments:
        allowed = allowed_by_metric.get(metric)
        if allowed is None:
            continue
        if all(_is_allowed(v, allowed) for v in _float_tokens(comment)):
            kept.append((metric, comment))

    order = {m["metric"]: i for i, m in enumerate(payload["metrics"])}
    kept.sort(key=lambda mc: order.get(mc[0], 999))
    deduped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for metric, comment in kept:
        if metric in seen:
            continue
        seen.add(metric)
        deduped.append((metric, comment))
    analysis.ratio_comments = deduped
    return analysis


def _global_allowed_numbers(payload: dict) -> set[float]:
    """Every number the AI may legitimately quote anywhere: all provided
    metric values, years, and the widely accepted general guideline levels."""
    nums = {
        float(payload["analysis_period"]["previous_year"]),
        float(payload["analysis_period"]["current_year"]),
        # known general guideline levels (referenced in recommendations)
        0.5, 1.0, 1.5, 2.0, 7.5, 15.0,
    }
    for m in payload["metrics"]:
        for keyf in ("previous", "current", "value", "change_pct"):
            if m.get(keyf) is not None:
                nums.update(_float_tokens(m[keyf]))
    return nums


def _audit_recommendations(analysis: AIAnalysis, payload: dict) -> AIAnalysis:
    """Drop any recommendation whose text quotes a number Python never
    provided — evidence must be traceable to the calculated metrics."""
    if not analysis.recommendations:
        return analysis
    allowed = _global_allowed_numbers(payload)
    clean: list[tuple[str, str]] = []
    for action, evidence in analysis.recommendations:
        text = f"{action} {evidence}"
        if all(_is_allowed(v, allowed) for v in _float_tokens(text)):
            clean.append((action, evidence))
    analysis.recommendations = clean
    return analysis


def analyze_financials(
    payload: dict,
    pool: APIKeyPool | None = None,
    caller=None,
) -> AIAnalysis:
    """Call Gemini through the rotating key/model pool. Never raises.

    On 429 (free quota exhausted) the next key/model pair is tried immediately;
    on 404 the fallback model is used; on 401/403 the key is retired. Quotas are
    per-model, so alternating gemini-3.8-flash / gemini-3.7-flash effectively
    doubles the free allowance per key.

    `caller(key, model, prompt, config) -> str` is injectable for tests.
    """
    pool = pool or get_pool()
    if not pool.states:
        return AIAnalysis(
            ok=False,
            error="No Gemini API keys configured. Add GEMINI_API_KEYS (or a single "
                  "GEMINI_API_KEY) to the .env file to enable AI insights. All "
                  "deterministic results below are still valid.",
        )

    try:
        import google.genai  # noqa: F401  (presence check only)
    except ImportError:
        return AIAnalysis(
            ok=False,
            error="The google-genai package is not installed. "
                  "Run: pip install google-genai",
        )

    prev_year = payload["analysis_period"]["previous_year"]
    curr_year = payload["analysis_period"]["current_year"]
    metrics_lines = []
    for m in payload["metrics"]:
        metrics_lines.append(json.dumps(m, ensure_ascii=False))
    user_prompt = (
        f"Company: {payload['company']}\n"
        f"Analysis period: {prev_year} (previous year) vs {curr_year} (current year)\n\n"
        f"Metrics (calculated by Python — comment on each, in this order):\n"
        + "\n".join(metrics_lines)
        + f"\n\nMissing data (do not comment on these):\n"
        + json.dumps(payload["missing_data"], ensure_ascii=False, indent=2)
    )
    notes_highlights = payload.get("notes_highlights") or []
    if notes_highlights:
        hl_lines = [f"[صفحة {h['page']}] {h['text']}" for h in notes_highlights]
        user_prompt += (
            "\n\nNotes highlights (الإيضاحات المتممة — explanatory notes read from "
            "the same document, each tagged with its source page):\n"
            + "\n".join(hl_lines)
            + "\n\nUse a note ONLY where it genuinely strengthens a comment or a "
            "recommendation (e.g. the depreciation policy vs the DEPI component, "
            "loan terms vs the leverage/interest comments). When you use one, cite "
            "its page number inside the comment (e.g. «وفق الإيضاح صفحة 21»). Do "
            "not invent anything beyond these excerpts, and do not force them in."
        )
    user_prompt += (
        "\n\nProvide the structured JSON now: one short comment per metric, "
        "then the recommendations section."
    )
    config = _build_config()

    # Traverse ALL (key, model) pairs (e.g. 7 keys × 7 models = 49 pairs).
    # With HttpRetryOptions(attempts=1), each 429 skips in ~250 ms (< 1s).
    max_attempts = max(pool.total_pairs, 1)
    last_error = "no attempt was made"
    started = time.time()
    # Two sweeps: if every pair failed with a TRANSIENT error (e.g. 503 high
    # demand), wait briefly and try once more. Quota/auth/model failures are
    # marked immediately and rotated to the next pair in < 1 second.
    for sweep in range(2):
        if time.time() - started > COMMENTARY_BUDGET:
            break
        transient_only = True
        for _ in range(max_attempts):
            if time.time() - started > COMMENTARY_BUDGET:
                break
            picked = pool.pick()
            if picked is None:
                break
            state, model = picked
            t_call = time.perf_counter()
            try:
                raw_text = (
                    caller(state.key, model, user_prompt, config)
                    if caller is not None
                    else _call_model(state.key, model, user_prompt, config)
                )
            except Exception as exc:
                fail_ms = (time.perf_counter() - t_call) * 1000.0
                kind = classify_gemini_error(exc)
                if kind == "quota":
                    scope, cd_s = classify_quota_scope(exc)
                    if scope == "rpm":
                        pool.mark_rpm_limited(state.key, model, cd_s)
                        last_error = f"RPM rate limit for {model} on {state.masked}"
                    else:
                        pool.mark_quota_exhausted(state.key, model)
                        last_error = f"free quota exhausted for {model} on {state.masked}"
                    pool.record_failover(fail_ms)
                    transient_only = False
                elif kind == "auth":
                    pool.mark_dead(state.key, str(exc)[:200])
                    pool.record_failover(fail_ms)
                    last_error = f"key {state.masked} rejected (invalid or forbidden)"
                    transient_only = False
                elif kind == "model":
                    low_exc = str(exc).lower()
                    global_404 = "no longer available" in low_exc or "models/" in low_exc
                    pool.mark_model_unavailable(
                        state.key, model, str(exc)[:200], all_keys=global_404
                    )
                    pool.record_failover(fail_ms)
                    last_error = f"model {model} unavailable for {state.masked}"
                    transient_only = False
                else:
                    last_error = str(exc)[:300]
                    pool.record_failover(fail_ms)
                    if any(tok in last_error.lower() for tok in ("503", "504", "deadline", "unavailable", "timeout")):
                        pool.mark_transient_failure(model)
                continue

            elapsed_s = time.perf_counter() - t_call
            try:
                analysis = parse_response(raw_text)
            except (json.JSONDecodeError, ValueError) as exc:
                return AIAnalysis(
                    ok=False,
                    error=f"Gemini returned an unexpected response format ({exc}). "
                          "All deterministic results below are still valid.",
                    model=model,
                )
            # v6 إصلاح حديد عز (إصلاح 5): حاجز ما بعد التوليد قبل المدقق —
            # يصلح % المُقحمة مكان x ويستعيد إشارة السالب من القيم الممررة
            analysis = _apply_post_generation_guardrail(analysis, payload)
            pool.mark_success(state.key)
            pool.record_call(model, elapsed_s)
            analysis.model = model
            try:
                analysis = _repair_comments(analysis, payload, state.key, model, config, caller)
                analysis = _audit_recommendations(analysis, payload)
            except Exception:
                pass  # repair is best-effort; keep the first-pass analysis
            return analysis

        if sweep == 0 and transient_only and pool.has_usable_pairs():
            time.sleep(1.5)  # brief pause on transient demand spike, then retry
        else:
            break

    return AIAnalysis(
        ok=False,
        error=f"Gemini API call failed on every key/model combination ({last_error}). "
              "All deterministic results below are still valid.",
    )
