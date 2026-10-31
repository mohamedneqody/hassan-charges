"""Self-contained printable study report (تقرير الدراسة التطبيقية).

One HTML file with the cross-company comparison table, an ROE bar strip and
Altman zone chips — the ready-to-print deliverable for the thesis's applied
study chapter (open in any browser → Ctrl+P → PDF). No external assets, no
JavaScript: pure inline CSS, RTL.
"""
from __future__ import annotations

from datetime import datetime

from src.analysis.portfolio import CompanyRecord


def _fmt(value: float | None, suffix: str = "", decimals: int = 1) -> str:
    if value is None:
        return "—"
    return f"{value:,.{decimals}f}{suffix}"


_ZONE_CLASS = {"safe": "z-safe", "grey": "z-grey", "distress": "z-distress"}


def build_study_report(records: list[CompanyRecord]) -> str:
    records = sorted(records, key=lambda r: (r.company.lower(), r.curr_year))
    max_roe = max([abs(r.roe_pct or 0) for r in records] + [1.0])

    rows_html = []
    for r in records:
        zone = (r.altman_zone or "").strip()
        zone_en = {"🟢": "safe", "🟡": "grey", "🔴": "distress"}.get(zone[:1], "")
        rows_html.append(
            "<tr>"
            f'<td class="co">{_esc(r.company)}</td>'
            f"<td>{r.prev_year} ← {r.curr_year}</td>"
            f'<td class="num">{_esc(r.currency)}</td>'
            f'<td class="num">{_fmt(r.revenue)}</td>'
            f'<td class="num">{_fmt(r.net_income)}</td>'
            f'<td class="num">{_fmt(r.net_margin_pct, "%")}</td>'
            f'<td class="num"><b>{_fmt(r.roe_pct, "%")}</b></td>'
            f'<td class="num">{_fmt(r.roa_pct, "%")}</td>'
            f'<td class="num">{_fmt(r.current_ratio, "", 2)}</td>'
            f'<td class="num">{_fmt(r.debt_to_equity, "", 2)}</td>'
            f'<td class="num">{_fmt(r.health_total, "", 0)}</td>'
            f'<td class="num">{_fmt(r.altman_score, "", 2)}</td>'
            f'<td><span class="zone {_ZONE_CLASS.get(zone_en, "")}">{_esc(zone or "—")}</span></td>'
            "</tr>"
        )

    bars_html = []
    for r in records:
        roe = r.roe_pct or 0
        width = max(2.0, abs(roe) / max_roe * 100)
        color = "#10b981" if roe >= 0 else "#f43f5e"
        bars_html.append(
            '<div class="bar-row">'
            f'<span class="bar-name">{_esc(r.company)} ({r.curr_year})</span>'
            '<span class="bar-track">'
            f'<span class="bar-fill" style="width:{width:.1f}%;background:{color};"></span>'
            f'<span class="bar-val" style="color:{color};">{roe:+.1f}%</span>'
            "</span></div>"
        )

    n = len(records)
    years = f"{min(r.prev_year for r in records)}–{max(r.curr_year for r in records)}" if records else "—"
    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8">
<title>تقرير الدراسة التطبيقية — مقارنة الشركات</title>
<style>
  body {{ font-family: "Segoe UI", Tahoma, Arial, sans-serif; color:#1e293b; margin:32px; }}
  h1 {{ color:#4f46e5; font-size:1.5rem; margin:0 0 4px; }}
  .sub {{ color:#64748b; font-size:.9rem; margin-bottom:18px; }}
  .meta {{ background:#eef2ff; border-radius:10px; padding:10px 14px; font-size:.85rem; margin-bottom:20px; line-height:1.9; }}
  table {{ width:100%; border-collapse:collapse; font-size:.8rem; }}
  th {{ background:#4f46e5; color:#fff; padding:8px 6px; text-align:center; }}
  td {{ border-bottom:1px solid #e2e8f0; padding:7px 6px; text-align:center; }}
  td.co {{ text-align:right; font-weight:600; }}
  tr:nth-child(even) td {{ background:#f8fafc; }}
  .num {{ direction:ltr; }}
  h2 {{ color:#4f46e5; font-size:1.05rem; margin:26px 0 10px; }}
  .bar-row {{ display:flex; align-items:center; gap:8px; margin:6px 0; }}
  .bar-name {{ width:280px; font-size:.78rem; color:#334155; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  .bar-track {{ flex:1; background:#f1f5f9; border-radius:6px; height:16px; position:relative; }}
  .bar-fill {{ display:block; height:100%; border-radius:6px; }}
  .bar-val {{ position:absolute; inset-inline-end:6px; top:-1px; font-size:.72rem; font-weight:700; }}
  .zone {{ padding:2px 10px; border-radius:99px; font-size:.75rem; }}
  .z-safe {{ background:#d1fae5; color:#065f46; }}
  .z-grey {{ background:#fef3c7; color:#92400e; }}
  .z-distress {{ background:#ffe4e6; color:#9f1239; }}
  .foot {{ margin-top:26px; color:#94a3b8; font-size:.75rem; line-height:1.9; border-top:1px solid #e2e8f0; padding-top:10px; }}
  @media print {{ body {{ margin:12mm; }} }}
</style></head><body>
<h1>📊 تقرير الدراسة التطبيقية — مقارنة الشركات</h1>
<div class="sub">مساعد ذكي لتحليل القوائم المالية باستخدام تقنيات الذكاء الاصطناعي — دراسة تطبيقية على الشركات المقيدة بالبورصة المصرية</div>
<div class="meta">
  <b>عينة الدراسة:</b> {n} شركة · <b>الفترة:</b> {years} · <b>تاريخ التوليد:</b> {datetime.now().strftime("%Y-%m-%d %H:%M")}<br>
  <b>المنهجية:</b> استخراج أرقام القوائم من الملفات المنشورة (بما فيها الممسوحة) عبر الذكاء الاصطناعي مع طبقات تحقق متعددة،
  وحساب كل النسب حتميًا بـ Python — التعليقات فقط تُصاغ بالذكاء الاصطناعي ولا يُسمح له باختراع أي رقم.
  درجة الصحة من 100 (سيولة/مديونية/ربحية/نقدية) وAltman Z″ مؤشر إنذار مبكر للضيق المالي (إرشادي وليس تنبؤًا).
</div>
<h2>جدول المقارنة</h2>
<table>
<thead><tr>
<th>الشركة</th><th>الفترة</th><th>العملة</th><th>الإيرادات</th><th>صافي الربح</th>
<th>هامش صافي</th><th>ROE</th><th>ROA</th><th>النسبة الجارية</th><th>الدين/حقوق الملكية</th>
<th>درجة الصحة</th><th>Altman Z″</th><th>المنطقة</th>
</tr></thead>
<tbody>{"".join(rows_html)}</tbody>
</table>
<h2>العائد على حقوق الملكية (ROE)</h2>
{"".join(bars_html)}
<div class="foot">
  أُنتج هذا التقرير آليًا بواسطة نظام تحليل القوائم المالية (Financial Statement Analysis Agent).
  جميع الأرقام مقروءة من قوائم الشركات المنشورة وخضعت للتحقق متعدد الطبقات؛ القيم الناقصة تظهر بشرطة (—).
  هذا التحليل إرشادي ولا يُعد توصية استثمارية.
</div>
</body></html>"""


def _esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


_SEV_CLASS = {"high": "f-high", "medium": "f-med", "low": "f-low"}


def build_research_note(note: dict) -> str:
    """One-company equity-research-note style HTML (بحثة محلل).

    `note` is a plain dict assembled by the app: company, prev_year,
    curr_year, currency, rating, health_total, health_label, altman_score,
    altman_zone, summary_lines (list[str]), flags [{name, severity, detail}],
    beneish {m_score, verdict, components, missing}, confidence
    [{label, year, value, witnesses}], footer.
    """
    rating = note.get("rating") or "—"
    rating_class = {
        "قوي": "r-strong", "مستقر": "r-stable", "مكشوف": "r-weak",
    }.get(rating, "r-stable")
    flags = note.get("flags") or []
    flag_rows = "".join(
        f'<tr><td class="flg {_SEV_CLASS.get(f["severity"], "f-low")}">{_esc(f["name"])}</td>'
        f'<td>{_esc(f["detail"])}</td></tr>'
        for f in flags
    ) or '<tr><td colspan="2" class="ok">لا توجد أعلام حمراء على مستوى الفحوصات الحالية ✅</td></tr>'

    beneish = note.get("beneish") or {}
    m_score = beneish.get("m_score")
    b_verdict = beneish.get("verdict") or ""
    if m_score is not None:
        b_block = (
            f'<div class="m-score">M = <b>{m_score:.2f}</b> '
            f'<span class="zone {_ZONE_CLASS.get(beneish.get("zone", ""), "")}">{_esc(b_verdict)}</span></div>'
            '<div class="m-comps">'
            + " ".join(
                f'<span class="chip">{_esc(k)} = {v:.2f}</span>'
                for k, v in (beneish.get("components") or {}).items()
            )
            + "</div>"
        )
    else:
        b_block = (
            f'<div class="m-comps muted">Beneish غير محسوب — بيانات ناقصة: '
            f'{_esc(", ".join(beneish.get("missing") or []) or "—")}</div>'
        )

    conf_rows = "".join(
        f'<tr><td>{_esc(c["label"])}</td><td>{c["year"]}</td>'
        f'<td class="num">{_esc(c["value"])}</td>'
        f'<td class="witnesses">{"●" * c["witnesses"]}{"○" * (3 - c["witnesses"])}</td></tr>'
        for c in note.get("confidence") or []
    ) or '<tr><td colspan="4">— لا توجد بيانات شهود لهذا الملف (مصدر نصي) —</td></tr>'

    summary = "".join(f"<li>{_esc(s)}</li>" for s in note.get("summary_lines") or [])
    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8">
<title>بحثة محلل — {_esc(note.get("company") or "")}</title>
<style>
  body {{ font-family:"Segoe UI", Tahoma, Arial, sans-serif; color:#1e293b; margin:32px; max-width:900px; }}
  h1 {{ color:#4f46e5; font-size:1.4rem; margin:0 0 2px; }}
  .sub {{ color:#64748b; font-size:.85rem; margin-bottom:14px; }}
  .head {{ display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin-bottom:14px; }}
  .rating {{ padding:6px 18px; border-radius:99px; font-weight:700; font-size:1.05rem; }}
  .r-strong {{ background:#d1fae5; color:#065f46; }}
  .r-stable {{ background:#fef3c7; color:#92400e; }}
  .r-weak {{ background:#ffe4e6; color:#9f1239; }}
  .chip-kpi {{ background:#eef2ff; color:#3730a3; padding:5px 12px; border-radius:8px; font-size:.85rem; }}
  h2 {{ color:#4f46e5; font-size:1rem; margin:22px 0 8px; border-bottom:1px solid #e2e8f0; padding-bottom:4px; }}
  ul.summary {{ line-height:2; font-size:.9rem; padding-inline-start:20px; }}
  table {{ width:100%; border-collapse:collapse; font-size:.8rem; }}
  th {{ background:#4f46e5; color:#fff; padding:6px; }}
  td {{ border-bottom:1px solid #e2e8f0; padding:6px; text-align:center; }}
  td.flg {{ font-weight:700; white-space:nowrap; }}
  .f-high {{ color:#9f1239; }} .f-med {{ color:#92400e; }} .f-low {{ color:#1d4ed8; }}
  td.ok {{ color:#065f46; }}
  .num {{ direction:ltr; }}
  .witnesses {{ letter-spacing:3px; color:#4f46e5; }}
  .m-score {{ font-size:1rem; margin:6px 0; }}
  .m-comps {{ font-size:.78rem; }}
  .chip {{ background:#f1f5f9; border-radius:6px; padding:2px 8px; margin:2px; display:inline-block; }}
  .muted {{ color:#94a3b8; }}
  .foot {{ margin-top:24px; color:#94a3b8; font-size:.72rem; line-height:1.8; border-top:1px solid #e2e8f0; padding-top:8px; }}
  @media print {{ body {{ margin:12mm; }} }}
</style></head><body>
<h1>📈 بحثة محلل — {_esc(note.get("company") or "")}</h1>
<div class="sub">تحليل القوائم المالية {note.get("prev_year")} ← {note.get("curr_year")} · العملة {_esc(note.get("currency") or "$")} · {_esc(str(note.get("generated") or ""))}</div>
<div class="head">
  <span class="rating {rating_class}">{_esc(rating)}</span>
  <span class="chip-kpi">درجة الصحة: {note.get("health_total") if note.get("health_total") is not None else "—"} {_esc(note.get("health_label") or "")}</span>
  <span class="chip-kpi">Altman Z″: {note.get("altman_score") if note.get("altman_score") is not None else "—"} {_esc(note.get("altman_zone") or "")}</span>
</div>
<h2>الخلاصة التنفيذية</h2>
<ul class="summary">{summary}</ul>
<h2>⚠️ الأعلام الحمراء</h2>
<table><thead><tr><th>المؤشر</th><th>الدليل الرقمي</th></tr></thead>
<tbody>{flag_rows}</tbody></table>
<h2>🧮 نموذج Beneish لكشف التلاعب بالأرباح</h2>
{b_block}
<h2>🔍 ثقة الأرقام الرئيسية</h2>
<table><thead><tr><th>البند</th><th>السنة</th><th>القيمة</th><th>قراءات مستقلة متفقة</th></tr></thead>
<tbody>{conf_rows}</tbody></table>
<div class="foot">{_esc(note.get("footer") or "")}</div>
</body></html>"""
