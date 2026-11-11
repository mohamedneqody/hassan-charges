# -*- coding: utf-8 -*-
"""تعريب ملاحظات المحرك عند العرض (v6): المحرك يبث ملاحظاته بالإنجليزية
(أنماط ثابتة + قيم) — الواجهة تعرضها عربية عبر مطابقة الأنماط مع الاحتفاظ
بالقيم. الملاحظة غير المطابقة تُعرض كما هي (بصدق، لا اختلاق ترجمة).
هذا تعريب عرض فقط: نصوص المحرك نفسها ونصوص الاختبارات المثبتة لا تُمس."""
from __future__ import annotations

import re

# (نمط إنجليزي مترجم بـregex، القالب العربي — {0}{1}… = المجموعات)
_PATTERNS: list[tuple[str, str]] = [
    (r"Scanned PDF detected \(no text layer\) — pages were read with AI vision \(OpenCV cleanup \+ Gemini\), then validated by accounting identities",
     "PDF ممسوح بلا طبقة نصية — قُرئت الصفحات برؤية الذكاء الاصطناعي (تنظيف OpenCV + Gemini) ثم تحقق منها التطابقات المحاسبية."),
    (r"Local OCR triage: (\d+)/(\d+) pages carry table markup — they are read first so the run can stop early",
     "فرز القراءة المحلية: {0}/{1} صفحة تحمل جداول — تُقرأ أولًا لإمكانية التوقف المبكر."),
    (r"Currency detected from the document:?\s*(.*)",
     "العملة مكتشفة من المستند: {0}"),
    (r"Vision extraction stopped early after page (\d+): the core statements were complete \(remaining pages are notes\)",
     "الاستخراج البصري توقف مبكرًا بعد الصفحة {0}: القوائم الأساسية اكتملت (البقية إيضاحات)."),
    (r"Verifying cash-flow totals by focused re-read of page\(s\) \[([^\]]+)\]",
     "التحقق من مجاميع التدفقات بإعادة قراءة مركزة للصفحات [{0}]"),
    (r"Verified by focused CF re-read: (\w+) in (\d+) ([^>]+) -> ([^✓]+) ✓",
     "تحقق بإعادة القراءة المركزة: {0} في {1} من {2} إلى {3} ✓"),
    (r"Checking marginal re-reads from accounting identities on page\(s\) \[([^\]]+)\]",
     "فحص إعادات القراءة الهامشية من التطابقات المحاسبية على الصفحات [{0}]"),
    (r"Disagreement on page (\d+) — resolving with a third read at higher resolution \(2-of-3 majority\)",
     "تعارض في الصفحة {0} — الحسم بقراءة ثالثة بدقة أعلى (أغلبية 2 من 3)"),
    (r"Resolved by 2-of-3 majority: (\w+) in (\d+) ([^>]+) -> ([^✓]+) ✓",
     "حُسم بأغلبية 2 من 3: {0} في {1} من {2} إلى {3} ✓"),
    (r"Notes text captured locally for (\d+) pages \(الإيضاحات صارت قابلة للسؤال في تاب الإيضاحات\)\.?",
     "نصوص الإيضاحات التقطت محليًا لـ{0} صفحة — صارت قابلة للسؤال."),
    (r"Notes text capture skipped \(local OCR unavailable or failed\) — the notes RAG tab needs a re-analysis\.?",
     "التقاط نصوص الإيضاحات تخطى (القراءة المحلية غير متاحة) — تاب الإيضاحات يحتاج إعادة تحليل."),
    (r"Data extracted from PDF tables\.", "استُخرجت البيانات من جداول PDF."),
    (r"Data extracted from PDF text \(no tables detected\)\.",
     "استُخرجت البيانات من نص PDF (لا جداول مكتشفة)."),
    (r"Loaded from the local cache — no API calls were spent\. \(Use «مسح الكاش المحلي» in the sidebar to re-extract fresh\)\.?",
     "حُمّل من الكاش المحلي — صفر نداءات. (استخدم «مسح الكاش المحلي» من الشريط الجانبي لاستخراج جديد.)"),
    (r"Document profile: (\w+) — text quality ([\d.]+) \(magnitude validity ([\d.]+), continuity ([\d.]+)\) → text layer (TRUSTED|NOT trusted)",
     "ملف المستند: {0} — جودة النص {1} (صلاحية المبالغ {2}، اتصال المجموعات {3}) → الطبقة النصية {4}."),
    (r"Vision path BLOCKED: (.+)",
     "مسار الرؤية محجوب: {0}"),
    (r"Vision fallback BLOCKED: ENABLE_VISION_FALLBACK flag is off — continuing with local layers only\.",
     "مسار الرؤية محجوب: العلم ENABLE_VISION_FALLBACK مطفأ — الاستمرار بالطبقات المحلية فقط."),
    (r"Adaptive routing: local spatial re-read of (\d+) worst-text pages → (\d+) extra tables \(layer local_ocr, zero API\)\.",
     "التوجيه التكيفي: إعادة قراءة مكانية محلية لـ{0} أسوأ الصفحات نصيًا → {1} جدولًا إضافيًا (طبقة محلية، صفر API)."),
    (r"Skipped an unparseable table: (.+)",
     "تخطي جدول غير قابل للتحليل: {0}"),
    (r"⚠ Accounting identity check FAILED for (\w+) in (\d+): captured ([\d,\.]+) but total_liabilities \+ equity = ([\d,\.]+)\. The captured value was kept — verify the source page \(possible extraction/OCR error\)\.",
     "⚠ فشل التطابق المحاسبي لـ{0} في {1}: الملتقط {2} لكن الالتزامات + حقوق الملكية = {3}. القيمة أُبقيت — تحقق من الصفحة الأصلية."),
    (r"⚠ Sanity check: (.+)",
     "⚠ فحص عقلي: {0}"),
    (r"Human review: (\d+) printed values attested via the review chain\.?",
     "مراجعة بشرية: {0} قيمة مطبوعة موثقة عبر سلسلة المراجعة."),
    (r"Vision batch (\d+)-(\d+) failed: (.+)",
     "فشلت دفعة الرؤية {0}-{1}: {2}"),
    (r"Stopping the vision sweep: all API key/model pairs are now exhausted or unavailable\.",
     "إيقاف المسح البصري: كل أزواج المفاتيح/النماذج مستنفدة أو غير متاحة."),
    (r"Vision extraction stopped early after page (\d+): the core statements were complete \(remaining pages are notes\)\.",
     "الاستخراج البصري توقف مبكرًا بعد الصفحة {0}: القوائم الأساسية اكتملت (البقية إيضاحات)."),
    (r"Using cached vision results for pages ([\d,\s]+)",
     "استخدام نتائج الرؤية المخزنة للصفحات {0}"),
]


def note_ar(note: str) -> str:
    """ملاحظة عربية إن طابق النص نمطًا معروفًا؛ وإلا فالأصل كما هو."""
    text = str(note).strip()
    for pattern, template in _PATTERNS:
        m = re.match(pattern + r"\s*$", text, re.IGNORECASE | re.DOTALL)
        if m:
            groups = [g.strip() for g in m.groups()]
            try:
                return template.format(*groups)
            except (IndexError, ValueError):
                return text
    return text
