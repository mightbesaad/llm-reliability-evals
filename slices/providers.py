"""
Shared provider module for all slice runners — the single-turn text path.
(The multi-turn tool-use path is slices/harness.py, which shares this module's
HTTP/retry layer, routing prefixes, and error type.)

Model-agnostic by design. Routing, by model id:
  claude* / anthropic*      -> Anthropic Messages API           (ANTHROPIC_API_KEY)
  mistral family            -> Mistral chat completions         (MISTRAL_API_KEY)
  gpt* / o1|o3|o4* / chatgpt-> OpenAI chat completions          (OPENAI_API_KEY)
  anything else             -> any OpenAI-compatible endpoint via OPENAI_BASE_URL
                               (Ollama, vLLM, Groq, Together, OpenRouter, llama.cpp, ...)

OPENAI_BASE_URL also re-points the gpt*/o* leg — the standard meaning of that env var.
Example (Ollama):
    OPENAI_BASE_URL=http://localhost:11434/v1 python3 runner.py --live --model llama3.2 ...
When OPENAI_BASE_URL routes an unknown model id, the API key is optional — many local
servers don't check one.

Sampling params are explicit and UNIFORM across providers (DEFAULT_TEMPERATURE /
DEFAULT_MAX_TOKENS) so cross-provider results are comparable — previously Anthropic got
no temperature while Mistral/OpenAI got 0.7 and no max_tokens, confounding any panel.
Pass temperature= / max_tokens= to call_model to override per run.

HTTP is stdlib-only (urllib); post_json retries 429/5xx with exponential backoff,
honoring Retry-After. Failures raise ProviderError. Transitional note: ProviderError
subclasses SystemExit so the existing runners exit cleanly with the message; the shared
runlib (TASKS.md task 4, PR 3) will catch it as a regular exception instead.

Usage in runners:
    from providers import call_model
    resp = call_model(model, prompt)
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
MISTRAL_BASE_URL = "https://api.mistral.ai/v1"
OPENAI_BASE_URL_DEFAULT = "https://api.openai.com/v1"

DEFAULT_TEMPERATURE = 0.7  # matches every live run recorded so far (the Mistral legs)
DEFAULT_MAX_TOKENS = 1024  # single-shot answers; the trajectory harness sets its own budget
DEFAULT_TIMEOUT = 120

RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4           # 1 call + 3 retries: 2s, 8s, 32s — or Retry-After, capped at 120s

# Order matters and is shared with harness.py: the open-mistral/open-mixtral ids must be
# checked before the OpenAI prefixes or "o1"-style matching would misroute them.
MISTRAL_PREFIXES = ("mistral", "open-mistral", "open-mixtral", "codestral", "pixtral",
                    "ministral", "magistral")
OPENAI_PREFIXES = ("gpt", "o1", "o3", "o4", "chatgpt")


class ProviderError(SystemExit):
    """A provider/API failure. Subclasses SystemExit (transitional) so runners exit cleanly
    with the message; PR 3's shared runlib will catch it as a regular exception."""


def _retry_delay(retry_after: str | None, attempt: int) -> float:
    if retry_after:
        try:
            return min(float(retry_after), 120.0)
        except ValueError:
            pass
    return 2.0 * (4 ** attempt)


def post_json(url: str, headers: dict, payload: dict, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """POST JSON; retry 429/5xx (honoring Retry-After) and network errors with backoff."""
    body = json.dumps(payload).encode()
    for attempt in range(MAX_ATTEMPTS):
        req = urllib.request.Request(url, data=body, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:600]
            if e.code not in RETRY_STATUSES or attempt == MAX_ATTEMPTS - 1:
                raise ProviderError(f"API error {e.code} from {url}: {detail}")
            delay = _retry_delay(e.headers.get("Retry-After") if e.headers else None, attempt)
            print(f"[providers] {e.code} from {url} — retrying in {delay:.0f}s "
                  f"(attempt {attempt + 2}/{MAX_ATTEMPTS})", file=sys.stderr)
            time.sleep(delay)
        except urllib.error.URLError as e:
            if attempt == MAX_ATTEMPTS - 1:
                raise ProviderError(f"network error calling {url}: {e.reason}")
            delay = 2.0 * (4 ** attempt)
            print(f"[providers] network error ({e.reason}) — retrying in {delay:.0f}s "
                  f"(attempt {attempt + 2}/{MAX_ATTEMPTS})", file=sys.stderr)
            time.sleep(delay)
    raise ProviderError(f"exhausted retries calling {url}")  # defensive; loop always raises


def _body_messages(prompt: str | None, messages: list | None, provider_name: str) -> list:
    if messages is not None:
        return messages
    if prompt is not None:
        return [{"role": "user", "content": prompt}]
    raise ProviderError(f"{provider_name} call requires either prompt or messages")


def _call_anthropic(model: str, prompt: str | None = None, messages: list | None = None,
                    temperature: float = DEFAULT_TEMPERATURE,
                    max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
    """Anthropic Messages API."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise ProviderError("Anthropic API key not found. Set ANTHROPIC_API_KEY.")
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": _body_messages(prompt, messages, "Anthropic"),
    }
    headers = {
        "content-type": "application/json",
        "x-api-key": key,
        "anthropic-version": ANTHROPIC_VERSION,
    }
    data = post_json(ANTHROPIC_URL, headers, payload)
    return "".join(part.get("text", "") for part in data.get("content", []))


def _call_openai_compatible(model: str, prompt: str | None = None, messages: list | None = None,
                            temperature: float = DEFAULT_TEMPERATURE,
                            max_tokens: int = DEFAULT_MAX_TOKENS,
                            base_url: str = OPENAI_BASE_URL_DEFAULT,
                            key_env: str = "OPENAI_API_KEY",
                            provider_name: str = "OpenAI",
                            key_required: bool = True) -> str:
    """Chat-completions call against any OpenAI-compatible endpoint (Mistral speaks it too)."""
    key = os.environ.get(key_env)
    if not key and key_required:
        raise ProviderError(f"{provider_name} API key not found. Set {key_env}.")
    headers = {"content-type": "application/json"}
    if key:
        headers["authorization"] = f"Bearer {key}"
    payload = {
        "model": model,
        "messages": _body_messages(prompt, messages, provider_name),
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    data = post_json(base_url.rstrip("/") + "/chat/completions", headers, payload)
    return data["choices"][0]["message"]["content"]


def call_model(model: str, prompt: str | None = None, messages: list | None = None,
               temperature: float = DEFAULT_TEMPERATURE, max_tokens: int = DEFAULT_MAX_TOKENS,
               base_url: str | None = None) -> str:
    """Dispatch a single-turn (or multi-turn text) call to the right provider.

    Supports two input signatures:
      - prompt: str (single-turn: modes 1, 2, 3, 5, 6)
      - messages: list (multi-turn: mode 4)

    Routing is by model id (see module docstring); ids that match no prefix go to the
    OpenAI-compatible endpoint in `base_url` / $OPENAI_BASE_URL if one is set, else fall
    back to whichever provider key is present. Sampling params are sent explicitly and
    identically to every provider so results are comparable across them.

    Returns the model's response text. Raises ProviderError if no route or no input.
    """
    if prompt is None and messages is None:
        raise ProviderError("call_model requires either 'prompt' or 'messages' argument")

    kw = dict(prompt=prompt, messages=messages, temperature=temperature, max_tokens=max_tokens)
    base = base_url or os.environ.get("OPENAI_BASE_URL")
    m = (model or "").lower()

    if m.startswith(("claude", "anthropic")):
        return _call_anthropic(model, **kw)
    if m.startswith(MISTRAL_PREFIXES):
        return _call_openai_compatible(model, base_url=MISTRAL_BASE_URL,
                                       key_env="MISTRAL_API_KEY", provider_name="Mistral", **kw)
    if m.startswith(OPENAI_PREFIXES):
        # Key only required when actually hitting api.openai.com — a re-pointed leg may be
        # a keyless local proxy.
        return _call_openai_compatible(model, base_url=base or OPENAI_BASE_URL_DEFAULT,
                                       key_required=base is None, **kw)
    if base:
        # The model-agnostic path: any OpenAI-compatible server. Key optional — many
        # local servers (Ollama, llama.cpp) don't check one.
        return _call_openai_compatible(model, base_url=base, key_required=False, **kw)

    # Legacy fallback: unknown id, no base_url — dispatch by whichever key is set.
    if os.environ.get("ANTHROPIC_API_KEY"):
        return _call_anthropic(model, **kw)
    if os.environ.get("MISTRAL_API_KEY"):
        return _call_openai_compatible(model, base_url=MISTRAL_BASE_URL,
                                       key_env="MISTRAL_API_KEY", provider_name="Mistral", **kw)
    if os.environ.get("OPENAI_API_KEY"):
        return _call_openai_compatible(model, **kw)
    raise ProviderError(
        f"No route for model '{model}': set OPENAI_BASE_URL for an OpenAI-compatible "
        f"endpoint, or one of ANTHROPIC_API_KEY / MISTRAL_API_KEY / OPENAI_API_KEY."
    )
