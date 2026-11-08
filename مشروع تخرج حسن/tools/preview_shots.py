# -*- coding: utf-8 -*-
"""Acceptance screenshots (المهمة 1): 1920x1080 desktop, real browser,
every section + full-page + EN/LTR + the source-evidence modal AS-IS."""
from playwright.sync_api import sync_playwright

OUT = "design/screenshots_1920"

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1920, "height": 1080},
                    device_scale_factor=1)
    pg.goto("http://localhost:8901/mvp_preview.html")
    pg.wait_for_timeout(800)

    def go(v):
        pg.evaluate(f"document.querySelector('[data-v={v}]').click()")
        pg.wait_for_timeout(450)

    # 1. dashboard (viewport)
    pg.screenshot(path=f"{OUT}/01_dashboard.png")
    # 1b. dashboard FULL page
    pg.screenshot(path=f"{OUT}/01b_dashboard_full.png", full_page=True)
    # 2. statements (full page — the tables are tall)
    go("stmts")
    pg.screenshot(path=f"{OUT}/02_statements_full.png", full_page=True)
    # 3. indicators
    go("kpi")
    pg.screenshot(path=f"{OUT}/03_metrics_full.png", full_page=True)
    # 4. health
    go("health")
    pg.screenshot(path=f"{OUT}/04_health.png")
    # 5. gemini
    go("gemini")
    pg.screenshot(path=f"{OUT}/05_gemini_full.png", full_page=True)
    # 6. chat
    go("chat")
    pg.screenshot(path=f"{OUT}/06_chat.png")
    # 7. review
    go("review")
    pg.screenshot(path=f"{OUT}/07_review_full.png", full_page=True)
    # 8. reports
    go("reports")
    pg.screenshot(path=f"{OUT}/08_reports.png")
    # 9. source-evidence modal (AS-IS — placeholder, documented gap)
    go("stmts")
    pg.evaluate("openSrc('إجمالي الأصول','2024','169,497,056','ص5',5)")
    pg.wait_for_timeout(300)
    pg.screenshot(path=f"{OUT}/09_source_modal_asis.png")
    # 10. EN/LTR (dashboard + statements)
    pg.evaluate("toggleLang()")
    pg.wait_for_timeout(400)
    go("dash")
    pg.screenshot(path=f"{OUT}/10_dashboard_en_ltr.png")
    go("stmts")
    pg.screenshot(path=f"{OUT}/10b_statements_en_ltr.png", full_page=True)
    b.close()
print("done")
