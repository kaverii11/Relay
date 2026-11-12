"""Build results.csv (the submission's raw file) from the per-run csvs in raw/. No Groq.
  .venv/bin/python scripts/assemble_results.py raw/results_steady_*.csv raw/results_e2e_*.csv ... -> results.csv
Columns = relay.service.COLUMNS (the brief's 12 first, extras after); runs written before a column existed get "".
source follows the brief ("real" or "stand-in"): runs recorded before 2026-11-12 wrote "groq" for real Groq calls, and
that is mapped to "real" here. The raw files keep what was recorded.
request_id is unique in results.csv: repeated runs reused their numbering (afternoon / evening profile, the shadow and
no-learn variants, the eval's three settings, v1/v2/v3), so a shared id gets "@" + whatever tells the rows apart
(run variant, stand-in profile, retrieval setting), e.g. minute_limit_halved-1-0043@nolearn, Q63@w250_k3_rr0_v2.
A row whose distinguishing values are all empty keeps the plain id. analysis/tables.py base_id() strips the suffix.
"""
import csv, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from relay.service import COLUMNS  # noqa: E402

LEGACY_SOURCE = {"groq": "real"}     # brief: source is "real" or "stand-in"


def unique_ids(rows):
    """Suffix shared request_ids with the fields that differ between the rows sharing them."""
    from collections import defaultdict
    groups = defaultdict(list)
    for r in rows:
        groups[r["request_id"]].append(r)
    fields = (lambda r: r.get("run_variant", ""), lambda r: (r.get("standin_profile") or "").split(" ")[0],
              lambda r: r.get("retrieval_setting", ""))
    for rid, rs in groups.items():
        if len(rs) < 2:
            continue
        vary = [g for g in fields if len({g(r) for r in rs}) > 1]
        for r in rs:
            tag = ".".join(v for v in (g(r) for g in vary) if v)
            if tag:
                r["request_id"] = f"{rid}@{tag}"
    ids = [r["request_id"] for r in rows]
    assert len(ids) == len(set(ids)), "request_id still not unique"

def main(paths, out=ROOT / "results.csv"):
    """Concatenate per-run result files into results.csv."""
    rows = []
    for p in paths:
        for r in csv.DictReader(open(p)):
            r["source"] = LEGACY_SOURCE.get(r.get("source", ""), r.get("source", ""))
            rows.append(r)
    unique_ids(rows)
    rows.sort(key=lambda r: r["start_time"])
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLUMNS})
    print(f"{len(rows)} rows from {len(paths)} files -> {out.relative_to(ROOT)}")

if __name__ == "__main__":
    main(sys.argv[1:])
