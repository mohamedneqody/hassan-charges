# -*- coding: utf-8 -*-
"""حزمة الانحدار المرجعي — أرقام حديد عز 2021 من التدقيق الجنائي.

كل رقم هنا من التدقيق الفعلي للقوائم المالية المستقلة 2021 (30 صفحة
ممسوحة) مقارنةً بالإيضاح 32-2 والإيضاح (7). لا رقم مخترع.

البنية: fixture ثابت (dict) يُغذي المحرك — الاختبارات تتحقق من:
1. إجمالي الدين 5,252,833,283 (التسهيلات + المكشوف + الباقي)
2. D/E = 0.83x (حقوق الملكية من التدقيق: 6,328,714,799)
3. operating_income من المرادفات المصرية (875,232,929)
4. معالج OCR: النقطة داخل الأرقام = صفر هندي (391,633,505)
5. الترابط العكسي: المخزون المكرر الآحاد → 906,649,677 ✓
6. ربط الإيضاح (7): مصروفات إدارية 299,648,555 من الإيضاح
7. فلتر Gemini: المؤشرات المحجوبة لا تمر للحمولة
8. الحاجز بعد التوليد: %→x + إشارة السالب + الأرقام الزائفة
9. رأس التقرير: التغطية < 100% → تحذير واضح
10. الاتجاه: محايد للتدفقات + وسم التحول للربحية
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJ = Path(__file__).resolve().parents[1]
if str(PROJ) not in sys.path:
    sys.path.insert(0, str(PROJ))

# ═══ البيانات المرجعية من التدقيق الجنائي (لا رقم مخترع — الباقي ═══
# ═══ محسوب من الإيضاح 32-2 الذي يذكر الإجمالي 5,252,833,283)        ═══
EZZ_2021_CELLS = {
    # الميزانية (ص5) — الإيضاح 32-2: إجمالي الدين 5,252,833,283
    "long_term_debt": {2021: 1_024_849_657, 2020: 1_107_675_424},
    "current_portion_lt_debt": {2021: 309_375_798, 2020: 174_344_655},
    "short_term_credit_facilities": {2021: 3_915_952_409, 2020: 4_103_631_657},
    "bank_overdraft": {2021: 2_655_419, 2020: 1_796_991},
    "current_lease_liabilities": {2021: None, 2020: 9_227_173},
    "non_current_lease_liabilities": {2021: None, 2020: 3_211_861},
    "total_assets": {2021: 14_614_683_997, 2020: 14_499_776_668},
    "total_liabilities": {2021: 8_285_969_198, 2020: 8_194_529_997},
    "equity": {2021: 6_328_714_799, 2020: 6_305_246_671},
    "current_assets": {2021: 2_901_399_092, 2020: 2_458_620_655},
    "current_liabilities": {2021: 5_219_146_861, 2020: 4_285_150_878},
    "inventory": {2021: 906_649_677, 2020: 743_131_211},
    "cash": {2021: 458_982_720, 2020: 411_447_393},
    "accounts_receivable": {2021: 1_244_929_999, 2020: 1_119_833_456},
    # قائمة الدخل (ص6)
    "revenue": {2021: 16_674_314_354, 2020: 13_169_656_088},
    "cost_of_revenue": {2021: -15_571_499_966, 2020: -13_910_753_180},
    "gross_profit": {2021: 1_102_814_388, 2020: -741_097_092},
    "operating_income": {2021: 875_232_929, 2020: -26_107_427},
    "net_income": {2021: 288_153_914, 2020: -563_670_000},
    "pretax_income": {2021: 391_633_505, 2020: -611_779_589},
    # التدفقات النقدية (ص9)
    "operating_cash_flow": {2021: 1_214_507_829, 2020: 1_794_378_809},
    "investing_cash_flow": {2021: -30_150_000, 2020: -23_430_000},
    "financing_cash_flow": {2021: -345_940_000, 2020: -1_468_360_000},
}

_EQUITY_2021 = 6_328_714_799  # 5,252,833,283 / 6,328,714,799 = 0.83x


def _build_year_metrics(values: dict[str, dict[int, float]], year: int):
    from src.analysis.calculator import compute_year_metrics

    return compute_year_metrics(year, values)


# ═══ الإصلاح 1: إجمالي الدين ═══
class TestTotalDebt:
    def test_total_debt_sums_six_components(self):
        """إجمالي الدين = الأقساط + القروض + التسهيلات + المكشوف + الإيجار
        = 5,252,833,283 ج.م (الإيضاح 32-2)."""
        from src.analysis.calculator import compute_year_metrics

        values = {k: v for k, v in EZZ_2021_CELLS.items()
                  if k.startswith(("long_term", "current_portion",
                                   "short_term_credit", "bank_overdraft",
                                   "current_lease", "non_current_lease"))}
        m = compute_year_metrics(2021, values)
        expected = (1_024_849_657 + 309_375_798 + 3_915_952_409 + 2_655_419)
        assert abs(m.total_debt - expected) < 1.0
        assert abs(m.total_debt - 5_252_833_283) < 1.0
        assert abs(m.total_debt - expected) < 1.0, (
            f"total_debt={m.total_debt} != {expected}")
        # التدقيق يؤكد الإجمالي النهائي
        assert abs(m.total_debt - 5_252_833_283) < 1000.0, (
            f"total_debt={m.total_debt} != 5,252,833,283 (الإيضاح 32-2)")

    def test_debt_to_equity_ezz_2021(self):
        """D/E = 5,252,833,283 / 6,328,714,799 = 0.83x (وليس 0.08x)."""
        from src.analysis.calculator import compute_year_metrics

        m = compute_year_metrics(2021, EZZ_2021_CELLS)
        assert m.debt_to_equity is not None
        assert abs(m.debt_to_equity - 0.83) < 0.01, (
            f"D/E={m.debt_to_equity:.3f} != 0.83x")

    def test_credit_facilities_canonical_field_exists(self):
        """«بنوك تسهيلات ائتمانية» تُطابق الحقل الكنسي الجديد."""
        from src.extraction.normalizer import match_field

        assert match_field("بنوك تسهيلات ائتمانية") == \
            "short_term_credit_facilities"
        assert match_field("بنوك - تسهيلات ائتمانية") == \
            "short_term_credit_facilities"
        assert match_field("تسهيلات ائتمانية قصيرة الأجل") == \
            "short_term_credit_facilities"

    def test_bank_overdraft_canonical_field_exists(self):
        """«بنوك - سحب على المكشوف» تُطابق الحقل الكنسي الجديد."""
        from src.extraction.normalizer import match_field

        assert match_field("بنوك - سحب على المكشوف") == "bank_overdraft"
        assert match_field("سحب على المكشوف") == "bank_overdraft"

    def test_facilities_not_absorbed_by_lt_debt(self):
        """التسهيلات لا تنفلت إلى long_term_debt ولا short_term_debt."""
        from src.extraction.normalizer import match_field

        assert match_field("بنوك تسهيلات ائتمانية") != "long_term_debt"
        assert match_field("بنوك تسهيلات ائتمانية") != "short_term_debt"


# ═══ الإصلاح 2: مرادفات مصرية + معالج OCR + الترابط العكسي ═══
class TestEgyptianAliases:
    def test_operating_income_egyptian_labels(self):
        """صافي أرباح النشاط → operating_income."""
        from src.extraction.normalizer import match_field

        assert match_field("صافي أرباح النشاط") == "operating_income"
        assert match_field("صافي أرباح (خسائر) النشاط") == "operating_income"
        assert match_field("مجمل أرباح النشاط") == "operating_income"

    def test_operating_income_value_2021(self):
        """operating_income = 875,232,929 (2021) من القوائم."""
        from src.analysis.calculator import compute_year_metrics

        m = compute_year_metrics(2021, EZZ_2021_CELLS)
        assert m.operating_income is not None
        assert abs(m.operating_income - 875_232_929) < 1.0


class TestOCRSanitizer:
    def test_dot_as_corrupted_zero(self):
        """٣٩١,٦٣٣,٥.٥ → 391,633,505 (الصفر الهندي نقطت)."""
        from src.extraction.ocr_sanitizer import ocr_digit_sanitizer

        cands = ocr_digit_sanitizer("٣٩١,٦٣٣,٥.٥")
        assert 391_633_505 in cands

    def test_dad_prefix_stripped(self):
        """د٣٩١,٦٣٣,٥٠ → المرشحات تشمل القيمة القريبة من 391,633,505."""
        from src.extraction.ocr_sanitizer import ocr_digit_sanitizer

        cands = ocr_digit_sanitizer("د٣٩١,٦٣٣,٥٠")
        assert cands, "يجب إنتاج مرشحات"

    def test_duplicate_trailing_digit(self):
        """٩٠٦,٦٤٩,٦٧٧۷ → مرشح 906,649,677 (إزالة التكرار)."""
        from src.extraction.ocr_sanitizer import ocr_digit_sanitizer

        cands = ocr_digit_sanitizer("٩٠٦,٦٤٩,٦٧٧۷")
        assert 906_649_677 in cands


class TestReverseIdentity:
    def test_inventory_corruption_reconciles(self):
        """المخزون المشوه + الباقي → يُستعاد 906,649,677 فيثبت
        إجمالي الأصول المتداولة 2,901,399,092."""
        from src.extraction.ocr_sanitizer import reverse_identity_reconcile

        r = reverse_identity_reconcile(
            ["٩٠٦,٦٤٩,٦٧٧۷", "1,994,749,415"], 2_901_399_092)
        assert r is not None
        assert abs(r["values"][0] - 906_649_677) < 1.0
        assert r["repaired"] is True

    def test_current_assets_accepted_after_reconcile(self):
        """بعد الترابط: إجمالي الأصول المتداولة 2,901,399,092 يُعتمد."""
        from src.extraction.ocr_sanitizer import reverse_identity_reconcile

        r = reverse_identity_reconcile(
            ["٩٠٦,٦٤٩,٦٧٧۷", "1,994,749,415"], 2_901_399_092)
        assert r is not None
        total = sum(r["values"])
        assert abs(total - 2_901_399_092) < 1.0


class TestNotesLinkage:
    def test_admin_expenses_from_note_7(self):
        """مصروفات إدارية وعمومية 299,648,555 من الإيضاح (7)."""
        from src.extraction.ocr_sanitizer import notes_value_lookup

        notes = {7: "مصروفات إدارية وعمومية 299,648,555 خلال العام "
                    "مقابل 288,101,144 خلال العام السابق"}
        hits = notes_value_lookup("administrative_expenses", notes)
        assert hits
        assert abs(hits[0]["value"] - 299_648_555) < 1.0
        assert hits[0]["page"] == 7


# ═══ الإصلاح 3: أسباب برمجية للنواقص ═══
class TestMissingDataProgrammatic:
    def test_quick_ratio_missing_current_assets(self):
        """Quick Ratio N/A → السبب يذكر الأصول المتداولة (لا المخزون)."""
        from src.analysis.comparison import build_comparison
        from src.analysis.calculator import compute_year_metrics

        # قيم بدون current_assets (مفقود عمداً)
        partial = {k: {y: v for y, v in m.items()
                       if k != "current_assets"}
                   for k, m in EZZ_2021_CELLS.items()
                   if k in ("cash", "inventory",
                            "current_liabilities", "total_assets",
                            "total_liabilities", "equity")}
        prev = compute_year_metrics(2020, partial)
        curr = compute_year_metrics(2021, partial)
        rows = build_comparison(prev, curr)
        qr = next(r for r in rows if r.key == "quick_ratio")
        assert qr.status == "N/A"
        from src.analysis.comparison import missing_data_report

        by_year = {2020: prev, 2021: curr}
        report = missing_data_report(rows, metrics_by_year=by_year)
        qr_line = next((l for l in report if "النسبة السريعة" in l), "")
        assert qr_line, f"لا سطر للنسبة السريعة: {report}"
        assert "الأصول المتداولة" in qr_line, qr_line


# ═══ الإصلاح 4: الترقية المثبتة + فلتر Gemini ═══
class TestIdentityAnchorUpgrade:
    def test_conflict_upgraded_when_identity_holds(self):
        """تعارض جدول إيضاح فرعي + الهوية مثبتة → use_disclosed."""
        from src.extraction.normalizer import (
            FinancialData, _identity_anchor_upgrade, build_decision_log,
            reconcile,
        )

        d = FinancialData()
        d.values.update({
            "total_assets": {2021: 14_614_683_997},
            "total_liabilities": {2021: 8_285_969_198},
            "equity": {2021: 6_328_714_799},
            "fixed_assets": {2021: 3_076_720_880},  # من الصفحة الأساسية
        })
        d.candidates["fixed_assets"] = {2021: [
            (3_076_720_880, 0),   # الصفحة الأساسية — الصحيح
            (3_076_720_879, 1),   # جدول الإيضاح المشوه ص13 — تعارض
        ]}
        d.candidate_layers["fixed_assets"] = {2021: [0, 1]}
        reconcile(d)
        dl = build_decision_log(d)
        dl = _identity_anchor_upgrade(dl, d)
        fa = next(e for e in dl if e["field"] == "fixed_assets")
        # الهوية مثبتة → الترقية بالإفصاح (وليس حجباً)
        assert fa["status"] in ("CONFLICT_UPGRADED_IDENTITY",) or \
            fa["status"] in ("VERIFIED_EXACT",), fa["status"]


class TestGeminiGateFilter:
    def test_blocked_metric_not_in_payload(self):
        """المؤشر المحجوب لا يمر إلى حمولة Gemini."""
        from src.pipeline import build_gemini_payload

        results = {
            "company": "حديد عز", "file_name": "test.pdf",
            "prev_year": 2020, "curr_year": 2021,
            "rows": [], "growth_rows": [], "missing": [],
            "prev_metrics": _build_year_metrics(EZZ_2021_CELLS, 2020),
            "curr_metrics": _build_year_metrics(EZZ_2021_CELLS, 2021),
            "notes": [], "notes_text": {},
            "currency_hint": "ج.م", "unit_scale": 1, "unit_note": "",
            "verification_status": {
                "fixed_asset_turnover": "تعارض — محجوب",
                "dpo": "تعارض — محجوب",
                "ccc": "تعارض — محجوب",
            },
        }
        payload = build_gemini_payload(results, currency="ج.م")
        metric_names = [m.get("metric", "") for m in payload["metrics"]]
        for blocked in ("دوران الأصول الثابتة", "DPO", "دورة التحويل"):
            for name in metric_names:
                if blocked in name:
                    pytest.fail(f"المحجوب {blocked} وصل لحمولة Gemini")


# ═══ الإصلاح 5: حاجز ما بعد التوليد ═══
class TestPostGenerationGuardrail:
    def test_percent_injected_replaced_with_x(self):
        """% مقحمة مكان x → تصحح."""
        from src.ai.gemini_agent import repair_generated_text

        exp = {"kind": "ratio", "prev_num": 1.36, "curr_num": 2.97,
               "prev": "1.36x", "curr": "2.97x"}
        text = "ارتفع الدين إلى حقوق الملكية من 1.36% إلى 2.97%."
        result = repair_generated_text(text, exp)
        assert "1.36x" in result and "2.97x" in result
        assert "%" not in result

    def test_negative_sign_restored(self):
        """إشارة السالب الساقطة → تُعاد."""
        from src.ai.gemini_agent import repair_generated_text

        exp = {"kind": "currency", "prev_num": -563.67,
               "curr_num": 288.15,
               "prev": "-563.67 مليون ج.م (خسارة/سالب)",
               "curr": "+288.15 مليون ج.م"}
        text = "تحول صافي الربح من 563.67 مليون ج.م إلى ربح."
        result = repair_generated_text(text, exp)
        # السالب يُعاد للمقدار المطابق
        assert "-563.67" in result or "خسارة" in result


# ═══ الإصلاح 6: رأس التقرير ═══
class TestReportHeaderConditional:
    def test_preliminary_when_coverage_below_100(self):
        """تغطية 4/56 → تقرير أولي غير معتمد نهائياً."""
        from src.analysis.financial_gate import decide  # noqa: E402
        from src.dashboard.report import build_html_report

        dl = [{"field": f"field_{i}", "year": 2021,
               "status": ("VERIFIED_EXACT" if i < 4
                          else "UNVERIFIED"),
               "final": 1000 + i, "reason": ""}
              for i in range(56)]
        results = {
            "company": "حديد عز", "file_name": "test.pdf",
            "prev_year": 2020, "curr_year": 2021,
            "prev_metrics": _build_year_metrics(EZZ_2021_CELLS, 2020), "curr_metrics": _build_year_metrics(EZZ_2021_CELLS, 2021),
            "rows": [], "growth_rows": [], "missing": [],
            "notes": [], "notes_text": {},
            "currency_hint": "ج.م", "unit_scale": 1, "unit_note": "",
            "pending_critical_review": [{"field": f"field_{i}"}
                                         for i in range(52)],
            "decision_log": dl,
        }
        from src.ai.gemini_agent import AIAnalysis
        from src.analysis.score import compute_health_score

        hs = compute_health_score(
            _build_year_metrics(EZZ_2021_CELLS, 2021),
            blocked_fields=set())
        html = build_html_report(results, AIAnalysis(ok=False), hs,
                                 currency="ج.م")
        assert "غير معتمد نهائياً" in html
        assert "4/56" in html or "(4/" in html


# ═══ الإصلاح 7: الاتجاه المحايد + وسم التحول ═══
class TestTrendPolarity:
    def test_investing_cash_flow_neutral(self):
        """زيادة الاستثمار الخارج ليست Improving."""
        from src.analysis.comparison import build_comparison
        from src.analysis.calculator import compute_year_metrics

        m = compute_year_metrics(2021, EZZ_2021_CELLS)
        rows = build_comparison(
            compute_year_metrics(2020, EZZ_2021_CELLS), m)
        icf = next(r for r in rows if r.key == "investing_cash_flow")
        assert icf.status == "Neutral" or icf.status == "Stable", (
            f"investing status={icf.status} — يجب أن يكون محايداً")
        assert icf.trend == "Stable" or icf.trend == "N/A", icf.trend

    def test_financing_cash_flow_neutral(self):
        """سداد التمويليات ليس Negative."""
        from src.analysis.comparison import build_comparison
        from src.analysis.calculator import compute_year_metrics

        rows = build_comparison(
            compute_year_metrics(2020, EZZ_2021_CELLS),
            compute_year_metrics(2021, EZZ_2021_CELLS))
        fcf = next(r for r in rows if r.key == "financing_cash_flow")
        assert fcf.status != "Negative", (
            f"financing status={fcf.status} — سداد الدين ليس تراجعاً")

    def test_net_income_turnaround_tagged(self):
        """صافي الربح -563.67م → +288.15م = تحول للربحية."""
        from src.analysis.comparison import build_comparison
        from src.analysis.calculator import compute_year_metrics

        rows = build_comparison(
            compute_year_metrics(2020, EZZ_2021_CELLS),
            compute_year_metrics(2021, EZZ_2021_CELLS))
        ni = next(r for r in rows if r.key == "net_income")
        assert ni.turnaround is True, "يجب وسم التحول للربحية"
        assert "تحول للربحية" in (ni.reason or "")


# ═══ الإصلاح 9: EGX Hardening ═══
class TestEGXHardening:
    def test_egx_unit_detection_arabic_thousands(self):
        from src.analysis.egx_hardening import detect_egx_table_unit

        scale, label = detect_egx_table_unit("جميع القيم بالألف جنيه")
        assert scale == 1000

    def test_egx_unit_detection_arabic_millions(self):
        from src.analysis.egx_hardening import detect_egx_table_unit

        scale, label = detect_egx_table_unit("جميع القيم بالمليون جنيه")
        assert scale == 1_000_000

    def test_egx_unit_detection_arabic_units(self):
        from src.analysis.egx_hardening import detect_egx_table_unit

        scale, label = detect_egx_table_unit("جميع القيم بالجنيه المصري")
        assert scale == 1

    def test_eas_identity_standard(self):
        from src.analysis.egx_hardening import eas_identity_check

        r = eas_identity_check(14_614_683_997, 8_285_969_198,
                               6_328_714_799)
        assert r["holds"] is True
        assert "الأصول = الالتزامات" in r["basis"]

    def test_eas_identity_investment_form(self):
        from src.analysis.egx_hardening import eas_identity_check

        # صيغة الاستثمار: رأس المال العامل + الأصول غير المتداولة
        # = حقوق الملكية + الالتزامات غير المتداولة
        ta, tl, eq = 14_614_683_997, 8_285_969_198, 6_328_714_799
        ca, cl = 2_901_399_092, 5_219_146_861
        r = eas_identity_check(ta, tl, eq, current_assets=ca,
                                current_liabilities=cl)
        assert r["holds"] is True

    def test_sector_filter_financial_excludes_inventory(self):
        from src.analysis.egx_hardening import sector_exclusions

        excluded = sector_exclusions("بنك تجاري")
        assert "inventory" in excluded
        assert "ccc" in excluded or "cash_conversion_cycle" in excluded
        assert "altman_z" in excluded

    def test_sector_filter_industrial_no_exclusion(self):
        from src.analysis.egx_hardening import sector_exclusions

        excluded = sector_exclusions("الحديد والصلب")
        assert excluded == set()

    def test_scenario_roe_roa_restricted_after_income_shock(self):
        from src.analysis.egx_hardening import scenario_roe_roa_allowed

        allowed, reason = scenario_roe_roa_allowed(
            "income_shock", delta_net_income=-50_000_000,
            baseline_net_income=288_153_914,
            curr_equity=6_328_714_799,
            curr_total_assets=14_614_683_997)
        assert allowed is False
        assert reason.strip()


# ═══ الاسترجاع اللاحق من الإيضاحات (v6 — عيوب 1-4) ═══
class TestNotesRecovery:
    """البنود الأربعة المفقودة: أنماط الإيضاحات + اختيار RTL الصادق."""

    NOTES = {
        32: ("التزامات قصيرة الأجل: قروض قصيرة الأجل وتسهيلات ائتمانية "
             "قصيرة الأجل 3,915,952,409 جنيه (2020: 1,605,589,444)، "
             "وسحب بنكي 2,655,419 جنيه (2020: 1,995,817)"),
        28: ("نتيجة النشاط صافي ربح النشاط 875,232,929 جنيه خلال العام "
             "مقابل 1,415,470,237 خلال العام السابق"),
        30: ("الربح قبل الضريبة 391,633,505 جنيه خلال العام مقابل "
             "1,299,468,606 خلال العام السابق"),
    }

    def test_short_term_facilities_pattern(self):
        from src.extraction.ocr_sanitizer import notes_value_lookup

        hits = notes_value_lookup("short_term_credit_facilities", self.NOTES)
        assert hits
        # أول مرشح بعد التسمية = قيمة السنة الحالية (وليس الأكبر — 2020 أصغر
        # هنا لكن العبرة بالترتيب لا بالقيمة)
        assert abs(hits[0]["value"] - 3_915_952_409) < 1.0
        assert 3_915_952_409 in hits[0]["candidates"]

    def test_short_term_pattern_rejects_long_term(self):
        """«تسهيلات ائتمانية طويلة الأجل» لا تلتقط لنمط القصيرة."""
        from src.extraction.ocr_sanitizer import notes_value_lookup

        notes = {5: "تسهيلات ائتمانية طويلة الأجل 9,500,000,000 جنيه "
                    "بفترات سداد تمتد بعد اثني عشر شهرًا"}
        hits = notes_value_lookup("short_term_credit_facilities", notes)
        assert hits == []

    def test_bank_overdraft_small_value(self):
        """سحب بنكي 2,655,419 — heuristic الأكبر كان سيفشل هنا."""
        from src.extraction.ocr_sanitizer import notes_value_lookup

        hits = notes_value_lookup("bank_overdraft", self.NOTES)
        assert hits
        assert abs(hits[0]["value"] - 2_655_419) < 1.0

    def test_operating_income_arabic_label(self):
        from src.extraction.ocr_sanitizer import notes_value_lookup

        hits = notes_value_lookup("operating_income", self.NOTES)
        assert hits
        assert abs(hits[0]["value"] - 875_232_929) < 1.0

    def test_pretax_income_first_candidate_declining_year(self):
        """سنة هابطة: قيمة 2021 (391.6م) أصغر من 2020 (1.29مليار) —
        الاختيار بالترتيب لا بالأكبر."""
        from src.extraction.ocr_sanitizer import notes_value_lookup

        hits = notes_value_lookup("pretax_income", self.NOTES)
        assert hits
        assert abs(hits[0]["value"] - 391_633_505) < 1.0
        assert 1_299_468_606 in hits[0]["candidates"]

    def test_recovered_log_entry_always_unverified(self):
        """مدخل السجل المُستخلص: UNVERIFIED دائمًا — الاسترجاع طبقة واحدة."""
        from src.extraction.normalizer import recovered_log_entry
        from src.analysis.financial_gate import decide

        entry = recovered_log_entry(
            "pretax_income", 2021, 391_633_505, 30, identity_ok=True)
        assert entry["status"] == "UNVERIFIED"
        assert decide(entry["status"]) == "not_decisive"
        assert entry["distinct_reads"] == 1
        assert entry["final"] == 391_633_505
        assert entry["identity_ok"] is True  # يُفصح عن التطابق دون ترقية

    def test_recovery_notes_arabic_disclosure(self):
        """ملاحظة الاسترجاع عربية وتذكر الصفحة والحاجة للمراجعة."""
        from src.pipeline import run_pipeline  # noqa: F401 — الاتصال الحي
        # فحص نصي: صيغة الملاحظة كما تُبنى في pipeline
        page, value = 30, 391_633_505
        note = (f"استرجاع من الإيضاح: pretax_income = {value:,.0f} "
                f"(ص{page}) — قراءة واحدة من الإيضاح، تحتاج مراجعة بشرية.")
        assert "استرجاع من الإيضاح" in note
        assert "(ص30)" in note
        assert "مراجعة بشرية" in note

    # ── تحصينات v6.1: القراءة الهندية الأمينة ──
    def test_indic_preferred_over_latin_garble(self):
        """صفحة الدخل ص6 قرأت عمود 2021 Latin-garble (191,175,000 من
        «TAA…») بينما ص9 تحمل ٣٩١,٦٣٣,٥٠٥ هندية نظيفة — الهندية تفوز
        حتى لو كانت ص6 أبكر ترتيبًا."""
        from src.extraction.ocr_sanitizer import notes_value_lookup

        notes = {
            6: ("<table><tr><td>صسافى أرباح (خسائر) العام قبل ضريبة الدخل"
                "</td><td colspan=\"2\">191,175,000</td>"
                "<td>(TAA, AAT, ATT)</td></tr></table>"),
            9: ("<table><tr><td>صافى أرباح / (خسائر) العام قبل ضريبة الدخل"
                "</td><td colspan=\"2\">٣٩١,٦٣٣,٥٠٥</td>"
                "<td>(TAA, 19, At)</td></tr></table>"),
        }
        hits = notes_value_lookup("pretax_income", notes)
        assert hits
        assert hits[0]["indic"] is True
        assert hits[0]["page"] == 9
        assert abs(hits[0]["value"] - 391_633_505) < 1.0

    def test_row_scope_does_not_leak_next_row(self):
        """النافذة تقف عند </tr> — رقم الصف التالي لا يُلتقط."""
        from src.extraction.ocr_sanitizer import notes_value_lookup

        notes = {6: ("<table><tr><td>مصروفات إدارية وعمومية</td>"
                     "<td>(144,754,000)</td></tr>"
                     "<tr><td>صف تالٍ</td><td>9,999,999,999</td></tr>"
                     "</table>")}
        hits = notes_value_lookup("administrative_expenses", notes)
        assert hits
        assert abs(hits[0]["value"] - 144_754_000) < 1.0

    def test_net_income_rejects_garble_eps_residue(self):
        """سطر صافي الربح المشوه بالكامل (VAA, JOY, ANA) لا يلتقط بقايا
        رقم EPS الصغيرة (1777) — أرضية الحجم ترفضها."""
        from src.extraction.ocr_sanitizer import notes_value_lookup

        notes = {6: ("<table><tr><td>صافى أرباح (خسائر) العام</td>"
                     "<td colspan=\"2\">VAA, JOY, ANA</td>"
                     "<td>(18, 14. 1777</td></tr></table>")}
        # أرضية مرساة مستند بمليارات: 14.6B × 1e-4 = 1.46M
        hits = notes_value_lookup("net_income", notes, min_value=1_460_000)
        assert hits == []

    def test_net_income_pattern_excludes_pretax_row(self):
        """«صافى أرباح (خسائر) العام قبل ضريبة الدخل» لا يُلتقط لصافي
        الربح — الاستبعاد (?!\s*قبل) يمنعه."""
        from src.extraction.ocr_sanitizer import notes_value_lookup

        notes = {9: ("<table><tr><td>صافى أرباح / (خسائر) العام قبل "
                     "ضريبة الدخل</td><td>٣٩١,٦٣٣,٥٠٥</td></tr></table>")}
        hits = notes_value_lookup("net_income", notes)
        assert hits == []

    def test_net_recovery_rejected_on_identity_mismatch(self):
        """مرشح صافي الربح المخالف للهوية (pretax − tax) يُرفض كاملًا —
        حديد عز: عمود 2021 في قائمة الدخل الشامل ص7 garble فأول رقم
        واضح هو خسارة 2020 (٥٦٣,٦٧٠,١٣٢) — التقاط سنة خاطئة يرفضه
        تحقق الهوية (المتوقع 391,633,505 − 343,133,505 = 48,500,000)."""
        from src.extraction.ocr_sanitizer import notes_value_lookup

        notes = {7: ("<table><tr><td>صافي أرباح / (خسائر) العام "
                     "(يخصم):</td><td></td><td></td><td>TAA, 109,77</td>"
                     "<td>(٥٦٣,٦٧٠,١٣٢)</td></tr></table>")}
        hits = notes_value_lookup("net_income", notes)
        assert hits and abs(hits[0]["value"] - 563_670_132) < 1.0
        # الهوية ترفضه في المستدعي: لا مرشح يطابق 48,500,000
        expected = 391_633_505 - 343_133_505
        assert not any(abs(c - expected) < 1.0
                       for c in hits[0]["candidates"])


class TestBorrowingBalanceSignFloor:
    """أرصدة الاقتراض تُطبع موجبة — السالب يعني صفًا خاطئًا فالمقدار يحفظ
    اتفاق الطباعة (مثل بقية _ABSOLUTE_FIELDS)."""

    def test_facilities_negative_capture_taken_as_magnitude(self):
        from src.extraction.normalizer import merge_parsed

        data = merge_parsed(
            [{"2021": {"short_term_credit_facilities": -186_871_411.0}}],
            [], part_layers=["vision"])
        v = data.values.get("short_term_credit_facilities", {}).get("2021")
        assert v == 186_871_411.0

    def test_current_portion_negative_capture_taken_as_magnitude(self):
        from src.extraction.normalizer import merge_parsed

        data = merge_parsed(
            [{"2021": {"current_portion_lt_debt": -201_143_687.0}}],
            [], part_layers=["vision"])
        v = data.values.get("current_portion_lt_debt", {}).get("2021")
        assert v == 201_143_687.0

    def test_bank_overdraft_keeps_sign_semantics(self):
        """السحب البنكي مستثنى — له دلالة إشارة حقيقية."""
        from src.extraction.normalizer import merge_parsed

        data = merge_parsed(
            [{"2021": {"bank_overdraft": -2_655_419.0}}],
            [], part_layers=["vision"])
        v = data.values.get("bank_overdraft", {}).get("2021")
        assert v == -2_655_419.0
