"""Fetch the library at the exact versions in the brief.

Hard check: the arXiv stamp inside each PDF names the exact version (e.g. arXiv:1706.03762v7).
Soft check: SHA-256 of the bytes we used. arXiv can re-render a PDF without changing the
version, so a hash mismatch is a warning, not a failure - the version stamp is what the brief asks for.
"""
import hashlib
import re
import sys
from pathlib import Path

import httpx
import pymupdf

ROOT = Path(__file__).resolve().parents[1]
PAPERS = {
    "1706.03762v7": "bdfaa68d8984f0dc02beaca527b76f207d99b666d31d1da728ee0728182df697",
    "2410.00037v1": "a687144cc77bea86b0c60ae800ccb1d3e0816033fa5c7960388fe29a0dbfcfac",
    "2507.07955v2": "04a2b32e6e82853cfc23c5db132750874a86cde99219ec6f664128f4aa83122f",
}


def main():
    """Download the three PDFs at their pinned versions and check their sha256."""
    out = ROOT / "papers"
    out.mkdir(exist_ok=True)
    ok = True
    for pid, sha in PAPERS.items():
        path = out / f"{pid}.pdf"
        if not path.exists():
            r = httpx.get(f"https://arxiv.org/pdf/{pid}", follow_redirects=True, timeout=60,
                          headers={"User-Agent": "relay-assignment/0.1"})
            r.raise_for_status()
            path.write_bytes(r.content)
        text = "".join(p.get_text() for p in pymupdf.open(path))
        base = pid.split("v")[0]
        stamps = set(re.findall(rf"arXiv:{re.escape(base)}v\d+", text))
        good = stamps == {f"arXiv:{pid}"}
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        print(f"{pid}: stamp {'OK' if good else 'MISMATCH ' + str(stamps)}; "
              f"sha256 {'matches' if digest == sha else 'differs (warning: arXiv may have re-rendered)'}")
        ok &= good
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
