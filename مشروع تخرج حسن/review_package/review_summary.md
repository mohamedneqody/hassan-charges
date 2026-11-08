# Review Package — Financial Analysis MVP (graduation project)

Generated: 2026-11-08 · Code frozen at commit `080fb80` + audit round `52bf0a1`
(298 tests passing). No API keys, credentials or reviewer data are included.

## Contents

- `screenshots/` — the standalone UI design preview (mvp_preview.html),
  captured in a REAL browser (Chromium) at 1920x1080: dashboard (viewport +
  full-page), statements, metrics, health, Gemini analysis, document chat,
  data review, reports, the source-evidence modal AS-IS, and the EN/LTR layout.
- `reports/` — the production report engine output for TWO companies
  (Telecom Egypt + EFG Holding): XLSX + HTML + PDF each.
- `pdf_pages/` — every PDF page rendered as PNG (12 pages) for visual
  print-quality review.
- `mvp_preview.html` — open in any browser (self-contained, no build).
- Audit artifacts (JSON): the 40-cell TE audit from the review chain, the EFG
  holdout results, both full-pipeline runs, the live Gemini analysis, the
  multilingual RAG evaluation, the per-page processing audit, and the TE
  error anatomy.

## Known defects found during THIS review (honest, unfixed)

1. PDF print layout (page 1 of both reports): the RTL layout breaks in
   LibreOffice's HTML->PDF — the title is truncated, the health gauge
   (conic-gradient) is lost, cards render as detached boxes. The metrics
   TABLE (page 2+) prints cleanly.
2. 'Ratio Commentary - No commentary available' in the produced PDF: the
   report script builds a fresh AIAnalysis(ok=False) and does not wire the
   saved Gemini comments (they exist in te_gemini_live_analysis.json).
3. Effective Tax Rate +40.5% (+560.8% change) on TE: the printed 2024 tax
   is a CREDIT (+1,272,749) — the engine stores it positive, so the rate
   reads as an expense rate. Metric-interpretation gap, disclosed.
4. Source-evidence modal in the preview shows a PLACEHOLDER (page number +
   bbox description), not the actual page image with the cell highlighted —
   the bbox coordinates exist in candidate_bbox but the preview does not
   embed the page images.
5. EN/LTR mode flips layout and navigation only; the data content remains
   Arabic (no full i18n).
6. N/A rows (FCF, EBITDA margin, ROIC, selling/R&D %) are honest
   missing-input states — printed as N/A per the registry policy.

## What was verified in this round

- 40/40 TE cells captured; 38/40 signed-exact automatic; 0 false
  acceptances after the sign-conflict + section-context + two-layer fixes.
- DuPont reconciles exactly (13.941% implied == direct). Beneish M
  honestly refuses (SGAI missing) - no fabrication.
- Reports: TE health 54.5 (preliminary, 1 pending critical), EFG health
  35.6 (preliminary, 2 pending) - both labeled PRELIMINARY, never
  verified-final (the attestations are TEST-reviewer, not production
  human review).
