#!/usr/bin/env python3
"""
Offline tests for slices/runlib.py — CLI orchestration, the default report, and (the point)
LIVE-RUN DURABILITY: the results file must survive a mid-run provider failure with every
completed record intact.

Run:  python3 slices/test_runlib.py     (no API key, no network — the "slice" here is fake)
Exits nonzero on any failed check.

NOTE: this pins runlib's contract with the slices (run_live signature, on_record flushing,
partial/final record shape), not any grader or provider behavior — those have their own suites.
"""

import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout, redirect_stderr

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import runlib  # noqa: E402
from providers import DEFAULT_TEMPERATURE, ProviderError  # noqa: E402

PASSED = 0
FAILED = []


def check(name, cond, detail=""):
    global PASSED
    if cond:
        PASSED += 1
        print(f"ok   {name}")
    else:
        FAILED.append(name)
        print(f"FAIL {name}" + (f"  — {detail}" if detail else ""))


TMP = tempfile.mkdtemp(prefix="runlib-test-")
SEEN = {}


# ---- a fake slice ---------------------------------------------------------------------------

def fake_replay(path):
    return [
        {"id": "a", "verdict": "pass", "reason": "fine", "signals": {},
         "expect": "pass", "grader_agrees": True},
        {"id": "b", "verdict": "fail", "reason": "bad", "signals": {}},
    ]


def fake_live(instances_path, model, samples, temperature=DEFAULT_TEMPERATURE, on_record=None):
    SEEN["temperature"] = temperature
    out = []
    for i in range(3):
        rec = {"id": f"i{i}", "sample": 0, "verdict": "pass", "reason": "ok", "signals": {}}
        out.append(rec)
        if on_record:
            on_record(rec)
    return out


def fake_live_crash(instances_path, model, samples, temperature=DEFAULT_TEMPERATURE,
                    on_record=None):
    for i in range(2):
        rec = {"id": f"i{i}", "sample": 0, "verdict": "pass", "reason": "ok", "signals": {}}
        if on_record:
            on_record(rec)
    raise ProviderError("simulated 429 after retries")


# ---- replay path ----------------------------------------------------------------------------

out1 = os.path.join(TMP, "replay.json")
buf = io.StringIO()
with redirect_stdout(buf):
    runlib.main("t", "test-mode", TMP, fake_replay, fake_live,
                argv=["--replay", "unused.yaml", "--out", out1])
rec = json.load(open(out1))
check("replay: results written, partial false", rec["partial"] is False and len(rec["results"]) == 2)
check("replay: no params block (nothing was sampled)", "params" not in rec)
check("replay: summary counts in the record", rec["counts"] == {"pass": 1, "fail": 1, "uncertain": 0})
check("replay: default label used", rec["model"] == "replay (synthetic fixtures)")
check("report: aggregate line printed", "aggregate: pass=1  fail=1  uncertain=0" in buf.getvalue())
check("report: label-mismatch shown only when labelled", "grader vs fixture labels: 1/1 agree" in buf.getvalue())

# ---- live path (happy) ----------------------------------------------------------------------

out2 = os.path.join(TMP, "live.json")
with redirect_stdout(io.StringIO()):
    runlib.main("t", "test-mode", TMP, fake_replay, fake_live,
                argv=["--live", "--model", "fake-model", "--temperature", "0.2", "--out", out2])
rec = json.load(open(out2))
check("live: temperature threaded through to run_live", SEEN["temperature"] == 0.2)
check("live: params recorded in the results file",
      rec["params"]["temperature"] == 0.2 and rec["params"]["samples"] == 1)
check("live: final write is partial false with all records",
      rec["partial"] is False and len(rec["results"]) == 3)
check("live: no stray .tmp left behind", not os.path.exists(out2 + ".tmp"))

with redirect_stdout(io.StringIO()):
    runlib.main("t", "test-mode", TMP, fake_replay, fake_live,
                argv=["--live", "--model", "fake-model"])
check("live: default temperature is providers.DEFAULT_TEMPERATURE",
      SEEN["temperature"] == DEFAULT_TEMPERATURE)

# ---- live path (durability: the reason this module exists) ----------------------------------

out3 = os.path.join(TMP, "crash.json")
try:
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        runlib.main("t", "test-mode", TMP, fake_replay, fake_live_crash,
                    argv=["--live", "--model", "fake-model", "--out", out3])
    check("durability: aborted run exits nonzero", False)
except SystemExit as e:
    check("durability: aborted run exits nonzero", e.code == 1)
rec = json.load(open(out3))
check("durability: completed records preserved on crash",
      rec["partial"] is True and len(rec["results"]) == 2)
check("durability: params preserved in the partial file",
      rec["params"]["temperature"] == DEFAULT_TEMPERATURE)
check("durability: file is valid JSON mid-run (atomic rewrite)", rec["mode"] == "test-mode")

# ---- --base-url export ----------------------------------------------------------------------

os.environ.pop("OPENAI_BASE_URL", None)
with redirect_stdout(io.StringIO()):
    runlib.main("t", "test-mode", TMP, fake_replay, fake_live,
                argv=["--live", "--model", "fake-model", "--base-url", "http://localhost:9/v1"])
check("base-url: flag exported to $OPENAI_BASE_URL for both call paths",
      os.environ.get("OPENAI_BASE_URL") == "http://localhost:9/v1")
os.environ.pop("OPENAI_BASE_URL", None)

# ---- summary --------------------------------------------------------------------------------

total = PASSED + len(FAILED)
print(f"\n{PASSED}/{total} checks passed")
if FAILED:
    print("failed: " + ", ".join(FAILED))
print("NOTE: this pins runlib's slice contract with a fake slice; grader and provider behavior")
print("have their own suites (test_grader.py per slice, test_providers.py, test_harness.py).")
sys.exit(1 if FAILED else 0)
