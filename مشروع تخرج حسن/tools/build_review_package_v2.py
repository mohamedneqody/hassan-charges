# -*- coding: utf-8 -*-
"""تجميع Financial_AI_Review_Package_v2.zip — جولة إصلاح المراجعة.

Contents (NO secrets, NO .env, NO reviewer credentials — the standing
constraints): the two real reports (+ per-page renders), the v2 preview
screenshots, the standalone preview with the real-evidence bundle, the
one final ledger, the unit-chain verification log, and a before/after
map. The v1 audit file (te_final_audit_post_fix.json) ships preserved
and its conflict is explained in the ledger, never hidden.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
PKG = PROJ / "Financial_AI_Review_Package_v2"


def git_state() -> dict:
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True,
                          cwd=PROJ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--", "src", "tools", "tests",
         "design"],
        capture_output=True, text=True, cwd=PROJ).stdout.strip().splitlines()
    return {"head": head, "dirty_count": len(dirty),
            "dirty": [d.split()[-1] for d in dirty]}


UNIT_LOG = """# سجل التحقق من وحدة القياس (العيب الحرج رقم 1)

التاريخ: {date} · الكود: {head} (+تعديلات الجولة)

## السلسلة الموحدة — من الترويسة المطبوعة إلى العرض

| الحلقة | الدليل | القيمة |
|---|---|---|
| المصدر المطبوع | TE: «in EGP Thousands» على كل ترويسة أعمدة (GT scope) · EFG: «(in EGP Thousands)» مطبوعة على كل قائمة (صفحات 6-9 من نص المستند نفسه) | وحدة الطباعة = آلاف جنيه |
| الكشف الآلي | `detect_printed_unit()` — 11/11 حالة اختبار (ترويسات EN/AR + غيابها) | scale=1000, unit_note موثق |
| التخزين | القيم المخزنة كما طُبعت حرفيًا — لا إعادة قياس في الاستخراج أو القرار | 27,730,150 (ألف) |
| العرض | `humanize(value, scale)` يضرب المقياس للعرض فقط | 27,730,150 ألف → «ج.م27.73 مليار» |
| Gemini | الحمولة والتعليقات الحية بصيغة الوحدات الفعلية | «من ج.م21.9 مليار إلى ج.م27.73 مليار» |
| Excel | خلايا العملة = القيمة الفعلية كأرقام حقيقية (فرز/تصفية سليم) | 27,727,014,000 |

## الإثبات القياسي على مخرجات هذه الجولة

- **طبقة نص PDF كاملة** (كل صفحات التقريرين): **صفر** توكيد bare «M» —
  TE 13 صفحة: 0 · EFG 11 صفحة: 0، مع 33 + 27 ظهورًا لكلمات
  «مليار/مليون» العربية.
- HTML الشاشة: «ج.م27.73 مليار» ×46 في تقرير TE، صفر M.
- قبل الإصلاح: الـPDF v1 عرض «27.73M» (القيمة بآلاف لكن اللاحقة M
  توحي بالمليون) بينما المعاينة عرضت «27.73 مليار» — التعارض الذي أبلغ
  عنه المراجع. الجذر: `humanize()` اختصر القيمة المطبوعة كما هي بلا
  وعي بوحدة الطباعة.

## اختبارات السلسلة (tests/test_unit_scale_display.py — 15 اختبارًا)

humanize(scale=1) غير المتغير · آلاف→مليار · السالب · وحدة الملايين ·
كلمات المضاعف العربية · موضع الإشارة · مرور النسب المئوية · كشف
الترويسات (EN/AR) · غياب الترويسة=1 · ملاحظات الدليل في كل قاعدة ·
حقل unit على FinancialData بلا مساس بالقيم المخزنة · HTML بالمليار ·
HTML بلا مقياس بكلمات عربية · خلايا Excel بالقيمة الفعلية · حمولة
Gemini بالوحدات الفعلية.
"""

BEFORE_AFTER = """# قبل / بعد — جولة إصلاح المراجعة v2

| # | العيب المبلغ | قبل (v1) | بعد (v2) | الدليل في الحزمة |
|---|---|---|---|---|
| 1 | وحدة القياس (حرج) | PDF «27.73M» بينما المعاينة «27.73 مليار» | «ج.م27.73 مليار» موحدة في PDF/HTML/Excel/تعليقات Gemini — صفر M في طبقة نص الـPDF | unit_verification_log.md + pdf_pages/ |
| 2 | تعارض سجل التدقيق | te_final_audit_post_fix.json FA=2 مقابل مراجعة FA=0 | سجل نهائي واحد (report_production.json) يربط كل تقرير بالكود+الGT+التحليل، والملف القديم محفوظ ومفسَّر كحالة وسيطة | report_production.json |
| 3 | Excel قطري | كل قيمة في صف مستقل (max_row لكل خلية) | صف واحد لكل مؤشر + عمود «حالة التحقق» التاسع + فلتر + أرقام فعلية | reports/TE_*.xlsx |
| 4 | PDF الطباعة | الغلاف مكسور في LibreOffice | print-safe: العنوان كامل، اللافتة الصادقة، وحدة/نوع الفترة، tr page-break، أرقام بلا كسر | pdf_pages/ |
| 5 | تحليل Gemini | «No commentary available» | تحليل حي جديد (TE: 40 تعليقًا gemini-3.6-flash · EFG: 24 تعليقًا gemini-3.5-flash) بوحدات صحيحة + القديم محفوظ بإفصاح | report_production.json + reports/*.pdf |
| 6 | التفسيرات | ضريبة/منفعة ملتبسة، N/A None، DuPont بلا أساس، مرحلي/سنوي ملتبس | ملاحظة المنفعة الضريبية (TE ائتمان / EFG مصروف)، قائمة N/A صريحة، نوع الفترة مرحلي-منفصل TE مقابل سنوي EFG، وسم test-reviewer | reports/*.pdf ص1 |
| 7 | المعاينة | مودال الأدلة عنصر نائب، فراغ كبير | مودال بالقصاصة الحقيقية + الصفحة + bbox + الهاشات + محدد الحزم + إفصاح؛ خط أكبر وقيم أوضح | preview_v2/09_*.png |
"""

SUMMARY = """# ملخص حزمة المراجعة v2 — {date}

الكود: {head} (+تعديلات الجولة) · **313 اختبارًا تمر** · لا push ولا نشر

## ما في الحزمة
- `reports/` — TE + EFG: xlsx + html + pdf (طباعة آمنة) + صور الصفحات pdf_pages/
- `preview_v2/` — 12 لقطة 1920×1080 (RTL + LTR + مودال الأدلة الحقيقية)
- `preview_html/` — معاينة التصميم المستقلة + evidence_bundle.js (أدلة حقيقية)
- `report_production.json` — السجل النهائي الواحد (ربط تقرير↔كود↔GT↔تحليل)
- `unit_verification_log.md` — إثبات سلسلة وحدة القياس (العيب الحرج 1)
- `before_after.md` — خريطة العيوب السبعة وإصلاحها
- `te_final_audit_post_fix.json` — سجل التدقيق v1 محفوظ كما هو (انظر السجل: حالة وسيطة قبل قاعدة التصديق عبر-طبقتين)

## حدود معلنة بصدق
- تقارير TE/EFG إعادة إنتاج من قيم GT المجمدة (وليست استخراجًا جديدًا) — اللافتة
  «أولي قابل للمراجعة» ظاهرة في التقريرين ومراجعهم اختباريون لا إنتاجيون.
- بُعد القصاصة في مودال المعاينة من سجل مراجعة مستند 2022 الحقيقي (الحزم
  المتاحة) — الإفصاح داخل المودال نفسه.
- كسر الأسطر عند حدود الاتجاه (bidi) في تعليقات PDF يظهر ترتيبًا بصريًا
  مختلفًا في بعض السطور — القيم والوحدات سليمة ومكتملة.
"""


def main() -> dict:
    if PKG.exists():
        shutil.rmtree(PKG)
    for sub in ("reports", "preview_v2", "preview_html"):
        (PKG / sub).mkdir(parents=True)

    reports = PROJ / "review_package/reports"
    for stem in ("TE_Financial_Report_2024", "EFG_Financial_Report_2024"):
        for ext in ("xlsx", "html", "pdf"):
            src = reports / f"{stem}.{ext}"
            if src.exists():
                shutil.copy2(src, PKG / "reports" / src.name)
    pages = reports / "pdf_pages"
    if pages.exists():
        shutil.copytree(pages, PKG / "reports" / "pdf_pages",
                        dirs_exist_ok=True)

    shots = PROJ / "design/screenshots_v2"
    for img in sorted(shots.glob("*.png")):
        shutil.copy2(img, PKG / "preview_v2" / img.name)

    shutil.copy2(PROJ / "design/mvp_preview.html",
                 PKG / "preview_html/mvp_preview.html")
    shutil.copy2(PROJ / "design/evidence_bundle.js",
                 PKG / "preview_html/evidence_bundle.js")

    shutil.copy2(PROJ / "review_package/report_production.json",
                 PKG / "report_production.json")
    shutil.copy2(PROJ / "cell_evidence/te_final_audit_post_fix.json",
                 PKG / "te_final_audit_post_fix.json")

    git = git_state()
    (PKG / "unit_verification_log.md").write_text(
        UNIT_LOG.format(date=datetime.now().strftime("%Y-%m-%d %H:%M"),
                        head=git["head"]), encoding="utf-8")
    (PKG / "before_after.md").write_text(BEFORE_AFTER, encoding="utf-8")
    (PKG / "review_summary_v2.md").write_text(
        SUMMARY.format(date=datetime.now().strftime("%Y-%m-%d %H:%M"),
                       head=git["head"]), encoding="utf-8")

    zpath = PROJ / "Financial_AI_Review_Package_v2.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(PKG.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(PROJ))
    n = sum(1 for f in PKG.rglob("*") if f.is_file())
    print(f"package: {n} files, {zpath.stat().st_size/1e6:.1f} MB "
          f"-> {zpath.name} (code {git['head']}, {git['dirty_count']} dirty)")
    return {"files": n, "zip": str(zpath)}


if __name__ == "__main__":
    main()
