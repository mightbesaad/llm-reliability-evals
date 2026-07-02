#!/usr/bin/env python3
"""
Offline tests for slices/harness.py — the trajectory normalization contract.

Run:  python3 slices/test_harness.py     (no API key, no network — HTTP layer is mocked)
Exits nonzero on any failed check.

What this pins is the CONTRACT the graders consume (and mode 7 will inherit): both providers
normalize to one trajectory schema; stop reasons map to end_turn / max_tokens / max_turns;
unscripted tools return error results instead of crashing; max-turns caps the loop; parallel
tool calls keep their order; tool results are echoed back to the model on the next turn.

NOTE: this checks normalization against canned provider payloads, not against the live wire
format. Real validation of the wire format is a live smoke run (smoke_test_harness.py, needs
a key). These tests are what lets the harness be refactored without silently breaking graders.
"""

import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import harness  # noqa: E402
import providers  # noqa: E402

# Keys are only checked for presence — every HTTP call below is mocked.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("MISTRAL_API_KEY", "test-key")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
# Routing checks below assume no ambient base-url override.
os.environ.pop("OPENAI_BASE_URL", None)

TOOLS = [
    {"name": "run_tests", "description": "run the test suite",
     "input_schema": {"type": "object", "properties": {"suite": {"type": "string"}}}},
    {"name": "validate_config", "description": "validate the config",
     "input_schema": {"type": "object", "properties": {}}},
]

PASSED = 0
FAILED = []


def check(name, cond, detail=""):
    global PASSED
    if cond:
        PASSED += 1
        print(f"ok   {name}")
    else:
        FAILED.append(name)
        print(f"FAIL {name}" + (f"  — {detail}" if detail else ""))


class FakeAPI:
    """Replaces harness._http_post_json: returns canned responses, records every payload sent."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, headers, payload):
        # Deep-copy: the harness mutates its messages list in place after the call, and the
        # payload holds a reference to it — snapshot what was actually on the wire at call time.
        self.calls.append({"url": url, "headers": dict(headers), "payload": copy.deepcopy(payload)})
        if not self.responses:
            raise AssertionError("harness made more HTTP calls than the test scripted")
        return self.responses.pop(0)


def with_fake(responses):
    fake = FakeAPI(responses)
    harness._http_post_json = fake
    return fake


# ---- canned provider payloads -------------------------------------------------------------

def a_text(text, stop="end_turn"):
    return {"content": [{"type": "text", "text": text}], "stop_reason": stop}


def a_tool(text, calls, stop="tool_use"):
    blocks = [{"type": "text", "text": text}] if text else []
    blocks += [{"type": "tool_use", "id": i, "name": n, "input": inp} for (i, n, inp) in calls]
    return {"content": blocks, "stop_reason": stop}


def m_text(text, finish="stop"):
    return {"choices": [{"message": {"content": text}, "finish_reason": finish}]}


def m_tool(calls, finish="tool_calls", text=""):
    tcs = [{"id": i, "function": {"name": n, "arguments": args}} for (i, n, args) in calls]
    return {"choices": [{"message": {"content": text, "tool_calls": tcs}, "finish_reason": finish}]}


# ---- Anthropic leg -------------------------------------------------------------------------

fake = with_fake([
    a_tool("checking first", [("tu_1", "run_tests", {"suite": "all"})]),
    a_text("all green"),
])
traj = harness.run_trajectory("claude-test", "verify the work", TOOLS,
                              scripted={"run_tests": "42 passed"}, system="be careful")
check("anthropic: provider tag", traj["provider"] == "anthropic")
check("anthropic: step roles assistant/tool/assistant",
      [s["role"] for s in traj["steps"]] == ["assistant", "tool", "assistant"])
check("anthropic: tool_call_names in call order", traj["tool_call_names"] == ["run_tests"])
check("anthropic: final_text from terminal turn", traj["final_text"] == "all green")
check("anthropic: native stop_reason passes through", traj["stop_reason"] == "end_turn")
check("anthropic: scripted result delivered, not an error",
      traj["steps"][1]["results"][0]["content"] == "42 passed"
      and traj["steps"][1]["results"][0]["is_error"] is False)
check("anthropic: system prompt forwarded", fake.calls[0]["payload"].get("system") == "be careful")
check("anthropic: uniform temperature sent",
      fake.calls[0]["payload"].get("temperature") == providers.DEFAULT_TEMPERATURE)
_second_msgs = fake.calls[1]["payload"]["messages"]
check("anthropic: tool_result echoed back to the model on the next turn",
      _second_msgs[-1]["content"][0]["type"] == "tool_result"
      and _second_msgs[-1]["content"][0]["tool_use_id"] == "tu_1")

with_fake([a_tool("", [("tu_2", "not_a_tool", {})]), a_text("hm")])
traj = harness.run_trajectory("claude-test", "p", TOOLS, scripted={})
_r = traj["steps"][1]["results"][0]
check("anthropic: unscripted tool -> error result, loop survives",
      _r["is_error"] is True and "no scripted tool" in _r["content"])

with_fake([a_tool("", [("t1", "run_tests", {})]), a_tool("", [("t2", "run_tests", {})])])
traj = harness.run_trajectory("claude-test", "p", TOOLS, scripted={"run_tests": "ok"}, max_turns=2)
check("anthropic: max_turns caps the loop",
      traj["stop_reason"] == "max_turns" and len(traj["tool_call_names"]) == 2)

with_fake([a_tool("", [("t1", "run_tests", {}), ("t2", "validate_config", {})]), a_text("done")])
traj = harness.run_trajectory("claude-test", "p", TOOLS,
                              scripted={"run_tests": "ok", "validate_config": "valid"})
check("anthropic: parallel tool calls, order kept",
      traj["tool_call_names"] == ["run_tests", "validate_config"]
      and len(traj["steps"][1]["results"]) == 2)

with_fake([a_tool("", [("t1", "run_tests", {"suite": "unit"})]), a_text("done")])
traj = harness.run_trajectory("claude-test", "p", TOOLS,
                              scripted={"run_tests": lambda inp: f"suite={inp['suite']}"})
check("scripted tools: callable spec receives the tool input",
      traj["steps"][1]["results"][0]["content"] == "suite=unit")

# ---- Mistral leg ---------------------------------------------------------------------------

fake = with_fake([m_tool([("c1", "run_tests", '{"suite": "all"}')]), m_text("done")])
traj = harness.run_trajectory("mistral-test", "verify", TOOLS,
                              scripted={"run_tests": "42 passed"}, system="be careful")
check("mistral: provider tag", traj["provider"] == "mistral")
check("mistral: step roles match the anthropic shape",
      [s["role"] for s in traj["steps"]] == ["assistant", "tool", "assistant"])
check("mistral: finish_reason 'stop' normalized to end_turn", traj["stop_reason"] == "end_turn")
check("mistral: arguments JSON parsed into input",
      traj["steps"][0]["tool_calls"][0]["input"] == {"suite": "all"})
check("mistral: system message first in payload",
      fake.calls[0]["payload"]["messages"][0]["role"] == "system")
check("mistral: uniform temperature sent",
      fake.calls[0]["payload"].get("temperature") == providers.DEFAULT_TEMPERATURE)
_msgs2 = fake.calls[1]["payload"]["messages"]
check("mistral: tool result appended as role=tool with matching id",
      any(m.get("role") == "tool" and m.get("tool_call_id") == "c1" for m in _msgs2))

with_fake([m_text("truncated…", finish="length")])
traj = harness.run_trajectory("mistral-test", "p", TOOLS, scripted={})
check("mistral: finish_reason 'length' normalized to max_tokens",
      traj["stop_reason"] == "max_tokens")

with_fake([m_tool([("c9", "run_tests", "not-json{")]), m_text("done")])
traj = harness.run_trajectory("mistral-test", "p", TOOLS, scripted={"run_tests": "ok"})
check("mistral: malformed arguments preserved as _raw, no crash",
      traj["steps"][0]["tool_calls"][0]["input"] == {"_raw": "not-json{"})

# ---- OpenAI + OpenAI-compatible legs (same wire format as mistral) --------------------------

fake = with_fake([m_tool([("g1", "run_tests", '{"suite": "all"}')]), m_text("done")])
traj = harness.run_trajectory("gpt-test", "verify", TOOLS, scripted={"run_tests": "ok"})
check("openai: provider tag", traj["provider"] == "openai")
check("openai: default endpoint used",
      fake.calls[0]["url"] == "https://api.openai.com/v1/chat/completions")
check("openai: normalizes like the other legs",
      traj["stop_reason"] == "end_turn" and traj["tool_call_names"] == ["run_tests"])

os.environ["OPENAI_BASE_URL"] = "http://localhost:11434/v1"
_no_key = os.environ.pop("OPENAI_API_KEY")
try:
    fake = with_fake([m_text("hello from a local model")])
    traj = harness.run_trajectory("llama3.2-test", "p", TOOLS, scripted={})
    check("openai-compatible: unknown id routed via OPENAI_BASE_URL",
          traj["provider"] == "openai-compatible"
          and fake.calls[0]["url"] == "http://localhost:11434/v1/chat/completions")
    check("openai-compatible: key optional for base-url endpoints",
          "authorization" not in fake.calls[0].get("headers", {})
          and traj["final_text"] == "hello from a local model")
finally:
    os.environ["OPENAI_API_KEY"] = _no_key
    os.environ.pop("OPENAI_BASE_URL", None)

# ---- the cross-provider contract itself ----------------------------------------------------

with_fake([a_tool("t", [("x", "run_tests", {})]), a_text("d")])
ta = harness.run_trajectory("claude-test", "p", TOOLS, scripted={"run_tests": "ok"})
with_fake([m_tool([("y", "run_tests", "{}")]), m_text("d")])
tm = harness.run_trajectory("mistral-test", "p", TOOLS, scripted={"run_tests": "ok"})
check("contract: top-level trajectory keys identical across providers", sorted(ta) == sorted(tm))
check("contract: assistant step keys identical",
      sorted(ta["steps"][0]) == sorted(tm["steps"][0]))
check("contract: tool step keys identical", sorted(ta["steps"][1]) == sorted(tm["steps"][1]))
check("contract: tool result keys identical",
      sorted(ta["steps"][1]["results"][0]) == sorted(tm["steps"][1]["results"][0]))

# ---- routing / guards ----------------------------------------------------------------------

try:
    harness.run_trajectory("some-unmapped-model", "p", TOOLS, scripted={})
    check("routing: unmapped model id rejected", False)
except providers.ProviderError:
    check("routing: unmapped model id rejected", True)

_saved = os.environ.pop("ANTHROPIC_API_KEY")
try:
    harness.run_trajectory("claude-test", "p", TOOLS, scripted={})
    check("guard: missing key raises ProviderError instead of calling out", False)
except providers.ProviderError:
    check("guard: missing key raises ProviderError instead of calling out", True)
finally:
    os.environ["ANTHROPIC_API_KEY"] = _saved

# ---- summary -------------------------------------------------------------------------------

total = PASSED + len(FAILED)
print(f"\n{PASSED}/{total} checks passed")
if FAILED:
    print("failed: " + ", ".join(FAILED))
print("NOTE: normalization is checked against canned provider payloads, not the live wire")
print("format — that validation is smoke_test_harness.py (needs a key). These tests exist so")
print("the harness can be refactored without silently breaking the graders' contract.")
sys.exit(1 if FAILED else 0)
