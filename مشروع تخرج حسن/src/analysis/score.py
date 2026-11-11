"""Deterministic Financial Health Score (0-100).

A transparent, explainable score from the CURRENT-year metrics only. Each
pillar averages simple sub-scores measured against widely accepted general
guideline levels (never sector data): a sub-score hits 100 when the ratio
reaches its guideline target and scales down linearly to 0 at a clearly weak
level. Pillar scores combine by weight; missing data is excluded and the
weights of available pillars are renormalized.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.analysis.calculator import YearMetrics


def report_language() -> str:
    from src.config import REPORT_LANGUAGE

    return REPORT_LANGUAGE


def _clamp100(value: float) -> float:
    return max(0.0, min(100.0, value))


def _vs_target(value: float | None, target: float) -> float | None:
    """Score 100 at the guideline target, scaling linearly down to 0."""
    if value is None:
        return None
    return _clamp100(value / target * 100)


def _lower_better(value: float | None, weak_at: float) -> float | None:
    """Score 100 at 0, linearly down to 0 at `weak_at` (for leverage-type)."""
    if value is None:
        return None
    return _clamp100((1 - value / weak_at) * 100)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


@dataclass
class Pillar:
    key: str
    name_en: str
    name_ar: str
    weight: float
    score: float | None
    details: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.name_ar if report_language() == "ar" else self.name_en


@dataclass
class HealthScore:
    total: float | None
    pillars: list[Pillar]
    label_en: str
    label_ar: str
    coverage: float = 1.0          # share of pillar weights actually computed
    complete: bool = True          # False = partial score (some pillars missing)
    missing_pillars: list[str] = None  # type: ignore[assignment]
    policy: str = ""               # Missing-Data-Coverage disclosure

    def __post_init__(self):
        if self.missing_pillars is None:
            self.missing_pillars = []

    @property
    def label(self) -> str:
        return self.label_ar if report_language() == "ar" else self.label_en


def compute_health_score(curr: YearMetrics,
                         blocked_fields: set[str] | None = None) -> HealthScore:
    """Build the score from current-year ratios (prev metrics not needed).
    `blocked_fields` (from financial_gate) excludes any metric whose input
    fields are not decisive — a pillar built ONLY from blocked inputs is
    dropped and the remaining weights renormalize, instead of printing a
    confident score computed from a conflicted number."""
    blocked = blocked_fields or set()
    pillars: list[Pillar] = []

    # --- Liquidity (25%) ---
    liq_subs = [
        (_vs_target(curr.current_ratio, 2.0), "نسبة التداول", "2.00x"),
        (_vs_target(curr.quick_ratio, 1.0), "Quick Ratio", "1.00x"),
    ]
    pillars.append(_pillar("liquidity", "Liquidity", "السيولة", 25, liq_subs))

    # --- Leverage (25%) — lower is better ---
    lev_subs = [
        (_lower_better(curr.debt_to_equity, 2.0), "الدين إلى حقوق الملكية", "< 1.00x"),
        (_lower_better(curr.debt_ratio, 1.0), "Debt Ratio", "< 0.50x"),
    ]
    pillars.append(_pillar("leverage", "Leverage", "المديونية", 25, lev_subs))

    # --- Profitability (30%) ---
    prof_subs = [
        (_vs_target(curr.net_margin, 15.0), "هامش صافي الربح", "15%"),
        (_vs_target(curr.roe, 15.0), "العائد على حقوق الملكية", "15%"),
        (_vs_target(curr.roa, 7.5), "العائد على الأصول", "7.5%"),
    ]
    pillars.append(_pillar("profitability", "Profitability", "الربحية", 30, prof_subs))

    # --- Cash generation (20%) ---
    cash_subs = [
        (_vs_target(curr.cfo_to_net_income, 1.0), "التدفق التشغيلي ÷ صافي الربح", "1.00x"),
        (_vs_target(curr.cfo_margin, 15.0), "هامش التدفق التشغيلي", "15%"),
    ]
    pillars.append(_pillar("cash", "Cash Generation", "التدفق النقدي", 20, cash_subs))

    if blocked:
        for p in pillars:
            key_inputs = {
                "liquidity": ("current_ratio", "quick_ratio"),
                "leverage": ("debt_to_equity", "debt_ratio"),
                "profitability": ("net_margin", "roe", "roa"),
                "cash": ("cfo_to_net_income", "cfo_margin"),
            }.get(p.key, ())
            # a pillar whose inputs ALL depend on blocked fields is dropped
            required = {"current_ratio": ["current_assets", "current_liabilities"],
                        "quick_ratio": ["current_assets", "current_liabilities", "inventory"],
                        "debt_to_equity": ["total_liabilities", "equity"],
                        "debt_ratio": ["total_liabilities", "total_assets"],
                        "net_margin": ["net_income", "revenue"],
                        "roe": ["net_income", "equity"],
                        "roa": ["net_income", "total_assets"],
                        "cfo_to_net_income": ["operating_cash_flow", "net_income"],
                        "cfo_margin": ["operating_cash_flow", "revenue"]}
            if key_inputs and all(
                any(f in blocked for f in required.get(k, []))
                for k in key_inputs
            ):
                p.score = None
                p.details.append("(محجوب: مدخلاته غير حاسمة — لن تُطبع كدرجة)")
    weighted = [(p.score, p.weight) for p in pillars if p.score is not None]
    total = (
        sum(s * w for s, w in weighted) / sum(w for _, w in weighted)
        if weighted
        else None
    )

    # Missing-Data-Coverage policy: liquidity and leverage are the risk
    # cores — a score printed without them would HIDE company risk, so the
    # score is REFUSED (not renormalized around the hole). Profitability/
    # cash may be missing: the score becomes PARTIAL with the coverage
    # disclosed next to it.
    CRITICAL_PILLARS = {"liquidity", "leverage"}
    total_weight = sum(p.weight for p in pillars) or 100.0
    missing_pillars = [p.key for p in pillars if p.score is None]
    coverage = sum(p.weight for p in pillars if p.score is not None) / total_weight
    refused = bool(CRITICAL_PILLARS & set(missing_pillars))

    if total is None or refused:
        total = None
        label_en = "Refused — critical data missing"
        label_ar = ("مرفوض — بيانات حرجة ناقصة (سيولة/مديونية): "
                    "لا تُصدر درجة قد تخفي مخاطر الشركة")
    elif total >= 80:
        label_en, label_ar = "Strong", "قوي"
    elif total >= 60:
        label_en, label_ar = "Stable", "مستقر"
    elif total >= 40:
        label_en, label_ar = "Needs attention", "يحتاج متابعة"
    else:
        label_en, label_ar = "Weak", "ضعيف"

    complete = not missing_pillars
    policy = (
        f"تغطية البيانات {coverage * 0.0 + coverage * 100:.0f}% | "
        f"الركائز المحسوبة: {sorted(set(p.key for p in pillars) - set(missing_pillars))} | "
        f"المحجوبة/الناقصة: {sorted(missing_pillars) or 'لا شيء'} | "
        + ("درجة كلية" if complete else
           "درجة جزئية — لا تعوض غياب ركيزة حرجة" if not refused else
           "رُفضت الدرجة: ركيزة سيولة/مديونية ناقصة")
    )
    return HealthScore(
        total=None if total is None else round(total, 1),
        pillars=pillars,
        label_en=label_en,
        label_ar=label_ar,
        coverage=round(coverage, 3),
        complete=complete,
        missing_pillars=missing_pillars,
        policy=policy,
    )


def _pillar(
    key: str, name_en: str, name_ar: str, weight: float,
    subs: list[tuple[float | None, str, str]],
) -> Pillar:
    """Average the available sub-scores; document each vs its guideline."""
    scores = [s for s, _, _ in subs if s is not None]
    details = []
    for s, label, target in subs:
        if s is None:
            details.append(f"{label}: N/A (guideline {target})")
        else:
            details.append(f"{label}: {s:.0f}/100 (guideline {target})")
    return Pillar(
        key=key, name_en=name_en, name_ar=name_ar, weight=weight,
        score=round(_mean(scores), 1) if scores else None,
        details=details,
    )


def top_movers(rows, limit: int = 3) -> tuple[list, list]:
    """(improving, declining) metric rows sorted by |change %| — both limited."""
    moving = [
        r for r in rows
        if r.change_pct is not None and r.change_pct != 0 and r.previous is not None
    ]
    improving = sorted(
        (r for r in moving if r.status == "Positive"),
        key=lambda r: r.change_pct, reverse=True,
    )[:limit]
    declining = sorted(
        (r for r in moving if r.status == "Negative"),
        key=lambda r: abs(r.change_pct), reverse=True,
    )[:limit]
    return improving, declining
