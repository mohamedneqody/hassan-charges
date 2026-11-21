"""Notes RAG (قراءة وفهم الإيضاحات المتممة) — local, zero-cost retrieval.

The vision reader sees the notes pages (الإيضاحات المتممة, typically pages
10-29) but only keeps tabular financial rows — the explanatory PROSE
(accounting policies, loan terms, receivables aging, NCI details) was
discarded. This module makes that prose first-class:

1. Index: every notes page's markdown text is split into paragraph chunks
   and indexed with a hand-rolled TF-IDF over normalized Arabic tokens
   (no new dependencies, works offline).
2. Search: a question is normalized/tokensed the same way and scored by
   cosine similarity against the chunks; the top-k chunks carry their
   source page numbers.
3. Answer: with Gemini available the chunks + question are formulated into
   an Arabic answer that QUOTES its sources; without it the top chunks are
   returned verbatim — the user still gets the text, never nothing.

Design constraints honored: no invented numbers, sources always shown,
works offline, zero extra model downloads.
"""
from __future__ import annotations

import json
import math
import re
import time
import unicodedata
from dataclasses import dataclass, field

# ── Arabic-aware normalization (lighter than normalizer.match_field:
#    keeps morphology, only strips what hurts retrieval) ──
_STOPWORDS = {
    "في", "من", "على", "الي", "عن", "مع", "هذا", "هذه", "ذلك", "التي",
    "الذي", "ما", "لا", "او", "أو", "و", "ثم", "كما", "قد", "بعد", "قبل",
    "عند", "كل", "بين", "حتى", "لكن", "ان", "أن", "إن", "كان", "كانت",
    "يتم", "تم", "له", "لها", "منها", "فيها", "منه", "فيه", "الى", "أي",
    "the", "of", "in", "to", "and", "or", "is", "are", "for", "on", "at",
}


def _norm(text: str) -> str:
    s = unicodedata.normalize("NFKC", str(text))
    s = s.replace("\u0640", "")  # tatweel
    s = s.lower()
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    s = s.replace("ة", "ه").replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي")
    s = re.sub(r"[^\w\u0600-\u06FF\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _tokens(text: str) -> list[str]:
    out = []
    for tok in _norm(text).split():
        if tok in _STOPWORDS or len(tok) < 2:
            continue
        out.append(tok)
    return out


@dataclass
class NotesChunk:
    page: int
    chunk_id: int
    text: str
    score: float = 0.0


_AR_EN_GLOSSARY: dict[str, str] = {
    "إيرادات": "revenues revenue", "الإيرادات": "revenues revenue",
    "ربح": "profit", "أرباح": "profit earnings", "الربح": "profit",
    "خسارة": "loss", "الخسارة": "loss",
    "ضريبة": "tax income", "الضرائب": "tax", "الضريبة": "tax",
    "نقدية": "cash", "النقدية": "cash", "نقدا": "cash",
    "قروض": "loans borrowings", "قرض": "loans",
    "التزامات": "liabilities liabilities", "الالتزامات": "liabilities",
    "أصول": "assets", "الأصول": "assets",
    "حقوق الملكية": "equity", "حقوق الملكيه": "equity",
    "تدفقات": "cash flows", "التدفقات النقدية": "cash flows",
    "تشغيل": "operating operating activities",
    "استثمار": "investing investment", "استثمارات": "investments",
    "تمويل": "financing", "التمويلية": "financing activities",
    "مخاطر": "risk risks", "المخاطر": "risks risk",
    "سياسات محاسبية": "accounting policies",
    "السياسات المحاسبية": "accounting policies",
    "مجلس الإدارة": "board of directors",
    "مجموعة": "group consolidated", "الشركات التابعة": "subsidiaries",
    "مستحق": "accrued", "مخصص": "provision provisions",
    "مبيعات": "revenue sales", "المخزون": "inventory inventories",
    "ذمم مدينة": "receivables debtors", "ذمم دائنة": "payables creditors",
    "عجز": "deficit", "فائض": "surplus",
    "ربحية السهم": "earnings per share",
    "مجمد": "impairment", "مماطلة": "impairment",
}


def _expand_query(question: str) -> str:
    """The question + glossary expansions for any Arabic finance term found
    in it (cross-language retrieval without a translation service)."""
    expanded = question
    low = question.lower()
    for ar, en in _AR_EN_GLOSSARY.items():
        if ar in question or ar in low:
            expanded = f"{expanded} {en}"
    return expanded






@dataclass
class NotesIndex:
    """TF-IDF index over notes-page chunks. Built once per analyzed file."""
    chunks: list[NotesChunk] = field(default_factory=list)
    _df: dict[str, int] = field(default_factory=dict)
    _tf: list[dict[str, float]] = field(default_factory=list)
    _norms: list[float] = field(default_factory=list)

    # ── building ──
    @classmethod
    def from_pages(cls, pages_text: dict[int, str]) -> "NotesIndex":
        """pages_text: {page_number: page text (markdown/plain)}."""
        idx = cls()
        for page in sorted(pages_text):
            text = (pages_text[page] or "").strip()
            if not text:
                continue
            # Input hygiene (تدقيق RAG — المهمة 3): Indra's markdown wraps
            # tables in HTML tags; the tag tokens («td», «tr», «th»)
            # pollute the TF-IDF space and push the PRIMARY statement
            # pages out of every retrieval. Strip the tags BEFORE chunking
            # so the printed numbers become the searchable content.
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"[ 	]{2,}", " ", text)
            # split into paragraph-like chunks (blank lines / table rows kept
            # together per block); a chunk ≈ 3-6 lines keeps sources precise
            blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
            if not blocks:
                continue
            # merge tiny blocks so single table rows don't become chunks
            merged: list[str] = []
            buf = ""
            for b in blocks:
                buf = (buf + "\n" + b).strip()
                if len(buf) >= 120:
                    merged.append(buf)
                    buf = ""
            if buf:
                merged.append(buf)
            for chunk_id, chunk in enumerate(merged):
                idx.chunks.append(NotesChunk(page=page, chunk_id=chunk_id, text=chunk))
        idx._build()
        return idx

    def _build(self) -> None:
        n_docs = len(self.chunks)
        if n_docs == 0:
            return
        doc_freq: dict[str, int] = {}
        tfs: list[dict[str, float]] = []
        for ch in self.chunks:
            tf: dict[str, float] = {}
            for tok in _tokens(ch.text):
                tf[tok] = tf.get(tok, 0.0) + 1.0
            tfs.append(tf)
            for tok in tf:
                doc_freq[tok] = doc_freq.get(tok, 0) + 1
        self._tf = tfs
        self._df = doc_freq
        self._norms = []
        for tf in tfs:
            norm = math.sqrt(sum((w * (1.0 + math.log(n_docs / doc_freq[tok]))) ** 2
                                 for tok, w in tf.items()))
            self._norms.append(norm if norm else 1.0)

    # ── search ──

# Minimal bilingual finance glossary (المهمة 1 — أقل تعديل ممكن على RAG
# الموجود): expands the QUERY tokens with the other language's equivalents
# so an Arabic question can retrieve from English-translation notes and
# vice versa. No translation service, no new library — a fixed term map.
    def search(self, question: str, top_k: int = 5) -> list[NotesChunk]:
        if not self.chunks:
            return []
        q_tf: dict[str, float] = {}
        for tok in _tokens(_expand_query(question)):
            q_tf[tok] = q_tf.get(tok, 0.0) + 1.0
        if not q_tf:
            return []
        n_docs = len(self.chunks)
        q_norm = math.sqrt(sum(w * w for w in q_tf.values())) or 1.0
        scored: list[NotesChunk] = []
        for i, tf in enumerate(self._tf):
            dot = 0.0
            for tok, qw in q_tf.items():
                if tok not in tf:
                    continue
                idf = 1.0 + math.log(n_docs / self._df[tok])
                dot += qw * tf[tok] * idf
            score = dot / (q_norm * self._norms[i])
            if score > 0:
                scored.append(NotesChunk(page=self.chunks[i].page,
                                         chunk_id=self.chunks[i].chunk_id,
                                         text=self.chunks[i].text, score=round(score, 4)))
        scored.sort(key=lambda c: c.score, reverse=True)
        return scored[:top_k]

    def stats(self) -> dict:
        pages = sorted({c.page for c in self.chunks})
        return {"chunks": len(self.chunks), "pages": pages}


def formulate_answer(question: str, chunks: list[NotesChunk], company: str = "") -> str | None:
    """Gemini-formulated Arabic answer over the retrieved chunks, quoting the
    source page after every claim. None on ANY failure — the caller then
    falls back to showing the retrieved chunks verbatim (never nothing)."""
    if not chunks:
        return None
    try:
        import src.config  # noqa: F401  (loads .env keys)
        from google.genai import types
        from src.ai.gemini_agent import classify_gemini_error, get_pool
        from src.ai.key_pool import (
            adapt_config_for_model,
            classify_quota_scope,
            get_genai_client,
            mark_thinking_budget_unsupported,
        )

        pool = get_pool()
        if not pool.has_usable_pairs():
            return None
        sources = "\n\n".join(f"[صفحة {c.page}]\n{c.text}" for c in chunks)
        prompt = (
            "أنت محلل مالي خبير. أجب على السؤال التالي بالعربية اعتمادًا حصريًا على "
            "مقاطع الإيضاحات المتممة المرفقة من قوائم الشركة، واذكر رقم الصفحة المصدر "
            "بين قوسين بعد كل معلومة. إن لم يكن الجواب موجودًا في المقاطع فقل ذلك "
            "صراحة — لا تخترع ولا تستنتج أرقامًا. اكتب الإجابة كفقرة نثرية عربية "
            "مباشرة — بلا JSON ولا جداول HTML ولا أسوار كود.\n\n"
            + (f"الشركة: {company}\n" if company else "")
            + f"السؤال: {question}\n\nمقاطع الإيضاحات:\n{sources}"
        )
        base_cfg = types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=1024,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
        raw = None
        started = time.perf_counter()
        max_attempts = max(pool.total_pairs, 1)
        for _ in range(max_attempts):
            if time.perf_counter() - started > 7.5:
                break
            picked = pool.pick()
            if picked is None:
                break
            state, model = picked
            t0 = time.perf_counter()
            try:
                client = get_genai_client(state.key, timeout_ms=10_000)
                eff_cfg = adapt_config_for_model(base_cfg, model)
                try:
                    resp = client.models.generate_content(
                        model=model, contents=prompt, config=eff_cfg
                    )
                except Exception as exc_inner:
                    low_i = str(exc_inner).lower()
                    if (
                        getattr(eff_cfg, "thinking_config", None) is not None
                        and ("400" in low_i or "invalid_argument" in low_i)
                    ):
                        mark_thinking_budget_unsupported(model)
                        resp = client.models.generate_content(
                            model=model,
                            contents=prompt,
                            config=adapt_config_for_model(base_cfg, model),
                        )
                    else:
                        raise
                elapsed = time.perf_counter() - t0
                pool.mark_success(state.key)
                pool.record_call(model, elapsed)
                raw = (resp.text or "").strip()
                break
            except Exception as exc:
                fail_ms = (time.perf_counter() - t0) * 1000.0
                kind = classify_gemini_error(exc)
                pool.record_failover(fail_ms)
                if kind == "quota":
                    scope, cd_s = classify_quota_scope(exc)
                    if scope == "rpm":
                        pool.mark_rpm_limited(state.key, model, cd_s)
                    else:
                        pool.mark_quota_exhausted(state.key, model)
                elif kind == "auth":
                    pool.mark_dead(state.key, str(exc)[:200])
                elif kind == "model":
                    low_e = str(exc).lower()
                    pool.mark_model_unavailable(
                        state.key,
                        model,
                        str(exc)[:200],
                        all_keys=("no longer available" in low_e or "models/" in low_e),
                    )
                else:
                    pool.mark_transient_failure(model)
                continue
        if not raw:
            return None
        cleaned = raw.strip()
        if cleaned.startswith("```"):  # fenced ```json blocks → plain prose
            cleaned = cleaned.split("```")[-2] if cleaned.count("```") >= 2 else cleaned[3:]
            cleaned = cleaned[4:] if cleaned.startswith("json") else cleaned
            cleaned = cleaned.strip()
        # The flash model often wraps even prose in a JSON object or list — flatten it:
        # collect every string value recursively and join as paragraphs.
        if cleaned.startswith(("{", "[")):
            try:
                obj = json.loads(cleaned)
                if isinstance(obj, dict) and set(obj.keys()) == {"error"}:
                    return None
                if isinstance(obj, list) and all(
                    isinstance(x, dict) and set(x.keys()) == {"error"} for x in obj
                ):
                    return None

                def _strings(o):
                    if isinstance(o, str):
                        return [o]
                    if isinstance(o, dict):
                        return [s for k, v in o.items() if k != "error" for s in _strings(v)]
                    if isinstance(o, list):
                        return [s for v in o for s in _strings(v)]
                    return []

                parts = [s.strip() for s in _strings(obj) if s and s.strip()]
                if parts:
                    cleaned = "\n\n".join(parts)
            except json.JSONDecodeError:
                pass
        return cleaned or None
    except Exception:
        return None


_FINANCE_KEYWORDS = (
    "سياسه", "سياسة", "اهلاك", "إهلاك", "استهلاك", "اقساط", "قرض", "قروض",
    "التزام", "التزامات", "ذمم", "مدينين", "مخصص", "مخصصات", "ضريبه", "ضريبة",
    "تاجير", "تأجير", "مسيطر", "مخزون", "تقييم", "محاسبي", "محاسبيه", "تمويل",
    "dividend", "loan", "provision", "policy", "depreciation", "impairment",
    "contingenc", "aging", "guarantee",
)


def build_notes_digest(pages_text: dict[int, str], max_chunks: int = 12,
                       chars_per_chunk: int = 350) -> list[dict]:
    """Select the most finance-relevant notes chunks for the commentary payload.

    Keyword-scored over the full chunk set (the same chunks the RAG tab
    searches), capped and trimmed so the payload stays compact. Every chunk
    carries its source page — the commentary can cite where it came from.
    """
    idx = NotesIndex.from_pages(pages_text)
    scored = []
    for ch in idx.chunks:
        norm = _norm(ch.text)
        score = sum(1 for kw in _FINANCE_KEYWORDS if kw in norm)
        if score:
            scored.append((score, ch))
    scored.sort(key=lambda t: (-t[0], t[1].page))
    out = []
    for score, ch in scored[:max_chunks]:
        text = ch.text[:chars_per_chunk].strip()
        out.append({"page": ch.page, "relevance": score, "text": text})
    return out
