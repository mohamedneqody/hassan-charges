"""Accuracy fixes (2026-10-31): the relaxed JSON loader that rescues
"Extra data" verify responses, the CFO gross-subtotal rejection, the
cash-movement negative patterns, and the new printed-label aliases —
all against the exact phrasings Indra saw on the real 2022 file."""
from __future__ import annotations

import json

import pytest

from src.extraction.normalizer import build_decision_log, match_field
from src.extraction.vision_ocr import _loads_relaxed


# --- _loads_relaxed ------------------------------------------------------- #

def test_plain_json_unchanged():
    assert _loads_relaxed('{"a": 1}') == {"a": 1}


def test_extra_data_after_object_is_rescued():
    """The exact failure that dropped a whole verification page."""
    text = '{"years": [2022, 2021], "totals": {}}  some trailing model chatter'
    assert _loads_relaxed(text) == {"years": [2022, 2021], "totals": {}}


def test_leading_prose_before_object():
    text = 'Here is the JSON you asked for:\n{"totals": {"revenue": [1, 2]}}'
    assert _loads_relaxed(text)["totals"]["revenue"] == [1, 2]


def test_braces_inside_strings_never_end_the_scan():
    text = '{"label": "total {weird} case", "x": 1} trailing junk'
    assert _loads_relaxed(text)["label"] == "total {weird} case"


def test_fenced_json_with_extra_data():
    text = '```json\n{"a": [1, 2]}\n```\nnote: values are in EGP'
    assert _loads_relaxed(text) == {"a": [1, 2]}


def test_top_level_list_with_trailing_junk():
    text = '[{"years": [2022], "rows": []}] ok'
    assert _loads_relaxed(text)[0]["years"] == [2022]


def test_no_json_at_all_raises():
    with pytest.raises(json.JSONDecodeError):
        _loads_relaxed("no structure here")


# --- CFO gross-subtotal rejection ----------------------------------------- #

def test_cfo_gross_subtotal_row_is_rejected():
    """Printed subtotal «النقدية الناتجة من أنشطة التشغيل» (BEFORE paid
    financing) — the capture that shipped 1,794M instead of 1,214M."""
    assert match_field("النقدية الناتجة من أنشطة التشغيل") is None


def test_cfo_net_line_is_accepted():
    assert match_field("صافي النقدية الناتجة من أنشطة التشغيل") == "operating_cash_flow"
    assert match_field("صافي التدفقات النقدية من الأنشطة التشغيلية") == "operating_cash_flow"


def test_net_cash_movement_rows_rejected_but_period_end_balance_kept():
    # net-cash-movement rows must not feed the cash balance or CF totals
    for label in ("صافي الزيادة في النقدية", "صافي النقص في النقدية",
                  "التغير في النقدية خلال العام"):
        assert match_field(label) is None
    # BUT «النقدية ... في نهاية الفترة» IS the legitimate balance-sheet row
    assert match_field("النقدية ونقدية ما يعادلها في نهاية الفترة") == "cash"


# --- new printed-label aliases (from the Indra label diagnosis) ------------ #

def test_selling_expenses_with_yaa_forms():
    assert match_field("مصروفات بيعية وتسويقية") == "selling_expenses"


def test_pretax_label_is_pretax_not_net_income():
    assert match_field("صافى أرباح العام قبل ضريبة الدخل") == "pretax_income"
    assert match_field("أرباح العام قبل ضريبة الدخل") == "pretax_income"


def test_operating_income_local_phrasing():
    assert match_field("ربح العمليات") == "operating_income"
    assert match_field("نتيجة العمليات") == "operating_income"


def test_depreciation_for_fixed_assets():
    assert match_field("إهلاك أصول ثابتة") == "depreciation_amortization"


def test_net_financing_costs():
    assert match_field("صافي التكاليف التمويلية") == "interest_expense"
    assert match_field("فوائد ومصروفات تمويلية") == "interest_expense"


def test_cf_bridge_and_comprehensive_income_never_feed_net_income():
    """The CF bridge subtotal and comprehensive-income lines mention net
    profit's words but hold NI + non-cash adjustments / NI + OCI."""
    assert match_field("صافي الربح قبل التغير في الأصول المتداولة والالتزامات المتداولة") is None
    assert match_field("صافي الدخل الشامل") is None
    assert match_field("إجمالي الدخل الشامل") is None


def test_non_controlling_interest_share_rows_rejected():
    assert match_field("أرباح العام قبل ضريبة الدخل لحصة غير المسيطرين") is None
    assert match_field("صافي الربح لحصة غير المسيطرين") is None


def test_retained_earnings_not_hijacked_by_oci_adjustment_rows():
    assert match_field("الجزء المحقق من ناتج تعديل تكلفة الأصول (المحول للأرباح المرحلة خلال العام)") is None
    assert match_field("الأرباح المرحلة") == "retained_earnings"


# --- tax bridge + cash beginning-row rejection (2026-10-31, second round) --- #

from src.extraction.normalizer import merge_parsed, reconcile


def _tax_bridge_data(ni_conf: int):
    data = merge_parsed(
        [{2022: {"net_income": 1_056_737_086.0,
                 "pretax_income": 1_236_363_213.0,
                 "income_tax_expense": -167_901_733.0}}],
        [],
    )
    if ni_conf:
        data.bump_confidence("net_income", 2022, ni_conf)
    return data


def test_tax_bridge_appends_implied_tax_and_identity_picks_it():
    data = _tax_bridge_data(ni_conf=2)
    reconcile(data)
    tax = data.get("income_tax_expense", 2022)
    assert tax == pytest.approx(-179_626_127.0, abs=1.0)
    assert data.get("net_income", 2022) == pytest.approx(1_056_737_086.0, abs=1.0)


def test_tax_derived_from_identity_when_rows_garbled():
    """New policy (analyst-grade): when the net_income identity fails, the tax
    is DERIVED from the two verified anchors (NI − pretax) and FLAGGED —
    better than keeping a garbled row, worse than hiding the problem."""
    data = _tax_bridge_data(ni_conf=0)
    reconcile(data)
    tax = data.get("income_tax_expense", 2022)
    assert tax == pytest.approx(-179_626_127.0, abs=1.0)
    assert any("derived from the identity" in n for n in data.notes)


def test_tax_bridge_gate_now_only_governs_candidate_append():
    # the bridge (candidate append) respects the confidence gate, but the
    # fallback derivation still corrects the value in the low-confidence case
    data = _tax_bridge_data(ni_conf=0)
    reconcile(data)
    assert data.get("income_tax_expense", 2022) == pytest.approx(-179_626_127.0, abs=1.0)


def test_cash_beginning_of_year_row_rejected():
    assert match_field("النقدية وما في حكمها في أول العام") is None
    assert match_field("النقدية وما في حكمها في نهاية الفترة") == "cash"


# --- debt definition (audit phase 4: بنوك تسهيلات إنتمانية were missing) --- #

def test_bank_facilities_row_maps_to_short_term_debt():
    """The BS prints «بنوك تسهيلات إنتمانية ٤,٠٦٣,٤٠٠,١٦٧» — missing this alias
    shipped Debt/Equity ≈ 0.03 (nonsense) because ST debt captured as None."""
    assert match_field("بنوك تسهيلات إنتمانية") ==         "short_term_credit_facilities"  # v6: حقل كانسي مستقل
    assert match_field("تسهيلات بنكية") == "short_term_debt"


def test_current_portion_maps_to_its_own_field():
    """بند مستقل مطبوع — لا يُدمج مع القروض غير المتداولة ولا مع التسهيلات"""
    assert match_field("أقساط قروض طويلة الأجل مستحقة السداد خلال عام") == "current_portion_lt_debt"
    # while the LT loans row itself stays long-term
    assert match_field("قروض طويلة الأجل") == "long_term_debt"


# --- debt mapping (التعريفان المعتمدان: بنود بدون تأجير / دين تمويلي شامل) --- #

def test_current_portion_maps_to_its_own_field_not_lt_or_double_count():
    assert match_field("أقساط قروض طويلة الأجل مستحقة السداد خلال عام") == "current_portion_lt_debt"
    # وقراءة سطر القروض غير المتداولة تبقى طويلة الأجل — لا عد مزدوج
    assert match_field("قروض طويلة الأجل") == "long_term_debt"


def test_dividends_from_subsidiaries_field():
    assert match_field("توزيعات أرباح من شركات تابعة") == "dividends_from_subsidiaries"


def test_lease_rows_map_to_distinct_fields():
    assert match_field("التزامات تأجير تمويلي") == "non_current_lease_liabilities"
    assert match_field("التزامات تأجير تمويلي مستحقة السداد خلال عام") == "current_lease_liabilities"


def test_debt_mapping_computes_both_totals_without_double_count():
    data = merge_parsed([{2022: {
        "short_term_debt": 4_063_400_167.0,          # بنوك تسهيلات إنتمانية
        "current_portion_lt_debt": 299_320_963.0,     # أقساط القروض المتداولة
        "long_term_debt": 363_974_291.0,              # القروض غير المتداولة
        "non_current_lease_liabilities": 209_154_419.0,
        "current_lease_liabilities": 83_301_722.0,
        "equity": 6_938_330_481.0,
        "operating_cash_flow": 1_214_507_839.0,
    }}], [])
    reconcile(data)
    borrowings = data.get("borrowings_excl_leases", 2022)
    fin = data.get("financial_debt_incl_leases", 2022)
    # 4,063,400,167 + 299,320,963 + 363,974,291 = 4,726,695,421 (قروض وتسهيلات — ص23)
    assert borrowings == pytest.approx(4_726_695_421.0, abs=1.0)
    # + 209,154,419 + 83,301,722 = 5,019,151,562 (شامل التأجير التمويلي — IFRS 16 / EAS 49)
    assert fin == pytest.approx(5_019_151_562.0, abs=1.0)
    # لا عد مزدوج: إجمالي الدين المالي يطابق الشامل للتأجير، بينما القروض وحدها محفوظة في borrowings_excl_leases
    assert data.get("total_debt", 2022) == pytest.approx(5_019_151_562.0, abs=1.0)
    log = {d["field"]: d for d in build_decision_log(data)}
    assert log["borrowings_excl_leases"]["status"] == "VERIFIED_DERIVED"
    assert log["financial_debt_incl_leases"]["status"] == "VERIFIED_DERIVED"


def test_partial_note_depreciation_never_outvotes_cash_flow_total():
    """إهلاك تكلفة المبيعات الجزئي (39M مكرر في إيضاحين) لا يُسقط إجمالي إهلاك التدفقات (49M)."""
    data = merge_parsed(
        [
            {2022: {"depreciation_amortization": 49_044_136.0, "fixed_assets": 495_544_560.0}},
            {2022: {"depreciation_amortization": 39_012_520.0}},
            {2022: {"depreciation_amortization": 39_012_520.0}},
            {2022: {"depreciation_amortization": 120_688.0}},
        ],
        [],
        captures_per_part=[
            [{"field": "depreciation_amortization", "year": 2022, "value": 49_044_136.0, "label_text": "إهلاك أصول ثابتة"}],
            [{"field": "depreciation_amortization", "year": 2022, "value": 39_012_520.0, "label_text": "إهلاك أصول ثابتة - تكلفة المبيعات"}],
            [{"field": "depreciation_amortization", "year": 2022, "value": 39_012_520.0, "label_text": "مصروف إهلاك الأصول الثابتة"}],
            [{"field": "depreciation_amortization", "year": 2022, "value": 120_688.0, "label_text": "إهلاك أصول ثابتة - بيع"}],
        ],
    )
    reconcile(data)
    assert data.get("depreciation_amortization", 2022) == pytest.approx(49_044_136.0, abs=1.0)
    log = {d["field"]: d for d in build_decision_log(data)}
    assert log["depreciation_amortization"]["status"] != "VERIFIED_EXACT"


def test_beneish_textbook_aqi_and_sgai_direction():
    """Beneish (1999): AQI includes CA+PPE, SGAI is curr/prev (not inverted) and includes G&A."""
    from src.analysis.calculator import YearMetrics
    from src.analysis.redflags import beneish_m_score

    prev = YearMetrics(
        year=2021, revenue=13_169_656_088.0, gross_profit=1_197_622_108.0,
        accounts_receivable=691_267_962.0, current_assets=2_901_399_092.0,
        fixed_assets=521_471_030.0, total_assets=14_614_683_997.0,
        depreciation_amortization=49_252_251.0,
        selling_expenses=-42_121_403.0, admin_expenses=-299_648_555.0,
        total_liabilities=8_250_997_672.0,
    )
    curr = YearMetrics(
        year=2022, revenue=16_665_919_878.0, gross_profit=1_632_142_979.0,
        accounts_receivable=770_203_387.0, current_assets=4_248_947_378.0,
        fixed_assets=495_544_560.0, total_assets=15_965_646_460.0,
        depreciation_amortization=49_044_136.0,
        selling_expenses=-48_052_831.0, admin_expenses=-383_519_092.0,
        total_liabilities=9_027_315_979.0,
        net_income=1_056_737_086.0, operating_cash_flow=1_214_507_839.0,
    )
    bn = beneish_m_score(prev, curr)
    assert bn.components["AQI"] == pytest.approx(0.9178, abs=0.001)
    assert bn.components["SGAI"] == pytest.approx(0.9978, abs=0.001)
    assert bn.components["DEPI"] == pytest.approx(0.9583, abs=0.001)
    assert bn.m_score == pytest.approx(-2.475, abs=0.01)


def test_operating_expenses_derived_gross_not_netted():
    """Gross OpEx = Selling + G&A + Other OpEx (does not net out Other Operating Income)."""
    from src.analysis.calculator import compute_year_metrics

    values = {
        "revenue": {2022: 16_665_919_878.0},
        "gross_profit": {2022: 1_632_142_979.0},
        "selling_expenses": {2022: -48_052_831.0},
        "admin_expenses": {2022: -383_519_092.0},
        "other_operating_expenses": {2022: -25_399_046.0},
        "operating_income": {2022: 1_257_960_603.0},
    }
    m = compute_year_metrics(2022, values)
    assert m.operating_expenses == pytest.approx(456_970_969.0, abs=1.0)
    assert m.opex_pct == pytest.approx(2.742, abs=0.01)


def test_accounts_payable_and_long_term_debt_vetoes():
    """2023 audit regressions: BS AP matches without ال, ECL/advances vetoed, CF loan repayments vetoed."""
    assert match_field("موردون وأوراق دفع") == "accounts_payable"
    assert match_field("إجمالي موردون و أوراق دفع") == "accounts_payable"
    assert match_field("موردون - دفعات مقدمة") is None
    assert match_field("الخسائر الإئتمانية المتوقعة من الموردين - دفعات مقدمة") is None
    assert match_field("(مدفوعات) لسداد قروض طويلة الأجل") is None
    assert match_field("الاضمحلال في قيمة المدينون") is None


def test_total_debt_computed_when_long_term_debt_is_zero_or_none():
    """2023 Ezz Steel: long_term_debt is '--' (None) while credit facilities + current portion exist."""
    data = merge_parsed([{2023: {
        "short_term_credit_facilities": 6_204_060_910.0,
        "bank_overdraft": 4_811_795.0,
        "current_portion_lt_debt": 363_974_291.0,
        "non_current_lease_liabilities": 121_960_204.0,
        "current_lease_liabilities": 90_144_503.0,
    }}], [])
    reconcile(data)
    assert data.get("borrowings_excl_leases", 2023) == pytest.approx(6_572_846_996.0, abs=1.0)
    assert data.get("total_debt", 2023) == pytest.approx(6_784_951_703.0, abs=1.0)


def test_tiny_echoed_note_cannot_outvote_balance_sheet_receivables():
    """Two echoed 80,100 note lines must never replace 54.89M balance-sheet receivables."""
    data = merge_parsed(
        [
            {2023: {"accounts_receivable": 54_893_089.0}},
            {2023: {"accounts_receivable": 80_100.0}},
            {2023: {"accounts_receivable": 80_100.0}},
        ],
        [],
        captures_per_part=[
            [{"field": "accounts_receivable", "year": 2023, "value": 54_893_089.0, "label_text": "عملاء وأوراق قبض"}],
            [{"field": "accounts_receivable", "year": 2023, "value": 80_100.0, "label_text": "إيضاح أ"}],
            [{"field": "accounts_receivable", "year": 2023, "value": 80_100.0, "label_text": "إيضاح ب"}],
        ],
    )
    reconcile(data)
    assert data.get("accounts_receivable", 2023) == pytest.approx(54_893_089.0, abs=1.0)


def test_balance_sheet_payables_protected_from_note_or_cf_majority_vote():
    """2021 Ezz Steel: two echoed note/CF values (958M) must never replace BS AP (2.39B)."""
    data = merge_parsed(
        [
            {2020: {"accounts_payable": 2_387_975_196.0}},
            {2020: {"accounts_payable": 958_616_702.0}},
            {2020: {"accounts_payable": 958_616_702.0}},
        ],
        [],
        captures_per_part=[
            [{"field": "accounts_payable", "year": 2020, "value": 2_387_975_196.0, "label_text": "موردون وأوراق دفع"}],
            [{"field": "accounts_payable", "year": 2020, "value": 958_616_702.0, "label_text": "التغير في الموردين"}],
            [{"field": "accounts_payable", "year": 2020, "value": 958_616_702.0, "label_text": "إيضاح الموردين"}],
        ],
    )
    reconcile(data)
    assert data.get("accounts_payable", 2020) == pytest.approx(2_387_975_196.0, abs=1.0)


def test_debt_mapping_partial_inputs_still_derive_borrowings():
    """وثيقة بلا بند أقساط: الإجمالي = تسهيلات + قروض غير متداولة (بلا فشل)"""
    data = merge_parsed([{2022: {"short_term_debt": 1_000.0, "long_term_debt": 2_000.0}}], [])
    reconcile(data)
    assert data.get("borrowings_excl_leases", 2022) == pytest.approx(3_000.0, abs=1.0)
    assert data.get("total_debt", 2022) == pytest.approx(3_000.0, abs=1.0)
