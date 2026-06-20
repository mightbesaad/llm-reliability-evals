#!/usr/bin/env python3
"""
Validate the stale-recall grader against the hand-labelled fixtures.

Run:  python3 test_grader.py     (from this directory)
Exits nonzero on any mismatch between grader verdict and the fixture's `expect`.

This is the slice's own check that the grader works — the apparatus is validated against
labelled data before any model is scored with it, rather than self-certified.
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
        got = grader.grade(row["response"])["verdict"]
        ok = got == row["expect"]
        flag = "ok " if ok else "XX "
        note = ""
        if "human_label" in row:
            note = f"   (human would call this '{row['human_label']}' — grader abstains by design)"
        print(f"{flag}{row['id']:<16} expect={row['expect']:<10} got={got}{note}")
        if not ok:
            mismatches.append((row["id"], row["expect"], got))

    print(f"\n{len(rows) - len(mismatches)}/{len(rows)} fixtures matched the grader")
    print(
        "NOTE: this checks internal consistency (grader vs. its own hand-written fixtures), not\n"
        "accuracy. Real validation is blind-labelling REAL model outputs and measuring agreement;\n"
        "these synthetic fixtures are not that step."
    )
    if mismatches:
        print("MISMATCHES:", mismatches)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
