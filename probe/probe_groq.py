"""Probe the real Groq free tier. Run phases one at a time and inspect output between them.

  latency  - sequential, spaced-out calls: unloaded TTFT/total spread per model, prompt sizes
  rpm      - fire tiny requests fast until a per-minute 429; capture body+headers; poll until recovered
  tpm      - large prompts until a token-per-minute 429; capture; poll until recovered
  inflight - N simultaneous tiny requests: does latency inflate / does anything get rejected?

Every attempt (including 429s) is appended raw to probe/raw/<phase>_<timestamp>.jsonl.
Stops immediately on anything that looks like a per-day limit, to protect the daily budget.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx
import pymupdf
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from relay.llm import GROQ_BASE, stream_chat  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
KEY = os.environ.get("GROQ_API_KEY", "")
# Llama models are no longer listed for this key (checked 2026-11-09 via `models`).
SMALL, BIG, QWEN = "openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b"

_paper_text = None


def context(n_chars: int) -> str:
    global _paper_text
    if _paper_text is None:
        d = pymupdf.open(ROOT / "papers/2410.00037v1.pdf")
        _paper_text = "".join(p.get_text() for p in d)
    return _paper_text[5000:5000 + n_chars]


def msgs(n_chars: int, q="In two sentences, what does this passage describe?"):
    return [{"role": "system", "content": "Answer only from the passage."},
            {"role": "user", "content": f"Passage:\n{context(n_chars)}\n\nQuestion: {q}"}]


class Log:
    def __init__(self, phase):
        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = ROOT / f"probe/raw/{phase}_{ts}.jsonl"
        self.f = open(self.path, "a")

    def write(self, **row):
        row["wall"] = dt.datetime.now(dt.timezone.utc).isoformat()
        # never write the Groq organization id (it appears in 429 bodies)
        self.f.write(re.sub(r"org_[0-9a-z]{20,}", "org_REDACTED", json.dumps(row)) + "\n")
        self.f.flush()


LEDGER = ROOT / "probe/raw/ledger.json"
HARD_CAP = 300          # total real Groq requests the probe may EVER send (all runs, all phases)
_lock = __import__("threading").Lock()


def _spend_one():
    """Count every request before it is sent; refuse past the cap. Persisted across runs."""
    with _lock:
        n = json.loads(LEDGER.read_text())["sent"] if LEDGER.exists() else 0
        if n >= HARD_CAP:
            raise SystemExit(f"probe hard cap reached ({n}/{HARD_CAP}) - raise HARD_CAP deliberately")
        LEDGER.write_text(json.dumps({"sent": n + 1}))


def call(log, model, n_chars, max_tokens, tag, client=None, messages=None, extra=None, meta=None):
    _spend_one()
    t_start = time.time()
    r = stream_chat(messages or msgs(n_chars), model, api_key=KEY, max_tokens=max_tokens,
                    timeout_s=60, client=client, extra=extra)
    log.write(tag=tag, model=model, prompt_chars=n_chars, max_tokens=max_tokens, extra=extra,
              meta=meta, t_start=t_start, status=r.status, first_any_ms=r.first_any_ms,
              ttft_ms=r.ttft_ms, total_ms=r.total_ms, tokens_in=r.tokens_in,
              tokens_out=r.tokens_out, reasoning_tokens=r.reasoning_tokens, cached_tokens=r.cached_tokens,
              reasoning_chars=len(r.reasoning), text=r.text[:1500], headers=r.headers,
              error_kind=r.error_kind, error_body=r.error_body, limit_kind=limit_kind(r))
    return r


def limit_kind(r) -> str:
    """Which limit a 429 names, from its message: rpm / tpm / rpd / tpd / unknown."""
    if r.status != 429:
        return ""
    b = (r.error_body or "").lower()
    for k in ("rpd", "tpd", "rpm", "tpm"):
        if f"({k})" in b:
            return k
    if "per day" in b:
        return "tpd" if "token" in b else "rpd"
    if "per minute" in b:
        return "tpm" if "token" in b else "rpm"
    return "unknown"


def looks_daily(r) -> bool:
    b = (r.error_body or "").lower()
    return r.status == 429 and ("per day" in b or "(rpd)" in b or "(tpd)" in b)


def show(r, label=""):
    h = r.headers
    print(f"{label:>10} {r.status} ttft={r.ttft_ms and round(r.ttft_ms)} total={round(r.total_ms)} "
          f"in={r.tokens_in} out={r.tokens_out} rem_req={h.get('x-ratelimit-remaining-requests')} "
          f"rem_tok={h.get('x-ratelimit-remaining-tokens')} retry-after={h.get('retry-after')}"
          + (f"\n           body={r.error_body[:300]}" if r.status != 200 else ""))


def poll_recovery(log, model, tag, every_s=2.0, max_s=120):
    # Is the quota per model? While `model` is limited, try the other one once.
    # If it succeeds, the fallback model is a separate quota (the biggest capacity lever).
    other = BIG if model == SMALL else SMALL
    show(call(log, other, 200, 5, tag + "_othermodel"), "other-mdl")
    t0 = time.time()
    while time.time() - t0 < max_s:
        r = call(log, model, 200, 5, tag + "_poll")
        show(r, "poll")
        if r.status == 200:
            print(f"recovered after {time.time() - t0:.1f}s since first 429-poll")
            return time.time() - t0
        if looks_daily(r):
            sys.exit("daily limit hit - stopping")
        time.sleep(every_s)
    return None


def phase_latency(args):
    log = Log("latency")
    # (model, prompt_chars, max_tokens, n). ~4 chars/token: 600ch~150tok (understand), 10k~2.5k tok (draft)
    plan = [(SMALL, 600, 60, args.n), (SMALL, 10000, 250, args.n),
            (BIG, 600, 60, args.n_big), (BIG, 10000, 250, args.n_big)]
    with httpx.Client(timeout=None) as c:
        for model, ch, mt, n in plan:
            for i in range(n):
                r = call(log, model, ch, mt, f"lat_{ch}", client=c)
                show(r, f"{model[:10]}#{i}")
                if looks_daily(r):
                    sys.exit("daily limit hit - stopping")
                time.sleep(args.gap)
    print("wrote", log.path)


def phase_rpm(args):
    log = Log("rpm")
    model = args.model
    first429 = None
    with cf.ThreadPoolExecutor(args.conc) as ex:
        futs = [ex.submit(call, log, model, 200, 5, "rpm") for _ in range(args.n)]
        for f in cf.as_completed(futs):
            r = f.result()
            show(r, "rpm")
            if r.status == 429 and first429 is None:
                first429 = time.time()
            if looks_daily(r):
                sys.exit("daily limit hit - stopping")
    if first429:
        poll_recovery(log, model, "rpm")
    print("wrote", log.path)


def phase_tpm(args):
    log = Log("tpm")
    model = args.model
    got429 = False
    for i in range(args.n):
        r = call(log, model, args.chars, 50, "tpm")
        show(r, f"tpm#{i}")
        if looks_daily(r):
            sys.exit("daily limit hit - stopping")
        if r.status in (429, 413):
            got429 = True
            break
    if got429:
        poll_recovery(log, model, "tpm")
    print("wrote", log.path)


def phase_inflight(args):
    log = Log("inflight")
    for k in args.levels:
        with cf.ThreadPoolExecutor(k) as ex:
            rs = list(ex.map(lambda _: call(log, args.model, 200, 5, f"inflight_{k}"), range(k)))
        ok = [r for r in rs if r.status == 200]
        ttfts = sorted(r.ttft_ms for r in ok if r.ttft_ms)
        print(f"k={k}: ok={len(ok)}/{k} statuses={sorted(set(r.status for r in rs))} "
              f"ttft min/med/max={ttfts and (round(ttfts[0]), round(ttfts[len(ttfts)//2]), round(ttfts[-1]))}")
        time.sleep(args.gap)
    print("wrote", log.path)


PLAN = {  # worst-case request count per phase with default args (shown by --plan)
    "models": lambda a: 0,
    "stage1": lambda a: 5,
    "spread": lambda a: a.n,
    "tpd": lambda a: a.n + 1 + 6,
    "latency": lambda a: 2 * a.n + 2 * a.n_big,
    "rpm": lambda a: a.n + 1 + 60,            # burst + other-model check + up to 60 recovery polls
    "tpm": lambda a: a.n + 1 + 60,
    "inflight": lambda a: sum(a.levels),
}


def phase_stage1(args):
    """5 calls of the real 'understand' step: learn limits from headers, the default vs low
    reasoning cost, and get rewritten queries for seed questions (incl. vague + unanswerable)."""
    from relay.prompts import understand_messages
    sys.path.insert(0, str(ROOT))
    from eval.seed_questions import SEED
    log = Log("stage1")
    jobs = [(SMALL, None, 11), (SMALL, {"reasoning_effort": "low"}, 6),
            (BIG, None, 11), (BIG, {"reasoning_effort": "low"}, 7),
            (QWEN, None, 9)]
    with httpx.Client(timeout=None) as c:
        for model, extra, qi in jobs:
            q, answerable = SEED[qi]
            r = call(log, model, 0, 1024, "stage1_understand", client=c,
                     messages=understand_messages(q), extra=extra,
                     meta={"q": q, "answerable": answerable})
            print(f"\n=== {model} extra={extra} q={q[:60]!r}")
            show(r, "")
            print(f"  first_any={r.first_any_ms and round(r.first_any_ms)} ttft={r.ttft_ms and round(r.ttft_ms)} "
                  f"reasoning_tokens={r.reasoning_tokens} reasoning_chars={len(r.reasoning)}")
            print("  text:", r.text[:300].replace("\n", " "))
            print("  limits:", {k: v for k, v in r.headers.items() if k.startswith("x-ratelimit")})
            if looks_daily(r):
                sys.exit("daily limit hit - stopping")
            time.sleep(args.gap)
    print("wrote", log.path)


def _draft_messages(q: str, k=8):
    """Draft-sized prompt: real BM25 top-k w250 chunks for q (~2.5-3k tokens), like the pipeline."""
    import re
    import numpy as np
    from rank_bm25 import BM25Okapi
    from relay.ingest import load
    cs = load(ROOT / "data/chunks_w250.jsonl")
    tok = lambda t: re.findall(r"\w+", t.lower())
    bm = BM25Okapi([tok(c.text) for c in cs])
    idx = np.argsort(-bm.get_scores(tok(q)))[:k]
    ctx = "\n\n".join(f"{cs[i].cite()} {cs[i].text}" for i in idx)
    return [{"role": "system", "content": "Answer only from the passages. Cite each claim like "
             "[paper §section p.N]. If the passages do not answer it, say the papers don't say."},
            {"role": "user", "content": f"Passages:\n{ctx}\n\nQuestion: {q}"}]


def phase_spread(args):
    """Latency SPREAD for stand-in calibration. Short = the real understand step on distinct
    questions (TTFT shape + slow tail); draft = real-size draft prompts (tokens/sec).
    Distinct questions so we never resend an identical prompt (cache would flatter latency)."""
    from relay.prompts import understand_messages
    from eval.latency_questions import QUESTIONS
    log = Log(f"spread_{args.kind}")
    extra = {"reasoning_effort": args.effort} if args.effort else None
    qs = QUESTIONS[args.offset:args.offset + args.n]
    with httpx.Client(timeout=None) as c:
        for i, q in enumerate(qs):
            m = understand_messages(q) if args.kind == "short" else _draft_messages(q)
            r = call(log, args.model, 0, 1024 if args.kind == "short" else 600, f"spread_{args.kind}",
                     client=c, messages=m, extra=extra, meta={"q": q, "tod_ist": dt.datetime.now().strftime("%H:%M")})
            tps = r.tokens_out / ((r.total_ms - r.ttft_ms) / 1000) if r.ttft_ms and r.total_ms > r.ttft_ms else None
            print(f"#{i} {r.status} any={r.first_any_ms and round(r.first_any_ms)} ttft={r.ttft_ms and round(r.ttft_ms)} "
                  f"total={round(r.total_ms)} in={r.tokens_in} cached={r.cached_tokens} out={r.tokens_out} "
                  f"reas={r.reasoning_tokens} tok/s={tps and round(tps)} rem_tok={r.headers.get('x-ratelimit-remaining-tokens')}")
            if r.status == 429:
                print("   429:", r.error_body[:300]); 
                if looks_daily(r): sys.exit("daily limit hit - stopping")
                time.sleep(float(r.headers.get("retry-after") or 5))
            time.sleep(args.gap)
    print("wrote", log.path)


def phase_tpd(args):
    """Exhaust the DAILY TOKEN limit on a model we don't otherwise need (default Qwen), to see
    the real TPD 429 body/headers and how it refills. Then 1 call to SMALL: does it still work
    (per-model TPD) or not (org-wide TPD)? Paces at ~7k tokens/min to stay under TPM."""
    if not args.approved_tpd:
        sys.exit("tpd NOT approved by K (DECISIONS §15). Earliest: after the eval runs. "
                 "Re-run with --approved-tpd only once she approves.")
    log = Log("tpd")
    m = msgs(24000)   # ~6k-token prompt, 5 output tokens: burns TPD fast with few requests
    for i in range(args.n):
        r = call(log, args.model, 24000, 5, "tpd", messages=m)
        show(r, f"tpd#{i}")
        if r.status == 429:
            print("FULL 429 BODY:", r.error_body)
            print("HEADERS:", r.headers)
            if looks_daily(r):
                show(call(log, SMALL, 200, 5, "tpd_othermodel"), "20b-after")
                # watch refill: one tiny call every 5 min for 30 min
                for j in range(6):
                    time.sleep(300)
                    rr = call(log, args.model, 200, 5, "tpd_refill_poll"); show(rr, f"refill+{5*(j+1)}m")
                break
            time.sleep(float(r.headers.get("retry-after") or 10))
        else:
            time.sleep(55)   # one ~6k-token call per ~minute keeps under 8k TPM
    print("wrote", log.path)


def phase_models(args):
    r = httpx.get(f"{GROQ_BASE}/models", headers={"Authorization": f"Bearer {KEY}"}, timeout=15)
    print(r.status_code)
    for m in sorted(r.json().get("data", []), key=lambda m: m["id"]):
        print(m["id"], m.get("context_window"), m.get("max_completion_tokens"))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("phase", choices=["models", "stage1", "spread", "tpd", "latency", "rpm", "tpm", "inflight"])
    p.add_argument("--n", type=int, default=20)
    p.add_argument("--n-big", type=int, default=10)
    p.add_argument("--gap", type=float, default=3.0)
    p.add_argument("--conc", type=int, default=10)
    p.add_argument("--model", default=SMALL)
    p.add_argument("--chars", type=int, default=24000)
    p.add_argument("--levels", type=int, nargs="+", default=[1, 4, 8, 16])
    p.add_argument("--kind", choices=["short", "draft"], default="short")
    p.add_argument("--effort", default="low")
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--approved-tpd", action="store_true")
    p.add_argument("--plan", action="store_true", help="print planned request count and exit")
    a = p.parse_args()
    sent = json.loads(LEDGER.read_text())["sent"] if LEDGER.exists() else 0
    print(f"[{a.phase}] planned <= {PLAN[a.phase](a)} requests; ledger {sent}/{HARD_CAP} used so far")
    if a.plan:
        sys.exit(0)
    if not KEY:
        sys.exit("GROQ_API_KEY missing - put it in .env")
    {"models": phase_models, "stage1": phase_stage1, "spread": phase_spread, "tpd": phase_tpd, "latency": phase_latency, "rpm": phase_rpm,
     "tpm": phase_tpm, "inflight": phase_inflight}[a.phase](a)
