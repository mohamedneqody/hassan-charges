"""Expert-grade red flags (الأعلام الحمراء) — deterministic, zero API calls.

The checks real analysts and auditors run on two consecutive years:

- Earnings quality: net income that never became cash (NI vs CFO divergence).
- Receivables growing far faster than revenue (channel stuffing pattern).
- Inventory piling up faster than sales (demand/obsolescence risk).
- Working capital turning or sinking deeper negative.
- Financing costs eating the operating profit (interest coverage squeeze).
- Beneish M-Score — the classic 8-variable earnings-manipulation model
  (M > −1.78 → pattern worth auditing; −1.78…−2.22 grey zone). Computed only
  when ALL 8 components are available — a partial M would be a guess, and
  this system never guesses.

Every flag carries its numeric evidence, matching the system's rule:
no claim without the numbers that justify it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

SEVERITY_ICON = {"high": "🔴", "medium": "🟡", "low": "🔵"}


@dataclass
class RedFlag:
    name: str
    severity: str  # high | medium | low
    detail: str


@dataclass
class BeneishResult:
    m_score: float | None = None
    verdict: str = ""
    components: dict[str, float] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)

    @property
    def zone(self) -> str:
        if self.m_score is None:
            return ""
        if self.m_score > -1.78:
            return "grey_above"   # pattern worth auditing
        if self.m_score > -2.22:
            return "grey"         # borderline
        return "clean"


def _g(curr: float | None, prev: float | None) -> float | None:
    """Growth rate prev→curr; None unless both exist and prev != 0."""
    if curr is None or prev is None or prev == 0:
        return None
    return (curr - prev) / abs(prev) * 100.0


def _safe_div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def red_flag_analysis(prev, curr) -> list[RedFlag]:
    """Rule-based flags on two YearMetrics. Missing data = silent skip."""
    flags: list[RedFlag] = []

    # 1) Earnings quality: NI that never became cash
    ni, cfo = curr.net_income, curr.operating_cash_flow
    ratio = _safe_div(cfo, ni) if (ni and ni > 0) else None
    if ni and ni > 0 and cfo is not None:
        if cfo < 0:
            flags.append(RedFlag(
                "أرباح بدون نقد", "high",
                f"صافي ربح {ni:,.0f} بينما التدفق النقدي التشغيلي سالب "
                f"({cfo:,.0f}) — الأرباح لم تتحول إلى نقد؛ النمط الكلاسيكي "
                "للأرباح المُدارة أو تحصيل ضعيف.",
            ))
        elif ratio is not None and ratio < 0.2:
            flags.append(RedFlag(
                "فجوة ربح/نقد واسعة", "high",
                f"التدفق التشغيلي يغطي {ratio * 100:.0f}% فقط من صافي الربح "
                f"(الربح {ni:,.0f} مقابل نقد {cfo:,.0f}).",
            ))
        elif ratio is not None and ratio < 0.5:
            flags.append(RedFlag(
                "جودة أرباح متوسطة", "medium",
                f"التدفق التشغيلي {cfo:,.0f} = {ratio * 100:.0f}% من صافي "
                f"الربح ({ni:,.0f}) — يستحق المتابعة ربعيًا.",
            ))

    # 2) Receivables outrunning revenue (channel stuffing pattern)
    ar_g, rev_g = _g(curr.accounts_receivable, prev.accounts_receivable), _g(curr.revenue, prev.revenue)
    if ar_g is not None and rev_g is not None and ar_g > rev_g * 2 + 10 and ar_g > 20:
        flags.append(RedFlag(
            "ذمم مدينة تنفصل عن الإيرادات", "medium",
            f"الذمم المدينة +{ar_g:.0f}% بينما الإيرادات +{rev_g:.0f}% — نمط "
            "يتسق مع ضخ مبيعات أو شروط سداد متساهلة (تحقق من أعمار الديون).",
        ))

    # 3) Inventory pile-up
    inv_g = _g(curr.inventory, prev.inventory)
    if inv_g is not None and rev_g is not None and inv_g > rev_g * 2 + 10 and inv_g > 20:
        flags.append(RedFlag(
            "تكدس المخزون", "medium",
            f"المخزون +{inv_g:.0f}% مقابل إيرادات +{rev_g:.0f}% — مخزون ينمو "
            "أسرع من البيع (خطر تقادم/خصومات اضطرارية).",
        ))

    # 4) Working capital trajectory
    if curr.working_capital is not None:
        if (prev.working_capital or 0) >= 0 > curr.working_capital:
            flags.append(RedFlag(
                "رأس المال العامل انقلب سالبًا", "medium",
                f"من {prev.working_capital:,.0f} إلى {curr.working_capital:,.0f} "
                "— الالتزامات قصيرة الأجل تجاوزت الأصول المتداولة.",
            ))
        elif (curr.working_capital or 0) < 0 and (prev.working_capital or 0) < 0 \
                and curr.working_capital < prev.working_capital:
            flags.append(RedFlag(
                "تعمق عجز رأس المال العامل", "low",
                f"العجز اتسع من {prev.working_capital:,.0f} إلى "
                f"{curr.working_capital:,.0f}.",
            ))

    # 5) Financing squeeze
    if curr.operating_income and curr.interest_expense:
        cov = curr.operating_income / abs(curr.interest_expense)
        if cov < 1:
            flags.append(RedFlag(
                "التمويل يلتهم التشغيل", "high",
                f"الربح التشغيلي {curr.operating_income:,.0f} لا يغطي التكاليف "
                f"التمويلية ({curr.interest_expense:,.0f}) — التغطية {cov:.2f}x.",
            ))
        elif cov < 2:
            flags.append(RedFlag(
                "تغطية فوهات ضيقة", "medium",
                f"الربح التشغيلي يغطي التكاليف التمويلية {cov:.1f}x فقط.",
            ))

    return flags


def beneish_m_score(prev, curr) -> BeneishResult:
    """8-variable Beneish M (1999). None-safe: computed ONLY when all eight
    components are available, otherwise the missing list explains why."""
    res = BeneishResult()
    c, p = curr, prev

    dsri = None
    if c.accounts_receivable is not None and c.revenue and p.accounts_receivable is not None and p.revenue:
        dsri = (c.accounts_receivable / c.revenue) / (p.accounts_receivable / p.revenue)
    gmi = None
    if p.gross_profit is not None and p.revenue and c.gross_profit is not None and c.revenue:
        gmi = (p.gross_profit / p.revenue) / (c.gross_profit / c.revenue)
    aqi = None
    if (c.fixed_assets is not None and c.total_assets and p.fixed_assets is not None and p.total_assets):
        soft_c = 1 - (c.fixed_assets / c.total_assets)   # soft-assets share (approx.)
        soft_p = 1 - (p.fixed_assets / p.total_assets)
        aqi = soft_c / soft_p if soft_p else None
    sgi = None
    if p.revenue and c.revenue is not None:
        sgi = c.revenue / p.revenue
    depi = None
    if (c.depreciation_amortization is not None and c.fixed_assets and p.depreciation_amortization is not None and p.fixed_assets):
        rate_c = c.depreciation_amortization / (c.depreciation_amortization + c.fixed_assets)
        rate_p = p.depreciation_amortization / (p.depreciation_amortization + p.fixed_assets)
        depi = rate_p / rate_c if rate_c else None
    sgai = None
    if (c.selling_expenses is not None and c.revenue and p.selling_expenses is not None and p.revenue):
        sgai = (p.selling_expenses / p.revenue) / (c.selling_expenses / c.revenue)
    lvgi = None
    if c.total_liabilities is not None and c.total_assets and p.total_liabilities is not None and p.total_assets:
        lvgi = (c.total_liabilities / c.total_assets) / (p.total_liabilities / p.total_assets)
    tata = None
    if c.net_income is not None and c.operating_cash_flow is not None and c.total_assets:
        tata = (c.net_income - c.operating_cash_flow) / c.total_assets

    comps = dict(DSRI=dsri, GMI=gmi, AQI=aqi, SGI=sgi, DEPI=depi, SGAI=sgai, LVGI=lvgi, TATA=tata)
    for name, v in comps.items():
        if v is None:
            res.missing.append(name)
        else:
            res.components[name] = round(v, 4)
    if res.missing:
        return res  # partial M would be a guess

    m = (
        -4.84
        + 0.920 * dsri + 0.528 * gmi + 0.404 * aqi + 0.892 * sgi
        + 0.115 * depi - 0.172 * sgai + 4.679 * tata - 0.327 * lvgi
    )
    res.m_score = round(m, 3)
    res.verdict = {
        "grey_above": "نمط يستحق التدقيق — مؤشرات اتساق مع التلاعب بالأرباح",
        "grey": "منطقة رمادية — راقب مكونات النموذج",
        "clean": "لا يظهر نمط تلاعب",
    }[res.zone]
    return res
