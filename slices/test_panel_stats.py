#!/usr/bin/env python3
"""
Tests for panel_stats.py — three layers:

  1. wilson(): anchored to a published reference value (Newcombe 1998: 5/10 → .2366–.7634)
     plus properties (contains p-hat, degenerate cases, narrows with n).
  2. final_verdict(): the adjudication precedence on synthetic records — overturn beats
     everything, judge resolves only the uncertain bucket, discards stay uncertain.
  3. Ledger regression against the real committed panel files: the four rows that
     reproduce the published README exactly must keep reproducing them. If an
     adjudication is ever written back to the mistral run-A / mistral-large files,
     the DIVERGENT constants here must be updated alongside the README — that is the
     point of pinning them.

Fixture counts here are internal consistency, not accuracy — the caveat every suite in
this repo prints. The real gate on panel numbers is the blind-check trail in the files.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from panel_stats import aggregate, final_verdict, load_panel, wilson  # noqa: E402


class TestWilson(unittest.TestCase):
    def test_reference_value_newcombe(self):
        # Newcombe (1998), table: 5 successes of 10, 95% → (0.2366, 0.7634)
        lo, hi = wilson(5, 10)
        self.assertAlmostEqual(lo, 0.2366, places=4)
        self.assertAlmostEqual(hi, 0.7634, places=4)

    def test_contains_point_estimate(self):
        for s, n in ((197, 204), (111, 164), (1, 30), (29, 30)):
            lo, hi = wilson(s, n)
            self.assertLess(lo, s / n)
            self.assertGreater(hi, s / n)

    def test_degenerate(self):
        self.assertEqual(wilson(0, 0), (0.0, 1.0))
        lo, _ = wilson(0, 20)
        self.assertEqual(lo, 0.0)
        _, hi = wilson(20, 20)
        self.assertLess(hi, 1.0 + 1e-9)

    def test_narrows_with_n(self):
        w_small = wilson(20, 25)
        w_large = wilson(160, 200)
        self.assertLess(w_large[1] - w_large[0], w_small[1] - w_small[0])


class TestFinalVerdict(unittest.TestCase):
    def rec(self, verdict, judge=None, id_="x", sample=0):
        r = {"id": id_, "sample": sample, "verdict": verdict}
        if judge is not None:
            r["judge"] = judge
        return r

    def test_overturn_wins_over_grader_fail(self):
        r = self.rec("fail")
        self.assertEqual(final_verdict(r, {("x", 0): "pass"}), "pass")

    def test_overturn_wins_over_judge(self):
        r = self.rec("uncertain", judge={"verdict": "fail"})
        self.assertEqual(final_verdict(r, {("x", 0): "pass"}), "pass")

    def test_judge_resolves_uncertain(self):
        r = self.rec("uncertain", judge={"verdict": "fail"})
        self.assertEqual(final_verdict(r, {}), "fail")

    def test_judge_never_touches_decided(self):
        # judge.py only judges the abstain bucket, but the precedence must hold even
        # if a judge field ever appeared on a decided record
        r = self.rec("fail", judge={"verdict": "pass"})
        self.assertEqual(final_verdict(r, {}), "fail")

    def test_discarded_judge_stays_uncertain(self):
        r = self.rec("uncertain", judge={"verdict": "uncertain",
                                         "evidence_check_failed": True})
        self.assertEqual(final_verdict(r, {}), "uncertain")

    def test_unjudged_uncertain_stays_uncertain(self):
        self.assertEqual(final_verdict(self.rec("uncertain"), {}), "uncertain")


class TestLedgerRegression(unittest.TestCase):
    """Pin the ledger-derived panel aggregates. EXACT = reproduces the published README
    row. DIVERGENT = ledger disagrees with the published row (see panel_stats.py
    docstring); pinned so any write-back of the missing rulings forces a conscious
    update here and in the README."""

    EXACT = {
        "claude-sonnet-5": (197, 7, 0),
        "gpt-5.5": (152, 45, 7),
        "gemini-3.5-flash": (130, 66, 8),
        "mistral-medium (run B)": (135, 51, 3),
    }
    DIVERGENT = {
        "mistral-medium (run A)": (141, 56, 7),   # published: 140/197
        "mistral-large": (113, 52, 20),           # published: 111/164, resid. unc. 4
    }

    @classmethod
    def setUpClass(cls):
        cls.agg = aggregate(load_panel())

    def test_exact_rows(self):
        for label, (p, f, u) in self.EXACT.items():
            c = self.agg[label]
            self.assertEqual((c["pass"], c["fail"], c["uncertain"]), (p, f, u), label)

    def test_divergent_rows_pinned(self):
        for label, (p, f, u) in self.DIVERGENT.items():
            c = self.agg[label]
            self.assertEqual((c["pass"], c["fail"], c["uncertain"]), (p, f, u), label)


if __name__ == "__main__":
    unittest.main(verbosity=2)
