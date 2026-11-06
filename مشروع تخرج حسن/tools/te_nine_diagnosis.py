# -*- coding: utf-8 -*-
"""Diagnostic dump for the 9 wrong cells (المهمة الأولى): every OCR
candidate with its raw row text, page, bbox, and WHY it won."""
import io
import json
import os
import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ))
os.environ.pop("GEMINI_API_KEYS", None)      # pure local, after imports
os.environ.pop("GEMINI_API_KEY", None)

import re

import cv2
import numpy as np
import pypdfium2 as pdfium

from src.extraction.file_parsers import (
    _adaptive_local_reread_scan, _parse_pdf_text_lines,
)
from src.extraction.normalizer import (
    FinancialData, merge_parsed, parse_number, reconcile,
)

PDF = PROJ / "independent_docs/te_holdout/te_standalone_h1_2024.pdf"
WRONG = [
    ("total_assets", 2024, 169_497_056.0, 20_327_981.0),
    ("total_assets", 2023, 134_358_541.0, 14_964_829.0),
    ("current_liabilities", 2024, 91_625_404.0, 50_666_774.0),
    ("current_liabilities", 2023, 64_166_416.0, 34_039_174.0),
    ("operating_income", 2024, 5_040_128.0, 11_374_911.0),
    ("operating_income", 2023, 5_451_938.0, 5_081_497.0),
    ("accounts_payable", 2024, 33_524_304.0, 15_928_525.0),
    ("accounts_payable", 2023, 25_538_574.0, 13_567_712.0),
    ("cash", 2023, 10_272_954.0, 10.0),
]

raw = PDF.read_bytes()
notes: list[str] = []
parts, caps, sources = _adaptive_local_reread_scan(raw, notes)

# rebuild the data exactly like the degradation path
data = merge_parsed(parts, notes, captures_per_part=caps,
                    part_layers=["local_ocr"] * len(parts))
reconcile_needed = True
reconcile(data)

# ALSO: keep the raw markdown per page so we can show the row text
pdf = pdfium.PdfDocument(io.BytesIO(raw))
from src.extraction.local_ocr import _page_markdown
import indra_ocr

conv = indra_ocr.load()
page_md: dict[int, str] = {}
for pno in range(1, 13):
    if pno - 1 >= len(pdf):
        break
    buf = io.BytesIO()
    pdf[pno - 1].render(scale=2.0).to_pil().convert("RGB").save(buf, format="PNG")
    md = _page_markdown(conv, buf.getvalue()) or ""
    page_md[pno] = re.sub(r"<[^>]+>", " ", md)

out = {"wrong_cells": []}
for field, year, gt_v, _stale in WRONG:
    cands = data.candidates.get(field, {}).get(year, [])
    labels = data.candidate_labels.get(field, {}).get(year, [])
    layers = data.candidate_layers.get(field, {}).get(year, [])
    selected_now = data.values.get(field, {}).get(year)
    trail = []
    for (v, o), lbl, ly in zip(cands, labels + [""] * len(cands),
                               layers + [""] * len(cands)):
        # the FULL source line: find the stripped-markdown line whose
        # numbers contain this candidate's digits
        src_line = ""
        digits = re.sub(r"\D", "", f"{v:.0f}")
        for pno in sources.get(field, []):
            for ln in page_md.get(pno, "").splitlines():
                if digits and digits in re.sub(r"\D", "", ln):
                    src_line = re.sub(r"\s+", " ", ln.strip())[:120]
                    break
            if src_line:
                break
        trail.append({"value": v, "order": o, "label_row": str(lbl)[:60],
                      "layer": ly, "source_line": src_line})
    entry = {
        "field": field, "year": year, "gt_test_only": gt_v,
        "selected_now": selected_now,
        "correct_selected": (selected_now is not None
                             and abs(selected_now - gt_v)
                             <= max(1000.0, 1e-6 * abs(gt_v))),
        "correct_in_candidates": any(
            abs(v - gt_v) <= max(1000.0, 1e-6 * abs(gt_v))
            for v, _o in cands),
        "candidates": trail,
    }
    out["wrong_cells"].append(entry)

# dump the stripped markdown of the pages that host these fields
for f, y, _g, _s in WRONG:
    for pno in sources.get(f, []):
        key = f"page_{pno}_stripped_md"
        if key not in out:
            out[key] = page_md.get(pno, "")[:4000]

dst = PROJ / "cell_evidence/te_nine_diagnosis.json"
dst.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
for e in out["wrong_cells"]:
    print(f"== {e['field']} {e['year']}  GT={e['gt_test_only']:,.0f}  "
          f"selectedNOW={e['selected_now']}  correct_selected={e['correct_selected']}  "
          f"in_cands={e['correct_in_candidates']}")
    for t in e["candidates"]:
        print(f"   cand {t['value']:>18,.0f}  [{t['layer']}]  {t['source_line'] or t['label_row']}")
print("artifact:", dst)
