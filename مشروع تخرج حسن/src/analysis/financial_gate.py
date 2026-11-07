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
        # documented faithful transfer from a DIGITAL source (spreadsheet
        # cell / PDF text layer) whose full evidence checklist passed —
        # decisive WITH the source cited in the decision log. Proof of
        # transfer, never of economic correctness.
        "VERIFIED_SOURCE_EXACT": "use",
        # explicit human attestation — usable, but always DISCLOSED as
        # human-assisted (never folded into automatic OCR accuracy)
        "VERIFIED_HUMAN": "use_disclosed",
        # spatial agreement = the SAME Indra model read twice under different
        # segmentation (full page vs row∩column crop) — correlated errors are
        # possible, so it is usable WITH disclosure, never silent "use"
        "VERIFIED_CANDIDATE": "use_disclosed",
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


# ── MVP safety guard (المهمة 3): critical fields NEVER skip human review ───
CRITICAL_FIELDS = frozenset({
    "revenue", "net_income", "total_assets", "total_liabilities",
    "equity", "operating_cash_flow", "current_assets",
    "current_liabilities", "pretax_income", "cost_of_revenue",
    "accounts_payable", "short_term_debt", "long_term_debt",
})


def pending_critical_review(decision_log: list[dict]) -> list[dict]:
    """The critical-benefit MVP guard: VERIFIED_EXACT/VERIFIED_DERIVED alone
    NEVER exempt a CRITICAL financial field from review when its evidence
    failed a safety check. A critical field NEEDS review when its decision-
    log entry shows: CONFLICT / UNVERIFIED / MISSING status, OR a
    sign conflict (the reason text carries it), OR identity_ok is False
    (the accounting identity contradicted the capture).

    Returns the list of pending entries — a non-empty list means the
    report is PRELIMINARY (reviewable), never a verified-final one.
    """
    # identity-group members: fields the identity engine actually evaluated
    # (identity_ok=False by default means "never participated", NOT
    # "contradicted" — current_assets/operating_cash_flow have no identity)
    identity_members = {
        f for target, comps in [
            (("net_income",), (("pretax_income", 1), ("income_tax_expense", -1))),
            (("total_assets",), (("total_liabilities", 1), ("equity", 1))),
            (("gross_profit",), (("revenue", 1), ("cost_of_revenue", -1))),
            (("operating_income",), (("gross_profit", 1),
                                     ("operating_expenses", -1))),
        ] for f in (target,) + tuple(c[0] for c in comps)
    }
    pending = []
    for e in decision_log:
        if e.get("field") not in CRITICAL_FIELDS:
            continue
        if e.get("status") == "VERIFIED_HUMAN":
            continue          # RESOLVED by the documented human review
        reason = e.get("reason") or ""
        # المهمة 3 (حارس الـMVP): a CRITICAL field is exempt from review
        # ONLY by TWO-LAYER attestation — a VERIFIED_EXACT/DERIVED backed by
        # ONE layer (e.g. two vision captures of the same wrong row) is
        # mandatory-review, never auto-final
        wl = e.get("winner_layers") or []
        single_layer_backing = bool(wl) and len(set(wl)) < 2
        needs = (
            e.get("status") in ("CONFLICT", "UNVERIFIED", "MISSING",
                                "CROP_ONLY", "MULTI_ROW")
            or "تعارض الإشارة" in reason
            or (e.get("identity_ok") is False
                and e.get("field") in identity_members)
            or (e.get("final") is not None and e.get("status") == "MISSING")
            or single_layer_backing
        )
        if needs:
            pending.append({
                "field": e["field"], "year": e["year"],
                "final": e.get("final"), "status": e["status"],
                "why": ("تعارض إشارة" if "تعارض الإشارة" in reason else
                        "تعارض قراءات" if e["status"] == "CONFLICT" else
                        "قراءة واحدة/echo" if e["status"] == "UNVERIFIED" else
                        "غير ملتقطة" if e["status"] == "MISSING" else
                        "تعارض الهوية المحاسبية" if e.get("identity_ok") is False
                        else e["status"]),
            })
    return pending


def report_is_preliminary(decision_log: list[dict]) -> bool:
    """True while ANY critical field still needs review — the generated
    report must then be labeled preliminary (reviewable), and a decisive/
    final report is only produced once this returns False."""
    return bool(pending_critical_review(decision_log))