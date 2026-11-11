# -*- coding: utf-8 -*-
"""تشخيص سريع: حالة التطبيق الحية بعد محاولة الرفع (لقطة + نص الحالة)."""
import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1720, "height": 950})
    pg.goto("http://localhost:8765")
    pg.wait_for_selector("body", timeout=15000)
    time.sleep(4)
    pg.screenshot(path="design/ui_merge_shots/diag_state.png")
    body = pg.inner_text("body")[:1500]
    print(body)
    b.close()
