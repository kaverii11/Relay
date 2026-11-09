"""Queue + workers around the pipeline, and the results.csv row format.

Arrivals go into a FIFO queue; `workers` threads serve them. Each person has a patience
timer: when it fires, their cancel flag is set and the pipeline stops spending tokens on them.
A request still queued at the system deadline gets the busy reply without being served.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import queue
import threading
import time
from pathlib import Path

from relay.pipeline import Ctx, Pipeline

COLUMNS = ["request_id", "scenario", "source", "start_time", "first_token_ms", "total_ms", "status",
           "retries", "tokens_in", "tokens_out", "retrieval_setting", "answer_grade",
           # extras, after the brief's 12 (DECISIONS §5)
           "service_start_ms", "gave_up", "degrade_level", "model", "calls"]


class Service:
    def __init__(self, pipeline: Pipeline, *, workers: int, scenario: str, events_path: Path):
        self.pl, self.scenario = pipeline, scenario
        self.q: queue.Queue = queue.Queue()
        self.rows, self.lock = [], threading.Lock()
        self.events_f = open(events_path, "a")
        self.pending = 0
        self.done = threading.Condition()
        for _ in range(workers):
            threading.Thread(target=self._worker, daemon=True).start()

    def submit(self, rid: str, question: str, patience_s: float):
        cancel = threading.Event()
        t0 = time.perf_counter()
        wall = dt.datetime.now(dt.timezone.utc)
        timer = threading.Timer(patience_s, cancel.set)
        timer.daemon = True
        timer.start()
        with self.done:
            self.pending += 1
        self.q.put((rid, question, t0, wall, cancel, timer, patience_s))

    def _worker(self):
        while True:
            rid, question, t0, wall, cancel, timer, patience = self.q.get()
            ctx = Ctx(rid=rid, question=question, t0=t0, cancel=cancel, deadline_ms=self.pl.p.system_deadline_ms)
            ctx.ev("arrive", patience_s=round(patience, 2))
            if cancel.is_set():                       # gave up while still queued
                ctx.ev("gave_up_in_queue")
                res = self.pl._finish(ctx, {"degrade_level": "none", "model": ""}, "timeout", gave_up=True)
            elif ctx.ms() > ctx.deadline_ms:          # waited past the deadline: busy, not served
                res = self.pl._busy(ctx, {"degrade_level": "none", "model": ""}, "queue", 5.0)
            else:
                ctx.ev("dequeued")
                res = self.pl.run(ctx)
            timer.cancel()
            self._record(rid, question, wall, res)
            with self.done:
                self.pending -= 1
                self.done.notify_all()

    def _record(self, rid, question, wall, res):
        row = {"request_id": rid, "scenario": self.scenario, "source": self.pl.source,
               "start_time": wall.isoformat(timespec="milliseconds"),
               "first_token_ms": res["first_token_ms"], "total_ms": res["total_ms"], "status": res["status"],
               "retries": res["retries"], "tokens_in": res["tokens_in"], "tokens_out": res["tokens_out"],
               "retrieval_setting": self.pl.setting.name, "answer_grade": "",
               "service_start_ms": res.get("service_start_ms"),
               "gave_up": res["gave_up"], "degrade_level": res.get("degrade_level", ""),
               "model": res.get("model", ""), "calls": res["calls"]}
        detail = {k: v for k, v in res.items() if k != "events"}
        with self.lock:
            self.rows.append(row)
            self.events_f.write(json.dumps({"row": row, "question": question, "result": detail,
                                            "events": res["events"]}) + "\n")
            self.events_f.flush()

    def wait_all(self, timeout=None):
        end = time.time() + (timeout or 1e9)
        with self.done:
            while self.pending and time.time() < end:
                self.done.wait(1)


def write_csv(rows, path: Path, append=False):
    exists = path.exists() and append
    with open(path, "a" if append else "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if not exists:
            w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in COLUMNS})
