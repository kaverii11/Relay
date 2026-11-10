"""One summary per scenario of a run_all.sh night (K, 2026-11-11 item 6). No Groq, no re-runs.

  .venv/bin/python analysis/run_all_summary.py raw/run_all_20261110.txt

Reads the run_all transcript (start / done / FAILED lines), each scenario's log (arrivals line, tracebacks)
and its results csv. Per scenario: n rows, status counts, reply kinds, first-token p50 / p95, peak waiting
(analysis.tables.peak_queue: requests waiting for service or for a draft slot at the same instant).
Flags anything that failed or looks wrong: FAILED, rows != arrivals, a traceback in the log, replies of
kind none, gave-ups, or a first-token p95 over the deadline.
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis.tables import f, pcts, peak_queue  # noqa: E402
from relay.config import Policy  # noqa: E402


def main(path):
    txt = Path(path).read_text()
    starts = re.findall(r"=== (\d\d:\d\d:\d\d) start (\S+) (.*?) -> (\S+)", txt)
    deadline = Policy().system_deadline_ms
    print(f"| scenario | profile / tag | n rows (arrivals) | status | reply kinds | first token p50 / p95 ms | "
          f"peak waiting | flags |\n|---|---|---|---|---|---|---|---|")
    for t, sc, args, log in starts:
        logp = ROOT / log
        flags = []
        if re.search(rf"=== \S+ FAILED {re.escape(sc)} {re.escape(args)}", txt):
            flags.append("FAILED")
        if not logp.exists():
            print(f"| {sc} | {args} | - | - | - | - | - | no log |")
            continue
        lt = logp.read_text()
        if "Traceback" in lt:
            flags.append("traceback in log")
        m = re.search(r"\[(\S+)\] (\d+) arrivals", lt)
        run, arrivals = (m.group(1), int(m.group(2))) if m else (None, None)
        csvp = ROOT / f"raw/results_{run}.csv" if run else None
        if not csvp or not csvp.exists():
            print(f"| {sc} | {args} | 0 ({arrivals}) | - | - | - | - | {', '.join(flags + ['no results csv'])} |")
            continue
        rows = list(csv.DictReader(open(csvp)))
        n = len(rows)
        if arrivals is not None and n != arrivals:
            flags.append(f"rows {n} != arrivals {arrivals}")
        st_ = {}
        for r in rows:
            st_[r["status"]] = st_.get(r["status"], 0) + 1
        kinds = {}
        for r in rows:
            kinds[r["reply_kind"]] = kinds.get(r["reply_kind"], 0) + 1
        if kinds.get("none"):
            flags.append(f"{kinds['none']} replies of kind none")
        gave = sum(r["gave_up"] in ("1", "True") for r in rows)
        if gave:
            flags.append(f"{gave} gave up")
        ft = [f(r["first_token_ms"]) for r in rows if r["reply_kind"] in ("answer", "refusal")]
        p = pcts(ft, ps=(50, 95)) if ft else "n=0"
        if ft:
            s = sorted(x for x in ft if x is not None)
            if s and s[min(len(s) - 1, int(0.95 * len(s)))] > deadline:
                flags.append(f"first-token p95 over the {deadline:.0f} ms deadline")
        pk = peak_queue(rows)
        print(f"| {sc} | {args} | {n} ({arrivals}) | {', '.join(f'{k} {v}' for k, v in sorted(st_.items()))} | "
              f"{', '.join(f'{k} {v}' for k, v in sorted(kinds.items()))} | {p} | {pk} | {', '.join(flags) or '-'} |")
    if "all done" not in txt:
        print("\nrun_all.sh has NOT printed 'all done' (still running or killed).")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "raw/run_all_20261110.txt")
