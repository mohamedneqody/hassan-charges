# -*- coding: utf-8 -*-
"""Quality gate for the financial engine (حماية المحرك المالي).

A captured value reaches the decisive analysis ONLY through its decision-log
status:
  VERIFIED_EXACT   → use
  VERIFIED_DERIVED → use, disclosed (derivation + input confidence shown)
  UNVERIFIED       → present but NOT decisive
  CONFLICT / MULTI_ROW → never decisive while unresolved
  UNREADABLE       → treated as a missing statement
No path may substitute a cached value without a valid extraction provenance.
"""
from __future__ import annotations

VERIFIED_EXACT = "VERIFIED_EXACT"
VERIFIED_DERIVED = "VERIFIED_DERIVED"


def decide(status: str) -> str:
    """use | use_disclosed | not_decisive | missing"""
    return {
        "VERIFIED_EXACT": "use",
        # explicit human attestation — usable, but always DISCLOSED as
        # human-assisted (never folded into automatic OCR accuracy)
        "VERIFIED_HUMAN": "use_disclosed",
        # spatial dual attestation (full-page read + focused crop read AGREE)
        "VERIFIED_CANDIDATE": "use",
        "VERIFIED_DERIVED": "use_disclosed",
        # a SINGLE uncorroborated read — never decisive on its own
        "CROP_ONLY": "not_decisive",
        "UNVERIFIED": "not_decisive",
        "CONFLICT": "not_decisive",
        "MULTI_ROW": "not_decisive",
        "UNREADABLE": "missing",
        "MISSING": "missing",
    }.get(status, "not_decisive")


def decisive_values(data) -> dict[tuple[str, object], dict]:
    """Walk the decision log; return only the values allowed into decisive
    analysis, each with its disclosure level. Blocked/missing ones are
    returned too — with their gate verdict — so the report can SHOW why a
    number is absent instead of hiding it."""
    from src.extraction.normalizer import build_decision_log

    out: dict[tuple[str, object], dict] = {}
    for entry in build_decision_log(data):
        verdict = decide(entry["status"])
        out[(entry["field"], entry["year"])] = {
            "value": entry["final"],
            "status": entry["status"],
            "gate": verdict,
            "usable_decisive": verdict in ("use", "use_disclosed"),
            "disclosure": (entry["reason"] if verdict == "use_disclosed"
                           else None),
        }
    return out
