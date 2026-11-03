"""LLM-backed reasoner with content-addressed record/replay — the real-agent path.

The deterministic generator in pipeline.py synthesizes reasoning text from fixed
word pools, which makes the divergence instrument measure the gap between two
author-written vocabularies rather than between a real agent's clean and
compromised reasoning. This module replaces that synthesis with an actual model
call: a phase's reasoning-to-tool-call trace is whatever the LLM produces when it
reads clean content versus content carrying an indirect prompt injection.

Determinism is NOT from temperature. kimi-k2.5 forces temperature=1, so a live
call is non-deterministic by construction. Reproducibility comes from the
content-addressed cache: every (model, system, user) triple is hashed and its
response stored under traces/. Replay reads the store and needs no key and no
network, which is what lets a reviewer reproduce §VI without a Moonshot account.
The traces/ directory is meant to be committed; the key in .env is not.

Modes:
  replay  — cache only. Raises on a miss. Offline, deterministic, key-free.
  record  — call the API on a miss and store the response. Needs MOONSHOT_API_KEY.
  auto    — replay if cached, else record. The default for a working session.

Stdlib only (urllib): the artifact keeps its no-dependency stance on the replay
path a reviewer runs.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

_HERE = os.path.dirname(os.path.abspath(__file__))
_CACHE_DIR = os.path.join(_HERE, "traces")

_BASE_URL = os.environ.get("MOONSHOT_BASE_URL", "https://api.moonshot.ai/v1")
_MODEL = os.environ.get("MOONSHOT_MODEL", "kimi-k2.5")
_TEMPERATURE = float(os.environ.get("MOONSHOT_TEMPERATURE", "1"))  # k2.5 allows only 1


class ReplayMiss(RuntimeError):
    """A prompt was not in the cache and the mode forbids a live call."""


class LLMError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Content-addressed cache
# ---------------------------------------------------------------------------


def _cache_key(system: str, user: str) -> str:
    h = hashlib.sha256()
    h.update(_MODEL.encode())
    h.update(b"\x00")
    h.update(system.encode())
    h.update(b"\x00")
    h.update(user.encode())
    return h.hexdigest()


def _cache_path(key: str) -> str:
    return os.path.join(_CACHE_DIR, key + ".json")


def _load(key: str) -> dict | None:
    path = _cache_path(key)
    if os.path.exists(path):
        with open(path) as fh:
            return json.load(fh)
    return None


def _store(key: str, record: dict) -> None:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    with open(_cache_path(key), "w") as fh:
        json.dump(record, fh, indent=2, sort_keys=True)


# ---------------------------------------------------------------------------
# Moonshot / OpenAI-compatible call over stdlib urllib
# ---------------------------------------------------------------------------


def _call_api(system: str, user: str, retries: int = 2) -> dict:
    key = os.environ.get("MOONSHOT_API_KEY")
    if not key:
        raise LLMError("MOONSHOT_API_KEY not set; cannot record. Source poc/.env "
                       "or run in replay mode against committed traces/.")
    body = json.dumps({
        "model": _MODEL,
        "temperature": _TEMPERATURE,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }).encode()
    req = urllib.request.Request(
        f"{_BASE_URL}/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode())
        except (urllib.error.URLError, TimeoutError) as exc:  # transient
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise LLMError(f"Moonshot call failed after {retries + 1} attempts: {last}")


# ---------------------------------------------------------------------------
# Public reasoner
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Reasoned:
    reasoning: str
    tool_calls: tuple[str, ...]
    from_cache: bool


def _parse_content(content: str, menu: tuple[str, ...]) -> tuple[str, tuple[str, ...]]:
    """The model is asked for {reasoning, tool_calls}. Be liberal: strip fences,
    keep only tool calls inside the phase menu so a hallucinated token cannot smear
    the tool-profile feature. Reasoning is taken verbatim, since that is the signal
    the divergence instrument embeds."""
    text = content.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text.strip("`")
        text = text.lstrip("json").strip()
    reasoning, tools = "", []
    try:
        obj = json.loads(text)
        reasoning = str(obj.get("reasoning", "")).strip()
        tools = [t for t in obj.get("tool_calls", []) if t in menu]
    except (json.JSONDecodeError, AttributeError):
        reasoning = content.strip()  # fall back to the whole message as reasoning
    if not tools:
        tools = list(menu)  # an agent that named none still ran the phase's tools
    return reasoning, tuple(tools)


def reason(system: str, user: str, menu: tuple[str, ...], mode: str = "auto") -> Reasoned:
    key = _cache_key(system, user)
    cached = _load(key)
    if cached is not None:
        r, t = _parse_content(cached["content"], menu)
        return Reasoned(r, t, from_cache=True)
    if mode == "replay":
        raise ReplayMiss(f"no cached trace for key {key[:12]}… and mode=replay")

    resp = _call_api(system, user)
    content = resp["choices"][0]["message"]["content"]
    _store(key, {
        "model": _MODEL,
        "system": system,
        "user": user,
        "content": content,
        "usage": resp.get("usage"),
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    r, t = _parse_content(content, menu)
    return Reasoned(r, t, from_cache=False)


def cache_stats() -> dict:
    if not os.path.isdir(_CACHE_DIR):
        return {"cached_traces": 0, "dir": _CACHE_DIR}
    n = len([f for f in os.listdir(_CACHE_DIR) if f.endswith(".json")])
    return {"cached_traces": n, "dir": _CACHE_DIR, "model": _MODEL}
