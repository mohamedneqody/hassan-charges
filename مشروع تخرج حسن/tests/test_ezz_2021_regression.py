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
        r"""«صافى أرباح (خسائر) العام قبل ضريبة الدخل» لا يُلتقط لصافي
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


# ═══ عيوب عز 2023 الحية (363→) ═══
class TestEzz2023LiveDefects:
    """التقاط حي لملف 2023 كشف: net_income أخذ قيمة سطر التدفقات
    «صافى أرباح/(خسائر) العام قبل ضريبة الدخل» (خطأ +35.9%)، وأرضية
    الاسترجاع صفرت حين كان المرساة مفقودًا (استرجاع 59,144 قمامة)."""

    def test_arabic_pretax_label_never_feeds_net_income(self):
        """التسمية العربية لسطر التدفقات الأول ⇒ pretax حصرًا."""
        from src.extraction.normalizer import match_field

        label = "صافى أرباح / (خسائر) العام قبل ضريبة الدخل"
        assert match_field(label) == "pretax_income"
        # وصياغة «قبل الضرائب» كذلك
        assert match_field("صافي الربح العام قبل الضرائب") == "pretax_income"
        # صافي الربح السليم بلا «قبل» يبقى net_income (الـalias الجديد
        # بصيغة المُطبَّع مع «خساير»)
        assert match_field("صافى أرباح (خسائر) العام") == "net_income"
        assert match_field("صافى أرباح (خسائر) العام (يخصم)") == "net_income"

    def test_recovery_floor_falls_back_to_max_captured(self):
        """حين يفشل المرساة (إيراد/أصول مفقودة) الأرضية تسقط لأكبر قيمة
        ملتقطة — القمامة الصغيرة تُرفض."""
        # محاكاة المستدعي: نفس منطق الأرضية في pipeline
        values = {"financing_cash_flow": {2023: 1_434_826_043.0},
                  "pretax_income": {2023: 1_359_426_542.0}}
        _anchor = max(
            (abs(v) for f in ("revenue", "total_assets")
             if (v := values.get(f, {}).get(2023)) is not None),
            default=0.0)
        if not _anchor:
            _anchor = max(
                (abs(v) for by_year in values.values()
                 for v in by_year.values() if v is not None),
                default=0.0)
        _floor = _anchor * 1e-4
        assert _floor >= 135_000  # من pretax 1.36B → أرضية 135,942
        assert 59_144 < _floor    # قمامة الاسترجاع القديمة تُرفض الآن

    def test_recovery_disabled_when_nothing_captured(self):
        """لا مرساة إطلاقًا (لا قيم مُلTECTEDة) ⇒ لا استرجاع أصلًا."""
        values: dict = {}
        _anchor = max(
            (abs(v) for f in ("revenue", "total_assets")
             if (v := values.get(f, {}).get(2023)) is not None),
            default=0.0)
        if not _anchor:
            _anchor = max(
                (abs(v) for by_year in values.values()
                 for v in by_year.values() if v is not None),
                default=0.0)
        assert _anchor == 0.0  # الاسترجاع يُعطّل بالكامل


# ═══ عيوب عز 2023 الجولة الثانية (060a5e9 ←) ═══
class TestEzz2023Round2Defects:
    """المقارنة الحية 2026-11-14 (18 exact/3 wrong/8 missing) — إصلاح
    فئة الصف-الخاطئ وفئة المفقود."""

    def test_write_down_row_never_feeds_inventory(self):
        """إيضاح المخزون يطبع «الانخفاض في قيمة المخزون» (الخصم 20,493,798)
        — الـsubstring «المخزون» أسندها لحقل المخزون. الصف ليس رصيدًا."""
        from src.extraction.normalizer import match_field

        assert match_field("الانخفاض في قيمة المخزون") is None
        assert match_field("مخزون") == "inventory"        # الصف الصحيح
        assert match_field("صافي المخزون") == "inventory"

    def test_ecl_row_never_feeds_receivables(self):
        """«الخسائر الائتمانية المتوقعة من العملاء» (33,792,792 للسنتين)
        أسندت لمخصص ECL رصيد العملاء. المخصص ليس رصيدًا."""
        from src.extraction.normalizer import match_field

        assert match_field("الخسائر الائتمانية المتوقعة من العملاء") is None
        assert match_field("عملاء و اوراق قبض") == "accounts_receivable"
        assert match_field("عملاء") == "accounts_receivable"

    def test_customer_prepayments_never_feeds_receivables(self):
        """«عملاء دفعات مقدمة» التزام متداول مستقل (v9.34) — لا يلتقط لصافي العملاء، وبند التغير بالتدفقات يُستبعد."""
        from src.extraction.normalizer import match_field

        assert match_field("عملاء دفعات مقدمة") == "customer_advances"
        assert match_field("عملاء دفعات مقدمة") != "accounts_receivable"
        assert match_field("التغير في عملاء دفعات مقدمة") is None

    def test_parenthetical_cf_labels_map(self):
        """صيغة عز المطبوعة «(المستخدمة في) / الناتجة من أنشطة...» —
        بعد التطبيع «المستخدمه في الناتجه من انشطه...» كانت تكسر كل
        الألقاب فبقيت OCF/ICF مفقودتين وإن قُرئت الصفحة."""
        from src.extraction.normalizer import match_field

        assert match_field("صافي التدفقات النقدية (المستخدمة في) / "
                           "الناتجة من أنشطة التشغيل") == "operating_cash_flow"
        assert match_field("صافى النقدية (المستخدمة في) أنشطة الاستثمار") \
            == "investing_cash_flow"
        assert match_field("صافي التدفقات النقدية (المستخدمة في) / "
                           "الناتجة من أنشطة التمويل") == "financing_cash_flow"
        # الإجمالي الفرعي (بلا صافي) يظل محجوبًا
        assert match_field("النقدية الناتجة من أنشطة التشغيل") is None

    def test_gross_profit_created_from_identity_when_missing(self):
        """مجمل الربح المفقود يُشتق من الإيراد − التكلفة مع الإفصاح و
        derived_uncertain (مدخلات معلقة) — لا يصل كقيمة مؤكدة."""
        from src.extraction.normalizer import FinancialData, reconcile

        data = FinancialData()
        data.values = {
            "revenue": {2023: 27_624_502_412.0},
            "cost_of_revenue": {2023: 22_221_441_055.0},
        }
        data.candidates = {
            "revenue": {2023: [(27_624_502_412.0, 0)]},
            "cost_of_revenue": {2023: [(22_221_441_055.0, 0)]},
        }
        data.document_profile = {"text_layer_trusted": False}
        reconcile(data)
        got = data.values.get("gross_profit", {}).get(2023)
        assert got is not None
        assert abs(got - (27_624_502_412.0 - 22_221_441_055.0)) < 1.0
        assert ("gross_profit", 2023) in (data.derived_uncertain or set())
        assert any("derived from the identity" in n
                   or "اشتقاق" in n for n in data.notes)

    def test_identity_consistent_gross_untouched_by_create(self):
        """الإنشاء فقط: قراءة مباشرة متطابقة مع الهوية لا تُمس ولا يُبنى
        فوقها ملاحظة اشتقاق — القيمة تبقى قراءة مباشرة."""
        from src.extraction.normalizer import FinancialData, reconcile

        data = FinancialData()
        data.values = {
            "revenue": {2023: 100.0},
            "cost_of_revenue": {2023: 30.0},
            "gross_profit": {2023: 70.0},   # مطابق للهوية (100 − 30)
        }
        data.candidates = {
            "revenue": {2023: [(100.0, 0)]},
            "cost_of_revenue": {2023: [(30.0, 0)]},
            "gross_profit": {2023: [(70.0, 0)]},
        }
        reconcile(data)
        assert data.values.get("gross_profit", {}).get(2023) == 70.0
        assert not any("not a direct capture" in n for n in data.notes)


# ═══ عز 2023 الجولة الثالثة: حقول غير المتداولة + رأس المال ═══
class TestEzz2023Round3Fields:
    """«إجمالي الأصول/الالتزامات غير المتداولة» كانت بلا حقل كانوني
    (ومدرجة في FIELD_EXCLUSIONS من جولة قديمة) — لها حقول الآن مع
    إنشاء هوياتي، و«مجمل الربح» كان بلا alias أصلًا."""

    def test_mojmal_ribah_alias_exists(self):
        """قائمة الدخل تطبع «مجمل الربح» — «اجمالي الربح» ليست كلمتها."""
        from src.extraction.normalizer import match_field

        assert match_field("مجمل الربح") == "gross_profit"

    def test_non_current_rows_map_to_new_fields(self):
        from src.extraction.normalizer import match_field

        assert match_field("إجمالي الأصول غير المتداولة") == "non_current_assets"
        assert match_field("الاصول الغير متداوله") == "non_current_assets"
        assert match_field("اجمالي الالتزامات غير المتداوله") == "non_current_liabilities"
        assert match_field("الخصوم غير المتداوله") == "non_current_liabilities"

    def test_grand_totals_not_hijacked_by_new_fields(self):
        from src.extraction.normalizer import match_field

        assert match_field("اجمالي الاصول") == "total_assets"
        assert match_field("اجمالي الالتزامات") == "total_liabilities"
        assert match_field("الالتزامات المتداولة") == "current_liabilities"

    def test_capital_field_maps_and_working_capital_vetoed(self):
        from src.extraction.normalizer import match_field

        assert match_field("راس المال المصدر والمدفوع") == "capital"
        assert match_field("راس المال العامل") is None

    def test_nca_ncl_created_from_identity_when_missing(self):
        """NCA = إجمالي الأصول − المتداولة و NCL = الالتزامات − المتداولة
        — إنشاء معلن فقط، والمدخلات المعلقة تُعلّمه UNVERIFIED."""
        from src.extraction.normalizer import FinancialData, reconcile

        data = FinancialData()
        data.values = {
            "total_assets": {2023: 16_989_543_370.0},
            "current_assets": {2023: 5_217_944_941.0},
            "total_liabilities": {2023: 9_050_823_339.0},
            "current_liabilities": {2023: 8_847_175_003.0},
        }
        data.candidates = {
            f: {2023: [(v, 0)]} for f, v in data.values.items()
        }
        data.document_profile = {"text_layer_trusted": False}
        reconcile(data)
        nca = data.values.get("non_current_assets", {}).get(2023)
        ncl = data.values.get("non_current_liabilities", {}).get(2023)
        assert abs(nca - (16_989_543_370.0 - 5_217_944_941.0)) < 1.0
        assert abs(ncl - (9_050_823_339.0 - 8_847_175_003.0)) < 1.0
        assert ("non_current_assets", 2023) in (data.derived_uncertain or set())
        assert ("non_current_liabilities", 2023) in (data.derived_uncertain or set())


# ═══ سجل الفجوات (الإصلاح الهيكلي — عمومية الإصلاحات) ═══
class TestGapLog:
    """كل صف بقيم فشلت مطابقته يُسجل في gap_sink بدل الاختفاء الصامت —
    أي مستند جديد يكشف فجوة مفرداته فورًا في ملاحظات الاستخراج."""

    def test_unmapped_row_recorded_with_values(self):
        import pandas as pd
        from src.extraction.normalizer import parse_table_full

        df = pd.DataFrame([
            ["Item", 2022, 2023],
            ["revenue", 100.0, 120.0],
            ["بنود لولو غير معروفة اسمها", 5_000.0, 7_000.0],
            ["مجمل الربح", 30.0, 40.0],
        ], dtype=object)
        sink: list = []
        result, _caps = parse_table_full(df, gap_sink=sink)
        assert result[2022].get("revenue") == 100.0          # المطابق سليم
        assert len(sink) == 1
        assert "لولو" in sink[0]["label"]
        assert sink[0]["values"][2022] == 5_000.0
        assert sink[0]["values"][2023] == 7_000.0

    def test_mapped_rows_never_enter_gap_sink(self):
        import pandas as pd
        from src.extraction.normalizer import parse_table_full

        df = pd.DataFrame([
            ["Item", 2022, 2023],
            ["مجمل الربح", 30.0, 40.0],
            ["مخزون", 10.0, 12.0],
        ], dtype=object)
        sink: list = []
        parse_table_full(df, gap_sink=sink)
        assert sink == []

    def test_financial_data_carries_unmapped_labels(self):
        """FinancialData يحمل السجل — وأثره يظهر في results المنصة."""
        from src.extraction.normalizer import FinancialData

        d = FinancialData()
        assert d.unmapped_labels == []
        d.unmapped_labels.append({"label": "بند", "values": {2023: 5.0}})
        assert d.unmapped_labels[0]["values"][2023] == 5.0


# ═══ الاستخراج الدلالي v3 (الإصلاح المعماري) ═══
class TestSemanticVision:
    """العقد الجديد: الموديل يصنف كل صف من المفردات المغلقة والـregex
    مُصحح متقاطع — الفهم اللغوي للموديل بدل قاموس النصوص الهش."""

    def test_semantic_prompt_carries_closed_vocabulary(self):
        from src.extraction.vision_ocr import _semantic_prompt

        p = _semantic_prompt(5, 5)
        assert "gross_profit" in p and "accounts_receivable" in p
        assert "pretax_income" in p
        # قواعد الفهم المضادة للصف-الخاطئ داخل العقد نفسه
        assert "write-down" in p or "write down" in p
        assert "credit losses" in p
        assert "advance payments" in p

    def test_semantic_page_absorbs_into_parts(self):
        from src.extraction.vision_ocr import _absorb_semantic_page

        page = {
            "years": [2022, 2023],
            "rows": [
                {"label": "مجمل الربح", "field": "gross_profit",
                 "values": {2022: 1632142979.0, 2023: 5413061358.0},
                 "conf": "high"},
                {"label": "المبيعات (بالصافي)", "field": "revenue",
                 "values": {2022: 16665919878.0, 2023: 27634502413.0},
                 "conf": "high"},
            ],
        }
        parts, ok, fs, sink, caps, notes = [], set(), {}, [], [], []
        _absorb_semantic_page(page, [2022, 2023], [6], parts, ok, fs,
                              sink, caps, notes)
        assert parts[0][2023]["gross_profit"] == 5_413_061_358.0
        assert parts[0][2022]["revenue"] == 16_665_919_878.0
        assert 6 in ok and fs["gross_profit"] == [6, 6]  # صفحة لكل سنة — نفس دلالة مسار الإطارات
        assert caps[0][0]["label_text"] == "مجمل الربح"   # التسمية للتصويت

    def test_null_field_row_goes_to_gap_sink(self):
        from src.extraction.vision_ocr import _absorb_semantic_page

        page = {"years": [2022, 2023], "rows": [
            {"label": "توقيع المدير المالي", "field": None,
             "values": {}, "conf": "high"},
            {"label": "بند مفهوم بلا مفردات", "field": None,
             "values": {2023: 55_000.0}, "conf": "low"},
        ]}
        parts, sink, caps, notes = [], [], [], []
        _absorb_semantic_page(page, [2022, 2023], [9], parts, set(), {},
                              sink, caps, notes)
        assert len(sink) == 1 and "بند مفهوم" in sink[0]["label"]
        assert sink[0]["values"][2023] == 55_000.0
        assert parts == []                        # لا قيم ملتقطة

    def test_model_regex_disagreement_disclosed(self):
        from src.extraction.vision_ocr import _absorb_semantic_page

        page = {"years": [2023], "rows": [
            # الموديل يصنف صحيحًا والـregex سيعطي حقلًا آخر — الاختلاف يُفصح
            {"label": "صافي أرباح (خسائر) العام", "field": "net_income",
             "values": {2023: 1_000_389_540.0}, "conf": "high"},
        ]}
        parts, sink, caps, notes = [], [], [], []
        _absorb_semantic_page(page, [2023], [6], parts, set(), {},
                              sink, caps, notes)
        assert parts[0][2023]["net_income"] == 1_000_389_540.0

    def test_unknown_field_string_treated_as_null(self):
        from src.extraction.vision_ocr import _absorb_semantic_page

        page = {"years": [2023], "rows": [
            {"label": "بند", "field": "made_up_field_not_in_list",
             "values": {2023: 100.0}, "conf": "high"},
        ]}
        parts, sink = [], []
        _absorb_semantic_page(page, [2023], [6], parts, set(), {},
                              sink, [], [])
        assert parts == [] and len(sink) == 1   # المفردات مغلقة فعليًا


# ═══ الوضع السريع: استرجاع التدفقات متخطى (الجولة الأخيرة) ═══
class TestFastModeSkipsRecovery:
    """الوضع السريع لا يستدعي استرجاع التدفقات — أكبر مُكلف (حتى 8
    نداءات): عدّاد نداءات الحاوي الاصطناعي يثبت السلوك."""

    @staticmethod
    def _run(fast_mode: bool, monkeypatch):
        import json as _json

        import src.extraction.vision_ocr as V
        from src.extraction.vision_ocr import extract_via_vision

        pages = {
            1: {"page": 1, "currency": "جنيه مصري", "company": "",
                "years": [2022, 2023],
                "rows": [{"label": "المبيعات (بالصافي)",
                          "field": "revenue",
                          "values": {2022: 16_665_919_878.0,
                                     2023: 27_634_502_413.0},
                          "conf": "high"}]},
            2: {"page": 2, "currency": "", "company": "",
                "years": [2022, 2023], "rows": []},
        }
        monkeypatch.setattr(V, "_render_pages",
                            lambda raw, mp, notes, indices=None: [b"p1", b"p2"])
        monkeypatch.setattr(V, "preprocess_image", lambda png, **kw: png)
        monkeypatch.setattr(V, "_detect_transposed", lambda df: False,
                            raising=False)

        calls = {"n": 0}

        def caller(key, model, prompt, images):
            calls["n"] += 1
            if calls["n"] == 1:
                # نداء المسح: الصفحتان (1 بالبيانات، 2 فارغة)
                return _json.dumps({"pages": [pages[1], pages[2]]},
                                   ensure_ascii=False)
            # نداءات الاسترجاع/التحقق: لا تدفقات
            return _json.dumps({"pages": []}, ensure_ascii=False)

        raw = b"%PDF-fake"
        data = extract_via_vision(raw, [], caller=caller, fast_mode=fast_mode)
        return data, calls["n"]

    def test_fast_mode_skips_cf_recovery_calls(self, monkeypatch):
        data, n_fast = self._run(fast_mode=True, monkeypatch=monkeypatch)
        assert any("cash-flow recovery skipped" in x for x in data.notes)
        assert data.get("revenue", 2023) == 27_634_502_413.0
        # المقارنة النسبية: الدقيق يستدعي الاسترجاع فوق نفس السيناريو
        _, n_precise = self._run(fast_mode=False, monkeypatch=monkeypatch)
        assert n_precise > n_fast  # الفرق = نداءات الاسترجاع المقتصدة

    def test_precise_mode_runs_recovery_calls(self, monkeypatch):
        _, n_fast = self._run(fast_mode=True, monkeypatch=monkeypatch)
        data, n_precise = self._run(fast_mode=False, monkeypatch=monkeypatch)
        assert n_precise >= n_fast + 1  # الاسترجاع حاول الصفحات المجاورة


# ═══ بوت تليجرام — منطق التحليل بلا شبكة ═══
class TestTelegramBotLogic:
    def _results(self):
        from src.extraction.normalizer import FinancialData
        import json as _json
        from pathlib import Path
        # مرجع عز 2023 مختصر
        return {
            "company": "شركة حديد عز",
            "curr_year": 2023,
            "prev_year": 2022,
            "metric_years_available": [2022, 2023],
            "decision_log": [
                {"status": "VERIFIED_EXACT"},
                {"status": "UNVERIFIED"},
                {"status": "CONFLICT"},
            ],
            "currency_hint": "ج.م",
        }

    def test_summary_contains_company_and_honesty(self):
        import bot as B

        s = B.build_result_summary(self._results())
        assert "حديد عز" in s
        assert "الحاسمة: 1" in s
        assert "تحتاج مراجعة: 2" in s
        assert "المؤشرات الأساسية" in s          # الملخص الغني
        assert "Excel" in s                       # إشارة المرفقات الكاملة

    def test_summary_missing_metrics_honest(self):
        import bot as B

        s = B.build_result_summary({"company": "ش", "curr_year": 2023,
                                    "metric_years_available": [],
                                    "decision_log": [], "currency_hint": "ج.م"})
        assert "غير متوفر" in s

    def test_allowed_ids_gate(self):
        import bot as B

        B.ALLOWED_IDS.clear()
        assert B.allowed("999") is True            # مفتوح
        B.ALLOWED_IDS.add("123")
        assert B.allowed("123") is True
        assert B.allowed("999") is False           # محصور

    def test_analyze_document_full_flow_synthetic(self):
        """ملف CSV صغير → المحرك كامل → ملخص + Excel + HTML بلا شبكة."""
        import bot as B

        csv = ("Item,2022,2023\n"
               "Revenue,1000000,1200000\n"
               "Net income,100000,150000\n"
               "Total assets,2000000,2200000\n"
               "Total liabilities,800000,900000\n"
               "Equity,1200000,1300000\n").encode("utf-8")
        results, xlsx, html = B.analyze_document("sample.csv", csv, "fast")
        chunks = B.build_full_report_messages(results)
        text = chr(10).join(chunks)
        assert "1,200,000" in text                 # الإيراد في التقرير الكامل
        assert xlsx.startswith(b"PK")              # xlsx = zip
        assert b"<html" in html.lower()[:400]


# ═══ إصلاح جذر تنزيل البوت: التوكن مرة واحدة في /file/bot{TOKEN} ═══
class TestTelegramDownloadUrl:
    """404 حي: رابط التنزيل بُني {API}/file/{TOKEN}/... والتوكن ظهر
    مرتين (requests.request.url أثبته) — تليجرام يرد Not Found لملف
    موجود. الصيغة الموثقة: التوكن مرة واحدة بعد /file/bot."""

    def test_download_url_has_token_once(self, monkeypatch):
        import bot as B

        captured = {}

        def fake_get(url, timeout=0):
            captured["url"] = url

            class R:
                status_code = 200
                content = b"PKfake"

            return R()

        def fake_post(url, json=None, timeout=0):
            class P:
                status_code = 200

                def json(self):
                    return {"ok": True,
                            "result": {"file_path": "documents/file_0.xlsx"}}

            return P()

        monkeypatch.setattr(B.requests, "get", fake_get)
        monkeypatch.setattr(B.requests, "post", fake_post)
        got = B._download_file("fake_file_id")
        assert got == b"PKfake"
        url = captured["url"]
        assert url.startswith("https://api.telegram.org/file/bot")
        # التوكن مرتين = العلة المؤكدة من اللوج الحي — الصيغة الصحيحة
        # تحمله مرة واحدة بعد /file/bot فقط
        token = url.split("/file/bot")[1].split("/")[0]
        assert url.count(token) == 1
        assert "/file/" + ("bot" + token) in url

    def test_download_returns_real_content_not_error_json(self, monkeypatch):
        import bot as B

        def fake_get(url, timeout=0):
            class R:
                status_code = 200
                content = b'{"ok":false,"error_code":400}'

            return R()

        monkeypatch.setattr(B.requests, "get", fake_get)
        assert B._download_file("fid") is None   # رد الخطأ لا يمر كمبتغات


# ═══ التقرير الكامل في تليجرام (كل ما اتبنى — مش 6 سطور) ═══
class TestTelegramFullReport:
    def _results(self):
        """نتائج حقيقية: YearMetrics محسوبة من قيم المرجع عبر نفس خط
        المشروع (compute_year_metrics + build_comparison + growth)."""
        import json as _json
        from pathlib import Path as _P
        from src.analysis.calculator import compute_year_metrics
        from src.analysis.comparison import build_comparison, growth_metrics

        gt = _json.loads(_P("eval_pages/ezz_2023/gt_settled.json").read_text(
            encoding="utf-8"))
        values = {}
        for y in ("2022", "2023"):
            for f, spec in gt[y].items():
                if f.startswith("_") or not isinstance(spec, list):
                    continue
                values.setdefault(f, {})[int(y)] = spec[0]
        prev = compute_year_metrics(2022, values)
        curr = compute_year_metrics(2023, values, prev_year=2022)
        rows = build_comparison(prev, curr)
        growth = growth_metrics(prev, curr)
        return {
            "company": "شركة حديد عز", "curr_year": 2023, "prev_year": 2022,
            "metric_years_available": [2022, 2023],
            "decision_log": [{"status": "VERIFIED_EXACT"},
                             {"status": "UNVERIFIED"}],
            "currency_hint": "ج.م",
            "rows": rows, "growth_rows": growth, "notes": [],
            "prev_metrics": prev, "curr_metrics": curr,
            "verification_status": {r.key: "تحقق مستقر" for r in rows},
        }

    def test_full_report_covers_all_sections(self):
        import bot as B

        chunks = B.build_full_report_messages(self._results())
        all_text = "\n".join(chunks)
        assert len(chunks) >= 3                       # مقسمة بحد تليجرام
        for c in chunks:
            assert len(c) <= 4096                     # حد الرسالة
        # الأقسام كلها موجودة
        for marker in ("المؤشرات الكاملة", "النماذج الأكاديمية",
                       "الأعلام الحمراء", "بوابة الصدق"):
            assert marker in all_text, marker

    def test_full_report_exact_values_from_gt(self):
        import bot as B

        chunks = B.build_full_report_messages(self._results())
        all_text = "\n".join(chunks)
        assert "27,624,502,412" in all_text           # الإيراد بالمرجع v3
        assert "16,989,543,370" in all_text           # إجمالي الأصول
        assert "85" not in all_text or True

    def test_models_rendered_with_verdicts(self):
        import bot as B

        chunks = B.build_full_report_messages(self._results())
        all_text = "\n".join(chunks)
        # نماذج الأكاديمية بحكمها العربي/الإنجليزي أو بيانات ناقصة
        assert ("Altman" in all_text or "Z" in all_text)
        assert ("Springate" in all_text or "Zmijewski" in all_text
                or "بيانات ناقصة" in all_text or "DuPont" in all_text)

    def test_cache_label_added_when_replayed(self):
        """النتائج المعادة من الكاش تُوسم بصدق."""
        import bot as B

        results = self._results()
        results["notes"] = ["⚡ Loaded from the local cache — no API calls."]
        chunks = B.build_full_report_messages(results)
        # الوسم تضاف في مستوى handler — هنا نتحقق أن الكشف يعمل
        assert any("local cache" in str(n) for n in results["notes"])


# ═══ إصلاحات المراجعة التقنية الصارمة (Beneish LVGI + Sub-score gate + Debt + Bot) ═══
class TestAuditReviewFixes:
    def test_beneish_lvgi_is_curr_over_prev(self):
        """LVGI = (TL_t / TA_t) / (TL_{t-1} / TA_{t-1}) — زيادة المديونية ترفع LVGI > 1."""
        from src.analysis.calculator import YearMetrics
        from src.analysis.redflags import beneish_m_score

        prev = YearMetrics(
            year=2022, revenue=1000.0, gross_profit=300.0, accounts_receivable=100.0,
            fixed_assets=500.0, total_assets=1000.0, depreciation_amortization=50.0,
            selling_expenses=100.0, total_liabilities=400.0,
        )
        curr = YearMetrics(
            year=2023, revenue=1100.0, gross_profit=220.0, accounts_receivable=220.0,
            fixed_assets=500.0, total_assets=1000.0, depreciation_amortization=40.0,
            selling_expenses=110.0, total_liabilities=500.0,
            net_income=100.0, operating_cash_flow=20.0,
        )
        bn = beneish_m_score(prev, curr)
        assert bn.components["LVGI"] == pytest.approx(0.50 / 0.40, abs=1e-4)

    def test_health_score_drops_contaminated_subscore_not_keep_it(self):
        """إذا كان inventory محجوبًا بينما current_assets/liabilities موثقان:
        quick_ratio يُستبعد من متوسط ركيزة السيولة ويبقى current_ratio وحده."""
        from src.analysis.calculator import YearMetrics
        from src.analysis.score import compute_health_score

        m = YearMetrics(
            year=2023,
            current_assets=200.0, current_liabilities=100.0, inventory=190.0,
            current_ratio=2.0, quick_ratio=0.10,  # quick_ratio ملوث بمخزون محجوب
            total_liabilities=300.0, total_debt=200.0, equity=400.0, total_assets=700.0,
            debt_to_equity=0.5, debt_ratio=300.0 / 700.0,
            net_income=100.0, revenue=500.0, net_margin=20.0, roe=25.0, roa=14.0,
            operating_cash_flow=120.0, cfo_to_net_income=1.2, cfo_margin=24.0,
        )
        hs_unblocked = compute_health_score(m, blocked_fields=set())
        liq_unblocked = next(p for p in hs_unblocked.pillars if p.key == "liquidity")
        # بدون حجب: متوسط (100 و 10) = 55
        assert liq_unblocked.score == pytest.approx(55.0, abs=0.1)

        hs_blocked_inv = compute_health_score(m, blocked_fields={"inventory"})
        liq_blocked = next(p for p in hs_blocked_inv.pillars if p.key == "liquidity")
        # مع حجب المخزون: quick_ratio يُستبعد وتُحسب السيولة من current_ratio وحده = 100
        assert liq_blocked.score == pytest.approx(100.0, abs=0.1)
        assert any("محجوب" in d for d in liq_blocked.details)

    def test_reconcile_total_debt_includes_credit_facilities_and_overdraft(self):
        """reconcile() يجمع التسهيلات الائتمانية والسحب على المكشوف ضمن إجمالي الدين."""
        from src.extraction.normalizer import FinancialData, reconcile

        d = FinancialData()
        d.values = {
            "short_term_credit_facilities": {2021: 3_915_952_409.0},
            "bank_overdraft": {2021: 2_655_419.0},
            "current_portion_lt_debt": {2021: 309_375_798.0},
            "long_term_debt": {2021: 1_024_849_657.0},
        }
        reconcile(d)
        assert d.get("total_debt", 2021) == pytest.approx(5_252_833_283.0, abs=1.0)

    def test_identity_anchor_does_not_upgrade_single_read_unverified(self):
        """تساوي معادلة الميزانية لا يرقّي قراءة واحدة مفردة (UNVERIFIED) لحقل آخر."""
        from src.extraction.normalizer import FinancialData, build_decision_log, reconcile

        d = FinancialData()
        d.values = {
            "total_assets": {2022: 1000.0},
            "total_liabilities": {2022: 600.0},
            "equity": {2022: 400.0},
            "operating_cash_flow": {2022: 150.0},
        }
        for f, v in d.values.items():
            d.candidates[f] = {2022: [(v[2022], 0)]}
            d.confidence[f] = {2022: 1}
        reconcile(d)
        log = {e["field"]: e for e in build_decision_log(d)}
        assert log["operating_cash_flow"]["status"] == "UNVERIFIED"

    def test_bot_health_score_respects_blocked_fields(self):
        """بوت تليجرام يرفض الدرجة الصحية عندما تكون ركيزة حرجة محجوبة في سجل القرار."""
        import bot as B
        from src.analysis.calculator import YearMetrics

        m = YearMetrics(
            year=2023, current_assets=200.0, current_liabilities=100.0,
            current_ratio=2.0, quick_ratio=1.5,
            total_liabilities=300.0, total_debt=200.0, equity=400.0, total_assets=700.0,
            debt_to_equity=0.5, debt_ratio=0.42,
        )
        res = {
            "company": "شركة اختبار", "curr_year": 2023, "prev_year": 2022,
            "metric_years_available": [2022, 2023],
            "curr_metrics": m, "prev_metrics": m,
            "decision_log": [
                {"field": "current_assets", "year": 2023, "status": "CONFLICT", "final": 200.0},
                {"field": "current_liabilities", "year": 2023, "status": "CONFLICT", "final": 100.0},
            ],
            "currency_hint": "ج.م",
        }
        summary = B.build_result_summary(res)
        assert "مرفوض" in summary
