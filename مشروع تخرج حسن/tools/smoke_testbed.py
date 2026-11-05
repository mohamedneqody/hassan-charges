# -*- coding: utf-8 -*-
"""Smoke-test the isolated review testbed: launch it, hit the page, dump."""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
tb = Path(tempfile.mkdtemp(prefix="tb_smoke_"))
env = dict(os.environ)
env.update({
    "TESTBED_DIR": str(tb),
    "REVIEW_LOG_PATH": str(tb / "human_reviews.json"),
    "REVIEW_ATTEMPTS_PATH": str(tb / ".attempts.json"),
    "REVIEWERS_FILE": str(tb / "reviewers.json"),
    "REVIEW_HMAC_KEY": "smoke-key",
    "REVIEW_SESSION_TTL": "1800",
    "PYTHONPATH": str(PROJ),
})
logf = open(tb / "out.log", "w", encoding="utf-8")
proc = subprocess.Popen(
    [str(PROJ / ".venv/Scripts/streamlit.exe"), "run",
     str(PROJ / "tools/streamlit_review_testbed.py"),
     "--server.port", "8795", "--server.headless", "true",
     "--browser.gatherUsageStats", "false"],
    cwd=str(PROJ), env=env, stdout=logf, stderr=subprocess.STDOUT)
ok = False
for _ in range(45):
    time.sleep(2)
    try:
        html = urllib.request.urlopen("http://localhost:8795", timeout=3).read()
        ok = b"streamlit" in html.lower()
        break
    except Exception:
        pass

# the app script only executes when a real client connects — use Playwright
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto("http://localhost:8795", timeout=30000)
    try:
        page.wait_for_selector("text=دخول المراجع", timeout=60000)
        seen = "login form rendered"
    except Exception as e:
        seen = f"selector failed: {e}"
    b.close()

time.sleep(4)
dump = (tb / "state_dump.json")
print("HTTP up:", ok)
print("browser:", seen)
print("dump exists:", dump.exists())
if dump.exists():
    d = json.loads(dump.read_text(encoding="utf-8"))
    print("chain_ok:", d["chain_ok"], "| log_len:", d["log_len"],
          "| decision_log fields:", len(d["decision_log"]))
print("---- app log tail ----")
logf.flush()
print((tb / "out.log").read_text(encoding="utf-8", errors="replace")[-1200:])
proc.terminate()
sys.exit(0 if ok and dump.exists() else 1)
