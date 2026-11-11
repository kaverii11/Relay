"""Relabel ALREADY-MEASURED result rows from their event logs (K, 2026-11-11 §44: no re-runs). Two labels:

1. reply_kind "unverified": rows whose check failed again after the one redraft. Before §44 the pipeline sent
   them as a "the papers don't say" refusal (refuse_reason "unverified"); K made them their own reply kind.
   The events line of every request keeps `result.refuse_reason`, so the relabel is exact.
2. daily_phase "before" | "after": whether, when the request arrived, the 120b day budget had stopped serving
   drafts. The instant T is the earliest event in the run of: ladder_skip (why daily_reserve), ladder to
   small_model (why tpd / rpd), busy (limit tpd / rpd), arrival_check (why daily). Rows arriving at or after
   T are "after". Runs with no such event are all "before".

  .venv/bin/python scripts/relabel_from_events.py raw/results_*.csv

Writes each csv in place (the first time, a copy is kept as <name>.orig.csv) and prints what changed. The
numbers in the rows (latencies, tokens, status) are untouched: this is a label, not a re-measurement.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from relay.service import COLUMNS  # noqa: E402


def exhaustion_instant(lines):
    """When the 120b day budget stopped serving drafts in a run (reserve or 429), from its events."""
    best = None
    for ln in lines:
        t0 = dt.datetime.fromisoformat(ln["row"]["start_time"]).timestamp()
        for e in ln["events"]:
            hit = ((e["ev"] == "ladder_skip" and e.get("why") == "daily_reserve")
                   or (e["ev"] == "ladder" and e.get("to") == "small_model" and e.get("why") in ("tpd", "rpd"))
                   or (e["ev"] == "busy" and e.get("limit") in ("tpd", "rpd"))
                   or (e["ev"] == "arrival_check" and e.get("why") == "daily"))
            if hit:
                t = t0 + e.get("t_ms", 0) / 1000
                best = t if best is None or t < best else best
                break
    return best


def main(paths):
    """Fill the daily_phase column (before / after) of each run's results from its event log."""
    for p in map(Path, paths):
        if ".orig." in p.name:
            continue
        run = p.name[len("results_"):-len(".csv")]
        ev_path = p.with_name(f"events_{run}.jsonl")
        if not ev_path.exists():
            print(f"{p.name}: no events file, skipped")
            continue
        lines = [json.loads(l) for l in ev_path.read_text().splitlines() if l.strip()]
        by_id = {ln["row"]["request_id"]: ln for ln in lines}
        T = exhaustion_instant(lines)
        rows = list(csv.DictReader(open(p)))
        orig = p.with_name(p.stem + ".orig.csv")
        if not orig.exists():
            shutil.copy(p, orig)
        n_unv = n_after = 0
        for r in rows:
            ln = by_id.get(r["request_id"])
            if ln and ln["result"].get("refuse_reason") == "unverified" and r["reply_kind"] == "refusal":
                r["reply_kind"] = "unverified"
                n_unv += 1
            t = dt.datetime.fromisoformat(r["start_time"]).timestamp()
            r["daily_phase"] = "after" if T is not None and t >= T else "before"
            n_after += r["daily_phase"] == "after"
        with open(p, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in COLUMNS})
        tt = "-" if T is None else dt.datetime.fromtimestamp(T).strftime("%H:%M:%S")
        print(f"{p.name}: {len(rows)} rows; refusal->unverified {n_unv}; 120b day stopped serving drafts at {tt} "
              f"(local); rows after: {n_after}")


if __name__ == "__main__":
    main(sys.argv[1:] or sorted(str(x) for x in (ROOT / "raw").glob("results_*.csv")))
