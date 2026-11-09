#!/bin/sh
# Run the stand-in scenarios ONE AFTER ANOTHER (K: parallel runs share CPU and pollute latency).
# Full five under the AFTERNOON stand-in profile (stage 2a, n=40); burst + overload also under the
# EVENING profile (stage 2b, n=20), replacing the earlier 2%/10% slow-call repeats (K §25).
# caffeinate -i keeps the Mac awake for the whole run. Starts its own stand-in on :8099.
cd "$(dirname "$0")/.." || exit 1
PY=.venv/bin/python
# Needs: K's pool (eval/k_questions.csv), X and Y set in load/scenarios.py, deadline + cutoff set,
# and load/mix.json recomputed at the current cutoff (done here so it can't be stale).
$PY load/mix.py || exit 1
.venv/bin/uvicorn standin.server:app --port 8099 --log-level warning > raw/standin_server.log 2>&1 &
SRV=$!
trap 'kill $SRV' EXIT
sleep 4
run() { echo "=== $(date '+%H:%M:%S') $*"; caffeinate -i $PY load/loadgen.py "$@" || echo "FAILED: $*"; }
for sc in steady burst overload minute_limit_halved daily_exhausted; do run $sc --profile afternoon; done
for sc in burst overload; do run $sc --profile evening; done
# K: shadow-mode arrival check (measures false-busy) and halved limit without 429 learning
run overload --profile afternoon --arrival-check shadow --tag shadow
run minute_limit_halved --profile afternoon --no-learn --tag nolearn
echo "=== $(date '+%H:%M:%S') all done"
