# -*- coding: utf-8 -*-
"""تدقيق بيانات المعاينة (نقطة 1 من مراجعة v3): كل رقم/سنة/تاريخ في
mvp_preview.html يُقارن بملف TE GT المجمد — مصدر الديمو الواحد القابل
للتتبع. يرصد: قيم شركات أخرى (خلط EFG/AbuQir)، صفوف بلا أصل في TE GT،
وتواريخ خاطئة. الناتج JSON يوثق حالة المعاينة قبل/بعد الإصلاح."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ))

PREVIEW = PROJ / "design/mvp_preview.html"
GT = PROJ / "independent_docs/te_holdout/gt_te_frozen.json"
OUT = PROJ / "cell_evidence/preview_data_audit.json"

# التسمية في جدول المعاينة → الحقل في TE GT (None = لا أصل في TE GT)
ROW_MAP = {
    "ممتلكات ومعدات": "fixed_assets",
    "أصول غير ملموسة": None,
    "إجمالي الأصول غير المتداولة": None,
    "المخزون": "inventory",
    "نقدية وما في حكمها": "cash",
    "إجمالي الأصول المتداولة": "current_assets",
    "إجمالي الأصول": "total_assets",
    "دائنون وأرصدة دائنة أخرى": "accounts_payable",
    "إجمالي الالتزامات المتداولة": "current_liabilities",
    "إجمالي الالتزامات": "total_liabilities",
    "الإيرادات": "revenue",
    "تكلفة الإيرادات": "cost_of_revenue",
    "مجمل الربح": "gross_profit",
    "الربح التشغيلي": "operating_income",
    "الربح قبل الضريبة": "pretax_income",
    "ضريبة الدخل المتداولة": None,       # GT يحمل مصروف الضريبة لا التزامها
    "صافي الربح للفترة": "net_income",
    "حقوق الملكية": "equity",
    "التدفق النقدي التشغيلي": "operating_cash_flow",
    "التدفق النقدي الاستثماري": "investing_cash_flow",
    "التدفق النقدي التمويلي": "financing_cash_flow",
    "ذمم مدينة وأرصدة مدينة أخرى": "accounts_receivable",
}


def _num(tok: str) -> float | None:
    t = tok.replace(",", "").strip().replace("(", "-").replace(")", "")
    try:
        return float(t)
    except ValueError:
        return None


def main() -> dict:
    gt = json.loads(GT.read_text(encoding="utf-8"))
    html = PREVIEW.read_text(encoding="utf-8")

    issues: list[dict] = []
    checked = 0

    # 1) صفوف جدولي القوائم: <tr><td>LABEL</td>…<td class="num">V24</td>
    #    <td class="num">V23</td>… — نمط خلايا الأرقام بعد التسمية
    for m in re.finditer(
            r"<tr[^>]*><td[^>]*>(?:<b>)?([^<]{2,40})(?:</b>)?</td>"
            r"(?:<td[^>]*>[^<]*</td>)?"
            r'<td class="num[^"]*">(?:<b>)?([^<]+)(?:</b>)?</td>'
            r'<td class="num[^"]*">(?:<b>)?([^<]+)(?:</b>)?</td>',
            html):
        label = m.group(1).strip()
        field = ROW_MAP.get(label, "?")
        if field is None:
            issues.append({"kind": "row_not_in_te_gt", "label": label})
            continue
        if field == "?":
            continue                      # صف بغير خرائط التدقيق
        for idx, year in ((2, "2024"), (3, "2023")):
            shown = _num(m.group(idx))
            if shown is None:
                continue
            checked += 1
            gt_e = gt["cells"].get(year, {}).get(field)
            gt_v = float(gt_e["value"]) if gt_e else None
            if gt_v is None:
                issues.append({"kind": "value_not_in_te_gt", "label": label,
                               "year": year, "shown": shown})
            elif abs(shown - gt_v) > 0.5:
                issues.append({"kind": "value_mismatch", "label": label,
                               "year": year, "shown": shown, "te_gt": gt_v,
                               "delta": shown - gt_v})

    # 2) التواريخ: SOFP المرحلي بتاريخ 30/06/2024 (مقابله 31/12/2023)
    for bad in ("31/12/2024",):
        if bad in html:
            issues.append({"kind": "wrong_date", "shown": bad,
                           "expected": "30/06/2024 (قائمة المركز المالي)"})

    # 3) صيغة الوحدة القديمة (M) داخل نصوص الديمو
    old_m = re.findall(r"ج\.م\d+\.?\d*M\b", html)
    if old_m:
        issues.append({"kind": "old_unit_notation", "samples": old_m[:6],
                       "count": len(old_m)})

    out = {"audited_values": checked, "issues": issues,
           "issue_count": len(issues),
           "source_of_truth": "independent_docs/te_holdout/gt_te_frozen.json",
           "note": "المعاينة ديمو من تشغيل TE الموثق — ليست استخراجًا جديدًا"
                   " ولا تُستهلك في الإنتاج."}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"checked={checked} issues={len(issues)}")
    for i in issues[:25]:
        print(" -", json.dumps(i, ensure_ascii=False)[:150])
    print(f"artifact: {OUT}")
    return out


if __name__ == "__main__":
    main()
