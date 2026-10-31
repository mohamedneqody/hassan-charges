"""One-off generator for sample_data/ files. Run once, then ignore."""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

HERE = Path(__file__).resolve().parent
OUT = HERE / "sample_data"
OUT.mkdir(exist_ok=True)

INCOME = [
    ("Revenue", 1_000_000, 1_180_000),
    ("Cost of Revenue", 420_000, 520_000),
    ("Gross Profit", 580_000, 660_000),
    ("Selling Expenses", 140_000, 165_000),
    ("Research and Development", 60_000, 75_000),
    ("Operating Expenses", 300_000, 360_000),
    ("Operating Income", 280_000, 300_000),
    ("Interest Expense", 45_000, 60_000),
    ("Income Before Tax", 225_000, 205_000),
    ("Income Tax Expense", 45_000, 40_000),
    ("Net Income", 180_000, 165_000),
    ("Depreciation and Amortization", 90_000, 105_000),
]
BALANCE = [
    ("Total Assets", 1_500_000, 1_650_000),
    ("Cash and Cash Equivalents", 150_000, 120_000),
    ("Accounts Receivable", 180_000, 220_000),
    ("Current Assets", 600_000, 560_000),
    ("Inventory", 120_000, 150_000),
    ("Net Fixed Assets", 700_000, 850_000),
    ("Accounts Payable", 140_000, 160_000),
    ("Total Liabilities", 700_000, 850_000),
    ("Current Liabilities", 250_000, 340_000),
    ("Total Debt", 400_000, 520_000),
    ("Shareholders Equity", 800_000, 800_000),
]
CASHFLOW = [
    ("Operating Cash Flow", 220_000, 190_000),
    ("Capital Expenditure", -120_000, -160_000),
    ("Investing Cash Flow", -150_000, -210_000),
    ("Financing Cash Flow", -40_000, 60_000),
]


def csv_value(v: float) -> str:
    if v < 0:
        return f'"({-v:,.0f})"'  # accounting-style negative
    return f'"{v:,.0f}"'


lines = ["Line Item,FY2025,FY2026"]
for label, y25, y26 in INCOME + BALANCE + CASHFLOW:
    lines.append(f"{label},{csv_value(y25)},{csv_value(y26)}")
(OUT / "sample_financials.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")

wb = Workbook()
for sheet, rows in (("Income Statement", INCOME), ("Balance Sheet", BALANCE), ("Cash Flow", CASHFLOW)):
    ws = wb.create_sheet(sheet)
    ws.append([sheet, None, None])
    ws.append(["Line Item", "FY2025", "FY2026"])
    for label, a, b in rows:
        ws.append([label, a, b])
del wb["Sheet"]
wb.save(OUT / "sample_financials.xlsx")

print("Wrote:", *(p.name for p in OUT.iterdir()), sep="\n  ")
