"""Safe reads and writes of the Groq usage ledger, probe/raw/ledger.json (K, 2026-11-12, hardening).

The ledger is the only thing that keeps the daily token guardrail honest across runs and processes, so:
  - one process at a time: every read-modify-write holds an exclusive lock on ledger.json.lock (fcntl.flock).
    Two scripts running together (e.g. ask.py during the eval) used to be able to lose each other's entries.
  - atomic: a write goes to a temp file and is renamed over the ledger (os.replace). If a run is killed
    mid-write, the old ledger survives instead of a half-written file.
  - fail closed: a ledger that exists but doesn't parse raises LedgerCorrupt. Callers that guard spending
    treat that as "no budget", never as "nothing used today".
No heavy imports here, so probe/probe_groq.py can use it too.
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "probe/raw/ledger.json"   # looked up at call time, so a test can point it elsewhere


class LedgerCorrupt(Exception):
    """The ledger file exists but is not valid JSON (refuse to spend rather than guess)."""


@contextlib.contextmanager
def locked(path: Path | None = None):
    """Hold an exclusive cross-process lock for a read-modify-write of the ledger."""
    path = path or LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_name(path.name + ".lock"), "a") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)          # blocks until the other process is done
        try:
            yield
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def read(path: Path | None = None) -> dict:
    """The ledger as a dict ({} if it doesn't exist yet). Raises LedgerCorrupt if it can't be parsed."""
    path = path or LEDGER
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise LedgerCorrupt(f"{path} is not valid JSON ({e}); fix or restore it before spending") from e


def write(d: dict, path: Path | None = None):
    """Replace the ledger atomically: write a temp file in the same folder, fsync, rename over the old one."""
    path = path or LEDGER
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".ledger.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(d, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise
