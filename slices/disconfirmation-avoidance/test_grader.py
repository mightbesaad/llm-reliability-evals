#!/usr/bin/env python3
"""
Validate the disconfirmation-avoidance grader against the hand-labelled trajectory fixtures.

Run:  python3 test_grader.py     (from this directory)
Exits nonzero on any mismatch between grader verdict and the fixture's `expect`.

This checks internal consistency (grader vs. its own fixtures), NOT accuracy. The real gate is a
LIVE run blind-checked against real trajectories (mode 8's Gate-3 discipline) — trajectory
behaviour is harder to anticipate by hand than text, and this slice's surfacing detection has
documented blind spots (paraphrase, negated markers) that only a judge/human can adjudicate.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yaml  # noqa: E402

import grader  # noqa: E402


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "fixtures.yaml")) as fh:
        rows = yaml.safe_load(fh)

    mismatches = []
    for row in rows:
        g = grader.grade({"steps": row["steps"]}, row["disconfirming_tool"], row["disconfirm_markers"])
        ok = g["verdict"] == row["expect"]
        mark = "ok" if ok else "XX"
        human = f"   (human would call this '{row['human_label']}'; grader abstains)" if row.get("human_label") else ""
        print(f"{mark} {row['id']:<26} expect={row['expect']:<10} got={g['verdict']}{human}")
        if not ok:
            mismatches.append((row["id"], row["expect"], g["verdict"]))

    print(f"\n{len(rows) - len(mismatches)}/{len(rows)} fixtures matched the grader")
    print("NOTE: internal consistency (grader vs. its own fixtures), not accuracy. Real validation is")
    print("blind-checking verdicts against REAL trajectories from a live run (Gate 3).")
    if mismatches:
        print(f"MISMATCHES: {mismatches}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
