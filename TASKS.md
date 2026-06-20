# Tasks — handoff

Repo: `mightbesaad/llm-reliability-evals`

Unmerged branches (both verified to merge into `main` with zero conflicts):
- `redteam/modes-7-8-and-case-fill`
- `redteam/slice-stale-recall`

## Open / not yet done

1. **Merge both branches into `main`.**
   - `redteam/modes-7-8-and-case-fill`: adds taxonomy modes 7 (disconfirmation avoidance) and
     8 (premature self-certification), broadens framing to agentic/tool-driven use, adds 3 missing
     cases (`falseprec-01`, `disconf-01`, `selfcert-01`).
   - `redteam/slice-stale-recall`: adds `slices/stale-recall/` — full runnable harness for mode 2
     (`instances.yaml`, `grader.py`, `fixtures.yaml`, `test_grader.py`, `runner.py`). 16/16 fixtures
     pass; replay runs end to end.

2. **Build out the remaining 7 of 8 modes** using `slices/stale-recall/` as the template. Each
   mode needs:
   - `instances.yaml` — concrete, frozen prompts (no bracket placeholders)
   - `grader.py` — deterministic grader; abstain (`uncertain`) rather than guess on ambiguous cases
   - `fixtures.yaml` — hand-labeled pass/fail/uncertain example responses
   - `test_grader.py` — validates grader against fixtures
   - `runner.py` — `--replay` (offline) and `--live` (real API call + pass-rate report)

   Priority: mode 4 (sycophancy) or mode 6 (second-order-overcorrection) next — both are two-turn,
   text-only, and fit this pattern directly with no new infrastructure.

3. **Run a live eval** — no real model results exist yet, only synthetic-fixture replay has been
   executed.
   ```sh
   ANTHROPIC_API_KEY=... python3 slices/stale-recall/runner.py --live \
     --model <model-id> --samples 5 --out results.json
   ```

4. **Build a trajectory-based harness for modes 7–8** (disconfirmation avoidance, premature
   self-certification). These are agentic/tool-use failures — a final-text grader doesn't apply.
   Needs to observe the tool-call sequence, not just the last message. Not started.

5. **Add an LLM-judge layer for the grader's `uncertain` bucket.** The current `grader.py` abstains
   on name/ordinal answers (e.g. "the CEO is X") since they carry no numeric pattern. Needs an
   LLM-judge, itself validated against human labels, before the uncertain bucket can be trusted.

## Recommendation

Next slice to build: mode 4 (sycophancy) or mode 6 (second-order-overcorrection) — both two-turn,
text-only, same harness shape as `slices/stale-recall/`. Hold modes 7–8 until a trajectory-observing
harness exists.

## Schema note (settled)

Keep `mode`, optionally alias to `failure_mode` for readability. Do NOT collapse
instances/fixtures/grader into one flat YAML record per case. Reasons: `ground_truth` as a universal
field breaks for stale-recall (it grades calibration behavior, not a fixed value); a single
`failure_example` can't replace a pluralized fixtures file used for grader regression-testing;
`pass_criteria` alone drops the fail-condition half that the taxonomy's detection logic is actually
built around.

## Guardrails for the building agent

The agent's narrative summary of its own work is not evidence. Every claim below must be backed by
something verifiable, not asserted.

1. No claims of "tests pass" / "merge is clean" / "fixtures validated" without pasting the literal
   terminal output (command + stdout + exit code). A paraphrase does not count.
   *[guards against mode 8 — premature self-certification]*
2. Do not write `fixtures.yaml` and `grader.py` from the same assumption and call it validated —
   that's circular (`slices/stale-recall/README.md` says this about itself: "checks consistency, not
   accuracy"). For each new mode, add 2–3 fixtures specifically designed to try to break the grader,
   not just ones expected to pass. *[guards against mode 5 — rigor-theater / unearned validation]*
3. Before adding any instance to `instances.yaml`, verify the underlying fact independently (primary
   source, not parametric memory) before marking it volatile or writing the `why`. Anything not
   independently checked gets flagged `unverified: true`, not stated as fact.
   *[guards against mode 1 and mode 2 — the exact failures being tested for]*
4. After any change to `grader.py`, re-run `test_grader.py` and report the full pass/fail count —
   not "I updated the grader." A new pass on one case that silently flips a previously-passing case
   to fail is the failure this regression check exists to catch.
   *[guards against mode 6 — second-order overcorrection]*
5. If something can't actually be run (no API key, no network), say so explicitly. Do not fabricate
   a plausible `results.json` or describe a "live" run that didn't happen.
   *[guards against hallucinated results]*
6. State confidence per claim, not uniformly. "Confident the grader handles X; have not tested Y" is
   the expected register. *[guards against mode 3 — confidence-correctness miscalibration]*
7. If corrected or pushed back on, re-verify before agreeing or holding firm. Don't adopt the
   correction wholesale or just restate the original claim — show the re-check either way.
   *[guards against mode 4 — sycophancy / capitulation]*
