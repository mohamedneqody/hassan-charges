# -*- coding: utf-8 -*-
"""تحصين معماري لبيئة البورصة المصرية (إصلاح 9 — EGX Hardening).

أربع طبقات حماية:
1. توحيد وحدات القياس: «بالجنيه المصري» = 1، «بالألف جنيه» = 1000،
   «بالمليون» = 1000000 — تُوحَّد القيم للوحدة الأساسية قبل الحساب.
2. صيغة EAS البديلة للميزانية: الأصول المتداولة + الأصول غير المتداولة
   = حقوق الملكية + الالتزامات (كلتاهما تُفحصان).
3. فلتر ملاءمة القطاع: مؤشرات المخزون وCCC وAltman Z'' → N/A تلقائياً
   للقطاعات المالية/البنكية في presets.
4. اتساق تحليل الحساسية: ما-ذا-لو على قائمة الدخل لا ينتج ROE/ROA إلا
   بعد إقرار التغير في صافي الربح بالأرباح المرحلة وحقوق الملكية.
"""
from __future__ import annotations

import re
from pathlib import Path

# ── 1) توحيد وحدات القياس ──
_UNIT_HEADER_PATTERNS_EGX: list[tuple[str, int, str]] = [
    (r"بالمليون\s*جنيه|بالمليون", 1_000_000,
     "بالمليون جنيه — مضاعِف 1,000,000"),
    (r"بالألف\s*جنيه|بالألاف", 1000,
     "بالألف جنيه — مضاعِف 1,000"),
    (r"بالجنيه\s*المصري|بالجنيه", 1,
     "بالجنيه المصري — مضاعِف 1"),
]


def detect_egx_table_unit(text: str) -> tuple[int, str]:
    """كشف وحدة الجدول من نص الترويسة العربية. Returns (scale, label)."""
    t = str(text or "")
    for pat, scale, label in _UNIT_HEADER_PATTERNS_EGX:
        if re.search(pat, t, re.IGNORECASE):
            return scale, label
    return 1, ""


def normalize_parts_scale(
    parts: list[dict],
    captures: list[list[dict]],
    dominant_scale: int,
    notes: list[str],
) -> tuple[list[dict], list[list[dict]]]:
    """توحيد أجزاء الجداول لوحدة سائدة — الأجزاء التي ترويستها وحدة
    مختلفة عن السائدة تُضرب بنسبة التحويل مع إفصاح في الملاحظات.

    parts: [{page: int, ...}] مع مفتاح "unit_scale" اختياري.
    dominant_scale: مقياس المستند السائد (من detect_egx_table_unit على
    النص الغالب أو من إجمالي الصفحات).
    """
    if not parts or dominant_scale <= 0:
        return parts, captures
    changed = 0
    for i, part in enumerate(parts):
        ps = part.get("unit_scale", dominant_scale)
        if ps == dominant_scale or ps <= 0:
            continue
        ratio = dominant_scale / ps
        caps = captures[i] if i < len(captures) else []
        for cap in caps:
            for y, v in cap.items():
                if isinstance(v, (int, float)) and v:
                    cap[y] = v * ratio
        changed += 1
    if changed:
        notes.append(
            f"توحيد الوحدات: {changed} جدولاً كانت بوحدة مختلفة عن "
            f"السائدة ({dominant_scale}×) — وُحدت قبل الحساب مع الإفصاح.")
    return parts, captures


# ── 2) صيغ EAS للميزانية ──
def eas_identity_check(
    total_assets: float | None,
    total_liabilities: float | None,
    equity: float | None,
    current_assets: float | None = None,
    current_liabilities: float | None = None,
    tolerance_pct: float = 1e-6,
) -> dict:
    """فحص الهوية المحاسبية بصيغتي EAS:
    الصيغة القياسية: الأصول = الالتزامات + الملكية
    صيغة إجمالي الاستثمار: (رأس المال العامل + الأصول غير المتداولة)
                           = حقوق الملكية + الالتزامات غير المتداولة
    (بما يعادل جبريًا الصيغة القياسية لكن تُفحص عند توفر المكونات فقط)
    """
    result = {"standard": None, "investment_form": None,
              "holds": False, "basis": ""}
    tol = max(1.0, tolerance_pct * max(abs(total_assets or 0),
                                       abs(total_liabilities or 0),
                                       abs(equity or 0)))
    if all(v is not None for v in (total_assets, total_liabilities, equity)):
        diff = abs(total_assets - (total_liabilities + equity))
        result["standard"] = {"diff": diff, "ok": diff <= tol}
        result["holds"] = diff <= tol
        result["basis"] = "الأصول = الالتزامات + الملكية"
    # صيغة الاستثمار: تحتاج current_assets/current_liabilities فقط
    if all(v is not None for v in (current_assets, current_liabilities,
                                    total_assets, total_liabilities, equity)):
        nca = total_assets - current_assets
        ncl = total_liabilities - current_liabilities
        wc = current_assets - current_liabilities
        diff2 = abs((wc + nca) - (equity + ncl))
        ok2 = diff2 <= tol
        result["investment_form"] = {"diff": diff2, "ok": ok2,
                                      "wc": wc, "nca": nca, "ncl": ncl}
        if not result["holds"] and ok2:
            result["holds"] = True
            result["basis"] = ("رأس المال العامل + الأصول غير المتداولة = "
                              "حقوق الملكية + الالتزامات غير المتداولة")
    return result


# ── 3) فلتر ملاءمة القطاع ──
FINANCIAL_SECTOR_MARKERS = (
    "بنك", "مصرف", "مالي", "تمويل", "أصول مالية", "استثمار",
    "bank", "financial", "insurance", "investment",
)
SECTOR_EXCLUDED_METRICS = {
    "inventory", "inventory_turnover", "dio",
    "ccc", "cash_conversion_cycle", "altman_z",
    "quick_ratio",  # المخزون غير جوهري للبنوك
}


def sector_exclusions(sector: str) -> set[str]:
    """مفاتيح المؤشرات غير الملائمة للقطاع — N/A تلقائي مع السبب."""
    s = str(sector or "").lower()
    for marker in FINANCIAL_SECTOR_MARKERS:
        if marker in s or marker in str(sector or ""):
            return set(SECTOR_EXCLUDED_METRICS)
    return set()


# ── 4) اتساق ما-ذا-لو ──
def scenario_roe_roa_allowed(
    shock_kind: str,
    delta_net_income: float | None,
    baseline_net_income: float | None,
    curr_equity: float | None,
    curr_total_assets: float | None,
) -> tuple[bool, str]:
    """هل يُسمح بحساب ROE/ROA بعد الصدمة؟
    v6 إصلاح حديد عز (إصلاح 9): صدمة قائمة الدخل (إيرادات/تكاليف) تُغيّر
    صافي الربح لكن دون إقرار التغير في الأرباح المرحلة → حقوق الملكية
    والأصول القديمة تعطي ROE/ROA مضللة. يُسمح فقط إذا:
    - الصدمة ليست على قائمة الدخل (لا تغيير في صافي الربح)، أو
    - التغير في صافي الربح = 0 (نظرية — لا أثر ملموس).
    """
    if shock_kind not in ("income_shock",):
        return True, ""
    if delta_net_income is not None and delta_net_income != 0:
        return False, (
            "ROE/ROA غير متسقة بعد صدمة قائمة الدخل — التغير في صافي "
            "الربح لم يُمرر للأرباح المرحلة وحقوق الملكية والأصول. "
            "القيم محجوبة وفق سياسة الاتساق المحاسبي."
        )
    return True, ""
