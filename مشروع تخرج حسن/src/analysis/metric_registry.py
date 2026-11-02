"""Financial Metric Registry (سجل المؤشرات المالية) — the single source of
truth documenting ALL 60 metrics the engine computes, per the external-audit
mandate (phase 4).

Every entry carries: metric_id, Arabic/English names, the FORMULA as
implemented in calculator.py, required canonical inputs, the accounting
definition, the calculation period, the average-balance policy, unit,
precision, zero-denominator policy, negative-value policy, interpretation
rule, category, and test reference.

validation_status per entry: "validated" = covered by an independent
hand-computed unit test; "documented" = defined and exercised by the live
pipeline but without a dedicated hand-computed fixture yet.

build_decision_log-compatible: consumers can check required_inputs against
FinancialData.values and mark MISSING/UNVERIFIED per input (lineage phase 9).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MetricEntry:
    metric_id: str
    name_ar: str
    name_en: str
    formula: str
    required_inputs: tuple
    definition: str
    period: str
    average_policy: str
    unit: str
    precision: int
    zero_denominator_policy: str
    negative_policy: str
    interpretation: str          # higher | lower | neutral (economic meaning)
    category: str
    test_reference: str
    validation_status: str = "documented"


_D = "تُحسب من أرقام السنة الحالية"
_AVG = "متوسط رصيد السنة الحالية والسابقة عند توفرهما، وإلا رصيد السنة الحالية مع ملاحظة"
_ZD = "N/A صادق — لا قيمة عند صفر المقام"
_ZD_KEEP = "N/A صادق — والقيمة السالبة للمقام تعني دلالة مختلفة تُذكر"
_NEG_ABS = "السالبة تُعامل مطلقًا (مصروف مطبوع بين قوسين)"
_NEG_KEEP = "السالب دلالة حقيقية تُعرض كما هي"
_H = "higher"   # الأعلى أفضل
_L = "lower"    # الأقل أفضل
_N = "neutral"  # حسب السياق

REGISTRY: list[MetricEntry] = [
    # ── Growth & Income (النمو والدخل) ──
    MetricEntry("revenue_growth", "نمو الإيرادات", "Revenue Growth",
        "(Revenue₂ − Revenue₁) / Revenue₁ × 100", ("revenue",),
        "نمو الإيرادات المحققة سنة-على-سنة", "سنتان متتاليتان", "لا ينطبق",
        "%", 2, _ZD, _NEG_KEEP, _H, "Growth & Income", "test_pipeline", "validated"),
    MetricEntry("net_income_growth", "نمو صافي الربح", "Net Income Growth",
        "(NI₂ − NI₁) / NI₁ × 100", ("net_income",),
        "نمو صافي الربح — يتأثر ببنود غير تشغيلية", "سنتان", "لا ينطبق",
        "%", 2, _ZD, _NEG_KEEP, _H, "Growth & Income", "test_pipeline", "validated"),
    MetricEntry("gross_profit_growth", "نمو مجمل الربح", "Gross Profit Growth",
        "(GP₂ − GP₁) / GP₁ × 100", ("gross_profit",),
        "نمو مجمل الربح", "سنتان", "لا ينطبق", "%", 2, _ZD, _NEG_KEEP, _H,
        "Growth & Income", "test_pipeline", "validated"),
    MetricEntry("operating_income_growth", "نمو الربح التشغيلي", "Operating Income Growth",
        "(OI₂ − OI₁) / OI₁ × 100", ("operating_income",),
        "نمو الربح التشغيلي", "سنتان", "لا ينطبق", "%", 2, _ZD, _NEG_KEEP, _H,
        "Growth & Income", "test_pipeline", "validated"),
    MetricEntry("total_assets_growth", "نمو إجمالي الأصول", "Total Assets Growth",
        "(TA₂ − TA₁) / TA₁ × 100", ("total_assets",),
        "نمو حجم الميزانية", "سنتان", "لا ينطبق", "%", 2, _ZD, _NEG_KEEP, _N,
        "Growth & Income", "test_pipeline", "validated"),
    MetricEntry("equity_growth", "نمو حقوق الملكية", "Equity Growth",
        "(E₂ − E₁) / E₁ × 100", ("equity",),
        "نمو حقوق الملكية", "سنتان", "لا ينطبق", "%", 2, _ZD, _NEG_KEEP, _H,
        "Growth & Income", "test_pipeline", "validated"),
    MetricEntry("cfo_growth", "نمو التدفق التشغيلي", "CFO Growth",
        "(CFO₂ − CFO₁) / CFO₁ × 100", ("operating_cash_flow",),
        "نمو التدفق التشغيلي", "سنتان", "لا ينطبق", "%", 2, _ZD, _NEG_KEEP, _H,
        "Growth & Income", "test_pipeline", "validated"),

    # ── القيم المطلقة المطبوعة (صفوف مستقلة في التقرير — مستخلصة وتتحقق آليًا) ──
    MetricEntry("revenue", "الإيرادات", "Revenue (reported)",
        "القيمة المطبوعة في قائمة الدخل — مستخلصة وتتحقق طبقات المصادر",
        ("revenue",), "الإيراد المحقق", "قائمة الدخل", "لا ينطبق (قيمة مطبوعة)",
        "عملة", 0, "لا ينطبق", "لا يُشتق أبدًا — قراءة مباشرة موثقة", _N,
        "Growth & Income", "test_decision_log", "validated"),
    MetricEntry("net_income", "صافي أرباح العام", "Net Income (reported)",
        "القيمة المطبوعة — تُطبع في ثلاث قوائم ويحسم التصويت والتحقق",
        ("net_income",), "صافي ربح العام", "ثلاث قوائم + تحقق مركزي + رأي ثالث",
        "لا ينطبق", "عملة", 0, "لا ينطبق", "لا يُشتق — الأكثر تحققًا في النظام",
        _N, "Growth & Income", "test_decision_log", "validated"),
    MetricEntry("gross_profit", "مجمل الربح", "Gross Profit (reported)",
        "المطبوع؛ يُشتق (الإيراد − التكلفة) عند غيابه مع علم", ("gross_profit",),
        "مجمل الربح", "قائمة الدخل", "لا ينطبق", "عملة", 0, "لا ينطبق",
        "الاشتقاق مسموح مع علم — الإيراد والتكلفة يتحققان بالهوية", _N,
        "Profitability", "test_pipeline", "validated"),
    MetricEntry("operating_income", "الربح التشغيلي", "Operating Income (reported)",
        "المطبوع؛ يُشتق (المجمل − المصروفات) عند غيابه", ("operating_income",),
        "الربح التشغيلي", "قائمة الدخل", "لا ينطبق", "عملة", 0, "لا ينطبق",
        "يُشتق مع علم عند الغياب", _N, "Profitability", "test_pipeline", "documented"),
    MetricEntry("operating_cash_flow", "صافي التدفق التشغيلي", "Operating Cash Flow (reported)",
        "المطبوع في قائمة التدفقات — يتحقق بطبقة مخصصة بنسختي معالجة",
        ("operating_cash_flow",), "التدفق التشغيلي", "قائمة التدفقات + تحقق مخصص",
        "لا ينطبق", "عملة", 0, "لا ينطبق", "السالب = استهلاك نقدي", _N,
        "Cash Flow", "test_decision_log", "validated"),
    MetricEntry("investing_cash_flow", "صافي التدفق الاستثماري", "Investing Cash Flow (reported)",
        "المطبوع في قائمة التدفقات — يتحقق بطبقة التدفقات", ("investing_cash_flow",),
        "التدفق الاستثماري", "قائمة التدفقات + تحقق مزدوج", "لا ينطبق",
        "عملة", 0, "لا ينطبق", "السالب طبيعي (استثمار)", _N, "Cash Flow",
        "test_decision_log", "validated"),
    MetricEntry("financing_cash_flow", "صافي التدفق التمويلي", "Financing Cash Flow (reported)",
        "المطبوع — يتحقق بطبقة مزدوجة (صحح لايف 727,093,341 → 727,063,341)",
        ("financing_cash_flow",), "التدفق التمويلي", "قائمة التدفقات + تحقق مزدوج",
        "لا ينطبق", "عملة", 0, "لا ينطبق", "السالب طبيعي (سداد)", _N,
        "Cash Flow", "test_decision_log", "validated"),
    # ── Profitability (الربحية) ──
    MetricEntry("gross_margin", "هامش مجمل الربح", "Gross Margin",
        "Gross Profit / Revenue × 100", ("gross_profit", "revenue"),
        "ربحية النشاط الأساسي بعد تكلفة المبيعات", "تدفقات السنة الحالية", "لا ينطبق",
        "%", 2, _ZD, _NEG_KEEP, _H, "Profitability", "test_metric_registry", "validated"),
    MetricEntry("operating_margin", "هامش الربح التشغيلي", "Operating Margin",
        "Operating Income / Revenue × 100", ("operating_income", "revenue"),
        "ربحية النشاط قبل التمويل والضرائب", "تدفقات السنة", "لا ينطبق",
        "%", 2, _ZD, _NEG_KEEP, _H, "Profitability", "test_metric_registry", "validated"),
    MetricEntry("ebitda_margin", "هامش EBITDA", "EBITDA Margin",
        "EBITDA / Revenue × 100", ("ebitda", "revenue"),
        "الربحية قبل الإهلاك والتمويل والضرائب", "تدفقات السنة", "لا ينطبق",
        "%", 2, _ZD, _NEG_KEEP, _H, "Profitability", "test_pipeline", "documented"),
    MetricEntry("pretax_margin", "هامش الربح قبل الضريبة", "Pretax Margin",
        "Pretax Income / Revenue × 100", ("pretax_income", "revenue"),
        "الربحية قبل الضريبة شاملة البنود الأخرى", "تدفقات السنة", "لا ينطبق",
        "%", 2, _ZD, _NEG_KEEP, _H, "Profitability", "test_metric_registry", "validated"),
    MetricEntry("net_margin", "هامش صافي الربح", "Net Margin",
        "Net Income / Revenue × 100", ("net_income", "revenue"),
        "الربحية النهائية لكل جنيه إيراد", "تدفقات السنة", "لا ينطبق",
        "%", 2, _ZD, _NEG_KEEP, _H, "Profitability", "test_metric_registry", "validated"),
    MetricEntry("roa", "العائد على الأصول", "ROA",
        "Net Income / Average Total Assets × 100", ("net_income", "total_assets"),
        "كفاءة الأصول في توليد الربح", "متوسط الأرصدة", _AVG,
        "%", 2, "المقام صفر → N/A", _NEG_KEEP, _H, "Profitability",
        "test_metric_registry", "validated"),
    MetricEntry("roe", "العائد على حقوق الملكية", "ROE",
        "Net Income / Average Equity × 100", ("net_income", "equity"),
        "عائد المساهمين — على متوسط الأرصدة (يختلف عن دوبونت المحسوب على أرصدة نهاية الفترة)",
        "متوسط الأرصدة", _AVG, "%", 2, "المقام صفر → N/A", _NEG_KEEP, _H,
        "Profitability", "test_metric_registry", "validated"),
    MetricEntry("roic", "العائد على رأس المال المستثمر", "ROIC",
        "EBIT × (1 − EffectiveTaxRate) / (Total Debt + Equity) × 100",
        ("operating_income", "pretax_income", "income_tax_expense", "total_debt", "equity"),
        "العائد على إجمالي رأس المال المستثمر (دين + حقوق)", "أرصدة نهاية الفترة",
        "لا ينطبق (رأس مال نهاية الفترة)", "%", 2, _ZD, _NEG_KEEP, _H,
        "Profitability", "test_pipeline", "documented"),
    MetricEntry("roce", "العائد على رأس المال المستخدم", "ROCE",
        "Operating Income / (Total Assets − Current Liabilities) × 100",
        ("operating_income", "total_assets", "current_liabilities"),
        "كفاءة رأس المال طويل الأجل", "أرصدة نهاية الفترة", "لا ينطبق",
        "%", 2, "رأس المال المستخدم ≤ 0 → N/A", _NEG_KEEP, _H,
        "Profitability", "test_pipeline", "documented"),
    MetricEntry("cash_roa", "العائد النقدي على الأصول", "Cash ROA",
        "Operating Cash Flow / Average Total Assets × 100",
        ("operating_cash_flow", "total_assets"),
        "جودة الأرباح: النقد الناتج من كل جنيه أصول", "متوسط الأرصدة", _AVG,
        "%", 2, _ZD, _NEG_KEEP, _H, "Profitability", "test_pipeline", "documented"),

    # ── Liquidity (السيولة) ──
    MetricEntry("current_ratio", "النسبة الجارية", "Current Ratio",
        "Current Assets / Current Liabilities", ("current_assets", "current_liabilities"),
        "تغطية الالتزامات المتداولة بالأصول المتداولة", "أرصدة نهاية الفترة",
        "لا ينطبق (رصيد لحظي)", "x", 2, _ZD, _NEG_KEEP, _H, "Liquidity",
        "test_metric_registry", "validated"),
    MetricEntry("quick_ratio", "النسبة السريعة", "Quick Ratio",
        "(Current Assets − Inventory) / Current Liabilities",
        ("current_assets", "inventory", "current_liabilities"),
        "التعريف التقليدي: يستبعد المخزون فقط — يشمل أصولا متداولة أخرى (مثل الدفعات المقدمة). "
        "لا يستبعد النقدية المقيدة إلا إن فصلها الإيضاح. اسم بديل: Acid-Test.",
        "أرصدة نهاية الفترة", "لا ينطبق", "x", 2,
        "بدون المخزون لا تُحسب (ستساوي الجارية صامتة) — N/A صادق", _NEG_KEEP, _H,
        "Liquidity", "test_metric_registry", "validated"),
    MetricEntry("cash_ratio", "نسبة النقدية", "Cash Ratio",
        "Cash / Current Liabilities", ("cash", "current_liabilities"),
        "أكثر نسب السيولة تحفظًا", "أرصدة نهاية الفترة", "لا ينطبق",
        "x", 2, _ZD, _NEG_KEEP, _H, "Liquidity", "test_pipeline", "documented"),
    MetricEntry("ocf_ratio", "نسبة التدفق التشغيلي", "Operating Cash Flow Ratio",
        "Operating Cash Flow / Current Liabilities", ("operating_cash_flow", "current_liabilities"),
        "السيولة النقدية المتولدة تشغيليًا", "تدفق السنة / رصيد نهاية الفترة", "لا ينطبق",
        "x", 2, _ZD, "التدفق السالب يعني عجزًا تشغيليًا", _H, "Liquidity",
        "test_pipeline", "documented"),

    # ── Leverage (المديونية) — التعريف: الدين ذو الفائدة ≠ إجمالي الالتزامات ──
    MetricEntry("debt_to_equity", "الدين / حقوق الملكية", "Debt to Equity (Interest-Bearing)",
        "Total Debt (Interest-Bearing) / Equity", ("total_debt", "equity"),
        "إجمالي الدين = بنوك تسهيلات + أقساط قروض متداولة + قروض غير متداولة "
        "(لا يشمل الموردين والمخصصات وغيرها من الالتزامات غير السعورية)",
        "أرصدة نهاية الفترة", "لا ينطبق", "x", 2, "حقوق سالبة/صفر → N/A",
        _NEG_KEEP, _L, "Leverage", "test_debt_mapping", "validated"),
    MetricEntry("debt_ratio", "نسبة الالتزامات إلى الأصول", "Debt Ratio (Total Liabilities)",
        "Total Liabilities / Total Assets", ("total_liabilities", "total_assets"),
        "نسبة إجمالي الالتزامات (شاملة غير السعورية) — تعريف منفصل عن الدين ذي الفائدة",
        "أرصدة نهاية الفترة", "لا ينطبق", "x", 2, _ZD, _NEG_KEEP, _L,
        "Leverage", "test_metric_registry", "validated"),
    MetricEntry("debt_to_assets", "الدين / الأصول", "Debt to Assets",
        "Total Debt (Interest-Bearing) / Total Assets", ("total_debt", "total_assets"),
        "الدين ذو الفائدة مقابل الأصول", "أرصدة نهاية الفترة", "لا ينطبق",
        "x", 2, _ZD, _NEG_KEEP, _L, "Leverage", "test_pipeline", "documented"),
    MetricEntry("liabilities_to_equity", "الالتزامات / حقوق الملكية", "Liabilities to Equity",
        "Total Liabilities / Equity", ("total_liabilities", "equity"),
        "الرافعة المحاسبية الشاملة", "أرصدة نهاية الفترة", "لا ينطبق",
        "x", 2, "حقوق صفر/سالبة → N/A", _NEG_KEEP, _L, "Leverage",
        "test_pipeline", "documented"),
    MetricEntry("equity_ratio", "نسبة حقوق الملكية", "Equity Ratio",
        "Equity / Total Assets", ("equity", "total_assets"),
        "حصة المساهمين من الأصول", "أرصدة نهاية الفترة", "لا ينطبق",
        "x", 2, _ZD, _NEG_KEEP, _H, "Leverage", "test_pipeline", "documented"),
    MetricEntry("financial_leverage", "الرافعة المالية", "Financial Leverage",
        "Total Assets / Equity", ("total_assets", "equity"),
        "مضاعف حقوق الملكية — مدخل دوبونت", "أرصدة نهاية الفترة", "لا ينطبق",
        "x", 2, "حقوق صفر/سالبة → N/A", _NEG_KEEP, _N, "Leverage",
        "test_metric_registry", "validated"),
    MetricEntry("interest_coverage", "تغطية الفوائد", "Interest Coverage",
        "Operating Income / |Interest Expense|", ("operating_income", "interest_expense"),
        "قدرة الربح التشغيلي على تغطية التكاليف التمويلية", "تدفقات السنة", "لا ينطبق",
        "x", 2, "المقام صفر → N/A (لا دين)؛ سالب المقام يعني فوائد دائنة", _NEG_KEEP,
        _H, "Leverage", "test_metric_registry", "validated"),

    # ── Efficiency (الكفاءة) — متوسطات الأرصدة مع الرجوع الموثق ──
    MetricEntry("asset_turnover", "دوران الأصول", "Asset Turnover",
        "Revenue / Average Total Assets", ("revenue", "total_assets"),
        "كفاءة الأصول في توليد الإيراد", "متوسط الأرصدة", _AVG, "x", 2,
        _ZD, _NEG_KEEP, _H, "Efficiency", "test_metric_registry", "validated"),
    MetricEntry("fixed_asset_turnover", "دوران الأصول الثابتة", "Fixed Asset Turnover",
        "Revenue / Average Fixed Assets", ("revenue", "fixed_assets"),
        "إيراد لكل جنيه أصول ثابتة — على صافي القيمة الدفترية المطبوعة",
        "متوسط الأرصدة", _AVG, "x", 2, _ZD, _NEG_KEEP, _H, "Efficiency",
        "test_metric_registry", "validated"),
    MetricEntry("inventory_turnover", "دوران المخزون", "Inventory Turnover",
        "|Cost of Revenue| / Average Inventory", ("cost_of_revenue", "inventory"),
        "مرات بيع المخزون سنويًا — التكلفة لا الإيراد", "متوسط الأرصدة", _AVG,
        "x", 2, _ZD, "مخزون سالب = خطأ التقاط يُعلَّم", _H, "Efficiency",
        "test_metric_registry", "validated"),
    MetricEntry("receivables_turnover", "دوران الذمم المدينة", "Receivables Turnover",
        "Revenue / Average Accounts Receivable", ("revenue", "accounts_receivable"),
        "سرعة التحصيل من العملاء", "متوسط الأرصدة", _AVG, "x", 2, _ZD,
        "ذمم سالبة = خطأ التقاط يُعلَّم", _H, "Efficiency", "test_metric_registry",
        "validated"),
    MetricEntry("payables_turnover", "دوران الذمم الدائنة", "Payables Turnover",
        "|Cost of Revenue| / Average Accounts Payable", ("cost_of_revenue", "accounts_payable"),
        "سرعة السداد للموردين", "متوسط الأرصدة", _AVG, "x", 2, _ZD, _NEG_KEEP,
        _N, "Efficiency", "test_metric_registry", "validated"),
    MetricEntry("working_capital_turnover", "دوران رأس المال العامل", "Working Capital Turnover",
        "Revenue / Average Working Capital", ("revenue", "current_assets", "current_liabilities"),
        "كفاءة رأس المال العامل — متوسط (أصول متداولة − التزامات متداولة) للسنتين",
        "متوسط أرصدة السنتين", _AVG, "x", 2, "رأس مال عامل صفر/سالب → N/A مع ملاحظة",
        "رأس مال عامل سالب يجعل الاتجاه معكوسًا", _H, "Efficiency",
        "test_pipeline", "documented"),

    # ── Days & CCC (الأيام ودورة التحويل) ──
    MetricEntry("inventory_days", "أيام المخزون", "Days Inventory Outstanding (DIO)",
        "365 / Inventory Turnover", ("inventory_turnover",),
        "أيام بقاء المخزون قبل البيع", "مشتق من دوران المخزون", "لا ينطبق",
        "يوم", 1, "دوران صفر → N/A", "مخزون سالب يجعل الأيام بلا معنى", _L,
        "Days & CCC", "test_pipeline", "documented"),
    MetricEntry("days_sales_outstanding", "أيام التحصيل", "Days Sales Outstanding (DSO)",
        "365 / Receivables Turnover", ("receivables_turnover",),
        "أيام تحصيل الذمم", "مشتق", "لا ينطبق", "يوم", 1, "دوران صفر → N/A",
        "ذمم سالبة تجعل DSO بلا معنى", _L, "Days & CCC", "test_pipeline", "documented"),
    MetricEntry("days_payables_outstanding", "أيام السداد", "Days Payables Outstanding (DPO)",
        "365 / Payables Turnover", ("payables_turnover",),
        "أيام سداد الموردين — أعلى = تمويل مجاني من الموردين", "مشتق", "لا ينطبق",
        "يوم", 1, "دوران صفر → N/A", "الأعلى يخفف الضغط النقدي عمومًا", _N,
        "Days & CCC", "test_pipeline", "documented"),
    MetricEntry("cash_conversion_cycle", "دورة التحويل النقدي", "Cash Conversion Cycle (CCC)",
        "DIO + DSO − DPO", ("inventory_days", "days_sales_outstanding", "days_payables_outstanding"),
        "الأيام بين دفع الموردين وتحصيل العملاء", "مشتق", "لا ينطبق",
        "يوم", 1, "مكون ناقص → N/A", "السالب = دورة تمويل ذاتي من الموردين", _L,
        "Days & CCC", "test_pipeline", "documented"),

    # ── Working Capital (رأس المال العامل) ──
    MetricEntry("working_capital", "رأس المال العامل", "Working Capital",
        "Current Assets − Current Liabilities", ("current_assets", "current_liabilities"),
        "الفارق التمويلي قصير الأجل", "أرصدة نهاية الفترة", "لا ينطبق",
        "عملة", 0, "لا ينطبق (فرق)", "السالب = عجز تمويلي قصير الأجل", _N,
        "Working Capital", "test_metric_registry", "validated"),
    MetricEntry("operating_working_capital", "رأس المال العامل التشغيلي",
        "Operating Working Capital", "AR + Inventory − Accounts Payable",
        ("accounts_receivable", "inventory", "accounts_payable"),
        "رأس المال العامل الناتج من النشاط فقط", "أرصدة نهاية الفترة", "لا ينطبق",
        "عملة", 0, "لا ينطبق (فرق)", "السالب = تمويل ذاتي من الموردين", _N,
        "Working Capital", "test_pipeline", "documented"),
    MetricEntry("working_capital_turnover_wc", "دوران رأس المال العامل", "Working Capital Turnover",
        "Revenue / Average Working Capital", ("revenue", "working_capital"),
        "مكرر مع دوران رأس المال العامل — يُعرض في فئة رأس المال العامل",
        "متوسط أرصدة السنتين", _AVG, "x", 2, "رأس مال عامل صفر → N/A",
        "السالب يعكس الاتجاه", _H, "Working Capital", "test_pipeline", "documented"),

    # ── Cash Flow (التدفقات النقدية) ──
    MetricEntry("cfo_margin", "هامش التدفق التشغيلي", "CFO Margin",
        "Operating Cash Flow / Revenue × 100", ("operating_cash_flow", "revenue"),
        "النقد الناتج من كل جنيه إيراد", "تدفق السنة", "لا ينطبق",
        "%", 2, _ZD, "السالب = حرق نقدي تشغيلي", _H, "Cash Flow",
        "test_metric_registry", "validated"),
    MetricEntry("free_cash_flow", "التدفق الحر", "Free Cash Flow",
        "Operating Cash Flow − |Capital Expenditure|", ("operating_cash_flow", "capex"),
        "النقد المتاح بعد الاستثمار — مشتق دائمًا (لا يُقرأ من المطبوع)",
        "مشتق من تدفقات السنة", "لا ينطبق", "عملة", 0, "لا ينطبق (فرق)",
        "السالب = استهلاك نقدي استثماري", _H, "Cash Flow", "test_pipeline",
        "documented"),
    MetricEntry("fcf_margin", "هامش التدفق الحر", "FCF Margin",
        "Free Cash Flow / Revenue × 100", ("free_cash_flow", "revenue"),
        "التدفق الحر لكل جنيه إيراد", "مشتق", "لا ينطبق", "%", 2, _ZD,
        "السالب = حرق استثماري", _H, "Cash Flow", "test_pipeline", "documented"),
    MetricEntry("cfo_to_net_income", "التدفق التشغيلي / صافي الربح", "CFO to Net Income",
        "Operating Cash Flow / Net Income", ("operating_cash_flow", "net_income"),
        "جودة الأرباح: هل الربح تحول لنقد", "تدفق السنة", "لا ينطبق",
        "x", 2, "صافي صفر → N/A", "أقل من 1 = أرباح لم تتحول نقدًا", _H,
        "Cash Flow", "test_metric_registry", "validated"),
    MetricEntry("cfo_to_debt", "التدفق التشغيلي / إجمالي الدين", "CFO to Total Debt",
        "Operating Cash Flow / Total Debt (Interest-Bearing)",
        ("operating_cash_flow", "total_debt"),
        "سنوات سداد الدين من التشغيل — التعريف: الدين ذو الفائدة فقط",
        "تدفق السنة / أرصدة نهاية الفترة", "لا ينطبق", "x", 2,
        "دين صفر → N/A (لا دين)؛ صفر مطلق → N/A", _NEG_KEEP, _H, "Cash Flow",
        "test_debt_mapping", "validated"),
    MetricEntry("capex_coverage", "تغطية الإنفاق الرأسمالي", "CapEx Coverage",
        "Operating Cash Flow / |Capital Expenditure|", ("operating_cash_flow", "capex"),
        "قدرة التشغيل على تمويل الاستثمار", "تدفق السنة", "لا ينطبق",
        "x", 2, "لا إنفاق → N/A (ليس ضعفًا)", "أقل من 1 = تمويل خارجي للاستثمار",
        _H, "Cash Flow", "test_pipeline", "documented"),

    # ── Cost Structure (بنية التكاليف) ──
    MetricEntry("cogs_pct", "تكلفة المبيعات / الإيراد", "COGS % of Revenue",
        "|Cost of Revenue| / Revenue × 100", ("cost_of_revenue", "revenue"),
        "حصة تكلفة المبيعات", "تدفقات السنة", "لا ينطبق", "%", 2, _ZD,
        _NEG_ABS, _L, "Cost Structure", "test_pipeline", "documented"),
    MetricEntry("opex_pct", "المصروفات التشغيلية / الإيراد", "OpEx % of Revenue",
        "|Operating Expenses| / Revenue × 100", ("operating_expenses", "revenue"),
        "حصة المصروفات التشغيلية", "تدفقات السنة", "لا ينطبق", "%", 2, _ZD,
        _NEG_ABS, _L, "Cost Structure", "test_pipeline", "documented"),
    MetricEntry("selling_pct", "مصروفات البيع والتسويق / الإيراد", "Selling % of Revenue",
        "|Selling Expenses| / Revenue × 100", ("selling_expenses", "revenue"),
        "حصة البيع والتسويق", "تدفقات السنة", "لا ينطبق", "%", 2, _ZD,
        _NEG_ABS, _L, "Cost Structure", "test_pipeline", "documented"),
    MetricEntry("rd_pct", "البحث والتطوير / الإيراد", "R&D % of Revenue",
        "|R&D Expenses| / Revenue × 100", ("rd_expenses", "revenue"),
        "حصة البحث والتطوير", "تدفقات السنة", "لا ينطبق", "%", 2, _ZD,
        _NEG_ABS, _N, "Cost Structure", "test_pipeline",
        "documented"),
    MetricEntry("interest_pct", "صافي التكاليف التمويلية / الإيراد",
        "Net Financing Costs % of Revenue", "|Interest Expense| / Revenue × 100",
        ("interest_expense", "revenue"),
        "حصة التمويل — في وثيقة 2022 يُطبع صافي التكاليف التمويلية (بعد الفوائد الدائنة)",
        "تدفقات السنة", "لا ينطبق", "%", 2, _ZD, _NEG_ABS, _L,
        "Cost Structure", "test_pipeline", "documented"),
    MetricEntry("da_pct", "الإهلاك / الإيراد", "D&A % of Revenue",
        "|D&A| / Revenue × 100", ("depreciation_amortization", "revenue"),
        "حصة الإهلاك", "تدفقات السنة", "لا ينطبق", "%", 2, _ZD, _NEG_ABS,
        _N, "Cost Structure", "test_pipeline", "documented"),
    MetricEntry("tax_rate", "معدل الضريبة الفعلي", "Effective Tax Rate",
        "|Income Tax Expense| / Pretax Income × 100",
        ("income_tax_expense", "pretax_income"),
        "معدل الضريبة الفعلي", "تدفقات السنة", "لا ينطبق", "%", 2,
        "ربح قبل ضريبة صفر/سالب → N/A", "معدل سالب = فائض ضريبي", _N,
        "Cost Structure", "test_pipeline", "documented"),
]

# الحقول الجوهرية السبعة التي يدققها التدقيق البشري (مرجع الحاكمية)
CORE_AUDIT_FIELDS = (
    "revenue", "net_income", "pretax_income", "income_tax_expense",
    "total_assets", "total_liabilities", "equity",
)


def registry_stats() -> dict:
    return {
        "total": len(REGISTRY),
        "validated": sum(1 for m in REGISTRY if m.validation_status == "validated"),
        "documented": sum(1 for m in REGISTRY if m.validation_status == "documented"),
        "categories": sorted({m.category for m in REGISTRY}),
    }
