#!/usr/bin/env python3
"""
Minimal runner for the secondary-source-over-trust vertical slice (single-turn, mode 1).

Two modes:
  --replay FILE   Grade pre-recorded responses offline (the path shipped demonstrated). FILE is a
                  fixtures-style list of {id, instance, response, claim, [expect]}. No model needed.
  --live          Call a model for each prompt in instances.yaml, passing the instance's `claim` to
                  the grader so it can detect a silently-used figure (needs a provider key).

Output: a per-item verdict line, an aggregate (pass / fail / uncertain, and pass-rate over the
DECIDED cases only), the uncertain ids routed to human/LLM-judge, and — in replay, when fixtures
carry `expect` — the grader's agreement with the labels. Optionally writes a results record.

Usage:
  python3 runner.py --replay fixtures.yaml
  python3 runner.py --replay fixtures.yaml --out results.json
  ANTHROPIC_API_KEY=... python3 runner.py --live --model <model-id> --samples 5 --out results.json
"""

import argparse
import datetime
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yaml  # noqa: E402

import grader  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def call_model(model: str, prompt: str) -> str:
    """Anthropic Messages API via stdlib (no SDK dependency). Set ANTHROPIC_API_KEY.

    Deliberately NOT exercised in the shipped demo — provided so a live run is a one-liner.
    Swap this single function to target a different provider.
    """
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise SystemExit("live mode needs ANTHROPIC_API_KEY in the environment")
    body = json.dumps(
        {
            "model": model,
            "max_tokens": 512,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "content-type": "application/json",
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.load(resp)
    return "".join(part.get("text", "") for part in data.get("content", []))


def run_replay(path: str) -> list[dict]:
    with open(path) as fh:
        rows = yaml.safe_load(fh)
    out = []
    for row in rows:
        g = grader.grade(row["response"], row.get("claim"))
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


def run_live(instances_path: str, model: str, samples: int) -> list[dict]:
    with open(instances_path) as fh:
        instances = yaml.safe_load(fh)["instances"]
    out = []
    for inst in instances:
        for s in range(samples):
            resp = call_model(model, inst["prompt"])
            g = grader.grade(resp, inst.get("claim"))
            out.append(
                {
                    "id": inst["id"],
                    "sample": s,
                    "verdict": g["verdict"],
                    "reason": g["reason"],
                    "signals": g["signals"],
                }
            )
    return out


def report(results: list[dict], model_label: str) -> dict:
    counts = {"pass": 0, "fail": 0, "uncertain": 0}
    for r in results:
        counts[r["verdict"]] += 1
    decided = counts["pass"] + counts["fail"]
    pass_rate = (counts["pass"] / decided) if decided else None

    print(f"model: {model_label}")
    print(f"items graded: {len(results)}\n")
    for r in results:
        agree = ""
        if "grader_agrees" in r:
            agree = "  [label match]" if r["grader_agrees"] else f"  [LABEL MISMATCH expect={r['expect']}]"
        print(f"  {r['id']:<16} {r['verdict']:<10} {r['reason']}{agree}")

    print(f"\naggregate: pass={counts['pass']}  fail={counts['fail']}  uncertain={counts['uncertain']}")
    print(
        "pass-rate over decided cases: "
        + (f"{pass_rate:.0%}  ({counts['pass']}/{decided})" if decided else "n/a")
    )
    uncertain = [r["id"] for r in results if r["verdict"] == "uncertain"]
    if uncertain:
        print(f"uncertain → route to human / LLM-judge: {uncertain}")

    labelled = [r for r in results if "grader_agrees" in r]
    if labelled:
        agreed = sum(1 for r in labelled if r["grader_agrees"])
        print(f"grader vs fixture labels: {agreed}/{len(labelled)} agree")

    return {"counts": counts, "pass_rate_decided": pass_rate}


def main() -> None:
    ap = argparse.ArgumentParser(description="secondary-source-over-trust slice runner")
    ap.add_argument("--instances", default=os.path.join(HERE, "instances.yaml"))
    ap.add_argument("--replay", help="fixtures-style yaml of recorded responses (offline)")
    ap.add_argument("--live", action="store_true", help="call a model (needs ANTHROPIC_API_KEY)")
    ap.add_argument("--model", default=os.environ.get("EVAL_MODEL", ""), help="model id (live) / results label")
    ap.add_argument("--samples", type=int, default=1, help="samples per instance (live; stochasticity)")
    ap.add_argument("--out", help="write results json here")
    args = ap.parse_args()

    if not args.replay and not args.live:
        ap.error("choose --replay FILE or --live")

    if args.replay:
        results = run_replay(args.replay)
        model_label = args.model or "replay (synthetic fixtures)"
    else:
        if not args.model:
            ap.error("--live needs --model <model-id> (or EVAL_MODEL)")
        results = run_live(args.instances, args.model, args.samples)
        model_label = args.model

    summary = report(results, model_label)

    if args.out:
        rec = {
            "model": model_label,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "mode": "secondary-source-over-trust",
            **summary,
            "results": results,
        }
        with open(args.out, "w") as fh:
            json.dump(rec, fh, indent=2)
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
