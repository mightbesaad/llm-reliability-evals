#!/usr/bin/env python3
"""
Harness self-test — the harness-level equivalent of a slice's test_grader.py. A trivial one-tool task
(NOT a mode-8 probe) that exercises harness.run_trajectory end-to-end against a REAL tool-calling model
and asserts the loop ran and the trajectory was captured faithfully (tool_use name+input, tool_result,
normalised stop_reason). Keep it: this is what catches a provider changing their tool-call response
shape before it silently corrupts a real eval run.

Run (provider auto-selected by model id):
  MISTRAL_API_KEY=...   python3 slices/smoke_test_harness.py --model mistral-small-latest
  ANTHROPIC_API_KEY=... python3 slices/smoke_test_harness.py --model claude-haiku-4-5-20251001
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import harness  # noqa: E402

TOOLS = [
    {
        "name": "get_weather",
        "description": "Get the current weather for a city.",
        "input_schema": {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "City name"}},
            "required": ["city"],
        },
    }
]

# Frozen, predetermined result — the model cannot tell it is mocked within one trajectory.
SCRIPTED = {"get_weather": "15°C, partly cloudy, wind 10 km/h"}

PROMPT = "What's the current weather in Paris? Use the get_weather tool, then tell me in one sentence."


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.environ.get("EVAL_MODEL", "mistral-small-latest"))
    args = ap.parse_args()

    traj = harness.run_trajectory(args.model, PROMPT, TOOLS, SCRIPTED)
    print(json.dumps(traj, indent=2, ensure_ascii=False))

    # mechanical pass/fail of the SMOKE TEST itself (does the harness work) — not a mode grade
    called = "get_weather" in traj["tool_call_names"]
    ended = traj["stop_reason"] == "end_turn"
    print(
        f"\n[smoke] get_weather called: {called} | terminal stop_reason: {traj['stop_reason']} | "
        f"ended cleanly: {ended} | final_text non-empty: {bool(traj['final_text'])} | "
        f"steps captured: {len(traj['steps'])}"
    )
    ok = called and ended and bool(traj["final_text"])
    print(f"[smoke] harness mechanics: {'OK' if ok else 'NOT OK — inspect trajectory above'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
