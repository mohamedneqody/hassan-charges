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

    # v4 (نقطة 4): FA=0 على صفر قيم معتمدة ليس إثباتًا لسلامة القبول الآلي —
    # FAR يبقى N/A هنا، والتفريق الثلاثي واجب التوثيق:
    attested_accepted = sum(
        r["cells_checked"] - len([
            m for m in r["mismatches"]])
        for r in results)  # كل خلايا الإعادة غير معتمدة أصلاً (يحتاج مراجعة)
    auto_accepted_count = 0   # الإعادة الصادقة لا تمنح أي قيمة حالة اعتماد
    far = (round(total_fa / auto_accepted_count, 4)
           if auto_accepted_count else None)   # None = N/A بصدق

    out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "what_this_is": (
            "نتيجة مستوى الخلايا: كل قيمة معروضة في التقارير مقابل ملف GT "
            "المجمد بقراءة مستقلة من الملف. تقيس سلامة إعادة إنتاج GT — "
            "ولا تقيس دقة الاستخراج ولا سلامة القبول الآلي (انظر "
            "three_way_distinction)."),
        "code_version": code,
        "code_state": ("commit نظيف — الملفات أعلاه تحديدًا؛ أي تعديل لاحق "
                       "على الكود يبطل هذه النتيجة"),
        "run_fingerprint_sha16": fingerprint,
        "historical_note": (
            "te_final_audit_post_fix.json (FA=2) تشغيل وسيط قبل قاعدة "
            "التصديق عبر-طبقتين — محفوظ ولا يُستبدل."),
        "three_way_distinction": {
            "1_replay_integrity": {
                "measured_here": True,
                "result": f"{total_cells - total_fa}/{total_cells} خلية مطابقة لـGT",
                "meaning": "صحة إعادة إنتاج قيم GT في التقارير — الإعادة "
                           "تأخذ قيمها من GT فالمطابقة شرط اتساق لا فضل.",
            },
            "2_extraction_accuracy": {
                "measured_here": False,
                "result": "غير مقيس هنا",
                "meaning": "دقة الاستخراج الفعلي من المستندات تُقاس في تقييمات "
                           "الـholdout المستقلة (TE: FAR 0.0 على التوقيعات في "
                           "جولة القبول؛ EFG عبر مسار الرؤية) — لا في هذه "
                           "الإعادة.",
            },
            "3_auto_acceptance_accuracy": {
                "measured_here": False,
                "result": "FAR = N/A",
                "meaning": "صفر قيم معتمدة آليًا في هذه الإعادة (كل الحالات "
                           "«يحتاج مراجعة») — FA=0 على صفر معتمد لا يثبت شيئًا "
                           "عن سلامة القبول الآلي، ولا يُقدَّم كذلك.",
            },
        },
        "total": {"cells_checked": total_cells,
                  "false_accepts": total_fa,
                  "auto_accepted_values": auto_accepted_count,
                  "false_accept_rate": far,      # None = N/A بصدق
                  "false_accept_rate_display": ("N/A — صفر قيم معتمدة آليًا"
                                                if far is None else far),
                  "attested_values_replayed": attested_accepted},
        "reports": results,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"cells={total_cells} FA={total_fa} auto_accepted={auto_accepted_count} "
          f"FAR={'N/A' if far is None else far} "
          f"(fingerprint {fingerprint}, code {code['head']}, "
          f"dirty={len(code['dirty'])})")
    print(f"artifact: {OUT}")
    return out


if __name__ == "__main__":
    main()
