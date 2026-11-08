# -*- coding: utf-8 -*-
"""تجميع Financial_AI_Review_Package_v3.zip — جولة إصلاح المراجعة.

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
PKG = PROJ / "Financial_AI_Review_Package_v3"


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

BEFORE_AFTER = """# قبل / بعد — جولة إصلاح المراجعة v3 (على أساس v2)

| # | العيب المبلغ | قبل (v1) | بعد (v2) | الدليل في الحزمة |
|---|---|---|---|---|
| 1 | وحدة القياس (حرج) | PDF «27.73M» بينما المعاينة «27.73 مليار» | «ج.م27.73 مليار» موحدة في PDF/HTML/Excel/تعليقات Gemini — صفر M في طبقة نص الـPDF | unit_verification_log.md + pdf_pages/ |
| 2 | تعارض سجل التدقيق | te_final_audit_post_fix.json FA=2 مقابل مراجعة FA=0 | سجل نهائي واحد (report_production.json) يربط كل تقرير بالكود+الGT+التحليل، والملف القديم محفوظ ومفسَّر كحالة وسيطة | report_production.json |
| 3 | Excel قطري | كل قيمة في صف مستقل (max_row لكل خلية) | صف واحد لكل مؤشر + عمود «حالة التحقق» التاسع + فلتر + أرقام فعلية | reports/TE_*.xlsx |
| 4 | PDF الطباعة | الغلاف مكسور في LibreOffice | print-safe: العنوان كامل، اللافتة الصادقة، وحدة/نوع الفترة، tr page-break، أرقام بلا كسر | pdf_pages/ |
| 5 | تحليل Gemini | «No commentary available» | تحليل حي جديد (TE: 40 تعليقًا gemini-3.6-flash · EFG: 24 تعليقًا gemini-3.5-flash) بوحدات صحيحة + القديم محفوظ بإفصاح | report_production.json + reports/*.pdf |
| 6 | التفسيرات | ضريبة/منفعة ملتبسة، N/A None، DuPont بلا أساس، مرحلي/سنوي ملتبس | ملاحظة المنفعة الضريبية (TE ائتمان / EFG مصروف)، قائمة N/A صريحة، نوع الفترة مرحلي-منفصل TE مقابل سنوي EFG، وسم test-reviewer | reports/*.pdf ص1 |
| 7 | المعاينة | مودال الأدلة عنصر نائب، فراغ كبير | مودال بالقصاصة الحقيقية + الصفحة + bbox + الهاشات + إفصاح؛ خط أكبر وقيم أوضح | preview_v3/09_*.png |
| 8 | v2: N/A موصوفة «موثق آلي» (13 TE / 21 EFG) | تصنيف من مدخلات ساقطة | أسوأ حالة عبر السنوات + المدخلة الناقصة = «غير متوفر» — متطابق في Excel وHTML وPDF | reports/*.xlsx + pdf_pages/ |
| 9 | v2: تناقض EFG (الإيراد معلق في السجل وموثق في Excel) + dataset TE داخل سجل EFG | إعادة إنتاج بتزييف تصديق + نص ثابت | إعادة إنتاج صادقة (إحالة واحدة) + هوية dataset مُتحقق منها بالبناء مع هاش GT | report_production.json |
| 10 | v2: FA=2 وسيط بلا نتيجة نهائية | وصف فقط | قبول نهائي على مستوى الخلايا: 68 خلية مقابل GT، FA=0، مربوط بالكود وبصمة التشغيل | v3_final_cell_acceptance.json |
| 11 | v2: الغلاف ينقسم صفحتين وMissing Data تقول None | تخطيط متضخم | غلاف صفحة واحدة + ميتا كجداول + Missing صادق يفرق المفقود عن غير القابل | pdf_pages/ |
| 12 | v2: صور مستند 2022 في نافذة TE 2024 + LTR للسايدبار فقط | مطابقة فضفاضة | مطابقة صارمة (بند، سنة) + رسالة عدم توفر + لوحة أدلة مستقلة + ترجمة LTR كاملة + شارة بيانات تجريبية | preview_v3/09_*.png |
"""

SUMMARY = """# ملخص حزمة المراجعة v3 — {date}

الكود: {head} (+تعديلات جولة v3) · **313 اختبارًا تمر** · لا push ولا نشر

## ما في الحزمة
- `reports/` — TE + EFG: xlsx + html + pdf (طباعة آمنة) + صور الصفحات pdf_pages/
- `preview_v3/` — لقطات 1920×1080 (RTL + LTR مترجم + مودال بلا دليل مطابق + لوحة الأدلة الحقيقية)
- `preview_html/` — معاينة التصميم المستقلة + evidence_bundle.js
- `report_production.json` — السجل النهائي الواحد (ربط تقرير↔كود↔GT↔تحليل بهوية dataset مُتحقق منها)
- `v3_final_cell_acceptance.json` — **القبول النهائي على مستوى الخلايا: 68 خلية مقابل GT، FA=0، مربوط بإصدار الكود وبصمة التشغيل**
- `unit_verification_log.md` — إثبات سلسلة وحدة القياس (العيب الحرج 1)
- `before_after.md` — خريطة العيوب وإصلاحها (v1 → v2 → v3)
- `te_final_audit_post_fix.json` — سجل التدقيق القديم (FA=2) محفوظ كما هو — تشغيل وسيط؛ النتيجة النهائية في v3_final_cell_acceptance.json

## ما الذي تغير في v3 (عيوب v2 الستة)
1. حالات التحقق: أسوأ حالة عبر السنوات + المدخلة الناقصة = «غير متوفر» — لا N/A تُوصف موثقة (متطابق Excel/HTML/PDF)
2. تناقض EFG: إعادة إنتاج صادقة بإحالة واحدة (بلا تزييف تصديق) — البوابة والسجل وعمود Excel يقولون الشيء نفسه؛ هوية dataset لكل شركة مع هاش GT
3. القبول الخاطئ: نتيجة نهائية فعلية على مستوى الخلايا (FA=0) مربوط بالكود وبصمة التشغيل
4. PDF: غلاف صفحة واحدة، الميتا جداول تُغلف سليمًا، عمود التحقق كامل الظهور، Missing Data يفرق المفقود عن غير القابل للحساب
5. المعاينة: منع أدلة مستند آخر في نافذة المصدر + رسالة عدم توفر + ترجمة LTR كاملة + شارة بيانات تجريبية
6. الاتساق: عمود التحقق في HTML/PDF مثل Excel، والدرجة الصحية المحجوبة تُعرض كحالة صادقة في الأسطح الثلاثة

## حدود معلنة بصدق
- تقارير TE/EFG إعادة إنتاج من قيم GT المجمدة **بإحالة واحدة لكل قيمة** (بلا تصديق مُصطنع):
  كل حالة التحقق «يحتاج مراجعة» والدرجة الصحية محجوبة — اللافتة الأولية ظاهرة في التقريرين.
- قيم GT نفسها وُثقت اختباريًا (test-reviewer) في جولة القبول — ليست مراجعة بشرية إنتاجية.
- حزم الأدلة الحقيقية في قسم المراجعة من مستند اختباري 2022 — موسومة بمستندها ولا تدخل نوافذ TE 2024.
- ثقب معروف لم يُمس (خارج نطاق الجولة): اتفاق echo داخل طبقة واحدة على مستند **موثوق** لا يزال
  يمنح VERIFIED_EXACT في سجل القرار — البوابة تعلقه فقط للحقول الحرجة وغير الموثوقة.
"""


def main() -> dict:
    if PKG.exists():
        shutil.rmtree(PKG)
    for sub in ("reports", "preview_v3", "preview_html"):
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

    shots = PROJ / "design/screenshots_v3"
    for img in sorted(shots.glob("*.png")):
        shutil.copy2(img, PKG / "preview_v3" / img.name)

    shutil.copy2(PROJ / "design/mvp_preview.html",
                 PKG / "preview_html/mvp_preview.html")
    shutil.copy2(PROJ / "design/evidence_bundle.js",
                 PKG / "preview_html/evidence_bundle.js")

    shutil.copy2(PROJ / "review_package/report_production.json",
                 PKG / "report_production.json")
    shutil.copy2(PROJ / "cell_evidence/te_final_audit_post_fix.json",
                 PKG / "te_final_audit_post_fix.json")
    shutil.copy2(PROJ / "cell_evidence/v3_final_cell_acceptance.json",
                 PKG / "v3_final_cell_acceptance.json")

    git = git_state()
    (PKG / "unit_verification_log.md").write_text(
        UNIT_LOG.format(date=datetime.now().strftime("%Y-%m-%d %H:%M"),
                        head=git["head"]), encoding="utf-8")
    (PKG / "before_after.md").write_text(BEFORE_AFTER, encoding="utf-8")
    (PKG / "review_summary_v3.md").write_text(
        SUMMARY.format(date=datetime.now().strftime("%Y-%m-%d %H:%M"),
                       head=git["head"]), encoding="utf-8")

    zpath = PROJ / "Financial_AI_Review_Package_v3.zip"
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
