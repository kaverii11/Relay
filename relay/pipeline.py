"""The Relay pipeline: one user question, end to end.

  [1 understand] 20b rewrites the question into a search query (never judges scope)
  [2 retrieve ]  TOOL: BM25 + cross-encoder over the chunked papers (local, no tokens)
  [3 decide   ]  BRANCH: cache hit | gate below threshold -> "the papers don't say"
                 | no capacity within the deadline -> busy reply | draft (choosing a ladder rung)
  [4 draft    ]  120b (or 20b on the ladder) writes a cited answer with word-for-word quotes
  [5 check    ]  code check (ids + quotes) + model check (20b); LOOP: one redraft on failure

The answer is buffered until the check passes, so the person's first token comes after step 5.
Every model call goes through call_model(), which owns the retry policy (DECISIONS §3).
"""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path
import random
import re
import threading
import time
from dataclasses import dataclass, field

import httpx

from relay.config import BIG, PAPER_VERSIONS, SMALL, Policy, RetrievalSetting
from relay.limiter import Limiter
from relay.llm import stream_chat
from relay.prompts import claim_quotes, check_messages, draft_messages, understand_messages
from relay.retrieval import Retriever
from relay.textnorm import match_key, quote_in

DRAFT_OUT_EST = 350      # tokens; real 120b drafts averaged 258 out (stage 2a), padded for safety
SHORT_OUT_EST = 120      # understand/check; real 20b understand averaged 98 out
# K (2026-11-10 §37): arrival check expects 3.2 s of work in all = the evening e2e set's answers-only first-token
# p50 (3212 ms, n=8, which includes 2 redrafts). Split: pre-draft and check at their measured p50s (understand 614
# + retrieve ~200; check 605); the draft stage carries the rest, i.e. the redraft allowance (measured draft p50 879).
EXPECTED_WORK_MS = {"draft": 1800, "check": 600}
EXPECTED_PRE_DRAFT_MS = 800


class Cancelled(Exception):
    """The person gave up (their patience ran out)."""


class Busy(Exception):
    def __init__(self, limit_kind, eta_s):
        super().__init__(limit_kind)
        self.limit_kind, self.eta_s = limit_kind, eta_s


class DailyLimit(Exception):
    def __init__(self, model, kind):
        super().__init__(kind)
        self.model, self.kind = model, kind


class CallFailed(Exception):
    pass


def est_tokens(messages) -> int:
    return max(1, sum(len(m["content"]) for m in messages) // 4)


def limit_kind(body: str) -> str:
    b = (body or "").lower()
    for k in ("rpd", "tpd", "itpm", "rpm", "tpm"):
        if f"({k})" in b:
            return k
    if "per day" in b:
        return "tpd" if "token" in b else "rpd"
    return "rpm" if "request" in b else "tpm"


def parse_json(text: str):
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def normalise_q(q: str) -> str:
    return " ".join(re.findall(r"\w+", q.lower()))


class ExactCache:
    """Exact match on the normalised question + setting + paper versions. No semantic matching
    (DECISIONS §2: 'Moshi latency' must not hit 'Moshi theoretical latency')."""

    def __init__(self):
        self.d, self.lock = {}, threading.Lock()

    def key(self, q, setting):
        return (normalise_q(q), setting, PAPER_VERSIONS)

    def get(self, q, setting):
        with self.lock:
            return self.d.get(self.key(q, setting))

    def put(self, q, setting, value):
        with self.lock:
            self.d[self.key(q, setting)] = value


@dataclass
class Ctx:
    rid: str
    question: str
    t0: float                       # perf_counter at ARRIVAL
    cancel: threading.Event
    deadline_ms: float
    retries: int = 0
    calls: int = 0
    service_start_ms: float | None = None   # first model call SENT (or cache answered); None = never served
    by_model: dict = field(default_factory=dict)   # model -> [tokens_in, tokens_out] (out includes reasoning)
    rerank_ms: float | None = None
    draft_ready_ms: float | None = None      # first draft: prompt built, asking the limiter for a slot
    draft_sent_ms: float | None = None       # first draft: request actually sent
    arrival_pred_draft_sent_ms: float | None = None
    arrival_busy_pred: int | None = None     # 1 = the arrival check said busy (acted on, or shadow only)
    busy_path: str = ""                      # arrival | mid | queue
    tokens_cached: int = 0                   # prompt tokens Groq served from its cache (K, eval: logged per call)
    limiter_wait_ms: float = 0.0             # our own limiter's planned waits, summed (Table 3 excludes it, K)
    tokens_in: int = 0
    tokens_out: int = 0
    events: list = field(default_factory=list)

    def ms(self):
        return (time.perf_counter() - self.t0) * 1000

    def ev(self, name, **kw):
        self.events.append({"t_ms": round(self.ms(), 1), "ev": name, **kw})

    def sleep(self, s, why):
        """Interruptible wait; logged as WAITING (planned limiter wait) or RETRYING (backoff)."""
        if s <= 0:
            return
        self.ev(why + "_start", seconds=round(s, 3))
        if self.cancel.wait(s):
            raise Cancelled()
        self.ev(why + "_end")


class _Async:
    """Run fn on a thread now; .result() joins and re-raises. Used for the raw-question retrieval pass,
    which overlaps the understand call (K §29: local, no tokens, ~220 ms measured)."""

    def __init__(self, fn):
        self.r = self.e = None
        self.t = threading.Thread(target=self._run, args=(fn,), daemon=True)
        self.t.start()

    def _run(self, fn):
        try:
            self.r = fn()
        except Exception as e:   # noqa: BLE001
            self.e = e

    def result(self):
        self.t.join()
        if self.e:
            raise self.e
        return self.r


class Pipeline:
    def __init__(self, *, base_url, api_key, source, setting: RetrievalSetting, policy: Policy,
                 limiter: Limiter, cache: ExactCache | None, retriever: Retriever, budget=None):
        self.base_url, self.api_key, self.source = base_url, api_key, source
        self.setting, self.p, self.lim, self.cache, self.ret = setting, policy, limiter, cache, retriever
        self.budget = budget      # relay.budget.Budget for real non-probe runs (K §31); None on the stand-in
        self.keep_passages = False    # e2e sets (K §34): keep the passages the drafter saw + each draft's claims
        self.daily_dump = None        # eval (K §41): Path -> on a per-day 429 save body + headers there, no ladder
        self.daily_hit = None
        self.http = httpx.Client(timeout=None, limits=httpx.Limits(max_connections=200, max_keepalive_connections=50))
        # Requests that will need a draft but haven't reserved it yet (K: a SET of ids, not a counter,
        # so it can't drift and can be inspected). Added at arrival, removed when the draft is
        # reserved or in `finally`.
        self.queued_drafts: set[str] = set()
        self.qlock = threading.Lock()
        chunk_tok = [len(c.text) // 4 + 12 for c in retriever.chunks]          # +12: the citation header
        self.mean_chunk_tok = sum(chunk_tok) / len(chunk_tok)
        self.draft_overhead_tok = len(draft_messages("x" * 80, [])[0]["content"]) // 4 + 30

    def draft_est(self, k):
        return self.draft_overhead_tok + k * self.mean_chunk_tok

    # ------------------------------------------------------------------ model calls + retry policy
    def call_model(self, ctx: Ctx, model, messages, kind, effort=None, out_est=SHORT_OUT_EST):
        n_in = est_tokens(messages)
        attempt = 0
        while True:
            if ctx.cancel.is_set():
                raise Cancelled()
            left_ms = ctx.deadline_ms - ctx.ms()
            max_wait = max(0.0, (left_ms - EXPECTED_WORK_MS.get(kind, 550)) / 1000)
            if kind == "draft" and ctx.draft_ready_ms is None:
                ctx.draft_ready_ms = ctx.ms()
            if self.budget is not None:          # real-run caps (K §31), checked before anything is spent
                self.budget.reserve(model, n_in, out_est)
            wait, binding, ok = self.lim.acquire(model, n_in, out_est, max_wait)
            if not ok:
                if binding in ("rpd", "tpd"):
                    raise DailyLimit(model, binding)
                raise Busy(binding, wait)
            # planned wait for the slot our limiter reserved; +50 ms because arriving exactly on the
            # refill boundary still got a 429 in the smoke test (float edge, no network slack locally)
            if kind == "draft":
                with self.qlock:
                    self.queued_drafts.discard(ctx.rid)    # its tokens now live in the limiter's buckets
            ctx.sleep(wait + 0.05 if wait > 0 else 0, "waiting")
            ctx.limiter_wait_ms += wait * 1000
            if kind == "draft" and ctx.draft_sent_ms is None:
                ctx.draft_sent_ms = ctx.ms()
            self.lim.note_request(is_retry=attempt > 0)
            ctx.calls += 1
            if ctx.service_start_ms is None:
                ctx.service_start_ms = ctx.ms()
            timeout = self.p.call_timeout_draft_s if kind == "draft" else self.p.call_timeout_short_s
            timeout = max(0.5, min(timeout, (ctx.deadline_ms - ctx.ms()) / 1000))
            extra = {"reasoning_effort": effort or self.p.reasoning_effort}
            ctx.ev("call_start", step=kind, model=model, attempt=attempt, est_in=n_in,
                   limiter_wait_s=round(wait, 3), limiter_binding=binding)     # K §34: limiter wait per call
            r = stream_chat(messages, model, base_url=self.base_url, api_key=self.api_key,
                            max_tokens=800 if kind == "draft" else 400, timeout_s=timeout,
                            client=self.http, extra=extra)
            self.lim.sync(model, r.headers)
            self.lim.settle(model, out_est, r.tokens_out)
            if self.budget is not None:
                self.budget.record(model, r.tokens_in, r.tokens_out, r.status)
            ctx.tokens_in += r.tokens_in
            ctx.tokens_out += r.tokens_out          # completion_tokens: reasoning is inside it (measured, stage 1)
            ctx.tokens_cached += r.cached_tokens
            mt = ctx.by_model.setdefault(model, [0, 0])
            mt[0] += r.tokens_in
            mt[1] += r.tokens_out
            lk = limit_kind(r.error_body) if r.status == 429 else ""
            ctx.ev("call_end", step=kind, model=model, attempt=attempt, status=r.status,
                   err=r.error_kind, limit=lk, first_any_ms=r.first_any_ms, ttft_ms=r.ttft_ms,
                   work_ms=round(r.total_ms, 1), tokens_in=r.tokens_in, tokens_out=r.tokens_out,
                   cached_tokens=r.cached_tokens, retry_after=r.headers.get("retry-after"))
            if r.status == 200 and not r.error_kind:
                return r
            # ---- failure: decide whether to retry
            if r.status == 429 and self.p.learn_limits:
                m = re.search(r"Limit (\d+)", r.error_body or "")
                if m and self.lim.learn(model, lk, int(m.group(1))):
                    ctx.ev("limit_learned", model=model, limit=lk, value=int(m.group(1)))
            if r.status == 429 and lk in ("rpd", "tpd"):
                if self.daily_dump is not None:           # K §41 (eval): keep the whole reply, then stop; no retry
                    self.daily_hit = {"wall": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                                      "model": model, "limit": lk, "status": r.status, "step": kind,
                                      "headers": dict(r.headers), "body": r.error_body}
                    Path(self.daily_dump).write_text(json.dumps(self.daily_hit, indent=2))
                raise DailyLimit(model, lk)               # never retry a per-day limit
            retryable = r.status == 429 or r.status >= 500 or r.error_kind in ("network", "truncated") \
                or (r.error_kind == "timeout" and kind != "draft" and attempt == 0)
            if r.status == 429:
                ra = float(r.headers.get("retry-after") or 1)
                delay = ra if self.p.retry_jitter == "exact" else ra + random.uniform(0, max(0.5, ra * 0.5))
            else:
                delay = random.uniform(0, self.p.backoff_base_ms * (2 ** attempt)) / 1000   # full jitter
            out_of_time = (ctx.ms() + delay * 1000 + EXPECTED_WORK_MS.get(kind, 550)) > ctx.deadline_ms
            if (not retryable or ctx.retries >= self.p.max_retries_per_question or out_of_time
                    or not self.lim.retry_allowed(self.p.retry_budget_fraction)):
                if r.status == 429:
                    raise Busy(lk, float(r.headers.get("retry-after") or 1))
                raise CallFailed(f"{kind} {r.status} {r.error_kind}")
            ctx.retries += 1
            attempt += 1
            ctx.sleep(delay, "retrying")

    # ------------------------------------------------------------------ the five steps
    def run(self, ctx: Ctx) -> dict:
        out = {"degrade_level": "full", "model": "", "answer": "", "kind": "", "gate": None,
               "citations": [], "query": None}
        try:
            # cache (rung 0)
            if self.p.cache and self.cache:
                hit = self.cache.get(ctx.question, self.setting.name)
                if hit:
                    ctx.service_start_ms = ctx.ms()
                    out.update(hit, degrade_level="cache")
                    return self._deliver(ctx, out, "ok")

            # arrival check (K, B): would even the CHEAPEST ladder rung miss the deadline?
            if self.p.arrival_check != "off":
                busy, eta_s, kind_ = self._arrival_predict(ctx)
                if busy and self.p.arrival_check == "on":
                    return self._busy(ctx, out, kind_, eta_s, path="arrival")
            with self.qlock:
                self.queued_drafts.add(ctx.rid)

            # [1] understand: rewrite query. If it can't run, the raw question still works as a query.
            # K §29: the RAW-question retrieval pass starts now and overlaps the 20b call (local, no tokens).
            raw_pass = _Async(lambda: self.ret.search(ctx.question)) if self.p.gate_input == "max" else None
            query, hints = ctx.question, {}
            try:
                r = self.call_model(ctx, SMALL, understand_messages(ctx.question), "understand")
                j = parse_json(r.text) or {}
                query = (j.get("search_query") or "").strip() or ctx.question
                hints = {k: j.get(k) for k in ("papers", "needs_numbers", "cross_paper")}
            except (Busy, DailyLimit, CallFailed) as e:
                ctx.ev("understand_skipped", why=type(e).__name__)
                out["degrade_level"] = "raw_query"
            out["query"] = query

            # [2] retrieve (tool). gate_input "max" (K §29): score the raw question and the rewrite; the
            # higher cross-encoder score is the gate, and the drafter gets THAT query's passages.
            gate_raw = gate_rw = None
            if raw_pass is not None and query == ctx.question:          # empty / skipped rewrite: one pass
                hits, gate, tms = raw_pass.result()
                gate_raw = gate_rw = gate
                by = "same"
            else:
                hits, gate, tms = self.ret.search(query)
                gate_rw, by = gate, "rewrite"
                if raw_pass is not None:
                    h_raw, gate_raw, _ = raw_pass.result()
                    if gate_raw > gate:
                        hits, gate, by = h_raw, gate_raw, "raw"
            out["gate"], out["gate_by"] = round(gate, 3), by
            ctx.rerank_ms = round(tms["ce_ms"], 1)      # the pass on the critical path (the raw one overlapped understand)
            ctx.ev("retrieve", **{k: round(v, 1) for k, v in tms.items()}, gate=round(gate, 3), gate_by=by,
                   gate_raw=None if gate_raw is None else round(gate_raw, 3),
                   gate_rewrite=None if gate_rw is None else round(gate_rw, 3),
                   hits=[h.chunk.cite() for h in hits])

            if self.keep_passages:
                out["passages"] = [{"cite": h.chunk.cite(), "bm25": round(h.bm25, 2), "ce": round(h.ce, 3),
                                    "text": h.chunk.text} for h in hits[:self.setting.k]]
            # [3] decide: refuse if the evidence isn't there (K §29 cutoff on the gate above)
            if gate < self.p.gate_threshold:
                return self._refuse(ctx, out, hits, "gate")

            # [3] decide: pick the ladder rung that fits the limits and the deadline
            plan = self._plan_draft(ctx, query, hits)
            if plan is None:
                return self._busy(ctx, out, *self._busy_eta(ctx, query, hits))
            model, k, level = plan
            if level != "full":
                out["degrade_level"] = level
            use = hits[:k]
            if self.keep_passages:
                out["passages"] = out["passages"][:k]

            # [4] draft  -> [5] check, with ONE redraft loop
            feedback = None
            for round_ in range(2):
                try:
                    r = self.call_model(ctx, model, draft_messages(ctx.question, use, feedback), "draft",
                                        out_est=DRAFT_OUT_EST)
                except DailyLimit as e:
                    if model == BIG and self.daily_hit is None:   # per-day limit on 120b: drop to 20b (separate quota); not in stop mode
                        ctx.ev("ladder", to="small_model", why=e.kind)
                        model, out["degrade_level"] = SMALL, "small_model"
                        r = self.call_model(ctx, model, draft_messages(ctx.question, use, feedback), "draft",
                                            out_est=DRAFT_OUT_EST)
                    else:
                        raise
                out["model"] = model
                d = parse_json(r.text)
                if d is None:
                    feedback = "Output was not valid JSON."
                    continue
                if self.keep_passages:
                    ctx.ev("draft_out", round=round_, model=model, draft=d)
                if d.get("not_in_papers"):
                    return self._refuse(ctx, out, use, "drafter")
                ok, why = self._code_check(d, use)
                code_ok, code_why, model_ok, model_why = ok, why, None, ""
                if ok and self._needs_model_check(hints):
                    ok, why = self._model_check(ctx, d, use)
                    model_ok, model_why = ok, why
                # K (2026-11-11, item 4): both verdicts recorded separately, so code-only vs both (§8) comes from one run
                ctx.ev("check", round=round_, ok=ok, why=why, redraft=round_ == 1,
                       code_ok=code_ok, code_why=code_why, model_ok=model_ok, model_why=model_why)
                if ok:
                    out["answer"] = self._render(d["answer"], use)
                    out["citations"] = sorted({use[int(c["chunk"][1:]) - 1].chunk.cite() for c in d["claims"]})
                    out["kind"] = "answer"
                    if self.cache:
                        self.cache.put(ctx.question, self.setting.name,
                                       {k: out[k] for k in ("answer", "citations", "kind", "model", "query", "gate")})
                    return self._deliver(ctx, out, "ok")
                feedback = why
            return self._refuse(ctx, out, use, "unverified")
        except Cancelled:
            ctx.ev("gave_up")
            return self._finish(ctx, out, "timeout", gave_up=True)
        except Busy as e:
            return self._busy(ctx, out, e.limit_kind, e.eta_s)
        except DailyLimit as e:
            return self._busy(ctx, out, e.kind, self._daily_eta(e.model))
        except CallFailed as e:
            ctx.ev("failed", why=str(e))
            return self._finish(ctx, out, "error")
        finally:
            with self.qlock:
                self.queued_drafts.discard(ctx.rid)

    # ------------------------------------------------------------------ decide helpers
    def _arrival_predict(self, ctx):
        """Predict when this request's draft could be sent, using the measured refill formula,
        the limiter's current buckets, and every not-yet-reserved draft queued ahead (each at the
        full-rung size: pessimistic, since some will be cache hits or refusals). Busy only if the
        cheapest rung misses the deadline (K). Logged in both 'on' and 'shadow' modes."""
        with self.qlock:
            ahead = len(self.queued_drafts - {ctx.rid})
        k_full, k_less = self.setting.k, max(2, self.setting.k // 2)
        best = None
        for model, k, level in [(BIG, k_full, "full"), (BIG, k_less, "fewer_chunks"), (SMALL, k_less, "small_model")]:
            if model == BIG and self.lim.daily_fraction_left(BIG) < self.p.daily_reserve_fraction:
                continue
            ahead_tok = ahead * self.draft_est(k_full) if model == BIG else 0.0
            wait, binding = self.lim.peek_wait(model, self.draft_est(k), DRAFT_OUT_EST, ahead_tok)
            if binding in ("rpd", "tpd") and wait > 0:
                continue
            sent_ms = ctx.ms() + max(EXPECTED_PRE_DRAFT_MS, wait * 1000)   # from NOW (may have queued already)
            if best is None or sent_ms < best[0]:
                best = (sent_ms, wait, binding, level)
        if best is None:                                  # every rung blocked by a daily limit
            ctx.arrival_busy_pred, ctx.arrival_pred_draft_sent_ms = 1, None
            ctx.ev("arrival_check", busy=True, why="daily", ahead=ahead, mode=self.p.arrival_check)
            return True, self._daily_eta(BIG), "tpd"
        sent_ms, wait, binding, level = best
        busy = sent_ms + EXPECTED_WORK_MS["draft"] + EXPECTED_WORK_MS["check"] > ctx.deadline_ms
        ctx.arrival_busy_pred, ctx.arrival_pred_draft_sent_ms = int(busy), round(sent_ms, 1)
        ctx.ev("arrival_check", busy=busy, ahead=ahead, rung=level, pred_draft_sent_ms=round(sent_ms, 1),
               binding=binding, mode=self.p.arrival_check)
        return busy, wait, binding

    def _plan_draft(self, ctx, query, hits):
        k_full, k_less = self.setting.k, max(2, self.setting.k // 2)
        rungs = [(BIG, k_full, "full"), (BIG, k_less, "fewer_chunks"), (SMALL, k_less, "small_model")]
        for model, k, level in rungs:
            if model == BIG and self.lim.daily_fraction_left(BIG) < self.p.daily_reserve_fraction:
                ctx.ev("ladder_skip", rung=level, why="daily_reserve")
                continue
            n_in = est_tokens(draft_messages(ctx.question, hits[:k]))
            wait, binding = self.lim.predict_wait_s(model, n_in, DRAFT_OUT_EST)
            if binding in ("rpd", "tpd") and wait > 0:
                continue
            budget_ms = ctx.deadline_ms - ctx.ms() - EXPECTED_WORK_MS["draft"] - EXPECTED_WORK_MS["check"]
            if wait * 1000 <= budget_ms:
                ctx.ev("ladder", rung=level, model=model, k=k, predicted_wait_s=round(wait, 2))
                return model, k, level
        return None

    def _busy_eta(self, ctx, query, hits):
        best = (None, math.inf)
        for model in (BIG, SMALL):
            n_in = est_tokens(draft_messages(ctx.question, hits[:max(2, self.setting.k // 2)]))
            w, kind = self.lim.predict_wait_s(model, n_in, DRAFT_OUT_EST)
            if w < best[1]:
                best = (kind, w)
        return best

    def _daily_eta(self, model):
        w, _ = self.lim.predict_wait_s(model, 3300, 0)
        return w

    def _needs_model_check(self, hints):
        if self.p.check_mode == "both":
            return True
        if self.p.check_mode == "code_only":
            return False
        return bool(hints.get("needs_numbers") or hints.get("cross_paper"))   # "adaptive", §8 option (iii)

    def _code_check(self, d, use):
        claims = d.get("claims") or []
        if not claims or not d.get("answer"):
            return False, "No claims with quotes."
        for c in claims:
            cid = str(c.get("chunk", ""))
            if not re.fullmatch(r"C\d+", cid) or not 1 <= int(cid[1:]) <= len(use):
                return False, f"Cited {cid}, which is not one of the passages."
            qs = claim_quotes(c)                 # K §37: several quotes per claim, EACH word for word
            if not qs:
                return False, f"No quote for {cid}."
            for q in qs:
                if not quote_in(q, use[int(cid[1:]) - 1].chunk.text):
                    return False, f"Quote for {cid} is not word-for-word in that passage: \"{q[:60]}\""
        return True, ""

    def _model_check(self, ctx, d, use):
        r = self.call_model(ctx, SMALL, check_messages(ctx.question, d["answer"], d["claims"], use), "check",
                            effort=self.p.check_effort)
        j = parse_json(r.text) or {}
        if j.get("supported") is True:
            return True, ""
        return False, "; ".join(j.get("problems") or ["checker did not confirm support"])

    def _render(self, answer, use):
        return re.sub(r"\[C(\d+)\]", lambda m: use[int(m.group(1)) - 1].chunk.cite()
                      if 1 <= int(m.group(1)) <= len(use) else m.group(0), answer)

    # ------------------------------------------------------------------ replies (no model calls)
    def _refuse(self, ctx, out, hits, why):
        near = ", ".join(h.chunk.cite() for h in hits[:3])
        out.update(kind="refusal", answer=(
            "The papers don't say. I searched all three papers (Attention Is All You Need v7, Moshi v1, "
            f"Dynamic Chunking v2) and found nothing that answers this. Closest passages: {near}."),
            citations=[h.chunk.cite() for h in hits[:3]], refuse_reason=why)
        if self.cache:
            self.cache.put(ctx.question, self.setting.name,
                           {k: out[k] for k in ("answer", "citations", "kind", "query", "gate")})
        return self._deliver(ctx, out, "ok")

    def _busy(self, ctx, out, limit_kind, eta_s, path="mid"):
        ctx.busy_path = path
        eta = "under a minute" if eta_s < 60 else (f"about {math.ceil(eta_s / 60)} min" if eta_s < 3600
                                                    else f"about {eta_s / 3600:.1f} h")
        at = (dt.datetime.now() + dt.timedelta(seconds=eta_s)).strftime("%H:%M")
        out.update(kind="busy", answer=(
            "I can't give you a checked answer right now: the assistant has hit its "
            f"{'daily' if limit_kind in ('rpd', 'tpd') else 'per-minute'} usage limit. "
            f"Capacity for a question like yours should be back in {eta} (around {at}). "
            "I won't send an unchecked answer instead. Please ask again then."), busy_limit=limit_kind,
            eta_s=round(eta_s, 1))
        ctx.ev("busy", limit=limit_kind, eta_s=round(eta_s, 1), path=path)
        return self._finish(ctx, out, "rate_limited", first_token=False)

    def _deliver(self, ctx, out, status):
        ctx.ev("first_token")
        return self._finish(ctx, out, status, first_token=True)

    def _finish(self, ctx, out, status, first_token=False, gave_up=False):
        t = ctx.ms()
        return {**out, "status": status, "first_token_ms": round(t, 1) if first_token else None,
                "total_ms": round(t, 1), "gave_up": int(gave_up), "retries": ctx.retries, "calls": ctx.calls,
                "tokens_in": ctx.tokens_in, "tokens_out": ctx.tokens_out, "events": ctx.events,
                "service_start_ms": None if ctx.service_start_ms is None else round(ctx.service_start_ms, 1),
                "by_model": ctx.by_model, "rerank_ms": ctx.rerank_ms,
                "tokens_cached": ctx.tokens_cached, "limiter_wait_ms": round(ctx.limiter_wait_ms, 1),
                **{k: (None if getattr(ctx, k) is None else (round(getattr(ctx, k), 1) if isinstance(getattr(ctx, k), float) else getattr(ctx, k)))
                   for k in ("draft_ready_ms", "draft_sent_ms", "arrival_pred_draft_sent_ms", "arrival_busy_pred")},
                "busy_path": ctx.busy_path}
