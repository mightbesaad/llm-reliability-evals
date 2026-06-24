# Tasks — handoff

Repo: `mightbesaad/llm-reliability-evals`

Status (2026-06-24): **6 of 8 modes** are merged into `main` — `slices/stale-recall/` (mode 2),
`slices/sycophancy/` (mode 4), `slices/overcorrection/` (mode 6), `slices/source-overtrust/`
(mode 1), `slices/false-precision/` (mode 5), `slices/confidence-calibration/` (mode 3). All six
slice graders pass offline (16/16, 17/17, 13/13, 17/17, 17/17, 20/20 fixtures respectively). **All
text-only modes (1–6) are done; only modes 7–8 remain** (blocked on the trajectory harness, task 1).
Mode 3 was rebuilt (a prose-register grader proved unworkable — it false-failed real output at 92%;
it now grades explicit per-item confidence labels) and **live-validated** against `mistral-medium`;
modes 1/2/4/5/6 have only synthetic-fixture replay (see task 2). No results fabricated. All feature
branches are merged and deleted; only `main` remains, synced with `origin`.

## Open / not yet done

1. **Build a trajectory-based harness for modes 7–8** (disconfirmation avoidance, premature
   self-certification) — now the **only remaining mode work**, since modes 1–6 are all merged. These
   are agentic/tool-use failures: a final-text grader doesn't apply; it must observe the tool-call
   sequence, not just the last message. Not started.

   Decision (recorded so it is not lost to chat history): prefer **forward-instrumenting the
   tool-call cycle going forward** — capturing calls as they happen — over historical reconstruction.
   A file-history-versus-timestamp correlation is a **weak supplementary** signal, usable only for
   **mode 8**, and only shows whether files were still changing when "done" was declared — it cannot
   show whether the prescribed check (tests, lint) actually ran. Useful as a cheap first-pass flag,
   not a substitute for real trajectory data.

2. **Get real-model data via API or manual chat-paste-replay.** Live API testing is permitted; the
   `--live` path in every runner is available. Mode 3 has been live-validated against `mistral-medium`
   (30 samples, blind-checked against the raw responses — extraction faithful, the lone fail a true
   positive, abstentions honest). Modes 1/2/4/5/6 still have only synthetic-fixture replay and want
   the same treatment.
   ```sh
   # Live (API):
   MISTRAL_API_KEY=... python3 slices/<mode>/runner.py --live --model mistral-medium --samples 3 --out results.json
   # Or manual: paste a slice prompt into claude.ai, copy the literal reply into a fixtures-style
   # entry { id, response: "<verbatim>", expect: <blind label> }, then --replay it.
   ```
   The **blind-check** (read the raw responses; confirm verdicts are sane) is the real gate — not the
   count of decisions. That is the step whose absence shipped a broken mode-3 grader twice. The
   confidence-calibration runner now keeps the raw response in `--live` records to make this possible.

3. **Add an LLM-judge layer for the grader's `uncertain` bucket**, itself validated against human
   labels before the uncertain bucket can be trusted. Most **load-bearing for modes 3, 1, and 5**:
   mode 3 abstains on ~60% of real output by design (the H==M cases a deterministic grader can't
   adjudicate); mode 1's bucket holds paraphrased figures the verbatim echo-check misses; mode 5's
   holds buried caveats. The judge is also the route to reading *natural-prose* calibration for mode 3
   (the deterministic grader reads only explicit confidence labels).

## Recommendation

All text-only modes (1–6) are merged, and mode 3 is live-validated. Remaining work: the **trajectory
harness for modes 7–8** (task 1) and the **LLM-judge layer** (task 3). Mode 3's rebuild is the
cautionary tale for both — a grader green on its own fixtures (twice) was broken on real output, so
the live blind-check, not the fixture count, is the gate (see guardrails).

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
