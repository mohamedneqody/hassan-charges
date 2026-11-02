# -*- coding: utf-8 -*-
"""Strip vs Cell quantitative comparison — same pages, same GT, same local
reader (Indra, zero API). The ONLY variable is the segmentation method:

  STRIP (proxy of the whole-page pipeline): one full-page OCR read; pick the
  single line containing the most field-label keywords; take the numbers on
  that line only; first number in text order = current year (the text-order
  heuristic a text-only reader is stuck with).

  CELL (this round's upgrade): 40 overlapping horizontal bands per page, each
  read locally; pick the band with the most keyword hits; numbers from that
  band only; same year heuristic — but the band's crop is saved as visual
  evidence and can be re-read by a vision model per-cell (PENDING_API_QUOTA).

Metrics per field: field_localization / row_match (a GT value of either year
appears among the extracted numbers) / year_column (selected 2022 == GT 2022)
/ numeric_exact (within tolerance) / false_match (selected value equals
NEITHER year's GT) / unverified (no localization or no numbers).

GT is the settled table from eval_2022.py plus the visually verified p5
balance-sheet rows. No company numbers are hardcoded in production code —
this is an evaluation harness only.
"""
import json
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

AR2EN = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
PROJ = Path(__file__).resolve().parent
PAGES = {5: "eval_pages/page_5.png", 6: "eval_pages/page_6.png", 9: "eval_pages/page_9.png"}
OUT = PROJ / "cell_evidence" / "strip_vs_cell.json"

# (field, page, keywords, GT2022, GT2021, tol) — tol in EGP; None GT = not
# settled for that year (row_match then checks the settled year only).
TARGETS = [
    ("short_term_debt", 5, ["تسهيلات", "بنوك"], 4_063_400_167, 3_910_902_409, 1),
    ("current_portion_lt_debt", 5, ["أقساط", "اقساط"], 299_320_963, 201_143_687, 1),
    ("long_term_debt", 5, ["قروض طويله", "قروض طويلة"], 363_974_291, None, 1),
    ("non_current_lease_liabilities", 5, ["تأجير تمويلي"], 209_154_419, None, 1),
    ("current_lease_liabilities", 5, ["تأجير تمويلي مستحقه", "تأجير تمويلي مستحقة"], 83_301_722, None, 1),
    ("revenue", 6, ["المبيعات", "مبيعات"], 16_665_919_878, 13_169_656_088, 1),
    ("net_income", 6, ["صافي", "أرباح"], 1_056_737_086, 288_152_668, 1),
    ("income_tax_expense", 6, ["ضريبة"], 179_626_127, None, 1),
    ("total_liabilities", 5, ["المتداولة"], 9_030_000_000, 8_250_000_000, 0.02),
    ("operating_cash_flow", 9, ["التشغيل"], 1_214_507_829, None, 1),
]


def numbers_in(text: str) -> list[float]:
    """Numeric tokens >= 1000 (note refs / page fragments are smaller)."""
    t = (text or "").translate(AR2EN)
    out = []
    for m in re.finditer(r"\d[\d,]*(?:\.\d+)?", t):
        try:
            v = float(m.group().replace(",", ""))
        except ValueError:
            continue
        if v >= 1000:
            out.append(v)
    return out


def _close(v: float, gt: float | None, tol: float) -> bool:
    if gt is None:
        return False
    if tol < 1:  # relative tolerance (approximate GT)
        return abs(v - gt) / gt <= tol
    return abs(v - gt) <= tol


def best_line(md: str, keywords: list[str]) -> str | None:
    """Strip method: the one line with the most distinct keyword hits."""
    best, best_hits = None, 0
    for ln in (md or "").splitlines():
        hits = sum(1 for k in keywords if k in ln)
        if hits > best_hits:
            best, best_hits = ln, hits
    return best


def evaluate(method: str, text: str | None, field: str, gt_c, gt_p, tol) -> dict:
    res = {
        "method": method, "field": field,
        "localized": text is not None,
        "row_match": False, "year_column": False, "numeric_exact": False,
        "false_match": False, "unverified": True, "selected_2022": None,
        "numbers": [], "text": (text or "")[:160],
    }
    if not text:
        return res
    nums = numbers_in(text)
    res["numbers"] = nums[:8]
    if not nums:
        return res
    res["unverified"] = False
    res["selected_2022"] = nums[0]  # first-in-text = current-year heuristic
    sel = nums[0]
    row_ok = _close(sel, gt_c, tol) or _close(sel, gt_p, tol) or \
        any(_close(n, gt_c, tol) or _close(n, gt_p, tol) for n in nums)
    res["row_match"] = row_ok
    res["year_column"] = _close(sel, gt_c, tol)
    res["numeric_exact"] = _close(sel, gt_c, tol)
    res["false_match"] = (not _close(sel, gt_c, tol)) and (not _close(sel, gt_p, tol))
    return res


def main() -> None:
    from src.extraction.local_ocr import indra_available, _page_markdown
    from src.extraction.cell_evidence import locate_row_band_by_text

    if not indra_available():
        print("Indra unavailable — run inside the WSL bench venv")
        sys.exit(2)
    import indra_ocr

    tls = threading.local()

    def conv():
        c = getattr(tls, "conv", None)
        if c is None:
            c = indra_ocr.load()
            tls.conv = c
        return c

    page_md: dict[int, str] = {}

    def _read_page(p: int) -> tuple[int, str | None]:
        png = (PROJ / PAGES[p]).read_bytes()
        return p, _page_markdown(conv(), png)

    with ThreadPoolExecutor(max_workers=3) as ex:
        for p, md in ex.map(_read_page, list(PAGES)):
            page_md[p] = md or ""
            print(f"page {p}: {len(page_md[p])} chars (strip read)")

    rows: list[dict] = []
    for field, page, kws, gt_c, gt_p, tol in TARGETS:
        strip_line = best_line(page_md.get(page, ""), kws)
        s = evaluate("strip", strip_line, field, gt_c, gt_p, tol)
        bands = locate_row_band_by_text((PROJ / PAGES[page]).read_bytes(), kws)
        best_band = None
        if bands:
            def hits(b):
                return len(set(b.matched_keywords))
            best_band = max(bands, key=hits)
        c = evaluate("cell", best_band.text if best_band else None, field, gt_c, gt_p, tol)
        c["band_y"] = [best_band.y0, best_band.y1] if best_band else None
        (PROJ / "cell_evidence" / f"cmp_{field}_p{page}.png").write_bytes(
            best_band.crop_png) if best_band else None
        rows += [s, c]
        print(f"{field:30s} strip: loc={s['localized']} row={s['row_match']} "
              f"yr={s['year_column']} false={s['false_match']} | "
              f"cell: loc={c['localized']} row={c['row_match']} "
              f"yr={c['year_column']} false={c['false_match']}")

    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    def tally(method):
        sub = [r for r in rows if r["method"] == method]
        n = len(sub)
        return {
            "fields": n,
            "localization": sum(r["localized"] for r in sub),
            "row_match": sum(r["row_match"] for r in sub),
            "year_column": sum(r["year_column"] for r in sub),
            "numeric_exact": sum(r["numeric_exact"] for r in sub),
            "false_match": sum(r["false_match"] for r in sub),
            "unverified": sum(r["unverified"] for r in sub),
        }

    summary = {"strip": tally("strip"), "cell": tally("cell")}
    (PROJ / "cell_evidence" / "strip_vs_cell_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print("saved", OUT.name, "+ strip_vs_cell_summary.json")


if __name__ == "__main__":
    main()
