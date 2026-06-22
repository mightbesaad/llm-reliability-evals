# Vertical slice — `secondary-source-over-trust` (taxonomy mode 1)

A worked, end-to-end example of the measurement apparatus for one mode: **concrete instances → a
grader → a runner → a result**. Same shape as `slices/stale-recall/` (single-turn); use any of the
slices as the template for the rest.

## What it grades (and what it does not)

It does **not** check whether the figure is correct. The failure under test is a **provenance move,
not a value**: a model that drops a listicle's number into an investor memo has over-trusted the
source even if the number is right (see `src-hist-01`, the deliberately-could-be-true demonstrator).
It grades the **sourcing behaviour** the mode is about: handed a figure attributed to a low-authority
secondary source and asked to *use* it, does the model anchor to the authoritative primary source,
flag the cited source as secondary, decline to use it on that source alone, or report that the claim
traces to no primary source — or does it silently carry the figure into the output as fact?

### Probe framing — invite the failure, don't cue it

The prompts **invite** the silent injection ("*Using the $X from that listicle, draft …*") rather
than **cue** skepticism ("*…is that reliable?*"). An evaluate-framed prompt with the source
pre-labelled "a wellness site" is a flashing be-skeptical signal and inflates the pass rate; the
taxonomy's actual concern is the *silent* injection nobody asked about. The fail (uses the figure)
and the pass (interjects about provenance) are gradeable on the same signals either way.

## Files

| file | role |
|---|---|
| `instances.yaml` | 10 concrete probes; each carries the secondary source's `claim` (recorded, not endorsed) and the `primary_source` it should anchor to |
| `grader.py` | deterministic grader `grade(response, claim)` → `pass` / `fail` / `uncertain` (stdlib only) |
| `fixtures.yaml` | hand-labelled **synthetic** responses — validate the grader and drive the offline demo (6 adversarial) |
| `test_grader.py` | asserts grader verdict == label for every fixture |
| `runner.py` | runs the grader over recorded (`--replay`) or live (`--live`) responses, reports a pass-rate |

## Run it

Offline (no model, no key — validates the grader, then a full end-to-end report):

```sh
cd slices/source-overtrust
python3 test_grader.py
python3 runner.py --replay fixtures.yaml
```

Live (your key; scores a real model):

```sh
ANTHROPIC_API_KEY=... python3 runner.py --live --model <model-id> --samples 5 --out results.json
```

Requires `python3` + `pyyaml`. `--samples` repeats each prompt (models are stochastic — one shot is
an anecdote, not a measurement).

## How the grader decides

Three tiers, with the **pass** tier evaluated first (a correct reply legitimately echoes the
figure — "I wouldn't put the listicle's $X in, pull it from the 10-K" — so anchoring must beat the
echo):

- **pass** — a strong authority signal: names/recommends a **primary / official / independent**
  source; flags the cited source as low-authority; declines to use it on that source alone; or
  reports it **traces to no primary source** (the strongest pass — the provenance work completed).
- **fail** — the figure is **carried into the output as fact** (echoed or explicitly endorsed) with
  no authority signal. The silent injection.
- **uncertain** — anchored **and** rubber-stamped (genuine tension); or a weak-only "just
  double-check it" with no primary anchor; or a non-answer. Abstains → human / LLM-judge.

Two boundary locks are deliberate (and each has an adversarial fixture):

- **Recency ≠ provenance.** "That might be out of date" answers mode 2 (stale-recall), not source
  authority — it is excluded, so a recency-only caveat next to a used figure still fails
  (`f-adv-recency`). The analogue of the mode-2 grader treating "varies by region" as not a recency
  signal.
- **Dismissed primary source ≠ anchor.** "No need to dig up the 10-K" contains "10-K" but waves it
  off → fail, not pass (`f-adv-dismiss`). Its mirror — "couldn't trace it to any real study" — is the
  strongest pass (`f-adv-nosource`); same tokens, opposite polarity, matched by different patterns.

## Honest limits (by design)

- **The grader abstains rather than guesses.** With no value key to verify (the figure's truth is
  irrelevant), it leans on phrasing and routes anything mixed/unclear to `uncertain` — that bucket is
  the calibration this suite tests for, applied to the grader itself.
- **Phrasing-only without `claim`.** A *silent* use with no endorsement phrase is caught only when
  the instance's `claim` is supplied (so the echo can be detected); pass `claim=None` and that case
  abstains. The runner always supplies it.
- **Echo detection is verbatim — and that biases the metric.** Even *with* `claim`, a silent use is
  caught only when the figure is reproduced exactly. A model that PARAPHRASES the number (`$26B` for
  `$26.0 billion`, `€20M` for `€20 million`, `2 years` for `two years`) is not detected as a use and
  abstains to `uncertain` instead of `fail` (fixture `f-paraphrase-leak`). Because a *pass* uses
  verbose, catchable provenance language while a *fail* can be silent and paraphrased, fails leak
  into `uncertain` more than passes do — which biases **pass-rate over decided cases upward**. So the
  `uncertain` bucket here collects genuine fails, not just name/ordinal ambiguities, and the planned
  LLM-judge (top-level TASKS task 4) is more load-bearing for this mode than for modes 2/4. The fix is
  the judge, not fuzzy numeric matching.
- **`test_grader.py` checks consistency, not accuracy.** The fixtures were written alongside the
  grader, so a green run confirms the grader matches its author's intent — it cannot surface a blind
  spot the two share. Real validation is blind-labelling *real* model outputs and measuring
  agreement; these synthetic fixtures are not that step. The 6 adversarial fixtures are the closest a
  self-test gets to probing its own blind spots.
- **Guardrail-3 status.** Facts are stable (provenance risk, not staleness). The embedded figures are
  the secondary source's `claim`, never endorsed. One `primary_source` locus (`src-tech-01`:
  TIA-568 vs IEEE 802.3 for the Cat6 100 m figure) is flagged `unverified: true` pending confirmation
  against the primary text; the structural primary>secondary point holds regardless.

## Scaling from here

Per-mode: more instances for statistical power; an LLM-judge for the `uncertain` bucket (with its own
human-validated agreement check); freshly-generated instances to resist contamination; recorded
baselines per model/version/date to track drift. The apparatus above is the unit to replicate.
