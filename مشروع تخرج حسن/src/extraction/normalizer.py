"""Label normalization, number parsing, year detection, and table structuring.

Turns raw tables (from CSV/XLSX/PDF) into a canonical structure:
    {canonical_field: {year: value}}
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field

import pandas as pd

from src.config import FIELD_ALIASES, FIELD_EXCLUSIONS
from src.analysis.financial_gate import decide  # حاكمية الحالات — بوابات القرار الأربع

_YEAR_RE = re.compile(r"(?:19|20)\d{2}")

# Arabic-Indic digits -> ASCII, plus Arabic decimal/thousands separators.
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_ARABIC_SEPARATORS = str.maketrans({"٫": ".", "٬": "", "،": " "})

_MISSINGS = {"", "-", "--", "—", "–", "na", "n a", "n/a", "nil", "none", "null", "."}


# ---------------------------------------------------------------------------
# Label normalization
# ---------------------------------------------------------------------------

def normalize_label(value: object) -> str:
    """Normalize a label so matching is insensitive to case, spaces,
    underscores, punctuation, and minor Arabic orthography variants."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    s = str(value)
    s = unicodedata.normalize("NFKC", s)
    s = s.translate(_ARABIC_DIGITS).translate(_ARABIC_SEPARATORS)
    s = s.replace("ـ", "")  # Arabic tatweel
    s = s.lower()
    # Any run of non-alphanumeric characters becomes a single space
    # (covers spaces, underscores, punctuation, "&", "/", parentheses...).
    s = re.sub(r"[^0-9a-z\u0600-\u06FF]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    # Light Arabic normalization: hamza forms -> alef, taa marbuta -> haa, alef maqsura -> yaa
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    s = s.replace("ة", "ه").replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي")
    return s


# Pre-compute normalized alias lookup: normalized alias -> canonical field.
_ALIAS_LOOKUP: dict[str, str] = {}
for _canon, _aliases in FIELD_ALIASES.items():
    _ALIAS_LOOKUP.setdefault(normalize_label(_canon), _canon)
    for _a in _aliases:
        _ALIAS_LOOKUP.setdefault(normalize_label(_a), _canon)

# Longest aliases first, for substring fallback matching.
_SORTED_ALIASES = sorted(_ALIAS_LOOKUP, key=len, reverse=True)

# Whole-word tokens that mark a DERIVED line (margins, growth, per-share, ...).
# Those are computed by the system itself, so source rows must not override them.
_DERIVED_TOKENS = {
    "سهم", "النصيب",
    "growth", "margin", "ratio", "change", "increase", "decrease",
    "percent", "percentage", "eps", "roe", "roa", "roi", "cagr",
    "per", "share", "shares", "vs", "variance", "variation", "ebitda",
    "end", "beginning", "closing", "opening",
    "نمو", "هامش", "نسبه",
}

# Rows that MENTION a field's words but are a different line entirely. A real
# run captured CFO = 1,794,378,809 from the cash-movement neighborhood of the
# statement instead of the printed 1,214,507,829 — CF totals must never come
# from cash-at-period-end / net-cash-movement rows (Arabic forms; the English
# end/beginning tokens above never fire on Arabic documents).
_CASH_MOVEMENT_PATTERNS = (
    "نهايه الفتره", "نهايه العام", "نهايه المده", "نهايه السنه",
    "بدايه الفتره", "بدايه العام", "بدايه المده", "بدايه السنه",
    "الزياده في النقديه", "النقص في النقديه",
    "صافي الزياده", "صافي النقص",
    "التغير في النقديه", "التغيرات في النقديه",
)

# Rows that are structurally NOT a canonical field line, whichever field
# their words may suggest: the CF bridge subtotal mentions الأصول المتداولة/
# الالتزامات المتداولة/صافي الربح, the OCI adjustment row («ناتج تعديل تكلفة
# الأصول») mentions الأصول AND الأرباح المرحلة, comprehensive-income lines
# mention الدخل, NCI-share rows mention أرباح. One real run let
# «ناتج تعديل تكلفة الأصول» feed total_assets and the CF bridge feed
# current_liabilities — these never map, globally.
_GLOBAL_NEGATIVE_PATTERNS = (
    "غير المسيطره", "غير المسيطرين", "حصه غير",
    "قبل التغير في", "قبل التغيرات في",
    "الدخل الشامل", "الربح الشامل", "ناتج تعديل",
)

_FIELD_NEGATIVE_PATTERNS: dict[str, tuple[str, ...]] = {
    "operating_cash_flow": _CASH_MOVEMENT_PATTERNS,
    "investing_cash_flow": _CASH_MOVEMENT_PATTERNS,
    "financing_cash_flow": _CASH_MOVEMENT_PATTERNS,
    # ص6 prints BOTH «صافي أرباح النشاط» (the pre-bridge subtotal) and
    # «صافي أرباح العام» (after the financing / dividends / tax bridge):
    # activity 1,257,960,603 − financing 771,597,390 + subsidiaries'
    # dividends 750,000,000 = pretax 1,236,363,213; pretax − tax
    # 179,626,127 = net income 1,056,737,086. Mixing the rows is a
    # 200M-class error — hard veto both ways. No non-controlling-interest
    # field exists in the standalone statements and none is created.
    "net_income": ("النشاط", "يضاف",
                   # English pretax rows («Net profit for the period BEFORE
                   # INCOME TAX») hijacked net_income in every run — the
                   # veto must cover the English phrasing too
                   "before income tax", "before tax", "before taxes"),
    "pretax_income": ("النشاط", "يضاف"),
    "net_activity_profit": ("العام", "السنه", "قبل ضريبه", "قبل الضريبه",
                            "يضاف", "يخصم"),
    # «إجمالي الالتزامات» (the balance-sheet total) vs «الالتزامات
    # المتداولة» (its current slice) — never feed one to the other.
    "total_liabilities": ("المتداوله", "غير متداوله", "الغير متداوله"),
    "current_liabilities": ("غير المتداوله",),
    # «أقساط قروض طويلة الأجل مستحقة السداد خلال عام» carries the words
    # «قروض طويلة الأجل» but is the CURRENT portion — a live run shipped it
    # as long_term_debt. And «(مدفوعات) لسداد قروض طويلة الأجل» is a CF outflow.
    "long_term_debt": (
        "اقساط", "أقساط", "مستحقه السداد خلال عام",
        "مدفوعات", "مدفوعات لسداد", "متحصلات", "المدفوع",
        "repayment", "proceeds", "paid",
    ),
    # «بنوك - سحب على المكشوف» is its own printed line and is NOT part of
    # the printed borrowings definition (facilities + installments + loans).
    "short_term_debt": ("مكشوف", "تسهيلات ائتمانيه", "مدفوعات", "متحصلات"),
    # إصلاح حديد عز: الحقلان الجديدان — كل بند مطبوع لحاله، ولا يجوز أن
    # يمتصه حقل آخر (short_term_debt توقف عن امتصاص التسهيلات والمكشوف)
    "short_term_credit_facilities": ("مكشوف", "اقساط", "أقساط",
                                      "قروض طويله", "مدفوعات", "متحصلات"),
    "bank_overdraft": ("تسهيلات", "اقساط", "أقساط", "قروض"),
    "current_portion_lt_debt": ("مدفوعات", "متحصلات"),
    "current_lease_liabilities": ("مدفوعات", "المدفوع"),
    "non_current_lease_liabilities": (
        "مستحقه السداد خلال عام", "المستحقه السداد خلال عام",
        "مدفوعات", "المدفوع",
    ),
    # «ضريبة الدخل المؤجلة» is not the period's income-tax expense.
    # (normalize_label unifies ؤ→و: المؤجلة → الموجله)
    # AbuQir root-cause fix (2026-11-05): the income-tax NOTE carries
    # components and bridges that aliased to the P&L total and OUTVOTED it —
    # «Current income tax 1,715,662,071» (×2 repeated note tables) beat the
    # printed «Income tax expense (3,631,829,544)». Components, OCI tax,
    # tax-law bridges and the effective rate are DIFFERENT accounting
    # concepts from the statement expense — generic IFRS vocabulary, both
    # languages (the same note structure exists in Arabic statements).
    "income_tax_expense": (
        "موجله",                                   # deferred (مؤجلة)
        "current income tax",                       # BS balance / note component
        "deferred income tax", "deferred tax",
        "income tax for other comprehensive",
        "deferred tax on other comprehensive",
        "tax on other comprehensive",
        "effective income tax rate",                # a ratio row
        "income tax according to tax law",          # tax-law bridge
        "income tax at income statement",           # note→P&L bridge row
        "income taxes paid", "paid income tax",
        "ضريبه الدخل الحاليه", "الضريبه الحاليه",
        "الضريبه الموجله", "ضريبه مؤجله",
        "معدل الضريبه", "ضريبه الدخل عن عناصر",
        "ضريبه الدخل طبقا", "ضريبه الدخل حسب قانون",
        "الضرايب المدفوعه", "ضريبه الدخل المدفوعه",
    ),
    # «إيرادات التشغيل الأخرى» is not the sales line.
    "revenue": ("اخري", "أخرى"),
    "cash": ("صافي الزياده", "صافي النقص",
             "التغير في النقديه", "التغيرات في النقديه",
             # «النقدية وما في حكمها في أول العام» holds the PRIOR year's
             # ending balance — a live run shipped it as the reporting-year
             # cash (595M) while the printed ending row was 1,804,894,141.
             "في اول العام", "في اول الفتره", "في بدايه العام", "في بدايه الفتره",
             # the cash-flow SUBTOTAL «Cash provided by operating activities»
             # is not the balance-sheet cash line (TE holdout root cause)
             "provided by operating activities", "operating activities"),
    # عز 2023 (التقاط الحي): إيضاح المخزون يطبع صف «الانخفاض في قيمة
    # المخزون» (مخصص الخصم) — الـsubstring «المخزون» أسند قيمة الخصم
    # (20,493,798) لحقل المخزون نفسه (الصحيح 2,092,224,250 من الإيضاح).
    # صف الخصم ليس رصيد المخزون — فيتو حاسم. كما نمنع «مشروعات تحت التنفيذ»
    # الصناعية (أصل غير متداول) ومدفوعات التدفقات النقدية من التداخل مع المخزون العقاري.
    "inventory": (
        "انخفاض", "اضمحلال", "مخصص",
        "تغير", "التغير", "مدفوعات", "متحصلات",
        "مشروعات تحت التنفيذ", "تحويلات",
    ),
    # «رأس المال العامل» مقياس محسوب — ليس رصيد رأس المال المصدر
    "capital": ("عامل",),
    # وإيضاح العملاء يطبع «الخسائر الائتمانية المتوقعة من العملاء» —
    # الـsubstring «العملاء» أسند مخصص ECL (33,792,792) للعميلين معًا.
    # المخصص ليس رصيد العملاء — فيتو حاسم. (normalize: ة→ه، ئ→ي)
    "accounts_receivable": (
        "الائتمانيه", "خساير",
        # «عملاء دفعات مقدمة» التزام عملاء — ليس رصيدًا مدينًا
        "دفعات مقدمه", "دفعات مقدمة",
        "اضمحلال", "الاضمحلال", "مخصص",
        "اطراف ذات علاقه", "اطراف ذوي علاقه",
    ),
    # نفس الفيتو للموردين: «موردون - دفعات مقدمة» أصل متداول وليس التزاماً،
    # و«الخسائر الائتمانية المتوقعة من الموردين» مخصص (718,191 أسقط 2.94B في 2023!)
    "accounts_payable": (
        "الائتمانيه", "خساير",
        "دفعات مقدمه", "دفعات مقدمة",
        "اضمحلال", "الاضمحلال", "مخصص",
        "اطراف ذات علاقه", "اطراف ذوي علاقه",
        "مدفوعات", "متحصلات",
    ),
    # مجمع الإهلاك / رصيد أول وآخر المدة أرصدة ميزانية — ليست مصروف إهلاك الفترة
    "depreciation_amortization": (
        "مجمع", "accumulated", "رصيد اول", "رصيد اخر",
        "في اول العام", "في اخر العام", "في نهايه العام",
    ),
    # الأصول الثابتة (رصيد الميزانية) — يُمنع تسلل سطور التدفقات النقدية أو الدخل
    # مثل «أرباح/خسائر رأسمالية من بيع أصول ثابتة» أو «متحصلات بيع أصول ثابتة» أو «إهلاك أصول ثابتة»
    "fixed_assets": (
        "اهلاك", "استهلاك", "مجمع", "اضمحلال",
        "بيع", "ارباح", "خساير", "راسماليه",
        "مدفوعات", "متحصلات", "شراء", "اقتناء", "اضافات", "تخريد", "استبعادات",
        "مشروعات تحت التنفيذ",
        "disposal", "gain", "loss", "proceeds", "purchase", "additions", "depreciation",
    ),
}

# A raw cell containing a percent sign is a ratio, never an absolute amount.
_PERCENT_CHARS = ("%", "٪")

# Component/flow QUALIFIERS that void a GENERIC alias match (المهمة: رقم
# صحيح على مفهوم خاطئ). «Intangible assets» is not total_assets; «Cash
# paid…» is not the cash balance; «equity securities» is not equity;
# «Non Current Liabilities» is not current_liabilities. Generic only —
# no document-specific words.
_GENERIC_ALIAS_VETOES: dict[str, tuple[str, ...]] = {
    "total_assets": ("intangible", "under construction", "right of use",
                     "fixed assets", "financial assets", "non current",
                     "non-current", "fair value", "amortized cost",
                     "usufruct", "lease", "investments", "inventories",
                     "receivable", "deferred"),
    "cash": ("paid", "receipts", "purchases", "provided by", "used in",
             "net change", "net increase", "net decrease", "beginning",
             "collected", "at the end"),
    "equity": ("securities", "fair value", "method", "changes in",
               "statement of"),
    "current_liabilities": ("non current", "non-current"),
    "current_assets": ("non current", "non-current"),
    "total_liabilities": ("non current", "non-current", "current"),
}

# A generic alias must match at WORD BOUNDARIES — «ebit» inside «debit»,
# «debt» inside «debtors» are NOT matches.
_WORD_BOUNDARY_CACHE: dict = {}


def _alias_matches(norm: str, alias: str) -> bool:
    import re as _re

    pat = _WORD_BOUNDARY_CACHE.get(alias)
    if pat is None:
        pat = _re.compile(
            r"(?<![a-z0-9])" + _re.escape(alias) + r"(?![a-z0-9])")
        _WORD_BOUNDARY_CACHE[alias] = pat
    return bool(pat.search(norm))


# Statement-section context for repeated same-label rows (المهمة: «Creditors
# and other credit balances» prints under BOTH the non-current AND the
# current liabilities sections — the label alone is ambiguous; the section
# header above the row disambiguates). Generic accounting structure.
_CURRENT_SECTION_FIELDS = frozenset({
    "accounts_payable", "current_liabilities", "inventory", "cash",
    "accounts_receivable",
})
_NONCURRENT_SECTION_FIELDS = frozenset({
    "long_term_debt", "non_current_lease_liabilities",
})


def match_field(label: object) -> str | None:
    """Map a raw line-item label to a canonical field, or None."""
    norm = normalize_label(label)
    if not norm or norm in FIELD_EXCLUSIONS:
        return None
    if any(pat in norm for pat in _GLOBAL_NEGATIVE_PATTERNS):
        return None
    if set(norm.split()) & _DERIVED_TOKENS:
        return None
    field = None
    if norm in _ALIAS_LOOKUP:
        field = _ALIAS_LOOKUP[norm]
    else:
        # Substring fallback: longest alias contained in the label, at WORD
        # BOUNDARIES («ebit» ⊄ «debit», «debt» ⊄ «debtors»), and generic
        # aliases are VOIDED by component/flow qualifiers.
        for alias in _SORTED_ALIASES:
            if len(alias) >= 4 and _alias_matches(norm, alias):
                field = _ALIAS_LOOKUP[alias]
                vetoes = _GENERIC_ALIAS_VETOES.get(field)
                if vetoes and any(v in norm for v in vetoes):
                    field = None          # a qualified component, keep scanning
                    continue
                break
    # A "before tax" row is NEVER net income — however the OCR phrased it
    # ("صافي ربح العام قبل ضريبة الدخل" / "قبل الضريبة" are pretax, not net).
    # عز 2023: remap بدل الإسقاط — الإسقاط كان يفقد سطر الربح قبل
    # الضريبة بالكامل بينما الفلسفة الإنجليزية أدناه تعيد توجيهه (وعز
    # 2023 كان يفقد pretax من سطر التدفقات الأول فيُشتق بدل أن يُقرأ)
    if field == "net_income" and ("قبل الضريبه" in norm or "قبل ضريبه" in norm):
        field = "pretax_income"
    # English pretax rows are PRETAX INCOME, not a hijacked net income —
    # remap instead of dropping («Net profit for the period before income
    # tax» is the printed pretax line on TE-style statements)
    if field == "net_income" and ("before income tax" in norm
                                  or "before tax" in norm
                                  or "before taxes" in norm):
        field = "pretax_income"
    # حديد عز 2023 (التقاط حي): التسمية العربية لسطر التدفقات الأول
    # «صافى أرباح / (خسائر) العام قبل ضريبة الدخل» كانت تُسند
    # لـincome_tax_expense (الـsubstring «ضريبه الدخل» داخل التسمية!)
    # ولـnet_income عبر مرشحات صافي الربح — net_income أخذ قيمة الربح
    # قبل الضريبة (خطأ +35.9% مقابل المرجع). أي تسمية تحمل «قبل ضريب»
    # هي سطر الربح قبل الضريبة حصرًا، مهما حوى من كلمات أخرى.
    # (normalize يجعل «ضرائب» ⇒ «ضرايب»)
    if ("قبل ضريب" in norm or "قبل الضرايب" in norm
            or "قبل ضرايب" in norm):
        field = "pretax_income"
    # The Ezz-style statement prints BOTH a pre-financing subtotal
    # («النقدية الناتجة من أنشطة التشغيل») AND the true net line
    # («صافي النقدية الناتجة…») — first-capture-wins then shipped the
    # SUBTOTAL as CFO (1,794M − 580M paid financing = the real 1,214M).
    # Only the line carrying «صافي» is the operating total.
    if field == "operating_cash_flow" and "صافي" not in norm and (
        "النقديه الناتجه" in norm or "النقديه النائجه" in norm
        # normalize_label renders ئ as ي: «النائجة» → «النايجه»
        or "النقديه النايجه" in norm
    ):
        return None
    # A row that mentions a field's words but is a different line (cash at
    # period end, net cash movement) must never feed that field.
    for pat in _FIELD_NEGATIVE_PATTERNS.get(field, ()):
        if pat in norm:
            return None
    return field


# ---------------------------------------------------------------------------
# Number and year parsing
# ---------------------------------------------------------------------------

def parse_number(raw: object) -> float | None:
    """Parse a financial cell value to float.

    Handles thousands separators, currency symbols, parenthesized negatives,
    percentages (value kept as the printed number), and dash/blank cells.
    Returns None when the cell holds no usable number.
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        val = float(raw)
        return val if math.isfinite(val) else None

    s = str(raw).strip().translate(_ARABIC_DIGITS).translate(_ARABIC_SEPARATORS)
    if normalize_label(s) in _MISSINGS:
        return None

    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1]
    # Keep digits, dot and sign; drop currency symbols, letters, %, NBSP...
    s = re.sub(r"[^0-9.\-]", "", s)
    if not re.search(r"\d", s):
        return None
    try:
        val = float(s)
    except ValueError:
        return None
    return -abs(val) if negative else val


def extract_year(raw: object) -> int | None:
    """Extract a fiscal year (1990-2099) from a header cell like
    '2025', 'FY2026', 'Dec 31, 2025', '٢٠٢٢/١٢/٣١' (Arabic-Indic digits),
    or a datetime-like value."""
    if raw is None:
        return None
    if hasattr(raw, "year"):  # datetime / Timestamp
        y = int(raw.year)
        return y if 1990 <= y <= 2099 else None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        if not math.isfinite(float(raw)):  # NaN / inf empty cells
            return None
        y = int(raw)
        return y if 1990 <= y <= 2099 else None
    s = str(raw).translate(_ARABIC_DIGITS)  # ٢٠٢٢ → 2022
    m = _YEAR_RE.search(s)
    if m:
        y = int(m.group(0))
        return y if 1990 <= y <= 2099 else None
    return None


# ---------------------------------------------------------------------------
# Table structuring
# ---------------------------------------------------------------------------

@dataclass
class FinancialData:
    """Canonical financial values: field -> year -> value.

    `candidates` keeps EVERY value captured for a field/year (with capture
    order) so `reconcile()` can pick the accounting-identity-consistent one
    instead of blindly trusting the first occurrence.
    """
    values: dict[str, dict[int, float]] = field(default_factory=dict)
    candidates: dict[str, dict[int, list[tuple[float, int]]]] = field(default_factory=dict)
    # سجل الفجوات: صفوف بقراءات فشلت مطابقتها لأي حقل — تشخيص هيكلي
    # يكشف فجوات مفردات كل مستند جديد فورًا بدل الاختفاء الصامت
    unmapped_labels: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    currency_hint: str | None = None
    company_hint: str | None = None  # company name read from the document itself
    # المهمة: وحدة الطباعة المكتشفة من ترويسة القائمة نفسها (مثل
    # «in EGP Thousands»). القيم المخزنة تبقى كما طُبعت حرفيًا — scale
    # للعرض فقط، والقرار يوثّق الدليل في unit_note.
    unit_scale: int = 1
    unit_note: str = ""
    # field -> year -> independent agreeing reads (1 = single capture,
    # 2 = cross-statement vote or focused verify agree, 3 = 2-of-3 with local
    # OCR). The audit-trail UI surfaces this as witness dots per figure.
    confidence: dict[str, dict[int, int]] = field(default_factory=dict)
    # page -> local Indra text of EVERY page (esp. الإيضاحات المتممة) — feeds
    # the notes RAG (search/Q&A) which the table-only sweep never kept.
    notes_text: dict[int, str] = field(default_factory=dict)
    # Verification Decision Log support — (field, year) -> human-readable note:
    # which final values were DERIVED or settled by VOTE (never silently).
    derived: dict = field(default_factory=dict)
    vote_outcomes: dict = field(default_factory=dict)
    # (field, year) -> True when the field participated in a SATISFIED
    # accounting identity — honest metadata: identity-consistent is NOT the
    # same as independently verified.
    identity_ok: dict = field(default_factory=dict)
    # Source-aware provenance (المهمة: إسناد المصدر) — (field, year) ->
    # CellEvidence.as_dict(): WHERE the value came from (digital cell, PDF
    # text, OCR…) with the verifiable evidence (file hash, sheet, address,
    # label, year, data type). Source is metadata — verification stays with
    # the status ladder; never conflated.
    cell_provenance: dict = field(default_factory=dict)
    # per-candidate provenance aligned with candidates order: the normalized
    # LABEL each capture came from and the extraction LAYER it was read by
    # (text | local_ocr | vision) — the vote independence guard needs both
    candidate_labels: dict = field(default_factory=dict)
    candidate_layers: dict = field(default_factory=dict)
    # المهمة 2: three SEPARATE sign fields per candidate — the RAW printed
    # cell string, the parsed signed value (already in candidates), and the
    # accounting sign convention detected for the row (parentheses/negative
    # print vs magnitude convention)
    candidate_raw: dict = field(default_factory=dict)
    # per-candidate snippet geometry: bbox in page pixels + page + render
    # scale (المهمة 3 — إحداثيات القصاصة والمصدر والدقة محفوظة)
    candidate_bbox: dict = field(default_factory=dict)
    # document source profile (document_profiler): kind, text-quality
    # metrics and text_layer_trusted — set for PDFs, absent for Excel
    document_profile: dict = field(default_factory=dict)
    # the pipeline path that produced this data (SCANNED_OCR | NATIVE_PDF_TEXT
    # | NATIVE_SPREADSHEET_CELL | VISION_MODEL) — the fallback source label
    # for values without cell-level provenance
    extraction_source: str = "SCANNED_OCR"

    def bump_confidence(self, field_name: str, year: int, level: int) -> None:
        if level > self.confidence.get(field_name, {}).get(year, 0):
            self.confidence.setdefault(field_name, {})[year] = level

    @property
    def years(self) -> list[int]:
        seen: set[int] = set()
        for by_year in self.values.values():
            seen.update(by_year)
        return sorted(seen, reverse=True)

    def latest_two_years(self) -> tuple[int, int] | None:
        ys = self.years
        return (ys[1], ys[0]) if len(ys) >= 2 else None  # (previous, current)

    def get(self, field_name: str, year: int) -> float | None:
        return self.values.get(field_name, {}).get(year)


def _cell_is_number_like(cell: object) -> bool:
    return parse_number(cell) is not None


def _detect_transposed(df: pd.DataFrame) -> bool:
    """True when years live in the first column or the index
    (rows = years, columns = line items)."""
    if sum(extract_year(c) is not None for c in df.columns) >= 2:
        return False
    if sum(extract_year(v) is not None for v in df.index) >= 2:
        return True
    first_col = df.iloc[:, 0]
    return sum(extract_year(v) is not None for v in first_col) >= 2


def _find_year_header(df: pd.DataFrame) -> tuple[int, dict[int, int]] | None:
    """Locate the row index holding >= 2 year cells.

    Returns (row_index, {column_position: year}) or None.
    """
    col_years = {i: extract_year(c) for i, c in enumerate(df.columns)}
    if sum(y is not None for y in col_years.values()) >= 2:
        # pandas already parsed the header; body starts at row 0.
        return -1, {i: y for i, y in col_years.items() if y is not None}

    scan = df.head(12)
    for idx, row in scan.iterrows():
        year_cells = {i: extract_year(v) for i, v in enumerate(row)}
        if sum(y is not None for y in year_cells.values()) >= 2:
            return idx, {i: y for i, y in year_cells.items() if y is not None}
    return None


def _row_label(row: pd.Series, year_cols: set[int]) -> str | None:
    """First text cell containing actual letters (e.g. 'ضريبة الدخل (25%)')
    in the first few columns = the label. Pure numbers never qualify, even
    when mixed with digits or punctuation."""
    for i, cell in enumerate(row):
        if i in year_cols:
            continue
        if i > 3:
            break
        if (
            isinstance(cell, str)
            and cell.strip()
            and extract_year(cell) is None
            and re.search(r"[A-Za-z\u0600-\u06FF]", cell)
        ):
            return cell
    return None


def parse_table(df: pd.DataFrame, gap_sink: list | None = None
                ) -> dict[int, dict[str, float]]:
    """Parse one DataFrame into {year: {canonical_field: value}}.

    Tables without a detectable two-year header return {}.
    gap_sink: سجل الفجوات — الصفوف ذات القيم التي فشلت مطابقتها تُسجل
    فيها (label + values) بدل الاختفاء الصامت."""
    return parse_table_full(df, gap_sink=gap_sink)[0]


def parse_table_full(
    df: pd.DataFrame,
    gap_sink: list | None = None,
) -> tuple[dict[int, dict[str, float]], list[dict]]:
    """parse_table + one capture record per value (label, year, position,
    transposed flag) so digital sources can attach verifiable evidence.

    gap_sink (سجل الفجوات): كل صف يحمل قيمة وتفشل مطابقته يُسجَّل فيه
    {label, values} — التشخيص الهيكلي بدل الاختفاء الصامت: أي مستند
    جديد يكشف فجوة مفرداته فورًا ويظهر في ملاحظات الاستخراج."""
    captures: list[dict] = []
    if df.empty:
        return {}, captures
    transposed = _detect_transposed(df)
    if transposed:
        # Rotate years-in-first-column/index layouts into the wide shape.
        df = df.T

    found = _find_year_header(df)
    if found is None:
        return {}, captures
    header_idx, year_cols_map = found
    year_cols = set(year_cols_map)

    result: dict[int, dict[str, float]] = {}
    body = df if header_idx == -1 else df.iloc[header_idx + 1:]
    for row_pos, row in body.iterrows():
        label = _row_label(row, year_cols)
        if label is None:
            continue
        canonical = match_field(label)
        if canonical is None:
            # سجل الفجوات: الصف يحمل أرقامًا لكنه بلا حقل — يُحفظ
            # تشخيصيًا بدل الاختفاء الصامت (فجوات المفردات تظهر فورًا)
            if gap_sink is not None:
                gap_vals: dict[int, float] = {}
                for col_pos, year in year_cols_map.items():
                    raw_cell = row.iloc[col_pos] if col_pos < len(row) else None
                    if isinstance(raw_cell, str) and any(
                            c in raw_cell for c in _PERCENT_CHARS):
                        continue
                    v = parse_number(raw_cell)
                    if v is not None:
                        gap_vals[year] = v
                if gap_vals:
                    gap_sink.append({
                        "label": str(label).strip()[:120],
                        "values": gap_vals,
                    })
            continue
        for col_pos, year in year_cols_map.items():
            raw_cell = row.iloc[col_pos] if col_pos < len(row) else None
            # Percentage cells are ratios, not absolute amounts — skip them.
            if isinstance(raw_cell, str) and any(c in raw_cell for c in _PERCENT_CHARS):
                continue
            value = parse_number(raw_cell)
            if value is None:
                continue
            result.setdefault(year, {}).setdefault(canonical, value)
            raw_cell = str(raw_cell) if raw_cell is not None else ""
            negative_print = raw_cell.strip().startswith("(")                 and raw_cell.strip().endswith(")")                 or raw_cell.strip().startswith("-")
            captures.append({
                "field": canonical, "year": year, "value": value,
                "label_text": str(label).strip(),
                "raw_printed": raw_cell.strip()[:40],
                "print_convention": ("negative-printed" if negative_print
                                     else "magnitude-printed"),
                # df position → openpyxl 1-based address is computed by the
                # caller that knows the physical layout; None when unknown
                "row": None if transposed else int(row_pos) + 1,
                "col": None if transposed else int(col_pos) + 1,
                "transposed": transposed,
            })
    return result, captures


def merge_parsed(parts: list[dict[int, dict[str, float]]], notes: list[str],
                 evidences: list[dict] | None = None,
                 captures_per_part: list[list[dict]] | None = None,
                 part_layers: list[str] | None = None) -> FinancialData:
    """Merge per-table parses, keeping every candidate for reconciliation.
    `evidences` attaches source provenance to the FIRST capture of each
    (field, year); `captures_per_part` (parse_table_full output per part)
    records each candidate's normalized LABEL, and `part_layers` names the
    extraction layer per part (text | local_ocr | vision) — both are kept
    ALIGNED with the candidates order so the majority vote can tell an
    independent witness from the same note table echoed twice."""
    data = FinancialData(notes=notes)
    order = 0
    for pi, part in enumerate(parts):
        caps = (captures_per_part[pi] if captures_per_part
                and pi < len(captures_per_part) else [])
        cap_by_key: dict[tuple[int, str], str] = {}
        raw_by_key: dict[tuple[int, str], dict] = {}
        for c in caps:
            for cyear in ([c["year"]] if isinstance(c.get("year"), int) else []):
                cap_by_key[(cyear, c["field"])] = normalize_label(
                    c.get("label_text") or "")
                raw_by_key[(cyear, c["field"])] = {
                    "raw_printed": str(c.get("raw_printed") or "")[:40],
                    "print_convention": c.get("print_convention", "unknown"),
                }
        layer = (part_layers[pi] if part_layers and pi < len(part_layers)
                 else "text")
        for year, fields in part.items():
            for canonical, value in fields.items():
                if canonical in _ABSOLUTE_FIELDS and value is not None:
                    value = abs(value)  # balance-sheet items are magnitudes
                by_year = data.candidates.setdefault(canonical, {})
                by_year.setdefault(year, []).append((value, order))
                data.candidate_labels.setdefault(canonical, {}).setdefault(
                    year, []).append(cap_by_key.get((year, canonical), ""))
                data.candidate_raw.setdefault(canonical, {}).setdefault(
                    year, []).append(raw_by_key.get((year, canonical), {
                        "raw_printed": "", "print_convention": "unknown"}))
                data.candidate_layers.setdefault(canonical, {}).setdefault(
                    year, []).append(layer)
                order += 1
                # first-wins base; reconcile() may override with better values
                data.values.setdefault(canonical, {}).setdefault(year, value)
    for ev in (evidences or []):
        key = (ev.get("field"), ev.get("year"))
        if key not in data.cell_provenance and ev.get("year") is not None:
            data.cell_provenance[key] = ev
    return data


# Accounting identities used to pick the right value when a field was captured
# more than once (e.g. "total assets" vs "total NON-CURRENT assets"):
# target = sum(sign * |component|)
_IDENTITY_GROUPS: list[tuple[str, tuple[tuple[str, int], ...]]] = [
    ("total_assets", (("total_liabilities", 1), ("equity", 1))),
    ("gross_profit", (("revenue", 1), ("cost_of_revenue", -1))),
    ("operating_income", (("gross_profit", 1), ("operating_expenses", -1))),
    ("net_income", (("pretax_income", 1), ("income_tax_expense", -1))),
]

_TOLERANCE = 0.005  # identities must hold within 0.5%
_MAX_CANDIDATES = 4
# By-DEFINITION income identities: when the captured value violates them and
# all components exist, the identity value REPLACES the capture. Balance-sheet
# totals (total_assets) are NOT force-derived: OCR errors in a component
# (e.g. capturing non-current liabilities as total liabilities) would corrupt
# a correct capture — instead the violation is flagged for the user.
# net_income was REMOVED (2026-10-31) after a live misfire: a hijacked
# pretax capture (wrong row) plus a wrong tax row overwrote a CORRECT
# 1,056,737,086 with a derived 1,208,469,355. Net income is printed on THREE
# statements and the cross-statement vote already polices it — the identity
# now only FLAGS (⚠) a disagreement.
_DERIVE_IF_FAILS = {"gross_profit"}

# Balance-sheet items are magnitudes — OCR sometimes flips their sign
# (inventory -128M, receivables -478M...). Normalize to positive.
_ABSOLUTE_FIELDS = {
    "total_assets", "current_assets", "inventory", "accounts_receivable",
    "cash", "fixed_assets", "accounts_payable", "current_liabilities",
    "total_liabilities", "short_term_debt", "long_term_debt",
    "total_debt", "equity",
    # أرصدة اقتراض تُطبع موجبة دائمًا في قائمة المركز — التقاط سالب =
    # صف حركة/فائدة قرئ في مكان الخطأ (حديد عز جولة التسريع: −186.9م)
    # — المقدار يحفظ الاتفاق مع طباعة القوائم (bank_overdraft مستثنى:
    # له دلالة إشارة حقيقية)
    "short_term_credit_facilities", "current_portion_lt_debt",
    # عز 2023: الأرصدة غير المتداولة ورأس المال — أرصدة تُطبع موجبة
    "non_current_assets", "non_current_liabilities", "capital",
}


def _digit_close(a: float, b: float) -> bool:
    """Near-exact agreement (OCR digit identity, not a percentage band)."""
    return abs(a - b) <= max(1.0, 1e-6 * max(abs(a), abs(b)))


def _majority_vote(data: FinancialData) -> None:
    """Cross-statement voting: a figure printed on several statements (net
    income appears on the income statement, the equity statement AND the
    first line of the cash-flow statement) is captured several times. When
    ≥2 INDEPENDENT witnesses agree digit-exactly, they outvote a disagreeing
    minority capture — free verification with zero extra API calls.

    Independence guard (AbuQir root cause, 2026-11-05): candidates are
    deduplicated to WITNESSES first — the same note line echoed by repeated
    tables («Current income tax 1,715,662,071» in two note sections) is ONE
    witness, not two. Echoed copies of one source must never outvote the
    primary statement; only ≥2 DISTINCT (label, value) witnesses count."""
    for field, by_year in data.candidates.items():
        for year, cands in list(by_year.items()):
            vals = [v for v, _ in cands if v is not None]
            if len(vals) < 2:
                continue
            labels = (data.candidate_labels.get(field, {}).get(year) or [])
            labels = labels + [""] * (len(cands) - len(labels))
            # witnesses: distinct (normalized label, digit-class value).
            # The echo-collapse applies ONLY when the labels are KNOWN —
            # without label knowledge two agreeing captures are counted as
            # two witnesses (the pre-provenance semantics).
            seen: list[tuple[str, float]] = []
            labels_known = any(lbl for lbl in labels)
            for (v, _o), lbl in zip(cands, labels):
                if v is None:
                    continue
                if labels_known and lbl:
                    w = next((i for i, (wl, wv) in enumerate(seen)
                              if wl == lbl and _digit_close(wv, v)), None)
                    if w is None:
                        seen.append((lbl, v))
                else:
                    seen.append(("", v))
            witness_vals = [sv for _l, sv in seen]
            best_val, best_count = None, 1
            for v in witness_vals:
                count = sum(1 for w in witness_vals if _digit_close(v, w))
                if count > best_count:
                    best_val, best_count = v, count
            if best_val is None or best_count < 2:
                continue  # no INDEPENDENT agreement — keep first-capture
            current = data.values.get(field, {}).get(year)
            # Partial-note D&A guard (حارس إهلاك الإيضاحات الجزئية):
            # In EAS/IFRS statements, Cash Flow prints TOTAL depreciation
            # while COGS/Selling/G&A notes each print a strictly smaller
            # partial slice (e.g. COGS D&A 39M echoed in two notes vs Cash Flow
            # total D&A 49M). Echoed partial slices must NEVER outvote a larger
            # total period depreciation capture.
            if field == "depreciation_amortization":
                max_cand = max((abs(v) for v in vals), default=0.0)
                if max_cand > 0 and abs(best_val) < 0.95 * max_cand:
                    continue
            # Balance-sheet detail guard: Balance-Sheet-only detail stocks
            # (AP, AR, Inventory, Fixed Assets, Cash) appear ONCE on the primary
            # Balance Sheet (guaranteed first by ascending page order + verified
            # by _verify_core_fields). Later occurrences are note sub-tables or
            # Cash Flow working-capital deltas (Δ) — echoed note/CF values must
            # NEVER replace the primary Balance Sheet capture via majority vote.
            if (
                field in ("accounts_receivable", "accounts_payable", "inventory", "fixed_assets", "cash")
                and current is not None
                and not _digit_close(current, best_val)
            ):
                continue
            # Record EVERY majority outcome that has a dissenting capture —
            # even when the winner equals the current value. A live run once
            # had two digit-close WRONG reads outvote the correct one; the
            # decision log must preserve that dissent, never fold it away.
            dissent = [v for v in vals if not _digit_close(v, best_val)]
            # the audit trail records the outcome whenever an INDEPENDENT
            # majority exists — dissent or not (the audited TE cell had none)
            if best_count >= 2:
                layers_all = (data.candidate_layers.get(field, {}).get(year)
                              or [])
                winner_layers = sorted({l for (v, _o), l in zip(cands, layers_all)
                                        if v is not None
                                        and _digit_close(v, best_val)})
                data.vote_outcomes[(field, year)] = {
                    "winner": best_val, "votes": best_count,
                    "total": len(vals), "witnesses": len(witness_vals),
                    "winner_layers": winner_layers,
                    "replaced": current, "dissent": dissent,
                    "contested": current is not None and not _digit_close(current, best_val),
                }
            if current is not None and not _digit_close(current, best_val):
                data.values.setdefault(field, {})[year] = best_val
                data.notes.append(
                    f"Cross-statement majority vote: '{field}' in {year} set to "
                    f"{best_val:,.0f} ({best_count} INDEPENDENT witnesses) — "
                    f"replaced a disagreeing capture of {current:,.0f}."
                )
            data.bump_confidence(field, year, min(best_count, 3))
            # downstream identity groups should see the winner only
            data.candidates[field][year] = [(best_val, 0)]


_CROSS_STATEMENT_SIGN_FIELDS = frozenset({
    "cost_of_revenue",
    "selling_expenses",
    "admin_expenses",
    "other_operating_expenses",
    "operating_expenses",
    "rd_expenses",
    "interest_expense",
    "income_tax_expense",
    "depreciation_amortization",
    "dividends_from_subsidiaries",
    "bank_overdraft",
    "other_operating_income",
})


def reconcile(data: FinancialData) -> None:
    """Choose the value for each disputed field that satisfies the most
    accounting identities. Statements legitimately violate identities
    (other income, discontinued ops), so identities are SCORED, never forced:
    the combo satisfying the most wins, ties keep first-occurrence order."""
    import itertools

    # 1) Cross-statement sign-convention alignment + Note tail-precision refinement:
    #    a) In multi-page PDFs (`len(pages) >= 2`), primary statements print expenses
    #       in parentheses `(-383,519,092)` while Note schedules print positive tables
    #       `(+383,519,092)`, or P&L prints `+750M` dividends while Cash Flow deducts
    #       `(-750M)`, or BS prints `+2.65M` overdraft while Cash Note subtracts `(-2.65M)`.
    #       When ALL candidates across >=2 distinct pages have the EXACT same magnitude,
    #       align their signs to the primary statement's capture so cross-page echoes
    #       never trigger a false sign-conflict (single-page / page-less sign conflicts
    #       remain strictly gated!).
    #    b) When Page 6 smudges the last 3 digits to `000` (e.g. `-299,648,000`) while
    #       the dedicated Note table on Page 12 prints the exact same leading thousands
    #       with non-zero units (`299,648,555`), adopt the full-precision Note magnitude
    #       with the primary statement's sign and preserve the truncated read in `replaced_values`.
    fs_pages_map = getattr(data, "field_sources", {}) or {}
    for field, by_year in list(data.candidates.items()):
        distinct_pages = sorted(set(fs_pages_map.get(field, [])))
        if len(distinct_pages) < 2:
            continue
        for year, cands in list(by_year.items()):
            non_null = [(v, o) for v, o in cands if v is not None]
            if len(non_null) < 2:
                continue
            primary = data.values.get(field, {}).get(year)
            if primary is None or primary == 0:
                primary = non_null[0][0]
            if primary == 0:
                continue
            primary_sign = -1.0 if primary < 0 else 1.0

            # Case (a): exact same magnitude across >=2 pages, opposite signs
            if field in _CROSS_STATEMENT_SIGN_FIELDS:
                mags = [abs(v) for v, _ in non_null]
                has_pos = any(v > 0 for v, _ in non_null)
                has_neg = any(v < 0 for v, _ in non_null)
                if has_pos and has_neg and all(_digit_close(m, mags[0]) for m in mags[1:]):
                    aligned_val = primary_sign * mags[0]
                    data.candidates[field][year] = [
                        (aligned_val if v is not None else v, o) for v, o in cands
                    ]
                    data.values.setdefault(field, {})[year] = aligned_val
                    data.notes.append(
                        f"Cross-statement sign convention aligned for '{field}' in {year} "
                        f"({aligned_val:,.0f} across pages {distinct_pages})."
                    )
                    continue

            # Case (b): exact thousand-prefix match where primary ends in `000` (margin smudge)
            # and the companion Note schedule carries the exact last 3 digits
            if field in ("admin_expenses", "selling_expenses", "other_operating_expenses", "cost_of_revenue"):
                mags = [round(abs(v)) for v, _ in non_null]
                if len(set(mags)) == 2:
                    m_trunc = min(mags, key=lambda m: 0 if (m % 1000 == 0) else 1)
                    m_exact = max(mags, key=lambda m: 1 if (m % 1000 != 0) else 0)
                    if (
                        m_trunc >= 1_000_000
                        and m_trunc % 1000 == 0
                        and m_exact % 1000 != 0
                        and (m_trunc // 1000) == (m_exact // 1000)
                    ):
                        healed_val = primary_sign * float(m_exact)
                        old_val = data.values.get(field, {}).get(year)
                        if old_val is not None and not _digit_close(old_val, healed_val):
                            data.replaced_values = getattr(data, "replaced_values", {})
                            data.replaced_values.setdefault((field, year), []).append(old_val)
                        data.values.setdefault(field, {})[year] = healed_val
                        data.candidates[field][year] = [
                            (healed_val if v is not None else v, o) for v, o in cands
                        ]
                        data.notes.append(
                            f"Refined thousand-truncated '{field}' in {year} from {old_val:,.0f} "
                            f"to Note schedule exact value {healed_val:,.0f} (pages {distinct_pages})."
                        )

    _majority_vote(data)

    # Total D&A preference over partial departmental note slices:
    # When multiple positive period D&A candidates exist (e.g. Cash Flow total
    # 49M alongside COGS note 39M and Selling note 0.12M), prefer the largest
    # valid period D&A candidate (sanity-bounded by fixed assets when known)
    # without upgrading its verification status.
    for year in list(data.years):
        da_cands = [v for v, _o in (data.candidates.get("depreciation_amortization", {}).get(year) or []) if v is not None]
        if len(da_cands) >= 2:
            fa = data.get("fixed_assets", year)
            valid = [v for v in da_cands if abs(v) > 0 and (fa is None or fa <= 0 or abs(v) <= 2.0 * abs(fa))]
            if valid:
                best_da = max(valid, key=abs)
                cur_da = data.get("depreciation_amortization", year)
                if cur_da is None or abs(best_da) > 1.05 * abs(cur_da):
                    data.values.setdefault("depreciation_amortization", {})[year] = best_da
                    data.notes.append(
                        f"Selected total period depreciation ({best_da:,.0f}) in {year} over smaller "
                        f"departmental note sub-allocation ({cur_da:,.0f})."
                        if cur_da is not None else
                        f"Selected total period depreciation ({best_da:,.0f}) in {year}."
                    )

    # Tax bridge (جسر الضريبة): net income and pretax income are the two most
    # verified figures in the system (NI prints on three statements and is
    # re-read by the verify layers). Their difference IS the income tax — a
    # live run captured the PARTIAL «ضريبة الدخل» row (−167.9M) while the
    # printed «إجمالي ضريبة الدخل عن العام» was −179.6M. Appending the implied
    # value as a free extra candidate lets the identity scoring prefer it over
    # garbled OCR of the tax rows — but ONLY anchored on a net income that at
    # least two independent captures/verifies agree on.
    for year in list(data.years):
        ni = data.get("net_income", year)
        pretax = data.get("pretax_income", year)
        if ni is None or pretax is None:
            continue
        if (data.confidence.get("net_income", {}) or {}).get(year, 0) < 2:
            continue
        # المهمة: المشتق لا يرقّى بمدخلات غير موثوقة — when the anchor NI's
        # agreement came from ONE layer on an UNTRUSTED document, the bridge
        # may still APPEND the implied candidate (identity scoring may use
        # it) but the derived tax is flagged derived_uncertain → the
        # decision log shows UNVERIFIED, never a confident VERIFIED_DERIVED
        _profile_untrusted = not (getattr(data, "document_profile", {})
                                  or {}).get("text_layer_trusted", True)
        _ni_vote = (getattr(data, "vote_outcomes", {}) or {}).get(
            ("net_income", year)) or {}
        _ni_layers = set(_ni_vote.get("winner_layers") or [])
        if not _ni_layers:
            _ni_layers = set(l for l in
                             ((getattr(data, "candidate_layers", {}) or {})
                              .get("net_income", {}).get(year) or []) if l)
        if _profile_untrusted and len(_ni_layers) < 2:
            data.derived_uncertain = getattr(data, "derived_uncertain", set())
            data.derived_uncertain.add(("income_tax_expense", year))
        implied = ni - pretax
        cands = data.candidates.setdefault("income_tax_expense", {}).setdefault(year, [])
        if not any(_digit_close(v, implied) for v, _ in cands):
            cands.append((implied, 10 ** 9))

    for target, comps in _IDENTITY_GROUPS:
        group_fields = (target,) + tuple(c[0] for c in comps)
        for year in list(data.years):
            cand_lists = {}
            for f in group_fields:
                base_cands = list(data.candidates.get(f, {}).get(year, [])[:_MAX_CANDIDATES])
                vote_f = (getattr(data, "vote_outcomes", {}) or {}).get((f, year)) or {}
                for idx_d, d_val in enumerate(vote_f.get("dissent") or [], start=1):
                    if d_val is not None and not any(_digit_close(d_val, bv) for bv, _ in base_cands):
                        base_cands.append((d_val, 100 + idx_d))
                cand_lists[f] = base_cands[:_MAX_CANDIDATES]
            if not cand_lists[target]:
                continue  # nothing captured for the target field this year
            best_assignment: dict[str, float] | None = None
            best_key = (-1, None)
            for combo in itertools.product(*(cand_lists[f] for f in group_fields)):
                assignment = {f: v for f, (v, _) in zip(group_fields, combo)}
                order_sum = sum(o for _, o in combo)
                t = assignment[target]
                components = sum(
                    sign * abs(assignment[c]) for c, sign in comps
                )
                residual = abs(t - components)
                scale = max(abs(t), components, 1.0)
                score = 1 if residual <= _TOLERANCE * scale else 0
                key = (score, -order_sum)
                if best_assignment is None or key > best_key:
                    best_assignment, best_key = assignment, key
            if best_assignment is not None and best_key[0] == 1:
                for f in group_fields:
                    data.identity_ok[(f, year)] = True
            if best_assignment is None:
                continue
            t = best_assignment[target]
            components = sum(sign * abs(best_assignment[c]) for c, sign in comps)
            residual = abs(t - components)
            scale = max(abs(t), components, 1.0)
            if residual > _TOLERANCE * scale:
                if target in _DERIVE_IF_FAILS and all(
                    best_assignment[c] is not None for c, _ in comps
                ):
                    derived = components
                    # Guard for gross_profit = revenue - |cost_of_revenue|:
                    # If COGS had a 1-digit OCR slip (e.g. 6.38B read as 1.38B)
                    # while printed gross_profit (453M) is consistent with
                    # operating_income (-26M), replacing gross_profit with 5.45B
                    # destroys gross margin & Beneish GMI. Heal COGS instead!
                    heal_cogs = False
                    if target == "gross_profit":
                        op_inc = data.get("operating_income", year)
                        rev_v = best_assignment.get("revenue")
                        if (
                            op_inc is not None
                            and rev_v
                            and abs(derived - t) > 0.25 * abs(rev_v)
                            and abs(t - op_inc) < 0.25 * abs(derived - op_inc)
                        ):
                            heal_cogs = True
                    if heal_cogs:
                        implied_cogs = -(abs(best_assignment["revenue"]) - t)
                        old_cogs = best_assignment["cost_of_revenue"]
                        data.notes.append(
                            f"Replaced garbled 'cost_of_revenue' in {year} ({old_cogs:,.0f}) "
                            f"with identity value ({implied_cogs:,.0f} = -(Revenue - Gross Profit)) "
                            f"because printed gross_profit ({t:,.0f}) aligns with operating_income."
                        )
                        best_assignment["cost_of_revenue"] = implied_cogs
                        best_assignment[target] = t
                    else:
                        data.notes.append(
                            f"Replaced captured '{target}' in {year} ({t:,.0f}) with the "
                            f"identity value ({derived:,.0f} = "
                            + " + ".join(
                                (f"|{c}|" if s == 1 else f"-|{c}|") for c, s in comps
                            ) + ")."
                        )
                        best_assignment[target] = derived
                else:
                    # Balance-sheet totals: never force-derive — flag instead.
                    first_captured = cand_lists[target][0][0]
                    best_assignment[target] = first_captured
                    derived_tax_note = None
                    if (target == "net_income"
                            and best_assignment.get("income_tax_expense") is not None
                            and best_assignment.get("pretax_income") is not None):
                        # Tax fallback (الضريبة المشتقة): a live run garbled the
                        # printed tax row (−205.4M vs −179.6M). NI and pretax are
                        # the two most-verified anchors — their difference IS the
                        # tax. Derived transparently with its own ⚠ note, never
                        # silently, and only when it actually differs.
                        implied_tax = (best_assignment["net_income"]
                                       - best_assignment["pretax_income"])
                        if not _digit_close(best_assignment["income_tax_expense"], implied_tax):
                            derived_tax_note = (
                                f"⚠ income_tax_expense in {year} derived from the "
                                f"identity (NI − pretax = {implied_tax:,.0f}) — the "
                                "printed tax row was garbled; verify against the "
                                "إجمالي ضريبة الدخل line of the notes."
                            )
                            best_assignment["income_tax_expense"] = implied_tax
                    if derived_tax_note:
                        data.notes.append(derived_tax_note)
                    else:
                        data.notes.append(
                            f"⚠ Accounting identity check FAILED for {target} in {year}: "
                            f"captured {first_captured:,.0f} but "
                            + " + ".join(c for c, _ in comps)
                            + f" = {components:,.0f}. The captured value was kept — "
                            "verify the source page (possible extraction/OCR error)."
                        )
            for f, value in best_assignment.items():
                if data.values.get(f, {}).get(year) != value:
                    if data.values.get(f, {}).get(year) is not None:
                        _vf = (getattr(data, "vote_outcomes", {}) or {}).get((f, year)) or {}
                        # the REPLACED capture is preserved and surfaced in the
                        # decision log — the original OCR error is never hidden
                        data.replaced_values = getattr(data, "replaced_values", {})
                        data.replaced_values.setdefault((f, year), []).append(
                            data.values.get(f, {}).get(year))
                        if (_vf.get("contested")
                                and _vf.get("replaced") is not None
                                and _digit_close(value, _vf["replaced"])):
                            data.notes.append(
                                f"Accounting identity confirmed primary capture for '{f}' in {year} "
                                f"({value:,.0f}) over conflicting note-table majority "
                                f"({data.values.get(f, {}).get(year):,.0f})."
                            )
                            (getattr(data, "vote_outcomes", {}) or {}).pop((f, year), None)
                        else:
                            data.notes.append(
                                f"Reconciled '{f}' in {year} to {value:,.0f} using the "
                                f"accounting identity ({target} = "
                                + " + ".join(c for c, _ in comps) + ")."
                            )
                            # Decision Log: a value rewritten by reconciliation is
                            # DERIVED, never silently presented as a direct capture
                            data.derived[(f, year)] = (
                                f"identity ({target} = "
                                + " + ".join(c for c, _ in comps) + ")"
                            )
                            # المهمة: المشتق لا يرقّى بمدخلات غير موثوقة — when the
                            # identity's INPUT values are backed by ONE layer on an
                            # UNTRUSTED document, the derived value is flagged
                            # derived_uncertain → UNVERIFIED in the decision log
                            _profile_untrusted = not (
                                getattr(data, "document_profile", {}) or {}
                            ).get("text_layer_trusted", True)
                            if _profile_untrusted:
                                _input_layers = set()
                                for _cf, _s in comps:
                                    _v = (getattr(data, "vote_outcomes", {})
                                          or {}).get((_cf, year)) or {}
                                    _input_layers.update(
                                        _v.get("winner_layers") or [])
                                    _input_layers.update(
                                        l for l in
                                        ((getattr(data, "candidate_layers", {})
                                          or {}).get(_cf, {}).get(year) or [])
                                        if l)
                                if len(_input_layers) < 2:
                                    data.derived_uncertain = getattr(
                                        data, "derived_uncertain", set())
                                    data.derived_uncertain.add((f, year))
                    data.values.setdefault(f, {})[year] = value
                # downstream groups should see the reconciled value only
                data.candidates[f][year] = [(value, 0)]

    # عز 2023: الإجمالي المفقود يُشتق هوياتيًا بدل أن يبقى N/A — عز قدمت
    # الإيراد والتكلفة ملتقطين (مطابقين للطباعة) بينما مجمل الربح لم
    # يُلتقط قط، فبقي هامش المجمل N/A رغم أن الطرح حسم مطبوعًا. الإنشاء
    # فقط: لا قراءة مباشرة تُستبدل، والمشتق يحمل ملاحظة صريحة و
    # derived_uncertain حين تكون المدخلات معلقة (قراءة مسح واحد) — لا
    # يصل للمؤشرات كقيمة مؤكدة أبدًا.
    _CREATE_IDENTITIES: list[tuple[str, tuple[tuple[str, int], ...]]] = [
        ("gross_profit", (("revenue", 1), ("cost_of_revenue", -1))),
        # عز 2023: التكلفة بلا قراءة (الصفحة المنحلة سُقطت) — تُشتق
        # عكسيًا من الإيراد والمجمل المُنشأ قبله (الترتيب جوهري)
        ("cost_of_revenue", (("revenue", 1), ("gross_profit", -1))),
        # عز 2023: «إجمالي الأصول/الالتزامات غير المتداولة» بلا حقول
        # كانونية — تُنشأ من الإجماليات الكبيرة والمتداولة
        ("non_current_assets",
         (("total_assets", 1), ("current_assets", -1))),
        ("non_current_liabilities",
         (("total_liabilities", 1), ("current_liabilities", -1))),
    ]
    for target, comps in _CREATE_IDENTITIES:
        for year in list(data.years):
            if data.get(target, year) is not None:
                continue  # قراءة مباشرة موجودة — لا إنشاء فوقها
            comp_vals = {c: data.get(c, year) for c, _s in comps}
            if any(v is None for v in comp_vals.values()):
                continue  # مكوّن مفقود — لا اشتقاق
            derived = sum(sign * abs(comp_vals[c]) for c, sign in comps)
            formula = " + ".join(
                (c if s == 1 else f"− {c}") for c, s in comps)
            data.values.setdefault(target, {})[year] = derived
            data.derived = getattr(data, "derived", {})
            data.derived[(target, year)] = f"identity ({target} = {formula})"
            data.candidates.setdefault(target, {}).setdefault(
                year, []).append((derived, 0))

            def _input_verified(f_: str, y_: int) -> bool:
                """مدخل المشتق موثوق عند: تصويت مستقل ≥2 (مع طبقتين على
                مستند مصنّف غير موثوق)، أو خلية رقمية بفحص المصدر الكامل
                (VERIFIED_SOURCE_EXACT)."""
                ok, _ev, _fails = _source_exact(data, f_, y_)
                if ok:
                    return True
                if (getattr(data, "confidence", {}).get(f_, {}).get(y_, 0) < 2):
                    return False
                _prof = getattr(data, "document_profile", {}) or {}
                if not _prof.get("text_layer_trusted", True) and _prof.get("kind") != "NATIVE_SPREADSHEET":
                    _vo = (getattr(data, "vote_outcomes", {}) or {}).get((f_, y_)) or {}
                    _wl = set(_vo.get("winner_layers") or [])
                    if not _wl:
                        _wl = {
                            l for l in ((getattr(data, "candidate_layers", {}) or {}).get(f_, {}).get(y_) or [])
                            if l
                        }
                    if len(_wl) < 2:
                        return False
                return True

            _pending_inputs = any(
                not _input_verified(c, year) for c, _s in comps)
            # الفحص الموحد كافٍ: مسار xlsx يحمل text_layer_trusted=False
            # عمدًا (الثقة عبر فحص الأدلات) — بروفايله لا يعلم المشتق
            if _pending_inputs:
                data.derived_uncertain = getattr(
                    data, "derived_uncertain", set())
                data.derived_uncertain.add((target, year))
            data.notes.append(
                f"⚠ '{target}' in {year} derived from the identity "
                f"({formula} = {derived:,.0f}) — not a direct capture; "
                "verify against the printed statement."
            )

    # Sanity cross-checks: a detail item can never exceed its total.
    for year in list(data.years):
        cl = data.get("current_liabilities", year)
        tl = data.get("total_liabilities", year)
        if cl is not None and tl is not None and cl > tl:
            data.notes.append(
                f"⚠ Sanity check: current liabilities ({cl:,.0f}) exceed total "
                f"liabilities ({tl:,.0f}) in {year} — the current-liabilities "
                "capture is likely wrong; verify the source page."
            )
        ca = data.get("current_assets", year)
        ta = data.get("total_assets", year)
        if ca is not None and ta is not None and ca > ta:
            data.notes.append(
                f"⚠ Sanity check: current assets ({ca:,.0f}) exceed total assets "
                f"({ta:,.0f}) in {year} — verify the source page."
            )

    # Debt mapping (تعريف الدين) — two explicit definitions, derived and
    # flagged: borrowings = bank facilities + current portion of LT loans +
    # non-current LT loans; financial debt adds lease liabilities. A live run
    # once shipped total_debt = 201M because the bank-facilities row and the
    # current-portion row had no matching fields.
    for year in list(data.years):
        st_d = data.get("short_term_debt", year)
        cp = data.get("current_portion_lt_debt", year)
        lt_d = data.get("long_term_debt", year)
        st_cf = data.get("short_term_credit_facilities", year)
        ovd = data.get("bank_overdraft", year)
        has_short = (st_d is not None or st_cf is not None or ovd is not None)
        if has_short and (lt_d is not None or cp is not None):
            # A directly captured total-debt row (e.g. «إجمالي القروض والتسهيلات»)
            # that disagrees with the component sum is a CONFLICT — logged, and
            # the COMPONENT SUM wins per the mandate (items beat opaque totals),
            # with the direct row preserved in the decision log.
            borrowings = (
                abs(st_d or 0.0) + abs(st_cf or 0.0) + abs(ovd or 0.0)
                + abs(cp or 0.0) + abs(lt_d or 0.0)
            )
            direct_total = data.get("direct_total_debt", year)
            if direct_total is not None and abs(direct_total - borrowings) > max(1.0, 0.005 * direct_total):
                data.notes.append(
                    f"⚠ CONFLICT: direct total-debt row ({direct_total:,.0f}) disagrees with "
                    f"the component sum ({borrowings:,.0f}) in {year} — "
                    "components used; verify the source row.")
            data.values.setdefault("borrowings_excl_leases", {})[year] = borrowings
            data.derived[("borrowings_excl_leases", year)] = (
                "تسهيلات بنكية/ائتمانية + سحب على المكشوف + أقساط قروض متداولة + قروض غير متداولة")
            # المهمة: نفس قاعدة انتشار عدم اليقين — single-layer inputs on an
            # untrusted document keep the derived debt mapping UNVERIFIED
            _prof_untrusted = not (getattr(data, "document_profile", {})
                                   or {}).get("text_layer_trusted", True)
            if _prof_untrusted:
                _in_layers = set()
                for _cf in ("short_term_debt", "short_term_credit_facilities",
                            "bank_overdraft", "current_portion_lt_debt",
                            "long_term_debt"):
                    _in_layers.update(
                        l for l in
                        ((getattr(data, "candidate_layers", {}) or {})
                         .get(_cf, {}).get(year) or []) if l)
                if len(_in_layers) < 2:
                    data.derived_uncertain = getattr(
                        data, "derived_uncertain", set())
                    data.derived_uncertain.add(("borrowings_excl_leases", year))
                    data.derived_uncertain.add(("total_debt", year))
            data.candidates.setdefault("borrowings_excl_leases", {})[year] = [(borrowings, 0)]
            nc_l = data.get("non_current_lease_liabilities", year)
            c_l = data.get("current_lease_liabilities", year)
            if nc_l is not None or c_l is not None:
                fin = borrowings + abs(nc_l or 0.0) + abs(c_l or 0.0)
                data.values.setdefault("financial_debt_incl_leases", {})[year] = fin
                data.derived[("financial_debt_incl_leases", year)] = (
                    "قروض وتسهيلات + التزامات التأجير التمويلي (طويلة وقصيرة الأجل)")
                data.candidates.setdefault("financial_debt_incl_leases", {})[year] = [(fin, 0)]
                if ("borrowings_excl_leases", year) in (getattr(data, "derived_uncertain", set()) or set()):
                    data.derived_uncertain.add(("financial_debt_incl_leases", year))
                # IFRS 16 / EAS 49: total financial debt includes lease liabilities
                # (matches calculator.py:217-227 and Note 32-2). Overwrite only if
                # total_debt is missing or was previously derived (never clobber a direct capture).
                td_map = data.values.setdefault("total_debt", {})
                if year not in td_map or ("total_debt", year) in data.derived:
                    td_map[year] = fin
                    data.derived[("total_debt", year)] = "borrowings + lease liabilities"
            else:
                td_map = data.values.setdefault("total_debt", {})
                if year not in td_map or ("total_debt", year) in data.derived:
                    td_map[year] = borrowings
                    data.derived[("total_debt", year)] = "borrowings excluding leases"

    # ص6 printed bridge (الجسر المطبوع في قائمة الدخل): pretax =
    # net activity profit − net financing costs + dividends from
    # subsidiaries. Printed identity: 1,257,960,603 − 771,597,390 +
    # 750,000,000 = 1,236,363,213. Derived ONLY when pretax was not
    # captured, always declared — a derived value never replaces a direct
    # capture (the 2026-10-31 NI lesson).
    for year in list(data.years):
        if data.get("pretax_income", year) is not None:
            continue
        activity = data.get("net_activity_profit", year)
        financing = data.get("interest_expense", year)
        dividends = data.get("dividends_from_subsidiaries", year)
        if None not in (activity, financing, dividends):
            pretax = activity - abs(financing) + dividends
            data.values.setdefault("pretax_income", {})[year] = pretax
            # input certainty travels with the derivation: an uncertain input
            # produces an UNCERTAIN derived value — never a confident one
            conf = data.confidence
            uncertain = [name for name, val in (
                ("صافي أرباح النشاط", ("net_activity_profit",)),
                ("صافي التكاليف التمويلية", ("interest_expense",)),
                ("توزيعات أرباح من شركات تابعة", ("dividends_from_subsidiaries",)),
            ) if conf.get(val[0], {}).get(year, 0) < 2]
            note = ("صافي أرباح النشاط − صافي التكاليف التمويلية "
                    "+ توزيعات أرباح من شركات تابعة")
            if uncertain:
                note += (f" — مدخلات غير مؤكدة: {', '.join(uncertain)} "
                         "(قراءات مفردة)")
                data.derived_uncertain = getattr(data, "derived_uncertain", set())
                data.derived_uncertain.add(("pretax_income", year))
            data.derived[("pretax_income", year)] = note
            data.candidates.setdefault("pretax_income", {}).setdefault(
                year, []).append((pretax, 0))


# ── Verification Decision Log (سجل قرارات التحقق) ────────────────────────────
# One record per captured field/year: every competing read, the accounting and
# source checks, the final value, and an HONEST status. Derived or contested
# values are never presented as VERIFIED_EXACT.

DECISION_STATUSES = (
    "VERIFIED_EXACT",     # ≥2 independent agreeing reads or verified re-read
    "VERIFIED_DERIVED",   # derived from a verified identity — flagged
    "CONFLICT",           # competing reads without resolution or verification
    "UNVERIFIED",         # single capture, no independent confirmation
    "MISSING",            # nothing captured
    "NOT_APPLICABLE",     # field not present in this document
)


def _value_source(data: FinancialData, field_name: str, year) -> str:
    """WHERE the value came from — metadata, never a verification claim."""
    from src.extraction.provenance import (
        SOURCE_DERIVED, SOURCE_HUMAN_REVIEWED,
    )

    hr = (getattr(data, "human_reviews", {}) or {}).get((field_name, year))
    if hr and hr.get("status") == "VERIFIED_HUMAN":
        return SOURCE_HUMAN_REVIEWED
    ev = (getattr(data, "cell_provenance", {}) or {}).get((field_name, year))
    if ev:
        return ev.get("source") or getattr(data, "extraction_source",
                                           "SCANNED_OCR")
    if derived_note := (getattr(data, "derived", {}) or {}).get(
            (field_name, year)):
        return SOURCE_DERIVED
    return getattr(data, "extraction_source", "SCANNED_OCR")


def _source_exact(data: FinancialData, field_name: str,
                  year) -> tuple[bool, dict | None, list[str]]:
    """VERIFIED_SOURCE_EXACT eligibility for a digital-source capture:
    the stored evidence must pass the full checklist AND the label must
    still map to the SAME canonical field it was captured under (a correct
    number on the wrong row must never be promoted)."""
    from src.extraction.provenance import (
        DIGITAL_SOURCES, CellEvidence, evaluate_source_evidence,
    )

    ev_d = (getattr(data, "cell_provenance", {}) or {}).get(
        (field_name, year))
    if not ev_d:
        return False, None, ["لا يوجد إسناد مصدري لهذه القيمة"]
    ev = CellEvidence.from_dict(ev_d)
    if ev.source not in DIGITAL_SOURCES:
        return False, ev, ["المصدر ليس خلية/نصًا رقميًا مباشرًا"]
    # the label the evidence saw must map to the field the capture used
    if ev.label_text and match_field(ev.label_text) != field_name:
        return False, ev, [
            f"البند «{ev.label_text}» لا يقابل الحقل '{field_name}' — "
            "رقم صحيح على الصف الخطأ لا يُعتمد"]
    ok, failures = evaluate_source_evidence(ev, expected_year=year)
    return ok, ev, failures


def build_decision_log(data: FinancialData) -> list[dict]:
    """One honest record per captured field/year. Status precedence:
    MISSING → VERIFIED_DERIVED (flagged) → CONFLICT (competing reads without
    enough verification) → VERIFIED_EXACT (≥2 agreeing reads or verified
    re-read) → UNVERIFIED (single unconfirmed capture)."""
    fs = getattr(data, "field_sources", {}) or {}
    derived = getattr(data, "derived", {}) or {}
    votes = getattr(data, "vote_outcomes", {}) or {}
    log = []
    for field_name, by_year in sorted(data.candidates.items()):
        for year in sorted(by_year, key=str):
            cands = [c for c in by_year[year] if c[0] is not None]
            if not cands:
                continue
            values = [v for v, _ in cands]
            final = data.values.get(field_name, {}).get(year)
            pages = sorted(set(fs.get(field_name, [])))
            conf = data.confidence.get(field_name, {}).get(year, 0)
            distinct = []
            for v in values:
                if not any(_digit_close(v, d) for d in distinct):
                    distinct.append(v)
            derived_note = derived.get((field_name, year))
            vote = votes.get((field_name, year))
            identity_ok = data.identity_ok.get((field_name, year), False)
            if final is None:
                status, reason = "MISSING", "لا قيمة معتمدة لهذا الحقل/السنة"
            elif derived_note:
                if (field_name, year) in (getattr(data, "derived_uncertain", set()) or set()):
                    status = "UNVERIFIED"
                    reason = (f"مشتق من مدخلات غير مؤكدة — لا يُصدَّر كمؤكد: "
                              f"{derived_note}")
                else:
                    status, reason = ("VERIFIED_DERIVED",
                                      f"مشتق: {derived_note} — موسوم ولا يُعد قراءة مباشرة")
            elif len(distinct) == 1 and (field_name, year) in (
                    getattr(data, "cell_provenance", {}) or {}):
                # Source-aware gate (البوابة الواعية بالمصدر): a DIGITAL cell
                # whose FULL evidence checklist passes is a documented
                # faithful TRANSFER of the printed value — decisive, with
                # the evidence cited. Never granted for wrong-field labels,
                # year mismatches, merged cells, scaled units, flipped
                # signs, or non-amount types. Values WITHOUT cell-level
                # provenance (OCR paths) keep the original ladder — this
                # branch never tightens or loosens them.
                src_ok, src_ev, src_fails = _source_exact(
                    data, field_name, year)
                if src_ok:
                    from src.extraction.provenance import evidence_reason

                    status = "VERIFIED_SOURCE_EXACT"
                    reason = evidence_reason(src_ev)
                else:
                    status, reason = ("UNVERIFIED",
                                      "قراءة واحدة بلا تحقق مستقل"
                                      + (f" — {src_fails[0]}"
                                         if src_fails and src_fails != [
                                             "لا يوجد إسناد مصدري لهذه القيمة"]
                                         else ""))
            elif len(distinct) >= 2 and conf < 2:
                status = "CONFLICT"
                reason = (f"قراءات متضاربة غير محسومة ({len(distinct)} قيمًا مختلفة) "
                          "والتحقق المستقل لم يحسم — القيمة المعتمدة أول الالتقاط")
            elif conf >= 2:
                if vote and vote.get("contested"):
                    status = "VERIFIED_EXACT"
                    reason = (f"اتفاق {vote['votes']} قراءات مستقلة بعد تصويت 2-ضد-1 "
                              f"(قراءة معارضة محفوظة: {vote['replaced']:,.0f})")
                else:
                    status = "VERIFIED_EXACT"
                    reason = f"اتفاق {conf} قراءات/تحقق مستقل"
                # Correlated-source guard (حارس اتفاق المصدر الواحد): when the
                # document profiler classified the text layer UNTRUSTED and
                # every agreeing witness came from THAT layer, agreement is
                # an echo of one corrupted source — never an attestation.
                if not (getattr(data, "document_profile", {}) or {}).get(
                        "text_layer_trusted", True):
                    # attestation needs TWO DISTINCT layers behind the
                    # WINNING value (text + vision, vision + local_ocr…) —
                    # agreement inside ONE layer is that layer's echo,
                    # whatever the layer is. The layers are read from the
                    # vote outcome (the raw candidates pre-collapse).
                    vote = votes.get((field_name, year))
                    winner_layers = (vote or {}).get("winner_layers")
                    if winner_layers is None:
                        # no vote outcome recorded — derive from the raw
                        # candidates that digit-match the FINAL value only
                        layers_all = ((getattr(data, "candidate_layers", {})
                                       or {}).get(field_name, {})
                                      .get(year) or [])
                        winner_layers = sorted({
                            l for (v, _o), l in zip(cands, layers_all)
                            if v is not None and _digit_close(v, final)})
                    if len(set(winner_layers)) < 2:
                        status = "UNVERIFIED"
                        reason = ("اتفاق قراءات داخل طبقة واحدة "
                                  f"({sorted(set(winner_layers)) or ['غير معروفة']}) "
                                  "على مستند مصنَّف غير موثوق — الاتفاق صدى "
                                  "لمصدر واحد وليس تصديقًا مستقلًا")
                    elif "z3_math" in winner_layers and not (vote and vote.get("contested")):
                        reason = "تطابق القراءة البصرية مع الإثبات الجبري المحاسبي (Z3 SMT)"
                    elif "vision_cross_model" in winner_layers and not (vote and vote.get("contested")):
                        reason = "تطابق قراءة نموذجين مستقلين للرؤية (Cross-Model Consensus)"
            elif len(values) >= 2 and conf >= 1:
                status, reason = "UNVERIFIED", "قراءتان بلا تحقق مستقل حاسم"
            else:
                status, reason = "UNVERIFIED", "قراءة واحدة بلا تحقق مستقل"
            # Spatial gate (بوابة الإسناد المكاني): when the spatial layer
            # ran and could not confirm the year column for this field/year,
            # a direct capture is downgraded — an unconfirmed column is never
            # VERIFIED_EXACT and never feeds the ratio engine as documented.
            spatial = (getattr(data, "spatial_findings", {}) or {}).get(
                (field_name, year))
            # Human-in-the-loop: an explicit reviewer attestation is an
            # independent verified re-read — status VERIFIED_HUMAN with the
            # reviewer/time cited; the change (if any) was applied to
            # data.values by human_review.apply_review and is kept in the log.
            hr = (getattr(data, "human_reviews", {}) or {}).get(
                (field_name, year))
            if hr and hr.get("status") == "VERIFIED_HUMAN"                     and hr.get("value_final") is not None:
                from pathlib import Path as _Path
                from src.extraction.human_review import (
                    REVIEW_LOG, review_is_trusted)

                if review_is_trusted(
                        hr, log_path=_Path(getattr(
                            data, "human_reviews_log", REVIEW_LOG))):
                    status = "VERIFIED_HUMAN"
                    reason = (
                        f"إقرار بشري موثق — المراجع {hr.get('reviewer')} في "
                        f"{hr.get('timestamp')}; القيمة الآلية قبل الاعتماد: "
                        f"{hr.get('value_before')} (سجل التغيير المتسلسل في "
                        "cell_evidence/human_reviews.json)")
                else:
                    # forged/stale/voided attestation — never decisive
                    status = "UNVERIFIED"
                    reason = ("إقرار بشري غير موثوق (سجل مفقود أو مُعدَّل أو "
                              "مصدر متغير) — لا يُعتمد")
            if spatial and status == "VERIFIED_EXACT" \
                    and spatial.get("year_assignment") != "confirmed":
                status = "UNVERIFIED"
                reason = (
                    "بوابة الإسناد المكاني: عمود السنة غير مؤكد هندسيًا "
                    f"({spatial.get('detail', 'لا تحديد')}) — لا تُعتمد "
                    "القراءة VERIFIED_EXACT ولا تمر للمحرك كموثقة")
            # Sign-conflict guard (المهمة 2 — يمنع الاعتماد عند تعارض
            # الإشارة بين المصدرين): two candidates with the SAME magnitude
            # and OPPOSITE signs mean one reader saw the printed
            # parentheses and the other lost them — the cell can never be
            # VERIFIED_EXACT/DERIVED on that agreement. Human review can
            # still resolve it (the override below runs after this).
            sign_conflict = False
            for _i, _v1 in enumerate(values):
                for _v2 in values[_i + 1:]:
                    if _v1 and _v2 and _v1 * _v2 < 0 and                             abs(abs(_v1) - abs(_v2)) <=                             max(1.0, 1e-6 * max(abs(_v1), abs(_v2))):
                        sign_conflict = True
                        break
                if sign_conflict:
                    break
            if sign_conflict and (status in ("VERIFIED_EXACT",
                                             "VERIFIED_DERIVED",
                                             "VERIFIED_SOURCE_EXACT")
                                  or status == "CONFLICT"):
                status = "CONFLICT"
                reason = ("تعارض الإشارة بين المصدرين (قوسان مطبوعان مقابل "
                          "مقدار) — القيمة محجوبة حتى تحسمها المراجعة "
                          "البشرية")
            log.append({
                "field": field_name,
                "year": year,
                "pages": pages,
                "candidates": (
                    [f"{v:,.0f}" for v in values]
                    + ([f"{d:,.0f} (مرفوضة بالتصويت)" for d in vote.get("dissent", [])]
                       if vote else [])
                    + [f"{rv:,.0f} (مستبدلة بالهوية المحاسبية)"
                       for rv in (getattr(data, "replaced_values", {}) or {}).get(
                           (field_name, year), [])]
                ),
                "final": final,
                "distinct_reads": len(distinct),
                "confidence": conf,
                "identity_ok": identity_ok,
                "source": _value_source(data, field_name, year),
                "winner_layers": ((vote or {}).get("winner_layers")
                                  if vote else None),
                "status": status,
                "reason": reason,
                **({"spatial": spatial} if spatial else {}),
            })
    log = _identity_anchor_upgrade(log, data)
    return log


def recovered_log_entry(field_name: str, year: int, value: float, page: int,
                        identity_ok: bool = False) -> dict:
    """مُدخل سجل لقيمة مستردة لاحقًا من نص الإيضاحات (استرجاع pipeline
    اللاحق). قراءة واحدة بلا تحقق مستقل → UNVERIFIED دائمًا — لا تُرقّى
    بالهوية ولا بالتصويت: الاسترجاع طبقة واحدة والترقية تحتاج طبقتين.
    يُستخدم فوق السجل المخزون (الكاش لا يحفظ المرشحين فإعادة البناء منه
    كانت ستفقد مدخل القيمة المستردة)."""
    return {
        "field": field_name,
        "year": year,
        "pages": [page],
        "candidates": [f"{value:,.0f} (استرجاع من الإيضاح)"],
        "final": value,
        "distinct_reads": 1,
        "confidence": 1,
        "identity_ok": identity_ok,
        "source": "SCANNED_OCR",
        "winner_layers": None,
        "status": "UNVERIFIED",
        "reason": ("استرجاع لاحق من نص الإيضاح — قراءة واحدة بلا تحقق "
                   "مستقل، تحتاج مراجعة بشرية"),
    }


def _identity_anchor_upgrade(log: list[dict], data) -> list[dict]:
    """إصلاح حديد عز (إصلاح 4): إذا ثبتت الهوية المحاسبية الكبرى للميزانية
    (الأصول = الالتزامات + الملكية ضمن سماحية ضيقة) فأرقام القوائم
    الأساسية الموثقة تطابق الواقع — تعارض جدول إيضاح فرعي مشوه (صفحة 13
    للأصول الثابتة) لا يبرر حجبها. الترقية معلنة (use_disclosed) ومحدودة
    بحقول القوائم الأساسية ذات التطابق المثبت — لا تمس المحجوبة لأسباب
    أخرى (تعارض إشارة، غياب، طبقة واحدة بلا تصديق)."""
    PRIMARY_FIELDS = {
        "total_assets", "current_assets", "cash", "inventory",
        "accounts_receivable", "fixed_assets", "total_liabilities",
        "current_liabilities", "equity", "revenue", "cost_of_revenue",
        "gross_profit", "operating_income", "pretax_income",
        "income_tax_expense", "net_income", "operating_cash_flow",
        "investing_cash_flow", "financing_cash_flow",
        "long_term_debt", "current_portion_lt_debt",
        "short_term_credit_facilities", "bank_overdraft",
        "current_lease_liabilities", "non_current_lease_liabilities",
        "accounts_payable",
    }
    assets = (data.values.get("total_assets") or {})
    liabs = (data.values.get("total_liabilities") or {})
    equity_v = (data.values.get("equity") or {})
    identity_years: set = set()
    for y, a in assets.items():
        l = liabs.get(y)
        e = equity_v.get(y)
        if a and l and e:
            if abs(a - (l + e)) <= max(1.0, 1e-6 * max(abs(a), abs(l + e))):
                identity_years.add(y)
    if not identity_years:
        return log
    changed = 0
    for e in log:
        if e["field"] not in PRIMARY_FIELDS or e["final"] is None:
            continue
        if e.get("year") not in identity_years:
            continue
        if e["status"] in ("CONFLICT", "MULTI_ROW", "UNVERIFIED") and                 decide(e["status"]) == "not_decisive":
            reason_l = (e.get("reason") or "")
            # الحجب سببه تعارض قراءات/تكرار فقط (وليس قراءة مفردة أو صدى طبقة واحدة أو تعارض إشارة)
            if ("تعارض الإشارة" not in reason_l
                    and "طبقة واحدة" not in reason_l
                    and "قراءة واحدة" not in reason_l
                    and e.get("identity_ok") is not False
                    and ("majority" in reason_l or "تعارض قراءات" in reason_l
                         or "قراءات متضاربة" in reason_l
                         or "2-of-3" in reason_l or "أغلبية" in reason_l)):
                e["status"] = "CONFLICT_UPGRADED_IDENTITY"
                e["identity_anchored"] = True
                e["reason"] = (reason_l + " | " if reason_l else "") +                     ("اعتماد بالإفصاح: الهوية المحاسبية الكبرى مثبتة "
                     "(الأصول = الالتزامات + الملكية) وتعارض جدول إيضاح "
                     "فرعي مشوه لا يبرر الحجب.")
                changed += 1
    return log
