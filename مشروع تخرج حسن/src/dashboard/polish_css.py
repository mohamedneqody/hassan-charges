# -*- coding: utf-8 -*-
"""طبقة التلميع التفاعلية (v5): تضاف فوق THEME_CSS بلا مساس — تصميم
مvp_preview.css المستورد إلى Streamlit: RTL حقيقي، hero داكن، dropzone
حي، أزرار مقسمة، أزرار متدرجة، بطاقات تُقلع عند التحويم."""

POLISH_CSS = """<style>
/* ── الاتجاه: عربي RTL حقيقي على كامل التطبيق ── */
html, body, .stApp, section[data-testid="stSidebar"] { direction: rtl; }
.stApp { text-align: right; }

/* ── الخلفية: تدرج ناعم حي ── */
.stApp {
  background:
    radial-gradient(1200px 500px at 85% -5%, rgba(99,102,241,.10), transparent 60%),
    radial-gradient(900px 420px at 10% 110%, rgba(124,58,237,.08), transparent 60%),
    linear-gradient(180deg, #f8faff 0%, #f5f3ff 100%);
}

/* ── الـHero: التصميم الداكن ينتصر — أزل تعارض الخلفية الفاتحة ── */
.hero {
  background: linear-gradient(135deg, #1e1b4b 0%, #312e81 45%, #4c1d95 100%) !important;
  border: 1px solid rgba(129,140,248,.5) !important;
  box-shadow: 0 34px 80px -24px rgba(49,46,129,.7) !important;
  padding: 3.2rem 2.6rem !important;
}
.hero h1 { font-size: 3rem !important; }
.hero h1 .grad-text {
  background: linear-gradient(90deg, #a5b4fc, #f0abfc, #67e8f9) !important;
  -webkit-background-clip: text !important; background-clip: text !important;
  -webkit-text-fill-color: transparent !important;
}
.hero p { color: #c7d2fe !important; font-size: 1.08rem !important; }
.hero .chip {
  background: rgba(255,255,255,.10) !important;
  border: 1px solid rgba(165,180,252,.4) !important;
  color: #e0e7ff !important; backdrop-filter: blur(6px);
  transition: transform .25s ease, background .25s ease;
}
.hero .chip:hover { transform: translateY(-3px); background: rgba(255,255,255,.17) !important; }

/* ── منطقة الرفع: Dropzone حي ── */
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] {
  border: 2px dashed #c7d2fe !important; border-radius: 18px !important;
  background: linear-gradient(180deg, #fafaff, #f5f3ff) !important;
  transition: all .3s cubic-bezier(.21,.98,.6,.99) !important;
}
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"]:hover {
  border-color: #818cf8 !important;
  background: linear-gradient(180deg, #eef2ff, #f5f3ff) !important;
  box-shadow: 0 14px 34px -14px rgba(79,70,229,.45) !important;
  transform: translateY(-2px);
}
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] button {
  background: linear-gradient(90deg, #4f46e5, #7c3aed) !important;
  color: #fff !important; border: none !important; border-radius: 12px !important;
  font-weight: 700 !important; padding: 8px 22px !important;
  box-shadow: 0 8px 20px -8px rgba(79,70,229,.6) !important;
}

/* ── الحقول: بطاقات بتركيز مضيء ── */
.stApp input, .stApp textarea,
.stApp [data-baseweb="select"] > div {
  border-radius: 12px !important;
  border: 1px solid #dbe2ef !important;
  transition: border-color .25s ease, box-shadow .25s ease !important;
}
.stApp input:focus, .stApp textarea:focus,
.stApp [data-baseweb="select"] > div:focus-within {
  border-color: #818cf8 !important;
  box-shadow: 0 0 0 4px rgba(99,102,241,.14) !important;
}

/* ── الراديو: أزرار مقسمة (Segmented) — بنية react-aria: label[data-selected] ── */
label[data-rac] {
  border: 1.5px solid #dbe2ef !important; border-radius: 999px !important;
  padding: 9px 16px !important; margin: 4px 0 4px 8px !important;
  background: #fff !important; cursor: pointer !important;
  transition: all .25s cubic-bezier(.21,.98,.6,.99) !important;
  font-weight: 600 !important; display: flex !important; width: fit-content !important;
}
label[data-rac]:hover {
  border-color: #a5b4fc !important; transform: translateY(-1px);
  box-shadow: 0 8px 18px -10px rgba(79,70,229,.4) !important;
}
label[data-rac][data-selected="true"] {
  background: linear-gradient(90deg, #eef2ff, #f5f3ff) !important;
  border-color: #6366f1 !important;
  box-shadow: 0 8px 20px -8px rgba(79,70,229,.45) !important;
}
label[data-rac] > span:first-child { display: none !important; }
/* حاوية المجموعة عمودية مريحة */
[data-testid="stRadio"] [role="radiogroup"] {
  display: flex; flex-direction: column; gap: 2px;
}

/* ── الأزرار: تدرج + إقلاع ── */
.stApp .stButton > button {
  border-radius: 14px !important; font-weight: 700 !important;
  transition: all .28s cubic-bezier(.21,.98,.6,.99) !important;
  border: 1px solid #dbe2ef !important; background: #fff !important;
}
.stApp .stButton > button:hover {
  transform: translateY(-2px) !important;
  border-color: #a5b4fc !important;
  box-shadow: 0 14px 28px -12px rgba(79,70,229,.5) !important;
}
.stApp .stButton > button[kind="primary"],
.stApp .stButton > button[data-testid="stBaseButton-primary"] {
  background: linear-gradient(90deg, #4f46e5, #7c3aed) !important;
  color: #fff !important; border: none !important;
  padding: 12px 26px !important; font-size: 1.02rem !important;
  box-shadow: 0 14px 30px -10px rgba(79,70,229,.65) !important;
}
.stApp .stButton > button[kind="primary"]:hover,
.stApp .stButton > button[data-testid="stBaseButton-primary"]:hover {
  transform: translateY(-3px) !important;
  box-shadow: 0 20px 40px -12px rgba(79,70,229,.75) !important;
  filter: brightness(1.06) !important;
}
.stApp .stButton > button[kind="primary"]:active { transform: translateY(0) !important; }

/* ── بطاقات المميزات والخطوات: إقلاع وشريط علوي متدرج ── */
.feature, .step-card {
  transition: transform .28s cubic-bezier(.21,.98,.6,.99),
              box-shadow .28s ease, border-color .28s ease !important;
}
.feature::before, .step-card::before {
  content: ""; position: absolute; inset: 0 0 auto 0; height: 4px;
  background: linear-gradient(90deg, #4f46e5, #7c3aed, #06b6d4);
  opacity: 0; transition: opacity .28s ease;
}
.feature:hover::before, .step-card:hover::before { opacity: 1; }
.feature:hover, .step-card:hover {
  transform: translateY(-6px) !important;
  border-color: #c7d2fe !important;
  box-shadow: 0 20px 40px -16px rgba(79,70,229,.45) !important;
}
.feature-ico, .step-ico { transition: transform .3s ease !important; }
.feature:hover .feature-ico, .step-card:hover .step-ico {
  transform: scale(1.18) rotate(-4deg);
}

/* ── شريط الإحصائيات: رقائق متدرجة ── */
.stat-band {
  background: linear-gradient(90deg, #1e1b4b, #312e81, #4c1d95) !important;
  border: none !important; border-radius: 18px !important;
  padding: 16px 26px !important;
  box-shadow: 0 18px 44px -18px rgba(49,46,129,.6) !important;
}
.stat-band span {
  color: #e0e7ff !important; background: rgba(255,255,255,.08) !important;
  border: 1px solid rgba(165,180,252,.3) !important; border-radius: 999px !important;
  padding: 6px 14px !important; margin: 3px 4px !important;
  transition: background .25s ease;
}
.stat-band span:hover { background: rgba(255,255,255,.16) !important; }
.stat-band b { color: #fff !important; }

/* ── التبويبات: حبوب نشطة متدرجة ── */
.stTabs [data-baseweb="tab-list"] { gap: 6px; }
.stTabs [data-baseweb="tab"] {
  border-radius: 999px !important; padding: 6px 16px !important;
  transition: all .25s ease !important;
}
.stTabs [data-baseweb="tab"]:hover { background: #eef2ff !important; }
.stTabs [aria-selected="true"] {
  background: linear-gradient(90deg, #4f46e5, #7c3aed) !important;
}
.stTabs [aria-selected="true"] p { color: #fff !important; font-weight: 700 !important; }
.stTabs [data-baseweb="tab-highlight"] { display: none !important; }

/* ── بطاقات الخانات في الواجهة الجديدة: إقلاع عند التحويم ── */
[data-testid="stVerticalBlockBorderWrapper"] {
  transition: transform .25s ease, box-shadow .25s ease,
              border-color .25s ease !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:hover {
  transform: translateY(-3px) !important;
  border-color: #a5b4fc !important;
  box-shadow: 0 16px 34px -16px rgba(79,70,229,.4) !important;
}

/* ── الشريط الجانبي: زجاج داكن ── */
section[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #111633, #1e1b4b 55%, #312e81) !important;
}
section[data-testid="stSidebar"] * { color: #e0e7ff !important; }
section[data-testid="stSidebar"] .rc-title { color: #fff !important; }
section[data-testid="stSidebar"] hr { border-color: rgba(165,180,252,.2) !important; }
section[data-testid="stSidebar"] .stTextInput input {
  background: rgba(255,255,255,.08) !important;
  border: 1px solid rgba(165,180,252,.3) !important; color: #fff !important;
}
section[data-testid="stSidebar"] .stButton > button {
  background: rgba(255,255,255,.08) !important;
  border: 1px solid rgba(165,180,252,.35) !important; color: #e0e7ff !important;
}
section[data-testid="stSidebar"] .stButton > button:hover {
  background: rgba(255,255,255,.16) !important; transform: translateY(-1px) !important;
}
section[data-testid="stSidebar"] .stButton > button[kind="primary"] {
  background: linear-gradient(90deg, #4f46e5, #7c3aed) !important; color: #fff !important;
}

/* ── تحسينات عامة ── */
.block-container { max-width: 1280px !important; padding-top: 2rem !important; }
.or-line { text-align: center; color: #94a3b8; font-size: .85rem; margin: 6px 0; }
::selection { background: #c7d2fe; }
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-thumb { background: #c7d2fe; border-radius: 999px; }
::-webkit-scrollbar-thumb:hover { background: #a5b4fc; }
</style>"""
