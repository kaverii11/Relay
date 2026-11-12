"""Queue + workers around the pipeline, and the results.csv row format.

Arrivals go into a FIFO queue; `workers` threads serve them. Each person has a patience
timer: when it fires, their cancel flag is set: a model stream in progress is closed, no new call, retry or redraft
starts, and no reply is sent to them afterwards (the row is gave_up = 1, status timeout).
A request still queued at the system deadline gets the busy reply without being served.
Load shedding (K, 2026-11-12, hardening): with max_queue set, an arrival that finds that many requests already
waiting gets the busy reply at once (busy_path "shed") instead of joining a queue it can't get through in time.
None (the default, and every measured run) = unbounded, as Tables 2a/2b were measured.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import queue
import threading
import time
import traceback
from pathlib import Path

from relay.pipeline import Ctx, Pipeline

COLUMNS = ["request_id", "scenario", "source", "start_time", "first_token_ms", "total_ms", "status",
           "retries", "tokens_in", "tokens_out", "retrieval_setting", "answer_grade",
           # extras, after the brief's 12 (DECISIONS §5)
           "service_start_ms", "gave_up", "degrade_level", "model", "calls",
           "tokens_in_120b", "tokens_out_120b", "tokens_in_20b", "tokens_out_20b", "rerank_ms",
           "limiter_wait_ms", "tokens_cached",   # K §41: our limiter's waits (Table 3 excludes them); Groq cached prompt tokens
           "reply_kind",   # answer | refusal | unverified (K §44: check failed twice) | busy | rejected (input guard) | none (gave up / error)
           "draft_ready_ms", "draft_sent_ms", "arrival_pred_draft_sent_ms", "arrival_busy_pred", "busy_path",
           "daily_phase",       # K §44: before | after the 120b day budget stopped serving drafts (reserve reached / per-day 429)
           "run_variant",       # "" = main run; else e.g. shadow / nolearn / evening (tables group by it)
           "standin_profile"]   # stand-in latency profile, with its n; "" for real Groq


class Service:
    """Runs the pipeline for many people at once: a queue, worker threads, patience timers, CSV rows."""
    def __init__(self, pipeline: Pipeline, *, workers: int, scenario: str, events_path: Path,
                 variant: str = "", profile: str = "", max_queue: int | None = None):
        self.pl, self.scenario, self.variant, self.profile = pipeline, scenario, variant, profile
        self.max_queue = max_queue
        self.q: queue.Queue = queue.Queue()
        self.rows, self.lock = [], threading.Lock()
        self.events_f = open(events_path, "a")
        self.pending = 0
        self.done = threading.Condition()
        for _ in range(workers):
            threading.Thread(target=self._worker, daemon=True).start()

    def submit(self, rid: str, question: str, patience_s: float):
        """A person asks: start their patience timer and queue the request."""
        cancel = threading.Event()
        t0 = time.perf_counter()
        wall = dt.datetime.now(dt.timezone.utc)
        if self.max_queue is not None and self.q.qsize() >= self.max_queue:     # shed: answer busy right away
            ctx = Ctx(rid=rid, question=question, t0=t0, cancel=cancel, deadline_ms=self.pl.p.system_deadline_ms)
            ctx.ev("arrive", patience_s=round(patience_s, 2))
            ctx.ev("shed", queued=self.q.qsize(), max_queue=self.max_queue)
            res = self.pl._busy(ctx, {"degrade_level": "none", "model": ""}, "queue", 5.0, path="shed")
            self._record(rid, question, wall, res)
            return
        timer = threading.Timer(patience_s, cancel.set)
        timer.daemon = True
        timer.start()
        with self.done:
            self.pending += 1
        self.q.put((rid, question, t0, wall, cancel, timer, patience_s))

    def _worker(self):
        """Worker thread: take the next request, run the pipeline, record the row."""
        while True:
            rid, question, t0, wall, cancel, timer, patience = self.q.get()
            ctx = None
            try:
                ctx = Ctx(rid=rid, question=question, t0=t0, cancel=cancel, deadline_ms=self.pl.p.system_deadline_ms)
                ctx.ev("arrive", patience_s=round(patience, 2))
                if cancel.is_set():                       # gave up while still queued
                    ctx.ev("gave_up_in_queue")
                    res = self.pl._finish(ctx, {"degrade_level": "none", "model": ""}, "timeout", gave_up=True)
                elif ctx.ms() > ctx.deadline_ms:          # waited past the deadline: busy, not served
                    res = self.pl._busy(ctx, {"degrade_level": "none", "model": ""}, "queue", 5.0, path="queue")
                else:
                    ctx.ev("dequeued")
                    res = self.pl.run(ctx)
                self._record(rid, question, wall, res)
            except Exception as e:    # noqa: BLE001 - a bug in one request must not kill this worker or hang wait_all
                traceback.print_exc()                     # reported, not hidden: stderr + an error row with the exception
                try:
                    ctx = ctx or Ctx(rid=rid, question=question, t0=t0, cancel=cancel,
                                     deadline_ms=self.pl.p.system_deadline_ms)
                    ctx.ev("worker_error", error=repr(e)[:500])
                    self._record(rid, question, wall, self.pl._finish(ctx, {"degrade_level": "none", "model": ""}, "error"))
                except Exception:   # noqa: BLE001
                    traceback.print_exc()
            finally:
                timer.cancel()
                with self.done:
                    self.pending -= 1
                    self.done.notify_all()

    def _record(self, rid, question, wall, res):
        """Turn one pipeline result into a results.csv row (and its event-log line)."""
        row = {"request_id": rid, "scenario": self.scenario, "source": self.pl.source,
               "start_time": wall.isoformat(timespec="milliseconds"),
               "first_token_ms": res["first_token_ms"], "total_ms": res["total_ms"], "status": res["status"],
               "retries": res["retries"], "tokens_in": res["tokens_in"], "tokens_out": res["tokens_out"],
               "retrieval_setting": self.pl.setting.name, "answer_grade": "",
               "service_start_ms": res.get("service_start_ms"),
               "gave_up": res["gave_up"], "degrade_level": res.get("degrade_level", ""),
               "model": res.get("model", ""), "calls": res["calls"],
               "tokens_in_120b": res.get("by_model", {}).get("openai/gpt-oss-120b", [0, 0])[0],
               "tokens_out_120b": res.get("by_model", {}).get("openai/gpt-oss-120b", [0, 0])[1],
               "tokens_in_20b": res.get("by_model", {}).get("openai/gpt-oss-20b", [0, 0])[0],
               "tokens_out_20b": res.get("by_model", {}).get("openai/gpt-oss-20b", [0, 0])[1],
               "rerank_ms": res.get("rerank_ms"),
               "limiter_wait_ms": res.get("limiter_wait_ms"), "tokens_cached": res.get("tokens_cached"),
               "reply_kind": res.get("kind") or "none",
               **{k: res.get(k) for k in ("draft_ready_ms", "draft_sent_ms", "arrival_pred_draft_sent_ms",
                                          "arrival_busy_pred", "busy_path", "daily_phase")},
               "run_variant": self.variant, "standin_profile": self.profile}
        detail = {k: v for k, v in res.items() if k != "events"}
        with self.lock:
            self.rows.append(row)
            self.events_f.write(json.dumps({"row": row, "question": question, "result": detail,
                                            "events": res["events"]}) + "\n")
            self.events_f.flush()

    def wait_all(self, timeout=None):
        """Block until every submitted request has finished (or the timeout)."""
        end = time.time() + (timeout or 1e9)
        with self.done:
            while self.pending and time.time() < end:
                self.done.wait(1)


def write_csv(rows, path: Path, append=False):
    """Write rows with the results.csv columns."""
    exists = path.exists() and append
    with open(path, "a" if append else "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if not exists:
            w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in COLUMNS})
