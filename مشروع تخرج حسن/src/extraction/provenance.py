# -*- coding: utf-8 -*-
"""Source-aware provenance (إسناد مصدر القيمة — من أين جاءت القيمة).

Separates two things the old gate conflated:
  1. WHERE a value came from (the SOURCE: scanned OCR, native PDF text,
     a spreadsheet cell, a vision model, a derivation, a human review)
  2. HOW WELL IT IS VERIFIED (the status ladder in financial_gate)

A deterministic read of a digital cell proves faithful TRANSFER of the
printed value — it does NOT prove the company's number is economically
correct. `VERIFIED_SOURCE_EXACT` is therefore granted ONLY when the full
evidence checklist passes: file hash, sheet, cell address, field label,
fiscal year, data type, unit-of-measure sanity, negative-sign sanity,
no merged-cell ambiguity. Cached formula values are granted WITH an
explicit staleness disclosure; anything short is left to the normal
verification ladder (or a human review).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

SOURCE_SCANNED_OCR = "SCANNED_OCR"
SOURCE_NATIVE_PDF_TEXT = "NATIVE_PDF_TEXT"
SOURCE_NATIVE_SPREADSHEET_CELL = "NATIVE_SPREADSHEET_CELL"
SOURCE_VISION_MODEL = "VISION_MODEL"
SOURCE_DERIVED = "DERIVED"
SOURCE_HUMAN_REVIEWED = "HUMAN_REVIEWED"

ALL_SOURCES = (SOURCE_SCANNED_OCR, SOURCE_NATIVE_PDF_TEXT,
               SOURCE_NATIVE_SPREADSHEET_CELL, SOURCE_VISION_MODEL,
               SOURCE_DERIVED, SOURCE_HUMAN_REVIEWED)

DIGITAL_SOURCES = (SOURCE_NATIVE_PDF_TEXT, SOURCE_NATIVE_SPREADSHEET_CELL)

# header words that mean the printed numbers are SCALED (أرقام مقسومة) —
# reading them as absolute units would be a unit-of-measure error
_SCALE_WORDS = ("آلاف", "الآلاف", "ألف", "مليون", "ملايين", "thousand",
                "million", "'000", "000'")

# title words that declare the statements' consolidation scope
_CONSOLIDATED_WORDS = ("القوائم المالية الموحدة", "المالية المجمعة",
                       "consolidated")
_STANDALONE_WORDS = ("القوائم المالية المستقلة", "المستقلة", "standalone",
                     "separate")


@dataclass
class CellEvidence:
    """What we can PROVE about where one captured value came from."""
    source: str
    file_sha256: str | None = None
    file_name: str | None = None
    sheet: str | None = None
    cell_address: str | None = None
    label_text: str | None = None
    year: int | None = None
    data_type: str = "value"          # value | formula_cached | percent | text
    unit_hint: str | None = None      # scale words found near the table header
    is_merged: bool = False           # the address sits inside a merged range
    sign_normalized: bool = False     # a negative print was flipped by |x|
    cached_formula: bool = False      # value came from a formula's cache
    consolidation: str | None = None  # standalone | consolidated | None
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "source": self.source, "file_sha256": self.file_sha256,
            "file_name": self.file_name, "sheet": self.sheet,
            "cell_address": self.cell_address, "label_text": self.label_text,
            "year": self.year, "data_type": self.data_type,
            "unit_hint": self.unit_hint, "is_merged": self.is_merged,
            "sign_normalized": self.sign_normalized,
            "cached_formula": self.cached_formula,
            "consolidation": self.consolidation, "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CellEvidence":
        base = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**base)


def file_sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sniff_consolidation(text: str) -> str | None:
    """standalone | consolidated | None — from the document/title wording."""
    low = text.lower()
    if any(w in low for w in _CONSOLIDATED_WORDS):
        return "consolidated"
    if any(w in low for w in _STANDALONE_WORDS):
        return "standalone"
    return None


def sniff_scale_words(text: str) -> str | None:
    low = text.lower()
    for w in _SCALE_WORDS:
        if w in low:
            return w
    return None


def evaluate_source_evidence(
    ev: CellEvidence, expected_year: int | None = None,
) -> tuple[bool, list[str]]:
    """The VERIFIED_SOURCE_EXACT checklist. Returns (eligible, failures).

    Empty/unknown unit is NOT a blocker (no claim is made); a DETECTED scale
    word IS a blocker unless the field is a ratio — reading «بالآلاف»
    numbers as absolute pounds is exactly the wrong-unit case the audit
    bans. Merged cells, text/percent types, flipped signs, missing
    hash/sheet/address/label/year, and a year mismatch all block.
    """
    failures: list[str] = []
    if ev.source not in DIGITAL_SOURCES:
        failures.append(f"المصدر {ev.source} ليس مصدرًا رقميًا مباشرًا")
    if not ev.file_sha256:
        failures.append("بصمة الملف مفقودة")
    if not ev.sheet:
        failures.append("اسم ورقة العمل مفقود")
    if not ev.cell_address:
        failures.append("عنوان الخلية مفقود")
    if not ev.label_text:
        failures.append("عنوان البند المالي مفقود")
    if ev.year is None:
        failures.append("السنة المالية غير محسومة")
    elif expected_year is not None and int(ev.year) != int(expected_year):
        failures.append(f"السنة في الدليل ({ev.year}) لا تطابق سنة القرار "
                        f"({expected_year})")
    if ev.data_type in ("text", "percent"):
        failures.append(f"نوع البيانات {ev.data_type} ليس مبلغًا ماليًا")
    if ev.is_merged:
        failures.append("الخلية مدمجة — عنوان القيمة غير حاسم")
    if ev.sign_normalized:
        failures.append("الإشارة السالبة في المصدر قُلبت عند الالتقاط — "
                        "لا يُمنح توثيق النقل الحرفي")
    if ev.unit_hint and ev.data_type == "value":
        failures.append(f"وحدة القياس تشير لتقسيم ({ev.unit_hint}) — "
                        "القيمة ليست بوحدات مطلقة")
    return (not failures), failures


def evidence_reason(ev: CellEvidence) -> str:
    """The decision-log reason: what the reader can AUDIT, plus the honesty
    rule — faithful transfer, not economic truth."""
    parts = [f"نقل حرفي موثق من مصدر رقمي ({ev.source})"]
    if ev.file_sha256:
        parts.append(f"بصمة الملف {ev.file_sha256[:12]}…")
    if ev.file_name:
        parts.append(f"«{ev.file_name}»")
    if ev.sheet:
        parts.append(f"ورقة «{ev.sheet}»")
    if ev.cell_address:
        parts.append(f"خلية {ev.cell_address}")
    if ev.label_text:
        parts.append(f"البند «{ev.label_text}»")
    if ev.year:
        parts.append(f"سنة {ev.year}")
    if ev.cached_formula:
        parts.append("⚠ قيمة مخزنة لمعادلة (cached) — قد تقادم إذا أُعيد "
                     "حساب الملف")
    if ev.consolidation:
        parts.append(f"نطاق {('مستقلة' if ev.consolidation == 'standalone'
                                   else 'موحدة/مجمعة')}")
    parts.append("دليل نقل القيمة من المصدر بدقة — ليس إثبات صحة القيمة "
                 "اقتصاديًا")
    return " — ".join(parts)
