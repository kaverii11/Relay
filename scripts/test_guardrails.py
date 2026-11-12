"""Offline tests for the hardening guardrails (K, 2026-11-12). No Groq, no stand-in, no tokens.

  .venv/bin/python scripts/test_guardrails.py

  1. input guard: empty / control characters / over-long questions; the longest real question passes
  2. pipeline: a rejected question gets the fixed reply with zero model calls and zero tokens
  3. cache: bounded, least-recently-used entry evicted first
  4. budget, threads: 16 workers reserving at the same moment can't all pass the same headroom
  5. budget, processes: 4 processes recording at once lose no ledger entries (lock + atomic write)
  6. budget, corrupt ledger: spending is refused (fail closed), not treated as "nothing used"
  7. service: with max_queue, arrivals beyond it get the busy reply at once (load shedding)
  8. tables: input-guard rejections are counted apart, not in latency percentiles or Succeeded %
Each test uses its own temporary ledger; the real probe/raw/ledger.json is never touched.
"""
from __future__ import annotations

import multiprocessing as mp
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from relay import ledger  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="relay_guard_"))
ledger.LEDGER = TMP / "ledger.json"           # every ledger call in this process now uses the temp file
REAL = ROOT / "probe/raw/ledger.json"


def _ok(name):
    """Print a passed test."""
    print(f"  PASS  {name}")


def test_guard():
    """Input guard rules."""
    from relay.guard import MAX_QUESTION_CHARS, check_question
    assert check_question("")[1] == "empty"
    assert check_question("   \n ")[1] == "empty"
    assert check_question(None)[1] == "empty"
    q, why = check_question("How many\x00 heads\x1b?")
    assert why is None and q == "How many heads?", q
    assert check_question("x" * (MAX_QUESTION_CHARS + 1))[1].startswith("too_long")
    assert check_question("x" * MAX_QUESTION_CHARS)[1] is None
    _ok("input guard: empty, control characters stripped, length cap")


def _pipeline():
    """A pipeline pointed at a closed port: any model call would fail loudly, so 0 calls proves none was made."""
    from relay.config import SETTINGS, SMALL, BIG, Policy
    from relay.limiter import Limiter
    from relay.pipeline import ExactCache, Pipeline
    from relay.retrieval import Retriever
    st = SETTINGS["chosen"]
    return Pipeline(base_url="http://127.0.0.1:9/v1", api_key="x", source="test", setting=st, policy=Policy(),
                    limiter=Limiter([SMALL, BIG]), cache=ExactCache(), retriever=Retriever(st))


def test_reject(pl):
    """A rejected question costs nothing."""
    from relay.pipeline import Ctx
    for q in ("", "why? " * 400):
        ctx = Ctx(rid="t", question=q, t0=time.perf_counter(), cancel=threading.Event(), deadline_ms=8000)
        res = pl.run(ctx)
        assert res["kind"] == "rejected" and res["status"] == "ok", (res["kind"], res["status"])   # brief enum
        assert res["calls"] == 0 and res["tokens_in"] == 0 and res["tokens_out"] == 0
    _ok("pipeline: rejected questions get the fixed reply, 0 model calls, 0 tokens")


def test_cache():
    """LRU bound."""
    from relay.pipeline import ExactCache
    c = ExactCache(max_entries=2)
    c.put("a", "s", 1)
    c.put("b", "s", 2)
    c.get("a", "s")                    # a is now the most recently used
    c.put("c", "s", 3)                 # evicts b
    assert c.get("a", "s") == 1 and c.get("b", "s") is None and c.get("c", "s") == 3
    _ok("cache: bounded at max_entries, least recently used evicted first")


def test_budget_threads():
    """Check-then-act race: 16 simultaneous reservations of 1,000 against 10,000 of headroom."""
    from relay.budget import Budget
    from relay.config import BIG
    from relay.pipeline import DailyLimit
    ledger.write({"calls": []})
    b = Budget("t", request_cap=100, ceiling=10_000)
    passed, go = [], threading.Barrier(16)

    def one():
        """One worker: wait for the others, then try to reserve."""
        go.wait()                      # all 16 arrive together
        try:
            b.reserve(BIG, 900, 100)
            passed.append(1)
        except DailyLimit:
            pass
    ts = [threading.Thread(target=one) for _ in range(16)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(passed) == 10, len(passed)
    for _ in range(10):                # recording releases the reservations; the ledger now holds the real use
        b.record(BIG, 900, 100, 200)
    assert b._inflight(BIG) == 0
    try:
        b.reserve(BIG, 1, 1)
        raise AssertionError("ceiling not enforced after recording")
    except DailyLimit:
        pass
    _ok("budget: 16 simultaneous reservations, exactly 10 fit the 10,000 headroom (in-flight counted)")


def _proc_record(path, n):
    """Child process: record n calls into the shared temp ledger."""
    from relay import ledger as lg
    lg.LEDGER = Path(path)
    from relay.budget import Budget
    from relay.config import SMALL
    b = Budget("p", request_cap=10_000, ceiling=10**9)
    for _ in range(n):
        b.record(SMALL, 1, 1, 200)


def test_budget_processes():
    """Lost updates across processes: 4 x 50 records must give 200 entries."""
    ledger.write({"calls": []})
    ctx = mp.get_context("spawn")
    ps = [ctx.Process(target=_proc_record, args=(str(ledger.LEDGER), 50)) for _ in range(4)]
    [p.start() for p in ps]
    [p.join() for p in ps]
    n = len(ledger.read()["calls"])
    assert n == 200, n
    _ok("ledger: 4 processes x 50 records at once, 200 entries kept (none lost)")


def test_budget_corrupt():
    """Fail closed on an unreadable ledger."""
    from relay.budget import Budget
    from relay.config import BIG
    from relay.pipeline import DailyLimit
    ledger.LEDGER.write_text('{"calls": [["2026-11-12T')     # a half-written file, as a crash would leave
    b = Budget("t", request_cap=10)
    try:
        b.reserve(BIG, 1, 1)
        raise AssertionError("spent against a corrupt ledger")
    except DailyLimit:
        assert "not valid JSON" in (b.stopped or "")
    _ok("budget: corrupt ledger refuses spending (fail closed) and says why")


def test_shed(pl):
    """Load shedding at the queue."""
    from relay.service import Service
    svc = Service(pl, workers=0, scenario="test", events_path=TMP / "ev.jsonl", max_queue=2)
    for i in range(5):                 # no workers: the first 2 wait in the queue, the other 3 are shed
        svc.submit(f"r{i}", "How many heads?", 60.0)
    assert len(svc.rows) == 3 and all(r["reply_kind"] == "busy" and r["busy_path"] == "shed" for r in svc.rows)
    assert svc.q.qsize() == 2
    _ok("service: max_queue=2, 3 of 5 arrivals shed with the busy reply, 2 queued")


def _table_rows(text, title, label):
    """The cells of the row starting with `label` in the table printed under `title` (analysis/tables.py output)."""
    part = text.split(title, 1)[1]
    for line in part.splitlines()[1:]:
        if line.startswith("| " + label):
            return [c.strip() for c in line.strip("|").split("|")]
        if line and not line.startswith("|"):
            break
    raise AssertionError(f"no row {label!r} under {title!r}")


def test_tables():
    """analysis/tables.py: rejected rows are out of the latency percentiles and Succeeded %, and counted apart.
    Real rows from results.csv (steady stand-in run + the eval), plus 6 synthetic rejections copied from them."""
    import contextlib
    import csv
    import io
    from analysis import tables
    rows = list(csv.DictReader(open(ROOT / "results.csv")))
    base = [r for r in rows if (r["scenario"], r["run_variant"]) in (("steady", ""), ("eval", "day1"))]
    steady = [r for r in base if r["scenario"] == "steady" and r["daily_phase"] == "before"]   # one table row
    ev = [r for r in base if r["scenario"] == "eval" and r["retrieval_setting"] == "w250_k3_rr0"]
    fake = [{**r, "request_id": r["request_id"] + "-rej", "status": "ok", "reply_kind": "rejected", "first_token_ms": "0.1",
             "total_ms": "0.1", "tokens_in": "0", "tokens_out": "0", "retries": "0", "calls": "0"}
            for r in steady[:4] + ev[:2]]

    def run(rs):
        """tables.main on these rows; its printed output."""
        path = TMP / f"t{len(rs)}.csv"
        with open(path, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rs)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            tables.main(str(path))
        return out.getvalue()
    before, after = run(base), run(base + fake)
    lab = "steady (before 120b day budget gone)"
    a0, a1 = _table_rows(before, "Table 2a", lab), _table_rows(after, "Table 2a", lab)
    assert a1[3] == str(len(steady) + 4), a1[3]                          # requests sent: every row counts
    assert a0[6:9] == a1[6:9], (a0[6:9], a1[6:9])                        # first token, total, busy: unchanged
    b0, b1 = _table_rows(before, "Table 2b", lab), _table_rows(after, "Table 2b", lab)
    ok = sum(r["status"] == "ok" for r in steady)
    assert b1[1] == f"{100 * ok / (len(steady) + 4):.1f}", (b1[1], ok)   # Succeeded % excludes the 4 rejections
    assert b0[1] == f"{100 * ok / len(steady):.1f}"
    t0, t1 = _table_rows(before, "Table 3", "w250_k3_rr0"), _table_rows(after, "Table 3", "w250_k3_rr0")
    assert t0[9:11] == t1[9:11], (t0[9:11], t1[9:11])                    # Table 3 first token / total: unchanged
    line = [x for x in after.splitlines() if x.startswith("Rejected by the input guard")][0]
    assert f"4 of {len(steady) + 4}" in line and "eval" in line, line
    assert "none in any scenario" in [x for x in before.splitlines() if x.startswith("Rejected by")][0]
    _ok("tables: rejected rows counted apart, out of latency percentiles and Succeeded % (Tables 2a, 2b, 3)")


def main():
    """Run every test; exit 1 on the first failure."""
    before = REAL.stat().st_mtime if REAL.exists() else None
    print(f"guardrail tests (temp ledger {ledger.LEDGER})")
    test_guard()
    test_cache()
    test_budget_threads()
    test_budget_processes()
    test_budget_corrupt()
    pl = _pipeline()
    test_reject(pl)
    test_shed(pl)
    test_tables()
    assert (REAL.stat().st_mtime if REAL.exists() else None) == before, "real ledger was touched"
    print("all passed; the real ledger was not touched")


if __name__ == "__main__":
    main()
