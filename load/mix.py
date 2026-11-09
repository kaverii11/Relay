"""Load mix: which questions the load generator asks, and how many of them need a 120b draft.

K (DECISIONS §22): pool = K's eval + tuning questions; X% unanswerable; the burst has Y% exact
repeats; question rates are chosen so DRAFT demand = k x measured ceiling (both rates reported).

K's questions: eval/k_questions.csv, columns  id,set,question,answerable
  set = eval | tuning;  answerable = yes | no  (by the three papers)
Variants (K §23): eval/variants_assistant.csv, columns  id,parent_id,question,answerable,author
  Rewordings of K's questions written by the assistant (author=assistant), so long scenarios
  don't run out of questions and turn into exact-match cache hits. LOAD POOL ONLY: never used
  for eval or gate tuning (those read k_questions.csv through load_pool(), which never sees them).
  Each variant is gate-scored on its own; it does not inherit its parent's pass/fail.

  .venv/bin/python load/mix.py                  # gate scores at Policy.gate_threshold -> load/mix.json
  .venv/bin/python load/mix.py --spotcheck 10   # K: 10 random variants beside their parents
  .venv/bin/python load/mix.py --coverage --x 0.3 --y 0.5 --hot 3   # forced repeats per scenario

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
VARIANTS_PATH = ROOT / "eval/variants_assistant.csv"
MIX_PATH = ROOT / "load/mix.json"


def load_pool(path: Path | None = None):
    path = path or POOL_PATH
    rows = list(csv.DictReader(open(path)))
    bad = [r for r in rows if r["answerable"].strip().lower() not in ("yes", "no")]
    if bad:
        raise SystemExit(f"{path}: answerable must be yes/no, bad rows: {[r['id'] for r in bad]}")
    return [{"id": r["id"], "set": r["set"], "q": r["question"].strip(),
             "ans": r["answerable"].strip().lower() == "yes"} for r in rows]


def load_variants(path: Path | None = None, parents=None):
    path = path or VARIANTS_PATH
    if not path.exists():
        return []
    parents = {p["id"]: p for p in (parents if parents is not None else load_pool())}
    out = []
    for r in csv.DictReader(open(path)):
        if r["parent_id"] not in parents:
            raise SystemExit(f"{path}: variant {r['id']} has unknown parent {r['parent_id']}")
        if r.get("author", "").strip() != "assistant":
            raise SystemExit(f"{path}: variant {r['id']} must be labelled author=assistant")
        a = r["answerable"].strip().lower()
        if a not in ("yes", "no"):
            raise SystemExit(f"{path}: variant {r['id']} answerable must be yes/no")
        out.append({"id": r["id"], "set": "variant", "parent": r["parent_id"], "q": r["question"].strip(),
                    "ans": a == "yes"})
    return out


def load_load_pool():
    """K's questions + assistant-written variants. For the load generator ONLY."""
    pool = load_pool()
    return pool + load_variants(parents=pool)


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
    Burst repeats (K §23): each burst gets a small HOT SET of `hot` questions (fresh draws at the
    start of the burst, so they follow X); a burst question is, with probability Y, an exact
    repeat of one of its burst's hot set, otherwise a fresh question."""

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

    def hot_set(self, hot: int):
        return [self.fresh() for _ in range(hot)]

    def burst(self, hot_set: list, repeat_share: float):
        if hot_set and self.rng.random() < repeat_share:
            return self.rng.choice(hot_set), True
        return self.fresh(), False


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def _scores(pool):
    from relay.config import SETTINGS
    from relay.retrieval import Retriever, cross_encoder
    ret = Retriever(SETTINGS["medium_rerank"])          # the setting the load scenarios use (loadgen default)
    cross_encoder()
    ret.search("warm-up query about attention heads")
    return SETTINGS["medium_rerank"].name, {p["id"]: ret.search(p["q"])[1] for p in pool}


def main():
    import argparse
    from relay.config import Policy
    ap = argparse.ArgumentParser()
    ap.add_argument("--spotcheck", type=int, default=0)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--coverage", action="store_true")
    ap.add_argument("--x", type=float)
    ap.add_argument("--y", type=float, default=0.0)
    ap.add_argument("--hot", type=int, default=0)
    a = ap.parse_args()
    cut = Policy().gate_threshold

    if a.coverage:
        from load.loadgen import schedule
        from load.scenarios import SCENARIOS
        mix = list(json.loads(MIX_PATH.read_text()).values())[0]
        pool = load_load_pool()
        ds = draft_share(mix, a.x)
        print(f"pool {len(pool)} (K {sum(p['set'] != 'variant' for p in pool)}, variants "
              f"{sum(p['set'] == 'variant' for p in pool)}); X={a.x} draft_share={ds:.2f}")
        for name, sc in SCENARIOS.items():
            smp = Sampler(pool, a.x, random.Random(1))
            sch = schedule(sc, random.Random(1), ds, smp, a.y, hot=a.hot)
            print(f"  {name:20s} questions {len(sch):4d}  forced repeats {smp.forced_repeats}")
        return

    pool = load_load_pool()
    name, sc = _scores(pool)
    if a.spotcheck:
        var = [p for p in pool if p["set"] == "variant"]
        par = {p["id"]: p for p in pool}
        for v in random.Random(a.seed).sample(var, min(a.spotcheck, len(var))):
            pp = par[v["parent"]]
            print(f"[{v['id']} <- {pp['id']}] answerable={'yes' if v['ans'] else 'no'}  gate {sc[pp['id']]:.2f} -> {sc[v['id']]:.2f}")
            print(f"   K:       {pp['q']}\n   variant: {v['q']}")
        return

    def share(items):
        return sum(sc[p["id"]] >= cut for p in items) / max(1, len(items))
    groups = {g: [p for p in pool if (p["set"] == "variant") == (g == "variant")] for g in ("k", "variant")}
    out = {name: {
        "gate_threshold": cut,
        # over the WHOLE load pool, every item scored on its own
        "pass_answerable": share([p for p in pool if p["ans"]]),
        "pass_unanswerable": share([p for p in pool if not p["ans"]]),
        "n_answerable": sum(p["ans"] for p in pool), "n_unanswerable": sum(not p["ans"] for p in pool),
        "by_origin": {g: {"pass_answerable": share([p for p in items if p["ans"]]),
                          "pass_unanswerable": share([p for p in items if not p["ans"]]), "n": len(items)}
                      for g, items in groups.items()},
        "pool": [_rel(POOL_PATH), _rel(VARIANTS_PATH)], "n_pool": len(pool),
        "computed": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "scores": {k: round(v, 3) for k, v in sc.items()}}}
    m = out[name]
    print(f"{name}: cutoff {cut}  pass answerable {m['pass_answerable']:.2f} (n={m['n_answerable']})  "
          f"pass unanswerable {m['pass_unanswerable']:.2f} (n={m['n_unanswerable']})")
    for g, d in m["by_origin"].items():
        print(f"  {g:8s} n={d['n']:4d}  pass answerable {d['pass_answerable']:.2f}  pass unanswerable {d['pass_unanswerable']:.2f}")
    MIX_PATH.write_text(json.dumps(out, indent=2))
    print(f"-> {_rel(MIX_PATH)}")


if __name__ == "__main__":
    main()
