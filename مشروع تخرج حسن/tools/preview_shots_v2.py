# -*- coding: utf-8 -*-
"""لقطات المعاينة بعد جولة الإصلاح (v2): 1920x1080، كل الأقسام + مودال
الأدلة الحقيقية (القصاصة + الصفحة مع bbox) + EN/LTR."""
from playwright.sync_api import sync_playwright

OUT = "design/screenshots_v2"

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1920, "height": 1080},
                    device_scale_factor=1)
    pg.goto("http://localhost:8901/mvp_preview.html")
    pg.wait_for_timeout(900)

    def go(v):
        pg.evaluate(f"document.querySelector('[data-v={v}]').click()")
        pg.wait_for_timeout(450)

    go("dash")
    pg.screenshot(path=f"{OUT}/01_dashboard_rtl.png")
    go("stmts")
    pg.screenshot(path=f"{OUT}/02_statements_full.png", full_page=True)
    go("kpi")
    pg.screenshot(path=f"{OUT}/03_metrics_full.png", full_page=True)
    go("health")
    pg.screenshot(path=f"{OUT}/04_health.png")
    go("gemini")
    pg.screenshot(path=f"{OUT}/05_gemini_full.png", full_page=True)
    go("chat")
    pg.screenshot(path=f"{OUT}/06_chat.png")
    go("review")
    pg.screenshot(path=f"{OUT}/07_review_full.png", full_page=True)
    go("reports")
    pg.screenshot(path=f"{OUT}/08_reports.png")
    # المودال بالأدلة الحقيقية: قصاصة البكسل + الصفحة مع bbox
    go("stmts")
    pg.evaluate("openSrc('نقدية وما في حكمها','2024','6,000,305','ص5',5)")
    pg.wait_for_timeout(600)
    pg.screenshot(path=f"{OUT}/09_evidence_modal_real.png")
    # مودال بحزمة مختلفة (من المحدد) للتحقق من التبديل
    pg.evaluate("drawEvidence('income_tax_expense|2022')")
    pg.wait_for_timeout(400)
    pg.screenshot(path=f"{OUT}/09b_evidence_modal_switched.png")
    # EN/LTR (المودال مغلق أولًا)
    pg.evaluate("document.getElementById('srcmodal').classList.remove('on')")
    pg.wait_for_timeout(200)
    pg.evaluate("toggleLang()")
    pg.wait_for_timeout(400)
    go("dash")
    pg.screenshot(path=f"{OUT}/10_dashboard_en_ltr.png")
    go("stmts")
    pg.screenshot(path=f"{OUT}/10b_statements_en_ltr.png", full_page=True)
    b.close()
print("done")
