#!/usr/bin/env python3
"""
Panel statistics — final-verdict derivation + Wilson 95% intervals (the error-bar layer).

Derives each record's FINAL verdict from the committed results files, applying the same
precedence the adjudication pipeline used (validated: reproduces four of the six published
2026-07-02/03 frontier-panel rows exactly — see RECONCILIATION below for the other two):

  1. Human blind-check overturn (`blind_check.overturns[].final_verdict`) — human labels win.
  2. Else, for grader-UNCERTAIN records only, a judge verdict that decided (pass/fail).
     Judge discards (`evidence_check_failed`) and parse-failure verdicts are already
     recorded as "uncertain" and stay uncertain. The judge never overrides a decided
     grader verdict (see judge.py: it adjudicates the abstain bucket only).
  3. Else the grader verdict as it stands in the file (regrades rewrite `verdict` in
     place with provenance in `regraded_with`, so no extra handling is needed).

Intervals are Wilson score (95%) on the decided pass-rate — chosen over the normal
approximation because panel cells are dozens of records, where the normal interval lies.

RECONCILIATION (--reconcile): prints ledger-derived rows against the numbers published in
the README on 2026-07-03. Four rows reproduce exactly (claude-sonnet-5, gpt-5.5,
gemini-3.5-flash, mistral-medium run B). Two do not: mistral-medium run A differs by one
pass (ledger 141/197 vs published 140/197) and mistral-large by two passes and one fail
(ledger 113 pass / 52 fail / 20 uncertain — 16 of those uncertain are the judge
parse-blocked confidence-calibration records — vs published 111/164 with residual
uncertain 4). The compiling session applied rulings that were never written back to the
files. The files are the record: where they disagree, the ledger-derived number is the
one this repo can defend, and the README carries the correction note.

Usage:
  python3 slices/panel_stats.py                 # aggregate table (markdown)
  python3 slices/panel_stats.py --cells         # per-mode × model cell table
  python3 slices/panel_stats.py --reconcile     # ledger vs published-README diff
  python3 slices/panel_stats.py --json out.json # machine-readable (grid generator input)
"""

import argparse
import collections
import glob
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# The frozen frontier panel: results files dated 2026-07-02/03, .prev snapshots excluded.
PANEL_DATES = ("2026-07-02", "2026-07-03")

MODEL_LABELS = {
    "anthropic/claude-sonnet-5": "claude-sonnet-5",
    "openai/gpt-5.5": "gpt-5.5",
    "google/gemini-3.5-flash": "gemini-3.5-flash",
    "mistral/mistral-medium": "mistral-medium",
    "mistral-medium": "mistral-medium",
    "mistral/mistral-large-latest": "mistral-large",
    "mistral-large-latest": "mistral-large",
}

# Published README rows (2026-07-03) for --reconcile: pass, fail, uncertain as printed.
PUBLISHED = {
    "claude-sonnet-5": (197, 7, 0),
    "gpt-5.5": (152, 45, 7),
    "gemini-3.5-flash": (130, 66, 8),
    "mistral-medium (run A)": (140, 57, None),  # README prints 140/197; fails not split per run
    "mistral-medium (run B)": (135, 51, 3),
    "mistral-large": (111, 53, 4),
}

Z95 = 1.959964


def wilson(successes, n, z=Z95):
    """Wilson score interval for a binomial proportion. Returns (lo, hi) in [0, 1]."""
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def final_verdict(record, overturns):
    """Apply the adjudication precedence to one record. `overturns` maps (id, sample)
    to the human final_verdict for this file."""
    key = (record["id"], record["sample"])
    if key in overturns:
        return overturns[key]
    v = record["verdict"]
    if v == "uncertain" and "judge" in record:
        jv = record["judge"].get("verdict")
        if jv in ("pass", "fail"):
            return jv
    return v


def load_panel(root=None):
    """Walk slices/*/results/ for panel-dated files; return
    {model_label: {slice_name: Counter(pass/fail/uncertain)}}."""
    root = root or os.path.dirname(HERE)
    files = []
    for date in PANEL_DATES:
        files += glob.glob(os.path.join(root, "slices", "*", "results", f"*{date}*.json"))
    files = sorted(f for f in files if not f.endswith(".prev"))

    # mistral-medium ran twice on 2026-07-02; the -b suffix marks the second run.
    has_b = any(os.path.basename(f).endswith("-b.json") for f in files)

    panel = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    for f in files:
        with open(f) as fh:
            doc = json.load(fh)
        label = MODEL_LABELS.get(doc["model"], doc["model"])
        if label == "mistral-medium" and has_b:
            label += " (run B)" if os.path.basename(f).endswith("-b.json") else " (run A)"
        slice_name = os.path.basename(os.path.dirname(os.path.dirname(f)))
        overturns = {
            (o["id"], o["sample"]): o["final_verdict"]
            for o in (doc.get("blind_check") or {}).get("overturns", [])
        }
        for r in doc.get("results", []):
            panel[label][slice_name][final_verdict(r, overturns)] += 1
    return panel


def aggregate(panel):
    """Collapse per-slice counters to per-model totals."""
    out = {}
    for label, slices in panel.items():
        c = collections.Counter()
        for counter in slices.values():
            c.update(counter)
        out[label] = c
    return out


def fmt_row(label, c):
    dec = c["pass"] + c["fail"]
    lo, hi = wilson(c["pass"], dec)
    rate = c["pass"] / dec * 100 if dec else 0
    return (f"| {label} | {rate:.0f}% ({c['pass']}/{dec}) | "
            f"{lo * 100:.1f}–{hi * 100:.1f}% | {c['fail']} | {c['uncertain']} |")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--cells", action="store_true", help="per-mode × model cell table")
    ap.add_argument("--reconcile", action="store_true", help="diff ledger vs published README rows")
    ap.add_argument("--json", metavar="PATH", help="write machine-readable cells + aggregates")
    args = ap.parse_args()

    panel = load_panel()
    agg = aggregate(panel)
    order = sorted(agg, key=lambda k: -(agg[k]["pass"] / max(1, agg[k]["pass"] + agg[k]["fail"])))

    print("| model | decided pass-rate | 95% CI (Wilson) | fails | uncertain |")
    print("|---|---|---|---|---|")
    for label in order:
        print(fmt_row(label, agg[label]))

    if args.cells:
        slices = sorted({s for v in panel.values() for s in v})
        print("\n| mode | " + " | ".join(order) + " |")
        print("|---" * (len(order) + 1) + "|")
        for s in slices:
            cells = []
            for label in order:
                c = panel[label].get(s, collections.Counter())
                dec = c["pass"] + c["fail"]
                if dec == 0:
                    cells.append("—")
                    continue
                lo, hi = wilson(c["pass"], dec)
                cells.append(f"{c['pass']}/{dec} ({lo * 100:.0f}–{hi * 100:.0f}%)")
            print(f"| {s} | " + " | ".join(cells) + " |")

    if args.reconcile:
        print("\nReconciliation vs README (published 2026-07-03):")
        for label in order:
            c = agg[label]
            pub = PUBLISHED.get(label)
            if not pub:
                print(f"  {label}: no published row")
                continue
            got = (c["pass"], c["fail"], c["uncertain"])
            ok = got[0] == pub[0] and got[1] == pub[1] and (pub[2] is None or got[2] == pub[2])
            mark = "exact" if ok else f"DIFFERS — ledger {got} vs published {pub}"
            print(f"  {label}: {mark}")

    if args.json:
        payload = {
            "aggregates": {
                label: {
                    **{k: agg[label][k] for k in ("pass", "fail", "uncertain")},
                    "ci95": wilson(agg[label]["pass"], agg[label]["pass"] + agg[label]["fail"]),
                }
                for label in order
            },
            "cells": {
                label: {
                    s: {
                        **{k: c[k] for k in ("pass", "fail", "uncertain")},
                        "ci95": wilson(c["pass"], c["pass"] + c["fail"]),
                    }
                    for s, c in slices_.items()
                }
                for label, slices_ in panel.items()
            },
        }
        with open(args.json, "w") as fh:
            json.dump(payload, fh, indent=1)
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
