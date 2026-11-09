"""How good is the arrival-time busy prediction? Reads results.csv-format rows only.

  .venv/bin/python analysis/arrival_check.py raw/results_<run>.csv [...]

- Prediction error (served requests that reached the draft): draft_sent_ms - arrival_pred_draft_sent_ms.
  Positive = the draft went out LATER than predicted (prediction optimistic).
- Shadow runs (everyone admitted): false-busy = predicted busy (arrival_busy_pred=1) but the person
  got a drafted answer anyway (status ok, reply_kind answer). Missed-busy = predicted OK but the
  person ended without an answer (busy reply later on, timeout or gave up).
  In non-shadow runs, predicted-busy people were turned away, so false-busy can't be observed.
"""
import csv
import sys

import numpy as np

for path in sys.argv[1:]:
    rows = list(csv.DictReader(open(path)))
    f = lambda x: None if x in ("", None) else float(x)  # noqa: E731
    err = [f(r["draft_sent_ms"]) - f(r["arrival_pred_draft_sent_ms"]) for r in rows
           if f(r["draft_sent_ms"]) is not None and f(r["arrival_pred_draft_sent_ms"]) is not None]
    pred = [r for r in rows if r["arrival_busy_pred"] not in ("", None)]
    pb = [r for r in pred if r["arrival_busy_pred"] == "1"]
    pn = [r for r in pred if r["arrival_busy_pred"] == "0"]
    got = lambda r: r["status"] == "ok" and r["reply_kind"] == "answer"  # noqa: E731
    none = lambda r: r["reply_kind"] in ("busy", "none") or r["status"] in ("timeout", "rate_limited", "error")  # noqa: E731
    paths = {}
    for r in rows:
        if r["busy_path"]:
            paths[r["busy_path"]] = paths.get(r["busy_path"], 0) + 1
    print(f"\n{path}\n  rows={len(rows)} checked={len(pred)} predicted_busy={len(pb)} busy replies by path={paths}")
    if err:
        e = np.array(err)
        print(f"  draft-sent prediction error ms (actual - predicted), n={len(e)}: "
              f"median {np.median(e):.0f}, p5 {np.percentile(e, 5):.0f}, p95 {np.percentile(e, 95):.0f}, "
              f"|err| median {np.median(np.abs(e)):.0f}")
    if pb:
        fb = sum(got(r) for r in pb)
        print(f"  false-busy (predicted busy, got a drafted answer): {fb}/{len(pb)} = {100 * fb / len(pb):.1f}%"
              "  [meaningful only in SHADOW runs]")
    if pn:
        mb = sum(none(r) for r in pn)
        print(f"  missed-busy (predicted OK, ended with no answer): {mb}/{len(pn)} = {100 * mb / len(pn):.1f}%")
