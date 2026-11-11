"""Streaming chat client for any OpenAI-compatible endpoint (Groq or our stand-in).

Deliberately no SDK: the openai/groq SDKs retry 429s by default, which would hide
retries from our logs. This client makes exactly ONE HTTP attempt per call; all
retry logic lives in the caller so every retry is counted.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field

import httpx

GROQ_BASE = "https://api.groq.com/openai/v1"


@dataclass
class CallResult:
    """What one streamed model call returned: status, text, timings, tokens, rate-limit headers, error."""
    status: int                 # HTTP status (0 = network error / timeout)
    text: str = ""
    ttft_ms: float | None = None  # time to first ANSWER (content) token - what a person sees
    first_any_ms: float | None = None  # first token of any kind, incl. reasoning ("thinking")
    reasoning: str = ""         # reasoning text if the model streamed it
    reasoning_tokens: int = 0   # from usage.completion_tokens_details, if reported
    cached_tokens: int = 0      # prompt tokens served from Groq's prompt cache (don't count to limits)
    total_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    headers: dict = field(default_factory=dict)   # x-ratelimit-*, retry-after, etc.
    error_body: str = ""
    error_kind: str = ""        # "", "timeout", "network", "http", "truncated"


def _keep_headers(h: httpx.Headers) -> dict:
    """Keep only the rate-limit and request-id headers worth logging."""
    return {k: v for k, v in h.items()
            if k.startswith("x-ratelimit") or k in ("retry-after", "x-request-id", "date")
            or k.startswith("x-groq")}


def stream_chat(messages, model, *, base_url=GROQ_BASE, api_key=None, max_tokens=400,
                temperature=0.0, timeout_s=30.0, client: httpx.Client | None = None,
                extra=None) -> CallResult:
    """One streaming chat call (Groq or the stand-in), timing the first answer token. Never raises."""
    api_key = api_key or os.environ.get("GROQ_API_KEY", "")
    body = {"model": model, "messages": messages, "max_tokens": max_tokens,
            "temperature": temperature, "stream": True,
            "stream_options": {"include_usage": True}}
    if extra:
        body.update(extra)
    own = client is None
    client = client or httpx.Client(timeout=None)
    t0 = time.perf_counter()
    res = CallResult(status=0)
    try:
        with client.stream("POST", f"{base_url}/chat/completions", json=body,
                           headers={"Authorization": f"Bearer {api_key}"},
                           timeout=httpx.Timeout(timeout_s, connect=5.0)) as r:
            res.status = r.status_code
            res.headers = _keep_headers(r.headers)
            if r.status_code != 200:
                res.error_body = r.read().decode(errors="replace")[:2000]
                res.error_kind = "http"
                return res
            parts, rparts = [], []
            got_done = False
            for line in r.iter_lines():
                if time.perf_counter() - t0 > timeout_s:
                    res.error_kind = "timeout"
                    break
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    got_done = True
                    break
                chunk = json.loads(data)
                usage = chunk.get("usage") or (chunk.get("x_groq") or {}).get("usage")
                if usage:
                    res.tokens_in = usage.get("prompt_tokens", 0)
                    res.tokens_out = usage.get("completion_tokens", 0)
                    det = usage.get("completion_tokens_details") or {}
                    res.reasoning_tokens = det.get("reasoning_tokens", 0) or 0
                    pdet = usage.get("prompt_tokens_details") or {}
                    res.cached_tokens = pdet.get("cached_tokens", 0) or 0
                for ch in chunk.get("choices") or []:
                    delta = ch.get("delta") or {}
                    think = delta.get("reasoning") or delta.get("reasoning_content")
                    piece = delta.get("content")
                    if (think or piece) and res.first_any_ms is None:
                        res.first_any_ms = (time.perf_counter() - t0) * 1000
                    if think:
                        rparts.append(think)
                    if piece:
                        if res.ttft_ms is None:
                            res.ttft_ms = (time.perf_counter() - t0) * 1000
                        parts.append(piece)
            res.text = "".join(parts)
            res.reasoning = "".join(rparts)
            if not got_done and not res.error_kind:
                res.error_kind = "truncated"   # stream closed without [DONE]: partial answer
    except httpx.TimeoutException:
        res.error_kind = "timeout"
    except httpx.HTTPError as e:
        res.error_kind = "network"
        res.error_body = repr(e)[:500]
    finally:
        res.total_ms = (time.perf_counter() - t0) * 1000
        if own:
            client.close()
    return res
