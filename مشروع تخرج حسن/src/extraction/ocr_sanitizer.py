# -*- coding: utf-8 -*-
"""معالج تشوهات أرقام OCR + الترابط الحسابي العكسي (إصلاح 2 — حديد عز).

ثلاثة عيوب موثقة من التدقيق الجنائي على «القوائم المالية المستقلة 2021»:
1. تحول الصفر الهندي (٠) إلى نقطة (.) — «٣٩١,٦٣٣,٥.٥» والصحيح 391,633,505
   (الربح قبل الضريبة).
2. حرف (د) كأثر OCR مسبق للرقم — «د٣٩١,٦٣٣,٥٠».
3. تكرار رقم في الآحاد — «٩٠٦,٦٤٩,٦٧٧۷» (المخزون) أسقط اعتماد إجمالي
   الأصول المتداولة (2,901,399,092 ج.م).

الدوال هنا تُنتج مرشحات (Candidates) ولا تختلق رقمًا واحدًا — الاختيار
النهائي يتم عبر الترابط الحسابي العكسي (reverse_identity_reconcile) الذي
يختار المرشح الذي يُثبت التطابق المحاسبي، أو عبر ربط الإيضاحات
(notes_value_lookup) حين يكون النص الأصلي مشوهًا والإيضاح واضحًا.
"""
from __future__ import annotations

import re
from itertools import product

# الأرقام الهندية → ASCII (يشمل الرقم الفارسي ۴-۶ اختلاف النسخ)
_ARABIC_DIGITS = str.maketrans({
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
    "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
    "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
    "٫": ".",          # الفاصلة العشرية العربية
    "٬": ",",          # فاصل الآلاف العربي
})


def _to_ascii_digits(raw: str) -> str:
    """تحويل الأرقام الهندية/الفارسية وفواصلها إلى ASCII."""
    return str(raw).translate(_ARABIC_DIGITS)


def _parse_ascii_number(text: str) -> float | None:
    """تحليل نص رقمي ASCII: يزيل الفواصل الآلاف والفراغات."""
    cleaned = re.sub(r"[,\s]", "", text)
    if not cleaned or not re.fullmatch(r"-?\d+(?:\.\d+)?", cleaned):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def ocr_digit_sanitizer(raw: str) -> list[float]:
    """مرشحات رقمية لقيمة مشوهة بـ OCR — لا تختلق أرقامًا من فراغ.

    الاستراتيجية (بترتيب الثقة):
    1. التحليل المباشر بعد توحيد الأرقام الهندية وإزالة (د) وأثر OCR.
    2. النقطة داخل مجموعة أرقام = صفر هندي (٠) مشوه → استبدالها بـ0
       (حديد عز: ٣٩١,٦٣٣,٥.٥ → 391,633,505 ✓).
    3. إسقاط النقطة مع بقاء الأرقام (إن كانت فاصلًا مشوهًا).
    4. إزالة الأرقام المكررة المتتالية داخل المجموعة الأخيرة (٧٧ → ٧).
    5. حالة الأرقام المبتورة: لو كانت المجموعات تشير لتكرار آحاد مفقود،
       مُرشّح بإلحاق ٠ للمجموعة الأخيرة (منخفض الثقة — الترابط العكسي
       هو من يقرر اعتماده).
    """
    text = _to_ascii_digits(str(raw))
    text = re.sub(r"[ددD]", " ", text)          # أثر OCR الموثق (حرف د)
    text = text.strip()
    candidates: list[float] = []
    seen: set[float] = set()

    def _add(v: float | None) -> None:
        if v is not None and v not in seen and v != 0:
            seen.add(v)
            candidates.append(v)

    base = _parse_ascii_number(text)
    _add(base)

    # النقطة داخل الأرقام = صفر هندي مشوه (المرشح الأعلى ثقة بعد المباشر)
    if "." in text and re.search(r"\d\.\d", text):
        _add(_parse_ascii_number(text.replace(".", "0")))
        _add(_parse_ascii_number(text.replace(".", "")))

    # إزالة تكرار رقم متتالٍ في نهاية المجموعة الأخيرة (٧٧۷ → ٧)
    last_group = re.search(r"(\d)(\1)\b(?!\d)", text[::-1][::-1])
    m = re.search(r"(\d)\1(?!\d)", text)
    if m:
        dedup = text[:m.start()] + m.group(1) + text[m.end():]
        _add(_parse_ascii_number(dedup))

    # مبتورة المجموعة الأخيرة (أرقام مفقودة من النهاية) — مرشح بإلحاق ٠
    # و٠٠ (منخفض الثقة — لا يُعتمد إلا بالترابط العكسي أو ربط الإيضاح)
    groups = re.findall(r"\d+", text)
    if groups and len(groups[-1]) <= 2 and len(groups) >= 2:
        head = "".join(groups[:-1])
        _add(_parse_ascii_number(head + groups[-1] + "0"))
        _add(_parse_ascii_number(head + groups[-1] + "00"))

    return candidates


def reverse_identity_reconcile(
    raw_components: list[str],
    expected_total: float,
    tolerance: float = 1.0,
) -> dict | None:
    """الترابط الحسابي العكسي: اختر مرشحات الإصلاح التي تجمع المكونات
    إلى الإجمالي المتوقع من مستند آخر (تطابق صريح).

    حديد عز: المخزون «٩٠٦,٦٤٩,٦٧٧۷» (مكرر الآحاد) أسقط اعتماد إجمالي
    الأصول المتداولة 2,901,399,092 — الترابط يستعيد 906,649,677 فيثبت
    الإجمالي ويُعتمد.

    Returns: {"values": [...], "indices": [...]} أو None عند الفشل.
    """
    if not raw_components:
        return None
    variants_per_component = []
    for raw in raw_components:
        base = _parse_ascii_number(_to_ascii_digits(str(raw)))
        direct = None if base is None else [base]
        variants = ocr_digit_sanitizer(str(raw))
        variants_per_component.append(
            ([direct[0]] if direct is not None else [], variants))

    # المسار المباشر أولًا: القيم كما قُرئت
    direct_values = [direct[0] if direct else None
                     for direct, _v in variants_per_component]
    if None not in direct_values and \
            abs(sum(direct_values) - expected_total) <= tolerance:
        return {"values": direct_values,
                "indices": list(range(len(direct_values))),
                "repaired": False}

    # المسار المُصلَح: منتج المرشحات (محدود — 4 مكونات × مرشحات قليلة)
    pool = [[d] if d is not None else [] for d, _v in variants_per_component]
    pool = [list(dict.fromkeys(d + v)) for d, v in variants_per_component]
    if any(not p for p in pool) or len(pool) > 5:
        return None
    for combo in product(*pool):
        if abs(sum(combo) - expected_total) <= tolerance:
            return {"values": list(combo),
                    "indices": list(range(len(combo))),
                    "repaired": True}
    return None


_LABEL_PATTERNS: dict[str, list[str]] = {
    # إصلاح حديد عز (إصلاح 2 — ربط القوائم بالإيضاحات): «مصروفات إدارية
    # وعمومية» ظهرت مشوهة بصفحة الدخل (دد ٢٩٩,٦٤٨,٥) بينما واضحة تمامًا في
    # الإيضاح (7) بقيمة 299,648,555 ج.م — البحث في نص الإيضاحات بنمط البند
    "administrative_expenses": [
        r"مصروفات?\s+إداري\w*\s+و?\s*عمومي\w*",
        r"المصروفات?\s+الإداري\w*\s+والعمومي\w*",
        r"administrative (?:and general |& general )?expenses",
    ],
    # البنود الأربعة المفقودة في حديد عز 2021 (لم يلتقطها الاستخراج البصري
    # وأسقطت مؤشراتها N/A). الأنماط تشترط «قصير/القصر» لبنود الدين قصير
    # الأجل حتى لا تلتقط التسهيلات طويلة الأجل في إيضاح القروض نفسه.
    "short_term_credit_facilities": [
        r"تسهيلات?\s+ائتماني\w*\s+قصير\w*",
        r"قروض?\s+قصير\w*\s+الأجل",
        r"اقتراضات?\s+قصير\w*\s+الأجل",
        r"short[- ]term (?:credit facilities|borrowings|loans)",
    ],
    "bank_overdraft": [
        r"سحب?\s+بنك\w*",
        r"السحب\s+على\s+البنوك",
        r"أرصدة\s+سحب?\s+بنك\w*",
        r"bank overdrafts?",
    ],
    "operating_income": [
        r"صافي\s+ربح?\s+النشاط",
        r"صافي\s+أرباح?\s+النشاط",
        r"صافي\s+(?:ربح|أرباح)\s+التشغيل",
        r"الربح\s+التشغيلي",
        r"ربح\s+النشاط",
        r"نتيجة\s+النشاط",
        r"operating (?:profit|income|result)",
    ],
    "pretax_income": [
        r"الربح\s+قبل\s+ضريب\w*",
        r"الربح\s+قبل\s+الضريب\w*",
        r"الربح\s+قبل\s+ضرائب\w*",
        r"الربح\s+قبل\s+الزكاة",
        # صياغة قائمة الدخل/التدفقات: «صافى أرباح / (خسائر) العام
        # قبل ضريبة الدخل» — الربح/أرباح بعيدة عن «قبل» فلا تكفي
        # الأنماط التي تشترط الربح قبل الضريبة مجاورتين
        r"قبل\s+ضريب[ةه]\s+الدخل",
        r"profit before (?:income )?tax(?:es)?",
    ],
    # صافي الربح: يشترط «بعد الضريبة» أو استبعاد «قبل» — حتى لا يلتقط
    # الربح قبل الضريبة ولا «صافي ربح النشاط» (التشغيلي)
    "net_income": [
        r"صافي\s+الربح\s+بعد\s+ضريب\w*",
        r"صافي\s+ربح?\s+العام\s+بعد\s+ضريب\w*",
        r"الربح\s+بعد\s+الضريب\w*",
        r"صافي\s+الربح\s+(?:للعام|المحقق)",
        # صياغة حديد عز: «صافى أرباح (خسائر) العام» — الاستبعدان يمنعان
        # التقاط سطر «… العام قبل ضريبة الدخل» في الصفحة نفسها
        r"صاف[يى]\s+أرباح?\s*/?\s*\(?\s*خسائر?\s*\)?\s+(?:العام|السنة)"
        r"(?!\s*قبل)",
        r"net\s+(?:income|profit)\s+after\s+tax(?:es)?",
        r"profit\s+(?:for\s+the\s+year|after\s+tax(?:es)?)",
    ],
}


# سلسلة أرقام هندية-عربية بفواصلها — القراءة النظيفة في المستندات
# الممسوحة: تشوه OCR يظهر كب transliteration لاتينية (TAA, VII) بينما
# الأرقام الهندية تُقرأ غالبًا كما هي
_AR_INDIC_RUN = re.compile(r"[٠-٩۰-۹][٠-٩۰-۹٬٫,]*")


def notes_value_lookup(
    field: str,
    notes_text: dict[int, str],
    min_value: float = 0.0,
) -> list[dict]:
    """استخراج قيمة بند من نصوص الإيضاحات حسب نمط تسميته — يُستخدم حين
    تكون قراءة صفحة القوائم مشوهة والإيضاح واضحًا.

    ثلاثة تحصينات من تدقيق حديد عز 2021:
    1. تفضيل الأرقام الهندية-العربية: عمود 2021 في صفحة الدخل قرئ
       Latin-garble («TATE, VII, ATA») بينما قائمة التدفقات ص9 تحمل
       «٣٩١,٦٣٣,٥٠٥» نظيفة — الهندية هي القراءة الأمينة.
    2. النافذة تُقطع عند نهاية صف الجدول (</tr>) — لا تلتقط أرقام
       الصفوف التالية، وعند غياب الأرقام في الصف لا يُلتقط شيئ.
    3. أول نمط محدد فقط (الأنماط مرتبة بالتحديد) — النمط العام لا
       يعمل إن كفى النمط المحدد.

    الاختيار بين أعمدتي السنتين: أول رقم بعد التسمية = العمود الأيمن
    (السنة الحالية في جدول RTL) — ليس الأكبر.

    Returns: [{"page": p, "value": v, "candidates": [...], "indic": bool,
               "snippet": ...}] مرتبة: القراءة الهندية أولًا ثم الصفحة.
    """
    patterns = _LABEL_PATTERNS.get(field, [])
    hits: list[dict] = []
    for page in sorted((notes_text or {}).keys(),
                       key=lambda k: int(k) if str(k).isdigit() else 0):
        text = str(notes_text[page] or "")
        if not text:
            continue
        for pat in patterns:
            pat_hits: list[dict] = []
            for m in re.finditer(pat, text, re.IGNORECASE):
                start = m.end()
                row_end = text.find("</tr>", start)
                end = start + 120 if row_end < 0 else min(row_end,
                                                          start + 120)
                window_raw = text[start:end]
                indic = []
                for im in _AR_INDIC_RUN.finditer(window_raw):
                    v = _parse_ascii_number(_to_ascii_digits(im.group(0)))
                    if v is not None and v > min_value:
                        indic.append(v)
                window = _to_ascii_digits(window_raw)
                nums = [float(x.replace(",", ""))
                        for x in re.findall(r"\d[\d,]{3,}(?:\.\d+)?", window)]
                nums = [n for n in nums if n > min_value]
                if indic:
                    pat_hits.append({"page": page, "value": indic[0],
                                     "candidates": list(
                                         dict.fromkeys(indic + nums)),
                                     "indic": True,
                                     "snippet": window_raw[:80]})
                elif nums:
                    pat_hits.append({"page": page, "value": nums[0],
                                     "candidates": nums, "indic": False,
                                     "snippet": window_raw[:80]})
            if pat_hits:
                hits.extend(pat_hits)
                break  # أول نمط محدد كفى — الأعم لا يعمل
    hits.sort(key=lambda h: (not h["indic"], h["page"]))
    return hits
