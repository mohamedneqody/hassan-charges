"""Two-year comparison: metric rows, changes, status and trend detection."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.analysis.calculator import YearMetrics, growth_pct
from src.config import STABLE_TREND_THRESHOLD

# Possible trend/status values
IMPROVING, DECLINING, STABLE, NOT_AVAILABLE = "Improving", "Declining", "Stable", "N/A"
POSITIVE, NEGATIVE, NEUTRAL = "Positive", "Negative", "Neutral"

CURRENCY, PERCENT, RATIO, DAYS = "currency", "percent", "ratio", "days"


@dataclass
class MetricRow:
    key: str
    label: str
    label_ar: str
    category: str
    kind: str  # currency | percent | ratio
    higher_is_better: bool | None  # None = محايد الاتجاه (إصلاح 7)
    previous: float | None
    current: float | None
    change: float | None
    change_pct: float | None
    status: str
    trend: str
    reason: str = ""  # why a value is N/A
    turnaround: bool = False  # إصلاح 7: سالب أساس → موجب حالي

    @property
    def trend_symbol(self) -> str:
        return {IMPROVING: "▲", DECLINING: "▼", STABLE: "→"}.get(self.trend, "–")


def _relative_change(previous: float | None, current: float | None) -> float | None:
    """Percent change robust to a negative base (uses |previous|)."""
    if previous is None or current is None or previous == 0:
        return None
    return (current - previous) / abs(previous) * 100


def _classify(
    change: float | None,
    change_pct: float | None,
    higher_is_better: bool | None,
) -> tuple[str, str]:
    """Return (status, trend) for a metric row.

    v6 إصلاح حديد عز (إصلاح 7 — polarity): higher_is_better=None مؤشر
    محايد الاتجاه — زيادة التدفق الاستثماري الخارج ليست "تحسنًا" وسداد
    التمويليات ليست "تراجعًا"؛ Gemini وصفهما بالعكس فتناقضت الواجهة.
    المحايد لا يقيَّم اتجاهيًا إطلاقًا.
    """
    if change is None:
        return NOT_AVAILABLE, NOT_AVAILABLE
    if higher_is_better is None:
        return NEUTRAL, STABLE
    if change == 0 or (change_pct is not None and abs(change_pct) < STABLE_TREND_THRESHOLD):
        return NEUTRAL, STABLE
    improving = (change > 0) == higher_is_better
    return (POSITIVE, IMPROVING) if improving else (NEGATIVE, DECLINING)


def _row(
    spec_key: str,
    label: str,
    category: str,
    kind: str,
    higher_is_better: bool,
    prev: YearMetrics,
    curr: YearMetrics,
    getter,
    reason: str = "",
) -> MetricRow:
    previous = getter(prev)
    current = getter(curr)
    if previous is None and current is None:
        reason = reason or f"{label} data unavailable."
    elif current is None:
        reason = reason or f"{label} unavailable for {curr.year}."
    elif previous is None:
        reason = reason or f"{label} unavailable for {prev.year}."

    change = None if (previous is None or current is None) else current - previous
    change_pct = _relative_change(previous, current) if change is not None else None
    status, trend = _classify(change, change_pct, higher_is_better)
    # v6 إصلاح 7: وسم التحول للربحية — سالب في سنة الأساس وموجب في الحالية
    # (حديد عز: صافي الربح -563.67م → +288.15م): نسبة التغير وحدها مضللة
    # دون وسم انقلاب الإشارة.
    turnaround = bool(
        kind == CURRENCY and previous is not None and current is not None
        and previous < 0 < current
    )
    if turnaround:
        reason = (reason + " | " if reason else "") +             "تحول للربحية — انقلاب الإشارة من سالب في سنة الأساس إلى موجب."
    return MetricRow(
        key=spec_key, label=label, label_ar=LABELS_AR.get(spec_key, label),
        category=category, kind=kind,
        higher_is_better=higher_is_better,
        previous=previous, current=current,
        change=change, change_pct=change_pct,
        status=status, trend=trend, reason=reason, turnaround=turnaround,
    )


# Metric definitions: (key, label, category, kind, higher_is_better, getter)
_METRIC_SPECS = [
    # Growth & Income (absolute currency rows)
    ("revenue", "Revenue", "Growth & Income", CURRENCY, True, lambda m: m.revenue),
    ("gross_profit", "Gross Profit", "Growth & Income", CURRENCY, True, lambda m: m.gross_profit),
    ("operating_income", "Operating Income", "Growth & Income", CURRENCY, True, lambda m: m.operating_income),
    ("net_income", "Net Income", "Growth & Income", CURRENCY, True, lambda m: m.net_income),
    ("free_cash_flow", "Free Cash Flow", "Growth & Income", CURRENCY, True, lambda m: m.free_cash_flow),
    # Profitability
    ("gross_margin", "Gross Profit Margin", "Profitability", PERCENT, True, lambda m: m.gross_margin),
    ("operating_margin", "Operating Margin", "Profitability", PERCENT, True, lambda m: m.operating_margin),
    ("ebitda_margin", "EBITDA Margin", "Profitability", PERCENT, True, lambda m: m.ebitda_margin),
    ("pretax_margin", "Pretax Profit Margin", "Profitability", PERCENT, True, lambda m: m.pretax_margin),
    ("net_margin", "Net Profit Margin", "Profitability", PERCENT, True, lambda m: m.net_margin),
    ("roa", "Return on Assets (ROA)", "Profitability", PERCENT, True, lambda m: m.roa),
    ("roe", "Return on Equity (ROE)", "Profitability", PERCENT, True, lambda m: m.roe),
    ("roic", "ROIC", "Profitability", PERCENT, True, lambda m: m.roic),
    ("roce", "ROCE", "Profitability", PERCENT, True, lambda m: m.roce),
    # Liquidity
    ("current_ratio", "Current Ratio", "Liquidity", RATIO, True, lambda m: m.current_ratio),
    ("quick_ratio", "Quick Ratio", "Liquidity", RATIO, True, lambda m: m.quick_ratio),
    ("cash_ratio", "Cash Ratio", "Liquidity", RATIO, True, lambda m: m.cash_ratio),
    ("ocf_ratio", "Operating Cash Flow Ratio", "Liquidity", RATIO, True, lambda m: m.ocf_ratio),
    # Leverage
    ("debt_to_equity", "Debt to Equity", "Leverage", RATIO, False, lambda m: m.debt_to_equity),
    ("debt_ratio", "Debt Ratio (Liabilities / Assets)", "Leverage", RATIO, False, lambda m: m.debt_ratio),
    ("debt_to_assets", "Debt to Assets", "Leverage", RATIO, False, lambda m: m.debt_to_assets),
    ("liabilities_to_equity", "Liabilities to Equity", "Leverage", RATIO, False, lambda m: m.liabilities_to_equity),
    ("equity_ratio", "Equity Ratio", "Leverage", RATIO, True, lambda m: m.equity_ratio),
    ("financial_leverage", "Financial Leverage", "Leverage", RATIO, False, lambda m: m.financial_leverage),
    ("interest_coverage", "Interest Coverage", "Leverage", RATIO, True, lambda m: m.interest_coverage),
    # Efficiency
    ("asset_turnover", "Asset Turnover", "Efficiency", RATIO, True, lambda m: m.asset_turnover),
    ("fixed_asset_turnover", "Fixed Asset Turnover", "Efficiency", RATIO, True, lambda m: m.fixed_asset_turnover),
    ("inventory_turnover", "Inventory Turnover", "Efficiency", RATIO, True, lambda m: m.inventory_turnover),
    ("receivables_turnover", "Receivables Turnover", "Efficiency", RATIO, True, lambda m: m.receivables_turnover),
    ("payables_turnover", "Payables Turnover", "Efficiency", RATIO, True, lambda m: m.payables_turnover),
    # Days
    ("inventory_days", "DIO — Inventory Days", "Days", DAYS, False, lambda m: m.inventory_days),
    ("days_sales_outstanding", "DSO — Days Sales Outstanding", "Days", DAYS, False, lambda m: m.days_sales_outstanding),
    ("days_payables_outstanding", "DPO — Days Payables Outstanding", "Days", DAYS, True, lambda m: m.days_payables_outstanding),
    ("cash_conversion_cycle", "Cash Conversion Cycle", "Days", DAYS, False, lambda m: m.cash_conversion_cycle),
    # Working capital
    ("working_capital", "Working Capital", "Working Capital", CURRENCY, True, lambda m: m.working_capital),
    ("operating_working_capital", "Operating Working Capital", "Working Capital", CURRENCY, True, lambda m: m.operating_working_capital),
    ("working_capital_turnover", "Working Capital Turnover", "Working Capital", RATIO, True, lambda m: m.working_capital_turnover),
    # Cash flow
    ("operating_cash_flow", "Operating Cash Flow", "Cash Flow", CURRENCY, True, lambda m: m.operating_cash_flow),
    # v6 إصلاح 7: polarity محايدة — زيادة الاستثمار سدادًا ليست تحسنًا،
    # وسداد التمويليات ليست تراجعًا (كانت Negative فتناقض مع تفسير Gemini)
    ("investing_cash_flow", "Investing Cash Flow", "Cash Flow", CURRENCY, None, lambda m: m.investing_cash_flow),
    ("financing_cash_flow", "Financing Cash Flow", "Cash Flow", CURRENCY, None, lambda m: m.financing_cash_flow),
    ("cfo_margin", "Operating Cash Flow Margin", "Cash Flow", PERCENT, True, lambda m: m.cfo_margin),
    ("fcf_margin", "Free Cash Flow Margin", "Cash Flow", PERCENT, True, lambda m: m.fcf_margin),
    ("cfo_to_net_income", "Cash Flow to Net Income", "Cash Flow", RATIO, True, lambda m: m.cfo_to_net_income),
    ("cfo_to_debt", "Cash Flow to Debt", "Cash Flow", RATIO, True, lambda m: m.cfo_to_debt),
    ("capex_coverage", "Capex Coverage", "Cash Flow", RATIO, True, lambda m: m.capex_coverage),
    ("cash_roa", "Cash Return on Assets", "Cash Flow", PERCENT, True, lambda m: m.cash_roa),
    # Cost structure
    ("cogs_pct", "COGS as % of Revenue", "Cost Structure", PERCENT, False, lambda m: m.cogs_pct),
    ("opex_pct", "Operating Expenses as % of Revenue", "Cost Structure", PERCENT, False, lambda m: m.opex_pct),
    ("selling_pct", "Selling Expenses as % of Revenue", "Cost Structure", PERCENT, False, lambda m: m.selling_pct),
    ("rd_pct", "R&D as % of Revenue", "Cost Structure", PERCENT, False, lambda m: m.rd_pct),
    ("interest_pct", "Net Financing Costs as % of Revenue", "Cost Structure", PERCENT, False, lambda m: m.interest_pct),
    ("da_pct", "D&A as % of Revenue", "Cost Structure", PERCENT, False, lambda m: m.da_pct),
    ("tax_rate", "Effective Tax Rate", "Cost Structure", PERCENT, False, lambda m: m.tax_rate),
]

# Arabic display labels for every metric key (UI + AI commentary run in Arabic).
LABELS_AR: dict[str, str] = {
    # Canonical statement fields (القوائم والخانات)
    "revenue": "الإيرادات",
    "cost_of_revenue": "تكلفة الإيرادات",
    "gross_profit": "مجمل الربح",
    "operating_expenses": "المصروفات التشغيلية",
    "selling_expenses": "مصاريف البيع والتسويق",
    "admin_expenses": "المصروفات العمومية والإدارية",
    "other_operating_expenses": "مصروفات تشغيل أخرى",
    "other_operating_income": "إيرادات تشغيل أخرى",
    "rd_expenses": "مصاريف البحث والتطوير",
    "operating_income": "الربح التشغيلي",
    "net_activity_profit": "صافي أرباح النشاط",
    "interest_expense": "التكاليف التمويلية والفوائد",
    "dividends_from_subsidiaries": "توزيعات أرباح من شركات تابعة",
    "pretax_income": "الربح قبل ضريبة الدخل",
    "income_tax_expense": "ضريبة الدخل",
    "net_income": "صافي الربح",
    "depreciation_amortization": "الإهلاك والاستهلاك",
    "fixed_assets": "الأصول الثابتة (بالصافي)",
    "projects_under_construction": "مشروعات تحت التنفيذ",
    "investments_in_subsidiaries": "استثمارات في شركات تابعة",
    "other_investments": "استثمارات أخرى",
    "deferred_tax_assets": "أصول ضريبية مؤجلة",
    "non_current_assets": "إجمالي الأصول غير المتداولة",
    "inventory": "المخزون",
    "accounts_receivable": "العملاء وأوراق القبض",
    "other_receivables": "مدينون وأرصدة مدينة أخرى",
    "supplier_advances": "موردون — دفعات مقدمة",
    "cash": "النقدية وما في حكمها",
    "current_assets": "إجمالي الأصول المتداولة",
    "total_assets": "إجمالي الأصول",
    "accounts_payable": "الموردون وأوراق الدفع",
    "customer_advances": "عملاء — دفعات مقدمة",
    "other_payables": "دائنون وأرصدة دائنة أخرى",
    "provisions": "مخصصات",
    "short_term_debt": "قروض وتسهيلات قصيرة الأجل",
    "short_term_credit_facilities": "بنوك — تسهيلات ائتمانية",
    "bank_overdraft": "بنوك — سحب على المكشوف",
    "current_portion_lt_debt": "أقساط قروض طويلة الأجل مستحقة خلال عام",
    "current_lease_liabilities": "التزامات تأجير تمويلي متداولة",
    "current_liabilities": "إجمالي الالتزامات المتداولة",
    "long_term_debt": "قروض طويلة الأجل",
    "long_term_notes_payable": "أوراق دفع طويلة الأجل",
    "non_current_lease_liabilities": "التزامات تأجير تمويلي غير متداولة",
    "deferred_tax_liabilities": "التزامات ضريبية مؤجلة",
    "non_current_liabilities": "إجمالي الالتزامات غير المتداولة",
    "total_liabilities": "إجمالي الالتزامات",
    "total_debt": "إجمالي المديونية",
    "borrowings_excl_leases": "القروض والتسهيلات (باستثناء التأجير)",
    "financial_debt_incl_leases": "المديونية المالية (شاملة التأجير)",
    "capital": "رأس المال المدفوع",
    "treasury_shares": "أسهم خزينة",
    "reserves": "الاحتياطيات",
    "asset_revaluation_reserve": "ناتج تعديل تكلفة الأصول",
    "retained_earnings": "الأرباح المرحلة / المحتجزة",
    "equity": "إجمالي حقوق الملكية",
    "finance_income": "فوائد دائنة",
    "fx_gain_loss": "فروق ترجمة العملات الأجنبية",
    "operating_cash_flow": "صافي التدفق النقدي التشغيلي",
    "investing_cash_flow": "صافي التدفق النقدي الاستثماري",
    "financing_cash_flow": "صافي التدفق النقدي التمويلي",
    "capex": "الإنفاق الرأسمالي (شراء أصول ثابتة)",
    "free_cash_flow": "التدفق النقدي الحر",
    # Calculated ratios & margins (المؤشرات المالية)
    "gross_margin": "هامش مجمل الربح",
    "operating_margin": "هامش الربح التشغيلي",
    "ebitda_margin": "هامش EBITDA",
    "pretax_margin": "هامش الربح قبل الضريبة",
    "net_margin": "هامش صافي الربح",
    "roa": "العائد على الأصول (ROA)",
    "roe": "العائد على حقوق الملكية (ROE)",
    "roic": "العائد على رأس المال المستثمر (ROIC)",
    "roce": "العائد على رأس المال المستخدم (ROCE)",
    "current_ratio": "النسبة الجارية",
    "quick_ratio": "النسبة السريعة",
    "cash_ratio": "نسبة النقدية",
    "ocf_ratio": "نسبة التدفق التشغيلي",
    "debt_to_equity": "الدين إلى حقوق الملكية",
    "debt_ratio": "إجمالي الالتزامات إلى الأصول",
    "debt_to_assets": "الدين إلى الأصول",
    "liabilities_to_equity": "الالتزامات إلى حقوق الملكية",
    "equity_ratio": "نسبة حقوق الملكية",
    "financial_leverage": "الرفع المالي",
    "interest_coverage": "تغطية الفوائد",
    "asset_turnover": "دوران الأصول",
    "fixed_asset_turnover": "دوران الأصول الثابتة",
    "inventory_turnover": "دوران المخزون",
    "receivables_turnover": "دوران الذمم المدينة",
    "payables_turnover": "دوران الذمم الدائنة",
    "inventory_days": "أيام المخزون (DIO)",
    "days_sales_outstanding": "أيام التحصيل (DSO)",
    "days_payables_outstanding": "أيام السداد (DPO)",
    "cash_conversion_cycle": "دورة التحويل النقدي",
    "working_capital": "رأس المال العامل",
    "operating_working_capital": "رأس المال العامل التشغيلي",
    "working_capital_turnover": "دوران رأس المال العامل",
    "cfo_margin": "هامش التدفق التشغيلي",
    "fcf_margin": "هامش التدفق الحر",
    "cfo_to_net_income": "التدفق التشغيلي إلى صافي الربح",
    "cfo_to_debt": "التدفق التشغيلي إلى إجمالي الدين",
    "capex_coverage": "تغطية النفقات الرأسمالية",
    "cash_roa": "العائد النقدي على الأصول",
    "cogs_pct": "تكلفة المبيعات إلى الإيرادات",
    "opex_pct": "المصاريف التشغيلية إلى الإيرادات",
    "selling_pct": "مصاريف البيع إلى الإيرادات",
    "rd_pct": "البحث والتطوير إلى الإيرادات",
    "interest_pct": "التكاليف التمويلية الصافية إلى الإيرادات",
    "da_pct": "الإهلاك إلى الإيرادات",
    "tax_rate": "نسبة الضريبة الفعلية",
}

CATEGORY_AR = {
    "Growth & Income": "النمو والدخل",
    "Profitability": "الربحية",
    "Liquidity": "السيولة",
    "Leverage": "المديونية",
    "Efficiency": "الكفاءة",
    "Days": "الأيام",
    "Working Capital": "رأس المال العامل",
    "Cash Flow": "التدفق النقدي",
    "Cost Structure": "هيكل التكاليف",
}

STATUS_AR = {"Positive": "إيجابي", "Negative": "سلبي", "Neutral": "محايد", "N/A": "غير متاح"}
TREND_AR = {"Improving": "تحسّن", "Declining": "تراجع", "Stable": "مستقر", "N/A": "—"}
GROWTH_LABELS_AR = {
    "revenue_growth": "نمو الإيرادات",
    "gross_profit_growth": "نمو مجمل الربح",
    "operating_income_growth": "نمو الربح التشغيلي",
    "net_profit_growth": "نمو صافي الربح",
    "assets_growth": "نمو الأصول",
    "equity_growth": "نمو حقوق الملكية",
    "cfo_growth": "نمو التدفق التشغيلي",
}


def build_comparison(prev: YearMetrics, curr: YearMetrics) -> list[MetricRow]:
    """Build all metric rows for previous vs current year."""
    rows = [
        _row(key, label, category, kind, hib, prev, curr, getter)
        for key, label, category, kind, hib, getter in _METRIC_SPECS
    ]
    for row in rows:
        if row.key == "quick_ratio" and row.status == NOT_AVAILABLE:
            row.reason = (
                "Quick Ratio requires Inventory data to exclude it from quick "
                "assets — inventory was not found in the file."
            )
    return rows


def growth_metrics(
    prev: YearMetrics, curr: YearMetrics
) -> list[MetricRow]:
    """Year-over-year growth rates (single values spanning both years)."""
    specs = [
        ("revenue_growth", "Revenue Growth", lambda m: m.revenue),
        ("gross_profit_growth", "Gross Profit Growth", lambda m: m.gross_profit),
        ("operating_income_growth", "Operating Income Growth", lambda m: m.operating_income),
        ("net_profit_growth", "Net Profit Growth", lambda m: m.net_income),
        ("assets_growth", "Assets Growth", lambda m: m.total_assets),
        ("equity_growth", "Equity Growth", lambda m: m.equity),
        ("cfo_growth", "Operating Cash Flow Growth", lambda m: m.operating_cash_flow),
    ]
    rows = []
    for key, label, getter in specs:
        value = growth_pct(getter(prev), getter(curr))
        reason = ""
        if value is None:
            prev_v, curr_v = getter(prev), getter(curr)
            if prev_v is None or curr_v is None:
                reason = f"{label.replace(' Growth', '')} data unavailable."
            else:
                reason = "Previous-year base is zero or negative."
        rows.append(
            MetricRow(
                key=key, label=label, label_ar=GROWTH_LABELS_AR.get(key, label),
                category="Growth & Income", kind=PERCENT,
                higher_is_better=True, previous=None, current=value,
                change=None, change_pct=None,
                status=POSITIVE if (value or 0) > 0 else (NEGATIVE if (value or 0) < 0 else NEUTRAL),
                trend=IMPROVING if (value or 0) > 0 else (DECLINING if (value or 0) < 0 else STABLE),
                reason=reason,
            )
        )
    return rows


def comparison_dataframe(rows: list[MetricRow], prev_year: int, curr_year: int) -> pd.DataFrame:
    """Tabular view: Metric | <prev> | <curr> | Change | Change % | Status | Trend."""
    records = []
    for r in rows:
        records.append(
            {
                "Category": r.category,
                "Metric": r.label,
                str(prev_year): r.previous,
                str(curr_year): r.current,
                "Change": r.change,
                "Change %": r.change_pct,
                "Status": r.status,
                "Trend": f"{r.trend_symbol} {r.trend}" if r.trend != NOT_AVAILABLE else NOT_AVAILABLE,
            }
        )
    return pd.DataFrame(records)


def missing_data_report(
    rows: list[MetricRow],
    metrics_by_year: dict[int, object] | None = None,
) -> list[str]:
    """Human-readable list of what could not be computed and WHY —
    v6 إصلاح حديد عز (إصلاح 3): السبب يُشتق برمجيًا من مدخلات المؤشر
    الفعلية (metric_registry.required_inputs مقابل قيم السنة) بدل النصوص
    الثابتة التي كانت تتهم المخزون بالغياب بينما المفقود فعليًا هو
    current_assets (حالة Quick Ratio).
    """
    from src.analysis.metric_registry import REGISTRY

    inputs_by_key = {e.metric_id: e.required_inputs
                     for e in REGISTRY}
    field_ar = {
        "current_assets": "الأصول المتداولة", "cash": "النقدية",
        "inventory": "المخزون", "accounts_receivable": "الذمم المدينة",
        "current_liabilities": "الالتزامات المتداولة",
        "total_assets": "إجمالي الأصول", "total_liabilities": "إجمالي الالتزامات",
        "equity": "حقوق الملكية", "revenue": "الإيرادات",
        "cost_of_revenue": "تكلفة الإيرادات", "gross_profit": "مجمل الربح",
        "operating_income": "الربح التشغيلي", "net_income": "صافي الربح",
        "operating_cash_flow": "التدفق التشغيلي",
        "investing_cash_flow": "التدفق الاستثماري",
        "financing_cash_flow": "التدفق التمويلي",
        "fixed_assets": "الممتلكات والمعدات", "interest_expense": "مصروف الفوائد",
        "depreciation_amortization": "الإهلاك والاستنزاف",
        "pretax_income": "الربح قبل الضريبة",
        "income_tax_expense": "مصروف ضريبة الدخل",
        "long_term_debt": "القروض طويلة الأجل",
        "current_portion_lt_debt": "الأقساط الجارية للقروض",
        "short_term_debt": "القروض قصيرة الأجل",
        "short_term_credit_facilities": "التسهيلات الائتمانية البنكية",
        "bank_overdraft": "السحب على المكشوف",
        "current_lease_liabilities": "التزامات الإيجار المتداولة",
        "non_current_lease_liabilities": "التزامات الإيجار غير المتداولة",
        "accounts_payable": "الدائنون والمستحقات",
    }

    def _missing_fields(spec_key: str, year: int | None) -> list[str]:
        required = inputs_by_key.get(spec_key)
        if not required or year is None:
            return []
        m = metrics_by_year.get(year) if metrics_by_year else None
        if m is None:
            return []
        missing = [f for f in required if getattr(m, f, None) is None]
        return [f"{field_ar.get(f, f)} ({f})" for f in missing]

    seen: set[str] = set()
    report: list[str] = []
    for r in rows:
        if r.status != NOT_AVAILABLE:
            continue
        year = None
        if metrics_by_year:
            # السنة الحالية أولًا (سبب N/A الواقعي في العرض)
            for y in sorted(metrics_by_year, reverse=True):
                missing = _missing_fields(r.key, y)
                if missing:
                    year = y
                    break
        detail = ""
        if year is not None:
            missing = _missing_fields(r.key, year)
            if missing:
                detail = (f" — المتغير المفقود فعلياً في {year}: "
                          + "، ".join(missing))
        # التسمية الإنجليزية داخل السطر أيضًا (Investing Cash Flow) — الواجهة
        # والاختبارات تعتمد مطابقة المصطلح بلغتيه، والقارئ العربي يرى العربي أولًا.
        line = (f"{r.label_ar or r.label} ({r.label}): غير قابل للحساب{detail}")
        if line in seen:
            continue
        seen.add(line)
        report.append(line)
    return report
