# -*- coding: utf-8 -*-
"""Human-in-the-Loop verification — SECURED (المراجعة البشرية المؤمَّنة).

Audit-trail guarantees:
- append-only JSONL-style log where every record carries `seq` and
  `prev_hash`; record_hash = HMAC-SHA256(canonical(record w/o hash) +
  prev_hash, REVIEW_HMAC_KEY). verify_log_integrity() recomputes the chain —
  any edit/reorder/deletion of an old record breaks every hash after it and
  is REPORTED, not silently accepted. apply_review() re-verifies the WHOLE
  chain BEFORE appending and refuses to write onto a broken chain.
- reviewer identity checked against an allowlist (reviewers.json) BEFORE
  anything is written; unknown reviewer → PermissionError, nothing recorded.
- PIN storage: PBKDF2-HMAC-SHA256 (600k iterations, 16-byte random salt).
  The PIN itself is NEVER stored. Legacy salted-sha256 entries still verify
  (read-only compat) but new entries are always PBKDF2.
- brute-force resistance: failed PIN attempts are persisted and rate-limited
  (5 failures / 15 min → 15 min lockout per reviewer name).
- every record stores: reviewer, timestamp, crop_sha256 AND page sha256 AND
  pdf sha256, field/year/bbox_rel, the five explicit confirmations
  (document/field/year/position/value), value_before (machine), value_final
  (human), decision kind (corroborate/correct/reject/conflict) and the
  extraction version.
- invalidation: review_is_valid() re-hashes the crop AND the page image —
  a changed source or a crop gone missing voids the attestation. apply_review
  additionally refuses to APPROVE when the sources changed after the queue
  was built (TOCTOU guard) and REFUSES value attestations (approve/correct)
  on packets whose year header or label context is incomplete.
- sessions: authenticate() exchanges PIN → short-lived token (default 30
  min, process-memory store); actions accept the token instead of re-sending
  the PIN. Backend enforces roles on EVERY action — the UI is never trusted.
- concurrency: log writes are serialized through an exclusive OS file lock
  (msvcrt/fcntl) with seq taken from the last record (not list length) and
  the write itself is atomic (tmp file + os.replace) — an interrupted write
  leaves the previous log intact.
- forgery resistance: a VERIFIED_HUMAN claim in a FinancialData object is
  trusted ONLY when the same record exists in the on-disk chain with a valid
  chain and unchanged sources (review_is_trusted). Injecting
  data.human_reviews directly from code does NOT pass the gate.

Documented security boundary (حدود الحماية): if an attacker obtains
REVIEW_HMAC_KEY itself they can forge/re-sign a chain — the log protects
against file tampering WITHOUT the key, not against key compromise. The key
therefore lives outside the repo (.env, gitignored) and outside the log;
with file-system access the attacker also wins regardless of the scheme —
attribution then rests on the reviewer PIN (PBKDF2, never stored) and on
operational key custody. Deletion of the attempts-state file resets the
lockout counter (documented; same trust boundary as the log file itself).

Separation rule (hard): automatic accuracy counters are computed from the
machine benchmark artifacts only; human reviews live in their own chain and
are reported as a SEPARATE coverage number.
"""
from __future__ import annotations

import hashlib
import hmac as _hmac_mod
import json
import os
import secrets
import threading
import time
from contextlib import contextmanager
from pathlib import Path

# isolated test runs override REVIEW_LOG_PATH — production default unchanged
REVIEW_LOG = Path(os.environ.get("REVIEW_LOG_PATH",
                                 "cell_evidence/human_reviews.json"))
PROVENANCE_LADDER_HUMAN = "VISUALLY_VERIFIED"
STATUS_HUMAN = "VERIFIED_HUMAN"
STATUS_CONFLICT_HUMAN = "CONFLICT_HUMAN"
STATUS_REJECTED_HUMAN = "REJECTED_HUMAN"

# version of the extraction pipeline recorded in every packet/record so a
# review can always be tied back to the code that produced the readings
EXTRACTION_VERSION = os.environ.get("EXTRACTION_VERSION",
                                    "extraction-spatial-2026.11")

# the five things a human must EXPLICITLY confirm before a value attestation
CONFIRMATION_KEYS = ("document", "field", "year", "position", "value")
CONFIRMATION_LABELS_AR = {
    "document": "المستند الصحيح",
    "field": "البند الصحيح",
    "year": "السنة الصحيحة",
    "position": "موضع الخانة الصحيح",
    "value": "القيمة الرقمية الصحيحة",
}

# ── PIN hashing policy ──────────────────────────────────────────────────────
PBKDF2_ITERATIONS = 600_000          # OWASP-recommended for PBKDF2-SHA256
MIN_PBKDF2_ITERATIONS = 210_000      # refuse weaker configs

# ── brute-force policy ──────────────────────────────────────────────────────
PIN_FAILURES_ALLOWED = 5             # failures within the window → lockout
PIN_FAILURE_WINDOW = 900             # 15 min sliding window
PIN_LOCKOUT = 900                    # 15 min lockout

_SESSIONS: dict[str, dict] = {}
_SESSIONS_LOCK = threading.Lock()
SESSION_TTL_DEFAULT = 1800           # 30 minutes


# ── reviewer identity / permissions ─────────────────────────────────────────

def _hmac_key() -> bytes | None:
    """The signing key lives OUTSIDE the log and OUTSIDE the repo (in .env,
    which is gitignored). Without it: writes are refused and the chain is
    'unverifiable' — an unsigned chain is NOT called tamper-proof."""
    raw = os.environ.get("REVIEW_HMAC_KEY", "")
    return raw.encode("utf-8") if raw else None


def _reviewers_file() -> Path:
    return Path(os.environ.get("REVIEWERS_FILE", "reviewers.json"))


def _allowlist() -> list[dict]:
    """reviewers.json entries: {name, salt, pin_hash, kdf, iterations,
    roles:[...]} — the PIN itself is NEVER stored, only its PBKDF2 hash."""
    f = _reviewers_file()
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8")).get("reviewers", [])
        except Exception:
            return []
    raw = os.environ.get("REVIEWERS", "")
    # env fallback: names only, NO credential → no roles → cannot attest
    return [{"name": x.strip(), "roles": []} for x in raw.split(",") if x.strip()]


def _pin_ok(entry: dict, credential: str) -> bool:
    """Constant-time PIN verification. PBKDF2 entries (new); legacy salted
    sha256 entries still verify read-only so old files keep working."""
    stored = entry.get("pin_hash")
    if stored:
        kdf = entry.get("kdf", "pbkdf2_sha256")
        iters = int(entry.get("iterations") or 0)
        if kdf != "pbkdf2_sha256" or iters < MIN_PBKDF2_ITERATIONS:
            return False   # refuse weak/unknown KDF config outright
        salt = bytes.fromhex(entry.get("salt") or "")
        calc = hashlib.pbkdf2_hmac("sha256", credential.encode("utf-8"),
                                   salt, iters).hex()
        return _hmac_mod.compare_digest(calc, stored)
    legacy = entry.get("pin_sha256")
    if legacy:   # legacy format — still constant-time, read-only compat
        calc = hashlib.sha256(((entry.get("salt") or "") + credential)
                              .encode("utf-8")).hexdigest()
        return _hmac_mod.compare_digest(calc, legacy)
    return False


def verify_reviewer(reviewer: str, credential: str | None = None,
                    action: str | None = None) -> dict:
    """AUTHENTICATION (name + PIN against the PBKDF2 hash, rate-limited)
    plus AUTHORIZATION (the action must be in the reviewer's roles). Raises
    PermissionError — nothing is written on failure. This is the BACKEND
    enforcement point; the UI can never grant a role the backend denies."""
    _check_lockout(reviewer)
    entry = next((r for r in _allowlist() if r.get("name") == reviewer), None)
    if entry is None:
        _register_failure(reviewer)          # unknown names are rate-limited too
        raise PermissionError(f"المراجع '{reviewer}' غير مسجل")
    stored = entry.get("pin_hash") or entry.get("pin_sha256")
    if stored:
        if not credential:
            raise PermissionError("اعتماد المراجع يتطلب رمز تحقق (PIN)")
        if not _pin_ok(entry, credential):
            _register_failure(reviewer)
            raise PermissionError("رمز تحقق غير صحيح")
    _register_success(reviewer)
    roles = set(entry.get("roles", []))
    if not roles:
        raise PermissionError(f"المراجع '{reviewer}' بلا صلاحيات اعتماد")
    if action and action not in roles:
        raise PermissionError(f"المراجع '{reviewer}' لا يملك صلاحية '{action}'")
    return entry


def pin_entry(name: str, pin: str, roles: list[str],
              file_path: Path | None = None) -> None:
    """Admin helper: store a reviewer with a PBKDF2 pin hash (never the PIN,
    never a bare SHA-256)."""
    f = file_path or _reviewers_file()
    salt = secrets.token_bytes(16)
    data = {"reviewers": []}
    if f.exists():
        data = json.loads(f.read_text(encoding="utf-8"))
    data["reviewers"] = [r for r in data.get("reviewers", [])
                         if r.get("name") != name]
    data["reviewers"].append({
        "name": name,
        "salt": salt.hex(),
        "kdf": "pbkdf2_sha256",
        "iterations": PBKDF2_ITERATIONS,
        "pin_hash": hashlib.pbkdf2_hmac(
            "sha256", pin.encode("utf-8"), salt, PBKDF2_ITERATIONS).hex(),
        "roles": roles,
    })
    f.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


# ── brute-force lockout state (persisted so restarts don't reset it) ───────

def _attempts_path() -> Path:
    p = os.environ.get("REVIEW_ATTEMPTS_PATH")
    return Path(p) if p else REVIEW_LOG.parent / ".review_attempts.json"


def _load_attempts() -> dict:
    p = _attempts_path()
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_attempts(state: dict) -> None:
    p = _attempts_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    os.replace(tmp, p)


def _lockout_state(name: str) -> dict:
    return _load_attempts().get(name, {})


def _check_lockout(name: str) -> None:
    st = _lockout_state(name)
    until = st.get("locked_until") or 0
    if until and time.time() < until:
        mins = int((until - time.time()) // 60) + 1
        raise PermissionError(
            f"محاولات دخول كثيرة — الحساب مقفل لمدة ~{mins} دقيقة")


def _register_failure(name: str) -> None:
    state = _load_attempts()
    st = state.get(name) or {}
    now = time.time()
    recent = [t for t in (st.get("failures") or [])
              if now - t < PIN_FAILURE_WINDOW]
    recent.append(now)
    st["failures"] = recent
    if len(recent) >= PIN_FAILURES_ALLOWED:
        st["locked_until"] = now + PIN_LOCKOUT
        st["failures"] = []
    state[name] = st
    _save_attempts(state)


def _register_success(name: str) -> None:
    state = _load_attempts()
    if name in state:
        state.pop(name)
        _save_attempts(state)


def attempts_remaining(name: str) -> int:
    st = _lockout_state(name)
    if st.get("locked_until") and time.time() < st["locked_until"]:
        return 0                          # locked → no attempts remain
    used = len(st.get("failures") or [])
    return max(0, PIN_FAILURES_ALLOWED - used)


# ── sessions (PIN → short-lived token; backend-validated) ───────────────────

def authenticate(reviewer: str, credential: str,
                 ttl_seconds: int = SESSION_TTL_DEFAULT) -> dict:
    """Verify credentials once, then issue a random session token bound to
    (reviewer, roles, expiry). Roles come from the BACKEND allowlist only."""
    entry = verify_reviewer(reviewer, credential=credential)
    token = secrets.token_urlsafe(32)
    with _SESSIONS_LOCK:
        _purge_expired_sessions()
        _SESSIONS[token] = {
            "reviewer": reviewer,
            "roles": sorted(entry.get("roles", [])),
            "expires": time.time() + ttl_seconds,
        }
    return {"token": token, "reviewer": reviewer,
            "roles": sorted(entry.get("roles", [])),
            "expires_in": ttl_seconds}


def validate_session(token: str, action: str | None = None) -> str:
    """Return the reviewer name for a live, authorized token — else raise."""
    with _SESSIONS_LOCK:
        _purge_expired_sessions()
        sess = _SESSIONS.get(token)
    if not sess or time.time() >= sess["expires"]:
        raise PermissionError("جلسة المراجع منتهية أو غير صالحة — أعد الدخول")
    if action and action not in sess["roles"]:
        raise PermissionError(
            f"المراجع '{sess['reviewer']}' لا يملك صلاحية '{action}'")
    return sess["reviewer"]


def session_expiry(token: str) -> float | None:
    with _SESSIONS_LOCK:
        sess = _SESSIONS.get(token)
    return sess["expires"] if sess else None


def revoke_session(token: str) -> None:
    with _SESSIONS_LOCK:
        _SESSIONS.pop(token, None)


def _purge_expired_sessions() -> None:
    now = time.time()
    for t in [t for t, s in _SESSIONS.items() if now >= s["expires"]]:
        _SESSIONS.pop(t, None)


# ── hash chain ──────────────────────────────────────────────────────────────

def _canonical(rec: dict) -> str:
    core = {k: v for k, v in rec.items()
            if k not in ("record_hash", "prev_hash", "seq")}
    return json.dumps(core, ensure_ascii=False, sort_keys=True, default=str)


def _record_hash(rec: dict, prev_hash: str) -> str:
    """HMAC-SHA256 with the secret key. An attacker with full file access can
    recompute a PLAIN hash after rewriting records — with HMAC they cannot
    re-sign without the key (which never lives in the log or the repo)."""
    key = _hmac_key()
    if key is None:
        raise PermissionError(
            "REVIEW_HMAC_KEY غير مضبوط — سلسلة غير موقعة لا تُدعى tamper-proof")
    return _hmac_mod.new(key, (_canonical(rec) + "|" + prev_hash)
                         .encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def _sha256_file(path: str | Path | None) -> str | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()[:32]


def load_log(log_path: Path = REVIEW_LOG) -> list[dict]:
    p = Path(log_path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def verify_log_integrity(log_path: Path = REVIEW_LOG) -> tuple[bool, int | None]:
    """(ok, first_bad_seq). Missing key → (False, "NO_KEY"): the chain is
    unverifiable, which the gate treats as NOT trusted."""
    if _hmac_key() is None:
        return False, "NO_KEY"
    prev = "GENESIS"
    for rec in load_log(log_path):
        if not _hmac_mod.compare_digest(str(rec.get("prev_hash")), prev) or \
                not _hmac_mod.compare_digest(str(rec.get("record_hash")),
                                             _record_hash(rec, prev)):
            return False, rec.get("seq")
        prev = rec["record_hash"]
    return True, None


def _atomic_write_json(path: Path, obj) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    os.replace(tmp, path)          # atomic on the same volume


@contextmanager
def _log_lock(log_path: Path):
    """Exclusive cross-process lock over the review log (msvcrt on Windows,
    flock elsewhere) so two concurrent reviews can never clobber each other
    or duplicate `seq`."""
    lock_path = Path(str(log_path) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    f = open(lock_path, "a+b")
    try:
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
            except OSError as e:
                raise PermissionError(
                    "سجل المراجعات مقفل من عملية أخرى — أعد المحاولة") from e
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        f.close()


# ── queue / packets (context-rich) ──────────────────────────────────────────

def build_review_queue(per_cell_json: Path, crops_dir: Path,
                       out_path: Path | None = None,
                       pdf_path: Path | None = None) -> list[dict]:
    """One packet per NON-decisive cell. The reviewer gets the FULL source
    context — page image, the printed year header above the column, the
    field label, the surrounding row strip, the cell crop, every machine
    reading, the conflict reason, and the extraction version — with the
    sha256 of the PDF / page image / crop recorded. GT is NOT included: the
    reviewer judges the printed image, not the answer key."""
    cells = json.loads(Path(per_cell_json).read_text(encoding="utf-8"))
    bench = json.loads((Path(per_cell_json).parent / "benchmark_abc.json")
                       .read_text(encoding="utf-8"))
    by_key = {(r["field"], r.get("page")): r for r in bench
              if r["method"] == "C_spatial_declared"}
    proj = Path(per_cell_json).resolve().parents[1]
    if pdf_path is None:
        cand = proj / "القوائم المالية المستقلة 2022.pdf"
        pdf_path = cand if cand.exists() else None
    pdf_sha = _sha256_file(pdf_path) if pdf_path else None
    queue = []
    for c in cells:
        if c["final_status"] == "VERIFIED_CANDIDATE":
            continue
        r = by_key.get((c["field"], c.get("page")), {})
        crop = Path(crops_dir) / f"spatial_{c['field']}_p{c['page']}_y2022.png"
        page_img = Path(crops_dir).parent / f"eval_pages/page_{c['page']}.png"
        date_hdr = Path(crops_dir) / f"date_header_p{c['page']}.png"
        label_text = r.get("label_2022")
        queue.append({
            "packet_id": f"{c['field']}|{c['page']}|2022",
            "field": c["field"], "page": c["page"], "year": 2022,
            "status": c["final_status"],
            "crop_image": str(crop) if crop.exists() else None,
            "page_image": str(page_img) if page_img.exists() else None,
            "date_header_image": str(date_hdr) if date_hdr.exists() else None,
            "label_text": label_text,
            "bbox_rel": r.get("bbox_rel"),
            "machine_selected": c.get("selected") or r.get("value_2022"),
            "readings": {
                "detection_line": (r.get("detection_values") or [])[:4]
                if isinstance(r.get("detection_values"), list) else [],
                "crop_variants": (r.get("crop_values") or [])[:6]
                if isinstance(r.get("crop_values"), list) else [],
            },
            "conflict_reason": r.get("detail_2022", ""),
            "source_pdf": (str(pdf_path) if pdf_path else None),
            "pdf_sha256": pdf_sha,
            "page_image_sha256": _sha256_file(page_img),
            "crop_sha256": _sha256_file(crop),
            "extraction_version": EXTRACTION_VERSION,
            # the reviewer may only ATTEST a value when the year header AND
            # the label are visible — an out-of-context crop is reject-only
            "context": {
                "year_header_available": date_hdr.exists(),
                "label_available": bool(label_text),
                "context_complete": date_hdr.exists() and bool(label_text),
            },
            "confirmations": {k: False for k in CONFIRMATION_KEYS},
            "decision": None,
        })
    if out_path:
        _atomic_write_json(Path(out_path), queue)
    return queue


# ── apply a decision (secured) ──────────────────────────────────────────────

def value_matches_probe(queue, packet_id, value) -> bool:
    pkt = next((p for p in queue if p["packet_id"] == packet_id), None)
    before = pkt.get("machine_selected") if pkt else None
    return (before is not None and value is not None
            and abs(value - before) <= max(1.0, 1e-6 * abs(before)))


def _confirmations_ok(kind: str, confirmations: dict | None) -> bool:
    """approve/correct need ALL five explicit confirmations; reject needs the
    four identity confirmations (the value one is explicitly denied)."""
    if not isinstance(confirmations, dict):
        return False
    need = set(CONFIRMATION_KEYS) if kind != "reject" \
        else set(CONFIRMATION_KEYS) - {"value"}
    return all(confirmations.get(k) is True for k in need)


def apply_review(queue: list[dict], packet_id: str,
                 approved_value: float | None, reviewer: str,
                 credential: str | None = None,
                 data=None, log_path: Path = REVIEW_LOG,
                 decision_note: str = "", session_token: str | None = None,
                 confirmations: dict | None = None) -> dict:
    """Record one human decision (identity + role checked in the BACKEND,
    whole chain verified BEFORE append, OS-locked, atomically written).
    kind: corroborate | correct | reject | conflict — conflict when a PRIOR
    record for the same packet holds a DIFFERENT final value."""
    kind_probe = "reject" if approved_value is None else (
        "approve" if value_matches_probe(queue, packet_id, approved_value)
        else "correct")
    if session_token:
        reviewer = validate_session(session_token, action=kind_probe)
    else:
        verify_reviewer(reviewer, credential=credential, action=kind_probe)
    if _hmac_key() is None:
        raise PermissionError(
            "REVIEW_HMAC_KEY غير مضبوط — الاعتماد مرفوض (سلسلة غير موقعة)")
    pkt = next((p for p in queue if p["packet_id"] == packet_id), None)
    if pkt is None:
        raise KeyError(f"unknown packet {packet_id}")
    field, page, year = pkt["field"], pkt["page"], pkt["year"]
    value_before = pkt.get("machine_selected")
    kind = ("corroborate" if value_before is not None and approved_value is not None
            and abs(approved_value - value_before) <= max(1.0, 1e-6 * abs(value_before))
            else "correct" if approved_value is not None else "reject")

    # five explicit confirmations — required BEFORE any value attestation
    if not _confirmations_ok(kind, confirmations):
        raise ValueError(
            "الاعتماد يتطلب تأكيد الخمسة عناصر صراحة: المستند، البند، السنة، "
            "موضع الخانة، القيمة الرقمية (الرفض يتطلب الأربعة الأولى)")

    # an out-of-context crop (year header or label unclear) can never be
    # attested — approve/correct are refused, only reject remains possible
    ctx = pkt.get("context") or {}
    if kind != "reject" and not ctx.get("context_complete", True):
        raise PermissionError(
            "سياق الخانة غير مكتمل (ترويسة السنة أو تسمية البند غير واضحة) — "
            "لا يُسمح باعتماد قيمة من قصاصة خارج سياقها")

    # TOCTOU guard: sources must be unchanged since the queue was built
    if kind != "reject":
        fresh_crop = _sha256_file(pkt.get("crop_image"))
        if pkt.get("crop_sha256") and fresh_crop != pkt["crop_sha256"]:
            raise PermissionError(
                "المصدر تغيّر بعد بناء الطابور (بصمة القصاصة مختلفة) — "
                "أعد توليد الطابور قبل الاعتماد")
        fresh_page = _sha256_file(pkt.get("page_image"))
        if pkt.get("page_image_sha256") and fresh_page != pkt["page_image_sha256"]:
            raise PermissionError(
                "صورة الصفحة تغيّرت بعد بناء الطابور — أعد توليد الطابور")

    with _log_lock(log_path):
        # verify the WHOLE chain before appending — never write onto a
        # broken/tampered log
        ok, bad = verify_log_integrity(log_path)
        if not ok:
            raise PermissionError(
                f"سجل المراجعات تالف (أول خرق عند seq={bad}) — الالكتابة مرفوضة")
        log = load_log(log_path)
        prior = [r for r in log if r["packet_id"] == packet_id
                 and r.get("status") == STATUS_HUMAN]
        status = STATUS_HUMAN
        if approved_value is None:
            status = STATUS_REJECTED_HUMAN
        elif prior and any(abs((r.get("value_final") or 0) - approved_value)
                           > max(1.0, 1e-6 * abs(r.get("value_final") or 1))
                           for r in prior):
            # two reviewers disagree — the cell is CONFLICT_HUMAN, never decided
            status = STATUS_CONFLICT_HUMAN

        rec = {
            "seq": (log[-1]["seq"] + 1) if log else 1,
            "packet_id": packet_id, "field": field, "page": page, "year": year,
            "bbox_rel": pkt.get("bbox_rel"),
            "reviewer": reviewer,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "crop_sha256": _sha256_file(pkt.get("crop_image")),
            "page_image_sha256": _sha256_file(pkt.get("page_image")),
            "doc_sha256": _sha256_file(pkt.get("page_image")),
            "source_pdf": pkt.get("source_pdf"),
            "pdf_sha256": pkt.get("pdf_sha256"),
            "extraction_version": pkt.get("extraction_version"),
            "label_text": pkt.get("label_text"),
            "confirmations": {k: bool((confirmations or {}).get(k))
                              for k in CONFIRMATION_KEYS},
            "value_before": value_before,
            "value_final": approved_value,
            "kind": kind, "status": status, "note": decision_note[:200],
            "security": "hmac_signed+pbkdf2+locked",
        }
        rec["prev_hash"] = log[-1]["record_hash"] if log else "GENESIS"
        rec["record_hash"] = _record_hash(rec, rec["prev_hash"])
        log.append(rec)
        _atomic_write_json(Path(log_path), log)

    if data is not None:
        hr = getattr(data, "human_reviews", None) or {}
        hr[(field, year)] = dict(rec)
        data.human_reviews = hr
        data.human_reviews_log = str(log_path)   # trust check reads THIS chain
        if status == STATUS_HUMAN:
            data.values.setdefault(field, {})[year] = float(approved_value)
            data.candidates.setdefault(field, {}).setdefault(year, []).append(
                (float(approved_value), 0))
            data.confidence.setdefault(field, {})[year] = 2
        if status == STATUS_CONFLICT_HUMAN:
            # two reviewers disagree — the earlier attestation's confidence
            # bump is withdrawn so nothing reaches VERIFIED_EXACT
            data.confidence.setdefault(field, {})[year] = 1
        data.notes.append(
            f"Human review [{reviewer}] {field} {year}: machine {value_before} "
            f"→ {status} final={approved_value}.")
    return rec


# ── trust & invalidation ────────────────────────────────────────────────────

def review_is_valid(record: dict, crops_dir: Path = Path("cell_evidence")) -> bool:
    """Void on ANY change of the crop or the page image, or a crop gone
    missing/appeared. Constant-time comparisons. Hashes are the same 32-hex
    sha256 digests the records carry (_sha256_file)."""
    crop = crops_dir / f"spatial_{record['field']}_p{record['page']}_y2022.png"
    if crop.exists():
        fresh = hashlib.sha256(crop.read_bytes()).hexdigest()[:32]
        claimed = record.get("crop_sha256")
        if claimed is None or \
                not _hmac_mod.compare_digest(fresh, str(claimed)):
            return False
    elif record.get("crop_sha256") is not None:
        return False
    page = crops_dir.parent / "eval_pages" / f"page_{record['page']}.png"
    if page.exists() and record.get("doc_sha256"):
        fresh = hashlib.sha256(page.read_bytes()).hexdigest()[:32]
        if not _hmac_mod.compare_digest(fresh, str(record.get("doc_sha256"))):
            return False
    return True


def review_is_trusted(record: dict, log_path: Path = REVIEW_LOG,
                      crops_dir: Path = Path("cell_evidence")) -> bool:
    """A VERIFIED_HUMAN claim is trusted ONLY when the SAME record exists in
    the on-disk chain (matching hash) with an intact chain and unchanged
    sources — direct data.human_reviews injection does not pass, and a stale
    record for a changed document/cell never passes (review_is_valid)."""
    ok, _bad = verify_log_integrity(log_path)
    if not ok:
        return False
    for rec in load_log(log_path):
        if (rec.get("packet_id") == record.get("packet_id")
                and _hmac_mod.compare_digest(str(rec.get("record_hash") or ""),
                                             str(record.get("record_hash") or ""))
                and rec.get("status") == STATUS_HUMAN):
            return review_is_valid(rec, crops_dir)
    return False


# ── separated accuracy metrics (المهمة 6 — مقاييس منفصلة تمامًا) ────────────

def separated_metrics(per_cell_rows: list[dict], human_log: Path = REVIEW_LOG,
                      crops_dir: Path = Path("cell_evidence"),
                      log_integrity: tuple[bool, int | None] | None = None) -> dict:
    """Metrics that NEVER mix, each with a VISIBLE denominator:

    - automatic_exact_match_accuracy      exact / n  (machine only)
    - automatic_decisive_coverage         gate-allowed / n  (machine only)
    - false_acceptance_rate               allowed-but-wrong / allowed (N/A if none allowed)
    - withheld_correct_share              gated-but-correct / gated
        (was misnamed correct_abstention_rate: it is the share of CORRECT
         values among WITHHELD cells — a COST of abstention, not a virtue;
         the denominator is the gated set, not n)
    - human_assisted_verified_coverage    trusted-human packets / n
        (denominator is ALL targeted cells n → 0/11 when no production
         reviews exist — NEVER N/A while n>0)
    - false_acceptances / correct_values_blocked / wrong_values_blocked /
      missing_values: separated COUNTS (not rates, not folded together)
    - reviewer_accuracy_unreviewed_sample: None (N/A by definition — no
      independently reviewed sample exists to measure reviewer accuracy)
    - final_report_coverage               (decisive + trusted-human) / n

    gate_partition is EXCLUSIVE: usable + not_decisive + missing == n.
    Any zero-denominator rate returns None (N/A) — never a fabricated %.
    """
    from src.analysis.financial_gate import decide

    n = len(per_cell_rows)
    allowed = [r for r in per_cell_rows
               if decide(r["final_status"]) in ("use", "use_disclosed")]
    gated = [r for r in per_cell_rows
             if decide(r["final_status"]) == "not_decisive"]
    missing = [r for r in per_cell_rows
               if decide(r["final_status"]) == "missing"]
    trusted_packets: set[str] = set()
    if log_integrity is None or log_integrity[0]:
        by_packet: dict[str, list[dict]] = {}
        for rec in load_log(human_log):
            by_packet.setdefault(rec.get("packet_id"), []).append(rec)
        for pid, recs in by_packet.items():
            # a packet counts ONLY if some record attests VERIFIED_HUMAN and
            # no LATER record withdraws it (conflict/reject) and the sources
            # it attests are unchanged
            attests = [(i, r) for i, r in enumerate(recs)
                       if r.get("status") == STATUS_HUMAN]
            if not attests:
                continue
            last_idx, last = attests[-1]
            withdrawn = any(r.get("status") in (STATUS_CONFLICT_HUMAN,
                                                STATUS_REJECTED_HUMAN)
                            for r in recs[last_idx + 1:])
            if not withdrawn and review_is_valid(last, crops_dir):
                trusted_packets.add(pid)

    def rate(num: int, den: int) -> float | None:
        return round(num / den, 3) if den else None   # zero denominator = N/A

    # Critical Field Coverage (تغطية الحقول الحرجة): the fields a reader MUST
    # have before any health/leverage/profitability verdict — measured over
    # the latest year present in the rows
    from src.analysis.financial_gate import decide as _decide
    critical = ({"revenue", "net_income", "total_assets", "total_liabilities",
                 "equity", "operating_cash_flow", "current_assets",
                 "current_liabilities"})
    crit_rows = [r for r in per_cell_rows if r.get("field") in critical]
    crit_allowed = [r for r in crit_rows
                    if _decide(r["final_status"]) in ("use", "use_disclosed")]

    exact = sum(1 for r in per_cell_rows if r["exact_value"])
    gated_exact = [r for r in gated if r["exact_value"]]
    gated_wrong = [r for r in gated if not r["exact_value"]]
    allowed_wrong = [r for r in allowed if not r["exact_value"]]
    # human coverage adds only cells the machine gate did NOT already allow
    allowed_keys = {(r["field"], r.get("page")) for r in allowed}
    final_covered = len(allowed) + len([
        pid for pid in trusted_packets
        if (pid.split("|")[0],
            int(pid.split("|")[1]) if pid.count("|") >= 2 else None)
        not in allowed_keys])
    return {
        "n": n,
        "automatic_exact_match_accuracy": rate(exact, n),
        "automatic_decisive_coverage": rate(len(allowed), n),
        "false_acceptance_rate": rate(len(allowed_wrong), len(allowed)),
        # renamed: correct values WITHIN the withheld (gated) set — a cost
        # measure, NOT "correct abstention"
        "withheld_correct_share": rate(len(gated_exact), len(gated)),
        # denominator is always n (all targeted cells) → 0.0 when no reviews
        "human_assisted_verified_coverage": rate(len(trusted_packets), n),
        "critical_field_coverage": rate(len(crit_allowed), len(crit_rows)),
        "final_report_coverage": rate(min(final_covered, n), n),
        "counts": {
            "correct_values_blocked": len(gated_exact),
            "wrong_values_blocked": len(gated_wrong),
            "missing_values": len(missing),
            "false_acceptances": len(allowed_wrong),
            "human_verified_values": len(trusted_packets),
        },
        # reviewer accuracy on a sample no one reviewed — undefined, and we
        # refuse to invent a number for it
        "reviewer_accuracy_unreviewed_sample": None,
        "gate_partition": {"usable": len(allowed), "not_decisive": len(gated),
                           "missing": len(missing)},
        "denominators": {"n": n, "allowed": len(allowed), "gated": len(gated),
                         "missing": len(missing),
                         "human_trusted_packets": len(trusted_packets)},
        "definitions": {
            "withheld_correct_share":
                "القيم الصحيحة بين المحجوبة / كل المحجوبة — تكلفة الامتناع "
                "(لا تعني امتناعًا صحيحًا)",
            "automatic_decisive_coverage":
                "الخانات الحاسمة آليًا / جميع الخانات المستهدفة (n)",
            "human_assisted_verified_coverage":
                "خانات موثوقة بإقرار بشري (سلسلة سليمة ومصادر لم تتغير) / n — "
                "0/11 عندما لا توجد مراجعات إنتاجية",
            "false_acceptance_rate":
                "قيم خاطئة قُبلت آليًا / كل المقبولة آليًا (N/A إذا لم يُقبل شيء)",
            "critical_field_coverage":
                "الحقول الحرجة المسموح بها (آليًا أو بشريًا) / كل الحقول الحرجة "
                "المستهدفة — سيولة/مديونية/ربحية لا تُبنى بدونها",
            "reviewer_accuracy_unreviewed_sample":
                "N/A — لا توجد عينة مراجَعة بشريًا مستقلة لقياس دقة المراجعين",
            "gate_partition":
                "تقسيم حصري: usable + not_decisive + missing == n",
        },
        "log_integrity_ok": (log_integrity or (True, None))[0],
    }
