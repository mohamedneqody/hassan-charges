"""Deterministic financial calculations.

ALL numbers here are computed in Python. The AI agent only interprets them.
Missing inputs yield None — never an invented number. Average-balance metrics
fall back to the current-year balance with an explanatory note.
"""
from __future__ import annotations

from dataclasses import dataclass, field


def safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _pct(numerator: float | None, denominator: float | None) -> float | None:
    result = safe_div(numerator, denominator)
    return None if result is None else result * 100


def growth_pct(previous: float | None, current: float | None) -> float | None:
    """Year-over-year growth in percent. None when the base is missing,
    zero, or negative (a negative base makes growth meaningless)."""
    if previous is None or current is None or previous <= 0:
        return None
    return (current - previous) / previous * 100


@dataclass
class YearMetrics:
    """Every value/ratio for one fiscal year. None = data unavailable."""
    year: int
    # Income statement (absolute)
    revenue: float | None = None
    cost_of_revenue: float | None = None
    gross_profit: float | None = None
    operating_expenses: float | None = None
    operating_income: float | None = None
    pretax_income: float | None = None
    income_tax_expense: float | None = None
    net_income: float | None = None
    depreciation_amortization: float | None = None
    selling_expenses: float | None = None
    admin_expenses: float | None = None
    other_operating_expenses: float | None = None
    rd_expenses: float | None = None
    interest_expense: float | None = None
    ebitda: float | None = None
    # Balance sheet (absolute)
    total_assets: float | None = None
    current_assets: float | None = None
    inventory: float | None = None
    accounts_receivable: float | None = None
    cash: float | None = None
    fixed_assets: float | None = None
    accounts_payable: float | None = None
    current_liabilities: float | None = None
    total_liabilities: float | None = None
    total_debt: float | None = None
    short_term_debt: float | None = None
    long_term_debt: float | None = None
    current_portion_lt_debt: float | None = None
    # إصلاح حديد عز: حقول كانسية مستقلة (التدقيق الجنائي — D/E 0.08x→0.83x)
    short_term_credit_facilities: float | None = None
    bank_overdraft: float | None = None
    current_lease_liabilities: float | None = None
    non_current_lease_liabilities: float | None = None
    equity: float | None = None
    retained_earnings: float | None = None
    working_capital: float | None = None
    operating_working_capital: float | None = None
    # Cash flow (absolute)
    operating_cash_flow: float | None = None
    investing_cash_flow: float | None = None
    financing_cash_flow: float | None = None
    capex: float | None = None
    free_cash_flow: float | None = None
    # Ratios — profitability (percent)
    gross_margin: float | None = None
    operating_margin: float | None = None
    ebitda_margin: float | None = None
    pretax_margin: float | None = None
    net_margin: float | None = None
    roa: float | None = None
    roe: float | None = None
    roic: float | None = None
    roce: float | None = None
    # Ratios — liquidity
    current_ratio: float | None = None
    quick_ratio: float | None = None
    cash_ratio: float | None = None
    ocf_ratio: float | None = None
    # Ratios — leverage
    debt_to_equity: float | None = None
    debt_ratio: float | None = None
    debt_to_assets: float | None = None
    liabilities_to_equity: float | None = None
    equity_ratio: float | None = None
    financial_leverage: float | None = None
    interest_coverage: float | None = None
    # Ratios — efficiency (x) and days
    asset_turnover: float | None = None
    fixed_asset_turnover: float | None = None
    inventory_turnover: float | None = None
    receivables_turnover: float | None = None
    payables_turnover: float | None = None
    working_capital_turnover: float | None = None
    inventory_days: float | None = None
    days_sales_outstanding: float | None = None
    days_payables_outstanding: float | None = None
    cash_conversion_cycle: float | None = None
    # Cash flow ratios
    cfo_margin: float | None = None
    fcf_margin: float | None = None
    cfo_to_net_income: float | None = None
    cfo_to_debt: float | None = None
    capex_coverage: float | None = None
    cash_roa: float | None = None
    # Cost structure (percent)
    cogs_pct: float | None = None
    opex_pct: float | None = None
    selling_pct: float | None = None
    rd_pct: float | None = None
    interest_pct: float | None = None
    da_pct: float | None = None
    tax_rate: float | None = None
    # Metadata: notes like "ROA used current-year assets only"
    notes: dict[str, str] = field(default_factory=dict)


def compute_year_metrics(
    year: int,
    data: dict[str, dict[int, float]],
    prev_year: int | None = None,
) -> YearMetrics:
    """Compute all metrics for `year` from canonical values.

    `prev_year` enables average-balance ratios when the previous year's
    balance sheet is available.
    """

    def get(field_name: str, y: int = year) -> float | None:
        return data.get(field_name, {}).get(y)

    def avg(field_name: str) -> float | None:
        """Average of current and previous balance when both exist."""
        cur = get(field_name)
        if cur is None:
            return None
        prev = get(field_name, prev_year) if prev_year else None
        return (prev + cur) / 2 if prev is not None else cur

    def note_fallback(key: str, label: str) -> None:
        if prev_year is not None:
            m.notes[key] = (
                f"Average {label} unavailable for {prev_year}; "
                f"computed on the {year} balance."
            )

    m = YearMetrics(year=year)
    # --- Absolutes from the source ---
    m.revenue = get("revenue")
    m.cost_of_revenue = get("cost_of_revenue")
    m.gross_profit = get("gross_profit")
    m.operating_expenses = get("operating_expenses")
    m.operating_income = (
        get("operating_income")
        if get("operating_income") is not None
        else get("net_activity_profit")
    )
    m.pretax_income = get("pretax_income")
    m.income_tax_expense = get("income_tax_expense")
    m.net_income = get("net_income")
    m.depreciation_amortization = get("depreciation_amortization")
    m.selling_expenses = get("selling_expenses")
    m.admin_expenses = get("admin_expenses")
    m.other_operating_expenses = get("other_operating_expenses")
    m.rd_expenses = get("rd_expenses")
    m.interest_expense = get("interest_expense")
    m.total_assets = get("total_assets")
    m.current_assets = get("current_assets")
    m.inventory = get("inventory")
    m.accounts_receivable = get("accounts_receivable")
    m.cash = get("cash")
    m.fixed_assets = get("fixed_assets")
    m.accounts_payable = get("accounts_payable")
    m.current_liabilities = get("current_liabilities")
    m.total_liabilities = get("total_liabilities")
    m.total_debt = get("total_debt")
    m.short_term_debt = get("short_term_debt")
    m.long_term_debt = get("long_term_debt")
    m.current_portion_lt_debt = get("current_portion_lt_debt")
    m.short_term_credit_facilities = get("short_term_credit_facilities")
    m.bank_overdraft = get("bank_overdraft")
    m.current_lease_liabilities = get("current_lease_liabilities")
    m.non_current_lease_liabilities = get("non_current_lease_liabilities")
    m.equity = get("equity")
    m.retained_earnings = get("retained_earnings")
    m.operating_cash_flow = get("operating_cash_flow")
    m.investing_cash_flow = get("investing_cash_flow")
    m.financing_cash_flow = get("financing_cash_flow")
    m.capex = get("capex")

    # --- Derived absolutes (only when not stated in the source) ---
    # Expenses are sometimes stored as negatives in the source — use magnitudes.
    if m.gross_profit is None and m.revenue is not None and m.cost_of_revenue is not None:
        m.gross_profit = m.revenue - abs(m.cost_of_revenue)
        m.notes["gross_profit"] = "Derived as Revenue - Cost of Revenue."
    if m.operating_income is None and m.gross_profit is not None and m.operating_expenses is not None:
        m.operating_income = m.gross_profit - abs(m.operating_expenses)
        m.notes["operating_income"] = "Derived as Gross Profit - Operating Expenses."
    if m.operating_expenses is None and m.selling_expenses is not None and m.admin_expenses is not None:
        m.operating_expenses = (
            abs(m.selling_expenses)
            + abs(m.admin_expenses)
            + abs(m.other_operating_expenses or 0.0)
        )
        m.notes["operating_expenses"] = (
            "Derived as Selling + General & Administrative"
            + (" + Other Operating Expenses." if m.other_operating_expenses is not None else ".")
        )
    elif m.operating_expenses is None and m.gross_profit is not None and m.operating_income is not None:
        m.operating_expenses = m.gross_profit - m.operating_income
        m.notes["operating_expenses"] = "Derived as Gross Profit - Operating Income."
    if m.total_debt is None and any(
        x is not None for x in (m.short_term_debt, m.current_portion_lt_debt,
                                m.long_term_debt,
                                m.short_term_credit_facilities,
                                m.bank_overdraft,
                                m.current_lease_liabilities,
                                m.non_current_lease_liabilities)
    ):
        # إصلاح حديد عز (التدقيق الجنائي): إجمالي الدين = القروض طويلة الأجل
        # + الأقساط الجارية + التسهيلات الائتمانية البنكية + السحب على
        # المكشوف + التزامات التأجير التمويلي (طويلة وقصيرة).
        # حديد عز 2021: 3,915,952,409 (تسهيلات) + 2,655,419 (مكشوف) + الباقي
        # = 5,252,833,283 ج.م بالإيضاح 32-2 — النظام كان يخرج 0.08x بدل 0.83x.
        parts = [abs(x) for x in (
            m.short_term_debt, m.current_portion_lt_debt, m.long_term_debt,
            m.short_term_credit_facilities, m.bank_overdraft,
            m.current_lease_liabilities, m.non_current_lease_liabilities,
        ) if x is not None]
        m.total_debt = sum(parts)
        m.notes["total_debt"] = (
            "إجمالي الدين (المديونية الفعلية) = القروض طويلة الأجل + الأقساط "
            "الجارية + التسهيلات الائتمانية البنكية + السحب على المكشوف + "
            "التزامات التأجير التمويلي (طويلة وقصيرة).")
    if m.ebitda is None and m.operating_income is not None and m.depreciation_amortization is not None:
        m.ebitda = m.operating_income + abs(m.depreciation_amortization)
        m.notes["ebitda"] = "Derived as Operating Income + D&A."
    if m.operating_cash_flow is not None and m.capex is not None:
        m.free_cash_flow = m.operating_cash_flow - abs(m.capex)
        m.notes["free_cash_flow"] = "Derived as Operating Cash Flow - Capital Expenditure."
    if m.current_assets is not None and m.current_liabilities is not None:
        m.working_capital = m.current_assets - m.current_liabilities
    if None not in (m.accounts_receivable, m.inventory, m.accounts_payable):
        m.operating_working_capital = (
            m.accounts_receivable + m.inventory - m.accounts_payable
        )
        m.notes["operating_working_capital"] = (
            "Derived as Accounts Receivable + Inventory - Accounts Payable."
        )

    # --- Profitability (percent) ---
    m.gross_margin = _pct(m.gross_profit, m.revenue)
    m.operating_margin = _pct(m.operating_income, m.revenue)
    m.ebitda_margin = _pct(m.ebitda, m.revenue)
    m.pretax_margin = _pct(m.pretax_income, m.revenue)
    m.net_margin = _pct(m.net_income, m.revenue)

    # --- Returns on average balances ---
    m.roa = _pct(m.net_income, avg("total_assets"))
    if m.roa is not None:
        m.notes["roa"] = (
            f"ROA computed on average total assets ({prev_year} & {year})."
            if prev_year is not None and get("total_assets", prev_year) is not None
            else f"Average assets unavailable for {prev_year}; ROA computed on {year} total assets."
        )

    m.roe = _pct(m.net_income, avg("equity"))
    if m.roe is not None:
        m.notes["roe"] = (
            f"ROE computed on average equity ({prev_year} & {year})."
            if prev_year is not None and get("equity", prev_year) is not None
            else f"Average equity unavailable for {prev_year}; ROE computed on {year} equity."
        )

    # ROIC = EBIT x (1 - effective tax rate) / (Total Debt + Equity)
    if None not in (m.pretax_income, m.income_tax_expense, m.operating_income, m.total_debt, m.equity):
        if m.pretax_income > 0:
            rate = abs(m.income_tax_expense) / m.pretax_income
            nopat = m.operating_income * (1 - rate)
            invested_capital = m.total_debt + m.equity
            m.roic = safe_div(nopat, invested_capital) * 100 if invested_capital != 0 else None
            m.notes["roic"] = (
                f"ROIC computed as EBIT x (1 - effective tax rate {rate:.1%}) / "
                f"(Total Debt + Equity)."
            )
    # ROCE = EBIT / Capital Employed (Total Assets - Current Liabilities)
    if m.total_assets is not None and m.current_liabilities is not None:
        capital_employed = m.total_assets - m.current_liabilities
        m.roce = _pct(m.operating_income, capital_employed) if capital_employed > 0 else None

    # --- Liquidity ---
    m.current_ratio = safe_div(m.current_assets, m.current_liabilities)
    if m.current_assets is not None and m.current_liabilities is not None:
        # Quick assets = current assets minus inventory. Without an inventory
        # figure the ratio would silently equal the current ratio, so it stays N/A.
        if m.inventory is not None:
            m.quick_ratio = safe_div(m.current_assets - m.inventory, m.current_liabilities)
    m.cash_ratio = safe_div(m.cash, m.current_liabilities)
    m.ocf_ratio = safe_div(m.operating_cash_flow, m.current_liabilities)

    # --- Leverage ---
    m.debt_to_equity = safe_div(m.total_debt, m.equity)
    m.debt_ratio = safe_div(m.total_liabilities, m.total_assets)
    m.debt_to_assets = safe_div(m.total_debt, m.total_assets)
    m.liabilities_to_equity = safe_div(m.total_liabilities, m.equity)
    m.equity_ratio = safe_div(m.equity, m.total_assets)
    m.financial_leverage = safe_div(m.total_assets, m.equity)
    m.interest_coverage = safe_div(m.operating_income, abs(m.interest_expense) if m.interest_expense is not None else None)

    # --- Efficiency: turnovers (average balances with fallback) ---
    cogs_abs = abs(m.cost_of_revenue) if m.cost_of_revenue is not None else None
    m.asset_turnover = safe_div(m.revenue, avg("total_assets"))
    if m.asset_turnover is not None and (prev_year is None or get("total_assets", prev_year) is None):
        note_fallback("asset_turnover", "total assets")
    m.fixed_asset_turnover = safe_div(m.revenue, avg("fixed_assets"))
    if m.fixed_asset_turnover is not None and (prev_year is None or get("fixed_assets", prev_year) is None):
        note_fallback("fixed_asset_turnover", "fixed assets")
    m.inventory_turnover = safe_div(cogs_abs, avg("inventory"))
    if m.inventory_turnover is not None and (prev_year is None or get("inventory", prev_year) is None):
        note_fallback("inventory_turnover", "inventory")
    m.receivables_turnover = safe_div(m.revenue, avg("accounts_receivable"))
    if m.receivables_turnover is not None and (prev_year is None or get("accounts_receivable", prev_year) is None):
        note_fallback("receivables_turnover", "accounts receivable")
    m.payables_turnover = safe_div(cogs_abs, avg("accounts_payable"))
    if m.payables_turnover is not None and (prev_year is None or get("accounts_payable", prev_year) is None):
        note_fallback("payables_turnover", "accounts payable")

    # --- Working capital turnover (average WC from both years' CA/CL) ---
    if m.revenue is not None and m.working_capital is not None and m.working_capital != 0:
        prev_wc = None
        if prev_year is not None:
            ca_p = get("current_assets", prev_year)
            cl_p = get("current_liabilities", prev_year)
            if ca_p is not None and cl_p is not None:
                prev_wc = ca_p - cl_p
        base = (prev_wc + m.working_capital) / 2 if prev_wc is not None else m.working_capital
        m.working_capital_turnover = safe_div(m.revenue, base)

    # --- Days metrics (365-day convention) ---
    if m.inventory_turnover:
        m.inventory_days = 365 / m.inventory_turnover
    if m.receivables_turnover:
        m.days_sales_outstanding = 365 / m.receivables_turnover
    if m.payables_turnover:
        m.days_payables_outstanding = 365 / m.payables_turnover
    if None not in (m.inventory_days, m.days_sales_outstanding, m.days_payables_outstanding):
        m.cash_conversion_cycle = (
            m.inventory_days + m.days_sales_outstanding - m.days_payables_outstanding
        )

    # --- Cash flow ratios ---
    m.cfo_margin = _pct(m.operating_cash_flow, m.revenue)
    m.fcf_margin = _pct(m.free_cash_flow, m.revenue)
    m.cfo_to_net_income = safe_div(m.operating_cash_flow, m.net_income)
    m.cfo_to_debt = safe_div(m.operating_cash_flow, m.total_debt)
    m.capex_coverage = (
        safe_div(m.operating_cash_flow, abs(m.capex)) if m.capex else None
    )
    m.cash_roa = _pct(m.operating_cash_flow, avg("total_assets"))

    # --- Cost structure (percent of revenue / effective tax rate) ---
    m.cogs_pct = _pct(cogs_abs, m.revenue)
    m.opex_pct = _pct(abs(m.operating_expenses) if m.operating_expenses is not None else None, m.revenue)
    m.selling_pct = _pct(abs(m.selling_expenses) if m.selling_expenses is not None else None, m.revenue)
    m.rd_pct = _pct(abs(m.rd_expenses) if m.rd_expenses is not None else None, m.revenue)
    m.interest_pct = _pct(abs(m.interest_expense) if m.interest_expense is not None else None, m.revenue)
    m.da_pct = _pct(abs(m.depreciation_amortization) if m.depreciation_amortization is not None else None, m.revenue)
    m.tax_rate = _pct(abs(m.income_tax_expense) if m.income_tax_expense is not None else None, m.pretax_income)
    # المهمة 6: ميّز المنفعة الضريبية عن المصروف — some statements print a
    # tax CREDIT (TE 2024: +1,272,749 added back: NI = pretax + credit) while
    # others print an expense. The rate number stays, but its MEANING is
    # recorded so the report never calls a benefit an expense rate.
    if m.tax_rate is not None and m.net_income is not None             and m.pretax_income not in (None, 0):
        if m.net_income > m.pretax_income:
            m.notes["tax_rate"] = (
                "Effective tax BENEFIT rate — the tax line increased profit "
                "(credit), not an expense.")
        else:
            m.notes["tax_rate"] = "Effective tax expense rate."
    return m
