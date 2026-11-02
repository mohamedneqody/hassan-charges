# -*- coding: utf-8 -*-
"""Human review helper for cell bounding boxes (أداة التعليم المرجعي).

Renders each page with the SYSTEM's candidate bboxes (red) and the REVIEWER
column bands from gt_cells.json (blue) overlaid, plus per-cell crop strips,
so a human can mark the final row bands and correct the column bands. It
NEVER claims its own output is manual GT — the JSON it writes is a review
worksheet (`gt_review_worksheet.json`) with `needs_human: true` until a
reviewer edits it.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

PROJ = Path(__file__).resolve().parents[1]
GT = PROJ / "cell_evidence" / "gt_cells.json"
BENCH = PROJ / "cell_evidence" / "benchmark_abc.json"


def main() -> None:
    import cv2
    import numpy as np

    gt = json.loads(GT.read_text(encoding="utf-8"))
    bench = json.loads(BENCH.read_text(encoding="utf-8"))
    ws = {"needs_human": True, "cells": []}
    for page_s, pg in gt["pages"].items():
        png_path = PROJ / f"eval_pages/page_{page_s}.png"
        if not png_path.exists():
            continue
        img = cv2.imdecode(np.frombuffer(png_path.read_bytes(), np.uint8),
                           cv2.IMREAD_GRAYSCALE)
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        h, w = img.shape[:2]
        for x0r, x1r, color, tag in (
                (pg["col_2021_x"][0], pg["col_2021_x"][1], (255, 128, 0), "GT-2021"),
                (pg["col_2022_x"][0], pg["col_2022_x"][1], (0, 128, 255), "GT-2022")):
            cv2.rectangle(img, (int(x0r * w), 0), (int(x1r * w), h), color, 3)
            cv2.putText(img, tag, (int(x0r * w) + 6, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.4, color, 3)
        for row in bench:
            if row.get("method") == "C_spatial_declared" \
                    and row.get("bbox_rel") and str(row.get("page")) == page_s:
                x0, y0, x1, y1 = row["bbox_rel"]
                cv2.rectangle(img, (int(x0 * w), int(y0 * h)),
                              (int(x1 * w), int(y1 * h)), (0, 0, 255), 2)
                cv2.putText(img, row["field"][:20], (int(x0 * w), int(y0 * h) - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                ws["cells"].append({
                    "field": row["field"], "page": int(page_s),
                    "system_bbox_rel": row["bbox_rel"],
                    "reviewer_bbox_rel": None,  # ← human fills this
                    "needs_human": True,
                })
        out = PROJ / "cell_evidence" / f"review_overlay_p{page_s}.png"
        cv2.imwrite(str(out), img)
        print(f"saved {out.name}")
    (PROJ / "cell_evidence" / "gt_review_worksheet.json").write_text(
        json.dumps(ws, ensure_ascii=False, indent=1), encoding="utf-8")
    print("worksheet: cell_evidence/gt_review_worksheet.json (needs_human=true)")


if __name__ == "__main__":
    main()
