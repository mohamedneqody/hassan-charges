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
