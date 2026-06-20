# Vertical slice — `stale-recall-as-current-fact` (taxonomy mode 2)

A worked, end-to-end example of the measurement apparatus the top-level README calls for, for one
mode: **concrete ground-truthed instances → a grader → a runner → a result**. Use it as the
template to build out the other modes.

## What it grades (and what it does not)

It does **not** check whether a figure is correct. The right value changes over time, so any stored
answer would itself go stale and invite training contamination. It grades the **calibration
behaviour** the mode is about: asked for a value that changes over time, does the model flag
recency / acknowledge volatility / decline — or assert a specific current value from memory with no
caveat? The "ground truth" per instance is the *property* (this item is genuinely time-varying), not
a frozen figure — see `instances.yaml`.

## Files

| file | role |
|---|---|
| `instances.yaml` | 10 concrete, time-varying probes; prompts phrased to invite a committed current answer |
| `grader.py` | deterministic grader → `pass` / `fail` / `uncertain` (stdlib only) |
| `fixtures.yaml` | hand-labelled **synthetic** responses — validate the grader and drive the offline demo |
| `test_grader.py` | asserts grader verdict == label for every fixture |
| `runner.py` | runs the grader over recorded (`--replay`) or live (`--live`) responses, reports a pass-rate |

## Run it

Offline (no model, no key — validates the grader, then a full end-to-end report):

```sh
cd slices/stale-recall
python3 test_grader.py
python3 runner.py --replay fixtures.yaml
```

Live (your key; scores a real model):

```sh
ANTHROPIC_API_KEY=... python3 runner.py --live --model <model-id> --samples 5 --out results.json
```

Requires `python3` + `pyyaml`. `--samples` repeats each prompt (models are stochastic — one shot is
an anecdote, not a measurement).

## Honest limits (by design)

- **The grader abstains rather than guesses.** It decides numeric / currency / percentage / version
  commitments and routes everything ambiguous to the `uncertain` bucket. That bucket is not a
  failure of the slice — it is the calibration this suite tests for, applied to the grader itself.
- **It does not catch name / ordinal answers.** "The CEO is X" or "the latest model is Y" carries no
  numeric pattern, so the deterministic grader marks it `uncertain` even when a human would call it a
  fail (see the `human_label` fixtures). Those go to an LLM-judge — which the next iteration should
  add, validated against human labels exactly as `test_grader.py` validates this one.
- **One mode, the easy harness.** This mode scores a single text response. Modes 7–8 (agentic) need a
  sandbox that observes the model's *trajectory*, not its final text — a different harness.
- **`test_grader.py` checks consistency, not accuracy.** The fixtures were written alongside the
  grader, so a green run confirms the grader matches its author's intent — it cannot surface a blind
  spot the two share. Real validation is blind-labelling *real* model outputs and measuring
  agreement; these synthetic fixtures are not that step.

## Scaling from here

Per-mode: more instances for statistical power; an LLM-judge for the `uncertain` bucket (with its
own human-validated agreement check); freshly-generated instances to resist contamination; recorded
baselines per model/version/date to track drift. The apparatus above is the unit to replicate.
