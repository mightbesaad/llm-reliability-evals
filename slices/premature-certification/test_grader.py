#!/usr/bin/env python3
"""
Validate the premature-self-certification grader against the hand-authored trajectory fixtures.

Run:  python3 test_grader.py     (from this directory)
Exits nonzero on any mismatch between grader verdict and the fixture's `expect`.

Internal consistency (grader vs. its own fixtures), NOT accuracy. For THIS slice especially, a green
run is not "done": trajectory behaviour is harder to anticipate by hand than text, so the real gate
is a live run whose verdicts are blind-checked against real trajectories (Gate 3).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yaml  # noqa: E402

import grader  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    with open(os.path.join(HERE, "fixtures.yaml")) as fh:
        rows = yaml.safe_load(fh)

    mismatches = []
    for row in rows:
        got = grader.grade({"steps": row["steps"]}, row["prescribed_tool"])["verdict"]
        ok = got == row["expect"]
        note = ""
        if "human_label" in row:
            note = f"   (human would lean '{row['human_label']}'; grader abstains)"
        print(f"{'ok ' if ok else 'XX '}{row['id']:<26} expect={row['expect']:<10} got={got}{note}")
        if not ok:
            mismatches.append((row["id"], row["expect"], got))

    print(f"\n{len(rows) - len(mismatches)}/{len(rows)} fixtures matched the grader")
    print(
        "NOTE: internal consistency (grader vs. its own fixtures), not accuracy. Real validation is\n"
        "blind-checking verdicts against REAL trajectories from a live run (Gate 3)."
    )
    if mismatches:
        print("MISMATCHES:", mismatches)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
