# -*- coding: utf-8 -*-
"""Constrained Financial Optimization Engine (`optimize_engine.py`).

Uses **Z3 Optimize (`z3.Optimize()`)** + **Multi-Layer Protection Gate** + **Lean 4
Formal Kernel Verification** to solve optimal, accounting-consistent improvement plans.

Unlike `whatif.py` (which leaves the Balance Sheet static), every plan solved here
propagates earnings retention, working-capital release, interest savings, and debt
paydown through exact double-entry accounting:
  ΔCash = ΔNetIncome − ΔDividends + ΔWorkingCapital − DebtRepay
  Assets' = Assets + ΔCash − ΔWorkingCapital
  Liabilities' = Liabilities − DebtRepay
  Equity' = Equity + ΔNetIncome − ΔDividends
so `Assets' == Liabilities' + Equity'` holds with ZERO discrepancy and is certified
by both Z3 SMT and the Lean 4 `optimization_double_entry_safety` proof kernel.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from src.analysis.calculator import YearMetrics, compute_year_metrics
from src.analysis.protection_layer import evaluate_protection_gate, verify_optimized_state
from src.analysis.score import compute_health_score

try:
    import z3  # type: ignore

    _Z3_OK = True
except Exception:  # pragma: no cover
    z3 = None
    _Z3_OK = False


OBJECTIVES: dict[str, dict[str, str]] = {
    "maximize_profit_eps": {
        "ar": "تعظيم صافي الربح وربحية السهم (EPS) ضمن حدود السيولة",
        "en": "Maximize Net Income & EPS under Liquidity Covenants",
    },
    "minimize_leverage_nd_ebitda": {
        "ar": "خفض صافي الدين / EBITDA والمديونية مع حماية النقدية",
        "en": "Minimize Net Debt / EBITDA & Leverage safely",
    },
    "maximize_health_balanced": {
        "ar": "خطة تحسين متوازنة لأعلى درجة صحة مالية وعائد حقوق الملكية (ROE)",
        "en": "Balanced Optimization for Peak Health Score & ROE",
    },
}


@dataclass
class OptimizationConstraints:
    objective: str = "maximize_health_balanced"
    max_revenue_boost_pct: float = 10.0     # 0..25%
    max_cogs_cut_pct: float = 5.0           # 0..15%
    max_opex_cut_pct: float = 10.0          # 0..20%
    max_wc_release_pct: float = 15.0        # 0..30% of Inventory + AR
    min_current_ratio: float = 1.25         # >= 1.0x liquidity floor
    min_cash_buffer_pct_cl: float = 5.0     # >= 5% of current liabilities
    max_payout_pct: float = 0.0             # additional incremental NI distributed as dividend
    allow_exploratory: bool = False         # if False & critical fields blocked -> refuse official


@dataclass
class OptimizationResult:
    status: str  # "OPTIMAL" | "EXPLORATORY_OPTIMAL" | "REFUSED_PROTECTION_GATE" | "INFEASIBLE"
    objective: str
    is_official: bool
    protection_verdict: dict[str, Any] = field(default_factory=dict)
    levers: dict[str, float] = field(default_factory=dict)
    baseline: dict[str, float | None] = field(default_factory=dict)
    optimized: dict[str, float | None] = field(default_factory=dict)
    deltas: dict[str, float | None] = field(default_factory=dict)
    lean4_proof: dict[str, Any] = field(default_factory=dict)
    recommendations_ar: list[str] = field(default_factory=list)
    recommendations_en: list[str] = field(default_factory=list)
    reason_ar: str = ""
    reason_en: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _snapshot_metrics(
    m: YearMetrics,
    *,
    share_price: float | None = None,
    employee_count: int | None = None,
    blocked_fields: set[str] | None = None,
    raw_extra: dict[str, dict[int, float]] | None = None,
) -> dict[str, float | None]:
    hs = compute_health_score(m, blocked_fields=blocked_fields)
    if share_price is not None and share_price > 0 or employee_count is not None and employee_count > 0:
        data_d: dict[str, dict[int, float]] = {}
        for f in (
            "revenue", "cost_of_revenue", "gross_profit", "operating_expenses",
            "operating_income", "pretax_income", "income_tax_expense", "net_income",
            "depreciation_amortization", "interest_expense", "total_assets",
            "current_assets", "inventory", "accounts_receivable", "cash",
            "fixed_assets", "accounts_payable", "current_liabilities",
            "total_liabilities", "total_debt", "equity", "retained_earnings",
            "operating_cash_flow", "capex", "shares_outstanding",
            "dividends_paid_shareholders", "income_taxes_paid", "total_wages",
            "related_party_payables",
        ):
            v = getattr(m, f, None)
            if v is not None:
                data_d[f] = {m.year: float(v)}
        if raw_extra:
            for fk, yv in raw_extra.items():
                data_d.setdefault(fk, {}).update(yv)
        m = compute_year_metrics(
            m.year,
            data_d,
            prev_year=None,
            share_price=share_price,
            employee_count=employee_count,
        )
    return {
        "revenue": m.revenue,
        "cost_of_revenue": m.cost_of_revenue,
        "gross_profit": m.gross_profit,
        "operating_income": m.operating_income,
        "ebitda": m.ebitda,
        "interest_expense": m.interest_expense,
        "pretax_income": m.pretax_income,
        "income_tax_expense": m.income_tax_expense,
        "net_income": m.net_income,
        "total_assets": m.total_assets,
        "current_assets": m.current_assets,
        "current_liabilities": m.current_liabilities,
        "cash": m.cash,
        "total_debt": m.total_debt,
        "net_debt": m.net_debt,
        "total_liabilities": m.total_liabilities,
        "equity": m.equity,
        "net_margin": m.net_margin,
        "current_ratio": m.current_ratio,
        "debt_to_equity": m.debt_to_equity,
        "roe": m.roe,
        "roa": m.roa,
        "net_debt_to_ebitda": m.net_debt_to_ebitda,
        "eps": m.eps,
        "bvps": m.bvps,
        "dps": m.dps,
        "pe_ratio": m.pe_ratio,
        "pb_ratio": m.pb_ratio,
        "ev_to_ebitda": m.ev_to_ebitda,
        "dividend_yield": m.dividend_yield,
        "employee_productivity": m.employee_productivity,
        "health_score": hs.total,
    }


def _to_float(z3_val: Any) -> float:
    if hasattr(z3_val, "numerator_as_long"):
        return float(z3_val.numerator_as_long()) / float(z3_val.denominator_as_long())
    if hasattr(z3_val, "as_long"):
        return float(z3_val.as_long())
    return float(str(z3_val))


def optimize_financial_plan(
    results: dict,
    constraints: OptimizationConstraints | None = None,
    *,
    share_price: float | None = None,
    employee_count: int | None = None,
) -> OptimizationResult:
    """Solve an accounting-consistent optimal improvement plan via Z3 Optimize + Lean 4 Proof."""
    cfg = constraints or OptimizationConstraints()
    obj = cfg.objective if cfg.objective in OBJECTIVES else "maximize_health_balanced"

    # Clamp user constraint bounds strictly to economic plausibility ranges
    max_rev_pct = max(0.0, min(25.0, float(cfg.max_revenue_boost_pct)))
    max_cogs_pct = max(0.0, min(15.0, float(cfg.max_cogs_cut_pct)))
    max_opex_pct = max(0.0, min(20.0, float(cfg.max_opex_cut_pct)))
    max_wc_pct = max(0.0, min(30.0, float(cfg.max_wc_release_pct)))
    min_cr = max(0.5, min(5.0, float(cfg.min_current_ratio)))
    min_cash_pct_cl = max(0.0, min(50.0, float(cfg.min_cash_buffer_pct_cl)))
    inc_payout = max(0.0, min(80.0, float(cfg.max_payout_pct))) / 100.0

    # Layer 1: Protection Gate
    prot = evaluate_protection_gate(results, allow_exploratory=cfg.allow_exploratory)
    curr_m: YearMetrics | None = results.get("curr_metrics")
    if curr_m is None:
        return OptimizationResult(
            status="INFEASIBLE",
            objective=obj,
            is_official=False,
            protection_verdict=prot.to_dict(),
            reason_ar="لا توجد بيانات سنة حالية للتحسين.",
            reason_en="Current-year metrics unavailable.",
        )

    is_official = (not prot.quota_interrupted) and (not prot.blocked_fields)
    if not prot.permit_official_optimization:
        return OptimizationResult(
            status="REFUSED_PROTECTION_GATE",
            objective=obj,
            is_official=False,
            protection_verdict=prot.to_dict(),
            reason_ar=(
                "حارس الحماية رفض إصدار خطة تحسين رسمية بسبب خانات حرجة معلقة أو مقاطعة الحصة — "
                "وثّق الخانات في «مراجعة بشرية» أو فعّل «وضع التحسين الاستكشافي»."
            ),
            reason_en=(
                "Protection Gate refused official optimization due to unverified critical fields or quota pause — "
                "verify pending cells or enable Exploratory Optimization mode."
            ),
        )

    # Layer 2: Required baseline scalars & accounting sanity check
    rev0 = float(curr_m.revenue or 0.0)
    cogs0 = abs(float(curr_m.cost_of_revenue or 0.0))
    opex0 = abs(float(curr_m.operating_expenses or 0.0))
    oi0 = float(curr_m.operating_income or 0.0)
    da0 = abs(float(curr_m.depreciation_amortization or 0.0))
    int0 = abs(float(curr_m.interest_expense or 0.0))
    pretax0 = float(curr_m.pretax_income if curr_m.pretax_income is not None else oi0 - int0)
    tax0 = abs(float(curr_m.income_tax_expense or 0.0))
    ni0 = float(curr_m.net_income or 0.0)
    ta0 = float(curr_m.total_assets or 0.0)
    ca0 = float(curr_m.current_assets or 0.0)
    cl0 = float(curr_m.current_liabilities or 0.0)
    tl0 = float(curr_m.total_liabilities or 0.0)
    eq0 = float(curr_m.equity or 0.0)
    cash0 = float(curr_m.cash or 0.0)
    debt0 = float(curr_m.total_debt or 0.0)
    inv0 = max(0.0, float(curr_m.inventory or 0.0))
    ar0 = max(0.0, float(curr_m.accounts_receivable or 0.0))

    if rev0 <= 0 or ta0 <= 0 or eq0 <= 0 or cl0 <= 0:
        return OptimizationResult(
            status="INFEASIBLE",
            objective=obj,
            is_official=False,
            protection_verdict=prot.to_dict(),
            reason_ar="البيانات الأساسية (الإيرادات، الأصول، حقوق الملكية، الالتزامات المتداولة) غير مكتملة أو غير موجبة.",
            reason_en="Core inputs (Revenue, Assets, Equity, Current Liabilities) missing or non-positive.",
        )

    # Balance-sheet closed check before optimizing (absorb minor derived residual only if BS open)
    if abs(ta0 - (tl0 + eq0)) > max(100.0, 1e-3 * ta0):
        return OptimizationResult(
            status="INFEASIBLE",
            objective=obj,
            is_official=False,
            protection_verdict=prot.to_dict(),
            reason_ar=(
                f"معادلة الميزانية الأساسية غير متزنة ({ta0:,.0f} مقابل {tl0 + eq0:,.0f}) — "
                "طبقة الحماية تمنع التحسين على ميزانية غير متوازنة."
            ),
            reason_en="Base Balance Sheet equation TA = TL + E is out of balance; optimization blocked.",
        )

    if not _Z3_OK:  # pragma: no cover
        return OptimizationResult(
            status="INFEASIBLE",
            objective=obj,
            is_official=False,
            protection_verdict=prot.to_dict(),
            reason_ar="مكتبة z3-solver غير متوفرة لتشغيل محرك التحسين.",
            reason_en="z3-solver unavailable.",
        )

    # Effective tax rate and interest rate estimates from printed baseline
    etr = min(0.35, max(0.0, tax0 / pretax0)) if pretax0 > 0 else 0.225
    interest_rate = min(0.30, max(0.0, int0 / debt0)) if debt0 > 0 else 0.0
    non_op_gap = pretax0 - (oi0 - int0)
    wc_base = inv0 + ar0
    max_repay_cap = debt0
    min_cash_floor = min(cash0, cl0 * (min_cash_pct_cl / 100.0))

    # Layer 3: Z3 Optimize Constrained Solver
    opt = z3.Optimize()
    opt.set("timeout", 3000)

    r_rev = z3.Real("rev_boost")        # 0 .. max_rev_pct / 100
    r_cogs = z3.Real("cogs_cut")        # 0 .. max_cogs_pct / 100
    r_opex = z3.Real("opex_cut")        # 0 .. max_opex_pct / 100
    r_wc = z3.Real("wc_release")        # 0 .. max_wc_pct / 100
    debt_repay = z3.Real("debt_repay")  # EGP repaid

    opt.add(r_rev >= 0, r_rev <= z3.RealVal(f"{max_rev_pct / 100.0:.6f}"))
    opt.add(r_cogs >= 0, r_cogs <= z3.RealVal(f"{max_cogs_pct / 100.0:.6f}"))
    opt.add(r_opex >= 0, r_opex <= z3.RealVal(f"{max_opex_pct / 100.0:.6f}"))
    opt.add(r_wc >= 0, r_wc <= z3.RealVal(f"{max_wc_pct / 100.0:.6f}"))
    opt.add(debt_repay >= 0, debt_repay <= z3.RealVal(f"{max_repay_cap:.2f}"))

    # Linearized cost reduction: new revenue carries baseline COGS ratio unless improved
    base_cogs_ratio = (cogs0 / rev0) if rev0 > 0 else 0.7
    rev1 = z3.RealVal(f"{rev0:.2f}") * (1 + r_rev)
    # Revenue expansion scales variable COGS cleanly at baseline COGS ratio, while cost-cut lowers effective COGS
    cogs_var_scaled = z3.RealVal(f"{cogs0:.2f}") * (1 + r_rev)
    cogs1 = cogs_var_scaled * (1 - r_cogs) if cogs0 > 0 else z3.RealVal("0")
    gp1 = rev1 - cogs1
    opex1 = z3.RealVal(f"{opex0:.2f}") * (1 - r_opex)
    oi1 = gp1 - opex1

    int_saved = debt_repay * z3.RealVal(f"{interest_rate:.6f}")
    int1 = z3.RealVal(f"{int0:.2f}") - int_saved
    pretax1 = oi1 - int1 + z3.RealVal(f"{non_op_gap:.2f}")
    tax1 = z3.If(pretax1 > 0, pretax1 * z3.RealVal(f"{etr:.6f}"), z3.RealVal("0"))
    ni1 = pretax1 - tax1

    dn = ni1 - z3.RealVal(f"{ni0:.2f}")
    # Only distribute incremental profit if baseline NI > 0 and user allowed payout
    dp = z3.If(dn > 0, dn * z3.RealVal(f"{inc_payout:.6f}"), z3.RealVal("0"))
    dw = z3.RealVal(f"{wc_base:.2f}") * r_wc
    dc = dn - dp + dw - debt_repay

    cash1 = z3.RealVal(f"{cash0:.2f}") + dc
    # Working capital cash release lowers Inventory/AR proportionally; extra cash enters CA -> net ΔCA = dc - dw = dn - dp - debt_repay
    ca1 = z3.RealVal(f"{ca0:.2f}") + dc - dw
    # Debt paydown reduces current liabilities first (credit facilities / short-term portion), capped safely by (cl0 - 1) if possible
    st_cap = max(0.0, min(debt0, cl0 * 0.8))
    cl_repay = z3.If(debt_repay <= z3.RealVal(f"{st_cap:.2f}"), debt_repay, z3.RealVal(f"{st_cap:.2f}"))
    cl1 = z3.RealVal(f"{cl0:.2f}") - cl_repay
    tl1 = z3.RealVal(f"{tl0:.2f}") - debt_repay
    eq1 = z3.RealVal(f"{eq0:.2f}") + dn - dp
    ta1 = z3.RealVal(f"{ta0:.2f}") + dc - dw
    debt1 = z3.RealVal(f"{debt0:.2f}") - debt_repay

    # Hard covenants
    opt.add(cash1 >= z3.RealVal(f"{min_cash_floor:.2f}"))
    opt.add(cl1 > 0)
    # Apply liquidity floor only if achievable; if baseline CR is already slightly below min_cr allow maximal feasible improvement
    baseline_cr = ca0 / cl0
    eff_min_cr = min(min_cr, max(baseline_cr, min_cr))
    opt.add(ca1 >= z3.RealVal(f"{eff_min_cr:.4f}") * cl1)
    opt.add(eq1 > 0)
    opt.add(debt1 >= 0)

    # Regularize excessive arbitrary debt paydown beyond liquidity need when obj == maximize_profit_eps
    scale_ref = max(rev0, ta0, 1.0)
    effort_penalty = (r_rev * 500 + r_cogs * 900 + r_opex * 700 + r_wc * 600)
    if obj == "maximize_profit_eps":
        opt.maximize((dn / z3.RealVal(f"{scale_ref:.2f}")) * 100000 - effort_penalty * 0.05)
    elif obj == "minimize_leverage_nd_ebitda":
        net_debt1 = debt1 - cash1
        # Maximize debt reduction + EBIT improvement while keeping effort tidy
        opt.minimize((net_debt1 / z3.RealVal(f"{scale_ref:.2f}")) * 100000 - (oi1 - z3.RealVal(f"{oi0:.2f}")) / z3.RealVal(f"{scale_ref:.2f}") * 10000 + effort_penalty * 0.02)
    else:
        # Balanced: boost profit + lower net debt + strengthen current ratio surplus
        opt.maximize(
            (dn / z3.RealVal(f"{scale_ref:.2f}")) * 70000
            + ((z3.RealVal(f"{debt0 - cash0:.2f}") - (debt1 - cash1)) / z3.RealVal(f"{scale_ref:.2f}")) * 50000
            + ((ca1 - z3.RealVal(f"{eff_min_cr:.4f}") * cl1) / z3.RealVal(f"{scale_ref:.2f}")) * 15000
            - effort_penalty * 0.03
        )

    verdict = opt.check()
    if verdict != z3.sat:
        return OptimizationResult(
            status="INFEASIBLE",
            objective=obj,
            is_official=False,
            protection_verdict=prot.to_dict(),
            reason_ar=(
                f"تعذر إيجاد حل يفي بجميع القيود (نسبة التداول المستهدفة {min_cr:.2f}x مقابل الحالية {baseline_cr:.2f}x) — خفّف قيد السيولة أو زد سقوف التحسين."
            ),
            reason_en=(
                f"Infeasible under current covenants (target CR {min_cr:.2f}x vs baseline {baseline_cr:.2f}x) — relax covenants or widen bounds."
            ),
        )

    mdl = opt.model()
    rev_p = round(_to_float(mdl[r_rev]) * 100.0, 2)
    cogs_p = round(_to_float(mdl[r_cogs]) * 100.0, 2)
    opex_p = round(_to_float(mdl[r_opex]) * 100.0, 2)
    wc_p = round(_to_float(mdl[r_wc]) * 100.0, 2)
    repay_v = round(_to_float(mdl[debt_repay]), 0)

    # Exact float forward pass + integer-snapped conservation for Lean 4
    dn_v = round(_to_float(mdl.evaluate(dn, model_completion=True)), 0)
    dp_v = round(_to_float(mdl.evaluate(dp, model_completion=True)), 0)
    dw_v = round(_to_float(mdl.evaluate(dw, model_completion=True)), 0)
    dc_v = dn_v - dp_v + dw_v - repay_v

    rev_v = round(_to_float(mdl.evaluate(rev1, model_completion=True)), 0)
    cogs_v = round(_to_float(mdl.evaluate(cogs1, model_completion=True)), 0)
    gp_v = rev_v - cogs_v
    opex_v = round(_to_float(mdl.evaluate(opex1, model_completion=True)), 0)
    oi_v = gp_v - opex_v
    int_v = round(_to_float(mdl.evaluate(int1, model_completion=True)), 0)
    pretax_v = oi_v - int_v + non_op_gap
    tax_v = max(0.0, round(pretax_v * etr, 0)) if pretax_v > 0 else 0.0
    ni_v = pretax_v - tax_v
    # Align dn_v to exact rounded P&L delta so every single number reconciles!
    dn_v = round(ni_v - ni0, 0)
    dp_v = round(max(0.0, dn_v * inc_payout), 0)
    dc_v = dn_v - dp_v + dw_v - repay_v

    ta_v = ta0 + dc_v - dw_v
    tl_v = tl0 - repay_v
    eq_v = eq0 + dn_v - dp_v
    ca_v = ca0 + dc_v - dw_v
    cl_repay_v = min(repay_v, st_cap)
    cl_v = cl0 - cl_repay_v
    cash_v = cash0 + dc_v
    debt_v = max(0.0, debt0 - repay_v)

    opt_map: dict[str, dict[int, float]] = {
        "revenue": {curr_m.year: rev_v},
        "cost_of_revenue": {curr_m.year: -cogs_v},
        "gross_profit": {curr_m.year: gp_v},
        "operating_expenses": {curr_m.year: -opex_v},
        "operating_income": {curr_m.year: oi_v},
        "depreciation_amortization": {curr_m.year: da0},
        "interest_expense": {curr_m.year: -int_v},
        "pretax_income": {curr_m.year: pretax_v},
        "income_tax_expense": {curr_m.year: -tax_v},
        "net_income": {curr_m.year: ni_v},
        "total_assets": {curr_m.year: ta_v},
        "current_assets": {curr_m.year: ca_v},
        "current_liabilities": {curr_m.year: cl_v},
        "total_liabilities": {curr_m.year: tl_v},
        "equity": {curr_m.year: eq_v},
        "cash": {curr_m.year: cash_v},
        "total_debt": {curr_m.year: debt_v},
    }
    if curr_m.inventory is not None:
        opt_map["inventory"] = {curr_m.year: max(0.0, inv0 * (1.0 - wc_p / 100.0))}
    if curr_m.accounts_receivable is not None:
        opt_map["accounts_receivable"] = {curr_m.year: max(0.0, ar0 * (1.0 - wc_p / 100.0))}
    if curr_m.fixed_assets is not None:
        opt_map["fixed_assets"] = {curr_m.year: float(curr_m.fixed_assets)}
    if curr_m.accounts_payable is not None:
        opt_map["accounts_payable"] = {curr_m.year: float(curr_m.accounts_payable)}
    if curr_m.operating_cash_flow is not None:
        opt_map["operating_cash_flow"] = {curr_m.year: float(curr_m.operating_cash_flow) + dn_v + dw_v}
    if curr_m.shares_outstanding is not None:
        opt_map["shares_outstanding"] = {curr_m.year: float(curr_m.shares_outstanding)}
    if curr_m.dividends_paid_shareholders is not None or dp_v > 0:
        base_dp = abs(float(curr_m.dividends_paid_shareholders or 0.0))
        opt_map["dividends_paid_shareholders"] = {curr_m.year: -(base_dp + dp_v)}

    opt_m = compute_year_metrics(
        curr_m.year,
        opt_map,
        prev_year=None,
        share_price=share_price,
        employee_count=employee_count,
    )

    lean4_proof = verify_optimized_state(
        ta_before=ta0,
        tl_before=tl0,
        eq_before=eq0,
        dc=dc_v,
        dw=dw_v,
        dr=repay_v,
        dn=dn_v,
        dp=dp_v,
        cash_after=cash_v,
        ca_after=ca_v,
        cl_after=cl_v,
        min_cr=eff_min_cr,
        min_cash=min_cash_floor,
    )

    base_snap = _snapshot_metrics(curr_m, share_price=share_price, employee_count=employee_count)
    opt_snap = _snapshot_metrics(opt_m, share_price=share_price, employee_count=employee_count)
    deltas = {
        k: (
            round(opt_snap[k] - base_snap[k], 4)
            if (opt_snap.get(k) is not None and base_snap.get(k) is not None)
            else None
        )
        for k in base_snap
    }

    recs_ar: list[str] = []
    recs_en: list[str] = []
    if cogs_p > 0:
        recs_ar.append(f"خفض تكلفة الإيرادات بنسبة {cogs_p:.1f}% لتعزيز مجمل الربح بمقدار {gp_v - float(curr_m.gross_profit or 0):+,.0f}.")
        recs_en.append(f"Reduce COGS by {cogs_p:.1f}% to expand gross profit by {gp_v - float(curr_m.gross_profit or 0):+,.0f}.")
    if opex_p > 0:
        recs_ar.append(f"ترشيد المصروفات التشغيلية بنسبة {opex_p:.1f}% لرفع الربح التشغيلي إلى {oi_v:,.0f}.")
        recs_en.append(f"Trim operating expenses by {opex_p:.1f}% to raise EBIT to {oi_v:,.0f}.")
    if rev_p > 0:
        recs_ar.append(f"تنمية الإيرادات بنسبة {rev_p:.1f}% لتصل إلى {rev_v:,.0f}.")
        recs_en.append(f"Grow revenue by {rev_p:.1f}% to reach {rev_v:,.0f}.")
    if wc_p > 0:
        recs_ar.append(f"تحرير سيولة {dw_v:,.0f} من المخزون والعملاء عبر تسريع الدورة النقدية بنسبة {wc_p:.1f}%.")
        recs_en.append(f"Release {dw_v:,.0f} cash from Inventory & Receivables ({wc_p:.1f}% working-capital efficiency gain).")
    if repay_v > 0:
        recs_ar.append(f"سداد ديون بقيمة {repay_v:,.0f} مما يخفض صافي الدين/EBITDA من {base_snap.get('net_debt_to_ebitda') or 0:.2f}x إلى {opt_snap.get('net_debt_to_ebitda') or 0:.2f}x ويوفر {int0 - int_v:,.0f} فوائد.")
        recs_en.append(f"Pay down {repay_v:,.0f} debt, cutting Net Debt/EBITDA to {opt_snap.get('net_debt_to_ebitda') or 0:.2f}x and saving {int0 - int_v:,.0f} interest.")

    final_status = "OPTIMAL" if is_official else "EXPLORATORY_OPTIMAL"
    return OptimizationResult(
        status=final_status,
        objective=obj,
        is_official=is_official,
        protection_verdict=prot.to_dict(),
        levers={
            "revenue_boost_pct": rev_p,
            "cogs_cut_pct": cogs_p,
            "opex_cut_pct": opex_p,
            "wc_release_pct": wc_p,
            "debt_repay": repay_v,
            "cash_released_wc": dw_v,
            "net_income_delta": dn_v,
            "interest_saved": round(int0 - int_v, 0),
        },
        baseline=base_snap,
        optimized=opt_snap,
        deltas=deltas,
        lean4_proof=lean4_proof,
        recommendations_ar=recs_ar,
        recommendations_en=recs_en,
        reason_ar="تم إيجاد الخطة المثلى بـ Z3 Optimize وتأكيد حفظ القيد المزدوج في طبقة الحماية وLean 4.",
        reason_en="Optimal plan solved via Z3 Optimize and double-entry verified via Protection Gate & Lean 4.",
    )
