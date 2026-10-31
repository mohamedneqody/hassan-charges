"""Excel export: builds a real workbook from synthetic results and verifies
it round-trips through openpyxl with every sheet and key cell intact."""
from __future__ import annotations

import io

import pytest
from openpyxl import load_workbook

from src.analysis.calculator import YearMetrics
from src.analysis.comparison import MetricRow, build_comparison
from src.dashboard.excel_report import build_excel_report, safe_file_name


def _metrics(year: int, revenue: float, net_income: float) -> YearMetrics:
    return YearMetrics(
        year=year,
        revenue=revenue,
        net_income=net_income,
        operating_income=revenue * 0.15,
        pretax_income=net_income * 1.3,
        total_assets=revenue * 0.6,
        current_assets=revenue * 0.3,
        current_liabilities=revenue * 0.15,
        total_liabilities=revenue * 0.32,
        equity=revenue * 0.28,
        retained_earnings=revenue * 0.2,
        working_capital=revenue * 0.15,
        net_margin=net_income / revenue * 100,
    )


def _results() -> dict:
    prev = _metrics(2023, 900_000.0, 90_000.0)
    curr = _metrics(2024, 1_000_000.0, 100_000.0)
    rows = build_comparison(prev, curr)
    return {
        "company": "شركة النيل للصناعات/تجريب 2024",
        "file_name": "statements.pdf",
        "prev_year": 2023,
        "curr_year": 2024,
        "prev_metrics": prev,
        "curr_metrics": curr,
        "rows": rows,
        "growth_rows": [],
        "notes": ["ملاحظة تجريبية 1", "ملاحظة تجريبية 2"],
        "currency_hint": "ج.م",
    }


def test_workbook_roundtrip_with_all_sheets():
    data = build_excel_report(_results())
    wb = load_workbook(io.BytesIO(data))
    assert wb.sheetnames == ["ملخص", "المؤشرات", "النماذج الأكاديمية", "الأعلام الحمراء", "ملاحظات الاستخراج"]


def test_summary_sheet_carries_identity_and_models():
    wb = load_workbook(io.BytesIO(build_excel_report(_results())))
    ws = wb["ملخص"]
    flat = {row[0].value: row[1].value for row in ws.iter_rows(min_row=2) if row[0].value}
    assert flat["الشركة"] == "شركة النيل للصناعات/تجريب 2024"
    assert flat["سنوات التحليل"] == "2023 ← 2024"
    assert isinstance(flat["الدرجة الصحية (0-100)"], (int, float))
    assert flat["Beneish M-Score"] in ("غير محسوب",) or isinstance(flat["Beneish M-Score"], (int, float))


def test_metrics_sheet_rows_have_status_colors_or_placeholder():
    wb = load_workbook(io.BytesIO(build_excel_report(_results())))
    ws = wb["المؤشرات"]
    n_rows = ws.max_row - 1
    assert n_rows >= 5  # the comparison produces many metric rows
    # at least one row must carry a real current value (not the "—" placeholder)
    values = [ws.cell(row=i, column=4).value for i in range(2, ws.max_row + 1)]
    assert any(isinstance(v, (int, float)) for v in values)


def test_academic_sheet_lists_all_four_models():
    wb = load_workbook(io.BytesIO(build_excel_report(_results())))
    ws = wb["النماذج الأكاديمية"]
    names = " | ".join(str(ws.cell(row=i, column=1).value) for i in range(2, ws.max_row + 1))
    assert "ألتمان" in names and "سبرينغيت" in names
    assert "زميجيفسكي" in names and "دوبونت" in names


def test_safe_file_name_strips_invalid_characters():
    assert "/" not in safe_file_name('شركة/العرب:*2024?')
    assert safe_file_name("///") == "report"


def test_bytes_are_nonempty_xlsx():
    data = build_excel_report(_results())
    assert data[:2] == b"PK"  # zip container magic
    assert len(data) > 4000
