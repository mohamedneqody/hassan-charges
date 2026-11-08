# -*- coding: utf-8 -*-
"""لقطات المعاينة v3: مودال بدون دليل مطابق (رسالة عدم توفر)، لوحة
الأدلة الحقيقية في قسم المراجعة، الترجمة الكاملة LTR، وشارة البيانات."""
from playwright.sync_api import sync_playwright

OUT = "design/screenshots_v3"

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1920, "height": 1080},
                    device_scale_factor=1)
    errors = []
    pg.on("console", lambda m: errors.append(m.text)
          if m.type == "error" else None)
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
    # المودال لقيمة TE 2024: رسالة عدم توفر دليل مطابق (لا صور 2022)
    go("stmts")
    pg.evaluate("openSrc('نقدية وما في حكمها','2024','6,000,305','ص5',5)")
    pg.wait_for_timeout(500)
    pg.screenshot(path=f"{OUT}/09_modal_no_matching_evidence.png")
    # لوحة الأدلة الحقيقية (مستقلة، موسومة بمستند 2022)
    pg.evaluate("document.getElementById('srcmodal').classList.remove('on')")
    pg.wait_for_timeout(200)
    go("review")
    pg.wait_for_timeout(400)
    pg.evaluate(
        "document.getElementById('real-ev').scrollIntoView({block:'center'})")
    pg.wait_for_timeout(300)
    pg.screenshot(path=f"{OUT}/09b_real_evidence_panel.png")
    # LTR كامل
    pg.evaluate("toggleLang()")
    pg.wait_for_timeout(500)
    go("dash")
    pg.screenshot(path=f"{OUT}/10_dashboard_en_ltr.png")
    go("stmts")
    pg.screenshot(path=f"{OUT}/10b_statements_en_ltr.png", full_page=True)
    go("kpi")
    pg.screenshot(path=f"{OUT}/10c_metrics_en_ltr.png", full_page=True)
    b.close()
print("console errors:", errors[:4] if errors else "NONE")
print("done")
