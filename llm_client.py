"""Minimal Anthropic-compatible LLM client.

The gateway uses Azure APIM auth: the `api-key` header (NOT Anthropic's `x-api-key`).
Stdlib only (urllib) so no extra deps. Reads creds from poc/.env (LLM_* vars).
"""
import json
import os
import urllib.request

_ENV = os.path.join(os.path.dirname(__file__), ".env")


def _load_env(path=_ENV):
    if not os.path.exists(path):
        return
    for line in open(path):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)


_load_env()


def call_llm(prompt, system=None, max_tokens=2000, temperature=0):
    base = os.environ["LLM_BASE_URL"]
    body = {
        "model": os.environ["LLM_MODEL"],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system
    req = urllib.request.Request(
        base + "/v1/messages",
        data=json.dumps(body).encode(),
        headers={
            "api-key": os.environ["LLM_API_KEY"],
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        out = json.load(r)
    return "".join(b.get("text", "") for b in out.get("content", []) if b.get("type") == "text")
