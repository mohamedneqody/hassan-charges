# -*- coding: utf-8 -*-
"""Spatial cell extraction + accounting-interpretation tests.

No Indra needed: geometry is tested with synthetic LineBox objects, the
negative rules and the p6 bridge through the production normalizer, and the
printed-identity numbers from the independent audit of page 6.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.extraction.normalizer import (  # noqa: E402
    FinancialData, build_decision_log, match_field, reconcile,
)
from src.extraction.spatial_cells import (  # noqa: E402
    LineBox, find_year_columns, parse_number_tokens,
)


# ── Negative field matching (الفصل بين البنود المتشابهة) ────────────────────

def test_activity_profit_is_not_net_income_and_vice_versa():
    # v7 (تدقيق حديد عز — إصلاح 2): «صافي أرباح (خسائر) النشاط» هو سطر
    # الربح التشغيلي المطبوع (875,232,929 ج.م في 2021) — يُطابق
    # operating_income ولا يغذي net_income أو pretax أبدًا.
    # «أرباح النشاط» المجردة (بدون «صافي») يظل net_activity_profit.
    assert match_field("صافي أرباح النشاط") == "operating_income"
    assert match_field("صافى ارباح النشاط") == "operating_income"
    assert match_field("صافي أرباح (خسائر) النشاط") == "operating_income"
    assert match_field("مجمل أرباح النشاط") == "operating_income"
    assert match_field("أرباح النشاط") == "net_activity_profit"
    # the pre-bridge subtotal must NEVER feed net income or pretax
    assert match_field("صافي أرباح النشاط") != "net_income"
    assert match_field("صافي أرباح العام") == "net_income"
    assert match_field("صافى أرباح العام قبل ضريبة الدخل") == "pretax_income"
    assert match_field("صافي أرباح العام قبل ضريبة الدخل") != "net_activity_profit"


def test_total_vs_current_liabilities_separated():
    assert match_field("إجمالي الالتزامات") == "total_liabilities"
    assert match_field("الالتزامات المتداولة") == "current_liabilities"
    assert match_field("اجمالي الالتزامات المتداولة") == "current_liabilities"


def test_installments_row_never_long_term_debt():
    # «أقساط قروض طويلة الأجل مستحقة السداد خلال عام» carries the LT words
    # but is the CURRENT portion (a live run shipped it as long_term_debt).
    assert match_field("أقساط قروض طويلة الأجل مستحقة السداد خلال عام") \
        == "current_portion_lt_debt"
    assert match_field("قروض طويلة الأجل") == "long_term_debt"


def test_overdraft_row_never_bank_facilities():
    # v7 (تدقيق حديد عز — إصلاح 1): «بنوك - سحب على المكشوف» صار حقلاً
    # كانسيًا مستقلاً (bank_overdraft) يغذي إجمالي الدين — لكنه لا يُمتص
    # أبدًا في short_term_debt ولا في التسهيلات الائتمانية.
    # «بنوك تسهيلات (ائتمانية/إنتمانية)» = short_term_credit_facilities.
    assert match_field("بنوك - سحب على المكشوف") == "bank_overdraft"
    assert match_field("بنوك - سحب على المكشوف") != "short_term_debt"
    assert match_field("بنوك - سحب على المكشوف") != "short_term_credit_facilities"
    assert match_field("بنوك تسهيلات إنتمانية") == "short_term_credit_facilities"
    assert match_field("بنوك تسهيلات ائتمانية") == "short_term_credit_facilities"


def test_deferred_tax_never_income_tax_and_other_revenue_never_sales():
    assert match_field("ضريبة الدخل المؤجلة") is None
    assert match_field("ضريبة الدخل") == "income_tax_expense"
    # v9.34: «إيرادات التشغيل الأخرى» became its own canonical field
    # (other_operating_income) for A5c_OP_EXACT — still must NEVER feed revenue.
    assert match_field("إيرادات التشغيل الأخرى") == "other_operating_income"
    assert match_field("إيرادات التشغيل الأخرى") != "revenue"
    assert match_field("المبيعات (بالصافي)") == "revenue"


# ── The p6 printed bridge (الجسر المطبوع) ───────────────────────────────────

def _mk(rows):
    d = FinancialData()
    for f, y, v in rows:
        d.values.setdefault(f, {})[y] = v
        d.candidates.setdefault(f, {}).setdefault(y, []).append((v, 0))
    return d


def test_p6_bridge_activity_minus_financing_plus_dividends():
    # Printed identity audited on page 6: 1,257,960,603 − 771,597,390
    # + 750,000,000 = 1,236,363,213. The difference to net income is the
    # financing + dividends + tax bridge — NOT a non-controlling interest.
    d = _mk([
        ("net_activity_profit", 2022, 1_257_960_603.0),
        ("interest_expense", 2022, -771_597_390.0),
        ("dividends_from_subsidiaries", 2022, 750_000_000.0),
    ])
    reconcile(d)
    got = d.get("pretax_income", 2022)
    assert got is not None, "the p6 bridge did not fire"
    assert abs(got - 1_236_363_213.0) <= 1.0
    assert ("pretax_income", 2022) in d.derived, "bridge must be declared"


def test_p6_bridge_never_overwrites_a_direct_capture():
    d = _mk([
        ("pretax_income", 2022, 1_236_363_213.0),
        ("net_activity_profit", 2022, 1_257_960_603.0),
        ("interest_expense", 2022, -771_597_390.0),
        ("dividends_from_subsidiaries", 2022, 750_000_000.0),
    ])
    before = d.get("pretax_income", 2022)
    reconcile(d)
    assert d.get("pretax_income", 2022) == before
    assert ("pretax_income", 2022) not in d.derived


# ── Year columns from REAL headers (بلا افتراض جهة السنة الحالية) ───────────

def _ln(x0, y0, x1, y1, text, conf=0.9):
    return LineBox(x0, y0, x1, y1, text, conf)


def test_year_columns_follow_their_own_headers_normal_layout():
    # RTL printed table: 2022 header at rel-x 0.62, 2021 at 0.25.
    lines = [
        _ln(560, 100, 680, 140, "2022"),
        _ln(220, 100, 300, 140, "2021"),
        _ln(700, 200, 900, 240, "إجمالي الالتزامات"),
        _ln(560, 200, 680, 240, "9,030,000,000"),
        _ln(220, 200, 340, 240, "8,250,000,000"),
    ]
    cols, detail = find_year_columns(lines, page_w=1000)
    assert set(cols) == {2022, 2021}, detail
    # 2022's range must cover its own header center and NOT reach 2021's.
    assert cols[2022].contains(0.62)
    assert not cols[2022].contains(0.25)
    assert cols[2021].contains(0.25)
    # the numeric line under each header maps to that header's column
    v22 = [v for v, _ in parse_number_tokens("9,030,000,000")]
    assert v22 == [9_030_000_000.0]


def test_year_columns_survive_a_mirrored_layout():
    # Mirrored rendering: 2021 sits to the RIGHT of 2022. The column ranges
    # must follow the headers themselves — not "current year is on the right".
    lines = [
        _ln(220, 100, 300, 140, "2021"),   # right side (x larger)
        _ln(560, 100, 680, 140, "2022"),   # left side
    ]
    cols, detail = find_year_columns(lines, page_w=1000)
    assert set(cols) == {2022, 2021}, detail
    assert cols[2022].contains(0.62)      # 2022 keeps ITS header position
    assert cols[2021].contains(0.25)
    assert detail.startswith("header row")


def test_missing_year_header_is_reported_not_assumed():
    lines = [_ln(560, 100, 680, 140, "2022")]
    cols, detail = find_year_columns(lines, page_w=1000)
    assert cols == {}
    assert "not co-located" in detail or "no pure" in detail


# ── The spatial gate in the decision log ────────────────────────────────────

def test_decision_log_downgrades_unconfirmed_year_assignment():
    d = FinancialData()
    d.candidates.setdefault("revenue", {})[2022] = [
        (16_665_919_878.0, 0), (16_665_919_878.0, 0)]
    d.values.setdefault("revenue", {})[2022] = 16_665_919_878.0
    d.confidence.setdefault("revenue", {})[2022] = 2
    # without spatial findings: two agreeing reads → VERIFIED_EXACT
    log = build_decision_log(d)
    entry = next(e for e in log if e["field"] == "revenue")
    assert entry["status"] == "VERIFIED_EXACT"
    # with an unconfirmed year assignment: downgraded, no EXACT
    d.spatial_findings = {("revenue", 2022): {
        "year_assignment": "unconfirmed", "detail": "year header not found"}}
    log = build_decision_log(d)
    entry = next(e for e in log if e["field"] == "revenue")
    assert entry["status"] == "UNVERIFIED"
    assert "الإسناد المكاني" in entry["reason"]
    assert entry["spatial"]["year_assignment"] == "unconfirmed"


def test_decision_log_keeps_verified_when_spatial_confirmed():
    d = FinancialData()
    d.candidates.setdefault("revenue", {})[2022] = [
        (16_665_919_878.0, 0), (16_665_919_878.0, 0)]
    d.values.setdefault("revenue", {})[2022] = 16_665_919_878.0
    d.confidence.setdefault("revenue", {})[2022] = 2
    d.spatial_findings = {("revenue", 2022): {
        "year_assignment": "confirmed", "detail": "header row found"}}
    log = build_decision_log(d)
    entry = next(e for e in log if e["field"] == "revenue")
    assert entry["status"] == "VERIFIED_EXACT"


# ── Date header detection (المهمة 2/6: التواريخ المطبوعة) ───────────────────

from src.extraction.spatial_cells import (  # noqa: E402
    find_date_columns, year_from_date_text,
)


def test_date_year_parsing_all_formats():
    assert year_from_date_text("٣١/١٢/٢٠٢٢") == 2022
    assert year_from_date_text("2022/12/31") == 2022
    assert year_from_date_text("31/12/2021") == 2021
    assert year_from_date_text("٢٠٢١/١٢/٣١") == 2021
    assert year_from_date_text("٢٠٢٢ / ١٢ / ٣١") == 2022


def test_date_year_garbled_or_absent_is_none():
    # the actual full-page OCR output of the printed dates
    assert year_from_date_text("4.41/14/1") is None
    assert year_from_date_text("Y. 11/11/1") is None
    assert year_from_date_text("") is None
    assert year_from_date_text("31/12") is None
    assert year_from_date_text("2021/12/31 2022") is None  # ambiguous


def test_find_date_columns_binds_year_to_its_own_column():
    # RTL layout: 2022 right, 2021 left — each above its currency title
    lines = [
        _ln(560, 100, 680, 140, ""),               # date above right col
        _ln(220, 100, 340, 140, ""),               # date above left col
        _ln(560, 160, 680, 190, "جنيه مصري"),      # right currency title
        _ln(220, 160, 340, 190, "جنيه مصري"),      # left currency title
    ]

    def reader(png, x0, y0, x1, y1):
        cx = (x0 + x1) / 2
        return "٢٠٢٢/١٢/٣١" if cx > 500 else "٢٠٢١/١٢/٣١"

    cols, detail = find_date_columns(
        None, b"", lines, 1000, 400, date_reader=reader)
    assert set(cols) == {2022, 2021}, detail
    assert cols[2022].contains(0.62) and not cols[2022].contains(0.25)
    assert cols[2021].contains(0.25)
    assert "printed column dates" in detail


def test_find_date_columns_survives_mirrored_layout():
    lines = [
        _ln(220, 100, 340, 140, ""),               # date above RIGHT col
        _ln(560, 100, 680, 140, ""),               # date above LEFT col
        _ln(220, 160, 340, 190, "جنيه مصري"),
        _ln(560, 160, 680, 190, "جنيه مصري"),
    ]

    def reader(png, x0, y0, x1, y1):
        cx = (x0 + x1) / 2
        return "31/12/2022" if cx < 500 else "31/12/2021"  # mirrored print

    cols, detail = find_date_columns(
        None, b"", lines, 1000, 400, date_reader=reader)
    assert set(cols) == {2022, 2021}, detail
    assert cols[2022].contains(0.25)      # follows ITS printed date
    assert cols[2021].contains(0.62)


def test_find_date_columns_unreadable_date_is_not_guessed():
    lines = [
        _ln(560, 100, 680, 140, ""),
        _ln(220, 100, 340, 140, ""),
        _ln(560, 160, 680, 190, "جنيه مصري"),
        _ln(220, 160, 340, 190, "جنيه مصري"),
    ]
    cols, detail = find_date_columns(
        None, b"", lines, 1000, 400,
        date_reader=lambda *a: "4.41/14/1")     # the real garbled output
    assert cols == {}
    assert "none readable" in detail


def test_date_in_page_header_is_not_a_column_title():
    # a date line far ABOVE the currency row (page header) must not bind
    lines = [
        _ln(100, 20, 900, 50, "القوائم المالية عن السنة المنتهية في ٣١/١٢/٢٠٢٢"),
        _ln(560, 100, 680, 140, ""),
        _ln(220, 100, 340, 140, ""),
        _ln(560, 160, 680, 190, "جنيه مصري"),
        _ln(220, 160, 340, 190, "جنيه مصري"),
    ]
    cols, detail = find_date_columns(
        None, b"", lines, 1000, 400,
        date_reader=lambda *a: "")
    assert cols == {}
    assert "none readable" in detail or "not co-located" in detail
