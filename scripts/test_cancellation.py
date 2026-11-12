"""Offline tests for cancellation (the person's patience runs out). No Groq, no stand-in, no PDFs, no tokens.

  .venv/bin/python scripts/test_cancellation.py

Model calls go to an in-process fake (httpx.MockTransport) that streams Groq-shaped SSE lines; retrieval is a fake
with three fixed pieces. Covers:
  1. stream_chat: cancel set mid-stream -> reading stops, the response is closed, no partial text, error_kind "cancelled"
  2. stream_chat: an HTTP 500 and a connection error with an UNSET cancel flag stay "http" / "network", not "cancelled"
  3. pipeline: cancelled before the first model call -> no call made, given up, no reply
  4. pipeline: cancelled while the draft streams -> that stream closed, no check call, given up, no reply
  5. pipeline: cancelled after the check passed, before delivery -> the answer is not delivered, given up
  6. pipeline: not cancelled -> answer delivered (understand, draft, check), every stream closed
  7. service: patience timer fires mid-stream -> row gave_up = 1, pending back to 0, stream closed
  8. service: a request that raises -> error row, traceback on stderr, pending back to 0, worker serves the next one
  9. accounting, stream cut: the limiter keeps the reservation (no refund), the estimate enters the pacing spend
     history, and the run ledger records the estimate
 10. accounting, never sent (gave up during the limiter wait, gave up just before sending, turned away by the
     limiter): run budget (request count + in-flight) and limiter reservations are given back; run_sent always
     equals the requests that reached the provider
Ledger writes go to a temporary ledger; the real probe/raw/ledger.json is never touched.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from relay import ledger  # noqa: E402
from relay.config import BIG, SETTINGS, SMALL, Policy  # noqa: E402
from relay.limiter import Limiter  # noqa: E402
from relay.llm import stream_chat  # noqa: E402
from relay.pipeline import Ctx, ExactCache, Pipeline  # noqa: E402
from relay.prompts import CHECK_SYSTEM, CHECK_SYSTEM_V2, DRAFT_SYSTEM, DRAFT_SYSTEM_V2  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="relay_cancel_"))
ledger.LEDGER = TMP / "ledger.json"           # every ledger call in this process now uses the temp file
REAL = ROOT / "probe/raw/ledger.json"
QUOTE = "we employ h = 8 parallel attention layers, or heads"
PIECES = [f"In this work {QUOTE}. For each of these we use dk = dv = dmodel/h = 64.",
          "The Transformer follows this overall architecture using stacked self-attention.",
          "We trained on the standard WMT 2014 English-German dataset."]
DRAFT = {"answer": "The base Transformer uses 8 attention heads [C1].",
         "claims": [{"chunk": "C1", "quotes": [QUOTE]}], "not_in_papers": False}


def _ok(name):
    """Print a passed test."""
    print(f"  PASS  {name}")


def sse(text, pieces=4, tokens=(100, 50)):
    """Groq-shaped SSE chunks for one reply: content deltas, a usage chunk, [DONE]."""
    n = max(1, len(text) // pieces)
    parts = [text[i:i + n] for i in range(0, len(text), n)]
    out = [f"data: {json.dumps({'choices': [{'delta': {'content': p}}]})}\n\n" for p in parts]
    out.append(f"data: {json.dumps({'choices': [], 'usage': {'prompt_tokens': tokens[0], 'completion_tokens': tokens[1]}})}\n\n")
    out.append("data: [DONE]\n\n")
    return out


class FakeStream(httpx.SyncByteStream):
    """A response body that yields one SSE chunk at a time and records how far it was read and whether it was closed."""
    def __init__(self, chunks, before_chunk=None, on_close=None, delay_s=0.0):
        self.chunks, self.before_chunk, self.on_close, self.delay_s = chunks, before_chunk, on_close, delay_s
        self.sent, self.closed = 0, False

    def __iter__(self):
        for i, c in enumerate(self.chunks):
            if self.before_chunk:
                self.before_chunk(i)
            if self.delay_s:
                time.sleep(self.delay_s)
            self.sent += 1
            yield c.encode()

    def close(self):
        self.closed = True
        if self.on_close:
            self.on_close()


def step_of(request):
    """Which pipeline step a request is, from its system prompt."""
    sys_ = json.loads(request.content)["messages"][0]["content"]
    if sys_ in (DRAFT_SYSTEM, DRAFT_SYSTEM_V2):
        return "draft"
    return "check" if sys_ in (CHECK_SYSTEM, CHECK_SYSTEM_V2) else "understand"


class FakeGroq:
    """Scripted model server: per step, a function returning a FakeStream (default: a good reply). Logs every call."""
    def __init__(self, **make):
        self.make, self.calls, self.streams = make, [], []

    def __call__(self, request):
        step = step_of(request)
        self.calls.append(step)
        default = {"understand": lambda: FakeStream(sse(json.dumps({"search_query": "Transformer attention heads"}))),
                   "draft": lambda: FakeStream(sse(json.dumps(DRAFT), pieces=8)),
                   "check": lambda: FakeStream(sse(json.dumps({"supported": True, "problems": []})))}
        s = self.make.get(step, default[step])()
        self.streams.append((step, s))
        return httpx.Response(200, stream=s, headers={"content-type": "text/event-stream"})


class FakeRetriever:
    """Three fixed pieces, a gate score well above every cutoff; no PDFs, no cross-encoder."""
    def __init__(self):
        self.chunks = [SimpleNamespace(text=t, cite=(lambda i=i: f"[Attention p.{i + 3}]")) for i, t in enumerate(PIECES)]

    def hinted_papers(self, papers):
        return []

    def search(self, query, k=None, papers=None):
        hits = [SimpleNamespace(chunk=c, bm25=10.0 - i, ce=3.0 - i) for i, c in enumerate(self.chunks)]
        return hits, 3.0, {"ce_ms": 1.0, "bm25_top": hits}


def pipeline(fake, budget=None):
    """The real Pipeline (chosen setting, default Policy) with model calls going to `fake` and the fake retriever."""
    st = SETTINGS["chosen"]
    pl = Pipeline(base_url="http://fake.invalid/v1", api_key="x", source="test", setting=st, policy=Policy(),
                  limiter=Limiter([SMALL, BIG]), cache=ExactCache(), retriever=FakeRetriever(), budget=budget)
    pl.http.close()
    pl.http = httpx.Client(transport=httpx.MockTransport(fake))
    return pl


def ctx_for(q="How many attention heads does the base Transformer use?"):
    """A fresh request context with an unset cancel flag."""
    return Ctx(rid="t", question=q, t0=time.perf_counter(), cancel=threading.Event(), deadline_ms=8000)


def gave_up_at(res):
    """Where the pipeline logged that the person gave up ('' if it didn't)."""
    return next((e.get("at", "") for e in res["events"] if e["ev"] == "gave_up"), "")


def assert_given_up(res):
    """No reply reached the person: given up, timeout, no first token, no answer text."""
    assert res["gave_up"] == 1 and res["status"] == "timeout", (res["gave_up"], res["status"])
    assert res["first_token_ms"] is None and res["answer"] == "" and res["kind"] == "", (res["first_token_ms"], res["kind"])
    assert not any(e["ev"] == "first_token" for e in res["events"])


# ------------------------------------------------------------------ stream_chat
def test_stream_cut():
    """Cancel set while the stream is read: stop, close, no partial text."""
    cancel = threading.Event()
    chunks = sse("x" * 400, pieces=20)
    s = FakeStream(chunks, before_chunk=lambda i: cancel.set() if i == 3 else None)
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, stream=s)))
    r = stream_chat([{"role": "user", "content": "q"}], SMALL, base_url="http://fake.invalid/v1", api_key="x",
                    client=client, cancel=cancel)
    assert r.error_kind == "cancelled" and r.text == "" and r.status == 200, (r.error_kind, r.text[:20], r.status)
    assert s.closed, "response stream not closed"
    assert s.sent == 4 < len(chunks), (s.sent, len(chunks))          # nothing read past the chunk where it was seen
    # cancelled before sending: no request at all
    sent = []
    client2 = httpx.Client(transport=httpx.MockTransport(lambda r: sent.append(1) or httpx.Response(200)))
    r2 = stream_chat([{"role": "user", "content": "q"}], SMALL, base_url="http://fake.invalid/v1", api_key="x",
                     client=client2, cancel=cancel)
    assert r2.error_kind == "cancelled" and r2.status == 0 and not sent
    _ok(f"stream_chat: cancel mid-stream stops after chunk {s.sent} of {len(chunks)}, closes the response, no partial "
        "text; cancel before sending sends nothing")


def test_errors_not_cancel():
    """Errors with an unset cancel flag keep their own kind."""
    cancel = threading.Event()
    c500 = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500, text="boom")))
    r = stream_chat([{"role": "user", "content": "q"}], SMALL, base_url="http://fake.invalid/v1", api_key="x",
                    client=c500, cancel=cancel)
    assert r.status == 500 and r.error_kind == "http", (r.status, r.error_kind)

    def refuse(request):
        raise httpx.ConnectError("refused", request=request)
    cnet = httpx.Client(transport=httpx.MockTransport(refuse))
    r = stream_chat([{"role": "user", "content": "q"}], SMALL, base_url="http://fake.invalid/v1", api_key="x",
                    client=cnet, cancel=cancel)
    assert r.error_kind == "network", r.error_kind
    _ok("stream_chat: HTTP 500 -> 'http', connection error -> 'network' (unset cancel flag never reads as cancelled)")


# ------------------------------------------------------------------ pipeline
def test_cancel_before_call():
    """Already given up when the pipeline starts: no model call."""
    fake = FakeGroq()
    pl, ctx = pipeline(fake), ctx_for()
    ctx.cancel.set()
    res = pl.run(ctx)
    assert_given_up(res)
    assert fake.calls == [] and res["calls"] == 0, fake.calls
    assert gave_up_at(res) == "before_call", gave_up_at(res)
    assert ctx.rid not in pl.queued_drafts
    _ok("pipeline: cancelled before the first call -> 0 model calls, given up, no reply")


def test_cancel_mid_draft():
    """Patience runs out while the draft streams."""
    holder = {}

    def draft():
        s = FakeStream(sse(json.dumps(DRAFT), pieces=12), before_chunk=lambda i: holder["ctx"].cancel.set() if i == 2 else None)
        holder["s"] = s
        return s
    fake = FakeGroq(draft=draft)
    pl, ctx = pipeline(fake), ctx_for()
    holder["ctx"] = ctx
    res = pl.run(ctx)
    assert_given_up(res)
    assert fake.calls == ["understand", "draft"], fake.calls            # no check call, no retry, no redraft
    assert holder["s"].closed and holder["s"].sent < len(holder["s"].chunks), (holder["s"].closed, holder["s"].sent)
    assert gave_up_at(res) == "stream", gave_up_at(res)
    ends = [e for e in res["events"] if e["ev"] == "call_end"]
    assert ends[-1]["step"] == "draft" and ends[-1]["err"] == "cancelled", ends[-1]
    assert res["retries"] == 0 and ctx.rid not in pl.queued_drafts
    _ok(f"pipeline: cancelled mid-draft -> stream closed after chunk {holder['s'].sent} of {len(holder['s'].chunks)}, "
        "no check call, no retry, given up, no reply")


def test_cancel_before_delivery():
    """The check passes, then the person is gone: the answer must not be sent."""
    holder = {}
    fake = FakeGroq(check=lambda: FakeStream(sse(json.dumps({"supported": True, "problems": []})),
                                             on_close=lambda: holder["ctx"].cancel.set()))
    pl, ctx = pipeline(fake), ctx_for()
    holder["ctx"] = ctx
    res = pl.run(ctx)
    assert fake.calls == ["understand", "draft", "check"], fake.calls   # generation and check both completed
    assert any(e["ev"] == "check" and e["ok"] for e in res["events"])
    assert_given_up(res)
    assert gave_up_at(res) == "before_delivery", gave_up_at(res)
    assert next(e for e in res["events"] if e["ev"] == "gave_up").get("dropped") == "answer"
    assert res["tokens_in"] == 300 and res["tokens_out"] == 150          # what it cost is still counted
    _ok("pipeline: cancelled after the check passed -> answer not delivered (no first token), given up, tokens counted")


def test_normal():
    """Nobody gives up: the normal path is unchanged."""
    fake = FakeGroq()
    pl, ctx = pipeline(fake), ctx_for()
    res = pl.run(ctx)
    assert res["kind"] == "answer" and res["status"] == "ok" and res["gave_up"] == 0, (res["kind"], res["status"])
    assert res["first_token_ms"] is not None and "8 attention heads" in res["answer"], res["answer"]
    assert fake.calls == ["understand", "draft", "check"] and res["calls"] == 3, fake.calls
    assert all(s.closed and s.sent == len(s.chunks) for _, s in fake.streams)   # read to the end, then closed
    assert gave_up_at(res) == "" and ctx.rid not in pl.queued_drafts
    _ok("pipeline: not cancelled -> answer delivered after understand, draft, check; every stream read and closed")


# ------------------------------------------------------------------ service
def test_service():
    """Through the Service: the patience timer, bookkeeping, and a request that raises."""
    from relay.service import Service
    slow = {}

    def draft():
        s = FakeStream(sse(json.dumps(DRAFT), pieces=100), delay_s=0.05)    # ~5 s if read to the end
        slow["s"] = s
        return s
    fake = FakeGroq(draft=draft)
    pl = pipeline(fake)
    svc = Service(pl, workers=1, scenario="test", events_path=TMP / "events.jsonl")
    t = time.perf_counter()
    svc.submit("patient-0", "How many attention heads does the base Transformer use?", patience_s=0.3)
    svc.wait_all(timeout=10)
    took = time.perf_counter() - t
    assert svc.pending == 0, svc.pending
    row = svc.rows[0]
    assert row["gave_up"] == 1 and row["status"] == "timeout" and row["first_token_ms"] is None, row
    assert row["reply_kind"] == "none", row["reply_kind"]
    assert slow["s"].closed and slow["s"].sent < len(slow["s"].chunks), (slow["s"].closed, slow["s"].sent)
    assert took < 3, took                                                 # stopped, not read to the end (~5 s)

    real_run = pl.run

    def run(ctx):
        if ctx.rid == "boom-1":
            raise RuntimeError("injected bug")
        return real_run(ctx)
    pl.run = run
    fake.make.pop("draft")                                                # back to the fast default draft
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        svc.submit("boom-1", "a question that hits a bug", patience_s=30)
        svc.submit("after-2", "How many attention heads does the base Transformer use, in the base model?", patience_s=30)
        svc.wait_all(timeout=10)
    assert svc.pending == 0, svc.pending
    by = {r["request_id"]: r for r in svc.rows}
    assert by["boom-1"]["status"] == "error" and by["boom-1"]["gave_up"] == 0, by["boom-1"]
    assert "RuntimeError: injected bug" in err.getvalue()
    assert by["after-2"]["status"] == "ok" and by["after-2"]["reply_kind"] == "answer", by["after-2"]
    logged = [json.loads(x) for x in (TMP / "events.jsonl").read_text().splitlines()]
    assert any(e["ev"] == "worker_error" for x in logged if x["row"]["request_id"] == "boom-1" for e in x["events"])
    _ok(f"service: patience 0.3 s fired mid-stream -> gave_up row in {took:.2f} s, stream closed; a raising request "
        "-> error row + traceback, pending 0, the same worker answered the next request")


# ------------------------------------------------------------------ accounting
def budget():
    """A real run Budget on the temporary ledger."""
    from relay.budget import Budget
    return Budget(run="test_cancellation", request_cap=50)


def ledger_calls():
    """Calls recorded in the temporary ledger."""
    return ledger.read().get("calls", []) if ledger.LEDGER.exists() else []


def test_cut_accounting():
    """A stream cut mid-draft: no refund, estimate in the pacing history and the ledger."""
    holder = {}

    def draft():
        s = FakeStream(sse(json.dumps(DRAFT), pieces=12), before_chunk=lambda i: holder["ctx"].cancel.set() if i == 2 else None)
        return s
    bud, n0 = budget(), len(ledger_calls())
    fake = FakeGroq(draft=draft)
    pl, ctx = pipeline(fake, bud), ctx_for()
    holder["ctx"] = ctx
    res = pl.run(ctx)
    assert gave_up_at(res) == "stream", gave_up_at(res)
    est_in = next(e["est_in"] for e in res["events"] if e["ev"] == "call_start" and e["step"] == "draft")
    est = est_in + 350                                                     # pipeline.DRAFT_OUT_EST
    big = pl.lim.b[BIG]
    assert big["tpm"].remaining() <= 8000 - est + 50, (big["tpm"].remaining(), est)   # reservation kept (<=50 refilled)
    assert big["tpd"].remaining() <= 200000 - est + 1, big["tpd"].remaining()
    spent = [t for _, t in pl.lim.spend[BIG]]
    assert spent == [est], (spent, est)                                    # pacing sees the cut draft's estimate
    over, cur, allowed = pl.lim.check_pacing(BIG, 300, 0.15)
    assert abs(cur - est / 300) < 1e-9, cur
    rec = ledger_calls()[n0:]
    assert [c[1] for c in rec] == [SMALL, BIG], rec                        # understand (actual) + the cut draft
    assert rec[1][2] + rec[1][3] == est, rec[1]                            # the cut draft at its estimate, not 0
    assert bud.run_sent == 2 and len(fake.calls) == 2 and not bud.inflight.get(BIG), (bud.run_sent, bud.inflight)
    _ok(f"accounting, stream cut: 120b reservation kept, {est} estimated tokens in the pacing history "
        f"(current {cur:.2f} tok/s) and in the ledger")


def test_never_sent_releases():
    """Reservations of calls that never reach the provider are given back; run_sent = requests actually sent."""
    # (a) gave up during the limiter wait, five times in a row: nothing sent, nothing kept
    bud, n0 = budget(), len(ledger_calls())
    for i in range(5):
        fake = FakeGroq()
        pl, ctx = pipeline(fake, bud), ctx_for()
        pl.lim.b[SMALL]["rpm"].used = 30.0                                # per-minute full: understand waits ~2 s
        threading.Timer(0.1, ctx.cancel.set).start()
        res = pl.run(ctx)
        assert gave_up_at(res) == "waiting" and fake.calls == [] and res["calls"] == 0, (gave_up_at(res), fake.calls)
        small = pl.lim.b[SMALL]
        assert small["rpd"].used < 1e-6 and small["tpd"].used < 1e-6, (small["rpd"].used, small["tpd"].used)
        assert small["rpm"].used <= 30.0, small["rpm"].used
    assert bud.run_sent == 0 and not bud.inflight.get(SMALL) and len(ledger_calls()) == n0, (bud.run_sent, bud.inflight)

    # (b) gave up after the wait, just before the request went out: nothing sent, nothing recorded
    fake = FakeGroq()
    pl, ctx = pipeline(fake, bud), ctx_for()
    real_note = pl.lim.note_request
    pl.lim.note_request = lambda is_retry: (real_note(is_retry), ctx.cancel.set())   # last step before stream_chat
    res = pl.run(ctx)
    assert gave_up_at(res) == "before_call" and fake.calls == [] and res["calls"] == 0, (gave_up_at(res), fake.calls, res["calls"])
    assert pl.lim.b[SMALL]["rpd"].used < 1e-6 and bud.run_sent == 0 and len(ledger_calls()) == n0
    assert next(e for e in res["events"] if e["ev"] == "call_end").get("sent") is False

    # (c) turned away by our limiter (Busy): the run budget's reservation is given back too
    fake = FakeGroq()
    pl, ctx = pipeline(fake, bud), ctx_for()
    pl.lim.b[SMALL]["rpm"].used = 1000.0                              # 20b would wait far past the deadline
    res = pl.run(ctx)
    assert "understand" not in fake.calls and "check" not in fake.calls, fake.calls
    assert bud.run_sent == len(fake.calls) == 1 and not bud.inflight.get(SMALL), (bud.run_sent, fake.calls, bud.inflight)

    # (d) a normal answer: three calls sent, three counted, nothing left in flight
    b2 = budget()
    fake = FakeGroq()
    pl, ctx = pipeline(fake, b2), ctx_for()
    res = pl.run(ctx)
    assert res["kind"] == "answer" and b2.run_sent == 3 == len(fake.calls), (res["kind"], b2.run_sent)
    assert not any(b2.inflight.get(m) for m in (SMALL, BIG)), b2.inflight
    _ok("accounting, never sent: gave up in the limiter wait (x5), just before sending, or turned away (Busy) -> "
        "run budget and limiter reservations given back; run_sent = requests sent (0, 0, 1; normal answer 3)")


def main():
    """Run every test; exit 1 on the first failure."""
    before = REAL.stat().st_mtime if REAL.exists() else None
    print(f"cancellation tests (offline, temp dir {TMP})")
    test_stream_cut()
    test_errors_not_cancel()
    test_cancel_before_call()
    test_cancel_mid_draft()
    test_cancel_before_delivery()
    test_normal()
    test_service()
    test_cut_accounting()
    test_never_sent_releases()
    assert (REAL.stat().st_mtime if REAL.exists() else None) == before, "real ledger was touched"
    print("all passed; the real ledger was not touched")


if __name__ == "__main__":
    main()
