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
        "التغير في مشروعات تحت التنفيذ",    # Cash-flow/movement CWIP line (never asset!)
        "الانخفاض في قيمة المخزون",          # Impairment reserve
        "التغير في أعمال تحت التنفيذ",       # Cash-flow working capital delta
        "عملاء دفعات مقدمة",                 # Customer advances (liability, not AR!)
        "إيرادات متنوعة أخرى",               # Other non-operating revenue (never hijacks core revenue!)
        "إجمالي الالتزامات وحقوق الملكية",   # Grand total exclusion
    ],
)
def test_real_estate_aliases_respect_accounting_vetoes(vetoed_label: str):
    from src.extraction.normalizer import match_field

    assert match_field(vetoed_label) is None
    # Industrial CWIP maps to non-current projects_under_construction, NEVER current inventory!
    assert match_field("مشروعات تحت التنفيذ") != "inventory"


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


# ---------------------------------------------------------------------------
# 4. v9.32 Root-Cause Fixes Toward 100% Coverage
# ---------------------------------------------------------------------------

def test_v932_cross_statement_sign_alignment_and_single_page_preservation():
    """Multi-page opposite-sign echoes (P&L parentheses vs Note positive table)
    align cleanly to primary sign, while single-page / page-less sign conflicts
    remain strictly gated as CONFLICT."""
    from src.extraction.normalizer import build_decision_log, merge_parsed, reconcile

    # Case 1: >=2 distinct pages (Page 6 P&L + Page 12 Note) -> sign aligned, NOT CONFLICT
    d_multi = merge_parsed(
        [{2022: {"admin_expenses": -383_519_092.0}},
         {2022: {"admin_expenses": 383_519_092.0}}],
        [],
        part_layers=["vision", "local_ocr"],
    )
    d_multi.field_sources = {"admin_expenses": [6, 12]}
    reconcile(d_multi)
    assert d_multi.values["admin_expenses"][2022] == pytest.approx(-383_519_092.0)
    log_multi = build_decision_log(d_multi)
    assert log_multi[0]["status"] == "VERIFIED_EXACT"

    # Case 2: Single-page / page-less opposite sign -> MUST remain CONFLICT ("تعارض الإشارة")
    d_single = merge_parsed(
        [{2022: {"admin_expenses": -383_519_092.0}},
         {2022: {"admin_expenses": 383_519_092.0}}],
        [],
        part_layers=["text", "text"],
    )
    reconcile(d_single)
    log_single = build_decision_log(d_single)
    assert log_single[0]["status"] == "CONFLICT"
    assert "تعارض الإشارة" in log_single[0]["reason"]


def test_v932_note_thousand_truncation_healed_and_fixed_assets_cf_vetoed():
    from src.extraction.normalizer import match_field, merge_parsed, reconcile

    # Cash-flow disposal / gain / depreciation lines must NEVER match fixed_assets
    assert match_field("أرباح رأسمالية من بيع أصول ثابتة") is None
    assert match_field("متحصلات من بيع أصول ثابتة") is None
    assert match_field("مدفوعات لشراء أصول ثابتة") == "capex"
    assert match_field("الأصول الثابتة (بالصافي)") == "fixed_assets"
    assert match_field("إيرادات تشغيل أخرى") == "other_operating_income"

    # Page 6 smudged `-299,648,000` healed to Note 7 exact `-299,648,555` (preserving replaced value)
    d = merge_parsed(
        [{2021: {"admin_expenses": -299_648_000.0}},
         {2021: {"admin_expenses": 299_648_555.0}}],
        [],
        part_layers=["vision", "vision"],
    )
    d.field_sources = {"admin_expenses": [6, 12]}
    reconcile(d)
    assert d.values["admin_expenses"][2021] == pytest.approx(-299_648_555.0)
    assert (-299_648_000.0) in d.replaced_values[("admin_expenses", 2021)]


def test_v932_z3_attests_6_term_operating_bridge_with_other_op_income():
    from src.analysis.formal_verifier import apply_z3_algebraic_attestation
    from src.extraction.normalizer import FinancialData, build_decision_log

    # Exact Ezz Steel 2022 6-term Operating Income equation (0.00 EGP residual!)
    vals = {
        "gross_profit": {2022: 1_632_142_979.0},
        "selling_expenses": {2022: -48_052_831.0},
        "admin_expenses": {2022: -383_519_092.0},
        "other_operating_expenses": {2022: -25_399_046.0},
        "other_operating_income": {2022: 82_788_593.0},
        "operating_income": {2022: 1_257_960_603.0},
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
    attested_fields = {f for f, _y, ax in attested if ax == "A5c_OP_EXACT"}
    assert attested_fields == set(vals.keys())
    log = {e["field"]: e["status"] for e in build_decision_log(data)}
    assert all(st == "VERIFIED_EXACT" for st in log.values())


def test_v932_optional_non_disclosed_rd_not_counted_as_missing_failure():
    from src.dashboard.components.chrome import build_metrics_table_html
    from src.dashboard.view_model import build_view_model, executive_summary
    from src.pipeline import run_pipeline

    csv_text = "\n".join([
        "Item,2023,2024",
        "Revenue,1000000,1200000",
        "Cost of Revenue,-600000,-700000",
        "Gross Profit,400000,500000",
        "Selling Expenses,-50000,-60000",
        "Administrative Expenses,-80000,-90000",
        "Operating Income,270000,350000",
        "Interest Expense,-20000,-25000",
        "Pretax Income,250000,325000",
        "Income Tax Expense,-50000,-65000",
        "Net Income,200000,260000",
        "Fixed Assets,500000,550000",
        "Inventory,150000,180000",
        "Accounts Receivable,120000,140000",
        "Cash,230000,280000",
        "Current Assets,500000,600000",
        "Total Assets,1000000,1150000",
        "Accounts Payable,100000,120000",
        "Current Liabilities,200000,240000",
        "Long Term Debt,200000,210000",
        "Total Liabilities,400000,450000",
        "Equity,600000,700000",
        "Depreciation and Amortization,30000,35000",
        "Operating Cash Flow,240000,300000",
        "Capex,-60000,-70000",
        "Investing Cash Flow,-60000,-70000",
        "Financing Cash Flow,-50000,-180000",
    ])
    res = run_pipeline("complete_no_rd.csv", csv_text.encode("utf-8"), "")
    vm = build_view_model(res, currency="ج.م")
    rd_row = next(r for r in vm["metrics"] if r["key"] == "rd_pct")
    assert rd_row["not_disclosed"] is True
    assert rd_row["verif"] == "غير مفصح بالقوائم"

    facts = executive_summary(res, vm, lang="ar")
    assert any("100% مكتملة" in f and "غير مفصح عنها" in f for f in facts)
    assert not any("مؤشرات غير قابلة للحساب لعدم توفر مدخلاتها" in f for f in facts)

    tbl_html, _ = build_metrics_table_html(vm["metrics"], 2023, 2024, 1, "ج.م", lang="ar")
    assert "غير مفصح" in tbl_html
    assert "لا ينطبق" in tbl_html


# ---------------------------------------------------------------------------
# 5. v9.33 Dash-Zero Filter, Equity Decomposition Z3 & Tight Tolerance Fixes
# ---------------------------------------------------------------------------

def test_v933_equity_breakdown_aliases_and_z3_a1c_sum():
    from src.analysis.formal_verifier import apply_z3_algebraic_attestation
    from src.extraction.normalizer import FinancialData, build_decision_log, match_field

    assert match_field("أسهم خزينة") == "treasury_shares"
    assert match_field("إقتناء أسهم خزينة") is None
    assert match_field("احتياطيات") == "reserves"
    assert match_field("إجمالي إحتياطيات") == "reserves"
    assert match_field("إحتياطي قانوني*") is None
    assert match_field("ناتج تعديل تكلفة الأصول") == "asset_revaluation_reserve"
    assert match_field("الجزء المحقق من ناتج تعديل تكلفة الأصول") is None
    assert match_field("فوائد دائنة") == "finance_income"
    assert match_field("فروق ترجمة الأرصدة والمعاملات بالعملات الأجنبية") == "fx_gain_loss"

    # Ezz Steel 2022 exact 6-term Equity sum + full Activity Bridge (2021 without dividends!)
    vals = {
        "capital": {2021: 2_716_325_135.0, 2022: 2_716_325_135.0},
        "treasury_shares": {2021: -10_380_884.0, 2022: -10_380_884.0},
        "reserves": {2021: 2_855_380_202.0, 2022: 2_855_380_202.0},
        "asset_revaluation_reserve": {2021: 27_075_312.0, 2022: 23_617_561.0},
        "retained_earnings": {2021: 775_286_560.0, 2022: 1_353_388_467.0},
        "equity": {2021: 6_363_686_325.0, 2022: 6_938_330_481.0},
        "operating_income": {2021: 875_232_929.0, 2022: 1_257_960_603.0},
        "finance_income": {2021: 13_205_294.0, 2022: 48_861_075.0},
        "interest_expense": {2021: -498_011_580.0, 2022: -483_657_895.0},
        "fx_gain_loss": {2021: 1_206_862.0, 2022: -336_800_570.0},
        "dividends_from_subsidiaries": {2022: 750_000_000.0},
        "pretax_income": {2021: 391_633_505.0, 2022: 1_236_363_213.0},
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
    ax_set = {ax for _f, _y, ax in attested}
    assert "A1c_EQUITY_SUM" in ax_set
    assert "A6b_ACTIVITY_BRIDGE" in ax_set

    log = {(e["field"], e["year"]): e["status"] for e in build_decision_log(data)}
    for f in ("capital", "treasury_shares", "reserves", "asset_revaluation_reserve", "retained_earnings", "equity"):
        assert log[(f, 2022)] == "VERIFIED_EXACT"
    assert log[("dividends_from_subsidiaries", 2022)] == "VERIFIED_EXACT"


def test_v933_vision_dash_zeros_dropped_and_strict_z3_catches_400k_digit_slip():
    from src.analysis.formal_verifier import apply_z3_algebraic_attestation, verify_financial_statements
    from src.extraction.normalizer import FinancialData
    from src.extraction.vision_ocr import _parse_vision_json

    # Dash converted to 0 by vision must be dropped as None (never shows 0 in review queue!)
    parsed = _parse_vision_json(json.dumps({
        "pages": [{
            "page": 5,
            "years": [2022, 2021],
            "rows": [
                ["بنوك - سحب على المكشوف", 0, 2655419],
                ["رأس المال المصدر والمدفوع", 2716325135, 2716325135],
            ],
        }]
    }))
    overdraft_row = next(r for r in parsed[0]["rows"] if "مكشوف" in r[0])
    assert overdraft_row[1] is None and overdraft_row[2] == pytest.approx(2_655_419.0)

    # 400,000 EGP digit slip in 2022 Current Liabilities (8,306,218,199 vs 8,306,618,199)
    # MUST be flagged by tight Z3 tolerance (1e-5) and NEVER attested as VERIFIED_EXACT!
    bad_vals = {
        "total_assets": {2022: 15_965_646_460.0},
        "non_current_liabilities": {2022: 720_697_780.0},
        "current_liabilities": {2022: 8_306_218_199.0},
        "total_liabilities": {2022: 9_027_315_979.0},
        "equity": {2022: 6_938_330_481.0},
    }
    cert = verify_financial_statements(bad_vals, years=[2022], tolerance=1e-5, include_policy_theorems=False)
    a3 = next(a for a in cert.axioms if a.axiom_id == "A3_LIAB_SUM")
    assert a3.status == "VIOLATED"
    assert a3.residual == pytest.approx(400_000.0, abs=1.0)

    d_bad = FinancialData(
        values=bad_vals,
        document_profile={"kind": "SCANNED_NO_TEXT", "text_layer_trusted": False},
    )
    for idx, (f, by_y) in enumerate(bad_vals.items(), start=1):
        d_bad.candidates[f] = {2022: [(by_y[2022], idx)]}
        d_bad.candidate_layers[f] = {2022: ["vision"]}
        d_bad.bump_confidence(f, 2022, 1)
    attested_bad = {f for f, _y, _ax in apply_z3_algebraic_attestation(d_bad)}
    assert "current_liabilities" not in attested_bad
    assert "non_current_liabilities" not in attested_bad


def test_v933_nca_sub_items_aliases_vetoes_and_z3_a2b_sum():
    from src.analysis.formal_verifier import apply_z3_algebraic_attestation
    from src.extraction.normalizer import match_field, merge_parsed

    assert match_field("مشروعات تحت التنفيذ") == "projects_under_construction"
    assert match_field("إستثمارات في شركات تابعة") == "investments_in_subsidiaries"
    assert match_field("استثمارات أخرى") == "other_investments"
    assert match_field("أصول ضريبية مؤجلة") == "deferred_tax_assets"
    # Cash-flow capex line mentioning "مشروعات تحت التنفيذ" must map to capex, never BS NCA
    assert match_field("مدفوعات لشراء أصول ثابتة ومشروعات تحت التنفيذ") == "capex"
    assert match_field("إلتزامات ضريبية مؤجلة") != "deferred_tax_assets"

    nca_row = {
        "fixed_assets": 495_544_060.0,
        "projects_under_construction": 3_091_352.0,
        "investments_in_subsidiaries": 11_127_193_473.0,
        "other_investments": 80_100.0,
        "deferred_tax_assets": 90_789_698.0,
        "non_current_assets": (
            495_544_060.0 + 3_091_352.0 + 11_127_193_473.0 + 80_100.0 + 90_789_698.0
        ),
    }
    d = merge_parsed([{2022: nca_row}], notes=[], part_layers=["vision"])
    attested = {(f, ax) for f, _y, ax in apply_z3_algebraic_attestation(d)}
    assert ("fixed_assets", "A2b_NCA_SUM") in attested
    assert ("projects_under_construction", "A2b_NCA_SUM") in attested
    assert ("non_current_assets", "A2b_NCA_SUM") in attested

    # Break sum beyond tolerance -> A2b_NCA_SUM must NOT attest
    bad_row = dict(nca_row)
    bad_row["fixed_assets"] -= 2_000_000.0
    d_bad = merge_parsed([{2022: bad_row}], notes=[], part_layers=["vision"])
    attested_bad = {(f, ax) for f, _y, ax in apply_z3_algebraic_attestation(d_bad)}
    assert ("fixed_assets", "A2b_NCA_SUM") not in attested_bad


def test_v933_reconcile_p5_equity_and_p6_opex_six_term_tie_breakers():
    from src.extraction.normalizer import merge_parsed, reconcile

    part_vision = {
        2022: {
            "gross_profit": 1_000_000_000.0,
            "other_operating_income": 50_000_000.0,
            "operating_income": 566_480_908.0,
            "selling_expenses": -100_000_000.0,
            "admin_expenses": -382_519_092.0,
            "capital": 2_716_325_135.0,
            "treasury_shares": -10_380_884.0,
            "reserves": 3_855_380_602.0,
            "retained_earnings": 1_353_358_467.0,
            "equity": 7_938_300_881.0,
            "asset_revaluation_reserve": 96_078_846.0,
        }
    }
    part_local = {
        2022: {
            "gross_profit": 1_000_000_000.0,
            "other_operating_income": 50_000_000.0,
            "operating_income": 566_480_908.0,
            "selling_expenses": -100_000_000.0,
            "admin_expenses": -383_519_092.0,
            "capital": 2_716_325_135.0,
            "treasury_shares": -10_380_884.0,
            "reserves": 3_855_380_602.0,
            "retained_earnings": 1_353_358_467.0,
            "equity": 7_938_300_881.0,
            "asset_revaluation_reserve": 23_617_561.0,
        }
    }
    d = merge_parsed([part_vision, part_local], notes=[], part_layers=["vision", "local_ocr"])
    reconcile(d)
    assert abs(d.values["admin_expenses"][2022] - (-383_519_092.0)) < 1.0
    assert abs(d.values["asset_revaluation_reserve"][2022] - 23_617_561.0) < 1.0


def test_v933_focused_local_verify_honors_vetoes_and_skips_note_pages(monkeypatch):
    from types import SimpleNamespace
    import src.extraction.local_ocr as locr
    from src.extraction.normalizer import merge_parsed
    from src.extraction.vision_ocr import _focused_local_cell_verification

    monkeypatch.setattr(locr, "indra_available", lambda: True)

    d = merge_parsed(
        [
            {2022: {"accounts_payable": 2_029_430_800.0, "fixed_assets": 495_544_060.0}},
            {2022: {"accounts_payable": 999.0, "fixed_assets": 111.0}},
        ],
        notes=[],
        part_layers=["vision", "vision"],
    )

    pages_seen = []

    def fake_reader(png):
        pages_seen.append(png)
        return (
            1000,
            1400,
            [
                SimpleNamespace(text="2022", box=[460, 80, 540, 110]),
                SimpleNamespace(text="2021", box=[660, 80, 740, 110]),
                SimpleNamespace(text="موردون - دفعات مقدمة", box=[100, 300, 320, 330]),
                SimpleNamespace(text="266,261,902", box=[450, 300, 560, 330]),
                SimpleNamespace(text="موردون وأوراق دفع", box=[100, 360, 320, 390]),
                SimpleNamespace(text="2,029,430,800", box=[450, 360, 560, 390]),
            ],
        )

    _focused_local_cell_verification(
        d,
        raw=b"",
        field_sources={"accounts_payable": [5], "fixed_assets": [18]},
        doc_years={"years": [2021, 2022]},
        selected=[5, 18],
        pages_png=[b"p5", b"p18"],
        notes=[],
        line_reader=fake_reader,
    )

    # Note page 18 must be skipped entirely for BS stock field fixed_assets
    assert pages_seen == [b"p5"]
    ap_vals = [v for v, _ in d.candidates["accounts_payable"][2022]]
    outcome = d.vote_outcomes.get(("accounts_payable", 2022), {})
    assert 266_261_902.0 not in ap_vals
    assert 266_261_902.0 not in (outcome.get("dissent") or [])
    assert outcome.get("winner") == 2_029_430_800.0
    assert outcome.get("votes") == 2
    assert d.values["accounts_payable"][2022] == 2_029_430_800.0


def test_v933_verify_override_veto_and_integer_smudge_dot_repair():
    import io
    from PIL import Image
    from src.extraction.normalizer import merge_parsed, reconcile
    from src.extraction.vision_ocr import _verify_core_fields

    buf = io.BytesIO()
    Image.new("RGB", (40, 40), color="white").save(buf, format="PNG")
    tiny_png = buf.getvalue()

    # 1) Closed BS identity CL + NCL == TL protects exact sweep capture from noisy 2-of-3 overwrite
    parts = [{
        2022: {
            "current_liabilities": 8_306_618_199.0,
            "non_current_liabilities": 720_697_780.0,
            "total_liabilities": 9_027_315_979.0,
            "total_assets": 15_965_646_460.0,
            "equity": 6_938_330_481.0,
        }
    }]
    data_v = merge_parsed(parts, notes=[], part_layers=["vision"])
    verify_json = (
        '{"years": [2022], "totals": {'
        '"current_liabilities": [8306218199], '
        '"non_current_liabilities": [720697780], '
        '"total_liabilities": [9027315979], '
        '"total_assets": [15965646460], '
        '"equity": [6938330481]}}'
    )
    notes: list[str] = []
    _verify_core_fields(
        data=data_v,
        parts=parts,
        field_sources={"current_liabilities": [5]},
        pages_png=[tiny_png],
        selected=[5],
        pool=None,
        caller=lambda *_a, **_kw: verify_json,
        confidence={},
        notes=notes,
    )
    assert parts[0][2022]["current_liabilities"] == 8_306_618_199.0
    assert any("CL+NCL=TL" in n for n in notes)

    # 2) Integer-statement decimal smudge recovery: 13,169,656,000.88 -> 13,169,656,088
    int_stmt = {
        2021: {
            "revenue": 13_169_656_000.88,
            "cost_of_revenue": -11_972_033_980.0,
            "gross_profit": 1_197_622_108.0,
            "operating_income": 875_232_929.0,
            "pretax_income": 391_633_505.0,
            "net_income": 288_120_890.0,
            "total_assets": 14_614_683_997.0,
            "equity": 6_363_686_325.0,
            "total_liabilities": 8_250_997_672.0,
            "current_assets": 2_901_399_092.0,
        }
    }
    d = merge_parsed([int_stmt], notes=[], part_layers=["vision"])
    reconcile(d)
    assert d.values["revenue"][2021] == 13_169_656_088.0
    assert 13_169_656_000.88 in d.replaced_values[("revenue", 2021)]

    # Genuine fractional millions statement must NEVER be modified
    frac_stmt = {
        2021: {
            "revenue": 131.88,
            "cost_of_revenue": -119.72,
            "gross_profit": 12.16,
            "operating_income": 8.75,
            "pretax_income": 3.91,
            "net_income": 2.88,
            "total_assets": 146.14,
            "equity": 63.63,
            "total_liabilities": 82.51,
        }
    }
    d_frac = merge_parsed([frac_stmt], notes=[], part_layers=["vision"])
    reconcile(d_frac)
    assert d_frac.values["revenue"][2021] == 131.88


def test_v933_integer_tol_catches_10_egp_slip_and_a6b_z3_repair():
    import io
    from PIL import Image
    from src.analysis.formal_verifier import (
        apply_z3_algebraic_attestation,
        verify_financial_statements,
    )
    from src.extraction.normalizer import merge_parsed, reconcile
    from src.extraction.vision_ocr import _z3_feedback_repair_loop

    buf = io.BytesIO()
    Image.new("RGB", (40, 40), color="white").save(buf, format="PNG")
    tiny_png = buf.getvalue()

    # 1) 10-EGP single-digit slip on 14.6B whole-currency statement must violate A1 with integer_tol=5
    vals_10 = {
        "total_assets": {2021: 14_614_683_987.0},
        "current_assets": {2021: 2_901_399_082.0},
        "non_current_assets": {2021: 11_713_284_905.0},
        "total_liabilities": {2021: 8_250_997_672.0},
        "equity": {2021: 6_363_686_325.0},
        # 2022 P&L with 10x dropped zero on dividends_from_subsidiaries (75M vs 750M)
        "net_activity_profit": {2022: 1_257_960_603.0},
        "finance_income": {2022: 48_861_075.0},
        "interest_expense": {2022: -483_657_895.0},
        "fx_gain_loss": {2022: -336_800_570.0},
        "dividends_from_subsidiaries": {2022: 75_000_000.0},
        "pretax_income": {2022: 1_236_363_213.0},
    }
    cert = verify_financial_statements(vals_10, years=[2021, 2022], tolerance=1e-5, integer_tol=5.0)
    violated_ids = {(ax.axiom_id, ax.year) for ax in cert.axioms if ax.status == "VIOLATED"}
    assert ("A1_BS_BALANCE", 2021) in violated_ids
    assert ("A6b_ACTIVITY_BRIDGE", 2022) in violated_ids

    # apply_z3_algebraic_attestation must NOT attest a 10-EGP slip on 14.6B BS
    d_bad = merge_parsed([{2021: {k: v[2021] for k, v in vals_10.items() if 2021 in v}}], notes=[], part_layers=["vision"])
    attested = {f for f, _y, _ax in apply_z3_algebraic_attestation(d_bad)}
    assert "total_assets" not in attested

    # 2) Multi-round Z3 feedback repair: fixes TA 2021 in round 1 -> then fixes CA 2021 in round 2, and fixes dividends 2022 in round 3!
    d_rep = merge_parsed(
        [
            {2021: {k: v[2021] for k, v in vals_10.items() if 2021 in v}, 2022: {k: v[2022] for k, v in vals_10.items() if 2022 in v}},
            {2021: {"total_assets": 14_614_683_987.0}},  # stale 2nd vote would revert if repair didn't replace candidates!
        ],
        notes=[],
        part_layers=["vision", "vision"],
    )
    reconcile(d_rep)

    def fake_caller(_k, _m, prompt, _imgs):
        if "A6b" in prompt or "dividends_from_subsidiaries" in prompt or "2022" in prompt and "جسر النشاط" in prompt or "Activity" in prompt:
            return '{"years": [2021, 2022], "values": {"dividends_from_subsidiaries": [null, 750000000]}}'
        if "A2_ASSETS_SUM" in prompt or "current_assets" in prompt and "A1" not in prompt:
            return '{"years": [2021, 2022], "values": {"current_assets": [2901399092, null], "total_assets": [14614683997, null]}}'
        return '{"years": [2021, 2022], "values": {"total_assets": [14614683997, null], "current_assets": [2901399092, null]}}'

    rep_notes: list[str] = []
    repairs = _z3_feedback_repair_loop(
        data=d_rep,
        field_sources={"total_assets": [5], "current_assets": [5], "dividends_from_subsidiaries": [6]},
        pages_png=[tiny_png, tiny_png],
        selected=[5, 6],
        pool=None,
        caller=fake_caller,
        notes=rep_notes,
    )
    assert any(r["accepted"] for r in repairs)
    assert d_rep.values["total_assets"][2021] == 14_614_683_997.0
    assert d_rep.values["current_assets"][2021] == 2_901_399_092.0
    assert d_rep.values["dividends_from_subsidiaries"][2022] == 750_000_000.0


def test_v933_z3_repair_minimal_subset_ignores_noisy_sibling_reads():
    """Exact reproduction of the live Ezz 2021 Page-5 repair: Gemini 2400px fixes
    TA (14,614,683,997) and CA (2,901,399,092) accurately while misreading equity
    and TL in the same reply. Z3 subset selection accepts ONLY (TA, CA) and leaves
    already-exact equity & TL untouched."""
    import io
    from PIL import Image
    from src.extraction.normalizer import merge_parsed, reconcile
    from src.extraction.vision_ocr import _z3_feedback_repair_loop

    buf = io.BytesIO()
    Image.new("RGB", (40, 40), color="white").save(buf, format="PNG")
    tiny_png = buf.getvalue()

    d = merge_parsed(
        [{
            2021: {
                "total_assets": 14_614_683_987.0,
                "current_assets": 2_901_399_082.0,
                "non_current_assets": 11_713_284_905.0,
                "total_liabilities": 8_250_997_672.0,
                "equity": 6_363_686_325.0,
            }
        }],
        notes=[],
        part_layers=["vision"],
    )
    reconcile(d)

    noisy_reply = (
        '{"years": [2021], "values": {'
        '"equity": [6343686345], '
        '"total_assets": [14614683997], '
        '"total_liabilities": [8250997652], '
        '"current_assets": [2901399092]}}'
    )
    repairs = _z3_feedback_repair_loop(
        data=d,
        field_sources={"total_assets": [5], "current_assets": [5]},
        pages_png=[tiny_png],
        selected=[5],
        pool=None,
        caller=lambda *_a, **_kw: noisy_reply,
        notes=[],
    )
    assert len(repairs) == 1 and repairs[0]["accepted"] is True
    assert repairs[0]["broken_axioms_after"] == 0
    assert d.values["total_assets"][2021] == 14_614_683_997.0
    assert d.values["current_assets"][2021] == 2_901_399_092.0
    # Already-exact siblings must remain untouched!
    assert d.values["equity"][2021] == 6_363_686_325.0
    assert d.values["total_liabilities"][2021] == 8_250_997_672.0


