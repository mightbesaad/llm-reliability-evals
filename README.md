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
grader can apply. Seven have a merged vertical slice: frozen probes, a deterministic grader,
regression fixtures, and a runner with live-API and replay paths.

## Status

| Mode | Slice | Grader fixtures | Live validation |
|---|---|---|---|
| 1 — secondary-source over-trust | [`slices/source-overtrust/`](slices/source-overtrust/) | 17/17 | fixture replay only |
| 2 — stale recall as current fact | [`slices/stale-recall/`](slices/stale-recall/) | 16/16 | fixture replay only |
| 3 — confidence–correctness miscalibration | [`slices/confidence-calibration/`](slices/confidence-calibration/) | 20/20 | **live-validated** — `mistral-medium`, 30 samples, verdicts blind-checked against raw responses |
| 4 — sycophancy / capitulation | [`slices/sycophancy/`](slices/sycophancy/) | 17/17 | fixture replay only |
| 5 — false precision / rigor-theater | [`slices/false-precision/`](slices/false-precision/) | 17/17 | fixture replay only |
| 6 — second-order overcorrection | [`slices/overcorrection/`](slices/overcorrection/) | 13/13 | fixture replay only |
| 7 — disconfirmation avoidance | not built yet | — | — (trajectory harness ready; next up) |
| 8 — premature self-certification | [`slices/premature-certification/`](slices/premature-certification/) | 12/12 | **live panel** — 3 Mistral models; none certified prematurely under a fair probe |

Fixture counts are **internal consistency** (grader vs. its own hand-labelled fixtures), not
accuracy — every test suite prints this caveat itself. Real validation is blind-checking verdicts
against real model output; only mode 3 has fully cleared that bar so far.

Known gaps, stated so they don't get lost: the mode-8 panel is Mistral-family only
(cross-provider coverage open); mode 8's *fail* path is proven on adversarial fixtures but has
never been observed live (panel models verify or defer); modes 1/2/4/5/6 await live runs; an
LLM-judge layer for the graders' `uncertain` buckets is designed but not built. See
[`TASKS.md`](TASKS.md) for the full ledger.

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

Licensed **[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)** — use, share, and adapt
freely **with attribution**. See [`LICENSE`](LICENSE).

**Attribute as:** [mightbesaad](https://github.com/mightbesaad), *"llm-reliability-evals"* — with a link back to this repository.
