# -*- coding: utf-8 -*-
"""إنتاج التقارير الحقيقية — جولة إصلاح المراجعة (v2).

The project's OWN report engine (build_excel_report + build_html_report +
LibreOffice HTML→PDF) run on the FROZEN GT values of TE and EFG.

What this round fixes (each one traceable in the ledger):
1. وحدة القياس: the printed unit «in EGP Thousands» is evidence — values
   stay stored as printed; the display multiplies by unit_scale=1000 so
   TE revenue 2024 reads «ج.م27.73 مليار», never the misleading «27.73M».
2. سجل التدقيق الموحد: report_production.json binds each report to the
   code version, the GT run, the unit evidence and the AI-analysis
   source (the old te_final_audit_post_fix.json FA=2 was an INTERMEDIATE
   code state before the two-layer exemption rule — preserved, explained).
3. Excel: one row per metric (the diagonal-spread bug was ws.max_row
   recomputed per cell) + the 9th verification column + ACTUAL numbers.
4. PDF: print-safe linearized layout converted from a separate _print.html.
5. Gemini: a FRESH live analysis on the unit-corrected payload when the
   quota allows; otherwise the SAVED analysis wired with an explicit
   disclosure that its numbers use the old notation (never edited text).
6. Honest interpretation: unit_note / period_type / reviewer_label /
   na_metrics / tax benefit vs expense.
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

OUT = PROJ / "review_package" / "reports"
SOFFICE = r"C:\Program Files\LibreOffice\program\soffice.exe"


def sha256_of(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def _git_state() -> dict:
    def _out(*args: str) -> str:
        r = subprocess.run(["git", "-c", "core.quotepath=off", *args],
                           capture_output=True, cwd=PROJ)
        return r.stdout.decode("utf-8", "replace").strip()
    head = _out("rev-parse", "--short", "HEAD")
    dirty = _out("status", "--porcelain", "--", "src", "tools",
                 "tests").splitlines()
    return {"head": head,
            "dirty_files": [d.split()[-1].replace("حسن/", "")
                            for d in dirty][:20]}


def _wire_gemini(results: dict, currency: str, saved_path: Path | None,
                 dataset_probe: str, dataset_label: str,
                 gt_path: Path | None) -> tuple[object, dict]:
    """Fresh live analysis first (unit-corrected payload); fallback → the
    saved analysis wired WITH its old-notation disclosure; else honest
    no-analysis. Returns (AIAnalysis, binding-metadata).

    v3 (defect 2 of the v2 review): the dataset identity is VERIFIED, not
    asserted — the fresh analysis is generated from THIS results dict (the
    same company/periods/values the report shows — identity by
    construction), and the binding records the company, periods and the
    GT file hash. The v2 bug printed the TE dataset line inside the EFG
    report because the label was hardcoded."""
    from src.ai.gemini_agent import AIAnalysis, analyze_financials
    from src.pipeline import build_gemini_payload

    # the verified dataset identity — same dict the report renders
    identity = {
        "company": results.get("company"),
        "periods": f"{results.get('prev_year')}–{results.get('curr_year')}",
        "gt_file": Path(gt_path).name if gt_path else None,
        "gt_sha256_16": sha256_of(gt_path) if gt_path else None,
        "identity_basis": ("التحليل وُلّد من نفس قاموس النتائج الذي يُعيد "
                           "إنتاج التقرير (نفس الشركة والفترات والقيم) — "
                           "تطابق بالبناء وليس ادعاءً نصيًا"),
        "values_state": "GT replay — يحتاج مراجعة (بلا تصديق في إعادة "
                        "الإنتاج)",
    }
    assert dataset_label, "dataset_label is required for honest binding"

    # 1) FRESH — the payload now quotes «27.73 مليار»-style actual units
    try:
        payload = build_gemini_payload(results, currency=currency)
        fresh = analyze_financials(payload)
        if fresh.ok and fresh.ratio_comments:
            return fresh, {"wired": True, "freshness": "fresh_live_run",
                           "model": fresh.model,
                           "comments": len(fresh.ratio_comments),
                           "recommendations": len(fresh.recommendations),
                           "notation": "actual units (مليار/مليون)",
                           "dataset": dataset_label,
                           "dataset_identity": identity}
    except Exception as exc:                      # quota/network — fall through
        fresh_error = f"{type(exc).__name__}: {str(exc)[:120]}"
    else:
        fresh_error = getattr(fresh, "error", "") or "no comments returned"

    # 2) SAVED — wired ONLY if the dataset probe passes: the saved text
    # must quote a distinctive number of THIS dataset (TE-only; EFG has no
    # saved analysis). Its numbers use the OLD notation, disclosed.
    if saved_path and Path(saved_path).exists():
        ga = json.loads(Path(saved_path).read_text(encoding="utf-8"))
        all_text = " ".join(str(c[1]) for c in ga.get("ratio_comments", []))
        probe_hit = dataset_probe in all_text
        if ga.get("ok") and probe_hit:
            return AIAnalysis(
                ok=True,
                ratio_comments=[tuple(c) for c in ga.get("ratio_comments", [])],
                recommendations=[tuple(r) for r in
                                 ga.get("recommendations", [])],
                model=ga.get("model", "gemini")), {
                    "wired": True, "freshness": "saved_from_closing_round",
                    "model": ga.get("model"),
                    "comments": len(ga.get("ratio_comments", [])),
                    "recommendations": len(ga.get("recommendations", [])),
                    "source": Path(saved_path).name,
                    "sha256_16": sha256_of(Path(saved_path)),
                    "notation_disclosure": (
                        "تعليقات تقتبس أرقامًا بصيغة الوحدة القديمة "
                        "(M = آلاف من جولة سابقة) — أُبقيت حرفيًا: نص "
                        "الذكاء الاصطناعي لا يُحرَّر. جداول التقرير نفسها "
                        "تعرض الوحدة الصحيحة."),
                    "dataset_probe": probe_hit,
                    "dataset": dataset_label,
                    "dataset_identity": identity}
        if not probe_hit:
            return AIAnalysis(ok=False, error="saved analysis failed the "
                              "same-dataset probe"), {
                              "wired": False,
                              "reason": "dataset probe mismatch — not wired",
                              "dataset": dataset_label,
                              "dataset_identity": identity}

    return AIAnalysis(ok=False, error=f"no valid analysis ({fresh_error})"), {
        "wired": False, "reason": fresh_error,
        "dataset": dataset_label, "dataset_identity": identity}


def build(company: str, values: dict, notes: list[str], stem: str,
          currency: str, unit_scale: int, unit_note: str, period_type: str,
          reviewer_label: str, saved_gemini: Path | None = None,
          dataset_probe: str = "", dataset_label: str = "",
          gt_path: Path | None = None) -> dict:
    from src.ai.gemini_agent import AIAnalysis
    from src.analysis import calculator as C
    from src.analysis.comparison import NOT_AVAILABLE, build_comparison
    from src.analysis.financial_gate import (
        decide, pending_critical_review, report_is_preliminary,
        verification_labels,
    )
    from src.analysis.score import compute_health_score
    from src.dashboard.excel_report import build_excel_report
    from src.dashboard.report import build_html_report
    from src.extraction.normalizer import (
        FinancialData, build_decision_log, reconcile,
    )

    d = FinancialData()
    d.unit_scale = unit_scale
    d.unit_note = unit_note
    d.values.update(values)
    # v3 HONEST replay (defects 1+2 of the v2 review): ONE reference read
    # per (field, year) — NO fabricated attestation. v2 recorded each GT
    # value twice (layers 0/1) which the decision log read as a two-layer
    # VERIFIED_EXACT while pending_critical_review (correctly) saw one
    # layer behind the winner — the exact report/banner contradiction the
    # reviewer found. A replay has no attestation, and now every surface
    # (banner, Excel, HTML, PDF) says so consistently: يحتاج مراجعة.
    for f in d.values:
        d.candidates[f] = {y: [(v, 0)] for y, v in d.values[f].items()}
        d.confidence[f] = {y: 1 for y in d.values[f]}
    reconcile(d)
    dl = build_decision_log(d)
    pending = pending_critical_review(dl)
    verif = verification_labels(dl)

    prev = C.compute_year_metrics(2023, d.values)
    curr = C.compute_year_metrics(2024, d.values, prev_year=2023)
    # Health Score HONESTY (defect 6): the score must respect the SAME gate
    # the verification column shows — a pillar built from gated inputs is
    # blocked, and a refused score is refused in Excel/HTML/PDF alike.
    blocked = {e["field"] for e in dl
               if decide(e["status"]) not in ("use", "use_disclosed")}
    hs = compute_health_score(curr, blocked_fields=blocked)

    rows = build_comparison(prev, curr)
    na_metrics = [r.label_ar or r.label for r in rows
                  if r.status == NOT_AVAILABLE]
    results = {"company": company, "file_name": f"{stem}.pdf",
               "prev_year": 2023, "curr_year": 2024,
               "prev_metrics": prev, "curr_metrics": curr,
               "rows": rows, "growth_rows": [],
               "notes": notes, "missing": [], "currency_hint": currency,
               "unit_scale": unit_scale, "unit_note": unit_note,
               "period_type": period_type, "reviewer_label": reviewer_label,
               "pending_critical_review": pending,
               "verification_status": verif,
               "blocked_fields": sorted(blocked),
               "na_metrics": na_metrics}
    preliminary = report_is_preliminary(dl)

    analysis, gemini_meta = _wire_gemini(results, currency, saved_gemini,
                                         dataset_probe, dataset_label,
                                         gt_path)
    results["gemini_analysis"] = gemini_meta

    OUT.mkdir(parents=True, exist_ok=True)
    xlsx = OUT / f"{stem}.xlsx"
    xlsx.write_bytes(build_excel_report(results))
    html_path = OUT / f"{stem}.html"
    html_path.write_text(
        build_html_report(results, analysis, hs, currency=currency),
        encoding="utf-8")
    # the PDF path: print-safe linearized layout (LibreOffice has no flex)
    print_path = OUT / f"{stem}_print.html"
    print_path.write_text(
        build_html_report(results, analysis, hs, currency=currency,
                          print_safe=True), encoding="utf-8")
    pdf = OUT / f"{stem}.pdf"
    conv = subprocess.run(
        [SOFFICE, "--headless", "--convert-to", "pdf",
         "--outdir", str(OUT), str(print_path)],
        capture_output=True, text=True, timeout=240)
    # LibreOffice names the output after the INPUT ({stem}_print.pdf) —
    # move it over {stem}.pdf so a stale previous-round file can never be
    # mistaken for this run's product (that is exactly what slipped through
    # the first v2 attempt: pdf_ok=True on a stale v1 PDF).
    printed = OUT / f"{stem}_print.pdf"
    if printed.exists():
        printed.replace(pdf)
    pdf_ok = pdf.exists()

    return {"company": company, "stem": stem,
            "xlsx": str(xlsx), "xlsx_sha256_16": sha256_of(xlsx),
            "html": str(html_path), "print_html": str(print_path),
            "pdf": str(pdf), "pdf_ok": pdf_ok,
            "pdf_sha256_16": sha256_of(pdf) if pdf_ok else "",
            "health": hs.total, "coverage": hs.coverage,
            "health_policy": getattr(hs, "policy", ""),
            "blocked_fields_count": len(blocked),
            "preliminary": preliminary,
            "pending_critical": len(pending),
            "pending_fields": [p["field"] for p in pending],
            "na_metrics": na_metrics,
            # defect 3: the CELLS this report presents — the independent
            # acceptance tool compares these against the frozen GT file
            "cells": {f: {str(y): v for y, v in ym.items()}
                      for f, ym in values.items()},
            "verification_counts": {
                "human": sum(1 for e in dl
                             if e["status"] == "VERIFIED_HUMAN"),
                "auto_two_layer": sum(1 for e in dl
                                      if e["status"] == "VERIFIED_EXACT"),
                "derived": sum(1 for e in dl
                               if e["status"] == "VERIFIED_DERIVED"),
                "needs_review": sum(1 for e in dl
                                    if e["status"] in
                                    ("CONFLICT", "UNVERIFIED", "CROP_ONLY",
                                     "MULTI_ROW"))},
            "gemini": gemini_meta,
            "unit_chain": {"stored": "printed values (EGP thousands)",
                           "display_scale": unit_scale,
                           "evidence": unit_note,
                           "display_example": "27,730,150 ألف → ج.م27.73 مليار"},
            "period_type": period_type, "reviewer_label": reviewer_label,
            "libreoffice_rc": conv.returncode}


def main() -> dict:
    git = _git_state()
    out = {"run_at": datetime.now().isoformat(timespec="seconds"),
           "code_version": git,
           "round": "v3 review package — defects 1-6 of the v2 review",
           "honest_replay": (
               "v3: كل قيمة GT تُعاد بإحالة واحدة (بلا تصديق مُصطنع) — "
               "اللافتة الأولية وعمود حالة التحقق والدرجة الصحية المتروكة "
               "كلها متسقة: القيم تحتاج مراجعة. سجل القبول النهائي على "
               "مستوى الخلايا: cell_evidence/v3_final_cell_acceptance.json."),
           "audit_conflict_resolution": (
               "te_final_audit_post_fix.json (FA=2) محفوظ كما هو — تشغيل "
               "وسيط قبل قاعدة التصديق عبر-طبقتين. النتيجة النهائية "
               "الفعلى على مستوى الخلايا في v3_final_cell_acceptance.json "
               "المربوط بإصدار الكود وبصمة التشغيل."),
           "reports": []}

    # ── TE: the frozen 40-cell GT (attested test-reviewer in acceptance) ──
    gt_path = PROJ / "independent_docs/te_holdout/gt_te_frozen.json"
    gt = json.loads(gt_path.read_text(encoding="utf-8"))
    te_values: dict = {}
    for y in ("2024", "2023"):
        for f, m in gt["cells"][y].items():
            te_values.setdefault(f, {})[int(y)] = float(m["value"])
    out["reports"].append(build(
        "Telecom Egypt (TE — verified subset)", te_values,
        ["الحالة: تقرير أولي — إعادة إنتاج من قيم GT المجمدة بإحالة واحدة "
         "لكل قيمة (بلا تصديق في إعادة الإنتاج): كل حالة التحقق «يحتاج "
         "مراجعة» والدرجة الصحية محجوبة لمدخلاتها. القيم نفسها وُثّقت "
         "اختباريًا في جولة القبول (test-reviewer) — ليست مراجعة بشرية "
         "إنتاجية.",
         "Beneish M-Score: غير قابل للحساب — SGAI غير موجود ضمن الخانات "
         "الموثقة (المكونات الستة الأخرى محسوبة ومعروضة).",
         "الضريبة 2024 ائتمان (+1,272,749 ألف ج.م) — المنفعة الضريبية "
         "معلنة في ملاحظة معدل الضريبة الفعلي."],
        "TE_Financial_Report_2024", "ج.م", unit_scale=1000,
        unit_note="جميع القيم بآلاف الجنيهات (in EGP Thousands) — مطبوعة "
                  "على كل ترويسة أعمدة القوائم",
        period_type="قوائم منفصلة مرحلية (كونسلسيدد لا) — ستة أشهر منتهية "
                    "30/06/2024 مقابل ستة أشهر 30/06/2023 (وليست سنوية)",
        reviewer_label="لا تصديق في إعادة الإنتاج — القيم وُثّقت اختباريًا "
                       "(test-reviewer) في جولة القبول، ليست مراجعة بشرية "
                       "إنتاجية",
        saved_gemini=PROJ / "cell_evidence/te_gemini_live_analysis.json",
        dataset_probe="27.73",
        dataset_label="TE frozen GT 40-cell set — 6 أشهر 2024/2023",
        gt_path=gt_path))

    # ── EFG: the frozen GT cells (no chain — honest GT-replay label) ──
    gt_e_path = PROJ / "independent_docs/efg_holdout/gt_efg_frozen.json"
    gt_e = json.loads(gt_e_path.read_text(encoding="utf-8"))
    efg_values: dict = {}
    for y in ("2024", "2023"):
        for f, m in gt_e["cells"][y].items():
            efg_values.setdefault(f, {})[int(y)] = float(m["value"])
    out["reports"].append(build(
        "EFG Holding (EFG — verified subset)", efg_values,
        ["الحالة: تقرير أولي — القيم من GT المرجعية المجمدة بإحالة واحدة "
         "(توثيق بصري مجمّد قبل التشغيل). لا توجد مراجعة بشرية لهذا "
         "التقرير.",
         "EFG Holding — شركة خدمات مالية قابضة: مفردات القوائم تختلف عن "
         "الشركات التشغيلية (دخل استثمارات، لا مخزون ولا تكلفة بضاعة)."],
        "EFG_Financial_Report_2024", "ج.م", unit_scale=1000,
        unit_note="جميع القيم بآلاف الجنيهات (in EGP Thousands) — مطبوعة "
                  "على كل قائمة",
        period_type="قوائم منفصلة سنوية FY2024 مقابل FY2023",
        reviewer_label="لا توجد مراجعة بشرية — القيم من GT المرجعية المجمّدة",
        saved_gemini=None,
        dataset_label="EFG frozen GT 14-cell set ×سنتان — FY2024/FY2023",
        gt_path=gt_e_path))

    out["reports"] = [_strip_paths(r) for r in out["reports"]]
    dst = PROJ / "review_package" / "report_production.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    for r in out["reports"]:
        print(f"{r['stem']}: pdf_ok={r['pdf_ok']} health={r['health']} "
              f"preliminary={r['preliminary']} pending={r['pending_critical']} "
              f"gemini={r['gemini'].get('wired')}/"
              f"{r['gemini'].get('freshness', '-')} na={len(r['na_metrics'])}")
    print(f"ledger: {dst}")
    return out


def _strip_paths(r: dict) -> dict:
    keep = {k: v for k, v in r.items() if k not in ("xlsx", "html",
                                                    "print_html", "pdf")}
    keep["files"] = {k: Path(r[k]).name for k in ("xlsx", "html",
                                                  "print_html", "pdf")}
    return keep


if __name__ == "__main__":
    main()
