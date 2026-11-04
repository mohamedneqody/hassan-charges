# -*- coding: utf-8 -*-
"""Extraction Benchmark A/B/C — same pages, same GT, same local reader.

Scope note (documented per the audit request): this round evaluates 11 rows —
the audit's 10 named cells with «التأجير التمويلي» split into its two printed
balance-sheet lines (non-current + current), plus «صافي أرباح النشاط» which
the audit added as a distinct cell from «صافي أرباح العام». The previous
strip-vs-cell round had 10 rows: no net_activity_profit, both lease lines.

Methods:
  A  FULL-PAGE: one Indra read; the line the production mapper assigns to
     the field; numbers from that line; year = first number in text order
     (the text-order heuristic — kept as the documented-broken baseline).
  B  STRIP: 40 overlapping horizontal bands (cell_evidence), best band by
     keyword hits; same text-order year rule.
  C  SPATIAL (src/extraction/spatial_cells.py): year columns from the actual
     year-header boxes; label row via the production mapper; value = row ∩
     column, cross-checked by a focused crop re-read.

Metric ladder per cell (each stage isolated so a failure localizes):
  label_match        the production mapper assigned the region's line to the field
  row_match          a GT value of EITHER year appears among the region's numbers
  year_match         the value ASSIGNED to 2022 equals GT 2022
  cell_bbox          (C only) the crop is the row∩column intersection and both
                     label box and column range are recorded (geometry complete);
                     N/A for A/B by construction
  exact_numeric      the final 2022 value equals GT within tolerance
  false_match        a value was selected and equals NEITHER year's GT
  unverified         no value extracted at all

Indra Arabic-number stage ladder (audit request #4):
  recognition        the GT value appears as a printed-form token (Arabic-Indic
                     OR Latin) anywhere in the page lines — raw OCR output
  normalization      the GT float appears after digit normalization (stage 2)
  row_alignment      the line carrying the GT token sits in the label row's y-band
  year_assignment    that line's x-center falls inside the correct year column
  field_mapping      the label row mapped to the right field with no veto
  final_exact        end-to-end (C's final value)

Zero API calls. GT = the settled table (eval_2022.py) plus the visually
verified p5 rows and the audited p6 bridge; None = that year's print is not
settled and it is never guessed.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

PROJ = Path(__file__).resolve().parent
PAGES = {5: "eval_pages/page_5.png", 6: "eval_pages/page_6.png", 9: "eval_pages/page_9.png"}
OUT = PROJ / "cell_evidence" / "benchmark_abc.json"

# (field, page, band keywords, GT 2022, GT 2021, tol)  — tol=1 EGP exact;
# tol<1 = relative (approximate GT). None = not settled for that year.
GT_ROWS = [
    ("short_term_debt", 5, ["تسهيلات", "بنوك"], 4_063_400_167, 3_910_902_409, 1),
    ("current_portion_lt_debt", 5, ["أقساط", "اقساط"], 299_320_963, 201_143_687, 1),
    ("long_term_debt", 5, ["قروض طويله", "قروض طويلة"], 363_974_291, None, 1),
    ("non_current_lease_liabilities", 5, ["تأجير تمويلي"], 209_154_419, None, 1),
    ("current_lease_liabilities", 5, ["تأجير تمويلي مستحقه", "تأجير تمويلي مستحقة"], 83_301_722, None, 1),
    ("revenue", 6, ["المبيعات", "مبيعات"], 16_665_919_878, 13_169_656_088, 1),
    ("net_activity_profit", 6, ["صافي", "أرباح"], 1_257_960_603, None, 1),
    ("net_income", 6, ["أرباح العام", "ربح العام"], 1_056_737_086, 288_152_668, 1),
    ("income_tax_expense", 6, ["ضريبة"], -179_626_127, None, 1),
    ("total_liabilities", 5, ["اجمالي الالتزامات", "إجمالي الالتزامات"], 9_027_315_979, 8_250_000_000, 0.02),
    ("operating_cash_flow", 9, ["التشغيل"], 1_214_507_839, None, 1),
]


def _close(v: float | None, gt: float | None, tol: float) -> bool:
    if v is None or gt is None:
        return False
    if tol < 1:
        return abs(v - gt) / gt <= tol
    return abs(v - gt) <= tol


def _best_line(text_lines: list[str], field: str) -> str | None:
    """Method A line picker: the production mapper decides (same rules as
    the pipeline)."""
    from src.extraction.normalizer import match_field

    hits = [ln for ln in text_lines if match_field(ln) == field]
    return hits[0] if hits else None


def _eval_common(method, field, region_text, lines_in_region, gt_c, gt_p, tol,
                 year_rule_values=None):
    """Shared metric computation for A and B (text-order year rule)."""
    from src.extraction.spatial_cells import parse_number_tokens

    r = {"method": method, "field": field, "label_match": region_text is not None}
    r["row_match"] = r["year_match"] = r["exact_numeric"] = False
    r["false_match"] = False
    r["unverified"] = True
    r["value_2022"] = None
    if region_text is None:
        return r
    tokens = parse_number_tokens(region_text)
    nums = [(v, t) for v, t in tokens if v >= 1000]
    r["row_match"] = any(_close(v, gt_c, tol) or _close(v, gt_p, tol)
                         for v, _ in nums)
    if not nums:
        return r
    r["unverified"] = False
    sel = (year_rule_values or nums)[0][0]
    r["value_2022"] = sel
    r["year_match"] = _close(sel, gt_c, tol)
    r["exact_numeric"] = _close(sel, gt_c, tol)
    r["false_match"] = not (_close(sel, gt_c, tol) or _close(sel, gt_p, tol))
    return r


def main() -> None:
    from src.extraction.cell_evidence import locate_row_band_by_text
    from src.extraction.local_ocr import indra_available, _page_markdown
    from src.extraction import spatial_cells as SC

    if not indra_available():
        print("Indra unavailable — run inside the WSL bench venv")
        sys.exit(2)
    conv = None

    def get_conv():
        nonlocal conv
        if conv is None:
            import indra_ocr
            conv = indra_ocr.load()
        return conv

    page_lines: dict[int, list] = {}
    page_pngs: dict[int, bytes] = {}
    page_dims: dict[int, tuple] = {}
    date_cols: dict[int, dict] = {}
    for p, rel in PAGES.items():
        png = (PROJ / rel).read_bytes()
        page_pngs[p] = png
        _w, _h, lines = SC.read_page_lines(get_conv(), png)
        page_lines[p] = lines
        page_dims[p] = (_w, _h)
        date_cols[p], _dd = SC.find_date_columns(get_conv(), png, lines, _w, _h)
        print(f"page {p}: {len(lines)} lines; date columns: "
              f"{sorted(date_cols[p]) or 'none readable'}")

    # printed-year columns from the REAL Gemini date reads (if any)
    gemini_date_cols: dict[int, dict] = {}
    gt_pages = json.loads((PROJ / "cell_evidence" / "gt_cells.json")
                          .read_text(encoding="utf-8"))["pages"]
    greads_p = PROJ / "cell_evidence" / "gemini_reads.json"
    if greads_p.exists():
        cur_cols_cache: dict[int, tuple] = {}
        for r in json.loads(greads_p.read_text(encoding="utf-8")):
            if r.get("read_status") != "READ" or not r.get("year"):
                continue
            ref = r["evidence_reference"]          # date_p{p}_{side}.png
            if not ref.startswith("date_"):
                continue
            p = int(ref.split("_")[1].replace("p", ""))
            side = "right" if ref.endswith("right.png") else "left"
            if p not in cur_cols_cache:
                cur_cols_cache[p] = SC.find_currency_columns(
                    page_lines[p], page_dims[p][0])
            cc, _cd = cur_cols_cache[p]
            if cc and side in cc:
                gemini_date_cols.setdefault(p, {})[int(r["year"])] = cc[side]
        for p, cols in gemini_date_cols.items():
            print(f"page {p}: printed-year columns read by Gemini: {sorted(cols)}")

    rows = []
    for field, page, kws, gt_c, gt_p, tol in GT_ROWS:
        lines = page_lines[page]

        # ── A: full page, production mapper, text-order year rule ──
        a_line = _best_line([ln.text for ln in lines], field)
        a = _eval_common("A_fullpage", field, a_line, lines, gt_c, gt_p, tol)
        a["page"] = page

        # ── B: horizontal strips (40 bands, overlap 0.5) ──
        bands = locate_row_band_by_text(page_pngs[page], kws)
        if bands:
            from src.extraction.normalizer import match_field
            scored = [b for b in bands if match_field(b.text) == field]
            best = scored[0] if scored else max(
                bands, key=lambda b: sum(1 for k in kws if k in b.text))
            b = _eval_common("B_strip", field, best.text, [], gt_c, gt_p, tol)
        else:
            b = _eval_common("B_strip", field, None, [], gt_c, gt_p, tol)
        b["page"] = page

        # ── C: spatial row∩column ──
        # C1: columns from the PRINTED column dates (31/12/2022-style) above
        # the currency titles — computed once per page; a year counts as
        # READ only when its date parsed. If a date is unreadable the pure
        # path reports honestly and the declared-convention run (C2) covers
        # the fallback, always labeled inferred.
        dcols = date_cols.get(page) or {}
        c22 = SC.extract_spatial_cell(
            get_conv(), page_pngs[page], field, 2022,
            columns=dcols or None,
            columns_source="printed column dates" if dcols else "none")
        c21 = SC.extract_spatial_cell(
            get_conv(), page_pngs[page], field, 2021,
            columns=dcols or None,
            columns_source="printed column dates" if dcols else "none")
        # C2: same geometry, but the columns come from the printed currency
        # titles and the YEAR ORDER is an explicitly DECLARED convention
        # (current year beside the note column — the Egyptian layout), never
        # silent, and still gated as unconfirmed by the decision log.
        cur_cols, cur_detail = SC.find_currency_columns(
            page_lines[page], page_dims[page][0])
        declared = None
        if cur_cols:
            declared = {
                2022: cur_cols["right"], 2021: cur_cols["left"],
            }
        c22d = SC.extract_spatial_cell(
            get_conv(), page_pngs[page], field, 2022, columns=declared,
            columns_source=f"declared convention ({cur_detail})")
        c = {
            "method": "C_spatial", "field": field, "page": page,
            "label_match": c22.status not in (SC.STATUS_NO_ROW,),
            "row_match": any(_close(v, gt_c, tol) or _close(v, gt_p, tol)
                             for v, _ in c22.detection_values + c22.crop_values),
            "year_match": _close(c22.value, gt_c, tol),
            "exact_numeric": _close(c22.value, gt_c, tol),
            "false_match": (
                c22.value is not None
                and not (_close(c22.value, gt_c, tol) or _close(c22.value, gt_p, tol))
            ) or (
                c22.value is None and c22.status == SC.STATUS_CONFLICT
            ),
            "unverified": c22.value is None and c22.status != SC.STATUS_CONFLICT,
            "cell_bbox": bool(c22.cell_bbox_rel) and bool(c22.column_rel),
            "year_source": ("PRINTED_YEAR_READ" if dcols
                            else "YEAR_UNVERIFIED"),
            "year_source_c2": "YEAR_INFERRED",
            "value_2022": c22.value,
            "status_2022": c22.status,
            "detail_2022": c22.detail,
            "status_2021": c21.status,
            "value_2021": c21.value,
            "label_2022": c22.label_text[:80],
            "column_detail": c22.column_rel,
            "bbox_rel": c22.cell_bbox_rel,
        }
        cd = {
            "method": "C_spatial_declared", "field": field, "page": page,
            "label_match": c22d.status not in (SC.STATUS_NO_ROW,),
            "row_match": any(_close(v, gt_c, tol) or _close(v, gt_p, tol)
                             for v, _ in c22d.detection_values + c22d.crop_values),
            "year_match": _close(c22d.value, gt_c, tol),
            "exact_numeric": _close(c22d.value, gt_c, tol),
            "false_match": (
                c22d.value is not None
                and not (_close(c22d.value, gt_c, tol) or _close(c22d.value, gt_p, tol))
            ) or (
                c22d.value is None and c22d.status == SC.STATUS_CONFLICT
            ),
            "unverified": c22d.value is None and c22d.status != SC.STATUS_CONFLICT,
            "cell_bbox": bool(c22d.cell_bbox_rel) and bool(c22d.column_rel),
            "year_source": "YEAR_INFERRED",
            "value_2022": c22d.value,
            "status_2022": c22d.status,
            "detail_2022": c22d.detail,
            "label_2022": c22d.label_text[:80],
            "column_detail": c22d.column_rel,
            "bbox_rel": c22d.cell_bbox_rel,
        }
        if c22d.crop_png:
            (PROJ / "cell_evidence" / f"spatial_{field}_p{page}_y2022.png") \
                .write_bytes(c22d.crop_png)

        # ── C3: columns from the dates Gemini actually READ (printed-year
        # evidence, second reader). Reads come from
        # cell_evidence/gemini_reads.json (real API responses; quota
        # exhaustion recorded as BLOCKED in that file). A page gets a
        # printed-year column only where ITS date was READ.
        c3 = None
        gemini_year_cols = gemini_date_cols.get(page)
        if gemini_year_cols:
            c22g = SC.extract_spatial_cell(
                get_conv(), page_pngs[page], field, 2022,
                columns=gemini_year_cols,
                columns_source="printed_dates_read_by_gemini")
            c3 = {
                "method": "C_spatial_gemini_dates", "field": field,
                "page": page,
                "label_match": c22g.status not in (SC.STATUS_NO_ROW,),
                "row_match": any(_close(v, gt_c, tol) or _close(v, gt_p, tol)
                                 for v, _ in c22g.detection_values + c22g.crop_values),
                "year_match": _close(c22g.value, gt_c, tol),
                "exact_numeric": _close(c22g.value, gt_c, tol),
                "false_match": (
                    c22g.value is not None
                    and not (_close(c22g.value, gt_c, tol)
                             or _close(c22g.value, gt_p, tol))
                ) or (c22g.value is None and c22g.status == SC.STATUS_CONFLICT),
                "unverified": c22g.value is None
                and c22g.status != SC.STATUS_CONFLICT,
                "cell_bbox": bool(c22g.cell_bbox_rel) and bool(c22g.column_rel),
                "year_source": "PRINTED_YEAR_READ",
                "year_association": "GEOMETRICALLY_ASSOCIATED",
                "value_2022": c22g.value,
                "status_2022": c22g.status,
                "detail_2022": c22g.detail,
                "provenance": c22g.provenance,
                "bbox_rel": c22g.cell_bbox_rel,
            }

        # ── IoU of the 2022 column interval vs the reviewer-estimated GT ──
        col_iou = None
        for cand in (c22d, c22g if c3 else None):
            if cand is not None and cand.column_rel:
                gx = gt_pages.get(str(page), {}).get("col_2022_x")
                if gx:
                    s0, s1 = cand.column_rel
                    inter = max(0.0, min(s1, gx[1]) - max(s0, gx[0]))
                    union = max(s1, gx[1]) - min(s0, gx[0])
                    if union > 0:
                        col_iou = round(inter / union, 3)
                        break

        rows += [a, b, c, cd] + ([c3] if c3 else [])
        for r in (c, cd, c3):
            if r is not None:
                r["column_iou_vs_reviewer_gt"] = col_iou
        tag = f" | C3: {c3['status_2022']} v={c3['value_2022'] and format(c3['value_2022'], ',.0f')}" if c3 else ""
        print(f"{field:30s} A: lm={a['label_match']} rm={a['row_match']} "
              f"yr={a['year_match']} | B: rm={b['row_match']} | "
              f"C1: {c22.status} | C2: {c22d.status} "
              f"v={c22d.value and format(c22d.value, ',.0f')}{tag}")

        # ── Indra stage ladder for this GT (audit request #4) ──
        AR2EN = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
        for year, gt in ((2022, gt_c), (2021, gt_p)):
            if gt is None:
                continue
            gt_tok = f"{gt:,}"
            recognition = any(gt_tok in (ln.text or "").translate(AR2EN)
                              for ln in lines)
            norm_vals = {v for ln in lines for v, _ in SC.parse_number_tokens(ln.text)}
            normalization = any(abs(v - gt) <= max(1.0, 1e-9 * gt) for v in norm_vals)
            row_alignment = year_assignment = None
            if normalization:
                for ln in lines:
                    toks = [v for v, _ in SC.parse_number_tokens(ln.text)]
                    if any(abs(v - gt) <= max(1.0, 1e-9 * gt) for v in toks):
                        # find the column this line belongs to
                        from src.extraction.normalizer import match_field
                        lbl_rows = [x for x in lines if match_field(x.text) == field]
                        if lbl_rows:
                            lbl = lbl_rows[0]
                            band = (lbl.y0 - 0.6 * lbl.height, lbl.y1 + 0.6 * lbl.height)
                            row_alignment = band[0] <= ln.cy <= band[1]
                        pw = page_dims[page][0]
                        cols, _d = SC.find_year_columns(lines, pw)
                        if cols and year in cols:
                            year_assignment = cols[year].contains(ln.cx / pw)
                        break
            stage_key = f"stages_{year}"
            a[stage_key] = {"recognition": recognition, "normalization": normalization,
                            "row_alignment": row_alignment, "year_assignment": year_assignment,
                            "field_mapping": a["label_match"]}

    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1, default=str),
                   encoding="utf-8")

    from src.analysis.financial_gate import decide as _gate_decide
    # SINGLE SOURCE OF TRUTH for gating: the gate's own decide() mapping.
    # (The old list-based counter under-counted CROP_ONLY cells.)

    def cell_strict(r) -> bool:
        """E2E pass = ALL conditions together: label AND row AND year AND
        bbox AND exact value AND a status eligible for decisive use."""
        return bool(
            r["label_match"] and r["row_match"] and r["year_match"]
            and r.get("cell_bbox") and r["exact_numeric"]
            and _gate_decide(r.get("status_2022")) in ("use", "use_disclosed")
        )

    def tally(m):
        sub = [r for r in rows if r["method"] == m]
        n = len(sub)
        no_value = sum(1 for r in sub if r["unverified"])
        gated = sum(1 for r in sub if not r["unverified"]
                    and r.get("status_2022") in BLOCKED_STATUS)
        year_printed = sum(1 for r in sub if r["year_match"]
                           and "PRINTED" in str(r.get("year_source", "")))
        year_inferred = sum(1 for r in sub if r["year_match"]
                            and "INFERRED" in str(r.get("year_source", "")))
        year_unresolved = n - year_printed - year_inferred
        strict = sum(1 for r in sub if cell_strict(r))
        read_any = sum(1 for r in sub if not r["unverified"])
        return {
            "n": n,
            "label_match": sum(r["label_match"] for r in sub),
            "row_match": sum(r["row_match"] for r in sub),
            "year_match_printed": year_printed,
            "year_match_inferred": year_inferred,
            "year_unresolved": year_unresolved,
            "cell_bbox": sum(r.get("cell_bbox", 0) or 0 for r in sub),
            "exact_numeric": sum(r["exact_numeric"] for r in sub),
            # FALSE MATCH = the FINAL selected value matches neither year's GT
            "false_match": sum(r["false_match"] for r in sub),
            # no_value: nothing extractable; gated: a value WAS extracted but
            # its status (CONFLICT/MULTI_ROW/UNREADABLE) blocks decisive use
            "no_value": no_value,
            "gated_not_decisive": gated,
            # usable_decisive = exact AND not gated — the honest final-answer
            # count (this is what the report may actually print)
            "usable_decisive": sum(
                1 for r in sub if r["exact_numeric"]
                and _gate_decide(r.get("status_2022")) in ("use", "use_disclosed")),
            # candidate yield: SOME number came out (correct or NOT) — the old
            # 'readability 100%' was this, NOT a correctness measure
            "candidate_yield_rate": round(read_any / n, 3) if n else None,
            # STRICT end-to-end: label+row+year+bbox+exact+usable together
            "e2e_strict": round(strict / n, 3) if n else None,
            "e2e_strict_count": strict,
        }

    summary = {m: tally(m) for m in
               ("A_fullpage", "B_strip", "C_spatial", "C_spatial_declared",
                "C_spatial_gemini_dates")}
    # UNIFIED C2-vs-C3 on the SAME 11-cell denominator: C3 only supports
    # fields whose page has a Gemini-read printed date; unsupported cells
    # count as NOT extracted (unverified) — never silently dropped.
    unified = {"n": 11, "note": "same 11 cells for both; C3-unsupported "
                                "cells count as unverified"}
    unified_rows = []
    for field, page, _k, gt_c, gt_p, tol in GT_ROWS:
        c2 = next((r for r in rows if r["method"] == "C_spatial_declared"
                   and r["field"] == field), None)
        c3 = next((r for r in rows if r["method"] == "C_spatial_gemini_dates"
                   and r["field"] == field), None)
        unified_rows.append({
            "field": field, "page": page,
            "C2_exact": bool(c2 and c2["exact_numeric"]),
            "C3_exact": bool(c3 and c3["exact_numeric"]),
            "C3_supported": c3 is not None,
        })
    unified = {
        "n": len(unified_rows),
        "C2_exact": sum(r["C2_exact"] for r in unified_rows),
        "C3_exact": sum(r["C3_exact"] for r in unified_rows),
        "C3_supported": sum(r["C3_supported"] for r in unified_rows),
        "note": "same 11-cell denominator; C3-unsupported cells count as "
                "not extracted (unverified), never dropped",
        "rows": unified_rows,
    }
    summary["unified_C2_vs_C3"] = unified
    (PROJ / "cell_evidence" / "benchmark_abc_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
