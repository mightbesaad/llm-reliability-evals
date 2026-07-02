#!/usr/bin/env python3
"""
Runner for the disconfirmation-avoidance slice (mode 7) — trajectory-shaped.

  --replay FILE   Grade hand-authored / recorded trajectories offline. FILE is a fixtures-style list
                  of {id, disconfirming_tool, disconfirm_markers, steps, [expect]}. No model needed.
  --live          For each instance in instances.yaml: run the agentic loop (../harness.py) with the
                  scenario's tools + a scripted check whose result CONTRADICTS the conclusion, then
                  grade the captured trajectory. Needs a provider key (mistral*/claude*/gpt* per
                  --model, or --base-url for any OpenAI-compatible endpoint).

Live output also reports the mode-7 mix-check per scenario: SKIPPED the disconfirming check /
CALLED+IGNORED (certified past the contradiction) / CALLED+SURFACED. All-skipped => the channel was
not established; all-surfaced => the probe may be over-telegraphed; a mix (or any called+ignored)
means the probe discriminates. Full trajectories are stored for the Gate-3 blind-check.

Usage:
  python3 runner.py --replay fixtures.yaml
  MISTRAL_API_KEY=...   python3 runner.py --live --model mistral-small-latest --samples 3 --out results.json
  ANTHROPIC_API_KEY=... python3 runner.py --live --model claude-haiku-4-5-20251001 --samples 3 --out results.json
  python3 runner.py --live --model llama3.2 --base-url http://localhost:11434/v1 ...   # any OpenAI-compatible endpoint
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import yaml  # noqa: E402

import harness  # noqa: E402

import runlib  # noqa: E402

import grader  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def run_replay(path: str) -> list[dict]:
    with open(path) as fh:
        rows = yaml.safe_load(fh)
    out = []
    for row in rows:
        g = grader.grade({"steps": row["steps"]}, row["disconfirming_tool"], row["disconfirm_markers"])
        rec = {
            "id": row["id"],
            "disconfirming_tool": row["disconfirming_tool"],
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
             temperature: float = harness.DEFAULT_TEMPERATURE, on_record=None) -> list[dict]:
    with open(instances_path) as fh:
        data = yaml.safe_load(fh)
    instances = data["instances"]
    system = data.get("system")
    out = []
    for inst in instances:
        for s in range(samples):
            traj = harness.run_trajectory(model, inst["task"], inst["tools"], inst["scripted"],
                                          system=system, temperature=temperature)
            g = grader.grade(traj, inst["disconfirming_tool"], inst["disconfirm_markers"])
            rec = {
                "id": inst["id"],
                "tier": inst.get("tier"),
                "sample": s,
                "disconfirming_tool": inst["disconfirming_tool"],
                "verdict": g["verdict"],
                "reason": g["reason"],
                "signals": g["signals"],
                "trajectory": traj,  # full trajectory kept for the Gate-3 blind-check
            }
            out.append(rec)
            if on_record:
                on_record(rec)  # durability: flushed to --out immediately
    return out


def report(results: list[dict], model_label: str) -> dict:
    counts = {"pass": 0, "fail": 0, "uncertain": 0}
    for r in results:
        counts[r["verdict"]] += 1

    print(f"model: {model_label}")
    print(f"items graded: {len(results)}\n")
    for r in results:
        agree = ""
        if "grader_agrees" in r:
            agree = "  [label match]" if r["grader_agrees"] else f"  [MISMATCH expect={r['expect']}]"
        called = r["signals"].get("disconfirming_called")
        surfaced = r["signals"].get("surfaced_contradiction")
        print(f"  {r['id']:<26} {r['verdict']:<10} called={str(called):<5} surfaced={str(surfaced):<5} {r['reason'][:56]}{agree}")
    print(f"\naggregate: pass={counts['pass']}  fail={counts['fail']}  uncertain={counts['uncertain']}")

    # Mode-7 mix-check: per scenario — skipped / called+ignored / called+surfaced.
    by_id: dict = {}
    for r in results:
        d = by_id.setdefault(r["id"], {"skipped": 0, "called_ignored": 0, "called_surfaced": 0})
        if not r["signals"].get("disconfirming_called"):
            d["skipped"] += 1
        elif r["signals"].get("surfaced_contradiction"):
            d["called_surfaced"] += 1
        else:
            d["called_ignored"] += 1
    if len(results) and any("sample" in r for r in results):
        print("\nmix-check (per scenario — skipped / called+ignored / called+surfaced):")
        for iid, d in by_id.items():
            print(f"  {iid:<26} skipped={d['skipped']}  called_ignored={d['called_ignored']}  called_surfaced={d['called_surfaced']}")
        if all(d["called_ignored"] == 0 and d["skipped"] == 0 for d in by_id.values()):
            print("  ! all-surfaced — probe may be over-telegraphed; loosen the standing rule / task surface")
        elif all(d["called_surfaced"] == 0 for d in by_id.values()):
            print("  ! nothing surfaced — check that the disconfirming channel is established at all")
        else:
            print("  mix present — the probe discriminates")

    labelled = [r for r in results if "grader_agrees" in r]
    if labelled:
        agreed = sum(1 for r in labelled if r["grader_agrees"])
        print(f"\ngrader vs fixture labels: {agreed}/{len(labelled)} agree")
    return {"counts": counts}


def main() -> None:
    runlib.main(
        description="disconfirmation-avoidance slice runner (trajectory)",
        mode_name="disconfirmation-avoidance",
        here=HERE,
        run_replay=run_replay,
        run_live=run_live,
        report_fn=report,
        replay_label="replay (hand-authored trajectories)",
    )


if __name__ == "__main__":
    main()
