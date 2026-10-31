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
    # Gemini 2.5 is closed to new keys. 3.5 Flash is a reasoning model: low effort is fast enough for
    # bulk labelling (~3 s), and the one synthesis call per company gets more room to think.
    "gemini": {"key": "GEMINI_API_KEY", "base": "https://generativelanguage.googleapis.com/v1beta/openai",
               "cheap": "gemini-3.5-flash", "strong": "gemini-3.5-flash", "free": True,
               "effort": {"cheap": "low", "strong": "medium"}},
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

_local = threading.local()


class cached_only:
    """Inside a web request, never wait on a model: answer from cache or return None,
    and let the background loop make the real call."""
    def __enter__(self):
        self.prev = getattr(_local, "cached_only", False)
        _local.cached_only = True

    def __exit__(self, *a):
        _local.cached_only = self.prev


def in_request():
    return getattr(_local, "cached_only", False)


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
        try:
            return json.loads(m.group(0)) if m else None
        except json.JSONDecodeError:
            return None  # malformed or truncated: the caller falls back to rules


def ask_json(prompt, tier="cheap", system=None, max_tokens=1500, attempts=5, timeout=90):
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
    if in_request():
        return None
    body = {"model": model, "temperature": 0.1, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": sys_msg}, {"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"}}
    effort = os.environ.get(f"FINN_{tier.upper()}_EFFORT") or (p.get("effort") or {}).get(tier)
    if effort:
        body["reasoning_effort"] = effort
        body["max_tokens"] = max_tokens + (6000 if effort != "low" else 1500)  # thinking tokens count against the limit
    for attempt in range(attempts):
        try:
            r = requests.post(f"{p['base']}/chat/completions", json=body, timeout=timeout,
                              headers={"Authorization": f"Bearer {os.environ.get(p['key'], 'none')}"})
        except requests.RequestException:
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code in (429, 503):  # free-tier rate limit or "high demand": back off and retry
            time.sleep(6 * (attempt + 1))
            continue
        if r.status_code != 200:
            return None
        data = r.json()
        if (data.get("choices") or [{}])[0].get("finish_reason") == "length" and attempt < 2:
            body["max_tokens"] *= 2  # ran out of room while thinking: give it more and ask again
            continue
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
