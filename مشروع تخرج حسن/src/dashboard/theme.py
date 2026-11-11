"""Light design system for the dashboard: global CSS + HTML components.

Everything visual that Streamlit's own widgets can't express lives here:
animations, KPI cards, the financial table with badges, the landing hero,
and the narrative report cards. CSS-only animations (Streamlit's markdown
cannot execute JavaScript).
"""
from __future__ import annotations

import html as _html

# Design tokens -------------------------------------------------------------
BRAND = "#4f46e5"        # indigo-600
BRAND_2 = "#7c3aed"      # violet-600
POS = "#059669"
NEG = "#e11d48"
INK = "#0f172a"

ESC = _html.escape

THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

:root {
  --bg: #f6f8fb; --card: #ffffff; --ink: #0f172a; --muted: #64748b;
  --line: #e2e8f0; --brand: #4f46e5; --brand2: #7c3aed;
  --pos: #059669; --neg: #e11d48;
}

html, body, .stApp, [data-testid="stAppViewContainer"] {
  font-family: 'Inter', 'Segoe UI', 'Tahoma', system-ui, sans-serif;
  color: var(--ink);
}
[dir="rtl"], .stApp {
  background:
    radial-gradient(900px 480px at 88% -8%, rgba(99,102,241,.09), transparent 62%),
    radial-gradient(760px 420px at -8% 104%, rgba(139,92,246,.07), transparent 60%),
    #f8fafc;
}

@media (prefers-reduced-motion: reduce) {
  .hero, .kpi-card, .feature, .step-card { animation-duration: .01s !important; animation-iteration-count: 1 !important; }
}
.stApp::before, .stApp::after {
  content: ""; position: fixed; border-radius: 50%; filter: blur(90px);
  z-index: -1; pointer-events: none;
}
.stApp::before { width: 420px; height: 420px; background: rgba(99,102,241,.16); top: -120px; left: -100px; animation: blobFloat 18s ease-in-out infinite alternate; }
.stApp::after { width: 380px; height: 380px; background: rgba(139,92,246,.13); bottom: -100px; right: -80px; animation: blobFloat 24s ease-in-out infinite alternate-reverse; }
@keyframes blobFloat { from { transform: translate(0,0) scale(1); } to { transform: translate(70px, 50px) scale(1.18); } }
h1, h2, h3 { text-align: center; }
[data-testid="stMarkdownContainer"] { direction: rtl; }
[data-testid="stMarkdownContainer"] pre, [data-testid="stMarkdownContainer"] code { direction: ltr; text-align: left; }
section.stMain, section.stMain > div, .block-container { position: relative; z-index: 1; }
.fin-table { direction: rtl; }
.fin-table td.num, .fin-table th { text-align: center; }

/* landing: centered composition */
.hero { text-align: center; }
.hero .chips, .hero [style*="margin-top:14px"] { display: flex; justify-content: center; flex-wrap: wrap; }
.sec-label {
  text-align: center; font-size: 1.15rem; font-weight: 800; margin: 1.6rem 0 .9rem;
  color: var(--ink);
}
.sec-label::after {
  content: ""; display: block; width: 64px; height: 4px; border-radius: 4px;
  background: linear-gradient(90deg, var(--brand), var(--brand2));
  margin: 8px auto 0;
}
.or-line { text-align: center; color: #94a3b8; }
.step-card {
  background: var(--card); border: 1px solid var(--line); border-radius: 16px;
  padding: 18px 14px; text-align: center; position: relative; overflow: hidden;
  box-shadow: 0 1px 2px rgba(15,23,42,.05), 0 10px 24px -20px rgba(15,23,42,.35);
  animation: fadeUp .55s cubic-bezier(.21,.98,.6,.99) both;
  transition: transform .25s ease, box-shadow .25s ease, border-color .25s ease;
  height: 100%;
}
.step-card:hover { transform: translateY(-5px); border-color: #c7d2fe; box-shadow: 0 14px 30px -14px rgba(79,70,229,.4); }
.step-num {
  position: absolute; top: 8px; inset-inline-start: 10px; width: 28px; height: 28px;
  border-radius: 50%; background: linear-gradient(135deg, var(--brand), var(--brand2));
  color: #fff; display: flex; align-items: center; justify-content: center;
  font-weight: 800; font-size: .82rem;
  animation: numPulse 2.6s ease-in-out infinite;
}
@keyframes numPulse { 0%,100% { transform: scale(1); } 50% { transform: scale(1.15); } }
.step-ico { font-size: 1.5rem; margin-bottom: 6px; }
.step-card b { font-size: .95rem; }
.step-card span { color: var(--muted); font-size: .82rem; }
.stat-band {
  display: flex; justify-content: center; gap: 26px; flex-wrap: wrap;
  background: linear-gradient(90deg, #eef2ff, #f5f3ff, #ecfeff);
  border: 1px solid #e0e7ff; border-radius: 16px; padding: 14px 22px;
  font-size: .92rem; color: #334155; animation: fadeUp .5s ease both;
}
.stat-band span { white-space: nowrap; }
[data-testid="stFileUploaderDropzone"] { margin-inline: auto; }
[data-testid="stFileUploader"] label { text-align: center; width: 100%; }
.block-container { padding-top: 2.2rem; max-width: 1200px; animation: fadeUp .5s ease both; }
h1, h2, h3 { font-weight: 700; letter-spacing: -.01em; color: var(--ink); }

/* Section headings get an indigo accent bar */
.block-container h3 {
  position: relative; padding-left: 14px;
}
.block-container h3::before {
  content: ""; position: absolute; left: 0; top: 50%; transform: translateY(-50%);
  width: 5px; height: 20px; border-radius: 3px;
  background: linear-gradient(180deg, var(--brand), var(--brand2));
}

/* ---------- keyframes ---------- */
@keyframes fadeUp { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
@keyframes heroShift { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }
@keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(16,185,129,.45); } 70% { box-shadow: 0 0 0 8px transparent; } 100% { box-shadow: 0 0 0 0 transparent; } }
@keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

/* ---------- KPI cards ---------- */
.kpi-card {
  position: relative; background: var(--card); border: 1px solid var(--line);
  border-radius: 16px; padding: 18px 20px 16px 24px; overflow: hidden;
  box-shadow: 0 1px 2px rgba(15,23,42,.05), 0 10px 26px -20px rgba(15,23,42,.35);
  animation: fadeUp .55s cubic-bezier(.21,.98,.6,.99) both;
  transition: transform .25s ease, box-shadow .25s ease, border-color .25s ease;
  height: 100%;
}
.kpi-card::before {
  content: ""; position: absolute; inset: 0 auto 0 0; width: 5px;
  background: linear-gradient(180deg, var(--accent), color-mix(in srgb, var(--accent) 55%, #ffffff));
}
.kpi-card:hover {
  transform: translateY(-5px);
  border-color: color-mix(in srgb, var(--accent) 35%, var(--line));
  box-shadow: 0 16px 34px -16px color-mix(in srgb, var(--accent) 45%, transparent);
}
.kpi-label { font-size: .8rem; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; }
.kpi-value { font-size: 1.85rem; font-weight: 800; margin-top: 4px; color: var(--ink); }
.kpi-card.info .kpi-value { font-size: 1.2rem; font-weight: 700; }
.kpi-delta {
  display: inline-flex; align-items: center; gap: 6px; margin-top: 10px;
  font-weight: 600; font-size: .8rem; padding: 4px 11px; border-radius: 999px;
}
.kpi-delta.up   { color: #047857; background: #d1fae5; }
.kpi-delta.down { color: #be123c; background: #ffe4e6; }
.kpi-delta.flat { color: #475569; background: #f1f5f9; }
.kpi-delta.na   { color: #94a3b8; background: #f8fafc; }

/* ---------- landing hero ---------- */
.hero {
  position: relative; overflow: hidden;
  border-radius: 28px; padding: 3.6rem 2.8rem;
  background: linear-gradient(135deg, #1e1b4b 0%, #312e81 45%, #4c1d95 100%);
  border: 1px solid rgba(129,140,248,.35);
  box-shadow: 0 24px 60px -18px rgba(49,46,129,.55);
  background: linear-gradient(120deg, #eef2ff, #f5f3ff, #ecfeff, #eef2ff);
  background-size: 300% 300%; animation: heroShift 16s ease infinite, fadeUp .6s ease both;
}
.hero h1 { font-size: 3.2rem; margin-bottom: .4rem; animation: fadeUp .8s cubic-bezier(.21,.98,.6,.99) both; }
.hero p { color: #c7d2fe; animation: fadeUp .9s .15s ease both; }
.hero .chip { animation: chipPop .5s cubic-bezier(.34,1.56,.64,1) both; }
.hero .chip:nth-child(2) { animation-delay: .08s; }
.hero .chip:nth-child(3) { animation-delay: .16s; }
.hero .chip:nth-child(4) { animation-delay: .24s; }
.hero .chip:nth-child(5) { animation-delay: .32s; }
.hero .chip:nth-child(6) { animation-delay: .4s; }
@keyframes chipPop { from { opacity: 0; transform: scale(.6) translateY(10px); } to { opacity: 1; transform: none; } }
.hero-float {
  position: absolute; font-size: 2.4rem; opacity: .45; pointer-events: none;
  animation: floatY 6s ease-in-out infinite;
}
.hero-float.hf1 { top: 16px; inset-inline-start: 5%; }
.hero-float.hf2 { bottom: 12px; inset-inline-start: 13%; font-size: 1.9rem; animation-delay: 1.1s; }
.hero-float.hf3 { top: 22px; inset-inline-end: 7%; font-size: 2rem; animation-delay: 2.2s; }
@keyframes floatY { 0%,100% { transform: translateY(0) rotate(-4deg); } 50% { transform: translateY(-16px) rotate(5deg); } }
.grad-text {
  background: linear-gradient(90deg, #a5b4fc, #e0e7ff, #67e8f9, #a5b4fc);
  background-size: 250% auto;
  -webkit-background-clip: text; background-clip: text; color: transparent;
  animation: gradShine 5s linear infinite;
}
@keyframes gradShine { to { background-position: 250% center; } }
.hero p.sub { color: var(--muted); font-size: 1.05rem; margin-bottom: 0; }
.chip {
  display: inline-flex; align-items: center; gap: 6px; padding: 5px 14px;
  border-radius: 999px; background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.25);
  font-weight: 600; font-size: .85rem; color: #e0e7ff; margin: 4px 6px 0 0;
  transition: all .2s ease;
}
.chip:hover { transform: translateY(-2px); background: rgba(255,255,255,.22); color: #fff; box-shadow: 0 6px 14px -8px rgba(255,255,255,.4); }
.live-dot { width: 8px; height: 8px; border-radius: 50%; background: #10b981; display: inline-block; animation: pulse 2s infinite; }

.feature {
  display: flex; gap: 12px; align-items: flex-start; background: var(--card);
  border: 1px solid var(--line); border-top: 3px solid var(--brand);
  border-radius: 14px; padding: 15px 16px; margin-bottom: 10px;
  animation: fadeUp .5s ease both; transition: transform .22s ease, box-shadow .22s ease, border-color .22s ease;
}
.feature:hover { transform: translateY(-3px); border-color: #c7d2fe; box-shadow: 0 12px 26px -16px rgba(79,70,229,.45); }
.feature .f-ico { font-size: 1.8rem; line-height: 1.2; transition: transform .35s cubic-bezier(.34,1.56,.64,1); }
.feature:hover .f-ico { transform: scale(1.4) rotate(-10deg); }
.feature b { font-size: 1rem; }
.feature span { font-size: .88rem; }
.feature b { font-size: .93rem; }
.feature span { color: var(--muted); font-size: .84rem; }

/* ---------- financial table ---------- */
.table-wrap {
  max-height: 560px; overflow: auto; border-radius: 16px;
  border: 1px solid var(--line); background: var(--card);
  box-shadow: 0 1px 2px rgba(15,23,42,.04), 0 12px 30px -22px rgba(15,23,42,.35);
}
.fin-table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: .9rem; }
.fin-table thead th {
  position: sticky; top: 0; z-index: 1; text-align: left; padding: 12px 14px;
  background: linear-gradient(90deg, #eef2ff, #f5f3ff);
  font-size: .74rem; text-transform: uppercase; letter-spacing: .07em; color: #475569;
}
.fin-table tbody td { padding: 11px 14px; border-top: 1px solid var(--line); font-weight: 500; }
.fin-table tbody td.num { font-variant-numeric: tabular-nums; }
.fin-table tbody tr { animation: fadeUp .4s ease both; transition: background .18s ease; }
.fin-table tbody tr:hover { background: #f5f7ff; }
.fin-table td.cat { color: var(--muted); font-size: .8rem; font-weight: 600; }
.badge { display: inline-block; padding: 3px 11px; border-radius: 999px; font-size: .78rem; font-weight: 700; }
.badge.pos { color: #047857; background: #d1fae5; }
.badge.neg { color: #be123c; background: #ffe4e6; }
.badge.neu { color: #475569; background: #f1f5f9; }
.badge.na  { color: #94a3b8; background: #f8fafc; }
.badge.ar-pos { color: #047857; background: #d1fae5; }
.badge.ar-neg { color: #be123c; background: #ffe4e6; }
.badge.ar-neu { color: #475569; background: #f1f5f9; }
.badge.ar-na  { color: #94a3b8; background: #f8fafc; }
.trend-up { color: var(--pos); font-weight: 700; }
.trend-down { color: var(--neg); font-weight: 700; }
.trend-flat { color: #64748b; font-weight: 700; }
.change-pos { color: var(--pos); font-weight: 600; }
.change-neg { color: var(--neg); font-weight: 600; }

.sw-card.risks { border-top: 4px solid #d97706; }
.sw-card.recs { border-top: 4px solid var(--brand); }
.sw-card ol { padding-inline-start: 22px; margin: .4rem 0 0; }
.sw-card ol li { margin-bottom: 10px; line-height: 1.6; }
.rec-evidence {
  font-size: .8rem; color: #475569; margin-top: 4px;
  background: #f8fafc; border: 1px solid var(--line);
  border-inline-start: 3px solid #a5b4fc;
  border-radius: 8px; padding: 5px 10px; line-height: 1.55;
}

/* ---------- narrative report cards ---------- */
.report-card {
  background: var(--card); border: 1px solid var(--line); border-left: 5px solid var(--accent, var(--brand));
  border-radius: 14px; padding: 16px 20px; margin: 12px 0;
  box-shadow: 0 1px 2px rgba(15,23,42,.04), 0 10px 24px -20px rgba(15,23,42,.4);
  animation: fadeUp .5s ease both; transition: transform .22s ease, box-shadow .22s ease;
}
.report-card:hover { transform: translateX(5px); box-shadow: 0 14px 30px -18px rgba(79,70,229,.4); }
.rc-title { display: flex; align-items: center; gap: 9px; font-weight: 700; font-size: 1.02rem; margin-bottom: 6px; }
.rc-title .rc-ico { font-size: 1.15rem; }
.report-card p { margin-bottom: 0; color: #334155; line-height: 1.65; }

/* per-ratio one-line comments */
.ratio-line { padding: 9px 2px; border-bottom: 1px dashed var(--line); color: #334155; line-height: 1.7; }
.ratio-line:last-child { border-bottom: none; }
.ratio-name { font-weight: 700; color: var(--brand); margin-inline-end: 6px; }
.ratio-name::after { content: ":"; }

.sw-card { border-radius: 14px; border: 1px solid var(--line); background: var(--card); padding: 16px 18px; height: 100%;
  animation: fadeUp .5s ease both; box-shadow: 0 1px 2px rgba(15,23,42,.04); }
.sw-card.strengths { border-top: 4px solid var(--pos); }
.sw-card.weaknesses { border-top: 4px solid var(--neg); }
.sw-card ul { margin: .4rem 0 0 1.1rem; padding: 0; }
.sw-card li { margin-bottom: 7px; color: #334155; line-height: 1.55; }

/* ---------- plotly chart cards ---------- */
[data-testid="stPlotlyChart"] {
  background: var(--card); border: 1px solid var(--line); border-radius: 16px;
  padding: 10px 8px 4px; box-shadow: 0 1px 2px rgba(15,23,42,.04), 0 12px 28px -24px rgba(15,23,42,.4);
  transition: transform .25s ease, box-shadow .25s ease; animation: fadeUp .55s ease both;
}
[data-testid="stPlotlyChart"]:hover { transform: translateY(-3px); box-shadow: 0 16px 34px -18px rgba(79,70,229,.35); }

/* ---------- widgets ---------- */
div[data-testid="stButton"] > button {
  border-radius: 12px; font-weight: 600; border: 1px solid var(--line);
  transition: all .22s ease;
}
div[data-testid="stButton"] > button[kind="primary"] {
  background: linear-gradient(135deg, var(--brand), var(--brand2)); border: none;
  color: #fff; font-size: 1.05rem; padding: .65rem 1.4rem;
  box-shadow: 0 10px 22px -10px rgba(79,70,229,.65);
  animation: btnGlow 2.6s ease-in-out infinite;
}
@keyframes btnGlow {
  0%,100% { box-shadow: 0 10px 22px -10px rgba(79,70,229,.6); }
  50% { box-shadow: 0 16px 38px -8px rgba(124,58,237,.85); }
}
div[data-testid="stButton"] > button[kind="primary"]:hover {
  transform: translateY(-2px); filter: saturate(1.12);
  box-shadow: 0 14px 28px -10px rgba(79,70,229,.75);
}
div[data-testid="stButton"] > button[kind="secondary"]:hover { border-color: var(--brand); color: var(--brand); background: #eef2ff; }

[data-testid="stFileUploaderDropzone"] {
  border: 2px dashed #c7d2fe; border-radius: 16px; background: #f8faff;
  transition: all .25s ease; animation: dropBreath 3.2s ease-in-out infinite;
}
@keyframes dropBreath {
  0%,100% { border-color: #c7d2fe; }
  50% { border-color: #818cf8; box-shadow: 0 0 0 5px rgba(99,102,241,.1); }
}
[data-testid="stFileUploaderDropzone"]:hover {
  border-color: var(--brand); background: #eef2ff; box-shadow: 0 0 0 4px #e0e7ff;
}

[data-testid="stSidebar"] { background: #ffffff; border-right: 1px solid var(--line); }
[data-testid="stSidebar"] .stTextInput input { border-radius: 10px; }

[data-testid="stAlert"] { border-radius: 14px; border: 1px solid rgba(15,23,42,.06); animation: fadeUp .4s ease both; }
[data-testid="stExpander"] {
  border: 1px solid var(--line); border-radius: 14px; background: var(--card);
  box-shadow: 0 1px 2px rgba(15,23,42,.04); overflow: hidden;
}
[data-testid="stMetric"] { background: transparent; }

/* tabs as soft pills */
[data-baseweb="tab-list"] { gap: 8px; border-bottom: 1px solid var(--line); }
[data-baseweb="tab"] {
  border-radius: 12px 12px 0 0; padding: 10px 18px; font-weight: 600;
  color: var(--muted); transition: background .2s ease, color .2s ease;
}
[data-baseweb="tab"]:hover { background: #eef2ff; color: var(--brand); }
[data-baseweb="tab"][aria-selected="true"] { color: var(--brand); }
[data-baseweb="tab-highlight"] {
  background: linear-gradient(90deg, var(--brand), var(--brand2));
  height: 3px; border-radius: 3px 3px 0 0;
}

/* scrollbar */
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 8px; border: 2px solid transparent; background-clip: content-box; }
::-webkit-scrollbar-thumb:hover { background-color: #94a3b8; }
</style>
"""


def inject_theme() -> None:
    import streamlit as st

    st.markdown(THEME_CSS, unsafe_allow_html=True)
    # v6: نظام التصميم FinSight AI — لوحة فاتحة احترافية (#5145CD/#22D3EE)
    # بخطوط Cairo/Inter وأرقام جدولية. يحل محل طبقة polish اللامعة عمodel
    # توجيه إعادة التصميم: minimal FinTech، بلا hero ضخم ولا تدرجات زائدة.
    from src.dashboard.design_system import DESIGN_CSS

    st.markdown(DESIGN_CSS, unsafe_allow_html=True)



def section_title(text: str) -> None:
    import streamlit as st
    st.markdown(f'<div class="section-title" style="display:flex;align-items:center;gap:10px;'
                f'font-size:1.3rem;font-weight:800;">'
                f'<span style="width:6px;height:24px;border-radius:4px;display:inline-block;'
                f'background:linear-gradient(180deg,{BRAND},{BRAND_2});"></span>{ESC(text)}</div>',
                unsafe_allow_html=True)


def kpi_card(
    label: str,
    value: str,
    delta_text: str,
    arrow: str,       # "▲" numeric direction glyph
    mood: str,        # "up" (good/green) | "down" (bad/red) | "flat" | "na"
    accent: str,
    delay_ms: int = 0,
    tooltip: str = "",
    variant: str = "",
) -> str:
    tip = f' title="{ESC(tooltip)}"' if tooltip else ""
    extra = f" {variant}" if variant else ""
    delta_html = (
        f'<div class="kpi-delta {mood}">{arrow} {ESC(delta_text)}</div>' if delta_text else ""
    )
    return (
        f'<div class="kpi-card{extra}" style="--accent:{accent}; animation-delay:{delay_ms}ms"{tip}>'
        f'<div class="kpi-label">{ESC(label)}</div>'
        f'<div class="kpi-value">{ESC(value)}</div>'
        f'{delta_html}'
        '</div>'
    )


def info_chip(label: str, value: str, accent: str = BRAND, delay_ms: int = 0) -> str:
    """Compact card for static facts (company, period, years)."""
    return kpi_card(label, value, "", "◆", "flat", accent, delay_ms, variant="info")


def hero(title_html: str, subtitle: str, chips_html: list[str]) -> str:
    """Landing hero. `chips_html` items are trusted HTML (caller-controlled)."""
    chips = "".join(f'<span class="chip">{c}</span>' for c in chips_html)
    return (
        '<div class="hero">'
        '<span class="hero-float hf1">📈</span>'
        '<span class="hero-float hf2">🧮</span>'
        '<span class="hero-float hf3">📄</span>'
        f'<h1>{title_html}</h1>'
        f'<p class="sub">{ESC(subtitle)}</p>'
        f'<div style="margin-top:14px;">{chips}</div>'
        '</div>'
    )


def feature(icon: str, title: str, body: str, delay_ms: int = 0) -> str:
    return (
        f'<div class="feature" style="animation-delay:{delay_ms}ms">'
        f'<div class="f-ico">{icon}</div>'
        f'<div><b>{ESC(title)}</b><br><span>{ESC(body)}</span></div>'
        '</div>'
    )


def report_card(title: str, icon: str, body: str, accent: str = BRAND, delay_ms: int = 0) -> str:
    return (
        f'<div class="report-card" style="--accent:{accent}; animation-delay:{delay_ms}ms">'
        f'<div class="rc-title"><span class="rc-ico">{icon}</span>{ESC(title)}</div>'
        f'<p dir="auto">{ESC(body)}</p>'
        '</div>'
    )


def sw_card(kind: str, title: str, icon: str, items: list[str], ordered: bool = False) -> str:
    """Colored-top list card (strengths / weaknesses / risks / recommendations)."""
    if ordered:
        lis = "".join(f"<li>{ESC(i)}</li>" for i in items) or '<li><i>None provided.</i></li>'
        body = f"<ol>{lis}</ol>"
    else:
        lis = "".join(f"<li>{ESC(i)}</li>" for i in items) or '<li><i>None identified.</i></li>'
        body = f"<ul>{lis}</ul>"
    return (
        f'<div class="sw-card {kind}">'
        f'<div class="rc-title"><span class="rc-ico">{icon}</span>{ESC(title)}</div>'
        f'{body}'
        '</div>'
    )


BADGE_AR = {"Positive": "إيجابي", "Negative": "سلبي", "Neutral": "محايد", "N/A": "غير متاح"}


def badge(status: str) -> str:
    cls = {"Positive": "pos", "Negative": "neg", "Neutral": "neu"}.get(status, "na")
    return f'<span class="badge {cls}">{ESC(BADGE_AR.get(status, status))}</span>'


def fin_table(headers: list[str], rows_html: list[str]) -> str:
    """Financial table with sticky header and hover rows.

    `rows_html` items are complete `<tr>...</tr>` strings built by the caller.
    .fin-table td, .fin-table th { unicode-bidi: plaintext; }
"""
    th = "".join(f"<th>{ESC(h)}</th>" for h in headers)
    return (
        '<div class="table-wrap"><table class="fin-table">'
        f'<thead><tr>{th}</tr></thead><tbody>{"".join(rows_html)}</tbody>'
        '</table></div>'
    )
