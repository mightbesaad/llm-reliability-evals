#!/usr/bin/env python3
"""
Minimal runner for the stale-recall vertical slice.

Two modes:
  --replay FILE   Grade pre-recorded responses offline (the path shipped demonstrated). FILE is
                  a fixtures-style list of {id, instance, response, [expect]}. No model needed.
  --live          Call a model for each prompt in instances.yaml (needs a provider key).

Output: a per-item verdict line, an aggregate (pass / fail / uncertain, and pass-rate over the
DECIDED cases only), the uncertain ids routed to human/LLM-judge, and — in replay, when fixtures
carry `expect` — the grader's agreement with the labels. Optionally writes a results record.

Usage:
  python3 runner.py --replay fixtures.yaml
  python3 runner.py --replay fixtures.yaml --out results.json
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
        g = grader.grade(row["response"])
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
            resp = call_model(model, inst["prompt"], temperature=temperature)
            g = grader.grade(resp)
            rec = {
                "id": inst["id"],
                "sample": s,
                "verdict": g["verdict"],
                "reason": g["reason"],
                "signals": g["signals"],
                "response": resp,  # raw text kept so verdicts are blind-checkable
            }
            out.append(rec)
            if on_record:
                on_record(rec)  # durability: flushed to --out immediately
    return out


def _report(results: list[dict], model_label: str) -> dict:
    return runlib.report(results, model_label, id_width=14)


def main() -> None:
    runlib.main(
        description="stale-recall slice runner",
        mode_name="stale-recall-as-current-fact",
        here=HERE,
        run_replay=run_replay,
        run_live=run_live,
        report_fn=_report,
    )


if __name__ == "__main__":
    main()
