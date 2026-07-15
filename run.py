#!/usr/bin/env python3
"""
llm-reliability-evals — one-command entry point.

  python3 run.py                          offline: every unit + grader fixture suite (no keys,
                                          no network — green in under a minute; what CI runs)
  python3 run.py --mode sycophancy        offline, one slice only
  python3 run.py --list                   list the slices / modes

  python3 run.py --live --model mistral-medium --samples 3
                                          live: run every slice against a model; one dated
                                          results file per slice (params recorded inside)
  python3 run.py --live --model llama3.2 --base-url http://localhost:11434/v1 --mode stale-recall
                                          any OpenAI-compatible endpoint (Ollama, vLLM, Groq,
                                          OpenRouter, ...), subset of modes

Live needs the matching key (ANTHROPIC_API_KEY / MISTRAL_API_KEY / OPENAI_API_KEY) or
--base-url. Per-slice work (custom replay files, a single scenario) goes through the slice's
own runner: python3 slices/<mode>/runner.py --help.
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# (slice-dir, taxonomy mode number)
SLICES = [
    ("source-overtrust", 1),
    ("stale-recall", 2),
    ("confidence-calibration", 3),
    ("sycophancy", 4),
    ("false-precision", 5),
    ("overcorrection", 6),
    ("disconfirmation-avoidance", 7),
    ("premature-certification", 8),
]

UNIT_SUITES = ["test_providers.py", "test_harness.py", "test_runlib.py", "test_judge.py",
               "test_panel_stats.py"]


def _run(cmd, quiet):
    """Run a child, optionally swallowing output; return (rc, captured-or-None)."""
    if quiet:
        p = subprocess.run(cmd, capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr
    return subprocess.run(cmd).returncode, None


def offline(selected, verbose):
    """The contributor path: unit suites (when unfiltered) + grader fixture suites."""
    failures = []
    rows = []

    if len(selected) == len(SLICES):
        for name in UNIT_SUITES:
            rc, out = _run([sys.executable, os.path.join(HERE, "slices", name)], quiet=not verbose)
            rows.append((name, rc))
            if rc != 0:
                failures.append((name, out))

    for slice_dir, _n in selected:
        t = os.path.join(HERE, "slices", slice_dir, "test_grader.py")
        rc, out = _run([sys.executable, t], quiet=not verbose)
        rows.append((f"{slice_dir}/test_grader.py", rc))
        if rc != 0:
            failures.append((f"{slice_dir}/test_grader.py", out))

    # The same fixtures through the real runner path (runlib integration) — exits nonzero on
    # any grader-vs-label mismatch, so a broken run_replay or drifted grader can't ship green.
    for slice_dir, _n in selected:
        runner = os.path.join(HERE, "slices", slice_dir, "runner.py")
        fixtures = os.path.join(HERE, "slices", slice_dir, "fixtures.yaml")
        rc, out = _run([sys.executable, runner, "--replay", fixtures], quiet=not verbose)
        rows.append((f"{slice_dir}/replay", rc))
        if rc != 0:
            failures.append((f"{slice_dir}/replay", out))

    print("offline suite results:")
    for name, rc in rows:
        print(f"  {'ok  ' if rc == 0 else 'FAIL'}  {name}")
    print(f"\n{len(rows) - len(failures)}/{len(rows)} suites green")
    for name, out in failures:
        print(f"\n--- output of failing suite: {name} ---")
        print(out or "(output was streamed above)")
    return 1 if failures else 0


def live(selected, args):
    """Drive each selected slice's runner --live; one dated results file per slice.
    A failing slice doesn't stop the panel — failures are collected and reported."""
    date = datetime.date.today().isoformat()
    safe_model = re.sub(r"[^A-Za-z0-9._-]", "-", args.model)
    statuses = []
    for slice_dir, _n in selected:
        runner = os.path.join(HERE, "slices", slice_dir, "runner.py")
        if args.out_dir:
            out_path = os.path.join(args.out_dir, f"{slice_dir}-{safe_model}-{date}.json")
        else:
            # Convention: slices/<mode>/results/<model>-<YYYY-MM-DD>.json
            res_dir = os.path.join(HERE, "slices", slice_dir, "results")
            os.makedirs(res_dir, exist_ok=True)
            out_path = os.path.join(res_dir, f"{safe_model}-{date}.json")
            # Same-day rerun: a COMPLETE file is a finished run (e.g. a drift baseline) — never
            # overwrite it; suffix -b, -c, ... Partials are resumed intents and may be replaced
            # (runlib snapshots them to .prev regardless).
            suffix = ord("b")
            while os.path.exists(out_path):
                try:
                    if json.load(open(out_path)).get("partial"):
                        break
                except Exception:
                    pass
                out_path = os.path.join(res_dir, f"{safe_model}-{date}-{chr(suffix)}.json")
                suffix += 1
        cmd = [sys.executable, runner, "--live",
               "--model", args.model,
               "--samples", str(args.samples),
               "--temperature", str(args.temperature),
               "--out", out_path]
        if args.base_url:
            cmd += ["--base-url", args.base_url]
        print(f"\n===== {slice_dir} (live, {args.model}) =====")
        rc = subprocess.run(cmd).returncode
        statuses.append((slice_dir, rc, out_path))

    print("\nlive panel summary:")
    for slice_dir, rc, out_path in statuses:
        mark = "ok  " if rc == 0 else "FAIL"
        print(f"  {mark}  {slice_dir:<26} -> {out_path}")
    print("\nReminder: verdict counts are not the gate — blind-check the raw responses/"
          "trajectories in the results files before trusting a run (see README).")
    return 1 if any(rc != 0 for _s, rc, _o in statuses) else 0


def main():
    ap = argparse.ArgumentParser(
        description="run the reliability suite — offline (default, no keys) or live against a model",
        epilog="per-slice flags live on the slice runners: python3 slices/<mode>/runner.py --help")
    ap.add_argument("--mode", action="append", dest="modes", metavar="SLICE",
                    help="limit to a slice (repeatable); default: all built modes")
    ap.add_argument("--list", action="store_true", help="list slices / taxonomy modes and exit")
    ap.add_argument("--live", action="store_true", help="run live against --model instead of offline suites")
    ap.add_argument("--model", default=os.environ.get("EVAL_MODEL", ""), help="model id (live)")
    ap.add_argument("--samples", type=int, default=1, help="samples per instance (live)")
    ap.add_argument("--temperature", type=float, default=0.7,
                    help="sampling temperature, recorded in results (default 0.7)")
    ap.add_argument("--base-url", default=None,
                    help="OpenAI-compatible endpoint (Ollama/vLLM/Groq/...); also via $OPENAI_BASE_URL")
    ap.add_argument("--out-dir", default=None,
                    help="directory for live results files (default: each slice's own directory)")
    ap.add_argument("--verbose", action="store_true", help="stream suite output instead of summarizing")
    args = ap.parse_args()

    if args.list:
        print("slice (dir under slices/)      taxonomy mode")
        for slice_dir, n in SLICES:
            print(f"  {slice_dir:<28} {n}")
        return 0

    known = {s for s, _n in SLICES}
    if args.modes:
        bad = [m for m in args.modes if m not in known]
        if bad:
            ap.error(f"unknown mode(s): {', '.join(bad)} — try --list")
        selected = [(s, n) for s, n in SLICES if s in set(args.modes)]
    else:
        selected = SLICES

    if not args.live:
        return offline(selected, args.verbose)

    if not args.model:
        ap.error("--live needs --model <model-id> (or EVAL_MODEL)")
    if args.out_dir:
        os.makedirs(args.out_dir, exist_ok=True)
    return live(selected, args)


if __name__ == "__main__":
    sys.exit(main())
