"""Replace the Groq organization id with org_REDACTED in raw probe/run files, in place.
Only that id string changes; no measurement does. Safe to re-run."""
import re
import sys
from pathlib import Path

ORG = re.compile(r"org_[0-9a-z]{20,}")
ROOT = Path(__file__).resolve().parents[1]
n_files = n_hits = 0
for p in list((ROOT / "probe/raw").glob("*")) + list((ROOT / "raw").glob("*")):
    if p.is_file() and p.suffix in (".jsonl", ".txt", ".csv", ".json"):
        s = p.read_text()
        new, k = ORG.subn("org_REDACTED", s)
        if k:
            p.write_text(new); n_files += 1; n_hits += k
print(f"redacted {n_hits} occurrences in {n_files} files")
sys.exit(0)
