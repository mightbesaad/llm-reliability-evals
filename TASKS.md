# Tasks — handoff

Repo: `mightbesaad/llm-reliability-evals`

Status (2026-06-26): **7 of 8 modes** are merged into `main` — `slices/stale-recall/` (mode 2),
`slices/sycophancy/` (mode 4), `slices/overcorrection/` (mode 6), `slices/source-overtrust/`
(mode 1), `slices/false-precision/` (mode 5), `slices/confidence-calibration/` (mode 3),
`slices/premature-certification/` (mode 8). Slice graders pass offline (16/16, 17/17, 13/13, 17/17,
17/17, 20/20, 12/12 respectively). **Only mode 7 (disconfirmation avoidance) remains, and it is no
longer blocked** — `slices/harness.py`, the shared trajectory harness, is built and proven (mode 8
runs on it). Mode 3 was rebuilt (a prose-register grader false-failed real output at 92%; it now
grades explicit per-item confidence labels) and live-validated against `mistral-medium`. **Mode 8
finding:** under a fair probe a 3-model Mistral panel showed *no model prematurely certified* — but
that is **Mistral-family only; cross-provider coverage is open** (see task 1 gaps). Modes 1/2/4/5/6
have only synthetic-fixture replay (see task 2). No results fabricated; only `main` remains, synced
with `origin`.

**Update (2026-07-02):** project definition settled — this is an **open, model-agnostic
instrument**. The suite itself stays free and independent (eval credibility requires it); any
billable application (panels run for a client, qualification gates, evidence packs, drift report
cards) lives *outside* this repo and consumes it. That definition drives task 4: a model-agnostic
provider layer and a one-command run are core properties, not polish. Same day: README rewritten to
reflect the actual repo, CI (offline fixture suites) added, v0.1.0 tagged, About/topics filled.

## Open / not yet done

1. **Build mode 7 (disconfirmation avoidance)** — the last of the original 8. **No longer blocked:**
   `slices/harness.py` (the shared trajectory harness) is built and proven on mode 8, and reuses
   cleanly — mode 7 is the same trajectory shape with a *failing* scripted check and a grader that
   reads whether the model **surfaced the disconfirming result** (vs mode 8's "did it run the check at
   all"). It's now a buildable text+trajectory slice like any other, not a blocked one.

   Mode 8 (`premature-certification`) is merged but carries **still-open gaps** — recorded so they
   don't get lost:
   - `mistral-large-latest` is **untested** — rate-limited (HTTP 429) on every attempt; retriable when
     the key's quota resets.
   - the **Anthropic leg is unrun** (no key provisioned), so the panel is Mistral-family only —
     **cross-provider coverage (a genuinely different lab) is open**.
   - the **fail path is validated on fixtures only**: no panel model has ever actually committed mode 8
     live (they verify or defer), so a real premature-certification has not yet been graded on real
     output. The adversarial fixtures prove the grader *would* catch one.

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

4. **Instrument hardening — model-agnostic + one-command run.** A dependency-ordered PR ladder;
   each PR is guarded by what the previous one built, and `main` stays shippable at every boundary.
   - **PR 1 — harness offline tests**: `slices/test_harness.py`, mocked HTTP. Pins the trajectory
     normalization contract (schema parity across providers, stop-reason mapping, unscripted-tool
     error results, max-turns cap, parallel calls) *before* anything touches the harness. In CI.
   - **PR 2 — provider layer**: uniform sampling params sent to *every* provider — today Anthropic
     gets no temperature + `max_tokens: 512` while Mistral/OpenAI get `0.7` + provider-default
     max_tokens, so any cross-provider comparison is confounded until this lands (this silently
     blocks the mode-8 Anthropic leg in task 1). Plus: an OpenAI-compatible `base_url` path
     (Ollama / vLLM / Groq / OpenRouter / local — model-agnostic for real); retry with backoff on
     429/5xx (likely closes the `mistral-large` 429 gap without waiting on quota); urllib-only so
     deps collapse to `pyyaml`; `ProviderError` raised from library modules instead of `SystemExit`.
   - **PR 3 — live-run durability**: incremental flush (today a crash at sample 29/30 discards all
     30 paid calls — results are only written at the end); extract *only* report/args/results-writing
     into a shared runlib. `run_live` / `run_replay` stay per-slice — self-containment is deliberate.
   - **PR 4 — entry point**: top-level `run.py`; bare invocation = all offline suites, zero keys,
     green in under a minute (the contributor-conversion path). README rewritten around it.
   - **PR 5 — results convention**: `slices/<mode>/results/<model>-<YYYY-MM-DD>.json` plus a
     `params` block *inside* every results file — sampling params are currently recorded nowhere,
     which quietly undermines the reproducibility claim. Retire `-latest` filenames.
   - **PR 6 — license split**: Apache-2.0 for code, CC-BY-4.0 retained for TAXONOMY.md and docs
     (CC licenses are not recommended for software; attribution keeps flowing where it matters —
     the taxonomy). Owner eyeballs this one before it lands.

   **Mode 7 starts after PR 2**, in parallel with PRs 3–5 — on a harness that is by then tested
   (PR 1) and retry-hardened (PR 2). The mode-3 lesson applies to infrastructure too: don't build
   the last mode on an untested substrate.

## Recommendation

**Mode 7 (disconfirmation avoidance) is next — the last of the original 8.** It is no longer
harness-blocked: `slices/harness.py` is built and proven on mode 8, and mode 7 reuses it with a
*failing* scripted check. After that, the open cross-cutting work is the **LLM-judge layer** (task 3)
plus closing mode 8's gaps (cross-provider panel, the live fail path). Mode 3's rebuild stays the
cautionary tale — a grader green on its own fixtures (twice) was broken on real output, so the live
blind-check, not the fixture count, is the gate (see guardrails).

**(2026-07-02) Sequencing revised:** instrument hardening (task 4) PRs 1–2 land first — tests, then
the provider layer — because mode 7 builds on the harness and the mode-8 Anthropic leg is confounded
until sampling params are uniform. Mode 7 then proceeds in parallel with PRs 3–5.

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
