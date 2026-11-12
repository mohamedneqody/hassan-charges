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
        # v6 إصلاح حديد عز (إصلاح 4): تعارض جدول إيضاح فرعي مشوه والهوية
        # الكبرى مثبتة (الأصول = الالتزامات + الملكية) — اعتماد بالإفصاح
        "CONFLICT_UPGRADED_IDENTITY": "use_disclosed",
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
        if e.get("identity_anchored"):
            continue          # v6 إصلاح 4: معتمد بالإفصاح — الهوية الكبرى مثبتة
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


def verification_labels(decision_log: list[dict]) -> dict[str, str]:
    """Per-field verification labels for report tables (المهمة: حالة
    التحقق بجوار كل مؤشر).

    v3 fix (defects 1+2 of the v2 review): a field's label is the WORST
    across its YEAR entries (v2 collapsed years — a gated 2024 under a
    verified 2023 printed as «موثق آلي»), and a metric's label is the
    worst across ALL its required_inputs — a MISSING input is «غير
    متوفر», never silently dropped (v2 skipped absent inputs, so N/A
    metrics with one present input printed as verified). The report
    column can therefore never claim a better state than the evidence
    or than the pending-review banner."""
    from src.analysis.metric_registry import REGISTRY

    rank = {"موثق (بشري)": 0, "موثق (آلي عبر-طبقتين)": 1,
            "موثق (نقل رقمي)": 1, "موثق (آلي)": 1,
            "مشتق معلن": 2, "يحتاج مراجعة": 3, "تعارض — محجوب": 4,
            "غير متوفر": 5}

    def label_of(e: dict | None) -> str:
        st = (e or {}).get("status", "MISSING")
        if st == "VERIFIED_HUMAN":
            return "موثق (بشري)"
        if st == "VERIFIED_SOURCE_EXACT":
            return "موثق (نقل رقمي)"
        if st == "CONFLICT_UPGRADED_IDENTITY":
            return "موثق (معلن — مثبت بالهوية المحاسبية)"
        if st == "VERIFIED_EXACT":
            return "موثق (آلي)"
        if st == "VERIFIED_DERIVED":
            return "مشتق معلن"
        if st in ("CONFLICT", "MULTI_ROW"):
            return "تعارض — محجوب"
        if st in ("UNVERIFIED", "CROP_ONLY"):
            return "يحتاج مراجعة"
        return "غير متوفر"

    def worst(labels: list[str]) -> str:
        return max(labels, key=lambda l: rank.get(l, 3)) if labels \
            else "غير متوفر"

    # per-field: worst label across the field's year entries
    by_field_years: dict[str, dict] = {}
    for e in decision_log:
        by_field_years.setdefault(e["field"], {})[e.get("year")] = e
    out: dict[str, str] = {
        f: worst([label_of(e) for e in ymap.values()])
        for f, ymap in by_field_years.items()}

    # per-metric: worst across ALL required_inputs — missing = غير متوفر
    for entry in REGISTRY:
        labels = [out.get(f, "غير متوفر") for f in entry.required_inputs]
        if not labels:
            continue
        out.setdefault(entry.metric_id, worst(labels))
    return out