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
# Version tag for the extraction prompts + pipeline (logged in every result
# and in the Verification Decision Log — reproducibility requirement).
VISION_PROMPT_VERSION = "sweep-v2/verify-v4(10-fields+dual-variant+cell-crop)/cf-v3(dual-variant)"   # seconds — hard cap on the whole vision sweep (raised: the 2-of-3 third opinion once ate 4.5 min and starved CF verification)
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


def preprocess_image(png: bytes, max_side: int | None = None, binarize: bool = False) -> bytes:
    """OpenCV cleanup for better machine reading: grayscale, cap resolution,
    deskew (small angles only), CLAHE contrast, light denoise, border crop.

    binarize=True adds an adaptive-threshold pass (the second preprocessing
    variant sent alongside the standard one in verification reads — faded
    digits that survive CLAHE often vanish in, or only appear under, the
    adaptive threshold; reading BOTH in one call breaks repeated misreads).
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

        ok, jpeg = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
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
                values = row.get("values") or []
            elif isinstance(row, list) and row:
                label, values = row[0], row[1:]
            else:
                continue
            if label is None:
                continue
            values = [parse_number(v) for v in values]
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

    client = _get_client(key)
    parts = [prompt] + [
        types.Part.from_bytes(data=img, mime_type="image/jpeg") for img in images
    ]
    response = client.models.generate_content(model=model, contents=parts, config=_vision_config())
    return (response.text or "").strip()


def _get_client(key: str):
    from google import genai
    from google.genai import types

    cached = _CLIENTS.get(key)
    if cached is None:
        cached = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=45_000))
        _CLIENTS[key] = cached
    return cached


def _vision_config():
    from google.genai import types

    return types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.0,  # OCR: zero creativity
        max_output_tokens=8192,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )


_CLIENTS: dict[str, object] = {}


def _call_with_rotation(pool: APIKeyPool, prompt: str, images: list[bytes]) -> str:
    """Vision call with the same key/model rotation as the commentary path,
    plus one extra full sweep after a pause when every failure was transient
    (e.g. 503 high demand) — mirroring analyze_financials.

    Fail-fast: when every pair is already marked depleted/dead, raise
    immediately instead of sweeping (a sweep against a dead pool only adds
    latency to every batch and retry).
    """
    import time

    from src.ai.gemini_agent import classify_gemini_error

    if not pool.has_usable_pairs():
        raise RuntimeError(
            "all API key/model pairs are exhausted or unavailable "
            "(daily free-tier quota resets after midnight US Pacific)."
        )
    last_error = "no attempt was made"
    for sweep in range(2):
        transient_only = True
        for _ in range(min(pool.total_pairs, 14)):
            picked = pool.pick()
            if picked is None:
                break
            state, model = picked
            try:
                return _call_vision(state.key, model, prompt, images)
            except Exception as exc:
                kind = classify_gemini_error(exc)
                if kind == "quota":
                    pool.mark_quota_exhausted(state.key, model)
                    last_error = f"quota exhausted for {model} on {state.masked}"
                    transient_only = False
                elif kind == "auth":
                    pool.mark_dead(state.key, str(exc)[:200])
                    last_error = f"key {state.masked} rejected"
                    transient_only = False
                elif kind == "model":
                    pool.mark_model_unavailable(state.key, model, str(exc)[:200])
                    last_error = f"model {model} unavailable"
                    transient_only = False
                else:
                    last_error = str(exc)[:250]
        if (
            sweep == 0
            and transient_only
            and pool.has_usable_pairs()
        ):
            time.sleep(6)  # wait out the demand spike, then sweep again
        else:
            break
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
- المبيعات / الإيرادات (revenue)
- صافي أرباح العام (net income)
- صافي أرباح العام قبل ضريبة الدخل (pretax income) — يُطبع أيضًا أول قائمة التدفقات
- المخزون (inventory)
- العملاء وأوراق القبض / الذمم المدينة (accounts receivable)
- الموردون / الذمم الدائنة (accounts payable)
- النقدية وما في حكمها (cash)

Return ONLY JSON:
{{"years": [2021, 2022],
  "totals": {{"current_liabilities": [v1, v2], "total_liabilities": [v1, v2],
              "total_assets": [v1, v2], "equity": [v1, v2],
              "revenue": [v1, v2], "net_income": [v1, v2],
              "pretax_income": [v1, v2],
              "inventory": [v1, v2], "accounts_receivable": [v1, v2],
              "accounts_payable": [v1, v2], "cash": [v1, v2]}}}}
Use null for any value not on the page. Parentheses = negative. Copy digits exactly.
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
            if num is not None:
                by_year[years[i]] = num
        if by_year:
            out[str(field).strip()] = by_year
    return out


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
            "revenue", "net_income", "pretax_income",
            # detail balances: a real run shipped inventory/AR from CF change
            # rows because the BS detail rows were never verified — same page,
            # same call, zero extra quota.
            "inventory", "accounts_receivable", "accounts_payable", "cash",
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

    third_budget = {"left": 2}  # third-opinion calls per run
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
        try:
            raw_text = (
                caller("k", "m", prompt, [img, img_bin])
                if caller is not None
                else _call_with_rotation(pool, prompt, [img, img_bin])
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
        for field, by_year in verified.items():
            if field not in core:
                continue
            for year, value in by_year.items():
                captured = data.get(field, year)
                if captured is None:
                    continue
                if field != "net_income":
                    value = abs(value)  # magnitudes; NI may be a real loss (negative)
                if local_reads:
                    from src.extraction.local_ocr import confirms

                    selected_set_v = set(selected)
                    src_pages = [p for p in field_sources.get(field, []) if p in selected_set_v]
                    if any(confirms(local_reads, p, captured) for p in src_pages):
                        # captured value already has two independent votes
                        key_c = (field, year)
                        conf[key_c] = max(conf.get(key_c, 0), 2)
                        continue
                # Digit-exact verification: a 0.5% tolerance let digit
                # transpositions through (26.5M on 13.2B = 0.2% — "matched").
                # The focused re-read copies digits; agreement must be exact.
                if abs(value - captured) > max(1.0, 1e-6 * abs(captured)):
                    disputes[(field, year)] = value
                else:
                    key_c = (field, year)
                    conf[key_c] = max(conf.get(key_c, 0), 2)  # focused read agrees

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
            if third is not None and field != "net_income":
                third = abs(third)
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


VERIFY_CF_PROMPT = """From this scanned ARABIC cash-flow statement page, read ONLY these three
net-cash totals, exactly as printed, for EACH year column shown:
- النقدية الناتجة من الأنشطة التشغيلية (OPERATING activities) — the printed
  phrasing may be "صافي التدفقات النقدية من الأنشطة التشغيلية" OR
  "صافي النقدية الناتجة من أنشطة التشغيل" — same row either way
- الأنشطة الاستثمارية (INVESTING activities)
- الأنشطة التمويلية (FINANCING activities)

Return ONLY JSON:
{{"years": [2021, 2022],
  "totals": {{"operating_cash_flow": [v1, v2], "investing_cash_flow": [v1, v2],
              "financing_cash_flow": [v1, v2]}}}}
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
                    parsed = parse_table(frame)
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
            if num is not None:
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
        try:
            raw_text = (
                caller("k", "m", VERIFY_CF_PROMPT, [img, img_bin])
                if caller is not None
                else _call_with_rotation(pool, VERIFY_CF_PROMPT, [img, img_bin])
            )
            verified = _parse_verify_cf_json(raw_text)
        except Exception as exc:
            notes.append(f"Cash-flow verification of page {page_number} failed: {exc}")
            continue
        for field, by_year in verified.items():
            if field not in cf_fields:
                continue
            for year, value in by_year.items():
                captured = data.get(field, year)
                if captured is None:
                    continue
                if local_reads:
                    from src.extraction.local_ocr import confirms

                    src_pages = [p for p in field_sources.get(field, [])
                                 if p in selected_set]
                    if any(confirms(local_reads, p, captured) for p in src_pages):
                        if confidence is not None:
                            key_c = (field, year)
                            confidence[key_c] = max(confidence.get(key_c, 0), 2)
                        continue  # captured value has two independent votes
                if abs(value - captured) > max(1.0, 1e-6 * abs(captured)):
                    for part in parts:
                        if year in part and field in part[year]:
                            part[year][field] = value  # sign included, corrected at source
                    if notes is not None:
                        notes.append(
                            f"✓ Verified by focused CF re-read: {field} in {year} "
                            f"{captured:,.0f} → {value:,.0f}."
                        )
                elif confidence is not None:
                    key_c = (field, year)
                    confidence[key_c] = max(confidence.get(key_c, 0), 2)


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
            table_first = [p for p in selected if local_reads[p].has_table]
            rest = [p for p in selected if not local_reads[p].has_table]
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
            if runs and (p == runs[-1][-1] + 1 and len(runs[-1]) < VISION_BATCH_SIZE):
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
    accumulated = FinancialData()
    currency_holder: dict = {"hint": None}
    company_holder: dict = {"name": None}
    doc_years_holder: dict = {"years": None}
    ok_pages: set[int] = set()
    field_sources: dict[str, list[int]] = {}  # field -> pages that provided it
    confidence: dict = {}                     # (field, year) -> agreeing reads
    failure_reasons: list[str] = []           # why vision reads failed (for the final error)
    stopped_early = False
    done_pages = 0

    def _run_batch(chunk: list[int], imgs: list[bytes]) -> list[dict]:
        first, last = chunk[0], chunk[-1]
        prompt = (
            VISION_PROMPT.format(first=first, last=last)
            if len(chunk) > 1
            else _single_prompt(first)
        )
        if caller is not None:
            return _parse_vision_json(caller("k", "m", prompt, imgs))
        raw_text = _call_with_rotation(pool, prompt, imgs)
        return _parse_vision_json(raw_text)

    import time as _time

    deadline = _time.time() + VISION_TOTAL_BUDGET
    wave_size = max(n_workers, 1)  # batches per wave
    for wave_start in range(0, len(batches), wave_size):
        if _time.time() > deadline:
            notes.append(
                f"Vision time budget ({VISION_TOTAL_BUDGET}s) exhausted — "
                f"proceeding with the {done_pages}/{n_pages} pages read so far."
            )
            break
        if not batches[wave_start : wave_start + wave_size] or (
            wave_start > 0 and not pool.has_usable_pairs()
        ):
            # Pool died mid-run (all pairs quota-exhausted): stop sweeping,
            # remaining batches cannot succeed.
            notes.append(
                "Stopping the vision sweep: all API key/model pairs are now "
                "exhausted or unavailable."
            )
            break
        wave = batches[wave_start : wave_start + wave_size]
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
                _absorb_batch(batch_pages, chunk, parts, ok_pages, notes, currency_holder, doc_years_holder, field_sources)
                if not company_holder.get("name"):
                    company_holder["name"] = next(
                        (p.get("company") for p in batch_pages if p.get("company")), None
                    )
                done_pages += len(chunk)
                if progress_cb:
                    progress_cb(f"📚 وصلنا للصفحة {done_pages} من {n_pages}…")

        accumulated = merge_parsed(parts, [])
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
        [p for p in selected if p not in ok_pages]
        if not stopped_early
        else []
    )
    if failed_pages and not pool.has_usable_pairs():
        notes.append(
            "Skipping the retry pass: all API key/model pairs are exhausted "
            "or unavailable."
        )
    elif failed_pages:
        notes.append(f"Retrying {len(failed_pages)} unread page(s): {failed_pages[:12]}…")
        if progress_cb:
            progress_cb(f"🔁 إعادة قراءة {len(failed_pages)} صفحة لم تكتمل…")
        for page_number in failed_pages:
            if not pool.has_usable_pairs():
                break
            try:
                img = preprocess_image(pages_png[selected.index(page_number)])
                raw_text = (
                    caller("k", "m", _single_prompt(page_number), [img])
                    if caller is not None
                    else _call_with_rotation(pool, _single_prompt(page_number), [img])
                )
                for page in _parse_vision_json(raw_text):
                    frame = _page_to_frame(page)
                    if frame is not None:
                        try:
                            parsed = parse_table(frame)
                            if parsed:
                                parts.append(parsed)
                        except Exception as exc:
                            notes.append(f"Vision page skipped ({exc}).")
                    if not company_holder.get("name") and page.get("company"):
                        company_holder["name"] = page["company"]
            except ExtractionError as exc:
                notes.append(f"Vision page {page_number} failed again (skipped).")
                failure_reasons.append(str(exc))
        accumulated = merge_parsed(parts, [])

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
    pre_merge = merge_parsed(parts, [])
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
        deadline=deadline,
        local_reads=local_reads,
    )

    # Focused double-read of the three net-cash totals — the CF statement
    # carries SIGNS (outflows negative). Runs BEFORE the expensive core
    # third-opinion stage: a real run once exhausted the whole time budget
    # on that stage and CFO shipped unverified with a wrong capture.
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
            deadline=deadline,
            confidence=confidence,
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
            deadline=deadline,
            confidence=confidence,
        )

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
    data = merge_parsed(parts, notes)
    # Confidence must reach reconcile BEFORE it runs: the tax bridge anchors
    # on a multiply-verified net income, which is only known here.
    for (field_name, year), level in confidence.items():
        data.bump_confidence(field_name, year, level)
    reconcile(data)
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
    # Provenance: which page each field was captured from — surfaces in the
    # UI and lets the pipeline flag balance fields sourced from notes pages.
    data.field_sources = field_sources
    # ── Cell-crop verification (الخانة المقتطعة) ──
    # Core fields whose decision-log status is CONFLICT or UNVERIFIED get ONE
    # focused strip re-read each (max 2 per run). Confidence-UPGRADE only: a
    # disagreeing crop read is RECORDED as CONFLICT, never auto-applied — per
    # mandate: no forced replacement, unresolved conflict stays visible.
    if LOCAL_OCR_ENABLED and caller is None:
        try:
            from .normalizer import build_decision_log
            from src.analysis.comparison import LABELS_AR as _CV_LBL

            _decisions = build_decision_log(data)
            _CORE = ("net_income", "revenue", "pretax_income", "total_assets",
                     "total_liabilities", "current_liabilities", "equity")
            _disputed = [d for d in _decisions
                         if d["field"] in _CORE
                         and d["status"] in ("CONFLICT", "UNVERIFIED")]
            _disputed.sort(key=lambda d: 0 if d["status"] == "CONFLICT" else 1)
            _spent = 0
            for d in _disputed:
                if _spent >= 2:
                    break
                _pages = [p for p in d["pages"] if p in selected]
                if not _pages:
                    continue
                _src = pages_png[selected.index(_pages[0])]
                _strip = _cell_crop_png(_src)
                _label = _CV_LBL.get(d["field"], d["field"])
                _prompt = CELL_VERIFY_PROMPT.format(label=_label, field=d["field"])
                try:
                    _raw = _call_with_rotation(pool, _prompt, [_strip])
                    _verified = _parse_verify_json(_raw)
                except Exception as exc:
                    if notes is not None:
                        notes.append(f"Cell verification of {d['field']} failed: {exc}")
                    continue
                _spent += 1
                _by_year = _verified.get(d["field"]) or {}
                _final = data.get(d["field"], d["year"])
                _agree = any(
                    y is not None and _final is not None
                    and abs(y - _final) <= max(1.0, 1e-6 * abs(_final))
                    for y in _by_year.values()
                )
                if _agree and _final is not None:
                    data.bump_confidence(d["field"], d["year"], 2)
                    if notes is not None:
                        notes.append(
                            f"✓ Cell-crop re-read confirms {d['field']} in {d['year']} "
                            f"= {_final:,.0f} (page {_pages[0]}) — VERIFIED_EXACT."
                        )
                elif notes is not None:
                    notes.append(
                        f"⚠ Cell-crop re-read DISAGREES on {d['field']} in {d['year']}: "
                        f"crop read {json.dumps(_by_year, ensure_ascii=False)} vs captured "
                        f"{_final:,.0f} — value kept, status CONFLICT (mandate: no forced "
                        "replacement).")
        except Exception:
            pass  # cell verification is an enhancement — never breaks extraction

    data.currency_hint = currency_holder.get("hint")
    data.company_hint = company_holder.get("name") or None
    if LOCAL_OCR_ENABLED and caller is None:
        # Notes text capture (الإيضاحات المتممة): a free LOCAL Indra read of
        # every page so the explanatory prose (accounting policies, loan
        # terms, aging, contingencies) becomes searchable — the table-only
        # sweep sees these pages but keeps none of their prose.
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
    return data


def _absorb_batch(
    batch_pages: list[dict],
    chunk: list[int],
    parts: list,
    ok_pages: set,
    notes: list[str],
    currency_holder: dict,
    doc_years_holder: dict,
    field_sources: dict[str, list[int]],
) -> None:
    """Merge one batch's parsed pages into the accumulators.

    A page whose header shows no years (common for cash-flow statements)
    inherits the document's years when the row value-count matches.
    """
    for page in batch_pages:
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
            parsed = parse_table(frame)
            if parsed:
                parts.append(parsed)
                ok_pages.update(chunk)
                for year_fields in parsed.values():
                    for field in year_fields:
                        field_sources.setdefault(field, []).extend(chunk)
        except Exception as exc:  # one bad page must not kill the run
            notes.append(f"Vision page skipped ({exc}).")
