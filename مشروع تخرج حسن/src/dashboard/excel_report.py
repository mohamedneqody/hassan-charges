"""Multi-sheet Excel export (التقرير الشامل) — openpyxl, no UI deps, testable.

Takes the pipeline results dict and produces a workbook:
  ملخص              — company, years, health score, models at a glance
  المؤشرات           — every metric row: previous/current/change/status
  النماذج الأكاديمية  — Altman/Springate/Zmijewski/DuPont + components
  الأعلام الحمراء     — deterministic flags + Beneish M
  ملاحظات الاستخراج   — extraction notes & missing-data report
Values come only from computed data — nothing is invented here either.
"""
from __future__ import annotations

import io
import re

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from src.analysis.academic_models import academic_models
from src.analysis.redflags import SEVERITY_ICON, beneish_m_score, red_flag_analysis
from src.analysis.score import compute_health_score

_HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
_POS_FILL = PatternFill("solid", fgColor="E2EFDA")
_NEG_FILL = PatternFill("solid", fgColor="FCE4E4")
_GREY_FILL = PatternFill("solid", fgColor="EDEDED")

_NUM_FMT = {"currency": "#,##0", "percent": "0.00", "ratio": "0.00"}


def safe_file_name(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "-", (name or "report").strip())[:60].strip()
    # must contain an actual letter/digit (Arabic range included) — else default
    return cleaned if re.search(r"[\w\u0600-\u06FF]", cleaned) else "report"


def _header(ws, headers: list[str]) -> None:
    ws.append(headers)
    for col, _ in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.freeze_panes = "A2"
    ws.sheet_view.rightToLeft = True
    for col, _ in enumerate(headers, start=1):
        ws.column_dimensions[get_column_letter(col)].width = 22


def build_excel_report(results: dict) -> bytes:
    """results = the pipeline's return dict. Returns .xlsx bytes."""
    wb = Workbook()
    curr = results["curr_metrics"]
    prev = results["prev_metrics"]

    # --- ملخص ---
    ws = wb.active
    ws.title = "ملخص"
    _header(ws, ["البند", "القيمة"])
    hs = compute_health_score(curr)
    ws.append(["الشركة", results.get("company", "—")])
    ws.append(["الملف", results.get("file_name", "—")])
    ws.append(["سنوات التحليل", f"{results.get('prev_year')} ← {results.get('curr_year')}"])
    ws.append(["الدرجة الصحية (0-100)", hs.total if hs.total is not None else "غير محسوبة"])
    ws.append(["تصنيف الدرجة", hs.label])
    flags = red_flag_analysis(prev, curr)
    ws.append(["عدد الأعلام الحمراء", len(flags)])
    bn = beneish_m_score(prev, curr)
    ws.append(["Beneish M-Score", bn.m_score if bn.m_score is not None else "غير محسوب"])
    for m in academic_models(curr):
        ws.append([m.name, m.value if m.value is not None else "غير محسوب"])

    # --- المؤشرات ---
    ws = wb.create_sheet("المؤشرات")
    _header(ws, ["المؤشر", "الوحدة", "السنة السابقة", "السنة الحالية", "التغير", "التغير %", "التقييم", "الاتجاه"])
    for row in list(results.get("growth_rows") or []) + list(results.get("rows") or []):
        label = row.label_ar or row.label
        unit = {"currency": "عملة", "percent": "%", "ratio": "x"}.get(row.kind, "")
        change_pct = f"{row.change_pct:+.2f}%" if row.change_pct is not None else "—"
        cells = [
            ws.cell(row=ws.max_row + 1, column=c, value=v)
            for c, v in enumerate(
                [label, unit,
                 row.previous if row.previous is not None else "—",
                 row.current if row.current is not None else "—",
                 row.change if row.change is not None else "—",
                 change_pct,
                 row.status or "—",
                 row.trend_symbol],
                start=1,
            )
        ]
        for cell in cells:
            if row.kind in _NUM_FMT and isinstance(cell.value, (int, float)):
                cell.number_format = _NUM_FMT[row.kind]
            if row.status == "Positive" and cell.column in (3, 4):
                cell.fill = _POS_FILL
            elif row.status == "Negative" and cell.column in (3, 4):
                cell.fill = _NEG_FILL

    # --- النماذج الأكاديمية ---
    ws = wb.create_sheet("النماذج الأكاديمية")
    _header(ws, ["النموذج", "القيمة", "الحكم", "المكوّنات", "بيانات ناقصة"])
    for m in academic_models(curr):
        ws.append([
            m.name,
            m.value if m.value is not None else "—",
            (m.icon + " " + m.verdict) if m.value is not None else "غير محسوب",
            " · ".join(f"{k}={v:g}" for k, v in m.components.items()) or "—",
            ", ".join(m.missing) or "—",
        ])

    # --- الأعلام الحمراء ---
    ws = wb.create_sheet("الأعلام الحمراء")
    _header(ws, ["النوع", "العلم", "الدليل الرقمي"])
    if flags:
        for fl in flags:
            ws.append(["فحص تحليلي", f"{SEVERITY_ICON[fl.severity]} {fl.name}", fl.detail])
    else:
        ws.append(["فحص تحليلي", "لا أعلام", "لا توجد أعلام حمراء على الفحوصات الحالية"])
    if bn.m_score is not None:
        ws.append(["نموذج", "Beneish M-Score", f"{bn.m_score:.2f} — {bn.verdict}"])
    else:
        ws.append(["نموذج", "Beneish M-Score", "غير محسوب — بيانات ناقصة: " + ", ".join(bn.missing)])

    # --- ملاحظات الاستخراج ---
    ws = wb.create_sheet("ملاحظات الاستخراج")
    _header(ws, ["#", "الملاحظة"])
    for i, note in enumerate(results.get("notes") or [], start=1):
        ws.append([i, str(note)])
    if not results.get("notes"):
        ws.append([1, "لا ملاحظات"])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
