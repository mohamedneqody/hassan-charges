# -*- coding: utf-8 -*-
"""Indicator audit (تدقيق المؤشرات — المهمة 3).

For EVERY headline indicator: Formula | Input Values | Input Sources |
Period | Accounting Definition | Verification Status — and the two audit
questions the mandate asks:

  1. debt_ratio moved 2.6% → 56.8% after the human review: the DEFINITION
     (total liabilities / total assets) and the DENOMINATOR never moved —
     only the INPUT VALUE was corrected (418,441,944 → 9,027,315,979).
     This test pins the definition so no future change can silently swap it.
  2. Health Score coverage=1.0 must never rest on stale/derived-from-
     unverified inputs: a derived-from-uncertain value stays UNVERIFIED →
     its pillar is dropped → a critical-pillar hole REFUSES the score.

Mixing rule pinned by test: total LIABILITIES (Beneish LVGI, debt_ratio) is
never conflated with total BORROWINGS (engine debt_to_equity, cfo_to_debt)
and neither with leases unless explicitly included.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

PROJ = Path(__file__).resolve().parents[1]
CONF_ALL = {"document": True, "field": True, "year": True,
            "position": True, "value": True}


def _scenario_data():
    from tests.test_accounting_impact import _build_machine_data

    return _build_machine_data()


def _review(secured, d):
    from src.extraction.human_review import apply_review, build_review_queue

    queue = build_review_queue(PROJ / "cell_evidence/per_cell_strict.json",
                               PROJ / "cell_evidence")
    for pkt, val in (("net_income|6|2022", 1_056_737_086.0),
                     ("total_liabilities|5|2022", 9_027_315_979.0),
                     ("operating_cash_flow|9|2022", 1_214_507_839.0)):
        apply_review(queue, pkt, val, reviewer="auditor-A",
                     credential=secured["A"], data=d,
                     log_path=secured["tmp"] / "hr.json",
                     confirmations=CONF_ALL)


@pytest.fixture()
def secured(tmp_path, monkeypatch):
    from src.extraction.human_review import pin_entry

    rf = tmp_path / "reviewers.json"
    pin_entry("auditor-A", "pin-A-123", ["approve", "correct", "reject"],
              file_path=rf)
    monkeypatch.setenv("REVIEWERS_FILE", str(rf))
    monkeypatch.setenv("REVIEW_HMAC_KEY", "indicator-audit-key")
    monkeypatch.setenv("REVIEW_ATTEMPTS_PATH", str(tmp_path / ".attempts.json"))
    monkeypatch.delenv("REVIEWERS", raising=False)
    return {"A": "pin-A-123", "tmp": tmp_path}


def test_indicator_audit_definitions_inputs_and_artifact(secured):
    from src.analysis import calculator as C
    from src.analysis.advanced import dupont_analysis
    from src.analysis.financial_gate import decisive_values
    from src.analysis.redflags import beneish_m_score
    from src.analysis.score import compute_health_score
    from src.extraction.normalizer import build_decision_log

    d = _scenario_data()

    # ── machine scenario ──
    from src.analysis.financial_gate import decisive_values as _dv
    blocked_A = {f for (f, y), e in _dv(d).items()
                 if y == 2022 and not e["usable_decisive"]}
    prev = C.compute_year_metrics(2021, d.values)
    curr_A = C.compute_year_metrics(2022, d.values, prev_year=2021)
    ben_A = beneish_m_score(prev, curr_A)
    dup_A = dupont_analysis(curr_A, prev)
    liab_before = d.values["total_liabilities"][2022]   # machine value

    _review(secured, d)
    blocked_B = {f for (f, y), e in decisive_values(d).items()
                 if y == 2022 and not e["usable_decisive"]}
    curr_B = C.compute_year_metrics(2022, d.values, prev_year=2021)
    hs_B = compute_health_score(curr_B, blocked_fields=blocked_B)
    ben_B = beneish_m_score(prev, curr_B)
    dup_B = dupont_analysis(curr_B, prev)

    # ── 1. debt_ratio: definition & denominator pinned; only the INPUT moved ──
    assert curr_A.debt_ratio == pytest.approx(
        liab_before / curr_A.total_assets, abs=1e-9)
    assert curr_B.debt_ratio == pytest.approx(
        9_027_315_979.0 / 15_900_000_000.0, abs=1e-9)
    assert curr_A.total_assets == curr_B.total_assets  # denominator untouched
    assert curr_A.debt_ratio < 0.05 < 0.5 < curr_B.debt_ratio
    # the movement is ENTIRELY input correction — numerator change / old denom
    implied = (curr_B.debt_ratio * curr_B.total_assets)
    assert implied == pytest.approx(9_027_315_979.0, abs=1.0)

    # ── 2. debt_to_equity: BORROWINGS, never total liabilities ──
    borrowings = (4_063_400_167 + 363_974_291 + 299_320_963)
    assert curr_B.debt_to_equity == pytest.approx(borrowings / 6_900_000_000.0,
                                                  abs=1e-9)
    assert curr_B.debt_to_equity != pytest.approx(
        9_027_315_979.0 / 6_900_000_000.0, abs=1e-3)   # no conflation

    # ── 3. current_ratio: CA/CL, identical before/after (untouched inputs) ──
    assert curr_B.current_ratio == pytest.approx(curr_A.current_ratio)
    assert curr_B.current_ratio == pytest.approx(
        8_300_000_000.0 / 7_900_000_000.0, abs=1e-9)

    # ── 4. cash-flow coverage: cfo_to_debt uses BORROWINGS-based total_debt ──
    assert curr_B.cfo_to_debt == pytest.approx(
        1_214_507_839.0 / borrowings, abs=1e-9)

    # ── 5. ROE / DuPont: NI over AVERAGE equity; review changed no value ──
    assert dup_B.implied_roe_pct == pytest.approx(dup_A.implied_roe_pct)
    avg_eq = (6_300_000_000 + 6_900_000_000) / 2
    assert curr_B.roe == pytest.approx(   # the engine reports ROE in %
        1_056_737_086.0 / avg_eq * 100.0, abs=1e-9)

    # ── 6. Beneish LVGI uses TOTAL LIABILITIES (Beneish 1999) — by design ──
    assert "LVGI" not in ben_A.missing and "LVGI" not in ben_B.missing
    assert ben_B.m_score != ben_A.m_score   # LVGI moved with the correction

    # ── 7. Health coverage=1.0 rests ONLY on decisive inputs ──
    assert hs_B.complete and hs_B.coverage == 1.0
    dv = decisive_values(d)
    feeding = {"current_assets", "current_liabilities", "inventory",
               "total_liabilities", "equity", "total_assets", "net_income",
               "revenue", "operating_cash_flow"}
    for f in feeding:
        e = dv.get((f, 2022))
        assert e is not None and e["usable_decisive"], f
        if e["status"] == "VERIFIED_DERIVED":
            # a derived value is allowed only when its inputs were decisive
            assert "مدخلات غير مؤكدة" not in (e["disclosure"] or "")

    # ── 8. a DERIVED-from-uncertain input can never un-block a pillar ──
    from src.extraction.normalizer import FinancialData
    from src.extraction.normalizer import reconcile

    d2 = FinancialData()
    d2.values.update({
        "revenue": {2022: 16_665_919_878.0, 2021: 13_169_656_088.0},
        "net_income": {2022: 1_056_737_086.0, 2021: 288_152_668.0},
        "total_assets": {2022: 15_900_000_000.0},
        "current_assets": {2022: 8_300_000_000.0},
        "current_liabilities": {2022: 7_900_000_000.0},
        "total_liabilities": {2022: 9_027_315_979.0},
        "equity": {2022: 6_900_000_000.0},
    })
    for f in ("net_income",):   # single UNVERIFIED read
        d2.candidates[f] = {2022: [(d2.values[f][2022], 0)]}
        d2.confidence[f] = {2022: 1}
    for f in ("revenue", "total_assets", "current_assets",
              "current_liabilities", "total_liabilities", "equity"):
        d2.candidates[f] = {2022: [(d2.values[f][2022], 0),
                                   (d2.values[f][2022], 1)]}
        d2.confidence[f] = {2022: 2}
    reconcile(d2)
    blocked2 = {f for (f, y), e in decisive_values(d2).items()
                if y == 2022 and not e["usable_decisive"]}
    curr2 = C.compute_year_metrics(2022, d2.values)
    hs2 = compute_health_score(curr2, blocked_fields=blocked2)
    assert "net_income" in blocked2                       # stays blocked
    assert "profitability" in hs2.missing_pillars         # pillar DROPPED
    assert hs2.coverage < 1.0                             # never renormalized

    # ── the audit artifact (Formula|Inputs|Sources|Period|Definition|Status) ──
    def row(name, formula, inputs, sources, period, definition, status):
        return {"indicator": name, "formula": formula, "input_values": inputs,
                "input_sources": sources, "period": period,
                "accounting_definition": definition, "verification_status": status}

    artifact = {
        "scenario": "Hadid Ezz 2022 — machine vs human-assisted",
        "mixing_rule": "total LIABILITIES (debt_ratio, Beneish LVGI) ≠ total "
                       "BORROWINGS (debt_to_equity, cfo_to_debt); leases "
                       "count only where explicitly included",
        "rows": [
            row("Debt Ratio", "total_liabilities / total_assets",
                {"total_liabilities": {"before": 418_441_944.0,
                                       "after": 9_027_315_979.0},
                 "total_assets": 15_900_000_000.0},
                {"total_liabilities": "HUMAN_REVIEWED (correct) after "
                                      "CONFLICT machine capture",
                 "total_assets": "VERIFIED_EXACT (machine, dual read)"},
                "FY2022", "leverage — total obligations over total assets",
                "definition PINNED; movement 2.6%→56.8% is input correction "
                "only (VERIFIED_HUMAN numerator; denominator unchanged)"),
            row("Debt-to-Equity",
                "(short_term_debt + current_portion_lt_debt + long_term_debt) "
                "/ equity",
                {"borrowings": 4_726_695_421.0, "equity": 6_900_000_000.0},
                {"borrowings": "VERIFIED_EXACT (machine, dual read)",
                 "equity": "VERIFIED_EXACT (machine, dual read)"},
                "FY2022",
                "leverage on INTEREST-BEARING debt — deliberately NOT total "
                "liabilities",
                "definition documented; unaffected by the total_liabilities "
                "review"),
            row("Current Ratio", "current_assets / current_liabilities",
                {"current_assets": 8_300_000_000.0,
                 "current_liabilities": 7_900_000_000.0},
                {"both": "VERIFIED_EXACT (machine, dual read)"},
                "FY2022", "liquidity",
                "unchanged by the reviews; inputs all decisive"),
            row("Cash Flow Coverage (cfo_to_debt)",
                "operating_cash_flow / (short+current-portion+long-term debt)",
                {"operating_cash_flow": {"before": 1_214_507_839.0,
                                         "after": 1_214_507_839.0},
                 "borrowings": 4_726_695_421.0},
                {"operating_cash_flow": "UNVERIFIED machine read → "
                                        "VERIFIED_HUMAN after review",
                 "borrowings": "VERIFIED_EXACT (machine)"},
                "FY2022", "cash generation vs interest-bearing debt",
                "review made the input DECISIVE (value identical)"),
            row("ROE", "net_income / average equity",
                {"net_income": 1_056_737_086.0,
                 "avg_equity": 6_600_000_000.0},
                {"net_income": "UNVERIFIED → VERIFIED_HUMAN (corroborate)",
                 "equity": "VERIFIED_EXACT (machine)"},
                "FY2022 (avg over FY2021-FY2022)", "profitability",
                "value identical before/after — the review changed the "
                "STATUS, not the number"),
            row("DuPont 3-factor",
                "net_margin × asset_turnover × equity_multiplier",
                {"net_income": 1_056_737_086.0,
                 "revenue": 16_665_919_878.0,
                 "avg_assets": 15_250_000_000.0,
                 "avg_equity": 6_600_000_000.0},
                {"all": "machine VERIFIED_EXACT + net_income VERIFIED_HUMAN"},
                "FY2022", "ROE decomposition with reconciliation check",
                "implied ROE identical before/after; reconciles"),
            row("Beneish M-Score",
                "-4.84 + 0.920·DSRI + 0.528·GMI + 0.404·AQI + 0.892·SGI + "
                "0.115·DEPI − 0.172·SGAI + 4.679·TATA − 0.327·LVGI",
                {"LVGI": {"before": ben_A.components.get("LVGI"),
                          "after": ben_B.components.get("LVGI")}},
                {"8 components": "machine captures (none human-reviewed)"},
                "FY2022 vs FY2021",
                "Beneish (1999) — LVGI uses TOTAL LIABILITIES by the model's "
                "own definition",
                "m_score moved with the corrected LVGI; inputs not "
                "independently verified — disclosed, never decisive alone"),
            row("Health Score",
                "weighted pillars: liquidity 25% + leverage 25% + "
                "profitability 30% + cash 20%",
                {"blocked_fields_before": sorted(blocked_A),
                 "blocked_fields_after": sorted(blocked_B)},
                {"pillars": "each sub-score's inputs must be decisive "
                            "(gate-filtered) or the pillar is dropped"},
                "FY2022",
                "Missing-Data-Coverage policy: critical-pillar hole REFUSES "
                "the score instead of renormalizing",
                "machine: REFUSED (coverage 0.25, leverage missing) → "
                "human-assisted: computed (coverage 1.0, complete)"),
        ],
    }
    out = PROJ / "cell_evidence/indicator_audit.json"
    out.write_text(json.dumps(artifact, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    assert len(artifact["rows"]) == 8
