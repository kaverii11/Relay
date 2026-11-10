#!/bin/sh
# Run the stand-in scenarios ONE AFTER ANOTHER (K: parallel runs share CPU and pollute latency).
# Full five under the AFTERNOON stand-in profile (stage 2a, n=40); burst + overload also under the
# EVENING profile (stage 2b: fitted on 20b only, n=20), replacing the earlier 2%/10% slow-call repeats (K §25).
# K §38: one log file per scenario (raw/log_<scenario>_<profile>[_<tag>].txt), continue on failure,
# one summary line printed as each finishes. caffeinate -i keeps the Mac awake. Starts its own stand-in on :8099.
cd "$(dirname "$0")/.." || exit 1
PY=.venv/bin/python
# Needs: K's pool (eval/k_questions.csv), X and Y set in load/scenarios.py, deadline + cutoff set,
# load/mix.json recomputed at the current cutoff (done here so it can't be stale), and the stand-in's
# check_fail_rate set from the check replay (standin/calibration.json).
$PY load/mix.py || exit 1
mkdir -p raw
.venv/bin/uvicorn standin.server:app --port 8099 --log-level warning > raw/standin_server.log 2>&1 &
SRV=$!
trap 'kill $SRV' EXIT
sleep 4
run() {
  sc=$1; shift; prof=$2; tag=""
  for a in "$@"; do case $prev in --tag) tag="_$a";; esac; prev=$a; done
  log="raw/log_${sc}_${prof}${tag}.txt"
  echo "=== $(date '+%H:%M:%S') start $sc $* -> $log"
  if caffeinate -i $PY load/loadgen.py $sc "$@" > "$log" 2>&1; then
    echo "=== $(date '+%H:%M:%S') done  $sc $*: $(grep '] done:' "$log" | tail -1 | cut -c1-200)"
  else
    echo "=== $(date '+%H:%M:%S') FAILED $sc $* (exit $?): $(tail -1 "$log" | cut -c1-200)"
  fi
}
for sc in steady burst overload minute_limit_halved daily_exhausted; do run $sc --profile afternoon; done
for sc in burst overload; do run $sc --profile evening; done
# K: shadow-mode arrival check (measures false-busy) and halved limit without 429 learning
run overload --profile afternoon --arrival-check shadow --tag shadow
run minute_limit_halved --profile afternoon --no-learn --tag nolearn
echo "=== $(date '+%H:%M:%S') all done"
