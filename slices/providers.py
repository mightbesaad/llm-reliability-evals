"""
Shared provider module for all slice runners.

Provider detection: checks environment variables for API keys and dispatches
to the appropriate provider implementation. Add new providers by implementing
_call_<provider>() and updating the call_model() dispatcher.

Usage in runners:
    from providers import call_model
    resp = call_model(model, prompt)
"""

import os
import sys
import json
import urllib.request


def _call_anthropic(model: str, prompt: str = None, messages: list = None) -> str:
    """Anthropic Messages API."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise SystemExit("Anthropic API key not found. Set ANTHROPIC_API_KEY.")
    
    if messages is not None:
        body_messages = messages
    elif prompt is not None:
        body_messages = [{"role": "user", "content": prompt}]
    else:
        raise SystemExit("Anthropic call requires either prompt or messages")
    
    body = json.dumps(
        {
            "model": model,
            "max_tokens": 512,
            "messages": body_messages,
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


def _call_mistral(model: str, prompt: str = None, messages: list = None) -> str:
    """Mistral Chat Completions API."""
    try:
        import requests
    except ImportError:
        raise SystemExit("Mistral provider requires 'requests' library: pip install requests")
    
    key = os.environ.get("MISTRAL_API_KEY")
    if not key:
        raise SystemExit("Mistral API key not found. Set MISTRAL_API_KEY.")
    
    if messages is not None:
        body_messages = messages
    elif prompt is not None:
        body_messages = [{"role": "user", "content": prompt}]
    else:
        raise SystemExit("Mistral call requires either prompt or messages")
    
    resp = requests.post(
        "https://api.mistral.ai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": body_messages,
            "temperature": 0.7,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _call_openai(model: str, prompt: str = None, messages: list = None) -> str:
    """OpenAI Chat Completions API."""
    try:
        import requests
    except ImportError:
        raise SystemExit("OpenAI provider requires 'requests' library: pip install requests")
    
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise SystemExit("OpenAI API key not found. Set OPENAI_API_KEY.")
    
    if messages is not None:
        body_messages = messages
    elif prompt is not None:
        body_messages = [{"role": "user", "content": prompt}]
    else:
        raise SystemExit("OpenAI call requires either prompt or messages")
    
    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": body_messages,
            "temperature": 0.7,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def call_model(model: str, prompt: str = None, messages: list = None) -> str:
    """Dispatch to the appropriate provider based on available API keys.
    
    Supports two signatures:
      - prompt: str (single-turn: modes 1, 2, 3, 5, 6)
      - messages: list (multi-turn: mode 4)
    
    Priority order: Anthropic -> Mistral -> OpenAI
    Set the corresponding env var (ANTHROPIC_API_KEY, MISTRAL_API_KEY, OPENAI_API_KEY).
    
    Args:
        model: Provider-specific model identifier
        prompt: Single-turn user prompt (optional if messages provided)
        messages: Multi-turn message list (optional if prompt provided)
        
    Returns:
        The model's response text
        
    Raises:
        SystemExit: If no supported API key is found or no input provided
    """
    if prompt is None and messages is None:
        raise SystemExit("call_model requires either 'prompt' or 'messages' argument")
    
    if os.environ.get("ANTHROPIC_API_KEY"):
        if messages is not None:
            return _call_anthropic(model, messages=messages)
        return _call_anthropic(model, prompt)
    elif os.environ.get("MISTRAL_API_KEY"):
        if messages is not None:
            return _call_mistral(model, messages=messages)
        return _call_mistral(model, prompt)
    elif os.environ.get("OPENAI_API_KEY"):
        if messages is not None:
            return _call_openai(model, messages=messages)
        return _call_openai(model, prompt)
    else:
        raise SystemExit(
            "No API key found. Set one of: ANTHROPIC_API_KEY, MISTRAL_API_KEY, OPENAI_API_KEY"
        )
