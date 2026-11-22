"""Central configuration: field aliases, model settings, thresholds."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")

_FAST_LIVE_MODELS_STR = (
    "gemini-flash-lite-latest,"
    "gemini-3.1-flash-lite-preview,"
    "gemini-3.5-flash-lite,"
    "gemini-3-flash-preview,"
    "gemini-3.1-flash-lite,"
    "gemini-3.6-flash,"
    "gemini-3.8-flash"
)
_FAST_TIER_SENTINELS = (
    "gemini-flash-lite-latest",
    "gemini-3.1-flash-lite-preview",
    "gemini-3.5-flash-lite",
)


def _upgrade_legacy_cloud_models(raw: str) -> str:
    """If Streamlit Cloud Secrets still holds the legacy slow 503/504 model list
    (no fast lite tier models), auto-upgrade it to the 7 verified fast models."""
    models = [m.strip() for m in str(raw or "").split(",") if m.strip()]
    if not models:
        return _FAST_LIVE_MODELS_STR
    if any(m in _FAST_TIER_SENTINELS for m in models):
        return ",".join(models)
    # Legacy list detected (e.g. 3.6/3.5/3.8/3.7/flash-latest without fast tier)
    return _FAST_LIVE_MODELS_STR


# توافق السحابة (Streamlit Community Cloud): أسرار اللوحة تُقرأ عبر
# st.secrets — نسحب المفتاحية إلى بيئة النظام كي يجدها مسبح المفاتيح
# والمحللات. محمي بالكامل: محليًا .env يتحكم، والسحابة بلا أسرار تمرّ سالمًا.
try:
    import streamlit as _st  # noqa: E402

    for _key in ("GEMINI_API_KEYS", "GEMINI_MODELS", "GEMINI_MODEL",
                 "REPORT_LANGUAGE", "TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_IDS",
                 "LOCAL_OCR_ENABLED", "LOCAL_OCR_WORKERS", "FOCUSED_LOCAL_VERIFY",
                 "VISION_SEMANTIC", "REVIEW_HMAC_KEY", "REVIEW_LOG_PATH",
                 "REVIEWER_NAME"):
        if not os.getenv(_key):
            try:
                _v = _st.secrets.get(_key)
                if _v:
                    _val = str(_v)
                    if _key == "GEMINI_MODELS" and not os.getenv("PYTEST_CURRENT_TEST"):
                        _val = _upgrade_legacy_cloud_models(_val)
                    os.environ[_key] = _val
            except Exception:
                pass

    # If a warm Streamlit Cloud container already loaded legacy GEMINI_MODELS
    # before this hot-reload, upgrade it in-place once (never during pytest).
    if not os.getenv("PYTEST_CURRENT_TEST") and os.getenv("GEMINI_MODELS"):
        try:
            if _st.secrets.get("GEMINI_MODELS"):
                os.environ["GEMINI_MODELS"] = _upgrade_legacy_cloud_models(
                    os.environ["GEMINI_MODELS"]
                )
        except Exception:
            pass

    # سجل المراجعين على السحابة: JSON كامل في سر واحد (REVIEWERS_JSON) يُكتب
    # مرة واحدة لملف وقت التشغيل ويُضبط REVIEWERS_FILE عليه — الملف يحوي
    # hashes فقط (PBKDF2) ولا يحوي أي PIN نصي.
    try:
        _rv = _st.secrets.get("REVIEWERS_JSON")
        if _rv and not os.getenv("REVIEWERS_FILE"):
            import json as _json
            import tempfile as _tempfile

            _parsed = _json.loads(str(_rv))
            if isinstance(_parsed, dict) and _parsed.get("reviewers"):
                _rp = Path(_tempfile.gettempdir()) / "finsight_reviewers.json"
                _rp.write_text(_json.dumps(_parsed, ensure_ascii=False), encoding="utf-8")
                try:
                    os.chmod(_rp, 0o600)
                except OSError:
                    pass
                os.environ["REVIEWERS_FILE"] = str(_rp)
    except Exception:
        pass
except Exception:
    pass  # بيئة بلا streamlit (سكربتات) — .env يكفي

if not os.getenv("PYTEST_CURRENT_TEST"):
    _default_rev = PROJECT_ROOT / "data" / "default_reviewers.json"
    if not os.getenv("REVIEWERS_FILE") and _default_rev.exists():
        os.environ["REVIEWERS_FILE"] = str(_default_rev)
    if not os.getenv("REVIEW_HMAC_KEY"):
        os.environ["REVIEW_HMAC_KEY"] = "finsight-cloud-instance-hmac-key-2026"
    if not os.getenv("REVIEW_LOG_PATH"):
        import tempfile as _tf_cfg
        os.environ["REVIEW_LOG_PATH"] = str(Path(_tf_cfg.gettempdir()) / "finsight_human_reviews.json")

# --- AI ---
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview").strip() or "gemini-3-flash-preview"

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
        "operating costs",
        "cost of revenue", "total cost of revenue", "cost of goods sold",
        "cogs", "cost of sales", "direct costs",
        # Arabic
        "تكلفة الايرادات", "تكلفة المبيعات", "تكلفة البضاعة المباعة",
    ],
    "gross_profit": [
        "gross profit", "gross income", "total gross profit",
        # Arabic
        "اجمالي الربح", "الربح الاجمالي",
        # عز 2023: قائمة الدخل تطبع «مجمل الربح» — «اجمالي» ليست كلمتها
        "مجمل الربح", "المجمل",
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
        # إصلاح حديد عز (إصلاح 2 — مرادفات مصرية بصيغة قائمة الدخل المحلية):
        # صافي أرباح النشاط 875,232,929 ج.م (2021) كان N/A بقصور المطابقة
        "صافي ارباح النشاط", "صافي ارباح خسائر النشاط",
        "صافي خسائر النشاط", "مجمل ارباح النشاط",
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
        # عز 2023: «صافى أرباح / (خسائر) العام» — normalize يدخل
        # «خساير» بين ارباح والعام فيكسر الـalias الأصصر. سطر «قبل
        # ضريبة الدخل» الذي يحمل الـsubstring نفسه يُقلب pretax بفلتر
        # «قبل ضريب» في match_field (عز 2023)
        "صافي ارباح خساير العام",
    ],
    # ص6 prints this subtotal BEFORE the «يضاف / (يخصم)» bridge:
    # net activity profit − net financing costs + dividends from
    # subsidiaries = pretax; pretax − tax = net income. A DIFFERENT line
    # from net income — it must never feed it (see _FIELD_NEGATIVE_PATTERNS).
    "net_activity_profit": [
        "net activity profit", "profit from activities",
        # Arabic
        "صافي أرباح النشاط", "صافى ارباح النشاط", "ارباح النشاط",
        "صافي ربح النشاط",
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
        # عز 2023: صف الميزانية مطبوع «مخزون» مجردة (بلا ال) — الـalias
        # المعرّف بالتاء المجرّدة كان يفوّته. صف «الانخفاض في قيمة
        # المخزون» محجوب بنمط سلبي (match_field)
        "مخزون", "صافي المخزون",
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
        # v7 (تدقيق حديد عز): «تسهيلات بنكية» صف مستقل بميزانية 2022 —
        # كان يرجع None (فجوة مطابقة) فتسرب D/E ≈ 0.03
        "تسهيلات بنكيه", "تسهيلات بنكية",
        # v6 إصلاح حديد عز: التسهيلات الائتمانية والسحب على المكشوف صارا
        # حقليْن كانسيين مستقلين (short_term_credit_facilities /
        # bank_overdraft) — كل بند مطبوع بحقله، وإجمالي الدين يجمع الستة.
    ],
    # إصلاح حديد عز (التدقيق الجنائي): «بنوك تسهيلات إئتمانية» 3,915,952,409
    # (2021) و4,103,631,657 (2020) أغفلها النظام فخرجت D/E 0.08x بدل 0.83x —
    # إجمالي المديونية الفعلي بالإيضاح 32-2 هو 5,252,833,283 ج.م.
    "short_term_credit_facilities": [
        "short term credit facilities", "bank credit facilities",
        "credit facilities",
        # Arabic — أشكال الطباعة الفعلية (normalize_label يوحد ئ→ي والهمزات)
        "بنوك تسهيلات ائتمانية", "بنوك تسهيلات إنتمانية",
        "تسهيلات ائتمانية قصيرة الأجل", "تسهيلات ائتمانيه قصيره الاجل",
        "بنوك - تسهيلات ائتمانية", "تسهيلات ائتمانية",
    ],
    # «بنوك - سحب على المكشوف» 2,655,419 ج.م (2021) — بند مستقل مطبوع
    "bank_overdraft": [
        "bank overdraft", "overdrafts",
        # Arabic
        "بنوك سحب على المكشوف", "سحب على المكشوف",
        "بنوك - سحب على المكشوف",
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
    # توزيعات أرباح من الشركات التابعة — بند مؤثر في تفسير نمو الأرباح
    "dividends_from_subsidiaries": [
        "dividends from subsidiaries", "income from subsidiaries",
        # Arabic
        "توزيعات أرباح من شركات تابعة", "توزيعات أرباح من الشركات التابعة",
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
        # صيغة مطبوعة بديلة (وُجدت في وثيقة 2022): «النائجة» بدل «الناتجة»
        "النقديه النايجه من انشطه التشغيل",
        "النقديه الناتجه من انشطه التشغيل",
        "النقديه المستخدمه في انشطه التشغيل",
        # عز 2023: «صافي التدفقات النقدية (المستخدمة في) / الناتجة من
        # أنشطة التشغيل» — normalize يزيل القوسين والشرطة فيصبح
        # «المستخدمه في الناتجه من انشطه التشغيل» فيكسر كل ما سبق
        "المستخدمه في الناتجه من انشطه التشغيل",
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
        # عز 2023: نفس صيغة القوسين «(المستخدمة في) / الناتجة من أنشطة
        # الاستثمار» — بعد التطبيع «المستخدمه في الناتجه من انشطه...»
        "المستخدمه في الناتجه من انشطه الاستثمار",
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
        # عز 2023: صيغة القوسين «(المستخدمة في) / الناتجة من أنشطة التمويل»
        "المستخدمه في الناتجه من انشطه التمويل",
    ],
    # عز 2023: صفوف «إجمالي الأصول/الالتزامات غير المتداولة» كانت بلا
    # حقل كانونية إطلاقًا فبقيت مفقودة في كل تشغيل
    "non_current_assets": [
        "non current assets", "non-current assets", "fixed and non current assets",
        # Arabic
        "اجمالي الاصول غير المتداوله", "الاصول غير المتداوله",
        "الاصول الغير متداوله", "اجمالي الاصول الغير متداوله",
    ],
    "non_current_liabilities": [
        "non current liabilities", "non-current liabilities",
        # Arabic
        "اجمالي الالتزامات غير المتداوله", "الالتزامات غير المتداوله",
        "الالتزامات الغير متداوله", "اجمالي الالتزامات الغير متداوله",
        "الخصوم غير المتداوله", "اجمالي الخصوم غير المتداوله",
    ],
    "capital": [
        "paid in capital", "share capital", "issued capital",
        "capital stock",
        # Arabic — «رأس المال العامل» (المقياس) محجوب بنمط سلبي
        "راس المال المصدر", "راس المال المدفوع", "راس المال",
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
        "before taxes",
        "before income tax",
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
        # عز 2023: صف الميزانية «عملاء و اوراق قبض» مجردة + «صافي
        # العملاء...» — «عملاء دفعات مقدمة» (التزام) محجوبة بنمط سلبي
        "عملاء", "اوراق قبض", "أوراق قبض",
    ],
    "accounts_payable": [
        "creditors and other credit balances",
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
    "admin_expenses": [
        "general and administrative expenses", "administrative expenses",
        "general administrative expenses", "g and a expenses",
        # Arabic
        "مصروفات عمومية وإدارية", "مصروفات عموميه واداريه",
        "مصاريف عمومية وإدارية", "مصاريف عموميه واداريه",
        "مصروفات إدارية وعمومية", "مصاريف إدارية وعمومية",
        "المصروفات العمومية والإدارية", "المصاريف العمومية والإدارية",
    ],
    "other_operating_expenses": [
        "other operating expenses", "other operating costs",
        # Arabic
        "مصروفات تشغيل أخرى", "مصروفات تشغيل اخري",
        "مصاريف تشغيل أخرى", "مصاريف تشغيل اخري",
        "مصروفات تشغيلية أخرى", "مصاريف تشغيلية أخرى",
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
    # عز 2023: «total/اجمالي الاصول غير المتداولة» أُزيلت من الاستبعاد —
    # لها حقل كانوني الآن (كانت تستبعد لأنها اختُرفت لحقل الإجمالي)
    "اجمالي الخصوم وحقوق الملكيه",
    "الخصوم وحقوق الملكيه",
    "اجمالي الالتزامات وحقوق الملكيه",
    "الالتزامات وحقوق الملكيه",
    "الخصوم طويله الاجل",
    "اجمالي الخصوم طويله الاجل",
    "الالتزامات طويله الاجل",
    "اجمالي الالتزامات طويله الاجل",
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
