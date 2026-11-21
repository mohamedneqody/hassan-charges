# -*- coding: utf-8 -*-
"""ترتيب الموديلات بالرتبة + ذاكرة الصحة الدائمة + إحصاء الأداء الحي."""
from src.ai.key_pool import APIKeyPool, MODEL_RANK


def _pool(tmp_path):
    p = APIKeyPool(["k1", "k2"],
                   ["gemini-3-flash-preview", "gemini-2.5-flash"])
    p._counter = 0   # حتمية الاختبار — البداية عشوائية في الإنتاج (key_pool.py:90)
    # الذاكرة الدائمة تشير لمسار مؤقت — لا تلوث الكاش الحقيقي
    p._health_file = tmp_path / "model_health.json"
    return p


def test_rank_order_within_key(tmp_path):
    """التدوير يمر على الأزواج بترتيب الرتبة: القوية أولًا في كل مفتاح."""
    p = _pool(tmp_path)
    seq = []
    for _ in range(4):
        s, m = p.pick()
        seq.append((s.key, m))
    # البداية عشوائية بين المفتاحين — المطلوب: القوية قبل الضعيفة داخل
    # كل مفتاح، وكل مفتاح يُغطى
    keys_covered = {k for k, _m in seq}
    assert len(keys_covered) == 2
    for key in keys_covered:
        block = [m for k, m in seq if k == key]
        assert block == ["gemini-3-flash-preview", "gemini-2.5-flash"]


def test_rank_order_is_by_model_rank_table(tmp_path):
    p = APIKeyPool(["k1"], ["gemini-2.5-flash", "gemini-3-flash-preview"])
    assert p.models[0] == "gemini-3-flash-preview"  # الرتبة أعلى = أول القائمة
    assert (MODEL_RANK["gemini-3-flash-preview"]
            > MODEL_RANK["gemini-2.5-flash"])


def test_depleted_pair_never_picked(tmp_path):
    """الزوج المستنزف لا يُختار إطلاقًا — البديل من أي مفتاح."""
    p = _pool(tmp_path)
    p.mark_quota_exhausted("k1", "gemini-3-flash-preview")
    for _ in range(6):
        s, m = p.pick()
        assert not (s.key == "k1" and m == "gemini-3-flash-preview")


def test_persistent_health_survives_restart(tmp_path):
    """المستنزف يُحفظ على القرص ويُحمّل في مسبح جديد — صفر اكتشاف مكلف."""
    p1 = _pool(tmp_path)
    p1.mark_quota_exhausted("k1", "gemini-3-flash-preview")
    p1._save_model_health()
    assert p1._health_file.exists()

    p2 = APIKeyPool(["k1", "k2"],
                    ["gemini-3-flash-preview", "gemini-2.5-flash"])
    p2._health_file = tmp_path / "model_health.json"
    p2._load_model_health()
    for _ in range(6):
        s, m = p2.pick()
        assert not (s.key == "k1" and m == "gemini-3-flash-preview")


def test_stats_ranking_in_status(tmp_path):
    p = _pool(tmp_path)
    p.record_call("gemini-3-flash-preview", 2.0)
    p.record_call("gemini-3-flash-preview", 4.0)
    p.mark_transient_failure("gemini-2.5-flash")
    p.mark_transient_failure("gemini-2.5-flash")
    st = p.status()
    ranking = {r["model"]: r for r in st["model_ranking"]}
    assert ranking["gemini-3-flash-preview"]["ok"] == 2
    assert abs(ranking["gemini-3-flash-preview"]["avg_s"] - 3.0) < 0.01
    assert ranking["gemini-2.5-flash"]["fail"] == 2
    assert ranking["gemini-2.5-flash"]["cooling"] is True
    assert st["model_ranking"][0]["model"] == "gemini-3-flash-preview"


def test_success_record_lifts_cooldown(tmp_path):
    """نجاح حي يثبت عودة الموديل — التبريد يُرفع فورًا."""
    p = _pool(tmp_path)
    p.mark_transient_failure("gemini-3-flash-preview")
    p.mark_transient_failure("gemini-3-flash-preview")
    assert p.model_in_cooldown("gemini-3-flash-preview")
    p.record_call("gemini-3-flash-preview", 1.0)
    assert not p.model_in_cooldown("gemini-3-flash-preview")


def test_full_7x7_pool_traversal_no_14_cap(tmp_path):
    """7 keys × 7 models = 49 pairs (980 RPD) — analyze_financials must traverse
    ALL 49 pairs instead of stopping early at 14, switching in sub-second time."""
    import json as _json
    import time as _t

    from src.ai.gemini_agent import analyze_financials
    from src.ai.key_pool import DEFAULT_MODELS

    keys = [f"key_{i:02d}_abcdefgh1234" for i in range(7)]
    assert len(DEFAULT_MODELS) == 7
    pool = APIKeyPool(keys, list(DEFAULT_MODELS))
    pool._health_file = tmp_path / "health_7x7.json"
    pool._counter = 0

    st0 = pool.status()
    assert st0["total_pairs"] == 49
    assert st0["usable_pairs"] == 49
    assert st0["est_daily_quota"] == 980

    good_json = _json.dumps({
        "ratio_comments": [{"metric": "Revenue", "comment": "ارتفع."}],
        "recommendations": [{"action": "تحسين السيولة.", "evidence": "Revenue: 100."}],
    }, ensure_ascii=False)
    calls: list[tuple[str, str]] = []

    def exhaust_48_then_ok(key, model, prompt, config):
        calls.append((key, model))
        if len(calls) <= 48:
            raise RuntimeError("429 RESOURCE_EXHAUSTED: GenerateRequestsPerDay limit: 20")
        return good_json

    payload = {
        "company": "TestCo",
        "metrics": [],
        "missing_data": [],
        "extraction_notes": [],
        "analysis_period": {"previous_year": 2020, "current_year": 2021},
    }
    # Pre-import google.genai so we measure failover loop speed, not cold SDK import
    import google.genai  # noqa: F401
    from src.ai.gemini_agent import _build_config
    _build_config()

    t0 = _t.perf_counter()
    res = analyze_financials(payload, pool=pool, caller=exhaust_48_then_ok)
    elapsed = _t.perf_counter() - t0

    assert res.ok is True
    assert len(calls) == 49, f"expected all 49 pairs traversed, got {len(calls)}"
    assert len(set(calls)) == 49, "every (key, model) pair must be unique"
    # First 7 calls rotate all 7 keys on the #1 fastest model before stepping down
    first_7_models = {m for _k, m in calls[:7]}
    first_7_keys = {k for k, _m in calls[:7]}
    assert len(first_7_models) == 1
    assert len(first_7_keys) == 7
    # Sub-second switching overhead across 48 failovers
    assert elapsed < 1.0, f"48 failovers took {elapsed:.3f}s (expected < 1.0s)"
    st1 = pool.status()
    assert st1["depleted_pairs"] == 48
    assert st1["usable_pairs"] == 1
    assert st1["switches"] == 48
    assert st1["last_switch_ms"] is not None and st1["last_switch_ms"] < 1000.0


def test_dynamic_speed_promotion_reorders_pick(tmp_path):
    """After measuring live latencies, a faster model jumps ahead of a slower one."""
    pool = APIKeyPool(["k1", "k2"], ["gemini-3-flash-preview", "gemini-3.6-flash"])
    pool._health_file = tmp_path / "health_speed.json"
    pool._counter = 0

    # Initially gemini-3-flash-preview (rank 100) leads gemini-3.6-flash (rank 90)
    assert pool.pick()[1] == "gemini-3-flash-preview"

    # Now live measurements show gemini-3.6-flash is much faster (0.4s vs 6.0s)
    pool.record_call("gemini-3-flash-preview", 6.0)
    pool.record_call("gemini-3.6-flash", 0.4)
    pool._counter = 0
    assert pool.pick()[1] == "gemini-3.6-flash"
    assert pool.status()["model_ranking"][0]["model"] == "gemini-3.6-flash"


def test_rpm_vs_rpd_quota_separation(tmp_path):
    """Per-minute RPM 429 cools a pair briefly without banning it for 24h."""
    import time as _t

    from src.ai.key_pool import classify_quota_scope

    scope_rpm, cd_rpm = classify_quota_scope(
        RuntimeError("429 RESOURCE_EXHAUSTED: GenerateRequestsPerMinute exceeded. Please retry in 18s")
    )
    assert scope_rpm == "rpm"
    assert 10.0 <= cd_rpm <= 90.0

    scope_rpd, _cd_rpd = classify_quota_scope(
        RuntimeError("429 RESOURCE_EXHAUSTED: GenerateRequestsPerDayPerProjectPerModel limit: 20")
    )
    assert scope_rpd == "rpd"

    pool = APIKeyPool(["k1"], ["m1"])
    pool._health_file = tmp_path / "health_rpm.json"
    pool.mark_rpm_limited("k1", "m1", cooldown_seconds=0.05)
    assert pool.pick() is None
    assert pool.status()["depleted_pairs"] == 0
    assert pool.status()["rpm_cooling_pairs"] == 1
    _t.sleep(0.06)
    assert pool.pick() is not None


def test_global_404_excludes_model_across_all_keys(tmp_path):
    """A globally deprecated 404 model is excluded on all 7 keys in one shot."""
    keys = [f"k{i}" for i in range(7)]
    pool = APIKeyPool(keys, ["m-dead", "m-alive"])
    pool._health_file = tmp_path / "health_404.json"
    pool.mark_model_unavailable("k0", "m-dead", "404 no longer available", all_keys=True)
    for _ in range(10):
        _s, m = pool.pick()
        assert m == "m-alive"


def test_genai_client_disables_hidden_sdk_retries():
    """Shared client sets HttpRetryOptions(attempts=1) & shared keep-alive httpx_client."""
    from src.ai.key_pool import get_genai_client

    c1 = get_genai_client("test-dummy-key-1-for-options-check", timeout_ms=15_000)
    c2 = get_genai_client("test-dummy-key-2-for-options-check", timeout_ms=15_000)
    http_opts = getattr(c1._api_client, "_http_options", None)
    assert http_opts is not None
    retry_opts = getattr(http_opts, "retry_options", None)
    assert retry_opts is not None
    assert getattr(retry_opts, "attempts", None) == 1
    # Both keys share one warm httpx connection pool (0 ms TLS handshake on switch)
    assert getattr(http_opts, "httpx_client", None) is not None
    assert http_opts.httpx_client is c2._api_client._http_options.httpx_client
    assert c1._api_client.api_key != c2._api_client.api_key
