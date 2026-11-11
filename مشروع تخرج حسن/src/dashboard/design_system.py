# -*- coding: utf-8 -*-
"""نظام التصميم — FinSight AI (v6): هوية FinTech SaaS فاتحة احترافية.

اللوحة الموحدة من التفويض: Primary #5145CD · Secondary #22D3EE · خلفية
#F8FAFC · سطح أبيض · نص #172033/#64748B · حدود #E2E8F0. خطوط Cairo
(عربي) وInter (إنجليزي) مع أرقام جدولية للقيم المالية. هذا التصميم
يحل محل الطبقة اللامعة (polish_css) عمodel التوجيه: minimal، بلا hero
ضخم، بلا تدرجات زائدة، بلا إيموجي زخرفي.
"""

# ── اللوحة (مصدر الحقيقة الوحيد للألوان) ──
PRIMARY = "#5145CD"
PRIMARY_HOVER = "#4338B8"
SECONDARY = "#22D3EE"
BG = "#F8FAFC"
SURFACE = "#FFFFFF"
INK = "#172033"
MUTED = "#64748B"
LINE = "#E2E8F0"
SUCCESS = "#16A34A"
WARNING = "#D97706"
DANGER = "#DC2626"

DESIGN_CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&family=IBM+Plex+Sans+Arabic:wght@400;600;700&family=Inter:wght@400;600;700;800&display=swap');

:root {
  --fs-primary: #5145CD;
  --fs-primary-hover: #4338B8;
  --fs-secondary: #22D3EE;
  --fs-bg: #F8FAFC;
  --fs-surface: #FFFFFF;
  --fs-ink: #172033;
  --fs-muted: #64748B;
  --fs-line: #E2E8F0;
  --fs-success: #16A34A;
  --fs-warning: #D97706;
  --fs-danger: #DC2626;
  --fs-radius: 12px;
  --fs-radius-lg: 16px;
  --fs-space: 8px;
}

/* ── الأساس: خطوط + اتجاه + خلفية هادئة ── */
html, body, .stApp {
  direction: rtl;
  font-family: 'IBM Plex Sans Arabic', 'Cairo', 'Inter', 'Segoe UI',
               Tahoma, sans-serif;
}
.stApp {
  background: var(--fs-bg);
  color: var(--fs-ink);
  text-align: right;
}
h1, h2, h3, h4 { color: var(--fs-ink); font-weight: 700; letter-spacing: -.01em; }
p, li, span { color: var(--fs-ink); }

/* الأرقام المالية: جدولية بارزة */
.fs-num {
  font-family: 'Inter', 'IBM Plex Sans Arabic', sans-serif;
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  letter-spacing: -.01em;
}

/* ── الهيدر المضغوط (بلا hero ضخم) ── */
.fs-header {
  display: flex; align-items: center; justify-content: space-between;
  gap: 14px; padding: 14px 20px; margin-bottom: 18px;
  background: var(--fs-surface);
  border: 1px solid var(--fs-line); border-radius: var(--fs-radius-lg);
  box-shadow: 0 1px 2px rgba(23,32,51,.05);
}
.fs-brand { display: flex; align-items: center; gap: 12px; }
.fs-logo {
  width: 38px; height: 38px; border-radius: 10px; flex: 0 0 auto;
  background: linear-gradient(135deg, var(--fs-primary), #7C6FE8);
  display: grid; place-items: center; color: #fff;
  font-weight: 800; font-size: 1.05rem; font-family: 'Inter', sans-serif;
}
.fs-brand-name {
  font-size: 1.12rem; font-weight: 800; color: var(--fs-ink);
  font-family: 'Inter', 'IBM Plex Sans Arabic', sans-serif; letter-spacing: -.02em;
}
.fs-brand-sub {
  font-size: .72rem; font-weight: 600; color: var(--fs-muted);
  text-transform: uppercase; letter-spacing: .14em;
}
.fs-header-meta {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  font-size: .78rem; color: var(--fs-muted); font-weight: 600;
}
.fs-pill {
  display: inline-flex; align-items: center; gap: 6px;
  border: 1px solid var(--fs-line); border-radius: 999px;
  padding: 4px 12px; background: var(--fs-surface); color: var(--fs-muted);
  font-size: .74rem; font-weight: 600;
}
.fs-pill .fs-dot { width: 7px; height: 7px; border-radius: 50%; }

/* ── البطاقات الموحدة ── */
.fs-card {
  background: var(--fs-surface); border: 1px solid var(--fs-line);
  border-radius: var(--fs-radius-lg); padding: 18px 20px;
  box-shadow: 0 1px 2px rgba(23,32,51,.04);
}
.fs-card-title {
  font-size: .78rem; font-weight: 700; color: var(--fs-muted);
  text-transform: uppercase; letter-spacing: .1em; margin-bottom: 10px;
}

/* ── KPI ── */
.fs-kpi {
  background: var(--fs-surface); border: 1px solid var(--fs-line);
  border-radius: var(--fs-radius-lg); padding: 16px 18px; height: 100%;
  box-shadow: 0 1px 2px rgba(23,32,51,.04);
  transition: border-color .2s ease, box-shadow .2s ease;
}
.fs-kpi:hover { border-color: color-mix(in srgb, var(--fs-primary) 40%, var(--fs-line));
               box-shadow: 0 8px 24px -12px rgba(81,69,205,.35); }
.fs-kpi .fs-kpi-label {
  font-size: .74rem; font-weight: 700; color: var(--fs-muted);
  text-transform: uppercase; letter-spacing: .08em;
}
.fs-kpi .fs-kpi-value {
  font-family: 'Inter', 'IBM Plex Sans Arabic', sans-serif;
  font-variant-numeric: tabular-nums;
  font-size: 1.7rem; font-weight: 800; color: var(--fs-ink);
  margin-top: 6px; letter-spacing: -.02em; direction: ltr; text-align: right;
}
.fs-kpi .fs-kpi-delta {
  display: inline-flex; align-items: center; gap: 5px; margin-top: 8px;
  font-size: .76rem; font-weight: 700; padding: 3px 10px; border-radius: 999px;
}
.fs-kpi .up { color: var(--fs-success); background: #F0FDF4; }
.fs-kpi .down { color: var(--fs-danger); background: #FEF2F2; }
.fs-kpi .flat { color: var(--fs-muted); background: #F1F5F9; }

/* ── شارات قرار البوابة ── */
.fs-gate {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: .72rem; font-weight: 700; padding: 3px 10px; border-radius: 999px;
}
.fs-gate.ok { color: var(--fs-success); background: #F0FDF4; border: 1px solid #BBF7D0; }
.fs-gate.pend { color: var(--fs-warning); background: #FFFBEB; border: 1px solid #FDE68A; }
.fs-gate.miss { color: var(--fs-muted); background: #F1F5F9; border: 1px solid var(--fs-line); }
.fs-gate.bad { color: var(--fs-danger); background: #FEF2F2; border: 1px solid #FECACA; }

/* ── أزرار ── */
.stApp .stButton > button {
  border-radius: 10px !important; font-weight: 700 !important;
  border: 1px solid var(--fs-line) !important; background: var(--fs-surface) !important;
  color: var(--fs-ink) !important;
  transition: all .18s ease !important;
}
.stApp .stButton > button:hover {
  border-color: var(--fs-primary) !important; color: var(--fs-primary) !important;
  box-shadow: 0 4px 14px -6px rgba(81,69,205,.35) !important;
}
.stApp .stButton > button[kind="primary"],
.stApp .stButton > button[data-testid="stBaseButton-primary"] {
  background: var(--fs-primary) !important; color: #fff !important;
  border: none !important; padding: 11px 24px !important; font-size: .98rem !important;
  box-shadow: 0 6px 18px -8px rgba(81,69,205,.55) !important;
}
.stApp .stButton > button[kind="primary"]:hover,
.stApp .stButton > button[data-testid="stBaseButton-primary"]:hover {
  background: var(--fs-primary-hover) !important;
  transform: translateY(-1px) !important;
  box-shadow: 0 10px 24px -8px rgba(81,69,205,.6) !important;
}
.stApp .stButton > button[kind="primary"]:disabled {
  background: #CBD5E1 !important; box-shadow: none !important;
  transform: none !important; cursor: not-allowed !important;
}

/* ── الرفع: منطقة سحب احترافية ── */
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] {
  border: 1.5px dashed #C7D2FE !important; border-radius: var(--fs-radius-lg) !important;
  background: var(--fs-surface) !important;
  transition: all .2s ease !important;
}
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"]:hover {
  border-color: var(--fs-primary) !important;
  background: #FAFAFF !important;
  box-shadow: 0 8px 24px -12px rgba(81,69,205,.3) !important;
}
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] button {
  background: var(--fs-primary) !important; color: #fff !important;
  border: none !important; border-radius: 9px !important; font-weight: 700 !important;
}

/* ── الحقول والراديو (بطاقة اختيار كوضعين) ── */
.stApp input, .stApp textarea,
.stApp [data-baseweb="select"] > div {
  border-radius: 10px !important; border: 1px solid var(--fs-line) !important;
  transition: border-color .2s ease, box-shadow .2s ease !important;
}
.stApp input:focus, .stApp textarea:focus,
.stApp [data-baseweb="select"] > div:focus-within {
  border-color: var(--fs-primary) !important;
  box-shadow: 0 0 0 3px rgba(81,69,205,.12) !important;
}
label[data-rac] {
  border: 1px solid var(--fs-line) !important; border-radius: 10px !important;
  padding: 10px 14px !important; margin: 4px 0 4px 0 !important;
  background: var(--fs-surface) !important; cursor: pointer !important;
  transition: all .18s ease !important; display: flex !important; width: 100% !important;
}
label[data-rac]:hover { border-color: var(--fs-primary) !important; }
label[data-rac][data-selected="true"] {
  border-color: var(--fs-primary) !important;
  background: #F5F4FF !important;
  box-shadow: 0 0 0 1px var(--fs-primary) !important;
}
label[data-rac] > span:first-child { position: absolute; opacity: 0; }

/* ── الجداول المالية ── */
.stApp [data-testid="stDataFrame"] {
  border: 1px solid var(--fs-line) !important; border-radius: var(--fs-radius) !important;
}
.fin-table-wrap table { font-variant-numeric: tabular-nums; }

/* ── الحالات: فارغ/خطأ/نجاح — بطاقات واضحة ── */
.fs-state {
  border-radius: var(--fs-radius-lg); padding: 22px 24px; text-align: center;
  border: 1px solid var(--fs-line); background: var(--fs-surface);
}
.fs-state .fs-state-ico { font-size: 1.6rem; margin-bottom: 8px; }
.fs-state .fs-state-title { font-weight: 800; font-size: 1.02rem; color: var(--fs-ink); }
.fs-state .fs-state-body { color: var(--fs-muted); font-size: .88rem; margin-top: 6px; line-height: 1.8; }
.fs-state.empty { border-style: dashed; }
.fs-state.error { border-color: #FECACA; background: #FEF2F2; }
.fs-state.success { border-color: #BBF7D0; background: #F0FDF4; }

/* ── الشريط الجانبي: سطح أبيض نظيف (لا زجاج داكن) ── */
section[data-testid="stSidebar"] {
  background: var(--fs-surface) !important;
  border-inline-start: 1px solid var(--fs-line);
}
section[data-testid="stSidebar"] * { color: var(--fs-ink) !important; }
section[data-testid="stSidebar"] .fs-nav-item {
  display: flex; align-items: center; gap: 10px; width: 100%;
  padding: 9px 12px; border-radius: 10px; font-weight: 600; font-size: .92rem;
  color: var(--fs-muted) !important; border: 1px solid transparent;
}
section[data-testid="stSidebar"] .fs-nav-item.active {
  color: var(--fs-primary) !important; background: #F5F4FF;
  border-color: color-mix(in srgb, var(--fs-primary) 30%, transparent);
}
section[data-testid="stSidebar"] hr { border-color: var(--fs-line) !important; }
section[data-testid="stSidebar"] .stTextInput input {
  background: var(--fs-bg) !important; border: 1px solid var(--fs-line) !important;
  color: var(--fs-ink) !important;
}
section[data-testid="stSidebar"] .stButton > button {
  background: var(--fs-surface) !important; border: 1px solid var(--fs-line) !important;
  color: var(--fs-ink) !important;
}
section[data-testid="stSidebar"] .stButton > button:hover {
  border-color: var(--fs-primary) !important; color: var(--fs-primary) !important;
}

/* ── الميتا والحواشي ── */
.fs-meta { font-size: .78rem; color: var(--fs-muted); }
.fs-meta b { color: var(--fs-ink); }
.fs-divider { border: none; border-top: 1px solid var(--fs-line); margin: 14px 0; }

/* ── استجابة العرض ── */
@media (max-width: 900px) {
  .fs-header { flex-direction: column; align-items: flex-start; }
  .fs-kpi .fs-kpi-value { font-size: 1.4rem; }
}
</style>"""
