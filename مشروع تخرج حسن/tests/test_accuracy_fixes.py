"""Accuracy fixes (2026-10-31): the relaxed JSON loader that rescues
"Extra data" verify responses, the CFO gross-subtotal rejection, the
cash-movement negative patterns, and the new printed-label aliases —
all against the exact phrasings Indra saw on the real 2022 file."""
from __future__ import annotations

import json

import pytest

from src.extraction.normalizer import match_field
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


def test_tax_bridge_requires_verified_net_income():
    data = _tax_bridge_data(ni_conf=0)
    reconcile(data)
    # without a multiply-verified NI the garbled capture is honestly kept
    assert data.get("income_tax_expense", 2022) == pytest.approx(-167_901_733.0, abs=1.0)


def test_cash_beginning_of_year_row_rejected():
    assert match_field("النقدية وما في حكمها في أول العام") is None
    assert match_field("النقدية وما في حكمها في نهاية الفترة") == "cash"
