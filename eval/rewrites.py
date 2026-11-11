"""Real 20b rewrites of K's questions (K §24), so the gate cutoff is tuned on what production scores.

  .venv/bin/python eval/rewrites.py --plan       # what would be sent (no requests)
  .venv/bin/python eval/rewrites.py --go         # send to real Groq (K approves the --plan first)
  .venv/bin/python eval/rewrites.py --go --base-url http://127.0.0.1:8099/v1   # dry run on the stand-in

Exactly the production understand call: same prompt (relay.prompts.understand_messages), model
gpt-oss-20b, temperature 0, reasoning_effort = Policy.reasoning_effort, max_tokens 400.
Also ~5 "Quick question:"-style WORDING PROBES of K's TUNING questions (assistant-written; not eval, not
tuning, not the load pool), to measure how much the rewrite undoes casual wording.

Stores eval/rewrites_20b.json, keyed by textnorm.match_key(question). The stand-in replays the
stored rewrite text for these questions (standin/server.py). Counts against the probe ledger
(probe/raw/ledger.json, hard cap 300). Paced at one call per --gap seconds; a per-minute 429 is
waited out once (retry-after); a per-day 429 stops the run.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from load.mix import POOL_PATH, load_pool  # noqa: E402
from relay.config import SMALL, Policy  # noqa: E402
from relay.llm import stream_chat  # noqa: E402
from relay.pipeline import parse_json  # noqa: E402
from relay.prompts import understand_messages  # noqa: E402
from relay.textnorm import match_key  # noqa: E402

OUT = ROOT / "eval/rewrites_20b.json"
# Casual framings for the wording probes (assistant-written). One each, on 5 seeded picks.
# All are prefixes ending in ":" so they never clash with how K's question starts.
FRAMINGS = ["Quick question: {q}", "Hey, sorry if this is basic: {q}", "Question for you: {q}",
            "I was reading the papers and wondered: {q}", "Not sure where to look for this: {q}"]
# Measured per-call size of the real understand call (stage 1 + 2a, 20b): ~415 in, ~98 out.
EST_IN, EST_OUT = 415, 105


def lower_first(q):
    """Lower-case the first letter (for wording probes), unless it starts an acronym."""
    return q[0].lower() + q[1:] if q and not q[:2].isupper() else q


def items(pool, n_probe, seed, sets=("eval", "tuning")):
    """What to rewrite: every question, plus seeded wording probes from tuning questions."""
    if any(not p["set"] for p in pool):
        sys.exit("set is blank: run eval/split.py first (K). Wording probes are drawn from TUNING questions only.")
    out = [{"id": p["id"], "kind": "k", "set": p["set"], "type": p.get("type", ""), "answerable": p["ans"], "q": p["q"]}
           for p in pool if p["set"] in sets]
    tuning = [p for p in pool if p["set"] == "tuning"]
    picks = random.Random(seed).sample(tuning, min(n_probe, len(tuning)))
    for i, (p, fr) in enumerate(zip(picks, FRAMINGS)):
        out.append({"id": f"wp{i}_{p['id']}", "kind": "wording_probe", "parent_id": p["id"], "set": "wording_probe",
                    "answerable": p["ans"], "q": fr.format(q=lower_first(p["q"])), "author": "assistant"})
    return out


def main():
    """Plan or run the real 20b understand step on every question; store the outputs."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--pool", type=Path, default=None, help="default eval/k_questions.csv")
    ap.add_argument("--probes", type=int, default=5)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--gap", type=float, default=5.0, help="seconds between calls")
    ap.add_argument("--base-url", default=None, help="stand-in URL for a dry run (no ledger)")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--sets", default="eval,tuning",
                    help="which of K's sets to rewrite; K 2026-11-10: tuning only (eval rewrites come from the eval run)")
    a = ap.parse_args()

    pool = load_pool(a.pool or POOL_PATH)
    todo = items(pool, a.probes, a.seed, tuple(x.strip() for x in a.sets.split(",")))
    done = json.loads(a.out.read_text()) if a.out.exists() else {}
    todo = [t for t in todo if match_key(t["q"]) not in done]         # resumable; never resend a stored one
    real = a.base_url is None
    pol = Policy()
    if real:
        from probe.probe_groq import HARD_CAP, LEDGER
        used = json.loads(LEDGER.read_text())["sent"] if LEDGER.exists() else 0
    n = len(todo)
    print(f"[rewrites] target: {'REAL Groq' if real else a.base_url}  model {SMALL}  temperature 0  "
          f"reasoning_effort {pol.reasoning_effort}  max_tokens 400")
    print(f"  requests: {n} = {sum(t['kind'] == 'k' for t in todo)} K questions + "
          f"{sum(t['kind'] == 'wording_probe' for t in todo)} wording probes  (+ at most 1 retry each on a per-minute 429)")
    print(f"  est tokens: ~{n * EST_IN} in + ~{n * EST_OUT} out = ~{n * (EST_IN + EST_OUT)} on 20b "
          f"({100 * n * (EST_IN + EST_OUT) / 200_000:.1f}% of 20b TPD 200k; RPD {n}/1000)")
    print(f"  pacing: 1 call / {a.gap:.0f} s -> {60 / a.gap:.0f}/min, ~{n * a.gap / 60:.1f} min; "
          f"~{60 / a.gap * (EST_IN + EST_OUT):.0f} tok/min vs TPM 8000, ~{60 / a.gap * EST_IN:.0f} in/min vs ITPM 7000")
    if real:
        print(f"  ledger: {used}/{HARD_CAP} used; after this run <= {used + 2 * n}/{HARD_CAP}")
    print(f"  stores: {a.out.relative_to(ROOT) if a.out.is_relative_to(ROOT) else a.out} "
          f"(already stored: {len(done)})")
    for t in todo:
        if t["kind"] == "wording_probe":
            print(f"    probe {t['id']}: {t['q']}")
    if a.plan or not a.go:
        if not a.go:
            print("  (plan only; nothing sent. Re-run with --go once approved.)")
        return

    if real:
        from probe.probe_groq import KEY, Log, _spend_one
        log = Log("rewrites")
    for i, t in enumerate(todo):
        for attempt in range(2):
            if real:
                _spend_one()
            t0 = time.time()
            r = stream_chat(understand_messages(t["q"]), SMALL, base_url=a.base_url or "https://api.groq.com/openai/v1",
                            api_key=KEY if real else "standin", max_tokens=400, temperature=0.0, timeout_s=30,
                            extra={"reasoning_effort": pol.reasoning_effort})
            if real:
                log.write(tag="rewrite", item=t, status=r.status, ttft_ms=r.ttft_ms, total_ms=r.total_ms,
                          tokens_in=r.tokens_in, tokens_out=r.tokens_out, text=r.text, headers=r.headers,
                          error_kind=r.error_kind, error_body=r.error_body)
            if r.status == 429:
                body = (r.error_body or "").lower()
                if "per day" in body:
                    sys.exit(f"per-day 429 on {t['id']}: stopping (stored {len(done)})")
                wait = float(r.headers.get("retry-after", 10))
                print(f"  429 per-minute on {t['id']}, waiting {wait:.1f} s")
                time.sleep(wait + 0.5)
                continue
            break
        j = parse_json(r.text) if r.status == 200 else None
        sq = ((j or {}).get("search_query") or "").strip()
        # valid JSON with an empty search_query: production searches with the raw question
        # (relay/pipeline.py, understand step), so store exactly that, flagged
        fallback = j is not None and not sq
        if fallback:
            sq = t["q"]
        rec = {**t, "status": r.status, "error_kind": r.error_kind, "text": r.text, "search_query": sq or None,
               "empty_rewrite_fallback": fallback,
               "tokens_in": r.tokens_in, "tokens_out": r.tokens_out, "total_ms": round(r.total_ms or 0, 1),
               "model": SMALL, "temperature": 0.0, "reasoning_effort": pol.reasoning_effort,
               "source": "groq" if real else "stand-in",
               "wall": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        if sq:
            done[match_key(t["q"])] = rec
            a.out.write_text(json.dumps(done, indent=1))
        shown = "(empty search_query -> raw question, as production)" if fallback else sq[:90]
        print(f"  {i + 1}/{n} {t['id']}: {r.status} -> {shown if sq else '(no rewrite: ' + (r.error_kind or 'unparsed') + ')'}")
        if i + 1 < n:
            time.sleep(a.gap)
    print(f"[rewrites] stored {len(done)} -> {a.out}")


if __name__ == "__main__":
    main()
