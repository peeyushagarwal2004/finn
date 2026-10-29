"""Two-tier model router over any OpenAI-compatible endpoint.

  cheap  -> bulk extraction (guidance sentences -> JSON, bios, one-liners)
  strong -> the few places that need judgment (narrative vs numbers, bull/bear)

Every call is cached by a hash of (model, prompt), so a second look at a company costs
nothing. Free tiers are used automatically; a paid OpenAI key is used only when
FINN_LLM_PROVIDER=openai is set explicitly, so a stray key in the env never spends money.
Without any provider, callers fall back to their deterministic path and still work.
"""
import hashlib
import json
import os
import re
import threading
import time

import requests

from . import store

PROVIDERS = {
    "gemini": {"key": "GEMINI_API_KEY", "base": "https://generativelanguage.googleapis.com/v1beta/openai",
               "cheap": "gemini-2.5-flash-lite", "strong": "gemini-2.5-flash", "free": True},
    "groq": {"key": "GROQ_API_KEY", "base": "https://api.groq.com/openai/v1",
             "cheap": "llama-3.1-8b-instant", "strong": "llama-3.3-70b-versatile", "free": True},
    "openrouter": {"key": "OPENROUTER_API_KEY", "base": "https://openrouter.ai/api/v1",
                   "cheap": "meta-llama/llama-3.3-70b-instruct:free", "strong": "deepseek/deepseek-chat-v3-0324:free",
                   "free": True},
    "openai": {"key": "OPENAI_API_KEY", "base": "https://api.openai.com/v1",
               "cheap": "gpt-4.1-nano", "strong": "gpt-4.1-mini", "free": False},
}
# USD per 1M tokens (in, out), only used to show what the free tier saved
LIST_PRICE = {"cheap": (0.10, 0.40), "strong": (0.30, 2.50)}

_usage_lock = threading.Lock()
_usage = {"calls": 0, "cache_hits": 0, "tokens_in": 0, "tokens_out": 0, "usd": 0.0, "by_tier": {"cheap": 0, "strong": 0}}


def provider():
    base = os.environ.get("FINN_LLM_BASE_URL")
    if base:  # any OpenAI-compatible server, e.g. a local Ollama / LM Studio / vLLM
        return "custom", {"key": "FINN_LLM_API_KEY", "base": base.rstrip("/"), "cheap": os.environ.get("FINN_CHEAP_MODEL", "llama3.1:8b"),
                          "strong": os.environ.get("FINN_STRONG_MODEL", "llama3.1:8b"), "free": True}
    name = os.environ.get("FINN_LLM_PROVIDER", "").lower()
    if name in PROVIDERS and os.environ.get(PROVIDERS[name]["key"]):
        return name, PROVIDERS[name]
    for name, p in PROVIDERS.items():
        if p["free"] and os.environ.get(p["key"]):
            return name, p
    return None, None


def status():
    name, p = provider()
    with _usage_lock:
        u = dict(_usage, by_tier=dict(_usage["by_tier"]))
    if name:
        u.update(provider=name, cheap=os.environ.get("FINN_CHEAP_MODEL", p["cheap"]),
                 strong=os.environ.get("FINN_STRONG_MODEL", p["strong"]), free=p["free"])
    else:
        u.update(provider=None)
    return u


def _extract_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"[\[{].*[\]}]", text, re.S)
        return json.loads(m.group(0)) if m else None


def ask_json(prompt, tier="cheap", system=None, max_tokens=1500):
    """Return parsed JSON from the tier's model, or None when no provider/failed."""
    name, p = provider()
    if not name:
        return None
    model = os.environ.get("FINN_CHEAP_MODEL" if tier == "cheap" else "FINN_STRONG_MODEL", p[tier])
    sys_msg = system or ("You are a precise financial analyst. Use ONLY the source text provided. "
                         "Never use outside knowledge. Reply with JSON only.")
    key = hashlib.sha256(f"{model}\n{sys_msg}\n{prompt}".encode()).hexdigest()
    hit = store.kv_get("llm", key)
    if hit is not None:
        with _usage_lock:
            _usage["cache_hits"] += 1
        return hit
    body = {"model": model, "temperature": 0.1, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": sys_msg}, {"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"}}
    for attempt in range(3):
        try:
            r = requests.post(f"{p['base']}/chat/completions", json=body, timeout=90,
                              headers={"Authorization": f"Bearer {os.environ.get(p['key'], 'none')}"})
        except requests.RequestException:
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code == 429:  # free-tier rate limit: back off and retry
            time.sleep(4 * (attempt + 1))
            continue
        if r.status_code != 200:
            return None
        data = r.json()
        out = _extract_json(data["choices"][0]["message"]["content"] or "")
        u = data.get("usage") or {}
        ti, to = u.get("prompt_tokens", 0), u.get("completion_tokens", 0)
        pi, po = LIST_PRICE[tier]
        with _usage_lock:
            _usage["calls"] += 1
            _usage["by_tier"][tier] += 1
            _usage["tokens_in"] += ti
            _usage["tokens_out"] += to
            _usage["usd"] += (ti * pi + to * po) / 1e6
        if out is not None:
            store.kv_set("llm", key, out)
        return out
    return None
