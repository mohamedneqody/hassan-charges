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
from dataclasses import dataclass, field

DEPLETION_RESET_SECONDS = 24 * 60 * 60
DEFAULT_MODELS = ["gemini-3.8-flash", "gemini-3.7-flash"]


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
        # Random start: every process used to begin at pair 0, so repeated
        # short-lived runs (each Streamlit/script run) hammered the SAME first
        # pairs until they 429'd while the rest of the pool sat unused.
        total = len(self.states) * len(self.models)
        self._counter = random.randrange(total) if total else 0
        self._lock = threading.Lock()  # pick/mark are called from worker threads

    # ------------------------------------------------------------------ pick

    def _usable_model(self, state: KeyState, model: str) -> bool:
        if model in state.unavailable:
            return False
        marked_at = state.depleted.get(model)
        if marked_at is None:
            return True
        return time.time() - marked_at > self.depletion_reset_seconds

    def pick(self) -> tuple[KeyState, str] | None:
        """Next available (key, model) pair.

        Walks the cartesian product linearly so usage spreads evenly over ALL
        pairs — every key serves both models in turn (per-model quotas mean
        alternating models doubles the free allowance per key).
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

    def mark_quota_exhausted(self, key: str, model: str) -> None:
        with self._lock:
            state = self._find(key)
            if state:
                state.depleted[model] = time.time()

    def mark_model_unavailable(self, key: str, model: str, reason: str) -> None:
        with self._lock:
            state = self._find(key)
            if state:
                state.unavailable[model] = reason

    def mark_dead(self, key: str, reason: str) -> None:
        with self._lock:
            state = self._find(key)
            if state:
                state.dead = True
                state.dead_reason = reason

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
        """
        return self.pick() is not None

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
