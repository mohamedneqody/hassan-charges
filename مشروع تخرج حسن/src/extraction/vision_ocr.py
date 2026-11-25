"""Scanned-PDF extraction: render pages → OpenCV cleanup → Gemini vision OCR.

Routed automatically when a PDF has no text layer. Gemini reads the cleaned
page images and returns rows JSON; the rows land in the SAME parse_table/
normalizer pipeline as native text, so accounting-identity reconciliation
reconcile() then cleans any OCR misreads (assets = liabilities + equity, ...).
"""
from __future__ import annotations

import io
import json

import pandas as pd

from src.ai.key_pool import APIKeyPool
from src.config import LOCAL_OCR_ENABLED
from src.exceptions import ExtractionError
from src.extraction.normalizer import (
    FinancialData,
    extract_year,
    merge_parsed,
    parse_number,
    parse_table,
    reconcile,
)

VISION_BATCH_SIZE = 4       # pages per Gemini call — fewer calls fit the free
                            # tier (20 req/day/model/key) and halve wall time
VISION_TOTAL_BUDGET = 720   # seconds — hard cap on the whole vision sweep
# التسريع (طلب 2026-11-13: ~20 دقيقة → ~8): السقوف المرحلية التي تجعل
# الرحلة النموذجية تلتزم ~8 دقائق بدل استهلاك السقف الكلي.
# 1) إعادة قراءة الصفحات الفاشلة: كانت تسلسلية (10 صفحات × 45 ثانية =
#    ~7.5 دقيقة خارج كل سقف!) — صارت متوازية وبسقف خاص.
VISION_RETRY_BUDGET = 180   # seconds — cap on the whole retry pass
# 2) مراحل التحقق الثلاث (CF recovery + CF verify + core verify) تتقاسم
#    ميزانية واحدة — كل مرحلة كانت يمكن أن تمشي حتى سقف المسح الكامل.
VISION_VERIFY_BUDGET = 240  # seconds — shared cap for the verify stages
# Version tag for the extraction prompts + pipeline (logged in every result
# and in the Verification Decision Log — reproducibility requirement).
def _semantic_enabled() -> bool:
    """بوابة الاستخراج الدلالي v3 (VISION_SEMANTIC=1): الموديل يصنف كل
    صف من المفردات المغلقة والـregex يعمل مُصححًا متقاطعًا — A/B مقابل
    العقد الحرفي v2 حتى يُحسم بالقياس الحي."""
    import os
    return os.environ.get("VISION_SEMANTIC", "0") == "1"


VISION_PROMPT_VERSION = ("sweep-v3(semantic-roles)" if _semantic_enabled() else "sweep-v2/verify-v4(10-fields+dual-variant)/cf-v3(dual-variant)")   # cell-crop claim dropped 2026-11-13: the stage never ran (undefined helpers swallowed by except) — honest versioning
VISION_CALL_TIMEOUT = 45_000  # ms — a hanging request must not eat the budget
VISION_WORKERS = 5          # concurrent batches — 14 key/model pairs absorb this
VISION_MAX_PAGES = 40       # hard cap so a huge scan cannot drain the pool
VISION_RENDER_SCALE = 2.0   # ~144 DPI renders
VISION_MAX_SIDE = 1600      # px — enough for digits, keeps tokens lean
JPEG_QUALITY = 82


def is_scanned_pdf(file_name: str, raw: bytes) -> bool:
    """True when a PDF carries (almost) no text layer — i.e. it is a scan."""
    if not file_name.lower().endswith(".pdf"):
        return False
    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            chars = 0
            for page in pdf.pages[:10]:
                chars += len(page.extract_text() or "")
                if chars > 50:
                    return False
            return chars <= 50
    except Exception:
        return False


def _render_pages(raw: bytes, max_pages: int, notes: list[str], indices: list[int] | None = None) -> list[bytes]:
    """Render selected PDF pages (1-based `indices`, default: first `max_pages`)."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(io.BytesIO(raw))
    total = len(pdf)
    selected = indices if indices is not None else list(range(1, min(total, max_pages) + 1))
    selected = [p for p in selected if 1 <= p <= min(total, max_pages)]
    if indices is None and total > max_pages:
        notes.append(
            f"Scanned PDF has {total} pages; processing only the first {max_pages}."
        )
    pages = []
    for i in selected:
        pil = pdf[i - 1].render(scale=VISION_RENDER_SCALE).to_pil().convert("RGB")
        buf = io.BytesIO()
        pil.save(buf, format="PNG")
        pages.append(buf.getvalue())
    return pages


def preprocess_image(png: bytes, max_side: int | None = None, binarize: bool = False, denoise: bool = True) -> bytes:
    """OpenCV cleanup for better machine reading: grayscale, cap resolution,
    deskew (small angles only), CLAHE contrast, light denoise, border crop.

    binarize=True adds an adaptive-threshold pass (the second preprocessing
    variant sent alongside the standard one in verification reads — faded
    digits that survive CLAHE often vanish in, or only appear under, the
    adaptive threshold; reading BOTH in one call breaks repeated misreads).
    denoise=False skips medianBlur(3) to preserve 1-2px stroke gaps in small
    Arabic-Indic digits (e.g. ٥ vs ٠, ٢ vs ٧) during Z3 repair reads.
    Any failure returns the original image — never raises."""
    try:
        import cv2
        import numpy as np

        cap = max_side or VISION_MAX_SIDE
        arr = np.frombuffer(png, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return png

        h, w = img.shape[:2]
        scale = min(1.0, cap / max(h, w))
        if scale < 1.0:
            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

        # deskew: measure the dominant text-line angle, correct small skews
        thr = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        coords = cv2.findNonZero(thr)
        if coords is not None:
            angle = cv2.minAreaRect(coords)[-1]
            if angle < -45:
                angle = -(90 + angle)
            if 0.3 < abs(angle) <= 10:
                h2, w2 = img.shape[:2]
                matrix = cv2.getRotationMatrix2D((w2 // 2, h2 // 2), angle, 1.0)
                img = cv2.warpAffine(img, matrix, (w2, h2),
                                     flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

        img = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(img)
        if denoise:
            img = cv2.medianBlur(img, 3)

        # crop empty borders (keep a small margin)
        thr = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        coords = cv2.findNonZero(thr)
        if coords is not None:
            x, y, w2, h2 = cv2.boundingRect(coords)
            pad = 15
            x0, y0 = max(0, x - pad), max(0, y - pad)
            img = img[y0 : min(img.shape[0], y + h2 + pad), x0 : min(img.shape[1], x + w2 + pad)]

        if binarize:
            # second preprocessing variant: adaptive threshold isolates printed
            # digits from scan shading that CLAHE alone cannot flatten
            img = cv2.adaptiveThreshold(
                img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10
            )

        jpeg_q = JPEG_QUALITY if denoise else min(96, max(JPEG_QUALITY, 94))
        ok, jpeg = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_q])
        return jpeg.tobytes() if ok else png
    except Exception:
        return png


VISION_PROMPT = """You are reading scanned pages of ARABIC financial statements (قوائم مالية).
The images are pages {first} to {last} of the document, in this exact order.

For EACH image, extract the financial statement table exactly as printed.
Return ONLY JSON in this shape:
{{"pages": [
  {{"page": {first}, "currency": "<currency mentioned on the page, e.g. جنيه مصري / EGP / ريال — or empty>",
    "company": "<company name as printed in the page header, e.g. شركة عز لصناعة الحديد والصلب — or empty>",
    "years": [2021, 2022],
    "rows": [["<label exactly as printed>", <value for years[0]>, <value for years[1]>], ...]}}
]}}

Rules:
1. "years" = the fiscal years printed in the page header (integers).
2. Values must be plain numbers; a number printed in parentheses is negative.
   A dash ("---", "—", "-") or blank cell means NOT printed — ALWAYS use null, NEVER 0.
3. Keep every label in Arabic exactly as printed — never translate it.
4. Copy numbers character-by-character; never compute or correct them.
5. Distinguish rows carefully: "الربح قبل الضريبة" is PRE-tax income, and
   "صافي الربح" / "صافي أرباح العام" is net income — never merge or swap them.
6. Distinguish "إجمالي الالتزامات" (total liabilities) from "الالتزامات غير
   المتداولة" (non-current liabilities) — they are different rows.
7. If a page has no financial table (cover letter, notes, signature page), return rows = [].
8. "company": fill it ONLY on the first page whose header shows the company
   name (usually the cover or first statement page) — copy it exactly as
   printed; leave it empty on every other page.
"""


def _loads_relaxed(text: str):
    """json.loads with the model-response repairs that repeatedly matter:
    fenced ```json blocks, leading prose, and TRAILING JUNK after the JSON
    object — the "Extra data" failure that once silently dropped a whole
    verification page. Falls back to the first balanced {...} / [...] block
    (string-aware so braces inside labels never end the scan)."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # First balanced {...} / [...] block — try the EARLIEST opener first so a
    # top-level [ ... ] with trailing junk returns the whole list, not its
    # first inner object. String-aware: braces inside labels never end it.
    openers = []
    for opener, closer in (("{", "}"), ("[", "]")):
        idx = text.find(opener)
        if idx >= 0:
            openers.append((idx, opener, closer))
    for _idx, opener, closer in sorted(openers):
        start = text.find(opener)
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
    raise json.JSONDecodeError("no parsable JSON block found", text[:60], 0)


def _parse_vision_json(text: str) -> list[dict]:
    """Coerce the model's JSON into [{years, rows, currency}]."""
    data = _loads_relaxed(text)
    raw_pages = data.get("pages", []) if isinstance(data, dict) else data
    pages = []
    for page in raw_pages if isinstance(raw_pages, list) else []:
        if not isinstance(page, dict):
            continue
        years = [extract_year(y) for y in (page.get("years") or [])]
        years = [y for y in years if y]
        rows = []
        for row in page.get("rows") or []:
            if isinstance(row, dict):
                label = row.get("label") or row.get("item") or row.get("name")
                # الشكل الدلالي v3: الصف يحمل تصنيفه وقيمه كقاموس سنوات —
                # يُحفظ كما هو (الامتصاص الدلالي يحل y1/y2 موضعيًا على
                # years). تحويله لقائمة كان يجعل مفاتيح السنوات قيمًا
                # (2022.0/2023.0) ويكسر الفرع الدلالي كله!
                if "field" in row:
                    rows.append({
                        "label": str(label or "").strip(),
                        "field": row.get("field"),
                        "values": row.get("values") or {},
                        "conf": row.get("conf") or "high",
                    })
                    continue
                values = row.get("values") or []
            elif isinstance(row, list) and row:
                label, values = row[0], row[1:]
            else:
                continue
            if label is None:
                continue
            values = [parse_number(v) for v in values]
            # Scanned PDF dash cells ("---", "—") are occasionally transcribed as 0;
            # on primary/note statement tables a standalone 0 is nil/not applicable -> None.
            values = [None if (v is not None and v == 0.0) else v for v in values]
            if not any(v is not None for v in values):
                continue  # narrative / subtotal-less rows are dropped
            rows.append([str(label).strip()] + values)
        # Keep pages even with unparsable years — doc_years inheritance fills
        # them later (cash-flow pages often show "۲۰۲۲/۱۲/۳۱" style headers).
        pages.append({
            "years": years,
            "rows": rows,
            "currency": str(page.get("currency") or "").strip(),
            "company": str(page.get("company") or "").strip(),
        })
    return pages


def _canonical_field_list() -> str:
    """المفردات المغلقة: كل حقول FIELD_ALIASES — الموديل يصنف منها فقط."""
    from src.config import FIELD_ALIASES
    return ", ".join(sorted(FIELD_ALIASES.keys()))


VISION_PROMPT_V3 = """You are reading scanned pages of ARABIC financial statements (قوائم مالية).
The images are pages {first} to {last} of this document, in this exact order.

SEMANTIC EXTRACTION — classify every financial row into a canonical concept.
Return ONLY JSON:
{{"pages": [
  {{"page": {first}, "currency": "<...>", "company": "<... or empty>",
    "years": [y1, y2],
    "rows": [{{"label": "<exactly as printed>",
               "field": "<one key from the CLOSED LIST below, or null>",
               "values": {{"y1": <number|null>, "y2": <number|null>}},
               "conf": "high"|"low"}}, ...]}}
]}}

CLOSED LIST (field keys — choose ONLY from these):
{fields}

Classification rules (language understanding applies, not memorization):
1. Classify by MEANING, not by words: a row about expected credit losses on
   customers is NOT receivables; an inventory write-down row is NOT inventory;
   customer advance payments are a LIABILITY, not receivables; working capital
   is not share capital; accumulated depreciation is not fixed assets.
2. "الربح قبل الضريبة" → pretax_income; "صافي أرباح/ربح العام" → net_income;
   "مجمل الربح" → gross_profit; "صافي ربح/أرباح النشاط" → operating_income.
3. SUBTOTAL rows (النقدية الناتجة من أنشطة التشغيل without صافي, pre-bridge
   activity profit rows marked يضاف/يخصم) → field = null.
4. Sub-grand rows: "إجمالي الأصول غير المتداولة" → non_current_assets;
   "إجمالي الالتزامات غير المتداولة" → non_current_liabilities;
   "إجمالي المخزون" / "أعمال تحت التنفيذ" / "وحدات تامة بغرض البيع" → inventory
   (but "الانخفاض في قيمة المخزون" or industrial non-current "مشروعات تحت التنفيذ" → null).
   Real-estate developers: "إيرادات النشاط / بيع وحدات" → revenue;
   "تكلفة النشاط / الوحدات المباعة" → cost_of_revenue;
   "موردون ومقاولون" → accounts_payable;
   "نقدية بالصندوق ولدى البنوك" → cash.
5. A row whose concept matches NONE of the list → field = null (do NOT force it).
6. Numbers: copy digit-by-digit; parentheses = negative; unreadable digits →
   null with conf = "low".
7. years = the fiscal years printed in the page header, in order.
"""


def _semantic_prompt(first: int, last: int) -> str:
    body = VISION_PROMPT_V3.format(first=first, last=last,
                                   fields=_canonical_field_list())
    if first == last:
        return body
    # متعدد الصفحات: نفس العقد — الصفوف تحمل رقم الصف ضمن الصف
    nl = chr(10)
    note = (nl + 'NOTE: the images are pages ' + str(first) + '..'
            + str(last) + ' in order — add "page_no": N to each row object.')
    return body + note


def _page_to_frame(page: dict) -> pd.DataFrame | None:
    years = page["years"]
    if len(years) < 2:
        return None  # the whole system compares two years
    rows = [row[: 1 + len(years)] + [None] * (1 + len(years) - len(row)) for row in page["rows"]]
    return pd.DataFrame(rows, columns=["Item"] + years, dtype=object)


_CURRENCY_HINTS = [
    ("جنيه", "ج.م"), ("جنيها", "ج.م"), ("ج.م", "ج.م"), ("egp", "EGP"),
    ("ريال", "ر.س"), ("دولار", "$"), ("درهم", "د.إ"), ("دينار", "د.ك"),
    ("يورو", "€"), ("eur", "€"),
]


def _currency_hint(text: str) -> str | None:
    low = str(text).lower()
    for keyword, symbol in _CURRENCY_HINTS:
        if keyword in low:
            return symbol
    return None


def _enough_core(data: FinancialData) -> bool:
    """Early-stop: core income + balance + OPERATING CASH FLOW present for both
    years. The cash-flow requirement matters — stopping on income+balance alone
    skips a cash-flow statement printed on later pages. Files WITHOUT a
    cash-flow statement are simply scanned in full (correctness > quota)."""
    years = data.years
    if len(years) < 2:
        return False
    y1, y2 = years[0], years[1]
    needed = ("revenue", "net_income", "total_assets", "equity", "operating_cash_flow")
    return all(data.get(f, y) is not None for f in needed for y in (y1, y2))


def _call_vision(key: str, model: str, prompt: str, images: list[bytes]) -> str:
    from google.genai import types
    from src.ai.key_pool import adapt_config_for_model, mark_thinking_budget_unsupported

    client = _get_client(key)
    parts = [prompt] + [
        types.Part.from_bytes(data=img, mime_type="image/jpeg") for img in images
    ]
    base_cfg = _vision_config()
    eff_cfg = adapt_config_for_model(base_cfg, model)
    try:
        response = client.models.generate_content(model=model, contents=parts, config=eff_cfg)
    except Exception as exc:
        msg = str(exc).lower()
        if (
            getattr(eff_cfg, "thinking_config", None) is not None
            and ("400" in msg or "invalid_argument" in msg)
        ):
            mark_thinking_budget_unsupported(model)
            response = client.models.generate_content(
                model=model,
                contents=parts,
                config=adapt_config_for_model(base_cfg, model),
            )
        else:
            raise
    return (response.text or "").strip()


def _get_client(key: str):
    from src.ai.key_pool import get_genai_client

    return get_genai_client(key, timeout_ms=35_000)


def _vision_config():
    from google.genai import types

    return types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.0,  # OCR: zero creativity
        max_output_tokens=8192,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )


def _call_with_rotation(
    pool: APIKeyPool,
    prompt: str,
    images: list[bytes],
    call_stats: list | None = None,
) -> str:
    """Vision call with full key/model rotation (ALL pairs, sub-second failover).

    Fail-fast: when every pair is already marked depleted/dead, raise
    immediately instead of sweeping. With `HttpRetryOptions(attempts=1)`,
    a 429 on one (key, model) returns in ~250ms and switches immediately to
    the next pair across all `len(keys) * len(models)` pairs.
    """
    import time

    from src.ai.gemini_agent import classify_gemini_error
    from src.ai.key_pool import classify_quota_scope

    last_error = "no attempt was made"
    max_attempts = max(pool.total_pairs, 1)
    for wait_cycle in range(2):
        if not pool.has_usable_pairs():
            wait_s = pool.shortest_cooldown_wait() if hasattr(pool, "shortest_cooldown_wait") else None
            if wait_cycle == 0 and wait_s is not None and 0.0 < wait_s <= 25.0:
                time.sleep(min(wait_s + 0.5, 25.0))
            else:
                break
        if not pool.has_usable_pairs():
            break
        for sweep in range(2):
            transient_only = True
            for _ in range(max_attempts):
                picked = pool.pick()
                if picked is None:
                    break
                state, model = picked
                t0 = time.perf_counter()
                try:
                    raw = _call_vision(state.key, model, prompt, images)
                    elapsed = time.perf_counter() - t0
                    if call_stats is not None:
                        call_stats.append((model, elapsed))
                    pool.reset_transient(model)
                    pool.mark_success(state.key)
                    pool.record_call(model, elapsed)
                    return raw
                except Exception as exc:
                    fail_ms = (time.perf_counter() - t0) * 1000.0
                    kind = classify_gemini_error(exc)
                    if kind == "quota":
                        scope, cd_s = classify_quota_scope(exc)
                        if scope == "rpm":
                            pool.mark_rpm_limited(state.key, model, cd_s)
                            last_error = f"RPM rate limit for {model} on {state.masked}"
                        else:
                            pool.mark_quota_exhausted(state.key, model)
                            last_error = f"quota exhausted for {model} on {state.masked}"
                        pool.record_failover(fail_ms)
                        transient_only = False
                    elif kind == "auth":
                        pool.mark_dead(state.key, str(exc)[:200])
                        pool.record_failover(fail_ms)
                        last_error = f"key {state.masked} rejected"
                        transient_only = False
                    elif kind == "model":
                        low_exc = str(exc).lower()
                        global_404 = "no longer available" in low_exc or "models/" in low_exc
                        pool.mark_model_unavailable(
                            state.key, model, str(exc)[:200], all_keys=global_404
                        )
                        pool.record_failover(fail_ms)
                        last_error = f"model {model} unavailable"
                        transient_only = False
                    else:
                        # عابر (503 high demand / 504 timeout): تبريد ناعم سريع
                        pool.mark_transient_failure(model)
                        pool.record_failover(fail_ms)
                        last_error = str(exc)[:250]
            if (
                sweep == 0
                and transient_only
                and pool.has_usable_pairs()
            ):
                time.sleep(1.5)  # brief pause on transient demand spike, then retry
            else:
                break
        if wait_cycle == 0 and not pool.has_usable_pairs():
            wait_s2 = pool.shortest_cooldown_wait() if hasattr(pool, "shortest_cooldown_wait") else None
            if wait_s2 is not None and 0.0 < wait_s2 <= 25.0:
                time.sleep(min(wait_s2 + 0.5, 25.0))
                continue
        break
    if not pool.has_usable_pairs() and last_error == "no attempt was made":
        raise RuntimeError(
            "all API key/model pairs are exhausted or unavailable "
            "(daily free-tier quota resets after midnight US Pacific)."
        )
    # RuntimeError, not ExtractionError: the caller (batch handler) prefixes
    # context, and extract_via_vision aggregates reasons — a nested
    # ExtractionError here would double-wrap the user-facing message.
    raise RuntimeError(f"AI vision extraction failed ({last_error}).")


def _single_prompt(page_number: int) -> str:
    return VISION_PROMPT.format(first=page_number, last=page_number)


VERIFY_PROMPT = """From this scanned ARABIC financial-statement page, read ONLY these totals,
exactly as printed, for EACH year column shown:
- إجمالي الخصوم المتداولة (current liabilities)
- إجمالي الالتزامات (total liabilities)
- إجمالي الأصول (total assets)
- إجمالي حقوق الملكية (total equity)
- المبيعات / الإيرادات / إيرادات النشاط / مبيعات وحدات (revenue)
- صافي أرباح العام / صافي ربح العام (net income)
- صافي أرباح العام قبل ضريبة الدخل (pretax income) — يُطبع أيضًا أول قائمة التدفقات
- المخزون / أعمال تحت التنفيذ / وحدات تامة بغرض البيع — قائمة المركز المالي فقط، لا تقرأ صفوف التغير في التدفقات (inventory)
- الأصول الثابتة (بالصافي) — قائمة المركز المالي فقط (fixed_assets)
- العملاء وأوراق القبض / الذمم المدينة — قائمة المركز المالي فقط، لا تقرأ صفوف التغير في التدفقات (accounts receivable)
- الموردون وأوراق الدفع / موردون ومقاولون / الذمم الدائنة — قائمة المركز المالي فقط، لا تقرأ صفوف التغير في التدفقات (accounts payable)
- النقدية وما في حكمها / نقدية بالصندوق ولدى البنوك — قائمة المركز المالي فقط (cash)
- إهلاك أصول ثابتة — إجمالي الإهلاك في قائمة التدفقات النقدية فقط (depreciation_amortization)
- مدفوعات لشراء أصول ثابتة ومشروعات تحت التنفيذ — في قائمة التدفقات النقدية فقط (capex)

Return ONLY JSON:
{{"years": [2021, 2022],
  "totals": {{"current_liabilities": [v1, v2], "total_liabilities": [v1, v2],
              "total_assets": [v1, v2], "equity": [v1, v2],
              "revenue": [v1, v2], "net_income": [v1, v2],
              "pretax_income": [v1, v2], "gross_profit": [v1, v2],
              "fixed_assets": [v1, v2],
              "inventory": [v1, v2], "accounts_receivable": [v1, v2],
              "accounts_payable": [v1, v2], "cash": [v1, v2],
              "depreciation_amortization": [v1, v2], "capex": [v1, v2]}}}}
Use null for any value not on the page or printed as a dash ("---" / "—", NEVER 0). Parentheses = negative. Copy digits exactly.
If TWO images of the same page are attached (standard cleanup + adaptive-threshold
variant), cross-check between them and read from whichever shows the digits more
clearly — faded or shaded cells often resolve in only one of the two variants.
"""


def _parse_verify_json(text: str) -> dict:
    """{field: {year: value}} from the focused verification response."""
    data = _loads_relaxed(text)
    years = [extract_year(y) for y in (data.get("years") or [])]
    years = [y for y in years if y]
    out: dict[str, dict[int, float]] = {}
    for field, values in (data.get("totals") or {}).items():
        if not isinstance(values, list):
            continue
        by_year: dict[int, float] = {}
        for i, v in enumerate(values):
            if i >= len(years):
                break
            num = parse_number(v)
            if num is not None and num != 0.0:
                by_year[years[i]] = num
        if by_year:
            out[str(field).strip()] = by_year
    return out


def _call_verify_prefer_distinct(
    pool: APIKeyPool,
    prompt: str,
    images: list[bytes],
    sweep_models: list[str] | None = None,
    call_stats: list[tuple[str, float]] | None = None,
) -> tuple[str, str | None]:
    """Call a genuinely DISTINCT Gemini model from `sweep_models` when possible
    so focused 2200px dual-variant verification doubles as independent Cross-Model
    Consensus (cutting duplicate page calls in half with zero accuracy loss).
    Falls back to `_call_with_rotation` when no distinct tier is usable.
    """
    from collections import Counter

    sweep_list = [m for m in (sweep_models or []) if m]
    if sweep_list and pool is not None:
        all_set = set(sweep_list)
        dom = Counter(sweep_list).most_common(1)[0][0]
        excl = all_set if pool.pick_distinct_model(exclude_models=all_set) is not None else {dom}
        if pool.pick_distinct_model(exclude_models=excl) is not None:
            try:
                raw_txt, used_m = _call_distinct_model(
                    pool, prompt, images, exclude_models=excl, call_stats=call_stats,
                )
                return raw_txt, used_m
            except Exception:
                pass
    raw_txt = _call_with_rotation(pool, prompt, images, call_stats=call_stats)
    return raw_txt, None


def _verify_core_fields(
    data: FinancialData,
    parts: list,
    field_sources: dict[str, list[int]],
    pages_png: list[bytes],
    selected: list[int],
    pool: APIKeyPool,
    caller=None,
    notes: list[str] | None = None,
    progress_cb=None,
    local_reads=None,
    deadline: float | None = None,
    confidence: dict | None = None,
    sweep_models: list[str] | None = None,
    call_stats: list[tuple[str, float]] | None = None,
    cross_model_hits: dict[tuple[str, int], tuple[float, str]] | None = None,
) -> None:
    """Focused double-read of the core statement totals (balance sheet + the
    revenue / net-income anchors).

    Vision reads of scanned pages vary run-to-run (the 2021 revenue column
    misread twice in live tests). Re-reading the source page with a focused
    six-number prompt removes most of that variance. When the local OCR layer
    read the same page and its digits already confirm a captured value, that
    value is verified for free.
    Cost: 1-3 extra calls, bounded — pages fully confirmed locally are skipped.

    Disagreements are NOT settled by the focused read alone (a bad focused
    read once replaced a correct capture). One further read at higher
    resolution (3000px) acts as the third vote; 2-of-3 digit-exact majority
    decides. Capped at 2 third-opinion calls per run and skipped when the
    time budget or the key pool is exhausted (then the focused read decides,
    as before).

    `confidence` is a mutable {(field, year): level} accumulator (level =
    independent agreeing reads, 1..3) — the caller applies it to the final
    FinancialData for the audit-trail UI (the `data` argument here is a
    throwaway merge used only for reading current values).
    """
    import time as _time

    notes = notes if notes is not None else []
    conf = confidence if confidence is not None else {}
    core = [
        f for f in (
            "total_assets", "total_liabilities", "current_liabilities", "equity",
            "revenue", "net_income", "pretax_income", "gross_profit",
            # detail balances: a real run shipped inventory/AR from CF change
            # rows because the BS detail rows were never verified — same page,
            # same call, zero extra quota.
            "fixed_assets", "inventory", "accounts_receivable", "accounts_payable", "cash",
        )
        if f in field_sources and any(data.get(f, y) is not None for y in data.years)
    ]
    if not core:
        return
    selected_set = set(selected)
    pages_needed = sorted({p for f in core for p in field_sources.get(f, [])})
    pages_needed = [p for p in pages_needed if p in selected_set]
    if local_reads:
        # batch chunks credit ALL their pages; pages the local read says carry
        # no table cannot hold these totals — don't burn a verify call there.
        pages_needed = [p for p in pages_needed
                        if local_reads.get(p) is None or local_reads[p].has_table]
    pages_needed = pages_needed[:3]
    if not pages_needed:
        return
    # Local second opinion: a page whose every core value is confirmed by the
    # free local OCR read needs no paid verification call at all.
    if local_reads:
        from src.extraction.local_ocr import confirms

        fully_local = []
        for p in pages_needed:
            fields_on_page = [f for f in core if p in field_sources.get(f, [])]
            vals = [(f, y, data.get(f, y)) for f in fields_on_page for y in data.years]
            if any(v is None for _f, _y, v in vals):
                continue
            if vals and all(confirms(local_reads, p, v) for _f, _y, v in vals):
                fully_local.append(p)
        if fully_local:
            pages_needed = [p for p in pages_needed if p not in fully_local]
            notes.append(
                f"Page(s) {fully_local}: all core totals confirmed by the free "
                "local OCR read — no verification call spent."
            )
            if not pages_needed:
                return
    if notes is not None:
        notes.append(
            f"التحقق المركزي من إجماليات الميزانية بإعادة قراءة مركزة للصفحات {pages_needed}…"
        )
    if progress_cb:
        progress_cb(f"🔎 جارٍ التحقق المركزي من إجماليات الميزانية (الصفحات {pages_needed})…")

    third_budget = {"left": 4}  # third-opinion calls per run (covers BS, IS, OCI/Equity, CF)
    time_left = deadline - _time.time() if deadline is not None else float("inf")

    for page_number in pages_needed:
        # Higher resolution than the sweep: faded digits (the hard 2021
        # column) resolve at 2200px where the 1600px cap blurs them.
        # TWO preprocessing variants of the same page go in ONE call: the
        # standard cleanup + an adaptive-threshold binarization. Repeated
        # misreads survive identical preprocessing; cross-variant agreement
        # breaks them. Same quota cost as a single-image call.
        src_png = pages_png[selected.index(page_number)]
        img = preprocess_image(src_png, max_side=2200)
        img_bin = preprocess_image(src_png, max_side=2200, binarize=True)
        prompt = VERIFY_PROMPT
        _used_verify_model: str | None = None
        try:
            if caller is not None:
                raw_text = caller("k", "m", prompt, [img, img_bin])
            else:
                raw_text, _used_verify_model = _call_verify_prefer_distinct(
                    pool, prompt, [img, img_bin],
                    sweep_models=sweep_models, call_stats=call_stats,
                )
            verified = _parse_verify_json(raw_text)
        except Exception as exc:
            if notes is not None:
                notes.append(f"Verification of page {page_number} failed: {exc}")
            continue

        # Collect disagreements first: they are rare, and only they justify
        # spending a third-opinion call. The 2-vs-1 guard (local OCR
        # corroborating the capture) filters here too.
        disputes: dict[tuple[str, int], float] = {}
        verify_fields = set(core) | {"depreciation_amortization", "capex"}
        _bs_only = {
            "inventory", "accounts_receivable", "accounts_payable", "cash",
            "fixed_assets", "total_assets", "current_assets", "total_liabilities",
            "current_liabilities", "equity",
            "other_receivables", "supplier_advances", "customer_advances",
            "other_payables", "provisions", "long_term_notes_payable",
            "deferred_tax_liabilities",
        }
        _cf_only_pages = (
            {p for f in ("operating_cash_flow", "investing_cash_flow", "financing_cash_flow")
             for p in field_sources.get(f, [])}
            - {p for f in ("total_assets", "equity") for p in field_sources.get(f, [])}
        )
        for field, by_year in verified.items():
            if field not in verify_fields:
                continue
            if page_number in _cf_only_pages and field in _bs_only:
                continue  # Cash-flow working-capital changes (Δ) are never BS balances
            for year, value in by_year.items():
                captured = data.get(field, year)
                if captured is None:
                    continue
                if field == "capex":
                    # Preserve outflow sign convention (align sign with captured)
                    value = -abs(value) if captured < 0 else abs(value)
                elif field not in ("net_income", "pretax_income"):
                    value = abs(value)  # magnitudes; NI & pretax may be real losses (negative)
                # الحاجز الهيكلي (عز 2023): الأعمدة المشوهة تجعل قراءة
                # التحقق ترجع موضع العمود (2/1) بدل المبلغ — قيمة عدد
                # صحيح 0-3 ليست مبلغ قائمة: لا شاهد ولا نزاع ولا رأي ثالث
                if float(value).is_integer() and 0 <= value <= 3:
                    continue
                if local_reads:
                    from src.extraction.local_ocr import confirms

                    selected_set_v = set(selected)
                    src_pages = [p for p in field_sources.get(field, []) if p in selected_set_v]
                    if any(confirms(local_reads, p, captured) for p in src_pages):
                        # captured value already has two independent votes
                        key_c = (field, year)
                        conf[key_c] = max(conf.get(key_c, 0), 2)
                        if (
                            cross_model_hits is not None
                            and _used_verify_model
                            and abs(value - captured) <= max(1.0, 1e-6 * abs(captured))
                        ):
                            cross_model_hits[(field, year)] = (captured, _used_verify_model)
                        continue
                # Digit-exact verification: a 0.5% tolerance let digit
                # transpositions through (26.5M on 13.2B = 0.2% — "matched").
                # The focused re-read copies digits; agreement must be exact.
                if abs(value - captured) > max(1.0, 1e-6 * abs(captured)):
                    disputes[(field, year)] = value
                else:
                    key_c = (field, year)
                    conf[key_c] = max(conf.get(key_c, 0), 2)  # focused read agrees
                    if cross_model_hits is not None and _used_verify_model:
                        cross_model_hits[(field, year)] = (captured, _used_verify_model)

        if not disputes:
            continue

        # Third opinion: one more read, higher still (3000px), then 2-of-3.
        third_map: dict[str, dict[int, float]] = {}
        pool_ok = caller is not None or pool.has_usable_pairs()
        if third_budget["left"] > 0 and time_left > 30 and pool_ok:
            try:
                if notes is not None:
                    notes.append(
                        f"Disagreement on page {page_number} — resolving with a "
                        "third read at higher resolution (2-of-3 majority)…"
                    )
                if progress_cb:
                    progress_cb("AI vision: third opinion on disputed totals…")
                img3 = preprocess_image(pages_png[selected.index(page_number)], max_side=3000)
                raw3 = (
                    caller("k", "m", VERIFY_PROMPT, [img3])
                    if caller is not None
                    else _call_with_rotation(pool, VERIFY_PROMPT, [img3])
                )
                third_map = _parse_verify_json(raw3)
                third_budget["left"] -= 1
            except Exception as exc:
                if notes is not None:
                    notes.append(
                        f"Third opinion failed ({exc}) — the focused verify "
                        "read decides."
                    )

        for (field, year), value in disputes.items():
            captured = data.get(field, year)
            if captured is None:
                continue
            third = third_map.get(field, {}).get(year)
            if third is not None:
                if field == "capex":
                    third = -abs(third) if captured < 0 else abs(third)
                elif field not in ("net_income", "pretax_income"):
                    third = abs(third)
            # نفس الحاجز: موضع العمود من الرأي الثالث ليس شاهدًا
            if third is not None and float(third).is_integer() and 0 <= third <= 3:
                third = None
            if third is None:
                winner = value  # no third vote: focused read decides (old behavior)
                why = "focused verify read"
            else:
                winner = _majority_of_three(captured, value, third)
                why = "2-of-3 majority"
                if winner is None:
                    # All three reads disagree — trust the sweep capture and
                    # flag for manual review instead of gambling on one vote.
                    if notes is not None:
                        notes.append(
                            f"⚠ {field} in {year}: all three reads disagree — "
                            f"keeping the sweep capture {captured:,.0f}; "
                            "check the source page manually."
                        )
                    continue
            if abs(winner - captured) <= max(1.0, 1e-6 * abs(captured)):
                if notes is not None and third is not None:
                    notes.append(
                        f"✓ {why} kept the sweep capture for {field} {year}."
                    )
            else:
                # Accounting-identity veto on verify override: if `captured`
                # ALREADY satisfies a closed statement identity within 1 ppm
                # while `winner` breaks it (>10 ppm), NEVER let a noisy
                # 2-of-3 digit slip (e.g. 6->2 by 400k, or 088->000.88)
                # corrupt an exact primary capture!
                _veto_reason = None
                if field == "net_income":
                    _pt = data.get("pretax_income", year)
                    _tx = data.get("income_tax_expense", year)
                    if _pt is not None and _tx is not None:
                        _imp_a = _pt + _tx
                        _imp_b = _pt - abs(_tx)
                        _cap_err = min(abs(captured - _imp_a), abs(captured - _imp_b))
                        _win_err = min(abs(winner - _imp_a), abs(winner - _imp_b))
                        if _cap_err <= max(10.0, 1e-4 * abs(captured)) and _win_err > max(100.0, 1e-3 * abs(captured)):
                            _veto_reason = "pretax+tax=net_income"
                elif field in ("current_liabilities", "non_current_liabilities", "total_liabilities"):
                    _cl = captured if field == "current_liabilities" else data.get("current_liabilities", year)
                    _ncl = captured if field == "non_current_liabilities" else data.get("non_current_liabilities", year)
                    _tl = captured if field == "total_liabilities" else data.get("total_liabilities", year)
                    _cl_w = winner if field == "current_liabilities" else _cl
                    _ncl_w = winner if field == "non_current_liabilities" else _ncl
                    _tl_w = winner if field == "total_liabilities" else _tl
                    if None not in (_cl, _ncl, _tl):
                        _sc = max(abs(_tl), 1.0)
                        _cap_err = abs(abs(_cl) + abs(_ncl) - abs(_tl))
                        _win_err = abs(abs(_cl_w) + abs(_ncl_w) - abs(_tl_w))
                        if _cap_err <= max(10.0, 1e-6 * _sc) and _win_err > max(100.0, 1e-5 * _sc):
                            _veto_reason = "CL+NCL=TL"
                elif field in ("current_assets", "non_current_assets", "total_assets"):
                    _ca = captured if field == "current_assets" else data.get("current_assets", year)
                    _nca = captured if field == "non_current_assets" else data.get("non_current_assets", year)
                    _ta = captured if field == "total_assets" else data.get("total_assets", year)
                    _ca_w = winner if field == "current_assets" else _ca
                    _nca_w = winner if field == "non_current_assets" else _nca
                    _ta_w = winner if field == "total_assets" else _ta
                    if None not in (_ca, _nca, _ta):
                        _sc = max(abs(_ta), 1.0)
                        _cap_err = abs(abs(_ca) + abs(_nca) - abs(_ta))
                        _win_err = abs(abs(_ca_w) + abs(_nca_w) - abs(_ta_w))
                        if _cap_err <= max(10.0, 1e-6 * _sc) and _win_err > max(100.0, 1e-5 * _sc):
                            _veto_reason = "CA+NCA=TA"
                elif field in ("equity", "total_liabilities", "total_assets"):
                    _eq = captured if field == "equity" else data.get("equity", year)
                    _tl = captured if field == "total_liabilities" else data.get("total_liabilities", year)
                    _ta = captured if field == "total_assets" else data.get("total_assets", year)
                    _eq_w = winner if field == "equity" else _eq
                    _tl_w = winner if field == "total_liabilities" else _tl
                    _ta_w = winner if field == "total_assets" else _ta
                    if None not in (_eq, _tl, _ta):
                        _sc = max(abs(_ta), 1.0)
                        _cap_err = abs(_eq + abs(_tl) - abs(_ta))
                        _win_err = abs(_eq_w + abs(_tl_w) - abs(_ta_w))
                        if _cap_err <= max(10.0, 1e-6 * _sc) and _win_err > max(100.0, 1e-5 * _sc):
                            _veto_reason = "TL+Equity=TA"
                elif field in ("revenue", "cost_of_revenue", "gross_profit"):
                    _rv = captured if field == "revenue" else data.get("revenue", year)
                    _cg = captured if field == "cost_of_revenue" else data.get("cost_of_revenue", year)
                    _gp = captured if field == "gross_profit" else data.get("gross_profit", year)
                    _rv_w = winner if field == "revenue" else _rv
                    _cg_w = winner if field == "cost_of_revenue" else _cg
                    _gp_w = winner if field == "gross_profit" else _gp
                    if None not in (_rv, _cg, _gp):
                        _sc = max(abs(_rv), abs(_gp), 1.0)
                        _cap_err = abs(abs(_rv) - abs(_cg) - _gp)
                        _win_err = abs(abs(_rv_w) - abs(_cg_w) - _gp_w)
                        if _cap_err <= max(10.0, 1e-6 * _sc) and _win_err > max(50.0, 1e-5 * _sc):
                            _veto_reason = "Rev-COGS=GP"
                if _veto_reason is not None:
                    if notes is not None:
                        notes.append(
                            f"✓ Accounting identity ({_veto_reason}) preserved sweep {field} {year} "
                            f"({captured:,.0f}) over disagreeing verify read ({winner:,.0f})."
                        )
                    continue
                for part in parts:
                    if year in part and field in part[year]:
                        part[year][field] = winner  # corrected at the source
                if notes is not None:
                    notes.append(
                        f"✓ Resolved by {why}: {field} in {year} "
                        f"{captured:,.0f} → {winner:,.0f}."
                    )
            if third is not None:
                # witness count for the surviving value (2 or 3 agreeing reads)
                tol_w = max(1.0, 1e-6 * max(abs(winner or 0), 1))
                votes = sum(
                    1 for v in (captured, value, third)
                    if v is not None and abs(v - winner) <= tol_w
                )
                key_c = (field, year)
                conf[key_c] = max(conf.get(key_c, 0), min(votes, 3))


def _majority_of_three(a: float, b: float, c: float) -> float | None:
    """Digit-exact majority among three reads; None when all differ."""
    tol = max(1.0, 1e-6 * max(abs(a or 0), abs(b or 0), abs(c or 0)))
    for x, y in ((a, b), (a, c), (b, c)):
        if x is not None and y is not None and abs(x - y) <= tol:
            return x
    return None


CF_RECOVERY_PROMPT = """This scanned ARABIC page may contain the cash-flow statement
(قائمة التدفقات النقدية). If it does, extract ONLY these three rows, exactly as
printed, for EACH year column shown:
- صافي التدفقات النقدية من الأنشطة التشغيلية (OPERATING activities)
- صافي التدفقات النقدية من الأنشطة الاستثمارية (INVESTING activities)
- صافي التدفقات النقدية من الأنشطة التمويلية (FINANCING activities)

Return ONLY JSON: {{"pages": [{{"page": {page}, "years": [y1, y2],
"rows": [["<exact label>", v1, v2], ...]}}]}}
Parentheses = negative. If the page has no cash-flow statement, return rows = [].
"""


VERIFY_CF_PROMPT = """From this scanned ARABIC cash-flow statement page, read ONLY these cash-flow
items, exactly as printed, for EACH year column shown:
- النقدية الناتجة من الأنشطة التشغيلية (OPERATING activities) — the printed
  phrasing may be "صافي التدفقات النقدية من الأنشطة التشغيلية" OR
  "صافي النقدية الناتجة من أنشطة التشغيل" — same row either way
- الأنشطة الاستثمارية (INVESTING activities)
- الأنشطة التمويلية (FINANCING activities)
- مدفوعات لشراء أصول ثابتة ومشروعات تحت التنفيذ (capex — investing outflow)
- إهلاك أصول ثابتة (depreciation_amortization — operating non-cash adjustment)

Return ONLY JSON:
{{"years": [2021, 2022],
  "totals": {{"operating_cash_flow": [v1, v2], "investing_cash_flow": [v1, v2],
              "financing_cash_flow": [v1, v2],
              "capex": [v1, v2], "depreciation_amortization": [v1, v2]}}}}
Use null for any value not on the page. Parentheses = NEGATIVE (they matter —
keep the sign). Copy digits exactly.
"""


def _recover_cash_flow(
    data: FinancialData,
    parts: list,
    field_sources: dict[str, list[int]],
    pages_png: list[bytes],
    selected: list[int],
    ok_pages: set,
    doc_years_holder: dict,
    pool: APIKeyPool,
    caller=None,
    notes: list[str] | None = None,
    progress_cb=None,
    deadline: float | None = None,
    local_reads=None,
    gap_sink: list | None = None,
) -> None:
    """If the cash-flow statement exists but wasn't captured, re-ask the pages
    adjacent to the identified statement pages with a focused cash-flow prompt."""
    import time as _time

    notes = notes if notes is not None else []
    years = doc_years_holder.get("years")
    if not years:
        return
    if all(data.get("operating_cash_flow", y) is not None for y in years[:2]):
        return  # already captured
    stmt_pages = sorted({
        p for f in ("total_assets", "revenue", "net_income", "equity")
        for p in field_sources.get(f, [])
    })
    # Candidates: pages adjacent to the statement pages — INCLUDING statement
    # pages themselves (the cash-flow statement often sits right after the
    # balance sheet, and its rows may have been missed by the general read).
    # Only pages the user actually selected can be re-read: adjacent pages in
    # DOC numbering may fall outside a user page range, and indexing them
    # into the rendered set would crash (list.index(x) — fixed bug).
    selected_set = set(selected)
    adj: list[int] = []
    for p in stmt_pages:
        for d in (-2, -1, 0, 1, 2):
            q = p + d
            if q in selected_set and q not in adj:
                adj.append(q)
    adj = [q for q in adj if q not in ok_pages or q in stmt_pages]
    adj = adj[:6]
    # Local OCR hint: pages whose free local read mentions the cash-flow
    # statement — target them FIRST even if the general sweep already read
    # them (its rows may have failed to match the CF aliases). This catches
    # the common layout where the CF statement sits >2 pages from the
    # balance sheet and the ±2 adjacency window misses it entirely.
    if local_reads:
        hinted = [p for p in selected if local_reads.get(p) is not None
                  and local_reads[p].cf_hint and p not in adj]
        if hinted:
            notes.append(
                f"Local OCR located the cash-flow statement on page(s) {hinted} — "
                "re-reading them with the focused cash-flow prompt."
            )
            adj = hinted[:2] + adj
            adj = adj[:8]
    if not adj:
        return
    notes.append(
        f"Cash-flow statement not captured — re-reading adjacent page(s) {adj} "
        "with a focused cash-flow prompt…"
    )
    if progress_cb:
        progress_cb(f"💧 استرجاع قائمة التدفقات النقدية (الصفحات {adj})…")

    for page_number in adj:
        if deadline is not None and _time.time() > deadline:
            notes.append("Cash-flow recovery skipped — time budget exhausted.")
            break
        try:
            img = preprocess_image(pages_png[selected.index(page_number)])
            prompt = CF_RECOVERY_PROMPT.format(page=page_number)
            raw_text = (
                caller("k", "m", prompt, [img])
                if caller is not None
                else _call_with_rotation(pool, prompt, [img])
            )
            for page in _parse_vision_json(raw_text):
                p_years = page["years"] or years
                if len(p_years) < 2:
                    p_years = years
                rows = [row[: 3] for row in page["rows"]]
                if not rows:
                    continue
                frame = pd.DataFrame(rows, columns=["Item"] + p_years, dtype=object)
                try:
                    parsed = parse_table(frame, gap_sink=gap_sink)
                    if parsed:
                        parts.append(parsed)
                        ok_pages.add(page_number)
                except Exception as exc:
                    notes.append(f"Cash-flow recovery page skipped ({exc}).")
        except Exception as exc:
            notes.append(f"Cash-flow recovery page {page_number} failed: {exc}")


def _parse_verify_cf_json(text: str) -> dict:
    """{field: {year: value}} from the focused cash-flow verify response.
    Signs are preserved (a financing outflow is genuinely negative)."""
    data = _loads_relaxed(text)
    years = [extract_year(y) for y in (data.get("years") or [])]
    years = [y for y in years if y]
    out: dict[str, dict[int, float]] = {}
    for field, values in (data.get("totals") or {}).items():
        if not isinstance(values, list):
            continue
        by_year: dict[int, float] = {}
        for i, v in enumerate(values):
            if i >= len(years):
                break
            num = parse_number(v)
            if num is not None and num != 0.0:
                by_year[years[i]] = num
        if by_year:
            out[str(field).strip()] = by_year
    return out


def _verify_cf_fields(
    data: FinancialData,
    parts: list,
    field_sources: dict[str, list[int]],
    pages_png: list[bytes],
    selected: list[int],
    pool: APIKeyPool,
    caller=None,
    notes: list[str] | None = None,
    progress_cb=None,
    local_reads=None,
    deadline: float | None = None,
    confidence: dict | None = None,
    sweep_models: list[str] | None = None,
    call_stats: list[tuple[str, float]] | None = None,
    cross_model_hits: dict[tuple[str, int], tuple[float, str]] | None = None,
) -> None:
    """Focused double-read of the three net-cash totals — the cash-flow
    statement was the last line without a verification layer, yet its rows
    carry signs (financing outflows are negative) and OCR flips them.

    Skips entirely when nothing was captured or the time budget is gone.
    The 2-vs-1 local-OCR rule applies: a value Indra's free read corroborates
    digit-for-digit cannot be replaced by a disagreeing focused read.
    """
    import time as _time

    notes = notes if notes is not None else []
    cf_fields = [f for f in ("operating_cash_flow", "investing_cash_flow", "financing_cash_flow")
                 if f in field_sources and any(data.get(f, y) is not None for y in data.years)]
    if not cf_fields:
        return
    if deadline is not None and _time.time() > deadline:
        notes.append("Cash-flow verification skipped — time budget exhausted.")
        return
    selected_set = set(selected)
    pages_needed = sorted({p for f in cf_fields for p in field_sources.get(f, [])
                           if p in selected_set})
    if local_reads:
        pages_needed = [p for p in pages_needed
                        if local_reads.get(p) is None or local_reads[p].has_table]
    pages_needed = pages_needed[:2]
    if not pages_needed:
        return
    notes.append(
        f"Verifying cash-flow totals by focused re-read of page(s) {pages_needed}…"
    )
    if progress_cb:
        progress_cb(f"🔎 جارٍ التحقق المركزي من إجماليات الميزانية (الصفحات {pages_needed})…")

    for page_number in pages_needed:
        if deadline is not None and _time.time() > deadline:
            notes.append("Cash-flow verification stopped — time budget exhausted.")
            break
        # Dual-variant protocol (same as the core verify): standard cleanup +
        # adaptive-threshold binarization of the same page in ONE call — a
        # live run misread the CF net row (1,914,507,839 vs printed
        # 1,214,507,829) from a single-variant image.
        src_png = pages_png[selected.index(page_number)]
        img = preprocess_image(src_png, max_side=2200)
        img_bin = preprocess_image(src_png, max_side=2200, binarize=True)
        _used_cf_model: str | None = None
        try:
            if caller is not None:
                raw_text = caller("k", "m", VERIFY_CF_PROMPT, [img, img_bin])
            else:
                raw_text, _used_cf_model = _call_verify_prefer_distinct(
                    pool, VERIFY_CF_PROMPT, [img, img_bin],
                    sweep_models=sweep_models, call_stats=call_stats,
                )
            verified = _parse_verify_cf_json(raw_text)
        except Exception as exc:
            notes.append(f"Cash-flow verification of page {page_number} failed: {exc}")
            continue
        cf_verify_fields = set(cf_fields) | {"capex", "depreciation_amortization"}
        for field, by_year in verified.items():
            if field not in cf_verify_fields:
                continue
            for year, value in by_year.items():
                captured = data.get(field, year)
                if captured is None:
                    continue
                if field == "capex":
                    value = -abs(value) if captured < 0 else abs(value)
                elif field == "depreciation_amortization":
                    value = abs(value)
                if local_reads:
                    from src.extraction.local_ocr import confirms

                    src_pages = [p for p in field_sources.get(field, [])
                                 if p in selected_set]
                    if any(confirms(local_reads, p, captured) for p in src_pages):
                        if confidence is not None:
                            key_c = (field, year)
                            confidence[key_c] = max(confidence.get(key_c, 0), 2)
                        if (
                            cross_model_hits is not None
                            and _used_cf_model
                            and abs(value - captured) <= max(1.0, 1e-6 * abs(captured))
                        ):
                            cross_model_hits[(field, year)] = (captured, _used_cf_model)
                        continue  # captured value has two independent votes
                if abs(value - captured) > max(1.0, 1e-6 * abs(captured)):
                    for part in parts:
                        if year in part and field in part[year]:
                            # For D&A, only replace if the part holds the CF capture (not a tiny note slice)
                            if field == "depreciation_amortization" and abs(part[year][field]) < 0.8 * abs(value):
                                continue
                            part[year][field] = value  # sign included, corrected at source
                    if notes is not None:
                        notes.append(
                            f"✓ Verified by focused CF re-read: {field} in {year} "
                            f"{captured:,.0f} → {value:,.0f}."
                        )
                else:
                    if confidence is not None:
                        key_c = (field, year)
                        confidence[key_c] = max(confidence.get(key_c, 0), 2)
                    if cross_model_hits is not None and _used_cf_model:
                        cross_model_hits[(field, year)] = (captured, _used_cf_model)


def extract_via_vision(
    raw: bytes,
    notes: list[str],
    pool: APIKeyPool | None = None,
    progress_cb=None,
    page_range: tuple[int, int] | None = None,
    workers: int | None = None,
    caller=None,
    fast_mode: bool = False,
) -> FinancialData:
    """Main scanned-PDF entry: renders → cleans → reads (parallel waves) →
    parses → merges.

    Parallelism does NOT change what the model sees: every page keeps its own
    image, prompt and temperature-0 config — only the request timing differs,
    so per-page results are identical to sequential extraction (proven by
    test_parallel_equals_sequential).

    `caller(key, model, prompt, images) -> str` is injectable for tests.
    `fast_mode` skips the paid verification layers (core verify, third
    opinion, CF verify) — one sweep only, roughly half the calls, for
    triaging many files; re-run in full mode for the final audited numbers.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from src.ai.gemini_agent import get_pool

    n_workers = workers or VISION_WORKERS
    pool = pool or get_pool()
    if not pool.states:
        raise ExtractionError(
            "AI vision extraction needs API keys (GEMINI_API_KEYS in .env) to read "
            "this scanned PDF."
        )
    try:
        import pypdfium2  # noqa: F401
    except ImportError:
        raise ExtractionError("pypdfium2 is not installed — cannot render scanned pages.")

    notes.append(
        "Scanned PDF detected (no text layer) — pages were read with AI vision "
        "(OpenCV cleanup + Gemini), then validated by accounting identities."
    )
    if not pool.has_usable_pairs():
        # Fail before rendering/sweeping: a dead pool cannot improve, and the
        # full sweep would burn minutes only to fail identically per batch.
        raise ExtractionError(
            "all API key/model pairs are exhausted or unavailable — the free "
            "tier allows ~20 requests/day per key per model and resets after "
            "midnight US Pacific. Add fresh keys in .env or try again later."
        )
    indices = None
    if page_range is not None:
        a, b = sorted(page_range)
        indices = list(range(a, b + 1))
        notes.append(f"Page range selected by the user: pages {a}-{b}.")
    pages_png = _render_pages(raw, VISION_MAX_PAGES, notes, indices)
    selected = indices if indices is not None else list(range(1, len(pages_png) + 1))
    n_pages = len(pages_png)
    t_overall = __import__("time").time()  # التسريع: قياس الرحلة للأسفل

    # Local OCR pre-layer (free, CPU-only): triage which pages carry table
    # markup and reorder them FIRST. Statement pages reach the early-stop
    # check sooner, so trailing note/signature pages never consume quota.
    # Never runs for injected test callers; any failure = silent no-op.
    local_reads = None
    if LOCAL_OCR_ENABLED and caller is None:
        try:
            from src.extraction.local_ocr import read_pages

            if progress_cb:
                progress_cb("Local OCR (Indra): triaging pages — zero API cost…")
            local_reads = read_pages({p: png for p, png in zip(selected, pages_png)})
        except Exception:
            local_reads = None
        if local_reads:
            table_first = [p for p in selected if p in local_reads and local_reads[p].has_table]
            rest = [p for p in selected if not (p in local_reads and local_reads[p].has_table)]
            order = table_first + rest
            if order != selected:
                by_page = dict(zip(selected, pages_png))
                pages_png = [by_page[p] for p in order]
                selected = order
            notes.append(
                f"Local OCR triage: {len(table_first)}/{n_pages} pages carry table "
                "markup — they are read first so the run can stop early."
            )

    # consecutive batches of the SELECTED pages. A batch must be a run of
    # CONSECUTIVE page numbers — the prompt tells the model "pages A to B in
    # this order", so a gap inside a batch would misattribute rows to the
    # wrong page numbers (seen live: chunk [9,11,12,3] garbled attribution).
    def _build_batches(order: list[int]) -> list[tuple[list[int], list[bytes]]]:
        runs: list[list[int]] = []
        for p in order:
            # Primary financial statement pages (p <= 12) hold dense 20-40 row
            # Arabic tables; bundling 3 of them into one call causes 20-35s
            # latency, 504 timeouts, or JSON truncation of Page 6 (Income Statement).
            # Reading dense early statement pages individually in parallel is both
            # faster and immune to cross-page output truncation.
            is_dense_stmt = (
                caller is None
                and p <= 12
                and (
                    (local_reads and p in local_reads and local_reads[p].has_table)
                    or not local_reads
                )
            )
            max_chunk = 1 if is_dense_stmt else VISION_BATCH_SIZE
            if (
                runs
                and max_chunk > 1
                and len(runs[-1]) < max_chunk
                and p == runs[-1][-1] + 1
                and not (caller is None and runs[-1][-1] <= 12 and (
                    (local_reads and runs[-1][-1] in local_reads and local_reads[runs[-1][-1]].has_table)
                    or not local_reads
                ))
            ):
                runs[-1].append(p)
            else:
                runs.append([p])
        return [(
            chunk,
            [preprocess_image(by_page[p]) for p in chunk],
        ) for chunk in runs]

    by_page = dict(zip(selected, pages_png))
    batches = _build_batches(selected)

    parts: list[dict[int, dict[str, float]]] = []
    part_pages: list[int] = []  # source page per part — keeps primary statements ahead of notes
    accumulated = FinancialData()
    currency_holder: dict = {"hint": None}
    company_holder: dict = {"name": None}
    doc_years_holder: dict = {"years": None}
    # التسريع: قياس زمن كل نداء ناجح (model, seconds) — يظهر في ملاحظة ⏱
    call_stats: list[tuple[str, float]] = []
    # سجل الفجوات: كل صف بقيم فشلت مطابقته يُسجل هنا ويظهر في الملاحظات
    gap_sink: list[dict] = []
    # التقاطات التسميات للشكل الدلالي — تغذي تصويت الشهود بمعرفة التسميات
    caps_acc: list = []
    ok_pages: set[int] = set()
    field_sources: dict[str, list[int]] = {}  # field -> pages that provided it
    confidence: dict = {}                     # (field, year) -> agreeing reads
    failure_reasons: list[str] = []           # why vision reads failed (for the final error)
    stopped_early = False
    quota_interrupted = False
    done_pages = 0

    def _run_batch(chunk: list[int], imgs: list[bytes]) -> list[dict]:
        first, last = chunk[0], chunk[-1]
        if _semantic_enabled():
            prompt = _semantic_prompt(first, last)
        else:
            prompt = (
                VISION_PROMPT.format(first=first, last=last)
                if len(chunk) > 1
                else _single_prompt(first)
            )
        if caller is not None:
            return _parse_vision_json(caller("k", "m", prompt, imgs))
        raw_text = _call_with_rotation(pool, prompt, imgs, call_stats)
        if _semantic_enabled():
            # التشخيص القاطع: الرد الخام يُحفظ — تحليل ما أرجعه الموديل
            # فعليًا بدل الارتكاز على آثار القيم في السجل
            try:
                import time as _t
                from pathlib import Path as _P
                _dir = _P(__file__).resolve().parents[2] / "logs" / "semantic_raw"
                _dir.mkdir(parents=True, exist_ok=True)
                (_dir / f"batch_{first}_{last}_{int(_t.time()*1000) % 10**9}.txt"
                 ).write_text(str(raw_text)[:300000], encoding="utf-8")
            except Exception:
                pass
        return _parse_vision_json(raw_text)

    import time as _time

    deadline = _time.time() + VISION_TOTAL_BUDGET
    t_stage = {"sweep": _time.time()}  # التسريع: قياس زمن كل مرحلة للملاحظة النهائية
    wave_size = max(n_workers, 1)  # batches per wave
    last_captured = -1
    dry_waves = 0
    for wave_start in range(0, len(batches), wave_size):
        if _time.time() > deadline:
            notes.append(
                f"Vision time budget ({VISION_TOTAL_BUDGET}s) exhausted — "
                f"proceeding with the {done_pages}/{n_pages} pages read so far."
            )
            break
        if not batches[wave_start : wave_start + wave_size]:
            break
        if wave_start > 0 and not pool.has_usable_pairs():
            wait_sw = pool.shortest_cooldown_wait() if hasattr(pool, "shortest_cooldown_wait") else None
            if wait_sw is not None and 0.0 < wait_sw <= 25.0 and _time.time() + wait_sw < deadline:
                _time.sleep(min(wait_sw + 0.5, 25.0))
        if wave_start > 0 and not pool.has_usable_pairs():
            # Pool died mid-run (all pairs quota-exhausted): stop sweeping,
            # remaining batches cannot succeed.
            quota_interrupted = True
            notes.append(
                "Stopping the vision sweep: all API key/model pairs are now "
                "exhausted or unavailable."
            )
            break
        wave = batches[wave_start : wave_start + wave_size]
        wave_results: list[tuple[list[int], list[dict]]] = []
        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            futures = {executor.submit(_run_batch, chunk, imgs): chunk for chunk, imgs in wave}
            for future in as_completed(futures):
                chunk = futures[future]
                try:
                    batch_pages = future.result()
                except ExtractionError as exc:
                    notes.append(
                        f"Vision batch {chunk[0]}-{chunk[-1]} failed: {exc}"
                    )
                    failure_reasons.append(str(exc))
                    batch_pages = []
                except Exception as exc:
                    notes.append(f"Vision batch {chunk[0]}-{chunk[-1]} error: {exc}")
                    failure_reasons.append(str(exc)[:250])
                    batch_pages = []
                wave_results.append((chunk, batch_pages))
                done_pages += len(chunk)
                if progress_cb:
                    progress_cb(f"📚 وصلنا للصفحة {done_pages} من {n_pages}…")
        # Absorb batches in ascending page order so parallel worker timing never
        # lets later note pages hijack first-capture priority from primary statements.
        for chunk, batch_pages in sorted(wave_results, key=lambda item: item[0][0]):
            _before = len(parts)
            _absorb_batch(batch_pages, chunk, parts, ok_pages, notes, currency_holder, doc_years_holder, field_sources, gap_sink, caps_acc)
            _added = len(parts) - _before
            if _added > 0:
                part_pages.extend([chunk[0]] * _added)
                if caps_acc and len(caps_acc) < len(parts):
                    caps_acc.extend([[] for _ in range(len(parts) - len(caps_acc))])
            if not company_holder.get("name"):
                company_holder["name"] = next(
                    (p.get("company") for p in batch_pages if p.get("company")), None
                )

        accumulated = merge_parsed(parts, [], part_layers=["vision"] * len(parts))
        # التسريع — توقف الموجة الجافة: موجتان متتاليتان بلا أي بند جديد =
        # الصفحات الباقية إيضاحات لن تضيف شيئًا — لا تحرق السقف الكامل
        # (حديد عز: صافي الربح لا يُلتقط أبدًا في هذا المستند فكان
        # _enough_core لن ينطلق والمسح يستهلك السقف كاملًا)
        captured_now = sum(
            1 for _f, by_y in accumulated.values.items()
            for v in by_y.values() if v is not None)
        if captured_now > last_captured:
            dry_waves = 0
        else:
            dry_waves += 1
        last_captured = captured_now
        has_is_anchor = bool(
            accumulated.values.get("revenue") or accumulated.values.get("net_income")
        )
        if dry_waves >= 2 and (has_is_anchor or done_pages >= min(n_pages, 14)):
            # ملاحظة: لا نضع stopped_early هنا — الصفحات الفاشلة قد تكون
            # قوائمًا فشلت عابرةً (503) وتستحق إعادة القراءة المحدودة
            notes.append(
                f"Vision sweep stopped after {done_pages}/{n_pages} pages: "
                "two consecutive waves captured no new fields (remaining "
                "pages are notes — diminishing returns)."
            )
            break
        if _enough_core(accumulated):
            stopped_early = True
            notes.append(
                f"Vision extraction stopped early after page "
                f"{max(ok_pages) if ok_pages else 0}: the core statements were "
                "complete (remaining pages are notes)."
            )
            break

    # Second pass: retry failed pages once, one at a time (503 storms are
    # transient — a page that failed in a batch often reads fine later).
    # Skipped when early-stop fired (those pages are notes) or when the pool
    # is already dead — retrying then only adds minutes with zero chance.
    failed_pages = (
        sorted(
            [p for p in selected if p not in ok_pages],
            key=lambda p: (0 if p <= 12 else 1, p),
        )
        if not stopped_early
        else []
    )
    if failed_pages and not pool.has_usable_pairs():
        quota_interrupted = True
        notes.append(
            "Skipping the retry pass: all API key/model pairs are exhausted "
            "or unavailable."
        )
    elif failed_pages:
        notes.append(f"Retrying {len(failed_pages)} unread page(s): {failed_pages[:12]}…")
        if progress_cb:
            progress_cb(f"🔁 إعادة قراءة {len(failed_pages)} صفحة لم تكتمل…")
        # التسريع: كانت الإعادة تسلسلية — 10 صفحات × 45 ثانية = ~7.5 دقيقة
        # خارج كل سقف (حديد عز: أكلت نصف الرحلة). صارت متوازية بنفس عرض
        # الموجات + سقف زمني خاص.
        # تنوع العقود (عز 2023): المسح الدلالي قد ينهار لمواضع الأعمدة على
        # الأعمدة المشوهة — الإعادة تستخدم العقد الحرفي v2 (فشل كل عقد
        # يغطيه الآخر: عقود مختلفة = أنماط فشل مختلفة = تنوع حقيقي)
        retry_semantic = _semantic_enabled()
        retry_deadline = min(deadline, _time.time() + VISION_RETRY_BUDGET)
        t_stage["retry"] = _time.time()
        by_page_png = dict(zip(selected, pages_png))

        def _retry_one(page_number: int) -> tuple[int, str | None, str]:
            try:
                prompt = (_single_prompt(page_number) if retry_semantic
                          else VISION_PROMPT.format(first=page_number,
                                                    last=page_number))
                raw_text = (
                    caller("k", "m", prompt,
                           [preprocess_image(by_page_png[page_number])])
                    if caller is not None
                    else _call_with_rotation(
                        pool, prompt,
                        [preprocess_image(by_page_png[page_number])])
                )
                return page_number, raw_text, ""
            except Exception as exc:
                return page_number, None, str(exc)

        retried_done = 0
        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            futures = {executor.submit(_retry_one, p): p for p in failed_pages}
            for future in as_completed(futures):
                if _time.time() > retry_deadline:
                    for f in futures:
                        f.cancel()  # المعلقة فقط تُلغى — الجارية تكتمل وتُسقط
                    notes.append(
                        f"Retry budget ({VISION_RETRY_BUDGET}s) exhausted "
                        "— proceeding with what was re-read.")
                    break
                pn, raw_text, err = future.result()
                retried_done += 1
                if raw_text is None:
                    notes.append(f"Vision page {pn} failed again (skipped).")
                    if err:
                        failure_reasons.append(err)
                    continue
                _before_r = len(parts)
                try:
                    retry_pages = _parse_vision_json(raw_text)
                except Exception as exc:
                    notes.append(f"Vision retry page {pn} returned non-JSON ({exc}) — skipped.")
                    retry_pages = []
                for page in retry_pages:
                    if page.get("rows") and isinstance(page["rows"][0], dict)                             and retry_semantic:
                        years0 = page["years"] or (doc_years_holder.get("years") or [])
                        if len(years0) >= 2:
                            _absorb_semantic_page(
                                page, years0, [pn], parts, ok_pages,
                                field_sources, gap_sink, caps_acc, notes)
                    else:
                        # عقد v2 الحرفي (الإعادة المعاكسة) أو رد غير دلالي
                        frame = _page_to_frame(page)
                        if frame is not None:
                            try:
                                parsed = parse_table(frame, gap_sink=gap_sink)
                                if parsed:
                                    _cf_k_r = {"operating_cash_flow", "investing_cash_flow", "financing_cash_flow", "capex"}
                                    _bs_anc_r = {"total_assets", "equity"}
                                    _bs_str_r = {
                                        "inventory", "accounts_receivable", "accounts_payable", "cash",
                                        "total_assets", "current_assets", "total_liabilities",
                                        "current_liabilities", "equity", "fixed_assets",
                                        "long_term_debt", "short_term_debt", "short_term_credit_facilities",
                                        "current_portion_lt_debt", "non_current_lease_liabilities",
                                        "current_lease_liabilities",
                                    }
                                    _all_f_r = {f for ym in parsed.values() for f in ym}
                                    if (_all_f_r & _cf_k_r) and not (_all_f_r & _bs_anc_r):
                                        for ym in parsed.values():
                                            for bf in list(ym.keys()):
                                                if bf in _bs_str_r:
                                                    ym.pop(bf, None)
                                    if any(ym for ym in parsed.values()):
                                        parts.append(parsed)
                                        for ym in parsed.values():
                                            for bf in ym:
                                                field_sources.setdefault(bf, []).append(pn)
                            except Exception as exc:
                                notes.append(f"Vision page skipped ({exc}).")
                    if not company_holder.get("name") and page.get("company"):
                        company_holder["name"] = page["company"]
                _added_r = len(parts) - _before_r
                if _added_r > 0:
                    part_pages.extend([pn] * _added_r)
                    if caps_acc and len(caps_acc) < len(parts):
                        caps_acc.extend([[] for _ in range(len(parts) - len(caps_acc))])
                if progress_cb:
                    progress_cb(
                        f"🔁 إعادة قراءة {retried_done}/{len(failed_pages)}…")
        # Restore ascending document page order after retries so a retried
        # Balance Sheet / Income Statement page still precedes later note pages.
        if len(part_pages) == len(parts) and len(parts) > 1:
            order_idx = sorted(range(len(parts)), key=lambda i: part_pages[i])
            parts[:] = [parts[i] for i in order_idx]
            part_pages[:] = [part_pages[i] for i in order_idx]
            if len(caps_acc) == len(parts):
                caps_acc[:] = [caps_acc[i] for i in order_idx]
        accumulated = merge_parsed(parts, [], part_layers=["vision"] * len(parts))

    # Income-Statement rescue pass: if BOTH revenue and net_income are still
    # missing after the initial sweep + retry (e.g., transient 503/truncation
    # on the P&L page), re-read up to 4 early table pages (p <= 10) individually
    # at 2000px using the literal v2 prompt before failing with InsufficientData.
    if (
        caller is None
        and pool.has_usable_pairs()
        and not accumulated.values.get("revenue")
        and not accumulated.values.get("net_income")
    ):
        _by_png = dict(zip(selected, pages_png))
        _early_cand = [
            p for p in sorted(_by_png)
            if p <= 10
            and (not local_reads or p not in local_reads or local_reads[p].has_table or local_reads[p].text_len >= 600)
        ][:4]
        for _ep in _early_cand:
            if _time.time() > deadline or not pool.has_usable_pairs():
                break
            try:
                _rtxt = _call_with_rotation(
                    pool,
                    _single_prompt(_ep),
                    [preprocess_image(_by_png[_ep], max_side=2000)],
                    call_stats,
                )
                _rpages = _parse_vision_json(_rtxt)
                _before_is = len(parts)
                _absorb_batch(
                    _rpages, [_ep], parts, ok_pages, notes,
                    currency_holder, doc_years_holder, field_sources,
                    gap_sink, caps_acc,
                )
                _added_is = len(parts) - _before_is
                if _added_is > 0:
                    part_pages.extend([_ep] * _added_is)
                    if caps_acc and len(caps_acc) < len(parts):
                        caps_acc.extend([[] for _ in range(len(parts) - len(caps_acc))])
                accumulated = merge_parsed(parts, [], part_layers=["vision"] * len(parts))
                if accumulated.values.get("revenue") or accumulated.values.get("net_income"):
                    notes.append(f"Income-Statement rescue succeeded on page {_ep}.")
                    break
            except Exception:
                continue

    # Focused double-read of the four core balance-sheet totals: replaces
    # captures that disagree with a fresh, focused read of their source page
    # (kills most of the run-to-run OCR variance on scanned pages).
    # Fast mode: skipped — its value is the final audited numbers, not triage.
    if fast_mode:
        notes.append(
            "⚡ Fast mode: verification layers skipped (single sweep). "
            "Re-run in full mode for audited figures."
        )
    # Cash-flow recovery: re-ask adjacent pages with a focused CF prompt
    # when the cash-flow statement exists but wasn't captured.
    pre_merge = merge_parsed(parts, [], part_layers=["vision"] * len(parts))
    # التسريع: مراحل التحقق الثلاث تتقاسم ميزانية واحدة (كانت كل مرحلة
    # يمكن أن تمشي حتى سقف المسح الكامل 720 ثانية)
    verify_deadline = min(deadline, _time.time() + VISION_VERIFY_BUDGET)
    t_stage["verify"] = _time.time()
    if fast_mode:
        # الوضع السريع: استرجاع التدفقات متخطى (أكبر مُكلف: حتى 8 نداءات)
        # — حقول التدفقات تبقى مفقودة بصدق ومقاييسها غير متوفر، أعد
        # بالوضع الدقيق للتحليل الكامل
        notes.append(
            "⚡ Fast mode: cash-flow recovery skipped — CF metrics show "
            "غير متوفر; re-run in precise mode for the full analysis."
        )
    else:
        _recover_cash_flow(
            pre_merge,
            parts,
            field_sources,
            pages_png,
            selected,
            ok_pages,
            doc_years_holder,
            pool,
            caller,
            notes,
            progress_cb,
            deadline=verify_deadline,
            local_reads=local_reads,
            gap_sink=gap_sink,
        )

    # Focused double-read of the three net-cash totals — the CF statement
    # carries SIGNS (outflows negative). Runs BEFORE the expensive core
    # third-opinion stage: a real run once exhausted the whole time budget
    # on that stage and CFO shipped unverified with a wrong capture.
    _sweep_models_v = [m for m, _t in (call_stats or []) if m]
    _unified_cm_hits: dict[tuple[str, int], tuple[float, str]] = {}

    if not fast_mode:
        _verify_cf_fields(
            merge_parsed(parts, []),
            parts,
            field_sources,
            pages_png,
            selected,
            pool,
            caller,
            notes,
            progress_cb,
            local_reads=local_reads,
            deadline=verify_deadline,
            confidence=confidence,
            sweep_models=_sweep_models_v,
            call_stats=call_stats,
            cross_model_hits=_unified_cm_hits,
        )

    # Focused double-read of the four core balance-sheet totals: replaces
    # captures that disagree with a fresh, focused read of their source page
    # (kills most of the run-to-run OCR variance on scanned pages).
    # Fast mode: skipped — its value is the final audited numbers, not triage.
    if not fast_mode:
        _verify_core_fields(
            merge_parsed(parts, []),
            parts,
            field_sources,
            pages_png,
            selected,
            pool,
            caller,
            notes,
            progress_cb,
            local_reads=local_reads,
            deadline=verify_deadline,
            confidence=confidence,
            sweep_models=_sweep_models_v,
            call_stats=call_stats,
            cross_model_hits=_unified_cm_hits,
        )

    # التسريع — ملاحظة توقيت المراحل: تشخيص صادق أين ذهب الزمن (تظهر في
    # ملاحظات الاستخراج بالواجهة) — تُبنى قبل فحص الفراغ حتى تظهر أيضًا
    # في الرحلات الفاشلة
    _t_end = _time.time()
    _sw = t_stage.get("retry", t_stage.get("verify", _t_end)) - t_stage["sweep"]
    _rt = (t_stage["verify"] - t_stage["retry"]) if "retry" in t_stage else 0.0
    _vf = _t_end - t_stage.get("verify", _t_end)
    notes.append(
        f"⏱ المراحل (ثوانٍ): إعداد+مسح {_sw:.0f} | إعادة قراءة {_rt:.0f} | "
        f"تحقق مركزي {_vf:.0f} | الإجمالي داخل الاستخراج "
        f"{_t_end - t_overall:.0f}")
    if call_stats:
        _n = len(call_stats)
        _avg = sum(s for _m, s in call_stats) / _n
        _slow_model, _slow = max(call_stats, key=lambda x: x[1])
        notes.append(
            f"⏱ النداءات: {_n} ناجحة | متوسط {_avg:.0f} ث | أبطأ "
            f"{_slow:.0f} ث ({_slow_model}) — توليد JSON بصري متسلسل، "
            "ليس نداءً فوريًا")

    if not parts:
        # Surface WHY the vision reads produced nothing — quota storms and
        # model outages must not masquerade as "unreadable pages".
        distinct = list(dict.fromkeys(failure_reasons))
        reason_txt = " | ".join(distinct[:3]) if distinct else "no reason recorded"
        raise ExtractionError(
            f"the scanned pages contained no readable financial tables. "
            f"Vision reader failures: {reason_txt}"
        )
    if __import__("os").environ.get("INDRA_DEBUG_PARTS"):
        # Post-verify parts dump: settles WHERE post-verification values
        # (e.g. the CF financing total corrected to -727,063,341) vanish.
        import json as _json
        from pathlib import Path as _Path

        _dbg = _Path(__file__).resolve().parents[2] / "logs" / "debug_parts.json"
        _dbg.parent.mkdir(parents=True, exist_ok=True)
        _dbg.write_text(
            _json.dumps(
                {"parts": [{str(y): dict(f) for y, f in p.items()} for p in parts],
                 "field_sources": field_sources},
                ensure_ascii=False, indent=1, default=str,
            ),
            encoding="utf-8",
        )
    data = merge_parsed(parts, notes,
                        captures_per_part=(caps_acc or None),
                        part_layers=["vision"] * len(parts))
    # سجل الفجوات: الصفوف ذات القراءات التي لم تطابق أي حقل — تُفرغ في
    # data (results/unmapped_labels) وتُلخص في الملاحظات؛ أي مستند
    # جديد يكشف فجوة مفرداته فورًا بدل ضياع بنوده بصمت
    if gap_sink:
        uniq: dict[str, dict] = {}
        for g in gap_sink:
            uniq.setdefault(g["label"], g)
        data.unmapped_labels = list(uniq.values())
        _top = list(uniq.items())[:8]
        _frag = "؛ ".join(
            f"{lbl[:28]} ({next(iter(g['values'].values()), 0):,.0f})"
            for lbl, g in _top)
        notes.append(
            f"📋 سجل الفجوات: {len(uniq)} بندًا بقراءات لم تُطابق أي حقل "
            f"معروف — {(_frag + (" …" if len(uniq) > 8 else ""))}. "
            "تُراجع لتوسيع مفردات المطابقة.")
    # Provenance: which page each field was captured from — surfaces in the
    # UI and lets the pipeline flag balance fields sourced from notes pages.
    data.field_sources = field_sources
    # Source-aware honesty (المهمة 1 — سد الاستثناء غير الآمن): a pure scan
    # has NO trusted text layer — every value here came from ONE model layer
    # (vision). The profile marks that BEFORE reconcile() runs, so the
    # decision log's correlated-source gate and reconcile's derived_uncertain
    # checks treat same-layer agreement as an echo, and only a SECOND
    # independent layer (local_ocr) can attest.
    from src.extraction.document_profiler import KIND_SCANNED_NO_TEXT

    data.document_profile = {
        "kind": KIND_SCANNED_NO_TEXT,
        "text_layer_trusted": False,
        "note": "pure scan — every value read by the vision model layer; "
                "same-layer agreement is an echo until an independent layer "
                "(local OCR) confirms",
    }
    # Second-layer attestation from the free local Indra OCR sweep: when
    # local_reads on a field's source page digit-confirms a captured value,
    # record it as an independent local_ocr candidate BEFORE reconcile().
    if local_reads:
        from src.extraction.local_ocr import confirms as _local_confirms

        _sel_set = set(selected)
        _order_l = max((o for cands in data.candidates.values()
                        for ys in cands.values() for _v, o in ys), default=0) + 1
        for _f, _by_year in list(data.values.items()):
            _src_pages = [p for p in field_sources.get(_f, []) if p in _sel_set]
            for _y, _v in list(_by_year.items()):
                if _v is None:
                    continue
                if any(_local_confirms(local_reads, p, _v) for p in _src_pages):
                    data.candidates.setdefault(_f, {}).setdefault(_y, []).append((_v, _order_l))
                    data.candidate_labels.setdefault(_f, {}).setdefault(_y, []).append(f"local_ocr:{_f}")
                    data.candidate_layers.setdefault(_f, {}).setdefault(_y, []).append("local_ocr")
                    data.bump_confidence(_f, _y, 2)
                    _order_l += 1
    # Confidence must reach reconcile BEFORE it runs: the tax bridge anchors
    # on a multiply-verified net income, which is only known here.
    for (field_name, year), level in confidence.items():
        data.bump_confidence(field_name, year, level)
    reconcile(data)
    # ── Neuro-Symbolic Deterministic Guardrail (Z3 SMT → AI Repair Feedback Loop) ──
    # When any formal EAS/IFRS accounting axiom fails after reconciliation,
    # Z3 extracts the minimal Unsat Core and routes ONLY the violated page/fields
    # back to Gemini Vision at 2400px. A proposed repair is ACCEPTED ONLY IF
    # re-running the formal certificate checker strictly reduces violations.
    if not fast_mode:
        _z3_feedback_repair_loop(
            data=data,
            field_sources=field_sources,
            pages_png=pages_png,
            selected=selected,
            pool=pool,
            caller=caller,
            notes=notes,
            progress_cb=progress_cb,
            deadline=deadline,
        )
    if _unified_cm_hits:
        _cm_unified_models: set[str] = set()
        _cm_unified_cnt = 0
        for (_uf, _uy), (_uval, _umodel) in _unified_cm_hits.items():
            _cur_uv = data.get(_uf, _uy)
            if _cur_uv is not None and abs(_cur_uv - _uval) <= max(1.0, 1e-6 * abs(_uval)):
                if _record_cross_model_layer(data, _uf, _uy, _cur_uv, _umodel):
                    _cm_unified_models.add(_umodel)
                    _cm_unified_cnt += 1
        if _cm_unified_cnt and notes is not None:
            notes.append(
                f"التحقق المدمج بنموذج ثانٍ مستقل ({', '.join(sorted(_cm_unified_models))}): "
                f"تم توثيق {_cm_unified_cnt} خانة محورية ضمن إعادة القراءة المركزة."
            )
    if __import__("os").environ.get("INDRA_DEBUG_PARTS"):
        import json as _json
        from pathlib import Path as _Path

        _dbg2 = _Path(__file__).resolve().parents[2] / "logs" / "debug_values.json"
        _dbg2.write_text(
            _json.dumps(
                {"values": data.values, "candidates": data.candidates},
                ensure_ascii=False, indent=1, default=str,
            ),
            encoding="utf-8",
        )
    # Focused local cell verification (المهمة 3/4 — استعادة الأدلة): free
    # local row-band reads of the non-decisive cells. Candidates only —
    # cross-layer agreement attests through the normal vote, conflicts stay
    # gated for human review. Never a silent replacement.
    _focused_local_cell_verification(data, raw, field_sources, doc_years_holder,
                                     selected, pages_png, notes)
    # ── Z3 Algebraic Checksum Attestation (التوثيق الجبري الرياضي بـ Z3) ──
    # Closed multi-term accounting identities (A1, A1b, A2, A3, A5, A5c, A6, A6b, A9, A10, A11)
    # where ALL terms were directly captured (zero tautology, zero conflicts)
    # provide a mathematically independent second verification layer (`z3_math`).
    try:
        from src.analysis.formal_verifier import (
            apply_z3_algebraic_attestation,
            recheck_derived_certainty,
        )

        apply_z3_algebraic_attestation(data, notes)
    except Exception:
        recheck_derived_certainty = None

    # ── Independent Cross-Model Vision Consensus (تحقق النموذج الثاني المستقل) ──
    # For cells STILL unverified after local OCR + Z3 algebraic attestation, ask
    # a STRICTLY DISTINCT Gemini model tier/ID to independently re-read ONLY the
    # unverified labels on up to 4 statement pages (zero leakage of Model A's
    # numbers). Digit-exact agreement records `vision_cross_model` as a second
    # independent layer; disagreements stay gated honestly for human review.
    if not fast_mode and caller is None:
        try:
            _sweep_models = [m for m, _t in (call_stats or []) if m]
            _cm_ok = _cross_model_consensus_verify(
                data=data,
                field_sources=field_sources,
                pages_png=pages_png,
                selected=selected,
                pool=pool,
                sweep_models=_sweep_models,
                notes=notes,
                progress_cb=progress_cb,
                deadline=deadline,
            )
            if _cm_ok and recheck_derived_certainty is not None:
                recheck_derived_certainty(data)
        except Exception as _cm_exc:
            if notes is not None:
                notes.append(f"Cross-model consensus skipped: {_cm_exc}")
    if not fast_mode and caller is None and not pool.has_usable_pairs():
        try:
            from src.extraction.normalizer import build_decision_log as _bdl_q

            if any(e.get("status") in ("UNVERIFIED", "CROP_ONLY") for e in _bdl_q(data)):
                quota_interrupted = True
        except Exception:
            pass
    data.extraction_quota_interrupted = quota_interrupted
    # ── Spatial shadow mode (FEATURE FLAG: SPATIAL_SHADOW=1) ──
    # Runs the spatial cell extractor on the rendered pages and RECORDS its
    # findings without touching any captured value or decision-log status
    # (the gate only fires on data.spatial_findings, which shadow never
    # sets). Rollback = unset the env var; default OFF, zero production
    # impact when unset.
    import os as _os

    # ── Spatial shadow mode (FEATURE FLAGS: SPATIAL_SHADOW=1 or
    # ENABLE_SPATIAL_EXTRACTION=1) ── records-only; never touches values or
    # decision-log statuses. Rollback = unset the env var (default OFF).
    if _os.getenv("SPATIAL_SHADOW") == "1"             or _os.getenv("ENABLE_SPATIAL_EXTRACTION") == "1":
        if caller is None:
            run_spatial_shadow(data, list(zip(selected, pages_png)), notes)
    


    # cell-crop verification حُذفت (تسريع 2026-11-13): كانت تستدعي
    # _cell_crop_png وCELL_VERIFY_PROMPT غير معرفتيهما — NameError يُبتلع
    # بصمت في except منذ جولة سابقة، فلم تعمل قط رغم ادعاء نسخة الـprompt.
    # التحقق المنازَع تغطيه الطبقة المحلية المجانية (focused local cell
    # verification) وشبكة التحقق المركزية.

    data.currency_hint = currency_holder.get("hint")
    data.company_hint = company_holder.get("name") or None
    if LOCAL_OCR_ENABLED and caller is None:
        # Notes text capture (الإيضاحات المتممة): reuse markdown ALREADY extracted
        # by the initial local_reads sweep so we never re-render or duplicate
        # 29-page Indra ONNX RAM on Streamlit Cloud!
        reused_notes = {
            p: lr.markdown
            for p, lr in (local_reads or {}).items()
            if getattr(lr, "markdown", "") and lr.markdown.strip()
        }
        if reused_notes:
            notes_pages = reused_notes
        else:
            from .local_ocr import capture_notes_text

            notes_pages = capture_notes_text(raw)
        if notes_pages:
            data.notes_text = notes_pages
            data.notes.append(
                f"Notes text captured locally for {len(notes_pages)} pages "
                "(الإيضاحات صارت قابلة للسؤال في تاب الإيضاحات)."
            )
        else:
            data.notes.append(
                "Notes text capture skipped (local OCR unavailable or failed) — "
                "the notes RAG tab needs a re-analysis."
            )
    # source-aware provenance: this whole path is MODEL-READ pixel text —
    # every value's source label (and the decision-log `source` field)
    # reflects that; the verification ladder is untouched
    from src.extraction.provenance import SOURCE_VISION_MODEL

    data.extraction_source = SOURCE_VISION_MODEL
    # v5: وحدة الطباعة على مسار الرؤية أيضًا — الترويسة المطبوعة تُقرأ من
    # نصوص صفحات Indra نفسها (كان مسار النص وحده يكشفها فعرضت TE الممسوحة
    # «مليون» بدل «مليار» — كشفه اختبار الدمج الحي)
    try:
        from src.extraction.file_parsers import detect_printed_unit

        # notes_text تُلتقط أعلى مباشرة (Indra محليًا على كل الصفحات) —
        # نصوص القوائم نفسها ضمنها فترويسة الوحدة مقروءة
        texts = [t for t in (getattr(data, "notes_text", {}) or {}).values()]
        scale, unit_note = detect_printed_unit(texts)
        data.unit_scale = scale
        data.unit_note = unit_note
        if scale != 1 and notes is not None:
            notes.append(
                f"وحدة الطباعة: {unit_note} — العرض يضرب في {scale}.")
    except Exception:
        pass  # كشف الوحدة تحسين عرض — لا يكسر الاستخراج أبدًا
    return data

# ── Focused local cell verification (المهمة 3/4) ──
import re as _re

_NUMBER_TOKENS = _re.compile(
    r"\(?\s*-?\s*(?:\d{1,3}(?:[,\s]\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*\)?%?")
FOCUSED_LOCAL_TIME_BUDGET_S = 120.0


def _focused_local_cell_verification(data, raw, field_sources, doc_years,
                                     selected, pages_png, notes,
                                     time_budget_s: float = FOCUSED_LOCAL_TIME_BUDGET_S,
                                     line_reader=None) -> None:
    """Free LOCAL cell re-reads of the non-decisive cells (المهمة 3/4 v3).

    REAL segment geometry — no text-order or char-offset assumptions:
      - one free local Indra page read returns a LineBox PER PRINTED SEGMENT
        («30/6/2024», «Total Assets», «169 497 056» each carry their own box);
      - the year-HEADER segments fix each year column's x-center;
      - a field's label segment (matched by the field's OWN alias keywords)
        defines the row's y-band; every numeric segment in that band belongs
        to the row;
      - numeric SEGMENTS chain horizontally (adjacent boxes, 1-3 digit
        groups) into magnitudes, and each magnitude goes to the NEAREST
        year column by its own box center.
    Every value lands as a local_ocr CANDIDATE carrying its bbox, page and
    render scale (الإحداثيات والمصدر والدقة محفوظة). Cross-layer agreement
    attests through the normal vote + gate; conflicts stay gated for human
    review. Never a silent replacement. Zero API; FOCUSED_LOCAL_VERIFY=0
    disables; reader injectable for tests.
    """
    import os
    import re
    import time as _time

    if os.getenv("FOCUSED_LOCAL_VERIFY", "1") != "1":
        return
    try:
        from src.config import FIELD_ALIASES
        from src.extraction.local_ocr import indra_available
        from src.extraction.normalizer import (
            _CURRENT_SECTION_FIELDS, _NONCURRENT_SECTION_FIELDS,
            _majority_vote, build_decision_log, parse_number,
        )
        from src.extraction import spatial_cells as _SC
    except Exception as exc:                       # pragma: no cover
        if notes is not None:
            notes.append(f"Focused local verification unavailable: {exc}")
        return
    if not indra_available():
        return
    years = (doc_years or {}).get("years") or []
    if not years:
        return
    try:
        decisions = build_decision_log(data)
    except Exception:
        return
    targets = {(d["field"], d["year"]) for d in decisions
               if d["status"] in ("CONFLICT", "UNVERIFIED", "CROP_ONLY")}
    if not targets:
        return
    by_page = dict(zip(selected, pages_png))
    t0 = _time.time()
    order = max((o for cands in data.candidates.values()
                 for ys in cands.values() for _v, o in ys), default=0) + 1
    appended = 0
    _fragment_map: dict = {}      # (field, year) -> [(full_v, group_segs, page)]
    from src.extraction.local_ocr import _SHARED_CONV_LOCK, get_shared_converter

    def _default_reader(png):
        conv = get_shared_converter()
        with _SHARED_CONV_LOCK:
            return _SC.read_page_lines(conv, png)

    reader = line_reader or _default_reader
    render_scale = float(os.getenv("FOCUSED_LOCAL_RENDER_SCALE", "2.0"))

    def _cx(seg):
        return (seg.box[0] + seg.box[2]) / 2.0

    def _cy(seg):
        return (seg.box[1] + seg.box[3]) / 2.0

    for page, png in list(by_page.items()):
        if _time.time() - t0 > time_budget_s:
            if notes is not None:
                notes.append("Focused local verification stopped at the "
                             "time budget (free local reads).")
            break
        # Never run focused local OCR verification of primary statement cells on trailing Note pages (p >= 15)
        # where Note schedules print additions/depreciation/sub-totals under similar labels.
        page_fields = sorted({
            f for (f, _y) in targets
            if page in (field_sources.get(f) or [])
            and (page <= 14 or f not in _CROSS_MODEL_BS_STOCK_FIELDS)
        })
        if not page_fields:
            continue
        try:
            _w, _h, segs = reader(png)
        except Exception as exc:
            if notes is not None:
                import traceback as _tb

                notes.append(f"Focused local verification: page {page} "
                             f"local read failed ({type(exc).__name__}: "
                             f"{_tb.format_exc(limit=2)[-160:]})")
            continue
        if not segs:
            continue
        # accept BOTH segment shapes: indra_ocr Line (.box/.text/.conf) and
        # spatial_cells LineBox (.x0/.y0/.x1/.y1/.text)
        class _Seg:
            __slots__ = ("box", "text", "conf")

            def __init__(self, sg):
                if hasattr(sg, "box"):
                    self.box = list(sg.box)
                else:
                    self.box = [sg.x0, sg.y0, sg.x1, sg.y1]
                self.text = sg.text or ""
                self.conf = getattr(sg, "conf", None)

        segs = [_Seg(x) for x in segs]
        # Never match Balance-Sheet stock rows (e.g. "المخزون", "العملاء", "الموردون")
        # on a pure Cash-Flow page ("التغير في: المخزون" = working-capital delta, NOT
        # ending inventory!). Prevents wrong Page-8 crops & false CONFLICT pollution.
        _pg_txt = " ".join(s.text or "" for s in segs)
        _is_cf_only_page = (
            any(m in _pg_txt for m in (
                "التدفقات النقدية", "التدفقات النقديه",
                "أنشطة التشغيل", "انشطة التشغيل", "انشطه التشغيل",
                "أنشطة الاستثمار", "انشطة الاستثمار",
            ))
            and not any(m in _pg_txt for m in (
                "المركز المالي", "إجمالي الأصول", "اجمالي الاصول",
                "الأصول المتداولة", "الاصول المتداولة",
            ))
        )
        if _is_cf_only_page:
            _bs_stocks = {
                "inventory", "accounts_receivable", "other_receivables",
                "supplier_advances", "customer_advances",
                "accounts_payable", "other_payables", "provisions",
                "fixed_assets", "cash", "current_assets", "non_current_assets",
                "total_assets", "current_liabilities", "non_current_liabilities",
                "total_liabilities", "equity", "retained_earnings", "capital",
                "long_term_debt", "long_term_notes_payable",
                "deferred_tax_liabilities", "short_term_credit_facilities",
                "current_portion_lt_debt", "current_lease_liabilities",
                "non_current_lease_liabilities", "total_debt",
            }
            page_fields = [f for f in page_fields if f not in _bs_stocks]
            if not page_fields:
                continue
        page_has_arabic_indic = any(
            re.search(r"[\u0660-\u0669\u06f0-\u06f9]", s.text or "") for s in segs
        )
        # year COLUMNS from the printed year-header segments — every header
        # segment is a column (a statement may print FOUR: 6-month and
        # 3-month periods side by side, years repeating); column ranges are
        # the midpoints between adjacent header centers
        header_cols: list[tuple[int, float]] = []
        note_cxs: list[float] = []
        for seg in segs:
            stxt = (seg.text or "").strip()
            if not stxt:
                continue
            if len(stxt) <= 16 and ("إيضاح" in stxt or "ايضاح" in stxt):
                note_cxs.append(_cx(seg))
            if len(stxt) > 36 or any(bw in stxt for bw in ("القوائم", "القواذم", "القوانم", "المنتهية", "تعتبر")):
                continue
            y = _extract_year_token(stxt)
            if y in years:
                header_cols.append((y, _cx(seg)))
        if len(header_cols) < 2 and len(years) >= 2:
            curr_hdrs = [
                seg for seg in segs
                if len((seg.text or "").strip()) <= 24
                and any(cw in (seg.text or "").lower() for cw in ("جنيه", "جنیه", "جئيه", "مصري", "مصرى"))
            ]
            paired_hdrs: list = []
            for i_h, h1 in enumerate(curr_hdrs):
                row_mates = [h1] + [
                    h2 for j_h, h2 in enumerate(curr_hdrs)
                    if j_h != i_h and abs(_cy(h1) - _cy(h2)) <= 15.0 and abs(_cx(h1) - _cx(h2)) >= 60.0
                ]
                if len(row_mates) == 2:
                    paired_hdrs = sorted(row_mates, key=lambda s: _cx(s))
                    break
            if len(paired_hdrs) == 2:
                y_old, y_new = min(years), max(years)
                header_cols = [(y_old, _cx(paired_hdrs[0])), (y_new, _cx(paired_hdrs[1]))]
        if not header_cols:
            continue
        header_cols.sort(key=lambda t: t[1])
        max_hdr_cx = max(c[1] for c in header_cols)
        note_cxs = [ncx for ncx in note_cxs if ncx > max_hdr_cx + 35.0]
        bounds = [(-1e18, None)]
        for i in range(1, len(header_cols)):
            mid = (header_cols[i - 1][1] + header_cols[i][1]) / 2.0
            bounds[-1] = (bounds[-1][0], mid)
            bounds.append((mid, None))

        def _column_of(cx: float) -> int:
            for i, (lo, hi) in enumerate(bounds):
                if lo <= cx < (hi if hi is not None else 1e18):
                    return i
            return len(bounds) - 1

        def _in_note_col(cx: float) -> bool:
            return any(abs(cx - ncx) <= 42.0 for ncx in note_cxs)

        # Statement-section context (المهمة 1): the SAME generic rules the
        # text parser uses — section-header segments («Current Liabilities»,
        # «Non Current Liabilities», …) ordered by y; a repeated same-label
        # row («Creditors and other credit balances») belongs to the section
        # header ABOVE it, so a current-section field under the non-current
        # header is a DIFFERENT printed line and never becomes a candidate.
        section_bands: list[tuple[float, str]] = []
        for sg in segs:
            t_low = (sg.text or "").strip().lower()
            if _is_number_text(t_low) or not t_low:
                continue
            sec = None
            if "non current" in t_low or "non-current" in t_low:
                if "liabilit" in t_low:
                    sec = "non-current-liabilities"
                elif "asset" in t_low:
                    sec = "non-current-assets"
            elif "current" in t_low:
                if "liabilit" in t_low:
                    sec = "current-liabilities"
                elif "asset" in t_low:
                    sec = "current-assets"
            if sec:
                section_bands.append((_cy(sg), sec))
        section_bands.sort()

        def _section_at(cy: float) -> str | None:
            cur = None
            for band_cy, sec in section_bands:
                if band_cy <= cy:
                    cur = sec
                else:
                    break
            return cur

        # label segments for the page's target fields (ALWAYS enforce accounting vetoes!)
        from src.extraction.normalizer import (
            _FIELD_NEGATIVE_PATTERNS as _FLCV_NEG,
            _GLOBAL_NEGATIVE_PATTERNS as _FLCV_GNEG,
            match_field as _match_fld,
            normalize_label as _norm_lbl,
        )
        for seg in segs:
            text = (seg.text or "").strip()
            if not text or _is_number_text(text):
                continue
            norm_seg = _norm_lbl(text)
            if any(gp in norm_seg for gp in _FLCV_GNEG):
                continue
            matched_fld = _match_fld(text)
            if matched_fld is not None:
                if matched_fld not in page_fields:
                    continue  # strictly belonging to a different canonical field!
                fld = matched_fld
            else:
                # Only match page_fields if NONE of that field's negative vetoes hit
                fld = None
                for cand_f in page_fields:
                    neg_p = _FLCV_NEG.get(cand_f, ())
                    if neg_p and any(_norm_lbl(p) in norm_seg for p in neg_p):
                        continue
                    if any(
                        _norm_lbl(k) in norm_seg
                        for k in FIELD_ALIASES.get(cand_f, [])
                        if len(_norm_lbl(k)) >= 5
                    ):
                        fld = cand_f
                        break
            if fld is None:
                continue
            row_section = _section_at(_cy(seg))
            if row_section == "non-current-liabilities"                     and fld in _CURRENT_SECTION_FIELDS:
                continue        # a different printed line (non-current slice)
            if row_section == "current-liabilities"                     and fld in _NONCURRENT_SECTION_FIELDS:
                continue
            band_cy, band_h = _cy(seg), max(seg.box[3] - seg.box[1], 4.0)
            # tight ROW bounds (المهمة: حدود الصف): the label's own printed
            # line only — a ±1.5×h band swallowed NEIGHBORING rows on the
            # ~20px-pitch TE scan and mixed their numbers into the chain
            row_band_segs = [
                sg for sg in segs
                if sg is not seg and not _in_note_col(_cx(sg))
                and abs(_cy(sg) - band_cy) <= band_h * 0.75 + 3.0
            ]
            # Geometric cell bounding boxes for RTL value columns (even if CRNN
            # garbled Arabic-Indic digits into Latin letters, the detector box
            # is the exact physical cell crop on the page)
            if _cx(seg) > max_hdr_cx + 40.0:
                col_cell_segs: dict[int, list] = {}
                for sg in row_band_segs:
                    st_sg = (sg.text or "").strip()
                    if (st_sg and sg.box[2] <= seg.box[0] - 10.0
                            and any(c.isdigit() or c in ",.()٠١٢٣٤٥٦٧٨٩" for c in st_sg)):
                        col_cell_segs.setdefault(_column_of(_cx(sg)), []).append(sg)
                for col_i, c_segs in sorted(col_cell_segs.items()):
                    year_c = header_cols[col_i][0]
                    if (fld, year_c) not in targets:
                        continue
                    ubox_c = [
                        round(min(x.box[0] for x in c_segs), 1),
                        round(min(x.box[1] for x in c_segs), 1),
                        round(max(x.box[2] for x in c_segs), 1),
                        round(max(x.box[3] for x in c_segs), 1),
                    ]
                    existing_bbs = data.candidate_bbox.setdefault(fld, {}).setdefault(year_c, [])
                    if not any(b.get("page") == page and b.get("bbox_px") == ubox_c for b in existing_bbs):
                        existing_bbs.append({"page": page, "bbox_px": ubox_c, "render_scale": render_scale})
            row_nums = [sg for sg in row_band_segs if _is_number_text(sg.text or "")]
            if not row_nums:
                continue
            # chain horizontally-adjacent fragments WITHIN ONE COLUMN, then
            # one magnitude per column (المهمة 3: أعمدة مالية هندسية)
            row_nums.sort(key=lambda sg: sg.box[0])
            col_nums: dict[int, list] = {}
            for sg in row_nums:
                col_nums.setdefault(_column_of(_cx(sg)), []).append(sg)
            mags: list[tuple[float, int, float, list]] = []   # (value, col, cx, group)
            for col_i, col_segs in sorted(col_nums.items()):
                cur: list = []
                for sg in col_segs + [None]:
                    if sg is not None and cur and _chains_box(cur[-1], sg):
                        cur.append(sg)
                    else:
                        if cur:
                            joined = " ".join(x.text.strip() for x in cur)
                            # Skip CRNN Latin-garbled or dot-for-zero garbled reads as numeric candidates
                            has_latin_garble = bool(re.search(r"[A-Za-z]", joined))
                            has_ascii_on_arabic_page = bool(
                                page_has_arabic_indic and re.search(r"[0-9]", joined)
                            )
                            has_dot_comma_garble = bool(
                                ("," in joined or "٬" in joined or "،" in joined)
                                and ("." in joined or "٫" in joined)
                                and re.search(r"[.٫]\s*\d*[,٬،]|[,٬،]\s*\d*[.٫]", joined)
                            )
                            if (not has_latin_garble
                                    and not has_ascii_on_arabic_page
                                    and not has_dot_comma_garble):
                                v = parse_number(joined)
                                if v is not None:
                                    mags.append((v, col_i, sum(_cx(x) for x in cur)
                                                 / len(cur), list(cur)))
                        cur = [sg] if sg is not None else []
            # drop leading note-REFERENCE magnitudes per column: «(19)» before
            # the real year values is a note number, never a statement amount
            for col_i in list(col_nums):
                col_mags = [m for m in mags if m[1] == col_i]
                if len(col_mags) > 1 and abs(col_mags[0][0]) <= 999:
                    mags = [m for m in mags if m is not col_mags[0]]
            for v, col_i, cx, grp in mags:
                year = header_cols[col_i][0]
                if (fld, year) not in targets:
                    continue
                # the provenance bbox is the VALUE segment's own box (the
                # union of the chained group when fragments were joined)
                ubox = [round(min(x.box[0] for x in grp), 1),
                        round(min(x.box[1] for x in grp), 1),
                        round(max(x.box[2] for x in grp), 1),
                        round(max(x.box[3] for x in grp), 1)]
                data.candidates.setdefault(fld, {}).setdefault(year, []) \
                    .append((v, order))
                data.candidate_labels.setdefault(fld, {}).setdefault(year, []) \
                    .append(text[:48])
                data.candidate_layers.setdefault(fld, {}).setdefault(year, []) \
                    .append("local_ocr")
                existing_bbs = data.candidate_bbox.setdefault(fld, {}).setdefault(year, [])
                if not any(b.get("page") == page and b.get("bbox_px") == ubox for b in existing_bbs):
                    existing_bbs.append({"page": page,
                                         "bbox_px": ubox,
                                         "render_scale": render_scale})
                if len(grp) > 1:
                    _fragment_map.setdefault((fld, year), []).append(
                        (v, list(grp), page))
                order += 1
                appended += 1
    # Fragment-superseding selection (المهمة: تصحيح اختيار المرشح بهندسة
    # الصف — لا GT): when a cell's captured value is EXACTLY one FRAGMENT
    # of a chained magnitude the pass read on the SAME page row (an OCR
    # split like «10» + «272 954»), the complete magnitude supersedes the
    # fragment. The fragment stays in candidates/replaced_values — nothing
    # is hidden, and the cell remains on the normal verification ladder.
    superseded = 0
    for (fld, year), info in list(_fragment_map.items()):
        base_v = data.values.get(fld, {}).get(year)
        if base_v is None:
            continue
        for full_v, frags, page in info:
            frag_vals = []
            for f in frags:
                try:
                    frag_vals.append(abs(parse_number(
                        f.text.strip().replace(" ", "") or "0") or 0))
                except Exception:
                    frag_vals.append(0.0)
            if any(abs(base_v - fv) <= max(1.0, 1e-9 * max(abs(base_v), 1))
                   for fv in frag_vals) and abs(base_v - full_v) > 1.0:
                data.replaced_values = getattr(data, "replaced_values", {})
                data.replaced_values.setdefault((fld, year), []).append(base_v)
                data.values.setdefault(fld, {})[year] = full_v
                data.candidates.setdefault(fld, {}).setdefault(year, []) \
                    .append((full_v, 10 ** 9))
                data.notes.append(
                    f"Row-geometry selection: '{fld}' in {year} — the "
                    f"captured {base_v:,.0f} is a FRAGMENT of the printed "
                    f"magnitude {full_v:,.0f} (segments chained by box "
                    f"adjacency on page {page}); fragment preserved in "
                    "candidates.")
                superseded += 1
                break
    if superseded and notes is not None:
        notes.append(f"Focused local verification: {superseded} fragment "
                     "captures superseded by their complete row magnitudes "
                     "(geometry-based selection).")
    if appended:
        if notes is not None:
            notes.append(
                f"Focused local verification: {appended} local_ocr "
                "candidates from geometric segment reads (zero API) — "
                "cross-layer agreement attests, conflicts stay gated for "
                "human review.")
        _majority_vote(data)


_AR_DIGITS_TRANS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫٬،", "01234567890123456789., ")


def _is_number_text(text: str) -> bool:
    import re as _re

    norm = (text or "").translate(_AR_DIGITS_TRANS).strip()
    return bool(_re.fullmatch(r"[\d,.()\s\-]+", norm)
                and _re.search(r"\d", norm))


def _chains_box(prev_seg, next_seg) -> bool:
    """Horizontal chaining: same row, adjacent boxes — 1-3 digit fragments
    («169» «497» «056») AND an OCR-split magnitude whose tail kept its
    groups («10» + «272 954» = «10 272 954»). The JOINED string must parse
    as a valid magnitude (checked by the caller)."""
    gap = next_seg.box[0] - prev_seg.box[2]
    h = max(prev_seg.box[3] - prev_seg.box[1], 4.0)
    if gap > h * 1.6 or gap < -h * 0.5:
        return False
    pt = (prev_seg.text or "").translate(_AR_DIGITS_TRANS).strip()
    nt = (next_seg.text or "").translate(_AR_DIGITS_TRANS).strip()
    import re as _re

    return bool(_re.fullmatch(r"[\d ]+", pt) and _re.fullmatch(r"[\d ]+", nt))


def _chains(prev_tok: str, next_tok: str) -> bool:
    """A 3-digit token CHAINS the running magnitude when the previous token
    ended a group and this one is exactly 3 digits («169 497 056»); a
    1-3 digit token starts a NEW magnitude after a comma-grouped one."""
    return bool(_re.fullmatch(r"\d{3}", next_tok)) and         not (_re.search(r"[,.]", prev_tok) and
             _re.fullmatch(r"\d{1,3}", prev_tok) and
             len(_re.sub(r"\D", "", prev_tok)) <= 3)


def _extract_year_token(tok: str) -> int | None:
    norm = (tok or "").translate(_AR_DIGITS_TRANS)
    m = _re.search(r"(?:19|20)\d{2}", norm)
    return int(m.group(0)) if m else None




def _absorb_semantic_page(
    page: dict,
    years: list[int],
    chunk: list[int],
    parts: list,
    ok_pages: set,
    field_sources: dict[str, list[int]],
    gap_sink: list | None,
    caps_acc: list | None,
    notes: list[str],
) -> None:
    """امتصاص صفوف الشكل الدلالي: {label, field, values, conf} —
    الموديل يصنف من المفردات المغلقة والـregex يعمل مُصححًا متقاطعًا:
    الاتفاق يقوى، والاختلاف يُفصح عنه (مصنّفان مستقلان)."""
    from src.config import FIELD_ALIASES
    from src.extraction.normalizer import (
        _FIELD_NEGATIVE_PATTERNS,
        match_field,
        normalize_label,
    )

    page_parts: dict[int, dict[str, float]] = {}
    page_caps: list[dict] = []
    # Detect Cash-Flow Statement page numbers inside this semantic response so
    # working-capital change rows («المخزون / العملاء / الموردون» under «التغير في:»)
    # on a Cash Flow page NEVER contaminate Balance Sheet ending balances.
    _BS_STOCK_FIELDS = {
        "inventory", "accounts_receivable", "accounts_payable", "cash",
        "total_assets", "current_assets", "total_liabilities",
        "current_liabilities", "equity", "fixed_assets",
        "long_term_debt", "short_term_debt", "short_term_credit_facilities",
        "current_portion_lt_debt", "non_current_lease_liabilities",
        "current_lease_liabilities",
    }
    _CF_MARKERS = ("operating_cash_flow", "investing_cash_flow", "financing_cash_flow", "capex")
    cf_page_nos: set = set()
    bs_page_nos: set = set()
    for _r in page.get("rows") or []:
        if not isinstance(_r, dict):
            continue
        _pno = _r.get("page_no")
        _rf = _r.get("field")
        _rl = normalize_label(str(_r.get("label") or ""))
        if _rf in _CF_MARKERS or "انشطه التشغيل" in _rl or "الانشطه التشغيليه" in _rl or "التدفقات النقديه" in _rl:
            cf_page_nos.add(_pno)
        if _rf in ("total_assets", "equity"):
            bs_page_nos.add(_pno)
    pure_cf_page_nos = cf_page_nos - bs_page_nos

    for row in page.get("rows") or []:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or "").strip()
        norm_lbl = normalize_label(label)
        field = row.get("field")
        values = row.get("values") or {}
        if field not in FIELD_ALIASES:
            field = None
        if field in _BS_STOCK_FIELDS and row.get("page_no") in pure_cf_page_nos:
            continue  # Working-capital Δ or CF ending cash — never a BS balance
        # خريطة مفاتيح القيم → السنة: الموديل يرجع y1/y2 (مفاتيح القالب)
        # أو السنوات أو المواضع — وyears قد تأتي معكوسة [الحالية، السابقة]
        # فالمفتاح y1 يُحل موضعيًا على years وليس بالفرض
        key_map: dict = {}
        for i, y in enumerate(years):
            key_map[f"y{i + 1}"] = int(y)
            key_map[str(y)] = int(y)
            key_map[int(y)] = int(y)
            key_map[i + 1] = int(y)
            key_map[str(i + 1)] = int(y)
        row_vals: dict[int, float] = {}
        for k, v in (values or {}).items():
            yy = key_map.get(k, key_map.get(str(k)))
            if yy is not None and isinstance(v, (int, float)):
                row_vals[int(yy)] = float(v)
        if field is None:
            # Check newly added OpEx/AP canonical fields that the semantic prompt may leave null
            fallback_field = match_field(label)
            if fallback_field in ("admin_expenses", "other_operating_expenses", "other_operating_income"):
                field = fallback_field
            else:
                # الصف بلا تصنيف — سجل الفجوات إن كان يحمل أرقامًا
                if row_vals and gap_sink is not None:
                    gap_sink.append({"label": label[:120], "values": row_vals})
                continue
        # Enforce hard accounting vetoes even on semantic model tags:
        # 1) Pre-interest CF subtotal («النقدية الناتجة من أنشطة التشغيل» without «صافي»)
        #    must NEVER hijack operating_cash_flow (2023 Ezz Steel: 1,794M vs 1,214M).
        if (
            field == "operating_cash_flow"
            and "صافي" not in norm_lbl
            and ("انشطه التشغيل" in norm_lbl or "الانشطه التشغيليه" in norm_lbl)
        ):
            continue
        # 2) Negative-pattern vetoes (e.g. CF loan repayments never feed long_term_debt;
        #    ECL/advances/related-party rows never feed AP/AR).
        neg_pats = _FIELD_NEGATIVE_PATTERNS.get(field)
        if neg_pats and any(normalize_label(p) in norm_lbl for p in neg_pats):
            continue
        # مُصحح متقاطع: الـregex ضد تصنيف الموديل
        regex_field = match_field(label)
        if regex_field is not None and regex_field != field:
            notes.append(
                f"⚠ Semantic/regex disagreement on «{label[:40]}»: "
                f"model={field}, regex={regex_field} — captured under "
                "the model's field; both go through the gate."
            )
        for y, v in list(row_vals.items()):
            # حاجز الحجم الهيكلي: مبلغ قائمة لا يكون 0-3 جنيهًا لشركة
            # بإيرادات المليارات — القيم الصغيرة العشرية الصحيحة هي
            # تسرب بنية من الموديل (فهرس عمود/عدد أعمدة) ⇒ unreadable
            if float(v).is_integer() and 0 <= v <= 3:
                row_vals.pop(y)
                continue
        for y, v in row_vals.items():
            page_parts.setdefault(y, {}).setdefault(field, v)
            field_sources.setdefault(field, []).extend(chunk)
            page_caps.append({
                "field": field, "year": y, "value": v,
                "label_text": label[:120],
                "raw_printed": "", "print_convention": "unknown",
                "row": None, "col": None, "transposed": False,
            })

    _vals = [v for yf in page_parts.values() for v in yf.values()]
    if page_parts and _vals and all(
        float(v).is_integer() and 0 <= v <= 3 for v in _vals):
        notes.append(
            f"⚠ Degenerate semantic page dropped (positions instead of "
            f"amounts on pages {chunk}) — the verify layers cover it.")
        return
    if page_parts:
        parts.append(page_parts)
        ok_pages.update(chunk)
        if caps_acc is not None:
            caps_acc.append(page_caps)


def _absorb_batch(
    batch_pages: list[dict],
    chunk: list[int],
    parts: list,
    ok_pages: set,
    notes: list[str],
    currency_holder: dict,
    doc_years_holder: dict,
    field_sources: dict[str, list[int]],
    gap_sink: list | None = None,
    caps_acc: list | None = None,
) -> None:
    """Merge one batch's parsed pages into the accumulators.

    A page whose header shows no years (common for cash-flow statements)
    inherits the document's years when the row value-count matches.
    """
    for page in batch_pages:
        # الشكل الدلالي v3: الصفوف قواميس {label, field, values}
        if page.get("rows") and isinstance(page["rows"][0], dict):
            years0 = page["years"]
            if len(years0) < 2 and doc_years_holder.get("years"):
                years0 = doc_years_holder["years"]
            if len(years0) < 2:
                continue
            _absorb_semantic_page(
                page, years0, chunk, parts, ok_pages, field_sources,
                gap_sink, caps_acc, notes)
            if not currency_holder.get("hint") and page.get("currency"):
                hint = _currency_hint(page["currency"])
                if hint:
                    currency_holder["hint"] = hint
                    notes.append(f"Currency detected from the document: {hint}")
            continue
        if not currency_holder.get("hint") and page.get("currency"):
            hint = _currency_hint(page["currency"])
            if hint:
                currency_holder["hint"] = hint
                notes.append(f"Currency detected from the document: {hint}")
        years = page["years"]
        if len(years) >= 2 and doc_years_holder.get("years") is None:
            doc_years_holder["years"] = years  # first dated page anchors the doc
        if len(years) < 2 and doc_years_holder.get("years"):
            years = doc_years_holder["years"]
        if len(years) < 2:
            continue
        rows = [row[: 1 + len(years)] + [None] * (1 + len(years) - len(row)) for row in page["rows"]]
        if not rows:
            continue
        frame = pd.DataFrame(rows, columns=["Item"] + years, dtype=object)
        try:
            parsed = parse_table(frame, gap_sink=gap_sink)
            # كاشف الصفحة المنحلة (عز 2023): عمود مشوه يجعل الموديل يرجع
            # مواضع الأعمدة (1/2) بدل المبالغ لكل صفوف الصفحة — صفحة كل
            # قيمها أعداد صحيحة ≤3 = تسرب بنية ⇒ تُسقط كاملة، ومراحل
            # التحقق وإعادة القراءة تعوضها بدل أن تسمم ~20 حقلاً
            _vals = [v for yf in parsed.values() for v in yf.values()]
            if parsed and _vals and all(
                float(v).is_integer() and 0 <= v <= 3 for v in _vals):
                notes.append(
                    f"⚠ Degenerate page read dropped (positions 1/2 instead "
                    f"of amounts on pages {chunk}) — the verify layers and "
                    "re-reads cover it.")
                continue
            if parsed:
                # Enforce BOTH Balance Sheet grand anchors (`total_assets` AND `equity`)
                # so Note pages mentioning `equity` alone (like Note 20 Treasury Shares)
                # still get isolated as Note schedules and NEVER overwrite primary BS lines!
                _cf_k = {"operating_cash_flow", "investing_cash_flow", "financing_cash_flow", "capex"}
                _bs_anchor = {"total_assets", "equity"}
                _bs_strip = {
                    "inventory", "accounts_receivable", "other_receivables",
                    "supplier_advances", "customer_advances",
                    "accounts_payable", "other_payables", "provisions", "cash",
                    "total_assets", "current_assets", "total_liabilities",
                    "current_liabilities", "equity", "fixed_assets",
                    "long_term_debt", "long_term_notes_payable",
                    "deferred_tax_liabilities", "short_term_debt",
                    "short_term_credit_facilities",
                    "current_portion_lt_debt", "non_current_lease_liabilities",
                    "current_lease_liabilities",
                    "capital", "treasury_shares", "reserves", "asset_revaluation_reserve",
                    "projects_under_construction", "investments_in_subsidiaries",
                    "other_investments", "deferred_tax_assets",
                }
                _all_f = {f for ym in parsed.values() for f in ym}
                _has_full_bs = _bs_anchor.issubset(_all_f)
                _is_note_subtable = (chunk[0] >= 11) and not _has_full_bs
                _existing_bs = {
                    bf for bf in _bs_strip
                    if any(bf in ym for p in parts for ym in p.values())
                }
                if (_all_f & _cf_k) and not _has_full_bs:
                    for ym in parsed.values():
                        for bf in list(ym.keys()):
                            if bf in _bs_strip:
                                ym.pop(bf, None)
                elif _is_note_subtable and _existing_bs:
                    for ym in parsed.values():
                        for bf in list(ym.keys()):
                            if bf in _existing_bs:
                                ym.pop(bf, None)
                # Drop trailing page numbers when trailing chunks carry nothing new after filtering
                if any(ym for ym in parsed.values()):
                    parts.append(parsed)
                    ok_pages.update(chunk)
                    for year_fields in parsed.values():
                        for field in year_fields:
                            field_sources.setdefault(field, []).extend(chunk)
        except Exception as exc:  # one bad page must not kill the run
            notes.append(f"Vision page skipped ({exc}).")


Z3_REPAIR_PROMPT = """A formal accounting verifier (Z3 SMT Solver) detected an arithmetic
inconsistency on this scanned ARABIC financial statement page for fiscal year {year}:
{violation_summary}

Re-read ONLY the following fields from the printed table on THIS page, digit-by-digit,
for EACH year column shown (parentheses = negative; copy exact printed digits, NEVER guess or compute):
{field_bullets}

Return ONLY JSON:
{{"years": [{years_hint}], "values": {{{json_template}}}}}
Use null if a field is NOT printed on this page or is printed as a dash ("---" / "—", NEVER 0).
Inspect BOTH attached high-resolution images digit-by-digit — watch Arabic digits ٦ vs ١, ٢ vs ٧, ٠ vs ٥, and exact zero count (e.g. hundreds of millions vs tens of millions).
"""


def _z3_feedback_repair_loop(
    data: FinancialData,
    field_sources: dict[str, list[int]],
    pages_png: list[bytes],
    selected: list[int],
    pool: APIKeyPool,
    caller=None,
    notes: list[str] | None = None,
    progress_cb=None,
    deadline: float | None = None,
    max_rounds: int = 6,
) -> list[dict]:
    """Deterministic Guardrail -> AI Repair Feedback Loop (Certificate-Checked).

    1. Runs the Z3 Formal Verifier on reconciled `data.values`.
    2. When `failed_axioms > 0`, takes Z3's minimal Unsat-Core suspect fields
       and asks Gemini Vision to independently re-read ONLY those fields at
       2400px dual-variant resolution (NEVER telling Gemini the Z3 implied number).
    3. Re-runs Z3 on a candidate copy: accepts the repair ONLY IF the certificate
       strictly reduces violations (or slashes the violated residual >80% with zero
       new violations). Otherwise rejects and records the attempt honestly.
    """
    import copy as _copy
    import time as _time
    from src.analysis.formal_verifier import (
        _FIELD_AR,
        RepairAttempt,
        verify_financial_statements,
    )

    notes = notes if notes is not None else []
    repairs: list[dict] = []
    years = sorted(y for y in (data.years or []) if isinstance(y, int))
    if not years or not selected:
        data.formal_repairs = repairs
        return repairs

    cert = verify_financial_statements(
        data.values, years=years, tolerance=1e-5, include_policy_theorems=False,
        integer_tol=5.0,
    )
    if cert.failed_axioms == 0 or not cert.fault_diagnoses:
        data.formal_repairs = repairs
        return repairs

    selected_set = set(selected)
    tried_targets: set[tuple] = set()

    for round_no in range(1, max_rounds + 1):
        if cert.failed_axioms == 0 or not cert.fault_diagnoses:
            break
        if deadline is not None and _time.time() > deadline - 15:
            notes.append("Z3 feedback repair stopped — time budget nearly exhausted.")
            break
        if caller is None and not pool.has_usable_pairs():
            break

        # Pick first untried (year, statement_hint, violated_axiom_tuple) diagnosis
        diag = None
        violated_y = []
        target_key = None
        for d in cert.fault_diagnoses:
            d_ax_ids = set(d.violated_axioms or [])
            vy_stmt = [
                ax for ax in cert.axioms
                if ax.year == d.year and ax.status == "VIOLATED"
                and (not d_ax_ids or ax.axiom_id in d_ax_ids)
            ]
            vy = vy_stmt or [ax for ax in cert.axioms if ax.year == d.year and ax.status == "VIOLATED"]
            tkey = (d.year, d.statement_hint, tuple(sorted(ax.axiom_id for ax in vy)))
            if tkey not in tried_targets:
                diag = d
                violated_y = vy
                target_key = tkey
                break
        if diag is None or target_key is None:
            break
        tried_targets.add(target_key)

        def _is_verified_cell(fld: str) -> bool:
            conf_v = data.confidence.get(fld, {}).get(diag.year, 0) if hasattr(data, "confidence") else 0
            lyrs_v = set((data.candidate_layers.get(fld, {}) or {}).get(diag.year, []) or [])
            return conf_v >= 2 or len(lyrs_v) >= 2

        stmt_suspects: list[str] = []
        for d in cert.fault_diagnoses:
            if d.year == diag.year and d.statement_hint == diag.statement_hint:
                if d.suspect_field not in stmt_suspects:
                    stmt_suspects.append(d.suspect_field)
        # Prioritize unverified/conflicting fields first, both in counterfactual suspects and axiom peers
        stmt_suspects.sort(key=lambda fld: (1 if _is_verified_cell(fld) else 0,))
        target_fields: list[str] = stmt_suspects[:6]
        unverified_cand: list[str] = []
        verified_cand: list[str] = []
        for ax in violated_y:
            for f in ax.fields:
                if f in target_fields or f in unverified_cand or f in verified_cand:
                    continue
                if _is_verified_cell(f):
                    verified_cand.append(f)
                else:
                    unverified_cand.append(f)
        for f in unverified_cand + verified_cand:
            if len(target_fields) >= 6:
                break
            target_fields.append(f)
        # Balance-sheet axioms A1 (TL+E=TA) and A2 (CA+NCA=TA) are coupled on the same page:
        # include coupled totals so a paired single-digit slip (e.g. CA & TA both off by 10 EGP)
        # can be repaired together in one 2400px read without trading an A1 error for an A2 error.
        if diag.statement_hint == "balance_sheet" and "total_assets" in target_fields:
            for bf in ("current_assets", "non_current_assets", "current_liabilities", "non_current_liabilities"):
                if bf in data.values and diag.year in data.values[bf] and bf not in target_fields and len(target_fields) < 7:
                    target_fields.append(bf)
        if not target_fields:
            break

        # Locate the primary statement page (prefer lowest page number <= 10)
        cand_pages: list[int] = []
        for f in target_fields:
            for p in field_sources.get(f, []):
                if p in selected_set and p not in cand_pages:
                    cand_pages.append(p)
        if not cand_pages:
            # Fallback to canonical primary pages
            fallback_p = {"balance_sheet": 5, "income_statement": 6, "cash_flow": 9}.get(diag.statement_hint, 5)
            if fallback_p in selected_set:
                cand_pages.append(fallback_p)
        if not cand_pages:
            continue
        page_number = min(cand_pages)

        violation_summary = "\n".join(
            f"- {ax.name_en} ({ax.formula}): residual = {ax.residual:+,.0f}"
            for ax in violated_y[:3]
        )
        field_bullets = "\n".join(
            f"- {f} ({_FIELD_AR.get(f, f)})" for f in target_fields
        )
        years_hint = ", ".join(str(y) for y in years[-2:])
        json_template = ", ".join(f'"{f}": [v1, v2]' for f in target_fields)
        prompt = Z3_REPAIR_PROMPT.format(
            year=diag.year,
            violation_summary=violation_summary,
            field_bullets=field_bullets,
            years_hint=years_hint,
            json_template=json_template,
        )

        if progress_cb:
            progress_cb(
                f"🛡️ حلقة التصحيح الرسمي (Z3 — جولة {round_no}): إعادة فحص صفحة {page_number}…"
            )

        try:
            src_png = pages_png[selected.index(page_number)]
            img = preprocess_image(src_png, max_side=3000, denoise=False)
            img_bin = preprocess_image(src_png, max_side=2400, binarize=True, denoise=False)
            if caller is not None:
                raw_text = caller("k", "m", prompt, [img, img_bin])
            else:
                raw_text = _call_with_rotation(pool, prompt, [img, img_bin])
            parsed_json = _loads_relaxed(raw_text)
        except Exception as exc:
            notes.append(f"Z3 repair round {round_no} (page {page_number}) skipped: {exc}")
            continue

        resp_years = [extract_year(y) for y in (parsed_json.get("years") or [])]
        resp_years = [y for y in resp_years if y]
        if not resp_years:
            resp_years = list(years[-2:])
        vals_block = parsed_json.get("values") or parsed_json.get("totals") or {}

        proposed: dict[tuple[str, int], float] = {}
        for f, arr in (vals_block.items() if isinstance(vals_block, dict) else []):
            if f not in target_fields or not isinstance(arr, list):
                continue
            for idx, raw_v in enumerate(arr):
                if idx >= len(resp_years):
                    break
                num = parse_number(raw_v)
                if num is None:
                    continue
                if float(num).is_integer() and 0 <= num <= 3:
                    continue
                proposed[(f, resp_years[idx])] = float(num)

        if not proposed:
            notes.append(
                f"ℹ حلقة التصحيح بـ Z3 (ص{page_number}): لم تعد قراءة قابلة للتحقق للحقول المستهدفة."
            )
            continue

        # Build candidate values and verify via Z3 Certificate Checker
        cand_values = _copy.deepcopy(data.values)
        prev_snap: dict[str, float | None] = {}
        prop_snap: dict[str, float] = {}
        for (f, y), new_v in proposed.items():
            if y != diag.year:
                continue
            old_v = data.get(f, y)
            if old_v is not None and abs(new_v - old_v) < 1.0:
                continue
            prev_snap[f] = old_v
            prop_snap[f] = new_v
            cand_values.setdefault(f, {})[y] = new_v

        if not prop_snap:
            notes.append(
                f"ℹ حلقة التصحيح بـ Z3 (ص{page_number}): إعادة القراءة كررت نفس القيمة المختلة "
                f"({diag.suspect_field} {diag.year}) — أُبقي التحذير في الشهادة الرسمية."
            )
            continue

        # Evaluate full bundle AND minimal subsets (sizes 1..3) so one noisy sibling
        # read in the same JSON reply never forces Z3 to reject an exact 2400px fix
        # (e.g. TA + CA exact while equity had a 1-digit slip in the same call).
        import itertools as _it

        old_res_sum = sum(abs(ax.residual or 0.0) for ax in cert.axioms if ax.status == "VIOLATED")
        prop_keys = list(prop_snap.keys())
        candidate_subsets: list[tuple[str, ...]] = [tuple(prop_keys)]
        if len(prop_keys) > 1:
            for r in range(1, min(len(prop_keys), 4)):
                for sub in _it.combinations(prop_keys, r):
                    if len(sub) < len(prop_keys):
                        candidate_subsets.append(sub)

        full_cert = verify_financial_statements(
            cand_values, years=years, tolerance=1e-5, include_policy_theorems=False,
            integer_tol=5.0,
        )
        best_choice = None  # ((failed_axioms, res_sum, subset_len), sub_keys, sub_cert)
        for sub in candidate_subsets:
            if len(sub) == len(prop_keys):
                sub_cert = full_cert
            else:
                sub_vals = _copy.deepcopy(data.values)
                for sf in sub:
                    sub_vals.setdefault(sf, {})[diag.year] = prop_snap[sf]
                sub_cert = verify_financial_statements(
                    sub_vals, years=years, tolerance=1e-5, include_policy_theorems=False,
                    integer_tol=5.0,
                )
            sub_res = sum(abs(ax.residual or 0.0) for ax in sub_cert.axioms if ax.status == "VIOLATED")
            sub_ok = (
                sub_cert.failed_axioms < cert.failed_axioms
                or (
                    sub_cert.failed_axioms == cert.failed_axioms
                    and old_res_sum > 0
                    and sub_res < 0.2 * old_res_sum
                )
            )
            if sub_ok:
                rank = (sub_cert.failed_axioms, sub_res, len(sub))
                if best_choice is None or rank < best_choice[0]:
                    best_choice = (rank, sub, sub_cert)

        if best_choice is not None:
            _, best_sub, new_cert = best_choice
            prop_snap = {f: prop_snap[f] for f in best_sub}
            prev_snap = {f: prev_snap[f] for f in best_sub}
            accepted = True
        else:
            new_cert = full_cert
            accepted = False

        broken_before = cert.failed_axioms
        if accepted:
            for f, new_v in prop_snap.items():
                old_v = prev_snap.get(f)
                if old_v is not None:
                    data.replaced_values = getattr(data, "replaced_values", {})
                    data.replaced_values.setdefault((f, diag.year), []).append(old_v)
                data.values.setdefault(f, {})[diag.year] = new_v
                # Replace stale majority candidates so downstream reconcile/attestation never reverts to broken OCR!
                data.candidates.setdefault(f, {})[diag.year] = [(new_v, 0)]
                data.candidate_layers.setdefault(f, {})[diag.year] = ["vision"]
                data.candidate_labels.setdefault(f, {})[diag.year] = [f"z3_repair:{f}"]
                if (f, diag.year) in getattr(data, "vote_outcomes", {}):
                    data.vote_outcomes[(f, diag.year)]["winner"] = new_v
            reconcile(data)
            reason_ar = (
                f"تم قبول التصحيح بشهادة Z3 (الانتهاكات انخفضت من {broken_before} "
                f"إلى {new_cert.failed_axioms}): "
                + "، ".join(
                    f"{_FIELD_AR.get(f, f)} ({prev_snap.get(f):,.0f} → {v:,.0f})"
                    if prev_snap.get(f) is not None else f"{_FIELD_AR.get(f, f)} (→ {v:,.0f})"
                    for f, v in prop_snap.items()
                )
            )
            notes.append(f"✓ حلقة التصحيح بـ Z3 (ص{page_number}): {reason_ar}")
            cert = verify_financial_statements(
                data.values, years=years, tolerance=1e-5, include_policy_theorems=False,
                integer_tol=5.0,
            )
        else:
            reason_ar = (
                f"رفض المُدقّق Z3 القراءة المقترحة (الانتهاكات بقيت {new_cert.failed_axioms} "
                f"مقابل {broken_before}) — تم الإبقاء على القراءة الأصلية بصدق."
            )
            notes.append(f"ℹ حلقة التصحيح بـ Z3 (ص{page_number}): {reason_ar}")

        repairs.append(RepairAttempt(
            round_no=round_no,
            year=diag.year,
            target_fields=list(prop_snap.keys()),
            page_number=page_number,
            broken_axioms_before=broken_before,
            broken_axioms_after=new_cert.failed_axioms,
            proposed_values=prop_snap,
            previous_values=prev_snap,
            accepted=accepted,
            reason_ar=reason_ar,
        ).to_dict())

    data.formal_repairs = repairs
    return repairs


CROSS_MODEL_VERIFY_PROMPT = """You are an independent second auditor reading a scanned ARABIC financial statement page.
Read ONLY the exact printed numbers on THIS page for each requested line item below,
for EACH year column shown (parentheses = negative; copy digits character-by-character,
NEVER compute, estimate, or copy values from a different row):
{field_bullets}

Strict rules:
- For Balance-Sheet stock items (inventory, accounts_receivable, accounts_payable, cash,
  fixed_assets, debt), read ONLY from a Balance Sheet (قائمة المركز المالي) — return null
  if this page is a Cash Flow statement (قائمة التدفقات النقدية).
- For Cash-Flow items (operating_cash_flow, investing_cash_flow, financing_cash_flow,
  capex, depreciation_amortization), read ONLY from the Cash Flow statement.
- Return null for any item NOT explicitly printed on this page or printed as a dash
  ("---", "—", "-") — NEVER output 0 for a dash cell.

Return ONLY JSON:
{{"years": [{years_hint}], "values": {{{json_template}}}}}
Cross-check both attached image variants (standard cleanup + adaptive-threshold) carefully.
"""


def _call_distinct_model(
    pool: APIKeyPool,
    prompt: str,
    images: list[bytes],
    exclude_models: set[str],
    call_stats: list[tuple[str, float]] | None = None,
) -> tuple[str, str]:
    """Invoke a STRICTLY distinct Gemini model outside `exclude_models`.

    Returns `(raw_text, model_name)`. Raises RuntimeError if no distinct healthy
    model can succeed — never falls back to a model inside `exclude_models`.
    """
    import time
    from src.ai.gemini_agent import classify_gemini_error
    from src.ai.key_pool import classify_quota_scope

    last_error = "no distinct model available"
    max_attempts = max(len(pool.states) * max(1, len(pool.models) - len(exclude_models)), 1)
    tried_exhausted = 0
    for _ in range(min(max_attempts, 14)):
        picked = pool.pick_distinct_model(exclude_models=exclude_models)
        if picked is None:
            break
        state, model = picked
        if model in exclude_models:
            break
        t0 = time.perf_counter()
        try:
            raw = _call_vision(state.key, model, prompt, images)
            elapsed = time.perf_counter() - t0
            if call_stats is not None:
                call_stats.append((model, elapsed))
            pool.reset_transient(model)
            pool.mark_success(state.key)
            pool.record_call(model, elapsed)
            return raw, model
        except Exception as exc:
            tried_exhausted += 1
            fail_ms = (time.perf_counter() - t0) * 1000.0
            kind = classify_gemini_error(exc)
            if kind == "quota":
                scope, cd_s = classify_quota_scope(exc)
                if scope == "rpm":
                    pool.mark_rpm_limited(state.key, model, cd_s)
                else:
                    pool.mark_quota_exhausted(state.key, model)
                pool.record_failover(fail_ms)
                last_error = f"quota on {model}"
            elif kind == "auth":
                pool.mark_dead(state.key, str(exc)[:200])
                pool.record_failover(fail_ms)
                last_error = f"auth rejected on {state.masked}"
            elif kind == "model":
                low_exc = str(exc).lower()
                global_404 = "no longer available" in low_exc or "models/" in low_exc
                pool.mark_model_unavailable(state.key, model, str(exc)[:200], all_keys=global_404)
                pool.record_failover(fail_ms)
                last_error = f"model {model} unavailable"
            else:
                pool.mark_transient_failure(model)
                pool.record_failover(fail_ms)
                last_error = str(exc)[:200]
    raise RuntimeError(f"Cross-model distinct vision call unavailable ({last_error}).")


_CROSS_MODEL_PRIORITY = (
    "net_income", "pretax_income", "operating_income", "net_activity_profit",
    "revenue", "cost_of_revenue", "gross_profit", "income_tax_expense",
    "total_assets", "current_assets", "non_current_assets",
    "total_liabilities", "current_liabilities", "non_current_liabilities", "equity",
    "operating_cash_flow", "investing_cash_flow", "financing_cash_flow",
    "cash", "inventory", "accounts_receivable", "other_receivables", "supplier_advances",
    "accounts_payable", "customer_advances", "other_payables", "provisions",
    "fixed_assets", "long_term_debt", "long_term_notes_payable", "short_term_debt",
    "short_term_credit_facilities", "current_portion_lt_debt", "bank_overdraft",
    "current_lease_liabilities", "non_current_lease_liabilities", "deferred_tax_liabilities",
    "capex", "depreciation_amortization", "finance_income", "interest_expense", "fx_gain_loss",
    "selling_expenses", "admin_expenses", "other_operating_expenses", "other_operating_income",
    "retained_earnings", "capital", "reserves", "treasury_shares", "asset_revaluation_reserve",
    "dividends_from_subsidiaries",
)

_CROSS_MODEL_EXPENSE_FIELDS = frozenset({
    "cost_of_revenue", "income_tax_expense", "selling_expenses",
    "admin_expenses", "other_operating_expenses", "operating_expenses",
    "interest_expense", "depreciation_amortization", "capex",
})

_CROSS_MODEL_BS_STOCK_FIELDS = frozenset({
    "inventory", "accounts_receivable", "other_receivables", "supplier_advances",
    "accounts_payable", "customer_advances", "other_payables", "provisions", "cash",
    "fixed_assets", "current_assets", "non_current_assets", "total_assets",
    "current_liabilities", "non_current_liabilities", "total_liabilities",
    "equity", "retained_earnings", "capital", "reserves",
    "long_term_debt", "long_term_notes_payable", "deferred_tax_liabilities",
    "short_term_debt", "short_term_credit_facilities",
    "current_portion_lt_debt", "bank_overdraft",
    "current_lease_liabilities", "non_current_lease_liabilities", "total_debt",
})


def _record_cross_model_layer(
    data: FinancialData,
    field: str,
    year: int,
    captured: float,
    used_model: str,
) -> bool:
    """Record an independent `vision_cross_model` witness on `(field, year)`."""
    from src.extraction.normalizer import _digit_close

    if captured is None or not used_model:
        return False
    votes = getattr(data, "vote_outcomes", None)
    if not isinstance(votes, dict):
        data.vote_outcomes = {}
        votes = data.vote_outcomes
    order_next = max(
        (o for cands in (getattr(data, "candidates", {}) or {}).values()
         for ys in cands.values() for _v, o in ys),
        default=0,
    ) + 1
    cand_list = data.candidates.setdefault(field, {}).setdefault(year, [])
    layer_list = data.candidate_layers.setdefault(field, {}).setdefault(year, [])
    label_list = data.candidate_labels.setdefault(field, {}).setdefault(year, [])
    if len(layer_list) < len(cand_list):
        fb_lyr = layer_list[0] if layer_list else "vision"
        layer_list.extend([fb_lyr] * (len(cand_list) - len(layer_list)))
    elif len(layer_list) > len(cand_list):
        del layer_list[len(cand_list):]
    if not any(
        v is not None and _digit_close(v, captured) and lyr == "vision_cross_model"
        for (v, _o), lyr in zip(cand_list, layer_list)
    ):
        cand_list.append((captured, order_next))
        label_list.append(f"cross_model:{used_model}")
        layer_list.append("vision_cross_model")
    data.bump_confidence(field, year, 2)
    vo = votes.get((field, year))
    if isinstance(vo, dict):
        wl = list(vo.get("winner_layers") or [])
        if not wl:
            wl.append("vision")
        if "vision_cross_model" not in wl:
            wl.append("vision_cross_model")
        vo["winner_layers"] = sorted(set(wl))
    else:
        existing_lyrs = {
            lyr for (v, _o), lyr in zip(cand_list, layer_list)
            if v is not None and _digit_close(v, captured) and lyr
        }
        existing_lyrs.add("vision_cross_model")
        if len(existing_lyrs) < 2:
            existing_lyrs.add("vision")
        votes[(field, year)] = {
            "winner": captured,
            "votes": max(2, len(existing_lyrs)),
            "total": len(cand_list),
            "witnesses": len(existing_lyrs),
            "winner_layers": sorted(existing_lyrs),
            "replaced": captured,
            "dissent": [],
            "contested": False,
        }
    return True


def _cross_model_consensus_verify(
    data: FinancialData,
    field_sources: dict[str, list[int]],
    pages_png: list[bytes],
    selected: list[int],
    pool: APIKeyPool | None,
    sweep_models: list[str] | None = None,
    notes: list[str] | None = None,
    progress_cb=None,
    deadline: float | None = None,
    max_pages: int = 6,
    time_budget_s: float = 75.0,
    distinct_caller=None,
) -> int:
    """Independent Cross-Model Consensus verification pass for remaining UNVERIFIED cells.

    Guarantees:
      1. Strictly uses a DIFFERENT Gemini model ID than the primary sweep model
         (prefers full Flash vs Flash-Lite contrast). Same-model repeats are forbidden.
      2. Zero prompt leakage: Model B never receives Model A's extracted numbers.
      3. Strict digit-exact consensus: only exact digit agreement attests a cell
         with layer `vision_cross_model`. Disagreements stay gated for human review
         and NEVER silently overwrite `data.values`.
      4. Bounded cost: at most `max_pages` (default 4) pages executed in parallel.

    Returns count of newly cross-model-attested `(field, year)` cells.
    """
    import os
    import time as _time
    from collections import Counter
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from src.analysis.comparison import LABELS_AR
    from src.extraction.normalizer import _digit_close, build_decision_log

    if os.getenv("CROSS_MODEL_VERIFY", "1") != "1":
        return 0
    if distinct_caller is None and (pool is None or not pool.has_usable_pairs()):
        return 0

    years = sorted(y for y in (data.years or []) if isinstance(y, int))
    if not years or not selected:
        return 0

    try:
        decisions = build_decision_log(data)
    except Exception:
        return 0

    derived_map = getattr(data, "derived", {}) or {}
    unverified_targets: dict[str, set[int]] = {}
    for d in decisions:
        f, y = d.get("field"), d.get("year")
        if d.get("status") != "UNVERIFIED" or d.get("final") is None:
            continue
        if (f, y) in derived_map:
            continue  # never ask Vision to read a synthetically derived cell
        if not isinstance(y, int):
            continue
        unverified_targets.setdefault(f, set()).add(y)

    if not unverified_targets:
        return 0

    # Determine models to exclude so Model B is genuinely distinct from the primary sweep
    sweep_list = [m for m in (sweep_models or []) if m]
    all_sweep_set = set(sweep_list)
    dominant_model = Counter(sweep_list).most_common(1)[0][0] if sweep_list else None
    exclude_set = set(all_sweep_set)
    if distinct_caller is None and pool is not None:
        if pool.pick_distinct_model(exclude_models=exclude_set) is None:
            # If the sweep happened to touch every model, at minimum exclude the dominant model
            exclude_set = {dominant_model} if dominant_model else set()
            if not exclude_set or pool.pick_distinct_model(exclude_models=exclude_set) is None:
                return 0  # No genuinely distinct healthy model available

    # Map each unverified field to its primary (lowest) source page in `selected`
    selected_set = set(selected)
    cf_only_pages = (
        {p for f in ("operating_cash_flow", "investing_cash_flow", "financing_cash_flow")
         for p in (field_sources.get(f) or [])}
        - {p for f in ("total_assets", "equity", "current_assets")
           for p in (field_sources.get(f) or [])}
    )
    page_to_fields: dict[int, list[str]] = {}
    prio_rank = {f: i for i, f in enumerate(_CROSS_MODEL_PRIORITY)}
    for f in sorted(unverified_targets, key=lambda k: prio_rank.get(k, 999)):
        src_pages = sorted({p for p in (field_sources.get(f) or []) if p in selected_set})
        if f in _CROSS_MODEL_BS_STOCK_FIELDS:
            src_pages = [p for p in src_pages if p not in cf_only_pages]
        if not src_pages:
            continue
        # Register up to 2 source pages (e.g. primary statement + Note schedule) so
        # whichever page prints the row clearest can confirm it digit-exactly
        for cand_p in src_pages[:2]:
            if f not in page_to_fields.setdefault(cand_p, []):
                page_to_fields[cand_p].append(f)

    if not page_to_fields:
        return 0

    # Prioritize core statement pages (p <= 12) and highest-impact unverified count
    ranked_pages = sorted(
        page_to_fields.items(),
        key=lambda kv: (
            0 if kv[0] <= 12 else 1,
            -sum(3 if prio_rank.get(f, 999) < 18 else 1 for f in kv[1]),
            kv[0],
        ),
    )[:max_pages]

    t0 = _time.time()
    eff_deadline = min(deadline, t0 + time_budget_s) if deadline is not None else (t0 + time_budget_s)
    if eff_deadline - t0 < 8.0:
        return 0

    if progress_cb:
        pg_list = [p for p, _ in ranked_pages]
        progress_cb(f"🤝 تحقق النموذج الثاني المستقل (Cross-Model Consensus) للصفحات {pg_list}…")

    by_page_png = dict(zip(selected, pages_png))
    years_hint = ", ".join(str(y) for y in years[-2:])
    cand_labels_map = getattr(data, "candidate_labels", {}) or {}

    def _printed_hint(f: str) -> str:
        base_ar = LABELS_AR.get(f, f)
        raw_set: list[str] = []
        for _y, lbls in (cand_labels_map.get(f) or {}).items():
            for lb in (lbls or []):
                s = str(lb or "").strip()
                if (
                    s
                    and ":" not in s
                    and not any(ch.isdigit() for ch in s)
                    and s not in raw_set
                    and s != base_ar
                ):
                    raw_set.append(s)
        if raw_set:
            return f"{base_ar} — مطبوع باسم: «{raw_set[0][:60]}»"
        if f == "capex":
            return f"{base_ar} — ابحث في أنشطة الاستثمار عن «مدفوعات لشراء أصول ثابتة ومشروعات تحت التنفيذ»"
        return base_ar

    def _verify_page(page_no: int, fields_on_p: list[str]) -> tuple[int, str | None, dict[str, dict[int, float]], str]:
        if _time.time() > eff_deadline - 3.0:
            return page_no, None, {}, "budget"
        target_f = fields_on_p[:24]  # cover full Balance Sheet / P&L / CF page without truncating AP or Fixed Assets
        bullets = "\n".join(
            f"- {f} ({_printed_hint(f)})" for f in target_f
        )
        json_tpl = ", ".join(f'"{f}": [v1, v2]' for f in target_f)
        prompt = CROSS_MODEL_VERIFY_PROMPT.format(
            field_bullets=bullets,
            years_hint=years_hint,
            json_template=json_tpl,
        )
        src_png = by_page_png[page_no]
        img = preprocess_image(src_png, max_side=2200)
        img_bin = preprocess_image(src_png, max_side=2200, binarize=True)
        try:
            if distinct_caller is not None:
                raw_text, used_model = distinct_caller(page_no, prompt, [img, img_bin], exclude_set)
            else:
                raw_text, used_model = _call_distinct_model(
                    pool, prompt, [img, img_bin], exclude_models=exclude_set
                )
            if used_model in exclude_set:
                return page_no, None, {}, "same_model_rejected"
            parsed_json = _loads_relaxed(raw_text)
        except Exception as exc:
            return page_no, None, {}, str(exc)[:140]

        resp_years = [extract_year(y) for y in (parsed_json.get("years") or [])]
        resp_years = [y for y in resp_years if y]
        if not resp_years:
            resp_years = list(years[-2:])
        vals_block = parsed_json.get("values") or parsed_json.get("totals") or {}
        out_map: dict[str, dict[int, float]] = {}
        if isinstance(vals_block, dict):
            for f, arr in vals_block.items():
                if f not in target_f or not isinstance(arr, list):
                    continue
                for idx, raw_v in enumerate(arr):
                    if idx >= len(resp_years):
                        break
                    num = parse_number(raw_v)
                    if num is None:
                        continue
                    if float(num).is_integer() and 0 <= num <= 3:
                        continue
                    out_map.setdefault(f, {})[resp_years[idx]] = float(num)
        return page_no, used_model, out_map, ""

    page_results: list[tuple[int, str | None, dict[str, dict[int, float]], str]] = []
    workers = min(3, len(ranked_pages))
    if workers <= 1 or distinct_caller is not None:
        for pno, flist in ranked_pages:
            page_results.append(_verify_page(pno, flist))
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(_verify_page, pno, flist) for pno, flist in ranked_pages]
            for fut in as_completed(futs):
                try:
                    page_results.append(fut.result())
                except Exception:
                    pass

    attested_count = 0
    disagreed_count = 0
    models_used: set[str] = set()

    for page_no, used_model, out_map, _err in sorted(page_results, key=lambda r: r[0]):
        if not used_model or not out_map:
            continue
        models_used.add(used_model)
        is_cf_page = page_no in cf_only_pages
        for f, by_y in out_map.items():
            if is_cf_page and f in _CROSS_MODEL_BS_STOCK_FIELDS:
                continue
            target_years = unverified_targets.get(f) or set()
            for y, val_b in by_y.items():
                if y not in target_years:
                    continue
                captured = data.get(f, y)
                if captured is None:
                    continue
                # Sign handling: balance-sheet stocks, expenses, and CF-deducted subsidiary dividends
                # allow cross-statement print-sign convention; net/pretax/operating/CF totals match sign strictly!
                cmp_b = val_b
                if f in _CROSS_MODEL_BS_STOCK_FIELDS:
                    cmp_b = abs(val_b)
                elif f in _CROSS_MODEL_EXPENSE_FIELDS or (is_cf_page and f == "dividends_from_subsidiaries"):
                    cmp_b = -abs(val_b) if captured < 0 else abs(val_b)
                if _digit_close(cmp_b, captured):
                    target_years.discard(y)
                    if _record_cross_model_layer(data, f, y, captured, used_model):
                        attested_count += 1
                else:
                    # Honest disagreement: never promote and never silently overwrite
                    disagreed_count += 1

    if notes is not None and (attested_count or disagreed_count):
        m_str = ", ".join(sorted(models_used))
        notes.append(
            f"التحقق المتقاطع بنموذج ثانٍ مستقل ({m_str}): تم توثيق {attested_count} خانة "
            f"بتطابق رقمي كامل (100% digit-exact)"
            + (f" — وبقيت {disagreed_count} خانة محجوبة للمراجعة البشرية لاختلاف القراءتين." if disagreed_count else ".")
        )
    return attested_count


def run_spatial_shadow(data, page_items, notes=None, fields=None,
                       converter=None) -> dict | None:
    """REPLAY/SHADOW runner: spatial extraction over the rendered pages,
    RECORDS-ONLY (no value/status changes). Returns the shadow record or
    None when the local reader is unavailable. Runnable directly against
    saved PNGs for replay tests (labelled REPLAY, not a live run)."""
    try:
        from .local_ocr import indra_available
        from .spatial_cells import extract_spatial_cell

        if not indra_available():
            if notes is not None:
                notes.append("Spatial shadow skipped: local OCR unavailable")
            return None
        import indra_ocr as _indra

        conv = converter or _indra.load()
        years = [int(y) for y in data.years if isinstance(y, int)][:2]
        fields = fields or ("revenue", "net_income", "total_assets",
                            "total_liabilities", "operating_cash_flow")
        shadow: dict = {}
        for pi, ppng in page_items[:3]:
            for f in fields:
                for y in years:
                    try:
                        c = extract_spatial_cell(conv, ppng, f, y)
                    except Exception as exc:  # noqa: BLE001 — recorded
                        shadow[f"{f}|{y}|p{pi}"] = {"status": "ERROR",
                                                    "detail": str(exc)[:120]}
                        continue
                    shadow[f"{f}|{y}|p{pi}"] = {
                        "status": c.status, "value": c.value,
                        "provenance": c.provenance,
                        "year_source": c.year_source,
                        "detail": c.detail[:160],
                    }
                    # pure geometry reports the honest UNCONFIRMED_YEAR on
                    # documents without readable year headers; ALSO record the
                    # declared-convention arm (labelled YEAR_INFERRED) so the
                    # shadow comparison is informative — never conflated.
                    if c.status in ("UNCONFIRMED_YEAR", "NO_COLUMN"):
                        try:
                            from .spatial_cells import find_currency_columns

                            _w, _h, _lines = (None, None, None)
                            cd = extract_spatial_cell(
                                conv, ppng, f, y,
                                columns=_declared_cols(conv, ppng),
                                columns_source="declared convention")
                            shadow[f"{f}|{y}|p{pi}|inferred"] = {
                                "status": cd.status, "value": cd.value,
                                "provenance": cd.provenance,
                                "year_source": "YEAR_INFERRED",
                                "detail": cd.detail[:160],
                            }
                        except Exception as exc:  # noqa: BLE001
                            shadow[f"{f}|{y}|p{pi}|inferred"] = {
                                "status": "ERROR", "detail": str(exc)[:120]}
        record = {
            "mode": "SHADOW_REPLAY",
            "affects_results": False,
            "cells": shadow,
            "produced_value": sum(1 for v in shadow.values()
                                  if v.get("value") is not None),
        }
        data.spatial_shadow = record
        if notes is not None:
            notes.append(f"Spatial shadow ran: {record['produced_value']}"
                         f"/{len(shadow)} cells produced a value — recorded "
                         "only, no status changed.")
        return record
    except Exception as exc:  # noqa: BLE001 — shadow must never break the run
        if notes is not None:
            notes.append(f"Spatial shadow mode failed (ignored): {exc}")
        return None


def _declared_cols(conv, png):
    """Currency-title columns + the declared year order (YEAR_INFERRED) —
    the fallback arm of the shadow, always labelled, never presented as a
    printed-date read."""
    from .spatial_cells import find_currency_columns, read_page_lines

    w, h, lines = read_page_lines(conv, png)
    cc, _d = find_currency_columns(lines, w)
    if not cc:
        return None
    return {2022: cc["right"], 2021: cc["left"]}
