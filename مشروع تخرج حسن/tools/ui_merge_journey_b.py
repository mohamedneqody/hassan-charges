# -*- coding: utf-8 -*-
"""رحلة B — مستند ممسوح كامل (TE) عبر مسار الرؤية: أدلة بصفحات وبbox
حقيقية + مراجعة حية بالرفض الموقّع. إن حُجبت الحصة يوثَّق السبب."""
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

PROJ = Path(__file__).resolve().parents[1]
SHOTS = PROJ / "design" / "ui_merge_shots"
PDF = PROJ / "independent_docs" / "te_holdout" / "te_standalone_h1_2024.pdf"
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
    pg.screenshot(path=str(SHOTS / f"{name}.png"))
    results["steps"][name] = "captured"


with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1720, "height": 950})
    pg.goto(BASE, wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_selector("input[type=file]", state="attached", timeout=30000)
    pg.locator("input[type=file]").set_input_files(str(PDF))
    time.sleep(1)
    shot(pg, "b01_upload_te")
    pg.get_by_text("🔍 حلّل القوائم المالية").first.click()
    results["steps"]["extraction_started"] = time.strftime("%H:%M:%S")
    pg.wait_for_selector("text=نظرة عامة", timeout=1200000)
    results["steps"]["extraction_done"] = time.strftime("%H:%M:%S")
    time.sleep(2)

    # التبديل للواجهة الجديدة
    pg.evaluate("""() => {
      const lbls = [...document.querySelectorAll(
        'section[data-testid="stSidebar"] label')];
      const t = lbls.find(l => l.textContent.includes('الواجهة الجديدة'));
      const inp = t && t.querySelector('input');
      if (inp) inp.click(); else if (t) t.click();
    }""")
    time.sleep(4)
    shot(pg, "b02_new_ui")

    # القوائم: افتح دليل أول خانة (مسار الرؤية = صفحات + bbox)
    pg.get_by_text("📋 القوائم والخانات").first.click()
    time.sleep(2.5)
    shot(pg, "b03_statements")
    ev = pg.get_by_text("🔍 فتح الدليل")
    results["steps"]["evidence_buttons"] = ev.count()
    if ev.count():
        ev.first.click()
        time.sleep(3)
        shot(pg, "b04_evidence_bbox")

    # المراجعة الحية — انتظر حقول المراجعة (بناء الطابور يرندر صفحات)
    pg.get_by_text("✍️ مراجعة بشرية").first.click()
    try:
        pg.wait_for_selector('input[type="password"]', timeout=120000,
                             state="attached")
    except Exception:
        pass
    time.sleep(4)
    shot(pg, "b05_review")
    results["steps"]["has_pin_input"] = pg.locator(
        'input[type="password"]').count() > 0
    if results["steps"]["has_pin_input"]:
        pg.locator('input[aria-label*="PIN"]').first.fill("5941")
        ta = pg.locator("textarea").first
        if ta.count():
            ta.fill("رفض حي — القيمة تحتاج تأكيدًا من المصدر الورقي "
                    "(رحلة دمج الواجهة v5).")
        # التأكيدات الأربعة: مدخلات مخفية داخل labels — نقر JS عليها
        checked = pg.evaluate("""() => {
          const boxes = [...document.querySelectorAll(
            'input[type="checkbox"]')];
          let n = 0;
          for (const b of boxes) {
            if (!b.checked) { b.click(); n += 1; }
          }
          return n;
        }""")
        time.sleep(1.5)
        results["steps"]["confirmations_checked"] = checked
        pg.locator('input[aria-label="اسم المراجع"]').first.fill(
            "test-reviewer")
        btn = pg.get_by_text("🗑️ تسجيل الرفض في السلسلة")
        if btn.count():
            btn.first.click()
            time.sleep(3)
            shot(pg, "b06_review_recorded")
            body = pg.inner_text("body")
            results["steps"]["reject_recorded"] = ("✓" in body) or \
                ("سُجل" in body)
            results["steps"]["reject_error"] = [ln for ln in
                                                body.splitlines()
                                                if "رفض السلسلة" in ln][:1]
    b.close()

results["finished"] = time.strftime("%H:%M:%S")
out = PROJ / "cell_evidence" / "ui_merge_e2e_b.json"
out.write_text(json.dumps(results, ensure_ascii=False, indent=1),
               encoding="utf-8")
print(json.dumps(results, ensure_ascii=False, indent=1))
print(f"artifact: {out}")
