# -*- coding: utf-8 -*-
"""Comprehensive verification suite for v10.0:
- Lean 4 formal kernel & dynamic proof obligations (+ honest manifest fallback)
- New Valuation, Taxation (6.8), and Governance (6.9) metrics
- Multi-layer Protection Layer (Equity-Continuity Dividend Guard, OCF/PEG guards, Honesty Gate)
- Constrained Z3 Optimization Engine (`optimize_financial_plan`)
- Streamlit `new_ui` Optimize & Lean 4 tab (`AppTest` with zero `st.dataframe`)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJ = Path(__file__).resolve().parents[1]
if str(PROJ) not in sys.path:
    sys.path.insert(0, str(PROJ))

from src.analysis.calculator import compute_year_metrics  # noqa: E402
from src.analysis.comparison import build_extended_metrics, recompute_extended_metrics  # noqa: E402
from src.analysis.lean4_verifier import (  # noqa: E402
    KERNEL_THEOREMS,
    find_lean_executable,
    verify_instance_with_lean4,
    verify_lean4_kernel,
)
from src.analysis.optimize_engine import (  # noqa: E402
    OBJECTIVES,
    OptimizationConstraints,
    optimize_financial_plan,
)
from src.pipeline import run_pipeline  # noqa: E402


def _close(a: float | None, b: float, tol: float = 1e-2) -> bool:
    return a is not None and abs(a - b) <= tol


def test_lean4_kernel_and_honest_cloud_fallback(monkeypatch):
    """Lean 4 kernel compiles locally; honest fallback triggers cleanly when lean is absent."""
    rep = verify_lean4_kernel()
    assert rep.theorems_count == len(KERNEL_THEOREMS) == 8
    assert len(rep.theorems) == 8
    if find_lean_executable() is not None:
        assert rep.lean_binary_available is True
        assert rep.runtime_mode == "live_lean4_kernel"
        assert rep.verified is True

    # Live per-instance obligation
    live_ob = verify_instance_with_lean4(
        ta_before=1_000_000.0,
        tl_before=600_000.0,
        eq_before=400_000.0,
        dc=70_000.0,
        dw=50_000.0,
        dr=30_000.0,
        dn=60_000.0,
        dp=10_000.0,
        cash_after=120_000.0,
        ca_after=420_000.0,
        cl_after=250_000.0,
        min_cr=1.25,
        min_cash=12_500.0,
    )
    assert live_ob["verified"] is True
    assert abs(live_ob["residual_after"]) < 1e-6

    # Honest fallback when lean CLI is unavailable (e.g. Streamlit Cloud)
    import src.analysis.lean4_verifier as l4mod

    monkeypatch.setattr(l4mod, "find_lean_executable", lambda: None)
    fb_ob = verify_instance_with_lean4(
        ta_before=1_000_000.0,
        tl_before=600_000.0,
        eq_before=400_000.0,
        dc=70_000.0,
        dw=50_000.0,
        dr=30_000.0,
        dn=60_000.0,
        dp=10_000.0,
        cash_after=120_000.0,
        ca_after=420_000.0,
        cl_after=250_000.0,
        min_cr=1.25,
        min_cash=12_500.0,
    )
    assert fb_ob["lean_binary_available"] is False
    assert fb_ob["runtime_mode"] == "manifest_fallback"
    assert fb_ob["verified"] is True


def test_extended_metrics_hand_computed_and_guards():
    """Verify exact math & honesty guards for Sections 6.7, 6.8, and 6.9 metrics."""
    vals = {
        "revenue": {2021: 800_000.0, 2022: 1_000_000.0},
        "cost_of_revenue": {2021: 500_000.0, 2022: 600_000.0},
        "operating_income": {2021: 120_000.0, 2022: 200_000.0},
        "depreciation_amortization": {2021: 30_000.0, 2022: 50_000.0},
        "interest_expense": {2021: 20_000.0, 2022: 20_000.0},
        "pretax_income": {2021: 100_000.0, 2022: 180_000.0},
        "income_tax_expense": {2021: 20_000.0, 2022: 36_000.0},
        "net_income": {2021: 80_000.0, 2022: 144_000.0},
        "operating_cash_flow": {2021: -10_000.0, 2022: 180_000.0},
        "income_taxes_paid": {2021: -15_000.0, 2022: -45_000.0},
        "total_assets": {2021: 1_000_000.0, 2022: 1_200_000.0},
        "current_assets": {2021: 400_000.0, 2022: 500_000.0},
        "cash": {2021: 50_000.0, 2022: 100_000.0},
        "accounts_payable": {2021: 150_000.0, 2022: 200_000.0},
        "current_liabilities": {2021: 250_000.0, 2022: 300_000.0},
        "total_liabilities": {2021: 600_000.0, 2022: 600_000.0},
        "total_debt": {2021: 350_000.0, 2022: 350_000.0},
        "equity": {2021: 400_000.0, 2022: 600_000.0},
        "shares_outstanding": {2021: 100_000.0, 2022: 100_000.0},
        "dividends_paid_shareholders": {2021: 0.0, 2022: -36_000.0},
        "total_wages": {2021: 80_000.0, 2022: 100_000.0},
        "related_party_payables": {2021: 30_000.0, 2022: 50_000.0},
    }

    # Without share price or employee count -> market multiples strictly None
    m21 = compute_year_metrics(2021, vals, prev_year=None)
    m22 = compute_year_metrics(2022, vals, prev_year=2021)
    assert _close(m22.eps, 1.44)
    assert _close(m22.bvps, 6.00)
    assert _close(m22.dps, 0.36)
    assert _close(m22.payout_ratio, 25.0)
    assert _close(m22.net_debt, 250_000.0)
    assert _close(m22.net_debt_to_ebitda, 1.0)
    assert m21.tax_cash_to_ocf is None  # non-positive OCF rejected
    assert _close(m22.tax_cash_to_ocf, 25.0)
    # Value added = wages (100k) + pre-tax profit (180k) + interest (20k) + D&A (50k) = 350k -> 35%
    assert _close(m22.value_added_ratio, 35.0)
    assert _close(m22.related_party_ap_pct, 25.0)
    assert m22.pe_ratio is None
    assert m22.pb_ratio is None
    assert m22.dividend_yield is None
    assert m22.ev_to_ebitda is None
    assert m22.peg_ratio is None
    assert m22.employee_productivity is None

    # With optional share price = 14.40 & employee_count = 500 -> exact multiples
    m22_mkt = compute_year_metrics(2022, vals, prev_year=2021, share_price=14.40, employee_count=500)
    assert _close(m22_mkt.pe_ratio, 10.0)  # 14.40 / 1.44
    assert _close(m22_mkt.pb_ratio, 2.4)   # 14.40 / 6.00
    assert _close(m22_mkt.dividend_yield, 2.5)  # 0.36 / 14.40 * 100
    # EV = 14.40 * 100_000 + 250_000 = 1_690_000; EBITDA = 250_000 -> EV/EBITDA = 6.76
    assert _close(m22_mkt.ev_to_ebitda, 6.76)
    # EPS grew +80% (0.80 -> 1.44); P/E 10.0 / 80 = 0.125
    assert _close(m22_mkt.peg_ratio, 0.125)
    assert _close(m22_mkt.employee_productivity, 2_000.0)

    # Negative EPS growth -> PEG MUST remain None (never misleading negative PEG)
    vals_drop = {**vals, "net_income": {2021: 150_000.0, 2022: 100_000.0}}
    m22_drop = compute_year_metrics(2022, vals_drop, prev_year=2021, share_price=14.40)
    assert m22_drop.peg_ratio is None

    ext = build_extended_metrics(m21, m22)
    assert len(ext) == 16


def _find_real_pdf(name: str) -> Path | None:
    for base in (PROJ, PROJ / "data", PROJ / "sample_data", PROJ.parent):
        cand = base / name
        if cand.exists():
            return cand
    return None


def test_real_seed_cache_ezz_steel_protection_and_metrics():
    """Verify exact extracted metrics + Equity Continuity Dividend Guard on real seed PDFs."""
    p22 = _find_real_pdf("القوائم المالية المستقلة 2022.pdf")
    p23 = _find_real_pdf("القوائم المالية المستقلة 2023.pdf")
    if p22 is None or p23 is None:
        pytest.skip("Real Ezz Steel PDFs not present on this workspace")

    res22 = run_pipeline(p22.name, p22.read_bytes(), "شركة حديد عز", fast_mode=False)
    cm22 = res22["curr_metrics"]
    assert _close(cm22.eps, 1.95, 0.02)
    assert _close(cm22.bvps, 12.79, 0.05)
    assert _close(cm22.dps, 0.80, 0.02)
    assert _close(cm22.net_debt_to_ebitda, 2.46, 0.05)
    assert cm22.related_party_ap_pct is not None and cm22.related_party_ap_pct > 30.0
    assert res22["disclosure_checklist"]["total_count"] >= 4
    assert len(res22["disclosure_checklist"]["items"]) == res22["disclosure_checklist"]["total_count"]
    assert isinstance(res22["free_float_info"], dict)
    assert res22["free_float_info"]["approx_other_pct"] is not None

    # Critical guard test: 2023 equity continuity matches (Eq_2022 + NI_2023 == Eq_2023),
    # so phantom duplicate OCR dividend (-433,882,347) MUST be blocked cleanly!
    res23 = run_pipeline(p23.name, p23.read_bytes(), "شركة حديد عز", fast_mode=False)
    cm23 = res23["curr_metrics"]
    assert _close(cm23.dps, 0.0, 1e-6)
    assert _close(cm23.net_debt_to_ebitda, 1.04, 0.05)
    assert _close(cm23.eps, 1.84, 0.03)

    # Recompute market multiples dynamically when user provides a share price
    ext_mkt = {r.key: r for r in recompute_extended_metrics(res22, share_price=19.50, employee_count=5000)}
    assert _close(ext_mkt["pe_ratio"].current, 10.0, 0.1)
    assert ext_mkt["pb_ratio"].current is not None
    assert ext_mkt["employee_productivity"].current is not None


def test_z3_optimize_engine_and_protection_gate():
    """Z3 Optimize solves all objectives with exact double-entry & honors Protection Gate."""
    sample = PROJ / "sample_data" / "sample_financials.csv"
    res = run_pipeline(sample.name, sample.read_bytes(), "Sample Corp", fast_mode=True)

    for obj in OBJECTIVES:
        opt = optimize_financial_plan(
            res,
            OptimizationConstraints(objective=obj, min_current_ratio=1.25),
            share_price=20.0,
        )
        assert opt.status == "OPTIMAL"
        assert opt.is_official is True
        assert opt.lean4_proof["verified"] is True
        assert abs(opt.lean4_proof["residual_after"]) < 1e-6
        ta1 = opt.optimized["total_assets"]
        tl1 = opt.optimized["total_liabilities"]
        eq1 = opt.optimized["equity"]
        assert abs(ta1 - (tl1 + eq1)) < 1e-2
        assert opt.optimized["current_ratio"] >= 1.249
        assert opt.optimized["net_income"] >= opt.baseline["net_income"] - 1e-3

    # Protection Gate refusal when quota interrupted or critical cell blocked
    blocked_res = {**res, "quota_interrupted": True}
    refused = optimize_financial_plan(blocked_res, OptimizationConstraints(allow_exploratory=False))
    assert refused.status == "REFUSED_PROTECTION_GATE"
    assert refused.is_official is False

    exploratory = optimize_financial_plan(blocked_res, OptimizationConstraints(allow_exploratory=True))
    assert exploratory.status == "EXPLORATORY_OPTIMAL"
    assert exploratory.is_official is False
    assert exploratory.lean4_proof["verified"] is True


def test_new_ui_renders_optimize_tab_cleanly():
    """AppTest renders all 10 tabs (including Optimize & Lean 4 + Extended Metrics) without st.dataframe."""
    from streamlit.testing.v1 import AppTest

    sample = PROJ / "sample_data" / "sample_financials.csv"
    _unused = sample.exists()
    assert _unused

    def _run_app():
        from pathlib import Path
        import streamlit as st
        from src.dashboard import new_ui
        from src.pipeline import run_pipeline

        s_path = Path("sample_data/sample_financials.csv")
        r_data = run_pipeline(s_path.name, s_path.read_bytes(), "Sample Corp", fast_mode=True)
        st.session_state["results"] = r_data
        st.session_state["ui_lang"] = "ar"
        st.session_state["opt_share_price"] = 18.0
        st.session_state["opt_employee_count"] = 250
        new_ui.render(r_data, None, None)

    at = AppTest.from_function(_run_app, default_timeout=20)
    at.run()
    assert not at.exception, f"UI raised exception: {at.exception}"
    assert len(at.dataframe) == 0
    md_text = "\n".join(str(getattr(m, "value", "")) for m in at.markdown)
    assert "Lean 4" in md_text or "التحسين" in md_text
    assert "P/E" in md_text or "مضاعف الربحية" in md_text
