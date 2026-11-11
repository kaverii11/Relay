"""v3 offline measurement (K, 2026-11-12). No Groq: stored 20b rewrites (they carry the "papers" hint) and stored drafts.

  .venv/bin/python eval/v3_offline.py      -> stdout + raw/v3_offline_{stamp}.md

Change B (paper hint, retrieval) on the TUNING questions, same method as eval/v1_v2_recall.py:
  1. hint accuracy: does the stored 20b hint name the labelled paper(s)? how many papers does it name?
  2. recall@3 of the labelled passage, chosen (v1) vs chosen_v3; query = whichever of raw question and stored
     rewrite has the higher gate (both searched with the hint for v3, as the pipeline does)
  3. the 250/3 cutoff by K's midpoint rule (fallback: fewest errors), for both
Change A (sticky check failure) on every stored real run with both checks logged: how many redrafts repeated a
claim (same passage, same quote) the model check had rejected, and what the reply was.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.check_questions import resolve_paper  # noqa: E402
from eval.cutoffs_by_size import cutoff, errors_at  # noqa: E402
from eval.recall import found, labelled  # noqa: E402
from load.mix import load_pool, load_rewrites  # noqa: E402
from relay.config import SETTINGS  # noqa: E402
from relay.prompts import claim_quotes  # noqa: E402
from relay.retrieval import Retriever, cross_encoder  # noqa: E402
from relay.textnorm import match_key  # noqa: E402


def stored(p, rw):
    """(rewrite query, papers hint) from the stored real 20b understand output, or (None, None)."""
    r = rw.get(match_key(p["q"]))
    if not r or not r.get("search_query"):
        return None, None
    try:
        hint = json.loads(r.get("text") or "{}").get("papers")
    except json.JSONDecodeError:
        hint = None
    return r["search_query"], hint


def part_b(L):
    pool = {p["id"]: p for p in load_pool()}
    rw = load_rewrites()
    cross_encoder()
    tuning = [p for p in pool.values() if p["set"] == "tuning"]
    lab = [p for p in tuning if p["meta"].get("paper", "").strip() and p["meta"].get("page", "").strip()]
    arms = {"chosen (v1)": Retriever(SETTINGS["chosen"]), "chosen_v3 (hint)": Retriever(SETTINGS["chosen_v3"]),
            "chosen_v3a (hint, append)": Retriever(SETTINGS["chosen_v3a"])}

    # 1. hint accuracy
    L += ["## B. Paper hint (understand step), tuning questions with a stored rewrite", ""]
    n_named = {1: 0, 2: 0, 3: 0, 0: 0}
    right, wrong, total = [], [], 0
    ret0 = arms["chosen_v3 (hint)"]
    for p in lab:
        _, hint = stored(p, rw)
        if hint is None:
            continue
        total += 1
        named = ret0.hinted_papers(hint)
        n_named[min(len(named), 3)] += 1
        want = {resolve_paper(x) for x in p["meta"]["paper"].split(";") if x.strip()}
        (right if want <= set(named) else wrong).append(f"{p['id']} (wants {', '.join(sorted(want))}; hint {', '.join(named) or '-'})")
    L += [f"- {total} labelled tuning questions with a stored hint; hint names 1 paper: {n_named[1]}, 2: {n_named[2]}, "
          f"3 (ignored): {n_named[3]}, none: {n_named[0]}",
          f"- hint includes every labelled paper: {len(right)}/{total}; misses: {'; '.join(wrong) or 'none'}", ""]

    # 2. recall@3, 3. cutoff
    res, rows_by = {}, {}
    for arm, ret in arms.items():
        idx = {id(c): i for i, c in enumerate(ret.chunks)}
        per, changed, sizes = {}, {}, []
        for p in lab:
            groups = labelled(p, ret.chunks)
            if not groups:
                continue
            q_rw, hint = stored(p, rw)
            qs = [p["q"]] + ([q_rw] if q_rw else [])
            got = [ret.search(q, papers=hint) for q in qs]
            hits, _, info = max(got, key=lambda x: x[1])
            per[p["id"]] = found(groups, [idx[id(h.chunk)] for h in hits], len(hits))
            sizes.append(len(hits))
            if info.get("paper_hint_added"):
                changed[p["id"]] = info["paper_hint_added"]
        res[arm] = (per, changed, sizes)
        rows = []
        for p in tuning:
            if p["meta"].get("gate_expected", "").lower() not in ("pass", "refuse"):
                continue
            q_rw, hint = stored(p, rw)
            if q_rw is None:
                continue
            s = max(ret.search(p["q"], papers=hint)[1], ret.search(q_rw, papers=hint)[1])
            rows.append({"id": p["id"], "ans": p["ans"], "ge": p["meta"]["gate_expected"].lower(), "type": p["type"], "s": s})
        rows_by[arm] = rows
    L += ["| arm | recall (labelled passage sent) | questions where the hint added a piece | pieces sent (mean) |",
          "|---|---|---|---|"]
    for arm, (per, changed, sizes) in res.items():
        L.append(f"| {arm} | {sum(per.values())}/{len(per)} | {len(changed)} | {sum(sizes) / len(sizes):.2f} |")
    a = res["chosen (v1)"][0]
    for arm in list(res)[1:]:
        b = res[arm][0]
        L += ["", f"Recall changed v1 -> {arm}: " + (", ".join(f"{q} {'found->missed' if a[q] else 'missed->found'}"
                                                             for q in a if a[q] != b.get(q)) or "none")]
    L += [""]
    L += ["### 250/3 cutoff, K's midpoint rule, tuning only", "",
          "| arm | highest refuse | lowest answerable above it | cutoff | rule | errors (answerable refused / false-premise refused / refuse passed) |",
          "|---|---|---|---|---|---|"]
    for arm, rows in rows_by.items():
        h, lo, c, how = cutoff(rows)
        hid = max((r for r in rows if r["ge"] == "refuse"), key=lambda r: r["s"])["id"]
        loid = min((r for r in rows if r["ans"] and r["s"] > h), key=lambda r: r["s"])["id"] if lo is not None else "-"
        ar, fp, rp = errors_at(rows, c)
        L.append(f"| {arm} | {h:.3f} ({hid}) | {'-' if lo is None else f'{lo:.3f} ({loid})'} | **{c:.3f}** | {how} | "
                 f"{', '.join(ar) or '-'} / {', '.join(fp) or '-'} / {', '.join(rp) or '-'} |")
    return L


def part_a(L):
    L += ["", "## A. Sticky check failure, replayed on every stored real run (drafts + both verdicts logged)", ""]
    files = sorted((ROOT / "raw").glob("events_e2e_*.jsonl")) + sorted((ROOT / "raw").glob("events_eval_*.jsonl")) \
        + sorted((ROOT / "raw").glob("ask_*.jsonl"))
    n_q = n_rej = 0
    hits = []
    for f in files:
        for line in f.read_text().splitlines():
            rec = json.loads(line)
            ev = rec.get("events", [])
            drafts = [e for e in ev if e["ev"] == "draft_out"]
            checks = [e for e in ev if e["ev"] == "check"]
            if not drafts:
                continue
            n_q += 1
            rejected = []
            for d, c in zip(drafts, checks):
                keys = [(str(x.get("chunk", "")), match_key(q)) for x in d["draft"].get("claims") or [] for q in claim_quotes(x)]
                rep = [k for k in keys for r in rejected if k[0] == r[0] and k[1] and r[1] and (k[1] in r[1] or r[1] in k[1])]
                if rep and c.get("code_ok"):
                    hits.append(f"{f.name} {rec.get('rid', rec.get('row', {}).get('request_id', '?'))}: round {c['round']} "
                                f"repeated a rejected quote; model check said {'OK' if c.get('model_ok') else 'FAIL'}; "
                                f"reply {rec.get('result', {}).get('kind', '?')}")
                if c.get("model_ok") is False:
                    n_rej += 1
                    rejected += keys
    L += [f"- {n_q} drafted questions in {len(files)} files; model check rejections: {n_rej}",
          f"- redrafts that repeated a rejected claim: {len(hits)}"] + [f"  - {h}" for h in hits]
    L += ["- With change A each of these fails without a second model check (reply: couldn't verify)."]
    return L


def main():
    L = [f"# v3 offline ({dt.datetime.now().isoformat(timespec='minutes')}); no Groq", ""]
    L = part_b(L)
    L = part_a(L)
    txt = "\n".join(L)
    print(txt)
    (ROOT / f"raw/v3_offline_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.md").write_text(txt + "\n")


if __name__ == "__main__":
    main()
