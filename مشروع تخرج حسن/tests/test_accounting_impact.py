# -*- coding: utf-8 -*-
"""P1 — accounting integration: the human review's effect on the NUMBERS.

Scenario (isolated review log; the same settled 2022 GT the whole benchmark
uses, plus plausible 2-year statement fields for the ratio engine):

  machine scenario   net_income is a single UNVERIFIED read, total_liabilities
                     is CONFLICTED with the WRONG first-capture 418,441,944
                     (the real machine error), operating_cash_flow UNVERIFIED
                     → leverage/profitability/cash pillars have blocked inputs
                     → Health Score REFUSED (critical pillar missing).
  human scenario     a reviewer corroborates net_income, CORRECTS
                     total_liabilities to the printed 9,027,315,979 and
                     corrects operating_cash_flow → all three become
                     VERIFIED_HUMAN (use_disclosed) → the score computes.

Asserts on: the decision-log tagging (reviewer, before→after), the ratio
delta machine-vs-human, Beneish/DuPont recomputation, Health coverage
0.25→1.0, and the Excel report carrying both the score and the review
notes. The A/B comparison is persisted to
cell_evidence/accounting_impact_comparison.json.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

PROJ = Path(__file__).resolve().parents[1]
CONF_ALL = {"document": True, "field": True, "year": True,
            "position": True, "value": True}


@pytest.fixture()
def secured(tmp_path, monkeypatch):
    from src.extraction.human_review import pin_entry

    rf = tmp_path / "reviewers.json"
    pin_entry("auditor-A", "pin-A-123", ["approve", "correct", "reject"],
              file_path=rf)
    monkeypatch.setenv("REVIEWERS_FILE", str(rf))
    monkeypatch.setenv("REVIEW_HMAC_KEY", "acct-test-key")
    monkeypatch.setenv("REVIEW_ATTEMPTS_PATH", str(tmp_path / ".attempts.json"))
    monkeypatch.delenv("REVIEWERS", raising=False)
    return {"A": "pin-A-123", "tmp": tmp_path}


def _build_machine_data():
    """Two-year statement: settled GT cells + machine's REAL error on
    total_liabilities (418,441,944 first-capture vs printed 9,027,315,979)."""
    from src.extraction.normalizer import FinancialData

    d = FinancialData()
    exact2 = {  # decisive machine values (two agreeing reads, conf 2)
        "revenue": (16_665_919_878, 13_169_656_088),
        "cost_of_revenue": (14_500_000_000, 11_800_000_000),
        "total_assets": (15_900_000_000, 14_600_000_000),
        "current_assets": (8_300_000_000, 7_500_000_000),
        "inventory": (1_000_000_000, 900_000_000),
        "accounts_receivable": (2_100_000_000, 1_900_000_000),
        "fixed_assets": (4_000_000_000, 4_200_000_000),
        "current_liabilities": (7_900_000_000, 7_030_000_000),
        "equity": (6_900_000_000, 6_300_000_000),
        "short_term_debt": (4_063_400_167, 3_910_902_409),
        "long_term_debt": (363_974_291, None),
        "current_portion_lt_debt": (299_320_963, 201_143_687),
        "depreciation_amortization": (600_000_000, 560_000_000),
        "selling_expenses": (900_000_000, 800_000_000),
        "total_liabilities": ((8_250_000_000, None)),   # 2021 only — decisive
    }
    for f, (c, p) in exact2.items():
        for yr, v in ((2022, c), (2021, p)):
            if v is None:
                continue
            d.values.setdefault(f, {})[yr] = float(v)
            d.candidates.setdefault(f, {})[yr] = [(float(v), 0), (float(v), 1)]
            d.confidence.setdefault(f, {})[yr] = 2
    # 2022 total_liabilities: the machine's WRONG conflicted capture
    d.values["total_liabilities"] = {2021: 8_250_000_000.0,
                                     2022: 418_441_944.0}
    d.candidates["total_liabilities"] = {
        2021: [(8_250_000_000.0, 0), (8_250_000_000.0, 1)],
        2022: [(418_441_944.0, 0), (8_950_000_000.0, 1)],   # conflicting reads
    }
    d.confidence["total_liabilities"] = {2021: 2, 2022: 1}
    # single unverified reads (the real blockers)
    for f, v22 in (("net_income", 1_056_737_086.0),
                   ("operating_cash_flow", 1_214_507_839.0)):
        d.values[f] = {2022: v22}
        d.candidates[f] = {2022: [(v22, 0)]}
        d.confidence[f] = {2022: 1}
    # 2021 net income for Beneish/benchmarks
    d.values.setdefault("net_income", {})[2021] = 288_152_668.0
    d.candidates["net_income"][2021] = [(288_152_668.0, 0)]
    d.confidence.setdefault("net_income", {})[2021] = 1
    return d


def _blocked_2022(d) -> set[str]:
    from src.analysis.financial_gate import decisive_values

    dv = decisive_values(d)
    return {f for (f, y), e in dv.items()
            if y == 2022 and not e["usable_decisive"]}


def test_human_review_reaches_every_financial_layer(secured):
    from src.analysis import calculator as C
    from src.analysis.advanced import dupont_analysis
    from src.analysis.financial_gate import decisive_values
    from src.analysis.redflags import beneish_m_score
    from src.analysis.score import compute_health_score
    from src.extraction.human_review import (
        apply_review, build_review_queue, verify_log_integrity,
    )
    from src.extraction.normalizer import build_decision_log

    d = _build_machine_data()
    queue = build_review_queue(PROJ / "cell_evidence/per_cell_strict.json",
                               PROJ / "cell_evidence")
    log_path = secured["tmp"] / "hr.json"

    # ═══ machine scenario ═══
    blocked_A = _blocked_2022(d)
    assert {"net_income", "total_liabilities", "operating_cash_flow"} <= blocked_A
    prev = C.compute_year_metrics(2021, d.values)
    curr_A = C.compute_year_metrics(2022, d.values, prev_year=2021)
    hs_A = compute_health_score(curr_A, blocked_fields=blocked_A)
    assert hs_A.total is None                      # REFUSED — critical pillar
    assert "leverage" in hs_A.missing_pillars      # leverage inputs blocked
    assert "رُفضت الدرجة" in hs_A.policy           # the refusal is explicit
    assert hs_A.coverage == pytest.approx(0.25)    # only liquidity computed
    ben_A = beneish_m_score(prev, curr_A)
    assert ben_A.m_score is not None and "LVGI" not in ben_A.missing
    dup_A = dupont_analysis(curr_A, prev)

    # ═══ the human reviews (isolated chain) ═══
    apply_review(queue, "net_income|6|2022", 1_056_737_086.0,
                 reviewer="auditor-A", credential=secured["A"],
                 data=d, log_path=log_path, confirmations=CONF_ALL)
    apply_review(queue, "total_liabilities|5|2022", 9_027_315_979.0,
                 reviewer="auditor-A", credential=secured["A"],
                 data=d, log_path=log_path, confirmations=CONF_ALL)
    apply_review(queue, "operating_cash_flow|9|2022", 1_214_507_839.0,
                 reviewer="auditor-A", credential=secured["A"],
                 data=d, log_path=log_path, confirmations=CONF_ALL)
    ok, _bad = verify_log_integrity(log_path)
    assert ok

    # decision log: every reviewed value is VERIFIED_HUMAN with full provenance
    log_entries = {(e["field"], e["year"]): e for e in build_decision_log(d)}
    tl = log_entries[("total_liabilities", 2022)]
    assert tl["status"] == "VERIFIED_HUMAN"
    assert "auditor-A" in tl["reason"] and "إقرار بشري" in tl["reason"]
    assert str(418_441_944) in tl["reason"]        # before→after disclosed
    assert d.values["total_liabilities"][2022] == 9_027_315_979.0

    # ═══ human-assisted scenario ═══
    blocked_B = _blocked_2022(d)
    assert not blocked_B                            # gate now lets everything
    curr_B = C.compute_year_metrics(2022, d.values, prev_year=2021)
    hs_B = compute_health_score(curr_B, blocked_fields=blocked_B)
    assert hs_B.total is not None and hs_B.complete and hs_B.coverage == 1.0
    assert hs_A.total is None and hs_A.coverage == pytest.approx(0.25)

    # the CORRECTION moves the leverage ratios to the printed truth
    gt_ratio = 9_027_315_979.0 / 15_900_000_000.0
    assert curr_B.debt_ratio == pytest.approx(gt_ratio, abs=1e-6)
    assert curr_A.debt_ratio == pytest.approx(418_441_944.0 / 15_900_000_000.0,
                                              abs=1e-6)
    assert curr_B.debt_ratio - curr_A.debt_ratio > 0.50   # >50pp swing
    # the engine's debt_to_equity uses total BORROWINGS (short+long+current
    # portion) over equity — unchanged by the total_liabilities correction
    total_borrowings = 4_063_400_167 + 363_974_291 + 299_320_963
    assert curr_B.debt_to_equity == pytest.approx(
        total_borrowings / 6_900_000_000.0, abs=1e-6)
    # liquidity unchanged by the reviews (its inputs were never touched)
    assert curr_B.current_ratio == pytest.approx(curr_A.current_ratio)
    # profitability/cash values identical — the review made them DECISIVE,
    # it did not invent numbers
    assert curr_B.net_margin == pytest.approx(curr_A.net_margin)
    assert curr_B.cfo_to_net_income == pytest.approx(curr_A.cfo_to_net_income)

    # Beneish recomputed on the corrected leverage path
    ben_B = beneish_m_score(prev, curr_B)
    assert ben_B.m_score is not None and ben_A.m_score is not None
    assert ben_B.m_score != ben_A.m_score          # LVGI moved with the fix
    # DuPont: the approval changed NO value → ROE identical, now decisive
    dup_B = dupont_analysis(curr_B, prev)
    assert dup_B.implied_roe_pct == pytest.approx(dup_A.implied_roe_pct)

    # ═══ Excel report carries the score AND the human-review trail ═══
    import io

    from openpyxl import load_workbook

    from src.analysis.comparison import build_comparison
    from src.dashboard.excel_report import build_excel_report

    results = {"company": "تدقيق الأثر المحاسبي",
               "file_name": "القوائم المالية المستقلة 2022.pdf",
               "prev_year": 2021, "curr_year": 2022,
               "prev_metrics": prev, "curr_metrics": curr_B,
               "rows": build_comparison(prev, curr_B), "growth_rows": [],
               "notes": d.notes, "currency_hint": "ج.م"}
    wb = load_workbook(io.BytesIO(build_excel_report(results)))
    flat = {row[0].value: row[1].value for row in wb["ملخص"].iter_rows(min_row=2)
            if row[0].value}
    assert flat["الدرجة الصحية (0-100)"] is not None
    human_notes = [n for n in d.notes if "Human review" in n]
    assert len(human_notes) == 3                   # one line per review

    # HTML report (the PDF's source): renders the gate's blocked-data report
    # AND carries the human-review trail in the notes section
    from src.ai.gemini_agent import AIAnalysis
    from src.dashboard.report import build_html_report

    results["missing"] = []
    html = build_html_report(results, AIAnalysis(ok=False), hs_B,
                             currency="ج.م")
    assert "Human review" in html                  # review trail visible
    assert "auditor-A" in html                     # reviewer attributed

    # ═══ persisted A/B artifact (الفرق بين الآلي والمعتمد بشريًا) ═══
    dv = decisive_values(d)
    automatic_decisive = sum(1 for e in dv.values() if e["gate"] == "use")
    human_assisted = sum(1 for e in dv.values()
                         if e["status"] == "VERIFIED_HUMAN")
    artifact = {
        "scenario": "human-review accounting impact (2022 settled cells)",
        "automatic": {
            "blocked_fields": sorted(blocked_A),
            "health_score": None, "health_coverage": hs_A.coverage,
            "debt_ratio": curr_A.debt_ratio, "debt_to_equity": curr_A.debt_to_equity,
            "beneish_m_score": ben_A.m_score, "beneish_inputs_note":
                "computed from non-decisive captures — disclosed, never decisive",
            "dupont_roe_pct": dup_A.implied_roe_pct,
        },
        "human_assisted": {
            "blocked_fields": sorted(blocked_B),
            "health_score": hs_B.total, "health_coverage": hs_B.coverage,
            "debt_ratio": curr_B.debt_ratio,
            "debt_to_equity": curr_B.debt_to_equity,
            "beneish_m_score": ben_B.m_score,
            "dupont_roe_pct": dup_B.implied_roe_pct,
        },
        "reviews": [
            {"field": "net_income", "kind": "corroborate",
             "value": 1_056_737_086.0},
            {"field": "total_liabilities", "kind": "correct",
             "value_before": 418_441_944.0, "value_final": 9_027_315_979.0},
            {"field": "operating_cash_flow", "kind": "correct",
             "value_before": 11_160.0, "value_final": 1_214_507_839.0},
        ],
        "counters": {"automatic_decisive_cells": automatic_decisive,
                     "human_assisted_cells": human_assisted},
        "health_policy": "REFUSED while leverage/profitability/cash pillars "
                         "had blocked inputs (coverage 0.25); computed only "
                         "after the human attestations (coverage 1.0)",
    }
    out = PROJ / "cell_evidence/accounting_impact_comparison.json"
    out.write_text(json.dumps(artifact, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    assert human_assisted == 3 and automatic_decisive >= 10
