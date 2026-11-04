# -*- coding: utf-8 -*-
"""Human-in-the-Loop verification (المراجعة البشرية للخانات غير الحاسمة).

A reviewer sees, per cell: the crop IMAGE, the field, the year, every machine
reading (full-page detection + each crop variant), and the recorded conflict
reason. On approval the review records WHO, WHEN, the source-crop SHA-256,
the machine value BEFORE, and the approved value — any later change to the
crop voids the review.

Separation rule (hard): human reviews NEVER touch the automatic extraction
artifacts (benchmark_abc.json / automatic counters). Automatic Extraction
Accuracy and Human-Assisted Verified Accuracy are reported as two separate
numbers, and the benchmark's machine rows are immutable here.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

REVIEW_LOG = Path("cell_evidence") / "human_reviews.json"
PROVENANCE_LADDER_HUMAN = "VISUALLY_VERIFIED"
STATUS_HUMAN = "VERIFIED_HUMAN"


def build_review_queue(per_cell_json: Path, crops_dir: Path,
                       out_path: Path | None = None) -> list[dict]:
    """One packet per NON-decisive cell: crop image + field + year + every
    machine reading + the conflict reason. GT is NOT included — the reviewer
    judges the printed image, not the answer key."""
    cells = json.loads(Path(per_cell_json).read_text(encoding="utf-8"))
    bench = json.loads((Path(per_cell_json).parent / "benchmark_abc.json")
                       .read_text(encoding="utf-8"))
    by_key = {(r["field"], r.get("page")): r for r in bench
              if r["method"] == "C_spatial_declared"}
    queue = []
    for c in cells:
        if c["final_status"] == "VERIFIED_CANDIDATE":
            continue  # already dual-attested by the machine
        r = by_key.get((c["field"], c.get("page")), {})
        crop = Path(crops_dir) / f"spatial_{c['field']}_p{c['page']}_y2022.png"
        queue.append({
            "packet_id": f"{c['field']}|{c['page']}|2022",
            "field": c["field"], "page": c["page"], "year": 2022,
            "status": c["final_status"],
            "crop_image": str(crop) if crop.exists() else None,
            "machine_selected": c.get("selected") or r.get("value_2022"),
            "readings": {
                "detection_line": (r.get("detection_values") or [])[:4]
                if isinstance(r.get("detection_values"), list) else [],
                "crop_variants": (r.get("crop_values") or [])[:6]
                if isinstance(r.get("crop_values"), list) else [],
            },
            "conflict_reason": r.get("detail_2022", ""),
            "decision": None,   # reviewer fills: approved value or REJECT
        })
    if out_path:
        out_path.write_text(json.dumps(queue, ensure_ascii=False, indent=1),
                            encoding="utf-8")
    return queue


def _crop_sha(crop_image: str | None) -> str | None:
    if not crop_image or not Path(crop_image).exists():
        return None
    return hashlib.sha256(Path(crop_image).read_bytes()).hexdigest()[:16]


def apply_review(queue: list[dict], packet_id: str, approved_value: float | None,
                 reviewer: str, data=None, log_path: Path = REVIEW_LOG) -> dict:
    """Record one human decision. Corroborating (approved == machine value) is
    an independent SECOND read; a differing value is a CORRECTION whose change
    log keeps the machine value. When `data` (FinancialData) is passed, the
    attestation flows into the decision log as VERIFIED_HUMAN and the value
    into data.values — the automatic artifacts are never modified."""
    pkt = next((p for p in queue if p["packet_id"] == packet_id), None)
    if pkt is None:
        raise KeyError(f"unknown packet {packet_id}")
    field, page, year = pkt["field"], pkt["page"], pkt["year"]
    value_before = pkt.get("machine_selected")
    record = {
        "packet_id": packet_id, "field": field, "page": page, "year": year,
        "reviewer": reviewer,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "crop_sha256": _crop_sha(pkt.get("crop_image")),
        "value_before": value_before,
        "value_final": approved_value,
        "corroborates_machine": (
            value_before is not None and approved_value is not None
            and abs(approved_value - value_before) <= max(1.0, 1e-6 * abs(value_before))
        ),
        "source_type": "HUMAN_VERIFIED",
        "status": STATUS_HUMAN if approved_value is not None else "REJECTED_HUMAN",
    }
    # append-only log (immutable trail)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else []
    log.append(record)
    log_path.write_text(json.dumps(log, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    if data is not None and approved_value is not None:
        hr = getattr(data, "human_reviews", None) or {}
        hr[(field, year)] = record
        data.human_reviews = hr
        # the human-approved value becomes the canonical value, with the
        # machine value preserved in the record as the change log
        data.values.setdefault(field, {})[year] = float(approved_value)
        data.candidates.setdefault(field, {}).setdefault(year, []).append(
            (float(approved_value), 0))
        data.confidence.setdefault(field, {})[year] = 2
        data.notes.append(
            f"Human review [{reviewer}] {field} {year}: machine {value_before} "
            f"→ approved {approved_value:,.0f} ({record['status']}).")
    return record


def review_is_valid(record: dict, crops_dir: Path = Path("cell_evidence")) -> bool:
    """The human attestation holds only while the reviewed crop is unchanged."""
    crop = crops_dir / f"spatial_{record['field']}_p{record['page']}_y2022.png"
    if not crop.exists():
        return record.get("crop_sha256") is None
    return (hashlib.sha256(crop.read_bytes()).hexdigest()[:16]
            == record.get("crop_sha256"))


def accuracy_separation(machine_summary: dict, human_log: Path = REVIEW_LOG,
                        gt: dict | None = None) -> dict:
    """TWO separate numbers: Automatic Extraction Accuracy is computed ONLY
    from the machine benchmark rows (human reviews cannot raise it);
    Human-Assisted Verified Accuracy is computed ONLY from the review log."""
    machine = {
        "automatic_exact": machine_summary.get("exact_numeric"),
        "automatic_usable_decisive": machine_summary.get("usable_decisive"),
        "automatic_e2e_strict": machine_summary.get("e2e_strict"),
        "note": "human reviews never modify these counters",
    }
    human = {"reviewed": 0, "human_verified_exact": 0}
    if gt and Path(human_log).exists():
        for r in json.loads(Path(human_log).read_text(encoding="utf-8")):
            if r.get("status") != STATUS_HUMAN:
                continue
            human["reviewed"] += 1
            g = gt.get(r["field"])
            if g is not None and r.get("value_final") is not None \
                    and abs(r["value_final"] - g) <= max(1.0, 0.02 * abs(g)):
                human["human_verified_exact"] += 1
    return {"automatic": machine, "human_assisted": human}
