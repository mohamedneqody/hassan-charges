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


def _tg_token_for_test():
    return BOT_TOKEN
ALLOWED_IDS = {
    s.strip() for s in (os.getenv("TELEGRAM_ALLOWED_IDS") or "").split(",")
    if s.strip()
}
API = f"https://api.telegram.org/bot{BOT_TOKEN}"
INBOX = PROJECT_ROOT / "inbox" / "telegram"
ALLOWED_EXTS = {".pdf", ".xlsx", ".xls", ".csv"}
MAX_BYTES = 20 * 1024 * 1024  # حد تليجرام للملفات

_MODES: dict[str, str] = {}  # chat_id → "fast" | "precise"

# حرس النسخة الواحدة: 4 نسخ بوت كانت شغالين مع بعض (كل تشغيل سابق سبت
# عملية حية) — تليجرام قسم التحديثات بينهم فتكررت الردود واختلطت
# الإصدارات. قفل ملفي بالـPID يمنع التشغيل المزدوج نهائيًا.
_LOCK = PROJECT_ROOT / "bot.lock"


def _pid_alive(pid_str: str) -> bool:
    """هل العملية بالـPID القديم ما زالت حية؟ — ويندوز عبر tasklist، لينكس عبر os.kill(0)"""
    if not pid_str.isdigit():
        return False
    pid = int(pid_str)
    if os.name == "nt":
        import subprocess
        try:
            r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                               capture_output=True, text=True, timeout=10)
            return pid_str in r.stdout
        except (OSError, subprocess.SubprocessError):
            return False  # تعذر الفحص — اعتبرها ميتة حتى لا يعلق البوت
    try:
        os.kill(pid, 0)  # على لينكس: إشارة 0 = فحص حياة فقط
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # حية لكن لا نملك إشارة إليها
    except OSError:
        return False


def _single_instance() -> bool:
    if _LOCK.exists():
        old_pid = _LOCK.read_text(encoding="utf-8").strip()
        if _pid_alive(old_pid):
            return False
        _LOCK.unlink(missing_ok=True)  # العملية القديمة ماتت — القفل باقي
    _LOCK.write_text(str(os.getpid()), encoding="utf-8")
    return True


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
        print(f"⬇ file_path = {fpath!r}")
        # الصيغة الموثقة: /file/bot{TOKEN}/{path} — التوكن مرة واحدة
        # (الخلط بين base-API الذي يحمل التوكن ونقطة /file/ كان يكرره
        # فيُرجع تليجرام 404 لملف موجود فعلًا!)
        url = (f"https://api.telegram.org/file/bot{BOT_TOKEN}/"
               f"{quote(str(fpath), safe='/')}")
        r = requests.get(url, timeout=120)
        print(f"⬇ download: HTTP {r.status_code} "
              f"({len(r.content)}B) {r.content[:60]!r}")
        if r.status_code == 200 and not (
                r.content[:1] == b"{" and b'"ok":false' in r.content[:60]):
            return r.content
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

def _clean_company(name: str) -> str:
    """تنظيف اسم الشركة من لاحقة العنوان العامة («الشركة — السنة المالية
    2025» كانت بتظهر اسمًا للشركة)."""
    import re
    return re.sub(r"\s*[—-]\s*السنة المالية.*$", "", str(name)).strip() or "الشركة"


def build_result_summary(results: dict, currency: str = "ج.م") -> str:
    """ملخص عربي غني: المؤشرات الأساسية + الصحة + الاتجاهات + التوصيات +
    حالة البوابة الصادقة — كل شيء محسوب، والتفصيل الكامل في المرفقات."""
    company = _clean_company(results.get("company") or "الشركة")
    years = results.get("metric_years_available") or []
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

    lines.append("💼 *المؤشرات الأساسية*")
    _val("الإيرادات", getattr(m, "revenue", None))
    _val("مجمل الربح", getattr(m, "gross_profit", None))
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
    roa = getattr(m, "roa", None)
    lines.append("• العائد على الأصول: " + (f"{roa:,.1f}%" if roa is not None
                                            else "غير متوفر"))
    npm = getattr(m, "net_profit_margin", None)
    lines.append("• هامش صافي الربح: " + (f"{npm:,.1f}%" if npm is not None
                                          else "غير متوفر"))

    # تقييم الصحة — نفس منطق الواجهة (مرفوض يظهر مرفوضًا بسببه)
    try:
        from src.analysis.financial_gate import decide
        from src.analysis.score import compute_health_score
        dl = results.get("decision_log") or []
        blocked = {
            e["field"] for e in dl
            if e.get("field") and decide(e.get("status", "MISSING")) not in ("use", "use_disclosed")
        }
        hs = compute_health_score(m, blocked_fields=blocked)
        if hs.total is not None:
            lines.append(f"🏥 تقييم الصحة المالية: {hs.total:.0f}/100")
        else:
            lines.append("🏥 تقييم الصحة: مرفوض — تغطية بيانات غير كافية "
                         "(الحاسم ناقص)")
    except Exception:
        pass

    # الاتجاهات المتحركة فقط (تحسّن/تراجع) — الثابت لا يضيف صوتًا
    rows = results.get("rows") or []
    moving = [r for r in rows
              if getattr(r, "trend", None) in ("improving", "declining")]
    if moving:
        lines.append("")
        lines.append("📈 *الاتجاهات*")
        arrow = {"improving": "▲", "declining": "▼"}
        for r in moving[:5]:
            lines.append(f"• {getattr(r, 'label_ar', None) or r.label}: "
                         f"{arrow.get(r.trend, '')} {r.trend}")

    # أعلى التوصيات من السرد الحتمي
    try:
        from src.analysis.narrative import build_recommendations
        recs = build_recommendations(results)
        if recs:
            lines.append("")
            lines.append("💡 *أهم التوصيات*")
            for action, _e in recs[:3]:
                lines.append(f"• {action}")
    except Exception:
        pass

    # حالة التحقق — صدق البوابة
    log = results.get("decision_log") or []
    decisive = sum(1 for e in log
                   if e.get("status") in ("VERIFIED_EXACT", "VERIFIED_DERIVED",
                                          "VERIFIED_SOURCE_EXACT",
                                          "VERIFIED_HUMAN"))
    pending = sum(1 for e in log if e.get("status") in
                  ("UNVERIFIED", "CONFLICT", "MULTI_ROW"))
    lines += ["", f"🔒 الخانات الحاسمة: {decisive} | تحتاج مراجعة: {pending}"]
    lines.append("_القيم المؤكدة فقط هي التي حُسمت بتحقق مستقل — التفصيل "
                 "الكامل (كل المؤشرات والنماذج والجداول) في ملفي Excel "
                 "وHTML المرفقين._")
    return "\n".join(lines)


def build_full_report_messages(results: dict, currency: str = "ج.م",
                               max_chars: int = 3800) -> list[str]:
    """التقرير الكامل كرسائل متعددة (حد تليجرام 4096 حرفًا) — نفس
    breadth الداشبورد: المؤشرات كلها + النماذج الأكاديمية + الصحة
    بأركانها + الأعلام الحمراء + Beneish + حالة التحقق لكل مؤشر.
    نص عادي (بلا Markdown) — الأسماء العربية والشرطات تكسر المحلل."""
    from src.analysis.academic_models import academic_models
    from src.analysis.redflags import red_flag_analysis, beneish_m_score
    from src.analysis.score import compute_health_score

    company = _clean_company(results.get("company") or "الشركة")
    m = results.get("curr_metrics")
    currency = results.get("currency_hint") or currency
    chunks: list[str] = []

    def flush(cur: list[str]) -> None:
        if cur:
            chunks.append("\n".join(cur))

    cur: list[str] = [f"📊 التقرير الكامل — {company}",
                      f"السنوات: {results.get('prev_year')} ← "
                      f"{results.get('curr_year')}", ""]

    # 1) المؤشرات الأساسية
    def _val(label, v, kind="currency"):
        if v is None:
            cur.append(f"• {label}: غير متوفر")
        elif kind == "currency":
            cur.append(f"• {label}: {v:,.0f} {currency}")
        elif kind == "pct":
            cur.append(f"• {label}: {v:,.1f}%")
        else:
            cur.append(f"• {label}: {v:,.2f}x")

    cur.append("💼 القائمة — الموجود والأرباح")
    _val("الإيرادات", getattr(m, "revenue", None))
    _val("تكلفة الإيرادات", getattr(m, "cost_of_revenue", None))
    _val("مجمل الربح", getattr(m, "gross_profit", None))
    _val("صافي الربح", getattr(m, "net_income", None))
    cur.append("💼 المركز المالي")
    _val("إجمالي الأصول", getattr(m, "total_assets", None))
    _val("المتداولة", getattr(m, "current_assets", None))
    _val("الالتزامات", getattr(m, "total_liabilities", None))
    _val("حقوق الملكية", getattr(m, "equity", None))
    cur.append("⚖️ النسب")
    for label, key, kind in (
            ("نسبة التداول", "current_ratio", "x"),
            ("السريعة", "quick_ratio", "x"),
            ("الدين إلى حقوق الملكية", "debt_to_equity", "x"),
            ("هامش صافي الربح", "net_profit_margin", "pct"),
            ("هامش التشغيل", "operating_margin", "pct"),
            ("ROE", "roe", "pct"), ("ROA", "roa", "pct"),
            ("دوران الأصول", "asset_turnover", "x")):
        _val(label, getattr(m, key, None), kind)

    # الصحة بأركانها
    try:
        from src.analysis.financial_gate import decide
        dl = results.get("decision_log") or []
        blocked = {
            e["field"] for e in dl
            if e.get("field") and decide(e.get("status", "MISSING")) not in ("use", "use_disclosed")
        }
        hs = compute_health_score(m, blocked_fields=blocked)
        cur.append("")
        if hs.total is not None:
            cur.append(f"🏥 الصحة المالية: {hs.total:.0f}/100 — {hs.label}")
        else:
            cur.append(f"🏥 الصحة: {hs.label}")
        for p in hs.pillars:
            sc = f"{p.score:.0f}/100" if p.score is not None else "N/A"
            cur.append(f"   ▪ {p.name} ({p.weight:.0%}): {sc}")
    except Exception:
        pass
    flush(cur)

    # 2) المؤشرات الكاملة (التغيرات + حالة التحقق لكل مؤشر)
    verif = results.get("verification_status") or {}
    cur = ["📋 المؤشرات الكاملة (السنة السابقة ← الحالية)"]
    for r in list(results.get("growth_rows") or []) + list(results.get("rows") or []):
        label = getattr(r, "label_ar", None) or r.label
        prev_v = getattr(r, "previous", None)
        curr_v = getattr(r, "current", None)
        kind = getattr(r, "kind", "currency")
        unit = currency if kind == "currency" else ("%" if kind == "percent" else "x")
        def _f(v):
            return f"{v:,.0f} {unit}" if v is not None else "غير متوفر"
        line = f"• {label}: {_f(prev_v)} ← {_f(curr_v)}"
        cp = getattr(r, "change_pct", None)
        if cp is not None:
            line += f" ({cp:+.1f}%)"
        line += f" [{r.trend_symbol} {r.status}]"
        vs = verif.get(r.key)
        if vs:
            line += f" | {vs}"
        cur.append(line)
        if len("\n".join(cur)) > max_chars:
            flush(cur)
            cur = ["📋 المؤشرات الكاملة (تتمة)"]
    flush(cur)

    # 3) النماذج الأكاديمية
    cur = ["🎓 النماذج الأكاديمية"]
    for mod in academic_models(m):
        cur.append(f"• {mod.icon} {mod.name}: {mod.value:g}"
                   if isinstance(mod.value, (int, float))
                   else f"• {mod.icon} {mod.name}")
        cur.append(f"   الحكم: {mod.verdict}")
        if mod.components:
            cur.append("   " + " · ".join(f"{k}={v:g}"
                                          for k, v in mod.components.items()))
        if mod.missing:
            cur.append(f"   بيانات ناقصة: {', '.join(mod.missing)}")
    flush(cur)

    # 4) الأعلام الحمراء + Beneish
    try:
        flags = red_flag_analysis(results.get("prev_metrics"),
                                  results.get("curr_metrics"))
        cur = ["🚩 الأعلام الحمراء"
               + (f" ({len(flags)} علم)" if flags else " — صفر 🎉")]
        for fl in flags:
            icon = {"high": "🔴", "medium": "🟠", "low": "🟡"}.get(
                fl.severity, "•")
            cur.append(f"• {icon} {fl.name}: {fl.detail}")
        bn = beneish_m_score(results.get("prev_metrics"),
                             results.get("curr_metrics"))
        if bn.m_score is None:
            cur.append("• Beneish M-Score: غير متوفر — بيانات ناقصة")
        else:
            cur.append(f"• Beneish M-Score: {bn.m_score:g} — {bn.verdict}")
        if bn.missing:
            cur.append(f"   بيانات ناقصة: {', '.join(bn.missing)}")
        flush(cur)
    except Exception:
        pass

    # 5) حالة التحقق الإجمالية
    log = results.get("decision_log") or []
    dec = sum(1 for e in log if e.get("status") in
              ("VERIFIED_EXACT", "VERIFIED_DERIVED",
               "VERIFIED_SOURCE_EXACT", "VERIFIED_HUMAN"))
    pend = sum(1 for e in log if e.get("status") in
               ("UNVERIFIED", "CONFLICT", "MULTI_ROW"))
    cur = [f"🔒 بوابة الصدق: الحاسمة {dec} | تحتاج مراجعة {pend} "
           f"| مفقود {len(results.get('missing') or [])}",
           "_كل قيمة حاسمة حُسمت بتحقق مستقل — الباقي ينتظر المراجعة "
           "البشرية._"]
    flush(cur)
    return chunks


def analyze_document(file_name: str, raw: bytes,
                     mode: str) -> tuple[dict, bytes | None, bytes | None]:
    """شغّل المحرك على الملف وأعد (results، Excel bytes، HTML bytes)."""
    from src.analysis.financial_gate import decide, verification_labels

    fast = mode == "fast"
    results = run_pipeline(file_name, raw, company="",
                           fast_mode=fast)
    dl = results.get("decision_log") or []
    blocked = {
        e["field"] for e in dl
        if e.get("field") and decide(e.get("status", "MISSING")) not in ("use", "use_disclosed")
    }
    if dl:
        results["blocked_fields"] = sorted(blocked)
        results["verification_status"] = verification_labels(dl)
    xlsx = build_excel_report(results)

    # تقرير HTML بالسرد الاحتياطي الحتمي (بلا نداء تعليق — سرعة البوت)
    analysis = build_fallback_narrative(results, type(
        "A", (), {"ok": False, "error": "", "ratio_comments": [],
                  "recommendations": [], "model": "fallback"}))
    html = build_html_report(
        results, analysis,
        score=compute_health_score(results.get("curr_metrics"), blocked_fields=blocked),
        currency=results.get("currency_hint") or "ج.م")
    return results, xlsx, html.encode("utf-8")


_LAST_DOC: dict[str, tuple[str, bytes]] = {}  # chat → آخر ملف للـ/reanalyze


def _clear_file_cache(file_name: str, raw: bytes, mode: str) -> int:
    """حذف كاش الاستخراج لهذا الملف تحديدًا — /reanalyze يعيد التحليل الحي."""
    from src.extraction.result_cache import extraction_key

    key = extraction_key(file_name, raw, None, mode == "fast")
    cache_file = (PROJECT_ROOT / "cache" / "extraction"
                  / (key.replace("|", "__") + ".json"))
    if cache_file.exists():
        cache_file.unlink()
        return 1
    return 0


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

    if text.startswith("/reanalyze"):
        last = _LAST_DOC.get(chat)
        if not last:
            _tg("sendMessage", {"chat_id": chat, "text":
                                "أرسل الملف أولًا — ثم /reanalyze يعيد "
                                "التحليل الحي بنداءات جديدة (بعد حذف الكاش)."})
            return
        rfname, rraw = last
        cleared = _clear_file_cache(rfname, rraw, _MODES.get(chat, "precise"))
        _tg("sendMessage", {"chat_id": chat, "text":
                            "🧹 حُذف كاش الاستخراج (" + str(cleared)
                            + " ملف) — جارٍ إعادة التحليل الحي…"})
        try:
            rresults, rxlsx, rhtml = analyze_document(
                rfname, rraw, _MODES.get(chat, "precise"))
        except Exception as exc:
            _tg("sendMessage", {"chat_id": chat, "text":
                                f"❌ {type(exc).__name__}: {str(exc)[:200]}"})
            return
        for chunk in build_full_report_messages(
                rresults, rresults.get("currency_hint") or "ج.م"):
            _tg("sendMessage", {"chat_id": chat, "text": chunk})
        if rxlsx:
            _tg("sendDocument",
                {"chat_id": chat,
                 "caption": "📊 التقرير الشامل (تحليل حي جديد)"},
                files={"document": (Path(rfname).stem + "_تحليل.xlsx",
                                    io.BytesIO(rxlsx))}, timeout=300)
        if rhtml:
            _tg("sendDocument",
                {"chat_id": chat, "caption": "🌐 تقرير HTML"},
                files={"document": (Path(rfname).stem + "_report.html",
                                    io.BytesIO(rhtml))}, timeout=300)
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
                                f"❌ الملف اللي وصل تالف أو مش {ext} فعلًا — "
                                "أرسله كـ Document من مصدره الأصلي، مش مُعاد تسميته."})
            return
        safe_fname = Path(fname).name or "document"
        inbox = INBOX / Path(chat).name
        inbox.mkdir(parents=True, exist_ok=True)
        (inbox / safe_fname).write_bytes(raw)
        _LAST_DOC[chat] = (safe_fname, raw)  # لـ/reanalyze

        try:
            results, xlsx, html = analyze_document(fname, raw,
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

        # وسم الكاش بصدق: إعادة تشغيل من الكاش المحلي = صفر نداءات
        from_cache = any("local cache" in str(n)
                         for n in results.get("notes") or [])
        # التقرير الكامل: كل الأقسام كرسائل متعددة
        chunks = build_full_report_messages(
            results, results.get("currency_hint") or "ج.م")
        if from_cache:
            chunks.insert(0, "⚡ مُعاد من الكاش المحلي (صفر نداءات) — "
                             "التحليل السابق نفسه.\nأرسل /reanalyze "
                             "لإعادة التحليل الحي بنداءات جديدة.")
        for chunk in chunks:
            _tg("sendMessage", {"chat_id": chat, "text": chunk})
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

    # المسار المحلي (الحل المضمون للمالك المحلي فقط): مقيد بـ ALLOW_LOCAL_PATHS=1
    # أو وجود المستخدم ضمن ALLOWED_IDS المحددة صراحةً، مع منع تسريب البايتات الخام.
    local_paths_allowed = (
        os.getenv("ALLOW_LOCAL_PATHS", "0").strip() == "1"
        or (bool(ALLOWED_IDS) and chat in ALLOWED_IDS)
    )
    if text and not text.startswith("/") and local_paths_allowed:
        candidate = Path(text.strip().strip('"').strip("'")).expanduser()
        if candidate.is_file():
            ext = candidate.suffix.lower()
            if ext not in ALLOWED_EXTS:
                _tg("sendMessage", {"chat_id": chat, "text":
                                    f"❌ {candidate.name}: امتداد غير مدعوم."})
                return
            raw = candidate.read_bytes()
            if not magic_matches(ext, raw[:16]):
                _tg("sendMessage", {"chat_id": chat, "text":
                                    f"❌ {candidate.name}: محتوى الملف لا يطابق الامتداد."})
                return
            _tg("sendMessage", {"chat_id": chat, "text":
                                f"📂 قرأت الملف محليًا: {candidate.name} — "
                                "جارٍ التحليل (قد يستغرق عدة دقائق)…"})
            try:
                results, xlsx, html = analyze_document(
                    candidate.name, raw, _MODES.get(chat, "precise"))
            except InsufficientDataError as exc:
                _tg("sendMessage", {"chat_id": chat, "text":
                                    "❌ " + str(exc) + "\n\nتأكد أن الملف قوائم "
                                    "مالية فيها سنتان على الأقل وأرقام مقروءة."})
                return
            except AppError as exc:
                _tg("sendMessage", {"chat_id": chat, "text": f"❌ {exc}"})
                return
            except Exception as exc:
                _tg("sendMessage", {"chat_id": chat, "text":
                                    f"❌ خطأ غير متوقع: {type(exc).__name__}"})
                return
            for chunk in build_full_report_messages(
                    results, results.get("currency_hint") or "ج.م"):
                _tg("sendMessage", {"chat_id": chat, "text": chunk})
            if xlsx:
                _tg("sendDocument",
                    {"chat_id": chat,
                     "caption": f"📊 التقرير الشامل — {candidate.name}"},
                    files={"document": (f"{candidate.stem}_تحليل.xlsx",
                                        io.BytesIO(xlsx))}, timeout=300)
            if html:
                _tg("sendDocument",
                    {"chat_id": chat,
                     "caption": "🌐 تقرير HTML (افتحه في المتصفح)"},
                    files={"document": (f"{candidate.stem}_report.html",
                                        io.BytesIO(html))}, timeout=300)
            return
        if len(text) > 3 and (":" in text or text.startswith("\\")):
            if local_paths_allowed:
                _tg("sendMessage", {"chat_id": chat, "text":
                                    f"❌ المسار غير موجود على الجهاز: {text[:80]}"})
            else:
                _tg("sendMessage", {"chat_id": chat, "text":
                                    "🔒 قراءة المسارات المحلية معطلة — أرسل الملف كـ Document في المحادثة."})
            return

    if text:
        _tg("sendMessage", {"chat_id": chat, "text":
                            "ارسل ملف PDF / Excel / CSV لتحليله، أو /help "
                            "للمساعدة، أو الصق مسار الملف المحلي من جهازك."})


def main() -> None:
    if not _single_instance():
        print("❌ نسخة من البوت شغالة أصلًا (bot.lock) — أغلقها أولًا، "
              "أو احذف bot.lock لو العملية القديمة ماتت فعلاً.")
        sys.exit(1)
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
