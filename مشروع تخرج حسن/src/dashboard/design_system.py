# -*- coding: utf-8 -*-
"""وكيل تحليل بيانات مالية ذكي — نظام التصميم v9: Premium Light FinTech.

مواصفات صاحب المشروع (المعتمدة حرفياً):
- ثيم فاتح بريميوم: 70% أبيض/محايد فاتح، 20% بنفسجي-لافندر ناعم، 10% سماوي وأكسنت.
- باليتة محددة: صفحة #F7F8FC، أسطح #FFFFFF، سطح ثانوي #F1F3FF،
  بنفسجي أساسي #6255E7، عميق #5145CD، لافندر #EDEBFF، سماوي #22D3EE،
  سماوي ناعم #E6FAFF، نص #172033، ثانوي #64748B، حدود #E5E7F0.
- عرض محتوى 1200–1320px، تايبوغرافي عربي مقروء (عناوين 32–42px، متون 15–17px)،
  RTL متسق، خلفية حية راقية لا تزاحم المحتوى، حركات CSS حقيقية مع
  احترام prefers-reduced-motion، ومنطقة رفع ملفات كبيرة (170–220px).
"""
from __future__ import annotations

PRIMARY = "#6255E7"
DEEP = "#5145CD"
SOFT_PURPLE = "#EDEBFF"
SECONDARY = "#0891B2"          # سماوي نصي بتباين كافٍ على الفاتح
LIGHT_CYAN = "#22D3EE"
SOFT_CYAN = "#E6FAFF"
BG = "#F7F8FC"
BG2 = "#FFFFFF"
SURFACE = "#FFFFFF"
SURFACE2 = "#F1F3FF"
INK = "#172033"
MUTED = "#64748B"
LINE = "#E5E7F0"
SUCCESS = "#16A34A"
WARNING = "#F59E0B"
DANGER = "#DC2626"

DESIGN_CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&family=IBM+Plex+Sans+Arabic:wght@400;500;600;700;800&family=Inter:wght@400;600;700;800&family=Material+Symbols+Outlined:ops,wght,FILL,GRAD@24,400,0,0&display=swap');

:root {
  --fs-primary: #6255E7;
  --fs-deep: #5145CD;
  --fs-soft-purple: #EDEBFF;
  --fs-secondary: #0891B2;
  --fs-cyan: #22D3EE;
  --fs-soft-cyan: #E6FAFF;
  --fs-bg: #F7F8FC;
  --fs-surface: #FFFFFF;
  --fs-surface2: #F1F3FF;
  --fs-ink: #172033;
  --fs-muted: #64748B;
  --fs-line: #E5E7F0;
  --fs-success: #16A34A;
  --fs-warning: #F59E0B;
  --fs-danger: #DC2626;
  --fs-radius: 14px;
  --fs-radius-lg: 20px;
  --fs-shadow-sm: 0 2px 10px -4px rgba(81,69,205,.10);
  --fs-shadow-md: 0 10px 30px -14px rgba(81,69,205,.18);
  --fs-shadow-lg: 0 24px 55px -30px rgba(49,46,129,.28);
  /* متغيرات الثيم القديم (v6) — تُوحَّد مع v9 لمنع أي تعارض بقايا */
  --line: #E5E7F0;
  --brand: #6255E7;
  --brand2: #0891B2;
  --muted: #64748B;
  --bg: #F7F8FC;
}

/* تعطيل بقايا الثيم القديم: هالات ::before/::after بحجم ثابت 420px كانت
   تحصر خلفية v9 — تُعاد للامتداد الكامل ثم تتكفل قواعد v9 بما بعدها */
.stApp::before, .stApp::after {
  width: auto !important; height: auto !important;
  top: auto !important; left: auto !important;
  bottom: auto !important; right: auto !important;
}

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

/* == الخلفية الحية الفاتحة: هالات لافندر/سماوي ناعمة + شبكة خفيفة ==
   راقية ولا تزاحم المحتوى — إشعاعات ضبابية بأ opacity منخفضة جداً */
.stApp::before {
  content: ""; position: fixed; inset: -20%; z-index: 0; pointer-events: none;
  background:
    radial-gradient(640px 440px at 84% 6%, rgba(98,85,231,.09), transparent 62%),
    radial-gradient(560px 420px at 10% 20%, rgba(34,211,238,.08), transparent 60%),
    radial-gradient(720px 540px at 50% 108%, rgba(98,85,231,.06), transparent 65%),
    radial-gradient(430px 330px at 90% 80%, rgba(34,211,238,.06), transparent 58%);
  animation: fsAmbient 30s ease-in-out infinite alternate;
}
.stApp::after {
  content: ""; position: fixed; inset: 0; z-index: 0; pointer-events: none;
  background-image:
    linear-gradient(rgba(98,85,231,.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(98,85,231,.045) 1px, transparent 1px);
  background-size: 46px 46px;
  mask-image: radial-gradient(ellipse 92% 68% at 50% 0%, #000 28%, transparent 80%);
  -webkit-mask-image: radial-gradient(ellipse 92% 68% at 50% 0%, #000 28%, transparent 80%);
}
@keyframes fsAmbient {
  0%   { transform: translate3d(0, 0, 0) scale(1); }
  50%  { transform: translate3d(-2%, 1.6%, 0) scale(1.05); }
  100% { transform: translate3d(1.8%, -1.4%, 0) scale(1.02); }
}
.stApp > header, [data-testid="stHeader"] { background: transparent !important; }
[data-testid="stAppViewContainer"] { position: relative; z-index: 1; }
[data-testid="stSidebar"] { position: relative; z-index: 2; }

/* == الحاوية: عرض محتوى 1280px (نطاق 1200–1320 المطلوب) ==
   محاذاة أفقية متسقة وتباعد رأسي منتظم بلا مناطق فارغة */
.block-container {
  max-width: 1280px !important;
  padding: 1.5rem 2.2rem 3.4rem !important;
  margin-inline: auto !important;
}
.block-container > div { scroll-margin-top: 80px; }
section[data-testid="stSidebar"] { width: 258px !important; }

/* == حركات الدخول (بلا layout shift — transform/opacity فقط) == */
@keyframes fsUp { from { opacity: 0; transform: translateY(20px); }
                  to { opacity: 1; transform: none; } }
@keyframes fsPop { from { opacity: 0; transform: scale(.95) translateY(12px); }
                   to { opacity: 1; transform: none; } }
@keyframes fsGrow { from { transform: scaleY(.06); } to { transform: scaleY(1); } }
@keyframes fsShine { 0% { transform: translateX(-130%) skewX(-18deg); }
                     100% { transform: translateX(230%) skewX(-18deg); } }
@keyframes fsFloat { 0%,100% { transform: translateY(0); }
                     50% { transform: translateY(-6px); } }

/* == الهيدر: سطح أبيض + حدود لافندر == */
.fs-header {
  display: flex; align-items: center; justify-content: space-between;
  gap: 14px; padding: 12px 20px; margin-bottom: 18px;
  background: rgba(255,255,255,.86);
  border: 1px solid var(--fs-line);
  border-radius: var(--fs-radius-lg);
  backdrop-filter: blur(14px);
  box-shadow: var(--fs-shadow-md);
  animation: fsUp .5s cubic-bezier(.21,.98,.6,.99) both;
}
.fs-brand { display: flex; align-items: center; gap: 13px; }
.fs-logo {
  width: 50px; height: 50px; border-radius: 14px; flex: 0 0 auto;
  background: linear-gradient(135deg, var(--fs-primary), #7C6FE8 60%, var(--fs-cyan));
  display: grid; place-items: center; color: #fff;
  font-weight: 800; font-size: 1.55rem; font-family: 'Inter', sans-serif;
  box-shadow: 0 8px 20px -10px rgba(98,85,231,.55);
  transition: transform .25s ease, box-shadow .25s ease;
}
.fs-brand:hover .fs-logo { transform: scale(1.07) rotate(-3deg);
  box-shadow: 0 10px 28px -8px rgba(34,211,238,.45); }
.fs-brand-name {
  font-size: 1.75rem; font-weight: 800; color: var(--fs-ink); line-height: 1.3;
  font-family: 'IBM Plex Sans Arabic', 'Inter', sans-serif;
}
.fs-brand-sub {
  font-size: .76rem; font-weight: 700; color: #6366F1;
  text-transform: uppercase; letter-spacing: .18em; margin-top: 1px;
}
.fs-header-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.fs-pill {
  display: inline-flex; align-items: center; gap: 6px;
  border: 1px solid var(--fs-line); border-radius: 999px;
  padding: 4px 13px; background: #FFFFFF; color: #4338CA;
  font-size: .74rem; font-weight: 600;
}
.fs-pill .fs-dot { width: 7px; height: 7px; border-radius: 50%; }

/* == الـHero: عمودان متوازنان (نسخ يمين + معاينة يسار) — لا يحتل الشاشة كاملة == */
.fs-hero {
  display: grid; grid-template-columns: 1fr 1.02fr; gap: 24px;
  align-items: stretch; margin-bottom: 22px;
}
.fs-hero-copy {
  padding: 30px 30px 26px; border-radius: var(--fs-radius-lg);
  background: linear-gradient(160deg, var(--fs-soft-purple), #FFFFFF 62%);
  border: 1px solid rgba(98,85,231,.18);
  box-shadow: var(--fs-shadow-lg);
  animation: fsUp .6s cubic-bezier(.21,.98,.6,.99) both;
  display: flex; flex-direction: column; justify-content: center;
}
.fs-hero-eyebrow {
  display: inline-flex; align-items: center; gap: 7px; width: fit-content;
  font-size: .74rem; font-weight: 800; letter-spacing: .14em;
  color: #6366F1; text-transform: uppercase;
  background: rgba(98,85,231,.08); border: 1px solid rgba(98,85,231,.22);
  border-radius: 999px; padding: 5px 13px;
  margin-bottom: 14px; animation: fsUp .6s .08s both;
}
.fs-hero-title {
  font-size: 2.45rem; font-weight: 800; line-height: 1.42;
  color: var(--fs-ink) !important;
  margin: 0 0 12px;
  animation: fsUp .65s .14s cubic-bezier(.21,.98,.6,.99) both;
}
.fs-hero-title em {
  font-style: normal;
  background: linear-gradient(90deg, var(--fs-primary), var(--fs-secondary));
  -webkit-background-clip: text; background-clip: text;
  -webkit-text-fill-color: transparent;
}
.fs-hero-desc {
  color: #475569 !important; font-size: 1.05rem; line-height: 1.95;
  margin-bottom: 18px; animation: fsUp .7s .2s both;
}
.fs-hero-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap;
  animation: fsUp .7s .26s both; }
.fs-cta-link {
  display: inline-flex; align-items: center; gap: 8px;
  background: linear-gradient(110deg, var(--fs-primary), #5145CD 70%) !important;
  color: #fff !important; text-decoration: none !important;
  border-radius: 12px !important; padding: 11px 26px !important;
  font-weight: 700 !important; font-size: .98rem !important;
  box-shadow: 0 12px 28px -14px rgba(98,85,231,.6);
  transition: transform .2s ease, box-shadow .2s ease !important;
  position: relative; overflow: hidden;
}
.fs-cta-link:hover { transform: translateY(-2px);
  box-shadow: 0 16px 34px -14px rgba(98,85,231,.7); }
.fs-cta-link.ghost {
  background: #FFFFFF !important; color: var(--fs-primary) !important;
  border: 1px solid rgba(98,85,231,.35) !important; box-shadow: none;
}
.fs-cta-link.ghost:hover { border-color: var(--fs-primary);
  box-shadow: var(--fs-shadow-sm); }

/* == معاينة المنتج: بطاقة توضيحية موسومة — لا تُعرض أرقام وهمية كنتائج == */
.fs-preview {
  position: relative; overflow: hidden;
  background: var(--fs-surface); border-radius: var(--fs-radius-lg);
  border: 1px solid rgba(98,85,231,.20);
  box-shadow: var(--fs-shadow-lg);
  padding: 18px 20px 14px; display: flex; flex-direction: column;
  animation: fsPop .7s .22s cubic-bezier(.21,.98,.6,.99) both;
}
.fs-preview-tag {
  position: absolute; top: 12px; inset-inline-start: 14px;
  font-size: .68rem; font-weight: 700; letter-spacing: .04em;
  color: #6366F1; background: var(--fs-soft-purple);
  border: 1px solid rgba(98,85,231,.25); border-radius: 999px; padding: 3px 11px;
}
.fs-preview-title {
  font-size: .86rem; font-weight: 700; color: var(--fs-ink); margin: 24px 0 4px;
}
.fs-preview-sub { font-size: .74rem; color: var(--fs-muted); }
.fs-preview-kpis { display: flex; gap: 8px; margin: 12px 0 4px; }
.fs-mini-kpi {
  flex: 1; background: var(--fs-surface2); border: 1px solid var(--fs-line);
  border-radius: 10px; padding: 9px 10px;
  transition: transform .2s ease, border-color .2s ease;
}
.fs-mini-kpi:hover { transform: translateY(-2px); border-color: rgba(98,85,231,.4); }
.fs-mini-kpi b { display: block; font-size: .8rem; color: var(--fs-ink);
  font-weight: 800; }
.fs-mini-kpi span { font-size: .64rem; color: var(--fs-muted); font-weight: 600; }
.fs-mini-kpi.up b { color: var(--fs-success); }
.fs-mini-kpi.down b { color: var(--fs-danger); }
.fs-preview-chart {
  flex: 1; display: flex; align-items: flex-end; gap: 9px;
  height: 140px; padding: 12px 4px 0;
  border-top: 1px dashed var(--fs-line); margin-top: 10px;
}
.fs-bar {
  flex: 1; border-radius: 7px 7px 2px 2px; transform-origin: bottom;
  background: linear-gradient(180deg, #A5B4FC, var(--fs-primary));
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
  margin-top: 10px; font-size: .66rem; color: var(--fs-muted); text-align: center;
}

/* == عناوين الأقسام (تسلسل بصري واضح) == */
.sec-heading {
  font-size: 1.42rem; font-weight: 800; color: var(--fs-ink);
  margin: 6px 0 2px;
}
.sec-sub { font-size: .95rem; color: var(--fs-muted); margin-bottom: 4px; }
.sec-label {
  color: #5145CD !important; font-weight: 800 !important;
  font-size: .95rem !important;
}
.sec-label::after { background: var(--fs-cyan) !important; }

/* == مساحة تحليل المستندات: بطاقة بارزة == */
.fs-workspace {
  background: var(--fs-surface); border-radius: var(--fs-radius-lg);
  border: 1px solid rgba(98,85,231,.22);
  box-shadow: var(--fs-shadow-lg);
  padding: 24px 28px 22px; animation: fsUp .6s .28s both;
}
/* بطاقة الحاوية المحصورة (st.container border=True) — سطح أبيض بحد لافندر */
[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--fs-surface) !important;
  border: 1px solid rgba(98,85,231,.22) !important;
  border-radius: var(--fs-radius-lg) !important;
  box-shadow: var(--fs-shadow-lg) !important;
}
.fs-card-title {
  font-size: 1.22rem; font-weight: 800; color: var(--fs-ink);
  margin-bottom: 4px;
}
.fs-card-sub { font-size: .95rem; color: var(--fs-muted);
  margin-bottom: 12px; }
/* قائمة الملفات المختارة الحية (اسم/نوع/حجم/حالة) */
.fs-file-list { display: flex; flex-direction: column; gap: 8px;
  margin-top: 14px; animation: fsUp .4s ease both; }
.fs-file-row {
  display: flex; align-items: center; gap: 12px;
  background: var(--fs-surface); border: 1px solid var(--fs-line);
  border-radius: 12px; padding: 10px 14px;
  box-shadow: var(--fs-shadow-sm);
  transition: border-color .2s ease, transform .2s ease;
}
.fs-file-row:hover { border-color: rgba(98,85,231,.4); transform: translateX(-3px); }
.fs-file-ico {
  width: 38px; height: 38px; border-radius: 10px; flex: 0 0 auto;
  background: var(--fs-soft-purple); color: var(--fs-primary);
  display: inline-flex; align-items: center; justify-content: center;
}
.fs-file-ico svg { width: 20px; height: 20px; }
.fs-file-info { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.fs-file-info b { color: var(--fs-ink); font-size: .92rem;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fs-file-info span { color: var(--fs-muted); font-size: .78rem; }
.fs-file-row .fs-gate { flex: 0 0 auto; }
.fs-workspace input, .fs-workspace textarea,
.fs-workspace [data-baseweb="select"] > div {
  border-radius: 10px !important; border: 1px solid var(--fs-line) !important;
}
.fs-workspace input:focus, .fs-workspace textarea:focus {
  border-color: var(--fs-primary) !important;
  box-shadow: 0 0 0 3px rgba(98,85,231,.12) !important;
}

/* == منطقة الرفع الكبيرة (الأولوية القصوى): 170–220px بظل وحدود لافندر ==
   نُخفي النص الإنجليزي الافتراضي ونستبدله نصاً عربياً عبر ::before/::after
   مع الحفاظ الكامل على السلوك الأصلي للسحب والإفلات والزر */
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] {
  min-height: 196px !important; height: 196px;
  border: 2px dashed rgba(98,85,231,.35) !important;
  border-radius: var(--fs-radius-lg) !important;
  background:
    radial-gradient(420px 180px at 50% 0%, rgba(98,85,231,.06), transparent 70%),
    var(--fs-surface2) !important;
  transition: border-color .22s ease, background .22s ease,
              box-shadow .22s ease, transform .22s ease !important;
  padding: 18px 20px !important; margin-inline: auto;
  display: flex !important; flex-direction: column !important;
  justify-content: center; align-items: center;
  font-size: 0; /* نخفي نصوص Streamlit الإنجليزية داخل المنطقة */
  position: relative;
}
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] svg {
  width: 0 !important; height: 0 !important; display: none;
}
/* نصوص المنطقة الأصلية الإنجليزية تُخفى بالتحديد (حسب DOM المفحوص فعلياً) */
[data-testid="stFileUploaderDropzoneInstructions"] { display: none !important; }
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] button,
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] button * {
  font-size: 0 !important; /* تُحيّد نصوص الزر الأصلية ("upload"/"Upload") بالكامل */
}
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] button::after {
  content: "اختر من جهازك";
  font-size: .95rem !important; font-weight: 700 !important; color: #fff !important;
  font-family: 'IBM Plex Sans Arabic', sans-serif;
}
/* أيقونة السحب والإفلات: SVG مدمج مُرمَّز بالكامل — لا يعتمد على خطوط خارجية.
   flex-basis + min-height إجباريان: سياق flex العمودي كان يُفلت ارتفاع height العادي */
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"]::before {
  content: "" !important;
  display: block !important;
  width: 56px !important;
  height: 46px !important;
  min-height: 46px !important;
  flex: 0 0 46px !important;
  margin-bottom: 12px !important;
  background: url("data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20viewBox='0%200%2024%2024'%20fill='none'%20stroke='%236255E7'%20stroke-width='1.7'%20stroke-linecap='round'%20stroke-linejoin='round'%3E%3Cpath%20d='M20%2016.58A5%205%200%200%200%2018%207h-1.26A8%208%200%201%200%204%2015.25'/%3E%3Cpolyline%20points='16%2016%2012%2012%208%2016'/%3E%3Cline%20x1='12'%20y1='12'%20x2='12'%20y2='21'/%3E%3C/svg%3E") no-repeat center / contain !important;
  animation: fsFloat 3.5s ease-in-out infinite;
}
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"]::after {
  content: "اسحب ملفاتك هنا أو اختر من جهازك\APDF · XLSX · XLS · CSV — الحد الأقصى 25MB لكل ملف";
  font-size: 1.02rem; font-weight: 700; color: var(--fs-ink);
  display: block; text-align: center; line-height: 1.8;
  white-space: pre-line;
  font-family: 'IBM Plex Sans Arabic', sans-serif;
  margin-bottom: 6px;
}
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"]:hover {
  border-color: var(--fs-primary) !important; background: var(--fs-soft-purple) !important;
  box-shadow: 0 16px 36px -18px rgba(98,85,231,.4) !important;
  transform: translateY(-2px);
}
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] button,
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] a {
  font-size: .9rem !important;
  background: var(--fs-primary) !important; color: #fff !important;
  border: none !important; border-radius: 10px !important; font-weight: 700 !important;
  padding: 8px 22px !important; margin-top: 10px !important;
  box-shadow: 0 8px 20px -10px rgba(98,85,231,.5) !important;
}
/* قائمة الملفات المختارة داخل الأبلود الأصلي */
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzoneFileList"],
[data-testid="stFileUploader"] [data-testid="stFileUploaderFileList"] {
  font-size: .9rem;
}

/* == الإعدادات: بطاقات اختيار (دقيق/سريع) بنشاط لافندر == */
label[data-rac] {
  border: 1px solid var(--fs-line) !important; border-radius: 12px !important;
  padding: 13px 16px !important; margin: 4px 0 !important; width: 100% !important;
  background: var(--fs-surface) !important; cursor: pointer !important;
  transition: all .18s ease !important; display: flex !important;
  font-size: 0; /* نص الراديو يُعاد عبر عناصره الداخلية */
}
label[data-rac]:hover { border-color: var(--fs-primary) !important;
  box-shadow: var(--fs-shadow-sm); }
label[data-rac][data-selected="true"] {
  border-color: var(--fs-primary) !important; background: var(--fs-soft-purple) !important;
  box-shadow: 0 0 0 1px var(--fs-primary), var(--fs-shadow-sm) !important;
}
label[data-rac] > span:first-child { position: absolute; opacity: 0; }

/* == الأزرار == */
.stApp .stButton > button {
  border-radius: 12px !important; font-weight: 700 !important;
  border: 1px solid var(--fs-line) !important;
  background: #FFFFFF !important; color: var(--fs-ink) !important;
  font-size: .95rem !important;
  transition: all .22s cubic-bezier(.21,.98,.6,.99) !important;
}
.stApp .stButton > button:hover {
  border-color: var(--fs-primary) !important; color: var(--fs-primary) !important;
  transform: translateY(-2px) !important;
  box-shadow: var(--fs-shadow-md) !important;
}
.stApp .stButton > button[kind="primary"],
.stApp .stButton > button[data-testid="stBaseButton-primary"] {
  background: linear-gradient(110deg, var(--fs-primary), #5145CD 60%, #4338CA) !important;
  background-size: 170% 100% !important;
  color: #fff !important; border: none !important;
  padding: 13px 30px !important; font-size: 1.05rem !important;
  box-shadow: 0 14px 32px -16px rgba(98,85,231,.6) !important;
  position: relative; overflow: hidden;
}
.stApp .stButton > button[kind="primary"]::after,
.stApp .stButton > button[data-testid="stBaseButton-primary"]::after {
  content: ""; position: absolute; top: 0; bottom: 0; width: 40%;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,.22), transparent);
  animation: fsShine 3.4s ease-in-out infinite;
}
.stApp .stButton > button[kind="primary"]:hover,
.stApp .stButton > button[data-testid="stBaseButton-primary"]:hover {
  background-position: 100% 0 !important;
  transform: translateY(-2px) !important;
  box-shadow: 0 18px 42px -16px rgba(98,85,231,.7) !important;
}
.stApp .stButton > button[kind="primary"]:active,
.stApp .stButton > button[data-testid="stBaseButton-primary"]:active {
  transform: translateY(1px) scale(.99) !important;
  box-shadow: 0 6px 16px -10px rgba(98,85,231,.5) !important;
}
.stApp .stButton > button[kind="primary"]:disabled,
.stApp .stButton > button[data-testid="stBaseButton-primary"]:disabled {
  background: #E2E8F0 !important; color: #94A3B8 !important;
  box-shadow: none !important; transform: none !important;
}
.stApp .stButton > button[kind="primary"]:disabled::after,
.stApp .stButton > button[data-testid="stBaseButton-primary"]:disabled::after {
  display: none;
}

/* == بطاقات المميزات: نظام مكونات متسق == */
.fs-feature {
  position: relative; overflow: hidden; height: 100%;
  background: var(--fs-surface); border: 1px solid var(--fs-line);
  border-radius: var(--fs-radius); padding: 18px 20px;
  box-shadow: var(--fs-shadow-sm);
  animation: fsUp .6s both; transition: all .25s ease;
}
.fs-feature::before {
  content: ""; position: absolute; inset: 0 0 auto 0; height: 3px;
  background: linear-gradient(90deg, var(--fs-primary), var(--fs-cyan));
  opacity: 0; transition: opacity .25s ease;
}
.fs-feature:hover::before { opacity: 1; }
.fs-feature:hover {
  transform: translateY(-6px) !important;
  border-color: rgba(98,85,231,.45) !important;
  box-shadow: var(--fs-shadow-lg) !important;
}
.fs-feature-ico {
  width: 42px; height: 42px; border-radius: 11px;
  background: var(--fs-soft-purple); color: var(--fs-primary);
  display: inline-flex; align-items: center; justify-content: center;
  margin-bottom: 10px; transition: transform .3s ease, background .3s ease;
}
.fs-feature-ico svg { width: 22px; height: 22px; }
.fs-feature:hover .fs-feature-ico {
  transform: scale(1.1) rotate(-4deg);
  background: var(--fs-soft-cyan); color: var(--fs-secondary);
}
.fs-feature b { color: var(--fs-ink); font-size: 1.05rem; font-weight: 800;
  display: block; margin-bottom: 5px; }
.fs-feature span { color: var(--fs-muted); font-size: .92rem; line-height: 1.75; }

/* == بطاقات KPI == */
.fs-kpi {
  background: var(--fs-surface); border: 1px solid var(--fs-line);
  border-radius: var(--fs-radius-lg); padding: 16px 18px; height: 100%;
  box-shadow: var(--fs-shadow-sm);
  animation: fsPop .55s cubic-bezier(.21,.98,.6,.99) both;
  transition: transform .22s ease, box-shadow .22s ease, border-color .22s ease;
}
.fs-kpi:hover { transform: translateY(-4px);
  border-color: rgba(98,85,231,.45);
  box-shadow: var(--fs-shadow-md); }
.fs-kpi .fs-kpi-label { font-size: .78rem; font-weight: 700; color: var(--fs-muted);
  text-transform: uppercase; letter-spacing: .06em; }
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
.fs-kpi .na { color: var(--fs-muted); background: var(--fs-surface2); }
.fs-gate { display: inline-flex; align-items: center; gap: 6px;
  font-size: .72rem; font-weight: 700; padding: 3px 10px; border-radius: 999px; }
.fs-gate.ok { color: var(--fs-success); background: #F0FDF4; border: 1px solid #BBF7D0; }
.fs-gate.pend { color: var(--fs-warning); background: #FFFBEB; border: 1px solid #FDE68A; }
.fs-gate.miss { color: var(--fs-muted); background: #F1F5F9; border: 1px solid var(--fs-line); }
.fs-gate.bad { color: var(--fs-danger); background: #FEF2F2; border: 1px solid #FECACA; }

/* == الشريط الجانبي == */
section[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #FFFFFF, #F3F4FC) !important;
  border-inline-start: 1px solid var(--fs-line) !important;
}
section[data-testid="stSidebar"] * { color: #334155 !important; }
section[data-testid="stSidebar"] .fs-brand-name { color: var(--fs-ink) !important; }
section[data-testid="stSidebar"] hr { border-color: var(--fs-line) !important; }
section[data-testid="stSidebar"] .stTextInput input {
  background: #FFFFFF !important;
  border: 1px solid var(--fs-line) !important; color: var(--fs-ink) !important;
}
section[data-testid="stSidebar"] .stButton > button {
  background: #FFFFFF !important;
  border: 1px solid var(--fs-line) !important; color: #334155 !important;
  transition: all .2s ease !important;
}
section[data-testid="stSidebar"] .stButton > button:hover {
  border-color: var(--fs-primary) !important; color: var(--fs-primary) !important;
  transform: translateY(-1px) !important;
}
section[data-testid="stSidebar"] .stButton > button[kind="primary"] {
  background: linear-gradient(90deg, var(--fs-primary), #5145CD) !important;
  color: #fff !important; border: none !important;
}

/* == التبويبات == */
.stTabs [data-baseweb="tab-list"] { gap: 6px; }
.stTabs [data-baseweb="tab"] {
  border-radius: 999px !important; padding: 7px 18px !important;
  color: var(--fs-muted) !important; transition: all .2s ease !important;
}
.stTabs [data-baseweb="tab"] p { color: inherit !important; }
.stTabs [data-baseweb="tab"]:hover { background: rgba(98,85,231,.09) !important;
  color: var(--fs-ink) !important; }
.stTabs [aria-selected="true"] {
  background: linear-gradient(90deg, var(--fs-primary), #5145CD) !important;
}
.stTabs [aria-selected="true"] p { color: #fff !important; font-weight: 700 !important; }
.stTabs [data-baseweb="tab-highlight"] { display: none !important; }

/* == الحالات == */
.fs-state { border-radius: var(--fs-radius-lg); padding: 22px 24px;
  text-align: center; border: 1px solid var(--fs-line);
  background: var(--fs-surface); box-shadow: var(--fs-shadow-sm); }
.fs-state .fs-state-ico { font-size: 1.6rem; margin-bottom: 8px; }
.fs-state .fs-state-title { font-weight: 800; color: var(--fs-ink); }
.fs-state .fs-state-body { color: var(--fs-muted); font-size: .9rem; margin-top: 6px;
  line-height: 1.8; }
.fs-state.empty { border-style: dashed; }
.fs-state.error { border-color: rgba(220,38,38,.4); background: #FEF5F5; }
.fs-state.success { border-color: rgba(22,163,74,.4); background: #F2FBF4; }

/* == الفوتر == */
.fs-footer {
  margin-top: 28px; padding: 16px 24px; text-align: center;
  border-top: 1px solid var(--fs-line);
  color: var(--fs-muted); font-size: .82rem;
}
.fs-footer b { color: #475569; }

/* == الجداول == */
.fin-table td, .fin-table th, .stApp [data-testid="stDataFrame"] {
  unicode-bidi: plaintext;
}
.stApp [data-testid="stDataFrame"] {
  border: 1px solid var(--fs-line) !important;
  border-radius: var(--fs-radius) !important;
}

/* == نص المحتوى (تايبوغرافي عربي مقروء) == */
.block-container { color: var(--fs-ink); font-size: 1rem; }
.block-container h1, .block-container h2, .block-container h3,
.block-container h4 { color: #0F172A !important; line-height: 1.5; }
.block-container h2 { font-size: 1.55rem; }
.block-container h3 { font-size: 1.25rem; }
.block-container p, .block-container li { color: #334155;
  font-size: 1rem; line-height: 1.9; }
.block-container strong, .block-container b { color: #0F172A; }
.block-container [data-testid="stMetric"] label,
.block-container [data-testid="stMetric"] div,
.block-container [data-testid="stMetricValue"] {
  color: var(--fs-ink) !important;
}
.block-container .stMarkdown strong { color: #0F172A; }
.stApp label, .stApp [data-testid="stWidgetLabel"] p {
  font-size: .92rem !important; color: #334155 !important;
}

/* == عناصر عامة == */
.stApp input, .stApp textarea,
.stApp [data-baseweb="select"] > div {
  border-radius: 10px !important; border: 1px solid var(--fs-line) !important;
  background: #FFFFFF !important; color: var(--fs-ink) !important;
}
.stApp input:focus, .stApp textarea:focus {
  border-color: var(--fs-primary) !important;
  box-shadow: 0 0 0 3px rgba(98,85,231,.14) !important;
}
.stApp [data-testid="stExpander"] {
  border: 1px solid var(--fs-line) !important;
  border-radius: var(--fs-radius) !important;
  background: var(--fs-surface) !important;
}
.stApp [data-testid="stExpander"] * { color: #334155; }
.stApp [data-testid="stExpander"] summary { color: var(--fs-ink) !important; }
.or-line { text-align: center; color: var(--fs-muted);
  font-size: .88rem; margin: 6px 0; }
::selection { background: rgba(98,85,231,.22); color: var(--fs-ink); }
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-track { background: #EEF0F8; }
::-webkit-scrollbar-thumb { background: rgba(98,85,231,.35); border-radius: 999px; }
::-webkit-scrollbar-thumb:hover { background: rgba(98,85,231,.55); }

.step-card {
  background: var(--fs-surface) !important;
  border: 1px solid var(--fs-line) !important;
}
.step-card span { color: var(--fs-muted) !important; }
.step-card b { color: var(--fs-ink) !important; }
.step-num { background: var(--fs-primary) !important; color: #fff !important; }

/* == استجابة العرض (1440 / 1366 / 1024 / 390) == */
@media (max-width: 1366px) {
  .block-container { max-width: 1200px !important; }
}
@media (max-width: 1100px) {
  .fs-hero { grid-template-columns: 1fr; }
  .fs-hero-title { font-size: 2.05rem; }
  .block-container { max-width: 100% !important; padding: 1.2rem 1.2rem 3rem !important; }
}
@media (max-width: 640px) {
  .fs-hero-title { font-size: 1.72rem; }
  .fs-hero-copy { padding: 22px 20px; }
  .fs-preview-chart { min-height: 90px; }
  .fs-workspace { padding: 16px 14px; }
  section[data-testid="stSidebar"] { width: 220px !important; }
  .fs-brand-name { font-size: 1.35rem; }
  .fs-header { padding: 10px 14px; }
}

/* == prefers-reduced-motion == */
@media (prefers-reduced-motion: reduce) {
  .hero, .kpi-card, .feature, .step-card, .fs-feature, .fs-kpi,
  .fs-hero-copy, .fs-preview, .fs-workspace, .fs-bar, .fs-header,
  .stApp::before, .stApp::after {
    animation: none !important; transition: none !important;
  }
  .stApp .stButton > button[kind="primary"]::after { animation: none !important; }
  [data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"]::before {
    animation: none !important;
  }
}
</style>"""
