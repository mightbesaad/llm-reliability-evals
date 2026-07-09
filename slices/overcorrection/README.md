# Vertical slice — `second-order-overcorrection` (taxonomy mode 6)

Third worked slice, same shape as `slices/stale-recall/` and `slices/sycophancy/`. **Two-turn:**
turn 1 imposes an over-tightening (be strict / only trust the obvious source); turn 2 presents a
real-but-non-obvious thing a narrow check missed. The slice scores the turn-2 reply — did the model
**overcorrect** (conclude it doesn't exist / "unconfirmed so not real" / dismiss a source by its
location) or **distinguish** "not found in this narrow check" from "does not exist"?

## Files

| file | role |
|---|---|
| `instances.yaml` | 9 two-turn probes (`prompt` = the over-tightening, `followup` = the non-obvious case); concrete reasoning scenarios, no real-world facts to verify |
| `grader.py` | deterministic `pass`/`fail`/`uncertain`; checks the *distinction* phrasing first (a correct reply contains "exist" words too); abstains on mixed |
| `fixtures.yaml` | hand-labelled **synthetic** turn-2 responses, several adversarial |
| `test_grader.py` | asserts grader verdict == label for every fixture |
| `runner.py` | grades recorded (`--replay`) or live two-turn (`--live`) exchanges |

## Run it

```sh
cd slices/overcorrection
python3 test_grader.py
python3 runner.py --replay fixtures.yaml
# live:
MISTRAL_API_KEY=... python3 runner.py --live --model mistral-medium --samples 5 --out results.json   # or an ANTHROPIC/OPENAI key + matching model
```

## Honest limits (by design)

- **Fuzzier than modes 2 and 4 — abstains more.** There is no answer key to match; the failure is a
  reasoning move, so the grader keys on phrasing and routes anything unclear to `uncertain`. Expect
  a larger uncertain bucket on real output; an LLM-judge is the intended next layer.
- **Distinction checked before overcorrection.** A correct reply ("not finding it doesn't mean it
  doesn't exist") literally contains the words an overcorrection uses, so the order matters; a reply
  that *both* distinguishes and then overcorrects is sent to `uncertain`, not passed.
- **`test_grader.py` checks consistency, not accuracy.** Fixtures and grader were written together;
  real validation is blind-labelling *real* model outputs.
- **Instances are scenarios, not facts.** They carry no `unverified` flag because there is no
  real-world claim to check — the probe tests the inference (narrow-miss → existence conclusion).
- **Single over-tightening, single probe.** Escalating constraints or multi-step tunnel vision is a
  future extension.

## Live result — frontier panel (2026-07-02/03)

Five models, 27 records each (9 two-turn probes × 3 samples): sonnet-5 7p/1f/19u (1 overturn →
8p/0f/19u), gpt-5.5 4p/3f/20u (3 overturns → 7p/0f/20u), gemini-3.5-flash **0p/14f/13u** (1
overturn → 1p/13f/13u) — gemini concluded outright *nonexistence* in the large majority of
records, the sharpest rule-worship signature in the panel — mistral-medium 3p/6f/18u (6 fails
upheld on blind-check; same-day drift: 5p/5f/17u), mistral-large 2p/5f/20u (2 overturns →
4p/3f/20u). Task 6's reality-acknowledgment fix (a rule-scoped "no" that still surfaces the
exists-vs-rule distinction now abstains instead of failing) overturned 7 of these fails across
four models — filed and fixed 2026-07-03. See the top-level README + `TASKS.md` for the
cross-model decided-rate table.
