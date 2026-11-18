"""Rotating pool of Gemini API keys and models.

The "endpoint layer": every Gemini call goes through this pool. When a key's
free quota is exhausted (429) the call moves to the next key immediately; if a
model is unavailable for a key (404) the fallback model is tried. Quotas are
per-model, so alternating models on each call effectively doubles the free
allowance per key. Depleted statuses auto-expire after DEPLETION_RESET_SECONDS.

Thread-safe: vision extraction runs batches concurrently, so pick()/mark_*
are guarded by a lock.
"""
from __future__ import annotations

import os
import random
import threading
import time
from pathlib import Path
from dataclasses import dataclass, field

DEPLETION_RESET_SECONDS = 24 * 60 * 60
DEFAULT_MODELS = ["gemini-3.8-flash", "gemini-3.7-flash"]
# ترتيب القوة/الأفضلية: رقم أعلى = يُجرَّب أولًا. الأحدث الحي (preview)
# والflash العائلة أولًا — pro أقوى لكن أبطأ وحصة أقل فآخر الجدول.
MODEL_RANK = {
    "gemini-3-flash-preview": 100,
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
# التبريد الناعم (تسريع 2026-11-13): 503 «high demand» عابرة لكن إعادة
# الدوران على موديل معطل يهدر حتى 45 ثانية × كل محاولة pick — بعد فشلين
# متتاليين يُستبعد الموديل من pick لمدة قصيرة تلقائيًا، والجولة تتقارب
# فورًا على الموديلات الحية. ومضة واحدة لا تبرّد (النجاح يفك العداد).
TRANSIENT_THRESHOLD = 2
SOFT_COOLDOWN_SECONDS = 90


@dataclass
class KeyState:
    key: str
    dead: bool = False                      # invalid / forbidden key
    dead_reason: str = ""
    depleted: dict[str, float] = field(default_factory=dict)   # model -> marked-at
    unavailable: dict[str, str] = field(default_factory=dict)  # model -> reason
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
        self.states = [KeyState(k.strip()) for k in keys if k and k.strip()]
        self.models = [m.strip() for m in (models or DEFAULT_MODELS) if m and m.strip()]
        self.depletion_reset_seconds = depletion_reset_seconds
        self._transient_503: dict[str, int] = {}     # model -> consecutive fails
        self._model_cooldown: dict[str, float] = {}  # model -> cooldown-until
        self.soft_cooldown_seconds = SOFT_COOLDOWN_SECONDS
        self.transient_threshold = TRANSIENT_THRESHOLD
        # الترتيب بالرتبة: داخل نفس المفتاح تُجرَّب الموديلات الأقوى/الأحدث
        # أولًا (الموديلات بلا لاحقة رقمية/معاينة تُرتب حسب الجدول)
        self.models = sorted(
            self.models,
            key=lambda m: (-MODEL_RANK.get(m, MODEL_RANK_DEFAULT), m))
        # إحصاء لكل موديل — الترتيب الذي يطلبه المستخدم (أقوى/أسرع/حالته)
        self.model_stats: dict[str, dict] = {}
        # ذاكرة صحة دائمة: حالة الموديلات الميتة تنجو من إعادة التشغيل
        self._health_file = (Path(__file__).resolve().parents[2]
                             / "cache" / "model_health.json")
        self._load_model_health()
        # Random start: every process used to begin at pair 0, so repeated
        # short-lived runs (each Streamlit/script run) hammered the SAME first
        # pairs until they 429'd while the rest of the pool sat unused.
        total = len(self.states) * len(self.models)
        self._counter = random.randrange(total) if total else 0
        self._lock = threading.Lock()  # pick/mark are called from worker threads

    # ------------------------------------------------------------------ pick

    # ----------------------------------------- persistent model health

    def _load_model_health(self) -> None:
        """حالة الموديلات الميتة تنجو من إعادة التشغيل — التشغيل الجديد
        يبدأ معرفًا بالمستنزف/المتبرّد (صفر اكتشاف مكلف 45 ثانية)."""
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
                if state is not None and model and now - float(
                        rec.get("ts", 0)) < 6 * 3600:
                    state.unavailable[model] = str(rec.get("reason", ""))[:120]
            for model, until in (data.get("cooldown") or {}).items():
                if float(until) > now:
                    self._model_cooldown[model] = float(until)
        except Exception:
            pass  # الذاكرة الدائمة تحسين — فشلها لا يوقف المسبح

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
                    f"{s.masked}|{m}": {"reason": r}
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
        # التبريد الناعم: موديل يترصد 503 عابرة — تنتهي تلقائيًا بالزمن
        if time.time() < self._model_cooldown.get(model, 0.0):
            return False
        marked_at = state.depleted.get(model)
        if marked_at is None:
            return True
        return time.time() - marked_at > self.depletion_reset_seconds

    # ------------------------------------------------- transient soft-cooldown

    def mark_transient_failure(self, model: str) -> None:
        """سجّل فشلًا عابرًا (503) على موديل — بعد فشلين متتاليين يُبرَّد
        الموديل كلًّا فلا يُختار في pick خلال نافذة قصيرة (يولّد الجولة
        العاصفة دقائق هدرًا بدل التقارب على الموديلات الحية)."""
        with self._lock:
            n = self._transient_503.get(model, 0) + 1
            self._transient_503[model] = n
            self._bump_model_stats(model, failed=True)   # كل فشل يُحصى
            if n >= self.transient_threshold:
                self._model_cooldown[model] = (
                        time.time() + self.soft_cooldown_seconds)
                self._save_model_health()   # حفظ عند بدء التبريد فقط

    def reset_transient(self, model: str) -> None:
        """نجاح = ومضة الـ503 السابقة لم تكن عطلًا — يفك العداد."""
        with self._lock:
            self._transient_503.pop(model, None)

    def model_in_cooldown(self, model: str) -> bool:
        """للتشخيص والاختبار: هل الموديل في نافذة التبريد الآن؟"""
        with self._lock:
            return time.time() < self._model_cooldown.get(model, 0.0)

    def pick(self) -> tuple[KeyState, str] | None:
        """Next available (key, model) pair.

        Walks the cartesian product linearly so usage spreads evenly over ALL
        pairs — the models list is RANK-sorted (strongest/freshest first per
        key), so the rotation naturally tries the best model on each key
        before falling to the weaker ones (per-model quotas mean alternating
        models multiplies the free allowance per key).
        Thread-safe (vision extraction runs batches concurrently).
        """
        n_keys, n_models = len(self.states), len(self.models)
        total = n_keys * n_models
        if total == 0:
            return None
        with self._lock:
            for offset in range(total):
                idx = (self._counter + offset) % total
                state = self.states[idx // n_models]
                model = self.models[idx % n_models]
                if state.dead:
                    continue
                if not self._usable_model(state, model):
                    continue
                self._counter = (idx + 1) % total
                return state, model
        return None

    # --------------------------------------------------------------- marking

    def _find(self, key: str) -> KeyState | None:
        return next((s for s in self.states if s.key == key), None)

    def record_call(self, model: str, seconds: float) -> None:
        """إحصاء النداء الناجح لكل موديل — ورفع أي تبريد ساري فورًا:
        نجاح حي يثبت أن الموديل عاد قبل انتهاء نافذته."""
        with self._lock:
            self._bump_model_stats(model, seconds)
            self._transient_503.pop(model, None)
            self._model_cooldown.pop(model, None)

    def mark_quota_exhausted(self, key: str, model: str) -> None:
        with self._lock:
            state = self._find(key)
            if state:
                state.depleted[model] = time.time()
            self._bump_model_stats(model, failed=True)
            self._save_model_health()

    def mark_model_unavailable(self, key: str, model: str, reason: str) -> None:
        with self._lock:
            state = self._find(key)
            if state:
                state.unavailable[model] = reason
            self._bump_model_stats(model, failed=True)
            self._save_model_health()

    def mark_dead(self, key: str, reason: str) -> None:
        with self._lock:
            state = self._find(key)
            if state:
                state.dead = True
                state.dead_reason = reason
            self._save_model_health()

    def mark_success(self, key: str) -> None:
        with self._lock:
            state = self._find(key)
            if state:
                state.ok_calls += 1

    def reset_statuses(self) -> None:
        with self._lock:
            for state in self.states:
                state.dead = False
                state.dead_reason = ""
                state.depleted.clear()
                state.unavailable.clear()

    # ---------------------------------------------------------------- status

    def status(self) -> dict:
        active = sum(1 for s in self.states if not s.dead)
        depleted_pairs = sum(
            1
            for s in self.states
            for m in self.models
            if m in s.depleted and not self._usable_model(s, m)
        )
        return {
            "total_keys": len(self.states),
            "active_keys": active,
            "models": list(self.models),
            "depleted_pairs": depleted_pairs,
            "total_ok_calls": sum(s.ok_calls for s in self.states),
            # ترتيب الموديلات بالأداء الحي: نجاحات/فشل/متوسط الاستجابة/تبريد
            "model_ranking": sorted(
                (
                    {"model": m,
                     "rank": MODEL_RANK.get(m, MODEL_RANK_DEFAULT),
                     "ok": (self.model_stats.get(m) or {}).get("ok", 0),
                     "fail": (self.model_stats.get(m) or {}).get("fail", 0),
                     "avg_s": (
                         round((self.model_stats.get(m) or {}).get("lat_sum", 0)
                               / max(1, (self.model_stats.get(m) or {}).get("lat_n", 1)), 1)
                         if (self.model_stats.get(m) or {}).get("lat_n")
                         else None),
                     "cooling": self.model_in_cooldown(m)}
                    for m in self.models
                ),
                key=lambda x: (-x["ok"], x["avg_s"] if x["avg_s"] else 999),
            ),
            "states": [
                {
                    "masked": s.masked,
                    "dead": s.dead,
                    "dead_reason": s.dead_reason,
                    "depleted": [m for m in self.models if not self._usable_model(s, m) and m in s.depleted],
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

        Lets callers fail fast with a clear quota message instead of sweeping
        every batch against a pool that is already known-dead.

        التصحيح (تسريع 2026-11-13): كانت `pick() is not None` — الفحص
        يستهلك خانة من الدوران في كل استدعاء (200 خانة ضائعة في رحلة
        نموذجية بـ5 عمال × 40 نداءً + تفاوت حرق الحصص). الآن فحص وجودي
        لا يمس العدّاد.
        """
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
