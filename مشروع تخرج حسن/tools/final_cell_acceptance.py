# -*- coding: utf-8 -*-
"""القبول النهائي على مستوى الخلايا (عيب 3 من مراجعة v2).

سجل FA=2 القديم لم يكفِ وصفه بأنه «وسيط» — هذه الأداة تنتج النتيجة
النهائية الفعلية: كل خلية (بند، سنة) في تقريري v3 تُقارن قيمتها
المعروضة مقابل ملف GT المجمد بقراءة مستقلة من الملف نفسه، مع ربط
بإصدار الكود وبصمة التشغيل (هاش ملف GT + هاشات المخرجات). النتيجة:
FA = عدد القيم التي اعتمدها التقرير واختلفت عن GT — مرفوض أي رقم
غير مسجل بهذه الطريقة.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ))

LEDGER = PROJ / "review_package/report_production.json"
OUT = PROJ / "cell_evidence/v3_final_cell_acceptance.json"


def sha16(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def git_state() -> dict:
    def _out(*args: str) -> str:
        r = subprocess.run(["git", "-c", "core.quotepath=off", *args],
                           capture_output=True, cwd=PROJ)
        return r.stdout.decode("utf-8", "replace").strip()
    return {"head": _out("rev-parse", "--short", "HEAD"),
            "dirty": _out("status", "--porcelain", "--", "src", "tools",
                          "tests").splitlines()}


def main() -> dict:
    led = json.loads(LEDGER.read_text(encoding="utf-8"))
    code = git_state()

    results = []
    total_cells = total_fa = 0
    for rep in led["reports"]:
        gt_name = rep["gemini"]["dataset_identity"]["gt_file"]
        stem_prefix = "te" if "TE_" in rep["stem"] else "efg"
        gt_path = (PROJ / "independent_docs" /
                   f"{stem_prefix}_holdout" / gt_name)
        gt = json.loads(gt_path.read_text(encoding="utf-8"))
        cells = rep["cells"]
        mismatches, checked = [], 0
        for field, years in cells.items():
            for y, presented in years.items():
                gt_entry = gt["cells"].get(str(y), {}).get(field)
                checked += 1
                if gt_entry is None:
                    mismatches.append({"field": field, "year": y,
                                       "kind": "not_in_gt",
                                       "presented": presented})
                    continue
                gt_value = float(gt_entry["value"])
                if abs(float(presented) - gt_value) > 1e-6:
                    mismatches.append({
                        "field": field, "year": y, "kind": "value_mismatch",
                        "presented": presented, "gt": gt_value})
        fa = len(mismatches)
        total_cells += checked
        total_fa += fa
        results.append({
            "report": rep["stem"],
            "gt_file": gt_name,
            "gt_sha256_16": sha16(gt_path),
            "cells_checked": checked,
            "false_accepts": fa,
            "mismatches": mismatches,
            "outputs_sha256_16": {k: rep.get(f"{k}_sha256_16")
                                  for k in ("xlsx", "pdf")},
        })

    fingerprint = hashlib.sha256(json.dumps(
        {"gt": [r["gt_sha256_16"] for r in results],
         "out": [r["outputs_sha256_16"] for r in results],
         "code_head": code["head"]},
        sort_keys=True).encode("utf-8")).hexdigest()[:16]

    out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "what_this_is": (
            "النتيجة النهائية على مستوى الخلايا: كل قيمة معروضة في تقارير "
            "v3 مقابل ملف GT المجمد بقراءة مستقلة من الملف. FA = قيم "
            "اعتمدها التقرير واختلفت عن GT."),
        "code_version": code,
        "run_fingerprint_sha16": fingerprint,
        "historical_note": (
            "te_final_audit_post_fix.json (FA=2) تشغيل وسيط قبل قاعدة "
            "التصديق عبر-طبقتين — محفوظ ولا يُستبدل؛ هذه هي النتيجة "
            "النهائية."),
        "total": {"cells_checked": total_cells,
                  "false_accepts": total_fa,
                  "false_accept_rate": (round(total_fa / total_cells, 4)
                                        if total_cells else None)},
        "reports": results,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"cells={total_cells} FA={total_fa} "
          f"(fingerprint {fingerprint}, code {code['head']})")
    print(f"artifact: {OUT}")
    return out


if __name__ == "__main__":
    main()
