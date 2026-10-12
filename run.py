#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 That Scottish Guy
# SPDX-License-Identifier: MIT
"""Container entrypoint: web server + scheduler in one process tree.

Runs the monitor every 3 hours at :15 past the hour, and the weekly digest on
Sunday at 08:00 (container timezone). Exits if the web server dies so Docker restarts us.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

APP = Path(__file__).resolve().parent
cfg = json.loads((APP / "config.json").read_text())
SITE = Path(cfg["site_dir"])
SITE.mkdir(parents=True, exist_ok=True)
shutil.copy(APP / "index.html", SITE / "index.html")   # a code update shows up immediately, not after the next scan
shutil.copy(APP / "phrases.json", SITE / "phrases.json")        # the console's phrases: served to signed-in people only, like jobs.json
for extra in (APP / "assets" / "egg.mp3",):                      # an optional sound for the donut easter egg (never public)
    if extra.exists():
        shutil.copy(extra, SITE / extra.name)
    elif (SITE / extra.name).exists():
        (SITE / extra.name).unlink()
PORT = os.environ.get("PORT", "31361")


def run_monitor(*extra):
    print(f"[{datetime.now():%Y-%m-%d %H:%M}] monitor {' '.join(extra)}", flush=True)
    try:
        subprocess.run([sys.executable, str(APP / "monitor.py"), *extra], cwd=APP, timeout=1500)
    except subprocess.TimeoutExpired:
        print("monitor timed out", flush=True)


import threading
DRAIN = threading.Event()          # set after a scan (and at start): time to work through any waiting postings


def drain_loop():
    """Read waiting posting pages in polite batches: a batch, a cooldown, another batch... until nothing is left.

    Each batch is one `monitor.py --details` run (per-site cap, same throttle, robots rules and scan lock as everything else).
    Exit code 10 means more are waiting, 11 means a scan was running; anything else ends the round."""
    cool = float(cfg.get("politeness", {}).get("detail_cooldown_seconds", 480))
    while True:
        DRAIN.wait()
        DRAIN.clear()
        for _ in range(80):
            print(f"[{datetime.now():%Y-%m-%d %H:%M}] details batch", flush=True)
            try:
                rc = subprocess.run([sys.executable, str(APP / "monitor.py"), "--details"], cwd=APP, timeout=900).returncode
            except subprocess.TimeoutExpired:
                rc = 12
            if rc not in (10, 11):
                break
            time.sleep(cool)


threading.Thread(target=drain_loop, daemon=True).start()

server = subprocess.Popen([sys.executable, str(APP / "server.py"), str(SITE), "0.0.0.0", PORT],
                          env={**os.environ, "STATE_DIRECTORY": str(Path(cfg["data_dir"]))})
print(f"web server on :{PORT}", flush=True)

if not (SITE / "jobs.json").exists():
    run_monitor()          # first start: build the site right away
time.sleep(60)             # let a restart settle, then work off whatever postings are still waiting
DRAIN.set()
last_slot = last_digest = None
sched = cfg.get("schedule", {"hours": [6, 9, 12, 15, 18, 21], "minute": 15, "jitter_minutes": 10})
import random
while True:
    if server.poll() is not None:
        sys.exit("web server exited")
    now = datetime.now()
    slot = (now.date(), now.hour)
    if now.hour in sched["hours"] and now.minute >= sched["minute"] and slot != last_slot:
        last_slot = slot
        time.sleep(random.uniform(0, 60 * sched.get("jitter_minutes", 0)))     # never exactly on the dot
        run_monitor()
        DRAIN.set()
    if now.weekday() == 6 and now.hour == 8 and last_digest != now.date():
        last_digest = now.date()
        run_monitor("--digest")
    time.sleep(30)
