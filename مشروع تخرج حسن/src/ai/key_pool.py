"""Rotating pool of Gemini API keys and models.

The "endpoint layer": every Gemini call goes through this pool. When a key's
free quota is exhausted (429) the call moves to the next (key, model) pair in
sub-second time (< 1s) because shared clients disable hidden SDK backoff retries
(`HttpRetryOptions(attempts=1)`).

Traversal strategy:
- **Model-first (ranked by live measured speed, else `MODEL_RANK`) × Key round-robin**:
  all healthy keys are rotated evenly on the fastest model before stepping down
  to the next model. With 7 keys × 7 models = 49 independent pairs × 20 RPD,
  the pool delivers up to ~980 free requests/day without hammering a single key.
- **RPM vs RPD separation**: per-minute (RPM/TPM) 429s trigger a short cooldown
  (~65s) instead of banning the pair for 24 hours; daily (RPD) 429s mark 24h
  depletion.
- **Persistent model health**: depleted/unavailable/cooling states survive
  restarts without burning discovery time.

Thread-safe: vision extraction runs batches concurrently, so pick()/mark_*
are guarded by a lock.
"""
from __future__ import annotations

import os
import random
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

DEPLETION_RESET_SECONDS = 24 * 60 * 60
RPM_COOLDOWN_SECONDS = 65.0
DAILY_QUOTA_PER_PAIR = 20

# 7 live, verified fast Gemini models (7 keys × 7 models × 20 RPD ≈ 980 req/day)
DEFAULT_MODELS = [
    "gemini-flash-lite-latest",
    "gemini-3.1-flash-lite-preview",
    "gemini-3.5-flash-lite",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.8-flash",
]

# ترتيب السرعة/الأفضلية الابتدائي (رقم أعلى = يُجرَّب أولًا قبل قياس السرعة الحية).
# بعد أول نداء ناجح يتكفّل الترتيب الديناميكي بالسرعة المقاسة فعليًا (avg_s).
MODEL_RANK = {
    "gemini-flash-lite-latest": 120,      # ~0.5–0.8s
    "gemini-3.1-flash-lite-preview": 115, # ~0.6–1.0s
    "gemini-3.5-flash-lite": 110,         # ~0.6–1.0s
    "gemini-3-flash-preview": 100,        # ~0.8–1.8s (الأقوى + سريع)
    "gemini-3.1-flash-lite": 95,          # ~1.2s
    "gemini-3.6-flash": 90,
    "gemini-3.5-flash": 85,
    "gemini-3.8-flash": 80,
    "gemini-3.7-flash": 78,
    "gemini-flash-latest": 70,
    "gemini-3.1-flash-image": 60,
    "gemini-2.5-flash": 55,
}
MODEL_RANK_DEFAULT = 50   # موديل غير معروف — منتصف الجدول
MODEL_HEALTH_FILE = "cache/model_health.json"

# التبريد الناعم (503 high demand / 504 timeout): بعد فشلين متتاليين يُستبعد
# الموديل من pick لمدة قصيرة تلقائيًا، والجولة تتقارب فورًا على الموديلات الحية.
TRANSIENT_THRESHOLD = 2
SOFT_COOLDOWN_SECONDS = 90

# Shared persistent HTTP clients with attempts=1 (zero hidden SDK retry delay)
# PLUS one shared httpx keep-alive connection pool across all 7 API keys so
# switching from Key #1 (429) to Key #2 reuses the warm TLS socket (0ms handshake).
_GENAI_CLIENTS: dict[tuple[str, int, int], object] = {}
_GENAI_CLIENTS_LOCK = threading.Lock()
_SHARED_HTTPX_CLIENT: object | None = None


def _get_shared_httpx_client():
    global _SHARED_HTTPX_CLIENT
    if _SHARED_HTTPX_CLIENT is not None:
        return _SHARED_HTTPX_CLIENT
    try:
        import httpx

        _SHARED_HTTPX_CLIENT = httpx.Client(
            limits=httpx.Limits(
                max_connections=32,
                max_keepalive_connections=16,
                keepalive_expiry=60.0,
            ),
            timeout=45.0,
        )
    except Exception:
        _SHARED_HTTPX_CLIENT = None
    return _SHARED_HTTPX_CLIENT


def get_genai_client(key: str, timeout_ms: int = 25_000):
    """Return a cached `google.genai.Client` configured for sub-second failover.

    - `retry_options=HttpRetryOptions(attempts=1)` disables the SDK's hidden
      5-attempt exponential backoff (15–30s stall on a 429 key), so 429 fails
      back to APIKeyPool in ~230–300 ms.
    - Shared `httpx.Client` keep-alive pool lets Key #2 reuse Key #1's open
      TLS socket to generativelanguage.googleapis.com (0 ms TLS handshake).
    """
    from google import genai
    from google.genai import types

    cache_key = (key, int(timeout_ms), id(genai.Client))
    cached = _GENAI_CLIENTS.get(cache_key)
    if cached is not None:
        return cached
    with _GENAI_CLIENTS_LOCK:
        cached = _GENAI_CLIENTS.get(cache_key)
        if cached is not None:
            return cached
        retry_opts = None
        if hasattr(types, "HttpRetryOptions"):
            try:
                retry_opts = types.HttpRetryOptions(attempts=1)
            except Exception:
                retry_opts = None
        http_kwargs: dict = {"timeout": int(timeout_ms)}
        if retry_opts is not None:
            http_kwargs["retry_options"] = retry_opts
        # Attach shared keep-alive httpx_client only when real HttpOptions supports it
        fields = getattr(types.HttpOptions, "model_fields", None) or {}
        if "httpx_client" in fields:
            shared_http = _get_shared_httpx_client()
            if shared_http is not None:
                http_kwargs["httpx_client"] = shared_http
        client = genai.Client(
            api_key=key,
            http_options=types.HttpOptions(**http_kwargs),
        )
        _GENAI_CLIENTS[cache_key] = client
        return client


# Models whose API rejects ThinkingConfig(thinking_budget=0) with 400 INVALID_ARGUMENT:
# - "minimal": replace with ThinkingConfig(thinking_level="minimal")
# - "omit": omit thinking_config entirely
_THINKING_MODE_OVERRIDES: dict[str, str] = {
    "gemini-flash-lite-latest": "minimal",
    "gemini-3.5-flash-lite": "omit",
}
_THINKING_OVERRIDE_LOCK = threading.Lock()


def mark_thinking_budget_unsupported(model: str) -> None:
    """Remember that `model` rejected `thinking_budget=0` so future calls omit it."""
    with _THINKING_OVERRIDE_LOCK:
        _THINKING_MODE_OVERRIDES[model] = "omit"


def adapt_config_for_model(config, model: str):
    """Adapt a GenerateContentConfig's `thinking_config` for model compatibility."""
    if config is None:
        return None
    with _THINKING_OVERRIDE_LOCK:
        mode = _THINKING_MODE_OVERRIDES.get(model)
    if not mode:
        return config
    if getattr(config, "thinking_config", None) is None:
        return config
    try:
        from google.genai import types

        if mode == "minimal":
            return config.model_copy(
                update={"thinking_config": types.ThinkingConfig(thinking_level="minimal")}
            )
        return config.model_copy(update={"thinking_config": None})
    except Exception:
        return config


def classify_quota_scope(exc: Exception) -> tuple[str, float]:
    """Distinguish per-minute RPM/TPM 429 (short cooldown) from daily RPD 429 (24h).

    Returns `("rpm", cooldown_seconds)` or `("rpd", DEPLETION_RESET_SECONDS)`.
    """
    text = str(exc).lower()
    # Explicit daily exhaustion / zero-quota tier -> 24h depletion
    if any(tok in text for tok in (
        "perday", "per_day", "requestsperday", "daily", "limit: 0", "limit:0",
    )):
        return "rpd", float(DEPLETION_RESET_SECONDS)

    retry_m = re.search(r"retry\s+in\s+(\d+(?:\.\d+)?)\s*s", text)
    retry_s = float(retry_m.group(1)) if retry_m else None

    # Explicit per-minute rate limit -> short cooldown (do NOT ban pair for 24h)
    if any(tok in text for tok in (
        "perminute", "per_minute", "requestsperminute", "tokensperminute",
        "permodelperminute", " rpm", "(rpm)", " tpm", "(tpm)",
    )):
        cd = max(10.0, min((retry_s + 2.0) if retry_s is not None else RPM_COOLDOWN_SECONDS, 90.0))
        return "rpm", cd

    # Short retry window (<= 120s) with no mention of daily quota -> RPM burst
    if retry_s is not None and retry_s <= 120.0 and "day" not in text:
        return "rpm", max(10.0, min(retry_s + 2.0, 90.0))

    # Conservative default: daily quota exhausted
    return "rpd", float(DEPLETION_RESET_SECONDS)


@dataclass
class KeyState:
    key: str
    dead: bool = False                      # invalid / forbidden key
    dead_reason: str = ""
    depleted: dict[str, float] = field(default_factory=dict)       # model -> marked-at (24h RPD)
    rpm_cooldown: dict[str, float] = field(default_factory=dict)   # model -> cooldown-until (short RPM)
    unavailable: dict[str, str] = field(default_factory=dict)      # model -> reason (404)
    unavailable_ts: dict[str, float] = field(default_factory=dict) # model -> marked-at
    ok_calls: int = 0
    masked: str = ""

    def __post_init__(self) -> None:
        if not self.masked:
            k = self.key
            self.masked = f"{k[:6]}…{k[-4:]}" if len(k) > 12 else k


class APIKeyPool:
    def __init__(
        self,
        keys: list[str],
        models: list[str] | None = None,
        depletion_reset_seconds: int = DEPLETION_RESET_SECONDS,
    ) -> None:
        # Deduplicate keys and models while preserving clean values
        seen_k: set[str] = set()
        clean_keys: list[str] = []
        for k in keys:
            ks = (k or "").strip()
            if ks and ks not in seen_k:
                seen_k.add(ks)
                clean_keys.append(ks)
        self.states = [KeyState(k) for k in clean_keys]

        seen_m: set[str] = set()
        clean_models: list[str] = []
        for m in (models or DEFAULT_MODELS):
            ms = (m or "").strip()
            if ms and ms not in seen_m:
                seen_m.add(ms)
                clean_models.append(ms)
        self.models = clean_models
        self.depletion_reset_seconds = depletion_reset_seconds
        self._transient_503: dict[str, int] = {}     # model -> consecutive fails
        self._model_cooldown: dict[str, float] = {}  # model -> cooldown-until
        self.soft_cooldown_seconds = SOFT_COOLDOWN_SECONDS
        self.transient_threshold = TRANSIENT_THRESHOLD
        # الترتيب بالسرعة والرتبة: أسرع/أقوى الموديلات أولًا
        self.models = sorted(
            self.models,
            key=lambda m: (-MODEL_RANK.get(m, MODEL_RANK_DEFAULT), m))
        # إحصاء لكل موديل — الترتيب الحي بالسرعة والأداء
        self.model_stats: dict[str, dict] = {}
        # قياس سرعة التبديل الفعلي بين المفاتيح/الموديلات عند انتهاء الحصة
        self._last_switch_ms: float | None = None
        self._switch_ms_sum: float = 0.0
        self._switch_count: int = 0
        # ذاكرة صحة دائمة: حالة الموديلات المستنزفة/الميتة تنجو من إعادة التشغيل
        self._health_file = (Path(__file__).resolve().parents[2]
                             / "cache" / "model_health.json")
        self._last_health_save: float = 0.0
        self._load_model_health()
        # Random key offset within the #1 fastest model tier: spreads fresh
        # runs across all 7 API keys while ALWAYS starting on the fastest model.
        self._counter = random.randrange(len(self.states)) if self.states else 0
        self._lock = threading.Lock()  # pick/mark are called from worker threads

    # ----------------------------------------- persistent model health

    def _load_model_health(self) -> None:
        """حالة الموديلات الميتة تنجو من إعادة التشغيل — التشغيل الجديد
        يبدأ معرفًا بالمستنزف/المتبرّد (صفر اكتشاف مكلف)."""
        try:
            import json
            f = self._health_file
            if not f.exists():
                return
            data = json.loads(f.read_text(encoding="utf-8"))
            now = time.time()
            # الصيغة: مفتاح التسجيل = masked|model — يُطبق على حالته
            for rec_key, rec in (data.get("depleted") or {}).items():
                masked, _, model = rec_key.partition("|")
                state = next((s for s in self.states
                              if s.masked == masked), None)
                ts = float(rec.get("ts", 0))
                if state is not None and model and now - ts < (
                        self.depletion_reset_seconds):
                    state.depleted[model] = ts
            for rec_key, rec in (data.get("unavailable") or {}).items():
                masked, _, model = rec_key.partition("|")
                state = next((s for s in self.states
                              if s.masked == masked), None)
                ts = float(rec.get("ts", 0))
                if state is not None and model and now - ts < 6 * 3600:
                    state.unavailable[model] = str(rec.get("reason", ""))[:120]
                    state.unavailable_ts[model] = ts
            for model, until in (data.get("cooldown") or {}).items():
                if float(until) > now:
                    self._model_cooldown[model] = float(until)
        except Exception:
            pass  # الذاكرة الدائمة تحسين — فشلها لا يوقف المسبح

    def _maybe_save_model_health(self) -> None:
        """Debounced persist (<= 2 writes/sec) so rapid multi-key failover stays < 1ms."""
        now = time.monotonic()
        if now - self._last_health_save < 0.5:
            return
        self._last_health_save = now
        self._save_model_health()

    def _save_model_health(self) -> None:
        try:
            import json
            f = self._health_file
            f.parent.mkdir(parents=True, exist_ok=True)
            now = time.time()
            data = {
                "ts": now,
                "depleted": {
                    f"{s.masked}|{m}": {"ts": ts}
                    for s in self.states for m, ts in s.depleted.items()
                    if now - ts < self.depletion_reset_seconds
                },
                "unavailable": {
                    f"{s.masked}|{m}": {
                        "reason": r,
                        "ts": s.unavailable_ts.get(m, now),
                    }
                    for s in self.states for m, r in s.unavailable.items()
                },
                "cooldown": {m: u for m, u in self._model_cooldown.items()
                             if u > now},
            }
            f.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                         encoding="utf-8")
        except Exception:
            pass

    def _bump_model_stats(self, model: str, seconds: float | None = None,
                          failed: bool = False) -> None:
        st = self.model_stats.setdefault(
            model, {"ok": 0, "fail": 0, "lat_sum": 0.0, "lat_n": 0})
        if failed:
            st["fail"] += 1
        else:
            st["ok"] += 1
            if seconds is not None:
                st["lat_sum"] += seconds
                st["lat_n"] += 1

    def _usable_model(self, state: KeyState, model: str) -> bool:
        if model in state.unavailable:
            return False
        now = time.time()
        # التبريد الناعم: موديل يترصد 503/504 عابرة — تنتهي تلقائيًا بالزمن
        if now < self._model_cooldown.get(model, 0.0):
            return False
        # تبريد RPM القصير (حد الطلبات في الدقيقة — يعود بعد ~65 ثانية)
        if now < state.rpm_cooldown.get(model, 0.0):
            return False
        marked_at = state.depleted.get(model)
        if marked_at is None:
            return True
        return now - marked_at > self.depletion_reset_seconds

    def _effective_speed_key(self, model: str) -> tuple[float, int, str]:
        """Dynamic speed priority key (lower = faster = picked earlier).

        When live latency has been observed (`lat_n >= 1`), uses the measured
        average response time so faster models automatically move ahead of
        slower ones. Before any live measurement, falls back deterministically
        to `MODEL_RANK` (higher rank = smaller prior latency).
        """
        rank = MODEL_RANK.get(model, MODEL_RANK_DEFAULT)
        st = self.model_stats.get(model)
        if st and st.get("lat_n", 0) > 0:
            avg_s = st["lat_sum"] / st["lat_n"]
            return (avg_s, -rank, model)
        prior_s = 1.0 + max(0, 120 - rank) * 0.05
        return (prior_s, -rank, model)

    def _ordered_models_unlocked(self) -> list[str]:
        # Only re-sort dynamically once at least one model has live latency data;
        # when completely unmeasured, self.models is already sorted by MODEL_RANK.
        if not any((st.get("lat_n", 0) > 0) for st in self.model_stats.values()):
            return self.models
        return sorted(self.models, key=self._effective_speed_key)

    # ------------------------------------------------- transient soft-cooldown

    def mark_transient_failure(self, model: str) -> None:
        """سجّل فشلًا عابرًا (503/504) على موديل — بعد فشلين متتاليين يُبرَّد
        الموديل كلًّا فلا يُختار في pick خلال نافذة قصيرة."""
        with self._lock:
            n = self._transient_503.get(model, 0) + 1
            self._transient_503[model] = n
            self._bump_model_stats(model, failed=True)
            if n >= self.transient_threshold:
                self._model_cooldown[model] = (
                    time.time() + self.soft_cooldown_seconds)
                self._maybe_save_model_health()

    def reset_transient(self, model: str) -> None:
        """نجاح = ومضة الـ503 السابقة لم تكن عطلًا — يفك العداد."""
        with self._lock:
            self._transient_503.pop(model, None)

    def model_in_cooldown(self, model: str) -> bool:
        """للتشخيص والاختبار: هل الموديل في نافذة التبريد الآن؟"""
        with self._lock:
            return time.time() < self._model_cooldown.get(model, 0.0)

    # ------------------------------------------------------------------ pick

    def pick(self) -> tuple[KeyState, str] | None:
        """Next available (key, model) pair in Model-First × Key-Round-Robin order.

        Walks the fastest healthy model across ALL keys first (spreading RPM
        across all 7 keys with zero collision), then steps to the next fastest
        model across all keys, utilizing 100% of `len(keys) * len(models)` pairs.
        Thread-safe (vision extraction runs batches concurrently).
        """
        with self._lock:
            ordered_models = self._ordered_models_unlocked()
            n_keys, n_models = len(self.states), len(ordered_models)
            total = n_keys * n_models
            if total == 0:
                return None
            for offset in range(total):
                idx = (self._counter + offset) % total
                model = ordered_models[idx // n_keys]
                state = self.states[idx % n_keys]
                if state.dead:
                    continue
                if not self._usable_model(state, model):
                    continue
                self._counter = (idx + 1) % total
                return state, model
        return None

    def pick_distinct_model(
        self, exclude_models: set[str] | None = None
    ) -> tuple[KeyState, str] | None:
        """Pick a healthy (key, model) pair whose model is STRICTLY outside
        `exclude_models`, preferring a different model tier (e.g. full Flash
        when the primary pass ran on Flash-Lite, or vice versa).

        Returns None when no distinct healthy model is available — callers
        must NEVER treat a same-model repeat as an independent cross-model
        verification witness.
        """
        excluded = {m for m in (exclude_models or set()) if m}
        with self._lock:
            ordered = [m for m in self._ordered_models_unlocked() if m not in excluded]
            if not ordered or not self.states:
                return None
            # Prefer a contrasting architecture/tier when available
            excluded_all_lite = bool(excluded) and all("lite" in m.lower() for m in excluded)
            excluded_no_lite = bool(excluded) and all("lite" not in m.lower() for m in excluded)
            if excluded_all_lite:
                ordered.sort(key=lambda m: (1 if "lite" in m.lower() else 0, -MODEL_RANK.get(m, MODEL_RANK_DEFAULT)))
            elif excluded_no_lite:
                ordered.sort(key=lambda m: (0 if "lite" in m.lower() else 1, -MODEL_RANK.get(m, MODEL_RANK_DEFAULT)))
            n_keys = len(self.states)
            for model in ordered:
                for offset in range(n_keys):
                    state = self.states[(self._counter + offset) % n_keys]
                    if state.dead:
                        continue
                    if not self._usable_model(state, model):
                        continue
                    self._counter = (self._counter + offset + 1) % max(1, n_keys * len(self.models))
                    return state, model
        return None

    # --------------------------------------------------------------- marking

    def _find(self, key: str) -> KeyState | None:
        return next((s for s in self.states if s.key == key), None)

    def record_call(self, model: str, seconds: float) -> None:
        """إحصاء النداء الناجح لكل موديل وسرعته الحية — ورفع أي تبريد ساري فورًا."""
        with self._lock:
            self._bump_model_stats(model, seconds)
            self._transient_503.pop(model, None)
            self._model_cooldown.pop(model, None)

    def record_failover(self, elapsed_ms: float) -> None:
        """Record observed failover switch duration (ms) when rotating on error."""
        with self._lock:
            ms = max(0.0, float(elapsed_ms))
            self._last_switch_ms = round(ms, 1)
            self._switch_ms_sum += ms
            self._switch_count += 1

    def mark_rpm_limited(
        self, key: str, model: str, cooldown_seconds: float = RPM_COOLDOWN_SECONDS
    ) -> None:
        """Per-minute RPM/TPM 429: cool down ONLY this (key, model) pair briefly."""
        with self._lock:
            state = self._find(key)
            if state:
                state.rpm_cooldown[model] = time.time() + float(cooldown_seconds)
            self._bump_model_stats(model, failed=True)

    def mark_quota_exhausted(self, key: str, model: str) -> None:
        """Daily RPD 429: mark this (key, model) pair depleted for 24 hours."""
        with self._lock:
            state = self._find(key)
            if state:
                state.depleted[model] = time.time()
            self._bump_model_stats(model, failed=True)
            self._maybe_save_model_health()

    def mark_model_unavailable(
        self, key: str, model: str, reason: str, all_keys: bool = False
    ) -> None:
        """404 model not found: exclude for this key (or all keys if deprecated globally)."""
        with self._lock:
            now = time.time()
            targets = self.states if all_keys else ([s] if (s := self._find(key)) else [])
            for state in targets:
                state.unavailable[model] = reason
                state.unavailable_ts[model] = now
            self._bump_model_stats(model, failed=True)
            self._maybe_save_model_health()

    def mark_dead(self, key: str, reason: str) -> None:
        with self._lock:
            state = self._find(key)
            if state:
                state.dead = True
                state.dead_reason = reason
            self._maybe_save_model_health()

    def mark_success(self, key: str) -> None:
        with self._lock:
            state = self._find(key)
            if state:
                state.ok_calls += 1

    def reset_statuses(self) -> None:
        with self._lock:
            self._transient_503.clear()
            self._model_cooldown.clear()
            for state in self.states:
                state.dead = False
                state.dead_reason = ""
                state.depleted.clear()
                state.rpm_cooldown.clear()
                state.unavailable.clear()
                state.unavailable_ts.clear()
            self._save_model_health()

    # ---------------------------------------------------------------- status

    def status(self) -> dict:
        with self._lock:
            now = time.time()
            ordered_models = self._ordered_models_unlocked()
            active = sum(1 for s in self.states if not s.dead)
            total_pairs = len(self.states) * len(self.models)
            depleted_pairs = sum(
                1
                for s in self.states
                for m in self.models
                if m in s.depleted and (now - s.depleted[m]) <= self.depletion_reset_seconds
            )
            rpm_cooling_pairs = sum(
                1
                for s in self.states
                for m in self.models
                if now < s.rpm_cooldown.get(m, 0.0)
            )
            usable_pairs = sum(
                1
                for s in self.states
                if not s.dead
                for m in self.models
                if self._usable_model(s, m)
            )
            ranking_rows = []
            for m in ordered_models:
                st = self.model_stats.get(m) or {}
                lat_n = st.get("lat_n", 0)
                avg_s = round(st.get("lat_sum", 0.0) / lat_n, 2) if lat_n else None
                ranking_rows.append({
                    "model": m,
                    "rank": MODEL_RANK.get(m, MODEL_RANK_DEFAULT),
                    "ok": st.get("ok", 0),
                    "fail": st.get("fail", 0),
                    "avg_s": avg_s,
                    "cooling": now < self._model_cooldown.get(m, 0.0),
                })
            ranking_rows.sort(
                key=lambda x: (
                    x["cooling"],
                    x["avg_s"] if x["avg_s"] is not None else 999.0,
                    -x["ok"],
                    -x["rank"],
                )
            )
            return {
                "total_keys": len(self.states),
                "active_keys": active,
                "models": list(ordered_models),
                "total_pairs": total_pairs,
                "usable_pairs": usable_pairs,
                "depleted_pairs": depleted_pairs,
                "rpm_cooling_pairs": rpm_cooling_pairs,
                "est_daily_quota": total_pairs * DAILY_QUOTA_PER_PAIR,
                "est_remaining_quota": usable_pairs * DAILY_QUOTA_PER_PAIR,
                "last_switch_ms": self._last_switch_ms,
                "avg_switch_ms": (
                    round(self._switch_ms_sum / self._switch_count, 1)
                    if self._switch_count else None
                ),
                "switches": self._switch_count,
                "total_ok_calls": sum(s.ok_calls for s in self.states),
                "model_ranking": ranking_rows,
                "states": [
                    {
                        "masked": s.masked,
                        "dead": s.dead,
                        "dead_reason": s.dead_reason,
                        "depleted": [
                            m for m in self.models
                            if m in s.depleted and (now - s.depleted[m]) <= self.depletion_reset_seconds
                        ],
                        "rpm_cooling": [
                            m for m in self.models if now < s.rpm_cooldown.get(m, 0.0)
                        ],
                        "unavailable": [m for m in self.models if m in s.unavailable],
                        "ok_calls": s.ok_calls,
                    }
                    for s in self.states
                ],
            }

    @property
    def total_pairs(self) -> int:
        return len(self.states) * len(self.models)

    def has_usable_pairs(self) -> bool:
        """True when at least one (key, model) pair is still usable.

        Read-only existence check — never consumes a rotation slot.
        """
        with self._lock:
            for state in self.states:
                if state.dead:
                    continue
                for model in self.models:
                    if self._usable_model(state, model):
                        return True
            return False

    # ------------------------------------------------------------------ env

    @classmethod
    def from_env(cls) -> "APIKeyPool":
        raw = os.getenv("GEMINI_API_KEYS", "").strip()
        keys = [k.strip() for k in raw.replace("\n", ",").split(",") if k.strip()]
        if not keys:
            single = (os.getenv("GEMINI_API_KEY") or "").strip()
            keys = [single] if single else []
        models_raw = os.getenv("GEMINI_MODELS", "").strip()
        models = [m.strip() for m in models_raw.split(",") if m.strip()] or list(DEFAULT_MODELS)
        return cls(keys, models)
