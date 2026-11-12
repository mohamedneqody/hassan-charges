"""Self-contained printable HTML report (open in a browser → Print → PDF).

Contains the full analysis: health score, KPI summary, ratio commentary,
recommendations, missing data and notes. Zero dependencies — pure string
building with inline CSS.
"""
from __future__ import annotations

import html as _html
from datetime import datetime

from src.ai.gemini_agent import AIAnalysis
from src.analysis.comparison import MetricRow
from src.analysis.score import HealthScore
from src.dashboard.charts import (fmt_signed_ar, fmt_signed_pct,
                                 fmt_value_ar)

ESC = _html.escape

_CSS = """
body { font-family: 'Segoe UI', Tahoma, Arial, sans-serif; color: #0f172a;
       background: #f6f8fb; margin: 0; padding: 32px; }
.page { max-width: 900px; margin: 0 auto; background: #fff; border: 1px solid #e2e8f0;
        border-radius: 16px; padding: 36px 40px; }
h1 { font-size: 1.6rem; margin: 0 0 4px; }
h2 { font-size: 1.1rem; border-inline-start: 5px solid #4f46e5; padding-inline-start: 10px;
     margin: 30px 0 10px; }
.meta { color: #64748b; font-size: .9rem; }
.score { display: flex; align-items: center; gap: 18px; background: #eef2ff;
         border: 1px solid #e0e7ff; border-radius: 14px; padding: 16px 20px; margin: 14px 0; }
.score .num { font-size: 2.6rem; font-weight: 800; color: #4f46e5; }
.pillars { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 8px; }
.pillar { background: #fff; border: 1px solid #e2e8f0; border-radius: 10px;
          padding: 8px 14px; font-size: .85rem; }
table { width: 100%; border-collapse: collapse; font-size: .86rem; margin: 8px 0; }
th { text-align: start; background: #f1f5f9; padding: 8px 10px; font-size: .74rem;
     text-transform: uppercase; letter-spacing: .05em; color: #475569; }
td { padding: 7px 10px; border-top: 1px solid #e2e8f0; }
td.num { font-variant-numeric: tabular-nums; }
.badge { padding: 2px 10px; border-radius: 999px; font-size: .75rem; font-weight: 700; }
.pos { background: #d1fae5; color: #047857; }
.neg { background: #ffe4e6; color: #be123c; }
.neu { background: #f1f5f9; color: #475569; }
.na { background: #f8fafc; color: #94a3b8; }
.comment { padding: 8px 2px; border-bottom: 1px dashed #e2e8f0; line-height: 1.7; }
.comment b { color: #4f46e5; }
ol { padding-inline-start: 22px; } li { margin-bottom: 6px; line-height: 1.6; }
ul { padding-inline-start: 22px; }
.muted { color: #94a3b8; font-size: .8rem; }
@media print { body { background: #fff; padding: 0; } .page { border: none; } }
/* print-safe fallback (المهمة 4): LibreOffice's HTML->PDF does not support
   flex — linearize the score/pillar boxes so nothing detaches or truncates */
body.printsafe .score { display: table; width: 100%; }
body.printsafe .score .num { display: table-cell; vertical-align: middle;
                             padding-left: 16px; }
body.printsafe .pillars { display: block; }
body.printsafe .pillar { display: block; margin: 6px 0; }
body.printsafe .page { max-width: 100%; padding: 18px 22px; }
body.printsafe h1 { font-size: 1.35rem; white-space: normal; }
/* أرقام لا تُكسر بين سطرين — 256.23 مليون لا تنقسم 256.2 / 3.
   th بلا nowrap: 9 أعمدة برؤوس غير قابلة للكسر قصّت عمود التحقق عند
   الحافة (عيب 4 من مراجعة v2) */
body.printsafe td.num { white-space: nowrap; }
/* v7 (تدقيق حديد عز — إصلاح 8): أسماء المؤشرات الإنجليزية كانت تُقصّ
   (Reve / Gross F) — عمود الاسم يأخذ حصة أوسع ولا يُكسر داخل الكلمة */
body.printsafe td.mname { white-space: nowrap; min-width: 15em; }
body.printsafe .vstat { white-space: normal; }
body.printsafe table { width: 100%; table-layout: auto; }
body.printsafe tr { page-break-inside: avoid; }
body.printsafe table { font-size: .8rem; }
body.printsafe .meta { font-size: .82rem; }
/* v3 (عيب 4): غلاف يعيش في صفحة واحدة — ضغط الكتل العلوية بدل ترك
   LibreOffice يوزعها على صفحتين، وصفحات أخيرة غير شبه فارغة */
body.printsafe { padding: 0; }
body.printsafe .page { padding: 14px 18px; border-radius: 0; }
body.printsafe h1 { font-size: 1.18rem; margin: 0 0 2px; }
body.printsafe h2 { font-size: .98rem; margin: 14px 0 8px;
                    page-break-after: avoid; }
body.printsafe .score { padding: 8px 12px; margin: 8px 0; }
body.printsafe .score .num { font-size: 1.7rem; padding-left: 10px; }
body.printsafe .pillars { display: block; }
body.printsafe .pillar { display: inline-block; padding: 4px 10px;
                         font-size: .78rem; margin: 3px 4px 3px 0; }
body.printsafe .meta { font-size: .78rem; margin: 2px 0; }
body.printsafe table { font-size: .76rem; }
body.printsafe th { padding: 5px 7px; }
body.printsafe td { padding: 4px 7px; }
body.printsafe .vstat { font-size: .72rem; color: #475569;
                        white-space: normal; }
/* سطور الميتا كجدول بلا حدود — التغليف الوحيد الذي يُتقنه LibreOffice */
body.printsafe table.metaln { width: 100%; margin: 2px 0; }
body.printsafe table.metaln td { border: none; padding: 2px 4px;
                                 font-size: .78rem; color: #64748b;
                                 vertical-align: top; }
body.printsafe table.metaln td.mlab { white-space: nowrap; font-weight: 600;
                                      color: #475569; width: 1%; }
body.printsafe ul { margin: 4px 0; }
body.printsafe li { margin-bottom: 3px; }
body.printsafe .comment { padding: 5px 2px; }
"""


def _badge(status: str) -> str:
    cls = {"Positive": "pos", "Negative": "neg", "Neutral": "neu"}.get(status, "na")
    return f'<span class="badge {cls}">{ESC(status)}</span>'


def _nb(text: str) -> str:
    """Non-breaking variant for print cells: spaces join the token so
    LibreOffice cannot wrap mixed-bidi currency values mid-number."""
    return text.replace(" ", " ")


def _metrics_table(rows: list[MetricRow], prev_year: int, curr_year: int,
                   currency: str, scale: int = 1,
                   verif: dict | None = None) -> str:
    verif = verif or {}
    # v7 (تدقيق حديد عز — إصلاح 8): أسهم ▲▼→ تتحول إلى «؟» في خط الطباعة
    # العربي (LibreOffice) — الكلمة العربية القياسية (TREND_AR) مضمونة
    # العرض في كل الخطوط ولا تنكسر الاتجاهيًا داخل <bdi>.
    from src.analysis.comparison import TREND_AR

    trend_text = {
        "Improving": TREND_AR["Improving"], "Declining": TREND_AR["Declining"],
        "Stable": TREND_AR["Stable"], "N/A": "–",
    }

    def _num(v: str) -> str:
        # كل قيمة رقمية داخل <bdi> — bidi-isolation يمنع تشتت الرقم
        # والوحدة في سياق RTL (كانت $N/A$ والانشطار ظاهرين بالتقرير).
        return f"<bdi>{ESC(v)}</bdi>"

    trs = []
    for r in rows:
        # نفس حالة Excel (عيب 6): كل مؤشر يحمل أسوأ حالة لمدخلاته —
        # غير القابل للحساب «غير متوفر» ولا يوصف أبدًا بأنه موثق
        vlabel = verif.get(r.key) or ("غير متوفر"
                                      if r.status == "N/A" else "—")
        trs.append(
            "<tr>"
            f"<td>{ESC(r.category)}</td>"
            f'<td class="mname">{ESC(r.label)}</td>'
            f'<td class="num">{_num(_nb(fmt_value_ar(r.previous, r.kind, currency, scale)))}</td>'
            f'<td class="num">{_num(_nb(fmt_value_ar(r.current, r.kind, currency, scale)))}</td>'
            f'<td class="num">{_num(_nb(fmt_signed_ar(r.change, r.kind, currency, scale)))}</td>'
            f'<td class="num">{_num(fmt_signed_pct(r.change_pct))}</td>'
            f"<td>{_badge(r.status)}</td>"
            f"<td>{ESC(trend_text.get(r.trend, r.trend))}</td>"
            f'<td class="vstat">{ESC(vlabel)}</td>'
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Category</th><th>Metric</th><th>"
        f"{prev_year}</th><th>{curr_year}</th><th>Change</th><th>Change %</th>"
        "<th>Status</th><th>Trend</th><th>Verification</th></tr></thead>"
        f"<tbody>{''.join(trs)}</tbody></table>"
    )


def build_html_report(
    results: dict,
    analysis: AIAnalysis,
    score: HealthScore,
    currency: str = "$",
    print_safe: bool = False,
) -> str:
    prev_y, cur_y = results["prev_year"], results["curr_year"]
    company = ESC(results["company"])
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")

    score_html = ""
    if score.total is not None:
        pillar_chips = "".join(
            f'<div class="pillar"><b>{ESC(p.name)}</b> — '
            f'{ESC("N/A") if p.score is None else f"{p.score:.0f}/100"}</div>'
            for p in score.pillars
        )
        score_html = (
            '<div class="score">'
            f'<div class="num">{score.total:.0f}</div>'
            f'<div><b>{ESC(score.label)}</b><div class="pillars">{pillar_chips}</div></div>'
            "</div>"
        )
    else:
        # v3 (عيب 6): الدرجة المحجوبة تُعرض كحالة صادقة في HTML/PDF —
        # نفس ما يقوله Excel («غير محسوبة»)، لا اختفاء صامت
        # سطر مضغوط: الأركان المحجوبة بالاسم — تفصيل السياسة الطويل
        # كان يدفع الغلاف لصفحة ثانية (عيب 4 من مراجعة v2)
        blocked_names = "، ".join(p.name for p in score.pillars
                                  if p.score is None) or "—"
        reason = ("السياسة ترفض الحسم عند ركيزة حرجة ناقصة — قيم تحتاج "
                  f"مراجعة. محجوبة: {blocked_names}")
        score_html = (
            '<div class="score">'
            '<div class="num">—</div>'
            f'<div><b>الدرجة الصحية: غير محسوبة</b>'
            f'<div class="meta">{ESC(reason)}</div>'
            "</div>"
            "</div>"
        )

    comments = "".join(
        f'<div class="comment" dir="auto"><b>{ESC(m)}:</b> {ESC(c)}</div>'
        for m, c in analysis.ratio_comments
    ) or '<p class="muted">No commentary available.</p>'

    recs = (
        "<ol>"
        + "".join(
            f'<li dir="auto">{ESC(action)}'
            + (f'<div class="muted" dir="auto">📎 {ESC(evidence)}</div>' if evidence else "")
            + "</li>"
            for action, evidence in analysis.recommendations
        )
        + "</ol>"
        if analysis.recommendations
        else '<p class="muted">No recommendations.</p>'
    )

    # النواقص بصدق (عيب 4 من مراجعة v2): «None» لا يُعرض أبداً بينما
    # توجد مؤشرات N/A — الفرق موثق: حقول لم تُستخرج مقابل مؤشرات لا
    # تُحسب لعدم توفر مدخلاتها
    na_metrics = results.get("na_metrics") or []
    missing = (
        "<ul>" + "".join(f"<li>{ESC(m)}</li>" for m in results["missing"]) + "</ul>"
        if results["missing"]
        else "")
    if not results["missing"] and na_metrics:
        missing = (f'<p class="muted">لا حقول مفقودة من الاستخراج — لكن '
                   f'{len(na_metrics)} مؤشرًا غير قابلة للحساب لعدم توفر '
                   f'مدخلاتها الموثقة (القائمة أعلاه): '
                   f'{ESC("، ".join(str(x) for x in na_metrics))}.</p>')
    elif not results["missing"]:
        missing = ('<p class="muted">None — all available metrics were '
                   'computed, and every metric found its inputs.</p>')

    # MVP safety guard (المهمة 3): the report is PRELIMINARY while any
    # critical field still needs review — a verified-final report is only
    # produced once the pending list is empty
    # v6 إصلاح حديد عز (إصلاح 6): الغلاف مربوط بحالة التوثيق الفعلية —
    # تغطية = الحاسمة من سجل القرار ÷ الخانات ذات القيمة. النص الثابت
    # «تقرير نهائي موثق» بلا تحقق كان يطبع على 4/56 (7%).
    from src.analysis.financial_gate import decide

    dl = results.get("decision_log") or []
    _valued = [e for e in dl if e.get("final") is not None]
    _decisive = [e for e in _valued
                 if decide(e.get("status", "MISSING"))
                 in ("use", "use_disclosed")]
    _coverage = (len(_decisive) / len(_valued)) if _valued else 0.0
    preliminary = bool(results.get("pending_critical_review")) or _coverage < 1.0
    # المهمة 6: honest labeling — test-reviewer attestations are NOT
    # production human review; the unit and period type come from the
    # document, never invented
    scale = int(results.get("unit_scale") or 1)   # printed-unit factor
    unit_note = results.get("unit_note") or ""
    period_type = results.get("period_type") or ""
    reviewer_label = results.get("reviewer_label") or ""
    na_metrics = results.get("na_metrics") or []
    tax_note = (results.get("curr_metrics").notes.get("tax_rate")
                if results.get("curr_metrics") and
                results["curr_metrics"].notes.get("tax_rate") else "")
    if preliminary:
        # v7 إصلاح عيب البنية: كان `[{"field": e["field"] for e in ...}]`
        # — dict-comprehension داخل list literal — ينتج [{}] دائمًا فيتكسر
        # p["field"] (KeyError) حين لا يوجد pending صريح. المطلوب كان
        # list comprehension ينتج عنصرًا لكل حقل غير حاسم.
        pend = results.get("pending_critical_review") or [
            {"field": e.get("field", "?")}
            for e in _valued
            if decide(e.get("status", "MISSING")) == "not_decisive"
        ]
        pend_all = sorted({str(p.get("field", "?")) for p in pend})
        # v3 (عيب 4): لافتة مضغوطة — العدد + أول ستة بنود، لا قائمة تطول
        # وتدفع الغلاف لصفحة ثانية
        pend_names = "، ".join(pend_all[:6]) + ("، …" if len(pend_all) > 6
                                                else "")
        report_status = (
            '<div style="background:#fff3cd;border:1px solid #f0d9a8;'
            'border-radius:9px;padding:11px 16px;margin:10px 0;font-size:.92rem">'
            f'⚠ <b>تقرير أولي غير معتمد نهائياً — تغطية التوثيق '
            f'({len(_decisive)}/{len(_valued)}) وتوجد بنود بانتظار '
            f'المراجعة البشرية</b><br>'
            f'البنود المعلقة: {pend_names}'
            + (f'<br>المراجع: {reviewer_label}' if reviewer_label else "")
            + "</div>")
    else:
        report_status = (
            '<div style="background:#d4edda;border:1px solid #a7d8bd;'
            'border-radius:9px;padding:11px 16px;margin:10px 0;font-size:.92rem">'
            '✓ <b>تقرير نهائي موثق</b> — كل البنود الحرجة تم التحقق منها '
            "(آليًا بتصديق عبر-طبقتين أو بشريًا)</div>")
    # v3 (عيب 4): LibreOffice لا يغلف سطور .meta الطويلة المختلطة الاتجاه
    # (قصّ عند الحافة وكسر داخل الكلمات) — الجداول وحدها تعمل بإتقان عنده،
    # فوضع الطباعة يجعلها صفوف جدول بلا حدود؛ الشاشة تبقى div عادية
    def _meta(label: str, value: str) -> str:
        if not value:
            return ""
        if print_safe:
            return (f'<table class="metaln"><tr>'
                    f'<td class="mlab">{ESC(label)}</td>'
                    f'<td>{ESC(value)}</td></tr></table>')
        return f'<div class="meta">{ESC(label)}: {ESC(value)}</div>'

    unit_html = _meta("وحدة القوائم", unit_note)
    period_html = _meta("نوع الفترة", period_type)
    na_html = _meta("مؤشرات غير قابلة للحساب (N/A)",
                    "، ".join(str(x) for x in na_metrics))
    tax_html = _meta("ملاحظة الضريبة", tax_note)
    # v4 (نقطة 2): الإخلاء صف في جدول الميتا على الغلاف — لا فقرة ذيلية
    # تُترك وحيدة في صفحة أخيرة شبه فارغة
    disclaimer_html = _meta(
        "إخلاء مسؤولية",
        "Benchmark mentions, if any, refer to widely accepted general "
        "guideline levels — not sector averages. This report does not "
        "constitute investment advice.")

    # Human-review trail (أثر المراجعة البشرية): every value a human attested
    # carries the reviewer, the machine value before, and the final verdict —
    # taken from the pipeline notes (the chain itself lives in the review log)
    review_lines = [n for n in (results.get("notes") or [])
                    if "Human review" in n]
    reviews = (
        "<ul>" + "".join(f'<li dir="auto">{ESC(m)}</li>' for m in review_lines)
        + "</ul>"
        if review_lines
        else '<p class="muted">لا مراجعات بشرية على هذه القيم.</p>'
    )

    interpreter = "Gemini AI" if analysis.ok else "deterministic rule-based engine"
    # v4 (نقطة 3): كل تحليل مبني على قيم غير مراجَعة يُوسم صراحة — تعليقات
    # Gemini والتوصيات وأي حكم مشتق لا يُقدَّم كحكم نهائي بينما أعمدة
    # التحقق تقول «يحتاج مراجعة». المعادلات نفسها بلا تغيير.
    if preliminary:
        provisional_html = (
            '<div style="background:#fef3c7;border:1px solid #f0d9a8;'
            'border-radius:9px;padding:9px 14px;margin:8px 0;font-size:.85rem">'
            '⚠ <b>تحليل تجريبي غير معتمد</b> — التعليقات والتوصيات التالية '
            'مولدة آليًا من قيم حالتها «يحتاج مراجعة» (عمود Verification في '
            'الجدول أعلاه) — تُقرأ كمؤشرات للاستكشاف، وليست حكمًا نهائيًا.'
            "</div>")
    else:
        provisional_html = ""
    # dir=rtl (v3): التقرير عربي أساسًا — غياب اتجاه القاعدة جعل LibreOffice
    # يكسر الأسطر العربية عند الحواف وحتى داخل الكلمات
    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8">
<title>Financial Analysis — {company}</title><style>{_CSS}</style></head>
<body class="{'printsafe' if print_safe else ''}">
<div class="page">
<h1>📊 Financial Statement Analysis — {company}</h1>
<div class="meta">Period: {prev_y} → {cur_y} · Generated: {generated} ·
Interpreted by: {ESC(interpreter)} ({ESC(analysis.model)}) · All numbers computed in Python</div>
{report_status}
{score_html}
{unit_html}{period_html}{tax_html}{na_html}{disclaimer_html}
<h2>Metrics — {prev_y} vs {cur_y}</h2>
{_metrics_table(results['rows'], prev_y, cur_y, currency, scale, results.get('verification_status'))}
<h2>Ratio Commentary</h2>
{provisional_html}
{comments}
<h2>Recommendations</h2>
{provisional_html}
{recs}
<h2>Missing Data</h2>
{missing}
<h2>Human Review Trail — أثر المراجعة البشرية</h2>
{reviews}
</div></body></html>"""
