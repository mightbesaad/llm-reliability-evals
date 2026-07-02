"""
Shared trajectory harness for the agentic failure modes (8: premature self-certification now;
7: disconfirmation avoidance, later). Parallel to providers.py, but for the multi-turn
call -> tool_use -> tool_result -> repeat loop, not a single text response. It shares
providers.py's HTTP/retry layer, routing prefixes, sampling defaults, and error type.

providers.call_model returns flattened text and DROPS tool calls, so it cannot drive an agentic
loop. This module makes its own tool-use calls that return the STRUCTURED response, runs the loop
against SCRIPTED tools (frozen, predetermined results), and captures the full trajectory.

Provider-dispatched by model id (claude* -> Anthropic content-block tool_use; mistral family,
gpt*/o*, and any OPENAI_BASE_URL endpoint -> OpenAI-style function calling). ALL legs normalize
to ONE trajectory schema, so graders never see the provider difference. Tools are declared once
in a canonical form ({name, description, input_schema}) and translated per provider here.

Why scripted tools: reproducible/deterministic (frozen like every other slice's probe), and the
only way to CONTROL the disconfirming signal mode 7 will need. The model can't tell a tool is
mocked within one trajectory.

Trajectory schema (the contract graders consume; mode 7 inherits it unchanged):
  provider:         "anthropic" | "mistral" | "openai" | "openai-compatible"
  steps: ordered list of
    {"role": "assistant", "text": str, "tool_calls": [{"id","name","input"}], "stop_reason": str}
    {"role": "tool",      "results": [{"tool_use_id","name","content","is_error"}]}
  final_text:       str    # assistant text at the terminating turn
  stop_reason:      str    # NORMALISED terminal reason: "end_turn" | "max_tokens" | "max_turns"
  tool_call_names:  [str]  # flattened, in call order — convenience for the grader

Robustness: a hard max-turns cap, a real token budget (single-shot defaults are too small for a
loop), retry/backoff on 429/5xx via providers.post_json, and unknown/unscripted tool calls return
an error tool_result instead of crashing. Temperature is sent explicitly and identically on every
leg (providers.DEFAULT_TEMPERATURE) so cross-provider trajectories are comparable.
"""

import json
import os

from providers import (  # noqa: F401  (ProviderError re-exported for callers)
    ANTHROPIC_URL,
    ANTHROPIC_VERSION,
    DEFAULT_TEMPERATURE,
    MISTRAL_BASE_URL,
    MISTRAL_PREFIXES,
    OPENAI_BASE_URL_DEFAULT,
    OPENAI_PREFIXES,
    ProviderError,
    post_json,
)

DEFAULT_MAX_TOKENS = 2048  # a loop needs headroom; the single-shot default is too small
DEFAULT_MAX_TURNS = 8      # hard cap so the tool-calling loop cannot run away


def _http_post_json(url, headers, payload):
    """Module-level indirection kept so tests can monkeypatch the HTTP layer."""
    return post_json(url, headers, payload)


def _run_scripted_tool(name, tool_input, scripted):
    """Resolve a tool's frozen result. `scripted` maps name -> str | callable(input)->str.
    Unknown/unscripted tools return an error result rather than crashing the loop."""
    if name not in scripted:
        return {"content": f"[harness] no scripted tool named '{name}'", "is_error": True}
    spec = scripted[name]
    result = spec(tool_input) if callable(spec) else spec
    return {"content": str(result), "is_error": False}


def _run_anthropic(model, user_prompt, tools, scripted, system, max_turns, max_tokens,
                   temperature):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise ProviderError("ANTHROPIC_API_KEY not set — needed for a claude* model.")
    headers = {"content-type": "application/json", "x-api-key": key,
               "anthropic-version": ANTHROPIC_VERSION}
    a_tools = [{"name": t["name"], "description": t["description"],
                "input_schema": t["input_schema"]} for t in tools]
    messages = [{"role": "user", "content": user_prompt}]
    steps, names, final_text, final_stop = [], [], "", "max_turns"
    for _ in range(max_turns):
        payload = {"model": model, "max_tokens": max_tokens, "temperature": temperature,
                   "messages": messages, "tools": a_tools}
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
            results.append({"tool_use_id": tc["id"], "name": tc["name"],
                            "content": r["content"], "is_error": r["is_error"]})
            blocks.append({"type": "tool_result", "tool_use_id": tc["id"],
                           "content": r["content"], "is_error": r["is_error"]})
        steps.append({"role": "tool", "results": results})
        messages.append({"role": "user", "content": blocks})
    return {"model": model, "provider": "anthropic", "steps": steps,
            "final_text": final_text, "stop_reason": final_stop, "tool_call_names": names}


def _run_openai_style(model, user_prompt, tools, scripted, system, max_turns, max_tokens,
                      temperature, url, key_env, provider_tag, key_required=True):
    """OpenAI-style function-calling loop — Mistral, OpenAI, and any OPENAI_BASE_URL endpoint
    all speak this wire format; only url/key/tag differ."""
    key = os.environ.get(key_env)
    if not key and key_required:
        raise ProviderError(f"{key_env} not set — needed for model '{model}'.")
    headers = {"content-type": "application/json"}
    if key:
        headers["authorization"] = f"Bearer {key}"
    m_tools = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                 "parameters": t["input_schema"]}} for t in tools]
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user_prompt})
    steps, names, final_text, final_stop = [], [], "", "max_turns"
    for _ in range(max_turns):
        payload = {"model": model, "max_tokens": max_tokens, "temperature": temperature,
                   "messages": messages, "tools": m_tools, "tool_choice": "auto"}
        resp = _http_post_json(url, headers, payload)
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
            results.append({"tool_use_id": tc["id"], "name": tc["name"],
                            "content": r["content"], "is_error": r["is_error"]})
            messages.append({"role": "tool", "tool_call_id": tc["id"], "name": tc["name"],
                             "content": r["content"]})
        steps.append({"role": "tool", "results": results})
    return {"model": model, "provider": provider_tag, "steps": steps,
            "final_text": final_text, "stop_reason": final_stop, "tool_call_names": names}


def run_trajectory(model, user_prompt, tools, scripted, system=None,
                   max_turns=DEFAULT_MAX_TURNS, max_tokens=DEFAULT_MAX_TOKENS,
                   temperature=DEFAULT_TEMPERATURE):
    """Drive the call -> tool_use -> tool_result loop; return the normalised trajectory."""
    m = (model or "").lower()
    base = os.environ.get("OPENAI_BASE_URL")
    common = (user_prompt, tools, scripted, system, max_turns, max_tokens, temperature)
    # Aggregator-form ids route to the base-url leg before native prefix matching (see providers).
    if "/" in m:
        if base:
            return _run_openai_style(model, *common, url=base.rstrip("/") + "/chat/completions",
                                     key_env="OPENAI_API_KEY", provider_tag="openai-compatible",
                                     key_required=False)
        raise ProviderError(
            f"harness: '{model}' is an aggregator-form model id (contains '/') — set "
            f"OPENAI_BASE_URL (e.g. https://openrouter.ai/api/v1) or use the native id."
        )
    if m.startswith(("claude", "anthropic")):
        return _run_anthropic(model, *common)
    if m.startswith(MISTRAL_PREFIXES):
        return _run_openai_style(model, *common, url=MISTRAL_BASE_URL + "/chat/completions",
                                 key_env="MISTRAL_API_KEY", provider_tag="mistral")
    if m.startswith(OPENAI_PREFIXES):
        # Key only required when actually hitting api.openai.com — a re-pointed leg may be
        # a keyless local proxy.
        url = (base or OPENAI_BASE_URL_DEFAULT).rstrip("/") + "/chat/completions"
        return _run_openai_style(model, *common, url=url, key_env="OPENAI_API_KEY",
                                 provider_tag="openai", key_required=base is None)
    if base:
        # Model-agnostic path: any OpenAI-compatible server. Key optional — many local
        # servers (Ollama, llama.cpp) don't check one.
        return _run_openai_style(model, *common, url=base.rstrip("/") + "/chat/completions",
                                 key_env="OPENAI_API_KEY", provider_tag="openai-compatible",
                                 key_required=False)
    raise ProviderError(
        f"harness: no route for model '{model}' — expected claude*/mistral*/gpt* "
        f"or OPENAI_BASE_URL set for an OpenAI-compatible endpoint."
    )
