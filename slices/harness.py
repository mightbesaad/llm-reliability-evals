"""
Shared trajectory harness for the agentic failure modes (8: premature self-certification now;
7: disconfirmation avoidance, later). Parallel to providers.py, but for the multi-turn
call -> tool_use -> tool_result -> repeat loop, not a single text response.

providers.call_model returns flattened text and DROPS tool calls, so it cannot drive an agentic
loop. This module makes its own tool-use calls that return the STRUCTURED response, runs the loop
against SCRIPTED tools (frozen, predetermined results), and captures the full trajectory.

Provider-dispatched by model id (claude* -> Anthropic content-block tool_use; mistral* -> Mistral
OpenAI-style function calling). BOTH normalize to ONE trajectory schema, so graders never see the
provider difference. Tools are declared once in a canonical form ({name, description, input_schema})
and translated per provider here.

Why scripted tools: reproducible/deterministic (frozen like every other slice's probe), and the
only way to CONTROL the disconfirming signal mode 7 will need. The model can't tell a tool is
mocked within one trajectory.

Trajectory schema (the contract graders consume; mode 7 inherits it unchanged):
  provider:         "anthropic" | "mistral"
  steps: ordered list of
    {"role": "assistant", "text": str, "tool_calls": [{"id","name","input"}], "stop_reason": str}
    {"role": "tool",      "results": [{"tool_use_id","name","content","is_error"}]}
  final_text:       str    # assistant text at the terminating turn
  stop_reason:      str    # NORMALISED terminal reason: "end_turn" | "max_tokens" | "max_turns"
  tool_call_names:  [str]  # flattened, in call order — convenience for the grader

Robustness: a hard max-turns cap, a real token budget (providers' 512 is single-shot only), and
unknown/unscripted tool calls return an error tool_result instead of crashing.
"""

import json
import os
import urllib.error
import urllib.request

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
DEFAULT_MAX_TOKENS = 2048  # a loop needs headroom; providers.py's 512 is single-shot only
DEFAULT_MAX_TURNS = 8      # hard cap so the tool-calling loop cannot run away


def _http_post_json(url, headers, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"API error {e.code} from {url}: {e.read().decode()[:600]}")


def _run_scripted_tool(name, tool_input, scripted):
    """Resolve a tool's frozen result. `scripted` maps name -> str | callable(input)->str.
    Unknown/unscripted tools return an error result rather than crashing the loop."""
    if name not in scripted:
        return {"content": f"[harness] no scripted tool named '{name}'", "is_error": True}
    spec = scripted[name]
    result = spec(tool_input) if callable(spec) else spec
    return {"content": str(result), "is_error": False}


def _run_anthropic(model, user_prompt, tools, scripted, system, max_turns, max_tokens):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise SystemExit("ANTHROPIC_API_KEY not set — needed for a claude* model.")
    headers = {"content-type": "application/json", "x-api-key": key, "anthropic-version": ANTHROPIC_VERSION}
    a_tools = [{"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]} for t in tools]
    messages = [{"role": "user", "content": user_prompt}]
    steps, names, final_text, final_stop = [], [], "", "max_turns"
    for _ in range(max_turns):
        payload = {"model": model, "max_tokens": max_tokens, "messages": messages, "tools": a_tools}
        if system:
            payload["system"] = system
        resp = _http_post_json(ANTHROPIC_URL, headers, payload)
        content = resp.get("content", [])
        stop = resp.get("stop_reason")
        text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
        tcs = [{"id": b["id"], "name": b["name"], "input": b.get("input", {})}
               for b in content if b.get("type") == "tool_use"]
        steps.append({"role": "assistant", "text": text, "tool_calls": tcs, "stop_reason": stop})
        names.extend(t["name"] for t in tcs)
        messages.append({"role": "assistant", "content": content})
        if stop != "tool_use" or not tcs:
            final_text, final_stop = text, stop
            break
        results, blocks = [], []
        for tc in tcs:
            r = _run_scripted_tool(tc["name"], tc["input"], scripted)
            results.append({"tool_use_id": tc["id"], "name": tc["name"], "content": r["content"], "is_error": r["is_error"]})
            blocks.append({"type": "tool_result", "tool_use_id": tc["id"], "content": r["content"], "is_error": r["is_error"]})
        steps.append({"role": "tool", "results": results})
        messages.append({"role": "user", "content": blocks})
    return {"model": model, "provider": "anthropic", "steps": steps,
            "final_text": final_text, "stop_reason": final_stop, "tool_call_names": names}


def _run_mistral(model, user_prompt, tools, scripted, system, max_turns, max_tokens):
    key = os.environ.get("MISTRAL_API_KEY")
    if not key:
        raise SystemExit("MISTRAL_API_KEY not set — needed for a mistral* model.")
    headers = {"content-type": "application/json", "authorization": f"Bearer {key}"}
    m_tools = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                 "parameters": t["input_schema"]}} for t in tools]
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user_prompt})
    steps, names, final_text, final_stop = [], [], "", "max_turns"
    for _ in range(max_turns):
        payload = {"model": model, "max_tokens": max_tokens, "messages": messages,
                   "tools": m_tools, "tool_choice": "auto"}
        resp = _http_post_json(MISTRAL_URL, headers, payload)
        choice = resp["choices"][0]
        msg = choice["message"]
        stop = choice.get("finish_reason")
        text = msg.get("content") or ""
        raw_tcs = msg.get("tool_calls") or []
        tcs = []
        for tc in raw_tcs:
            args = tc.get("function", {}).get("arguments") or "{}"
            try:
                parsed = json.loads(args) if isinstance(args, str) else args
            except (ValueError, TypeError):
                parsed = {"_raw": args}
            tcs.append({"id": tc.get("id"), "name": tc["function"]["name"], "input": parsed})
        steps.append({"role": "assistant", "text": text, "tool_calls": tcs, "stop_reason": stop})
        names.extend(t["name"] for t in tcs)
        messages.append({"role": "assistant", "content": text, "tool_calls": raw_tcs})
        if not raw_tcs:
            final_text = text
            final_stop = {"stop": "end_turn", "length": "max_tokens"}.get(stop, stop)
            break
        results = []
        for tc in tcs:
            r = _run_scripted_tool(tc["name"], tc["input"], scripted)
            results.append({"tool_use_id": tc["id"], "name": tc["name"], "content": r["content"], "is_error": r["is_error"]})
            messages.append({"role": "tool", "tool_call_id": tc["id"], "name": tc["name"], "content": r["content"]})
        steps.append({"role": "tool", "results": results})
    return {"model": model, "provider": "mistral", "steps": steps,
            "final_text": final_text, "stop_reason": final_stop, "tool_call_names": names}


def run_trajectory(model, user_prompt, tools, scripted, system=None,
                   max_turns=DEFAULT_MAX_TURNS, max_tokens=DEFAULT_MAX_TOKENS):
    """Drive the call -> tool_use -> tool_result loop; return the normalised trajectory."""
    m = (model or "").lower()
    if m.startswith(("claude", "anthropic")):
        return _run_anthropic(model, user_prompt, tools, scripted, system, max_turns, max_tokens)
    if m.startswith(("mistral", "codestral", "open-mistral", "open-mixtral", "ministral", "pixtral", "magistral")):
        return _run_mistral(model, user_prompt, tools, scripted, system, max_turns, max_tokens)
    raise SystemExit(f"harness: unknown provider for model '{model}' (expected claude* or mistral*).")
