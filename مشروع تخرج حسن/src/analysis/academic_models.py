"""Academic early-warning & attribution models (النماذج الأكاديمية) — deterministic, zero API.

Published models from the finance literature, computed on the CURRENT fiscal
year alone (no prior year needed). Like every module in this system: a model
is computed ONLY when all its components exist in the extracted data —
otherwise the missing list says exactly what the document lacks. No guesses.

- Altman Z′ (1968, private-firms revision with book equity):
      Z′ = 0.717·X1 + 0.847·X2 + 3.107·X3 + 0.420·X4 + 0.998·X5
      X1 = Working Capital / Total Assets,  X2 = Retained Earnings / Total Assets,
      X3 = EBIT / Total Assets,             X4 = Book Equity / Total Liabilities,
      X5 = Sales / Total Assets.
      Zones: safe > 2.90 | grey 1.23–2.90 | distress < 1.23.
- Springate (1978):
      S = 1.03·A + 3.07·B + 0.57·C + 0.59·D
      A = WC/TA, B = EBIT/TA, C = Pretax Income / Current Liabilities, D = Sales/TA.
      S < 0.862 → potential insolvency (overall accuracy ≈ 92.5% in the paper).
- Zmijewski (1984):
      X = −4.336 − 4.513·(NI/TA) + 5.679·(TL/TA) + 0.004·(CL/CA)
      Fitted so the financially-distressed group scores higher; X > 0 reads as
      elevated bankruptcy probability (the widely used study threshold).
- DuPont decomposition: 3-step (margin × turnover × leverage) and 5-step
  (tax burden × interest burden × EBIT margin × turnover × leverage).
  Reconstructed ROE cross-checks the directly computed ROE.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.analysis.calculator import YearMetrics, safe_div


@dataclass
class ModelResult:
    key: str
    name_en: str
    name_ar: str
    value: float | None = None
    zone: str = ""          # safe | grey | distress | risk_low | risk_high | ""
    verdict_en: str = ""
    verdict_ar: str = ""
    formula: str = ""
    reference: str = ""
    components: dict[str, float] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.name_ar if _lang() == "ar" else self.name_en

    @property
    def verdict(self) -> str:
        return self.verdict_ar if _lang() == "ar" else self.verdict_en

    @property
    def icon(self) -> str:
        return {
            "safe": "🟢", "grey": "🟡", "distress": "🔴",
            "risk_low": "🟢", "risk_high": "🔴", "": "",
        }.get(self.zone, "")


def _lang() -> str:
    from src.config import REPORT_LANGUAGE

    return REPORT_LANGUAGE


def altman_z_prime(curr: YearMetrics) -> ModelResult:
    """Altman Z′ — the private/unlisted-firms revision (book equity)."""
    res = ModelResult(
        key="altman",
        name_en="Altman Z-Score (Z′, private firms)",
        name_ar="نموذج ألتمان Z-Score (نسخة الشركات غير المدرجة)",
        formula="Z′ = 0.717·X1 + 0.847·X2 + 3.107·X3 + 0.420·X4 + 0.998·X5",
        reference="Altman (1968; 1983 revision)",
    )
    x1 = safe_div(curr.working_capital, curr.total_assets)
    x2 = safe_div(curr.retained_earnings, curr.total_assets)
    x3 = safe_div(curr.operating_income, curr.total_assets)
    x4 = safe_div(curr.equity, curr.total_liabilities)
    x5 = safe_div(curr.revenue, curr.total_assets)
    raw = {"X1": x1, "X2": x2, "X3": x3, "X4": x4, "X5": x5}
    for k, v in raw.items():
        if v is None:
            res.missing.append(k)
        else:
            res.components[k] = round(v, 4)
    if res.missing:
        return res
    z = 0.717 * x1 + 0.847 * x2 + 3.107 * x3 + 0.420 * x4 + 0.998 * x5
    res.value = round(z, 3)
    if z > 2.90:
        res.zone = "safe"
        res.verdict_en = "Safe zone — low bankruptcy risk per the model"
        res.verdict_ar = "منطقة آمنة — مخاطر الإفلاس منخفضة وفق النموذج"
    elif z >= 1.23:
        res.zone = "grey"
        res.verdict_en = "Grey zone — monitor the model components"
        res.verdict_ar = "منطقة رمادية — يلزم مراقبة مكونات النموذج"
    else:
        res.zone = "distress"
        res.verdict_en = "Distress zone — elevated bankruptcy risk per the model"
        res.verdict_ar = "منطقة ضائقة — احتمال إفلاس مرتفع وفق النموذج"
    return res


def springate_score(curr: YearMetrics) -> ModelResult:
    """Springate (1978) bankruptcy model."""
    res = ModelResult(
        key="springate",
        name_en="Springate Model",
        name_ar="نموذج سبرينغيت",
        formula="S = 1.03·A + 3.07·B + 0.57·C + 0.59·D (حد الخطر 0.862)",
        reference="Springate (1978)",
    )
    a = safe_div(curr.working_capital, curr.total_assets)
    b = safe_div(curr.operating_income, curr.total_assets)
    c = safe_div(curr.pretax_income, curr.current_liabilities)
    d = safe_div(curr.revenue, curr.total_assets)
    raw = {"A": a, "B": b, "C": c, "D": d}
    for k, v in raw.items():
        if v is None:
            res.missing.append(k)
        else:
            res.components[k] = round(v, 4)
    if res.missing:
        return res
    s = 1.03 * a + 3.07 * b + 0.57 * c + 0.59 * d
    res.value = round(s, 3)
    if s < 0.862:
        res.zone = "distress"
        res.verdict_en = "Below the 0.862 cut-off — potential insolvency signal"
        res.verdict_ar = "تحت حد الخطر 0.862 — إشارة احتمال تعثر مالي"
    else:
        res.zone = "safe"
        res.verdict_en = "Above the cut-off — no distress signal from the model"
        res.verdict_ar = "فوق حد الخطر — لا إشارة تعثر من النموذج"
    return res


def zmijewski_score(curr: YearMetrics) -> ModelResult:
    """Zmijewski (1984) distress-probability score."""
    res = ModelResult(
        key="zmijewski",
        name_en="Zmijewski Score",
        name_ar="نموذج زميجيفسكي",
        formula="X = −4.336 − 4.513·(NI/TA) + 5.679·(TL/TA) + 0.004·(CL/CA)",
        reference="Zmijewski (1984)",
    )
    roa = safe_div(curr.net_income, curr.total_assets)
    debt_ratio = safe_div(curr.total_liabilities, curr.total_assets)
    cl_ca = safe_div(curr.current_liabilities, curr.current_assets)
    raw = {"NI/TA": roa, "TL/TA": debt_ratio, "CL/CA": cl_ca}
    for k, v in raw.items():
        if v is None:
            res.missing.append(k)
        else:
            res.components[k] = round(v, 4)
    if res.missing:
        return res
    x = -4.336 - 4.513 * roa + 5.679 * debt_ratio + 0.004 * cl_ca
    res.value = round(x, 3)
    if x > 0:
        res.zone = "risk_high"
        res.verdict_en = "Score above zero — the model's distressed-group range"
        res.verdict_ar = "الدرجة أعلى من الصفر — نطاق مجموعة الضائقة في معايرة النموذج"
    else:
        res.zone = "risk_low"
        res.verdict_en = "Score at or below zero — not in the distressed range"
        res.verdict_ar = "الدرجة صفر أو أقل — خارج نطاق الضائقة"
    return res


def dupont_analysis(curr: YearMetrics) -> ModelResult:
    """DuPont 3-step + 5-step decomposition of ROE from year-end balances."""
    res = ModelResult(
        key="dupont",
        name_en="DuPont Analysis (ROE decomposition)",
        name_ar="تحليل دوبونت (تفكيك العائد على حقوق الملكية)",
        formula="ROE = هامش صافي الربح × دوران الأصول × الرافعة المالية",
        reference="DuPont (3-step and 5-step forms)",
    )
    ni, rev, ta, eq = curr.net_income, curr.revenue, curr.total_assets, curr.equity
    margin = safe_div(ni, rev)
    turnover = safe_div(rev, ta)
    leverage = safe_div(ta, eq)
    if margin is None or turnover is None or leverage is None:
        res.missing = [k for k, v in
                       {"NI/Rev": margin, "Rev/TA": turnover, "TA/Equity": leverage}.items()
                       if v is None]
        return res
    roe_rebuilt = margin * turnover * leverage
    res.components = {
        "NetMargin": round(margin * 100, 2),        # %
        "AssetTurnover": round(turnover, 3),         # x
        "EquityMultiplier": round(leverage, 3),      # x
        "ROE_rebuilt": round(roe_rebuilt * 100, 2),  # %
    }
    # 5-step when the income statement is deep enough
    if None not in (ni, curr.pretax_income, curr.operating_income):
        tax_burden = safe_div(ni, curr.pretax_income)
        interest_burden = safe_div(curr.pretax_income, curr.operating_income)
        ebit_margin = safe_div(curr.operating_income, rev)
        if None not in (tax_burden, interest_burden, ebit_margin):
            res.components["TaxBurden"] = round(tax_burden, 3)
            res.components["InterestBurden"] = round(interest_burden, 3)
            res.components["EBITMargin"] = round(ebit_margin * 100, 2)
    res.value = round(roe_rebuilt * 100, 2)
    res.zone = ""
    # Which driver carries the ROE: the factor farthest from its neutral level.
    drivers = []
    if turnover < 0.5:
        drivers.append(("AssetTurnover", "دوران أصول بطيء يثقل العائد"))
    if leverage > 3.0:
        drivers.append(("EquityMultiplier", "الرافعة المالية مرتفعة — العائد مدفوع بالدين"))
    if margin is not None and margin < 0.03:
        drivers.append(("NetMargin", "هامش ربح صافٍ ضيق"))
    if not drivers:
        res.verdict_en = "ROE drivers are within ordinary levels"
        res.verdict_ar = "محركات العائد على حقوق الملكية ضمن المستويات الاعتيادية"
    else:
        res.verdict_en = "Watch: " + "; ".join(d[1] for d in drivers)
        res.verdict_ar = "انتبه: " + "؛ ".join(d[1] for d in drivers)
    return res


def academic_models(curr: YearMetrics) -> list[ModelResult]:
    """All four academic models for the current year, in presentation order."""
    return [
        altman_z_prime(curr),
        springate_score(curr),
        zmijewski_score(curr),
        dupont_analysis(curr),
    ]
