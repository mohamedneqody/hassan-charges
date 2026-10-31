"""Evaluate selftest_2022_results.json against the hand-audited ground truth
(the user's own digit-level audit from 2026-10-07 + later verified runs).

Statuses: EXACT (±1) | CLOSE (≤0.5% rel) | MISMATCH | MISSING.
Approximate GT figures (audited as rounded billions / percents) get 1-2% bands
and are labeled [تقريبي]. Prints problem counts at the end.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parent
DATA = json.loads((PROJ / "selftest_2022_results.json").read_text(encoding="utf-8"))

# (field, year, GT value, tolerance, exact?)
# GT SETTLED 2026-10-31 from high-res page crops of the printed document
# (eval_pages/) + internal arithmetic (revenue − COGS = GP as printed;
# pretax − tax = NI as printed). The old "13,196,156,088" revenue-2021 and
# "1,175,759" pretax entries were transcription/Indra errors — the printed
# document and the system agree on 13,169,656,088 and 1,236,363,213.
GT = [
    ("revenue",             "prev", 13_169_656_088, 1, True),   # settled from page 6 crop + GP arithmetic
    ("revenue",             "curr", 16_665_919_878, 1, True),
    ("net_income",          "prev", 288_152_668, 1, True),      # printed; system vote took …153,668 (1-digit defect)
    ("net_income",          "curr", 1_056_737_086, 1, True),
    ("total_assets",        "prev", 14_614_683_997, 1, True),
    ("total_assets",        "curr", 15_965_646_460, 1, True),
    ("operating_cash_flow", "curr", 1_214_507_829, 1, True),
    ("pretax_income",       "curr", 1_236_363_213, 1, True),    # settled from page 6 crop
    ("income_tax_expense",  "curr", -179_626_127, 1, True),     # إجمالي ضريبة الدخل عن العام (printed)
    ("financing_cash_flow", "curr", -727_063_341, 1, True),     # settled from page 9 crop
    ("investing_cash_flow", "curr", 722_097_212, 1, True),      # page 9 [تقريبي — arithmetic gap]
    ("gross_profit",        "prev", 1_197_622_108, 1, True),    # revenue − COGS as printed
    ("total_liabilities",   "prev", 8_250_000_000, 0.02, False),  # ≈8.25B [تقريبي]
    ("total_liabilities",   "curr", 9_030_000_000, 0.02, False),  # ≈9.03B [تقريبي]
    ("current_liabilities", "prev", 7_030_000_000, 0.01, False),  # = 48.1% من الأصول (نسبة مدققة)
    ("current_liabilities", "curr", 8_300_000_000, 0.03, False),  # ≈52.0% من الأصول
]

GT_RATIOS = [
    ("debt_ratio", 0.565, 0.012),
    ("equity_ratio", 0.435, 0.012),
    ("financial_leverage", 2.30, 0.05),
    ("asset_turnover", 1.09, 0.06),
]

AR = {"revenue": "الإيرادات", "net_income": "صافي الربح",
      "operating_cash_flow": "التدفق التشغيلي", "total_assets": "إجمالي الأصول",
      "total_liabilities": "إجمالي الالتزامات", "current_liabilities": "الالتزامات المتداولة"}


def status(extracted, gt, tol, is_exact):
    if extracted is None:
        return "MISSING"
    if is_exact:
        if abs(extracted - gt) <= 1:
            return "EXACT"
        rel = abs(extracted - gt) / abs(gt)
        return "CLOSE" if rel <= 0.005 else "MISMATCH"
    rel = abs(extracted - gt) / abs(gt)
    return "CLOSE" if rel <= tol else "MISMATCH"


def main() -> int:
    prev_y, curr_y = DATA["prev_year"], DATA["curr_year"]
    print(f"الشركة: {DATA['company']} | العملة: {DATA.get('currency_hint')} | "
          f"السنوات: {DATA['years']} | الزمن: {DATA['elapsed_s']}s | صفوف المؤشرات: {DATA['rows_count']}")
    print("=" * 100)

    counts = {"EXACT": 0, "CLOSE": 0, "MISMATCH": 0, "MISSING": 0}
    problems: list[str] = []
    for field, which, gt, tol, is_exact in GT:
        extracted = DATA[which].get(field)
        st = status(extracted, gt, tol, is_exact)
        counts[st] += 1
        year = prev_y if which == "prev" else curr_y
        mark = "" if is_exact else " [تقريبي]"
        ext_txt = f"{extracted:,.0f}" if isinstance(extracted, (int, float)) else "—"
        print(f"{AR.get(field, field):<22} {year} | GT: {gt:>16,.0f}{mark} | "
              f"المستخرج: {ext_txt:>16} | {st}")
        if st in ("MISMATCH", "MISSING"):
            problems.append(f"{field} {year}: {st} (GT {gt:,.0f})")

    print("-" * 100)
    curr = DATA["curr"]
    for field, gt, tol in GT_RATIOS:
        v = curr.get(field)
        if v is None:
            st = "MISSING"; counts["MISSING"] += 1; problems.append(f"{field}: MISSING")
        else:
            ok = abs(v - gt) <= tol
            st = "EXACT" if ok else "MISMATCH"
            counts[st] += 1
            if not ok:
                problems.append(f"{field}: {v} vs GT {gt}")
        print(f"نسبة {field:<22} | GT≈ {gt} | المستخرج: {v if v is not None else '—'} | {st}")

    # accounting identity on the extracted numbers themselves
    print("-" * 100)
    for which, year in (("prev", prev_y), ("curr", curr_y)):
        d = DATA[which]
        ta, tl, eq = d.get("total_assets"), d.get("total_liabilities"), d.get("equity")
        if None not in (ta, tl, eq):
            gap = ta - (tl + eq)
            rel = abs(gap) / ta * 100
            print(f"هوية الميزانية {year}: الأصول {ta:,.0f} مقابل الالتزامات+حقوق الملكية "
                  f"{tl + eq:,.0f} — فرق {gap:+,.0f} ({rel:.2f}%)")
            if rel > 1.0:
                problems.append(f"identity {year}: gap {rel:.1f}%")

    print("-" * 100)
    h = DATA["health"]
    print(f"الدرجة الصحية: {h['total']} ({h['label']}) | أعلام حمراء: {len(DATA['red_flags'])} | "
          f"Beneish: {DATA['beneish']['m_score']} ({DATA['beneish']['zone']}) | "
          f"أوراق مكتبة الشركات: {DATA['library_records']} | شذوذ: {len(DATA['anomalies'])}")
    for m in DATA["academic"]:
        print(f"  {m['key']:<12} = {m['value']} [{m['zone']}] {m['verdict'][:60]}"
              + (f" | ناقص: {','.join(m['missing'])}" if m["missing"] else ""))
    warn_notes = [n for n in DATA["notes"] if ("⚠" in n or "FAILED" in n or "تحقق" in n and "فشل" in n)]
    print(f"ملاحظات استخراج: {len(DATA['notes'])} (منها تحذيرية: {len(warn_notes)})")
    for n in warn_notes[:8]:
        print(f"  ⚠ {n[:110]}")

    print("=" * 100)
    print(f"الملخص: EXACT={counts['EXACT']} CLOSE={counts['CLOSE']} "
          f"MISMATCH={counts['MISMATCH']} MISSING={counts['MISSING']} | "
          f"مشاكل مسجلة: {len(problems)}")
    for p in problems:
        print(f"  ✗ {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
