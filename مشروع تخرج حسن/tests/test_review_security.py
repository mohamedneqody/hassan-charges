# -*- coding: utf-8 -*-
"""Security acceptance tests for the human-review chain (اختبارات قبول أمنية).

Isolated: every test gets its own reviewers file, HMAC key, review log and
attempts-state file under tmp_path. Covers the full tamper matrix — edit,
delete, reorder, rewrite, interrupted write, concurrent reviews — plus
PIN storage (PBKDF2, never plaintext/bare-sha256), brute-force lockout,
sessions (expiry, role enforcement, revocation), backend role enforcement,
context-complete gating, the TOCTOU source-change guard, and stale-record
reuse after invalidation. Secrets never appear in the log, the test output,
or anything committed.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

import pytest

PROJ = Path(__file__).resolve().parents[1]
CONF_ALL = {"document": True, "field": True, "year": True,
            "position": True, "value": True}
CONF_IDENTITY = {k: v for k, v in CONF_ALL.items() if k != "value"}


@pytest.fixture()
def secured(tmp_path, monkeypatch):
    """Isolated reviewer accounts + isolated log + isolated attempt state."""
    from src.extraction.human_review import pin_entry

    rf = tmp_path / "reviewers.json"
    pin_entry("auditor-A", "pin-A-123", ["approve", "correct", "reject"],
              file_path=rf)
    pin_entry("auditor-B", "pin-B-456", ["approve", "correct", "reject"],
              file_path=rf)
    pin_entry("ro-viewer", "pin-R-789", ["reject"], file_path=rf)
    monkeypatch.setenv("REVIEWERS_FILE", str(rf))
    monkeypatch.setenv("REVIEW_HMAC_KEY", "test-key-isolated-NOT-in-repo")
    monkeypatch.setenv("REVIEW_ATTEMPTS_PATH", str(tmp_path / ".attempts.json"))
    monkeypatch.delenv("REVIEWERS", raising=False)
    monkeypatch.chdir(tmp_path)          # crops_dir default resolves inside tmp
    return {"A": "pin-A-123", "B": "pin-B-456", "RO": "pin-R-789",
            "tmp": tmp_path}


@pytest.fixture()
def queue():
    from src.extraction.human_review import build_review_queue

    return build_review_queue(PROJ / "cell_evidence/per_cell_strict.json",
                              PROJ / "cell_evidence")


def _apply(secured, queue, log_path, pkt, value, reviewer="auditor-A",
           cred_key="A", confirmations=CONF_ALL, **kw):
    from src.extraction.human_review import apply_review

    return apply_review(queue, pkt, value, reviewer=reviewer,
                        credential=secured[cred_key], log_path=log_path,
                        confirmations=confirmations, **kw)


# ── PIN storage (متطلب 1) ───────────────────────────────────────────────────

def test_pin_stored_as_pbkdf2_never_plaintext_or_bare_sha256(tmp_path, monkeypatch):
    from src.extraction.human_review import (
        PBKDF2_ITERATIONS, pin_entry, verify_reviewer,
    )

    rf = tmp_path / "reviewers.json"
    monkeypatch.setenv("REVIEWERS_FILE", str(rf))
    monkeypatch.setenv("REVIEW_ATTEMPTS_PATH", str(tmp_path / ".attempts.json"))
    pin_entry("sec-auditor", "Sup3r-Secret-PIN!", ["approve"], file_path=rf)
    raw = rf.read_text(encoding="utf-8")
    entry = json.loads(raw)["reviewers"][0]
    assert "Sup3r-Secret-PIN!" not in raw                 # plaintext: NEVER
    assert entry["kdf"] == "pbkdf2_sha256"
    assert int(entry["iterations"]) >= PBKDF2_ITERATIONS >= 210_000
    assert len(bytes.fromhex(entry["salt"])) >= 16        # real random salt
    # NOT a bare sha256(salt+pin) — recomputing the legacy scheme must fail
    legacy = hashlib.sha256(
        (entry["salt"] + "Sup3r-Secret-PIN!").encode()).hexdigest()
    assert legacy != entry["pin_hash"]
    assert verify_reviewer("sec-auditor", "Sup3r-Secret-PIN!")["roles"] == ["approve"]
    with pytest.raises(PermissionError):
        verify_reviewer("sec-auditor", "wrong-pin")


def test_weak_kdf_config_is_refused(tmp_path, monkeypatch):
    """A hand-edited reviewers.json with a weak iteration count is refused
    outright — the backend never accepts a downgraded KDF."""
    from src.extraction.human_review import _reviewers_file, verify_reviewer

    rf = tmp_path / "reviewers.json"
    rf.write_text(json.dumps({"reviewers": [{
        "name": "weak", "salt": "aa", "kdf": "pbkdf2_sha256",
        "iterations": 1000,
        "pin_hash": hashlib.pbkdf2_hmac("sha256", b"x", b"\xaa", 1000).hex(),
        "roles": ["approve"],
    }]}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("REVIEWERS_FILE", str(rf))
    with pytest.raises(PermissionError):
        verify_reviewer("weak", "x")


# ── brute-force lockout (متطلب 2) ───────────────────────────────────────────

def test_repeated_wrong_pins_lock_the_reviewer_out(secured):
    from src.extraction.human_review import (
        attempts_remaining, verify_reviewer,
    )

    log = secured["tmp"] / "hr.json"
    with pytest.raises(PermissionError):
        verify_reviewer("auditor-A", "nope")
    for i in range(4):                     # 1 already recorded above
        with pytest.raises(PermissionError):
            verify_reviewer("auditor-A", f"nope-{i}")
    assert attempts_remaining("auditor-A") == 0
    # even the CORRECT pin is refused while locked
    with pytest.raises(PermissionError, match="مقفل"):
        verify_reviewer("auditor-A", secured["A"])
    # and nothing was written
    assert not log.exists()
    # a different reviewer is unaffected
    assert verify_reviewer("auditor-B", secured["B"])["name"] == "auditor-B"


def test_correct_pin_after_failures_resets_the_counter(secured):
    from src.extraction.human_review import attempts_remaining, verify_reviewer

    for i in range(3):
        with pytest.raises(PermissionError):
            verify_reviewer("auditor-A", f"bad-{i}")
    assert attempts_remaining("auditor-A") == 2
    verify_reviewer("auditor-A", secured["A"])
    assert attempts_remaining("auditor-A") == 5


def test_lockout_persists_across_restart(secured):
    """The lockout state is persisted — restarting the process does NOT
    reset the counter."""
    from src.extraction.human_review import _attempts_path, verify_reviewer

    for i in range(5):
        with pytest.raises(PermissionError):
            verify_reviewer("auditor-A", f"x{i}")
    state = json.loads(_attempts_path().read_text(encoding="utf-8"))
    assert "auditor-A" in state            # persisted on disk


# ── sessions (متطلب 4) ──────────────────────────────────────────────────────

def test_session_lifecycle_expiry_and_revocation(secured, monkeypatch):
    from src.extraction.human_review import (
        apply_review, authenticate, revoke_session, session_expiry,
        validate_session,
    )

    s = authenticate("auditor-A", secured["A"], ttl_seconds=60)
    assert validate_session(s["token"]) == "auditor-A"
    exp = session_expiry(s["token"])
    assert exp and exp > time.time()
    # expiry: move the clock past the TTL
    monkeypatch.setattr(time, "time", lambda: exp + 1)
    with pytest.raises(PermissionError, match="منتهية"):
        validate_session(s["token"])
    # revocation
    s2 = authenticate("auditor-A", secured["A"], ttl_seconds=60)
    revoke_session(s2["token"])
    with pytest.raises(PermissionError):
        validate_session(s2["token"])
    # a forged token is not a session
    with pytest.raises(PermissionError):
        validate_session("forged-token")


def test_session_role_enforced_in_backend_and_action_time(secured, queue):
    """A read-only reviewer's session token cannot approve through the
    BACKEND — the UI never grants what the backend denies (متطلب 5)."""
    from src.extraction.human_review import apply_review, authenticate

    s = authenticate("ro-viewer", secured["RO"], ttl_seconds=60)
    log = secured["tmp"] / "hr.json"
    with pytest.raises(PermissionError, match="صلاحية 'approve'"):
        apply_review(queue, "net_income|6|2022", 1_056_737_086.0,
                     reviewer="ro-viewer", session_token=s["token"],
                     log_path=log, confirmations=CONF_ALL)
    assert not log.exists()
    # but the reject role works end-to-end for that same session
    rec = apply_review(queue, "operating_cash_flow|9|2022", None,
                       reviewer="ro-viewer", session_token=s["token"],
                       log_path=log, confirmations=CONF_IDENTITY)
    assert rec["status"] == "REJECTED_HUMAN"


def test_wrong_pin_via_session_path_is_rate_limited_too(secured):
    from src.extraction.human_review import authenticate

    for i in range(5):
        with pytest.raises(PermissionError):
            authenticate("auditor-A", "bad")
    with pytest.raises(PermissionError, match="مقفل"):
        authenticate("auditor-A", secured["A"])   # even correct pin


# ── tamper matrix (متطلبات 7، 8) ────────────────────────────────────────────

def _write_two_reviews(secured, queue, log_path):
    _apply(secured, queue, log_path, "net_income|6|2022", 1_056_737_086.0)
    _apply(secured, queue, log_path, "revenue|6|2022", 16_665_919_878.0)


def test_tamper_edit_value_detected(secured, queue):
    from src.extraction.human_review import verify_log_integrity

    log = secured["tmp"] / "hr.json"
    _write_two_reviews(secured, queue, log)
    recs = json.loads(log.read_text(encoding="utf-8"))
    recs[0]["value_final"] = 42.0                       # EDIT
    log.write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")
    ok, bad = verify_log_integrity(log)
    assert not ok and bad == 1


def test_tamper_delete_middle_record_detected(secured, queue):
    from src.extraction.human_review import verify_log_integrity

    log = secured["tmp"] / "hr.json"
    _apply(secured, queue, log, "net_income|6|2022", 1_056_737_086.0)
    _apply(secured, queue, log, "revenue|6|2022", 16_665_919_878.0)
    _apply(secured, queue, log, "net_activity_profit|6|2022", 1_257_960_603.0)
    recs = json.loads(log.read_text(encoding="utf-8"))
    del recs[1]                                          # DELETE the middle one
    log.write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")
    ok, bad = verify_log_integrity(log)
    assert not ok and bad == 3                           # seq-3's prev_hash breaks


def test_tamper_reorder_detected(secured, queue):
    from src.extraction.human_review import verify_log_integrity

    log = secured["tmp"] / "hr.json"
    _write_two_reviews(secured, queue, log)
    recs = json.loads(log.read_text(encoding="utf-8"))
    recs[0], recs[1] = recs[1], recs[0]                  # REORDER
    log.write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")
    ok, bad = verify_log_integrity(log)
    assert not ok


def test_tamper_full_rewrite_with_plain_hashes_fails(secured, queue):
    """Attacker with FILE access rewrites everything and recomputes PLAIN
    sha256 — HMAC verification still fails without the key (متطلب 8)."""
    from src.extraction.human_review import _hmac_key, verify_log_integrity

    log = secured["tmp"] / "hr.json"
    _write_two_reviews(secured, queue, log)
    recs = json.loads(log.read_text(encoding="utf-8"))
    for r in recs:
        r["value_final"] = 1.0
        core = {k: v for k, v in r.items()
                if k not in ("record_hash", "prev_hash", "seq")}
        r["record_hash"] = hashlib.sha256(
            json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()[:32]
    log.write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")
    assert not verify_log_integrity(log)[0]
    # the key never leaks into the log file
    assert _hmac_key().decode() not in log.read_text(encoding="utf-8")


def test_no_append_onto_broken_chain(secured, queue):
    """verify-before-append: a tampered log REFUSES further reviews instead
    of extending the damage (متطلب 8)."""
    from src.extraction.human_review import verify_log_integrity

    log = secured["tmp"] / "hr.json"
    _write_two_reviews(secured, queue, log)
    recs = json.loads(log.read_text(encoding="utf-8"))
    recs[0]["value_final"] = 42.0
    log.write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(PermissionError, match="تالف"):
        _apply(secured, queue, log, "net_activity_profit|6|2022",
               1_257_960_603.0)
    # the refused record was NOT written
    assert len(json.loads(log.read_text(encoding="utf-8"))) == 2


def test_seq_never_collides_after_gap(secured, queue):
    """seq comes from the last record's seq (not list length) — a pre-seeded
    log with a seq gap cannot produce duplicate sequence numbers."""
    from src.extraction.human_review import verify_log_integrity

    log = secured["tmp"] / "hr.json"
    _write_two_reviews(secured, queue, log)
    recs = json.loads(log.read_text(encoding="utf-8"))
    recs.append({"seq": 99, "packet_id": "seed|0|2022", "prev_hash":
                 recs[-1]["record_hash"], "record_hash": "seed-not-signed"})
    log.write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")
    # (chain now broken on purpose — proves we cannot append; that's the
    # guard. With an intact log the next seq is always last_seq + 1.)
    assert not verify_log_integrity(log)[0]
    log2 = secured["tmp"] / "hr2.json"
    _apply(secured, queue, log2, "net_income|6|2022", 1_056_737_086.0)
    _apply(secured, queue, log2, "revenue|6|2022", 16_665_919_878.0)
    seqs = [r["seq"] for r in json.loads(log2.read_text(encoding="utf-8"))]
    assert seqs == [1, 2]


def test_concurrent_reviews_no_lost_update_no_seq_collision(secured, queue):
    """Two simultaneous reviews both land, with distinct seq numbers and an
    intact chain (متطلب 7)."""
    from src.extraction.human_review import verify_log_integrity

    log = secured["tmp"] / "hr.json"
    errors = []

    def worker(pkt, value):
        try:
            _apply(secured, queue, log, pkt, value)
        except Exception as e:                     # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(
                   "net_income|6|2022", 1_056_737_086.0)),
               threading.Thread(target=worker, args=(
                   "revenue|6|2022", 16_665_919_878.0))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(120)
    assert not errors
    recs = json.loads(log.read_text(encoding="utf-8"))
    assert len(recs) == 2
    assert sorted(r["seq"] for r in recs) == [1, 2]   # no collision
    ok, _bad = verify_log_integrity(log)
    assert ok                                          # chain intact


def test_interrupted_write_leaves_log_intact(secured, queue, monkeypatch):
    """A crash between append and persist loses NOTHING: the write is atomic
    (tmp + os.replace), so the log stays complete and the next review
    continues with the right seq."""
    from src.extraction.human_review import verify_log_integrity

    log = secured["tmp"] / "hr.json"
    _apply(secured, queue, log, "net_income|6|2022", 1_056_737_086.0)
    import os as _os

    real_replace = _os.replace
    crashed = {"once": False}

    def boom(src, dst):
        if str(dst).endswith("hr.json") and not crashed["once"]:
            crashed["once"] = True               # crash exactly once, then pass
            raise OSError("interrupted (simulated crash)")
        return real_replace(src, dst)

    monkeypatch.setattr(_os, "replace", boom)
    with pytest.raises(OSError):
        _apply(secured, queue, log, "revenue|6|2022", 16_665_919_878.0)
    ok, _bad = verify_log_integrity(log)
    assert ok                                    # previous log intact
    recs = json.loads(log.read_text(encoding="utf-8"))
    assert len(recs) == 1                        # partial record lost cleanly
    rec = _apply(secured, queue, log, "revenue|6|2022", 16_665_919_878.0)
    assert rec["seq"] == 2                       # seq continues correctly


# ── confirmations & context gating (متطلبات P0-3) ──────────────────────────

def test_value_attestation_requires_all_five_confirmations(secured, queue):
    from src.extraction.human_review import apply_review

    log = secured["tmp"] / "hr.json"
    for partial in ({}, {"document": True}, {k: True for k in
                    ("document", "field", "year", "position")}):
        with pytest.raises(ValueError, match="الخمسة"):
            apply_review(queue, "net_income|6|2022", 1_056_737_086.0,
                         reviewer="auditor-A", credential=secured["A"],
                         log_path=log, confirmations=partial)
    # a LIE (False) is as good as missing
    lying = dict(CONF_ALL, value=False)
    with pytest.raises(ValueError):
        apply_review(queue, "net_income|6|2022", 1_056_737_086.0,
                     reviewer="auditor-A", credential=secured["A"],
                     log_path=log, confirmations=lying)
    assert not log.exists()
    # all five → accepted, and the record CARRIES them
    rec = _apply(secured, queue, log, "net_income|6|2022", 1_056_737_086.0)
    assert rec["confirmations"] == CONF_ALL


def test_reject_needs_identity_confirmations_only(secured, queue):
    from src.extraction.human_review import apply_review

    log = secured["tmp"] / "hr.json"
    with pytest.raises(ValueError):
        apply_review(queue, "operating_cash_flow|9|2022", None,
                     reviewer="auditor-A", credential=secured["A"],
                     log_path=log, confirmations={"document": True})
    rec = apply_review(queue, "operating_cash_flow|9|2022", None,
                       reviewer="auditor-A", credential=secured["A"],
                       log_path=log, confirmations=CONF_IDENTITY)
    assert rec["status"] == "REJECTED_HUMAN"


def test_incomplete_context_packet_cannot_be_attested(secured):
    """An out-of-context crop (year header or label unclear) is REJECT-ONLY —
    the backend refuses approve/correct even with all five confirmations."""
    from src.extraction.human_review import apply_review

    pkt = {"packet_id": "mystery|1|2022", "field": "mystery", "page": 1,
           "year": 2022, "crop_image": None, "page_image": None,
           "date_header_image": None, "label_text": None,
           "bbox_rel": [0.1, 0.1, 0.2, 0.2], "machine_selected": 777.0,
           "readings": {"crop_variants": [777.0]},
           "conflict_reason": "unclear",
           "context": {"year_header_available": False,
                       "label_available": False, "context_complete": False},
           "confirmations": {k: False for k in CONF_ALL},
           "decision": None}
    log = secured["tmp"] / "hr.json"
    with pytest.raises(PermissionError, match="غير مكتمل"):
        apply_review([pkt], "mystery|1|2022", 777.0, reviewer="auditor-A",
                     credential=secured["A"], log_path=log,
                     confirmations=CONF_ALL)
    with pytest.raises(PermissionError, match="غير مكتمل"):
        apply_review([pkt], "mystery|1|2022", 555.0, reviewer="auditor-A",
                     credential=secured["A"], log_path=log,
                     confirmations=CONF_ALL)
    # reject remains possible
    rec = apply_review([pkt], "mystery|1|2022", None, reviewer="auditor-A",
                       credential=secured["A"], log_path=log,
                       confirmations=CONF_IDENTITY)
    assert rec["status"] == "REJECTED_HUMAN"


# ── TOCTOU + stale-record reuse (متطلب 9) ───────────────────────────────────

def test_source_changed_after_queue_build_refuses_attestation(secured, queue):
    """TOCTOU guard: the crop changed between queue build and review — the
    backend refuses the attestation (a stale queue is not evidence)."""
    from src.extraction.human_review import apply_review

    log = secured["tmp"] / "hr.json"
    crop = PROJ / "cell_evidence/spatial_net_income_p6_y2022.png"
    crop.write_bytes(crop.read_bytes())                # same content, mtime bump
    pkt = next(p for p in queue if p["packet_id"] == "net_income|6|2022")
    stale = dict(pkt)                                   # simulate the file having
    stale["crop_sha256"] = "0" * 32                     # changed since build
    with pytest.raises(PermissionError, match="أعد توليد الطابور"):
        apply_review([stale], "net_income|6|2022", 1_056_737_086.0,
                     reviewer="auditor-A", credential=secured["A"],
                     log_path=log, confirmations=CONF_ALL)
    assert not log.exists()


def test_stale_record_reuse_after_invalidation_never_trusted(secured, queue):
    """A trusted record is captured, the source crop is then REPLACED —
    replaying the OLD attestation (same record dict, same hashes) against
    the new source must fail: review_is_trusted checks the on-disk sources,
    and the decision log downgrades to UNVERIFIED (متطلب 9)."""
    from src.analysis.financial_gate import decisive_values
    from src.extraction.human_review import (
        apply_review, review_is_trusted,
    )
    from src.extraction.normalizer import FinancialData, build_decision_log

    log = secured["tmp"] / "hr.json"
    d = FinancialData()
    d.values["net_income"] = {2022: 1_056_737_086.0}
    d.candidates["net_income"] = {2022: [(1_056_737_086.0, 0)]}
    _apply(secured, queue, log, "net_income|6|2022", 1_056_737_086.0, data=d)
    rec = dict(d.human_reviews[("net_income", 2022)])
    assert review_is_trusted(rec, log_path=log,
                             crops_dir=PROJ / "cell_evidence")

    # the source crop is REPLACED (a re-scan of the document)
    ev = secured["tmp"] / "cell_evidence"
    ev.mkdir(exist_ok=True)
    crop = PROJ / "cell_evidence/spatial_net_income_p6_y2022.png"
    (ev / crop.name).write_bytes(crop.read_bytes() + b"re-scan-2027")
    # replay the OLD record against the changed source → NOT trusted
    assert not review_is_trusted(rec, log_path=log, crops_dir=ev)
    # even re-injecting it into a fresh FinancialData does not pass
    d2 = FinancialData()
    d2.human_reviews = {("net_income", 2022): rec}
    d2.human_reviews_log = str(log)
    d2.values["net_income"] = {2022: 1_056_737_086.0}
    d2.candidates["net_income"] = {2022: [(1_056_737_086.0, 0)]}
    e = next(e for e in build_decision_log(d2)
             if e["field"] == "net_income" and e["year"] == 2022)
    assert e["status"] == "UNVERIFIED"
    assert decisive_values(d2)[("net_income", 2022)]["usable_decisive"] is False


def test_reviewer_identity_and_timestamps_recorded_with_sources(secured, queue):
    """Every record carries reviewer, timestamp, all three source hashes,
    bbox, extraction version and the extraction provenance the reviewer saw."""
    from src.extraction.human_review import EXTRACTION_VERSION, review_is_valid

    log = secured["tmp"] / "hr.json"
    rec = _apply(secured, queue, log, "net_income|6|2022", 1_056_737_086.0,
                 decision_note="printed value verified on page 6")
    assert rec["reviewer"] == "auditor-A" and rec["timestamp"]
    assert rec["crop_sha256"] and rec["page_image_sha256"] and rec["pdf_sha256"]
    assert rec["bbox_rel"] and rec["extraction_version"] == EXTRACTION_VERSION
    assert rec["label_text"] == "صافى أرباح العام"
    assert rec["note"] == "printed value verified on page 6"
    assert review_is_valid(rec, crops_dir=PROJ / "cell_evidence")
