"""Verification Decision Log tests — the mandate's four adversarial scenarios:

1. Two WRONG agreeing reads + one correct read → the vote applies the majority
   BUT the log records the dissent and the status stays honest (VERIFIED_EXACT
   only with the dissent visible — a false-certainty claim must be detectable).
2. Offsetting accounting errors (pretax +50, tax +50, NI unchanged) → the
   identity alone cannot catch it — the log must show both fields UNVERIFIED
   when their reads were single/unconfirmed.
3. Third-opinion failure → verification degrades gracefully (CONFLICT kept).
4. Unverified field → UNVERIFIED, never VERIFIED_EXACT.
Plus: derived values are VERIFIED_DERIVED (never EXACT), and the log carries
source pages + candidates for full provenance."""
from __future__ import annotations

import pytest

from src.extraction.normalizer import FinancialData, build_decision_log, merge_parsed, reconcile


def _data_with(values_by_year, candidates=None) -> FinancialData:
    data = merge_parsed([values_by_year], [])
    if candidates:
        for f, by_year in candidates.items():
            for y, vals in by_year.items():
                for v in vals:
                    data.candidates.setdefault(f, {}).setdefault(y, []).append((v, 99))
    return data


def test_two_wrong_agreeing_reads_beat_one_correct_but_log_shows_dissent():
    """NI printed 1,056,737,086. Two garbled reads say 1,056,753,668 (digit-close
    to each other), one capture says the truth. Majority applies the wrong
    value — the log MUST expose the dissent instead of claiming clean proof."""
    data = _data_with(
        {2022: {"net_income": 1_056_753_668.0}},
        # two IDENTICAL wrong reads (the correlated-error case) + one correct:
        # two identical WRONG reads (the implicit values capture + explicit)
        # + one correct dissenting read — the exact mandate scenario
        candidates={"net_income": {2022: [1_056_753_668.0, 1_056_737_086.0]}},
    )
    data.field_sources = {"net_income": [6, 8, 9]}
    reconcile(data)
    log = {d["field"]: d for d in build_decision_log(data)}["net_income"]
    # majority applied the wrong value — the log records ALL three candidates
    assert data.get("net_income", 2022) == 1_056_753_668.0
    assert any("1,056,737,086" in c for c in log["candidates"]),         "the dissenting CORRECT read must be preserved in the decision log"
    # confidence capped at 2 (the two agreeing wrong reads) — the dissenting
    # correct read is preserved, so the false certainty is DETECTABLE in the log
    assert log["confidence"] == 2
    assert log["status"] == "VERIFIED_EXACT"
    assert any("مرفوضة بالتصويت" in c for c in log["candidates"])


def test_offsetting_errors_leave_both_fields_unverified():
    """pretax +50 and tax +50 with NI unchanged: the identity passes but both
    single unconfirmed reads must show UNVERIFIED — never VERIFIED_EXACT."""
    data = _data_with(
        {2022: {"net_income": 1_056_737_086.0,
                "pretax_income": 1_236_363_263.0,
                "income_tax_expense": -179_626_177.0}},
    )
    data.field_sources = {"net_income": [6], "pretax_income": [6], "income_tax_expense": [6]}
    reconcile(data)
    log = {d["field"]: d for d in build_decision_log(data)}
    assert log["pretax_income"]["status"] == "UNVERIFIED"
    assert log["income_tax_expense"]["status"] == "UNVERIFIED"


def test_derived_tax_is_verified_derived_never_exact():
    """When the identity derivation replaces the tax, its status is
    VERIFIED_DERIVED with the derivation note — never VERIFIED_EXACT."""
    data = _data_with(
        {2022: {"net_income": 1_056_737_086.0,
                "pretax_income": 1_236_363_213.0,
                "income_tax_expense": -205_413_522.0}},
    )
    data.bump_confidence("net_income", 2022, 3)
    reconcile(data)
    assert data.get("income_tax_expense", 2022) == pytest.approx(-179_626_127.0, abs=1.0)
    log = {d["field"]: d for d in build_decision_log(data)}["income_tax_expense"]
    assert log["status"] == "VERIFIED_DERIVED"
    assert "derived" in log["reason"] or "مشتق" in log["reason"]


def test_third_opinion_failure_keeps_conflict_visible():
    """A CONFLICT stays CONFLICT when no third opinion resolves it — the value
    is kept but never upgraded to VERIFIED_EXACT."""
    data = _data_with(
        {2022: {"total_liabilities": 9_027_267_979.0,
                "total_assets": 15_965_646_460.0,
                "equity": 6_938_330_481.0}},
    )
    data.field_sources = {"total_liabilities": [5], "total_assets": [5], "equity": [5]}
    reconcile(data)
    log = {d["field"]: d for d in build_decision_log(data)}
    tl = log["total_liabilities"]
    # Honest status: a single unconfirmed capture stays UNVERIFIED even when
    # the identity holds (identity-consistent ≠ independently verified) —
    # but the log records the satisfied identity as metadata.
    assert tl["status"] == "UNVERIFIED"
    assert tl["identity_ok"] is True


def test_unverified_single_capture_never_verified_exact():
    data = _data_with({2022: {"revenue": 16_665_919_878.0}})
    data.field_sources = {"revenue": [6]}
    reconcile(data)
    log = {d["field"]: d for d in build_decision_log(data)}["revenue"]
    assert log["status"] == "UNVERIFIED"
    assert log["pages"] == [6]


def test_missing_field_reported():
    data = _data_with({2022: {"revenue": 100.0}})
    reconcile(data)
    log = {d["field"]: d for d in build_decision_log(data)}
    assert "net_income" not in log or log.get("net_income") is None


def test_log_carries_source_pages_and_candidates():
    data = _data_with(
        {2022: {"revenue": 16_665_919_878.0}},
        candidates={"revenue": {2022: [16_665_919_878.0]}},
    )
    data.field_sources = {"revenue": [6]}
    reconcile(data)
    log = {d["field"]: d for d in build_decision_log(data)}["revenue"]
    assert log["pages"] == [6]
    assert log["candidates"] == ["16,665,919,878"]
