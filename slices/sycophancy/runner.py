#!/usr/bin/env python3
"""
Minimal runner for the sycophancy vertical slice (two-turn, mode 4).

Two modes:
  --replay FILE   Grade recorded turn-2 responses offline (the path shipped demonstrated). FILE is
                  a fixtures-style list of {response, correct, wrong, [expect], [instance]}.
  --live          For each instance: send `prompt` -> r1, then [prompt, r1, followup] -> r2, and
                  grade r2. Needs a provider API key (ANTHROPIC_API_KEY, MISTRAL_API_KEY, or OPENAI_API_KEY).

Output: per-item verdict, aggregate (pass / fail / uncertain, pass-rate over DECIDED cases), the
uncertain ids routed to a judge, and — in replay with `expect` — grader-vs-label agreement.

  python3 runner.py --replay fixtures.yaml
  MISTRAL_API_KEY=... python3 runner.py --live --model mistral-medium --samples 5 --out results.json   # or an ANTHROPIC/OPENAI key + matching model
  OPENAI_API_KEY=... python3 runner.py --live --model gpt-4 --samples 5 --out results.json
  python3 runner.py --live --model llama3.2 --base-url http://localhost:11434/v1 ...   # any OpenAI-compatible endpoint
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import yaml  # noqa: E402

from providers import DEFAULT_TEMPERATURE, call_model  # noqa: E402

import runlib  # noqa: E402

import grader  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def run_replay(path: str) -> list[dict]:
    with open(path) as fh:
        rows = yaml.safe_load(fh)
    out = []
    for row in rows:
        g = grader.grade(row["response"], row.get("correct"), row.get("wrong"))
        rec = {
            "id": row.get("instance", row["id"]),
            "verdict": g["verdict"],
            "reason": g["reason"],
            "signals": g["signals"],
        }
        if "expect" in row:
            rec["expect"] = row["expect"]
            rec["grader_agrees"] = row["expect"] == g["verdict"]
        out.append(rec)
    return out


def run_live(instances_path: str, model: str, samples: int,
             temperature: float = DEFAULT_TEMPERATURE, on_record=None) -> list[dict]:
    with open(instances_path) as fh:
        instances = yaml.safe_load(fh)["instances"]
    out = []
    for inst in instances:
        for s in range(samples):
            r1 = call_model(model, messages=[{"role": "user", "content": inst["prompt"]}],
                            temperature=temperature)
            r2 = call_model(
                model,
                messages=[
                    {"role": "user", "content": inst["prompt"]},
                    {"role": "assistant", "content": r1},
                    {"role": "user", "content": inst["followup"]},
                ],
                temperature=temperature,
            )
            g = grader.grade(r2, inst.get("correct"), inst.get("wrong"))
            rec = {
                "id": inst["id"],
                "sample": s,
                "verdict": g["verdict"],
                "reason": g["reason"],
                "signals": g["signals"],
                "response": r2,  # raw turn-2 text kept so verdicts are blind-checkable
            }
            out.append(rec)
            if on_record:
                on_record(rec)  # durability: flushed to --out immediately
    return out


def _report(results: list[dict], model_label: str) -> dict:
    return runlib.report(results, model_label, id_width=14)


def main() -> None:
    runlib.main(
        description="sycophancy slice runner",
        mode_name="sycophancy-capitulation",
        here=HERE,
        run_replay=run_replay,
        run_live=run_live,
        report_fn=_report,
    )


if __name__ == "__main__":
    main()
