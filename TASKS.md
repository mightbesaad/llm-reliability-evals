# Tasks — handoff

Repo: `mightbesaad/llm-reliability-evals`

Status (2026-06-23): **5 of 8 modes** are merged into `main` — `slices/stale-recall/` (mode 2),
`slices/sycophancy/` (mode 4), `slices/overcorrection/` (mode 6), `slices/source-overtrust/`
(mode 1), `slices/false-precision/` (mode 5). All five slice graders pass offline (16/16, 17/17,
13/13, 17/17, 17/17 fixtures respectively). No paid live eval has been run (see task 2); no results
fabricated. Feature branches are merged; `redteam/slice-source-overtrust` has been deleted from
`origin`, `redteam/slice-false-precision` is local-only.

## Open / not yet done

1. **Build the last text-only mode — mode 3** (confidence-correctness miscalibration), using any
   existing slice as the template. It is the **only** buildable text-only mode left; modes 1 and 5
   are now done and merged. Modes 7, 8 stay BLOCKED on the trajectory harness (task 3); hold.

   The mode needs `instances.yaml` / `grader.py` / `fixtures.yaml` / `test_grader.py` / `runner.py`
   (concrete frozen prompts; a deterministic grader that abstains on ambiguity; hand-labelled
   fixtures including 2–3 adversarial ones per guardrail 2; `--replay` offline + the unused `--live`).

   Note (guardrail 6): mode 3 is the **hardest design** of the fuzzy set — its grader will lean
   hardest on the `uncertain` bucket. Its Card-1 plan gets full review before any build begins.

2. **Get real-model data via API or manual chat-paste-replay.** Live API testing is
   permitted; the `--live` path in every runner is available for this purpose. Alternatively,
   paste each case's frozen prompt into claude.ai, copy the literal reply into a
   fixtures-style entry, and `--replay` it:
   ```sh
   # Live (API):
   ANTHROPIC_API_KEY=... python3 slices/<mode>/runner.py --live --model <model-id> --samples 5 --out results.json
   
   # Or manual copy-paste:
   # 1. paste a slice prompt into claude.ai → 2. copy the literal response into an entry:
   #    { id, instance, response: "<verbatim model text>", <claim|precision_unwarranted>, expect: <blind label> }
   # 3. run it offline:
   python3 slices/<mode>/runner.py --replay real_responses.yaml
   ```
   Note: No paid live eval has been run yet; only synthetic-fixture replay has been executed
   so far. The `--live` path is intentionally preserved in every runner for portability.

3. **Build a trajectory-based harness for modes 7–8** (disconfirmation avoidance, premature
   self-certification). These are agentic/tool-use failures — a final-text grader doesn't apply; it
   must observe the tool-call sequence, not just the last message. Not started.

   Decision (recorded so it is not lost to chat history): prefer **forward-instrumenting the
   tool-call cycle going forward** — capturing calls as they happen — over historical reconstruction.
   A file-history-versus-timestamp correlation is a **weak supplementary** signal, usable only for
   **mode 8**, and only shows whether files were still changing when "done" was declared — it cannot
   show whether the prescribed check (tests, lint) actually ran. Useful as a cheap first-pass flag,
   not a substitute for real trajectory data.

4. **Add an LLM-judge layer for the grader's `uncertain` bucket**, itself validated against human
   labels before the uncertain bucket can be trusted. More **load-bearing for modes 1 and 5** than
   for 2/4/6: their abstain buckets collect genuine failures — mode 1, paraphrased figures the
   verbatim echo-check misses; mode 5, buried caveats and a bidirectional abstain-skew — not just the
   name/ordinal ambiguities stale-recall abstains on.

## Recommendation

Next slice to build: **mode 3** (confidence-correctness miscalibration) — the last of the buildable
text-only set, and the hardest design of the three fuzzy modes, so its Card-1 plan gets full review
before any build. Modes 7–8 wait on the trajectory harness (task 3).

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
