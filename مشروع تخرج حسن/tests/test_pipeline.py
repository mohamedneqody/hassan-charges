"""Pipeline tests — runnable with pytest OR directly: python tests/test_pipeline.py

No network access required: the Gemini call is tested only for its
graceful-degradation paths (missing key / malformed JSON).
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from src.analysis.calculator import compute_year_metrics, growth_pct
from src.analysis.comparison import (
    DECLINING,
    IMPROVING,
    NEGATIVE,
    POSITIVE,
    STABLE,
    build_comparison,
    growth_metrics,
    missing_data_report,
)
from src.exceptions import EmptyFileError, InsufficientDataError, UnsupportedFormatError
from src.extraction.file_parsers import _parse_pdf_text_lines, load_financial_data
from src.extraction.normalizer import (
    extract_year,
    match_field,
    parse_number,
    parse_table,
)
from src.pipeline import build_gemini_payload, run_pipeline


import pytest
@pytest.fixture(autouse=True)
def _isolated_model_health(monkeypatch):
    """عزل ملف الصحة الدائمة — الاختبارات لا تلوث cache/model_health.json
    (الذي يحمله التشغيل الحي عبر التشغيلات) ولا تتلوث منه."""
    from src.ai import key_pool as _kp

    monkeypatch.setattr(_kp.APIKeyPool, "_save_model_health",
                        lambda self: None, raising=False)
    monkeypatch.setattr(_kp.APIKeyPool, "_load_model_health",
                        lambda self: None, raising=False)


SAMPLE_CSV = PROJECT_ROOT / "sample_data" / "sample_financials.csv"
SAMPLE_XLSX = PROJECT_ROOT / "sample_data" / "sample_financials.xlsx"


# ---------------------------------------------------------------------------
# Normalization & matching
# ---------------------------------------------------------------------------

def test_alias_matching():
    assert match_field("Net Sales") == "revenue"
    assert match_field("PROFIT AFTER TAX") == "net_income"
    assert match_field("total_assets") == "total_assets"
    assert match_field("Total  Assets") == "total_assets"
    assert match_field("Cost of Goods Sold (COGS)") == "cost_of_revenue"
    assert match_field("Total Shareholders Equity") == "equity"
    assert match_field("Inventories") == "inventory"
    assert match_field("المخزون") == "inventory"
    assert match_field("Net Cash from Operating Activities") == "operating_cash_flow"
    # Derived lines must never map (system computes them itself)
    assert match_field("Revenue Growth") is None
    assert match_field("Gross Profit Margin") is None
    assert match_field("Current Ratio") is None
    assert match_field("Earnings Per Share") is None
    # Tricky exclusion
    assert match_field("Total Liabilities and Equity") is None
    # Arabic aliases
    assert match_field("الإيرادات") == "revenue"
    assert match_field("صافي الربح") == "net_income"
    assert match_field("إجمالي الأصول") == "total_assets"
    assert match_field("الأصول المتداولة") == "current_assets"
    assert match_field("حقوق الملكية") == "equity"


def test_parse_number():
    assert parse_number("(1,234.5)") == -1234.5
    assert parse_number("$2,000") == 2000.0
    assert parse_number("1 000 000") == 1_000_000.0
    assert parse_number("12%") == 12.0
    assert parse_number("—") is None
    assert parse_number("") is None
    assert parse_number("n/a") is None
    assert parse_number(1000) == 1000.0
    assert parse_number("-45.5") == -45.5
    assert parse_number("١٢٣٤") == 1234.0  # Arabic-Indic digits
    assert parse_number("(2,500)") == -2500.0


def test_extract_year():
    assert extract_year("FY2025") == 2025
    assert extract_year("2026") == 2026
    assert extract_year("Dec 31, 2025") == 2025
    assert extract_year(2024) == 2024
    assert extract_year("Total Revenue") is None
    assert extract_year(1899) is None


def test_transposed_table():
    df = pd.DataFrame(
        [
            ["Year", "Revenue", "Net Income"],
            ["2025", "1,000", "180"],
            ["2026", "1,180", "165"],
        ],
        dtype=object,
    )
    parsed = parse_table(df)
    assert parsed[2025]["revenue"] == 1000.0
    assert parsed[2026]["net_income"] == 165.0


def test_percentage_rows_skipped():
    df = pd.DataFrame(
        [
            ["Line Item", "FY2025", "FY2026"],
            ["Revenue", "1,000", "1,180"],
            ["Gross Margin", "58%", "56%"],  # derived row: must be ignored
        ],
        dtype=object,
    )
    parsed = parse_table(df)
    assert parsed[2025] == {"revenue": 1000.0}
    assert parsed[2026] == {"revenue": 1180.0}


def test_pdf_text_fallback():
    lines = [
        "ACME Industries - Annual Report",
        "                            2025        2026",
        "Revenue                 1,000,000   1,180,000",
        "Net Profit                (30,000)     165,000",
    ]
    frames = _parse_pdf_text_lines(lines)
    parsed = parse_table(frames[0])
    assert parsed[2025]["revenue"] == 1_000_000.0
    assert parsed[2026]["revenue"] == 1_180_000.0
    assert parsed[2025]["net_income"] == -30_000.0


# ---------------------------------------------------------------------------
# Calculations
# ---------------------------------------------------------------------------

def make_data():
    return {
        "revenue": {2025: 1_000_000, 2026: 1_180_000},
        "cost_of_revenue": {2025: 420_000, 2026: 520_000},
        "gross_profit": {2025: 580_000, 2026: 660_000},
        "operating_expenses": {2025: 300_000, 2026: 360_000},
        "operating_income": {2025: 280_000, 2026: 300_000},
        "net_income": {2025: 180_000, 2026: 165_000},
        "pretax_income": {2025: 225_000, 2026: 205_000},
        "income_tax_expense": {2025: 45_000, 2026: 40_000},
        "depreciation_amortization": {2025: 90_000, 2026: 105_000},
        "selling_expenses": {2025: 140_000, 2026: 165_000},
        "rd_expenses": {2025: 60_000, 2026: 75_000},
        "interest_expense": {2025: 45_000, 2026: 60_000},
        "total_assets": {2025: 1_500_000, 2026: 1_650_000},
        "current_assets": {2025: 600_000, 2026: 560_000},
        "inventory": {2025: 120_000, 2026: 150_000},
        "accounts_receivable": {2025: 180_000, 2026: 220_000},
        "cash": {2025: 150_000, 2026: 120_000},
        "fixed_assets": {2025: 700_000, 2026: 850_000},
        "accounts_payable": {2025: 140_000, 2026: 160_000},
        "current_liabilities": {2025: 250_000, 2026: 340_000},
        "total_liabilities": {2025: 700_000, 2026: 850_000},
        "total_debt": {2025: 400_000, 2026: 520_000},
        "equity": {2025: 800_000, 2026: 800_000},
        "operating_cash_flow": {2025: 220_000, 2026: 190_000},
        "capex": {2025: -120_000, 2026: -160_000},
    }


def test_calculations():
    data = make_data()
    prev = compute_year_metrics(2025, data, prev_year=None)
    curr = compute_year_metrics(2026, data, prev_year=2025)

    assert round(prev.gross_margin, 9) == 58.0
    assert round(curr.gross_margin, 9) == round(660_000 / 1_180_000 * 100, 9)
    assert round(prev.net_margin, 9) == 18.0
    assert round(curr.net_margin, 2) == round(165_000 / 1_180_000 * 100, 2)

    # ROA/ROE on average balances, with explanatory notes
    assert round(prev.roa, 9) == 12.0
    assert round(curr.roa, 9) == round(165_000 / ((1_500_000 + 1_650_000) / 2) * 100, 9)
    assert "average total assets" in curr.notes["roa"]
    assert round(curr.roe, 9) == round(165_000 / 800_000 * 100, 9)

    assert round(prev.current_ratio, 9) == 2.4
    assert round(curr.current_ratio, 4) == round(560_000 / 340_000, 4)
    assert round(prev.debt_to_equity, 9) == 0.5
    assert round(curr.debt_to_equity, 9) == 0.65

    # Liquidity / leverage / efficiency additions
    assert round(prev.quick_ratio, 9) == round((600_000 - 120_000) / 250_000, 9)  # 1.92
    assert round(curr.quick_ratio, 9) == round((560_000 - 150_000) / 340_000, 9)
    assert round(prev.debt_ratio, 9) == round(700_000 / 1_500_000, 9)
    assert round(curr.debt_ratio, 9) == round(850_000 / 1_650_000, 9)
    assert round(prev.asset_turnover, 9) == round(1_000_000 / 1_500_000, 9)
    assert round(curr.asset_turnover, 9) == round(1_180_000 / ((1_500_000 + 1_650_000) / 2), 9)
    assert round(prev.inventory_turnover, 9) == round(420_000 / 120_000, 9)
    assert round(curr.inventory_turnover, 9) == round(520_000 / ((120_000 + 150_000) / 2), 9)
    # averages available for 2026 -> no fallback note; 2025 uses its own balance
    assert "asset_turnover" not in curr.notes
    assert "inventory_turnover" not in curr.notes

    # --- Extended criteria ---
    # EBITDA / FCF derived absolutes
    assert prev.ebitda == 370_000 and curr.ebitda == 405_000
    assert round(prev.ebitda_margin, 6) == 37.0
    assert round(curr.ebitda_margin, 6) == round(405_000 / 1_180_000 * 100, 6)
    assert prev.free_cash_flow == 100_000 and curr.free_cash_flow == 30_000
    # Returns: ROIC / ROCE
    rate25 = 45_000 / 225_000
    assert round(prev.roic, 6) == round(280_000 * (1 - rate25) / 1_200_000 * 100, 6)
    rate26 = 40_000 / 205_000
    assert round(curr.roic, 6) == round(300_000 * (1 - rate26) / 1_320_000 * 100, 6)
    assert round(prev.roce, 6) == round(280_000 / 1_250_000 * 100, 6)
    assert round(curr.roce, 6) == round(300_000 / 1_310_000 * 100, 6)
    # Liquidity additions
    assert round(prev.cash_ratio, 6) == 0.6
    assert round(curr.cash_ratio, 6) == round(120_000 / 340_000, 6)
    assert round(prev.ocf_ratio, 6) == 0.88
    # Leverage additions
    assert round(prev.debt_to_assets, 6) == round(400_000 / 1_500_000, 6)
    assert round(curr.liabilities_to_equity, 6) == round(850_000 / 800_000, 6)
    assert round(curr.equity_ratio, 6) == round(800_000 / 1_650_000, 6)
    assert round(curr.financial_leverage, 6) == round(1_650_000 / 800_000, 6)
    assert round(prev.interest_coverage, 6) == round(280_000 / 45_000, 6)
    # Turnovers & days
    assert round(curr.receivables_turnover, 6) == round(1_180_000 / 200_000, 6)
    assert round(curr.payables_turnover, 6) == round(520_000 / 150_000, 6)
    assert round(curr.inventory_days, 4) == round(365 / curr.inventory_turnover, 4)
    assert round(curr.days_sales_outstanding, 4) == round(365 / curr.receivables_turnover, 4)
    assert round(curr.days_payables_outstanding, 4) == round(365 / curr.payables_turnover, 4)
    assert round(curr.cash_conversion_cycle, 4) == round(
        curr.inventory_days + curr.days_sales_outstanding - curr.days_payables_outstanding, 4)
    assert round(prev.cash_conversion_cycle, 4) == round(
        prev.inventory_days + prev.days_sales_outstanding - prev.days_payables_outstanding, 4)
    # Working capital
    assert prev.working_capital == 350_000 and curr.working_capital == 220_000
    assert prev.operating_working_capital == 160_000
    assert round(curr.working_capital_turnover, 4) == round(1_180_000 / ((350_000 + 220_000) / 2), 4)
    # Cash flow ratios
    assert round(prev.cfo_margin, 6) == 22.0
    assert round(curr.fcf_margin, 6) == round(30_000 / 1_180_000 * 100, 6)
    assert round(prev.cfo_to_net_income, 6) == round(220_000 / 180_000, 6)
    assert round(curr.cfo_to_debt, 6) == round(190_000 / 520_000, 6)
    assert round(curr.capex_coverage, 6) == round(190_000 / 160_000, 6)
    assert round(curr.cash_roa, 6) == round(190_000 / 1_575_000 * 100, 6)
    # Cost structure
    assert round(prev.cogs_pct, 6) == 42.0
    assert round(prev.opex_pct, 6) == 30.0
    assert round(curr.selling_pct, 6) == round(165_000 / 1_180_000 * 100, 6)
    assert round(prev.rd_pct, 6) == 6.0
    assert round(curr.interest_pct, 6) == round(60_000 / 1_180_000 * 100, 6)
    assert round(prev.tax_rate, 6) == 20.0

    assert round(growth_pct(1_000_000, 1_180_000), 9) == 18.0
    assert round(growth_pct(180_000, 165_000), 9) == round((165_000 - 180_000) / 180_000 * 100, 9)
    assert growth_pct(0, 100) is None
    assert growth_pct(-100, 50) is None
    assert growth_pct(None, 100) is None


def test_comparison_and_trends():
    data = make_data()
    prev = compute_year_metrics(2025, data, prev_year=None)
    curr = compute_year_metrics(2026, data, prev_year=2025)
    rows = {r.key: r for r in build_comparison(prev, curr)}

    assert rows["revenue"].trend == IMPROVING
    assert rows["revenue"].status == POSITIVE
    assert rows["revenue"].change == 180_000
    assert rows["revenue"].change_pct == 18.0

    assert rows["net_margin"].trend == DECLINING  # 18% -> ~13.98%
    assert rows["net_margin"].status == NEGATIVE
    assert rows["debt_to_equity"].trend == DECLINING  # 0.5 -> 0.65, higher is worse

    growth = {r.key: r for r in growth_metrics(prev, curr)}
    assert len(growth) == 7
    assert growth["revenue_growth"].current == 18.0
    assert growth["net_profit_growth"].current < 0
    assert growth["assets_growth"].current == 10.0
    assert growth["cfo_growth"].current < 0

    missing = missing_data_report(list(rows.values()))
    assert any("Investing" in m for m in missing)  # no cash-flow investing data


def test_stable_trend():
    data = make_data()
    data["total_debt"][2026] = data["total_debt"][2025]  # isolate equity effect
    data["equity"][2026] = 800_000 * 1.005  # +0.5% => below 1% threshold
    prev = compute_year_metrics(2025, data, prev_year=None)
    curr = compute_year_metrics(2026, data, prev_year=2025)
    rows = {r.key: r for r in build_comparison(prev, curr)}
    # D/E: debt unchanged, equity up 0.5% -> relative change ~ -0.5% -> Stable
    de = rows["debt_to_equity"]
    assert abs(de.change_pct) < 1.0, f"change_pct={de.change_pct}"
    assert de.trend == STABLE, f"trend={de.trend}, change_pct={de.change_pct}"


def test_missing_data_never_invented():
    data = {"revenue": {2025: 1000.0, 2026: 1200.0}}
    prev = compute_year_metrics(2025, data)
    curr = compute_year_metrics(2026, data, prev_year=2025)
    assert prev.roa is None and curr.roa is None
    assert prev.current_ratio is None and curr.current_ratio is None
    assert prev.quick_ratio is None and curr.quick_ratio is None
    assert prev.inventory_turnover is None and curr.inventory_turnover is None
    # extended metrics stay None without their inputs
    assert curr.roic is None and curr.roce is None
    assert curr.cash_ratio is None and curr.interest_coverage is None
    assert curr.cash_conversion_cycle is None and curr.free_cash_flow is None
    assert curr.cogs_pct is None and curr.tax_rate is None
    rows = {r.key: r for r in build_comparison(prev, curr)}
    assert rows["roa"].status == "N/A"
    assert "Total Assets" in rows["roa"].reason or "assets" in rows["roa"].reason.lower()
    assert "Inventory" in rows["quick_ratio"].reason


def test_narrative_fallback_english():
    import src.analysis.narrative as narrative
    from src.ai.gemini_agent import AIAnalysis

    original = narrative.REPORT_LANGUAGE
    narrative.REPORT_LANGUAGE = "en"
    try:
        raw = SAMPLE_CSV.read_bytes()
        results = run_pipeline("sample_financials.csv", raw, "Sample Corp")
        analysis = narrative.build_fallback_narrative(results, AIAnalysis(ok=False, error="no key"))
        assert analysis.ok is False
        assert analysis.error == "no key"
        # One comment per commentable metric: 53 rows + 7 growth rows, sample is complete
        assert len(analysis.ratio_comments) == 60
        names = [m for m, _ in analysis.ratio_comments]
        for expected in ("الإيرادات", "النسبة السريعة", "الدين إلى حقوق الملكية", "العائد على رأس المال المستثمر (ROIC)",
                         "نسبة النقدية", "تغطية الفوائد", "دورة التحويل النقدي",
                         "التدفق النقدي الحر", "نسبة الضريبة الفعلية", "رأس المال العامل"):
            assert expected in names, f"missing comment for {expected}"
        comments = dict(analysis.ratio_comments)
        # direction + exact values + hedged meaning, one/two lines max
        assert "rose from $1M to $1.18M" in comments["الإيرادات"]
        assert "may indicate" in comments["هامش صافي الربح"]
        assert "1.65x" in comments["النسبة الجارية"]
        assert "1.21x" in comments["النسبة السريعة"]
        assert "fell from 2.40x to 1.65x" in comments["النسبة الجارية"]
        assert "reached +18.0%" in comments["نمو الإيرادات"]
        # 3-5 recommendations, EACH with numeric evidence
        assert 3 <= len(analysis.recommendations) <= 5
        for action, evidence in analysis.recommendations:
            assert action.strip()
            assert evidence.strip() and any(ch.isdigit() for ch in evidence), \
                f"rec without evidence: {action!r} -> {evidence!r}"
    finally:
        narrative.REPORT_LANGUAGE = original


def test_narrative_fallback_arabic():
    import src.analysis.narrative as narrative
    from src.ai.gemini_agent import AIAnalysis

    original = narrative.REPORT_LANGUAGE
    narrative.REPORT_LANGUAGE = "ar"
    try:
        raw = SAMPLE_CSV.read_bytes()
        results = run_pipeline("sample_financials.csv", raw, "Sample Corp")
        analysis = narrative.build_fallback_narrative(results, AIAnalysis(ok=False, error="x"))
        names = dict(analysis.ratio_comments)
        net_margin = names["هامش صافي الربح"]
        # comment is Arabic, hedged, quotes both values (name is the dict key / UI prefix)
        assert "من 18.0% إلى 14.0%" in net_margin
        assert "قد يشير إلى" in net_margin
        assert "1.65x" in names["النسبة الجارية"]
        assert "بين عامي 2025 و2026" in names["نمو الإيرادات"]
        # each recommendation carries a numeric evidence line
        assert 3 <= len(analysis.recommendations) <= 5
        for action, evidence in analysis.recommendations:
            assert any(ch.isdigit() for ch in evidence), f"no evidence: {action!r}"
            assert any("\u0600" <= ch <= "\u06FF" for ch in evidence)
    finally:
        narrative.REPORT_LANGUAGE = original


def test_gemini_parse_response():
    from src.ai.gemini_agent import parse_response

    raw = json.dumps(
        {
            "ratio_comments": [
                {"metric": "Revenue", "comment": "ارتفع من $1M إلى $1.18M."},
                {"metric": "ROA", "comment": "انخفض من 12.0% إلى 10.5%."},
            ],
            "recommendations": [
                {"action": "مراجعة التكاليف.", "evidence": "Net Margin: 12.5%."},
                "توصية نصية بسيطة.",
            ],
        },
        ensure_ascii=False,
    )
    analysis = parse_response(raw)
    assert analysis.ok is True
    assert analysis.ratio_comments == [
        ("Revenue", "ارتفع من $1M إلى $1.18M."),
        ("ROA", "انخفض من 12.0% إلى 10.5%."),
    ]
    assert analysis.recommendations == [
        ("مراجعة التكاليف.", "Net Margin: 12.5%."),
        ("توصية نصية بسيطة.", ""),
    ]
    # fenced JSON is tolerated
    assert parse_response("```json\n" + raw + "\n```").ok is True
    # malformed shapes raise
    try:
        parse_response('{"ratio_comments": "not a list"}')
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_gemini_payload_shape():
    raw = SAMPLE_CSV.read_bytes()
    results = run_pipeline("sample_financials.csv", raw, "Sample Corp")
    payload = build_gemini_payload(results, "$")
    assert payload["company"] == "Sample Corp"
    assert payload["analysis_period"] == {"previous_year": 2025, "current_year": 2026}
    entries = {m["metric"]: m for m in payload["metrics"]}
    # growth rows come first with a single value
    assert payload["metrics"][0]["metric"] == "نمو الإيرادات"
    assert payload["metrics"][0]["value"] == "+18.0%"
    assert payload["metrics"][0]["direction"] == "rose"
    # two-year metrics carry pre-formatted strings + direction + assessment
    # (unit chain: the Arabic magnitude word replaces the ambiguous "M")
    rev = entries["الإيرادات"]
    assert rev["previous"] == "$1 مليون" and rev["current"] == "$1.18 مليون"
    assert rev["direction"] == "rose" and rev["assessment"] == "improving"
    de = entries["الدين إلى حقوق الملكية"]
    assert de["previous"] == "0.50x" and de["current"] == "0.65x"
    assert de["direction"] == "rose" and de["assessment"] == "declining"
    # N/A metrics are skipped entirely (none missing in the sample)
    assert all(m.get("previous") is not None or m.get("value") for m in payload["metrics"])


# ---------------------------------------------------------------------------
# File-level end to end
# ---------------------------------------------------------------------------

def test_end_to_end_csv():
    raw = SAMPLE_CSV.read_bytes()
    data = load_financial_data("sample_financials.csv", raw)
    assert data.years == [2026, 2025]
    assert data.get("revenue", 2026) == 1_180_000
    assert data.get("net_income", 2025) == 180_000
    assert data.get("investing_cash_flow", 2026) == -210_000  # parenthesized negative

    results = run_pipeline("sample_financials.csv", raw, "Sample Corp")
    assert (results["prev_year"], results["curr_year"]) == (2025, 2026)
    assert results["rows_by_key"]["revenue"].current == 1_180_000
    assert results["growth_rows"][0].current == 18.0
    for key in ("quick_ratio", "debt_ratio", "asset_turnover", "inventory_turnover"):
        assert key in results["rows_by_key"], f"missing {key} row"
        assert results["rows_by_key"][key].current is not None
    assert not any("Insufficient" in m for m in results["missing"])

    payload = build_gemini_payload(results, "$")
    assert payload["company"] == "Sample Corp"
    assert any(m["metric"] == "الإيرادات" for m in payload["metrics"])


def test_end_to_end_xlsx_multisheet():
    raw = SAMPLE_XLSX.read_bytes()
    data = load_financial_data("sample_financials.xlsx", raw)
    assert data.years == [2026, 2025]
    assert data.get("total_assets", 2026) == 1_650_000
    assert data.get("operating_cash_flow", 2025) == 220_000
    results = run_pipeline("sample_financials.xlsx", raw, "Sample Corp")
    assert results["rows_by_key"]["current_ratio"].current is not None


def test_validation_errors():
    try:
        load_financial_data("report.docx", b"whatever")
        raise AssertionError("expected UnsupportedFormatError")
    except UnsupportedFormatError:
        pass
    try:
        load_financial_data("empty.csv", b"")
        raise AssertionError("expected EmptyFileError")
    except EmptyFileError:
        pass
    # Single-year data => insufficient
    df = pd.DataFrame([["Line Item", "FY2026"], ["Revenue", "1,180"]], dtype=object)
    csv_bytes = df.to_csv(index=False, header=False).encode()
    try:
        run_pipeline("one_year.csv", csv_bytes, "X")
        raise AssertionError("expected InsufficientDataError")
    except InsufficientDataError as exc:
        assert "Insufficient financial data" in str(exc)


def test_three_years_uses_latest_two():
    csv_text = (
        "Line Item,FY2024,FY2025,FY2026\n"
        "Revenue,900000,1000000,1180000\n"
        "Net Income,150000,180000,165000\n"
    )
    results = run_pipeline("three_years.csv", csv_text.encode(), "X")
    assert (results["prev_year"], results["curr_year"]) == (2025, 2026)
    assert results["rows_by_key"]["revenue"].previous == 1_000_000


def test_health_score_and_top_movers():
    from src.analysis.score import compute_health_score, top_movers

    data = make_data()
    prev = compute_year_metrics(2025, data, prev_year=None)
    curr = compute_year_metrics(2026, data, prev_year=2025)

    score = compute_health_score(curr)
    assert 0 <= score.total <= 100
    # hand-computed pillars for the fixture:
    liq = next(p for p in score.pillars if p.key == "liquidity")
    assert round(liq.score, 1) == round((min(100, 1.6470588 * 50) + 100) / 2, 1)
    lev = next(p for p in score.pillars if p.key == "leverage")
    assert round(lev.score, 1) == round(((1 - 0.65 / 2) * 100 + (1 - 850_000 / 1_650_000) * 100) / 2, 1)
    cash = next(p for p in score.pillars if p.key == "cash")
    assert cash.score == 100.0  # CFO/NI > 1.0 and CFO margin 16.1% > 15%
    assert score.label in ("Strong", "Stable", "Needs attention", "Weak", "قوي", "مستقر")

    # missing data: liquidity+leverage missing → the score is REFUSED, not
    # renormalized around the hole (a reassuring score would hide risk)
    sparse = {"revenue": {2026: 1000.0}, "net_income": {2026: 100.0}}
    curr_sparse = compute_year_metrics(2026, sparse)
    score2 = compute_health_score(curr_sparse)
    available = [p for p in score2.pillars if p.score is not None]
    assert all(p.key in ("profitability",) for p in available)
    assert score2.total is None                        # refused
    assert score2.coverage < 0.5
    assert not score2.complete
    assert "liquidity" in score2.missing_pillars
    assert "مرفوض" in score2.label_ar

    # top movers: strongest improving / declining by |change %|
    rows = build_comparison(prev, curr)
    improving, declining = top_movers(rows)
    assert improving and improving[0].status == "Positive"
    assert declining and declining[0].status == "Negative"
    assert all(r.change_pct is not None for r in improving + declining)


def test_vision_json_to_parts():
    import io as _io

    from src.extraction.normalizer import parse_table
    from src.extraction.vision_ocr import _page_to_frame, _parse_vision_json

    raw = json.dumps(
        {
            "pages": [
                {
                    "page": 1,
                    "years": [2021, 2022],
                    "rows": [
                        ["المبيعات", 100000, 120000],
                        {"label": "صافي الربح", "values": [20000, 25000]},
                        ["سرد بلا أرقام", None, None],  # must be dropped
                    ],
                }
            ]
        },
        ensure_ascii=False,
    )
    pages = _parse_vision_json(raw)
    assert pages[0]["years"] == [2021, 2022]
    frame = _page_to_frame(pages[0])
    parsed = parse_table(frame)
    assert parsed[2022]["revenue"] == 120000.0
    assert parsed[2021]["revenue"] == 100000.0
    assert parsed[2022]["net_income"] == 25000.0

    # single-year page is skipped (the system compares two years)
    one_year = _parse_vision_json(json.dumps({"pages": [{"page": 2, "years": [2022], "rows": [["مبيعات", 5]]}]}))
    assert _page_to_frame(one_year[0]) is None


def test_preprocess_image_synthetic():
    import cv2
    import numpy as np

    from src.extraction.vision_ocr import preprocess_image

    img = np.full((400, 600), 255, np.uint8)
    cv2.rectangle(img, (50, 50), (550, 350), 0, 2)
    cv2.putText(img, "2022", (60, 90), cv2.FONT_HERSHEY_SIMPLEX, 1.2, 0, 2)
    ok, png = cv2.imencode(".png", img)
    assert ok
    out = preprocess_image(png.tobytes())
    assert isinstance(out, bytes) and len(out) > 0
    decoded = cv2.imdecode(np.frombuffer(out, np.uint8), cv2.IMREAD_GRAYSCALE)
    assert decoded is not None and decoded.size > 0


def test_is_scanned_pdf_detection():
    import io as _io

    from PIL import Image

    from src.extraction.vision_ocr import is_scanned_pdf

    img = Image.new("RGB", (600, 800), "white")
    buf = _io.BytesIO()
    img.save(buf, format="PDF")
    assert is_scanned_pdf("scan.pdf", buf.getvalue()) is True
    assert is_scanned_pdf("data.xlsx", b"whatever") is False


def test_reconciliation_picks_identity_consistent():
    from src.extraction.normalizer import merge_parsed, reconcile

    # The real-file trap: a wrong value captured FIRST for total_assets
    part1 = {2026: {"total_assets": 288000.0, "equity": 200000.0}}
    part2 = {2026: {"total_assets": 537000.0, "total_liabilities": 337000.0}}
    data = merge_parsed([part1, part2], [])
    reconcile(data)
    # assets = liabilities + equity only holds for 537000
    assert data.get("total_assets", 2026) == 537000.0
    assert data.get("equity", 2026) == 200000.0
    assert data.get("total_liabilities", 2026) == 337000.0
    assert any("Reconciled" in n for n in data.notes)

    # gross profit identity with negative-stored cost
    part_a = {2025: {"revenue": 420000.0, "gross_profit": 685000.0}}
    part_b = {2025: {"cost_of_revenue": -265000.0}}
    data2 = merge_parsed([part_a, part_b], [])
    reconcile(data2)
    assert data2.get("gross_profit", 2025) == 155000.0  # 420 - 265

    # single candidates: reconcile must be a no-op
    data3 = merge_parsed([{2025: {"revenue": 1000.0}}], [])
    reconcile(data3)
    assert data3.get("revenue", 2025) == 1000.0


def test_ai_number_audit_and_repair():
    import json as _json

    from src.ai.gemini_agent import analyze_financials, _audit_comments
    from src.ai.key_pool import APIKeyPool

    payload = {
        "company": "X",
        "analysis_period": {"previous_year": 2025, "current_year": 2026},
        "metrics": [
            {"metric": "Revenue", "previous": "$1M", "current": "$1.18M",
             "change_pct": "+18.0%", "direction": "rose", "assessment": "improving"},
            {"metric": "ROA", "previous": "12.0%", "current": "10.5%",
             "change_pct": "-12.5%", "direction": "fell", "assessment": "declining"},
        ],
        "missing_data": [], "extraction_notes": [],
    }
    bad_first = _json.dumps(
        {
            "ratio_comments": [
                {"metric": "Revenue", "comment": "ارتفع من $1M إلى $1.18M."},   # clean
                {"metric": "ROA", "comment": "انخفض من 12.0% إلى 15.9%."},       # 15.9 invented
            ],
            "recommendations": [
                {"action": "مراقبة العائد على الأصول.", "evidence": "ROA: من 12.0% إلى 10.5%."},
                {"action": "توصية مختلقة.", "evidence": "نمت المبيعات بنسبة 77.3%."},  # invented
            ],
        },
        ensure_ascii=False,
    )
    repaired = _json.dumps(
        {
            "ratio_comments": [
                {"metric": "ROA", "comment": "انخفض من 12.0% إلى 10.5%."},
            ],
        },
        ensure_ascii=False,
    )
    calls = []

    def caller(key, model, prompt, config):
        calls.append(prompt)
        return bad_first if len(calls) == 1 else repaired

    analysis = analyze_financials(payload, pool=APIKeyPool(["k1"], ["m1"]), caller=caller)
    assert analysis.ok is True
    assert len(calls) == 2, "repair call should happen"
    names = dict(analysis.ratio_comments)
    assert "15.9" not in names.get("ROA", "")
    assert "10.5%" in names["ROA"]
    assert "Revenue" in names  # clean comment kept
    # recommendation audit: evidence citing real values kept, invented dropped
    assert len(analysis.recommendations) == 1
    assert "ROA" in analysis.recommendations[0][1]
    assert "10.5%" in analysis.recommendations[0][1]
    assert not any("77.3" in e for _, e in analysis.recommendations)

    # audit unit: clean comment not flagged
    clean = type("A", (), {"ratio_comments": [("Revenue", "ارتفع من $1M إلى $1.18M.")]})()
    missing, suspects = _audit_comments(clean, payload)
    assert suspects == [] and missing == ["ROA"]


def test_pretax_never_net_income():
    # The real-file trap: OCR phrasings of a BEFORE-TAX row must never
    # land in net_income (it corrupted NI and every ratio built on it).
    from src.extraction.normalizer import match_field

    assert match_field("صافي ربح العام قبل الضريبة") in (None, "pretax_income")
    assert match_field("صافي الربح قبل الضريبة") == "pretax_income"
    assert match_field("الربح قبل الضريبة") == "pretax_income"
    assert match_field("صافي أرباح العام") == "net_income"  # clean NI still matches


def test_liabilities_noncurrent_excluded():
    # Same trap as total_assets: non-current liability totals must never
    # be captured as total liabilities (it poisoned leverage ratios).
    from src.extraction.normalizer import match_field

    # عز 2023: للصفين حقل كانوني الآن — الوجهة non_current_liabilities
    # (كانت مستبعدة كليًا قبل وجود الحقل) — والنية الأصلية باقية:
    # لا يُمسكان أبدًا كالتزامات إجمالية
    got1 = match_field("إجمالي الالتزامات غير المتداولة")
    got2 = match_field("الخصوم غير المتداولة")
    assert got1 == "non_current_liabilities"
    assert got2 == "non_current_liabilities"
    assert got1 != "total_liabilities" and got2 != "total_liabilities"
    assert match_field("إجمالي الخصوم") == "total_liabilities"
    assert match_field("إجمالي الالتزامات") == "total_liabilities"


def test_reconcile_flags_but_never_forces_assets():
    from src.extraction.normalizer import FinancialData, merge_parsed, reconcile

    # The user's real-file case: assets captured CORRECTLY (15.97B) but
    # liabilities misread (0.715B) + equity correct (6.94B) sum to 7.66B.
    # The old derive-if-fails replaced the CORRECT assets — forbidden now.
    part1 = {2022: {"total_assets": 15_970_000_000.0}}
    part2 = {2022: {"total_liabilities": 715_000_000.0, "equity": 6_940_000_000.0}}
    data = merge_parsed([part1, part2], [])
    reconcile(data)
    assert data.get("total_assets", 2022) == 15_970_000_000.0  # capture kept
    assert any("identity check FAILED" in n for n in data.notes)  # flagged honestly

    # consistent case still reconciles candidates normally
    part3 = {2022: {"total_assets": 7_655_000_000.0}}
    data2 = merge_parsed([part3, part2], [])
    reconcile(data2)
    assert data2.get("total_assets", 2022) == 7_655_000_000.0
    assert not any("FAILED" in n for n in data2.notes)


def test_currency_detection():
    import io as _io

    import pandas as pd

    from src.extraction.file_parsers import _currency_hint_from_frames
    from src.extraction.vision_ocr import _currency_hint

    assert _currency_hint("جميع المبالغ بالجنيه المصري") == "ج.م"
    assert _currency_hint("Amounts in EGP") == "EGP"
    assert _currency_hint("no currency here") is None
    df = pd.DataFrame([["المبيعات بالجنيه", 100]], dtype=object)
    assert _currency_hint_from_frames([df]) == "ج.م"


def test_parallel_equals_sequential():
    """THE PROOF: parallel vision extraction yields byte-identical financial
    data to sequential extraction — parallelism changes timing, not content
    (every page keeps its own image + prompt + temperature 0)."""
    import io as _io

    from PIL import Image
    from src.extraction.vision_ocr import extract_via_vision
    from src.ai.key_pool import APIKeyPool

    # 4-page scanned-style PDF (image-only)
    pages_imgs = [Image.new("RGB", (400, 300), "white") for _ in range(4)]
    buf = _io.BytesIO()
    pages_imgs[0].save(buf, format="PDF", save_all=True, append_images=pages_imgs[1:])
    pdf_bytes = buf.getvalue()

    def fake_caller(key, model, prompt, images):
        # deterministic per-page rows derived from the batch's page numbers
        import re as _re
        m = _re.search(r"pages (\d+) to (\d+)", prompt)
        a, b = int(m.group(1)), int(m.group(2))
        pages = []
        for p in range(a, b + 1):
            pages.append({
                "page": p,
                "currency": "جنيه مصري",
                "years": [2023, 2024],
                "rows": [["المبيعات", 1000 * p, 1200 * p], ["صافي الربح", 100 * p, 150 * p]],
            })
        return json.dumps({"pages": pages}, ensure_ascii=False)

    payload_pool = APIKeyPool(["k1", "k2"], ["m1", "m2"])

    seq = extract_via_vision(pdf_bytes, [], pool=payload_pool, workers=1, caller=fake_caller)
    par = extract_via_vision(pdf_bytes, [], pool=payload_pool, workers=4, caller=fake_caller)

    # identical financial data, identical currency hint — THE PROOF
    assert seq.values == par.values
    assert seq.currency_hint == par.currency_hint == "ج.م"
    # deterministic merge semantics (first page wins) identical in both modes
    assert par.get("revenue", 2024) == 1200.0
    assert par.get("net_income", 2023) == 100.0
    # all 4 pages' years detected
    assert par.years == [2024, 2023]


def test_pool_thread_safety():
    import threading

    from src.ai.key_pool import APIKeyPool

    pool = APIKeyPool(["k1", "k2", "k3"], ["m1", "m2"])
    picked: list = []
    lock = threading.Lock()

    def worker():
        for _ in range(20):
            got = pool.pick()
            if got:
                with lock:
                    picked.append((got[0].key, got[1]))

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # every pick was a valid pair, and all 6 pairs got used
    valid = {("k1", "m1"), ("k1", "m2"), ("k2", "m1"), ("k2", "m2"), ("k3", "m1"), ("k3", "m2")}
    assert set(picked) <= valid
    assert set(picked) == valid


def test_page_range_selection():
    import io as _io

    from PIL import Image
    from src.extraction.vision_ocr import extract_via_vision
    from src.ai.key_pool import APIKeyPool

    pages_imgs = [Image.new("RGB", (400, 300), "white") for _ in range(6)]
    buf = _io.BytesIO()
    pages_imgs[0].save(buf, format="PDF", save_all=True, append_images=pages_imgs[1:])
    pdf_bytes = buf.getvalue()

    seen_pages: list = []

    def fake_caller(key, model, prompt, images):
        import re as _re
        m = _re.search(r"pages (\d+) to (\d+)", prompt)
        a, b = int(m.group(1)), int(m.group(2))
        seen_pages.extend(range(a, b + 1))
        pages = [{"page": p, "years": [2023, 2024],
                  "rows": [["المبيعات", 10 * p, 20 * p]]} for p in range(a, b + 1)]
        return json.dumps({"pages": pages}, ensure_ascii=False)

    pool = APIKeyPool(["k1"], ["m1"])
    extract_via_vision(pdf_bytes, [], pool=pool, workers=3, caller=fake_caller, page_range=(2, 4))
    assert seen_pages == [2, 3, 4]  # only the selected pages were ever read


def test_gemini_missing_key_graceful():
    from src.ai.gemini_agent import analyze_financials
    from src.ai.key_pool import APIKeyPool

    analysis = analyze_financials(
        {"calculated_metrics": [], "missing_data": [], "extraction_notes": [],
         "metrics": [], "analysis_period": {"previous_year": 2025, "current_year": 2026}},
        pool=APIKeyPool([], ["m1"]),
    )
    assert analysis.ok is False
    assert "No Gemini API keys" in analysis.error


def test_key_pool_rotation_and_depletion():
    from src.ai.key_pool import APIKeyPool

    pool = APIKeyPool(["k1", "k2"], ["m1", "m2"])  # depletion persists in this pool
    # picks always come from the cartesian product and rotate
    picks = set()
    for _ in range(8):
        picked = pool.pick()
        assert picked is not None
        picks.add((picked[0].key, picked[1]))
    assert picks == {("k1", "m1"), ("k1", "m2"), ("k2", "m1"), ("k2", "m2")}

    # quota exhausted on one pair -> that pair is skipped
    pool.mark_quota_exhausted("k1", "m1")
    for _ in range(8):
        state, model = pool.pick()
        assert not (state.key == "k1" and model == "m1")

    # model unavailable (404) for a key -> other model used for that key
    pool.mark_model_unavailable("k2", "m1", "not found")
    for _ in range(8):
        state, model = pool.pick()
        assert not (state.key == "k2" and model == "m1")

    # dead key (401) -> excluded entirely
    pool.mark_dead("k1", "invalid")
    for _ in range(6):
        state, _model = pool.pick()
        assert state.key == "k2"

    # depletion auto-expires (reset_seconds=0) -> usable again
    pool2 = APIKeyPool(["k1"], ["m1"], depletion_reset_seconds=0)
    pool2.mark_quota_exhausted("k1", "m1")
    assert pool2.pick() is not None  # expired immediately

    # everything exhausted -> None
    pool3 = APIKeyPool(["k1"], ["m1"], depletion_reset_seconds=999999)
    pool3.mark_quota_exhausted("k1", "m1")
    assert pool3.pick() is None


def test_analyze_rotates_on_quota_exhaustion():
    import json as _json

    from src.ai.gemini_agent import analyze_financials, parse_response
    from src.ai.key_pool import APIKeyPool

    good_json = _json.dumps(
        {
            "ratio_comments": [{"metric": "Revenue", "comment": "ارتفع."}],
            "recommendations": [
                {"action": "مراجعة التكاليف.", "evidence": "Net Margin: من 12.5% إلى 13.8%."},
            ],
        },
        ensure_ascii=False,
    )
    calls: list[tuple[str, str]] = []

    def flaky_caller(key, model, prompt, config):
        calls.append((key, model))
        # exhaust quota on the first two pairs, succeed on the third
        if len(calls) <= 2:
            raise RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded")
        return good_json

    pool = APIKeyPool(["k1", "k2"], ["m1", "m2"])
    payload = {"company": "X", "metrics": [], "missing_data": [], "extraction_notes": [],
               "analysis_period": {"previous_year": 2025, "current_year": 2026}}
    analysis = analyze_financials(payload, pool=pool, caller=flaky_caller)
    assert analysis.ok is True
    assert analysis.ratio_comments == [("Revenue", "ارتفع.")]
    assert len(calls) == 3
    # the exhausted pairs are marked in the pool
    status = pool.status()
    assert status["depleted_pairs"] == 2
    assert status["total_ok_calls"] == 1

    # auth failure retires the key permanently
    def auth_failer(key, model, prompt, config):
        raise RuntimeError("API key not valid. Please pass a valid API key. (401)")

    pool2 = APIKeyPool(["bad1", "bad2"], ["m1"])
    result = analyze_financials(payload, pool=pool2, caller=auth_failer)
    assert result.ok is False
    assert pool2.status()["active_keys"] == 0


def test_error_classification():
    from src.ai.gemini_agent import classify_gemini_error

    assert classify_gemini_error(RuntimeError("429 RESOURCE_EXHAUSTED")) == "quota"
    assert classify_gemini_error(RuntimeError("quota exceeded for the model")) == "quota"
    assert classify_gemini_error(RuntimeError("API key not valid (401)")) == "auth"
    assert classify_gemini_error(RuntimeError("403 PERMISSION_DENIED")) == "auth"
    assert classify_gemini_error(RuntimeError("404 model not found")) == "model"
    assert classify_gemini_error(RuntimeError("connection reset")) == "other"


def test_cash_flow_recovery_respects_page_range():
    """Regression (fixed 2026-10-24): with a user page range, cash-flow
    recovery used to crash list.index(x) on adjacent pages that fall OUTSIDE
    the selected range — losing the cash-flow statement entirely."""
    import io as _io

    from PIL import Image
    from src.extraction.vision_ocr import extract_via_vision
    from src.ai.key_pool import APIKeyPool

    pages_imgs = [Image.new("RGB", (400, 300), "white") for _ in range(8)]
    buf = _io.BytesIO()
    pages_imgs[0].save(buf, format="PDF", save_all=True, append_images=pages_imgs[1:])
    pdf_bytes = buf.getvalue()

    def fake_caller(key, model, prompt, images):
        import re as _re
        m = _re.search(r"pages (\d+) to (\d+)", prompt)
        if m:  # general page read: page 5 (doc numbering) = balance sheet
            a, b = int(m.group(1)), int(m.group(2))
            pages = []
            for p in range(a, b + 1):
                if p == 5:
                    pages.append({"page": p, "years": [2021, 2022],
                                  "rows": [["اجمالي الاصول", 100, 200],
                                           ["اجمالي حقوق الملكيه", 60, 120]]})
                else:
                    pages.append({"page": p, "years": [2021, 2022], "rows": []})
            return json.dumps({"pages": pages}, ensure_ascii=False)
        if "التدفقات النقدية" in prompt:  # focused cash-flow recovery prompt
            return json.dumps({"pages": [{"page": 0, "years": [2021, 2022],
                "rows": [["صافي التدفقات النقديه من الانشطه التشغيليه", 10, 20]]}]},
                ensure_ascii=False)
        # focused verify prompt (totals): agree with the general read
        return json.dumps({"years": [2021, 2022], "totals": {
            "total_assets": [100, 200], "equity": [60, 120]}}, ensure_ascii=False)

    pool = APIKeyPool(["k1"], ["m1"])
    data = extract_via_vision(pdf_bytes, [], pool=pool, workers=2,
                              caller=fake_caller, page_range=(4, 8))
    # the crash used to happen HERE (before the fix); the cash-flow row must
    # now actually be recovered from the in-range pages
    assert data.get("operating_cash_flow", 2022) == 20.0
    assert data.get("total_assets", 2022) == 200.0


def test_majority_vote_cross_statement():
    """NI printed on 3 statements: two agreeing captures outvote a misread."""
    from src.analysis.calculator import compute_year_metrics
    from src.extraction.normalizer import merge_parsed, reconcile

    parts = [
        {2022: {"net_income": 1056737086.0}},  # income statement
        {2022: {"net_income": 1056737086.0}},  # equity statement (agrees)
        {2022: {"net_income": 1050737086.0}},  # cash-flow page misread
    ]
    data = merge_parsed(parts, [])
    assert data.get("net_income", 2022) == 1056737086.0  # first capture
    reconcile(data)
    assert data.get("net_income", 2022) == 1056737086.0  # majority kept
    assert any("majority vote" in n for n in data.notes) is False  # no change needed

    parts_bad_first = [
        {2022: {"net_income": 1050737086.0}},  # misread came FIRST
        {2022: {"net_income": 1056737086.0}},
        {2022: {"net_income": 1056737086.0}},
    ]
    data2 = merge_parsed(parts_bad_first, [])
    assert data2.get("net_income", 2022) == 1050737086.0
    reconcile(data2)
    assert data2.get("net_income", 2022) == 1056737086.0  # outvoted
    assert any("majority vote" in n for n in data2.notes)


def test_majority_vote_no_agreement_keeps_first():
    from src.extraction.normalizer import merge_parsed, reconcile

    parts = [{2022: {"total_assets": 100.0}}, {2022: {"total_assets": 200.0}}]
    data = merge_parsed(parts, [])
    reconcile(data)
    assert data.get("total_assets", 2022) == 100.0  # tie -> first capture


def test_retained_earnings_alias():
    from src.extraction.normalizer import match_field

    assert match_field("أرباح مرحلة") == "retained_earnings"
    assert match_field("الارباح المحتجزة") == "retained_earnings"
    assert match_field("retained earnings") == "retained_earnings"


def test_dupont_analysis():
    from src.analysis.advanced import dupont_analysis
    from src.analysis.calculator import YearMetrics

    curr = YearMetrics(
        year=2022, revenue=1000.0, net_income=100.0,
        total_assets=2000.0, equity=1000.0,
    )
    prev = YearMetrics(
        year=2021, revenue=900.0, net_income=90.0,
        total_assets=2000.0, equity=1000.0,
    )
    dp = dupont_analysis(curr, prev)
    assert dp.missing == []
    assert abs(dp.net_margin_pct - 10.0) < 1e-9      # 100/1000
    assert abs(dp.asset_turnover - 0.5) < 1e-9       # 1000/2000 (avg)
    assert abs(dp.equity_multiplier - 2.0) < 1e-9    # 2000/1000 (avg)
    assert abs(dp.implied_roe_pct - 10.0) < 1e-9     # 10% × 0.5 × 2
    assert dp.reconciles is True                     # direct = 100/1000 avg equity


def test_altman_z_score():
    from src.analysis.advanced import altman_z
    from src.analysis.calculator import YearMetrics

    m = YearMetrics(
        year=2022, total_assets=1000.0, current_assets=800.0,
        current_liabilities=400.0, retained_earnings=300.0,
        operating_income=100.0, equity=600.0, total_liabilities=400.0,
    )
    az = altman_z(m)
    assert az.missing == []
    # 6.56*0.4 + 3.26*0.3 + 6.72*0.1 + 1.05*1.5 = 2.624+0.978+0.672+1.575
    assert abs(az.score - 5.849) < 1e-9
    assert az.zone == "safe"

    m2 = YearMetrics(year=2022, total_assets=1000.0)  # everything else missing
    az2 = altman_z(m2)
    assert az2.score is None and az2.missing  # honest N/A, never invented


def test_whatif_scenarios():
    from src.analysis.calculator import YearMetrics
    from src.analysis.whatif import whatif_analysis

    m = YearMetrics(
        year=2022, revenue=1000.0, cost_of_revenue=400.0, gross_profit=600.0,
        operating_expenses=300.0, operating_income=300.0,
        pretax_income=280.0, income_tax_expense=56.0, net_income=224.0,
        equity=1000.0, total_assets=2000.0,
    )
    scs = whatif_analysis(m)
    by_name = {s.name: s for s in scs}
    base = by_name["خط الأساس"]
    assert abs(base.net_income - 224.0) < 0.5 and abs(base.net_margin_pct - 22.4) < 0.1
    down = by_name["إيرادات −20%"]
    assert abs(down.revenue - 800.0) < 0.5
    # costs FIXED: GP=800-400=400, OI=100, +gap(-20) → pretax 80, tax 20% → 64
    assert abs(down.net_income - 64.0) < 1.0
    assert down.net_margin_pct < base.net_margin_pct  # operating leverage bites
    up = by_name["إيرادات +10%"]
    assert up.net_income > base.net_income
    cogs = by_name["تكلفة الإيرادات +10%"]
    assert cogs.net_income < base.net_income


def test_benchmarks_loader_and_band():
    from src.analysis.benchmarks import band_for, load_benchmarks

    bm = load_benchmarks()  # sector_benchmarks.csv exists in project root
    assert bm.source in ("general", "sector")
    assert "current_ratio" in bm.rows
    assert band_for(2.1, bm.rows["current_ratio"], True) == "جيد"
    assert band_for(1.6, bm.rows["current_ratio"], True) == "مقبول"
    assert band_for(1.2, bm.rows["current_ratio"], True) == "ضعيف"
    # lower-is-better metric (debt_to_equity: good <= 0.5)
    assert band_for(0.4, bm.rows["debt_to_equity"], False) == "جيد"
    assert band_for(3.0, bm.rows["debt_to_equity"], False) == "ضعيف"
    assert band_for(None, bm.rows["current_ratio"], True) == ""


def test_cf_verify_prompt_and_parser():
    from src.extraction.vision_ocr import _parse_verify_cf_json

    txt = '{"years": [2021, 2022], "totals": {"operating_cash_flow": [484942852, 1214507829], "financing_cash_flow": [-345940155, -727063341]}}'
    out = _parse_verify_cf_json(txt)
    assert out["operating_cash_flow"] == {2021: 484942852.0, 2022: 1214507829.0}
    # SIGNS preserved — a financing outflow must stay negative
    assert out["financing_cash_flow"][2021] < 0


def test_company_hint_detected_from_document():
    csv_text = (
        "شركة النيل للصناعات الغذائية\n"
        "البيان,2025,2026\n"
        "الإيرادات,1000000,1200000\n"
        "صافي الربح,80000,100000\n"
    )
    data = load_financial_data("nile.csv", csv_text.encode("utf-8"))
    assert data.company_hint == "شركة النيل للصناعات الغذائية"


def test_company_hint_overrides_filename_in_pipeline():
    csv_text = (
        "شركة النيل للصناعات الغذائية\n"
        "البيان,2025,2026\n"
        "الإيرادات,1000000,1200000\n"
        "صافي الربح,80000,100000\n"
    )
    results = run_pipeline("تقرير_مؤقت.csv", csv_text.encode("utf-8"), "تقرير_مؤقت")
    assert results["company"] == "شركة النيل للصناعات الغذائية"


def test_vision_parse_keeps_company():
    from src.extraction.vision_ocr import _parse_vision_json

    txt = json.dumps(
        {"pages": [
            {"page": 1, "currency": "جنيه", "company": "شركة عز لصناعة الحديد والصلب",
             "years": [2021, 2022], "rows": [["الإيرادات", 100, 200]]},
            {"page": 2, "currency": "", "company": "",
             "years": [2021, 2022], "rows": [["الإيرادات", 100, 200]]},
        ]},
        ensure_ascii=False,
    )
    pages = _parse_vision_json(txt)
    assert pages[0]["company"] == "شركة عز لصناعة الحديد والصلب"
    assert pages[1]["company"] == ""


def test_portfolio_save_load_overwrite_and_clear(tmp_path, monkeypatch):
    # v6: عزل مكتبة المحفظة — كانت على المجلد الحقيقي companies_library
    # فتصادم مع تحليلات الخادم الحي (المستخدم يحلل بالتوازي) وتكسر العدّاد
    from src.analysis import portfolio as pf

    monkeypatch.setattr(pf, "LIBRARY_DIR", tmp_path)
    from src.analysis.portfolio import (
        clear_library,
        load_records,
        record_from_results,
        save_record,
    )

    try:
        raw = (PROJECT_ROOT / "sample_data" / "sample_financials.csv").read_bytes()
        results = run_pipeline("sample_financials.csv", raw, "Sample Co")
        assert results["company"] == "Sample Co"  # no شركة cell in the sample

        rec = record_from_results(results)
        assert rec.company == "Sample Co"
        assert rec.revenue is not None and rec.health_total is not None
        assert rec.prev_year == results["prev_year"] and rec.curr_year == results["curr_year"]

        save_record(rec)
        save_record(rec)  # same company+year → overwrite, never duplicate
        recs = load_records()
        assert len(recs) == 1
        assert recs[0].company == "Sample Co"
        assert recs[0].net_income == rec.net_income
    finally:
        assert clear_library() >= 1
        assert load_records() == []


def test_benchmarks_sector_presets():
    from src.analysis.benchmarks import available_sectors, general_benchmarks, load_benchmarks

    sectors = available_sectors()
    assert "الحديد والصلب" in sectors
    bm = load_benchmarks("الحديد والصلب")
    assert bm.source == "sector" and bm.sector_name == "الحديد والصلب"
    assert bm.rows["current_ratio"] == (0.8, 1.2, 1.7)

    custom = load_benchmarks(None)  # root sector_benchmarks.csv ships with the repo
    assert custom.source == "sector" and custom.sector_name == "مخصص"

    gen = general_benchmarks()  # the explicit «عام» choice
    assert gen.source == "general" and "current_ratio" in gen.rows


def test_result_cache_roundtrip_and_pipeline_hit(tmp_path, monkeypatch):
    # v6: عزل الكاش — كانت هذه الاختبارات تمسح كاش التشغيل الحقيقي
    # (مسحت كاش رحلة واجهة حية أثناء الحزمة)؛ CACHE_DIR يوجه لـtmp
    from src.extraction.result_cache import clear_all_caches
    from src.extraction import result_cache as rc

    monkeypatch.setattr(rc, "CACHE_DIR", tmp_path)
    clear_all_caches()
    try:
        raw = (PROJECT_ROOT / "sample_data" / "sample_financials.csv").read_bytes()
        first = run_pipeline("sample_financials.csv", raw, "Sample Co")
        second = run_pipeline("sample_financials.csv", raw, "Sample Co")
        assert any("الكاش" in n for n in second["notes"]), (
            "second run must load from the local cache"
        )
        assert second["curr_metrics"].revenue == first["curr_metrics"].revenue
        assert second["curr_metrics"].net_income == first["curr_metrics"].net_income
        assert second["company"] == first["company"]
    finally:
        clear_all_caches()


def test_majority_of_three():
    from src.extraction.vision_ocr import _majority_of_three

    assert _majority_of_three(100.0, 100.000001, 55.0) == 100.0  # 2 agree
    assert _majority_of_three(100.0, 55.0, 55.0) == 55.0
    assert _majority_of_three(100.0, 200.0, 300.0) is None       # all differ


def _tiny_png() -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (120, 90), "white").save(buf, format="PNG")
    return buf.getvalue()


def _verify_json(revenue_2021: float) -> str:
    return json.dumps({
        "years": [2021, 2022],
        "totals": {"revenue": [revenue_2021, 200.0]},
    })


def test_verify_third_opinion_resolves_dispute():
    """Sweep capture vs focused verify vs third read — 2-of-3 must decide."""
    from src.extraction.normalizer import FinancialData
    from src.extraction.vision_ocr import _verify_core_fields

    capture, truth = 13169656088.0, 13196156088.0  # the live 2021 transposition
    notes: list[str] = []

    # Case A: verify + third agree on the truth → capture replaced.
    data = FinancialData(values={"revenue": {2021: capture}})
    parts = [{2021: {"revenue": capture}}]
    calls = {"n": 0}

    def caller(k, m, prompt, imgs):  # 1st call = verify, 2nd = third opinion
        calls["n"] += 1
        return _verify_json(truth if calls["n"] == 1 else truth)

    _verify_core_fields(
        data, parts, {"revenue": [3]}, [_tiny_png()], [3], None,
        caller=caller, notes=notes, local_reads=None, deadline=None,
    )
    assert parts[0][2021]["revenue"] == truth
    assert any("2-of-3" in n for n in notes)

    # Case B: third read confirms the CAPTURE → focused read is outvoted.
    notes2: list[str] = []
    data = FinancialData(values={"revenue": {2021: capture}})
    parts = [{2021: {"revenue": capture}}]
    calls["n"] = 0

    def caller_b(k, m, prompt, imgs):
        calls["n"] += 1
        return _verify_json(truth if calls["n"] == 1 else capture)

    _verify_core_fields(
        data, parts, {"revenue": [3]}, [_tiny_png()], [3], None,
        caller=caller_b, notes=notes2, local_reads=None, deadline=None,
    )
    assert parts[0][2021]["revenue"] == capture  # kept
    assert any("kept the sweep capture" in n for n in notes2)

    # Case C: all three disagree → keep capture, flag for manual review.
    notes3: list[str] = []
    data = FinancialData(values={"revenue": {2021: capture}})
    parts = [{2021: {"revenue": capture}}]
    calls["n"] = 0

    def caller_c(k, m, prompt, imgs):
        calls["n"] += 1
        return _verify_json(truth if calls["n"] == 1 else 999.0)

    _verify_core_fields(
        data, parts, {"revenue": [3]}, [_tiny_png()], [3], None,
        caller=caller_c, notes=notes3, local_reads=None, deadline=None,
    )
    assert parts[0][2021]["revenue"] == capture
    assert any("all three reads disagree" in n for n in notes3)


def test_run_batch_jobs_mixed(tmp_path, monkeypatch):
    from src.extraction.result_cache import clear_all_caches
    from src.extraction import result_cache as rc

    monkeypatch.setattr(rc, "CACHE_DIR", tmp_path)
    clear_all_caches()
    try:
        import app as app_mod
        from src.ai.gemini_agent import AIAnalysis

        run_batch_jobs = app_mod.run_batch_jobs
        # never let a test spend real API quota — deterministic fallback only
        orig = app_mod.analyze_financials
        app_mod.analyze_financials = lambda payload, **kw: AIAnalysis(ok=False, error="test: no AI")
        try:
            good = (PROJECT_ROOT / "sample_data" / "sample_financials.csv").read_bytes()
            oks, failed = run_batch_jobs(
                [("good.csv", good), ("empty.csv", b"")],
                page_range=None, currency="$",
            )
            assert [name for name, _r, _a in oks] == ["good.csv"]
            assert oks[0][1]["company"] == "good"  # derived from the job name
            assert oks[0][2].ratio_comments, "fallback narrative must fill comments"
            assert [name for name, _e in failed] == ["empty.csv"]
            assert "empty" in failed[0][1].lower()

            # same good file again → served from the in-process memo, still works
            oks2, failed2 = run_batch_jobs([("good.csv", good)], page_range=None, currency="$")
            assert not failed2 and len(oks2) == 1
        finally:
            app_mod.analyze_financials = orig
    finally:
        clear_all_caches()


def test_study_report_builds():
    from src.analysis.portfolio import record_from_results
    from src.dashboard.study_report import build_study_report

    raw = (PROJECT_ROOT / "sample_data" / "sample_financials.csv").read_bytes()
    results = run_pipeline("sample_financials.csv", raw, "Sample Co")
    rec = record_from_results(results)
    html = build_study_report([rec])
    assert "الدراسة التطبيقية" in html and "<table" in html
    assert "Sample Co" in html and rec.altman_zone in html
    assert len(html) > 1500


def test_read_pages_parallel_shapes():
    from src.extraction.local_ocr import indra_available, read_pages

    if not indra_available():
        return  # optional layer — nothing to test without it
    png = _tiny_png()
    reads = read_pages({5: png, 6: png, 7: png})
    assert reads is not None and sorted(reads.keys()) == [5, 6, 7]
    for lr in reads.values():
        assert lr.has_table is False  # blank white pages carry no tables


def _ym(**kw):
    """YearMetrics fixture builder (defaults: all None)."""
    from src.analysis.calculator import YearMetrics

    return YearMetrics(year=kw.pop("year", 2024), **kw)


def test_red_flag_rules():
    from src.analysis.redflags import red_flag_analysis

    # Company A: paper profits + receivables outrunning revenue + squeezed
    prev = _ym(year=2023, revenue=1000, accounts_receivable=100, working_capital=50,
               operating_income=200, interest_expense=40)
    curr = _ym(year=2024, revenue=1100, net_income=300, operating_cash_flow=20,
               accounts_receivable=400, inventory=None, working_capital=-20,
               operating_income=100, interest_expense=150)
    flags = red_flag_analysis(prev, curr)
    names = {f.name for f in flags}
    # NI=300 vs CFO=20 → coverage 6.7% < 20% → wide profit/cash gap (high)
    assert any(f.name == "فجوة ربح/نقد واسعة" for f in flags)
    assert any(f.severity == "high" for f in flags)
    assert "ذمم مدينة تنفصل عن الإيرادات" in names   # +300% vs +10%
    assert "رأس المال العامل انقلب سالبًا" in names
    assert "التمويل يلتهم التشغيل" in names           # coverage 0.67x < 1

    # Company B: clean, well-covered, cash-backed
    prev_b = _ym(year=2023, revenue=1000, accounts_receivable=100)
    curr_b = _ym(year=2024, revenue=1100, net_income=100, operating_cash_flow=140,
                 accounts_receivable=110, working_capital=80,
                 operating_income=200, interest_expense=30)
    assert red_flag_analysis(prev_b, curr_b) == []


def test_beneish_m_score():
    from src.analysis.redflags import beneish_m_score

    prev = _ym(year=2023, revenue=1000, gross_profit=300, accounts_receivable=100,
               fixed_assets=500, total_assets=1000, depreciation_amortization=50,
               selling_expenses=100, total_liabilities=400)
    curr = _ym(year=2024, revenue=1100, gross_profit=220, accounts_receivable=220,
               fixed_assets=500, total_assets=1000, depreciation_amortization=40,
               selling_expenses=110, total_liabilities=440,
               net_income=100, operating_cash_flow=20)
    bn = beneish_m_score(prev, curr)
    assert bn.m_score is not None
    # hand-computed: DSRI 2.0, GMI 1.5, AQI 1.0, SGI 1.1, DEPI 1.2267,
    # SGAI 1.0, LVGI 1.1000 (0.44 / 0.40), TATA 0.08 → M ≈ −0.839 → above the −1.78 line
    assert abs(bn.components["LVGI"] - 1.1) < 1e-4
    assert abs(bn.m_score - (-0.8391)) < 0.01
    assert bn.zone == "grey_above"
    assert set(bn.components) == {"DSRI", "GMI", "AQI", "SGI", "DEPI", "SGAI", "LVGI", "TATA"}

    # missing CFO → TATA unavailable → honest refusal (no partial M guesses)
    curr2 = _ym(year=2024, revenue=1100, gross_profit=220, accounts_receivable=220,
                fixed_assets=500, total_assets=1000, depreciation_amortization=40,
                selling_expenses=110, total_liabilities=440, net_income=100)
    bn2 = beneish_m_score(prev, curr2)
    assert bn2.m_score is None and "TATA" in bn2.missing


def test_confidence_bump_via_majority_vote():
    from src.extraction.normalizer import FinancialData, reconcile

    data = FinancialData()
    # first capture was the minority value; two later captures agree on 1000.
    # (Values within ±1 absolute count as rounding noise, not a dispute.)
    data.values["net_income"] = {2022: 850.0}
    data.candidates["net_income"] = {2022: [(1000.0, 0), (1000.0, 1), (850.0, 2)]}
    reconcile(data)
    assert data.get("net_income", 2022) == 1000.0
    assert data.confidence["net_income"][2022] == 2  # two agreeing captures


def test_peer_comparison():
    from src.analysis.peers import peer_comparison
    from src.analysis.portfolio import CompanyRecord

    def rec(company, margin):
        return CompanyRecord(company=company, file_name=f"{company}.pdf",
                             prev_year=2025, curr_year=2026,
                             net_margin_pct=margin)

    peers = [rec("أ", 4.0), rec("ب", 8.0), rec("ج", 16.0), rec("د", 20.0)]
    me = _ym(year=2026, net_margin=10.0)
    rows = peer_comparison(me, "الهدف", 2026, records=peers + [rec("الهدف", 10.0)])
    by_key = {r.metric: r for r in rows}
    p = by_key["net_margin"]
    assert p.n_peers == 4                      # self excluded
    assert abs(p.median - 12.0) < 1e-9 and abs(p.q25 - 6.0) < 1e-9 and abs(p.q75 - 18.0) < 1e-9
    assert p.standing == "قرب وسيط الأقران"

    # too few peers → honest empty (no fake benchmark)
    assert peer_comparison(me, "الهدف", 2026, records=[rec("الهدف", 10.0), rec("أ", 4.0)]) == []


def test_research_note_builds():
    from src.dashboard.study_report import build_research_note

    note = {
        "company": "شركة اختبار", "prev_year": 2023, "curr_year": 2024,
        "currency": "ج.م", "rating": "مستقر", "health_total": 72.5,
        "health_label": "مستقر", "altman_score": 2.9, "altman_zone": "منطقة أمان",
        "summary_lines": ["الإيرادات نمت 10.0%."],
        "flags": [{"name": "فجوة ربح/نقد", "severity": "high", "detail": "التدفق 20 مقابل ربح 300"}],
        "beneish": {"m_score": -0.78, "verdict": "نمط يستحق التدقيق",
                    "components": {"DSRI": 2.0, "TATA": 0.08}, "missing": [],
                    "zone": "grey_above"},
        "confidence": [{"label": "الإيرادات", "year": 2024, "value": "1.1K", "witnesses": 3}],
        "generated": "2026-10-30", "footer": "إخلاء مسؤولية",
    }
    html = build_research_note(note)
    assert "شركة اختبار" in html and "مستقر" in html
    assert "فجوة ربح/نقد" in html and "Beneish" in html
    assert "●●●" in html and len(html) > 2000


def test_fast_mode_skips_verification_layers():
    """Fast mode = sweep + recovery only: fewer calls, no verify prompts."""
    import io as _io
    import re as _re

    from PIL import Image
    from src.ai.key_pool import APIKeyPool
    from src.extraction.vision_ocr import extract_via_vision

    pages_imgs = [Image.new("RGB", (400, 300), "white") for _ in range(4)]
    buf = _io.BytesIO()
    pages_imgs[0].save(buf, format="PDF", save_all=True, append_images=pages_imgs[1:])
    pdf_bytes = buf.getvalue()

    def fake_caller(key, model, prompt, images):
        m = _re.search(r"pages (\d+) to (\d+)", prompt)
        if not m:
            return json.dumps({"pages": []})  # recovery prompt: nothing to add
        a, b = int(m.group(1)), int(m.group(2))
        pages = [{
            "page": p, "currency": "جنيه مصري", "years": [2023, 2024],
            "rows": [["المبيعات", 1000 * p, 1200 * p], ["صافي الربح", 100 * p, 150 * p]],
        } for p in range(a, b + 1)]
        return json.dumps({"pages": pages}, ensure_ascii=False)

    pool = APIKeyPool(["k1"], ["m1"])
    notes: list[str] = []
    data = extract_via_vision(pdf_bytes, notes, pool=pool, workers=2,
                              caller=fake_caller, fast_mode=True)
    assert data.get("revenue", 2024) is not None  # extraction still works
    assert any("Fast mode" in n for n in notes)

    # same file: full mode must make strictly MORE calls (verify layers ran)
    fast_calls = {"n": 0}

    def counting_fast(k, m, prompt, imgs):
        fast_calls["n"] += 1
        return fake_caller(k, m, prompt, imgs)

    extract_via_vision(pdf_bytes, [], pool=APIKeyPool(["k1"], ["m1"]),
                       workers=2, caller=counting_fast, fast_mode=True)

    full_calls = {"n": 0}

    def counting_full(k, m, prompt, imgs):
        full_calls["n"] += 1
        return fake_caller(k, m, prompt, imgs)

    extract_via_vision(pdf_bytes, [], pool=APIKeyPool(["k1"], ["m1"]),
                       workers=2, caller=counting_full, fast_mode=False)
    assert full_calls["n"] > fast_calls["n"]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main() -> int:
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_") and callable(fn)]
    failures = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception:
            failures += 1
            print(f"FAIL  {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - failures}/{len(tests)} tests passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
