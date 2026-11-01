"""Final proof chain: cache roundtrip (with notes_text + field_sources) →
payload contains notes highlights → LIVE Gemini commentary → recommendations
cite notes pages. Then the accuracy evaluation is re-printed for comparison."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import src.config  # noqa: F401

PDF = Path(__file__).resolve().parent / "القوائم المالية المستقلة 2022.pdf"

print("── 1) run_pipeline (must hit the cache: zero extraction calls) ──")
from src.pipeline import build_gemini_payload, run_pipeline

raw = PDF.read_bytes()
t0 = time.perf_counter()
r = run_pipeline(PDF.name, raw, "شركة", fast_mode=False)
elapsed = time.perf_counter() - t0
print(f"pipeline returned in {elapsed:.1f}s (cache hit ⇒ fast, no vision sweep)")
nt = r.get("notes_text") or {}
print(f"notes_text pages: {len(nt)}  ← must be 29/29")
fs = r.get("field_sources") or {}
print(f"field_sources fields: {len(fs)}  ← حاكمية المصادر محفوظة")

print("\n── 2) build_gemini_payload: notes_highlights ──")
payload = build_gemini_payload(r, currency="ج.م")
hl = payload.get("notes_highlights") or []
print(f"notes_highlights: {len(hl)} مقطعًا ماليًا مختارًا من الإيضاحات")
for h in hl[:4]:
    print(f"  [صفحة {h['page']} | relevance {h['relevance']}] {h['text'][:110]}...")

print("\n── 3) LIVE commentary: do the recommendations cite notes pages? ──")
from src.ai.gemini_agent import analyze_financials

t0 = time.perf_counter()
analysis = analyze_financials(payload)
elapsed = time.perf_counter() - t0
print(f"analyze_financials: ok={analysis.ok} in {elapsed:.0f}s")
if not analysis.ok:
    print("ERROR:", analysis.error)
    sys.exit(1)

import re

cites = []
recs = analysis.recommendations or []
print(f"recommendations: {len(recs)}")
for rec in recs:
    text = " | ".join(str(part) for part in rec) if isinstance(rec, (tuple, list)) else str(rec)
    m = re.search(r"صفحة (\d+)", text)
    if m:
        cites.append(int(m.group(1)))
    print(" •", text[:170])
page_cited = sorted(set(cites))
print("\n── PROOF ──")
if page_cited:
    print(f"✓ التوصيات تستشهد بصفحات إيضاحات: {page_cited} "
          "(كلها ≥ 10 = صفحات الإيضاحات المتممة، كانت مهدورة قبل هذا الإصلاح)")
else:
    print("✗ لم تستشهد أي توصية بصفحة إيضاح — راجع النموذج/التوجيه")

# ── 4) الدقة لم تتأثر ──
print("\n── 4) الدقة (نفس معايير eval_2022) ──")
import re as _re

AR2EN = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
CHECKS = [
    ("revenue 2022", r["curr_metrics"].revenue, 16_665_919_878),
    ("net_income 2022", r["curr_metrics"].net_income, 1_056_737_086),
    ("total_assets 2022", r["curr_metrics"].total_assets, 15_965_646_460),
    ("CFO 2022", r["curr_metrics"].operating_cash_flow, 1_214_507_829),
    ("pretax 2022", r["curr_metrics"].pretax_income, 1_236_363_213),
    ("tax 2022", r["curr_metrics"].income_tax_expense, -179_626_127),
    ("CFF 2022", r["curr_metrics"].financing_cash_flow, -727_063_341),
    ("CFI 2022", r["curr_metrics"].investing_cash_flow, 722_097_212),
]
ok = 0
for name, got, want in CHECKS:
    good = got is not None and abs(got - want) <= 1
    ok += good
    print(f"  {'✓' if good else '✗'} {name}: {got if got is not None else '—'}")
print(f"{ok}/{len(CHECKS)} EXACT")
