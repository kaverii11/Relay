"""Ask the system one question (K, 2026-11-12). Same production pipeline as the eval, chosen setting by default.

  .venv/bin/python scripts/ask.py "How many attention heads does the base Transformer use?"          # plan only
  .venv/bin/python scripts/ask.py "How many attention heads does the base Transformer use?" --go     # real Groq

Plan first (nothing sent): the gate score this question would get, so whether it reaches the 120b draft, and the
token cost against the 24 h ledger. --go sends it (counted in the ledger, cap 5 requests). --base-url runs it on the
stand-in instead. Writes raw/ask_{stamp}.jsonl (the full event log); never touches results.csv.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from relay.budget import CEILING, Budget, usage_24h  # noqa: E402
from relay.config import BIG, CHOSEN, SETTINGS, SMALL, Policy  # noqa: E402
from relay.limiter import Limiter  # noqa: E402
from relay.pipeline import ExactCache, Pipeline  # noqa: E402
from relay.retrieval import Retriever, cross_encoder  # noqa: E402
from relay.service import Service  # noqa: E402

GROQ = "https://api.groq.com/openai/v1"


def main():
    """Plan, or with --go ask, one question on a chosen setting; print the reply, citations and checks."""
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--go", action="store_true", help="send it (real Groq unless --base-url)")
    ap.add_argument("--setting", default=CHOSEN, choices=list(SETTINGS))
    ap.add_argument("--base-url", default=None, help="stand-in URL, e.g. http://127.0.0.1:8099/v1")
    a = ap.parse_args()
    real = a.base_url is None
    setting = SETTINGS[a.setting]
    # each arm's Policy, as eval/run_v1v2.py runs them: v2 = new check + draft prompts; v3 = v2 + sticky check failure
    # pacing off (K §72): one question can't be paced meaningfully, and it should match the arms as measured
    pol = (Policy(check_prompt="v2", draft_prompt="v2", sticky_check_fail=True, pacing_enabled=False) if a.setting.startswith("chosen_v3")
           else Policy(check_prompt="v2", draft_prompt="v2", pacing_enabled=False) if a.setting == "chosen_v2"
           else Policy(pacing_enabled=False))
    ret = Retriever(setting)
    cross_encoder()
    hits, gate, _ = ret.search(a.question)
    cut = setting.cutoff(pol)
    print(f"setting {setting.name}; cutoff {cut}; gate on the raw question {gate:.3f} -> "
          f"{'reaches the draft' if gate >= cut else 'below the cutoff (the 20b rewrite may still lift it)'}")
    for i, h in enumerate(hits[:setting.k], 1):
        print(f"  C{i} {h.chunk.cite()}  (ce {h.ce:.2f})")
    u = usage_24h()
    print("worst case: 20b 3 calls ~2.6k tokens, 120b 2 calls ~5k tokens; cap 5 requests")
    for m in (SMALL, BIG):
        print(f"  {m:22s} last 24 h {u[m]['tokens']:6d} of ceiling {CEILING}")
    if not a.go:
        print("(plan only; nothing sent. Add --go to ask it.)")
        return

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    run = f"ask_{stamp}"
    pl = Pipeline(base_url=a.base_url or GROQ, api_key="standin", source="groq" if real else "stand-in",
                  setting=setting, policy=pol, limiter=Limiter([SMALL, BIG]), cache=ExactCache(), retriever=ret,
                  budget=Budget(run, 5) if real else None)
    if real:
        from probe.probe_groq import KEY
        pl.api_key = KEY
    pl.keep_passages = True
    events = ROOT / f"raw/{run}.jsonl"
    svc = Service(pl, workers=1, scenario="ask", events_path=events, variant="", profile="")
    svc.submit("ask-1", a.question, 60.0)
    svc.wait_all(timeout=90)
    row = svc.rows[-1]
    rec = json.loads(events.read_text().splitlines()[-1])
    res = rec["result"]
    print(f"\nreply ({row['reply_kind']}, {row['status']}; {row['degrade_level']}; first token {row['first_token_ms']} ms; "
          f"calls {row['calls']}; 20b {row['tokens_in_20b']}+{row['tokens_out_20b']}, "
          f"120b {row['tokens_in_120b']}+{row['tokens_out_120b']} tokens):\n")
    print(textwrap.fill(res.get("answer", ""), 100))
    if res.get("citations"):
        print("\ncitations:")
        for c in res["citations"]:
            print(f"  {c}")
    checks = [e for e in rec["events"] if e["ev"] == "check"]
    if checks:
        print("\nchecks: " + "; ".join(f"round {c['round']} {'OK' if c['ok'] else 'FAIL'}"
                                       + (f" ({c['why']})" if c.get("why") else "") for c in checks))
    print(f"\nfull log: {events.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
