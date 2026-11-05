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
from src.dashboard.charts import fmt_signed, fmt_signed_pct, fmt_value

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
"""


def _badge(status: str) -> str:
    cls = {"Positive": "pos", "Negative": "neg", "Neutral": "neu"}.get(status, "na")
    return f'<span class="badge {cls}">{ESC(status)}</span>'


def _metrics_table(rows: list[MetricRow], prev_year: int, curr_year: int, currency: str) -> str:
    trs = []
    for r in rows:
        trs.append(
            "<tr>"
            f"<td>{ESC(r.category)}</td><td>{ESC(r.label)}</td>"
            f'<td class="num">{ESC(fmt_value(r.previous, r.kind, currency))}</td>'
            f'<td class="num">{ESC(fmt_value(r.current, r.kind, currency))}</td>'
            f'<td class="num">{ESC(fmt_signed(r.change, r.kind, currency))}</td>'
            f'<td class="num">{ESC(fmt_signed_pct(r.change_pct))}</td>'
            f"<td>{_badge(r.status)}</td>"
            f"<td>{ESC(r.trend_symbol + ' ' + r.trend) if r.trend != 'N/A' else '–'}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Category</th><th>Metric</th><th>"
        f"{prev_year}</th><th>{curr_year}</th><th>Change</th><th>Change %</th>"
        "<th>Status</th><th>Trend</th></tr></thead>"
        f"<tbody>{''.join(trs)}</tbody></table>"
    )


def build_html_report(
    results: dict,
    analysis: AIAnalysis,
    score: HealthScore,
    currency: str = "$",
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

    missing = (
        "<ul>" + "".join(f"<li>{ESC(m)}</li>" for m in results["missing"]) + "</ul>"
        if results["missing"]
        else '<p class="muted">None — all available metrics were computed.</p>'
    )

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
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>Financial Analysis — {company}</title><style>{_CSS}</style></head>
<body><div class="page">
<h1>📊 Financial Statement Analysis — {company}</h1>
<div class="meta">Period: {prev_y} → {cur_y} · Generated: {generated} ·
Interpreted by: {ESC(interpreter)} ({ESC(analysis.model)}) · All numbers computed in Python</div>
{score_html}
<h2>Metrics — {prev_y} vs {cur_y}</h2>
{_metrics_table(results['rows'], prev_y, cur_y, currency)}
<h2>Ratio Commentary</h2>
{comments}
<h2>Recommendations</h2>
{recs}
<h2>Missing Data</h2>
{missing}
<h2>Human Review Trail — أثر المراجعة البشرية</h2>
{reviews}
<p class="muted">Benchmark mentions, if any, refer to widely accepted general guideline
levels — not sector averages. This report does not constitute investment advice.</p>
</div></body></html>"""
