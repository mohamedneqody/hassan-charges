# -*- coding: utf-8 -*-
"""رحلة المستخدم الكاملة E2E — الواجهة الجديدة المدمجة في Streamlit (v5).

ملف PDF حقيقي كامل (abuqir_fs_fy2025.pdf) عبر الـPipeline الحي — لا GT
ولا بيانات تجريبية. تُلتقط لقطات لكل مرحلة وتُسجل النتائج JSON."""
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

PROJ = Path(__file__).resolve().parents[1]
SHOTS = PROJ / "design" / "ui_merge_shots"
SHOTS.mkdir(parents=True, exist_ok=True)
PDF = PROJ / "independent_docs" / "abuqir_2023" / "abuqir_fs_fy2025.pdf"
BASE = "http://localhost:8765"
results = {"steps": {}, "started": time.strftime("%H:%M:%S")}


def click_tab(pg, text, tries=4):
    """نقر تبويب Streamlit: get_by_text يعمل مع تبويبات هذا الإصدار —
    إعادة محاولة لأن الصفحة الطويلة يعاد رسمها أثناء الاستقرار."""
    for _ in range(tries):
        loc = pg.get_by_text(text)
        if loc.count():
            try:
                loc.first.click(timeout=5000)
                time.sleep(2)
                return True
            except Exception:
                pass
        time.sleep(2)
    return False


def shot(pg, name):
    pg.screenshot(path=str(SHOTS / f"{name}.png"), full_page=False)
    results["steps"][name] = "captured"


def click_when_visible(pg, selector, timeout=8000):
    pg.wait_for_selector(selector, timeout=timeout)
    pg.click(selector)


with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1720, "height": 950},
                    device_scale_factor=1)
    pg.goto(BASE)
    pg.wait_for_selector("input[type=file]", state="attached", timeout=20000)
    pg.locator("input[type=file]").set_input_files(str(PDF))
    time.sleep(1)
    shot(pg, "01_upload")
    # حلّل القوائم المالية
    pg.get_by_text("🔍 حلّل القوائم المالية").first.click()
    results["steps"]["extraction_started"] = time.strftime("%H:%M:%S")
    # انتظار انتهاء الاستخراج الحي (شريط الحالة يختفي ويظهر الداشبورد)
    pg.wait_for_selector("text=نظرة عامة", timeout=900000)
    results["steps"]["extraction_done"] = time.strftime("%H:%M:%S")
    time.sleep(2)
    shot(pg, "02_classic_dashboard")
    results["steps"]["classic_intact"] = True

    # التبديل للواجهة الجديدة — مدخل الـtoggle مخفي بصريًا فننقره بـJS
    toggled = pg.evaluate("""() => {
      const lbls = [...document.querySelectorAll(
        'section[data-testid="stSidebar"] label')];
      const t = lbls.find(l => l.textContent.includes('الواجهة الجديدة'));
      if (!t) return false;
      const inp = t.querySelector('input');
      if (inp) { inp.click(); return true; }
      t.click(); return true;
    }""")
    time.sleep(4)
    shot(pg, "03_new_ui_dashboard")
    results["steps"]["new_ui_reached"] = toggled

    # القوائم والخانات
    pg.get_by_text("📋 القوائم والخانات").first.click()
    time.sleep(2)
    shot(pg, "04_statements_cells")
    # فتح دليل أول خانة
    ev_btns = pg.get_by_text("🔍 فتح الدليل")
    results["steps"]["evidence_buttons"] = ev_btns.count()
    if ev_btns.count():
        ev_btns.first.click()
        time.sleep(2.5)
        shot(pg, "05_source_evidence")

    # المؤشرات + الدرجة
    results["steps"]["tab_06_metrics"] = click_tab(pg, "📈 المؤشرات المالية")
    shot(pg, "06_metrics")
    results["steps"]["tab_07_health"] = click_tab(pg, "❤️ الدرجة الصحية")
    shot(pg, "07_health")

    # Gemini
    results["steps"]["tab_08_gemini"] = click_tab(pg, "✦ تفسير Gemini")
    shot(pg, "08_gemini")

    # RAG (يعاد استخدام الكلاسيكي)
    results["steps"]["tab_09_rag"] = click_tab(pg, "💬 محادثة المستند (RAG)")
    shot(pg, "09_rag")

    # المراجعة البشرية الحية: لمسار النص (AbuQir) لا صفحات مصدر مسجلة —
    # الطابور فارغ بصدق والواجهة تعرض السبب؛ اختبار الرفض الموقّع في رحلة B
    results["steps"]["tab_10_review_panel"] = click_tab(pg, "✍️ مراجعة بشرية")
    shot(pg, "10_review_panel")
    body = pg.inner_text("body")
    results["steps"]["review_empty_honest"] = (
        "لا خانات بانتظار مراجعة" in body
        or "No cells awaiting review" in body)
    results["steps"]["pin_input_present"] = pg.locator(
        'input[type="password"]').count()

    # التقارير: تنزيل Excel
    results["steps"]["tab_12_reports"] = click_tab(pg, "📄 التقارير")
    shot(pg, "12_reports")
    try:
        with pg.expect_download(timeout=30000) as dl_info:
            pg.get_by_text("⬇️ Excel (.xlsx)").first.click()
        dl = dl_info.value
        out = SHOTS / "e2e_download.xlsx"
        dl.save_as(str(out))
        results["steps"]["xlsx_download"] = {
            "ok": out.exists(), "size": out.stat().st_size}
    except Exception as exc:
        results["steps"]["xlsx_download"] = {"ok": False, "err": str(exc)[:120]}

    # تبديل اللغة EN/LTR
    pg.get_by_text("English / عربي").first.click()
    time.sleep(2)
    shot(pg, "13_en_ltr")
    pg.get_by_text("عربي / English").first.click()
    time.sleep(1.5)

    # العودة للكلاسيكية — النتائج لا تُفقد
    pg.get_by_text("عودة للواجهة الكلاسيكية").first.click()
    time.sleep(2.5)
    shot(pg, "14_back_to_classic")
    results["steps"]["back_to_classic"] = pg.locator(
        "text=نظرة عامة").count() > 0

    b.close()

results["finished"] = time.strftime("%H:%M:%S")
out = PROJ / "cell_evidence" / "ui_merge_e2e.json"
out.write_text(json.dumps(results, ensure_ascii=False, indent=1),
               encoding="utf-8")
print(json.dumps(results, ensure_ascii=False, indent=1))
print(f"artifact: {out}")
