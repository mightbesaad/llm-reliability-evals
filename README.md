# llm-reliability-evals

[![tests](https://github.com/mightbesaad/llm-reliability-evals/actions/workflows/tests.yml/badge.svg)](https://github.com/mightbesaad/llm-reliability-evals/actions/workflows/tests.yml)

A small, reproducible evaluation suite for **reliability failures in LLM research and agentic
assistants** — the failure modes that surface when a capable model is used for fact-finding,
comparison, decision-support, and tool-driven execution across many turns.

Most public evals target *capability* (can the model do X) or *safety* (will it produce harm).
This suite targets a quieter, high-impact class: **how a capable model fails on ordinary
knowledge work** — over-trusting weak sources, stating stale recall as current fact, miscalibrated
confidence, agreeing under pressure, over-correcting one bug into another, and — in agentic use —
avoiding the check that would disconfirm a claim, or certifying its own work without running the
prescribed external check.

Eight failure modes are defined in [`TAXONOMY.md`](TAXONOMY.md), each with detection criteria a
grader can apply. **All eight have a merged vertical slice**: frozen probes, a deterministic
grader, regression fixtures, and a runner with live-API and replay paths.

## Status

| Mode | Slice | Grader fixtures | Live validation |
|---|---|---|---|
| 1 — secondary-source over-trust | [`slices/source-overtrust/`](slices/source-overtrust/) | 17/17 | **the universal failure** — every panel model's worst or near-worst cell; several fabricated supporting figures that changed between samples |
| 2 — stale recall as current fact | [`slices/stale-recall/`](slices/stale-recall/) | 18/18 | live, 5 models — bare version numbers and "as of today" assertions; one lexicon overturn fed back as a fixture |
| 3 — confidence–correctness miscalibration | [`slices/confidence-calibration/`](slices/confidence-calibration/) | 20/20 | live, 5 models — gpt-5.5's distinct wound (same register on solid and contested claims) |
| 4 — sycophancy / capitulation | [`slices/sycophancy/`](slices/sycophancy/) | 31/31 | live, 5 models — frontier tier swept clean; the grader was itself caught false-failing 6/7 real fails and rebuilt against human labels |
| 5 — false precision / rigor-theater | [`slices/false-precision/`](slices/false-precision/) | 18/18 | live, 5 models — incl. the hedge-then-nine-digit-figure shape the grader correctly failed |
| 6 — second-order overcorrection | [`slices/overcorrection/`](slices/overcorrection/) | 14/14 | live, 5 models — gemini-3.5-flash concluded *nonexistence* in 21/27 records (rule-worship); the exists-vs-rule distinction is the pass |
| 7 — disconfirmation avoidance | [`slices/disconfirmation-avoidance/`](slices/disconfirmation-avoidance/) | 17/17 | **live, clean sweep** — zero fails across all panel models; no one proceeded past a contradiction |
| 8 — premature self-certification | [`slices/premature-certification/`](slices/premature-certification/) | 13/13 | **live, clean sweep** — ~60 trajectories across 5 models + the earlier Mistral panel; the fail path has never been observed (and three fake observations were killed by the blind-check) |

## The frontier panel (2026-07-02/03)

Five models, eight modes, temperature pinned, params recorded in every results file. Every fail
verdict adjudicated in two tiers (mechanical rubric-conformance, then human judgment on
escalations — 10 grader false positives overturned, labels in each file's `blind_check` block).
Every abstain adjudicated by an LLM judge that was **validated against human labels first**
(15/15 primary / 13/15 secondary / 6/8 on the hardest set) and must quote its evidence verbatim
or its verdict is discarded. 402/428 abstains resolved; the rest stay uncertain, on the record.

| | claude-sonnet-5 | gpt-5.5 | gemini-3.5-flash | mistral-medium | mistral-large |
|---|---|---|---|---|---|
| **decided pass-rate** | **97% (197/204)** | 77% (152/197) | 66% (130/196) | 73% (135/186) / 71% (140/197) | 68% (111/164) |
| fails (human-confirmed + judge-attributed) | 7 + 0 | 28 + 17 | 34 + 32 | 28 + 23 | 28 + 25 |
| residual uncertain | 0 | 7 | 8 | 3–7 | 4 |

**Read the top row with a discount:** the probes were authored with Claude-family assistance, so
family-specific contamination of the claude-sonnet-5 result cannot be excluded. The finding this
table is prepared to defend is the *fingerprints*, not the ranking.

The models fail *differently* — calibration for gpt-5.5, rule-worship for gemini, source-trust
for the Mistral tier — which is the point: these are behavioral fingerprints, not a leaderboard.
Same-day drift pair (mistral-medium ×2, n=189/204): 73% vs 71% — stable at this sample size,
though cells are dozens of records, not thousands; treat single-cell differences accordingly.

Fixture counts are **internal consistency** (grader vs. its own hand-labelled fixtures), not
accuracy — every test suite prints this caveat itself. Real validation is the pipeline above,
and its full audit trail (including every time it overruled the graders, twice mid-panel) is in
the results files and [`TASKS.md`](TASKS.md).

Known gaps, stated so they don't get lost: **all human labels come from a single rater** (the
maintainer) — a legitimate constraint for a solo artifact, stated rather than implied;
mode 8's *fail* path has never been observed live —
a defended null result, not a blind spot; 26 records remain uncertain (17 judge parse-failures,
9 evidence-guard discards); the interesting cells await depth interrogation (see
[`slices/specimens/INTERROGATION-PROTOCOL.md`](slices/specimens/INTERROGATION-PROTOCOL.md) and
the ready probe cards); grader gaps from the blind-check are filed as task 6 with their
acceptance fixtures in place.

## The agentic modes grade trajectories, not prose

Modes 7 and 8 can't be graded from a text answer — they're about whether a check *actually ran*.
[`slices/harness.py`](slices/harness.py) drives the model through a real tool-use loop
(provider-dispatched: Anthropic content-block `tool_use`, Mistral function calling) against
**scripted, frozen tools**, and normalizes both providers to one trajectory schema. The mode-8
grader's primary signal is structural — the prescribed tool's presence in the trajectory's
`tool_use` blocks — so it distinguishes *running the check* from *claiming to have run it*.
Scripted tools keep every probe deterministic and make the disconfirming signal controllable,
which is exactly what mode 7 needs.

## Structure

- [`TAXONOMY.md`](TAXONOMY.md) — the eight failure modes: definition, why it matters, detection criteria.
- [`evals/cases.yaml`](evals/cases.yaml) — the original rubric-graded cases (human- or LLM-judge scored).
- `slices/<mode>/` — one vertical slice per mode:
  - `instances.yaml` — the frozen probes;
  - `grader.py` — deterministic grader implementing the mode's detection criteria;
  - `fixtures.yaml` + `test_grader.py` — hand-labelled regression fixtures, including adversarial
    ones written to break the grader;
  - `runner.py` — `--live` (API) and `--replay` (paste-in transcript) paths;
  - `results/` — dated live-run results (`<model>-<YYYY-MM-DD>.json`); sampling params,
    blind-check labels, and regrades are recorded *inside* each file;
  - `README.md` — the slice's design decisions and grader logic.
- [`slices/providers.py`](slices/providers.py) — shared single-turn provider routing
  (Anthropic / Mistral / OpenAI, dispatched by model id).
- [`slices/harness.py`](slices/harness.py) — shared trajectory harness for the agentic modes.
- [`slices/specimens/`](slices/specimens/) — *organic* specimens: unscripted evidence of taxonomy
  modes found in real working sessions, preserved verbatim and tagged, explicitly separated from
  the designed probes.

## How to run

One dependency (`pip install -r requirements.txt` — it's PyYAML), then one command:

```sh
python3 run.py
```

That's the whole offline suite — every unit and grader fixture suite, no keys, no network,
green in under a minute. It is exactly what CI runs.

Live, against any model:

```sh
# a hosted provider (key selects nothing — the model id routes)
MISTRAL_API_KEY=... python3 run.py --live --model mistral-medium --samples 3

# any OpenAI-compatible endpoint: Ollama, vLLM, Groq, Together, OpenRouter, llama.cpp
python3 run.py --live --model llama3.2 --base-url http://localhost:11434/v1
```

One dated results file per slice, sampling params recorded inside, flushed after every record
so an aborted run keeps everything already completed. `python3 run.py --list` shows the modes;
`--mode <slice>` limits the run.

Per-slice work — custom replay files, single scenarios — goes through the slice's own runner:

```sh
python3 slices/<mode>/runner.py --replay fixtures.yaml
python3 slices/<mode>/runner.py --help
```

Live records keep the model's **raw response** alongside the verdict so results can be
blind-checked. That rule exists for a reason: mode 3's original grader passed 100% of its own
fixtures — twice — and still false-failed ~92% of real model output (it graded prose register
instead of stated confidence). The rebuilt grader reads explicit per-item confidence labels and
was validated by blind-checking a live run. **The blind-check, not the fixture count, is the
gate.**

## Build discipline

The suite is built in agentic sessions run under explicit guardrails that mirror the taxonomy
itself — no "tests pass" claims without pasted terminal output, mandatory adversarial fixtures,
independent verification before an instance is added, confidence stated per claim. The guardrails
are recorded at the end of [`TASKS.md`](TASKS.md).

## Contributing

Early / community. Counter-examples, additional cases, live-run results, and grader
implementations welcome — open an issue or PR. The bar for new fixtures: at least some must be
written to *break* the grader, not confirm it.

## License

Dual-licensed by content type (CC licenses are not recommended for software; the taxonomy is
the part attribution should follow):

- **Code and machine-readable data** (Python, YAML, JSON, CI config):
  **[Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0)** — see [`LICENSE`](LICENSE).
- **The taxonomy and prose documentation** ([`TAXONOMY.md`](TAXONOMY.md),
  [`evals/cases.yaml`](evals/cases.yaml), all `*.md`):
  **[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)** — use, share, and adapt freely
  **with attribution**. See [`LICENSE-DOCS`](LICENSE-DOCS).

**Attribute the taxonomy as:** [mightbesaad](https://github.com/mightbesaad),
*"llm-reliability-evals"* — with a link back to this repository.
