"""Stand-in for Groq: an OpenAI-compatible streaming chat server we control.

It can be slow (calibrated latency + rare pre-first-token delay), fail (5xx, mid-stream
stall, mid-stream drop), refuse at a limit (429 shaped like Groq's, exact retry-after),
get slower under load (in-flight slowdown + FIFO above max concurrency), and stream
(reasoning deltas, then content deltas, then a usage chunk, then [DONE]).

Every number comes from standin/calibration.json (built from real probe logs by
standin/calibrate.py). Run:
    .venv/bin/uvicorn standin.server:app --port 8099
Admin (scenario control):
    POST /admin/config  {"profile":"evening", "rare_rate":0.1 (override), "limits":{"itpm":3500}, "seed":1, ...}
    POST /admin/exhaust {"model":"openai/gpt-oss-120b","limit":"tpd","leave":2000}
    POST /admin/reset   GET /admin/stats
"""
from __future__ import annotations

import asyncio
import json
import math
import random
import re
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

ROOT = Path(__file__).resolve().parents[1]
CAL = json.loads((ROOT / "standin/calibration.json").read_text())
MODELS = list(CAL["profiles"][CAL["default_profile"]]["models"])
V = lambda d: d["value"]  # noqa: E731

# ---------------------------------------------------------------- limits
LIMIT_NAMES = {"rpm": ("requests per minute", 60), "itpm": ("input tokens per minute", 60),
               "tpm": ("tokens per minute", 60), "rpd": ("requests per day", 86400),
               "tpd": ("tokens per day", 86400)}


class Bucket:
    """Continuously refilling bucket, exactly as measured on Groq:
    usage drains at limit/window per second; admit iff used + r <= limit;
    else wait = (used + r - limit) / (limit/window)."""

    def __init__(self, limit: float, window_s: float):
        self.limit, self.window, self.used, self.t = float(limit), float(window_s), 0.0, time.monotonic()

    def _refill(self):
        """Give back capacity in proportion to time passed (continuous refill, like Groq)."""
        now = time.monotonic()
        self.used = max(0.0, self.used - (now - self.t) * self.limit / self.window)
        self.t = now

    def wait_for(self, r: float) -> float:
        """Seconds until r more units fit."""
        self._refill()
        over = self.used + r - self.limit
        return 0.0 if over <= 0 else over / (self.limit / self.window)

    def charge(self, r: float):
        """Use r units."""
        self._refill()
        self.used += r

    def remaining(self):
        """Units left now."""
        self._refill()
        return max(0, int(self.limit - self.used))


REWRITES_PATH = Path(__file__).resolve().parents[1] / "eval/rewrites_20b.json"


def _load_rewrites() -> dict:
    """Real 20b understand replies (temperature 0) for K's questions + wording probes (K §24),
    keyed by match_key(question). Replayed verbatim; anything else (e.g. variants) gets the raw
    question as its search query: a KNOWN DIFFERENCE (more gate refusals than real Groq)."""
    try:
        return {k: v["text"] for k, v in json.loads(REWRITES_PATH.read_text()).items() if v.get("text")}
    except (OSError, ValueError):
        return {}


class State:
    """The stand-in's whole state: config, limit buckets, in-flight count, stats, random generator."""
    def __init__(self):
        self.reset()

    def reset(self, seed=None):
        """Default config (calibrated profile, Groq's limits) and empty counters."""
        self.rng = random.Random(seed)
        self.cfg = {
            # latency profile (K §25): "afternoon" (stage 2a) or "evening" (stage 2b, n=20); never pooled
            "profile": CAL["default_profile"],
            "rare_rate": None,          # None = the profile's measured rate; a number overrides it
            "slowdown": V(CAL["load_slowdown"]["per_inflight_fraction"]),
            "max_conc": V(CAL["load_slowdown"]["max_concurrency"]),
            "err_rate": V(CAL["failures"]["error_5xx_rate"]),
            "stall_rate": V(CAL["failures"]["midstream_stall_rate"]),
            "stall_ms": V(CAL["failures"]["midstream_stall_ms"]),
            "drop_rate": V(CAL["failures"]["midstream_drop_rate"]),
            "check_fail_rate": V(CAL["failures"]["check_fail_rate"]),   # K §37: share of checks that say "not supported"
            "limits": {k: V(CAL["limits"][k]) for k in LIMIT_NAMES},
        }
        self._build_buckets()
        self.inflight = 0
        self.peak_inflight = 0
        self.sem = asyncio.Semaphore(self.cfg["max_conc"])
        self.stats = {"requests": 0, "ok": 0, "429": {}, "5xx": 0, "stall": 0, "drop": 0, "rare": 0,
                      "rewrite_replayed": 0, "rewrite_raw": 0, "check_failed": 0}
        self.rewrites = _load_rewrites()

    def _build_buckets(self):
        """One bucket per (model, limit)."""
        self.buckets = {m: {k: Bucket(self.cfg["limits"][k], LIMIT_NAMES[k][1]) for k in LIMIT_NAMES}
                        for m in MODELS}


S = State()
app = FastAPI()


def est_tokens(text: str) -> int:
    # ~4 chars/token; real Groq counted 2792-3096 tokens for ~11.2k-char draft prompts
    """Token estimate, ~4 characters per token (matches Groq's counts on our prompts)."""
    return max(1, len(text) // 4)


# ---------------------------------------------------------------- canned content per pipeline step
def make_reply(messages) -> str:
    """Canned reply text for the pipeline step the prompt belongs to (understand / draft / check)."""
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    if "route questions" in system:          # step 1 understand
        from relay.textnorm import match_key
        hit = S.rewrites.get(match_key(user))
        S.stats["rewrite_replayed" if hit else "rewrite_raw"] += 1
        if hit:
            return hit
        return json.dumps({"papers": [], "search_query": user[:200], "needs_numbers": False, "cross_paper": False})
    if "verify" in system.lower():           # step 5 check: fails at the replay-measured rate (K §37) -> one redraft
        if S.rng.random() < S.cfg["check_fail_rate"]:
            S.stats["check_failed"] += 1
            return json.dumps({"supported": False, "problems": ["simulated: checker did not confirm support"]})
        return json.dumps({"supported": True, "problems": []})
    m = re.search(r"\[(C\d+)\][^\n]*\n(.+)", user)   # step 4 draft: quote the first passage verbatim
    if m:
        cid, body = m.group(1), m.group(2)
        quote = " ".join(body.split()[:18])
        return json.dumps({"not_in_papers": False,
                           "answer": f"The papers state that {quote} [{cid}].",
                           "claims": [{"chunk": cid, "quote": quote}]})
    return json.dumps({"not_in_papers": True, "answer": "", "claims": []})


def groq_429(model, kind, used, req, wait):
    """A 429 response shaped exactly like Groq's (same message text and retry-after)."""
    name, _ = LIMIT_NAMES[kind]
    msg = (f"Rate limit reached for model `{model}` in organization `org_STANDIN` service tier `on_demand` "
           f"on {name} ({kind.upper()}): Limit {int(S.cfg['limits'][kind])}, Used {int(used)}, "
           f"Requested {int(req)}. Please try again in {wait:.9g}s. (stand-in)")
    S.stats["429"][kind] = S.stats["429"].get(kind, 0) + 1
    return JSONResponse(status_code=429, headers={"retry-after": str(math.ceil(wait))},
                        content={"error": {"message": msg, "type": "tokens" if "t" in kind[:2] else "requests",
                                           "code": "rate_limit_exceeded"}})


def ratelimit_headers(b):
    """x-ratelimit-* headers like Groq's, from the stand-in's buckets."""
    return {"x-ratelimit-limit-requests": str(int(b["rpd"].limit)),
            "x-ratelimit-remaining-requests": str(b["rpd"].remaining()),
            "x-ratelimit-reset-requests": f"{(b['rpd'].used) * 86400 / b['rpd'].limit:.1f}s",
            "x-ratelimit-limit-tokens": str(int(b["tpm"].limit)),
            "x-ratelimit-remaining-tokens": str(b["tpm"].remaining()),
            "x-ratelimit-reset-tokens": f"{(b['tpm'].used) * 60 / b['tpm'].limit:.3f}s"}


@app.post("/v1/chat/completions")
async def chat(req: Request):
    """POST /v1/chat/completions: limits, injected faults, then a streamed reply with calibrated timing."""
    body = await req.json()
    model = body.get("model")
    if model not in MODELS:
        return JSONResponse(status_code=404, content={"error": {"message": f"model {model} not in stand-in"}})
    S.stats["requests"] += 1
    prof = CAL["profiles"][S.cfg["profile"]]
    cal = prof["models"][model]
    rare_rate = S.cfg["rare_rate"] if S.cfg["rare_rate"] is not None else V(prof["rare_delay"]["rate"])
    rare_mults = V(prof["rare_delay"]["multipliers"])
    messages = body["messages"]
    n_in = est_tokens("".join(m["content"] for m in messages))

    # ---- admission: check every bucket, refuse with the one needing the longest wait
    b = S.buckets[model]
    need = {"rpm": 1, "rpd": 1, "itpm": n_in, "tpm": n_in, "tpd": n_in}
    waits = {k: b[k].wait_for(r) for k, r in need.items()}
    worst = max(waits, key=waits.get)
    if waits[worst] > 0:
        return groq_429(model, worst, b[worst].used, need[worst], waits[worst])
    for k, r in need.items():
        b[k].charge(r)          # charged at admission; output tokens charged at the end
    hdrs = ratelimit_headers(b)

    rng = S.rng
    if rng.random() < S.cfg["err_rate"]:
        await asyncio.sleep(rng.uniform(0.05, 0.4))
        S.stats["5xx"] += 1
        return JSONResponse(status_code=503, content={"error": {"message": "stand-in: service unavailable"}})

    text = make_reply(messages)
    n_reason = max(1, int(rng.gauss(50, 15)))
    n_out = min(body.get("max_tokens", 1024), est_tokens(text))

    async def stream():
        """The streamed body: wait in the FIFO, sleep the calibrated first-token time, send chunks."""
        async with S.sem:                        # FIFO above max concurrency (assumed)
            S.inflight += 1
            S.peak_inflight = max(S.peak_inflight, S.inflight)
            try:
                load = 1 + S.cfg["slowdown"] * max(0, S.inflight - 4)
                ttft = (V(cal["ttft_base_ms"]) + V(CAL["ttft_ms_per_input_token"]) * n_in)
                ttft *= math.exp(rng.gauss(0, V(cal["ttft_lognormal_sigma"]))) * load
                if rng.random() < rare_rate:
                    ttft *= rng.choice(rare_mults)          # one of the measured slow-call multipliers
                    S.stats["rare"] += 1
                gap = V(cal["reasoning_gap_ms"]) * load
                await asyncio.sleep(max(0, ttft - gap) / 1000)          # wait before ANY token
                base = {"id": "standin", "object": "chat.completion.chunk", "model": model}
                yield f"data: {json.dumps({**base, 'choices': [{'index': 0, 'delta': {'reasoning': '…'}}]})}\n\n"
                await asyncio.sleep(gap / 1000)                          # reasoning gap
                tps = (V(cal["decode_tok_per_s"]) or 500) / load
                words = re.findall(r"\S+\s*", text)
                step = 3
                stall_at = rng.randrange(len(words)) if rng.random() < S.cfg["stall_rate"] else -1
                drop_at = rng.randrange(1, max(2, len(words))) if rng.random() < S.cfg["drop_rate"] else -1
                for i in range(0, len(words), step):
                    if drop_at != -1 and i >= drop_at:
                        S.stats["drop"] += 1
                        return                                           # no [DONE]: client sees truncation
                    if stall_at != -1 and i <= stall_at < i + step:
                        S.stats["stall"] += 1
                        await asyncio.sleep(S.cfg["stall_ms"] / 1000)    # "succeeds slowly"
                    piece = "".join(words[i:i + step])
                    yield f"data: {json.dumps({**base, 'choices': [{'index': 0, 'delta': {'content': piece}}]})}\n\n"
                    await asyncio.sleep(est_tokens(piece) / tps)
                b["tpm"].charge(n_out + n_reason)
                b["tpd"].charge(n_out + n_reason)
                usage = {"prompt_tokens": n_in, "completion_tokens": n_out + n_reason,
                         "completion_tokens_details": {"reasoning_tokens": n_reason}}
                yield f"data: {json.dumps({**base, 'choices': [], 'usage': usage})}\n\n"
                yield "data: [DONE]\n\n"
                S.stats["ok"] += 1
            finally:
                S.inflight -= 1

    return StreamingResponse(stream(), media_type="text/event-stream", headers=hdrs)


@app.post("/admin/config")
async def config(req: Request):
    """POST /admin/config: change limits, fault rates, profile or seed for a scenario."""
    body = await req.json()
    if "seed" in body:
        S.rng = random.Random(body["seed"])
    for k, v in body.items():
        if k == "limits":
            S.cfg["limits"].update(v)
            S._build_buckets()
        elif k == "profile" and v not in CAL["profiles"]:
            return JSONResponse(status_code=400, content={"error": f"unknown profile {v}"})
        elif k in S.cfg:
            S.cfg[k] = v
    return {"cfg": S.cfg}


@app.post("/admin/exhaust")
async def exhaust(req: Request):
    """Fill a daily bucket to leave only `leave` units (the 3pm 'budget gone' scenario)."""
    body = await req.json()
    bk = S.buckets[body["model"]][body.get("limit", "tpd")]
    bk.charge(max(0, bk.limit - bk.used - body.get("leave", 0)))
    return {"used": bk.used, "limit": bk.limit}


@app.post("/admin/reset")
async def reset(req: Request):
    """POST /admin/reset: fresh buckets and stats (optionally a new seed)."""
    body = await req.json() if (await req.body()) else {}
    S.reset(seed=body.get("seed"))
    return {"ok": True}


@app.get("/admin/stats")
async def stats():
    """GET /admin/stats: counters, in-flight peak, remaining capacity."""
    return {**S.stats, "inflight": S.inflight, "peak_inflight": S.peak_inflight,
            "remaining": {m: {k: bk.remaining() for k, bk in b.items()} for m, b in S.buckets.items()}}
