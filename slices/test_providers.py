#!/usr/bin/env python3
"""
Offline tests for slices/providers.py — routing, uniform sampling params, retry/backoff.

Run:  python3 slices/test_providers.py     (no API key, no network — HTTP layer is mocked)
Exits nonzero on any failed check.

Two mock layers, matching the two things under test:
  - routing/params: providers.post_json is replaced, so call_model's dispatch and the exact
    payload each provider leg sends are observable;
  - retry: the real post_json runs against a mocked urllib.request.urlopen (and a recorded
    time.sleep), so backoff and Retry-After handling are exercised for real.

NOTE: these pin dispatch and payload shape, not the live wire format — that validation is a
live run. The uniform-params checks exist because the previous layer sent different sampling
params per provider, silently confounding any cross-provider comparison.
"""

import email.message
import io
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import providers  # noqa: E402

# Keys are only checked for presence — every HTTP call below is mocked.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("MISTRAL_API_KEY", "test-key")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.pop("OPENAI_BASE_URL", None)

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


# ---- routing + uniform params (post_json mocked) --------------------------------------------

_real_post_json = providers.post_json
CAP = {}


def fake_post(url, headers, payload, timeout=None):
    CAP.clear()
    CAP.update(url=url, headers=dict(headers), payload=payload)
    if "anthropic" in url:
        return {"content": [{"type": "text", "text": "hi"}]}
    return {"choices": [{"message": {"content": "hi"}}]}


providers.post_json = fake_post

out = providers.call_model("claude-test", "q")
check("routing: claude* -> anthropic endpoint", CAP["url"] == providers.ANTHROPIC_URL)
check("anthropic: response text extracted", out == "hi")
anthropic_payload = dict(CAP["payload"])

providers.call_model("mistral-medium", "q")
check("routing: mistral* -> mistral endpoint",
      CAP["url"] == "https://api.mistral.ai/v1/chat/completions")
check("mistral: bearer auth sent", CAP["headers"].get("authorization") == "Bearer test-key")
mistral_payload = dict(CAP["payload"])

providers.call_model("open-mixtral-8x7b", "q")
check("routing: open-mixtral not misrouted to the o* OpenAI prefixes",
      CAP["url"] == "https://api.mistral.ai/v1/chat/completions")

providers.call_model("gpt-test", "q")
check("routing: gpt* -> openai default endpoint",
      CAP["url"] == "https://api.openai.com/v1/chat/completions")
openai_payload = dict(CAP["payload"])

check("uniform params: temperature identical across all three legs",
      anthropic_payload["temperature"] == mistral_payload["temperature"]
      == openai_payload["temperature"] == providers.DEFAULT_TEMPERATURE)
check("uniform params: max_tokens identical across all three legs",
      anthropic_payload["max_tokens"] == mistral_payload["max_tokens"]
      == openai_payload["max_tokens"] == providers.DEFAULT_MAX_TOKENS)

providers.call_model("mistral-medium", "q", temperature=0.0, max_tokens=64)
check("uniform params: per-call override honored",
      CAP["payload"]["temperature"] == 0.0 and CAP["payload"]["max_tokens"] == 64)

providers.call_model("mistral-medium", messages=[{"role": "user", "content": "a"},
                                                 {"role": "assistant", "content": "b"},
                                                 {"role": "user", "content": "c"}])
check("input: messages list passed through verbatim (mode 4)",
      len(CAP["payload"]["messages"]) == 3)

os.environ["OPENAI_BASE_URL"] = "http://localhost:11434/v1"
_key = os.environ.pop("OPENAI_API_KEY")
try:
    providers.call_model("llama3.2-test", "q")
    check("base_url: unknown id routed to the OpenAI-compatible endpoint",
          CAP["url"] == "http://localhost:11434/v1/chat/completions")
    check("base_url: key optional for base-url endpoints",
          "authorization" not in CAP["headers"])
    providers.call_model("gpt-test", "q")
    check("base_url: re-points the gpt* leg too",
          CAP["url"] == "http://localhost:11434/v1/chat/completions")
finally:
    os.environ["OPENAI_API_KEY"] = _key
    os.environ.pop("OPENAI_BASE_URL", None)

try:
    providers.call_model("mistral-medium")
    check("guard: prompt or messages required", False)
except SystemExit:
    check("guard: prompt or messages required", True)

_saved = {k: os.environ.pop(k) for k in
          ("ANTHROPIC_API_KEY", "MISTRAL_API_KEY", "OPENAI_API_KEY")}
try:
    providers.call_model("some-unmapped-model", "q")
    check("guard: no route + no keys + no base_url rejected", False)
except SystemExit:
    check("guard: no route + no keys + no base_url rejected", True)
finally:
    os.environ.update(_saved)

_key = os.environ.pop("MISTRAL_API_KEY")
try:
    providers.call_model("mistral-medium", "q")
    check("guard: missing provider key exits cleanly", False)
except SystemExit:
    check("guard: missing provider key exits cleanly", True)
finally:
    os.environ["MISTRAL_API_KEY"] = _key

providers.post_json = _real_post_json

# ---- retry/backoff (real post_json, urlopen mocked) ------------------------------------------


def http_error(code, retry_after=None, body=b"err"):
    hdrs = email.message.Message()
    if retry_after is not None:
        hdrs["Retry-After"] = retry_after
    return urllib.error.HTTPError("http://x/y", code, "msg", hdrs, io.BytesIO(body))


class FakeResp:
    def __init__(self, data):
        self._body = json.dumps(data).encode()

    def read(self, *a):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


_real_urlopen = urllib.request.urlopen
_real_sleep = providers.time.sleep
SLEEPS = []
providers.time.sleep = SLEEPS.append

N = {"calls": 0}


def flaky_429(req, timeout=None):
    N["calls"] += 1
    if N["calls"] < 3:
        raise http_error(429, retry_after="1")
    return FakeResp({"ok": True})


try:
    urllib.request.urlopen = flaky_429
    out = providers.post_json("http://x/y", {}, {})
    check("retry: 429 retried, then succeeds",
          out == {"ok": True} and N["calls"] == 3)
    check("retry: Retry-After honored over exponential backoff", SLEEPS[:2] == [1.0, 1.0])

    SLEEPS.clear()
    N["calls"] = 0

    def flaky_503(req, timeout=None):
        N["calls"] += 1
        if N["calls"] < 2:
            raise http_error(503)
        return FakeResp({"ok": True})

    urllib.request.urlopen = flaky_503
    providers.post_json("http://x/y", {}, {})
    check("retry: 5xx without Retry-After uses exponential backoff", SLEEPS == [2.0])

    N["calls"] = 0

    def hard_400(req, timeout=None):
        N["calls"] += 1
        raise http_error(400, body=b"bad request detail")

    urllib.request.urlopen = hard_400
    try:
        providers.post_json("http://x/y", {}, {})
        check("retry: 4xx (non-429) fails immediately, no retry", False)
    except SystemExit as e:
        check("retry: 4xx (non-429) fails immediately, no retry",
              N["calls"] == 1 and "bad request detail" in str(e))

    N["calls"] = 0

    def always_429(req, timeout=None):
        N["calls"] += 1
        raise http_error(429)

    urllib.request.urlopen = always_429
    try:
        providers.post_json("http://x/y", {}, {})
        check("retry: persistent 429 exhausts attempts and raises", False)
    except SystemExit:
        check("retry: persistent 429 exhausts attempts and raises",
              N["calls"] == providers.MAX_ATTEMPTS)
finally:
    urllib.request.urlopen = _real_urlopen
    providers.time.sleep = _real_sleep

# ---- summary ---------------------------------------------------------------------------------

total = PASSED + len(FAILED)
print(f"\n{PASSED}/{total} checks passed")
if FAILED:
    print("failed: " + ", ".join(FAILED))
print("NOTE: dispatch, payload shape, and retry policy are pinned against mocks, not the live")
print("wire format — that validation is a live run per slice (--live) or the harness smoke test.")
sys.exit(1 if FAILED else 0)
