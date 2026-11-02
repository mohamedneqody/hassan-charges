"""Central configuration: field aliases, model settings, thresholds."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")

# --- AI ---
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip() or "gemini-3.8-flash"

# Language of the AI ratio commentary: "ar" (Modern Standard Arabic, default)
# or "en". Metric names stay in English either way.
REPORT_LANGUAGE = (os.getenv("REPORT_LANGUAGE", "ar").strip().lower() or "ar")

# Local OCR pre-layer (Indra OCR). When the package is importable it runs a
# free local pass over scanned pages: table-page triage (statement pages are
# sent to Gemini first so early-stop fires sooner) and a second-opinion check
# on core totals (a matching local read skips paid verification calls).
# Set LOCAL_OCR_ENABLED=0 to disable. Missing package = silent no-op.
LOCAL_OCR_ENABLED = os.getenv("LOCAL_OCR_ENABLED", "1").strip() != "0"


def get_gemini_api_key() -> str:
    return (os.getenv("GEMINI_API_KEY") or "").strip()


# --- Input validation ---
SUPPORTED_EXTENSIONS = {".pdf", ".csv", ".xlsx", ".xls"}
MAX_UPLOAD_MB = 25

# --- Trend detection ---
# Relative change (%) below which a metric is considered "Stable".
STABLE_TREND_THRESHOLD = 1.0

DEFAULT_CURRENCY = "$"

# Canonical field -> accepted aliases. Matching is case-, space-, underscore-,
# and punctuation-insensitive (see normalizer.normalize_label), so aliases are
# written here in already-normalized form.
FIELD_ALIASES: dict[str, list[str]] = {
    "revenue": [
        "revenue", "revenues", "total revenue", "total revenues", "sales",
        "net sales", "total sales", "net revenue", "gross sales",
        "operating revenue", "total operating revenues",
        # Arabic
        "الايرادات", "ايرادات العمليات", "صافي المبيعات", "المبيعات",
    ],
    "cost_of_revenue": [
        "cost of revenue", "total cost of revenue", "cost of goods sold",
        "cogs", "cost of sales", "direct costs",
        # Arabic
        "تكلفة الايرادات", "تكلفة المبيعات", "تكلفة البضاعة المباعة",
    ],
    "gross_profit": [
        "gross profit", "gross income", "total gross profit",
        # Arabic
        "اجمالي الربح", "الربح الاجمالي",
    ],
    "operating_expenses": [
        "operating expenses", "total operating expenses", "opex",
        "selling general and administrative expenses", "sg and a expenses",
        "sg a expenses", "g a expenses",
        # Arabic
        "المصاريف التشغيلية", "مصاريف التشغيل",
    ],
    "operating_income": [
        "operating income", "operating profit", "ebit", "income from operations",
        "profit from operations", "total operating income",
        # Arabic
        "الربح التشغيلي", "الربح من العمليات",
        "ربح العمليات", "ربح التشغيل", "نتيجة العمليات",
    ],
    "net_income": [
        "net income", "net profit", "profit after tax", "net earnings",
        "earnings after tax", "profit for the year", "profit for the period",
        "net income after tax", "profit after taxation",
        "net income attributable to shareholders",
        # Arabic
        "صافي الربح", "صافي الربح بعد الضريبة", "الربح بعد الضريبة",
        "صافي الدخل",
        "صافي ارباح العام", "صافي ربح العام", "صافي ارباح السنه",
        "صافي ربح الفتره", "صافي ربح السنه", "الربح الصافي", "نتيجه السنه",
    ],
    "total_assets": [
        "total assets", "assets", "sum of total assets",
        # Arabic
        "اجمالي الاصول", "الاصول",
    ],
    "current_assets": [
        "current assets", "total current assets",
        # Arabic
        "الاصول المتداولة", "اجمالي الاصول المتداولة",
    ],
    "inventory": [
        "inventory", "inventories", "stock", "stock in trade",
        "total inventories", "merchandise inventory",
        # Arabic
        "المخزون", "المخزونات", "اجمالي المخزون",
    ],
    "total_liabilities": [
        "total liabilities", "liabilities", "sum of total liabilities",
        # Arabic
        "اجمالي الالتزامات", "الالتزامات", "الخصوم", "اجمالي الخصوم",
    ],
    "current_liabilities": [
        "current liabilities", "total current liabilities",
        # Arabic
        "الالتزامات المتداولة", "اجمالي الالتزامات المتداولة",
        "الخصوم المتداولة", "اجمالي الخصوم المتداولة",
    ],
    "total_debt": [
        "total debt", "debt", "total borrowings", "borrowings",
        "total loans", "loans", "interest bearing debt",
        # Arabic
        "اجمالي الدين", "الديون", "اجمالي القروض",
    ],
    "short_term_debt": [
        "short term debt", "short term borrowings", "short term loans",
        "bank facilities", "bank borrowings",
        # Arabic
        "قروض قصيره الاجل", "ديون قصيره الاجل",
        # البنود المطبوعة فعليًا في القوائم المصرية (وُجدت في وثيقة 2022):
        "بنوك تسهيلات إنتمانية", "بنوك تسهيلات ائتمانية", "تسهيلات بنكية",
        "تسهيلات بنكيه", "تسهيلات ائتمانية", "سحب على المكشوف",
    ],
    # الجزء المتداول من القروض طويلة الأجل — بند مستقل مطبوع في الميزانية
    # (لا يجوز دمجه مع القروض غير المتداولة ولا إغفاله من إجمالي الدين)
    "current_portion_lt_debt": [
        "current portion of long term debt", "current portion of long-term loans",
        # Arabic
        "أقساط قروض طويلة الأجل", "أقساط القروض طويلة الأجل",
        "أقساط قروض طويلة الأجل مستحقة السداد خلال عام",
        "اقساط قروض طويله الاجل",
    ],
    # التزامات التأجير التمويلي — متداولة وغير متداولة (بندان مستقلان مطبوعان)
    "current_lease_liabilities": [
        "current lease liabilities",
        # Arabic
        "التزامات تأجير تمويلي مستحقة السداد خلال عام",
        "التزامات التأجير التمويلي المستحقة السداد",
    ],
    "non_current_lease_liabilities": [
        "non current lease liabilities", "long term lease liabilities",
        # Arabic
        "التزامات تأجير تمويلي", "التزامات التأجير التمويلي",
    ],
    "long_term_debt": [
        "long term debt", "long term borrowings", "long term loans",
        # Arabic
        "قروض طويله الاجل", "ديون طويله الاجل",
    ],
    "equity": [
        "equity", "total equity", "shareholders equity", "stockholders equity",
        "total shareholders equity", "total stockholders equity",
        "owners equity", "total owners equity", "net assets",
        # Arabic
        "حقوق الملكية", "اجمالي حقوق الملكية",
    ],
    "retained_earnings": [
        "retained earnings", "accumulated profits", "retained deficit",
        "accumulated deficit", "retained profits",
        # Arabic
        "ارباح مرحله", "الارباح المرحله", "الارباح المحتجزه",
        "الارباح المبقاه", "ارباح مبقاة",
    ],
    "operating_cash_flow": [
        "operating cash flow", "cash from operations", "cash flow from operations",
        "net cash from operating activities",
        "net cash provided by operating activities",
        "net cash provided by operating", "net cash used in operating activities",
        # Arabic
        "التدفق النقدي التشغيلي", "صافي التدفق النقدي من الانشطه التشغيلية",
        "التدفقات النقديه من الانشطه التشغيليه",
        "التدفقات النقديه الصافيه من الانشطه التشغيليه",
        "صافي النقدية من الانشطه التشغيليه",
        "صافي التدفقات النقديه من الانشطه التشغيليه",
        "التدفق النقدي من الانشطه التشغيليه",
        "النقد المتولد من الانشطه التشغيليه",
        # "net cash GENERATED FROM / USED IN operating activities" — the
        # phrasing actually printed on the Ezz Steel 2022 cash-flow page
        "صافي النقديه الناتجه من انشطه التشغيل",
        "النقديه الناتجه من انشطه التشغيل",
        "النقديه المستخدمه في انشطه التشغيل",
    ],
    "investing_cash_flow": [
        "investing cash flow", "cash flow from investing",
        "net cash from investing activities",
        "net cash provided by investing activities",
        "net cash used in investing activities",
        # Arabic
        "التدفق النقدي الاستثماري", "صافي التدفق النقدي من الانشطه الاستثمارية",
        "التدفقات النقديه من الانشطه الاستثماريه",
        "التدفقات النقديه الصافيه من الانشطه الاستثماريه",
        "صافي التدفقات النقديه من الانشطه الاستثماريه",
        "التدفق النقدي من الانشطه الاستثماريه",
        "صافي النقديه الناتجه من انشطه الاستثمار",
        "النقديه الناتجه من انشطه الاستثمار",
        "النقديه المستخدمه في انشطه الاستثمار",
        "المستخدمه في انشطه الاستثمار",
    ],
    "financing_cash_flow": [
        "financing cash flow", "cash flow from financing",
        "net cash from financing activities",
        "net cash provided by financing activities",
        "net cash used in financing activities",
        # Arabic
        "التدفق النقدي التمويلي", "صافي التدفق النقدي من الانشطه التمويلية",
        "التدفقات النقديه من الانشطه التمويليه",
        "التدفقات النقديه الصافيه من الانشطه التمويليه",
        "صافي التدفقات النقديه من الانشطه التمويليه",
        "التدفق النقدي من الانشطه التمويليه",
        "صافي النقديه الناتجه من انشطه التمويل",
        "النقديه الناتجه من انشطه التمويل",
        "النقديه المستخدمه في انشطه التمويل",
        "المستخدمه في انشطه التمويل",
    ],
    # --- Extended fields (optional; ratios fall back to N/A when absent) ---
    "cash": [
        "cash and cash equivalents", "cash and equivalents", "cash and bank",
        "cash", "النقد وما يعادله", "النقد والنقديات",
        "نقديه", "النقديه", "النقد وما يعادلها",
    ],
    "capex": [
        "capital expenditure", "capital expenditures", "capex",
        "purchases of property and equipment",
        "purchase of property plant and equipment", "purchase of fixed assets",
        "additions to property plant and equipment",
        # Arabic
        "النفقات الراسمالية", "النفقات الرأسمالية", "مشتريات الأصول الثابتة",
        "مدفوعات لشراء أصول ثابتة", "مدفوعات لشراء أصول ثابتة ومشروعات تحت التنفيذ",
        "لشراء أصول ثابتة", "شراء أصول ثابتة",
    ],
    "interest_expense": [
        "interest expense", "interest expenses", "interest costs",
        "finance costs", "financing costs", "finance cost",
        # Arabic
        "مصروف الفوائد", "تكاليف التمويل", "مصروفات التمويل",
        "مصروفات فوائد", "مصروف فوائد",
        "صافي التكاليف التمويلية", "فوائد ومصروفات تمويلية",
    ],
    "pretax_income": [
        "income before tax", "income before income tax", "income before taxes",
        "profit before tax", "earnings before tax", "pre tax income",
        "pretax income", "profit before taxation",
        # Arabic
        "الربح قبل الضريبة", "الربح قبل خصم الضريبة",
        "صافى أرباح العام قبل ضريبة الدخل", "أرباح العام قبل ضريبة الدخل",
        "ربح العام قبل ضريبة الدخل", "الربح قبل ضريبة الدخل",
        "الربح قبل الضرائب", "الأرباح قبل الضرائب",
    ],
    "income_tax_expense": [
        "income tax expense", "income tax", "tax expense", "taxation",
        "provision for income taxes", "income taxes",
        # Arabic
        "ضريبة الدخل", "مصروف الضريبة", "الضرائب",
    ],
    "depreciation_amortization": [
        "depreciation and amortization", "depreciation amortization",
        "depreciation", "d a", "depreciation and amortisation",
        # Arabic
        "الاهلاك والاستنفاد", "الإهلاك والاستنفاد", "مصروف الاهلاك",
        "مصروفات اهلاك", "مصروف اهلاك", "مصروفات الاهلاك",
        "إهلاك أصول ثابتة", "إهلاك الأصول الثابتة", "اهلاك اصول ثابته",
    ],
    "fixed_assets": [
        "net fixed assets", "fixed assets", "property plant and equipment",
        "property plant and equipment net", "pp and e",
        # Arabic
        "الأصول الثابتة", "الاصول الثابتة", "اصول ثابتة",
    ],
    "accounts_receivable": [
        "accounts receivable", "trade receivables", "receivables",
        "accounts receivable net",
        # Arabic
        "الذمم المدينة", "المدينون", "اذمم مدينة", "العملاء",
    ],
    "accounts_payable": [
        "accounts payable", "trade payables", "payables",
        # Arabic
        "الذمم الدائنة", "الدائنون", "اذمم دائنة", "الموردون", "الموردين",
    ],
    "selling_expenses": [
        "selling expenses", "sales and marketing expenses",
        "selling and distribution expenses", "marketing expenses",
        # Arabic
        "مصاريف البيع", "مصاريف البيع والتسويق",
        "مصروفات بيع وتسويق", "مصروفات بيع",
        "مصروفات بيعية وتسويقية", "مصاريف بيعية وتسويقية",
    ],
    "rd_expenses": [
        "research and development", "research and development expenses",
        "r d", "rd expenses",
        # Arabic
        "البحث والتطوير", "مصاريف البحث والتطوير",
    ],
}

# Labels that contain an alias as a substring but must NOT map to that field.
FIELD_EXCLUSIONS: set[str] = {
    "total liabilities and equity",
    "total liabilities and shareholders equity",
    "total liabilities and stockholders equity",
    "total liabilities and owners equity",
    "total equity and liabilities",
    "total assets and liabilities",
    "total non current assets",
    "non current assets",
    # Arabic variants seen in real statements
    "اجمالي الاصول غير المتداوله",
    "الاصول غير المتداوله",
    "اجمالي الخصوم وحقوق الملكيه",
    "الخصوم وحقوق الملكيه",
    "اجمالي الالتزامات وحقوق الملكيه",
    "الالتزامات وحقوق الملكيه",
    "الخصوم طويله الاجل",
    "اجمالي الخصوم طويله الاجل",
    "الالتزامات طويله الاجل",
    "اجمالي الالتزامات طويله الاجل",
    "الالتزامات غير المتداوله",
    "اجمالي الالتزامات غير المتداوله",
    "الخصوم غير المتداوله",
    "اجمالي الخصوم غير المتداوله",
    "مجمع الاهلاك",
    "مجمع الاهلاكات",
    "معدل ضريبه الدخل افتراض",
    "معدل الضريبه",
}

# Core fields: the analysis can proceed only if one of these exists for BOTH years.
CORE_FIELDS = ("revenue", "net_income")

REQUIRED_FIELDS_FOR = {
    # metric -> fields needed (used to build clear "missing data" reasons)
    "gross_profit_margin": ["revenue"],
    "operating_margin": ["revenue", "operating_income"],
    "net_profit_margin": ["revenue", "net_income"],
    "roa": ["net_income", "total_assets"],
    "roe": ["net_income", "equity"],
    "current_ratio": ["current_assets", "current_liabilities"],
    "debt_to_equity": ["total_debt", "equity"],
}
