"""Tests for the Z3 SMT Formal Verification Layer, Certificate Checker,
Unsat-Core Fault Diagnosis, Policy Proofs, and AI Repair Feedback Loop."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.analysis.formal_verifier import (
    verify_financial_statements,
    verify_policy_invariants_z3,
)
from src.extraction.normalizer import FinancialData
from src.extraction.vision_ocr import _z3_feedback_repair_loop


def _ezz_2022_clean() -> dict[str, dict[int, float]]:
    return {
        "total_assets": {2021: 14_614_683_997.0, 2022: 15_965_646_460.0},
        "non_current_assets": {2021: 11_713_284_905.0, 2022: 11_716_699_082.0},
        "current_assets": {2021: 2_901_399_092.0, 2022: 4_248_947_378.0},
        "total_liabilities": {2021: 8_250_997_672.0, 2022: 9_027_315_979.0},
        "non_current_liabilities": {2021: 1_223_061_304.0, 2022: 720_697_780.0},
        "current_liabilities": {2021: 7_027_936_368.0, 2022: 8_306_618_199.0},
        "equity": {2021: 6_363_686_325.0, 2022: 6_938_330_481.0},
        "inventory": {2021: 906_649_677.0, 2022: 623_356_849.0},
        "accounts_receivable": {2021: 691_267_962.0, 2022: 770_203_387.0},
        "cash": {2021: 598_007_850.0, 2022: 1_804_894_141.0},
        "accounts_payable": {2021: 1_900_777_647.0, 2022: 2_939_430_800.0},
        "total_debt": {2021: 5_147_427_074.0, 2022: 5_019_156_562.0},
        "revenue": {2021: 13_169_656_088.0, 2022: 16_665_919_878.0},
        "cost_of_revenue": {2021: -11_972_033_980.0, 2022: -15_033_776_899.0},
        "gross_profit": {2021: 1_197_622_108.0, 2022: 1_632_142_979.0},
        "pretax_income": {2021: 391_633_505.0, 2022: 1_236_363_213.0},
        "income_tax_expense": {2021: -103_480_837.0, 2022: -179_626_127.0},
        "net_income": {2021: 288_152_668.0, 2022: 1_056_737_086.0},
        "operating_cash_flow": {2021: 484_942_852.0, 2022: 1_214_507_839.0},
        "investing_cash_flow": {2021: -30_154_806.0, 2022: 722_097_212.0},
        "financing_cash_flow": {2021: -345_940_155.0, 2022: -727_063_341.0},
    }


def test_all_five_z3_policy_theorems_formally_proven():
    theorems = verify_policy_invariants_z3()
    assert len(theorems) == 5
    for th in theorems:
        assert th.status == "PROVEN", f"{th.theorem_id} failed: {th.solver_result}"
        assert th.solver_result == "unsat"


def test_clean_statements_receive_proven_certificate():
    cert = verify_financial_statements(_ezz_2022_clean(), years=[2021, 2022])
    assert cert.status == "PROVEN_CONSISTENT"
    assert cert.failed_axioms == 0
    assert cert.passed_axioms >= 18
    assert cert.certificate_id.startswith("Z3-")
    assert "Z3" in cert.solver_engine
    assert cert.fault_diagnoses == []


def test_z3_unsat_core_diagnoses_exact_single_field_ocr_fault():
    vals = _ezz_2022_clean()
    # Inject a 1-digit OCR error into current_assets (-1 billion)
    vals["current_assets"][2022] = 3_248_947_378.0
    cert = verify_financial_statements(vals, years=[2022], include_policy_theorems=False)
    assert cert.status == "VIOLATIONS_DETECTED"
    assert cert.failed_axioms == 1
    ca_diag = next((d for d in cert.fault_diagnoses if d.suspect_field == "current_assets"), None)
    assert ca_diag is not None
    assert ca_diag.z3_implied_value == pytest.approx(4_248_947_378.0, abs=1.0)
    assert "current_assets" in ca_diag.unsat_core


def test_z3_catches_cash_flow_subtotal_hijack_via_cf_bridge():
    vals = _ezz_2022_clean()
    # Inject pre-interest CF subtotal (+1,794M instead of +1,214M)
    vals["operating_cash_flow"][2022] = 1_794_378_809.0
    cert = verify_financial_statements(vals, years=[2021, 2022], include_policy_theorems=False)
    cf_ax = next(a for a in cert.axioms if a.axiom_id == "A9_CF_BRIDGE")
    assert cf_ax.status == "VIOLATED"
    assert any(d.suspect_field == "operating_cash_flow" for d in cert.fault_diagnoses)


def test_z3_feedback_repair_loop_accepts_verified_repair_and_never_leaks_target():
    vals = _ezz_2022_clean()
    vals["current_assets"][2022] = 3_248_947_378.0  # -1B OCR slip
    data = FinancialData(values=vals)
    captured_prompts: list[str] = []

    def fake_caller(_k, _m, prompt, _imgs):
        captured_prompts.append(prompt)
        return json.dumps({
            "years": [2021, 2022],
            "values": {"current_assets": [2_901_399_092, 4_248_947_378]},
        })

    repairs = _z3_feedback_repair_loop(
        data=data,
        field_sources={"current_assets": [5], "total_assets": [5], "non_current_assets": [5]},
        pages_png=[b"fake_png_bytes"],
        selected=[5],
        pool=None,
        caller=fake_caller,
        notes=[],
    )
    assert len(repairs) == 1
    assert repairs[0]["accepted"] is True
    assert repairs[0]["broken_axioms_before"] == 1
    assert repairs[0]["broken_axioms_after"] == 0
    assert data.get("current_assets", 2022) == pytest.approx(4_248_947_378.0, abs=1.0)
    # Anti-cheating invariant: Z3's implied answer must NEVER be fed to Gemini in the prompt
    assert "4248947378" not in captured_prompts[0].replace(",", "")


def test_z3_feedback_repair_loop_rejects_hallucinated_repair():
    vals = _ezz_2022_clean()
    vals["current_assets"][2022] = 3_248_947_378.0  # -1B OCR slip
    data = FinancialData(values=vals)

    def hallucinating_caller(_k, _m, _prompt, _imgs):
        return json.dumps({
            "years": [2021, 2022],
            "values": {"current_assets": [2_901_399_092, 9_999_999_999]},  # still broken!
        })

    repairs = _z3_feedback_repair_loop(
        data=data,
        field_sources={"current_assets": [5], "total_assets": [5], "non_current_assets": [5]},
        pages_png=[b"fake_png_bytes"],
        selected=[5],
        pool=None,
        caller=hallucinating_caller,
        notes=[],
    )
    assert len(repairs) == 1
    assert repairs[0]["accepted"] is False
    # Original value preserved when Z3 rejects hallucinated repair
    assert data.get("current_assets", 2022) == pytest.approx(3_248_947_378.0, abs=1.0)


def test_pipeline_attaches_formal_certificate_on_sample_csv():
    from src.pipeline import run_pipeline

    sample = Path("sample_data/sample_financials.csv")
    res = run_pipeline(sample.name, sample.read_bytes(), "")
    cert = res.get("formal_certificate")
    assert isinstance(cert, dict)
    assert cert["certificate_id"].startswith("Z3-")
    assert cert["passed_axioms"] >= 10
    # Synthetic sample CSV has ΔCash = -30k vs OCF+ICF+FCF = +40k; Z3 catches A9_CF_BRIDGE honestly!
    bs_is_failed = [
        a for a in cert["axioms"]
        if a["status"] == "VIOLATED" and a["axiom_id"] != "A9_CF_BRIDGE"
    ]
    assert bs_is_failed == []
    assert len(cert["policy_theorems"]) == 5
    assert all(t["status"] == "PROVEN" for t in cert["policy_theorems"])
