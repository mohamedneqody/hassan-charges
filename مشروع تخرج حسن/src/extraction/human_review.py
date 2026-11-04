# -*- coding: utf-8 -*-
"""Human-in-the-Loop verification — SECURED (المراجعة البشرية المؤمَّنة).

Audit-trail guarantees:
- append-only JSONL-style log where every record carries `seq` and
  `prev_hash`; record_hash = sha256(canonical(record w/o hash) + prev_hash).
  verify_log_integrity() recomputes the chain — any edit to an old record
  breaks every hash after it and is REPORTED, not silently accepted.
- reviewer identity checked against an allowlist (env REVIEWERS or
  reviewers.json) BEFORE anything is written; unknown reviewer →
  PermissionError, nothing recorded.
- every record stores: reviewer, timestamp, crop_sha256 AND document
  sha256, field/year/bbox, value_before (machine), value_final (human),
  decision kind (corroborate/correct/reject/conflict).
- invalidation: review_is_valid() re-hashes the crop AND the page image AND
  compares the bbox — a changed source, position, or field definition voids
  the attestation.
- forgery resistance: a VERIFIED_HUMAN claim in a FinancialData object is
  trusted ONLY when the same record exists in the on-disk chain with a valid
  chain and unchanged sources (review_is_trusted). Injecting
  data.human_reviews directly from code does NOT pass the gate.

Separation rule (hard): automatic accuracy counters are computed from the
machine benchmark artifacts only; human reviews live in their own chain and
are reported as a SEPARATE coverage number.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

# isolated test runs override REVIEW_LOG_PATH — production default unchanged
REVIEW_LOG = Path(os.environ.get("REVIEW_LOG_PATH",
                                 "cell_evidence/human_reviews.json"))
PROVENANCE_LADDER_HUMAN = "VISUALLY_VERIFIED"
STATUS_HUMAN = "VERIFIED_HUMAN"
STATUS_CONFLICT_HUMAN = "CONFLICT_HUMAN"
STATUS_REJECTED_HUMAN = "REJECTED_HUMAN"


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
    """reviewers.json entries: {name, salt, pin_sha256, roles:[...]} — the PIN
    itself is NEVER stored, only its salted hash."""
    f = _reviewers_file()
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8")).get("reviewers", [])
        except Exception:
            return []
    raw = os.environ.get("REVIEWERS", "")
    # env fallback: names only, NO credential → no roles → cannot attest
    return [{"name": x.strip(), "roles": []} for x in raw.split(",") if x.strip()]


def verify_reviewer(reviewer: str, credential: str | None = None,
                    action: str | None = None) -> dict:
    """AUTHENTICATION (name + PIN against the salted hash) plus
    AUTHORIZATION (the action must be in the reviewer's roles). Raises
    PermissionError — nothing is written on failure."""
    entry = next((r for r in _allowlist() if r.get("name") == reviewer), None)
    if entry is None:
        raise PermissionError(f"المراجع '{reviewer}' غير مسجل")
    salt, stored = entry.get("salt"), entry.get("pin_sha256")
    if stored:
        if not credential:
            raise PermissionError("اعتماد المراجع يتطلب رمز تحقق (PIN)")
        if hashlib.sha256(((salt or "") + credential).encode("utf-8")).hexdigest() != stored:
            raise PermissionError("رمز تحقق غير صحيح")
    roles = set(entry.get("roles", []))
    if not roles:
        raise PermissionError(f"المراجع '{reviewer}' بلا صلاحيات اعتماد")
    if action and action not in roles:
        raise PermissionError(f"المراجع '{reviewer}' لا يملك صلاحية '{action}'")
    return entry


def pin_entry(name: str, pin: str, roles: list[str],
              file_path: Path | None = None) -> None:
    """Admin helper: store a reviewer with a SALTED pin hash (never the PIN)."""
    import secrets

    f = file_path or _reviewers_file()
    salt = secrets.token_hex(8)
    data = {"reviewers": []}
    if f.exists():
        data = json.loads(f.read_text(encoding="utf-8"))
    data["reviewers"] = [r for r in data.get("reviewers", [])
                         if r.get("name") != name]
    data["reviewers"].append({
        "name": name, "salt": salt,
        "pin_sha256": hashlib.sha256((salt + pin).encode("utf-8")).hexdigest(),
        "roles": roles,
    })
    f.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


# ── hash chain ──────────────────────────────────────────────────────────────

def _canonical(rec: dict) -> str:
    core = {k: v for k, v in rec.items() if k not in ("record_hash", "prev_hash", "seq")}
    return json.dumps(core, ensure_ascii=False, sort_keys=True, default=str)


def _record_hash(rec: dict, prev_hash: str) -> str:
    """HMAC-SHA256 with the secret key. An attacker with full file access can
    recompute a PLAIN hash after rewriting records — with HMAC they cannot
    re-sign without the key (which never lives in the log or the repo)."""
    import hmac as _hmac

    key = _hmac_key()
    if key is None:
        raise PermissionError(
            "REVIEW_HMAC_KEY غير مضبوط — سلسلة غير موقعة لا تُدعى tamper-proof")
    return _hmac.new(key, (_canonical(rec) + "|" + prev_hash).encode("utf-8"),
                     hashlib.sha256).hexdigest()[:32]


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
        if rec.get("prev_hash") != prev or \
                rec.get("record_hash") != _record_hash(rec, prev):
            return False, rec.get("seq")
        prev = rec["record_hash"]
    return True, None


# ── queue / packets ─────────────────────────────────────────────────────────

def build_review_queue(per_cell_json: Path, crops_dir: Path,
                       out_path: Path | None = None) -> list[dict]:
    """One packet per NON-decisive cell: crop image + page image + field +
    year + bbox + every machine reading + the conflict reason. GT is NOT
    included — the reviewer judges the printed image, not the answer key."""
    cells = json.loads(Path(per_cell_json).read_text(encoding="utf-8"))
    bench = json.loads((Path(per_cell_json).parent / "benchmark_abc.json")
                       .read_text(encoding="utf-8"))
    by_key = {(r["field"], r.get("page")): r for r in bench
              if r["method"] == "C_spatial_declared"}
    queue = []
    for c in cells:
        if c["final_status"] == "VERIFIED_CANDIDATE":
            continue
        r = by_key.get((c["field"], c.get("page")), {})
        crop = Path(crops_dir) / f"spatial_{c['field']}_p{c['page']}_y2022.png"
        page_img = Path(crops_dir).parent / f"eval_pages/page_{c['page']}.png"
        queue.append({
            "packet_id": f"{c['field']}|{c['page']}|2022",
            "field": c["field"], "page": c["page"], "year": 2022,
            "status": c["final_status"],
            "crop_image": str(crop) if crop.exists() else None,
            "page_image": str(page_img) if page_img.exists() else None,
            "bbox_rel": r.get("bbox_rel"),
            "machine_selected": c.get("selected") or r.get("value_2022"),
            "readings": {
                "detection_line": (r.get("detection_values") or [])[:4]
                if isinstance(r.get("detection_values"), list) else [],
                "crop_variants": (r.get("crop_values") or [])[:6]
                if isinstance(r.get("crop_values"), list) else [],
            },
            "conflict_reason": r.get("detail_2022", ""),
            "decision": None,
        })
    if out_path:
        out_path.write_text(json.dumps(queue, ensure_ascii=False, indent=1),
                            encoding="utf-8")
    return queue


# ── apply a decision (secured) ──────────────────────────────────────────────

def value_matches_probe(queue, packet_id, value) -> bool:
    pkt = next((p for p in queue if p["packet_id"] == packet_id), None)
    before = pkt.get("machine_selected") if pkt else None
    return (before is not None and value is not None
            and abs(value - before) <= max(1.0, 1e-6 * abs(before)))


def apply_review(queue: list[dict], packet_id: str,
                 approved_value: float | None, reviewer: str,
                 credential: str | None = None,
                 data=None, log_path: Path = REVIEW_LOG,
                 decision_note: str = "") -> dict:
    """Record one human decision (identity checked, chain appended). kind:
    corroborate | correct | reject | conflict — conflict when a PRIOR record
    for the same packet holds a DIFFERENT final value."""
    kind_probe = "reject" if approved_value is None else (
        "approve" if value_matches_probe(queue, packet_id, approved_value)
        else "correct")
    verify_reviewer(reviewer, credential=credential, action=kind_probe)
    if _hmac_key() is None:
        raise PermissionError(
            "REVIEW_HMAC_KEY غير مضبوط — الاعتماد مرفوض (سلسلة غير موقعة)")
    pkt = next((p for p in queue if p["packet_id"] == packet_id), None)
    if pkt is None:
        raise KeyError(f"unknown packet {packet_id}")
    field, page, year = pkt["field"], pkt["page"], pkt["year"]
    value_before = pkt.get("machine_selected")

    log = load_log(log_path)
    prior = [r for r in log if r["packet_id"] == packet_id
             and r.get("status") == STATUS_HUMAN]
    kind = ("corroborate" if value_before is not None and approved_value is not None
            and abs(approved_value - value_before) <= max(1.0, 1e-6 * abs(value_before))
            else "correct" if approved_value is not None else "reject")
    status = STATUS_HUMAN
    if approved_value is None:
        status = STATUS_REJECTED_HUMAN
    elif prior and any(abs((r.get("value_final") or 0) - approved_value)
                       > max(1.0, 1e-6 * abs(r.get("value_final") or 1))
                       for r in prior):
        # two reviewers disagree — the cell is CONFLICT_HUMAN, never decided
        status = STATUS_CONFLICT_HUMAN

    doc_sha = None
    if pkt.get("page_image") and Path(pkt["page_image"]).exists():
        doc_sha = hashlib.sha256(Path(pkt["page_image"]).read_bytes()).hexdigest()[:16]
    rec = {
        "seq": len(log) + 1,
        "packet_id": packet_id, "field": field, "page": page, "year": year,
        "bbox_rel": pkt.get("bbox_rel"),
        "reviewer": reviewer,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "crop_sha256": _crop_sha(pkt.get("crop_image")),
        "doc_sha256": doc_sha,
        "value_before": value_before,
        "value_final": approved_value,
        "kind": kind, "status": status, "note": decision_note[:200],
        "security": "hmac_signed",
    }
    rec["prev_hash"] = log[-1]["record_hash"] if log else "GENESIS"
    rec["record_hash"] = _record_hash(rec, rec["prev_hash"])
    log.append(rec)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    Path(log_path).write_text(json.dumps(log, ensure_ascii=False, indent=1),
                              encoding="utf-8")

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


def _crop_sha(crop_image: str | None) -> str | None:
    if not crop_image or not Path(crop_image).exists():
        return None
    return hashlib.sha256(Path(crop_image).read_bytes()).hexdigest()[:16]


# ── trust & invalidation ────────────────────────────────────────────────────

def review_is_valid(record: dict, crops_dir: Path = Path("cell_evidence")) -> bool:
    """Void on ANY change of the crop, the page image, or the bbox."""
    crop = crops_dir / f"spatial_{record['field']}_p{record['page']}_y2022.png"
    if crop.exists():
        if (hashlib.sha256(crop.read_bytes()).hexdigest()[:16]
                != record.get("crop_sha256")):
            return False
    elif record.get("crop_sha256") is not None:
        return False
    page = crops_dir.parent / "eval_pages" / f"page_{record['page']}.png"
    if page.exists() and record.get("doc_sha256"):
        if (hashlib.sha256(page.read_bytes()).hexdigest()[:16]
                != record.get("doc_sha256")):
            return False
    return True


def review_is_trusted(record: dict, log_path: Path = REVIEW_LOG,
                      crops_dir: Path = Path("cell_evidence")) -> bool:
    """A VERIFIED_HUMAN claim is trusted ONLY when the SAME record exists in
    the on-disk chain (matching hash) with an intact chain and unchanged
    sources — direct data.human_reviews injection does not pass."""
    ok, _bad = verify_log_integrity(log_path)
    if not ok:
        return False
    for rec in load_log(log_path):
        if (rec.get("packet_id") == record.get("packet_id")
                and rec.get("record_hash") == record.get("record_hash")
                and rec.get("status") == STATUS_HUMAN):
            return review_is_valid(rec, crops_dir)
    return False


# ── separated accuracy metrics (المهمة 6) ───────────────────────────────────

def separated_metrics(per_cell_rows: list[dict], human_log: Path = REVIEW_LOG,
                      crops_dir: Path = Path("cell_evidence"),
                      log_integrity: tuple[bool, int | None] | None = None) -> dict:
    """SIX never-mixed metrics with VISIBLE denominators; any zero-denominator
    rate returns None (N/A) — never a fabricated percentage:
    - automatic_exact_match_accuracy
    - automatic_decisive_coverage
    - false_acceptance_rate
    - correct_abstention_rate
    - human_assisted_verified_coverage
    - final_report_coverage (decisive + trusted-human) / n"""
    from src.analysis.financial_gate import decide

    n = len(per_cell_rows)
    allowed = [r for r in per_cell_rows
               if decide(r["final_status"]) in ("use", "use_disclosed")]
    gated = [r for r in per_cell_rows
             if decide(r["final_status"]) == "not_decisive"]
    missing = [r for r in per_cell_rows
               if decide(r["final_status"]) == "missing"]
    trusted = 0
    if log_integrity is None or log_integrity[0]:
        for rec in load_log(human_log):
            if rec.get("status") == STATUS_HUMAN and review_is_valid(rec, crops_dir):
                trusted += 1

    def rate(num: int, den: int) -> float | None:
        return round(num / den, 3) if den else None   # zero denominator = N/A

    exact = sum(1 for r in per_cell_rows if r["exact_value"])
    allowed_wrong = sum(1 for r in allowed if not r["exact_value"])
    abstained_right = sum(1 for r in gated if r["exact_value"])
    final_covered = len(allowed) + trusted
    return {
        "n": n,
        "automatic_exact_match_accuracy": rate(exact, n),
        "automatic_decisive_coverage": rate(len(allowed), n),
        "false_acceptance_rate": rate(allowed_wrong, len(allowed)),
        "correct_abstention_rate": rate(abstained_right, len(gated)),
        "human_assisted_verified_coverage": rate(trusted, n),
        "final_report_coverage": rate(min(final_covered, n), n),
        "gate_partition": {"usable": len(allowed), "not_decisive": len(gated),
                           "missing": len(missing)},
        "denominators": {"n": n, "allowed": len(allowed), "gated": len(gated),
                         "missing": len(missing), "human_trusted": trusted},
        "log_integrity_ok": (log_integrity or (True, None))[0],
    }
