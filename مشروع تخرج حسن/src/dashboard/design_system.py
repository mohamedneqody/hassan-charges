# -*- coding: utf-8 -*-
"""FinSight AI — نظام التصميم v7: SaaS داكن محيطي بأسطح مضيئة.

التوجيه المعتمد بعد رفض v6:
- خلفية داكنة محيطية (#0B1020) بتدرجات بنفسجية/سماوية ضبابية متحركة
  + شبكة هندسية دقيقة — عبر pseudo-elements على .stApp.
- أسطح المحتوى بيضاء مضيئة قابلة للقراءة فوق الخلفية (فصل واضح).
- عرض كامل (wide) بلا عمود ضيق — max-width واسع للشاشات الكبيرة.
- حركات CSS حقيقية: دخول متدرج للأقسام، إقلاع البطاقات، لمعان الأزرار،
  نمو أعمدة المعاينة — مع احترام prefers-reduced-motion.
- اللوحة: #5145CD/#312E81/#22D3EE على داكن، أسطح #FFFFFF، نص #172033.
"""
from __future__ import annotations

PRIMARY = "#5145CD"
DEEP = "#312E81"
SECONDARY = "#22D3EE"
BG = "#0B1020"
BG2 = "#111827"
SURFACE = "#FFFFFF"
INK = "#172033"
MUTED = "#64748B"
LINE = "#E2E8F0"
SUCCESS = "#16A34A"
WARNING = "#D97706"
DANGER = "#DC2626"

DESIGN_CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&family=IBM+Plex+Sans+Arabic:wght@400;500;600;700&family=Inter:wght@400;600;700;800;900&display=swap');

:root {
  --fs-primary: #5145CD;
  --fs-deep: #312E81;
  --fs-secondary: #22D3EE;
  --fs-bg: #0B1020;
  --fs-bg2: #111827;
  --fs-surface: #FFFFFF;
  --fs-ink: #172033;
  --fs-muted: #64748B;
  --fs-line: #E2E8F0;
  --fs-success: #16A34A;
  --fs-warning: #D97706;
  --fs-danger: #DC2626;
  --fs-radius: 14px;
  --fs-radius-lg: 20px;
}

/* == الخلفية المحيطية المتحركة == */
html, body, .stApp {
  direction: rtl;
  font-family: 'IBM Plex Sans Arabic', 'Cairo', 'Inter', 'Segoe UI',
               Tahoma, sans-serif;
}
.stApp {
  background: var(--fs-bg) !important;
  color: var(--fs-ink);
  text-align: right;
}
.stApp::before {
  content: ""; position: fixed; inset: -20%; z-index: 0; pointer-events: none;
  background:
    radial-gradient(620px 420px at 82% 8%, rgba(81,69,205,.34), transparent 65%),
    radial-gradient(560px 400px at 12% 22%, rgba(34,211,238,.13), transparent 62%),
    radial-gradient(700px 520px at 55% 105%, rgba(124,58,237,.20), transparent 65%),
    radial-gradient(420px 320px at 92% 78%, rgba(34,211,238,.10), transparent 60%);
  animation: fsAmbient 26s ease-in-out infinite alternate;
}
.stApp::after {
  content: ""; position: fixed; inset: 0; z-index: 0; pointer-events: none;
  background-image:
    linear-gradient(rgba(148,163,184,.055) 1px, transparent 1px),
    linear-gradient(90deg, rgba(148,163,184,.055) 1px, transparent 1px);
  background-size: 44px 44px;
  mask-image: radial-gradient(ellipse 90% 70% at 50% 0%, #000 30%, transparent 78%);
  -webkit-mask-image: radial-gradient(ellipse 90% 70% at 50% 0%, #000 30%, transparent 78%);
}
@keyframes fsAmbient {
  0%   { transform: translate3d(0, 0, 0) scale(1); }
  50%  { transform: translate3d(-2.5%, 2%, 0) scale(1.06); }
  100% { transform: translate3d(2%, -1.5%, 0) scale(1.02); }
}
.stApp > header, [data-testid="stHeader"] { background: transparent !important; }
[data-testid="stAppViewContainer"] { position: relative; z-index: 1; }
[data-testid="stSidebar"] { position: relative; z-index: 2; }

/* == الحاويات: عرض كامل == */
.block-container {
  max-width: 1560px !important; padding: 1.6rem 2.4rem 4rem !important;
}
section[data-testid="stSidebar"] { width: 260px !important; }

/* == حركات الدخول == */
@keyframes fsUp { from { opacity: 0; transform: translateY(22px); }
                  to { opacity: 1; transform: none; } }
@keyframes fsPop { from { opacity: 0; transform: scale(.94) translateY(14px); }
                   to { opacity: 1; transform: none; } }
@keyframes fsGrow { from { transform: scaleY(.06); } to { transform: scaleY(1); } }
@keyframes fsShine { 0% { transform: translateX(-130%) skewX(-18deg); }
                     100% { transform: translateX(230%) skewX(-18deg); } }

/* == الهيدر: زجاج داكن == */
.fs-header {
  display: flex; align-items: center; justify-content: space-between;
  gap: 14px; padding: 13px 22px; margin-bottom: 20px;
  background: rgba(17,24,39,.72);
  border: 1px solid rgba(129,140,248,.22);
  border-radius: var(--fs-radius-lg);
  backdrop-filter: blur(14px);
  box-shadow: 0 12px 40px -18px rgba(0,0,0,.8);
  animation: fsUp .5s cubic-bezier(.21,.98,.6,.99) both;
}
.fs-brand { display: flex; align-items: center; gap: 12px; }
.fs-logo {
  width: 40px; height: 40px; border-radius: 11px; flex: 0 0 auto;
  background: linear-gradient(135deg, var(--fs-primary), #7C6FE8 60%, var(--fs-secondary));
  display: grid; place-items: center; color: #fff;
  font-weight: 800; font-size: 1.05rem; font-family: 'Inter', sans-serif;
  box-shadow: 0 8px 22px -8px rgba(81,69,205,.8);
  transition: transform .25s ease, box-shadow .25s ease;
}
.fs-brand:hover .fs-logo { transform: scale(1.08) rotate(-3deg);
  box-shadow: 0 10px 30px -6px rgba(34,211,238,.5); }
.fs-brand-name {
  font-size: 1.15rem; font-weight: 800; color: #F1F5F9;
  font-family: 'Inter', 'IBM Plex Sans Arabic', sans-serif; letter-spacing: -.02em;
}
.fs-brand-sub {
  font-size: .7rem; font-weight: 700; color: #818CF8;
  text-transform: uppercase; letter-spacing: .18em;
}
.fs-header-meta { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.fs-pill {
  display: inline-flex; align-items: center; gap: 6px;
  border: 1px solid rgba(129,140,248,.3); border-radius: 999px;
  padding: 4px 13px; background: rgba(17,24,39,.6); color: #C7D2FE;
  font-size: .74rem; font-weight: 600;
}
.fs-pill .fs-dot { width: 7px; height: 7px; border-radius: 50%; }

/* == الـHero: عمودان == */
.fs-hero {
  display: grid; grid-template-columns: 1.05fr .95fr; gap: 26px;
  align-items: stretch; margin-bottom: 26px;
}
.fs-hero-copy {
  padding: 34px 34px 30px; border-radius: var(--fs-radius-lg);
  background: linear-gradient(160deg, rgba(49,46,129,.55), rgba(17,24,39,.75));
  border: 1px solid rgba(129,140,248,.28);
  backdrop-filter: blur(10px);
  box-shadow: 0 24px 60px -28px rgba(0,0,0,.85);
  animation: fsUp .6s cubic-bezier(.21,.98,.6,.99) both;
  display: flex; flex-direction: column; justify-content: center;
}
.fs-hero-eyebrow {
  display: inline-flex; align-items: center; gap: 8px; width: fit-content;
  font-size: .72rem; font-weight: 800; letter-spacing: .16em;
  color: var(--fs-secondary); text-transform: uppercase;
  margin-bottom: 14px; animation: fsUp .6s .1s both;
}
.fs-hero-title {
  font-size: 2.5rem; font-weight: 900; line-height: 1.25;
  color: #F8FAFC !important;   /* h1 الافتراضي داكن — العنوان فاتح إجباريًا */
  margin: 0 0 14px; letter-spacing: -.01em;
  animation: fsUp .65s .16s cubic-bezier(.21,.98,.6,.99) both;
}
.fs-hero-title em {
  font-style: normal;
  background: linear-gradient(90deg, #A5B4FC, var(--fs-secondary));
  -webkit-background-clip: text; background-clip: text;
  -webkit-text-fill-color: transparent;
}
.fs-hero-desc {
  color: #B6C2D9 !important; font-size: 1.02rem; line-height: 2;
  margin-bottom: 22px; animation: fsUp .7s .22s both;
}
.fs-hero-actions { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }

/* == معاينة المنتج (بطاقة فاتحة ببيانات توضيحية معلنة) == */
.fs-preview {
  position: relative; overflow: hidden;
  background: var(--fs-surface); border-radius: var(--fs-radius-lg);
  border: 1px solid rgba(129,140,248,.35);
  box-shadow: 0 30px 70px -30px rgba(0,0,0,.9);
  padding: 20px 22px 16px; display: flex; flex-direction: column;
  animation: fsPop .7s .25s cubic-bezier(.21,.98,.6,.99) both;
}
.fs-preview-tag {
  position: absolute; top: 12px; inset-inline-start: 14px;
  font-size: .66rem; font-weight: 700; letter-spacing: .08em;
  color: var(--fs-muted); background: #F1F5F9;
  border: 1px solid var(--fs-line); border-radius: 999px; padding: 3px 10px;
}
.fs-preview-title {
  font-size: .82rem; font-weight: 700; color: var(--fs-ink); margin: 22px 0 4px;
}
.fs-preview-sub { font-size: .7rem; color: var(--fs-muted); }
.fs-preview-kpis { display: flex; gap: 8px; margin: 12px 0 4px; }
.fs-mini-kpi {
  flex: 1; background: #F8FAFC; border: 1px solid var(--fs-line);
  border-radius: 10px; padding: 8px 10px;
}
.fs-mini-kpi b { display: block; font-size: .95rem; color: var(--fs-ink);
  font-family: 'Inter', sans-serif; font-variant-numeric: tabular-nums; }
.fs-mini-kpi span { font-size: .62rem; color: var(--fs-muted); font-weight: 600; }
.fs-mini-kpi.up b { color: var(--fs-success); }
.fs-preview-chart {
  flex: 1; display: flex; align-items: flex-end; gap: 9px;
  height: 150px; padding: 12px 4px 0;
  border-top: 1px dashed var(--fs-line); margin-top: 10px;
}
.fs-bar {
  flex: 1; border-radius: 7px 7px 2px 2px; transform-origin: bottom;
  background: linear-gradient(180deg, #818CF8, var(--fs-primary));
  animation: fsGrow .8s cubic-bezier(.21,.98,.6,.99) both;
  min-height: 12%;
}
.fs-bar.alt { background: linear-gradient(180deg, #67E8F9, #0891B2); }
.fs-bar:nth-child(1) { height: 42%; animation-delay: .45s; }
.fs-bar:nth-child(2) { height: 66%; animation-delay: .55s; }
.fs-bar:nth-child(3) { height: 34%; animation-delay: .65s; }
.fs-bar:nth-child(4) { height: 82%; animation-delay: .75s; }
.fs-bar:nth-child(5) { height: 58%; animation-delay: .85s; }
.fs-bar:nth-child(6) { height: 96%; animation-delay: .95s; }
.fs-preview-line {
  margin-top: 10px; font-size: .64rem; color: var(--fs-muted); text-align: center;
}

/* == مساحة العمل == */
.fs-workspace {
  background: var(--fs-surface); border-radius: var(--fs-radius-lg);
  border: 1px solid rgba(148,163,184,.18);
  box-shadow: 0 40px 90px -40px rgba(0,0,0,.95);
  padding: 26px 30px; animation: fsUp .6s .3s both;
}
.fs-workspace .fs-card-title {
  font-size: .78rem; font-weight: 800; color: var(--fs-primary);
  text-transform: uppercase; letter-spacing: .1em; margin-bottom: 12px;
}
.fs-workspace input, .fs-workspace textarea,
.fs-workspace [data-baseweb="select"] > div {
  border-radius: 10px !important; border: 1px solid var(--fs-line) !important;
}
.fs-workspace input:focus, .fs-workspace textarea:focus {
  border-color: var(--fs-primary) !important;
  box-shadow: 0 0 0 3px rgba(81,69,205,.12) !important;
}
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] {
  border: 1.5px dashed #C7D2FE !important; border-radius: var(--fs-radius) !important;
  background: #FAFAFF !important; transition: all .22s ease !important;
}
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"]:hover {
  border-color: var(--fs-primary) !important; background: #F5F4FF !important;
  box-shadow: 0 10px 28px -12px rgba(81,69,205,.35) !important;
}
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] button {
  background: var(--fs-primary) !important; color: #fff !important;
  border: none !important; border-radius: 9px !important; font-weight: 700 !important;
}
label[data-rac] {
  border: 1px solid var(--fs-line) !important; border-radius: 10px !important;
  padding: 10px 14px !important; margin: 4px 0 !important; width: 100% !important;
  background: var(--fs-surface) !important; cursor: pointer !important;
  transition: all .18s ease !important; display: flex !important;
}
label[data-rac]:hover { border-color: var(--fs-primary) !important; }
label[data-rac][data-selected="true"] {
  border-color: var(--fs-primary) !important; background: #F5F4FF !important;
  box-shadow: 0 0 0 1px var(--fs-primary) !important;
}
label[data-rac] > span:first-child { position: absolute; opacity: 0; }

/* == الأزرار == */
.stApp .stButton > button {
  border-radius: 11px !important; font-weight: 700 !important;
  border: 1px solid rgba(148,163,184,.3) !important;
  background: rgba(255,255,255,.06) !important; color: #E2E8F0 !important;
  transition: all .22s cubic-bezier(.21,.98,.6,.99) !important;
}
.stApp .stButton > button:hover {
  border-color: var(--fs-secondary) !important; color: var(--fs-secondary) !important;
  transform: translateY(-2px) !important;
  box-shadow: 0 10px 26px -10px rgba(34,211,238,.4) !important;
}
.stApp .stButton > button[kind="primary"],
.stApp .stButton > button[data-testid="stBaseButton-primary"] {
  background: linear-gradient(110deg, var(--fs-primary), #6D5FE0 55%, #4338B8) !important;
  background-size: 160% 100% !important;
  color: #fff !important; border: none !important;
  padding: 12px 28px !important; font-size: 1rem !important;
  box-shadow: 0 14px 34px -12px rgba(81,69,205,.8) !important;
  position: relative; overflow: hidden;
}
.stApp .stButton > button[kind="primary"]::after,
.stApp .stButton > button[data-testid="stBaseButton-primary"]::after {
  content: ""; position: absolute; top: 0; bottom: 0; width: 40%;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,.25), transparent);
  animation: fsShine 3.2s ease-in-out infinite;
}
.stApp .stButton > button[kind="primary"]:hover,
.stApp .stButton > button[data-testid="stBaseButton-primary"]:hover {
  background-position: 100% 0 !important;
  transform: translateY(-2px) !important;
  box-shadow: 0 18px 44px -12px rgba(81,69,205,.9) !important;
}
.stApp .stButton > button[kind="primary"]:active { transform: translateY(1px) scale(.99) !important; }
.stApp .stButton > button[kind="primary"]:disabled {
  background: #334155 !important; box-shadow: none !important; transform: none !important;
}

/* == بطاقات المميزات == */
.fs-feature {
  position: relative; overflow: hidden; height: 100%;
  background: var(--fs-surface); border: 1px solid rgba(148,163,184,.22);
  border-radius: var(--fs-radius); padding: 18px 20px;
  box-shadow: 0 20px 50px -30px rgba(0,0,0,.9);
  animation: fsUp .6s both; transition: all .25s ease;
}
.fs-feature::before {
  content: ""; position: absolute; inset: 0 0 auto 0; height: 3px;
  background: linear-gradient(90deg, var(--fs-primary), var(--fs-secondary));
  opacity: 0; transition: opacity .25s ease;
}
.fs-feature::after {
  content: ""; position: absolute; top: -60%; bottom: -60%;
  inset-inline-start: -30%; width: 34%;
  background: linear-gradient(90deg, transparent, rgba(81,69,205,.07), transparent);
  transform: translateX(-130%) skewX(-18deg); transition: transform .7s ease;
}
.fs-feature:hover::before { opacity: 1; }
.fs-feature:hover::after { transform: translateX(320%) skewX(-18deg); }
.fs-feature:hover {
  transform: translateY(-7px) !important;
  border-color: rgba(129,140,248,.5) !important;
  box-shadow: 0 30px 60px -24px rgba(81,69,205,.55) !important;
}
.fs-feature-ico { font-size: 1.5rem; margin-bottom: 8px; display: inline-block;
  transition: transform .3s ease; }
.fs-feature:hover .fs-feature-ico { transform: scale(1.15) rotate(-5deg); }
.fs-feature b { color: var(--fs-ink); font-size: .98rem; }
.fs-feature span { color: var(--fs-muted); font-size: .84rem; line-height: 1.7; }

/* == بطاقات KPI == */
.fs-kpi {
  background: var(--fs-surface); border: 1px solid rgba(148,163,184,.22);
  border-radius: var(--fs-radius-lg); padding: 16px 18px; height: 100%;
  box-shadow: 0 24px 60px -34px rgba(0,0,0,.9);
  animation: fsPop .55s cubic-bezier(.21,.98,.6,.99) both;
  transition: transform .22s ease, box-shadow .22s ease, border-color .22s ease;
}
.fs-kpi:hover { transform: translateY(-4px);
  border-color: rgba(129,140,248,.55);
  box-shadow: 0 30px 66px -30px rgba(81,69,205,.5); }
.fs-kpi .fs-kpi-label { font-size: .74rem; font-weight: 700; color: var(--fs-muted);
  text-transform: uppercase; letter-spacing: .08em; }
.fs-kpi .fs-kpi-value {
  font-family: 'Inter', 'IBM Plex Sans Arabic', sans-serif;
  font-variant-numeric: tabular-nums; direction: ltr; text-align: right;
  font-size: 1.72rem; font-weight: 800; color: var(--fs-ink); margin-top: 6px;
}
.fs-kpi .fs-kpi-delta { display: inline-flex; margin-top: 8px;
  font-size: .76rem; font-weight: 700; padding: 3px 10px; border-radius: 999px; }
.fs-kpi .up { color: var(--fs-success); background: #F0FDF4; }
.fs-kpi .down { color: var(--fs-danger); background: #FEF2F2; }
.fs-kpi .flat { color: var(--fs-muted); background: #F1F5F9; }
.fs-gate { display: inline-flex; align-items: center; gap: 6px;
  font-size: .72rem; font-weight: 700; padding: 3px 10px; border-radius: 999px; }
.fs-gate.ok { color: var(--fs-success); background: #F0FDF4; border: 1px solid #BBF7D0; }
.fs-gate.pend { color: var(--fs-warning); background: #FFFBEB; border: 1px solid #FDE68A; }
.fs-gate.miss { color: var(--fs-muted); background: #F1F5F9; border: 1px solid var(--fs-line); }
.fs-gate.bad { color: var(--fs-danger); background: #FEF2F2; border: 1px solid #FECACA; }

/* == الشريط الجانبي == */
section[data-testid="stSidebar"] {
  background: linear-gradient(180deg, rgba(17,24,39,.92), rgba(11,16,32,.95)) !important;
  border-inline-start: 1px solid rgba(129,140,248,.2) !important;
  backdrop-filter: blur(12px);
}
section[data-testid="stSidebar"] * { color: #CBD5E1 !important; }
section[data-testid="stSidebar"] .fs-brand-name { color: #F1F5F9 !important; }
section[data-testid="stSidebar"] hr { border-color: rgba(129,140,248,.18) !important; }
section[data-testid="stSidebar"] .stTextInput input {
  background: rgba(255,255,255,.06) !important;
  border: 1px solid rgba(129,140,248,.25) !important; color: #E2E8F0 !important;
}
section[data-testid="stSidebar"] .stButton > button {
  background: rgba(255,255,255,.05) !important;
  border: 1px solid rgba(129,140,248,.25) !important; color: #CBD5E1 !important;
  transition: all .2s ease !important;
}
section[data-testid="stSidebar"] .stButton > button:hover {
  border-color: var(--fs-secondary) !important; color: var(--fs-secondary) !important;
  transform: translateY(-1px) !important;
}
section[data-testid="stSidebar"] .stButton > button[kind="primary"] {
  background: linear-gradient(90deg, var(--fs-primary), #4338B8) !important;
  color: #fff !important; border: none !important;
}

/* == التبويبات == */
.stTabs [data-baseweb="tab-list"] { gap: 6px; }
.stTabs [data-baseweb="tab"] {
  border-radius: 999px !important; padding: 6px 16px !important;
  color: #94A3B8 !important; transition: all .2s ease !important;
}
.stTabs [data-baseweb="tab"] p { color: inherit !important; }
.stTabs [data-baseweb="tab"]:hover { background: rgba(129,140,248,.12) !important;
  color: #E2E8F0 !important; }
.stTabs [aria-selected="true"] {
  background: linear-gradient(90deg, var(--fs-primary), #4338B8) !important;
}
.stTabs [aria-selected="true"] p { color: #fff !important; font-weight: 700 !important; }
.stTabs [data-baseweb="tab-highlight"] { display: none !important; }

/* == الحالات == */
.fs-state { border-radius: var(--fs-radius-lg); padding: 22px 24px;
  text-align: center; border: 1px solid rgba(148,163,184,.25);
  background: rgba(255,255,255,.04); }
.fs-state .fs-state-ico { font-size: 1.6rem; margin-bottom: 8px; }
.fs-state .fs-state-title { font-weight: 800; color: #F1F5F9; }
.fs-state .fs-state-body { color: #94A3B8; font-size: .88rem; margin-top: 6px;
  line-height: 1.8; }
.fs-state.empty { border-style: dashed; }
.fs-state.error { border-color: rgba(220,38,38,.5); background: rgba(220,38,38,.08); }
.fs-state.success { border-color: rgba(22,163,74,.5); background: rgba(22,163,74,.08); }

/* == الفوتر == */
.fs-footer {
  margin-top: 30px; padding: 18px 24px; text-align: center;
  border-top: 1px solid rgba(129,140,248,.18);
  color: #64748B; font-size: .78rem;
}
.fs-footer b { color: #94A3B8; }

/* == الجداول == */
.fin-table td, .fin-table th, .stApp [data-testid="stDataFrame"] {
  unicode-bidi: plaintext;
}
.stApp [data-testid="stDataFrame"] {
  border: 1px solid rgba(148,163,184,.25) !important;
  border-radius: var(--fs-radius) !important;
}

/* == نص المحتوى على الخلفية الداكنة: فاتح مقروء (الاستثناء: الأسطح
   البيضاء fs-kpi/fs-preview/fs-workspace تحمل ألوانها الداكنة الخاصة) == */
.block-container { color: #B6C2D9; }
.block-container h1, .block-container h2, .block-container h3,
.block-container h4 { color: #F1F5F9 !important; }
.block-container p, .block-container li { color: #B6C2D9; }
.block-container strong, .block-container b { color: #F1F5F9; }
.block-container [data-testid="stMetric"] label,
.block-container [data-testid="stMetric"] div,
.block-container [data-testid="stMetricValue"] {
  color: #E2E8F0 !important;
}
.block-container .stMarkdown strong { color: #F1F5F9; }

/* == عناصر عامة == */
.stApp input, .stApp textarea,
.stApp [data-baseweb="select"] > div {
  border-radius: 10px !important; border: 1px solid rgba(148,163,184,.3) !important;
  background: rgba(255,255,255,.95) !important; color: var(--fs-ink) !important;
}
.stApp input:focus, .stApp textarea:focus {
  border-color: var(--fs-primary) !important;
  box-shadow: 0 0 0 3px rgba(81,69,205,.18) !important;
}
.stApp [data-testid="stExpander"] {
  border: 1px solid rgba(148,163,184,.22) !important;
  border-radius: var(--fs-radius) !important;
  background: rgba(255,255,255,.04) !important;
}
.stApp [data-testid="stExpander"] * { color: #CBD5E1; }
.stApp [data-testid="stExpander"] summary { color: #E2E8F0 !important; }
.or-line { text-align: center; color: #64748B; }
::selection { background: rgba(81,69,205,.4); color: #fff; }
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-track { background: rgba(255,255,255,.03); }
::-webkit-scrollbar-thumb { background: rgba(129,140,248,.4); border-radius: 999px; }
::-webkit-scrollbar-thumb:hover { background: rgba(129,140,248,.65); }

.sec-label {
  color: #A5B4FC !important; font-weight: 800 !important;
}
.sec-label::after { background: var(--fs-secondary) !important; }
.step-card {
  background: var(--fs-surface) !important;
  border: 1px solid rgba(148,163,184,.22) !important;
}
.step-card span { color: var(--fs-muted) !important; }
.step-card b { color: var(--fs-ink) !important; }
.step-num { background: var(--fs-primary) !important; color: #fff !important; }

/* == استجابة العرض == */
@media (max-width: 1100px) {
  .fs-hero { grid-template-columns: 1fr; }
  .block-container { max-width: 100% !important; padding: 1.2rem 1.2rem 3rem !important; }
}
@media (max-width: 640px) {
  .fs-hero-title { font-size: 1.7rem; }
  .fs-hero-copy { padding: 22px 20px; }
  .fs-preview-chart { min-height: 90px; }
  .fs-workspace { padding: 16px 14px; }
  section[data-testid="stSidebar"] { width: 220px !important; }
}

/* == prefers-reduced-motion == */
@media (prefers-reduced-motion: reduce) {
  .hero, .kpi-card, .feature, .step-card, .fs-feature, .fs-kpi,
  .fs-hero-copy, .fs-preview, .fs-workspace, .fs-bar, .fs-header,
  .stApp::before, .stApp::after {
    animation: none !important; transition: none !important;
  }
  .stApp .stButton > button[kind="primary"]::after { animation: none !important; }
}
</style>"""
