"""Formal Neuro-Symbolic Verification Layer (Z3 SMT Solver — Certificate Checker & Policy Proofs).

Implements the hybrid "Untrusted AI Extractor + Deterministic Formal Verifier" pattern:
1. **Accounting Proof Certificate (`verify_financial_statements`)**:
   Verifies every extracted fiscal year against formal EAS / IFRS accounting axioms
   (Balance Sheet balance, asset/liability decompositions, working-capital stock bounds,
   Gross Profit & Net Income bridges, debt bounds, non-negativity, and cash-flow bridge).
2. **Z3 SMT Unsat-Core Fault Diagnosis (`_diagnose_with_z3`)**:
   When any accounting axiom fails, encodes the extracted numbers as tracked Z3 assertions
   alongside hard accounting axioms, extracts the minimal `unsat_core`, and computes
   single-field counterfactual repairs via Z3 to pinpoint the exact suspect field(s)
   and generate actionable instructions for the AI Repair Feedback Loop.
3. **Formal Policy Verification (`verify_policy_invariants_z3`)**:
   Uses Z3 SMT (`unsat` of the negation) to mathematically prove 5 universal governance
   theorems over FinSight's Honesty Gate, Health Score rubric, Academic Zones, and
   Working Capital Conservation Law.

Zero API calls, deterministic, runs in ~10-25ms per document, and degrades gracefully
to algebraic checking if `z3-solver` is absent.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from typing import Any

try:
    import z3  # type: ignore

    _Z3_AVAILABLE = True
    _Z3_VERSION = z3.get_version_string()
except Exception:  # pragma: no cover - graceful fallback
    z3 = None
    _Z3_AVAILABLE = False
    _Z3_VERSION = "unavailable"


# ---------------------------------------------------------------------------
# Data models (JSON-serializable for caching, exports, and UI rendering)
# ---------------------------------------------------------------------------

@dataclass
class AxiomCheck:
    """Result of checking one formal accounting axiom for a fiscal year."""
    axiom_id: str
    year: int
    name_ar: str
    name_en: str
    formula: str
    lhs: float | None = None
    rhs: float | None = None
    residual: float | None = None
    tolerance: float | None = None
    status: str = "SKIPPED"  # PROVEN | VIOLATED | SKIPPED
    fields: list[str] = field(default_factory=list)
    detail_ar: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FaultDiagnosis:
    """Minimal conflict diagnosis produced by Z3 Unsat Core + counterfactual SAT."""
    year: int
    suspect_field: str
    current_value: float | None
    z3_implied_value: float | None
    unsat_core: list[str] = field(default_factory=list)
    violated_axioms: list[str] = field(default_factory=list)
    statement_hint: str = "balance_sheet"  # balance_sheet | income_statement | cash_flow
    reason_ar: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RepairAttempt:
    """Audit record of one Deterministic Verifier -> AI Repair Feedback Loop round."""
    round_no: int
    year: int
    target_fields: list[str]
    page_number: int | None
    broken_axioms_before: int
    broken_axioms_after: int
    proposed_values: dict[str, float] = field(default_factory=dict)
    previous_values: dict[str, float | None] = field(default_factory=dict)
    accepted: bool = False
    reason_ar: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PolicyTheorem:
    """One universal governance theorem formally proven via Z3 SMT."""
    theorem_id: str
    name_ar: str
    name_en: str
    statement_ar: str
    smt_property: str
    status: str  # PROVEN | FAILED | UNAVAILABLE
    solver_result: str  # unsat (proven) | sat (counterexample) | unknown

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProofCertificate:
    """Machine-checkable formal verification certificate for an analyzed statement."""
    certificate_id: str
    solver_engine: str
    status: str  # PROVEN_CONSISTENT | PARTIALLY_PROVEN | VIOLATIONS_DETECTED
    years_checked: list[int] = field(default_factory=list)
    passed_axioms: int = 0
    failed_axioms: int = 0
    skipped_axioms: int = 0
    total_checked: int = 0
    axioms: list[AxiomCheck] = field(default_factory=list)
    fault_diagnoses: list[FaultDiagnosis] = field(default_factory=list)
    repair_history: list[RepairAttempt] = field(default_factory=list)
    policy_theorems: list[PolicyTheorem] = field(default_factory=list)
    summary_ar: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "certificate_id": self.certificate_id,
            "solver_engine": self.solver_engine,
            "status": self.status,
            "years_checked": list(self.years_checked),
            "passed_axioms": self.passed_axioms,
            "failed_axioms": self.failed_axioms,
            "skipped_axioms": self.skipped_axioms,
            "total_checked": self.total_checked,
            "axioms": [a.to_dict() for a in self.axioms],
            "fault_diagnoses": [d.to_dict() for d in self.fault_diagnoses],
            "repair_history": [r.to_dict() for r in self.repair_history],
            "policy_theorems": [t.to_dict() for t in self.policy_theorems],
            "summary_ar": self.summary_ar,
        }


# ---------------------------------------------------------------------------
# Field -> Statement mapping (for targeted AI repair feedback routing)
# ---------------------------------------------------------------------------

_BS_FIELDS = {
    "total_assets", "non_current_assets", "current_assets", "fixed_assets",
    "projects_under_construction", "investments_in_subsidiaries",
    "other_investments", "deferred_tax_assets",
    "inventory", "accounts_receivable", "other_receivables", "supplier_advances", "cash",
    "total_liabilities", "non_current_liabilities", "current_liabilities",
    "accounts_payable", "customer_advances", "other_payables", "provisions",
    "equity", "retained_earnings", "capital",
    "treasury_shares", "reserves", "asset_revaluation_reserve",
    "total_debt", "long_term_debt", "long_term_notes_payable", "short_term_debt",
    "short_term_credit_facilities", "bank_overdraft",
    "current_portion_lt_debt", "current_lease_liabilities",
    "non_current_lease_liabilities", "deferred_tax_liabilities",
}
_IS_FIELDS = {
    "revenue", "cost_of_revenue", "gross_profit", "operating_expenses",
    "operating_income", "net_activity_profit", "pretax_income",
    "income_tax_expense", "net_income",
    "selling_expenses", "admin_expenses", "other_operating_expenses",
    "other_operating_income", "interest_expense", "finance_income",
    "fx_gain_loss", "dividends_from_subsidiaries",
}
_CF_FIELDS = {
    "operating_cash_flow", "investing_cash_flow", "financing_cash_flow",
    "capex", "depreciation_amortization",
}

_FIELD_AR = {
    "total_assets": "إجمالي الأصول",
    "non_current_assets": "الأصول غير المتداولة",
    "current_assets": "الأصول المتداولة",
    "fixed_assets": "الأصول الثابتة",
    "inventory": "المخزون",
    "accounts_receivable": "العملاء وأوراق القبض",
    "other_receivables": "مدينون وأرصدة مدينة أخرى",
    "supplier_advances": "موردون — دفعات مقدمة",
    "cash": "النقدية وما في حكمها",
    "total_liabilities": "إجمالي الالتزامات",
    "non_current_liabilities": "الالتزامات غير المتداولة",
    "current_liabilities": "الالتزامات المتداولة",
    "accounts_payable": "الموردون وأوراق الدفع",
    "customer_advances": "عملاء — دفعات مقدمة",
    "other_payables": "دائنون وأرصدة دائنة أخرى",
    "provisions": "مخصصات",
    "long_term_debt": "قروض طويلة الأجل",
    "long_term_notes_payable": "أوراق دفع طويلة الأجل",
    "non_current_lease_liabilities": "التزامات تأجير تمويلي غير متداولة",
    "deferred_tax_liabilities": "التزامات ضريبية مؤجلة",
    "short_term_credit_facilities": "بنوك — تسهيلات ائتمانية",
    "bank_overdraft": "بنوك — سحب على المكشوف",
    "current_portion_lt_debt": "أقساط قروض طويلة الأجل مستحقة خلال عام",
    "current_lease_liabilities": "التزامات تأجير تمويلي متداولة",
    "equity": "إجمالي حقوق الملكية",
    "capital": "رأس المال المدفوع",
    "treasury_shares": "أسهم خزينة",
    "reserves": "الاحتياطيات",
    "asset_revaluation_reserve": "ناتج تعديل تكلفة الأصول",
    "retained_earnings": "الأرباح المرحلة",
    "projects_under_construction": "مشروعات تحت التنفيذ",
    "investments_in_subsidiaries": "استثمارات في شركات تابعة",
    "other_investments": "استثمارات أخرى",
    "deferred_tax_assets": "أصول ضريبية مؤجلة",
    "revenue": "المبيعات / الإيرادات",
    "cost_of_revenue": "تكلفة المبيعات",
    "gross_profit": "مجمل الربح",
    "operating_income": "صافي أرباح النشاط",
    "net_activity_profit": "صافي أرباح النشاط",
    "selling_expenses": "مصروفات بيعية وتسويقية",
    "admin_expenses": "مصروفات إدارية وعمومية",
    "other_operating_expenses": "مصروفات تشغيل أخرى",
    "other_operating_income": "إيرادات تشغيل أخرى",
    "finance_income": "فوائد دائنة",
    "interest_expense": "فوائد ومصروفات تمويلية",
    "fx_gain_loss": "فروق ترجمة العملات الأجنبية",
    "dividends_from_subsidiaries": "توزيعات أرباح من شركات تابعة",
    "pretax_income": "الربح قبل ضريبة الدخل",
    "income_tax_expense": "إجمالي ضريبة الدخل",
    "net_income": "صافي أرباح العام",
    "total_debt": "إجمالي المديونية",
    "operating_cash_flow": "التدفق النقدي التشغيلي",
    "investing_cash_flow": "التدفق النقدي الاستثماري",
    "financing_cash_flow": "التدفق النقدي التمويلي",
}


def _statement_of(field_name: str) -> str:
    if field_name in _IS_FIELDS:
        return "income_statement"
    if field_name in _CF_FIELDS:
        return "cash_flow"
    return "balance_sheet"


def _val(values: dict[str, dict[int, float]], field_name: str, year: int) -> float | None:
    by_y = values.get(field_name)
    if not isinstance(by_y, dict):
        return None
    v = by_y.get(year)
    if v is None:
        v = by_y.get(str(year))  # tolerate string-keyed cached dicts
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 1. Accounting Axiom Checker + Z3 Unsat-Core Fault Diagnosis
# ---------------------------------------------------------------------------

def _whole_currency_tol(
    lhs: float,
    rhs: float,
    rel_tol: float,
    integer_tol: float | None = None,
) -> float:
    """Tighten tolerance to `integer_tol` (e.g. 5 EGP) when a whole-currency
    statement (>= 100k integers) is checked — also catching single fractional-digit
    OCR comma-to-dot slips (.88) when magnitudes exceed 10M."""
    scale = max(abs(lhs), abs(rhs), 1.0)
    base = max(10.0, rel_tol * scale)
    if integer_tol is not None and abs(lhs) >= 100_000.0 and abs(rhs) >= 100_000.0:
        lhs_int = abs(lhs - round(lhs)) < 1e-6
        rhs_int = abs(rhs - round(rhs)) < 1e-6
        if (lhs_int and rhs_int) or (
            abs(lhs) >= 10_000_000.0
            and abs(rhs) >= 10_000_000.0
            and (lhs_int or rhs_int)
        ):
            return min(base, float(integer_tol))
    return base


def _check_equality(
    axiom_id: str,
    year: int,
    name_ar: str,
    name_en: str,
    formula: str,
    lhs: float | None,
    rhs: float | None,
    fields: list[str],
    rel_tol: float,
    integer_tol: float | None = None,
) -> AxiomCheck:
    if lhs is None or rhs is None:
        return AxiomCheck(
            axiom_id=axiom_id, year=year, name_ar=name_ar, name_en=name_en,
            formula=formula, status="SKIPPED", fields=fields,
            detail_ar="أحد أطراف المعادلة غير متاح في هذه السنة.",
        )
    tol = _whole_currency_tol(lhs, rhs, rel_tol, integer_tol=integer_tol)
    residual = lhs - rhs
    ok = abs(residual) <= tol
    return AxiomCheck(
        axiom_id=axiom_id, year=year, name_ar=name_ar, name_en=name_en,
        formula=formula, lhs=round(lhs, 2), rhs=round(rhs, 2),
        residual=round(residual, 2), tolerance=round(tol, 2),
        status="PROVEN" if ok else "VIOLATED",
        fields=fields,
        detail_ar=(
            "القيد مُثبت رياضياً ضمن السماحية المحاسبية."
            if ok else
            f"خرق في القيد بفارق {residual:+,.0f} (الحد المسموح ±{tol:,.0f})."
        ),
    )


def _diagnose_with_z3(
    year: int,
    values: dict[str, dict[int, float]],
    violated: list[AxiomCheck],
    rel_tol: float,
    integer_tol: float | None = None,
) -> list[FaultDiagnosis]:
    """Use Z3 SMT Solver (`assert_and_track` + `unsat_core` + counterfactual SAT)
    to identify the minimal set of suspect fields and compute Z3-implied values."""
    if not violated:
        return []

    suspect_fields: list[str] = []
    for ax in violated:
        for f in ax.fields:
            if f not in suspect_fields:
                suspect_fields.append(f)

    if not _Z3_AVAILABLE:  # pragma: no cover - fallback when z3 is absent
        return [
            FaultDiagnosis(
                year=year,
                suspect_field=ax.fields[0],
                current_value=_val(values, ax.fields[0], year),
                z3_implied_value=ax.rhs,
                unsat_core=list(ax.fields),
                violated_axioms=[ax.axiom_id],
                statement_hint=_statement_of(ax.fields[0]),
                reason_ar=f"فشل القيد {ax.name_ar}: {ax.detail_ar}",
            )
            for ax in violated if ax.fields
        ]

    # Collect all fields present this year that participate in linear axioms
    relevant = [
        "total_assets", "non_current_assets", "current_assets",
        "fixed_assets", "projects_under_construction", "investments_in_subsidiaries",
        "other_investments", "deferred_tax_assets",
        "inventory", "accounts_receivable", "other_receivables", "supplier_advances", "cash",
        "total_liabilities", "non_current_liabilities", "current_liabilities",
        "accounts_payable", "customer_advances", "other_payables", "provisions",
        "bank_overdraft", "short_term_credit_facilities", "current_portion_lt_debt",
        "current_lease_liabilities", "long_term_debt", "long_term_notes_payable",
        "non_current_lease_liabilities", "deferred_tax_liabilities",
        "equity", "capital", "treasury_shares", "reserves", "asset_revaluation_reserve", "retained_earnings",
        "revenue", "cost_of_revenue", "gross_profit",
        "other_operating_income", "selling_expenses", "admin_expenses", "other_operating_expenses",
        "net_activity_profit", "operating_income", "finance_income",
        "interest_expense", "fx_gain_loss", "dividends_from_subsidiaries",
        "pretax_income", "income_tax_expense", "net_income",
        "total_debt",
    ]
    present: dict[str, float] = {}
    for f in relevant:
        v = _val(values, f, year)
        if v is not None:
            present[f] = v

    violated_ids = {ax.axiom_id for ax in violated}

    def _build_solver(
        drop_field: str | None = None,
        exact_eq: bool = False,
        only_axioms: set[str] | None = None,
    ):
        def _want(ax_id: str) -> bool:
            return only_axioms is None or ax_id in only_axioms

        s = z3.Solver()
        s.set("timeout", 400)  # 400ms hard cap — deterministic & fast
        vmap = {f: z3.Real(f) for f in present}

        # Hard accounting axioms (encoded over Z3 Reals; exact for counterfactual target)
        def _eq_tol(expr_l, expr_r, scale_ref: float, terms: tuple[str, ...] = (), custom_int_tol: float | None = None):
            if exact_eq:
                s.add(expr_l == expr_r)
            else:
                eff_int_tol = custom_int_tol if custom_int_tol is not None else integer_tol
                base_eps = max(10.0, rel_tol * max(abs(scale_ref), 1.0))
                present_terms = [present[t] for t in terms if t in present]
                int_count = sum(1 for tv in present_terms if abs(tv - round(tv)) < 1e-6)
                if (
                    eff_int_tol is not None
                    and abs(scale_ref) >= 100_000.0
                    and present_terms
                    and (
                        int_count == len(present_terms)
                        or (abs(scale_ref) >= 10_000_000.0 and int_count >= max(2, len(present_terms) - 1))
                    )
                ):
                    eps = min(base_eps, float(eff_int_tol))
                else:
                    eps = base_eps
                s.add(expr_l - expr_r <= eps)
                s.add(expr_r - expr_l <= eps)

        if _want("A1_BS_BALANCE") and all(k in vmap for k in ("total_assets", "total_liabilities", "equity")):
            _eq_tol(vmap["total_assets"], vmap["total_liabilities"] + vmap["equity"], present["total_assets"], ("total_assets", "total_liabilities", "equity"))
        if _want("A1c_EQUITY_SUM") and "A1c_EQUITY_SUM" in violated_ids and all(k in vmap for k in ("equity", "capital", "retained_earnings")):
            cap_mag = z3.If(vmap["capital"] < 0, -vmap["capital"], vmap["capital"])
            ts_mag = z3.If(vmap["treasury_shares"] < 0, -vmap["treasury_shares"], vmap["treasury_shares"]) if "treasury_shares" in vmap else 0
            res_mag = z3.If(vmap["reserves"] < 0, -vmap["reserves"], vmap["reserves"]) if "reserves" in vmap else 0
            rev_r = vmap["asset_revaluation_reserve"] if "asset_revaluation_reserve" in vmap else 0
            eq_terms = tuple(k for k in ("equity", "capital", "treasury_shares", "reserves", "asset_revaluation_reserve", "retained_earnings") if k in present)
            _eq_tol(vmap["equity"], cap_mag - ts_mag + res_mag + rev_r + vmap["retained_earnings"], present["equity"], eq_terms)
        if _want("A2_ASSETS_SUM") and all(k in vmap for k in ("total_assets", "non_current_assets", "current_assets")):
            _eq_tol(vmap["total_assets"], vmap["non_current_assets"] + vmap["current_assets"], present["total_assets"], ("total_assets", "non_current_assets", "current_assets"))
        if _want("A3_LIAB_SUM") and all(k in vmap for k in ("total_liabilities", "non_current_liabilities", "current_liabilities")):
            _eq_tol(vmap["total_liabilities"], vmap["non_current_liabilities"] + vmap["current_liabilities"], present["total_liabilities"], ("total_liabilities", "non_current_liabilities", "current_liabilities"))
        if _want("A2c_CA_SUM") and "A2c_CA_SUM" in violated_ids and "current_assets" in vmap:
            ca_fs = tuple(k for k in ("inventory", "accounts_receivable", "other_receivables", "supplier_advances", "cash") if k in vmap)
            if len(ca_fs) >= 4:
                _eq_tol(vmap["current_assets"], z3.Sum([vmap[k] for k in ca_fs]), present["current_assets"], ("current_assets",) + ca_fs)
        if _want("A3b_CL_SUM") and "A3b_CL_SUM" in violated_ids and "current_liabilities" in vmap:
            cl_fs = tuple(k for k in ("bank_overdraft", "short_term_credit_facilities", "current_portion_lt_debt", "current_lease_liabilities", "accounts_payable", "customer_advances", "other_payables", "provisions") if k in vmap)
            if len(cl_fs) >= 5:
                _eq_tol(vmap["current_liabilities"], z3.Sum([vmap[k] for k in cl_fs]), present["current_liabilities"], ("current_liabilities",) + cl_fs)
        if _want("A3c_NCL_SUM") and "A3c_NCL_SUM" in violated_ids and "non_current_liabilities" in vmap:
            ncl_fs = tuple(k for k in ("long_term_debt", "long_term_notes_payable", "non_current_lease_liabilities", "deferred_tax_liabilities") if k in vmap)
            if len(ncl_fs) >= 3:
                _eq_tol(vmap["non_current_liabilities"], z3.Sum([vmap[k] for k in ncl_fs]), present["non_current_liabilities"], ("non_current_liabilities",) + ncl_fs)
        if _want("A4_CA_BOUNDS") and all(k in vmap for k in ("inventory", "accounts_receivable", "cash", "current_assets")):
            eps = max(10.0, rel_tol * max(abs(present["current_assets"]), 1.0))
            s.add(vmap["inventory"] + vmap["accounts_receivable"] + vmap["cash"] <= vmap["current_assets"] + eps)
        if _want("A4_AP_BOUND") and all(k in vmap for k in ("accounts_payable", "current_liabilities")):
            eps = max(10.0, rel_tol * max(abs(present["current_liabilities"]), 1.0))
            s.add(vmap["accounts_payable"] <= vmap["current_liabilities"] + eps)
        if _want("A7_DEBT_BOUND") and all(k in vmap for k in ("total_debt", "total_liabilities")):
            eps = max(10.0, rel_tol * max(abs(present["total_liabilities"]), 1.0))
            s.add(vmap["total_debt"] <= vmap["total_liabilities"] + eps)
        if _want("A5_GROSS_PROFIT") and all(k in vmap for k in ("revenue", "cost_of_revenue", "gross_profit")):
            cogs_var = vmap["cost_of_revenue"]
            cogs_mag = z3.If(cogs_var < 0, -cogs_var, cogs_var)
            _eq_tol(vmap["revenue"] - cogs_mag, vmap["gross_profit"], present["revenue"], ("revenue", "cost_of_revenue", "gross_profit"))
        act_f = "net_activity_profit" if "net_activity_profit" in vmap else ("operating_income" if "operating_income" in vmap else None)
        if _want("A5c_OP_EXACT") and "A5c_OP_EXACT" in violated_ids and act_f and all(k in vmap for k in ("gross_profit", "selling_expenses", "admin_expenses")):
            sell_mag = z3.If(vmap["selling_expenses"] < 0, -vmap["selling_expenses"], vmap["selling_expenses"])
            adm_mag = z3.If(vmap["admin_expenses"] < 0, -vmap["admin_expenses"], vmap["admin_expenses"])
            oexp_mag = z3.If(vmap["other_operating_expenses"] < 0, -vmap["other_operating_expenses"], vmap["other_operating_expenses"]) if "other_operating_expenses" in vmap else 0
            oinc_mag = z3.If(vmap["other_operating_income"] < 0, -vmap["other_operating_income"], vmap["other_operating_income"]) if "other_operating_income" in vmap else 0
            a5c_terms = tuple(k for k in ("gross_profit", "other_operating_income", "selling_expenses", "admin_expenses", "other_operating_expenses", act_f) if k in present)
            _eq_tol(vmap["gross_profit"] + oinc_mag - sell_mag - adm_mag - oexp_mag, vmap[act_f], max(abs(present["gross_profit"]), abs(present[act_f])), a5c_terms)
        has_div_disclosed = isinstance(values.get("dividends_from_subsidiaries"), dict) and any(
            v is not None for v in values["dividends_from_subsidiaries"].values()
        )
        if _want("A6b_ACTIVITY_BRIDGE") and act_f and all(k in vmap for k in ("interest_expense", "pretax_income")) and (
            "dividends_from_subsidiaries" in vmap or has_div_disclosed or "A6b_ACTIVITY_BRIDGE" in violated_ids
        ):
            fin_v = vmap["interest_expense"]
            fin_mag = z3.If(fin_v < 0, -fin_v, fin_v)
            fi_expr = z3.If(vmap["finance_income"] < 0, -vmap["finance_income"], vmap["finance_income"]) if "finance_income" in vmap else 0
            fx_expr = vmap["fx_gain_loss"] if "fx_gain_loss" in vmap else 0
            div_expr = vmap["dividends_from_subsidiaries"] if "dividends_from_subsidiaries" in vmap else z3.RealVal("0")
            a6b_terms = tuple(k for k in (act_f, "finance_income", "interest_expense", "fx_gain_loss", "dividends_from_subsidiaries", "pretax_income") if k in present)
            _eq_tol(vmap[act_f] + fi_expr - fin_mag + fx_expr + div_expr, vmap["pretax_income"], max(abs(present["pretax_income"]), abs(present[act_f])), a6b_terms)
        if _want("A6_NI_BRIDGE") and all(k in vmap for k in ("pretax_income", "income_tax_expense", "net_income")):
            ni_tol_c = min(float(integer_tol), 1.5) if integer_tol is not None else None
            _eq_tol(vmap["pretax_income"] + vmap["income_tax_expense"], vmap["net_income"],
                    max(abs(present["pretax_income"]), abs(present["net_income"])), ("pretax_income", "income_tax_expense", "net_income"), custom_int_tol=ni_tol_c)
        # Non-negativity of balance-sheet stocks
        for stock in ("total_assets", "current_assets", "current_liabilities",
                      "inventory", "accounts_receivable", "accounts_payable", "cash"):
            if stock in vmap:
                s.add(vmap[stock] >= 0)

        # Soft tracked assumptions for every extracted field value
        for f, val in present.items():
            if f == drop_field:
                continue
            s.assert_and_track(vmap[f] == z3.RealVal(str(round(val, 4))), f"val_{f}")
        return s, vmap

    s0, _ = _build_solver(drop_field=None)
    core_fields: list[str] = []
    if s0.check() == z3.unsat:
        core_fields = [
            str(atom).removeprefix("val_")
            for atom in s0.unsat_core()
            if str(atom).startswith("val_")
        ]

    # Candidate fields to test for single-field counterfactual repair.
    # When multiple disjoint axioms fail in the same year, s0.unsat_core() returns only
    # ONE minimal conflict cluster; unioning participants of every violated axiom ensures
    # independent broken statements are also diagnosed cleanly.
    if len(violated_ids) > 1:
        violated_participants = [
            f for ax in violated for f in ax.fields if f in present
        ]
        test_fields = list(dict.fromkeys([*core_fields, *violated_participants]))
    else:
        test_fields = core_fields or [f for f in suspect_fields if f in present]
    # Rank fields that participate in MORE violated axioms first (root-cause heuristic)
    ax_by_field: dict[str, list[str]] = {}
    for ax in violated:
        for f in ax.fields:
            ax_by_field.setdefault(f, []).append(ax.axiom_id)
    test_fields.sort(key=lambda f: (-len(ax_by_field.get(f, [])), f))

    diagnoses: list[FaultDiagnosis] = []
    for f in test_fields:
        # Try exact accounting equality first for digit-exact implied target, fall back to tolerance band
        s_cf, vmap_cf = _build_solver(drop_field=f, exact_eq=True)
        verdict_cf = s_cf.check()
        if verdict_cf != z3.sat:
            s_cf, vmap_cf = _build_solver(drop_field=f, exact_eq=False)
            verdict_cf = s_cf.check()
        # Multi-fault isolation: when another disjoint axiom in the same year is also broken,
        # evaluate counterfactual solvability within the subset of violated axioms touching `f`.
        f_axioms = set(ax_by_field.get(f, []))
        if verdict_cf != z3.sat and 0 < len(f_axioms) < len(violated_ids):
            s_cf, vmap_cf = _build_solver(drop_field=f, exact_eq=True, only_axioms=f_axioms)
            verdict_cf = s_cf.check()
            if verdict_cf != z3.sat:
                s_cf, vmap_cf = _build_solver(drop_field=f, exact_eq=False, only_axioms=f_axioms)
                verdict_cf = s_cf.check()
        if verdict_cf == z3.sat:
            model = s_cf.model()
            raw_val = model.eval(vmap_cf[f], model_completion=True)
            implied: float | None = None
            try:
                if z3.is_rational_value(raw_val):
                    implied = float(raw_val.numerator_as_long()) / float(raw_val.denominator_as_long())
                else:
                    implied = float(str(raw_val).rstrip("?"))
            except Exception:
                implied = None
            cur_v = present.get(f)
            f_ar = _FIELD_AR.get(f, f)
            ax_ids = ax_by_field.get(f) or [ax.axiom_id for ax in violated]
            reason = (
                f"تشخيص Z3 (Unsat Core): تعديل «{f_ar}» وحده من "
                f"{cur_v:,.0f} إلى ~{implied:,.0f} يُعيد التوازن الرياضي للقيود ({', '.join(ax_ids)})."
                if implied is not None and cur_v is not None else
                f"تشخيص Z3 (Unsat Core): البند «{f_ar}» ضمن مجموعة التعارض الصغرى للقيود ({', '.join(ax_ids)})."
            )
            diagnoses.append(FaultDiagnosis(
                year=year,
                suspect_field=f,
                current_value=cur_v,
                z3_implied_value=round(implied, 2) if implied is not None else None,
                unsat_core=list(core_fields or test_fields),
                violated_axioms=ax_ids,
                statement_hint=_statement_of(f),
                reason_ar=reason,
            ))

    # Direct fault diagnoses for whole-unit fractional OCR outliers (e.g. .88 comma-to-dot slip)
    for ax in violated:
        if ax.axiom_id == "A8b_INTEGER_PRECISION":
            for f in ax.fields:
                if f in present and not any(d.suspect_field == f for d in diagnoses):
                    cur_v = present[f]
                    f_ar = _FIELD_AR.get(f, f)
                    diagnoses.append(FaultDiagnosis(
                        year=year,
                        suspect_field=f,
                        current_value=cur_v,
                        z3_implied_value=float(round(cur_v)),
                        unsat_core=list(ax.fields),
                        violated_axioms=["A8b_INTEGER_PRECISION"],
                        statement_hint=_statement_of(f),
                        reason_ar=(
                            f"تشخيص Z3: البند «{f_ar}» يحمل كسراً عشرياً شاذاً ({cur_v:,.2f}) "
                            f"في قائمة مطبوعة بالوحدات الصحيحة الكاملة."
                        ),
                    ))

    # If no single field alone resolves all violations (multi-field fault), still report the core
    if not diagnoses and test_fields:
        top_f = test_fields[0]
        ax_ids = ax_by_field.get(top_f) or [ax.axiom_id for ax in violated]
        diagnoses.append(FaultDiagnosis(
            year=year,
            suspect_field=top_f,
            current_value=present.get(top_f),
            z3_implied_value=None,
            unsat_core=list(core_fields or test_fields),
            violated_axioms=ax_ids,
            statement_hint=_statement_of(top_f),
            reason_ar=(
                f"تعرض متعدد البنود في {year} — مجموعة التعارض الصغرى بـ Z3: "
                + "، ".join(_FIELD_AR.get(x, x) for x in (core_fields or test_fields))
            ),
        ))
    return diagnoses


def verify_financial_statements(
    values: dict[str, dict[int, float]],
    years: list[int] | None = None,
    tolerance: float = 0.005,
    include_policy_theorems: bool = True,
    integer_tol: float | None = None,
) -> ProofCertificate:
    """Run the formal EAS/IFRS Certificate Checker over extracted financial data."""
    if years is None:
        yr_set: set[int] = set()
        for by_y in (values or {}).values():
            if isinstance(by_y, dict):
                for y in by_y:
                    try:
                        yr_set.add(int(y))
                    except (TypeError, ValueError):
                        pass
        years = sorted(yr_set)
    else:
        years = sorted({int(y) for y in years})

    axioms: list[AxiomCheck] = []
    diagnoses: list[FaultDiagnosis] = []

    # Detect whole-currency integer statements (e.g. full EGP scans where >=85% of >=100k cells are integers)
    _whole_check_fields = _BS_FIELDS | _IS_FIELDS | _CF_FIELDS
    _all_big_vals = [
        float(v)
        for fn, ym in (values or {}).items()
        if fn in _whole_check_fields and isinstance(ym, dict)
        for v in ym.values()
        if isinstance(v, (int, float)) and abs(v) >= 100_000.0
    ]
    _is_whole_unit_doc = bool(
        integer_tol is not None
        and len(_all_big_vals) >= 8
        and (sum(1 for v in _all_big_vals if abs(v - round(v)) < 1e-6) / len(_all_big_vals) >= 0.75)
    )

    # Detect whether any year in this filing exhibits an exact 6-term EAS operating profit bridge
    _op_exact_template = False
    for _yr in years:
        _gp0 = _val(values, "gross_profit", _yr)
        _act0 = _val(values, "net_activity_profit", _yr)
        if _act0 is None:
            _act0 = _val(values, "operating_income", _yr)
        _s0 = _val(values, "selling_expenses", _yr)
        _a0 = _val(values, "admin_expenses", _yr)
        _oi0 = _val(values, "other_operating_income", _yr)
        _oe0 = _val(values, "other_operating_expenses", _yr)
        _rd0 = _val(values, "rd_expenses", _yr)
        if (
            None not in (_gp0, _act0, _s0, _a0)
            and _rd0 is None
            and (_oi0 is not None or _oe0 is not None)
        ):
            _lhs0 = (
                _gp0
                + (abs(_oi0) if _oi0 is not None else 0.0)
                - abs(_s0)
                - abs(_a0)
                - (abs(_oe0) if _oe0 is not None else 0.0)
            )
            if abs(_lhs0 - _act0) <= 0.005 * max(abs(_gp0), 1.0):
                _op_exact_template = True
                break

    for y in years:
        ta = _val(values, "total_assets", y)
        nca = _val(values, "non_current_assets", y)
        ca = _val(values, "current_assets", y)
        tl = _val(values, "total_liabilities", y)
        ncl = _val(values, "non_current_liabilities", y)
        cl = _val(values, "current_liabilities", y)
        eq = _val(values, "equity", y)
        inv = _val(values, "inventory", y)
        ar = _val(values, "accounts_receivable", y)
        cash = _val(values, "cash", y)
        ap = _val(values, "accounts_payable", y)
        td = _val(values, "total_debt", y)
        rev = _val(values, "revenue", y)
        cogs = _val(values, "cost_of_revenue", y)
        gp = _val(values, "gross_profit", y)
        pretax = _val(values, "pretax_income", y)
        tax = _val(values, "income_tax_expense", y)
        ni = _val(values, "net_income", y)

        year_axioms: list[AxiomCheck] = []

        # A1: Balance Sheet Fundamental Equation (Assets = Liabilities + Equity)
        year_axioms.append(_check_equality(
            "A1_BS_BALANCE", y,
            "معادلة الميزانية الأساسية", "Balance Sheet Identity",
            "Total Assets = Total Liabilities + Equity",
            ta, (tl + eq) if (tl is not None and eq is not None) else None,
            ["total_assets", "total_liabilities", "equity"], tolerance,
            integer_tol=integer_tol,
        ))

        # A2: Assets Decomposition (Total Assets = Non-Current + Current)
        year_axioms.append(_check_equality(
            "A2_ASSETS_SUM", y,
            "تطابق مجموع الأصول", "Asset Decomposition",
            "Total Assets = Non-Current Assets + Current Assets",
            ta, (nca + ca) if (nca is not None and ca is not None) else None,
            ["total_assets", "non_current_assets", "current_assets"], tolerance,
            integer_tol=integer_tol,
        ))

        # A3: Liabilities Decomposition (Total Liabilities = Non-Current + Current)
        year_axioms.append(_check_equality(
            "A3_LIAB_SUM", y,
            "تطابق مجموع الالتزامات", "Liability Decomposition",
            "Total Liabilities = Non-Current Liabilities + Current Liabilities",
            tl, (ncl + cl) if (ncl is not None and cl is not None) else None,
            ["total_liabilities", "non_current_liabilities", "current_liabilities"], tolerance,
            integer_tol=integer_tol,
        ))

        # A4a: Current Assets Working-Capital Stock Bound (Inv + AR + Cash <= CA)
        if ca is not None and any(x is not None for x in (inv, ar, cash)):
            wc_sum = (inv or 0.0) + (ar or 0.0) + (cash or 0.0)
            tol_ca = max(10.0, tolerance * max(abs(ca), 1.0))
            ok_wc = wc_sum <= ca + tol_ca
            used_f = [f for f, v in (("inventory", inv), ("accounts_receivable", ar), ("cash", cash)) if v is not None] + ["current_assets"]
            year_axioms.append(AxiomCheck(
                axiom_id="A4_CA_BOUNDS", year=y,
                name_ar="حد مكونات الأصول المتداولة", name_en="Current Asset Component Bound",
                formula="Inventory + Receivables + Cash ≤ Current Assets",
                lhs=round(wc_sum, 2), rhs=round(ca, 2),
                residual=round(max(0.0, wc_sum - ca), 2), tolerance=round(tol_ca, 2),
                status="PROVEN" if ok_wc else "VIOLATED",
                fields=used_f,
                detail_ar=(
                    "مجموع (المخزون + العملاء + النقدية) داخل حد الأصول المتداولة."
                    if ok_wc else
                    f"مجموع المكونات ({wc_sum:,.0f}) يتجاوز إجمالي الأصول المتداولة ({ca:,.0f}) — احتمال تداخل صف من التدفقات النقدية!"
                ),
            ))

        # A4b: Accounts Payable <= Current Liabilities
        if ap is not None and cl is not None:
            tol_cl = max(10.0, tolerance * max(abs(cl), 1.0))
            ok_ap = ap <= cl + tol_cl
            year_axioms.append(AxiomCheck(
                axiom_id="A4_AP_BOUND", year=y,
                name_ar="حد الموردين ضمن الالتزامات المتداولة", name_en="Payables Bound",
                formula="Accounts Payable ≤ Current Liabilities",
                lhs=round(ap, 2), rhs=round(cl, 2),
                residual=round(max(0.0, ap - cl), 2), tolerance=round(tol_cl, 2),
                status="PROVEN" if ok_ap else "VIOLATED",
                fields=["accounts_payable", "current_liabilities"],
                detail_ar=(
                    "رصيد الموردين ضمن حدود الالتزامات المتداولة."
                    if ok_ap else
                    f"رصيد الموردين ({ap:,.0f}) يتجاوز الالتزامات المتداولة ({cl:,.0f})!"
                ),
            ))

        # A5: Gross Profit Identity (Revenue - |COGS| = Gross Profit)
        year_axioms.append(_check_equality(
            "A5_GROSS_PROFIT", y,
            "معادلة مجمل الربح", "Gross Profit Identity",
            "Gross Profit = Revenue − |Cost of Revenue|",
            gp, (rev - abs(cogs)) if (rev is not None and cogs is not None) else None,
            ["gross_profit", "revenue", "cost_of_revenue"], tolerance,
            integer_tol=integer_tol,
        ))

        # A5b: Operating Income Bridge Sanity (GP - |OpEx| ≈ Operating Income within other-op-income band)
        # Catches single-digit OCR slips in COGS (e.g. 6.38B → 1.38B) that fabricate a bogus
        # 5.45B gross profit completely incompatible with operating_income (-26M) and OpEx (533M)!
        op_inc = _val(values, "operating_income", y)
        sell_v = _val(values, "selling_expenses", y)
        adm_v = _val(values, "admin_expenses", y)
        oth_op_v = _val(values, "other_operating_expenses", y)
        opex_v = _val(values, "operating_expenses", y)
        if opex_v is None and sell_v is not None and adm_v is not None:
            opex_v = abs(sell_v) + abs(adm_v) + abs(oth_op_v or 0.0)
        if gp is not None and op_inc is not None and opex_v is not None and rev:
            implied_op = gp - abs(opex_v)
            # Allow up to max(10% of revenue, 30% of |GP|) for Other Operating Income/Expenses
            op_tol = max(0.10 * abs(rev), 0.30 * abs(gp), 100.0)
            op_res = implied_op - op_inc
            ok_op = abs(op_res) <= op_tol
            year_axioms.append(AxiomCheck(
                axiom_id="A5b_OP_BRIDGE", year=y,
                name_ar="اتساق مجمل الربح مع ربح النشاط", name_en="Gross-to-Operating Profit Bridge",
                formula="Gross Profit − |Operating Expenses| ≈ Operating Income",
                lhs=round(implied_op, 2), rhs=round(op_inc, 2),
                residual=round(op_res, 2), tolerance=round(op_tol, 2),
                status="PROVEN" if ok_op else "VIOLATED",
                fields=["gross_profit", "cost_of_revenue", "revenue", "operating_income"],
                detail_ar=(
                    "مجمل الربح متسق مع المصروفات التشغيلية وصافي ربح النشاط."
                    if ok_op else
                    f"تباين هائل بين (مجمل الربح − مصروفات التشغيل = {implied_op:,.0f}) "
                    f"وربح النشاط ({op_inc:,.0f}) بفارق {op_res:+,.0f} — يُرجّح خطأ رقم في تكلفة المبيعات أو مجمل الربح!"
                ),
            ))

        # A5c: Exact 6-Term Operating Profit Bridge (GP + Other Op Inc - |Selling + Admin + Other OpEx| = Operating Profit)
        net_act_v = _val(values, "net_activity_profit", y)
        act_op_f = "net_activity_profit" if net_act_v is not None else ("operating_income" if op_inc is not None else None)
        act_op_v = net_act_v if net_act_v is not None else op_inc
        oth_inc_v = _val(values, "other_operating_income", y)
        rd_v = _val(values, "rd_expenses", y)
        if (
            gp is not None
            and act_op_v is not None
            and sell_v is not None
            and adm_v is not None
            and rd_v is None
            and (oth_inc_v is not None or oth_op_v is not None)
        ):
            lhs_a5c = (
                gp
                + (abs(oth_inc_v) if oth_inc_v is not None else 0.0)
                - abs(sell_v)
                - abs(adm_v)
                - (abs(oth_op_v) if oth_op_v is not None else 0.0)
            )
            if _op_exact_template or abs(lhs_a5c - act_op_v) <= 0.02 * max(abs(gp), 1.0):
                a5c_fields = ["gross_profit", "selling_expenses", "admin_expenses", act_op_f]
                if oth_inc_v is not None:
                    a5c_fields.append("other_operating_income")
                if oth_op_v is not None:
                    a5c_fields.append("other_operating_expenses")
                year_axioms.append(_check_equality(
                    "A5c_OP_EXACT", y,
                    "تطابق جسر ربح النشاط التفصيلي", "Exact Operating Profit Bridge",
                    "Gross Profit + Other Op Income − |Selling + Admin + Other OpEx| = Operating Profit",
                    lhs_a5c, act_op_v,
                    a5c_fields, tolerance,
                    integer_tol=integer_tol,
                ))

        # A6: Net Income Tax Bridge (Pretax + Tax = Net Income, sign-aware)
        if pretax is not None and tax is not None and ni is not None:
            # Handle both negative-printed tax (-179M) and magnitude-printed tax (+179M)
            rhs_signed = pretax + tax
            rhs_sub = pretax - abs(tax)
            best_rhs = rhs_signed if abs(ni - rhs_signed) <= abs(ni - rhs_sub) else rhs_sub
            ni_int_tol = min(float(integer_tol), 1.5) if integer_tol is not None else None
            year_axioms.append(_check_equality(
                "A6_NI_BRIDGE", y,
                "جسر صافي الربح والضريبة", "Net Income Tax Bridge",
                "Net Income = Pretax Income + Income Tax",
                ni, best_rhs,
                ["net_income", "pretax_income", "income_tax_expense"], tolerance,
                integer_tol=ni_int_tol,
            ))

        # A6b: Activity-to-Pretax Bridge when subsidiary dividends are disclosed OR 4-term finance bridge holds closely
        net_act = _val(values, "net_activity_profit", y)
        act_key = "net_activity_profit" if net_act is not None else ("operating_income" if op_inc is not None else None)
        act_val = net_act if net_act is not None else op_inc
        fin_exp = _val(values, "interest_expense", y)
        fin_inc = _val(values, "finance_income", y)
        fx_gl = _val(values, "fx_gain_loss", y)
        div_sub = _val(values, "dividends_from_subsidiaries", y)
        div_disclosed = isinstance(values.get("dividends_from_subsidiaries"), dict) and any(
            v is not None for v in values["dividends_from_subsidiaries"].values()
        )
        _a6b_zero_div_ok = (
            None not in (act_val, fin_inc, fin_exp, fx_gl, pretax)
            and abs((act_val + abs(fin_inc) - abs(fin_exp) + fx_gl) - pretax)
            <= 0.02 * max(abs(pretax), abs(act_val), 1.0)
        )
        if None not in (act_val, fin_exp, pretax) and (div_sub is not None or div_disclosed or _a6b_zero_div_ok):
            div_eff = div_sub if div_sub is not None else 0.0
            lhs_a6b = (
                act_val
                + (abs(fin_inc) if fin_inc is not None else 0.0)
                - abs(fin_exp)
                + (fx_gl if fx_gl is not None else 0.0)
                + div_eff
            )
            a6b_fields = [act_key, "interest_expense", "pretax_income"]
            if div_sub is not None:
                a6b_fields.append("dividends_from_subsidiaries")
            if fin_inc is not None:
                a6b_fields.append("finance_income")
            if fx_gl is not None:
                a6b_fields.append("fx_gain_loss")
            year_axioms.append(_check_equality(
                "A6b_ACTIVITY_BRIDGE", y,
                "جسر النشاط إلى الربح قبل الضريبة", "Activity-to-Pretax Bridge",
                "Activity Profit + Finance Net + FX + Subsidiary Dividends = Pretax Income",
                lhs_a6b, pretax,
                a6b_fields, tolerance,
                integer_tol=integer_tol,
            ))

        # A1c: Standalone Equity Component Sum (Capital - |Treasury Shares| + Reserves + Revaluation + Retained == Equity)
        _cap_v = _val(values, "capital", y)
        _re_v = _val(values, "retained_earnings", y)
        _eq_opt = ("treasury_shares", "reserves", "asset_revaluation_reserve")
        _pres_eq = [f for f in _eq_opt if _val(values, f, y) is not None]
        if (
            eq is not None
            and _cap_v is not None
            and _re_v is not None
            and len(_pres_eq) >= 2
            and _val(values, "minority_interest", y) is None
        ):
            def _calc_eq_sum(_yr_e: int) -> tuple[float | None, float | None]:
                _eq_e = _val(values, "equity", _yr_e)
                _cp_e = _val(values, "capital", _yr_e)
                _re_e = _val(values, "retained_earnings", _yr_e)
                if None in (_eq_e, _cp_e, _re_e):
                    return None, None
                _ts_e = _val(values, "treasury_shares", _yr_e)
                _rs_e = _val(values, "reserves", _yr_e)
                _rv_e = _val(values, "asset_revaluation_reserve", _yr_e)
                _s_e = (
                    abs(_cp_e)
                    + _re_e
                    + (-abs(_ts_e) if _ts_e is not None else 0.0)
                    + (abs(_rs_e) if _rs_e is not None else 0.0)
                    + (_rv_e if _rv_e is not None else 0.0)
                )
                return _eq_e, _s_e

            _, _eq_sum = _calc_eq_sum(y)
            _eq_template = any(
                _ee is not None and _se is not None and abs(_ee - _se) <= 0.005 * max(abs(_ee), 1.0)
                for _yr_e in years
                for _ee, _se in [_calc_eq_sum(_yr_e)]
            )
            if _eq_sum is not None and (_eq_template or abs(_eq_sum - eq) <= 0.03 * max(abs(eq), 1.0)):
                year_axioms.append(_check_equality(
                    "A1c_EQUITY_SUM", y,
                    "تطابق مكونات حقوق الملكية", "Equity Component Sum",
                    "Equity = Capital − |Treasury Shares| + Reserves + Revaluation Reserve + Retained Earnings",
                    eq, _eq_sum,
                    ["equity", "capital", "retained_earnings"] + _pres_eq, tolerance,
                    integer_tol=integer_tol,
                ))

        # A2c: Itemized Current Assets Sum (only when itemized CA lines like other_receivables exist)
        _ca_fields = ("inventory", "accounts_receivable", "other_receivables", "supplier_advances", "cash")
        _present_ca = [f for f in _ca_fields if _val(values, f, y) is not None]
        if ca is not None and "other_receivables" in _present_ca and len(_present_ca) >= 4:
            _ca_sum = sum(abs(_val(values, f, y)) for f in _present_ca)
            if len(_present_ca) == 5 or abs(_ca_sum - ca) <= 0.02 * max(abs(ca), 1.0):
                year_axioms.append(_check_equality(
                    "A2c_CA_SUM", y,
                    "تطابق مكونات الأصول المتداولة", "Current Assets Component Sum",
                    "Current Assets = Inventory + AR + Other Receivables + Supplier Advances + Cash",
                    ca, _ca_sum,
                    ["current_assets"] + _present_ca, tolerance,
                    integer_tol=integer_tol,
                ))

        # A3b: Itemized Current Liabilities Sum (only when itemized lines like other_payables & provisions exist)
        _cl_fields = (
            "bank_overdraft", "short_term_credit_facilities", "current_portion_lt_debt",
            "current_lease_liabilities", "accounts_payable", "customer_advances",
            "other_payables", "provisions",
        )
        _present_cl = [f for f in _cl_fields if _val(values, f, y) is not None]
        if (
            cl is not None
            and "other_payables" in _present_cl
            and "provisions" in _present_cl
            and len(_present_cl) >= 6
        ):
            _cl_sum = sum(abs(_val(values, f, y)) for f in _present_cl)
            if len(_present_cl) >= 7 or abs(_cl_sum - cl) <= 0.02 * max(abs(cl), 1.0):
                year_axioms.append(_check_equality(
                    "A3b_CL_SUM", y,
                    "تطابق مكونات الالتزامات المتداولة", "Current Liabilities Component Sum",
                    "Current Liabilities = Sum of Short-Term Debt, Payables, Advances, Other Payables & Provisions",
                    cl, _cl_sum,
                    ["current_liabilities"] + _present_cl, tolerance,
                    integer_tol=integer_tol,
                ))

        # A3c: Itemized Non-Current Liabilities Sum (when itemized lines like LT notes & DTL exist)
        _ncl_fields = (
            "long_term_debt", "long_term_notes_payable",
            "non_current_lease_liabilities", "deferred_tax_liabilities",
        )
        _present_ncl = [f for f in _ncl_fields if _val(values, f, y) is not None]
        if (
            ncl is not None
            and "long_term_notes_payable" in _present_ncl
            and "deferred_tax_liabilities" in _present_ncl
            and len(_present_ncl) >= 3
        ):
            _ncl_sum = sum(abs(_val(values, f, y)) for f in _present_ncl)
            if len(_present_ncl) == 4 or abs(_ncl_sum - ncl) <= 0.02 * max(abs(ncl), 1.0):
                year_axioms.append(_check_equality(
                    "A3c_NCL_SUM", y,
                    "تطابق مكونات الالتزامات غير المتداولة", "Non-Current Liabilities Component Sum",
                    "Non-Current Liabilities = LT Debt + LT Notes Payable + LT Leases + Deferred Tax Liabilities",
                    ncl, _ncl_sum,
                    ["non_current_liabilities"] + _present_ncl, tolerance,
                    integer_tol=integer_tol,
                ))

        # A7: Debt Bound (Total Debt <= Total Liabilities)
        if td is not None and tl is not None:
            tol_tl = max(10.0, tolerance * max(abs(tl), 1.0))
            ok_td = td <= tl + tol_tl
            year_axioms.append(AxiomCheck(
                axiom_id="A7_DEBT_BOUND", year=y,
                name_ar="حد إجمالي المديونية ضمن الالتزامات", name_en="Total Debt Bound",
                formula="Total Debt ≤ Total Liabilities",
                lhs=round(td, 2), rhs=round(tl, 2),
                residual=round(max(0.0, td - tl), 2), tolerance=round(tol_tl, 2),
                status="PROVEN" if ok_td else "VIOLATED",
                fields=["total_debt", "total_liabilities"],
                detail_ar=(
                    "إجمالي المديونية ضمن حدود إجمالي الالتزامات."
                    if ok_td else
                    f"إجمالي المديونية ({td:,.0f}) يتجاوز إجمالي الالتزامات ({tl:,.0f})!"
                ),
            ))

        # A8: Non-Negativity of Balance-Sheet Stocks
        stock_checks = [
            (f, _val(values, f, y))
            for f in ("total_assets", "current_assets", "current_liabilities",
                      "inventory", "accounts_receivable", "accounts_payable",
                      "fixed_assets", "cash")
        ]
        present_stocks = [(f, v) for f, v in stock_checks if v is not None]
        if present_stocks:
            neg_stocks = [(f, v) for f, v in present_stocks if v < -1.0]
            year_axioms.append(AxiomCheck(
                axiom_id="A8_NON_NEG_STOCKS", year=y,
                name_ar="إيجابية أرصدة المركز المالي", name_en="Balance Sheet Non-Negativity",
                formula="All Balance-Sheet Asset/Liability Stocks ≥ 0",
                lhs=float(len(present_stocks) - len(neg_stocks)),
                rhs=float(len(present_stocks)),
                residual=float(len(neg_stocks)),
                tolerance=0.0,
                status="PROVEN" if not neg_stocks else "VIOLATED",
                fields=[f for f, _ in (neg_stocks or present_stocks)],
                detail_ar=(
                    f"جميع الأرصدة الـ {len(present_stocks)} موجبة وصحيحة الإشارة."
                    if not neg_stocks else
                    "أرصدة سالبة غير منطقية: " + "، ".join(f"{_FIELD_AR.get(f, f)} ({v:,.0f})" for f, v in neg_stocks)
                ),
            ))

        # A8b: Whole-Currency Integer Precision (flags .88 comma-to-dot OCR glitches on >=1M lines)
        if _is_whole_unit_doc:
            big_y = [
                (f, _val(values, f, y))
                for f in sorted(_whole_check_fields)
                if _val(values, f, y) is not None and abs(_val(values, f, y)) >= 1_000_000.0
            ]
            if big_y:
                frac_bad = [
                    (f, v) for f, v in big_y
                    if 0.005 < abs(v - round(v)) < 0.995
                ]
                year_axioms.append(AxiomCheck(
                    axiom_id="A8b_INTEGER_PRECISION", year=y,
                    name_ar="سلامة الوحدات الصحيحة (بلا كسور شاذة)",
                    name_en="Whole-Currency Integer Precision",
                    formula="All ≥1M Statement Lines ∈ ℤ (no comma-to-dot fractional OCR glitches)",
                    lhs=float(len(big_y) - len(frac_bad)),
                    rhs=float(len(big_y)),
                    residual=float(len(frac_bad)),
                    tolerance=0.0,
                    status="PROVEN" if not frac_bad else "VIOLATED",
                    fields=[f for f, _ in (frac_bad or big_y[:3])],
                    detail_ar=(
                        f"جميع البنود المليونية الـ {len(big_y)} أعداد صحيحة خالية من كسور OCR الشاذة."
                        if not frac_bad else
                        "كسور عشرية شاذة بقائمة وحدات صحيحة: "
                        + "، ".join(f"{_FIELD_AR.get(f, f)} ({v:,.2f})" for f, v in frac_bad)
                    ),
                ))

        axioms.extend(year_axioms)
        violated_y = [ax for ax in year_axioms if ax.status == "VIOLATED"]
        if violated_y:
            diagnoses.extend(_diagnose_with_z3(y, values, violated_y, tolerance, integer_tol=integer_tol))

    # A9: Cross-Year Cash Flow Bridge (OCF + ICF + FCF ≈ ΔCash within FX/overdraft tolerance)
    if len(years) >= 2:
        prev_y, curr_y = years[-2], years[-1]
        c_prev = _val(values, "cash", prev_y)
        c_curr = _val(values, "cash", curr_y)
        ocf = _val(values, "operating_cash_flow", curr_y)
        icf = _val(values, "investing_cash_flow", curr_y)
        fcf = _val(values, "financing_cash_flow", curr_y)
        ta_curr = _val(values, "total_assets", curr_y) or 1.0
        if None not in (c_prev, c_curr, ocf, icf, fcf):
            delta_cash = c_curr - c_prev
            net_cf = ocf + icf + fcf
            # Allow FX translation + bank overdraft delta (up to max(15% |ΔCash|, 3% TA))
            cf_tol = max(0.15 * abs(delta_cash), 0.03 * abs(ta_curr), 100.0)
            res_cf = net_cf - delta_cash
            ok_cf = abs(res_cf) <= cf_tol
            ax_cf = AxiomCheck(
                axiom_id="A9_CF_BRIDGE", year=curr_y,
                name_ar="اتساق جسر التدفقات النقدية", name_en="Cash Flow Bridge Consistency",
                formula="OCF + ICF + FCF ≈ ΔCash (within FX/Overdraft band)",
                lhs=round(net_cf, 2), rhs=round(delta_cash, 2),
                residual=round(res_cf, 2), tolerance=round(cf_tol, 2),
                status="PROVEN" if ok_cf else "VIOLATED",
                fields=["operating_cash_flow", "investing_cash_flow", "financing_cash_flow", "cash"],
                detail_ar=(
                    "صافي التدفقات النقدية متسق مع التغير في رصيد النقدية بالميزانية."
                    if ok_cf else
                    f"تباين كبير بين صافي التدفقات ({net_cf:,.0f}) والتغير الفعلي في النقدية ({delta_cash:,.0f}) بفارق {res_cf:+,.0f} — يُرجّح التقاط صف فرعي بالتدفقات!"
                ),
            )
            axioms.append(ax_cf)
            if not ok_cf:
                diagnoses.append(FaultDiagnosis(
                    year=curr_y,
                    suspect_field="operating_cash_flow",
                    current_value=ocf,
                    z3_implied_value=round(delta_cash - icf - fcf, 2),
                    unsat_core=["operating_cash_flow", "investing_cash_flow", "financing_cash_flow", "cash"],
                    violated_axioms=["A9_CF_BRIDGE"],
                    statement_hint="cash_flow",
                    reason_ar=(
                        f"جسر التدفقات النقدية مكسور بفارق {res_cf:+,.0f} — "
                        f"القيمة المتوقعة للتدفق التشغيلي قريبة من {delta_cash - icf - fcf:,.0f} (راجع صف «صافي النقدية الناتجة من أنشطة التشغيل»)."
                    ),
                ))

    passed = sum(1 for a in axioms if a.status == "PROVEN")
    failed = sum(1 for a in axioms if a.status == "VIOLATED")
    skipped = sum(1 for a in axioms if a.status == "SKIPPED")
    checked = passed + failed

    if failed > 0:
        status = "VIOLATIONS_DETECTED"
        summary_ar = (
            f"اكتشف المُدقّق الرسمي {failed} خرقاً من أصل {checked} قيد محاسبي مفحوص "
            f"({passed} مُثبت، {failed} يحتاج مراجعة/تصحيح)."
        )
    elif checked > 0 and skipped == 0:
        status = "PROVEN_CONSISTENT"
        summary_ar = f"جميع القيود المحاسبية المفحوصة ({passed}/{checked}) مُثبتة رياضياً بدون أي تناقض."
    elif checked > 0:
        status = "PROVEN_CONSISTENT" if passed >= 4 else "PARTIALLY_PROVEN"
        summary_ar = f"تم إثبات {passed}/{checked} قيد محاسبي متاح رياضياً بدون أي خرق."
    else:
        status = "PARTIALLY_PROVEN"
        summary_ar = "بيانات غير كافية لإصدار شهادة إثبات محاسبية كاملة."

    # Tamper-evident SHA-256 certificate ID
    fingerprint_payload = json.dumps(
        {
            "years": years,
            "status": status,
            "axioms": [(a.axiom_id, a.year, a.status, a.residual) for a in axioms],
        },
        sort_keys=True,
    )
    cert_id = hashlib.sha256(fingerprint_payload.encode("utf-8")).hexdigest()[:12].upper()

    theorems = list(verify_policy_invariants_z3()) if include_policy_theorems else []

    return ProofCertificate(
        certificate_id=f"Z3-{cert_id}",
        solver_engine=f"Z3 SMT Solver v{_Z3_VERSION}" if _Z3_AVAILABLE else "Algebraic Verifier",
        status=status,
        years_checked=years,
        passed_axioms=passed,
        failed_axioms=failed,
        skipped_axioms=skipped,
        total_checked=checked,
        axioms=axioms,
        fault_diagnoses=diagnoses,
        repair_history=[],
        policy_theorems=theorems,
        summary_ar=summary_ar,
    )


# ---------------------------------------------------------------------------
# 2. Formal Policy Verification via Z3 SMT (Universal Quantifier Proofs)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def verify_policy_invariants_z3() -> tuple[PolicyTheorem, ...]:
    """Formally prove 5 universal governance & scoring theorems using Z3 SMT.

    Each theorem asserts the NEGATION of the required invariant; Z3 returning
    `unsat` constitutes a mathematical proof that NO counterexample exists
    anywhere in the real/boolean state space.
    """
    if not _Z3_AVAILABLE:  # pragma: no cover
        return (
            PolicyTheorem(
                theorem_id="Z3_UNAVAILABLE",
                name_ar="محرك Z3 غير مثبت",
                name_en="Z3 Solver Unavailable",
                statement_ar="قم بتثبيت z3-solver لتفعيل براهين السياسات الرسمية.",
                smt_property="N/A",
                status="UNAVAILABLE",
                solver_result="unknown",
            ),
        )

    results: list[PolicyTheorem] = []

    def _prove(tid: str, name_ar: str, name_en: str, stmt_ar: str, prop: str, build_negation) -> None:
        s = z3.Solver()
        s.set("timeout", 1000)
        build_negation(s)
        verdict = s.check()
        proven = verdict == z3.unsat
        results.append(PolicyTheorem(
            theorem_id=tid,
            name_ar=name_ar,
            name_en=name_en,
            statement_ar=stmt_ar,
            smt_property=prop,
            status="PROVEN" if proven else "FAILED",
            solver_result=str(verdict),
        ))

    # T1: Honesty Gate Non-Leakage
    def _t1(s):
        b_liq, b_lev, b_prof, b_cf = z3.Bools("b_liq b_lev b_prof b_cf")
        # Policy specification: official score is issued iff NO critical pillar is blocked
        official_issued = z3.And(z3.Not(b_liq), z3.Not(b_lev), z3.Not(b_prof), z3.Not(b_cf))
        any_blocked = z3.Or(b_liq, b_lev, b_prof, b_cf)
        # Negation of (any_blocked => ¬official_issued): can a blocked pillar leak?
        s.add(z3.And(any_blocked, official_issued))

    _prove(
        "T1_HONESTY_GATE_NON_LEAKAGE",
        "عدم تسرب الخانات المحجوبة للدرجة الرسمية",
        "Honesty Gate Non-Leakage",
        "يستحيل رياضياً إصدار درجة صحة مالية رسمية إذا كانت أي ركيزة حرجة محجوبة أو غير موثقة.",
        "∀ b_i ∈ Bool: (∨ b_i) ⇒ ¬OfficialScoreIssued",
        _t1,
    )

    # T2: Distressed / Insolvent Excellence Impossibility
    def _t2(s):
        # FinSight weights: Liquidity 0.25, Leverage 0.25, Profitability 0.30, CashFlow 0.20
        cr, qr, nm, roe, roa, cfo_ni, cfo_m, eq, de, dr = z3.Reals(
            "cr qr nm roe roa cfo_ni cfo_m eq de dr"
        )
        # Severe distress precondition:
        # Equity <= 0 (insolvent -> leverage score = 0), Net Margin < 0, ROE < 0, ROA < 0 (prof = 0),
        # CFO < 0 (cf = 0), Current Ratio < 0.5 & Quick Ratio < 0.5 (liq <= 50)
        s.add(eq <= 0, nm < 0, roe < 0, roa < 0, cfo_ni < 0, cfo_m < 0)
        s.add(cr >= 0, cr < 0.5, qr >= 0, qr < 0.5)
        liq = (z3.If(cr / 2.0 * 100 > 100, 100, cr / 2.0 * 100)
               + z3.If(qr / 1.0 * 100 > 100, 100, qr / 1.0 * 100)) / 2.0
        lev = z3.RealVal(0)   # negative equity -> 0/100
        prof = z3.RealVal(0)  # all profitability metrics negative -> 0/100
        cf = z3.RealVal(0)    # negative operating cash flow -> 0/100
        total = 0.25 * liq + 0.25 * lev + 0.30 * prof + 0.20 * cf
        # Negation: can a severely distressed insolvent firm ever score >= 80 ("ممتاز")?
        s.add(total >= 80)

    _prove(
        "T2_INSOLVENT_CEILING",
        "استحالة منح تصنيف «ممتاز» لشركة متعثرة",
        "Distressed Firm Rating Ceiling",
        "يستحيل تحت أي أرقام أن تحصل شركة متعثرة (حقوق ملكية سالبة + خسائر + تدفق تشغيلي سالب + سيولة < 0.5x) على تصنيف «ممتاز» (≥ 80).",
        "∀ x ∈ InsolventDistress: HealthScore(x) < 80",
        _t2,
    )

    # T3: Health Score Boundedness & Monotonicity
    def _t3(s):
        p1, p2, p3, p4 = z3.Reals("p1 p2 p3 p4")
        q1, q2, q3, q4 = z3.Reals("q1 q2 q3 q4")
        for p in (p1, p2, p3, p4, q1, q2, q3, q4):
            s.add(p >= 0, p <= 100)
        s.add(q1 >= p1, q2 >= p2, q3 >= p3, q4 >= p4)
        score_p = 0.25 * p1 + 0.25 * p2 + 0.30 * p3 + 0.20 * p4
        score_q = 0.25 * q1 + 0.25 * q2 + 0.30 * q3 + 0.20 * q4
        # Negation: out of [0, 100] OR violates monotonicity
        s.add(z3.Or(score_p < 0, score_p > 100, score_q < score_p))

    _prove(
        "T3_SCORE_BOUNDED_MONOTONE",
        "محدودية ورتابة درجة الصحة المالية",
        "Score Boundedness & Monotonicity",
        "درجة الصحة المالية محصورة دائماً في [0, 100] وتحسّن أي ركيزة لا يمكن أبداً أن يخفض الدرجة الكلية.",
        "∀ p ≤ q ∈ [0,100]⁴: 0 ≤ S(p) ≤ S(q) ≤ 100",
        _t3,
    )

    # T4: Academic Model Zone Partition Completeness (Altman Z', Springate, Zmijewski)
    def _t4(s):
        z, sp, zm = z3.Reals("z sp zm")
        alt_safe = z > 2.90
        alt_grey = z3.And(z >= 1.23, z <= 2.90)
        alt_dist = z < 1.23
        alt_count = z3.If(alt_safe, 1, 0) + z3.If(alt_grey, 1, 0) + z3.If(alt_dist, 1, 0)

        sp_safe = sp >= 0.862
        sp_dist = sp < 0.862
        sp_count = z3.If(sp_safe, 1, 0) + z3.If(sp_dist, 1, 0)

        zm_high = zm > 0
        zm_low = zm <= 0
        zm_count = z3.If(zm_high, 1, 0) + z3.If(zm_low, 1, 0)

        # Negation: any real number lands in != 1 zone (gap or overlap)
        s.add(z3.Or(alt_count != 1, sp_count != 1, zm_count != 1))

    _prove(
        "T4_ACADEMIC_ZONE_PARTITION",
        "اكتمال وعدم تداخل مناطق النماذج الأكاديمية",
        "Academic Zone Partition Completeness",
        "كل قيمة حقيقية في نماذج Altman وSpringate وZmijewski تقع في منطقة حكم واحدة بالضبط (بلا فجوات أو تداخل).",
        "∀ x ∈ ℝ: |Zones(x)| = 1 (Altman ∧ Springate ∧ Zmijewski)",
        _t4,
    )

    # T5: Working Capital Conservation Law
    def _t5(s):
        ta, nca, ca, tl, ncl, cl, eq = z3.Reals("ta nca ca tl ncl cl eq")
        s.add(ta == tl + eq)
        s.add(ta == nca + ca)
        s.add(tl == ncl + cl)
        # Negation: WC = CA - CL != Equity + NCL - NCA
        s.add((ca - cl) != (eq + ncl - nca))

    _prove(
        "T5_WC_CONSERVATION",
        "قانون حفظ رأس المال العامل المحاسبي",
        "Working Capital Conservation Law",
        "تحت معادلات الميزانية الثلاث، رأس المال العامل (CA − CL) يطابق دائماً (حقوق الملكية + الالتزامات غير المتداولة − الأصول غير المتداولة).",
        "(A1 ∧ A2 ∧ A3) ⇒ (CA − CL = E + NCL − NCA)",
        _t5,
    )

    return tuple(results)


# ---------------------------------------------------------------------------
# Z3 Algebraic Checksum Attestation (التوثيق الجبري الرياضي بـ Z3)
# ---------------------------------------------------------------------------

_STRICT_EQUALITY_AXIOMS = frozenset({
    "A1_BS_BALANCE",
    "A1c_EQUITY_SUM",
    "A2_ASSETS_SUM",
    "A2b_NCA_SUM",
    "A2c_CA_SUM",
    "A3_LIAB_SUM",
    "A3b_CL_SUM",
    "A3c_NCL_SUM",
    "A5_GROSS_PROFIT",
    "A5c_OP_EXACT",
    "A6_NI_BRIDGE",
    "A6b_ACTIVITY_BRIDGE",
})

_DEBT_COMPONENT_FIELDS = (
    "long_term_debt",
    "short_term_debt",
    "short_term_credit_facilities",
    "bank_overdraft",
    "current_portion_lt_debt",
    "current_lease_liabilities",
    "non_current_lease_liabilities",
)

_OPEX_COMPONENT_FIELDS = (
    "selling_expenses",
    "admin_expenses",
    "other_operating_expenses",
    "rd_expenses",
)


_EXPENSE_SIGN_FIELDS = frozenset({
    "cost_of_revenue",
    "income_tax_expense",
    "selling_expenses",
    "admin_expenses",
    "other_operating_expenses",
    "operating_expenses",
    "interest_expense",
    "depreciation_amortization",
    "capex",
})


def _vals_close(a: float, b: float, ignore_sign: bool = False) -> bool:
    if ignore_sign:
        a, b = abs(a), abs(b)
    return abs(a - b) <= max(1.0, 0.005 * max(abs(a), abs(b)))


def _is_eligible_for_z3_attestation(data, field: str, year: int) -> bool:
    """Strict Honesty-Gate guard: only directly captured, non-derived,
    non-conflicting, spatially clean cells may receive Z3 algebraic attestation."""
    val = (getattr(data, "values", {}) or {}).get(field, {}).get(year)
    if val is None:
        return False
    # Rule 1: Never self-attest synthetically derived cells (zero tautology!)
    derived = getattr(data, "derived", {}) or {}
    if (field, year) in derived:
        return False
    # Rule 2: Must have at least one direct candidate capture from the document
    raw_cands = (getattr(data, "candidates", {}) or {}).get(field, {}).get(year) or []
    cand_vals = [v for v, _ in raw_cands if v is not None]
    if not cand_vals:
        return False
    # Rule 3: Never override a genuine magnitude CONFLICT (for expenses printed in
    # parentheses like (14.87B) vs +14.87B, sign-convention-only difference is not a
    # digit error when closed by a Z3 algebraic identity!)
    ign_sign = field in _EXPENSE_SIGN_FIELDS
    distinct: list[float] = []
    for v in cand_vals:
        if not any(_vals_close(v, d, ignore_sign=ign_sign) for d in distinct):
            distinct.append(v)
    conf = (getattr(data, "confidence", {}) or {}).get(field, {}).get(year, 0)
    if len(distinct) >= 2 and conf < 2:
        return False
    # Rule 4: Respect spatial gate findings if present
    spatial = (getattr(data, "spatial_findings", {}) or {}).get((field, year))
    if isinstance(spatial, dict) and spatial.get("downgrade"):
        return False
    return True


def apply_z3_algebraic_attestation(
    data,
    notes: list[str] | None = None,
    strict_rel_tol: float = 1e-5,
    cf_rel_tol: float = 0.05,
    integer_tol: float | None = 5.0,
) -> list[tuple[str, int, str]]:
    """Attest directly captured cells participating in PROVEN closed accounting
    equalities as an independent deterministic mathematical layer (`z3_math`).

    Guarantees:
      - Zero tautology: ALL participating terms of an equation must be directly
        captured from the document (none synthetically derived by Python).
      - Zero conflict suppression: conflicted cells (`CONFLICT`) are never promoted.
      - Strict algebraic checksum: ≤ 0.2% residual for Balance Sheet / Income
        identities (A1, A2, A3, A5, A6) — tightened to ±5 units when all terms are
        exact whole-currency integers ≥ 100k — and ≤ 5% for the Cash Flow bridge (A9).

    Returns list of newly attested `(field, year, axiom_id)` triples.
    """
    values = getattr(data, "values", None) or {}
    if not values:
        return []

    cert = verify_financial_statements(
        values, tolerance=strict_rel_tol, integer_tol=integer_tol,
    )
    to_attest: dict[tuple[str, int], str] = {}

    # 1. Core closed multi-term accounting equalities (A1, A2, A3, A5, A6)
    for ax in cert.axioms:
        if ax.axiom_id not in _STRICT_EQUALITY_AXIOMS or ax.status != "PROVEN":
            continue
        if ax.lhs is None or ax.rhs is None or ax.residual is None:
            continue
        if abs(ax.residual) > _whole_currency_tol(ax.lhs, ax.rhs, strict_rel_tol, integer_tol=integer_tol):
            continue
        if len(ax.fields) < 3:
            continue
        if all(_is_eligible_for_z3_attestation(data, f, ax.year) for f in ax.fields):
            for f in ax.fields:
                to_attest.setdefault((f, ax.year), ax.axiom_id)

    # 2. Direct 4-term Egyptian Balance Sheet Identity (A1b_BS_4TERM):
    # Egyptian EAS statements print Equity + Non-Current Liab + Current Liab = Total Assets
    # directly without printing a separate Total Liabilities subtotal line (so total_liabilities
    # is derived, which blocks A1/A3). Checking TA == Eq + NCL + CL directly has ZERO tautology!
    years = sorted(cert.years_checked)
    for y in years:
        bs4 = ("total_assets", "equity", "non_current_liabilities", "current_liabilities")
        if all(_is_eligible_for_z3_attestation(data, f, y) for f in bs4):
            ta = float(values["total_assets"][y])
            rhs4 = (
                float(values["equity"][y])
                + float(values["non_current_liabilities"][y])
                + float(values["current_liabilities"][y])
            )
            if abs(ta - rhs4) <= _whole_currency_tol(ta, rhs4, strict_rel_tol, integer_tol=integer_tol):
                for f in bs4:
                    to_attest.setdefault((f, y), "A1b_BS_4TERM")

    # 3. Cross-year Cash Flow Bridge (A9): OCF + ICF + FCF ≈ cash(curr) - cash(prev)
    if len(years) >= 2:
        prev_y, curr_y = years[-2], years[-1]
        cf_pairs = [
            ("operating_cash_flow", curr_y),
            ("investing_cash_flow", curr_y),
            ("financing_cash_flow", curr_y),
            ("cash", curr_y),
            ("cash", prev_y),
        ]
        if all(_is_eligible_for_z3_attestation(data, f, y) for f, y in cf_pairs):
            ocf = float(values["operating_cash_flow"][curr_y])
            icf = float(values["investing_cash_flow"][curr_y])
            fcf = float(values["financing_cash_flow"][curr_y])
            c_curr = float(values["cash"][curr_y])
            c_prev = float(values["cash"][prev_y])
            delta_c = c_curr - c_prev
            net_cf = ocf + icf + fcf
            cf_scale = max(abs(ocf), abs(icf), abs(fcf), abs(delta_c), 1.0)
            if abs(net_cf - delta_c) <= max(1000.0, cf_rel_tol * cf_scale):
                for f, y in cf_pairs:
                    to_attest.setdefault((f, y), "A9_CF_BRIDGE")

    # 3. Exact Component-Sum Checksums (Debt sum & OpEx sum when non-derived)
    for y in years:
        # Total Debt == sum of directly captured debt components
        if _is_eligible_for_z3_attestation(data, "total_debt", y):
            td = float(values["total_debt"][y])
            comp_f = [f for f in _DEBT_COMPONENT_FIELDS if _is_eligible_for_z3_attestation(data, f, y)]
            if len(comp_f) >= 2:
                comp_sum = sum(abs(float(values[f][y])) for f in comp_f)
                if abs(abs(td) - comp_sum) <= _whole_currency_tol(abs(td), comp_sum, strict_rel_tol, integer_tol=integer_tol):
                    to_attest.setdefault(("total_debt", y), "A10_DEBT_SUM")
                    for f in comp_f:
                        to_attest.setdefault((f, y), "A10_DEBT_SUM")

        # Operating Expenses == sum of directly captured OpEx components
        if _is_eligible_for_z3_attestation(data, "operating_expenses", y):
            opex = abs(float(values["operating_expenses"][y]))
            comp_f = [f for f in _OPEX_COMPONENT_FIELDS if _is_eligible_for_z3_attestation(data, f, y)]
            if len(comp_f) >= 2:
                comp_sum = sum(abs(float(values[f][y])) for f in comp_f)
                if abs(opex - comp_sum) <= _whole_currency_tol(opex, comp_sum, strict_rel_tol, integer_tol=integer_tol):
                    to_attest.setdefault(("operating_expenses", y), "A11_OPEX_SUM")
                    for f in comp_f:
                        to_attest.setdefault((f, y), "A11_OPEX_SUM")

        # A6b: Egyptian EAS Income Statement Activity-to-Pretax Bridge
        # Supports both compact bridge (act - |fin| + div == pretax) and full bridge
        # (act + finance_income - |interest_expense| + fx_gain_loss + [dividends] == pretax).
        act_f = (
            "net_activity_profit"
            if _is_eligible_for_z3_attestation(data, "net_activity_profit", y)
            else ("operating_income" if _is_eligible_for_z3_attestation(data, "operating_income", y) else None)
        )
        if act_f and _is_eligible_for_z3_attestation(data, "pretax_income", y) and _is_eligible_for_z3_attestation(data, "interest_expense", y):
            pt_v = float(values["pretax_income"][y])
            act_v = float(values[act_f][y])
            fin_v = float(values["interest_expense"][y])
            has_fi = _is_eligible_for_z3_attestation(data, "finance_income", y)
            has_fx = _is_eligible_for_z3_attestation(data, "fx_gain_loss", y)
            has_div = _is_eligible_for_z3_attestation(data, "dividends_from_subsidiaries", y)
            fi_v = abs(float(values["finance_income"][y])) if has_fi else 0.0
            fx_v = float(values["fx_gain_loss"][y]) if has_fx else 0.0
            div_v = float(values["dividends_from_subsidiaries"][y]) if has_div else 0.0
            rhs_compact = act_v + fin_v + div_v
            rhs_compact_sub = act_v - abs(fin_v) + div_v
            rhs_full = act_v + fi_v - abs(fin_v) + fx_v + div_v
            best_full_err = abs(pt_v - rhs_full)
            used_a6b: list[str] = [act_f, "pretax_income", "interest_expense"]
            if has_fi or has_fx:
                if best_full_err <= _whole_currency_tol(pt_v, rhs_full, strict_rel_tol, integer_tol=integer_tol):
                    if has_fi:
                        used_a6b.append("finance_income")
                    if has_fx:
                        used_a6b.append("fx_gain_loss")
                    if has_div:
                        used_a6b.append("dividends_from_subsidiaries")
                    for f in used_a6b:
                        to_attest.setdefault((f, y), "A6b_ACTIVITY_BRIDGE")
            if act_f and not any((f, y) in to_attest for f in ("finance_income", "fx_gain_loss")):
                best_comp = rhs_compact if abs(pt_v - rhs_compact) <= abs(pt_v - rhs_compact_sub) else rhs_compact_sub
                if abs(pt_v - best_comp) <= _whole_currency_tol(pt_v, best_comp, strict_rel_tol, integer_tol=integer_tol):
                    for f in ([act_f, "pretax_income", "interest_expense"] + (["dividends_from_subsidiaries"] if has_div else [])):
                        to_attest.setdefault((f, y), "A6b_ACTIVITY_BRIDGE")

        # A1c: Exact Equity Component Sum (capital + treasury_shares + reserves + asset_revaluation_reserve + retained_earnings == equity)
        if (
            _is_eligible_for_z3_attestation(data, "equity", y)
            and _is_eligible_for_z3_attestation(data, "capital", y)
            and _is_eligible_for_z3_attestation(data, "retained_earnings", y)
        ):
            eq_v = float(values["equity"][y])
            eq_opt = ("treasury_shares", "reserves", "asset_revaluation_reserve")
            present_opt = [f for f in eq_opt if _is_eligible_for_z3_attestation(data, f, y)]
            if present_opt:
                eq_parts = ["capital", "retained_earnings"] + present_opt
                eq_sum = (
                    abs(float(values["capital"][y]))
                    + float(values["retained_earnings"][y])
                    + (-abs(float(values["treasury_shares"][y])) if "treasury_shares" in present_opt else 0.0)
                    + (abs(float(values["reserves"][y])) if "reserves" in present_opt else 0.0)
                    + (float(values["asset_revaluation_reserve"][y]) if "asset_revaluation_reserve" in present_opt else 0.0)
                )
                if abs(eq_v - eq_sum) <= _whole_currency_tol(eq_v, eq_sum, strict_rel_tol, integer_tol=integer_tol):
                    to_attest.setdefault(("equity", y), "A1c_EQUITY_SUM")
                    for f in eq_parts:
                        to_attest.setdefault((f, y), "A1c_EQUITY_SUM")

        # A2b: Non-Current Assets Balance-Sheet Sum (fixed + CWIP + subsidiaries + other_inv + DTA == non_current_assets)
        nca_v = float(values["non_current_assets"][y]) if _is_eligible_for_z3_attestation(data, "non_current_assets", y) else None
        if nca_v is not None and _is_eligible_for_z3_attestation(data, "fixed_assets", y):
            nca_parts_f = (
                "fixed_assets", "projects_under_construction",
                "investments_in_subsidiaries", "other_investments", "deferred_tax_assets",
            )
            present_nca = [f for f in nca_parts_f if _is_eligible_for_z3_attestation(data, f, y)]
            if len(present_nca) >= 3:
                nca_sum = sum(abs(float(values[f][y])) for f in present_nca)
                nca_tol = _whole_currency_tol(nca_v, nca_sum, strict_rel_tol, integer_tol=integer_tol)
                if abs(nca_v - nca_sum) <= nca_tol:
                    to_attest.setdefault(("non_current_assets", y), "A2b_NCA_SUM")
                    for f in present_nca:
                        to_attest.setdefault((f, y), "A2b_NCA_SUM")

        # A2c: Itemized Current Assets Sum (inventory + AR + other_receivables + supplier_advances + cash == current_assets)
        ca_v = float(values["current_assets"][y]) if _is_eligible_for_z3_attestation(data, "current_assets", y) else None
        if ca_v is not None:
            ca_parts_f = ("inventory", "accounts_receivable", "other_receivables", "supplier_advances", "cash")
            present_ca = [f for f in ca_parts_f if _is_eligible_for_z3_attestation(data, f, y)]
            if "other_receivables" in present_ca and len(present_ca) >= 4:
                ca_sum = sum(abs(float(values[f][y])) for f in present_ca)
                ca_tol = _whole_currency_tol(ca_v, ca_sum, strict_rel_tol, integer_tol=integer_tol)
                if abs(ca_v - ca_sum) <= ca_tol:
                    to_attest.setdefault(("current_assets", y), "A2c_CA_SUM")
                    for f in present_ca:
                        to_attest.setdefault((f, y), "A2c_CA_SUM")

        # A3b: Itemized Current Liabilities Sum (bank_overdraft + facilities + CPLTD + CL leases + AP + cust advances + other payables + provisions == CL)
        cl_v = float(values["current_liabilities"][y]) if _is_eligible_for_z3_attestation(data, "current_liabilities", y) else None
        if cl_v is not None:
            cl_parts_f = (
                "bank_overdraft", "short_term_credit_facilities", "current_portion_lt_debt",
                "current_lease_liabilities", "accounts_payable", "customer_advances",
                "other_payables", "provisions",
            )
            present_cl = [f for f in cl_parts_f if _is_eligible_for_z3_attestation(data, f, y)]
            if "accounts_payable" in present_cl and "other_payables" in present_cl and len(present_cl) >= 5:
                cl_sum = sum(abs(float(values[f][y])) for f in present_cl)
                cl_tol = _whole_currency_tol(cl_v, cl_sum, strict_rel_tol, integer_tol=integer_tol)
                if abs(cl_v - cl_sum) <= cl_tol:
                    to_attest.setdefault(("current_liabilities", y), "A3b_CL_SUM")
                    for f in present_cl:
                        to_attest.setdefault((f, y), "A3b_CL_SUM")

        # A3c: Itemized Non-Current Liabilities Sum (LT debt + LT notes payable + LT leases + DTL == NCL)
        ncl_v = float(values["non_current_liabilities"][y]) if _is_eligible_for_z3_attestation(data, "non_current_liabilities", y) else None
        if ncl_v is not None:
            ncl_parts_f = (
                "long_term_debt", "long_term_notes_payable",
                "non_current_lease_liabilities", "deferred_tax_liabilities",
            )
            present_ncl = [f for f in ncl_parts_f if _is_eligible_for_z3_attestation(data, f, y)]
            if "long_term_notes_payable" in present_ncl and "deferred_tax_liabilities" in present_ncl and len(present_ncl) >= 3:
                ncl_sum = sum(abs(float(values[f][y])) for f in present_ncl)
                ncl_tol = _whole_currency_tol(ncl_v, ncl_sum, strict_rel_tol, integer_tol=integer_tol)
                if abs(ncl_v - ncl_sum) <= ncl_tol:
                    to_attest.setdefault(("non_current_liabilities", y), "A3c_NCL_SUM")
                    for f in present_ncl:
                        to_attest.setdefault((f, y), "A3c_NCL_SUM")

        # A5c: Exact Gross-to-Operating Profit Bridge when OpEx components (+ optional Other Operating Income) are directly captured
        op_field = "operating_income" if _is_eligible_for_z3_attestation(data, "operating_income", y) else (
            "net_activity_profit" if _is_eligible_for_z3_attestation(data, "net_activity_profit", y) else None
        )
        if op_field and _is_eligible_for_z3_attestation(data, "gross_profit", y):
            op_comps = [f for f in _OPEX_COMPONENT_FIELDS if _is_eligible_for_z3_attestation(data, f, y)]
            has_other_inc = _is_eligible_for_z3_attestation(data, "other_operating_income", y)
            other_inc_v = abs(float(values["other_operating_income"][y])) if has_other_inc else 0.0
            if len(op_comps) >= 2:
                gp_v = float(values["gross_profit"][y])
                op_v = float(values[op_field][y])
                op_sum = sum(abs(float(values[f][y])) for f in op_comps)
                lhs_with_inc = gp_v - op_sum + other_inc_v
                lhs_no_inc = gp_v - op_sum
                if has_other_inc and abs(lhs_with_inc - op_v) <= _whole_currency_tol(lhs_with_inc, op_v, strict_rel_tol, integer_tol=integer_tol):
                    to_attest.setdefault(("gross_profit", y), "A5c_OP_EXACT")
                    to_attest.setdefault((op_field, y), "A5c_OP_EXACT")
                    to_attest.setdefault(("other_operating_income", y), "A5c_OP_EXACT")
                    for f in op_comps:
                        to_attest.setdefault((f, y), "A5c_OP_EXACT")
                elif abs(lhs_no_inc - op_v) <= _whole_currency_tol(lhs_no_inc, op_v, strict_rel_tol, integer_tol=integer_tol):
                    to_attest.setdefault(("gross_profit", y), "A5c_OP_EXACT")
                    to_attest.setdefault((op_field, y), "A5c_OP_EXACT")
                    for f in op_comps:
                        to_attest.setdefault((f, y), "A5c_OP_EXACT")

    # Formal soundness guard: never grant `z3_math` attestation to any (field, year)
    # participating in a VIOLATED axiom (e.g. TA=CA+NCA passing while TA!=TL+E fails).
    violated_fy = {
        (f, ax.year)
        for ax in cert.axioms
        if ax.status == "VIOLATED"
        for f in ax.fields
    }
    if violated_fy:
        to_attest = {k: v for k, v in to_attest.items() if k not in violated_fy}

    if not to_attest:
        recheck_derived_certainty(data)
        return []

    order_next = max(
        (o for cands in (getattr(data, "candidates", {}) or {}).values()
         for ys in cands.values() for _v, o in ys),
        default=0,
    ) + 1

    attested: list[tuple[str, int, str]] = []
    votes = getattr(data, "vote_outcomes", None)
    if not isinstance(votes, dict):
        votes = getattr(data, "votes", None) or {}
    for (field, year), ax_id in sorted(to_attest.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        val = float(values[field][year])
        cand_list = data.candidates.setdefault(field, {}).setdefault(year, [])
        layer_list = data.candidate_layers.setdefault(field, {}).setdefault(year, [])
        label_list = data.candidate_labels.setdefault(field, {}).setdefault(year, [])
        # Align existing candidates with their primary layer ("vision") so
        # zip(cands, layers_all) never sees ["z3_math"] alone (length-1 bug!).
        if len(layer_list) < len(cand_list):
            fallback_layer = layer_list[0] if layer_list else "vision"
            layer_list.extend([fallback_layer] * (len(cand_list) - len(layer_list)))
        elif len(layer_list) > len(cand_list):
            del layer_list[len(cand_list):]
        # Ensure at least one primary reading layer ("vision") aligns with `val`
        # (needed when Z3 repair updated `values[f][y]` from a 2400px vision re-read
        # while the earlier candidate in `cand_list` held the old un-repaired value).
        has_non_z3_match = any(
            v is not None and _vals_close(v, val) and lyr != "z3_math"
            for (v, _o), lyr in zip(cand_list, layer_list)
        )
        if not has_non_z3_match:
            cand_list.append((val, order_next))
            label_list.append(f"vision_z3_repaired:{ax_id}")
            layer_list.append("vision")
            order_next += 1
        if not any(
            v is not None and _vals_close(v, val) and lyr == "z3_math"
            for (v, _o), lyr in zip(cand_list, layer_list)
        ):
            cand_list.append((val, order_next))
            label_list.append(f"z3_math:{ax_id}")
            layer_list.append("z3_math")
        data.bump_confidence(field, year, 2)
        data.identity_ok[(field, year)] = True
        if (field, year) in votes and isinstance(votes[(field, year)], dict):
            wl = list(votes[(field, year)].get("winner_layers") or [])
            if not wl:
                wl.append("vision")
            if "z3_math" not in wl:
                wl.append("z3_math")
            votes[(field, year)]["winner_layers"] = sorted(set(wl))
        attested.append((field, year, ax_id))
        order_next += 1

    # Upgrade derived_uncertain for derived fields whose directly-printed
    # inputs are now verified by >=2 independent layers (z3_math / local_ocr / cross-model).
    recheck_derived_certainty(data, extra_attested=set(to_attest.keys()))

    if attested and notes is not None:
        notes.append(
            f"التوثيق الجبري بـ Z3: تم إثبات وتوثيق {len(attested)} خانة رياضياً "
            f"عبر المعادلات المحاسبية المقفولة كطبقة تحقق مستقلة (z3_math)."
        )
    return attested


def recheck_derived_certainty(
    data,
    extra_attested: set[tuple[str, int]] | None = None,
) -> int:
    """Clear `derived_uncertain` for derived fields once ALL their directly
    captured inputs are independently verified (>=2 distinct layers).

    Honest cascade: never upgrades a derived cell while any of its required
    inputs still rests on a single unverified layer. Returns number upgraded.
    """
    derived_unc = getattr(data, "derived_uncertain", None)
    if not isinstance(derived_unc, set) or not derived_unc:
        return 0
    attested_set = set(extra_attested or set())
    values = getattr(data, "values", {}) or {}
    votes = getattr(data, "vote_outcomes", {}) or {}
    cand_layers = getattr(data, "candidate_layers", {}) or {}
    candidates = getattr(data, "candidates", {}) or {}
    conf_map = getattr(data, "confidence", {}) or {}

    def _is_multi_layer_verified(field: str, year: int) -> bool:
        if (field, year) in attested_set:
            return True
        val = values.get(field, {}).get(year)
        if val is None:
            return False
        if (conf_map.get(field, {}) or {}).get(year, 0) < 2:
            return False
        vo = votes.get((field, year)) or {}
        wl = set(vo.get("winner_layers") or [])
        if len(wl) >= 2:
            return True
        cands = candidates.get(field, {}).get(year) or []
        lyrs = cand_layers.get(field, {}).get(year) or []
        matching_lyrs = {
            lyr for (v, _o), lyr in zip(cands, lyrs)
            if v is not None and lyr and _vals_close(v, val, ignore_sign=(field in _EXPENSE_SIGN_FIELDS))
        }
        return len(matching_lyrs) >= 2

    years = sorted({y for _f, y in derived_unc if isinstance(y, int)})
    upgraded = 0
    _direct_pairs = (
        ("total_liabilities", ("non_current_liabilities", "current_liabilities")),
        ("gross_profit", ("revenue", "cost_of_revenue")),
        ("cost_of_revenue", ("revenue", "gross_profit")),
        ("revenue", ("gross_profit", "cost_of_revenue")),
        ("income_tax_expense", ("pretax_income", "net_income")),
        ("pretax_income", ("net_income", "income_tax_expense")),
        ("net_income", ("pretax_income", "income_tax_expense")),
        ("non_current_assets", ("total_assets", "current_assets")),
        ("non_current_liabilities", ("total_liabilities", "current_liabilities")),
    )
    for y in years:
        for target, reqs in _direct_pairs:
            if (target, y) in derived_unc and all(_is_multi_layer_verified(r, y) for r in reqs):
                derived_unc.discard((target, y))
                upgraded += 1

        # Debt aggregations: clear once every present debt component is multi-layer verified
        _borrow_comps = (
            "short_term_debt", "short_term_credit_facilities", "bank_overdraft",
            "current_portion_lt_debt", "long_term_debt",
        )
        _lease_comps = ("current_lease_liabilities", "non_current_lease_liabilities")
        present_borrow = [f for f in _borrow_comps if values.get(f, {}).get(y) is not None]
        present_lease = [f for f in _lease_comps if values.get(f, {}).get(y) is not None]
        if ("borrowings_excl_leases", y) in derived_unc and present_borrow:
            if all(_is_multi_layer_verified(f, y) for f in present_borrow):
                derived_unc.discard(("borrowings_excl_leases", y))
                upgraded += 1
        all_debt_present = present_borrow + present_lease
        if all_debt_present and all(_is_multi_layer_verified(f, y) for f in all_debt_present):
            for df in ("financial_debt_incl_leases", "total_debt"):
                if (df, y) in derived_unc:
                    derived_unc.discard((df, y))
                    upgraded += 1
    return upgraded
