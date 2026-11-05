# -*- coding: utf-8 -*-
"""Browser tests for the human-review journey (اختبارات المتصفح المعزولة).

Launches the isolated Streamlit testbed (tools/streamlit_review_testbed.py)
twice — main (30-min sessions) and short-TTL (4 s sessions) — and drives the
REAL UI with Playwright through the ten required cases. Every case asserts
on SYSTEM EFFECTS read from state_dump.json + the on-disk review log (the
UI's own success message is never treated as proof):

  1  approve a correct number        → VERIFIED_HUMAN record + value reaches
                                       FinancialData AND the decision log
  2  correct a wrong number          → kind=correct, corrected value lands
  3  reject an unreadable cell       → REJECTED_HUMAN, no value attested
  4  wrong PIN                       → no session, no writes
  5  action without the role         → backend refusal, no record
  6  two conflicting reviews         → CONFLICT_HUMAN, never decisive
  7  page reload                     → session gone, log untouched
  8  session expiry                  → backend refuses after TTL
  9  source replaced after approval  → trust voided, decision log UNVERIFIED
  10 stale record replay             → old attestation not trusted

Usage:  .venv/Scripts/python.exe tools/browser_review_tests.py
Output: cell_evidence/browser_test_results.json + console summary.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ))

from playwright.sync_api import sync_playwright  # noqa: E402

PORT_MAIN = 8791
PORT_SHORT = 8792
RESULTS: list[dict] = []


def log(msg: str) -> None:
    print(msg, flush=True)


def case(name: str, ok: bool, detail: str) -> None:
    RESULTS.append({"case": name, "pass": bool(ok), "detail": detail})
    log(f"  {'✅' if ok else '❌'} {name} — {detail}")


# ── browser helpers (Streamlit needs JS clicks — plain Playwright clicks
#    time out on st widgets) ────────────────────────────────────────────────

def js_click(page, text: str, tag: str = "button") -> bool:
    return page.evaluate(
        """([text, tag]) => {
             const els = [...document.querySelectorAll(tag)];
             const el = els.find(e => e.textContent.trim().includes(text));
             if (el) { el.click(); return true; } return false;
           }""", [text, tag])


EXPAND_JS = """(text) => {
  // st.expander = <details><summary>… in most versions; older/forked DOM may
  // use [data-testid="stExpander"] with a toggle button — try both.
  const det = [...document.querySelectorAll('details')].find(
      d => d.querySelector('summary') &&
           d.querySelector('summary').textContent.includes(text));
  if (det) {
    if (!det.open) det.querySelector('summary').click();
    return true;
  }
  const divs = [...document.querySelectorAll('[data-testid="stExpander"]')];
  const dv = divs.find(d => d.textContent.includes(text));
  if (dv) {
    const btn = dv.querySelector('button, [data-testid="stExpanderToggle"], summary');
    if (btn) { btn.click(); return true; }
  }
  return false;
}"""


def expand_packet(page, field: str, timeout: float = 45) -> bool:
    """Wait for the expander to render (the queue shows 11 image-heavy
    packets — a full rerun can take several seconds) and open it."""
    end = time.time() + timeout
    while time.time() < end:
        if page.evaluate(EXPAND_JS, field):
            return True
        page.wait_for_timeout(1000)
    return False


def wait_idle(page, pre_ms: int = 400) -> None:
    """Wait for Streamlit to finish a rerun (status widget disappears)."""
    page.wait_for_timeout(pre_ms)
    try:
        page.wait_for_selector('[data-testid="stStatusWidget"]',
                               state="attached", timeout=2500)
        page.wait_for_selector('[data-testid="stStatusWidget"]',
                               state="detached", timeout=60000)
    except Exception:
        pass
    page.wait_for_timeout(300)


CONFIRM_LABELS = ("المستند الصحيح", "البند الصحيح", "السنة الصحيحة",
                  "موضع الخانة الصحيح", "القيمة الرقمية الصحيحة")
IDENTITY_LABELS = CONFIRM_LABELS[:4]

TICK_IN_EXPANDER_JS = """([field, label]) => {
  // click the INPUT directly — clicking the LABEL double-toggles it
  const det = [...document.querySelectorAll('details')].find(
      d => d.querySelector('summary') &&
           d.querySelector('summary').textContent.includes(field));
  if (!det) return 'no-expander';
  const lab = [...det.querySelectorAll('label')].find(
      l => l.textContent.trim().includes(label));
  if (!lab) return 'no-label';
  const box = lab.querySelector('input[type=checkbox]');
  if (!box) return 'no-box';
  if (box.checked) return 'checked';        // already ticked
  box.click();
  return box.checked ? 'checked' : 'no-toggle';
}"""


def tick_confirmation(page, field: str, label: str, timeout: float = 30) -> bool:
    """Tick and VERIFY — a click that doesn't register is retried, because a
    missed confirmation silently leaves the action button disabled forever."""
    end = time.time() + timeout
    last = "timeout"
    while time.time() < end:
        last = page.evaluate(TICK_IN_EXPANDER_JS, [field, label])
        if last == "checked":
            return True
        page.wait_for_timeout(900)
    raise AssertionError(f"tick '{label}' in '{field}': {last}")


CLICK_IN_JS = """([field, text, tag]) => {
  const det = [...document.querySelectorAll('details')].find(
      d => d.querySelector('summary') &&
           d.querySelector('summary').textContent.includes(field));
  if (!det) return 'no-expander';
  const el = [...det.querySelectorAll(tag)].find(
      e => e.textContent.trim().includes(text));
  if (!el) return 'no-widget';
  if (el.disabled) return 'disabled';        // wait — confirmations still applying
  el.click();
  return 'clicked';
}"""


def ui_alerts(page) -> list[str]:
    try:
        return [e.inner_text() for e in
                page.locator('[data-testid="stAlert"]').all()]
    except Exception:
        return []


def js_click_in(page, field: str, text: str, tag: str = "button",
                timeout: float = 40) -> bool:
    """Click a widget INSIDE the target packet's expander — the same widget
    exists in every packet, so page-wide lookup would hit the wrong (hidden)
    one. The confirmations-gated buttons start DISABLED and only enable
    after Streamlit's rerun, so retry until enabled."""
    end = time.time() + timeout
    last = "timeout"
    while time.time() < end:
        last = page.evaluate(CLICK_IN_JS, [field, text, tag])
        if last == "clicked":
            return True
        page.wait_for_timeout(1000)
    raise AssertionError(f"click '{text}' in '{field}': {last}")


def fill_number_in(page, field: str, value: str) -> bool:
    """Fill the packet's correction number input through the React native
    setter (plain .value assignment is ignored by React)."""
    return page.evaluate(
        """([field, value]) => {
             const det = [...document.querySelectorAll('details')].find(
                 d => d.querySelector('summary') &&
                      d.querySelector('summary').textContent.includes(field));
             if (!det) return false;
             const inp = det.querySelector('input[type="number"]');
             if (!inp) return false;
             const desc = Object.getOwnPropertyDescriptor(
                 Object.getPrototypeOf(inp), 'value');
             inp.focus();
             desc.set.call(inp, value);
             inp.dispatchEvent(new Event('input', {bubbles: true}));
             inp.dispatchEvent(new Event('change', {bubbles: true}));
             inp.blur();
             return true;
           }""", [field, value])


def settle(page, ms: int = 2200) -> None:
    wait_idle(page, pre_ms=ms)


def login(page, name: str, pin: str) -> bool:
    inputs = page.locator('input[type="text"]')
    inputs.first.fill(name)
    page.locator('input[type="password"]').fill(pin)
    clicked = js_click(page, "بدء جلسة المراجعة")
    settle(page)
    return clicked


def run_review_action(page, field: str, action_text: str,
                      confirm: str = "all",
                      correct_value: str | None = None) -> None:
    """Expand the packet's expander, tick the confirmations INSIDE it, fill
    the optional correction, click the action button — all scoped to THIS
    packet. confirm: all | identity (all five for attestations, four for
    reject)."""
    assert expand_packet(page, field), f"expander not found: {field}"
    labels = {"all": CONFIRM_LABELS, "identity": IDENTITY_LABELS}[confirm]
    for lbl in labels:
        assert tick_confirmation(page, field, lbl),             f"checkbox missing for {field}: {lbl}"
        settle(page, 800)
    if correct_value is not None:
        assert fill_number_in(page, field, correct_value), "number input"
        settle(page, 800)
    assert js_click_in(page, field, action_text),         f"button not found in {field}: {action_text}"
    settle(page, 2600)


def read_dump(testbed: Path) -> dict:
    f = testbed / "state_dump.json"
    for _ in range(20):
        if f.exists():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                pass
        time.sleep(0.3)
    raise AssertionError("state_dump.json never written")


def read_disk_log(testbed: Path) -> list[dict]:
    f = testbed / "human_reviews.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []


def launch_app(port: int, ttl_env: dict) -> tuple[subprocess.Popen, Path]:
    testbed = Path(tempfile.mkdtemp(prefix=f"review_testbed_{port}_"))
    env = dict(os.environ)
    env.update({
        "TESTBED_DIR": str(testbed),
        "REVIEW_LOG_PATH": str(testbed / "human_reviews.json"),
        "REVIEW_ATTEMPTS_PATH": str(testbed / ".attempts.json"),
        "REVIEWERS_FILE": str(testbed / "reviewers.json"),
        "REVIEW_HMAC_KEY": "browser-test-key-isolated",
        "REVIEW_SESSION_TTL": "1800",
        "PYTHONPATH": str(PROJ),
    })
    env.update(ttl_env)
    exe = str(PROJ / ".venv/Scripts/streamlit.exe")
    proc = subprocess.Popen(
        [exe, "run", str(PROJ / "tools/streamlit_review_testbed.py"),
         "--server.port", str(port), "--server.headless", "true",
         "--browser.gatherUsageStats", "false"],
        cwd=str(PROJ), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return proc, testbed


def wait_up(page, port: int, deadline: float = 90) -> None:
    end = time.time() + deadline
    while time.time() < end:
        try:
            page.goto(f"http://localhost:{port}", timeout=4000)
            page.wait_for_selector("text=دخول المراجع", timeout=8000)
            return
        except Exception:
            time.sleep(2)
    raise RuntimeError(f"testbed on {port} never came up")


# ── the journey ─────────────────────────────────────────────────────────────

def browser_tests() -> None:
    proc_main, tb_main = launch_app(PORT_MAIN, {})
    proc_short, tb_short = launch_app(
        PORT_SHORT, {"REVIEW_SESSION_TTL": "4"})
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(locale="ar")
            page = ctx.new_page()

            # ══ main app cases ══
            wait_up(page, PORT_MAIN)
            dump = read_dump(tb_main)
            case("testbed-up", dump.get("chain_ok") is True,
                 f"chain_ok={dump.get('chain_ok')}, log_len={dump.get('log_len')}")

            # ── case 4: wrong PIN ──
            ok = login(page, "auditor-A", "WRONG-pin")
            page.wait_for_timeout(1200)
            err = page.locator("text=مرفوض").count() > 0
            dump = read_dump(tb_main)
            disk = read_disk_log(tb_main)
            case("wrong-pin-rejected", ok and err and dump["session_active"] is False
                 and not disk,
                 "error shown, no session, no log writes")

            # ── login auditor-A ──
            assert login(page, "auditor-A", "pin-A-123")
            page.wait_for_selector("text=جلسة المراجع", timeout=15000)

            # ── case 1: approve a correct number (net_income) ──
            run_review_action(page, "صافى أرباح العام", "✅ اعتماد المقترح")
            dump = read_dump(tb_main)
            disk = read_disk_log(tb_main)
            ni = next((e for e in dump["decision_log"]
                       if e["field"] == "net_income" and e["year"] == 2022), {})
            val = dump["values"].get("net_income", {}).get("2022")
            case("approve-correct-value",
                 ni.get("status") == "VERIFIED_HUMAN"
                 and val == 1_056_737_086.0 and len(disk) == 1
                 and dump["chain_ok"] and dump["trusted"].get("net_income|6|2022") is True,
                 f"decision_log={ni.get('status')}, value={val}, "
                 f"log_len={len(disk)}, trusted={dump['trusted'].get('net_income|6|2022')}, "
                 f"alerts={ui_alerts(page)[:2]}")

            # ── case 2: correct a wrong number (total_liabilities) ──
            run_review_action(page, "إجمالي الالتزامات", "✏️ اعتماد قيمة مصححة",
                              correct_value="9027315979")
            dump = read_dump(tb_main)
            disk = read_disk_log(tb_main)
            tl = next((e for e in dump["decision_log"]
                       if e["field"] == "total_liabilities"
                       and e["year"] == 2022), {})
            val = dump["values"].get("total_liabilities", {}).get("2022")
            rec = next((r for r in disk if r["packet_id"] == "total_liabilities|5|2022"), {})
            case("correct-wrong-value",
                 val == 9_027_315_979.0 and rec.get("kind") == "correct"
                 and rec.get("value_before") == 418_441_944.0
                 and tl.get("status") == "VERIFIED_HUMAN",
                 f"value={val}, kind={rec.get('kind')}, "
                 f"before={rec.get('value_before')}, decision={tl.get('status')}")

            # ── case 3: reject an unreadable cell (operating_cash_flow) ──
            # reject needs the FOUR identity confirmations (value is denied)
            run_review_action(page, "النائجة من أنشطة التشغيل",
                              "🚫 رفض — غير مقروءة", confirm="identity")
            dump = read_dump(tb_main)
            disk = read_disk_log(tb_main)
            rec = next((r for r in disk
                        if r["packet_id"] == "operating_cash_flow|9|2022"), {})
            ocf = next((e for e in dump["decision_log"]
                        if e["field"] == "operating_cash_flow"
                        and e["year"] == 2022), {})
            ocf_val = dump["values"].get("operating_cash_flow", {}).get("2022")
            case("reject-unreadable",
                 rec.get("status") == "REJECTED_HUMAN"
                 and ocf.get("status") != "VERIFIED_HUMAN"
                 and ocf_val == 1_214_507_839.0,   # machine value UNCHANGED
                 f"record={rec.get('status')}, decision={ocf.get('status')}, "
                 f"value_unchanged={ocf_val}")

            # ── case 7: page reload → session gone, log untouched ──
            len_before = len(read_disk_log(tb_main))
            page.reload()
            settle(page, 3000)
            back_to_login = page.locator("text=دخول المراجع").count() > 0
            dump = read_dump(tb_main)
            case("reload-clears-session-only",
                 back_to_login and dump["session_active"] is False
                 and len(read_disk_log(tb_main)) == len_before
                 and dump["chain_ok"],
                 f"login shown again, log_len stable at {len_before}")

            # ── case 6: two conflicting reviews (short_term_debt) ──
            assert login(page, "auditor-A", "pin-A-123")
            page.wait_for_selector("text=جلسة المراجع", timeout=15000)
            run_review_action(page, "بنوك تسهيلات إنتمانية", "✅ اعتماد المقترح")
            dump = read_dump(tb_main)
            disk = read_disk_log(tb_main)
            std_recs = [r for r in disk if r["packet_id"] == "short_term_debt|5|2022"]
            first_ok = len(std_recs) == 1 and std_recs[0]["status"] == "VERIFIED_HUMAN"
            page.reload()
            settle(page, 2000)
            assert login(page, "auditor-B", "pin-B-456")
            page.wait_for_selector("text=جلسة المراجع", timeout=15000)
            run_review_action(page, "بنوك تسهيلات إنتمانية",
                              "✏️ اعتماد قيمة مصححة",
                              correct_value="4999999999")
            dump = read_dump(tb_main)
            disk = read_disk_log(tb_main)
            std_recs = [r for r in disk if r["packet_id"] == "short_term_debt|5|2022"]
            std = next((e for e in dump["decision_log"]
                        if e["field"] == "short_term_debt"
                        and e["year"] == 2022), {})
            case("conflicting-reviews-never-decide",
                 first_ok and len(std_recs) == 2
                 and std_recs[-1]["status"] == "CONFLICT_HUMAN"
                 and std.get("status") != "VERIFIED_HUMAN"
                 and dump["trusted"].get("short_term_debt|5|2022") is False,
                 f"records={[r['status'] for r in std_recs]}, "
                 f"decision={std.get('status')}, "
                 f"trusted={dump['trusted'].get('short_term_debt|5|2022')}")

            # ── case 5: action without the role (ro-viewer tries approve) ──
            page.reload()
            settle(page, 2000)
            assert login(page, "ro-viewer", "pin-R-789")
            page.wait_for_selector("text=جلسة المراجع", timeout=15000)
            run_review_action(page, "المبيعات", "✅ اعتماد المقترح")
            dump = read_dump(tb_main)
            disk = read_disk_log(tb_main)
            rev_recs = [r for r in disk if r["packet_id"] == "revenue|6|2022"]
            role_err = page.locator("text=مرفوض").count() > 0
            case("no-role-no-record",
                 not rev_recs and role_err and dump["chain_ok"],
                 f"backend refused, revenue records={len(rev_recs)}")

            # ── case 9: source replaced after approval → voided ──
            page.reload()
            settle(page, 2000)
            assert login(page, "auditor-A", "pin-A-123")
            page.wait_for_selector("text=جلسة المراجع", timeout=15000)
            assert js_click(page, "♻️ استبدال صورة المصدر"), "replace button"
            settle(page, 2500)
            dump = read_dump(tb_main)
            ni = next((e for e in dump["decision_log"]
                       if e["field"] == "net_income" and e["year"] == 2022), {})
            case("source-change-voids-attestation",
                 dump["trusted"].get("net_income|6|2022") is False
                 and ni.get("status") == "UNVERIFIED",
                 f"trusted={dump['trusted'].get('net_income|6|2022')}, "
                 f"decision={ni.get('status')}")

            # ── case 10: stale record replay after invalidation ──
            assert js_click(page, "🔁 إعادة استخدام سجل قديم"), "replay button"
            settle(page, 2500)
            stale_msg = page.locator(
                "text=الإقرار القديم غير موثوق").count() > 0
            dump = read_dump(tb_main)
            ni = next((e for e in dump["decision_log"]
                       if e["field"] == "net_income" and e["year"] == 2022), {})
            case("stale-record-replay-refused",
                 stale_msg and ni.get("status") == "UNVERIFIED"
                 and dump["chain_ok"],
                 f"probe_message_shown={stale_msg}, decision={ni.get('status')}")

            # ══ short-TTL app: case 8 (session expiry) ══
            page2 = ctx.new_page()
            wait_up(page2, PORT_SHORT)
            assert login(page2, "auditor-A", "pin-A-123")
            page2.wait_for_selector("text=جلسة المراجع", timeout=15000)
            time.sleep(6)                       # TTL = 4 s
            ok = expand_packet(page2, "صافى أرباح العام")
            for lbl in CONFIRM_LABELS:
                tick_confirmation(page2, "صافى أرباح العام", lbl)
                settle(page2, 700)
            js_click_in(page2, "صافى أرباح العام", "✅ اعتماد المقترح")
            settle(page2, 2600)
            expired_err = page2.locator("text=منتهية").count() > 0
            disk_short = read_disk_log(tb_short)
            case("session-expiry-enforced",
                 expired_err and not disk_short,
                 f"expiry error shown={expired_err}, short-app records={len(disk_short)}")

            browser.close()
    finally:
        for proc in (proc_main, proc_short):
            proc.terminate()
            try:
                proc.wait(10)
            except Exception:
                proc.kill()


def main() -> int:
    log("═══ P0-4 browser journey (isolated Streamlit testbed) ═══")
    browser_tests()
    passed = sum(1 for r in RESULTS if r["pass"])
    out = PROJ / "cell_evidence/browser_test_results.json"
    out.write_text(json.dumps(
        {"passed": passed, "total": len(RESULTS), "results": RESULTS},
        ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"═══ {passed}/{len(RESULTS)} passed — report: {out} ═══")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
