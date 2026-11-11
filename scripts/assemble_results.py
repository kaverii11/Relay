"""Build results.csv (the submission's raw file) from the per-run csvs in raw/. No Groq.
  .venv/bin/python scripts/assemble_results.py raw/results_steady_*.csv raw/results_e2e_*.csv ... -> results.csv
Columns = relay.service.COLUMNS (the brief's 12 first, extras after); runs written before a column existed get "".
"""
import csv, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from relay.service import COLUMNS  # noqa: E402

def main(paths, out=ROOT / "results.csv"):
    """Concatenate per-run result files into results.csv."""
    rows = []
    for p in paths:
        rows += list(csv.DictReader(open(p)))
    rows.sort(key=lambda r: r["start_time"])
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLUMNS})
    print(f"{len(rows)} rows from {len(paths)} files -> {out.relative_to(ROOT)}")

if __name__ == "__main__":
    main(sys.argv[1:])
