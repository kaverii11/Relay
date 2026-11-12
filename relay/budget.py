"""Caps for REAL Groq runs that are not probes: the end-to-end sets and the eval (K §31, 2026-11-10).

The probe hard cap (probe/probe_groq.py, HARD_CAP = 300) counts probes + rewrites only. Runs that go
through the production pipeline get, instead:
  - a per-RUN request cap, printed by --plan and approved by K before --go;
  - a per-MODEL daily token ceiling: 170k of Groq's 200k TPD, over a rolling 24 h window. Groq refills
    continuously (measured for RPD, stage 1), so a rolling window is the conservative reading.
Both are checked BEFORE a request is sent. Hardening (K, 2026-11-12): calls that passed the check but haven't
reported their tokens yet count as in flight, so parallel workers can't all pass the same check at once; the ledger
is locked and written atomically (relay/ledger.py); an unreadable ledger refuses spending (fail closed). A hit raises DailyLimit(model, "budget"): the pipeline treats
it like Groq's own per-day limit (ladder to the other model, or the busy reply) and the run script stops
submitting (`stopped`).

Ledger: probe/raw/ledger.json
  {"sent": <probe counter>, "calls": [[wall_iso, model, tokens_in, tokens_out, run, status], ...]}

  .venv/bin/python -m relay.budget --show        # usage per model over the last 24 h
  .venv/bin/python -m relay.budget --backfill    # add every probe/raw/*.jsonl call not yet in the ledger
"""
from __future__ import annotations

import argparse
import datetime as dt
import itertools
import json
import threading
import time

from relay import ledger
from relay.config import BIG, SMALL
from relay.ledger import LEDGER, ROOT, LedgerCorrupt
from relay.pipeline import DailyLimit

TPD = 200_000
CEILING = 170_000          # K: stop at 170k of 200k
WINDOW_H = 24
INFLIGHT_TTL_S = 120       # a reservation never recorded (call not sent, or crashed) stops counting after this;
                           # longer than any call's timeout (draft 15 s) plus its limiter wait (<= the 8 s deadline)


def _now():
    """Current UTC time (ledger timestamps)."""
    return dt.datetime.now(dt.timezone.utc)


def _read():
    """The ledger file as a dict (empty if it doesn't exist yet; LedgerCorrupt if it can't be parsed)."""
    return ledger.read()


def usage_24h(d=None, now=None):
    """{model: {"requests", "in", "out", "tokens"}} over the last WINDOW_H hours."""
    d = _read() if d is None else d
    now = now or _now()
    out = {m: {"requests": 0, "in": 0, "out": 0, "tokens": 0} for m in (SMALL, BIG)}
    for wall, model, tin, tout, *_ in d.get("calls", []):
        if (now - dt.datetime.fromisoformat(wall)).total_seconds() > WINDOW_H * 3600:
            continue
        u = out.setdefault(model, {"requests": 0, "in": 0, "out": 0, "tokens": 0})
        u["requests"] += 1
        u["in"] += tin or 0
        u["out"] += tout or 0
        u["tokens"] += (tin or 0) + (tout or 0)
    return out


class Budget:
    """Safety caps for one real run: a request cap, and the per-model 24 h token ceiling (170k of 200k)."""
    def __init__(self, run: str, request_cap: int, ceiling: int = CEILING):
        self.run, self.request_cap, self.ceiling = run, request_cap, ceiling
        self.run_sent, self.stopped = 0, None
        self.lock = threading.Lock()
        # check-then-act fix: estimates of calls that passed reserve() but haven't been recorded yet, per model:
        # {reservation id: (monotonic time, tokens)}. Without this, 16 workers reading the ledger at the same moment
        # would all see the same headroom and all pass. Each call removes ITS OWN entry by id (record / release), so
        # calls finishing out of order can't remove another call's larger reservation and under-count what is in flight.
        self.inflight: dict[str, dict[int, tuple[float, int]]] = {}
        self._ids = itertools.count(1)

    def _inflight(self, model) -> int:
        """Tokens reserved but not yet recorded for this model (stale reservations dropped)."""
        now = time.monotonic()
        live = {i: x for i, x in self.inflight.get(model, {}).items() if now - x[0] < INFLIGHT_TTL_S}
        self.inflight[model] = live
        return sum(t for _, t in live.values())

    def _drop(self, model, res_id):
        """Remove one in-flight reservation: by id; without an id (older callers), the oldest one. Caller holds the lock."""
        live = self.inflight.get(model, {})
        if res_id is None:
            res_id = next(iter(live), None)        # insertion order = oldest first
        live.pop(res_id, None)

    def reserve(self, model, est_in, est_out) -> int:
        """Before a real call: refuse (DailyLimit) if the run cap or the 24 h ceiling would be passed,
        counting calls still in flight. An unreadable ledger refuses too (fail closed). Returns the reservation id,
        which the caller passes back to record() or release()."""
        with self.lock:
            if self.run_sent >= self.request_cap:
                self.stopped = self.stopped or f"run request cap {self.request_cap} reached"
                raise DailyLimit(model, "budget")
            try:
                used = usage_24h()[model]["tokens"]
            except LedgerCorrupt as e:
                self.stopped = self.stopped or str(e)
                raise DailyLimit(model, "budget") from e
            pending = self._inflight(model)
            if used + pending + est_in + est_out > self.ceiling:
                self.stopped = self.stopped or (f"{model}: {used} tokens in the last 24 h + {pending} in flight "
                                                f"+ ~{est_in + est_out} would pass the {self.ceiling} ceiling")
                raise DailyLimit(model, "budget")
            self.run_sent += 1
            res_id = next(self._ids)
            self.inflight.setdefault(model, {})[res_id] = (time.monotonic(), est_in + est_out)
            return res_id

    def release(self, model, res_id):
        """A reserved call never reached the provider (cancelled while waiting, cancelled before sending, or turned
        away by our limiter): undo reserve(), so it uses up neither the run's request cap nor in-flight headroom."""
        with self.lock:
            self.run_sent = max(0, self.run_sent - 1)
            self._drop(model, res_id)

    def record(self, model, tokens_in, tokens_out, status, res_id=None):
        """After a real call: append it to the ledger (locked, atomic) and release ITS in-flight reservation."""
        with self.lock:
            self._drop(model, res_id)
            with ledger.locked():
                d = _read()
                d.setdefault("calls", []).append([_now().isoformat(timespec="seconds"), model,
                                                  tokens_in or 0, tokens_out or 0, self.run, status])
                ledger.write(d)


def backfill():
    """Add probe/raw/*.jsonl calls (probes, rewrites) to the ledger so the 24 h window counts them."""
    with ledger.locked():
        return _backfill()


def _backfill():
    """backfill() body, run under the ledger lock."""
    d = _read()
    calls = d.setdefault("calls", [])
    seen = {tuple(c[:4]) for c in calls}
    added = 0
    for f in sorted((ROOT / "probe/raw").glob("*.jsonl")):
        for line in open(f):
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "tokens_in" not in r or "wall" not in r:
                continue
            model = r.get("model") or (SMALL if r.get("tag") == "rewrite" else None)
            if not model:
                continue
            wall = dt.datetime.fromisoformat(r["wall"]).astimezone(dt.timezone.utc).isoformat(timespec="seconds")
            key = (wall, model, r.get("tokens_in") or 0, r.get("tokens_out") or 0)
            if key in seen:
                continue
            seen.add(key)
            calls.append([*key, f.stem, r.get("status")])
            added += 1
    calls.sort()
    ledger.write(d)
    return added


def show():
    """Print the ledger: probe counter and last-24 h tokens per model."""
    d = _read()
    u = usage_24h(d)
    print(f"ledger {LEDGER.relative_to(ROOT)}: probe counter {d.get('sent', 0)}/300; "
          f"{len(d.get('calls', []))} calls recorded; last {WINDOW_H} h per model (ceiling {CEILING} of {TPD} TPD):")
    for m, x in u.items():
        print(f"  {m:22s} requests {x['requests']:4d}  tokens {x['tokens']:7d} (in {x['in']}, out {x['out']})"
              f"  headroom {CEILING - x['tokens']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--backfill", action="store_true")
    a = ap.parse_args()
    if a.backfill:
        print(f"backfilled {backfill()} calls")
    show()
