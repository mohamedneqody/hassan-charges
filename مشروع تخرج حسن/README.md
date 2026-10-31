# 📊 Financial Statement Analysis Agent

MVP application that takes **one financial statement file** (PDF / CSV / XLSX / XLS),
extracts the financial data, computes **two-year ratios deterministically in Python**,
compares performance across the two fiscal years, then uses **Google Gemini**
(`gemini-3.8-flash`) to interpret the results and produce recommendations — all
presented in an **interactive Streamlit + Plotly dashboard**.

```
Upload File → File Validation → Data Extraction → Financial Data Structuring
→ Deterministic Financial Calculations → Two-Year Comparison
→ Gemini 3.8 Flash Analysis → Recommendations → Interactive Dashboard
```

> **Design rule:** Gemini never computes financial numbers. Python calculates every
> metric; the AI only interprets them. Missing data is shown as `N/A` with a reason —
> never invented.

---

## Features

- **Multi-format upload** — `.pdf` (tables via pdfplumber, text fallback), `.csv`,
  `.xlsx` / `.xls` (all sheets parsed and merged automatically).
- **Scanned-PDF vision extraction** — a PDF with no text layer is detected
  automatically, its pages are rendered and cleaned with OpenCV (deskew,
  CLAHE, denoise, border crop), then read page-by-page by Gemini vision
  (through the same key rotation). Extracted rows flow into the same
  matching + accounting-identity reconciliation pipeline, which corrects OCR
  misreads (assets must equal liabilities + equity). Processing stops early
  once the core statements are complete to save quota.
- **Smart normalization** — maps dozens of label variants (`Net Sales`, `Total
  Revenue`, `Sales`, …) to canonical fields like `revenue`; insensitive to case,
  spaces, underscores, punctuation, and common Arabic label variants
  (الإيرادات، صافي الربح، إجمالي الأصول…). Accounting negatives `(2,500)`,
  currency symbols, thousands separators and Arabic-Indic digits are handled.
- **Automatic year detection** — `FY2025`, `2026`, `Dec 31, 2025`, transposed
  layouts… If more than two years exist, the **latest two** are used.
- **Deterministic calculations** — growth, profitability, liquidity, leverage;
  ROA/ROE use average balances when possible (with a clear note when falling
  back to current-year balances).
- **Trend detection in Python** — `Improving / Declining / Stable` per metric,
  with `Positive / Negative / Neutral` status.
- **Gemini agent** — receives the computed metrics, trends and missing-data list,
  returns structured JSON: executive summary, strengths, weaknesses, risks,
  recommendations, key observations. Graceful degradation when no API key is set:
  the deterministic dashboard still works.
- **Interactive dashboard** — Overview KPI cards, Profitability / Liquidity &
  Leverage / Cash-flow charts, color-coded metrics table, AI analysis screen,
  JSON report download.

## Metrics computed

**53 metric rows + 7 growth rates** across 9 categories (all computed in Python,
all receiving a one-line AI comment):

| Category | Metrics |
|---|---|
| Growth & Income | Revenue, Gross/Operating/Net Income, Free Cash Flow (+ 7 growth rates: Revenue, Gross Profit, Operating Income, Net Profit, Assets, Equity, CFO) |
| Profitability | Gross / Operating / EBITDA / Pretax / Net Margin, ROA, ROE, ROIC, ROCE |
| Liquidity | Current, Quick, Cash Ratio, Operating Cash Flow Ratio |
| Leverage | Debt/Equity, Debt Ratio, Debt to Assets, Liabilities/Equity, Equity Ratio, Financial Leverage, Interest Coverage |
| Efficiency | Asset, Fixed Asset, Inventory, Receivables, Payables Turnover |
| Days | DIO, DSO, DPO, Cash Conversion Cycle |
| Working Capital | Working Capital, Operating Working Capital, WC Turnover |
| Cash Flow | CFO/ICF/FCF absolutes, CFO Margin, FCF Margin, CFO/Net Income, CFO/Debt, Capex Coverage, Cash ROA |
| Cost Structure | COGS%, Opex%, Selling%, R&D%, Interest%, D&A% of Revenue, Effective Tax Rate |

Ratios on average balances (ROA/ROE/ROIC/turnovers/days) use the two-year average
and fall back to the current-year balance with an explanatory note.

**Deliberately excluded:** CAGR (needs 3+ years — the app analyzes exactly two by
design) and DSCR (requires debt-service detail not present in standard statements).

## The Gemini endpoint layer (key & model rotation)

All AI calls go through a rotating pool (`src/ai/key_pool.py` + `analyze_financials`):

- **7+ API keys** from `GEMINI_API_KEYS` in `.env` (comma-separated). When a
  key's free quota is exhausted (**429**), the next key is used immediately.
- **Model rotation**: `GEMINI_MODELS=gemini-3.8-flash,gemini-3.7-flash` — quotas
  are per-model, so alternating both models doubles the free allowance per key.
  The fallback model also takes over when the first is under high demand (503).
- **Invalid keys (401/403)** are retired automatically; **unavailable models
  (404)** fall back to the other model; **transient errors (503)** trigger one
  extra full sweep after a 5-second pause.
- Depleted statuses auto-expire after 24h (or use "Reset key statuses" in the
  sidebar, which also shows a live status card per key).
- **Speed**: thinking is disabled (`thinking_budget=0` — verified supported),
  Gemini clients are cached per key, output is capped at 8192 tokens, the HTTP
  timeout fails fast at 45s, and results are cached per file so a rerun never
  spends quota twice.

## The AI ratio commentary

The **AI Analysis** tab contains exactly two things:

1. **One short comment per metric** (1–2 lines max): states whether the ratio
   rose, fell, or stayed stable, quotes the exact Python-computed values, and
   gives the financial meaning of the change in one sentence — with hedged
   language (`قد يشير إلى…`) whenever the cause is not visible in the data.
2. **التوصيات** — one section with 3–5 short recommendations based on the
   most important changes.

Guardrails:
- Gemini never computes numbers: Python sends each metric with pre-formatted
  values (`18.0%`, `1.65x`, `$1.18M`), the numeric direction (rose/fell/stable)
  and the assessment (improving/declining/stable).
- Comments come as a flat list — no sections per axis, no introduction, no
  formula explanations.
- Metrics with missing data are skipped, never commented on with invented values.
- Comment language follows `REPORT_LANGUAGE` in `.env` (`ar` = Arabic default,
  `en`); metric names stay in English either way.
- **Without an API key** the same output shape is produced deterministically
  by rule-based templates in Python (labeled as such in the UI).

## Project structure

```
├── app.py                        # Streamlit dashboard (UI only)
├── src/
│   ├── config.py                 # FIELD_ALIASES, model name, thresholds
│   ├── exceptions.py             # User-facing validation errors
│   ├── pipeline.py               # End-to-end orchestration (headless-testable)
│   ├── extraction/
│   │   ├── file_parsers.py       # CSV / Excel / PDF readers
│   │   └── normalizer.py         # Alias matching, number & year parsing, structuring
│   ├── analysis/
│   │   ├── calculator.py         # Deterministic ratios (never the AI's job)
│   │   ├── comparison.py         # Two-year table, trends, missing-data report
│   │   └── narrative.py          # Rule-based report fallback (en/ar)
│   ├── ai/
│   │   └── gemini_agent.py       # Gemini call + structured JSON parsing
│   └── dashboard/
│       └── charts.py             # Plotly figures & formatting helpers
├── tests/test_pipeline.py        # 17 tests: parsing, ratios, trends, report, e2e
├── sample_data/                  # sample_financials.csv / .xlsx (3 sheets)
└── make_samples.py               # Regenerates the sample files
```

## Quick start

### Windows — one double-click (easiest)

1. Install **Python 3.11+** once (from [python.org](https://www.python.org/downloads/)) and
   check **"Add python.exe to PATH"** during setup.
2. Double-click **`run.bat`**.

The first run creates the virtual environment and installs everything
(needs internet, takes a few minutes); after that it starts instantly and
opens the dashboard at `http://localhost:8501`. Keep the black window open
while using the app — closing it stops the app.

### Manual (any OS)

```bash
# 1. Create a virtual environment (Python 3.11+)
python -m venv .venv
.venv\Scripts\activate            # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure the Gemini API keys
copy .env.example .env            # then paste your keys inside .env
#    Get free keys: https://aistudio.google.com/apikey

# 4. Run
streamlit run app.py
```

Then either upload a file or click **“Try with the built-in sample file”**.

> The app runs **without** an API key — the AI Analysis tab shows the
> rule-based commentary instead and everything else stays fully functional.

## Input format expectations

There is no rigid template — the extractor scans every sheet/page for:

- a header (row or column) containing **at least two fiscal years**;
- line-item labels matching the alias table in `src/config.py`.

A typical CSV looks like:

```csv
Line Item,FY2025,FY2026
Revenue,"1,000,000","1,180,000"
Cost of Revenue,"420,000","520,000"
Net Income,"180,000","165,000"
Total Assets,"1,500,000","1,650,000"
Current Assets,"600,000","560,000"
Current Liabilities,"250,000","340,000"
Total Debt,"400,000","520,000"
Shareholders Equity,"800,000","800,000"
```

Validation messages: `Unsupported file format`, `The uploaded file is empty.`,
`Insufficient financial data for analysis.` — a parsing error in one table never
crashes the whole run.

## Testing

```bash
.venv\Scripts\python tests\test_pipeline.py   # or: pytest tests/
```

Covers alias matching (incl. Arabic), number/year parsing, ratio math, trend
classification, missing-data handling, CSV/XLSX end-to-end runs, and Gemini
graceful degradation.

## Limitations (by design — MVP)

- Two-year analysis only (latest two years are selected automatically).
- Scanned PDFs are read by AI vision — Arabic handwriting (not print) and
  very low-quality scans may still misread; the identity reconciliation and
  the missing-data report flag anything suspicious. Vision needs API keys
  (a scanned file cannot be analyzed offline) and takes minutes, not seconds.
- Cash flow statement is optional; charts hide what is absent.
- Scanned/image-only PDFs (no text layer) are not OCR-ed.
- Percentage rows in source files are ignored on purpose — ratios are recomputed
  from absolute values so the AI never sees second-hand numbers.
