# -*- coding: utf-8 -*-
"""Isolated Streamlit review testbed (منصة اختبار المراجعة المعزولة).

Browser-test target ONLY (P0-4) — never a production entrypoint. The runner
(tools/browser_review_tests.py) launches it with an isolated environment:
TESTBED_DIR, REVIEW_LOG_PATH, REVIEW_ATTEMPTS_PATH, REVIEWERS_FILE,
REVIEW_HMAC_KEY, REVIEW_SESSION_TTL. Everything the browser test must PROVE
lands in state_dump.json after every rerun: FinancialData values, the
decision log, the on-disk chain state, and per-record trust — so the tests
assert on SYSTEM EFFECTS, not on UI messages.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

import streamlit as st

PROJ = Path(__file__).resolve().parents[1]
TESTBED_DIR = Path(os.environ["TESTBED_DIR"]).resolve()
EV = TESTBED_DIR / "cell_evidence"
os.chdir(TESTBED_DIR)                       # relative crops_dir/eval_pages resolve here

from src.dashboard.review_ui import render_review_tab        # noqa: E402
from src.extraction import human_review as HR                # noqa: E402
from src.extraction.normalizer import (                      # noqa: E402
    FinancialData, build_decision_log,
)

QUEUE_PATH = EV / "review_queue.json"
REVIEWERS = TESTBED_DIR / "reviewers.json"

# the settled 2022/2021 values (GT from eval_2022) — single machine reads so
# every cell starts non-decisive and only reviews can make it decisive
GT = {
    "revenue": (16_665_919_878, 13_169_656_088),
    "net_activity_profit": (1_257_960_603, None),
    "net_income": (1_056_737_086, 288_152_668),
    "income_tax_expense": (-179_626_127, None),
    "pretax_income": (1_236_363_213, None),
    "short_term_debt": (4_063_400_167, 3_910_902_409),
    "current_portion_lt_debt": (299_320_963, 201_143_687),
    "long_term_debt": (363_974_291, None),
    "non_current_lease_liabilities": (209_154_419, None),
    "current_lease_liabilities": (83_301_722, None),
    "total_liabilities": (9_027_315_979, 8_250_000_000),
    "operating_cash_flow": (1_214_507_839, None),
    "total_assets": (15_900_000_000, 14_600_000_000),
    "current_assets": (8_300_000_000, 7_500_000_000),
    "current_liabilities": (7_900_000_000, 7_030_000_000),
    "equity": (6_900_000_000, 6_300_000_000),
    "inventory": (1_000, 900),
}


def setup_testbed(force: bool = False) -> None:
    if QUEUE_PATH.exists() and not force:
        return
    EV.mkdir(exist_ok=True)
    (TESTBED_DIR / "eval_pages").mkdir(exist_ok=True)
    src_ev = PROJ / "cell_evidence"
    for name in ("per_cell_strict.json", "benchmark_abc.json"):
        shutil.copy(src_ev / name, EV / name)
    for png in list(src_ev.glob("spatial_*.png")) + \
            list(src_ev.glob("date_header_*.png")):
        shutil.copy(png, EV / png.name)
    for pno in (5, 6, 9):
        shutil.copy(PROJ / f"eval_pages/page_{pno}.png",
                    TESTBED_DIR / f"eval_pages/page_{pno}.png")
    HR.pin_entry("auditor-A", "pin-A-123", ["approve", "correct", "reject"],
                 file_path=REVIEWERS)
    HR.pin_entry("auditor-B", "pin-B-456", ["approve", "correct", "reject"],
                 file_path=REVIEWERS)
    HR.pin_entry("ro-viewer", "pin-R-789", ["reject"], file_path=REVIEWERS)
    Path(HR.REVIEW_LOG).unlink(missing_ok=True)
    HR._save_attempts({})
    HR.build_review_queue(EV / "per_cell_strict.json", EV,
                          out_path=QUEUE_PATH,
                          pdf_path=PROJ / "القوائم المالية المستقلة 2022.pdf")


def make_financial_data() -> FinancialData:
    d = FinancialData()
    for f, (curr, prev) in GT.items():
        for yr, v in ((2022, curr), (2021, prev)):
            if v is None:
                continue
            d.values.setdefault(f, {})[yr] = float(v)
            d.candidates.setdefault(f, {})[yr] = [(float(v), 0)]
            d.confidence.setdefault(f, {})[yr] = 1       # single machine read
    return d


def dump_state(data: FinancialData, extra: dict | None = None) -> None:
    try:
        log = HR.load_log()
        trusted = {r["packet_id"]: HR.review_is_trusted(r, log_path=HR.REVIEW_LOG)
                   for r in log}
        dl = build_decision_log(data)
        dump = {
            "ts": time.time(),
            "log_path": str(HR.REVIEW_LOG),
            "log_len": len(log),
            "chain_ok": HR.verify_log_integrity()[0],
            "values": {f: {str(y): v for y, v in yy.items()}
                       for f, yy in data.values.items()},
            "decision_log": [{"field": e["field"], "year": e["year"],
                              "status": e["status"]} for e in dl],
            "human_reviews": {
                f"{k[0]}|{k[1]}": {"status": v.get("status"),
                                   "value_final": v.get("value_final"),
                                   "reviewer": v.get("reviewer"),
                                   "seq": v.get("seq")}
                for k, v in (getattr(data, "human_reviews", {}) or {}).items()},
            "trusted": trusted,
            "session_active": st.session_state.get("review_session") is not None,
        }
        if extra:
            dump.update(extra)
        (TESTBED_DIR / "state_dump.json").write_text(
            json.dumps(dump, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:                      # pragma: no cover
        (TESTBED_DIR / "state_dump_error.txt").write_text(repr(e),
                                                          encoding="utf-8")


setup_testbed(force=os.environ.get("TESTBED_RESET") == "1")

if "data" not in st.session_state:
    st.session_state["data"] = make_financial_data()
data: FinancialData = st.session_state["data"]
dump_state(data)                                # dump at rerun start too

st.title("منصة اختبار المراجعة البشرية (معزولة)")
st.caption(f"السجل: {HR.REVIEW_LOG}")

# ── sidebar controls (browser-test levers) ─────────────────────────────────
with st.sidebar:
    st.subheader("أدوات الاختبار")
    if st.button("🔄 تصفير المنصة"):
        Path(HR.REVIEW_LOG).unlink(missing_ok=True)
        HR._save_attempts({})
        st.session_state["data"] = make_financial_data()
        st.session_state["review_session"] = None
        setup_testbed(force=True)
        st.rerun()
    if st.button("♻️ استبدال صورة المصدر (إبطال)"):
        # re-scan simulation: the reviewed crop's bytes change on disk
        crop = EV / "spatial_net_income_p6_y2022.png"
        if crop.exists():
            crop.write_bytes(crop.read_bytes() + f"\x00rescan-{time.time()}".encode())
            st.success("تم استبدال القصاصة — الإقرارات القديمة باطلة الآن")
    if st.button("🔁 إعادة استخدام سجل قديم"):
        # stale-attestation replay: take the FIRST net_income record from the
        # chain and re-inject it — the backend must refuse to trust it if the
        # source changed (and the decision log must show UNVERIFIED)
        recs = [r for r in HR.load_log()
                if r["packet_id"] == "net_income|6|2022"
                and r.get("status") == HR.STATUS_HUMAN]
        if recs:
            old = recs[0]
            data.human_reviews = {("net_income", 2022): dict(old)}
            data.human_reviews_log = str(HR.REVIEW_LOG)
            ok = HR.review_is_trusted(old, log_path=HR.REVIEW_LOG,
                                      crops_dir=EV)
            st.session_state["stale_probe"] = {
                "trusted": bool(ok),
                "message": ("الإقرار القديم موثوق" if ok
                            else "الإقرار القديم غير موثوق — المصدر تغيّر "
                                 "(قرار السجل: UNVERIFIED)"),
            }
        else:
            st.session_state["stale_probe"] = {
                "trusted": False, "message": "لا يوجد سجل قديم"}
    probe = st.session_state.get("stale_probe")
    if probe:
        st.error(probe["message"]) if not probe["trusted"] else \
            st.success(probe["message"])

queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
render_review_tab(st, queue, reviewer="auditor-A", data=data)
dump_state(data)                                # authoritative end-of-rerun dump
