# -*- coding: utf-8 -*-
"""Multi-Layer Protection Guard & Safe Supplemental Extractor (`protection_layer.py`).

Enforces strict neuro-symbolic safety across:
1. **Extraction & Reconciliation Protection (`enrich_supplemental_fields`)**:
   - Captures `eps`, `shares_outstanding`, `dividends_paid_shareholders`,
     `income_taxes_paid`, `related_party_payables`, `related_party_receivables`,
     `total_wages` / `wages_cogs`, `free_float_other_pct` (approx minority row),
     and `disclosure_checklist` WITHOUT perturbing core `match_field` contracts.
   - **Equity-Continuity Dividend Guard**: blocks duplicate multi-column Equity OCR
     dividends when ΔEquity matches Net Income (`zero_dividend_when_equity_closed`).
   - **Tax Cash Guard**: separates subsidiary dividend withholding taxes from
     operational income taxes paid.
2. **Pre-Optimization & Metric Protection Gate (`evaluate_protection_gate`)**:
   - Refuses official optimization / Health Score issuance when extraction was
     quota-interrupted or critical balance-sheet/P&L fields remain unresolved
     (mirrors `FinSightProofs.permitOfficialOptimization` in Lean 4).
   - Provides explicit **Exploratory** vs **Official** distinction and exact reasons.
3. **Post-Solve Covenant & Double-Entry Verification (`verify_optimized_state`)**:
   - Checks exact balance-sheet conservation (`Assets' == Liabilities' + Equity'`)
     plus liquidity/leverage covenants and runs live Lean 4 instance checking.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from src.analysis.financial_gate import decide
from src.analysis.lean4_verifier import verify_instance_with_lean4, verify_lean4_kernel

CRITICAL_OPT_FIELDS: tuple[str, ...] = (
    "revenue",
    "cost_of_revenue",
    "operating_income",
    "net_income",
    "total_assets",
    "current_assets",
    "current_liabilities",
    "total_liabilities",
    "total_debt",
    "equity",
    "cash",
)

_AR_TRANS = str.maketrans("٠١٢٣٤٥٦٧٨٩أإآةىئؤ", "0123456789اااهييو")


def _norm_ar(text: object) -> str:
    s = str(text or "").strip().translate(_AR_TRANS).lower()
    s = re.sub(r"[ـ\u064b-\u065f]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _parse_int_tokens_from_prose(raw: str) -> int | None:
    digits = re.sub(r"[^\d]", "", str(raw or "").translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")))
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def build_disclosure_checklist(notes_text: dict | None, values: dict[str, dict]) -> dict[str, Any]:
    """Build an honest Statement Disclosure Readiness checklist (NOT an ESG score).

    Only marks items present when concrete evidence appears in extracted notes
    or canonical statement fields. Explicitly discloses that standalone ESG /
    sustainability metrics require an external ESG/Annual report.
    """
    notes = notes_text or {}
    joined = "\n".join(_norm_ar(v) for v in notes.values())
    checks = [
        {
            "id": "auditor_report",
            "name_ar": "تقرير مراقب الحسابات المستقل",
            "name_en": "Independent Auditor Report",
            "present": bool(
                any(k in joined for k in ("مراقب الحسابات", "تقرير الفحص", "الي الساده مساهمي", "راجعنا القوايم"))
            ),
        },
        {
            "id": "shareholder_structure",
            "name_ar": "هيكل المساهمين ورأس المال المصدر",
            "name_en": "Capital & Shareholder Structure",
            "present": bool(
                values.get("capital")
                or any(k in joined for k in ("بيان بمساهمي", "نسبه المساهمه", "راس المال المصدر"))
            ),
        },
        {
            "id": "related_parties",
            "name_ar": "إيضاح المعاملات والأطراف ذات العلاقة",
            "name_en": "Related-Party Disclosures",
            "present": bool(
                any(k in joined for k in ("اطراف ذوي علاقه", "اطراف ذات علاقه", "الاطراف ذوي العلاقه"))
            ),
        },
        {
            "id": "risk_management",
            "name_ar": "سياسات إدارة مخاطر الائتمان والسيولة والسوق",
            "name_en": "Credit, Liquidity & Market Risk Policy",
            "present": bool(
                any(k in joined for k in ("خطر الايتمان", "خطر السيوله", "خطر السوق", "اداره راس المال"))
            ),
        },
        {
            "id": "employee_benefits",
            "name_ar": "مزايا العاملين والتأمينات الاجتماعية",
            "name_en": "Employee Benefits & Social Insurance",
            "present": bool(
                any(k in joined for k in ("مزايا العاملين", "صندوق التامين والادخار", "التامينات الاجتماعيه"))
            ),
        },
        {
            "id": "tax_reconciliation",
            "name_ar": "تسوية السعر الفعلي للضريبة والضرائب المؤجلة",
            "name_en": "Effective Tax Rate Reconciliation & Deferred Tax",
            "present": bool(
                any(k in joined for k in ("السعر الفعلي لضريبه الدخل", "الضريبيه الموجله"))
                or bool(values.get("income_tax_expense"))
            ),
        },
    ]
    present_n = sum(1 for c in checks if c["present"])
    total_n = len(checks)
    return {
        "present_count": present_n,
        "total_count": total_n,
        "readiness_pct": round(present_n / total_n * 100.0, 1) if total_n else 0.0,
        "items": checks,
        "disclaimer_ar": (
            "فحص جاهزية الإفصاح المحاسبي من القوائم المالية فقط — لا يمثل تقييم ESG بيئياً/اجتماعياً "
            "شاملاً (GRI / S&P EGX ESG)، لأن تقارير الانبعاثات والاستدامة ومجلس الإدارة غير مرفقة بالملف."
        ),
        "disclaimer_en": (
            "Financial-statement disclosure checklist only — NOT a full GRI / S&P ESG rating, "
            "as standalone sustainability, emissions, and board-independence reports are absent."
        ),
    }


def enrich_supplemental_fields(
    *,
    values: dict[str, dict],
    unmapped_labels: list[dict] | None,
    notes_text: dict | None,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    """Safely extract and cross-check supplemental per-share, tax, wage, related-party,
    and governance fields from unmapped_labels and notes_text.

    Modifies NOTHING in `values` unless already absent, and applies strict
    accounting guards (e.g., Equity-Continuity guard against phantom 2023 dividends).
    Returns supplemental metadata dictionary (`audit_notes`, `disclosure_checklist`, `free_float_info`).
    """
    audit_notes = notes if notes is not None else []
    unmapped = unmapped_labels or []
    notes_map = notes_text or {}

    def _add_val(field_name: str, yr: int, val: float) -> None:
        values.setdefault(field_name, {})
        if values[field_name].get(yr) is None:
            values[field_name][yr] = float(val)

    # 1) Weighted average shares & EPS from unmapped_labels (and Note 20/9 fallback)
    for item in unmapped:
        if not isinstance(item, dict):
            continue
        lbl = _norm_ar(item.get("label", ""))
        yv = item.get("values") or {}
        if not lbl or not isinstance(yv, dict):
            continue

        # Shares count (weighted average shares)
        if any(p in lbl for p in ("متوسط الاسهم القايمه", "weighted average", "عدد الاسهم القايمه")):
            for y_k, val_k in yv.items():
                if not str(y_k).isdigit() or val_k is None:
                    continue
                yr = int(y_k)
                v_f = abs(float(val_k))
                if v_f >= 1_000.0:
                    _add_val("shares_outstanding", yr, v_f)

        # Printed EPS (strict sign kept, guard |v| < 1000 so share counts never leak)
        elif any(p in lbl for p in ("النصيب الاساسي والمخفض للسهم", "نصيب السهم في صافي", "earnings per share", "basic and diluted eps")):
            for y_k, val_k in yv.items():
                if not str(y_k).isdigit() or val_k is None:
                    continue
                yr = int(y_k)
                v_f = float(val_k)
                if abs(v_f) < 1_000.0:
                    _add_val("eps", yr, v_f)

        # Income taxes paid in Cash Flow (exclude subsidiary dividend withholding tax!)
        elif (
            any(p in lbl for p in ("ضريبه دخل مدفوعه", "ضرايب دخل مدفوعه", "income taxes paid", "taxes paid"))
            and "توزيعات" not in lbl
            and "موجله" not in lbl
        ):
            for y_k, val_k in yv.items():
                if not str(y_k).isdigit() or val_k is None:
                    continue
                _add_val("income_taxes_paid", int(y_k), float(val_k))

        # Related-party payables / receivables (Note 26)
        elif "موردون" in lbl and any(p in lbl for p in ("اطراف ذات علاقه", "اطراف ذوي علاقه")):
            for y_k, val_k in yv.items():
                if not str(y_k).isdigit() or val_k is None:
                    continue
                _add_val("related_party_payables", int(y_k), abs(float(val_k)))

        elif "عملا" in lbl and any(p in lbl for p in ("اطراف ذوي علاقه", "اطراف ذات علاقه")):
            for y_k, val_k in yv.items():
                if not str(y_k).isdigit() or val_k is None:
                    continue
                _add_val("related_party_receivables", int(y_k), abs(float(val_k)))

        # Wages captured (track separately unless explicitly total wages)
        elif lbl in ("مرتبات واجور", "الاجور والمرتبات") or "total wages" in lbl or "salaries and wages" in lbl or "اجمالي الاجور" in lbl:
            target = "total_wages" if ("اجمالي" in lbl or "total" in lbl) else "wages_cogs"
            for y_k, val_k in yv.items():
                if not str(y_k).isdigit() or val_k is None:
                    continue
                _add_val(target, int(y_k), abs(float(val_k)))

    # Fall back to Note 20 capital prose for total issued shares if shares_outstanding still missing
    all_years = sorted(
        {
            int(y)
            for by_y in values.values()
            if isinstance(by_y, dict)
            for y in by_y
            if str(y).isdigit()
        }
    )
    if notes_map and not values.get("shares_outstanding"):
        joined_notes = "\n".join(str(t) for t in notes_map.values()).translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
        m_sh = re.search(r"موزع\s+عل[يى]\s+([\d,]+)\s*سهم", joined_notes)
        if m_sh:
            sh_cnt = _parse_int_tokens_from_prose(m_sh.group(1))
            if sh_cnt and sh_cnt >= 1_000:
                for yr in all_years:
                    _add_val("shares_outstanding", yr, float(sh_cnt))
                audit_notes.append(
                    f"Supplemental shares_outstanding inferred from Note 20 issued share count ({sh_cnt:,} shares — check treasury share deductions if applicable)."
                )

    # 2) EPS cross-check protection: ensure EPS isn't out of line with NI / shares when both exist
    for yr in all_years:
        eps_v = (values.get("eps") or {}).get(yr)
        ni_v = (values.get("net_income") or {}).get(yr)
        sh_v = (values.get("shares_outstanding") or {}).get(yr)
        if eps_v is not None and ni_v is not None and sh_v and sh_v > 0:
            calc_eps = ni_v / sh_v
            if abs(eps_v - calc_eps) > max(0.25, 0.15 * abs(calc_eps)):
                audit_notes.append(
                    f"Protection Guard: printed EPS {eps_v:.2f} in {yr} differs materially from NI/Shares ({calc_eps:.2f}) — keeping printed EPS only after flag."
                )

    # 3) Shareholder Dividends with Equity-Continuity Guard (prevents 2023 duplicate OCR bug!)
    cf_div_by_year: dict[int, float] = {}
    eq_div_by_year: dict[int, float] = {}
    emp_div_by_year: dict[int, float] = {}
    for item in unmapped:
        if not isinstance(item, dict):
            continue
        lbl = _norm_ar(item.get("label", ""))
        yv = item.get("values") or {}
        if not lbl or not isinstance(yv, dict):
            continue
        if any(bad in lbl for bad in ("شركات تابعه", "شركه تابعه", "توزيعات ارباح من", "داينو", "ضريب", "ضرايب", "مسدد مقدما", "معاملات")):
            continue
        if "توزيعات" in lbl and any(w in lbl for w in ("للمساهمين", "المساهمين", "shareholders", "equity holders")):
            is_cf_phrasing = "للمساهمين" in lbl or "cash" in lbl
            for y_k, val_k in yv.items():
                if not str(y_k).isdigit() or val_k is None:
                    continue
                yr = int(y_k)
                mag = -abs(float(val_k))
                if is_cf_phrasing:
                    cf_div_by_year[yr] = mag
                else:
                    eq_div_by_year[yr] = mag
        elif "توزيعات" in lbl and any(w in lbl for w in ("للعاملين", "العاملين")):
            for y_k, val_k in yv.items():
                if not str(y_k).isdigit() or val_k is None:
                    continue
                emp_div_by_year[int(y_k)] = -abs(float(val_k))

    # Cross-check each year using Equity Continuity: Eq(y) = Eq(y-1) + NI(y) - Distributions
    eq_map = values.get("equity") or {}
    ni_map = values.get("net_income") or {}
    for idx, yr in enumerate(all_years):
        prev_yr = all_years[idx - 1] if idx > 0 else None
        eq_curr = eq_map.get(yr)
        eq_prev = eq_map.get(prev_yr) if prev_yr is not None else None
        ni_curr = ni_map.get(yr)

        cand_div = cf_div_by_year.get(yr)
        if cand_div is None:
            cand_div = eq_div_by_year.get(yr)

        if None not in (eq_curr, eq_prev, ni_curr):
            ts_curr = abs(float((values.get("treasury_shares") or {}).get(yr) or 0.0))
            ts_prev = abs(float((values.get("treasury_shares") or {}).get(prev_yr) or 0.0))
            ts_delta = max(0.0, ts_curr - ts_prev)
            implied_gap = (eq_prev + ni_curr - ts_delta) - eq_curr
            tol_eq = max(5_000.0, 1e-4 * abs(eq_curr))
            if abs(implied_gap) <= tol_eq:
                if cand_div is not None and abs(cand_div) > tol_eq:
                    audit_notes.append(
                        f"حارس استمرارية حقوق الملكية (Lean 4 Guard): رفض توزيعات {abs(cand_div):,.0f} في {yr} "
                        f"لأن معادلة حقوق الملكية مغلقة (ملكية {prev_yr} + ربح {yr} − ملكية {yr} = {implied_gap:,.0f}) — التوزيع الفعلي للمساهمين = 0."
                    )
                _add_val("dividends_paid_shareholders", yr, 0.0)
                continue
            if cand_div is not None and implied_gap > 0 and abs(cand_div) <= implied_gap + tol_eq:
                _add_val("dividends_paid_shareholders", yr, cand_div)
                continue

        if yr in cf_div_by_year:
            _add_val("dividends_paid_shareholders", yr, cf_div_by_year[yr])
        elif yr in eq_div_by_year and yr not in cf_div_by_year and prev_yr is not None:
            # Unverified equity-table-only candidate when bridge could not confirm -> hold back
            audit_notes.append(
                f"حارس التوزيعات: استُبعد مرشح جدول حقوق الملكية غير المؤكد ({abs(eq_div_by_year[yr]):,.0f}) في {yr} لغياب سند التدفق النقدي أو فجوة الملكية."
            )

    # 4) Approximate "Other shareholders" minority slice from Note 20 table (never labeled official EGX Free Float)
    free_float_info: dict[str, Any] = {
        "other_shareholders_shares": None,
        "total_issued_shares": None,
        "approx_other_pct": None,
        "turnover_available": False,
        "note_ar": "معدل دوران السهم وقيمة التداول غير متوفرين في القوائم المالية؛ نسبة «آخرون» تقريبية فقط وليست Free Float الرسمي للبورصة.",
        "note_en": "Stock turnover/volume is absent from financial statements; 'Others' shareholder slice is an approximation only, not official EGX Free Float.",
    }
    if notes_map:
        for pg_txt in notes_map.values():
            norm_pg = str(pg_txt).translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
            if "المساهم" not in norm_pg:
                continue
            m_tot = re.search(r"موزع\s+عل[يى]\s+([\d,]+)\s*سهم", norm_pg)
            tot_issued = _parse_int_tokens_from_prose(m_tot.group(1)) if m_tot else None
            m_other = re.search(r"(?:أخرون|آخرون|اخرون)[^0-9]{0,25}([\d,]{7,15})", norm_pg)
            other_sh = _parse_int_tokens_from_prose(m_other.group(1)) if m_other else None
            if tot_issued and other_sh and 0 < other_sh < tot_issued:
                free_float_info["other_shareholders_shares"] = other_sh
                free_float_info["total_issued_shares"] = tot_issued
                free_float_info["approx_other_pct"] = round(other_sh / tot_issued * 100.0, 2)
                break

    checklist = build_disclosure_checklist(notes_map, values)
    return {
        "audit_notes": audit_notes,
        "disclosure_checklist": checklist,
        "free_float_info": free_float_info,
    }


@dataclass
class ProtectionVerdict:
    permit_official_score: bool
    permit_official_optimization: bool
    quota_interrupted: bool
    blocked_fields: list[str] = field(default_factory=list)
    warnings_ar: list[str] = field(default_factory=list)
    warnings_en: list[str] = field(default_factory=list)
    lean4_kernel: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_protection_gate(results: dict, *, allow_exploratory: bool = False) -> ProtectionVerdict:
    """Evaluate Lean 4-aligned Protection Gate before official Health Score or Optimization."""
    curr_yr = results.get("curr_year")
    dec_log = results.get("decision_log") or []
    quota_int = bool(results.get("quota_interrupted"))

    blocked: list[str] = []
    if dec_log:
        for e in dec_log:
            f_name = e.get("field")
            yr = e.get("year")
            if f_name not in CRITICAL_OPT_FIELDS:
                continue
            if curr_yr is not None and yr not in (None, curr_yr) and str(yr) != str(curr_yr):
                continue
            if decide(e.get("status", "MISSING")) not in ("use", "use_disclosed"):
                blocked.append(str(f_name))
    else:
        for f_name in (results.get("blocked_fields") or []):
            if f_name in CRITICAL_OPT_FIELDS:
                blocked.append(str(f_name))
    blocked = sorted(set(blocked))

    warnings_ar: list[str] = []
    warnings_en: list[str] = []
    if quota_int:
        warnings_ar.append("توقّف الاستخراج بسبب نفاد حصة API — الحماية تمنع إصدار خطة تحسين رسمية معتمدة.")
        warnings_en.append("Extraction stopped early due to API quota — official optimization is blocked.")
    if blocked:
        warnings_ar.append(
            f"خانات حرجة غير محسومة ({', '.join(blocked)}) — التشغيل الرسمي محجوب؛ المتاح وضع استكشافي معلن فقط."
        )
        warnings_en.append(
            f"Critical fields unverified ({', '.join(blocked)}) — official mode blocked; exploratory preview only."
        )

    cert = results.get("formal_certificate") or {}
    if int(cert.get("failed_axioms") or 0) > 0:
        warnings_ar.append(
            f"تنبيه Z3: يوجد {cert.get('failed_axioms')} قيد محاسبي مفتوح يحتاج مراجعة؛ طبقة التحسين تفحص أثره قبل التوازن."
        )
        warnings_en.append(
            f"Z3 notice: {cert.get('failed_axioms')} accounting axiom(s) unclosed; double-entry guard will flag residuals."
        )

    kernel_rep = verify_lean4_kernel().to_dict()
    permit = (not quota_int) and (not blocked)
    return ProtectionVerdict(
        permit_official_score=permit,
        permit_official_optimization=permit or allow_exploratory,
        quota_interrupted=quota_int,
        blocked_fields=blocked,
        warnings_ar=warnings_ar,
        warnings_en=warnings_en,
        lean4_kernel=kernel_rep,
    )


def verify_optimized_state(
    *,
    ta_before: float,
    tl_before: float,
    eq_before: float,
    dc: float,
    dw: float,
    dr: float,
    dn: float,
    dp: float,
    cash_after: float,
    ca_after: float,
    cl_after: float,
    min_cr: float,
    min_cash: float,
) -> dict[str, Any]:
    """Run deterministic double-entry & Lean 4 verification on an OptimizeEngine solution."""
    return verify_instance_with_lean4(
        ta_before=ta_before,
        tl_before=tl_before,
        eq_before=eq_before,
        dc=dc,
        dw=dw,
        dr=dr,
        dn=dn,
        dp=dp,
        cash_after=cash_after,
        ca_after=ca_after,
        cl_after=cl_after,
        min_cr=min_cr,
        min_cash=min_cash,
    )
