# -*- coding: utf-8 -*-
"""A degraded extraction (no revenue/net income) must never be cached or replayed."""
from __future__ import annotations

import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
if str(PROJ) not in sys.path:
    sys.path.insert(0, str(PROJ))


def test_degraded_cache_entry_is_ignored_and_replaced(tmp_path, monkeypatch):
    from src import pipeline
    from src.extraction import result_cache

    monkeypatch.setattr(result_cache, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(result_cache, "SEED_CACHE_DIR", tmp_path / "seed")

    sample = PROJ / "sample_data" / "sample_financials.csv"
    raw = sample.read_bytes()
    key = result_cache.extraction_key(sample.name, raw, "", False)

    # Poisoned entry: balance-sheet only, no revenue / net income
    result_cache.store_extraction(key, {
        "values": {"total_assets": {2021: 1.0, 2022: 2.0}},
        "notes": [],
    })

    calls = {"n": 0}
    real_loader = pipeline.load_financial_data

    def counting_loader(*a, **kw):
        calls["n"] += 1
        return real_loader(*a, **kw)

    monkeypatch.setattr(pipeline, "load_financial_data", counting_loader)

    res = pipeline.run_pipeline(sample.name, raw, "")
    assert calls["n"] == 1, "poisoned cache must trigger a fresh extraction"
    assert res["curr_metrics"].revenue is not None

    # The good result replaced the bad one: second run replays from cache
    res2 = pipeline.run_pipeline(sample.name, raw, "")
    assert calls["n"] == 1
    assert res2["curr_metrics"].revenue == res["curr_metrics"].revenue


def test_failed_extraction_is_not_stored(tmp_path, monkeypatch):
    import pytest

    from src import pipeline
    from src.exceptions import InsufficientDataError
    from src.extraction import result_cache
    from src.extraction.normalizer import FinancialData

    monkeypatch.setattr(result_cache, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(result_cache, "SEED_CACHE_DIR", tmp_path / "seed")

    def degraded_loader(*a, **kw):
        d = FinancialData(values={"total_assets": {2021: 10.0, 2022: 20.0}})
        d.notes.append("Vision batch 6-6 failed: 504 deadline exceeded")
        return d

    monkeypatch.setattr(pipeline, "load_financial_data", degraded_loader)
    raw = b"%PDF-fake"
    with pytest.raises(InsufficientDataError) as ei:
        pipeline.run_pipeline("x.pdf", raw, "")
    assert "failed" in str(ei.value).lower()
    key = result_cache.extraction_key("x.pdf", raw, None, False)
    assert result_cache.load_cached_extraction(key) is None
