# Probe protocol — rotation with commitment

How this suite keeps its probes out of training corpora without giving up the property
the whole repo is built on: **everything used is public, every number is re-derivable.**

Adopted 2026-07-15. Applies from the next panel onward; the 2026-07-02/03 frontier panel
predates it and carries the contamination caveats already stated in the README.

---

## The threat model, stated precisely

Two different things get called "contamination":

1. **Answer memorization** — a model trains on the published probes and their graded
   results, and passes by recall rather than behavior. This is the fraud the protocol
   kills: a probe that is public before it is used is dead as a measurement.
2. **Behavior learning** — a model trains on the taxonomy and gets genuinely better at
   avoiding the failure modes. This is the suite working as intended, and no defense
   against it is wanted. The taxonomy and graders stay public on purpose.

What the protocol does **not** defend against: the provider being tested sees the probes
at run time by definition (they arrive through its API). A provider could in principle
log and train on them. Rotation limits the damage to one panel window; the residual
exposure is disclosed here rather than pretended away.

## The cycle, per panel

1. **Author** a fresh probe batch: 2–3 new probes per mode (the freshness budget — full
   regeneration each panel is the maintenance grind that kills solo instruments; a small
   fresh core plus the bridge subset below is the sustainable dose). Same authoring
   discipline as ever: independent fact verification before an instance lands, adversarial
   fixtures, the guardrails at the end of `TASKS.md`.
2. **Commit before running.** Serialize the fresh batch (`instances.yaml` files, byte-exact),
   hash it (SHA-256 per file plus one hash over the sorted concatenation), and record the
   commitment **before the first API call**, in two layers:
   - **Git (mandatory, publicly verifiable):** commit a `commitments/<panel-date>.txt`
     file containing the hashes — not the probes — and push. The public timestamp is the
     commitment; anyone can later verify the published probes hash to it.
   - **Witness chain (layered):** record the same hash as an `audit-event-mcp` event and
     keep the returned `chain_hash`. The eval's own probes are witnessed by the same
     tamper-evident log the maintainer ships — the receipt is independent of git history.
3. **Run the panel.** Temperature pinned, params in every results file, blind-check and
   judge layers unchanged — the commitment changes nothing about adjudication.
4. **Publish everything.** Probes, raw responses, verdicts, labels — the full batch goes
   public with the results. Openness is preserved retroactively: nothing stays hidden,
   nothing was public *before it had done its job*.

A third party verifies in three steps: hash the published probe files, find that hash in
a git commit (and/or witness event) dated before the results files' timestamps, done.

## The bridge subset

Fresh probes each panel would break longitudinal claims — "model X regressed since May"
must not be confounded with "the May probes were easier." So each panel carries a
**bridge subset** forward: a marked selection of the previous panel's probes, reused
exactly once, then retired. Training crawls lag by months; a probe published in July is
a usable bridge for a model trained before roughly year-end, and the residual risk is
disclosed per-result (`bridge: true` in the record). Cross-panel deltas are computed on
the bridge subset; fresh-probe cells stand alone.

## Difficulty anchoring

A fresh batch has unanchored difficulty. While the previous panel's model versions remain
addressable (pinned API ids), each fresh batch is smoke-run against one prior-generation
model; a fresh probe whose result profile diverges wildly from its mode's history gets a
second look before the panel, not after. This anchor decays as providers sunset old APIs —
that limit is accepted and noted in results rather than papered over.

## Retirement

A probe is **retired** after its second panel (first as fresh, second as bridge). Retired
probes stay in the repo permanently — as grader regression fixtures and as the public
history that makes every past number checkable — but never again as measurements. Panels
must not quote retired-probe cells as current behavior.

## Honest limits

- Hosted-API exposure (above): commitment hides probes from crawls and other labs until
  use, not from the provider under test at run time.
- Single author: probe difficulty and topic selection carry one person's fingerprint.
  The blind-check protects verdicts, not authoring variance; the anchor run partially
  covers it. Volunteer co-raters remain the standing ask (`TASKS.md`).
- The commitment proves the probes predate the results. It does not prove they were the
  *only* probes authored — a bad-faith operator could author ten batches and publish the
  flattering one. The defense is the same as everywhere in this repo: raw responses and
  abstentions are committed too, and the operator's incentive structure is public. Stated
  so no one has to discover it.
