# llm-reliability-evals

A small, reproducible evaluation suite for **reliability failures in LLM research and agentic
assistants** — the failure modes that surface when a capable model is used for fact-finding,
comparison, decision-support, and tool-driven execution across many turns.

Most public evals target *capability* (can the model do X) or *safety* (will it produce harm).
This suite targets a quieter, high-impact class: **how a capable model fails on ordinary
knowledge work** — over-trusting weak sources, stating stale recall as current fact, miscalibrated
confidence, agreeing under pressure, over-correcting one bug into another, and — in agentic use —
avoiding the check that would disconfirm a claim or certifying its own work.

Each failure mode is defined in [`TAXONOMY.md`](TAXONOMY.md) and probed by reproducible cases in
[`evals/cases.yaml`](evals/cases.yaml), each with an explicit grading rubric so results can be
scored consistently and tracked across models and versions.

## How to run / score

1. Send each case's `prompt` (and any `followup`) to the model under test, with no extra context.
2. Score the response against the case's `rubric` (`pass` / `fail`), human- or LLM-judge graded.
3. Log model name, version, date, and verdict. Re-run on new model versions to track drift.

## Structure

- `TAXONOMY.md` — the failure modes, each with a definition, why it matters, and detection criteria.
- `evals/cases.yaml` — reproducible test cases (setup, prompt, target failure, grading rubric).

## Status

Early / community. Counter-examples, additional cases, and grader implementations welcome —
open an issue or PR.

## License

Licensed **[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)** — use, share, and adapt
freely **with attribution**. See [`LICENSE`](LICENSE).

**Attribute as:** [mightbesaad](https://github.com/mightbesaad), *"llm-reliability-evals"* — with a link back to this repository.
