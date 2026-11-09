#!/bin/sh
# Run the stand-in scenarios ONE AFTER ANOTHER (K: parallel runs share CPU and pollute latency).
# Full five at rare-delay 5%; burst + overload also at 2% and 10% (K, 2026-11-09).
# caffeinate -i keeps the Mac awake for the whole run. Starts its own stand-in on :8099.
cd "$(dirname "$0")/.." || exit 1
PY=.venv/bin/python
.venv/bin/uvicorn standin.server:app --port 8099 --log-level warning > raw/standin_server.log 2>&1 &
SRV=$!
trap 'kill $SRV' EXIT
sleep 4
run() { echo "=== $(date '+%H:%M:%S') $*"; caffeinate -i $PY load/loadgen.py "$@" || echo "FAILED: $*"; }
for sc in steady burst overload minute_limit_halved daily_exhausted; do run $sc --rare 0.05; done
for r in 0.02 0.10; do run burst --rare $r; run overload --rare $r; done
echo "=== $(date '+%H:%M:%S') all done"
