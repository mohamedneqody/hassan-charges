#!/usr/bin/env python3
"""Accuracy evaluation: compare saved OCR outputs against known ground truth.

Metrics per sample:
  - CER (character error rate) and WER (word error rate) via jiwer, on
    normalized text (NFKC folds Arabic presentation forms; tatweel removed;
    whitespace collapsed).
  - CER_order_insensitive: same metric with GT lines sorted alphabetically,
    so a high gap between the two points at a reading-order problem rather
    than a recognition problem.
  - line_match_in_order / line_match_sorted: per-line exact-match ratios
    (recognition vs reading-order diagnosis).
  - For the table sample additionally cell_recall: the share of GT cells
    found verbatim in the output (structure-aware).

Writes benchmarks/accuracy_results.json and prints a summary table.
"""
from __future__ import annotations

import difflib
import json
import re
import sys
import unicodedata
from pathlib import Path

import jiwer

PROJ = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
OUT = PROJ / "outputs"
GT_PATH = PROJ / "test_data" / "ground_truth.json"

PAIRS = [
    # (gt key, output-file prefix, mode suffix, label)
    ("en_printed", "en_printed", "ocr", "en_printed_ocr"),
    ("ar_printed", "ar_printed", "ocr", "ar_printed_ocr"),
    ("mixed_ar_en", "mixed_ar_en", "ocr", "mixed_ar_en_ocr"),
    ("table", "table", "ocr", "table_ocr"),
    ("searchable_pdf", "searchable", "auto", "searchable_auto (text layer)"),
    ("searchable_pdf", "searchable", "ocr", "searchable_ocr (real OCR)"),
    ("scanned_pdf", "scanned", "auto", "scanned_auto (real OCR, no layer)"),
    ("scanned_pdf", "scanned", "ocr", "scanned_ocr (real OCR, no layer)"),
]


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\u0640", "")  # tatweel
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def error_examples(ref: str, hyp: str, n: int = 6) -> list[dict]:
    sm = difflib.SequenceMatcher(None, ref, hyp, autojunk=False)
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        ctx_ref = ref[max(0, i1 - 20):i1]
        ctx_hyp = hyp[max(0, j1 - 20):j1]
        out.append({
            "tag": tag,
            "ref": f"{ctx_ref}[{ref[i1:i2]}]",
            "hyp": f"{ctx_hyp}[{hyp[j1:j2]}]",
        })
        if len(out) >= n:
            break
    return out


def line_diag(gt_lines: list[str], hyp: str) -> dict:
    gt = [norm(l) for l in gt_lines if norm(l)]
    hp = [norm(l) for l in hyp.split("\n") if norm(l)]
    if not gt:
        return {}
    in_order = difflib.SequenceMatcher(None, gt, hp, autojunk=False).ratio()
    sorted_ratio = difflib.SequenceMatcher(None, sorted(gt), sorted(hp), autojunk=False).ratio()
    return {
        "line_match_in_order": round(in_order, 3),
        "line_match_sorted": round(sorted_ratio, 3),
    }


def cell_recall(cells: list[str], hyp_norm: str) -> float:
    found = sum(1 for c in cells if norm(c) and norm(c) in hyp_norm)
    return round(found / max(len(cells), 1), 3)


def main() -> int:
    gt = json.loads(GT_PATH.read_text(encoding="utf-8"))
    results = []
    for key, prefix, suffix, label in PAIRS:
        gt_text = norm("\n".join(p["text"] for p in gt[key]["pages"]))
        gt_lines = [l for p in gt[key]["pages"] for l in p["lines"]]
        out_path = OUT / f"{prefix}_{suffix}.txt"
        if not out_path.exists():
            results.append({"label": label, "error": f"missing {out_path.name}"})
            continue
        hyp_raw = out_path.read_text(encoding="utf-8")
        hyp = norm(hyp_raw)
        row = {
            "label": label,
            "gt_chars": len(gt_text),
            "hyp_chars": len(hyp),
            "cer": round(jiwer.cer(gt_text, hyp), 4) if hyp else None,
            "wer": round(jiwer.wer(gt_text, hyp), 4) if hyp else None,
            **line_diag(gt_lines, hyp_raw),
            "examples": error_examples(gt_text, hyp),
        }
        if key == "table":
            cells = gt[key]["header"] + [c for r in gt[key]["rows"] for c in r]
            row["cell_recall"] = cell_recall(cells, hyp)
        results.append(row)
        print(f"{label:38s} CER={row['cer']} WER={row['wer']} lines={row.get('line_match_in_order')}/{row.get('line_match_sorted')}")

    out_json = PROJ / "benchmarks" / "accuracy_results.json"
    out_json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {out_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
