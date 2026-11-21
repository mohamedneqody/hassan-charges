# -*- coding: utf-8 -*-
"""Comprehensive verification suite for the v9.1 UI cleanup & upgrade.

Tests design tokens, RTL/LTR CSS, dead CSS removal, charts formatting fix,
reusable cards, waiting progress card, Health Score 4-pillar bars, custom
RTL financial tables (no st.dataframe), empty states, report_memo isolation,
bbox extraction, and end-to-end Streamlit AppTest flows (new UI, EN-LTR,
classic UI roundtrip, offline fallback insights, fast-mode commentary).

Isolated: monkeypatches portfolio.LIBRARY_DIR and result cache paths so
tracked repository files (e.g., companies_library/) are never touched.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
if str(PROJ) not in sys.path:
    sys.path.insert(0, str(PROJ))


# ---------------------------------------------------------------------------
# 1. Design System, Tokens & Cleanup
# ---------------------------------------------------------------------------

def test_design_tokens_and_rtl_ltr_css():
    from src.dashboard import design_system as DS
    from src.dashboard import theme

    ar_css = DS.get_design_css("ar")
    en_css = DS.get_design_css("en")

    # Unified tokens & spacing scale 4/8/12/16/24
    for token in (
        "--fs-primary:",
        "--fs-surface:",
        "--fs-ink:",
        "--fs-success:",
        "--fs-warning:",
        "--fs-danger:",
        "--fs-sp-1: 4px;",
        "--fs-sp-2: 8px;",
        "--fs-sp-3: 12px;",
        "--fs-sp-4: 16px;",
        "--fs-sp-6: 24px;",
        "--fs-shadow-md:",
    ):
        assert token in ar_css, f"missing CSS token {token}"

    # RTL vs LTR direction & dropzone localization
    assert "direction: rtl;" in ar_css
    assert "اختر من جهازك" in ar_css
    assert "direction: ltr;" in en_css
    assert "Browse files" in en_css

    # Sticky table headers & responsive breakpoints & reduced motion
    assert "position: sticky;" in ar_css
    assert "@media (max-width: 1024px)" in ar_css
    assert "@media (max-width: 640px)" in ar_css
    assert "@media (prefers-reduced-motion: reduce)" in ar_css

    # Cleanup: dead/conflicting THEME_CSS neutralized & tokens unified
    import re

    assert theme.THEME_CSS == ""
    assert theme.BRAND == DS.PRIMARY
    assert theme.POS == DS.SUCCESS
    assert theme.NEG == DS.DANGER
    assert "Material Symbols Outlined" not in ar_css
    assert ".hero-float" not in ar_css
    assert ".stat-band" not in ar_css
    assert 'section[data-testid="stSidebar"] *' not in ar_css
    # No universal stExpander * override; sidebar border unified on inline-end
    assert '[data-testid="stExpander"] *' not in ar_css
    assert '[data-testid="stExpander"] *' not in en_css
    assert "border-inline-end: var(--fs-border) !important;" in ar_css
    assert "border-inline-end: var(--fs-border) !important;" in en_css
    assert "border-inline-end: none !important;" in ar_css
    assert "border-inline-start: var(--fs-border)" not in ar_css
    assert "--fs-row-hover: #F6F7FF;" in ar_css
    # No hardcoded UI hex colors outside :root (except alpha mask #000)
    for css_text in (ar_css, en_css):
        after_root = css_text.split(":root {", 1)[1].split("}", 1)[1]
        leftover_hex = [h for h in re.findall(r"#[0-9a-fA-F]{3,8}", after_root) if h != "#000"]
        assert leftover_hex == [], f"hardcoded hex outside :root: {leftover_hex}"


def test_no_forbidden_experimental_memo_in_dashboard():
    dashboard_dir = PROJ / "src" / "dashboard"
    for py_file in [PROJ / "app.py", *dashboard_dir.rglob("*.py")]:
        txt = py_file.read_text(encoding="utf-8")
        assert "experimental_memo" not in txt, f"forbidden experimental_memo in {py_file}"


# ---------------------------------------------------------------------------
# 2. Charts Formatting Bug Fix & Palette Alignment
# ---------------------------------------------------------------------------

def test_currency_chart_formats_both_years_as_currency():
    from src.dashboard import charts, design_system as DS

    fig = charts.currency_chart(
        "الإيرادات — 2025 مقابل 2026",
        "الإيرادات",
        2025,
        2026,
        1_000_000.0,
        1_180_000.0,
        "$",
    )
    prev_bar, curr_bar = fig.data[0], fig.data[1]
    # Regression guard: previously prev_bar formatted as RATIO ("1000000.00x")
    assert list(prev_bar.text) == ["$1M"]
    assert list(curr_bar.text) == ["$1.18M"]
    assert charts.CURR_COLOR == DS.PRIMARY
    assert charts.POS_COLOR == DS.SUCCESS
    assert charts.NEG_COLOR == DS.DANGER


# ---------------------------------------------------------------------------
# 3. Reusable Components: KPI cards, Progress, Health Bars, RTL Table, Empty
# ---------------------------------------------------------------------------

def test_reusable_kpi_card_escapes_and_preserves_gate_contract():
    from src.dashboard.components.chrome import kpi_card, verification_badge_info

    html = kpi_card(
        "Revenue <script>",
        "EGP27.73 مليار",
        delta="-30.6%",
        mood="down",
        year=2025,
        explanation="مقارنة بـ 2024",
        gate_kind="pend",
        gate_glyph="◐",
        gate_label="يحتاج مراجعة",
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert '<bdi dir="ltr">-30.6%</bdi>' in html
    assert 'class="fs-gate pend"' in html
    assert "يحتاج مراجعة" in html

    # None year edge case must not render "None"
    html_none_year = kpi_card("Test", "N/A", year=None)
    assert "fs-kpi-year" not in html_none_year
    assert "None" not in html_none_year

    # Verification badge mapping strictly preserves semantic colors
    assert verification_badge_info("موثق (آلي)", "ar")[0] == "ok"
    assert verification_badge_info("موثق (بشري)", "ar")[0] == "ok"
    assert verification_badge_info("يحتاج مراجعة", "ar")[0] == "pend"
    assert verification_badge_info("مشتق معلن", "ar")[0] == "pend"
    assert verification_badge_info("تعارض — محجوب", "ar")[0] == "bad"
    assert verification_badge_info("غير متوفر", "ar")[0] == "miss"


def test_progress_card_parses_pages_and_no_double_clock():
    from src.dashboard.components.chrome import build_progress_html

    html = build_progress_html(
        "ezz_2022.pdf",
        "01:24",
        "📚 وصلنا للصفحة 6 من 12…",
        fast_mode=False,
        batch_idx=1,
        batch_total=3,
        lang="ar",
    )
    assert "⏱ ⏱" not in html
    assert "01:24" in html
    assert "[1/3] ezz_2022.pdf" in html
    assert "fs-progress-track" in html
    assert "fs-stages" in html
    assert "44%" in html  # 18 + 0.5 * 52 = 44%


def test_health_panel_renders_four_weighted_pillars_and_refusal():
    from src.analysis.calculator import compute_year_metrics
    from src.analysis.score import compute_health_score
    from src.dashboard.components.chrome import build_health_html

    data = {
        "revenue": {2025: 1_000_000, 2026: 1_180_000},
        "net_income": {2025: 180_000, 2026: 165_000},
        "total_assets": {2025: 1_500_000, 2026: 1_650_000},
        "current_assets": {2025: 600_000, 2026: 560_000},
        "inventory": {2025: 120_000, 2026: 150_000},
        "current_liabilities": {2025: 250_000, 2026: 340_000},
        "total_liabilities": {2025: 700_000, 2026: 850_000},
        "total_debt": {2025: 400_000, 2026: 520_000},
        "equity": {2025: 800_000, 2026: 800_000},
        "operating_cash_flow": {2025: 220_000, 2026: 190_000},
    }
    curr = compute_year_metrics(2026, data, prev_year=2025)
    hs_ok = compute_health_score(curr)
    html_ok = build_health_html(hs_ok, lang="ar")
    assert "fs-pillar-track" in html_ok
    assert html_ok.count("fs-pillar-card") == 4
    assert "الوزن 25%" in html_ok
    assert "الوزن 30%" in html_ok
    assert "الوزن 20%" in html_ok

    # Refused score when critical pillar is blocked: still shows 4 pillars honestly
    hs_ref = compute_health_score(curr, blocked_fields={"current_assets", "current_liabilities"})
    assert hs_ref.total is None
    html_ref = build_health_html(hs_ref, lang="ar")
    assert "الدرجة الصحية محجوبة" in html_ref
    assert html_ref.count("fs-pillar-card") == 4
    assert "الخطوة التالية" in html_ref


def test_metrics_html_table_rtl_filtering_and_states():
    from src.dashboard.components.chrome import build_metrics_table_html, build_state_html

    rows = [
        {
            "key": "revenue",
            "label": "الإيرادات",
            "label_en": "Revenue",
            "category": "Growth & Income",
            "category_ar": "النمو والدخل",
            "kind": "currency",
            "prev": 1_000_000.0,
            "curr": 1_180_000.0,
            "change": 180_000.0,
            "change_pct": 18.0,
            "status": "Positive",
            "trend": "▲",
            "verif": "موثق (آلي)",
        },
        {
            "key": "current_ratio",
            "label": "النسبة الجارية",
            "label_en": "Current Ratio",
            "category": "Liquidity",
            "category_ar": "السيولة",
            "kind": "ratio",
            "prev": 2.4,
            "curr": 1.65,
            "change": -0.75,
            "change_pct": -31.25,
            "status": "Negative",
            "trend": "▼",
            "verif": "يحتاج مراجعة",
        },
    ]
    html, count = build_metrics_table_html(rows, 2025, 2026, 1, "$", lang="ar")
    assert count == 2
    assert '<table class="fin-table">' in html
    assert '<bdi dir="ltr">+18.0%</bdi>' in html
    assert "موثق (آلي)" in html
    assert "يحتاج مراجعة" in html

    # Filter by verification status
    html_pend, count_pend = build_metrics_table_html(
        rows, 2025, 2026, 1, "$", lang="ar", filter_verif="pend"
    )
    assert count_pend == 1 and "النسبة الجارية" in html_pend

    # No-match filter returns 0
    empty_html, count_zero = build_metrics_table_html(
        rows, 2025, 2026, 1, "$", lang="ar", query="nonexistent"
    )
    assert count_zero == 0 and empty_html == ""

    # Empty state HTML includes icon, title, body, next_step
    st_html = build_state_html("لا بيانات", "شرح الحالة", icon="🔎", next_step="امسح التصفية")
    assert "fs-state empty" in st_html
    assert "امسح التصفية" in st_html


# ---------------------------------------------------------------------------
# 4. ViewModel Report Memo Isolation & BBox Extraction
# ---------------------------------------------------------------------------

def test_report_memo_isolates_different_documents(monkeypatch):
    import streamlit as st
    from src.dashboard.view_model import report_memo

    fake_session: dict = {}
    monkeypatch.setattr(st, "session_state", fake_session)

    res_a = {"document_sha256_16": "aaaa1111bbbb2222", "human_reviews": {}}
    res_b = {"document_sha256_16": "cccc3333dddd4444", "human_reviews": {}}

    out_a = report_memo(res_a, "xlsx", lambda: b"DOC_A")
    out_b = report_memo(res_b, "xlsx", lambda: b"DOC_B")
    assert out_a == b"DOC_A"
    assert out_b == b"DOC_B"

    # Human review attestation invalidates memo automatically
    res_a_reviewed = {
        "document_sha256_16": "aaaa1111bbbb2222",
        "human_reviews": {"revenue|2025": {"status": "VERIFIED_HUMAN"}},
    }
    out_a2 = report_memo(res_a_reviewed, "xlsx", lambda: b"DOC_A_REVIEWED")
    assert out_a2 == b"DOC_A_REVIEWED"

    # blocked_fields change invalidates memo even when human_reviews count is unchanged
    res_a_blocked = {
        "document_sha256_16": "aaaa1111bbbb2222",
        "human_reviews": {},
        "blocked_fields": ["current_assets"],
    }
    out_a3 = report_memo(res_a_blocked, "xlsx", lambda: b"DOC_A_BLOCKED")
    assert out_a3 == b"DOC_A_BLOCKED"


def test_extract_bbox_coords_handles_dict_and_normalized_shapes():
    from src.dashboard.new_ui import (
        _build_live_queue,
        _extract_bbox_coords,
        _render_crop,
        _render_page_with_bbox,
    )

    # vision_ocr dict list format with render_scale=2.0 -> target_scale=3.0 (1.5x)
    bbox_dicts = [{"page": 5, "bbox_px": [100, 200, 300, 240], "render_scale": 2.0}]
    assert _extract_bbox_coords(bbox_dicts, 5, 1200, 1600, 3.0) == (150.0, 300.0, 450.0, 360.0)

    # Normalized [0..1] bbox
    assert _extract_bbox_coords([0.1, 0.2, 0.5, 0.3], 1, 1000, 2000, 2.0) == (100.0, 400.0, 500.0, 600.0)

    # Non-PDF bytes (CSV/XLSX) must never crash pypdfium2 with PdfiumError
    csv_bytes = b"Item,2025,2026\nRevenue,100,120\n"
    assert _render_page_with_bbox(csv_bytes, 1, None) is None
    assert _render_crop(csv_bytes, 1, [10, 10, 50, 50]) is None
    assert _build_live_queue({"pending": [{"field": "revenue", "year": 2026, "pages": [1]}]}, {}, csv_bytes, Path(".")) == []


# ---------------------------------------------------------------------------
# 5. End-to-End Streamlit AppTest Verification (Isolated)
# ---------------------------------------------------------------------------

def test_streamlit_new_ui_en_ltr_and_classic_roundtrip(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    from src.ai import gemini_agent
    from src.analysis import portfolio
    from src.extraction import result_cache

    monkeypatch.setattr(gemini_agent, "_POOL", None)
    monkeypatch.setenv("GEMINI_API_KEYS", "")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("LOCAL_OCR_ENABLED", "0")
    monkeypatch.setattr(portfolio, "LIBRARY_DIR", tmp_path / "companies_library")
    monkeypatch.setattr(result_cache, "CACHE_DIR", tmp_path / "cache")

    at = AppTest.from_file(str(PROJ / "app.py"), default_timeout=120)
    at.run()

    # 1) Landing screen: primary analyze button disabled with no files
    analyze_btns = [b for b in at.button if "ابدأ التحليل المالي" in (b.label or "")]
    assert analyze_btns and analyze_btns[0].disabled is True

    # 2) Run sample file
    sample_btns = [b for b in at.button if "جرّب بملف العينة" in (b.label or "")]
    assert sample_btns
    sample_btns[0].click()
    at.run()
    if "results" not in at.session_state:
        at.run()
    assert "results" in at.session_state
    assert not at.exception

    # 3) New UI assertions:
    # - NO st.dataframe used for Arabic financial metrics table
    assert len(at.dataframe) == 0
    blob = "\n".join(m.value for m in at.markdown)
    # - Unified KPI grid + Health 4 pillars with weights + RTL custom table
    assert "fs-kpi-grid" in blob
    assert "$1.65 مليون" in blob  # total_assets fallback from curr_metrics (never false N/A)
    assert "fs-pillar-track" in blob
    assert "الوزن 25%" in blob
    assert '<table class="fin-table">' in blob
    # - Offline fallback insights MUST be visible (regression guard for hidden fallback bug)
    assert "نقاط القوة" in blob or "مؤشرات مستقرة" in blob or "التوصيات" in blob

    # 4) Language switch AR -> EN-LTR
    lang_btns = [b for b in at.button if "English / عربي" in (b.label or "")]
    assert lang_btns
    lang_btns[0].click()
    at.run()
    assert not at.exception
    assert at.session_state["ui_lang"] == "en"
    en_blob = "\n".join(m.value for m in at.markdown)
    assert "direction: ltr;" in en_blob
    assert "Weight 25%" in en_blob
    assert "Verification coverage:" in en_blob
    assert "$1.65M" in en_blob

    # Switch back to AR
    lang_btns = [b for b in at.button if "English / عربي" in (b.label or "")]
    lang_btns[0].click()
    at.run()
    assert at.session_state["ui_lang"] == "ar"

    # 5) Classic UI button in New UI ACTUALLY switches to Classic UI (regression guard)
    classic_btns = [b for b in at.button if "الواجهة الكلاسيكية" in (b.label or "")]
    assert classic_btns
    classic_btns[0].click()
    at.run()
    assert not at.exception
    assert at.session_state["ui_mode"] == "classic"
    classic_subheaders = [s.value for s in at.subheader]
    assert "التحليل المتقدم" in classic_subheaders
    assert "تحليل الحساسية (ماذا لو؟)" in classic_subheaders

    # Roundtrip toggle back from Classic UI -> New UI
    toggles = [t for t in at.toggle if "الواجهة الكلاسيكية" in (t.label or "")]
    assert toggles and toggles[0].value is True
    toggles[0].set_value(False)
    at.run()
    assert not at.exception
    assert at.session_state["ui_mode"] == "new"

    # Evidence button click in Statements & Cells works cleanly even for CSV (no raw PDF pages)
    ev_btns = [b for b in at.button if b.label == "الدليل"]
    assert ev_btns
    ev_btns[0].click()
    at.run()
    assert not at.exception
    assert "ev_cell" in at.session_state

    # 6) New analysis button clears session cleanly back to upload screen
    new_btns = [b for b in at.button if "تحليل جديد" in (b.label or "")]
    assert new_btns
    new_btns[0].click()
    at.run()
    assert not at.exception
    assert "results" not in at.session_state
    assert "ev_cell" not in at.session_state


def test_streamlit_fast_mode_deferred_commentary_and_filters(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    from src.ai import gemini_agent
    from src.analysis import portfolio
    from src.extraction import result_cache

    monkeypatch.setattr(gemini_agent, "_POOL", None)
    monkeypatch.setenv("GEMINI_API_KEYS", "")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("LOCAL_OCR_ENABLED", "0")
    monkeypatch.setattr(portfolio, "LIBRARY_DIR", tmp_path / "companies_library")
    monkeypatch.setattr(result_cache, "CACHE_DIR", tmp_path / "cache")

    at = AppTest.from_file(str(PROJ / "app.py"), default_timeout=120)
    at.run()

    # Select fast mode on landing screen
    radios = at.radio
    assert radios
    fast_opt = next(o for o in radios[0].options if o.startswith("⚡ سريع"))
    radios[0].set_value(fast_opt)

    sample_btns = [b for b in at.button if "جرّب بملف العينة" in (b.label or "")]
    sample_btns[0].click()
    at.run()
    if "results" not in at.session_state:
        at.run()
    assert "results" in at.session_state
    assert at.session_state["analysis"] is None
    assert not at.exception

    # Fast mode empty state + generate commentary button present
    gen_btns = [b for b in at.button if "توليد التعليق التحليلي" in (b.label or "")]
    assert gen_btns
    gen_btns[0].click()
    at.run()
    assert not at.exception
    assert at.session_state["analysis"] is not None
    blob = "\n".join(m.value for m in at.markdown)
    assert "نقاط القوة" in blob or "التوصيات" in blob

    # Search filter yielding zero metrics displays designed empty state
    search_boxes = [ti for ti in at.text_input if "مثال: ROE" in (ti.placeholder or "")]
    assert search_boxes
    search_boxes[0].set_value("__NO_SUCH_METRIC__")
    at.run()
    assert not at.exception
    filtered_blob = "\n".join(m.value for m in at.markdown)
    assert "لا توجد مؤشرات مطابقة للتصفية" in filtered_blob
    assert "fs-state empty" in filtered_blob


def test_streamlit_csv_does_not_crash_when_reviewers_configured(tmp_path, monkeypatch):
    """Regression test: when REVIEWERS_FILE is configured, uploading CSV/Excel
    must never crash sec_review with pypdfium2 PdfiumError."""
    from streamlit.testing.v1 import AppTest
    from src.ai import gemini_agent
    from src.analysis import portfolio
    from src.extraction import human_review, result_cache

    rf = tmp_path / "reviewers.json"
    human_review.pin_entry("auditor-A", "pin-A-123", ["reject"], file_path=rf)
    monkeypatch.setenv("REVIEWERS_FILE", str(rf))
    monkeypatch.setenv("REVIEW_HMAC_KEY", "test-key-isolated")
    monkeypatch.setattr(gemini_agent, "_POOL", None)
    monkeypatch.setenv("GEMINI_API_KEYS", "")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("LOCAL_OCR_ENABLED", "0")
    monkeypatch.setattr(portfolio, "LIBRARY_DIR", tmp_path / "companies_library")
    monkeypatch.setattr(result_cache, "CACHE_DIR", tmp_path / "cache")

    at = AppTest.from_file(str(PROJ / "app.py"), default_timeout=120)
    at.run()
    sample_btns = [b for b in at.button if "جرّب بملف العينة" in (b.label or "")]
    sample_btns[0].click()
    at.run()
    if "results" not in at.session_state:
        at.run()
    assert "results" in at.session_state
    assert not at.exception
    blob = "\n".join(m.value for m in at.markdown)
    assert "المراجعة المصوّرة لملفات PDF فقط" in blob


def _make_solid_pdf(rgb: tuple[int, int, int], pages: int = 1) -> bytes:
    import io
    from PIL import Image

    buf = io.BytesIO()
    imgs = [Image.new("RGB", (240, 320), rgb) for _ in range(pages)]
    if pages == 1:
        imgs[0].save(buf, format="PDF")
    else:
        imgs[0].save(buf, format="PDF", save_all=True, append_images=imgs[1:])
    return buf.getvalue()


def test_live_review_crops_isolated_by_doc_sha(tmp_path, monkeypatch):
    """Two different PDFs with the same pending page/field must never collide
    or reuse stale page/crop PNGs inside live_review_crops."""
    import hashlib
    import tempfile
    import streamlit as st
    from src.dashboard.new_ui import _build_live_queue, _safe_doc_sha, sec_review
    from src.extraction import human_review

    pdf_a = _make_solid_pdf((220, 20, 20), pages=2)
    pdf_b = _make_solid_pdf((20, 20, 220), pages=2)
    sha_a = hashlib.sha256(pdf_a).hexdigest()[:16]
    sha_b = hashlib.sha256(pdf_b).hexdigest()[:16]
    assert sha_a != sha_b

    base_dir = tmp_path / "live_review_crops"
    vm_a = {
        "doc_sha": sha_a,
        "pending_count": 1,
        "pending": [{"field": "revenue", "year": 2026, "pages": [1], "status": "UNVERIFIED", "final": 100.0}],
    }
    vm_b = {
        "doc_sha": sha_b,
        "pending_count": 1,
        "pending": [{"field": "revenue", "year": 2026, "pages": [1], "status": "UNVERIFIED", "final": 200.0}],
    }
    res_a = {"file_name": "a.pdf", "candidate_bbox": {"revenue|2026": [0.1, 0.1, 0.5, 0.3]}}
    res_b = {"file_name": "b.pdf", "candidate_bbox": {"revenue|2026": [0.1, 0.1, 0.5, 0.3]}}

    q_a = _build_live_queue(vm_a, res_a, pdf_a, base_dir)
    q_b = _build_live_queue(vm_b, res_b, pdf_b, base_dir)
    assert len(q_a) == 1 and len(q_b) == 1

    page_a = Path(q_a[0]["page_image"])
    page_b = Path(q_b[0]["page_image"])
    crop_a = Path(q_a[0]["crop_image"])
    crop_b = Path(q_b[0]["crop_image"])
    assert page_a.parent == base_dir / sha_a
    assert page_b.parent == base_dir / sha_b
    assert crop_a.parent == base_dir / sha_a
    assert crop_b.parent == base_dir / sha_b
    assert q_a[0]["page_image_sha256"] != q_b[0]["page_image_sha256"]
    assert q_a[0]["crop_sha256"] != q_b[0]["crop_sha256"]

    # Path-traversal / unsafe / empty doc_sha falls back strictly to sha256(raw)[:16]
    assert _safe_doc_sha("../..", pdf_a) == sha_a
    assert _safe_doc_sha("../foo", pdf_a) == sha_a
    assert _safe_doc_sha("", pdf_a) == sha_a

    # sec_review isolates tempfile.gettempdir() / "live_review_crops" / doc_sha
    rf = tmp_path / "reviewers.json"
    human_review.pin_entry("auditor-A", "pin-A-123", ["reject"], file_path=rf)
    monkeypatch.setenv("REVIEWERS_FILE", str(rf))
    monkeypatch.setenv("REVIEW_HMAC_KEY", "test-key-isolated")
    monkeypatch.setenv("REVIEW_LOG_PATH", str(tmp_path / "hr.json"))
    monkeypatch.setattr(human_review, "REVIEW_LOG", tmp_path / "hr.json")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path / "sys_tmp"))

    class _Col:
        def text_input(self, *a, **kw):
            return ""

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    fake_session: dict = {}
    errors: list[str] = []
    monkeypatch.setattr(st, "session_state", fake_session)
    # Stub Streamlit UI calls only to inspect queue path constructed by sec_review
    monkeypatch.setattr(st, "subheader", lambda *a, **kw: None)
    monkeypatch.setattr(st, "caption", lambda *a, **kw: None)
    monkeypatch.setattr(st, "selectbox", lambda lbl, opts, **kw: opts[0])
    monkeypatch.setattr(st, "columns", lambda spec: [_Col(), _Col()])
    monkeypatch.setattr(st, "image", lambda *a, **kw: None)
    monkeypatch.setattr(st, "markdown", lambda txt, **kw: errors.append(str(txt)))
    monkeypatch.setattr(st, "checkbox", lambda *a, **kw: False)
    monkeypatch.setattr(st, "text_area", lambda *a, **kw: "")
    monkeypatch.setattr(st, "text_input", lambda *a, **kw: "")
    monkeypatch.setattr(st, "button", lambda *a, **kw: False)

    sec_review(vm_a, res_a, pdf_a)
    assert fake_session["live_queue_key"].startswith(f"{sha_a}|")
    assert Path(fake_session["live_queue"][0]["page_image"]).parent == (
        tmp_path / "sys_tmp" / "live_review_crops" / sha_a
    )

    # Same doc_sha & same pending_count=1 but different field/page -> must rebuild queue!
    vm_a_changed = {
        "doc_sha": sha_a,
        "pending_count": 1,
        "pending": [{"field": "net_income", "year": 2026, "pages": [2], "status": "UNVERIFIED", "final": 50.0}],
    }
    sec_review(vm_a_changed, res_a, pdf_a)
    assert fake_session["live_queue"][0]["field"] == "net_income"
    assert fake_session["live_queue"][0]["page"] == 2

    # Second distinct PDF -> distinct subdirectory
    sec_review(vm_b, res_b, pdf_b)
    assert fake_session["live_queue_key"].startswith(f"{sha_b}|")
    assert Path(fake_session["live_queue"][0]["page_image"]).parent == (
        tmp_path / "sys_tmp" / "live_review_crops" / sha_b
    )

    # Mismatched raw vs vm["doc_sha"] must be blocked cleanly
    fake_session.clear()
    errors.clear()
    sec_review(vm_a, res_a, pdf_b)
    assert "live_queue" not in fake_session
    assert any("عدم تطابق بصمة المستند" in e for e in errors)


def test_streamlit_apptest_sec_review_multi_pdf_and_reject_chain(tmp_path, monkeypatch):
    """End-to-end AppTest with two real multi-page PDFs inside sec_review:
    1) Crops stay isolated per doc_sha
    2) Confirmation checkboxes never leak across documents
    3) Submitting reject records a valid HMAC-signed entry in the review log
    """
    import hashlib
    import json
    import tempfile
    from streamlit.testing.v1 import AppTest
    from src.ai import gemini_agent
    from src.analysis import portfolio
    from src.analysis.calculator import compute_year_metrics
    from src.analysis.comparison import build_comparison, growth_metrics
    from src.extraction import human_review, result_cache

    rf = tmp_path / "reviewers.json"
    human_review.pin_entry("auditor-A", "pin-A-123", ["reject"], file_path=rf)
    log_file = tmp_path / "hr.json"
    monkeypatch.setenv("REVIEWERS_FILE", str(rf))
    monkeypatch.setenv("REVIEW_HMAC_KEY", "test-key-isolated")
    monkeypatch.setenv("REVIEW_LOG_PATH", str(log_file))
    monkeypatch.setenv("REVIEW_ATTEMPTS_PATH", str(tmp_path / "attempts.json"))
    monkeypatch.setattr(human_review, "REVIEW_LOG", log_file)
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path / "sys_tmp"))
    monkeypatch.setattr(gemini_agent, "_POOL", None)
    monkeypatch.setenv("GEMINI_API_KEYS", "")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("LOCAL_OCR_ENABLED", "0")
    monkeypatch.setattr(portfolio, "LIBRARY_DIR", tmp_path / "companies_library")
    monkeypatch.setattr(result_cache, "CACHE_DIR", tmp_path / "cache")

    pdf_a = _make_solid_pdf((210, 30, 30), pages=2)
    pdf_b = _make_solid_pdf((30, 30, 210), pages=2)
    sha_a = hashlib.sha256(pdf_a).hexdigest()[:16]
    sha_b = hashlib.sha256(pdf_b).hexdigest()[:16]

    data = {
        "revenue": {2025: 1_000_000.0, 2026: 1_180_000.0},
        "net_income": {2025: 180_000.0, 2026: 165_000.0},
        "total_assets": {2025: 1_500_000.0, 2026: 1_650_000.0},
        "current_assets": {2025: 600_000.0, 2026: 560_000.0},
        "current_liabilities": {2025: 250_000.0, 2026: 340_000.0},
        "total_liabilities": {2025: 700_000.0, 2026: 850_000.0},
        "equity": {2025: 800_000.0, 2026: 800_000.0},
    }
    pm = compute_year_metrics(2025, data, prev_year=None)
    cm = compute_year_metrics(2026, data, prev_year=2025)
    rows = build_comparison(pm, cm)
    g_rows = growth_metrics(pm, cm)

    def _make_res(name, sha):
        return {
            "company": f"Co {name}",
            "file_name": name,
            "prev_year": 2025,
            "curr_year": 2026,
            "prev_metrics": pm,
            "curr_metrics": cm,
            "rows": rows,
            "growth_rows": g_rows,
            "rows_by_key": {x.key: x for x in rows},
            "notes": [],
            "missing": [],
            "document_sha256_16": sha,
            "candidate_bbox": {"revenue|2026": [0.1, 0.1, 0.5, 0.3]},
            "decision_log": [
                {"field": "revenue", "year": 2026, "status": "UNVERIFIED", "final": 1_180_000.0, "pages": [1]},
            ],
        }

    at = AppTest.from_file(str(PROJ / "app.py"), default_timeout=120)
    at.session_state["results"] = _make_res("a.pdf", sha_a)
    at.session_state["raw_bytes"] = pdf_a
    at.session_state["analysis"] = None
    at.run()
    assert not at.exception
    assert Path(at.session_state["live_queue"][0]["page_image"]).parent == (
        tmp_path / "sys_tmp" / "live_review_crops" / sha_a
    )

    # Tick all 4 confirmation checkboxes for PDF A, fill reason/reviewer/PIN, submit reject
    conf_boxes_a = [c for c in at.checkbox if f"conf-{sha_a}-" in (c.key or "")]
    assert len(conf_boxes_a) == 4
    for cb in conf_boxes_a:
        cb.set_value(True)
    reason_ta = [t for t in at.text_area if "سبب الرفض" in (t.label or "")][0]
    reason_ta.set_value("Unclear scan row")
    rev_ti = [t for t in at.text_input if "اسم المراجع" in (t.label or "")][0]
    rev_ti.set_value("auditor-A")
    pin_ti = [t for t in at.text_input if t.label == "PIN"][0]
    pin_ti.set_value("pin-A-123")
    rej_btn = [b for b in at.button if "تسجيل الرفض في السلسلة" in (b.label or "")][0]
    rej_btn.click()
    at.run()
    assert not at.exception
    assert log_file.exists()
    recs = json.loads(log_file.read_text(encoding="utf-8"))
    assert len(recs) == 1 and recs[0]["status"] == "REJECTED_HUMAN"
    assert human_review.verify_log_integrity(log_file)[0] is True

    # Load PDF B with identical field/year/page -> distinct crops dir & unchecked confirmations
    at.session_state["results"] = _make_res("b.pdf", sha_b)
    at.session_state["raw_bytes"] = pdf_b
    at.run()
    assert not at.exception
    assert Path(at.session_state["live_queue"][0]["page_image"]).parent == (
        tmp_path / "sys_tmp" / "live_review_crops" / sha_b
    )
    conf_boxes_b = [c for c in at.checkbox if f"conf-{sha_b}-" in (c.key or "")]
    assert len(conf_boxes_b) == 4
    assert all(cb.value is False for cb in conf_boxes_b)


def test_classic_ui_blocked_fields_health_and_csv_bom(monkeypatch):
    """Verify Classic UI fixes:
    1) overview_screen & ai_screen respect blocked_fields consistently with new_ui
    2) stale blocked_fields clears if decision_log becomes decisive
    3) overview_screen Excel export records refused Health Score ('غير محسوبة')
    4) ai_screen handles Fast Mode deferred commentary without empty warning
    5) metrics_table_screen exports CSV as utf-8-sig (with BOM)
    """
    import io
    import json
    import streamlit as st
    from openpyxl import load_workbook
    import app as app_mod
    from src.ai.gemini_agent import AIAnalysis
    from src.analysis.calculator import compute_year_metrics
    from src.analysis.comparison import build_comparison, growth_metrics

    data = {
        "revenue": {2025: 1_000_000.0, 2026: 1_180_000.0},
        "net_income": {2025: 180_000.0, 2026: 165_000.0},
        "total_assets": {2025: 1_500_000.0, 2026: 1_650_000.0},
        "current_assets": {2025: 600_000.0, 2026: 560_000.0},
        "inventory": {2025: 120_000.0, 2026: 150_000.0},
        "current_liabilities": {2025: 250_000.0, 2026: 340_000.0},
        "total_liabilities": {2025: 700_000.0, 2026: 850_000.0},
        "equity": {2025: 800_000.0, 2026: 800_000.0},
        "operating_cash_flow": {2025: 220_000.0, 2026: 190_000.0},
    }
    prev_m = compute_year_metrics(2025, data, prev_year=None)
    curr_m = compute_year_metrics(2026, data, prev_year=2025)
    rows = build_comparison(prev_m, curr_m)
    g_rows = growth_metrics(prev_m, curr_m)

    # Critical liquidity field blocked in decision_log -> health score must be refused (None)
    r_blocked = {
        "company": "Test Co",
        "file_name": "test.pdf",
        "prev_year": 2025,
        "curr_year": 2026,
        "prev_metrics": prev_m,
        "curr_metrics": curr_m,
        "rows": rows,
        "growth_rows": g_rows,
        "rows_by_key": {x.key: x for x in rows},
        "notes": [],
        "missing": [],
        "document_sha256_16": "deadbeef12345678",
        "decision_log": [
            {"field": "revenue", "year": 2026, "status": "VERIFIED_EXACT", "final": 1_180_000.0},
            {"field": "current_assets", "year": 2026, "status": "CONFLICT", "final": 560_000.0},
        ],
    }

    assert app_mod._blocked_fields(r_blocked) == {"current_assets"}

    # Capture overview_screen warnings & tables & downloads
    warnings: list[str] = []
    infos: list[str] = []
    markdowns: list[str] = []
    downloads: list[dict] = []
    monkeypatch.setattr(st, "session_state", {"currency": "ج.م"})
    monkeypatch.setattr(st, "subheader", lambda *a, **kw: None)
    monkeypatch.setattr(st, "divider", lambda *a, **kw: None)
    monkeypatch.setattr(st, "caption", lambda *a, **kw: None)
    monkeypatch.setattr(st, "markdown", lambda txt, **kw: markdowns.append(str(txt)))
    monkeypatch.setattr(st, "warning", lambda txt, **kw: warnings.append(str(txt)))
    monkeypatch.setattr(st, "info", lambda txt, **kw: infos.append(str(txt)))
    monkeypatch.setattr(st, "plotly_chart", lambda *a, **kw: None)
    monkeypatch.setattr(st, "selectbox", lambda lbl, opts, **kw: opts[0])

    class _DummyCol:
        def markdown(self, txt, **kw):
            markdowns.append(str(txt))

        def caption(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        st,
        "columns",
        lambda spec: [_DummyCol() for _ in range(spec if isinstance(spec, int) else len(spec))],
    )

    class _DummyExp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(st, "expander", lambda *a, **kw: _DummyExp())
    monkeypatch.setattr(
        st,
        "download_button",
        lambda label, data=None, file_name="", mime="", **kw: downloads.append(
            {"label": label, "data": data, "file_name": file_name, "mime": mime}
        ),
    )

    app_mod.overview_screen(r_blocked)
    assert any("مرفوض" in w for w in warnings), "overview_screen must refuse health score when critical pillar is blocked"
    assert "current_assets" in r_blocked["blocked_fields"]
    xlsx_dl = next(d for d in downloads if d["file_name"].endswith(".xlsx"))
    wb = load_workbook(io.BytesIO(xlsx_dl["data"]))
    flat = {row[0].value: row[1].value for row in wb["ملخص"].iter_rows(min_row=2) if row[0].value}
    assert flat["الدرجة الصحية (0-100)"] == "غير محسوبة"

    # ai_screen must export health_score.total == None (not an unblocked numeric score)
    analysis = AIAnalysis(ok=True, ratio_comments=[("Revenue", "+18%")], recommendations=[("Act", "Ev")], model="m")
    downloads.clear()
    app_mod.ai_screen(r_blocked, analysis)
    json_dl = next(d for d in downloads if d["file_name"].endswith(".json"))
    exported = json.loads(json_dl["data"])
    assert exported["health_score"]["total"] is None
    html_dl = next(d for d in downloads if d["file_name"].startswith("financial_report_"))
    assert "غير محسوبة" in html_dl["data"]

    # Fast-mode deferred commentary in Classic ai_screen shows info (no blank warning) and exports remain available
    warnings.clear()
    infos.clear()
    downloads.clear()
    app_mod.ai_screen(r_blocked, AIAnalysis(ok=False, error=""))
    assert warnings == []
    assert any("الوضع السريع" in i for i in infos)
    assert any(d["file_name"].endswith(".json") for d in downloads)

    # metrics_table_screen CSV export must use utf-8-sig BOM
    downloads.clear()
    app_mod.metrics_table_screen(r_blocked)
    csv_dl = next(d for d in downloads if d["file_name"].endswith(".csv"))
    assert isinstance(csv_dl["data"], bytes)
    assert csv_dl["data"].startswith(b"\xef\xbb\xbf")

    # Resolving decision_log to VERIFIED_HUMAN must clear stale blocked_fields
    r_blocked["decision_log"][1]["status"] = "VERIFIED_HUMAN"
    assert app_mod._sync_gate_metadata(r_blocked) == set()
    assert r_blocked["blocked_fields"] == []


def test_streamlit_classic_sidebar_xss_and_currency_reset(tmp_path, monkeypatch):
    """End-to-end AppTest: Classic sidebar escapes XSS in file_name and
    clicking New Analysis in Classic UI clears currency cleanly."""
    from streamlit.testing.v1 import AppTest
    from src.ai import gemini_agent
    from src.analysis import portfolio
    from src.extraction import result_cache

    monkeypatch.setattr(gemini_agent, "_POOL", None)
    monkeypatch.setenv("GEMINI_API_KEYS", "")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("LOCAL_OCR_ENABLED", "0")
    monkeypatch.setattr(portfolio, "LIBRARY_DIR", tmp_path / "companies_library")
    monkeypatch.setattr(result_cache, "CACHE_DIR", tmp_path / "cache")

    at = AppTest.from_file(str(PROJ / "app.py"), default_timeout=120)
    at.run()
    sample_btns = [b for b in at.button if "جرّب بملف العينة" in (b.label or "")]
    sample_btns[0].click()
    at.run()
    if "results" not in at.session_state:
        at.run()
    assert "results" in at.session_state

    # Inject XSS-like filename & custom currency, switch to Classic UI
    r_mut = dict(at.session_state["results"])
    r_mut["file_name"] = '<img src=x onerror=alert(1)>.csv'
    at.session_state["results"] = r_mut
    at.session_state["currency"] = "ج.م"
    at.session_state["ui_mode"] = "classic"
    at.session_state["ui_mode_classic_toggle"] = True
    at.run()
    assert not at.exception

    classic_md = "\n".join(m.value for m in at.markdown)
    assert "<img src=x onerror=alert(1)>" not in classic_md
    assert "&lt;img src=x onerror=alert(1)&gt;.csv" in classic_md

    # Click Classic New Analysis button -> must clear currency as well as results
    new_btns = [b for b in at.button if "تحليل جديد" in (b.label or "")]
    assert new_btns
    new_btns[0].click()
    at.run()
    assert not at.exception
    assert "results" not in at.session_state
    assert "currency" not in at.session_state


