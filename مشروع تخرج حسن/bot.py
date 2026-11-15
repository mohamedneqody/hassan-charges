# -*- coding: utf-8 -*-
"""بوت تليجرام — يشغل محرك تحليل القوائم المالية من الموبايل.

ترسل PDF/Excel/CSV من الشات → المحرك يحلل (بنفس بوابة الصدق) → يرجعلك
ملخص عربي + تقرير Excel + تقرير HTML. يعمل محليًا على جهازك (long-polling
صادر فقط — لا بورتات مفتوحة).

الإعداد (دقيقتان):
1. على تليجرام: @BotFather → /newbot → انسخ الـTOKEN
2. في ملف .env: TELEGRAM_BOT_TOKEN=123456:ABC...
3. (اختياري) TELEGRAM_ALLOWED_IDS=123456789 — حصر من يتحدث للبوت
   (فاضي = مفتوح للجميع؛ اجعله معرفك من @userinfobot في الاستخدام الفعلي)
4. شغّل:  .venv\\Scripts\\python.exe bot.py

بلا مكتبات جديدة: requests موجودة أصلًا في البيئة.
"""
from __future__ import annotations

import io
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

import requests  # noqa: E402

from src.analysis.narrative import build_fallback_narrative  # noqa: E402
from src.dashboard.excel_report import build_excel_report  # noqa: E402
from src.analysis.score import compute_health_score  # noqa: E402
from src.dashboard.report import build_html_report  # noqa: E402
from src.exceptions import AppError, InsufficientDataError  # noqa: E402
from src.pipeline import run_pipeline  # noqa: E402

BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
ALLOWED_IDS = {
    s.strip() for s in (os.getenv("TELEGRAM_ALLOWED_IDS") or "").split(",")
    if s.strip()
}
API = f"https://api.telegram.org/bot{BOT_TOKEN}"
INBOX = PROJECT_ROOT / "inbox" / "telegram"
ALLOWED_EXTS = {".pdf", ".xlsx", ".xls", ".csv"}
MAX_BYTES = 20 * 1024 * 1024  # حد تليجرام للملفات

_MODES: dict[str, str] = {}  # chat_id → "fast" | "precise"


# ─────────────────────────── Telegram API (stdlib-level) ───────────────────

def _tg(method: str, payload: dict | None = None,
        files: dict | None = None, timeout: int = 40) -> dict | None:
    """نداء تليجرام واحد — لا شيء يقتل الحلقة."""
    try:
        if files:
            r = requests.post(f"{API}/{method}", data=payload or {},
                              files=files, timeout=timeout)
        else:
            r = requests.post(f"{API}/{method}", json=payload or {},
                              timeout=timeout)
        return r.json()
    except Exception as exc:
        print(f"⚠ telegram {method}: {type(exc).__name__}: {exc}")
        return None


def _download_file(file_id: str) -> bytes | None:
    """تنزيل ملف من تليجرام — بفحص صارم: getFile.ok + ترميز المسار
    (أسماء عربية!) + رفض ردود الخطأ JSON (كانت بتتكتب ملفًا!)."""
    from urllib.parse import quote

    try:
        meta = _tg("getFile", {"file_id": file_id}, timeout=30)
        if not meta or not meta.get("ok"):
            print(f"⚠ getFile failed: {str(meta)[:200]}")
            return None
        fpath = ((meta or {}).get("result") or {}).get("file_path")
        if not fpath:
            print(f"⚠ getFile: no file_path — {str(meta)[:200]}")
            return None
        # المسار العربي لازم يتشفر — وإلا 404 ورد الخطأ يتكتب ملفًا
        url = f"{API}/file/{BOT_TOKEN}/{quote(str(fpath), safe='/')}"
        r = requests.get(url, timeout=120)
        if r.status_code != 200:
            print(f"⚠ download HTTP {r.status_code}: {r.content[:120]!r}")
            return None
        content = r.content
        if content[:1] == b"{" and b'"ok":false' in content[:60]:
            print(f"⚠ download got an API error instead of the file: "
                  f"{content[:160]!r}")
            return None
        return content or None
    except Exception as exc:
        print(f"⚠ download: {type(exc).__name__}: {exc}")
        return None


_MAGIC_OK = {
    ".xlsx": lambda b: b[:2] == b"PK",
    ".xls": lambda b: b[:4] == bytes.fromhex("d0cf11e0"),
    ".csv": lambda b: not b[:1] == b"{",
    ".pdf": lambda b: b[:4] == b"%PDF",
}


def magic_matches(ext: str, content: bytes) -> bool:
    """هل بايتات الملف تطابق امتداده المعلن؟ — رد خطأ JSON/HTML يمسك
    قبل ما يوصل للمحرك بخطأ pandas غامض."""
    check = _MAGIC_OK.get(ext)
    return check(content) if check else True


# ─────────────────────────── منطق التحليل (قابل للاختبار) ──────────────────

def build_result_summary(results: dict, currency: str = "ج.م") -> str:
    """ملخص عربي مختصر من نتائج run_pipeline — بلا أي اختراع."""
    company = results.get("company") or "الشركة"
    years = results.get("metric_years_available") or []
    vm_cell = {
        "decisive": None, "pending": None,
    }
    m = results.get("curr_metrics")
    lines = [
        f"📊 **{company}** — السنة المالية {results.get('curr_year')}",
        f"السنوات: {', '.join(str(y) for y in years) or '—'}",
        "",
    ]

    def _val(label: str, v, pct: bool = False, suffix: str = "") -> None:
        if v is None:
            lines.append(f"• {label}: غير متوفر")
        else:
            lines.append(f"• {label}: {v:,.2f}{suffix}" if pct
                         else f"• {label}: {v:,.0f} {currency}{suffix}")

    _val("الإيرادات", getattr(m, "revenue", None))
    _val("صافي الربح", getattr(m, "net_income", None))
    cr = getattr(m, "current_ratio", None)
    lines.append("• نسبة التداول: " + (f"{cr:,.2f}x" if cr is not None
                                       else "غير متوفر"))
    de = getattr(m, "debt_to_equity", None)
    lines.append("• الدين إلى حقوق الملكية: " + (f"{de:,.2f}x" if de is not None
                                                 else "غير متوفر"))
    roe = getattr(m, "roe", None)
    lines.append("• العائد على حقوق الملكية: " + (f"{roe:,.1f}%" if roe is not None
                                                  else "غير متوفر"))

    # حالة التحقق — صدق البوابة
    log = results.get("decision_log") or []
    decisive = sum(1 for e in log
                   if e.get("status") in ("VERIFIED_EXACT", "VERIFIED_DERIVED",
                                          "VERIFIED_SOURCE_EXACT",
                                          "VERIFIED_HUMAN"))
    pending = sum(1 for e in log if e.get("status") in
                  ("UNVERIFIED", "CONFLICT", "MULTI_ROW"))
    lines += ["", f"🔒 الخانات الحاسمة: {decisive} | تحتاج مراجعة: {pending}"]
    lines.append("_القيم المؤكدة فقط هي التي حُسمت بتحقق مستقل — "
                 "الباقي محجوب بعلن حسب بوابة الصدق._")
    return "\n".join(lines)


def analyze_document(file_name: str, raw: bytes,
                     mode: str) -> tuple[str, bytes | None, bytes | None]:
    """شغّل المحرك على الملف وأعد (الملخص، Excel bytes، HTML bytes)."""
    fast = mode == "fast"
    results = run_pipeline(file_name, raw, company="",
                           fast_mode=fast)
    summary = build_result_summary(results)
    note = ("⚡ الوضع السريع — أعد بالوضع الدقيق (/mode) للتحقق المزدوج"
            if fast else
            "🔬 الوضع الدقيق — تحقق مركزي كامل")
    summary = note + "\n\n" + summary
    xlsx = build_excel_report(results)

    # تقرير HTML بالسرد الاحتياطي الحتمي (بلا نداء تعليق — سرعة البوت)
    analysis = build_fallback_narrative(results, type(
        "A", (), {"ok": False, "error": "", "ratio_comments": [],
                  "recommendations": [], "model": "fallback"}))
    html = build_html_report(
        results, analysis,
        score=compute_health_score(results.get("curr_metrics")),
        currency=results.get("currency_hint") or "ج.م")
    return summary, xlsx, html.encode("utf-8")


def allowed(chat_id: str) -> bool:
    return (not ALLOWED_IDS) or (chat_id in ALLOWED_IDS)


# ─────────────────────────── الحلقة الرئيسية ───────────────────────────────

def handle_update(update: dict) -> None:
    msg = update.get("message") or update.get("edited_message") or {}
    chat = str((msg.get("chat") or {}).get("id", ""))
    text = (msg.get("text") or "").strip()
    doc = msg.get("document")

    if chat and not allowed(chat):
        _tg("sendMessage", {"chat_id": chat, "text":
                            "🔒 هذا البوت مخصص لمعرّفات محددة. "
                            "معرفك من @userinfobot."})
        return

    if text.startswith("/start") or text.startswith("/help"):
        _tg("sendMessage", {"chat_id": chat, "text":
                            "🤖 *بوت تحليل القوائم المالية*\n\n"
                            "ارسل ملف PDF / Excel / CSV (قوائم مالية) "
                            "وأرجعلك الملخص + تقرير Excel + تقرير HTML.\n\n"
                            "/mode — تبديل بين الوضع السريع (~5 دقائق) "
                            "والدقيق (~8 دقائق)\n"
                            "الوضع الحالي: "
                            + ("⚡ سريع" if _MODES.get(chat) == "fast"
                               else "🔬 دقيق"),
                            "parse_mode": "Markdown"})
        return

    if text.startswith("/mode"):
        new_mode = "fast" if _MODES.get(chat) != "fast" else "precise"
        _MODES[chat] = new_mode
        _tg("sendMessage", {"chat_id": chat, "text":
                            ("⚡ الوضع السريع (~5 دقائق) — طبقات تحقق أقل "
                             "والتدفقات غير متاحة"
                             if new_mode == "fast" else
                             "🔬 الوضع الدقيق (~8 دقائق) — تحقق مركزي كامل")})
        return

    if doc:
        fname = doc.get("file_name") or "file"
        ext = Path(fname).suffix.lower()
        size = int(doc.get("file_size") or 0)
        if ext not in ALLOWED_EXTS:
            _tg("sendMessage", {"chat_id": chat, "text":
                                f"❌ الامتداد {ext or 'غير معروف'} غير مدعوم — "
                                "ارسل PDF / Excel / CSV."})
            return
        if size > MAX_BYTES:
            _tg("sendMessage", {"chat_id": chat, "text":
                                f"❌ الملف كبير ({size / 1e6:.1f}MB) — حد "
                                "تليجرام 20MB للملفات."})
            return
        _tg("sendMessage", {"chat_id": chat, "text":
                            f"📥 استلمت {fname} — جارٍ التحليل "
                            f"(الوضع {'⚡ سريع' if _MODES.get(chat) == 'fast' else '🔬 دقيق'})…"
                            " قد يستغرق عدة دقائق."})
        raw = _download_file(doc.get("file_id"))
        if not raw:
            _tg("sendMessage", {"chat_id": chat, "text":
                                "❌ فشل تنزيل الملف من تليجرام — حاول مرة أخرى، "
                                "وتأكد أنك أرسلته كـ Document (مش صورة/ضغط)."})
            return
        if not magic_matches(ext, raw[:16]):
            _tg("sendMessage", {"chat_id": chat, "text":
                                f"❌ الملف اللي وصل تالف أو مش {ext} فعلًا "
                                f"(أول البايتات: {raw[:12]!r}) — أرسله كـ "
                                "Document من مصدره الأصلي، مش مُعاد تسميته."})
            return
        inbox = INBOX / chat
        inbox.mkdir(parents=True, exist_ok=True)
        (inbox / fname).write_bytes(raw)

        try:
            summary, xlsx, html = analyze_document(fname, raw,
                                                   _MODES.get(chat, "precise"))
        except InsufficientDataError as exc:
            _tg("sendMessage", {"chat_id": chat, "text":
                                f"❌ {exc}\n\nتأكد أن الملف قوائم مالية فيها "
                                "سنتان على الأقل وأرقام مقروءة."})
            return
        except AppError as exc:
            _tg("sendMessage", {"chat_id": chat, "text": f"❌ {exc}"})
            return
        except Exception as exc:
            _tg("sendMessage", {"chat_id": chat, "text":
                                f"❌ خطأ غير متوقع: {type(exc).__name__} — "
                                "جرب الوضع الدقيق أو ملفاً أوضح."})
            return

        _tg("sendMessage", {"chat_id": chat, "text": summary,
                            "parse_mode": "Markdown"})
        if xlsx:
            _tg("sendDocument",
                {"chat_id": chat,
                 "caption": f"📊 التقرير الشامل — {fname}"},
                files={"document": (f"{Path(fname).stem}_تحليل.xlsx",
                                    io.BytesIO(xlsx))}, timeout=300)
        if html:
            _tg("sendDocument",
                {"chat_id": chat,
                 "caption": "🌐 تقرير HTML (افتحه في المتصفح)"},
                files={"document": (f"{Path(fname).stem}_report.html",
                                    io.BytesIO(html))}, timeout=300)
        return

    if text:
        _tg("sendMessage", {"chat_id": chat, "text":
                            "ارسل ملف PDF / Excel / CSV لتحليله، أو /help للمساعدة."})


def main() -> None:
    if not BOT_TOKEN:
        print("=" * 60)
        print("TELEGRAM_BOT_TOKEN غير موجود في .env")
        print("1) على تليجرام: تحدث مع @BotFather → /newbot")
        print("2) انسخ الـTOKEN")
        print("3) في .env أضف:  TELEGRAM_BOT_TOKEN=123456:ABC...")
        print("4) شغّل مرة أخرى:  .venv\\Scripts\\python.exe bot.py")
        print("=" * 60)
        sys.exit(1)

    me = _tg("getMe", timeout=15)
    if not me or not me.get("ok"):
        print("❌ الـTOKEN مرفوض من تليجرام — تحقق منه في .env")
        sys.exit(1)
    username = (me.get("result") or {}).get("username")
    print("=" * 60)
    print(f"🤝 البوت يعمل: @{username}")
    print(f"   الوضع الافتراضي: 🔬 دقيق (بدّل بـ/mode)")
    print(f"   المسموح: {'الجميع' if not ALLOWED_IDS else ALLOWED_IDS}")
    print("   اضغط Ctrl+C للإيقاف")
    print("=" * 60)

    offset = 0
    while True:
        updates = _tg("getUpdates",
                      {"timeout": 25, "offset": offset}, timeout=35)
        for u in (updates or {}).get("result") or []:
            offset = max(offset, int(u.get("update_id", 0)) + 1)
            try:
                handle_update(u)
            except Exception as exc:
                print(f"⚠ update error: {type(exc).__name__}: {exc}")
        time.sleep(0.2)


if __name__ == "__main__":
    main()
