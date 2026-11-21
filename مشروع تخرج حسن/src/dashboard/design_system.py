# -*- coding: utf-8 -*-
"""وكيل تحليل بيانات مالية ذكي — نظام التصميم الموحد v9.1: Premium Light FinTech.

المواصفات المعتمدة:
- باليتة موحدة: صفحة #F7F8FC، أسطح #FFFFFF، سطح ثانوي #F1F3FF،
  بنفسجي أساسي #6255E7، عميق #5145CD، لافندر #EDEBFF، سماوي #0891B2 / #22D3EE،
  نص #172033، ثانوي #64748B، حدود #E5E7F0، نجاح #16A34A، تحذير #F59E0B، خطر #DC2626.
- مقياس مسافات موحد: 4 / 8 / 12 / 16 / 24 / 32px كمتغيرات CSS (--fs-sp-*).
- عربي RTL أولًا مع دعم تبديل كامل إلى EN-LTR عبر get_design_css(lang).
- كافة مكونات الواجهة (الكلاسيكية والجديدة) تستمد ألوانها وحدودها وظلالها من هنا فقط.
"""
from __future__ import annotations

from functools import lru_cache

# ---------------------------------------------------------------------------
# Unified Design Tokens (Python + CSS source of truth)
# ---------------------------------------------------------------------------
PRIMARY = "#6255E7"
PRIMARY_MID = "#7C6FE8"
PRIMARY_DARK = "#4338CA"
DEEP = "#5145CD"
SOFT_PURPLE = "#EDEBFF"
INDIGO_SOFT = "#A5B4FC"
SECONDARY = "#0891B2"
LIGHT_CYAN = "#22D3EE"
CYAN_SOFT = "#67E8F9"
SOFT_CYAN = "#E6FAFF"
ON_PRIMARY = "#FFFFFF"

BG = "#F7F8FC"
BG2 = "#FFFFFF"
SURFACE = "#FFFFFF"
SURFACE2 = "#F1F3FF"
ROW_HOVER = "#F6F7FF"
SIDEBAR_BG_END = "#F3F4FC"
TRACK_BG = "#EEF0F8"

INK = "#172033"
INK_BODY = "#334155"
MUTED = "#64748B"
LINE = "#E5E7F0"
DISABLED_BG = "#E2E8F0"
DISABLED_INK = "#94A3B8"

SUCCESS = "#16A34A"
SUCCESS_LIGHT = "#22C55E"
SUCCESS_BG = "#F0FDF4"
SUCCESS_SOFT = "#DCFCE7"
SUCCESS_BORDER = "#BBF7D0"

WARNING = "#F59E0B"
WARNING_LIGHT = "#FBBF24"
WARNING_TEXT = "#B45309"
WARNING_BG = "#FFFBEB"
WARNING_BORDER = "#FDE68A"

DANGER = "#DC2626"
DANGER_LIGHT = "#F87171"
DANGER_BG = "#FEF2F2"
DANGER_SOFT = "#FEE2E2"
DANGER_BORDER = "#FECACA"

NEUTRAL_BG = "#F1F5F9"

SPACING = {
    1: "4px",
    2: "8px",
    3: "12px",
    4: "16px",
    6: "24px",
    8: "32px",
}


@lru_cache(maxsize=2)
def get_design_css(lang: str = "ar") -> str:
    """Build the complete, conflict-free CSS stylesheet for `ar` (RTL) or `en` (LTR)."""
    is_rtl = lang != "en"
    direction = "rtl" if is_rtl else "ltr"
    text_align = "right" if is_rtl else "left"
    drop_btn_text = "اختر من جهازك" if is_rtl else "Browse files"
    drop_body_text = (
        "اسحب ملفاتك هنا أو اختر من جهازك\\APDF · XLSX · XLS · CSV — الحد الأقصى 25MB لكل ملف"
        if is_rtl
        else "Drag & drop financial files here or browse\\APDF · XLSX · XLS · CSV — Max 25MB per file"
    )
    hover_shift = "-3px" if is_rtl else "3px"

    return f"""<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@600;700;800&family=IBM+Plex+Sans+Arabic:wght@400;500;600;700&family=Inter:wght@400;600;700;800&display=swap');

:root {{
  /* Colors */
  --fs-primary: {PRIMARY};
  --fs-primary-mid: {PRIMARY_MID};
  --fs-primary-dark: {PRIMARY_DARK};
  --fs-deep: {DEEP};
  --fs-soft-purple: {SOFT_PURPLE};
  --fs-indigo-soft: {INDIGO_SOFT};
  --fs-secondary: {SECONDARY};
  --fs-cyan: {LIGHT_CYAN};
  --fs-cyan-soft: {CYAN_SOFT};
  --fs-soft-cyan: {SOFT_CYAN};
  --fs-on-primary: {ON_PRIMARY};
  --fs-bg: {BG};
  --fs-surface: {SURFACE};
  --fs-surface2: {SURFACE2};
  --fs-row-hover: {ROW_HOVER};
  --fs-sidebar-bg-end: {SIDEBAR_BG_END};
  --fs-track-bg: {TRACK_BG};
  --fs-ink: {INK};
  --fs-ink-body: {INK_BODY};
  --fs-muted: {MUTED};
  --fs-line: {LINE};
  --fs-disabled-bg: {DISABLED_BG};
  --fs-disabled-ink: {DISABLED_INK};

  /* Semantic Status Colors */
  --fs-success: {SUCCESS};
  --fs-success-light: {SUCCESS_LIGHT};
  --fs-success-bg: {SUCCESS_BG};
  --fs-success-soft: {SUCCESS_SOFT};
  --fs-success-border: {SUCCESS_BORDER};
  --fs-warning: {WARNING};
  --fs-warning-light: {WARNING_LIGHT};
  --fs-warning-text: {WARNING_TEXT};
  --fs-warning-bg: {WARNING_BG};
  --fs-warning-border: {WARNING_BORDER};
  --fs-danger: {DANGER};
  --fs-danger-light: {DANGER_LIGHT};
  --fs-danger-bg: {DANGER_BG};
  --fs-danger-soft: {DANGER_SOFT};
  --fs-danger-border: {DANGER_BORDER};
  --fs-neutral-bg: {NEUTRAL_BG};

  /* Spacing Scale (4 / 8 / 12 / 16 / 24 / 32) */
  --fs-sp-1: 4px;
  --fs-sp-2: 8px;
  --fs-sp-3: 12px;
  --fs-sp-4: 16px;
  --fs-sp-6: 24px;
  --fs-sp-8: 32px;

  /* Radii, Borders & Shadows */
  --fs-radius-sm: 10px;
  --fs-radius: 14px;
  --fs-radius-lg: 20px;
  --fs-radius-pill: 999px;
  --fs-border: 1px solid var(--fs-line);
  --fs-border-accent: 1px solid rgba(98, 85, 231, .22);
  --fs-shadow-sm: 0 2px 10px -4px rgba(81, 69, 205, .10);
  --fs-shadow-md: 0 10px 30px -14px rgba(81, 69, 205, .18);
  --fs-shadow-lg: 0 24px 55px -30px rgba(49, 46, 129, .28);
  --fs-focus-ring: 0 0 0 3px rgba(98, 85, 231, .14);

  /* Unified aliases for Classic UI components */
  --bg: var(--fs-bg);
  --card: var(--fs-surface);
  --ink: var(--fs-ink);
  --muted: var(--fs-muted);
  --line: var(--fs-line);
  --brand: var(--fs-primary);
  --brand2: var(--fs-deep);
  --pos: var(--fs-success);
  --neg: var(--fs-danger);
}}

/* == Base Direction & Typography == */
html, body, .stApp {{
  direction: {direction};
  font-family: 'IBM Plex Sans Arabic', 'Cairo', 'Inter', 'Segoe UI', Tahoma, sans-serif;
}}
.stApp {{
  background: var(--fs-bg) !important;
  color: var(--fs-ink);
  text-align: {text_align};
}}
[data-testid="stMarkdownContainer"] {{
  direction: {direction};
  text-align: {text_align};
}}
[data-testid="stMarkdownContainer"] pre,
[data-testid="stMarkdownContainer"] code {{
  direction: ltr;
  text-align: left;
  unicode-bidi: isolate;
}}

/* == Ambient Light FinTech Background == */
.stApp::before {{
  content: "";
  position: fixed;
  inset: -20%;
  z-index: 0;
  pointer-events: none;
  background:
    radial-gradient(640px 440px at 84% 6%, rgba(98, 85, 231, .09), transparent 62%),
    radial-gradient(560px 420px at 10% 20%, rgba(34, 211, 238, .08), transparent 60%),
    radial-gradient(720px 540px at 50% 108%, rgba(98, 85, 231, .06), transparent 65%),
    radial-gradient(430px 330px at 90% 80%, rgba(34, 211, 238, .06), transparent 58%);
  animation: fsAmbient 30s ease-in-out infinite alternate;
}}
.stApp::after {{
  content: "";
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background-image:
    linear-gradient(rgba(98, 85, 231, .04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(98, 85, 231, .04) 1px, transparent 1px);
  background-size: 46px 46px;
  mask-image: radial-gradient(ellipse 92% 68% at 50% 0%, #000 28%, transparent 80%);
  -webkit-mask-image: radial-gradient(ellipse 92% 68% at 50% 0%, #000 28%, transparent 80%);
}}
@keyframes fsAmbient {{
  0%   {{ transform: translate3d(0, 0, 0) scale(1); }}
  50%  {{ transform: translate3d(-2%, 1.6%, 0) scale(1.05); }}
  100% {{ transform: translate3d(1.8%, -1.4%, 0) scale(1.02); }}
}}
.stApp > header, [data-testid="stHeader"] {{ background: transparent !important; }}
[data-testid="stAppViewContainer"], section.stMain {{ position: relative; z-index: 1; }}

/* == Main Container == */
.block-container {{
  max-width: 1280px !important;
  padding: 2.6rem 2rem var(--fs-sp-8) !important;
  margin-inline: auto !important;
  color: var(--fs-ink);
  font-size: 1rem;
}}
.block-container > div {{ scroll-margin-top: 80px; }}
@media (min-width: 1025px) {{
  section[data-testid="stSidebar"][aria-expanded="true"] {{
    width: 272px !important;
  }}
}}

/* == Entrance & UI Animations == */
@keyframes fsUp {{
  from {{ opacity: 0; transform: translateY(16px); }}
  to   {{ opacity: 1; transform: none; }}
}}
@keyframes fsPop {{
  from {{ opacity: 0; transform: scale(.96) translateY(10px); }}
  to   {{ opacity: 1; transform: none; }}
}}
@keyframes fsGrow {{
  from {{ transform: scaleY(.06); }}
  to   {{ transform: scaleY(1); }}
}}
@keyframes fsShine {{
  0%   {{ transform: translateX(-130%) skewX(-18deg); }}
  100% {{ transform: translateX(230%) skewX(-18deg); }}
}}
@keyframes fsFloat {{
  0%, 100% {{ transform: translateY(0); }}
  50%      {{ transform: translateY(-5px); }}
}}
@keyframes fsPulse {{
  0%   {{ box-shadow: 0 0 0 0 rgba(22, 163, 74, .45); }}
  70%  {{ box-shadow: 0 0 0 8px transparent; }}
  100% {{ box-shadow: 0 0 0 0 transparent; }}
}}
@keyframes fsBarShimmer {{
  0%   {{ transform: translateX(-100%); }}
  100% {{ transform: translateX(220%); }}
}}

/* == Compact App Header == */
.fs-header {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--fs-sp-3);
  padding: var(--fs-sp-3) var(--fs-sp-4);
  margin-bottom: var(--fs-sp-4);
  background: rgba(255, 255, 255, .9);
  border: var(--fs-border);
  border-radius: var(--fs-radius-lg);
  backdrop-filter: blur(14px);
  box-shadow: var(--fs-shadow-md);
  animation: fsUp .45s cubic-bezier(.21, .98, .6, .99) both;
}}
.fs-brand {{
  display: flex;
  align-items: center;
  gap: var(--fs-sp-3);
  min-width: 0;
}}
.fs-logo {{
  width: 46px;
  height: 46px;
  border-radius: var(--fs-radius);
  flex: 0 0 auto;
  background: linear-gradient(135deg, var(--fs-primary), var(--fs-primary-mid) 60%, var(--fs-cyan));
  display: grid;
  place-items: center;
  color: var(--fs-on-primary);
  font-weight: 800;
  box-shadow: 0 8px 20px -10px rgba(98, 85, 231, .55);
  transition: transform .25s ease, box-shadow .25s ease;
}}
.fs-logo svg {{ width: 24px; height: 24px; }}
.fs-brand:hover .fs-logo {{
  transform: scale(1.06) rotate(-3deg);
  box-shadow: 0 10px 28px -8px rgba(34, 211, 238, .45);
}}
.fs-brand-name {{
  font-size: clamp(1.15rem, 1.8vw, 1.55rem);
  font-weight: 800;
  color: var(--fs-ink);
  line-height: 1.3;
  font-family: 'IBM Plex Sans Arabic', 'Cairo', 'Inter', sans-serif;
}}
.fs-brand-sub {{
  font-size: .72rem;
  font-weight: 700;
  color: var(--fs-deep);
  text-transform: uppercase;
  letter-spacing: .14em;
  margin-top: 2px;
}}
.fs-header-meta {{
  display: flex;
  align-items: center;
  gap: var(--fs-sp-2);
  flex-wrap: wrap;
}}
.fs-pill {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: var(--fs-border);
  border-radius: var(--fs-radius-pill);
  padding: 5px var(--fs-sp-3);
  background: var(--fs-surface);
  color: var(--fs-deep);
  font-size: .76rem;
  font-weight: 700;
  max-width: 100%;
}}
.fs-pill .fs-dot {{
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex: 0 0 auto;
}}
.live-dot {{
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--fs-success);
  display: inline-block;
  animation: fsPulse 2s infinite;
}}

/* == Landing Hero == */
.fs-hero-copy {{
  padding: var(--fs-sp-8) var(--fs-sp-6) var(--fs-sp-6);
  border-radius: var(--fs-radius-lg);
  background: linear-gradient(160deg, var(--fs-soft-purple), var(--fs-surface) 62%);
  border: var(--fs-border-accent);
  box-shadow: var(--fs-shadow-lg);
  animation: fsUp .55s cubic-bezier(.21, .98, .6, .99) both;
  display: flex;
  flex-direction: column;
  justify-content: center;
}}
.fs-hero-eyebrow {{
  display: inline-flex;
  align-items: center;
  gap: var(--fs-sp-2);
  width: fit-content;
  font-size: .74rem;
  font-weight: 800;
  letter-spacing: .14em;
  color: var(--fs-deep);
  text-transform: uppercase;
  background: rgba(98, 85, 231, .08);
  border: var(--fs-border-accent);
  border-radius: var(--fs-radius-pill);
  padding: var(--fs-sp-1) var(--fs-sp-3);
  margin-bottom: var(--fs-sp-4);
}}
.fs-hero-title {{
  font-size: clamp(1.72rem, 2.8vw, 2.45rem);
  font-weight: 800;
  line-height: 1.4;
  color: var(--fs-ink) !important;
  margin: 0 0 var(--fs-sp-3);
  text-align: start !important;
}}
.fs-hero-title em {{
  font-style: normal;
  background: linear-gradient(90deg, var(--fs-primary), var(--fs-secondary));
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}}
.fs-hero-desc {{
  color: var(--fs-ink-body) !important;
  font-size: 1.02rem;
  line-height: 1.9;
  margin-bottom: var(--fs-sp-4);
}}
.fs-hero-actions {{
  display: flex;
  gap: var(--fs-sp-3);
  align-items: center;
  flex-wrap: wrap;
}}
.fs-cta-link {{
  display: inline-flex;
  align-items: center;
  gap: var(--fs-sp-2);
  background: linear-gradient(110deg, var(--fs-primary), var(--fs-deep) 70%) !important;
  color: var(--fs-on-primary) !important;
  text-decoration: none !important;
  border-radius: 12px !important;
  padding: 11px var(--fs-sp-6) !important;
  font-weight: 700 !important;
  font-size: .96rem !important;
  box-shadow: 0 12px 28px -14px rgba(98, 85, 231, .6);
  transition: transform .2s ease, box-shadow .2s ease !important;
}}
.fs-cta-link:hover {{
  transform: translateY(-2px);
  box-shadow: 0 16px 34px -14px rgba(98, 85, 231, .7);
}}
.fs-cta-link.ghost {{
  background: var(--fs-surface) !important;
  color: var(--fs-primary) !important;
  border: 1px solid rgba(98, 85, 231, .35) !important;
  box-shadow: none;
}}
.fs-cta-link.ghost:hover {{
  border-color: var(--fs-primary);
  box-shadow: var(--fs-shadow-sm);
}}

/* == Landing Product Preview == */
.fs-preview {{
  position: relative;
  overflow: hidden;
  background: var(--fs-surface);
  border-radius: var(--fs-radius-lg);
  border: var(--fs-border-accent);
  box-shadow: var(--fs-shadow-lg);
  padding: var(--fs-sp-4) var(--fs-sp-6) var(--fs-sp-4);
  display: flex;
  flex-direction: column;
  animation: fsPop .6s .15s cubic-bezier(.21, .98, .6, .99) both;
}}
.fs-preview-tag {{
  position: absolute;
  top: var(--fs-sp-3);
  inset-inline-start: var(--fs-sp-4);
  font-size: .68rem;
  font-weight: 700;
  color: var(--fs-deep);
  background: var(--fs-soft-purple);
  border: var(--fs-border-accent);
  border-radius: var(--fs-radius-pill);
  padding: 3px var(--fs-sp-3);
}}
.fs-preview-title {{
  font-size: .9rem;
  font-weight: 700;
  color: var(--fs-ink);
  margin: var(--fs-sp-6) 0 var(--fs-sp-1);
}}
.fs-preview-sub {{
  font-size: .76rem;
  color: var(--fs-muted);
}}
.fs-preview-kpis {{
  display: flex;
  gap: var(--fs-sp-2);
  margin: var(--fs-sp-3) 0 var(--fs-sp-1);
}}
.fs-mini-kpi {{
  flex: 1;
  background: var(--fs-surface2);
  border: var(--fs-border);
  border-radius: var(--fs-radius-sm);
  padding: var(--fs-sp-2) var(--fs-sp-3);
  transition: transform .2s ease, border-color .2s ease;
}}
.fs-mini-kpi:hover {{
  transform: translateY(-2px);
  border-color: rgba(98, 85, 231, .4);
}}
.fs-mini-kpi b {{
  display: block;
  font-size: .82rem;
  color: var(--fs-ink);
  font-weight: 800;
}}
.fs-mini-kpi span {{
  font-size: .68rem;
  color: var(--fs-muted);
  font-weight: 600;
}}
.fs-mini-kpi.up b {{ color: var(--fs-success); }}
.fs-mini-kpi.down b {{ color: var(--fs-danger); }}
.fs-preview-chart {{
  flex: 0 0 136px;
  display: flex;
  align-items: flex-end;
  gap: var(--fs-sp-2);
  height: 136px;
  min-height: 136px;
  padding: var(--fs-sp-3) var(--fs-sp-1) 0;
  border-top: 1px dashed var(--fs-line);
  margin-top: var(--fs-sp-3);
}}
.fs-bar {{
  flex: 1;
  border-radius: 7px 7px 2px 2px;
  transform-origin: bottom;
  background: linear-gradient(180deg, var(--fs-indigo-soft), var(--fs-primary));
  animation: fsGrow .8s cubic-bezier(.21, .98, .6, .99) both;
  min-height: 12%;
}}
.fs-bar.alt {{ background: linear-gradient(180deg, var(--fs-cyan-soft), var(--fs-secondary)); }}
.fs-bar:nth-child(1) {{ height: 42%; animation-delay: .35s; }}
.fs-bar:nth-child(2) {{ height: 66%; animation-delay: .45s; }}
.fs-bar:nth-child(3) {{ height: 34%; animation-delay: .55s; }}
.fs-bar:nth-child(4) {{ height: 82%; animation-delay: .65s; }}
.fs-bar:nth-child(5) {{ height: 58%; animation-delay: .75s; }}
.fs-bar:nth-child(6) {{ height: 96%; animation-delay: .85s; }}
.fs-preview-line {{
  margin-top: var(--fs-sp-3);
  font-size: .7rem;
  color: var(--fs-muted);
  text-align: center;
}}

/* == Headings & Section Labels == */
.sec-heading {{
  font-size: 1.38rem;
  font-weight: 800;
  color: var(--fs-ink);
  margin: var(--fs-sp-6) 0 var(--fs-sp-2);
  text-align: start;
}}
.block-container h1,
.block-container h2,
.block-container h3,
.block-container h4 {{
  color: var(--fs-ink) !important;
  line-height: 1.45;
  text-align: {text_align};
  font-weight: 800;
}}
.block-container h2 {{ font-size: 1.5rem; }}
.block-container h3 {{
  font-size: 1.24rem;
  position: relative;
  padding-inline-start: var(--fs-sp-3);
}}
.block-container h3::before {{
  content: "";
  position: absolute;
  inset-inline-start: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 4px;
  height: 18px;
  border-radius: 4px;
  background: linear-gradient(180deg, var(--fs-primary), var(--fs-cyan));
}}
.block-container p, .block-container li {{
  color: var(--fs-ink-body);
  font-size: 1rem;
  line-height: 1.85;
}}
.block-container strong, .block-container b {{ color: var(--fs-ink); }}
.stApp label, .stApp [data-testid="stWidgetLabel"] p {{
  font-size: .92rem !important;
  color: var(--fs-ink-body) !important;
  font-weight: 600 !important;
}}

/* == Upload Bordered Containers == */
[data-testid="stVerticalBlockBorderWrapper"] {{
  background: var(--fs-surface) !important;
  border: var(--fs-border) !important;
  border-radius: var(--fs-radius-lg) !important;
  box-shadow: var(--fs-shadow-sm) !important;
}}
.fs-card-title {{
  font-size: 1.2rem;
  font-weight: 800;
  color: var(--fs-ink);
  margin-bottom: var(--fs-sp-1);
}}
.fs-card-sub {{
  font-size: .95rem;
  color: var(--fs-muted);
  margin-bottom: var(--fs-sp-3);
}}
.fs-file-list {{
  display: flex;
  flex-direction: column;
  gap: var(--fs-sp-2);
  margin-top: var(--fs-sp-3);
  animation: fsUp .35s ease both;
}}
.fs-file-row {{
  display: flex;
  align-items: center;
  gap: var(--fs-sp-3);
  background: var(--fs-surface);
  border: var(--fs-border);
  border-radius: 12px;
  padding: var(--fs-sp-3) var(--fs-sp-4);
  box-shadow: var(--fs-shadow-sm);
  transition: border-color .2s ease, transform .2s ease;
}}
.fs-file-row:hover {{
  border-color: rgba(98, 85, 231, .4);
  transform: translateX({hover_shift});
}}
.fs-file-ico {{
  width: 38px;
  height: 38px;
  border-radius: var(--fs-radius-sm);
  flex: 0 0 auto;
  background: var(--fs-soft-purple);
  color: var(--fs-primary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}}
.fs-file-ico svg {{ width: 20px; height: 20px; }}
.fs-file-info {{
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}}
.fs-file-info b {{
  color: var(--fs-ink);
  font-size: .92rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}}
.fs-file-info span {{
  color: var(--fs-muted);
  font-size: .78rem;
}}
.fs-file-row .fs-gate {{ flex: 0 0 auto; }}

/* == File Uploader Dropzone (Arabic/English dynamic) == */
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] {{
  min-height: 188px !important;
  height: auto !important;
  border: 2px dashed rgba(98, 85, 231, .35) !important;
  border-radius: var(--fs-radius-lg) !important;
  background:
    radial-gradient(420px 180px at 50% 0%, rgba(98, 85, 231, .06), transparent 70%),
    var(--fs-surface2) !important;
  transition: border-color .22s ease, background .22s ease,
              box-shadow .22s ease, transform .22s ease !important;
  padding: var(--fs-sp-6) var(--fs-sp-4) !important;
  margin-inline: auto;
  display: flex !important;
  flex-direction: column !important;
  justify-content: center;
  align-items: center;
  font-size: 0;
  position: relative;
}}
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] svg,
[data-testid="stFileUploaderDropzoneInstructions"] {{
  display: none !important;
}}
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] button > * {{
  display: none !important;
}}
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] button::after {{
  content: "{drop_btn_text}";
  font-size: .95rem !important;
  font-weight: 700 !important;
  color: var(--fs-on-primary) !important;
  font-family: 'IBM Plex Sans Arabic', 'Inter', sans-serif;
}}
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"]::before {{
  content: "" !important;
  display: block !important;
  width: 56px !important;
  height: 46px !important;
  min-height: 46px !important;
  flex: 0 0 46px !important;
  margin-bottom: var(--fs-sp-3) !important;
  background: url("data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20viewBox='0%200%2024%2024'%20fill='none'%20stroke='%23{PRIMARY.lstrip('#')}'%20stroke-width='1.7'%20stroke-linecap='round'%20stroke-linejoin='round'%3E%3Cpath%20d='M20%2016.58A5%205%200%200%200%2018%207h-1.26A8%208%200%201%200%204%2015.25'/%3E%3Cpolyline%20points='16%2016%2012%2012%208%2016'/%3E%3Cline%20x1='12'%20y1='12'%20x2='12'%20y2='21'/%3E%3C/svg%3E") no-repeat center / contain !important;
  animation: fsFloat 3.5s ease-in-out infinite;
}}
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"]::after {{
  content: "{drop_body_text}";
  font-size: 1rem;
  font-weight: 700;
  color: var(--fs-ink);
  display: block;
  text-align: center;
  line-height: 1.8;
  white-space: pre-line;
  font-family: 'IBM Plex Sans Arabic', 'Inter', sans-serif;
  margin-bottom: var(--fs-sp-2);
}}
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"]:hover {{
  border-color: var(--fs-primary) !important;
  background: var(--fs-soft-purple) !important;
  box-shadow: 0 16px 36px -18px rgba(98, 85, 231, .4) !important;
  transform: translateY(-2px);
}}
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] button,
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] a {{
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  font-size: .9rem !important;
  background: var(--fs-primary) !important;
  color: var(--fs-on-primary) !important;
  border: none !important;
  border-radius: var(--fs-radius-sm) !important;
  font-weight: 700 !important;
  padding: var(--fs-sp-2) var(--fs-sp-6) !important;
  margin-top: var(--fs-sp-2) !important;
  box-shadow: 0 8px 20px -10px rgba(98, 85, 231, .5) !important;
}}
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzoneFileList"],
[data-testid="stFileUploader"] [data-testid="stFileUploaderFileList"] {{
  font-size: .9rem;
}}

/* == Radio Mode Cards (scoped strictly to stRadio, never stToggle) == */
[data-testid="stRadio"] label[data-rac] {{
  border: var(--fs-border) !important;
  border-radius: 12px !important;
  padding: var(--fs-sp-3) var(--fs-sp-4) !important;
  margin: var(--fs-sp-1) 0 !important;
  width: 100% !important;
  background: var(--fs-surface) !important;
  cursor: pointer !important;
  transition: all .18s ease !important;
  display: flex !important;
  font-size: 0;
}}
[data-testid="stRadio"] label[data-rac]:hover {{
  border-color: var(--fs-primary) !important;
  box-shadow: var(--fs-shadow-sm);
}}
[data-testid="stRadio"] label[data-rac][data-selected="true"] {{
  border-color: var(--fs-primary) !important;
  background: var(--fs-soft-purple) !important;
  box-shadow: 0 0 0 1px var(--fs-primary), var(--fs-shadow-sm) !important;
}}
[data-testid="stRadio"] label[data-rac] > span:first-child {{ position: absolute; opacity: 0; }}

/* == Buttons == */
.stApp .stButton > button,
.stApp .stDownloadButton > button {{
  border-radius: 12px !important;
  font-weight: 700 !important;
  border: var(--fs-border) !important;
  background: var(--fs-surface) !important;
  color: var(--fs-ink) !important;
  font-size: .94rem !important;
  min-height: 42px !important;
  transition: all .2s cubic-bezier(.21, .98, .6, .99) !important;
}}
.stApp .stButton > button:hover,
.stApp .stDownloadButton > button:hover {{
  border-color: var(--fs-primary) !important;
  color: var(--fs-primary) !important;
  transform: translateY(-2px) !important;
  box-shadow: var(--fs-shadow-md) !important;
}}
.stApp .stButton > button[kind="primary"],
.stApp .stButton > button[data-testid="stBaseButton-primary"] {{
  background: linear-gradient(110deg, var(--fs-secondary) 0%, var(--fs-primary-mid) 50%, var(--fs-cyan) 100%) !important;
  background-size: 165% 100% !important;
  color: var(--fs-on-primary) !important;
  border: 1px solid rgba(255, 255, 255, .32) !important;
  border-radius: 14px !important;
  padding: 13px var(--fs-sp-6) !important;
  min-height: 48px !important;
  font-size: 1.05rem !important;
  font-weight: 800 !important;
  box-shadow: 0 12px 28px -10px rgba(8, 145, 178, .42), 0 6px 18px -8px rgba(124, 111, 232, .38) !important;
  position: relative;
  overflow: hidden;
}}
.stApp .stButton > button[kind="primary"] *,
.stApp .stButton > button[data-testid="stBaseButton-primary"] * {{
  color: var(--fs-on-primary) !important;
  font-weight: 800 !important;
  background: transparent !important;
}}
.stApp .stButton > button[kind="primary"]::after,
.stApp .stButton > button[data-testid="stBaseButton-primary"]::after {{
  content: "";
  position: absolute;
  top: 0;
  bottom: 0;
  width: 40%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, .28), transparent);
  animation: fsShine 3.4s ease-in-out infinite;
}}
.stApp .stButton > button[kind="primary"]:hover,
.stApp .stButton > button[data-testid="stBaseButton-primary"]:hover {{
  background-position: 100% 0 !important;
  transform: translateY(-2px) !important;
  box-shadow: 0 16px 36px -10px rgba(34, 211, 238, .52), 0 10px 24px -10px rgba(124, 111, 232, .48) !important;
}}
.stApp .stButton > button[kind="primary"]:active,
.stApp .stButton > button[data-testid="stBaseButton-primary"]:active {{
  transform: translateY(1px) scale(.99) !important;
  box-shadow: 0 6px 16px -10px rgba(8, 145, 178, .45) !important;
}}
.stApp .stButton > button[kind="primary"]:disabled,
.stApp .stButton > button[data-testid="stBaseButton-primary"]:disabled {{
  background: var(--fs-disabled-bg) !important;
  color: var(--fs-disabled-ink) !important;
  border-color: var(--fs-line) !important;
  box-shadow: none !important;
  transform: none !important;
}}
.stApp .stButton > button[kind="primary"]:disabled *,
.stApp .stButton > button[data-testid="stBaseButton-primary"]:disabled * {{
  color: var(--fs-disabled-ink) !important;
}}
.stApp .stButton > button[kind="primary"]:disabled::after,
.stApp .stButton > button[data-testid="stBaseButton-primary"]:disabled::after {{
  display: none;
}}

/* == Landing Feature & Step Cards == */
.fs-feature {{
  position: relative;
  overflow: hidden;
  height: 100%;
  background: var(--fs-surface);
  border: var(--fs-border);
  border-radius: var(--fs-radius);
  padding: var(--fs-sp-4) var(--fs-sp-4);
  box-shadow: var(--fs-shadow-sm);
  animation: fsUp .55s both;
  transition: all .25s ease;
}}
.fs-feature::before {{
  content: "";
  position: absolute;
  inset: 0 0 auto 0;
  height: 3px;
  background: linear-gradient(90deg, var(--fs-primary), var(--fs-cyan));
  opacity: 0;
  transition: opacity .25s ease;
}}
.fs-feature:hover::before {{ opacity: 1; }}
.fs-feature:hover {{
  transform: translateY(-5px) !important;
  border-color: rgba(98, 85, 231, .45) !important;
  box-shadow: var(--fs-shadow-lg) !important;
}}
.fs-feature-ico {{
  width: 42px;
  height: 42px;
  border-radius: 11px;
  background: var(--fs-soft-purple);
  color: var(--fs-primary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-bottom: var(--fs-sp-3);
  transition: transform .25s ease, background .25s ease;
}}
.fs-feature-ico svg {{ width: 22px; height: 22px; }}
.fs-feature:hover .fs-feature-ico {{
  transform: scale(1.08) rotate(-4deg);
  background: var(--fs-soft-cyan);
  color: var(--fs-secondary);
}}
.fs-feature b {{
  color: var(--fs-ink);
  font-size: 1.02rem;
  font-weight: 800;
  display: block;
  margin-bottom: var(--fs-sp-1);
}}
.fs-feature span {{
  color: var(--fs-muted);
  font-size: .9rem;
  line-height: 1.75;
}}
.step-card {{
  background: var(--fs-surface);
  border: var(--fs-border);
  border-radius: var(--fs-radius);
  padding: var(--fs-sp-4) var(--fs-sp-3);
  text-align: center;
  position: relative;
  overflow: hidden;
  box-shadow: var(--fs-shadow-sm);
  height: 100%;
  transition: transform .22s ease, border-color .22s ease, box-shadow .22s ease;
}}
.step-card:hover {{
  transform: translateY(-4px);
  border-color: rgba(98, 85, 231, .45);
  box-shadow: var(--fs-shadow-md);
}}
.step-num {{
  position: absolute;
  top: var(--fs-sp-2);
  inset-inline-start: var(--fs-sp-3);
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--fs-primary);
  color: var(--fs-on-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  font-size: .82rem;
}}
.step-card b {{ color: var(--fs-ink); font-size: .96rem; }}
.step-card span {{ color: var(--fs-muted); font-size: .84rem; }}

/* == Unified Reusable Cards (Header + Big Value + Explanation + Colored Status) == */
.fs-kpi-grid {{
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--fs-sp-4);
  margin: var(--fs-sp-3) 0;
}}
.fs-stats-grid {{
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--fs-sp-4);
  margin: var(--fs-sp-3) 0;
}}
.fs-kpi {{
  display: flex;
  flex-direction: column;
  height: 100%;
  min-width: 0;
  background: var(--fs-surface);
  border: var(--fs-border);
  border-radius: var(--fs-radius-lg);
  padding: var(--fs-sp-4) var(--fs-sp-4);
  box-shadow: var(--fs-shadow-sm);
  animation: fsPop .45s cubic-bezier(.21, .98, .6, .99) both;
  transition: transform .2s ease, box-shadow .2s ease, border-color .2s ease;
}}
.fs-kpi:hover {{
  transform: translateY(-3px);
  border-color: rgba(98, 85, 231, .42);
  box-shadow: var(--fs-shadow-md);
}}
.fs-kpi-head {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--fs-sp-2);
}}
.fs-kpi-label {{
  font-size: .82rem;
  font-weight: 700;
  color: var(--fs-muted);
  line-height: 1.4;
}}
.fs-kpi-year {{
  font-size: .72rem;
  font-weight: 700;
  color: var(--fs-deep);
  background: var(--fs-soft-purple);
  padding: 2px var(--fs-sp-2);
  border-radius: var(--fs-radius-pill);
  flex: 0 0 auto;
}}
.fs-kpi-value {{
  font-family: 'Inter', 'IBM Plex Sans Arabic', sans-serif;
  font-variant-numeric: tabular-nums;
  font-size: clamp(1.25rem, 1.8vw, 1.68rem);
  font-weight: 800;
  color: var(--fs-ink);
  margin-top: var(--fs-sp-2);
  line-height: 1.3;
  overflow-wrap: anywhere;
}}
.fs-kpi-value bdi {{
  direction: ltr;
  unicode-bidi: isolate;
  display: inline-block;
}}
.fs-kpi-value.is-na {{
  color: var(--fs-muted);
}}
.fs-kpi-sub {{
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--fs-sp-2);
  margin-top: var(--fs-sp-2);
}}
.fs-kpi-delta {{
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: .78rem;
  font-weight: 700;
  padding: 3px var(--fs-sp-3);
  border-radius: var(--fs-radius-pill);
  line-height: 1.4;
}}
.fs-kpi-delta bdi {{
  direction: ltr;
  unicode-bidi: isolate;
  display: inline-block;
}}
.fs-kpi .up {{ color: var(--fs-success); background: var(--fs-success-bg); }}
.fs-kpi .down {{ color: var(--fs-danger); background: var(--fs-danger-bg); }}
.fs-kpi .flat {{ color: var(--fs-muted); background: var(--fs-neutral-bg); }}
.fs-kpi .na {{ color: var(--fs-muted); background: var(--fs-surface2); }}
.fs-kpi-explain {{
  font-size: .78rem;
  color: var(--fs-muted);
  line-height: 1.5;
  margin-top: var(--fs-sp-1);
  margin-bottom: var(--fs-sp-3);
}}
.fs-kpi-foot {{
  margin-top: auto;
  padding-top: var(--fs-sp-3);
  border-top: 1px dashed var(--fs-line);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--fs-sp-2);
}}
.fs-num {{
  font-family: 'Inter', 'IBM Plex Sans Arabic', sans-serif;
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  color: var(--fs-ink);
  direction: ltr;
  unicode-bidi: isolate;
  display: inline-block;
}}

/* == Gate & Verification Status Badges (Strict Semantic Contract) == */
.fs-gate {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: .74rem;
  font-weight: 700;
  padding: 3px var(--fs-sp-3);
  border-radius: var(--fs-radius-pill);
  white-space: nowrap;
  line-height: 1.45;
}}
.fs-gate.ok   {{ color: var(--fs-success); background: var(--fs-success-bg); border: 1px solid var(--fs-success-border); }}
.fs-gate.pend {{ color: var(--fs-warning-text); background: var(--fs-warning-bg); border: 1px solid var(--fs-warning-border); }}
.fs-gate.miss {{ color: var(--fs-muted); background: var(--fs-neutral-bg); border: var(--fs-border); }}
.fs-gate.bad  {{ color: var(--fs-danger); background: var(--fs-danger-bg); border: 1px solid var(--fs-danger-border); }}

/* == Multi-Minute Waiting & Progress Screen == */
.fs-progress-card {{
  background: var(--fs-surface);
  border: var(--fs-border-accent);
  border-radius: var(--fs-radius-lg);
  padding: var(--fs-sp-4) var(--fs-sp-6);
  box-shadow: var(--fs-shadow-md);
  margin: var(--fs-sp-2) 0;
}}
.fs-progress-head {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--fs-sp-3);
  margin-bottom: var(--fs-sp-3);
}}
.fs-progress-title {{
  font-size: 1rem;
  font-weight: 800;
  color: var(--fs-ink);
}}
.fs-progress-file {{
  font-size: .82rem;
  color: var(--fs-muted);
  margin-top: 2px;
}}
.fs-timer-pill {{
  display: inline-flex;
  align-items: center;
  gap: var(--fs-sp-2);
  padding: var(--fs-sp-1) var(--fs-sp-3);
  border-radius: var(--fs-radius-pill);
  background: var(--fs-soft-purple);
  color: var(--fs-deep);
  border: var(--fs-border-accent);
  font-family: 'Inter', 'IBM Plex Sans Arabic', sans-serif;
  font-variant-numeric: tabular-nums;
  font-size: .88rem;
  font-weight: 800;
}}
.fs-progress-meta {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: .8rem;
  font-weight: 700;
  color: var(--fs-muted);
  margin-bottom: var(--fs-sp-2);
}}
.fs-progress-track {{
  width: 100%;
  height: 11px;
  border-radius: var(--fs-radius-pill);
  background: var(--fs-surface2);
  border: var(--fs-border);
  overflow: hidden;
  position: relative;
}}
.fs-progress-fill {{
  height: 100%;
  border-radius: var(--fs-radius-pill);
  background: linear-gradient(90deg, var(--fs-primary), var(--fs-secondary));
  transition: width .35s ease;
  position: relative;
  overflow: hidden;
}}
.fs-progress-fill::after {{
  content: "";
  position: absolute;
  inset: 0;
  width: 45%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, .42), transparent);
  animation: fsBarShimmer 1.8s ease-in-out infinite;
}}
.fs-stages {{
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--fs-sp-2);
  margin-top: var(--fs-sp-4);
}}
.fs-stage {{
  display: flex;
  align-items: center;
  gap: var(--fs-sp-2);
  padding: var(--fs-sp-2) var(--fs-sp-3);
  border-radius: var(--fs-radius-sm);
  border: var(--fs-border);
  background: var(--fs-bg);
  font-size: .78rem;
  font-weight: 600;
  color: var(--fs-muted);
}}
.fs-stage.done {{
  background: var(--fs-success-bg);
  border-color: var(--fs-success-border);
  color: var(--fs-success);
}}
.fs-stage.active {{
  background: var(--fs-soft-purple);
  border-color: rgba(98, 85, 231, .45);
  color: var(--fs-deep);
  font-weight: 800;
}}
.fs-stage-dot {{
  width: 18px;
  height: 18px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: .7rem;
  font-weight: 800;
  flex: 0 0 auto;
  background: var(--fs-line);
  color: var(--fs-muted);
}}
.fs-stage.done .fs-stage-dot {{
  background: var(--fs-success);
  color: var(--fs-on-primary);
}}
.fs-stage.active .fs-stage-dot {{
  background: var(--fs-primary);
  color: var(--fs-on-primary);
  animation: fsPulse 1.8s infinite;
}}
.fs-progress-msg {{
  margin-top: var(--fs-sp-3);
  padding: var(--fs-sp-2) var(--fs-sp-3);
  border-radius: var(--fs-radius-sm);
  background: var(--fs-surface2);
  border-inline-start: 3px solid var(--fs-primary);
  color: var(--fs-ink);
  font-size: .88rem;
  font-weight: 600;
  line-height: 1.6;
}}
.fs-progress-hint {{
  margin-top: var(--fs-sp-2);
  font-size: .78rem;
  color: var(--fs-muted);
}}

/* == Health Score Tab: Hero + 4 Weighted Pillar Progress Bars == */
.fs-health-hero {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--fs-sp-4);
  background: linear-gradient(135deg, var(--fs-soft-purple), var(--fs-surface) 60%);
  border: var(--fs-border-accent);
  border-radius: var(--fs-radius-lg);
  padding: var(--fs-sp-4) var(--fs-sp-6);
  box-shadow: var(--fs-shadow-sm);
  margin-bottom: var(--fs-sp-4);
}}
.fs-health-score-box {{
  display: flex;
  align-items: baseline;
  gap: var(--fs-sp-2);
}}
.fs-health-num {{
  font-family: 'Inter', sans-serif;
  font-variant-numeric: tabular-nums;
  font-size: 2.5rem;
  font-weight: 800;
  color: var(--fs-deep);
  line-height: 1;
}}
.fs-health-denom {{
  font-size: 1rem;
  font-weight: 700;
  color: var(--fs-muted);
}}
.fs-health-meta {{
  flex: 1;
  min-width: 220px;
}}
.fs-health-meta-title {{
  font-size: 1.08rem;
  font-weight: 800;
  color: var(--fs-ink);
  margin-bottom: var(--fs-sp-1);
}}
.fs-health-meta-sub {{
  font-size: .84rem;
  color: var(--fs-muted);
  line-height: 1.6;
}}
.fs-pillars-grid {{
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--fs-sp-4);
  margin: var(--fs-sp-3) 0;
}}
.fs-pillar-card {{
  background: linear-gradient(180deg, var(--fs-surface), var(--fs-bg));
  border: var(--fs-border);
  border-inline-start: 5px solid var(--fs-primary);
  border-radius: var(--fs-radius-lg);
  padding: var(--fs-sp-4) var(--fs-sp-4);
  box-shadow: var(--fs-shadow-md);
  display: flex;
  flex-direction: column;
  gap: var(--fs-sp-3);
  transition: transform .2s ease, box-shadow .2s ease;
}}
.fs-pillar-card:hover {{
  transform: translateY(-2px);
  box-shadow: var(--fs-shadow-lg);
}}
.fs-pillar-card.tone-ok   {{ border-inline-start-color: var(--fs-success); }}
.fs-pillar-card.tone-mid  {{ border-inline-start-color: var(--fs-secondary); }}
.fs-pillar-card.tone-warn {{ border-inline-start-color: var(--fs-warning); }}
.fs-pillar-card.tone-bad  {{ border-inline-start-color: var(--fs-danger); }}
.fs-pillar-card.tone-miss {{ border-inline-start-color: var(--fs-disabled-ink); }}
.fs-pillar-head {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--fs-sp-2);
  padding-bottom: var(--fs-sp-2);
  border-bottom: 1px dashed var(--fs-line);
}}
.fs-pillar-name {{
  font-size: 1.06rem;
  font-weight: 800;
  color: var(--fs-ink);
  display: inline-flex;
  align-items: center;
  gap: 6px;
}}
.fs-pillar-weight {{
  font-size: .76rem;
  font-weight: 800;
  color: var(--fs-deep);
  background: var(--fs-soft-purple);
  border: var(--fs-border-accent);
  border-radius: var(--fs-radius-pill);
  padding: 3px var(--fs-sp-3);
  white-space: nowrap;
}}
.fs-pillar-score-row {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--fs-sp-2);
}}
.fs-pillar-score {{
  font-family: 'Inter', 'IBM Plex Sans Arabic', sans-serif;
  font-variant-numeric: tabular-nums;
  font-size: 1.55rem;
  font-weight: 800;
  color: var(--fs-ink);
}}
.fs-pillar-track {{
  width: 100%;
  height: 12px;
  border-radius: var(--fs-radius-pill);
  background: var(--fs-track-bg);
  border: var(--fs-border);
  overflow: hidden;
}}
.fs-pillar-fill {{
  height: 100%;
  border-radius: var(--fs-radius-pill);
  transition: width .45s ease;
}}
.fs-pillar-fill.tone-ok   {{ background: linear-gradient(90deg, var(--fs-success-light), var(--fs-success)); }}
.fs-pillar-fill.tone-mid  {{ background: linear-gradient(90deg, var(--fs-primary-mid), var(--fs-secondary), var(--fs-cyan)); }}
.fs-pillar-fill.tone-warn {{ background: linear-gradient(90deg, var(--fs-warning-light), var(--fs-warning)); }}
.fs-pillar-fill.tone-bad  {{ background: linear-gradient(90deg, var(--fs-danger-light), var(--fs-danger)); }}
.fs-pillar-fill.tone-miss {{ background: var(--fs-line); }}
.fs-pillar-details {{
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 2px;
}}
.fs-detail-chip {{
  font-size: .78rem;
  font-weight: 600;
  color: var(--fs-ink);
  background: var(--fs-surface2);
  border: var(--fs-border-accent);
  border-radius: 9px;
  padding: 4px 10px;
  line-height: 1.5;
}}

/* == Statement Cell Row Cards (القوائم والخانات) == */
.fs-stmt-row {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--fs-sp-3);
  padding: var(--fs-sp-2) var(--fs-sp-3);
  border-radius: var(--fs-radius);
  background: linear-gradient(90deg, var(--fs-surface), var(--fs-bg));
  border-inline-start: 4px solid var(--fs-primary);
}}
.fs-stmt-row.is-ok   {{ border-inline-start-color: var(--fs-success); }}
.fs-stmt-row.is-pend {{ border-inline-start-color: var(--fs-warning); }}
.fs-stmt-row.is-miss {{ border-inline-start-color: var(--fs-disabled-ink); }}
.fs-stmt-title {{
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 1.02rem;
  font-weight: 800;
  color: var(--fs-ink);
}}
.fs-stmt-year {{
  font-size: .76rem;
  font-weight: 800;
  color: var(--fs-deep);
  background: var(--fs-soft-purple);
  border: var(--fs-border-accent);
  border-radius: var(--fs-radius-pill);
  padding: 2px 10px;
}}
.fs-stmt-val {{
  font-family: 'Inter', 'IBM Plex Sans Arabic', sans-serif;
  font-variant-numeric: tabular-nums;
  font-size: 1.12rem;
  font-weight: 800;
  color: var(--fs-deep);
  background: var(--fs-surface2);
  border: var(--fs-border-accent);
  border-radius: 10px;
  padding: 4px 14px;
}}
.fs-stmt-reason {{
  margin-top: 6px;
  padding: 5px 10px;
  border-radius: 8px;
  background: var(--fs-warning-bg);
  border: 1px solid var(--fs-warning-border);
  color: var(--fs-ink-body);
  font-size: .8rem;
  font-weight: 600;
  line-height: 1.55;
}}

/* == Insights Cards == */
.fs-insight-grid {{
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--fs-sp-3);
  margin: var(--fs-sp-2) 0 var(--fs-sp-4);
}}
.fs-insight-card {{
  background: var(--fs-surface);
  border: var(--fs-border);
  border-inline-start: 4px solid var(--fs-primary);
  border-radius: var(--fs-radius);
  padding: var(--fs-sp-3) var(--fs-sp-4);
  box-shadow: var(--fs-shadow-sm);
  display: flex;
  flex-direction: column;
  gap: var(--fs-sp-2);
  height: 100%;
}}
.fs-insight-card.is-pos {{ border-inline-start-color: var(--fs-success); }}
.fs-insight-card.is-neg {{ border-inline-start-color: var(--fs-danger); }}
.fs-insight-card.is-neu {{ border-inline-start-color: var(--fs-secondary); }}
.fs-insight-card.is-rec {{ border-inline-start-color: var(--fs-primary); background: linear-gradient(180deg, var(--fs-surface), var(--fs-bg)); }}
.fs-insight-head {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--fs-sp-2);
}}
.fs-insight-title {{
  font-size: .95rem;
  font-weight: 800;
  color: var(--fs-ink);
}}
.fs-insight-body {{
  font-size: .9rem;
  color: var(--fs-ink-body);
  line-height: 1.75;
}}

/* == Financial Tables (RTL/LTR Sticky Headers & Isolated Numbers) == */
.table-wrap,
.fin-table-wrap {{
  max-height: 560px;
  width: 100%;
  overflow: auto;
  -webkit-overflow-scrolling: touch;
  border-radius: var(--fs-radius);
  border: var(--fs-border-accent);
  background: var(--fs-surface);
  box-shadow: var(--fs-shadow-md);
  margin: var(--fs-sp-2) 0;
}}
.fin-table {{
  width: 100%;
  min-width: 640px;
  border-collapse: separate;
  border-spacing: 0;
  font-size: .92rem;
  direction: {direction};
}}
.fin-table thead th {{
  position: sticky;
  top: 0;
  z-index: 2;
  background: linear-gradient(90deg, var(--fs-primary), var(--fs-deep));
  color: var(--fs-on-primary);
  font-size: .84rem;
  font-weight: 800;
  letter-spacing: .02em;
  padding: 12px 14px;
  border-bottom: 2px solid var(--fs-primary-dark);
  text-align: start;
  white-space: nowrap;
}}
.fin-table thead th.num {{
  text-align: end;
}}
.fin-table tbody td {{
  padding: 12px 14px;
  border-top: 1px solid var(--fs-line);
  color: var(--fs-ink);
  font-weight: 600;
  line-height: 1.65;
  text-align: start;
  vertical-align: middle;
  min-width: 105px;
}}
.fin-table tbody td.num {{
  text-align: end;
  font-family: 'Inter', 'IBM Plex Sans Arabic', sans-serif;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  min-width: 90px;
}}
.fin-table tbody td.num bdi {{
  direction: ltr;
  unicode-bidi: isolate;
  display: inline-block;
  font-variant-numeric: tabular-nums;
}}
bdi[dir="ltr"] {{
  direction: ltr;
  unicode-bidi: isolate;
}}
.fin-table tbody tr {{
  transition: background .15s ease;
}}
.fin-table tbody tr:nth-child(even) {{
  background: var(--fs-bg);
}}
.fin-table tbody tr:hover {{
  background: var(--fs-row-hover);
}}
.fin-table td.cat {{
  color: var(--fs-deep);
  font-size: .82rem;
  font-weight: 800;
  white-space: nowrap;
}}
.badge {{
  display: inline-block;
  padding: 3px var(--fs-sp-3);
  border-radius: var(--fs-radius-pill);
  font-size: .75rem;
  font-weight: 700;
  white-space: nowrap;
}}
.badge.pos, .badge-pass {{ color: var(--fs-success); background: var(--fs-success-bg); border: 1px solid var(--fs-success-border); }}
.badge.neg {{ color: var(--fs-danger); background: var(--fs-danger-bg); border: 1px solid var(--fs-danger-border); }}
.badge.neu {{ color: var(--fs-ink-body); background: var(--fs-neutral-bg); border: var(--fs-border); }}
.badge.na, .badge-warn {{ color: var(--fs-warning-text); background: var(--fs-warning-bg); border: 1px solid var(--fs-warning-border); }}
.trend-up {{ color: var(--fs-success); font-weight: 700; white-space: nowrap; }}
.trend-down {{ color: var(--fs-danger); font-weight: 700; white-space: nowrap; }}
.trend-flat {{ color: var(--fs-muted); font-weight: 700; white-space: nowrap; }}
.change-pos {{ color: var(--fs-success); font-weight: 700; }}
.change-neg {{ color: var(--fs-danger); font-weight: 700; }}

/* == Designed States (Empty / Error / Success / Info) == */
.fs-state {{
  border-radius: var(--fs-radius-lg);
  padding: var(--fs-sp-6) var(--fs-sp-6);
  text-align: center;
  border: var(--fs-border);
  background: var(--fs-surface);
  box-shadow: var(--fs-shadow-sm);
  margin: var(--fs-sp-3) 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--fs-sp-2);
}}
.fs-state .fs-state-ico {{
  width: 52px;
  height: 52px;
  border-radius: 14px;
  background: var(--fs-soft-purple);
  color: var(--fs-primary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 1.5rem;
  margin-bottom: var(--fs-sp-1);
}}
.fs-state .fs-state-title {{
  font-size: 1.04rem;
  font-weight: 800;
  color: var(--fs-ink);
}}
.fs-state .fs-state-body {{
  color: var(--fs-muted);
  font-size: .92rem;
  line-height: 1.8;
  max-width: 620px;
}}
.fs-state-next {{
  margin-top: var(--fs-sp-1);
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px var(--fs-sp-3);
  border-radius: var(--fs-radius-pill);
  background: var(--fs-surface2);
  border: var(--fs-border-accent);
  color: var(--fs-deep);
  font-size: .8rem;
  font-weight: 700;
}}
.fs-state.empty {{ border-style: dashed; border-color: rgba(98, 85, 231, .32); }}
.fs-state.error {{ border-color: var(--fs-danger-border); background: var(--fs-danger-bg); }}
.fs-state.error .fs-state-ico {{ background: var(--fs-danger-soft); color: var(--fs-danger); }}
.fs-state.success {{ border-color: var(--fs-success-border); background: var(--fs-success-bg); }}
.fs-state.success .fs-state-ico {{ background: var(--fs-success-soft); color: var(--fs-success); }}

/* == Sidebar == */
section[data-testid="stSidebar"] {{
  background: linear-gradient(180deg, var(--fs-surface), var(--fs-sidebar-bg-end)) !important;
  border-inline-start: none !important;
  border-inline-end: var(--fs-border) !important;
}}
section[data-testid="stSidebar"][aria-expanded="false"],
section[data-testid="stSidebar"][aria-expanded="false"] > div,
section[data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarContent"],
section[data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarUserContent"] {{
  width: 0 !important;
  min-width: 0 !important;
  max-width: 0 !important;
  padding: 0 !important;
  margin: 0 !important;
  border-inline-end: none !important;
  overflow: hidden !important;
  visibility: hidden !important;
  opacity: 0 !important;
  pointer-events: none !important;
  display: none !important;
}}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{
  color: var(--fs-ink-body) !important;
}}
section[data-testid="stSidebar"] .fs-brand-name,
section[data-testid="stSidebar"] h3 {{ color: var(--fs-ink) !important; }}
section[data-testid="stSidebar"] hr {{ border-color: var(--fs-line) !important; }}
section[data-testid="stSidebar"] .stTextInput input {{
  background: var(--fs-surface) !important;
  border: var(--fs-border) !important;
  color: var(--fs-ink) !important;
}}
section[data-testid="stSidebar"] .stButton > button {{
  background: var(--fs-surface) !important;
  border: var(--fs-border) !important;
  color: var(--fs-ink-body) !important;
}}
section[data-testid="stSidebar"] .stButton > button:hover {{
  border-color: var(--fs-primary) !important;
  color: var(--fs-primary) !important;
}}
section[data-testid="stSidebar"] .stButton > button[kind="primary"],
section[data-testid="stSidebar"] .stButton > button[data-testid="stBaseButton-primary"] {{
  background: linear-gradient(90deg, var(--fs-primary), var(--fs-deep)) !important;
  color: var(--fs-on-primary) !important;
  border: none !important;
}}
section[data-testid="stSidebar"] .stButton > button[kind="primary"] *,
section[data-testid="stSidebar"] .stButton > button[data-testid="stBaseButton-primary"] * {{
  background: transparent !important;
  color: var(--fs-on-primary) !important;
  border: none !important;
}}

/* == Tabs == */
.stTabs [data-baseweb="tab-list"] {{
  gap: 6px;
  border-bottom: var(--fs-border);
  padding-bottom: var(--fs-sp-2);
  overflow-x: auto;
  flex-wrap: nowrap;
  scrollbar-width: none;
}}
.stTabs [data-baseweb="tab-list"]::-webkit-scrollbar {{ display: none; }}
.stTabs [data-baseweb="tab"] {{
  border-radius: var(--fs-radius-pill) !important;
  padding: 7px 18px !important;
  padding-inline: 18px !important;
  color: var(--fs-muted) !important;
  font-weight: 600 !important;
  white-space: nowrap !important;
  flex: 0 0 auto !important;
  transition: all .18s ease !important;
}}
.stTabs [data-baseweb="tab"] p {{ color: inherit !important; }}
.stTabs [data-baseweb="tab"]:hover {{
  background: rgba(98, 85, 231, .09) !important;
  color: var(--fs-ink) !important;
}}
.stTabs [aria-selected="true"] {{
  background: linear-gradient(90deg, var(--fs-primary), var(--fs-deep)) !important;
  padding-inline: 18px !important;
}}
.stTabs [aria-selected="true"] p {{
  color: var(--fs-on-primary) !important;
  font-weight: 700 !important;
}}
.stTabs [data-baseweb="tab-highlight"],
.stTabs [data-baseweb="tab-border"] {{ display: none !important; }}

/* == Classic UI Shared Cards (RTL/LTR clean) == */
.kpi-card {{
  position: relative;
  background: var(--fs-surface);
  border: var(--fs-border);
  border-radius: var(--fs-radius);
  padding: var(--fs-sp-4);
  padding-inline-start: 20px;
  overflow: hidden;
  box-shadow: var(--fs-shadow-sm);
  height: 100%;
  transition: transform .22s ease, box-shadow .22s ease, border-color .22s ease;
}}
.kpi-card::before {{
  content: "";
  position: absolute;
  inset-block: 0;
  inset-inline-start: 0;
  width: 5px;
  background: var(--accent, var(--fs-primary));
}}
.kpi-card:hover {{
  transform: translateY(-4px);
  box-shadow: var(--fs-shadow-md);
}}
.kpi-label {{ font-size: .8rem; font-weight: 700; color: var(--fs-muted); }}
.kpi-value {{
  font-family: 'Inter', 'IBM Plex Sans Arabic', sans-serif;
  font-variant-numeric: tabular-nums;
  font-size: 1.65rem;
  font-weight: 800;
  margin-top: var(--fs-sp-1);
  color: var(--fs-ink);
}}
.kpi-card.info .kpi-value {{ font-size: 1.15rem; font-weight: 700; }}
.kpi-delta {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: var(--fs-sp-2);
  font-weight: 700;
  font-size: .78rem;
  padding: 3px var(--fs-sp-3);
  border-radius: var(--fs-radius-pill);
}}
.kpi-delta.up   {{ color: var(--fs-success); background: var(--fs-success-bg); }}
.kpi-delta.down {{ color: var(--fs-danger); background: var(--fs-danger-bg); }}
.kpi-delta.flat {{ color: var(--fs-muted); background: var(--fs-neutral-bg); }}
.kpi-delta.na   {{ color: var(--fs-muted); background: var(--fs-surface2); }}

.report-card {{
  background: var(--fs-surface);
  border: var(--fs-border);
  border-inline-start: 5px solid var(--accent, var(--fs-primary));
  border-radius: var(--fs-radius);
  padding: var(--fs-sp-4) var(--fs-sp-6);
  margin: var(--fs-sp-3) 0;
  box-shadow: var(--fs-shadow-sm);
  transition: transform .2s ease, box-shadow .2s ease;
}}
.report-card:hover {{
  transform: translateY(-2px);
  box-shadow: var(--fs-shadow-md);
}}
.rc-title {{
  display: flex;
  align-items: center;
  gap: var(--fs-sp-2);
  font-weight: 800;
  font-size: 1.02rem;
  color: var(--fs-ink);
  margin-bottom: var(--fs-sp-2);
}}
.rc-title .rc-ico {{ font-size: 1.12rem; }}
.report-card p {{ margin-bottom: 0; color: var(--fs-ink-body); line-height: 1.7; }}
.ratio-line {{
  padding: var(--fs-sp-2) 2px;
  border-bottom: 1px dashed var(--fs-line);
  color: var(--fs-ink-body);
  line-height: 1.75;
}}
.ratio-line:last-child {{ border-bottom: none; }}
.ratio-name {{ font-weight: 700; color: var(--fs-deep); margin-inline-end: 6px; }}
.ratio-name::after {{ content: ":"; }}

.sw-card {{
  border-radius: var(--fs-radius);
  border: var(--fs-border);
  background: var(--fs-surface);
  padding: var(--fs-sp-4);
  height: 100%;
  box-shadow: var(--fs-shadow-sm);
}}
.sw-card.strengths {{ border-top: 4px solid var(--fs-success); }}
.sw-card.weaknesses {{ border-top: 4px solid var(--fs-danger); }}
.sw-card.risks {{ border-top: 4px solid var(--fs-warning); }}
.sw-card.recs {{ border-top: 4px solid var(--fs-primary); }}
.sw-card ul, .sw-card ol {{
  padding-inline-start: 22px;
  margin: var(--fs-sp-2) 0 0;
}}
.sw-card li {{
  margin-bottom: var(--fs-sp-2);
  color: var(--fs-ink-body);
  line-height: 1.65;
}}
.rec-evidence {{
  font-size: .82rem;
  color: var(--fs-ink-body);
  margin-top: var(--fs-sp-1);
  background: var(--fs-bg);
  border: var(--fs-border);
  border-inline-start: 3px solid var(--fs-primary);
  border-radius: 8px;
  padding: 5px var(--fs-sp-3);
  line-height: 1.55;
}}

/* == Charts, Inputs, Expanders, Footer == */
[data-testid="stPlotlyChart"] {{
  background: var(--fs-surface);
  border: var(--fs-border);
  border-radius: var(--fs-radius);
  padding: var(--fs-sp-3) var(--fs-sp-2) var(--fs-sp-1);
  box-shadow: var(--fs-shadow-sm);
}}
.stApp input, .stApp textarea,
.stApp [data-baseweb="select"] > div {{
  border-radius: var(--fs-radius-sm) !important;
  border: var(--fs-border) !important;
  background: var(--fs-surface) !important;
  color: var(--fs-ink) !important;
}}
.stApp input:focus, .stApp textarea:focus {{
  border-color: var(--fs-primary) !important;
  box-shadow: var(--fs-focus-ring) !important;
}}
.stApp [data-testid="stExpander"] {{
  border: var(--fs-border) !important;
  border-radius: var(--fs-radius) !important;
  background: var(--fs-surface) !important;
  color: var(--fs-ink-body);
}}
.stApp [data-testid="stExpander"] summary {{ color: var(--fs-ink) !important; font-weight: 700; }}
[data-testid="stAlert"] {{ border-radius: var(--fs-radius) !important; }}
.stApp [data-testid="stDataFrame"] {{
  border: var(--fs-border) !important;
  border-radius: var(--fs-radius) !important;
}}
.or-line {{
  text-align: center;
  color: var(--fs-muted);
  font-size: .88rem;
  margin: var(--fs-sp-2) 0;
}}
.fs-footer {{
  margin-top: var(--fs-sp-8);
  padding: var(--fs-sp-4) var(--fs-sp-6);
  text-align: center;
  border-top: var(--fs-border);
  color: var(--fs-muted);
  font-size: .84rem;
}}
.fs-footer b {{ color: var(--fs-ink-body); }}
::selection {{ background: rgba(98, 85, 231, .2); color: var(--fs-ink); }}
::-webkit-scrollbar {{ width: 9px; height: 9px; }}
::-webkit-scrollbar-track {{ background: var(--fs-track-bg); }}
::-webkit-scrollbar-thumb {{ background: rgba(98, 85, 231, .35); border-radius: 999px; }}
::-webkit-scrollbar-thumb:hover {{ background: rgba(98, 85, 231, .55); }}

/* == Responsive Breakpoints (Desktop / Tablet / Mobile) == */
@media (max-width: 1366px) {{
  .block-container {{ max-width: 1200px !important; }}
}}
@media (max-width: 1024px) {{
  .block-container {{
    max-width: 100% !important;
    padding: 2.5rem var(--fs-sp-4) var(--fs-sp-8) !important;
  }}
  .fs-kpi-grid, .fs-stats-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  .fs-pillars-grid, .fs-insight-grid {{ grid-template-columns: 1fr; }}
  .fs-stages {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  .stTabs [data-baseweb="tab-list"] {{ gap: 4px; padding-inline: 2px; }}
  .stTabs [data-baseweb="tab"] {{ padding: 6px 12px !important; padding-inline: 12px !important; font-size: .88rem !important; }}
  .stTabs [aria-selected="true"] {{ padding-inline: 12px !important; }}
}}
@media (max-width: 1024px) and (min-width: 769px) {{
  section[data-testid="stSidebar"][aria-expanded="true"] {{
    width: 236px !important;
    min-width: 236px !important;
  }}
}}
@media (max-width: 768px) {{
  section[data-testid="stSidebar"][aria-expanded="false"] {{
    width: 0 !important;
    min-width: 0 !important;
    max-width: 0 !important;
    border-inline-end: none !important;
    overflow: hidden !important;
    visibility: hidden !important;
    opacity: 0 !important;
    pointer-events: none !important;
    display: none !important;
  }}
  section[data-testid="stSidebar"][aria-expanded="true"] {{
    position: fixed !important;
    inset-block: 0 !important;
    inset-inline-start: 0 !important;
    z-index: 999991 !important;
    width: min(272px, 82vw) !important;
    min-width: min(272px, 82vw) !important;
    max-width: min(272px, 82vw) !important;
    visibility: visible !important;
    box-shadow: var(--fs-shadow-lg) !important;
  }}
}}
@media (max-width: 640px) {{
  .block-container {{ padding: 2.5rem var(--fs-sp-3) var(--fs-sp-6) !important; }}
  .fs-header {{ padding: var(--fs-sp-3); }}
  .fs-hero-copy {{ padding: var(--fs-sp-4); }}
  .fs-preview {{ padding: var(--fs-sp-3) var(--fs-sp-4); }}
  .fs-preview-chart {{ flex: 0 0 96px; height: 96px; min-height: 96px; }}
  .fs-kpi-grid, .fs-stats-grid, .fs-pillars-grid, .fs-insight-grid, .fs-stages {{
    grid-template-columns: 1fr;
  }}
  .fs-kpi {{ padding: var(--fs-sp-3) var(--fs-sp-4); }}
  .fs-progress-card {{ padding: var(--fs-sp-3) var(--fs-sp-4); }}
  .fs-health-hero {{ padding: var(--fs-sp-3) var(--fs-sp-4); }}
  .fin-table {{ font-size: .82rem; }}
  .fin-table thead th, .fin-table tbody td {{ padding: var(--fs-sp-2) var(--fs-sp-2); }}
  [data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] {{
    min-height: 164px !important;
    padding: var(--fs-sp-4) var(--fs-sp-3) !important;
  }}
}}

/* == Accessibility: prefers-reduced-motion == */
@media (prefers-reduced-motion: reduce) {{
  .fs-header, .fs-hero-copy, .fs-preview, .fs-feature, .fs-kpi, .fs-bar,
  .fs-file-list, .live-dot, .fs-stage.active .fs-stage-dot,
  .stApp::before, .stApp::after,
  .fs-progress-fill::after,
  .stApp .stButton > button[kind="primary"]::after,
  [data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"]::before {{
    animation: none !important;
    transition: none !important;
  }}
}}
</style>"""


DESIGN_CSS = get_design_css("ar")
