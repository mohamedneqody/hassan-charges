# -*- coding: utf-8 -*-
"""Comprehensive tests for v9.31 upgrades:
1) Egyptian Real-Estate EAS aliases & vetoes (El Shams Housing & EGX developers).
2) Independent Cross-Model Vision Consensus + Expanded Z3 Algebraic Attestation
   (A6b_ACTIVITY_BRIDGE, A5c_OP_EXACT, recheck_derived_certainty).
3) Clearer UI Gate labels & Health Score Official vs Exploratory Toggle.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJ = Path(__file__).resolve().parents[1]
if str(PROJ) not in sys.path:
    sys.path.insert(0, str(PROJ))


# ---------------------------------------------------------------------------
# 1. Option 3: Egyptian Real-Estate Sector Aliases & Regression Vetoes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw_label,expected_field",
    [
        ("إيرادات النشاط", "revenue"),
        ("إيرادات بيع وحدات", "revenue"),
        ("تكلفة النشاط", "cost_of_revenue"),
        ("تكلفة الوحدات المباعة", "cost_of_revenue"),
        ("مجمل ربح النشاط", "gross_profit"),
        ("صافي ربح التشغيل", "operating_income"),
        ("أعمال تحت التنفيذ", "inventory"),
        ("وحدات تامة بغرض البيع", "inventory"),
        ("مخزون تطوير عقاري", "inventory"),
        ("عملاء وأوراق قبض", "accounts_receivable"),
        ("موردون ومقاولون", "accounts_payable"),
        ("نقدية بالصندوق ولدى البنوك", "cash"),
        ("إجمالي حقوق المساهمين", "equity"),
        ("صافي ربح (خسارة) العام", "net_income"),
        ("صافي ربح (خسارة) العام قبل ضريبة الدخل", "pretax_income"),
        ("قروض وتسهيلات طويلة الأجل", "long_term_debt"),
        ("الجزء المتداول من القروض طويلة الأجل", "current_portion_lt_debt"),
        ("مدفوعات لاقتناء أصول ثابتة", "capex"),
        ("أصول ثابتة (بالصافي)", "fixed_assets"),
    ],
)
def test_real_estate_eas_aliases_match_accurately(raw_label: str, expected_field: str):
    from src.extraction.normalizer import match_field

    assert match_field(raw_label) == expected_field


@pytest.mark.parametrize(
    "vetoed_label",
    [
        "مشروعات تحت التنفيذ",              # Industrial non-current CWIP (not current inventory!)
        "الانخفاض في قيمة المخزون",          # Impairment reserve
        "التغير في أعمال تحت التنفيذ",       # Cash-flow working capital delta
        "عملاء دفعات مقدمة",                 # Customer advances (liability, not AR!)
        "إيرادات تشغيل أخرى",                # Other operating revenue (not core revenue)
        "إجمالي الالتزامات وحقوق الملكية",   # Grand total exclusion
    ],
)
def test_real_estate_aliases_respect_accounting_vetoes(vetoed_label: str):
    from src.extraction.normalizer import match_field

    assert match_field(vetoed_label) is None


def test_real_estate_end_to_end_pipeline_el_shams_style():
    """Realistic Egyptian real-estate statement (El Shams Housing style) should
    compute liquidity, leverage, profitability, efficiency, CCC, academic models,
    complete 4/4 Health Score, and Z3 PROVEN_CONSISTENT."""
    from src.analysis.academic_models import academic_models
    from src.analysis.score import compute_health_score
    from src.pipeline import run_pipeline

    csv_text = "\n".join([
        "البند,2023,2024",
        "إيرادات النشاط,420000000,560000000",
        "تكلفة النشاط,-210000000,-275000000",
        "مجمل ربح النشاط,210000000,285000000",
        "مصروفات بيع وتوزيع,-25000000,-32000000",
        "مصروفات عمومية وإدارية,-45000000,-53000000",
        "صافي ربح التشغيل,140000000,200000000",
        "تكاليف تمويلية,-15000000,-20000000",
        "صافي ربح (خسارة) العام قبل ضريبة الدخل,125000000,180000000",
        "ضريبة الدخل عن العام,-28000000,-40000000",
        "صافي ربح (خسارة) العام,97000000,140000000",
        "أصول ثابتة بالصافي,180000000,200000000",
        "إجمالي الأصول غير المتداولة,400000000,450000000",
        "أعمال تحت التنفيذ,500000000,620000000",
        "عملاء وأوراق قبض,350000000,420000000",
        "نقدية بالصندوق ولدى البنوك,250000000,310000000",
        "إجمالي الأصول المتداولة,1100000000,1350000000",
        "مجموع الأصول,1500000000,1800000000",
        "رأس المال المصدر والمدفوع,226875000,226875000",
        "أرباح مرحلة,473125000,613125000",
        "إجمالي حقوق المساهمين,700000000,840000000",
        "قروض وتسهيلات طويلة الأجل,150000000,180000000",
        "إجمالي الالتزامات غير المتداولة,300000000,360000000",
        "موردون ومقاولون,220000000,260000000",
        "الجزء المتداول من القروض طويلة الأجل,50000000,60000000",
        "إجمالي الالتزامات المتداولة,500000000,600000000",
        "إجمالي الالتزامات,800000000,960000000",
        "إهلاك الأصول الثابتة,12000000,14000000",
        "صافي التدفقات النقدية من الأنشطة التشغيلية,160000000,190000000",
        "مدفوعات لاقتناء أصول ثابتة,-40000000,-50000000",
        "صافي التدفقات النقدية من الأنشطة الاستثمارية,-40000000,-60000000",
        "صافي التدفقات النقدية من الأنشطة التمويلية,-30000000,-70000000",
    ])
    res = run_pipeline("شركة الشمس للإسكان والتعمير 2024.csv", csv_text.encode("utf-8"), "")
    curr = res["curr_metrics"]
    assert curr.revenue == pytest.approx(560_000_000.0)
    assert curr.inventory == pytest.approx(620_000_000.0)
    assert curr.accounts_receivable == pytest.approx(420_000_000.0)
    assert curr.accounts_payable == pytest.approx(260_000_000.0)
    assert curr.cash == pytest.approx(310_000_000.0)
    assert curr.current_ratio is not None and curr.quick_ratio is not None
    assert curr.cash_conversion_cycle is not None
    assert curr.free_cash_flow == pytest.approx(140_000_000.0)

    hs = compute_health_score(curr)
    assert hs.total is not None and hs.complete is True and hs.missing_pillars == []

    models = {m.name: m.value for m in academic_models(curr)}
    assert all(v is not None for v in models.values())

    cert = res["formal_certificate"]
    assert cert["status"] == "PROVEN_CONSISTENT"
    assert cert["failed_axioms"] == 0


# ---------------------------------------------------------------------------
# 2. Option 1: Cross-Model Consensus & Expanded Z3 Attestation
# ---------------------------------------------------------------------------

def test_key_pool_pick_distinct_model_prefers_contrasting_tier_and_never_repeats():
    from src.ai.key_pool import APIKeyPool

    pool = APIKeyPool(
        keys=["key-1", "key-2"],
        models=["gemini-flash-lite-latest", "gemini-3.5-flash-lite", "gemini-3-flash-preview"],
    )
    # Excluding all lite models -> must pick full Flash
    picked = pool.pick_distinct_model(exclude_models={"gemini-flash-lite-latest", "gemini-3.5-flash-lite"})
    assert picked is not None
    assert picked[1] == "gemini-3-flash-preview"

    # Excluding ONLY the first lite model -> still prefers contrasting non-lite tier
    picked2 = pool.pick_distinct_model(exclude_models={"gemini-flash-lite-latest"})
    assert picked2 is not None
    assert picked2[1] == "gemini-3-flash-preview"

    # Excluding ALL models -> must return None (zero same-model echo!)
    picked_none = pool.pick_distinct_model(
        exclude_models={"gemini-flash-lite-latest", "gemini-3.5-flash-lite", "gemini-3-flash-preview"}
    )
    assert picked_none is None


def test_cross_model_consensus_promotes_exact_matches_and_keeps_disagreements_gated():
    from src.analysis.formal_verifier import recheck_derived_certainty
    from src.extraction.normalizer import FinancialData, build_decision_log
    from src.extraction.vision_ocr import _cross_model_consensus_verify

    data = FinancialData(
        values={
            "net_income": {2022: 1_056_737_086.0},
            "pretax_income": {2022: 1_236_363_213.0},
            "income_tax_expense": {2022: -179_626_127.0},
            "inventory": {2022: 623_356_849.0},
        },
        document_profile={"kind": "SCANNED_NO_TEXT", "text_layer_trusted": False},
    )
    for idx, (f, v) in enumerate([
        ("net_income", 1_056_737_086.0),
        ("pretax_income", 1_236_363_213.0),
        ("income_tax_expense", -179_626_127.0),
        ("inventory", 623_356_849.0),
    ], start=1):
        data.candidates.setdefault(f, {})[2022] = [(v, idx)]
        data.candidate_layers.setdefault(f, {})[2022] = ["vision"]
        data.candidate_labels.setdefault(f, {})[2022] = [f"vision:{f}"]
        data.bump_confidence(f, 2022, 1)

    # Mark income_tax_expense as derived from unverified inputs initially
    data.derived[("income_tax_expense", 2022)] = "identity (net_income = pretax_income - income_tax_expense)"
    data.derived_uncertain = {("income_tax_expense", 2022)}

    seen_prompts: list[str] = []

    def fake_distinct_caller(page_no, prompt, _imgs, _excl):
        seen_prompts.append(prompt)
        if page_no == 6:
            return json.dumps({
                "years": [2022],
                "values": {
                    "net_income": [1_056_737_086],
                    "pretax_income": [1_236_363_213],
                },
            }), "gemini-3-flash-preview"
        # Page 5: Model B DISAGREES on inventory (623M vs 999M)
        return json.dumps({
            "years": [2022],
            "values": {"inventory": [999_000_000]},
        }), "gemini-3-flash-preview"

    notes: list[str] = []
    attested = _cross_model_consensus_verify(
        data=data,
        field_sources={"net_income": [6], "pretax_income": [6], "inventory": [5]},
        pages_png=[b"p5_png", b"p6_png"],
        selected=[5, 6],
        pool=None,
        sweep_models=["gemini-flash-lite-latest"],
        notes=notes,
        distinct_caller=fake_distinct_caller,
    )
    assert attested == 2
    # Zero prompt leakage: Model A's numbers must NEVER appear in Model B's prompts
    for pr in seen_prompts:
        assert "1056737086" not in pr.replace(",", "")
        assert "623356849" not in pr.replace(",", "")

    # Cascade derived certainty now that pretax_income & net_income are multi-layer verified
    upgraded = recheck_derived_certainty(data)
    assert upgraded == 1

    log = {(e["field"], e["year"]): e for e in build_decision_log(data)}
    assert log[("net_income", 2022)]["status"] == "VERIFIED_EXACT"
    assert "Cross-Model Consensus" in log[("net_income", 2022)]["reason"]
    assert log[("pretax_income", 2022)]["status"] == "VERIFIED_EXACT"
    assert log[("income_tax_expense", 2022)]["status"] == "VERIFIED_DERIVED"
    # Disagreed cell stays UNVERIFIED and keeps its original value (no silent overwrite)
    assert log[("inventory", 2022)]["status"] == "UNVERIFIED"
    assert data.get("inventory", 2022) == pytest.approx(623_356_849.0)


def test_cross_model_consensus_rejects_same_model_echo():
    from src.extraction.normalizer import FinancialData, build_decision_log
    from src.extraction.vision_ocr import _cross_model_consensus_verify

    data = FinancialData(
        values={"net_income": {2022: 100_000.0}},
        document_profile={"kind": "SCANNED_NO_TEXT", "text_layer_trusted": False},
    )
    data.candidates["net_income"] = {2022: [(100_000.0, 1)]}
    data.candidate_layers["net_income"] = {2022: ["vision"]}
    data.candidate_labels["net_income"] = {2022: ["vision:ni"]}
    data.bump_confidence("net_income", 2022, 1)

    def same_model_caller(_p, _prompt, _imgs, _excl):
        return json.dumps({"years": [2022], "values": {"net_income": [100_000]}}), "gemini-flash-lite-latest"

    attested = _cross_model_consensus_verify(
        data=data,
        field_sources={"net_income": [6]},
        pages_png=[b"p6_png"],
        selected=[6],
        pool=None,
        sweep_models=["gemini-flash-lite-latest"],
        notes=[],
        distinct_caller=same_model_caller,
    )
    assert attested == 0
    log = build_decision_log(data)
    assert log[0]["status"] == "UNVERIFIED"


def test_z3_attestation_activity_bridge_and_op_exact():
    from src.analysis.formal_verifier import apply_z3_algebraic_attestation
    from src.extraction.normalizer import FinancialData, build_decision_log

    vals = {
        "gross_profit": {2022: 1_632_142_979.0},
        "selling_expenses": {2022: -174_182_376.0},
        "admin_expenses": {2022: -200_000_000.0},
        "net_activity_profit": {2022: 1_257_960_603.0},
        "interest_expense": {2022: -771_597_390.0},
        "dividends_from_subsidiaries": {2022: 750_000_000.0},
        "pretax_income": {2022: 1_236_363_213.0},
    }
    data = FinancialData(
        values={f: dict(by_y) for f, by_y in vals.items()},
        document_profile={"kind": "SCANNED_NO_TEXT", "text_layer_trusted": False},
    )
    for idx, (f, by_y) in enumerate(vals.items(), start=1):
        for y, v in by_y.items():
            data.candidates.setdefault(f, {})[y] = [(v, idx)]
            data.candidate_layers.setdefault(f, {})[y] = ["vision"]
            data.candidate_labels.setdefault(f, {})[y] = [f"v:{f}"]
            data.bump_confidence(f, y, 1)

    attested = apply_z3_algebraic_attestation(data, [])
    ax_ids = {ax for _f, _y, ax in attested}
    assert "A6b_ACTIVITY_BRIDGE" in ax_ids
    assert "A5c_OP_EXACT" in ax_ids

    log = {e["field"]: e["status"] for e in build_decision_log(data)}
    for f in vals:
        assert log[f] == "VERIFIED_EXACT", f"{f} should be attested by Z3"


# ---------------------------------------------------------------------------
# 3. Option 2: Clearer UI Gate Copy & Official vs Exploratory Health Toggle
# ---------------------------------------------------------------------------

def test_gate_label_and_partial_health_score_toggle(monkeypatch):
    import streamlit as st
    from src.analysis.calculator import compute_year_metrics
    from src.dashboard.new_ui import sec_health
    from src.dashboard.view_model import GATE_LABELS

    assert "يدخل المؤشرات" in GATE_LABELS["not_decisive"][0]
    assert "الدرجة الرسمية" in GATE_LABELS["not_decisive"][0]

    data = {
        "revenue": {2022: 16_000_000_000.0},
        "net_income": {2022: 1_200_000_000.0},
        "total_assets": {2022: 15_000_000_000.0},
        "current_assets": {2022: 4_200_000_000.0},
        "inventory": {2022: 600_000_000.0},
        "current_liabilities": {2022: 8_000_000_000.0},
        "total_liabilities": {2022: 9_000_000_000.0},
        "total_debt": {2022: 5_000_000_000.0},
        "equity": {2022: 6_000_000_000.0},
        "operating_cash_flow": {2022: 1_200_000_000.0},
    }
    curr = compute_year_metrics(2022, data)
    vm = {
        "pending": [{"field": "net_income", "year": 2022, "status": "UNVERIFIED"}],
    }
    results = {"curr_year": 2022, "curr_metrics": curr}

    fake_session = {"ui_lang": "ar"}
    radio_calls: list[list[str]] = []
    md_out: list[str] = []
    info_out: list[str] = []

    class _DummyCol:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    monkeypatch.setattr(st, "session_state", fake_session)
    monkeypatch.setattr(st, "subheader", lambda *a, **kw: None)
    monkeypatch.setattr(st, "caption", lambda *a, **kw: None)
    monkeypatch.setattr(st, "columns", lambda n: [_DummyCol() for _ in range(n)])
    monkeypatch.setattr(st, "plotly_chart", lambda *a, **kw: None)
    monkeypatch.setattr(st, "markdown", lambda txt, **kw: md_out.append(str(txt)))
    monkeypatch.setattr(st, "info", lambda txt, **kw: info_out.append(str(txt)))

    # Select Exploratory Full Estimate (option 2)
    def fake_radio(_lbl, options, **kw):
        radio_calls.append(list(options))
        return options[1]

    monkeypatch.setattr(st, "radio", fake_radio)

    sec_health(vm, results)
    assert len(radio_calls) == 1
    assert "الدرجة الرسمية" in radio_calls[0][0]
    assert "التقدير الشامل الاستكشافي" in radio_calls[0][1]
    assert any("تغطية 100%" in opt for opt in radio_calls[0])
    assert any("عرض استكشافي تجريبي" in i for i in info_out)
    # In exploratory full mode, Profitability is unlocked (no longer blocked!)
    joined_md = "\n".join(md_out)
    assert "درجة كلية مكتملة الأركان" in joined_md
