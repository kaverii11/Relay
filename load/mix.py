"""Load mix: which questions the load generator asks, and how many of them need a 120b draft.

K (DECISIONS §22): pool = K's eval + tuning questions; X% unanswerable; the burst has Y% exact
repeats; question rates are chosen so DRAFT demand = k x measured ceiling (both rates reported).

Pool file: eval/k_questions.csv, columns  id,set,question,answerable
  set = eval | tuning;  answerable = yes | no  (by the three papers)

  .venv/bin/python load/mix.py            # gate-pass shares at Policy.gate_threshold -> load/mix.json

No Groq calls. The gate is scored on the raw question, which is what the stand-in's understand
step returns as the search query (standin/server.py). Real Groq rewrites the query, so its pass
shares can differ; that is listed as a stand-in difference.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

POOL_PATH = ROOT / "eval/k_questions.csv"
MIX_PATH = ROOT / "load/mix.json"


def load_pool(path: Path = POOL_PATH):
    rows = list(csv.DictReader(open(path)))
    bad = [r for r in rows if r["answerable"].strip().lower() not in ("yes", "no")]
    if bad:
        raise SystemExit(f"{path}: answerable must be yes/no, bad rows: {[r['id'] for r in bad]}")
    return [{"id": r["id"], "set": r["set"], "q": r["question"].strip(),
             "ans": r["answerable"].strip().lower() == "yes"} for r in rows]


def draft_share(mix: dict, unanswerable_share: float, repeat_share: float = 0.0) -> float:
    """Expected fraction of offered questions that reach the 120b draft.
    = P(gate passes) over the X/(1-X) mix, times (1 - exact repeats), since repeats are cache hits.
    Ignores drafter refusals and busy replies (busy is load, not demand)."""
    x = unanswerable_share
    p = (1 - x) * mix["pass_answerable"] + x * mix["pass_unanswerable"]
    return p * (1 - repeat_share)


class Sampler:
    """Fresh questions: each is unanswerable with probability X, drawn WITHOUT replacement from
    that stratum's shuffled deck. When a deck runs out it is reshuffled and reused; those reuses
    are counted (`forced_repeats`) because they become exact-match cache hits.
    Burst repeats (Y): an exact repeat of a question already asked in the same burst."""

    def __init__(self, pool, unanswerable_share: float, rng: random.Random):
        self.rng, self.x = rng, unanswerable_share
        self.decks = {True: [p for p in pool if p["ans"]], False: [p for p in pool if not p["ans"]]}
        if self.x > 0 and not self.decks[False]:
            raise SystemExit("X > 0 but the pool has no unanswerable questions")
        if self.x < 1 and not self.decks[True]:
            raise SystemExit("X < 1 but the pool has no answerable questions")
        self.left = {k: [] for k in self.decks}
        self.forced_repeats, self.used_once = 0, set()

    def fresh(self):
        ans = self.rng.random() >= self.x
        if not self.left[ans]:
            self.left[ans] = self.decks[ans][:]
            self.rng.shuffle(self.left[ans])
        p = self.left[ans].pop()
        if p["id"] in self.used_once:
            self.forced_repeats += 1
        self.used_once.add(p["id"])
        return p

    def burst(self, asked_in_burst: list, repeat_share: float):
        if asked_in_burst and self.rng.random() < repeat_share:
            return self.rng.choice(asked_in_burst), True
        return self.fresh(), False


def main():
    from relay.config import SETTINGS, Policy
    from relay.retrieval import Retriever, cross_encoder
    pool = load_pool()
    pol = Policy()
    out = {}
    for name in ("medium_rerank",):            # the setting the load scenarios use (loadgen default)
        ret = Retriever(SETTINGS[name])
        cross_encoder()
        ret.search("warm-up query about attention heads")
        g = [(p, ret.search(p["q"])[1]) for p in pool]
        a = [s for p, s in g if p["ans"]]
        u = [s for p, s in g if not p["ans"]]
        out[SETTINGS[name].name] = {
            "gate_threshold": pol.gate_threshold, "n_answerable": len(a), "n_unanswerable": len(u),
            "pass_answerable": sum(s >= pol.gate_threshold for s in a) / max(1, len(a)),
            "pass_unanswerable": sum(s >= pol.gate_threshold for s in u) / max(1, len(u)),
            "pool": str(POOL_PATH.relative_to(ROOT)), "n_pool": len(pool),
            "computed": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "scores": {p["id"]: round(s, 3) for p, s in g}}
        m = out[SETTINGS[name].name]
        print(f"{name}: cutoff {pol.gate_threshold}  pass answerable {m['pass_answerable']:.2f} "
              f"(n={len(a)})  pass unanswerable {m['pass_unanswerable']:.2f} (n={len(u)})")
    MIX_PATH.write_text(json.dumps(out, indent=2))
    print(f"-> {MIX_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
