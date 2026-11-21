"""Financial Statement Analysis Agent — Streamlit dashboard.

Pipeline: Upload → Validation → Extraction → Structuring → Deterministic
Calculations → Two-Year Comparison → Gemini Interpretation → Dashboard.
"""
from __future__ import annotations

import hashlib
import json
import sys
import threading
import time
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_APP_BUILD_ID = "2026-11-21-v9.10"
if not __import__("os").environ.get("PYTEST_CURRENT_TEST"):
    if getattr(sys, "_finsight_build_id", None) != _APP_BUILD_ID:
        for _mod_name in [m for m in list(sys.modules) if m == "src" or m.startswith("src.")]:
            sys.modules.pop(_mod_name, None)
        sys._finsight_build_id = _APP_BUILD_ID
    try:
        if st.session_state.get("_app_build_id") != _APP_BUILD_ID:
            for _sk in ("results", "analysis", "raw_bytes", "ev_cell", "live_queue", "live_queue_key", "_report_memo"):
                st.session_state.pop(_sk, None)
            st.session_state["_app_build_id"] = _APP_BUILD_ID
    except Exception:
        pass

from src.ai.gemini_agent import AIAnalysis, analyze_financials  # noqa: E402
from src.analysis.comparison import CATEGORY_AR as _CAT_AR, LABELS_AR as _LBL_AR  # noqa: E402
from src.analysis.narrative import build_fallback_narrative  # noqa: E402
from src.analysis.score import compute_health_score, top_movers  # noqa: E402
from src.config import GEMINI_MODEL, MAX_UPLOAD_MB, REPORT_LANGUAGE, SUPPORTED_EXTENSIONS  # noqa: E402
from src.dashboard import charts, theme  # noqa: E402
from src.dashboard.report import build_html_report  # noqa: E402
from src.dashboard.view_model import report_memo  # noqa: E402
from src.exceptions import AppError, EmptyFileError  # noqa: E402
from src.pipeline import build_gemini_payload, run_pipeline  # noqa: E402

st.set_page_config(
    page_title="محلل القوائم المالية",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)
theme.inject_theme()

SAMPLE_FILE = PROJECT_ROOT / "sample_data" / "sample_financials.csv"

_ACCENTS = {"currency": theme.BRAND, "percent": "#0ea5e9", "ratio": "#8b5cf6", "days": "#d97706"}

# --- Per-process result cache (replaces st.cache_data: the heavy work runs in
# a worker thread so the status box can show live progress, which cached
# functions cannot do — st.* calls inside them are dropped) ---
_MEMO_LOCK = threading.Lock()
_PIPELINE_MEMO: dict[str, tuple[str, object]] = {}  # key -> ("ok", results) | ("err", message)
_ANALYSIS_MEMO: dict[str, tuple[str, object]] = {}  # key -> ("ok", AIAnalysis) | ("err", message)


def _memo_key(raw: bytes, *parts) -> str:
    digest = hashlib.sha1(raw).hexdigest()[:16]
    return "|".join([digest, *[str(p) for p in parts]])


def _memo_get(memo: dict, key: str):
    with _MEMO_LOCK:
        return memo.get(key)


def _memo_put(memo: dict, key: str, state: str, value) -> None:
    with _MEMO_LOCK:
        memo[key] = (state, value)


def _clear_memos() -> None:
    with _MEMO_LOCK:
        _PIPELINE_MEMO.clear()
        _ANALYSIS_MEMO.clear()


def _pool_health_lines() -> list[str]:
    """Short Arabic summary of key-pool health for error/warning boxes."""
    from src.ai.gemini_agent import get_pool

    pool = get_pool()
    if not pool.states:
        return ["لا توجد مفاتيح API في ملف ‎.env — أضف GEMINI_API_KEYS لتفعيل قراءة الملفات الممسوحة."]
    st = pool.status()
    total_pairs = st.get("total_pairs", len(pool.states) * len(pool.models))
    usable_pairs = st.get("usable_pairs", total_pairs - st["depleted_pairs"])
    est_daily = st.get("est_daily_quota", total_pairs * 20)
    sw_txt = f" · سرعة التبديل: {st['last_switch_ms']}ms" if st.get("last_switch_ms") is not None else ""
    return [
        f"حالة المفاتيح: {st['active_keys']}/{st['total_keys']} نشط · "
        f"أزواج متاحة: {usable_pairs}/{total_pairs} (حصة ≈ {est_daily} طلب/يوم) · "
        f"مستنفد يومي: {st['depleted_pairs']} · تبريد دقيقة: {st.get('rpm_cooling_pairs', 0)}{sw_txt}",
        f"ترتيب الموديلات بالسرعة: {', '.join(st['models'])}",
        "الحصة المجانية ≈ 20 طلباً/يوم لكل مفتاح لكل موديل وتتجدد بعد منتصف "
        "الليل بتوقيت غرب أمريكا؛ التبديل التلقائي عند انتهاء حصة أي زوج يتم في أقل من ثانية.",
    ]


def _ar_name(row) -> str:
    """Arabic display name for a metric row (system language: Arabic)."""
    return _LBL_AR.get(row.key, row.label_ar)


def _kpi_fields(row, currency: str, prev_year: int, curr_year: int) -> dict:
    """Arrow / mood / delta text for a KPI card from a MetricRow."""
    value = charts.fmt_value(row.current, row.kind, currency)
    accent = _ACCENTS.get(row.kind, theme.BRAND)
    if row.current is None:
        return dict(label=_ar_name(row), value="N/A", delta_text="لا توجد بيانات لهذه السنة",
                    arrow="–", mood="na", accent=accent, tooltip=row.reason)
    if row.previous is None or row.change is None:
        return dict(label=_ar_name(row), value=value, delta_text="لا توجد بيانات للسنة السابقة",
                    arrow="–", mood="na", accent=accent, tooltip=row.reason)
    arrow = "▲" if row.change > 0 else ("▼" if row.change < 0 else "◆")
    mood = "flat"
    if row.change != 0:
        good = (row.change > 0) == row.higher_is_better
        mood = "up" if good else "down"
    if row.kind == "currency":
        pct = row.change / abs(row.previous) * 100 if row.previous else None
        delta_text = f"{charts.fmt_signed_pct(pct)} vs {prev_year}"
    elif row.kind == "percent":
        delta_text = f"{charts.fmt_signed(row.change, 'percent')} vs {prev_year}"
    else:
        delta_text = f"{charts.fmt_signed(row.change, 'ratio')} vs {prev_year}"
    return dict(label=_ar_name(row), value=value, delta_text=delta_text,
                arrow=arrow, mood=mood, accent=accent, tooltip="")


# ---------------------------------------------------------------------------
# Screens
# ---------------------------------------------------------------------------

def _parse_page_range(txt: str | None):
    """'3-8' → (3, 8) · '5' → (5, 5) · anything else → None (all pages)."""
    import re as _re

    txt = (txt or "").strip()
    if not txt:
        return None
    m = _re.match(r"^(\d+)\s*-\s*(\d+)$", txt)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return (min(a, b), max(a, b))
    if txt.isdigit():
        return (int(txt), int(txt))
    return None


def upload_screen() -> None:
    """Landing v7: هيدر مضغوط + hero بعمودين (نص/معاينة) + مساحة رفع
    كاملة العرض + مميزات + خطوات + فوتر. الويدجتات نفسها ومنطق المعالجة
    نفسه — إعادة تصميم عرض فقط."""
    from src.dashboard.components.chrome import render_header

    render_header()

    # ── الـHero: عمودان (نسخ يمين / معاينة توضيحية يسار) — متوازن ولا يحتل الشاشة ──
    # ملاحظة RTL المؤكدة بصرياً: العمود الأول يظهر يميناً → النسخة أولاً، المعاينة ثانياً
    h_left, h_right = st.columns([1.05, 0.95])
    with h_left:
        st.markdown(
            '''
            <div class="fs-hero-copy">
              <span class="fs-hero-eyebrow">FINANCIAL INTELLIGENCE</span>
              <h1 class="fs-hero-title">حوّل قوائمك المالية<br>إلى <em>قرارات ذكية.</em></h1>
              <p class="fs-hero-desc">حلّل بياناتك المالية، اكتشف المؤشرات والمخاطر،
              واحصل على رؤى مالية مدعومة بالذكاء الاصطناعي.</p>
              <div class="fs-hero-actions">
                <a class="fs-cta-link" href="#upload-zone">ابدأ التحليل المالي ↓</a>
                <a class="fs-cta-link ghost" href="#how-steps">كيف يعمل؟</a>
              </div>
            </div>
            ''',
            unsafe_allow_html=True,
        )
    with h_right:
        # معاينة توضيحية موسومة — لا أرقام وهمية تُعرض كنتائج (اتجاهات رمزية فقط)
        st.markdown(
            '''
            <div class="fs-preview">
              <span class="fs-preview-tag">معاينة توضيحية — بيانات تجريبية</span>
              <div class="fs-preview-title">لوحة التحليل المالي</div>
              <div class="fs-preview-sub">هكذا تظهر نتائج تحليلك بعد المعالجة</div>
              <div class="fs-preview-kpis">
                <div class="fs-mini-kpi up"><b>▲ تحسّن</b><span>اتجاه توضيحي</span></div>
                <div class="fs-mini-kpi down"><b>▼ تراجع</b><span>اتجاه توضيحي</span></div>
                <div class="fs-mini-kpi"><b>◆ مستقر</b><span>اتجاه توضيحي</span></div>
              </div>
              <div class="fs-preview-chart">
                <div class="fs-bar">&nbsp;</div><div class="fs-bar alt">&nbsp;</div>
                <div class="fs-bar">&nbsp;</div><div class="fs-bar">&nbsp;</div>
                <div class="fs-bar alt">&nbsp;</div><div class="fs-bar">&nbsp;</div>
              </div>
              <div class="fs-preview-line">كل رقم في التحليل الفعلي يأتي من مستندك أنت — لا بيانات تجريبية</div>
            </div>
            ''',
            unsafe_allow_html=True,
        )

    # ── مساحة تحليل المستندات: البطاقة البارزة (الأولوية القصوى) ──
    # مرساة التمرير لزر الـ Hero — سلوك حقيقي: ينقل المستخدم لمساحة الرفع
    st.markdown('<div id="upload-zone"></div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown('<div class="fs-card-title">مساحة تحليل المستندات</div>'
                    '<div class="fs-card-sub">ارفع القوائم المالية وابدأ استخراج المؤشرات والرؤى.</div>',
                    unsafe_allow_html=True)
        # الأبلود الأصلي الوحيد داخل البطاقة — السحب والإفلات يعمل كما هو
        uploaded = st.file_uploader(
            "ارفع القوائم المالية (يمكن اختيار عدة ملفات)",
            type=sorted(ext.lstrip(".") for ext in SUPPORTED_EXTENSIONS),
            accept_multiple_files=True,
            help=f"الحد الأقصى: {MAX_UPLOAD_MB} م.ب لكل ملف — عدة ملفات تُحلَّل واحدًا وراء الآخر.",
            label_visibility="collapsed",
            key="uploader_main",
        )
        # قائمة الملفات المختارة الفعلية (اسم/نوع/حجم/حالة) — بيانات حية من الأبلود الأصلي
        if uploaded:
            _file_svg = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                         'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
                         'aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
                         '<polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/>'
                         '<line x1="16" y1="17" x2="8" y2="17"/></svg>')
            file_rows = "".join(
                '<div class="fs-file-row">'
                f'<span class="fs-file-ico">{_file_svg}</span>'
                f'<div class="fs-file-info"><b>{theme.ESC(f.name)}</b>'
                f'<span>{theme.ESC((f.type or "ملف").split(";")[0])} · {max(1, f.size // 1024):,} KB</span></div>'
                '<span class="fs-gate ok">جاهزة للتحليل</span></div>'
                for f in uploaded
            )
            st.markdown(f'<div class="fs-file-list">{file_rows}</div>', unsafe_allow_html=True)
        w_col1, w_col2 = st.columns([1.1, 1])
        with w_col2:
            # يسار الشاشة في RTL = وضع المعالجة
            st.radio(
                "وضع القراءة (لملفات PDF الممسوحة)",
                ["🔬 دقيق (~8-9 دقائق) — طبقات تحقق كاملة",
                 "⚡ سريع (~5 دقائق) — طبقات أقل: بعض الخانات تبقى بحاجة مراجعة والتدفقات غير متاحة"],
                index=0,
                key="read_mode",
                help="السريع يعمل مسحًا واحدًا ويؤجل التعليق التحليلي لضغطة من قسم الرؤى — "
                     "مثالي لفرز عدد كبير من الملفات؛ الدقيق يفحص الإجماليات الكبرى بقراءة مركزة "
                     "ويوفر خانات حاسمة أكثر. الصدق محفوظ في الوضعين: لا قيمة تُعرض مؤكدة إلا بتحقق.",
            )
        with w_col1:
            # يمين الشاشة في RTL = نطاق الصفحات
            st.text_input(
                "نطاق صفحات القوائم — للملفات الممسوحة الكبيرة (اختياري)",
                placeholder="مثال: 1-12",
                key="page_range",
                help="اتركه فارغاً لقراءة كل الصفحات. حدد النطاق لتسريع القراءة وتوفير الحصة.",
            )
        if st.button(
            "ابدأ التحليل المالي",
            type="primary",
            use_container_width=True,
            disabled=not uploaded,
        ):
            process_upload(uploaded)
        st.markdown("<p class='or-line'>أو</p>", unsafe_allow_html=True)
        if st.button("جرّب بملف العينة الجاهز", use_container_width=True):
            if SAMPLE_FILE.exists():

                class _SampleUpload:
                    """Minimal file-like handle so the sample flows through the
                    exact same validated path as a real upload."""

                    name = SAMPLE_FILE.name
                    size = SAMPLE_FILE.stat().st_size

                    @staticmethod
                    def getvalue() -> bytes:
                        return SAMPLE_FILE.read_bytes()

                process_upload([_SampleUpload()])
            else:
                st.error("ملف العينة غير موجود في sample_data/.")

    # ── المميزات: نظام بطاقات متسق بأيقونات SVG مدمجة (بلا إيموجي وبلا خطوط أيقونات خارجية) ──
    st.markdown('<div class="sec-heading">لماذا وكيل تحليل بيانات مالية ذكي؟</div>', unsafe_allow_html=True)
    feats = st.columns(4)
    _svg = (
        lambda body: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
        'aria-hidden="true">' + body + "</svg>"
    )
    feat_data = [
        (_svg('<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>'),
         "تحليل مالي بالذكاء الاصطناعي",
         "تعليق لكل مؤشر وتوصيات مسنودة بالأدلة — النموذج يفسّر النتائج ولا يحسبها."),
        (_svg('<line x1="19" y1="5" x2="5" y2="19"/><circle cx="6.5" cy="6.5" r="2.5"/>'
              '<circle cx="17.5" cy="17.5" r="2.5"/>'),
         "نسب مالية حتمية",
         "ربحية وسيولة ومديونية وكفاءة تُحسب بـ Python من قيمك المطلقة دائماً."),
        (_svg('<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/>'
              '<polyline points="17 6 23 6 23 12"/>'),
         "اتجاهات سنتين",
         "تحسّن / تراجع / استقرار لكل مؤشر مع نسبة التغير بين السنتين الماليتين."),
        (_svg('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
              '<polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>'),
         "تصدير Excel وPDF",
         "تقارير رسمية جاهزة للمشاركة بنفس الأرقام الموثقة المعروضة على الشاشة."),
    ]
    for i, (col, (icon, title, body)) in enumerate(zip(feats, feat_data)):
        col.markdown(
            f'<div class="fs-feature" style="animation-delay:{i * 90}ms">'
            f'<span class="fs-feature-ico">{icon}</span>'
            f"<b>{title}</b>"
            f"<span>{body}</span></div>",
            unsafe_allow_html=True,
        )

    # ── الخطوات ──
    st.markdown('<div class="sec-heading" id="how-steps">كيف يعمل؟</div>', unsafe_allow_html=True)
    steps = st.columns(4)
    step_data = [
        ("1", "ارفع الملف", "PDF أو Excel أو CSV"),
        ("2", "استخراج ذكي", "قراءة الجداول والصور الممسوحة"),
        ("3", "حساب حتمي", "60 مؤشراً بـ Python"),
        ("4", "تقرير كامل", "تعليقات وتوصيات بالأدلة"),
    ]
    for col, (num, title, body) in zip(steps, step_data):
        col.markdown(
            '<div class="step-card"><div class="step-num">' + num + "</div>"
            "<b>" + title + "</b><br><span>" + body + "</span></div>",
            unsafe_allow_html=True,
        )

    # ── الفوتر ──
    st.markdown(
        '<div class="fs-footer"><b>وكيل تحليل بيانات مالية ذكي</b> — محلل القوائم المالية · '
        "استخراج موثق بقرار بوابة لكل قيمة · "
        "حساب حتمي بـ Python · يعمل محليًا بالكامل</div>",
        unsafe_allow_html=True,
    )


def _pipeline_with_progress(file_name: str, raw: bytes, page_range, currency: str, progress_cb=None, fast_mode: bool = False):
    """Memoized pipeline + AI analysis in a worker thread with live progress.

    No st.* calls — safe to run headlessly (tests) and inside the batch loop.
    Returns (results, analysis); raises on failure (caller decides display).
    """
    company = Path(file_name).stem.replace("_", " ").replace("-", " ").strip() or file_name
    key = _memo_key(raw, file_name, page_range, fast_mode)
    akey = _memo_key(raw, file_name, page_range, currency, fast_mode)
    outcome: dict = {}
    # st.* is not safe from a worker thread: the worker only updates this
    # holder and the poller loop below (caller's/script thread) renders it.
    holder = {"line": "…"}

    def _work() -> None:
        try:
            memo = _memo_get(_PIPELINE_MEMO, key)
            if memo is None:
                results = run_pipeline(
                    file_name, raw, company,
                    progress_cb=lambda m: holder.__setitem__("line", m),
                    page_range=page_range, fast_mode=fast_mode,
                )
                _memo_put(_PIPELINE_MEMO, key, "ok", results)
            else:
                results = memo[1]
            outcome["results"] = results
            if fast_mode:
                # الوضع السريع: التعليق مؤجل — يولّد بالضغطة من قسم الرؤى
                # بدل حجب عرض الأرقام 60 ثانية إضافية
                holder["line"] = "تم الاستخراج وحساب النسب — الوضع السريع: التعليق بالضغطة من قسم الرؤى."
                outcome["analysis"] = None
                _memo_put(_PIPELINE_MEMO, key, "ok", results)
                return
            holder["line"] = "تم الاستخراج وحساب النسب — جارٍ تجهيز التعليق التحليلي…"
            eff_currency = results.get("currency_hint") or currency
            akey = _memo_key(raw, file_name, page_range, eff_currency, fast_mode)
            amemo = _memo_get(_ANALYSIS_MEMO, akey)
            if amemo is None:
                payload = build_gemini_payload(results, eff_currency)
                # Persistent analysis cache: the commentary is deterministic
                # given the payload, so a re-run (or the demo day) replays it
                # with zero API calls.
                from src.extraction.result_cache import (
                    analysis_key,
                    load_cached_analysis,
                    store_analysis,
                )

                dkey = analysis_key(payload)
                cached_a = load_cached_analysis(dkey)
                if cached_a is not None:
                    from src.ai.gemini_agent import AIAnalysis as _AA

                    analysis = _AA(
                        ok=bool(cached_a["ok"]),
                        ratio_comments=[tuple(x) for x in cached_a["ratio_comments"]],
                        recommendations=[tuple(x) for x in cached_a["recommendations"]],
                        error=str(cached_a.get("error") or ""),
                        model=str(cached_a.get("model") or ""),
                    )
                    if not analysis.ratio_comments:
                        analysis = build_fallback_narrative(results, analysis)
                else:
                    analysis = analyze_financials(payload)
                    if not analysis.ok or not analysis.ratio_comments:
                        analysis = build_fallback_narrative(results, analysis)
                    else:
                        if len(analysis.ratio_comments) < 6:
                            fb = build_fallback_narrative(results, analysis)
                            seen_m = {m for m, _ in analysis.ratio_comments}
                            for m, c in fb.ratio_comments:
                                if m not in seen_m:
                                    analysis.ratio_comments.append((m, c))
                                    seen_m.add(m)
                        if len(analysis.recommendations) < 3:
                            from src.analysis.narrative import build_recommendations

                            existing = {a for a, _ in analysis.recommendations}
                            for action, evidence in build_recommendations(results):
                                if len(analysis.recommendations) >= 5:
                                    break
                                if action not in existing:
                                    analysis.recommendations.append((action, evidence))
                                    existing.add(action)
                    if analysis.ok:
                        # cache AI output ONLY when the AI actually ran —
                        # caching the deterministic fallback would poison
                        # future runs (they would never try Gemini again).
                        store_analysis(dkey, {
                            "ok": analysis.ok,
                            "ratio_comments": [list(x) for x in analysis.ratio_comments],
                            "recommendations": [list(x) for x in analysis.recommendations],
                            "error": analysis.error,
                            "model": analysis.model,
                        })
                _memo_put(_ANALYSIS_MEMO, akey, "ok", analysis)
            else:
                analysis = amemo[1]
            outcome["analysis"] = analysis
        except Exception as exc:  # reported by the caller
            outcome["error"] = exc
            # Errors are never memoized: they are usually transient
            # (quota resets, keys added, demand spikes) and must not
            # stick to the file until the server restarts.

    worker = threading.Thread(target=_work, daemon=True)
    worker.start()
    while worker.is_alive():
        worker.join(timeout=0.4)
        if progress_cb:
            progress_cb(holder["line"])
    if "error" in outcome:
        raise outcome["error"]
    return outcome["results"], outcome["analysis"]


def run_batch_jobs(jobs: list[tuple[str, bytes]], page_range, currency: str, progress_cb=None, fast_mode: bool = False):
    """Analyze (file_name, raw) jobs sequentially. Returns (oks, failed):
    oks = [(name, results, analysis)], failed = [(name, error_message)]."""
    oks: list = []
    failed: list = []
    total = len(jobs)
    for i, (name, raw) in enumerate(jobs, 1):
        if progress_cb:
            progress_cb(i, total, name, "بدء المعالجة…")
        try:
            cb = (lambda msg, _i=i, _n=total, _nm=name: progress_cb(_i, _n, _nm, msg)) if progress_cb else None
            results, analysis = _pipeline_with_progress(name, raw, page_range, currency, cb, fast_mode)
            oks.append((name, results, analysis))
        except Exception as exc:
            failed.append((name, str(exc)))
    return oks, failed


def process_upload(uploaded) -> None:
    """One or many files: validate, then analyze sequentially with live
    progress; every success lands in the study library."""
    jobs: list[tuple[str, bytes]] = []
    for up in uploaded if isinstance(uploaded, list) else [uploaded]:
        raw = up.getvalue()
        try:
            if len(raw) == 0:
                raise EmptyFileError()
            if getattr(up, "size", len(raw)) > MAX_UPLOAD_MB * 1024 * 1024:
                raise AppError(f"File is larger than {MAX_UPLOAD_MB} MB.")
            jobs.append((up.name, raw))
        except AppError as exc:
            st.error(f"{up.name}: {exc}")
    if not jobs:
        return

    page_range = _parse_page_range(st.session_state.get("page_range"))
    currency = st.session_state.get("currency", "$")
    fast_mode = (st.session_state.get("read_mode") or "").startswith("⚡ سريع")
    batch = len(jobs) > 1

    oks: list = []
    failed: list = []
    with st.status(
        f"جارٍ تحليل {len(jobs)} ملف واحدًا وراء الآخر…" if batch else "جارٍ تحليل القوائم المالية…",
        expanded=True,
    ) as status:
        progress_box = st.empty()

        from src.dashboard.components.chrome import build_progress_html

        t0 = time.time()

        def _clock() -> str:
            """العدّاد الحي: دقائق:ثوانٍ منذ بدء التحليل."""
            secs = int(time.time() - t0)
            return f"{secs // 60:02d}:{secs % 60:02d}"

        def progress_cb(i: int, total: int, name: str, msg: str) -> None:
            # حلقة الاستطلاع في _pipeline_with_progress تستدعي هذا كل 0.4ث
            # فيتحدث العداد حيًا وشريط التقدم والمراحل بلا خيوط إضافية
            progress_box.markdown(
                build_progress_html(
                    name,
                    _clock(),
                    msg,
                    fast_mode=fast_mode,
                    batch_idx=i,
                    batch_total=total,
                    lang=st.session_state.get("ui_lang", "ar"),
                ),
                unsafe_allow_html=True,
            )

        oks, failed = run_batch_jobs(jobs, page_range, currency, progress_cb, fast_mode)
        if failed and not oks:
            status.update(label=f"فشل تحليل الملفات ✖ ({len(failed)})", state="error", expanded=True)
        elif failed:
            status.update(label=f"اكتمل: {len(oks)} ناجح · {len(failed)} فاشل", state="complete", expanded=False)
        else:
            status.update(
                label=f"اكتمل التحليل ✔ — ⏱ {_clock()}",
                state="complete", expanded=False)
    progress_box.empty()

    for name, err in failed:
        st.error(f"تعذّر تحليل «{name}»: {err}")
    if failed:
        for line in _pool_health_lines():
            st.caption(line)

    if not oks:
        return
    # Every success (already analyzed this run or cached from before) goes to
    # the study library so the batch builds the comparison table by itself.
    for _name, results, _analysis in oks:
        try:
            from src.analysis.portfolio import record_from_results, save_record

            save_record(record_from_results(results))
        except Exception:
            pass
    # The dashboard shows the LAST successful file (batch users then open the
    # comparison tab); single uploads behave exactly as before.
    results, analysis = oks[-1][1], oks[-1][2]
    for stale_k in (
        "ev_cell",
        "live_queue",
        "live_queue_key",
        "_report_memo",
        "_ev_img_cache",
        "new_ui_currency_input",
        "stmt_gate_filter",
        "stmt_search",
        "metrics_cat_filter",
        "metrics_verif_filter",
        "metrics_search_query",
        "confirm_clear_cache",
        "confirm_clear_library",
    ):
        st.session_state.pop(stale_k, None)
    for stale_k in [k for k in st.session_state if str(k).startswith("conf-")]:
        st.session_state.pop(stale_k, None)
    st.session_state["results"] = results
    st.session_state["analysis"] = analysis
    # v5: بايتات الملف الأصلي للجلسة — دليل المصدر الحي (صفحة + bbox) في
    # الواجهة الجديدة يُبنى منها؛ الكلاسيكية لا تستخدمها
    st.session_state["raw_bytes"] = jobs[0][1] if len(jobs) == 1 else         next((r for n, r in jobs if n == results.get("file_name")), None)
    # Currency: detected from the document, unless the user already chose one
    hint = results.get("currency_hint")
    if hint and "currency" not in st.session_state:
        st.session_state["currency"] = hint
    st.session_state["currency"] = st.session_state.get("currency", "$")
    st.rerun()


def _blocked_fields(r: dict) -> set[str]:
    """Fields blocked from decisive health scoring (consistent with view_model/new_ui)."""
    from src.analysis.financial_gate import decide

    dl = r.get("decision_log") or []
    curr_yr = r.get("curr_year")
    from_log = {
        e["field"]
        for e in dl
        if e.get("field")
        and (curr_yr is None or e.get("year") in (None, curr_yr) or str(e.get("year")) == str(curr_yr))
        and decide(e.get("status", "MISSING")) not in ("use", "use_disclosed")
    }
    if not dl:
        return set(r.get("blocked_fields") or [])
    dl_fields = {
        e["field"] for e in dl
        if e.get("field")
        and (curr_yr is None or e.get("year") in (None, curr_yr) or str(e.get("year")) == str(curr_yr))
    }
    extra_blocked = set(r.get("blocked_fields") or []) - dl_fields
    return from_log | extra_blocked


def _sync_gate_metadata(r: dict) -> set[str]:
    """Compute blocked_fields and ensure Classic UI exports share gate metadata."""
    from src.analysis.financial_gate import verification_labels

    blocked = _blocked_fields(r)
    dl = r.get("decision_log") or []
    if dl:
        r["blocked_fields"] = sorted(blocked)
        r["verification_status"] = verification_labels(dl)
    return blocked


def overview_screen(r: dict) -> None:
    currency = st.session_state.get("currency", "$")
    analysis: AIAnalysis | None = st.session_state.get("analysis")

    st.subheader("نظرة عامة على الشركة")

    info = [
        ("الشركة", r["company"], theme.BRAND, 0),
        ("فترة التحليل", f"{r['prev_year']} ← {r['curr_year']}", "#0ea5e9", 60),
        ("السنة السابقة", str(r["prev_year"]), "#8b5cf6", 120),
        ("السنة الحالية", str(r["curr_year"]), "#10b981", 180),
    ]
    cols = st.columns(4)
    for col, (label, value, accent, delay) in zip(cols, info):
        col.markdown(theme.info_chip(label, value, accent, delay), unsafe_allow_html=True)

    # --- AI quick verdict (top recommendation up front) ---
    if analysis is not None and analysis.recommendations:
        verb = "خلاصة التحليل" if REPORT_LANGUAGE == "ar" else "AI quick verdict"
        hint = (
            "القائمة الكاملة في تبويب 🤖 AI Analysis."
            if REPORT_LANGUAGE == "ar"
            else "Full commentary in the 🤖 AI Analysis tab."
        )
        first_action, first_evidence = analysis.recommendations[0]
        body = f"{first_action}"
        if first_evidence:
            body += f" — 📎 {first_evidence}"
        body += f" ({hint})"
        st.markdown(
            theme.report_card(verb, "🤖", body, theme.BRAND, 0),
            unsafe_allow_html=True,
        )

    # --- Financial Health Score ---
    blocked = _sync_gate_metadata(r)
    score = compute_health_score(r["curr_metrics"], blocked_fields=blocked)
    st.divider()
    st.subheader("مؤشر الصحة المالية")
    headers = ["الركيزة", "الدرجة", "الوزن", "مقارنة بالحدود الإرشادية العامة"]
    rows_html = [
        "<tr>"
        f"<td>{theme.ESC(p.name)}</td>"
        f'<td class="num"><b>{theme.ESC("N/A" if p.score is None else f"{p.score:.0f}/100")}</b></td>'
        f'<td class="num">{p.weight:.0f}%</td>'
        f"<td>{theme.ESC(' · '.join(p.details))}</td>"
        "</tr>"
        for p in score.pillars
    ]
    if score.total is not None:
        col_gauge, col_pillars = st.columns([2, 3])
        with col_gauge:
            st.plotly_chart(charts.health_gauge(score), use_container_width=True)
        with col_pillars:
            col_pillars.markdown(
                theme.fin_table(headers, rows_html), unsafe_allow_html=True
            )
            col_pillars.caption(
                "درجة حتمية مقابل مستويات إرشادية عامة مقبولة — "
                "ليست بيانات قطاعية. تُعاد موازنة الأوزان عند غياب البيانات."
            )
    else:
        st.warning(f"⚠️ {score.label}")
        if getattr(score, "policy", ""):
            st.caption(score.policy)
        st.markdown(theme.fin_table(headers, rows_html), unsafe_allow_html=True)

    # --- Advanced analysis: DuPont + Altman Z'' (deterministic, Python-only) ---
    from src.analysis.advanced import altman_z, dupont_analysis

    st.divider()
    st.subheader("التحليل المتقدم")
    st.caption(
        "أدوات مالية كلاسيكية محسوبة حتمياً في Python — تفكيك DuPont للعائد على "
        "حقوق الملكية، ونموذج Altman Z'' كمؤشر إنذار مبكر للضيق المالي."
    )
    col_dupont, col_altman = st.columns(2)

    with col_dupont:
        st.markdown("**تحليل DuPont (3 عوامل على متوسط الأرصدة) — مصادر العائد على حقوق الملكية**")
        dp = dupont_analysis(r["curr_metrics"], r["prev_metrics"])
        if dp.missing:
            for miss in dp.missing:
                st.markdown(f"- ⚠️ بيانات ناقصة: {miss}")
        else:
            headers = ["المكوّن", "القيمة", ""]
            rows_html = [
                "<tr>"
                f"<td>{theme.ESC('هامش صافي الربح (NI ÷ الإيرادات)')}</td>"
                f'<td class="num"><b>{theme.ESC(f"{dp.net_margin_pct:.2f}%")}</b></td>'
                "<td>×</td></tr>",
                "<tr>"
                f"<td>{theme.ESC('دوران الأصول (الإيرادات ÷ متوسط الأصول)')}</td>"
                f'<td class="num"><b>{theme.ESC(f"{dp.asset_turnover:.2f}x")}</b></td>'
                "<td>×</td></tr>",
                "<tr>"
                f"<td>{theme.ESC('مضاعف حقوق الملكية (متوسط الأصول ÷ متوسط حقوق الملكية)')}</td>"
                f'<td class="num"><b>{theme.ESC(f"{dp.equity_multiplier:.2f}x")}</b></td>'
                "<td>=</td></tr>",
                "<tr>"
                f"<td>{theme.ESC('العائد المركّب على حقوق الملكية')}</td>"
                f'<td class="num"><b>{theme.ESC(f"{dp.implied_roe_pct:.2f}%")}</b></td>'
                "<td></td></tr>",
            ]
            st.markdown(theme.fin_table(headers, rows_html), unsafe_allow_html=True)
            if dp.reconciles is not None:
                if dp.reconciles:
                    st.markdown(
                        f"✅ الناتج يطابق ROE المحسوب مباشرة "
                        f"({dp.direct_roe_pct:.2f}%) — التفكيك سليم."
                    )
                else:
                    st.markdown(
                        f"ℹ️ الناتج ({dp.implied_roe_pct:.2f}%) يختلف قليلاً عن ROE "
                        f"المباشر ({dp.direct_roe_pct:.2f}%) — عادةً بسبب تقريب "
                        "المتوسطات أو بنود الدخل الشامل الأخرى."
                    )

    with col_altman:
        st.markdown("**نموذج Altman Z'' (الأسواق الناشئة — 4 متغيرات) — الإنذار المبكر للضيق المالي**")
        az = altman_z(r["curr_metrics"])
        if az.missing:
            for miss in az.missing:
                st.markdown(f"- ⚠️ بيانات ناقصة: {miss}")
        else:
            zone_badge = {"safe": "🟢", "grey": "🟡", "distress": "🔴"}.get(az.zone, "")
            st.markdown(
                f"<div style='text-align:center;font-size:1.6rem;'>"
                f"<b>{az.score:.2f}</b> &nbsp; {zone_badge} {theme.ESC(az.zone_ar)}"
                "</div>",
                unsafe_allow_html=True,
            )
            rows_html = [
                "<tr>"
                f"<td>{theme.ESC(label)}</td>"
                f'<td class="num"><b>{theme.ESC(f"{part:.3f}")}</b></td>'
                "</tr>"
                for label, part in az.components
            ]
            st.markdown(
                theme.fin_table(["المكوّن", "القيمة"], rows_html),
                unsafe_allow_html=True,
            )
            st.caption(
                "المناطق: أقل من 1.1 ضيق مالي · 1.1–2.6 رمادية · أعلى من 2.6 أمان "
                "(معايير Altman 2012 للأسواق الناشئة). النموذج إرشادي وليس "
                "تنبؤاً مؤكداً."
            )

    # --- What-if sensitivity + sector/general benchmarks ---
    from src.analysis.benchmarks import DISPLAY, band_for, general_benchmarks, load_benchmarks
    from src.analysis.whatif import whatif_analysis

    st.divider()
    st.subheader("تحليل الحساسية (ماذا لو؟)")
    st.caption(
        "إعادة حساب النسب الرئيسية تحت سيناريوهات افتراضية — الميزانية ثابتة "
        "والمصاريف غير المتغيرة تبقى ثابتة، والضريبة تُعاد بنفس النسبة الفعلية. "
        "أرقام تخطيطية وليست تنبؤاً."
    )
    scenarios = whatif_analysis(r["curr_metrics"])
    headers = ["السيناريو", "الافتراض", "الإيرادات", "صافي الربح", "هامش صافي", "ROE", "ROA"]
    rows_html = []
    for i, sc in enumerate(scenarios):
        cls = " style='opacity:.75'" if i == 0 else ""
        rows_html.append(
            f"<tr{cls}>"
            f"<td>{theme.ESC(sc.name)}</td>"
            f"<td>{theme.ESC(sc.assumption)}</td>"
            f"<td class='num'>{theme.ESC(charts.fmt_value(sc.revenue, 'currency', currency))}</td>"
            f"<td class='num'>{theme.ESC(charts.fmt_value(sc.net_income, 'currency', currency))}</td>"
            f"<td class='num'>{theme.ESC(charts.fmt_signed(sc.net_margin_pct, 'percent'))}</td>"
            f"<td class='num'>{theme.ESC(charts.fmt_signed(sc.roe_pct, 'percent'))}</td>"
            f"<td class='num'>{theme.ESC(charts.fmt_signed(sc.roa_pct, 'percent'))}</td>"
            "</tr>"
        )
    st.markdown(theme.fin_table(headers, rows_html), unsafe_allow_html=True)

    st.divider()
    st.subheader("مقارنة بالمعايير")
    sector = st.session_state.get("sector")
    if sector in (None, "", "عام"):
        bm = general_benchmarks()
    elif sector.startswith("مخصص"):
        bm = load_benchmarks(None)
    else:
        bm = load_benchmarks(sector)
    if bm.source == "sector" and bm.sector_name and bm.sector_name != "مخصص":
        src_txt = (
            f"معايير قطاعية: {bm.sector_name} — من ملف "
            f"sector_benchmarks/{bm.sector_name}.csv (عدّله بمعايير قطاعك)"
        )
    elif bm.source == "sector":
        src_txt = "معايير مخصصة من ملف sector_benchmarks.csv (عدّله بمعايير قطاعك)"
    else:
        src_txt = "مستويات إرشادية عامة — اختر قطاع الشركة من الشريط الجانبي أو أضف ملف معايير"
    st.caption(src_txt)
    by_key = r["rows_by_key"]
    bm_rows_html = []
    for key, (weak, fair, good) in bm.rows.items():
        if key not in DISPLAY or key not in by_key:
            continue
        label_ar, hib = DISPLAY[key]
        row = by_key[key]
        kind = "percent" if "%" in label_ar else "ratio"
        value = row.current
        band = band_for(value, (weak, fair, good), hib)
        badge = {"جيد": "change-pos", "مقبول": "", "ضعيف": "change-neg"}.get(band, "")
        bm_rows_html.append(
            "<tr>"
            f"<td>{theme.ESC(label_ar)}</td>"
            f"<td class='num'><b>{theme.ESC(charts.fmt_value(value, kind, currency))}</b></td>"
            f"<td class='num'>{theme.ESC(charts.fmt_value(weak, kind))}</td>"
            f"<td class='num'>{theme.ESC(charts.fmt_value(fair, kind))}</td>"
            f"<td class='num'>{theme.ESC(charts.fmt_value(good, kind))}</td>"
            f"<td class='{badge}'>{theme.ESC(band or 'N/A')}</td>"
            "</tr>"
        )
    if bm_rows_html:
        st.markdown(
            theme.fin_table(
                ["المؤشر", "الحالي", "ضعيف", "مقبول", "جيد", "التقييم"],
                bm_rows_html,
            ),
            unsafe_allow_html=True,
        )

    # Peer-group comparison (quartiles from the companies library) — the
    # professional benchmark: "compared to WHOM", not just static levels.
    from src.analysis.peers import peer_comparison

    peer_rows = peer_comparison(r["curr_metrics"], r["company"], r["curr_year"])
    if peer_rows:
        st.markdown(
            f"**مقارنة بالأقران** — موقع الشركة بين {peer_rows[0].n_peers} شركات "
            "محلَّلة في المكتبة (أرباع التوزيع):"
        )
        pr_rows = []
        for p in peer_rows:
            kind = "percent" if "%" in p.label else "ratio"
            pr_rows.append(
                "<tr>"
                f"<td>{theme.ESC(p.label)}</td>"
                f"<td class='num'><b>{theme.ESC(charts.fmt_value(p.value, kind, currency))}</b></td>"
                f"<td class='num'>{theme.ESC(charts.fmt_value(p.median, kind))}</td>"
                f"<td class='num'>{theme.ESC(charts.fmt_value(p.q25, kind))}</td>"
                f"<td class='num'>{theme.ESC(charts.fmt_value(p.q75, kind))}</td>"
                f"<td>{theme.ESC(p.standing)}</td>"
                "</tr>"
            )
        st.markdown(
            theme.fin_table(
                ["المؤشر", "الشركة", "وسيط الأقران", "الربع الأدنى", "الربع الأعلى", "الموقع"],
                pr_rows,
            ),
            unsafe_allow_html=True,
        )

    # --- Anomaly screen: ±2σ vs the peer group (deterministic, zero API) ---
    from src.analysis.peers import detect_anomalies

    anomalies = detect_anomalies(r["curr_metrics"], r["company"], r["curr_year"])
    if anomalies:
        st.markdown("**🚨 شذوذ إحصائي مقابل الأقران (±2σ)**")
        an_rows = []
        for a in anomalies:
            an_rows.append(
                "<tr>"
                f"<td><b>{theme.ESC(a.label)}</b></td>"
                f"<td class='num'>{a.value:g}</td>"
                f"<td class='num'>{a.peer_mean:g} ± {a.peer_std:g}</td>"
                f"<td class='num'><b>{a.z:+.2f}σ</b></td>"
                f"<td>{theme.ESC(a.verdict)}</td>"
                "</tr>"
            )
        st.markdown(
            theme.fin_table(
                ["المؤشر", "القيمة", "متوسط الأقران ± σ", "الانحراف", "القراءة"],
                an_rows,
            ),
            unsafe_allow_html=True,
        )
        st.caption(
            "أي مؤشر يبتعد أكثر من انحرافين معياريين عن متوسط أقرانه من مكتبة "
            "الشركات يُعلَّم للمراجعة — شذوذ إحصائي وليس حكمًا نهائيًا."
        )

    # --- Expert layer: red flags + Beneish M (deterministic, zero API) ---
    from src.analysis.redflags import SEVERITY_ICON, beneish_m_score, red_flag_analysis

    st.divider()
    st.subheader("⚠️ الأعلام الحمراء")
    st.caption(
        "فحوصات المحلل والمراجع المهنية على سنتين: جودة الأرباح (الربح مقابل "
        "النقد)، انفصال الذمم/المخزون عن الإيرادات، عجز رأس المال العامل، "
        "ضغط التمويل، ونموذج Beneish لكشف أنماط التلاعب بالأرباح."
    )
    flags = red_flag_analysis(r["prev_metrics"], r["curr_metrics"])
    if flags:
        flag_rows = []
        for fl in flags:
            cls = {"high": "change-neg", "medium": "", "low": ""}.get(fl.severity, "")
            flag_rows.append(
                "<tr>"
                f"<td class='{cls}'><b>{theme.ESC(SEVERITY_ICON[fl.severity] + ' ' + fl.name)}</b></td>"
                f"<td>{theme.ESC(fl.detail)}</td>"
                "</tr>"
            )
        st.markdown(
            theme.fin_table(["المؤشر", "الدليل الرقمي"], flag_rows),
            unsafe_allow_html=True,
        )
    else:
        st.markdown("✅ لا توجد أعلام حمراء على مستوى الفحوصات الحالية.")

    bn = beneish_m_score(r["prev_metrics"], r["curr_metrics"])
    if bn.m_score is not None:
        zone_icon = {"grey_above": "🟠", "grey": "🟡", "clean": "🟢"}.get(bn.zone, "")
        st.markdown(
            f"**نموذج Beneish M-Score:** <span style='font-size:1.15rem;'><b>"
            f"{bn.m_score:.2f}</b></span> {zone_icon} {theme.ESC(bn.verdict)}",
            unsafe_allow_html=True,
        )
        st.caption(
            "المكوّنات: " + " · ".join(f"{k}={v:.2f}" for k, v in bn.components.items())
            + " — عتبة التدقيق −1.78 (أعلى منها يستحق فحصًا إضافيًا)."
        )
    else:
        st.caption(
            "نموذج Beneish غير محسوب لهذا الملف — بيانات ناقصة: "
            + theme.ESC(", ".join(bn.missing) or "—")
        )

    # --- Academic early-warning models (deterministic, zero API) ---
    from src.analysis.academic_models import academic_models

    st.divider()
    st.subheader("🎓 النماذج الأكاديمية للإنذار المبكر")
    st.caption(
        "نماذج منشورة في الأدبيات المالية تُحسب على أرصدة السنة الحالية فقط (نهاية الفترة): "
        "ألتمان Z′-Score (نسخة الشركات غير المدرجة — 5 متغيرات)، سبرينغيت، زميجيفسكي، "
        "وتحليل دوبونت (3 و5 عوامل على أرصدة نهاية العام) — حتمية بالكامل وبلا أي "
        "نداءات ذكاء اصطناعي، ولا تُحسب إلا ببياناتها كاملة."
    )
    acad_rows = []
    for m in academic_models(r["curr_metrics"]):
        if m.value is not None:
            comps = " · ".join(f"{k}={v:g}" for k, v in m.components.items())
            acad_rows.append(
                "<tr>"
                f"<td><b>{theme.ESC(m.icon + ' ' + m.name)}</b></td>"
                f"<td class='num'><b>{m.value:g}</b></td>"
                f"<td>{theme.ESC(m.verdict)}</td>"
                f"<td>{theme.ESC(comps)}</td>"
                "</tr>"
            )
        else:
            acad_rows.append(
                "<tr>"
                f"<td><b>{theme.ESC(m.name)}</b></td>"
                "<td class='num'>—</td>"
                f"<td>غير محسوب — بيانات ناقصة: {theme.ESC(', '.join(m.missing))}</td>"
                "<td>—</td>"
                "</tr>"
            )
    st.markdown(
        theme.fin_table(["النموذج", "القيمة", "الحكم", "المكوّنات"], acad_rows),
        unsafe_allow_html=True,
    )
    st.caption(
        "المراجع: Altman (1968/1983) · Springate (1978) · Zmijewski (1984) · DuPont — "
        "النماذج أداة إنذار مبكر مساعدة وليست حكمًا نهائيًا على الشركة."
    )

    from src.dashboard.excel_report import build_excel_report, safe_file_name
    from src.dashboard.view_model import report_memo

    st.download_button(
        "⬇️ تصدير التقرير الشامل (Excel — 5 أوراق)",
        data=report_memo(r, "xlsx", lambda: build_excel_report(r)),
        file_name=f"{safe_file_name(r.get('company', 'report'))}_تحليل_شامل.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    # --- Multi-year trends (deterministic, zero API) ---
    aym = r.get("all_year_metrics") or {}
    if len(aym) >= 3:
        from src.analysis.trends import format_series, year_trends

        st.divider()
        st.subheader("📈 الاتجاهات عبر السنوات")
        st.caption(
            "سلسلة كل مؤشر عبر كل السنوات المتاحة في المستند: معدل النمو "
            "السنوي المركب CAGR، وقراءة الاتجاه، وتحذير تلقائي عند استمرار "
            "الاتجاه الضار ثلاث سنوات متتالية أو أكثر."
        )
        tr_rows = []
        for t in year_trends(aym):
            cagr_txt = f"{t.cagr_pct:+.1f}%" if t.cagr_pct is not None else "—"
            tr_rows.append(
                "<tr>"
                f"<td><b>{theme.ESC(t.label)}</b></td>"
                f"<td class='num'>{theme.ESC(format_series(t.kind, t.series))}</td>"
                f"<td class='num'><b>{cagr_txt}</b></td>"
                f"<td>{theme.ESC(t.reading)}</td>"
                f"<td>{theme.ESC(t.warning or '—')}</td>"
                "</tr>"
            )
        st.markdown(
            theme.fin_table(
                ["المؤشر", "السلسلة الزمنية", "CAGR", "القراءة", "تحذير"],
                tr_rows,
            ),
            unsafe_allow_html=True,
        )

    # --- Audit trail: how many independent reads agree on each key figure ---
    conf = r.get("confidence") or {}
    if conf:
        st.subheader("🔍 ثقة الأرقام الرئيسية")
        from src.analysis.comparison import LABELS_AR as _CONF_LBL

        conf_rows = []
        for f in ("revenue", "net_income", "total_assets", "total_liabilities",
                  "current_liabilities", "equity", "operating_cash_flow"):
            for year in sorted((conf.get(f) or {}), reverse=True):
                level = int(conf[f][year])
                metrics_year = r["prev_metrics"] if year == r["prev_year"] else r["curr_metrics"]
                val = getattr(metrics_year, f, None)
                if val is None:
                    continue
                dots = "●" * min(level, 3) + "○" * max(0, 3 - min(level, 3))
                level_txt = {3: "ثلاثة قراءات مستقلة متفقة", 2: "قراءتان مستقلتان", 1: "قراءة واحدة"}.get(level, "")
                conf_rows.append(
                    "<tr>"
                    f"<td>{theme.ESC(_CONF_LBL.get(f, f))}</td>"
                    f"<td>{year}</td>"
                    f"<td class='num'>{theme.ESC(charts.fmt_value(val, 'currency', currency))}</td>"
                    f"<td class='num' title='{theme.ESC(level_txt)}'>{dots}</td>"
                    "</tr>"
                )
        if conf_rows:
            st.markdown(
                theme.fin_table(["البند", "السنة", "القيمة", "قراءات متفقة"], conf_rows),
                unsafe_allow_html=True,
            )
            st.caption("● عدد القراءات المستقلة المتفقة رقميًا (مسح + تحقق + OCR محلي) — 3/3 هو أعلى تأكيد.")

    # --- Top movers ---
    improving, declining = top_movers(r["rows"])
    if improving or declining:
        st.divider()
        st.subheader("أبرز التغيرات")
        headers = ["المؤشر", str(r["prev_year"]), str(r["curr_year"]), "التغير %", "الحالة"]
        for title, items, icon in (
            ("💪 أقوى التحسينات", improving, "change-pos"),
            ("⚠️ أكبر التراجعات", declining, "change-neg"),
        ):
            if not items:
                continue
            rows_html = []
            for row in items:
                ch_cls = "change-pos" if row.status == "Positive" else "change-neg"
                rows_html.append(
                    "<tr>"
                    f"<td>{theme.ESC(_ar_name(row))}</td>"
                    f'<td class="num">{theme.ESC(charts.fmt_value(row.previous, row.kind, currency))}</td>'
                    f'<td class="num">{theme.ESC(charts.fmt_value(row.current, row.kind, currency))}</td>'
                    f'<td class="num {ch_cls}">{theme.ESC(charts.fmt_signed_pct(row.change_pct))}</td>'
                    f"<td>{theme.badge(row.status)}</td>"
                    "</tr>"
                )
            st.markdown(f"**{title}**")
            st.markdown(theme.fin_table(headers, rows_html), unsafe_allow_html=True)

    st.divider()
    st.subheader(f"المؤشرات الرئيسية — {r['curr_year']}")
    kpi_keys = ["revenue", "net_income", "net_margin", "roe", "roa", "current_ratio", "debt_to_equity"]
    rows = [r["rows_by_key"][k] for k in kpi_keys if k in r["rows_by_key"]]
    for start in range(0, len(rows), 4):
        chunk = rows[start:start + 4]
        cols = st.columns(4)
        for i, (col, row) in enumerate(zip(cols, chunk)):
            f = _kpi_fields(row, currency, r["prev_year"], r["curr_year"])
            col.markdown(
                theme.kpi_card(**f, delay_ms=(start + i) * 70),
                unsafe_allow_html=True,
            )

    st.divider()
    st.subheader("النمو السنوي")
    g1, g2 = st.columns(2)
    for col, grow in zip((g1, g2), r["growth_rows"]):
        value = grow.current
        if value is None:
            col.markdown(theme.kpi_card(_ar_name(grow), "N/A", grow.reason or "cannot be computed", "–", "na",
                                        "#94a3b8", tooltip=grow.reason), unsafe_allow_html=True)
            continue
        arrow = "▲" if value > 0 else ("▼" if value < 0 else "◆")
        mood = "up" if value > 0 else ("down" if value < 0 else "flat")
        accent = "#10b981" if value > 0 else ("#f43f5e" if value < 0 else "#94a3b8")
        col.markdown(
            theme.kpi_card(
                _ar_name(grow), charts.fmt_value(value, "percent"),
                f"بين عامي {r['prev_year']} و{r['curr_year']}", arrow, mood, accent,
                tooltip=grow.reason or "تُحسب: (الحالية − السابقة) ÷ السابقة × 100.",
            ),
            unsafe_allow_html=True,
        )

    with st.expander("ℹ️ ملاحظات الاستخراج والافتراضات", expanded=False):
        from src.dashboard.notes_ar import note_ar

        if r["notes"]:
            st.markdown("**ملاحظات الاستخراج**")
            for note in r["notes"]:
                st.markdown(f"- {note_ar(note)}")
        else:
            st.markdown("- لا توجد ملاحظات استخراج.")
        metric_notes = {}
        for m in (r["prev_metrics"], r["curr_metrics"]):
            metric_notes.update(m.notes)
        if metric_notes:
            st.markdown("**افتراضات الحساب**")
            for note in metric_notes.values():
                st.markdown(f"- {note_ar(note)}")
        if r["missing"]:
            st.markdown("**Missing data**")
            for item in r["missing"]:
                st.markdown(f"- {item}")


def profitability_screen(r: dict) -> None:
    currency = st.session_state.get("currency", "$")
    prev_y, cur_y = r["prev_year"], r["curr_year"]
    by_key = r["rows_by_key"]

    st.subheader("الربحية")
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(
            charts.currency_chart(
                f"الإيرادات — {prev_y} مقابل {cur_y}", "الإيرادات",
                prev_y, cur_y,
                by_key["revenue"].previous, by_key["revenue"].current, currency,
            ),
            use_container_width=True,
        )
    with col2:
        st.plotly_chart(
            charts.currency_chart(
                f"صافي الربح — {prev_y} مقابل {cur_y}", "صافي الربح",
                prev_y, cur_y,
                by_key["net_income"].previous, by_key["net_income"].current, currency,
            ),
            use_container_width=True,
        )

    col3, col4 = st.columns(2)
    with col3:
        st.plotly_chart(charts.margins_chart(by_key, prev_y, cur_y, currency), use_container_width=True)
    with col4:
        st.plotly_chart(charts.returns_chart(by_key, prev_y, cur_y), use_container_width=True)

    scatter = charts.trend_scatter(r["rows"], prev_y, cur_y)
    if scatter is not None:
        st.plotly_chart(scatter, use_container_width=True)


def liquidity_screen(r: dict) -> None:
    currency = st.session_state.get("currency", "$")
    prev_y, cur_y = r["prev_year"], r["curr_year"]
    by_key = r["rows_by_key"]

    st.subheader("السيولة والمديونية")
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(charts.liquidity_chart(by_key, prev_y, cur_y), use_container_width=True)
    with col2:
        st.plotly_chart(charts.leverage_chart(by_key, prev_y, cur_y), use_container_width=True)

    if any(k in by_key and by_key[k].current is not None
           for k in ("operating_cash_flow", "investing_cash_flow", "financing_cash_flow")):
        st.plotly_chart(charts.cashflow_chart(by_key, prev_y, cur_y, currency), use_container_width=True)
    else:
        st.info("لم يتم العثور على بيانات التدفقات النقدية في الملف — وهي اختيارية في هذه النسخة.")

    st.markdown("**كيف تقرأ هذه النسب**")
    st.markdown(
        "- **النسبة الجارية** فوق 1.0x تعني تغطية الأصول المتداولة للالتزامات قصيرة الأجل؛ "
        "والقرب من 2.0x مريح عمومًا (حد إرشادي عام، لا بيانات قطاع).\n"
        "- **النسبة السريعة** تستبعد المخزون — نظرة أكثر صرامة على السيولة؛ وقرب 1.0x حد شائع.\n"
        "- **نسبة النقد** تحسب النقد وحده مقابل الالتزامات قصيرة الأجل.\n"
        "- **الدين إلى حقوق الملكية** دون 1.0x يعني اعتمادًا أقل على الدين من أموال الملاك؛ "
        "والقيم الأعلى تعني مخاطر رفع مالي أكبر.\n"
        "- **نسبة الالتزامات إلى الأصول** تُظهر حصة الأصول الممولة بالالتزامات؛ وتحت 0.5x تعتبر متحفظة عموماً."
    )

    wc_keys = ("working_capital", "operating_working_capital", "working_capital_turnover")
    wc_rows = [by_key[k] for k in wc_keys if k in by_key and
               (by_key[k].previous is not None or by_key[k].current is not None)]
    if wc_rows:
        st.markdown("**موقف رأس المال العامل**")
        headers = ["المؤشر", str(prev_y), str(cur_y), "التغير", "التغير %", "الحالة"]
        rows_html = []
        for row in wc_rows:
            ch_cls = ""
            if row.change is not None and row.change != 0:
                ch_cls = "change-pos" if (row.change > 0) == row.higher_is_better else "change-neg"
            rows_html.append(
                "<tr>"
                f'<td>{theme.ESC(_ar_name(row))}</td>'
                f'<td class="num">{theme.ESC(charts.fmt_value(row.previous, row.kind, currency))}</td>'
                f'<td class="num">{theme.ESC(charts.fmt_value(row.current, row.kind, currency))}</td>'
                f'<td class="num {ch_cls}">{theme.ESC(charts.fmt_signed(row.change, row.kind, currency))}</td>'
                f'<td class="num {ch_cls}">{theme.ESC(charts.fmt_signed_pct(row.change_pct))}</td>'
                f'<td>{theme.badge(row.status)}</td>'
                "</tr>"
            )
        st.markdown(theme.fin_table(headers, rows_html), unsafe_allow_html=True)


def efficiency_screen(r: dict) -> None:
    currency = st.session_state.get("currency", "$")
    prev_y, cur_y = r["prev_year"], r["curr_year"]
    by_key = r["rows_by_key"]

    st.subheader("الكفاءة التشغيلية")
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(charts.efficiency_chart(by_key, prev_y, cur_y), use_container_width=True)
    with col2:
        st.markdown("**ماذا تقيس هذه المؤشرات**")
        st.markdown(
            "- **دوران الأصول** = الإيرادات ÷ متوسط إجمالي الأصول — كم إيراداً تولّده كل وحدة أصول.\n"
            "- **دوران المخزون** = تكلفة الإيرادات ÷ متوسط المخزون — كم مرة يُباع ويُستبدل المخزون سنوياً."
        )
        if by_key.get("inventory_turnover") and by_key["inventory_turnover"].current is None:
            st.info(by_key["inventory_turnover"].reason)
        eff_rows = [by_key[k] for k in ("asset_turnover", "inventory_turnover") if k in by_key]
        if eff_rows:
            headers = ["المؤشر", str(prev_y), str(cur_y), "التغير", "التغير %", "الحالة"]
            rows_html = []
            for row in eff_rows:
                ch_cls = ""
                if row.change is not None and row.change != 0:
                    ch_cls = "change-pos" if (row.change > 0) == row.higher_is_better else "change-neg"
                rows_html.append(
                    "<tr>"
                    f'<td>{theme.ESC(_ar_name(row))}</td>'
                    f'<td class="num">{theme.ESC(charts.fmt_value(row.previous, row.kind, currency))}</td>'
                    f'<td class="num">{theme.ESC(charts.fmt_value(row.current, row.kind, currency))}</td>'
                    f'<td class="num {ch_cls}">{theme.ESC(charts.fmt_signed(row.change, row.kind, currency))}</td>'
                    f'<td class="num {ch_cls}">{theme.ESC(charts.fmt_signed_pct(row.change_pct))}</td>'
                    f'<td>{theme.badge(row.status)}</td>'
                    "</tr>"
                )
            st.markdown(theme.fin_table(headers, rows_html), unsafe_allow_html=True)


def common_size_screen(r: dict) -> None:
    """Common-size view: every line as % of Revenue (income statement) or
    % of Total Assets (balance sheet), for both years side by side."""
    pm, cm = r["prev_metrics"], r["curr_metrics"]
    prev_y, cur_y = r["prev_year"], r["curr_year"]
    currency = st.session_state.get("currency", "$")

    st.subheader("تحليل الحجم المشترك")
    st.caption(
        "Structure view: each line as a % of Revenue (income statement) or of "
        "Total Assets (balance sheet) — shows the company's composition, not "
        "just absolute changes."
    )

    def common_size_rows(items, base_attr: str):
        base_prev = getattr(pm, base_attr)
        base_curr = getattr(cm, base_attr)
        rows_html = []
        for attr, label, up_is_good in items:
            pv, cv = getattr(pm, attr), getattr(cm, attr)
            pp = (pv / base_prev * 100) if (pv is not None and base_prev) else None
            cp = (cv / base_curr * 100) if (cv is not None and base_curr) else None
            if pp is None and cp is None:
                continue
            if pp is not None and cp is not None:
                if cp == pp:
                    ch_cls = ""
                else:
                    grew = cp > pp
                    ch_cls = "change-pos" if (grew == up_is_good) else "change-neg"
                change = f'{cp - pp:+.1f}pp'
            else:
                ch_cls, change = "", "–"
            rows_html.append(
                "<tr>"
                f'<td>{theme.ESC(label)}</td>'
                f'<td class="num">{theme.ESC(charts.fmt_value(pv, "currency", currency))}</td>'
                f'<td class="num">{theme.ESC(charts.fmt_value(cv, "currency", currency))}</td>'
                f'<td class="num">{theme.ESC(charts.fmt_value(pp, "percent"))}</td>'
                f'<td class="num">{theme.ESC(charts.fmt_value(cp, "percent"))}</td>'
                f'<td class="num {ch_cls}">{theme.ESC(change)}</td>'
                "</tr>"
            )
        return rows_html

    st.markdown(f"**قائمة الدخل — % من الإيرادات**")
    is_items = [
        ("cost_of_revenue", "تكلفة الإيرادات", False),
        ("gross_profit", "مجمل الربح", True),
        ("operating_expenses", "المصاريف التشغيلية", False),
        ("selling_expenses", "مصاريف البيع", False),
        ("rd_expenses", "البحث والتطوير", False),
        ("depreciation_amortization", "الإهلاك والاستنفاد", False),
        ("interest_expense", "التكاليف التمويلية", False),
        ("operating_income", "الربح التشغيلي", True),
        ("pretax_income", "الربح قبل الضريبة", True),
        ("income_tax_expense", "مصروف ضريبة الدخل", False),
        ("net_income", "صافي الربح", True),
    ]
    st.markdown(
        theme.fin_table(
            ["البند", str(prev_y), str(cur_y), f"% من {prev_y}", f"% من {cur_y}", "الانزياح"],
            common_size_rows(is_items, "revenue"),
        ),
        unsafe_allow_html=True,
    )

    st.markdown("**الميزانية — % من إجمالي الأصول**")
    bs_items = [
        ("cash", "النقد وما يعادله", True),
        ("current_assets", "الأصول المتداولة", True),
        ("inventory", "المخزون", True),
        ("accounts_receivable", "الذمم المدينة (العملاء)", True),
        ("fixed_assets", "الأصول الثابتة", True),
        ("current_liabilities", "الالتزامات المتداولة", False),
        ("total_liabilities", "إجمالي الالتزامات", False),
        ("total_debt", "إجمالي الدين", False),
        ("equity", "حقوق الملكية", True),
    ]
    st.markdown(
        theme.fin_table(
            ["البند", str(prev_y), str(cur_y), f"% من {prev_y}", f"% من {cur_y}", "الانزياح"],
            common_size_rows(bs_items, "total_assets"),
        ),
        unsafe_allow_html=True,
    )


def metrics_table_screen(r: dict) -> None:
    currency = st.session_state.get("currency", "$")
    st.subheader(f"المؤشرات — {r['prev_year']} مقابل {r['curr_year']}")

    categories = []
    for row in r["rows"]:
        if row.category not in categories:
            categories.append(row.category)
    selected = st.selectbox(
        "تصفية حسب الفئة",
        ["كل الفئات"] + [_CAT_AR.get(c, c) for c in categories],
    )
    sel_cat = {v: k for k, v in _CAT_AR.items()}.get(selected, selected)
    visible_rows = r["rows"] if selected == "كل الفئات" else [
        row for row in r["rows"] if row.category == sel_cat
    ]

    headers = ["الفئة", "المؤشر", str(r["prev_year"]), str(r["curr_year"]),
               "التغير", "التغير %", "الحالة", "الاتجاه"]
    rows_html = []
    for row in visible_rows:
        if row.change is None:
            ch_cls = ""
        elif row.change == 0:
            ch_cls = ""
        else:
            ch_cls = "change-pos" if (row.change > 0) == row.higher_is_better else "change-neg"
        trend_cls = {"↑": "trend-up", "↓": "trend-down", "→": "trend-flat"}.get(row.trend_symbol, "")
        from src.analysis.comparison import TREND_AR as _TREND_AR
        trend_text = f'{row.trend_symbol} {_TREND_AR.get(row.trend, row.trend)}' if row.trend != "N/A" else "–"
        rows_html.append(
            "<tr>"
            f'<td class="cat">{theme.ESC(_CAT_AR.get(row.category, row.category))}</td>'
            f'<td>{theme.ESC(_ar_name(row))}</td>'
            f'<td class="num">{theme.ESC(charts.fmt_value(row.previous, row.kind, currency))}</td>'
            f'<td class="num">{theme.ESC(charts.fmt_value(row.current, row.kind, currency))}</td>'
            f'<td class="num {ch_cls}">{theme.ESC(charts.fmt_signed(row.change, row.kind, currency))}</td>'
            f'<td class="num {ch_cls}">{theme.ESC(charts.fmt_signed_pct(row.change_pct))}</td>'
            f'<td>{theme.badge(row.status)}</td>'
            f'<td class="{trend_cls}">{theme.ESC(trend_text)}</td>'
            "</tr>"
        )
    st.markdown(theme.fin_table(headers, rows_html), unsafe_allow_html=True)

    csv_df = charts.styled_comparison_table(r["rows"], r["prev_year"], r["curr_year"], currency)
    growth_df = charts.styled_comparison_table(r["growth_rows"], r["prev_year"], r["curr_year"], currency)
    combined = pd.concat([csv_df, growth_df], ignore_index=True)

    col1, col2 = st.columns([3, 1])
    col1.caption(
        "التغير % نسبي للسنة السابقة؛ ولمقاييس النسب المئوية يُقاس التغير بالنقاط (pp). الاتجاه محسوب حتمياً بـ Python."
    )
    with col2:
        csv_combined = combined.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "⬇️ تصدير الجدول (CSV)",
            data=csv_combined,
            file_name=f"metrics_{r['prev_year']}_{r['curr_year']}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.markdown("**معدلات النمو السنوي**")
    growth_rows_html = []
    for row in r["growth_rows"]:
        rows_html_cls = ""
        if row.current is not None:
            rows_html_cls = "change-pos" if row.current > 0 else ("change-neg" if row.current < 0 else "")
        growth_rows_html.append(
            "<tr>"
            f'<td class="cat">Growth & Income</td>'
            f'<td>{theme.ESC(_ar_name(row))}</td>'
            f'<td class="num">–</td>'
            f'<td class="num">–</td>'
            f'<td class="num">–</td>'
            f'<td class="num {rows_html_cls}">{theme.ESC(charts.fmt_signed_pct(row.current))}</td>'
            f'<td>{theme.badge(row.status)}</td>'
            f'<td class="{"trend-up" if (row.current or 0) > 0 else ("trend-down" if (row.current or 0) < 0 else "trend-flat")}">'
            f'{theme.ESC(f"{row.trend_symbol} {row.trend}")}</td>'
            "</tr>"
        )
    st.markdown(theme.fin_table(headers, growth_rows_html), unsafe_allow_html=True)


def ai_screen(r: dict, analysis: AIAnalysis) -> None:
    currency = st.session_state.get("currency", "$")
    st.subheader("🤖 تعليقات المؤشرات والتوصيات")
    st.caption(
        f"التفسير بواسطة {analysis.model} — Python حسب كل قيمة واتجاهها، "
        "والذكاء الاصطناعي يكتب التفسير المختصر فقط."
    )

    if not analysis.ok:
        if analysis.error:
            st.warning(analysis.error)
            if not analysis.ratio_comments:
                return
        elif not analysis.ratio_comments and not analysis.recommendations:
            st.info(
                "⚡ الوضع السريع: التعليق التحليلي مؤجل — يمكنك توليده من تبويب «رؤى Gemini» في الواجهة الجديدة."
            )
        if analysis.ratio_comments:
            st.caption(
                "Showing a rule-based commentary generated deterministically from the "
                "computed metrics (no AI was involved)."
            )

    if analysis.ratio_comments:
        lines = "".join(
            f'<div class="ratio-line"><span class="ratio-name">{theme.ESC(metric)}</span>'
            f"{theme.ESC(comment)}</div>"
            for metric, comment in analysis.ratio_comments
        )
        st.markdown(
            f'<div class="report-card" style="--accent:{theme.BRAND}">'
            f'<div class="rc-title"><span class="rc-ico">💬</span>تعليقات المؤشرات</div>'
            f"{lines}</div>",
            unsafe_allow_html=True,
        )

    if analysis.recommendations:
        recs_title = "التوصيات" if REPORT_LANGUAGE == "ar" else "Recommendations"
        items = "".join(
            f"<li><span dir=\"auto\">{theme.ESC(action)}</span>"
            + (f'<div class="rec-evidence" dir="auto">📎 {theme.ESC(evidence)}</div>' if evidence else "")
            + "</li>"
            for action, evidence in analysis.recommendations
        )
        st.markdown(
            f'<div class="sw-card recs">'
            f'<div class="rc-title"><span class="rc-ico">🧭</span>{theme.ESC(recs_title)}</div>'
            f'<ol>{items}</ol>'
            f'<div class="rec-evidence" dir="auto">📌 '
            f'{"كل توصية مرفقة بدليلها الرقمي المحسوب في Python — لا توصية بلا دليل."
              if REPORT_LANGUAGE == "ar" else
              "Every recommendation carries its Python-computed numeric evidence — none without proof."}'
            f'</div></div>',
            unsafe_allow_html=True,
        )

    blocked = _sync_gate_metadata(r)
    score = compute_health_score(r["curr_metrics"], blocked_fields=blocked)
    report = {
        "company": r["company"],
        "period": {"previous_year": r["prev_year"], "current_year": r["curr_year"]},
        "health_score": {
            "total": score.total,
            "label": score.label,
            "pillars": [
                {"pillar": p.name, "score": p.score, "weight": p.weight}
                for p in score.pillars
            ],
        },
        "ratio_comments": [
            {"metric": metric, "comment": comment} for metric, comment in analysis.ratio_comments
        ],
        "recommendations": [
            {"action": action, "evidence": evidence}
            for action, evidence in analysis.recommendations
        ],
        "metrics": [
            {
                "metric": x.label, "previous": x.previous, "current": x.current,
                "change": x.change, "change_pct": x.change_pct,
                "status": x.status, "trend": x.trend,
            }
            for x in r["rows"]
        ],
        "missing_data": r["missing"],
        "notes": r["notes"],
    }
    col_json, col_html, col_note = st.columns(3)
    with col_json:
        st.download_button(
            "⬇️ تنزيل التقرير (JSON)",
            data=json.dumps(report, indent=2, ensure_ascii=False, default=str),
            file_name=f"financial_analysis_{r['prev_year']}_{r['curr_year']}.json",
            mime="application/json",
            use_container_width=True,
        )
    with col_html:
        html_key = (
            f"html|{bool(getattr(analysis, 'ok', False))}|"
            f"{len(getattr(analysis, 'ratio_comments', []) or [])}"
        )
        st.download_button(
            "⬇️ تنزيل تقرير قابل للطباعة (HTML ← PDF)",
            data=report_memo(r, html_key,
                             lambda: build_html_report(r, analysis, score,
                                                       currency)),
            file_name=f"financial_report_{r['prev_year']}_{r['curr_year']}.html",
            mime="text/html",
            use_container_width=True,
        )
    with col_note:
        from datetime import datetime

        from src.analysis.advanced import altman_z as _altman_z
        from src.analysis.comparison import LABELS_AR as _CONF_LBL_NOTE
        from src.analysis.redflags import beneish_m_score, red_flag_analysis
        from src.dashboard.study_report import build_research_note

        flags = red_flag_analysis(r["prev_metrics"], r["curr_metrics"])
        bn = beneish_m_score(r["prev_metrics"], r["curr_metrics"])
        az = _altman_z(r["curr_metrics"])
        cm = r["curr_metrics"]
        rev_g = ((cm.revenue - r["prev_metrics"].revenue) / abs(r["prev_metrics"].revenue) * 100
                 if (cm.revenue is not None and r["prev_metrics"].revenue) else None)
        summary = []
        if rev_g is not None:
            summary.append(f"الإيرادات {'نمت' if rev_g >= 0 else 'تراجعت'} بنسبة {abs(rev_g):.1f}% مقارنة بالسنة السابقة.")
        if cm.net_margin is not None:
            summary.append(f"هامش صافي الربح {cm.net_margin:.1f}% ({'يغطي' if cm.net_margin > 0 else 'لا يغطي'} تكاليف التشغيل).")
        if cm.working_capital is not None:
            summary.append(f"رأس المال العامل {'موجب' if cm.working_capital >= 0 else 'سالب'} بمقدار {cm.working_capital:,.0f}.")
        note_data = {
            "company": r["company"], "prev_year": r["prev_year"],
            "curr_year": r["curr_year"], "currency": currency,
            "rating": (score.label if score.total is not None else "—"),
            "health_total": score.total, "health_label": score.label,
            "altman_score": (az.score if not az.missing else None),
            "altman_zone": az.zone_ar,
            "summary_lines": summary or ["—"],
            "flags": [{"name": f.name, "severity": f.severity, "detail": f.detail} for f in flags],
            "beneish": {
                "m_score": bn.m_score, "verdict": bn.verdict,
                "components": bn.components, "missing": bn.missing,
                "zone": bn.zone,
            },
            "confidence": [
                {"label": _CONF_LBL_NOTE.get(f, f), "year": y,
                 "value": charts.fmt_value(getattr(r["curr_metrics"] if y == r["curr_year"] else r["prev_metrics"], f, None), "currency", currency),
                 "witnesses": int(lvl)}
                for f, by_year in (r.get("confidence") or {}).items() for y, lvl in by_year.items()
            ],
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "footer": "أُنتجت آليًا بواسطة نظام تحليل القوائم المالية — جميع الأرقام محسوبة حتميًا بـ Python "
                      "من قوائم الشركة مع طبقات تحقق متعددة؛ التحليل إرشادي ولا يُعد توصية استثمارية.",
        }
        st.download_button(
            "⬇️ بحثة محلل (HTML ← PDF)",
            data=build_research_note(note_data),
            file_name=f"research_note_{r['prev_year']}_{r['curr_year']}.html",
            mime="text/html",
            use_container_width=True,
        )
    st.caption(
        "تقرير HTML مستقل بذاته — افتحه في أي متصفح واطبعه (Ctrl+P) لحفظه PDF."
    )


def comparison_screen() -> None:
    """Cross-company study table (دراسة تطبيقية على الشركات)."""
    import pandas as pd
    import plotly.graph_objects as go

    from src.analysis.portfolio import clear_library, load_records

    st.subheader("مقارنة الشركات")
    st.caption(
        "كل تحليل ناجح يُحفَظ تلقائيًا هنا (باسم الشركة وسنته كما وردا في "
        "الملف نفسه) — حلّل ملفات شركات البورصة واحدًا واحدًا وسيُبنى هذا "
        "الجدول تلقائيًا. هذا الجدول هو مخرج الدراسة التطبيقية."
    )
    records = load_records()
    if not records:
        from src.dashboard.components.chrome import render_empty_state

        render_empty_state(
            "مكتبة الشركات فارغة بعد",
            "كل شركة تحلَّل بنجاح تُحفَظ هنا تلقائيًا لبناء جدول مقارنة الشركات.",
            icon="🏢",
            next_step="ارفع قوائم أول شركة من شاشة البداية وستظهر هنا تلقائيًا.",
        )
        return

    df = pd.DataFrame([
        {
            "الشركة": r.company,
            "السنة": r.curr_year,
            "العملة": r.currency,
            "الإيرادات": r.revenue,
            "صافي الربح": r.net_income,
            "هامش صافي %": r.net_margin_pct,
            "ROE %": r.roe_pct,
            "ROA %": r.roa_pct,
            "النسبة الجارية": r.current_ratio,
            "الدين/حقوق الملكية": r.debt_to_equity,
            "دوران الأصول": r.asset_turnover,
            "الصحة": r.health_total,
            "Altman": r.altman_score,
            "منطقة Altman": r.altman_zone,
            "الملف": r.file_name,
        }
        for r in records
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)

    # ROE comparison bar (None-safe)
    plotted = df.dropna(subset=["ROE %"])
    if not plotted.empty:
        fig = go.Figure(go.Bar(
            x=plotted["الشركة"] + " (" + plotted["السنة"].astype(str) + ")",
            y=plotted["ROE %"],
            marker_color=theme.BRAND,
        ))
        fig.update_layout(
            title="العائد على حقوق الملكية — مقارنة بين الشركات",
            xaxis_title="", yaxis_title="ROE %", height=380,
            margin=dict(l=10, r=10, t=50, b=10),
        )
        st.plotly_chart(fig, use_container_width=True)

    col_csv, col_report, col_clear, _ = st.columns([2, 2, 2, 1])
    with col_csv:
        st.download_button(
            "⬇️ تصدير مقارنة الشركات (CSV)",
            data=df.to_csv(index=False).encode("utf-8-sig"),
            file_name="companies_comparison.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with col_report:
        from src.dashboard.study_report import build_study_report

        st.download_button(
            "⬇️ تقرير الدراسة التطبيقية (HTML ← PDF)",
            data=build_study_report(records),
            file_name="study_report.html",
            mime="text/html",
            use_container_width=True,
        )
    with col_clear:
        if st.button("🗑️ مسح مكتبة الشركات", use_container_width=True):
            if st.session_state.get("confirm_clear_library"):
                n = clear_library()
                st.session_state["confirm_clear_library"] = False
                st.rerun()
            else:
                st.session_state["confirm_clear_library"] = True
                st.warning("اضغط المسح مرة ثانية لتأكيد الحذف.")
    if st.session_state.get("confirm_clear_library"):
        st.caption("الحذف يتأثر بزر ثانٍ — إعادة التشغيل تلغي التأكيد.")


# ---------------------------------------------------------------------------
# App shell
# ---------------------------------------------------------------------------

def dashboard_screen() -> None:
    # v6: الواجهة الجديدة هي الافتراضية بعد التحليل (توجيه إعادة
    # التصميم) — الكلاسيكية كاملة خلف مفتاح "الواجهة الكلاسيكية" في
    # سايدبار الجديدة. ui_mode مفتاح جلسة مستمر: الـtoggle الكلاسيكي
    # يكتب "classic" لحظة التبديل، وزر العودة في الجديدة يكتب "new" ويطفئ
    # حالة الويدجت المخزنة (فخ دورة الحياة الموثق في اختبار v5).
    if st.session_state.get("ui_mode", "new") == "new":
        from src.dashboard.new_ui import render as render_new_ui

        render_new_ui(
            st.session_state["results"],
            st.session_state.get("analysis"),
            st.session_state.get("raw_bytes"),
        )
        return
    r: dict = st.session_state["results"]
    analysis: AIAnalysis = st.session_state.get("analysis") or AIAnalysis(ok=False, error="")

    with st.sidebar:
        st.markdown(
            '<div class="rc-title" style="font-size:1.25rem;">'
            '<span class="rc-ico">📊</span>محلل القوائم المالية</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<span class="live-dot"></span>&nbsp;<span style="color:var(--fs-muted);font-size:.85rem;">'
            f'التحليل جاهز — <bdi dir="auto">{theme.ESC(r.get("file_name") or "")}</bdi></span>',
            unsafe_allow_html=True,
        )
        st.caption(f"الموديل: {GEMINI_MODEL}")
        currency = st.text_input("رمز العملة", value=st.session_state.get("currency", "$"), max_chars=4)
        st.session_state["currency"] = currency.strip() or "$"

        from src.analysis.benchmarks import BENCHMARKS_CSV, available_sectors

        sector_options = ["عام"]
        if BENCHMARKS_CSV.exists():
            sector_options.append("مخصص (sector_benchmarks.csv)")
        sector_options += available_sectors()
        sector_default = st.session_state.get("sector", "عام")
        sector = st.selectbox(
            "قطاع الشركة (لمقارنة المعايير)",
            sector_options,
            index=sector_options.index(sector_default) if sector_default in sector_options else 0,
            help="يحدد ملف المعايير القطاعية المستخدم في «مقارنة بالمعايير».",
        )
        st.session_state["sector"] = sector

        from src.ai.gemini_agent import get_pool

        pool_status = get_pool().status()
        with st.expander(
            f"🔑 مفاتيح API ({pool_status['active_keys']}/{pool_status['total_keys']} نشط · {pool_status.get('usable_pairs', 0)}/{pool_status.get('total_pairs', 0)} زوج)",
            expanded=False,
        ):
            sw_part = (
                f" · تبديل: {pool_status['last_switch_ms']}ms"
                if pool_status.get("last_switch_ms") is not None
                else ""
            )
            st.caption(
                f"الحصة اليومية المقدّرة: ~{pool_status.get('est_remaining_quota', 0)} / {pool_status.get('est_daily_quota', 0)} طلب/يوم\n\n"
                f"نداءات ناجحة: {pool_status['total_ok_calls']} · "
                f"مستنفد يومي: {pool_status['depleted_pairs']} · "
                f"تبريد RPM: {pool_status.get('rpm_cooling_pairs', 0)}{sw_part}"
            )
            # ترتيب الموديلات بالأداء والسرعة الحية
            ranking = pool_status.get("model_ranking") or []
            if ranking:
                st.markdown("**⚡ ترتيب الموديلات (السرعة والأداء الحي)**")
                for idx_m, r_ in enumerate(ranking, 1):
                    cool = " · ❄️ تبريد" if r_["cooling"] else ""
                    avg = (f" · {r_['avg_s']}s" if r_["avg_s"] is not None else "")
                    st.markdown(
                        f"{idx_m}. `{r_['model']}` — ✓ {r_['ok']} / ✗ {r_['fail']}"
                        f"{avg}{cool}")
            for s in pool_status["states"]:
                icon = "⛔" if s["dead"] else ("🟡" if (s["depleted"] or s.get("rpm_cooling")) else "🟢")
                line = f"{icon} `{s['masked']}` — {s['ok_calls']} نداء"
                if s["dead"]:
                    line += f" · {s['dead_reason'][:40]}"
                elif s["depleted"]:
                    line += f" · مستنفد: {', '.join(s['depleted'])}"
                elif s.get("rpm_cooling"):
                    line += f" · تبريد دقيقة: {', '.join(s['rpm_cooling'])}"
                st.markdown(line)
            if st.button("🔄 إعادة ضبط حالة المفاتيح", use_container_width=True):
                from src.ai.gemini_agent import reset_pool

                reset_pool()
                _clear_memos()
                st.rerun()

        if st.button("🔄 تحليل جديد", use_container_width=True):
            for key in (
                "results",
                "analysis",
                "raw_bytes",
                "ev_cell",
                "live_queue",
                "live_queue_key",
                "_report_memo",
                "_ev_img_cache",
                "new_ui_currency_input",
                "currency",
                "stmt_gate_filter",
                "stmt_search",
                "metrics_cat_filter",
                "metrics_verif_filter",
                "metrics_search_query",
                "confirm_clear_cache",
                "confirm_clear_library",
            ):
                st.session_state.pop(key, None)
            for key in [k for k in st.session_state if str(k).startswith("conf-")]:
                st.session_state.pop(key, None)
            st.rerun()

        # v6: المفتاح معكوس الدلالة — الكلاسيكية هي الاستثناء الآن.
        # زر العودة في الجديدة يكتب ui_mode="new" ويطفئ هذه الويدجت
        # المخزنة (فخ دورة الحياة الموثق في اختبار v5).
        if "ui_mode_classic_toggle" not in st.session_state:
            st.session_state["ui_mode_classic_toggle"] = (
                st.session_state.get("ui_mode") == "classic"
            )
        if st.toggle("📜 الواجهة الكلاسيكية",
                     key="ui_mode_classic_toggle",
                     help="الواجهة الأصلية كاملة — التبديل لا يفقد النتائج."):
            st.session_state["ui_mode"] = "classic"
        else:
            st.session_state["ui_mode"] = "new"
            st.session_state.pop("new_ui_currency_input", None)
            st.rerun()

        if st.button("🧹 مسح الكاش المحلي", use_container_width=True,
                     help="يمسح نتائج الملفات المحلولة سابقًا — التحليل القادم سيقرأ من الصفر ويتحمل النداءات من جديد."):
            if st.session_state.get("confirm_clear_cache"):
                from src.extraction.result_cache import clear_all_caches

                n = clear_all_caches()
                st.session_state["confirm_clear_cache"] = False
                _clear_memos()
                st.toast(f"تم مسح {n} ملف كاش محلي.")
            else:
                st.session_state["confirm_clear_cache"] = True
                st.warning("اضغط مرة ثانية لتأكيد مسح الكاش.")

        if r["missing"]:
            with st.expander(f"⚠️ بيانات ناقصة ({len(r['missing'])})", expanded=False):
                for item in r["missing"]:
                    st.markdown(f"- {item}")

    tab_overview, tab_profit, tab_liq, tab_eff, tab_size, tab_table, tab_cmp, tab_ai, tab_notes, tab_review = st.tabs(
        ["🏠 نظرة عامة", "📈 الربحية", "💧 السيولة والمديونية", "⚙️ الكفاءة", "🧮 الحجم المشترك", "📋 جدول المؤشرات", "🏢 مقارنة الشركات", "🤖 تحليل الذكاء الاصطناعي", "📖 الإيضاحات المتممة", "✅ مراجعة الخانات"]
    )

    with tab_review:
        _render_review_tab_guarded()
    with tab_overview:
        overview_screen(r)
    with tab_profit:
        profitability_screen(r)
    with tab_liq:
        liquidity_screen(r)
    with tab_eff:
        efficiency_screen(r)
    with tab_size:
        common_size_screen(r)
    with tab_table:
        metrics_table_screen(r)
    with tab_cmp:
        comparison_screen()
    with tab_ai:
        ai_screen(r, analysis)
    with tab_notes:
        notes_screen(r)


def notes_screen(r) -> None:
    """تاب الإيضاحات المتممة: قراءة نصوص الإيضاحات + سؤال/جواب محلي (RAG)."""
    from src.dashboard.components.chrome import render_empty_state

    lang = st.session_state.get("ui_lang", "ar")
    is_ar = lang != "en"
    st.subheader(
        "📖 الإيضاحات المتممة — اقرأها واسألها"
        if is_ar
        else "📖 Financial Notes — Browse & Ask (Local RAG)"
    )
    notes_text = r.get("notes_text") or {}
    if not notes_text:
        render_empty_state(
            "لا توجد نصوص إيضاحات محفوظة لهذا الملف"
            if is_ar
            else "No financial notes text saved",
            "يلتقط المحرك نصوص الإيضاحات محليًا أثناء قراءة ملف PDF (مجانًا وبلا API)."
            if is_ar
            else "Notes text is captured locally during PDF analysis.",
            icon="📖",
            next_step="امسح الكاش المحلي من الشريط الجانبي ثم أعد تحليل الملف لالتقاط النصوص."
            if is_ar
            else "Clear local cache in the sidebar and re-analyze the PDF.",
        )
        return
    from src.analysis.notes_rag import NotesIndex, formulate_answer

    idx = NotesIndex.from_pages(notes_text)
    stt = idx.stats()
    if not stt["chunks"]:
        render_empty_state(
            "نصوص الإيضاحات فارغة" if is_ar else "Notes text is empty",
            "لم تتضمن الصفحات الملتقطة فقرات نصية صالحة للفهرسة."
            if is_ar
            else "No indexable text paragraphs were found in the captured notes.",
            icon="📄",
            next_step="جرّب توسيع نطاق الصفحات أو التحقق من جودة ملف PDF."
            if is_ar
            else "Try broadening the page range or verifying the PDF quality.",
        )
        return
    st.caption(
        (
            f"مُفهرسة {stt['chunks']} مقطعًا من {len(stt['pages'])} صفحة إيضاحات "
            f"(الصفحات: {', '.join(map(str, stt['pages']))}) — البحث محلي مجاني، "
            "والإجابة تُصاغ من المقاطع مع ذكر الصفحة المصدر."
            if is_ar
            else f"Indexed {stt['chunks']} chunks across {len(stt['pages'])} pages — local zero-API search with source page citations."
        )
    )

    # ── حاكمية المصادر: من أي صفحة التُقط كل رقم ──
    fs = r.get("field_sources") or {}
    if fs:
        ta_pages = set(fs.get("total_assets") or [])  # صفحات الميزانية المعروفة
        from src.analysis.comparison import LABELS_AR as _SRC_LBL

        st.markdown(
            "**🔍 حاكمية المصادر — من أي صفحة التُقط كل رقم:**"
            if is_ar
            else "**🔍 Source provenance — page origin per captured figure:**"
        )
        src_rows = []
        balance_only_notes = []
        for f in sorted(fs):
            pages = sorted(set(fs[f]))
            lbl = _SRC_LBL.get(f, f)
            if any(p in ta_pages for p in pages):
                src = "قوائم أساسية"
            elif pages:
                src = "⚠ من صفحات إيضاحات فقط — تعامل معها كمؤشر"
                if f in ("inventory", "accounts_receivable", "accounts_payable", "cash"):
                    balance_only_notes.append(lbl)
            else:
                src = "—"
            src_rows.append(f"- **{lbl}** ({f}): صفحات {', '.join(map(str, pages))} — {src}")
        with st.expander(
            "أصل الأرقام الكامل (حاكمية المصادر)"
            if is_ar
            else "Full numeric provenance"
        ):
            st.markdown("\n".join(src_rows))
        if balance_only_notes:
            st.warning(
                "⚠ هذه أرصدة تفصيلية التُقطت من صفحات الإيضاحات فقط (وليس من صفحة "
                "الميزانية) — تعامل معها كمؤشر استرشادي: " + "، ".join(balance_only_notes)
            )

    q = st.text_input(
        "اسأل سؤالًا عن الإيضاحات — مثال: ما سياسة الإهلاك المستخدمة؟"
        if is_ar
        else "Ask a question about the notes — e.g., what is the depreciation policy?"
    )
    if not q.strip():
        render_empty_state(
            "اسأل عن أي بند أو سياسة محاسبية" if is_ar else "Ask about any note or policy",
            "ابحث داخل نصوص الإيضاحات المتممة محليًا مع إظهار رقم الصفحة المصدر لكل فقرة."
            if is_ar
            else "Search locally across the footnotes with exact source page numbers.",
            icon="💬",
            next_step="أمثلة: «سياسة الإهلاك»، «القروض والتسهيلات»، «رأس المال»."
            if is_ar
            else "Try: depreciation policy, credit facilities, or share capital.",
        )
        return
    chunks = idx.search(q, top_k=5)
    if not chunks:
        render_empty_state(
            "لا توجد مقاطع مطابقة للسؤال" if is_ar else "No matching note chunks",
            "لم نعثر على فقرات تحتوي على الكلمات المفتاحية المطلوبة."
            if is_ar
            else "No paragraphs matched your query terms.",
            icon="🔎",
            next_step="جرّب كلمات مختلفة أو أقرب مصطلح محاسبي بالعربية أو الإنجليزية."
            if is_ar
            else "Try alternative accounting keywords in Arabic or English.",
        )
        return
    with st.spinner("جارٍ صياغة الإجابة من مقاطع الإيضاحات…" if is_ar else "Formulating answer..."):
        _ans_box: list[str | None] = [None]
        _co_str = r.get("company", "")

        def _run_rag_llm() -> None:
            try:
                _ans_box[0] = formulate_answer(q, chunks, _co_str)
            except Exception:
                _ans_box[0] = None

        _rag_t = threading.Thread(target=_run_rag_llm, daemon=True)
        _rag_t.start()
        _rag_t.join(timeout=8.0)
        answer = _ans_box[0]
    if answer:
        st.markdown(answer)
    else:
        extractive_lines = [
            f"- **[{'صفحة' if is_ar else 'Page'} {c.page}]**: {c.text[:420].strip()}{'…' if len(c.text) > 420 else ''}"
            for c in chunks[:3]
        ]
        st.markdown(
            ("📋 **الإجابة المستخرجة محليًا من مقاطع الإيضاحات المطابقة:**\n\n" if is_ar else "📋 **Local extractive answer from matching note chunks:**\n\n")
            + "\n\n".join(extractive_lines)
        )
    st.markdown(
        "**المقاطع المصدر (بالترتيب حسب التطابق):**"
        if is_ar
        else "**Source chunks (ranked by relevance):**"
    )
    for idx_c, c in enumerate(chunks):
        with st.expander(
            f"📄 صفحة {c.page} — درجة تطابق {c.score:.3f}" if is_ar else f"📄 Page {c.page} — score {c.score:.3f}",
            expanded=(idx_c == 0),
        ):
            st.markdown(c.text)


def _render_review_tab_guarded() -> None:
    """Human-review tab — only active when a reviewers file is configured.
    Ground Truth is never rendered here (review_ui enforces by construction)."""
    import os

    if not (os.environ.get("REVIEWERS_FILE") or os.environ.get("REVIEWERS")):
        st.info("تبويب المراجعة البشرية معطل — يتطلب إعداد سجل مراجعين "
                "(REVIEWERS_FILE) ومفتاح توقيع (REVIEW_HMAC_KEY) في ‎.env أو Streamlit Secrets.")
        return
    from pathlib import Path

    qpath = Path("cell_evidence/review_queue.json")
    if not qpath.exists():
        st.warning("لا يوجد طابور مراجعة — شغّل eval_extraction_benchmark.py أولًا.")
        return
    import json as _json

    from src.dashboard.review_ui import render_review_tab

    queue = _json.loads(qpath.read_text(encoding="utf-8"))
    render_review_tab(st, queue, reviewer=os.environ.get("REVIEWER_NAME", ""))


def main() -> None:
    if "results" in st.session_state:
        dashboard_screen()
    else:
        upload_screen()


if __name__ == "__main__":
    main()


