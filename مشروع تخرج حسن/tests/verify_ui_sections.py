"""Headless UI verification via Streamlit's official AppTest framework.

Runs app.py, clicks the sample-file button, and asserts the new Overview
sections (DuPont/Altman, What-if, Benchmarks) render with real values.
Offline: GEMINI_API_KEYS is blanked so the AI step fails fast to the
deterministic fallback narrative — no quota is consumed.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
os.environ["GEMINI_API_KEYS"] = ""          # no AI calls — deterministic path only
os.environ.pop("GEMINI_API_KEY", None)
os.environ["LOCAL_OCR_ENABLED"] = "0"

sys.path.insert(0, str(PROJECT))
os.chdir(PROJECT)

from streamlit.testing.v1 import AppTest  # noqa: E402

FAILURES: list[str] = []


def check(cond: bool, what: str) -> None:
    print(f"{'PASS' if cond else 'FAIL'}  {what}")
    if not cond:
        FAILURES.append(what)


at = AppTest.from_file(str(PROJECT / "app.py"), default_timeout=120)
at.run()

# 1) Upload screen shows the sample button
sample_btns = [b for b in at.button if "جرّب بملف العينة" in (b.label or "")]
check(bool(sample_btns), "upload screen shows the sample-file button")
if not sample_btns:
    print("buttons found:", [b.label for b in at.button])
    sys.exit(1)

# 2) Click it → pipeline runs → st.rerun() → dashboard. AppTest raises
#    the RerunException as a handled event; run again to render dashboard.
sample_btns[0].click()
at.run()
if "results" not in at.session_state:
    at.run()
check("results" in at.session_state, "sample pipeline completed (session_state['results'] set)")
check(not at.exception, f"no uncaught exception (got: {[e.value for e in at.exception]})")
if "results" not in at.session_state:
    sys.exit(1)

# 3) Dashboard renders — collect all markdown text (tabs are all present in AppTest)
texts = [m.value for m in at.markdown]
blob = "\n".join(texts)
subheaders = [s.value for s in at.subheader]
print("subheaders:", subheaders)

r = at.session_state["results"]
print(f"years: {r['prev_year']} -> {r['curr_year']}  company: {r['company']}")

# --- Advanced analysis (DuPont + Altman) ---
check("التحليل المتقدم" in subheaders, "subheader: التحليل المتقدم")
check("تحليل DuPont" in blob, "DuPont block rendered")
check("Altman Z" in blob, "Altman Z'' block rendered")
check("مصادر العائد على حقوق الملكية" in blob, "DuPont table title")

# --- What-if section ---
# fmt: currency cells go through charts.humanize ($2M / $165K / $-31K);
# minus in scenario labels is U+2212 (−), not ASCII hyphen.
check("تحليل الحساسية (ماذا لو؟)" in subheaders, "subheader: تحليل الحساسية (ماذا لو؟)")
check("خط الأساس" in blob, "what-if baseline row")
check("إيرادات +20%" in blob and "إيرادات −20%" in blob, "revenue ±20% scenarios")
check("تكلفة الإيرادات +10%" in blob, "cost +10% scenario")
check("المصاريف التشغيلية +10%" in blob, "opex +10% scenario")

# Sample data: revenue 1,180,000 / NI 165,000 → baseline row shows $1.18M / $165K
check("$1.18M" in blob, "what-if baseline revenue value present ($1.18M)")
check("$165K" in blob, "what-if baseline net income value present ($165K)")
# Operating leverage: revenue −20% with FIXED costs → NI collapses to negative
check("$-31K" in blob, "revenue −20% scenario NI = −31,000 rendered as $-31K (fixed costs)")

# --- Benchmarks section ---
captions = [c.value for c in at.caption]
check("مقارنة بالمعايير" in subheaders, "subheader: مقارنة بالمعايير")
check(any("مستويات إرشادية عامة" in c for c in captions),
      "benchmark caption shows general-guideline source")
check("التقييم" in blob, "benchmark table has band column")
check("مقبول" in blob, "band badge مقبول present (current_ratio 1.65 vs fair 1.5)")

# --- Ensure the pre-existing sections are intact (top movers anchor) ---
check("أبرز التغيرات" in subheaders, "subheader: أبرز التغيرات (regression guard)")
check("المؤشرات الرئيسية" in blob or any("المؤشرات الرئيسية" in s for s in subheaders),
      "KPI section intact (regression guard)")

# --- Companies comparison tab + auto-saved study library ---
check("مقارنة الشركات" in subheaders, "subheader: مقارنة الشركات tab rendered")

# --- Expert layer: red flags + Beneish (always rendered on Overview) ---
check(any("الأعلام الحمراء" in s for s in subheaders), "subheader: الأعلام الحمراء rendered")
check("Beneish" in blob, "Beneish M-Score block present (score or honest-missing caption)")
check("ثقة الأرقام الرئيسية" in subheaders or "confidence" not in blob,
      "confidence section rendered when witness data exists")
dl_labels_all = [d.label for d in at.download_button]
check(any("بحثة محلل" in (lbl or "") for lbl in dl_labels_all),
      "research-note download button present")

from src.analysis.portfolio import clear_library, load_records  # noqa: E402

records = load_records()
check(len(records) == 1 and records[0].company == "sample financials",
      f"auto-save wrote exactly one library record (got: {[(r.company, r.curr_year) for r in records]})")
if records:
    rec = records[0]
    check(rec.revenue is not None and rec.health_total is not None and rec.prev_year == r["prev_year"],
          "library record carries the study metrics")
    dl_labels = [d.label for d in at.download_button]
    check(any("تصدير مقارنة الشركات" in (lbl or "") for lbl in dl_labels),
          f"comparison CSV export button present (download buttons: {dl_labels})")
clear_library()  # keep the user's real library clean
check(load_records() == [], "library cleaned up after verification")

# This run had AI disabled (deterministic fallback) — never let its payload
# key sit in the persistent analysis cache, or the user's real run would
# replay the fallback commentary instead of calling Gemini.
from src.extraction.result_cache import clear_all_caches  # noqa: E402

clear_all_caches()

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S):")
    for f in FAILURES:
        print(" -", f)
    sys.exit(1)
print("ALL UI CHECKS PASSED")
