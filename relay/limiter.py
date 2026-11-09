"""Our own copy of the provider's limits, so we can predict a 429 before sending.

Same continuous-refill rule we measured on Groq: wait = (used + r - limit) / (limit/window).
Synced from response headers: x-ratelimit-remaining-requests (per DAY) and
x-ratelimit-remaining-tokens (per MINUTE). Parallel responses arrive out of order, so a
sync only ever makes our estimate MORE conservative (never trusts a larger 'remaining').
"""
from __future__ import annotations

import threading
import time
from collections import deque

WINDOWS = {"rpm": 60, "itpm": 60, "tpm": 60, "rpd": 86400, "tpd": 86400}
DEFAULT_LIMITS = {"rpm": 30, "itpm": 7000, "tpm": 8000, "rpd": 1000, "tpd": 200000}


class _Bucket:
    def __init__(self, limit, window):
        self.limit, self.window, self.used, self.t = float(limit), float(window), 0.0, time.monotonic()

    def _refill(self):
        now = time.monotonic()
        self.used = max(0.0, self.used - (now - self.t) * self.limit / self.window)
        self.t = now

    def wait_for(self, r):
        self._refill()
        over = self.used + r - self.limit
        return 0.0 if over <= 0 else over / (self.limit / self.window)

    def remaining(self):
        self._refill()
        return self.limit - self.used


class Limiter:
    def __init__(self, models, limits=None):
        self.lock = threading.Lock()
        lim = {**DEFAULT_LIMITS, **(limits or {})}
        self.b = {m: {k: _Bucket(lim[k], WINDOWS[k]) for k in WINDOWS} for m in models}
        self.recent = deque()        # (t, is_retry) over the last 60 s, for the shared retry budget

    def predict_wait_s(self, model, tokens_in, tokens_out_est=0) -> tuple[float, str]:
        """Seconds until this call would be admitted, and which limit binds."""
        need = {"rpm": 1, "rpd": 1, "itpm": tokens_in, "tpm": tokens_in + tokens_out_est,
                "tpd": tokens_in + tokens_out_est}
        with self.lock:
            waits = {k: self.b[model][k].wait_for(r) for k, r in need.items()}
        k = max(waits, key=waits.get)
        return waits[k], k

    def acquire(self, model, tokens_in, tokens_out_est, max_wait_s) -> tuple[float, str, bool]:
        """ATOMIC check-and-reserve. Separate predict() then reserve() raced: 16 workers all saw
        'free' at once and all sent (smoke test: 6 TPM 429s). Reserving future capacity pushes
        `used` over the limit, so the next caller is told to wait longer - a queue in token time.
        Returns (wait_s, binding_limit, reserved). Daily limits are never reserved into the future."""
        need = {"rpm": 1, "rpd": 1, "itpm": tokens_in, "tpm": tokens_in + tokens_out_est,
                "tpd": tokens_in + tokens_out_est}
        with self.lock:
            bb = self.b[model]
            waits = {k: bb[k].wait_for(r) for k, r in need.items()}
            k = max(waits, key=waits.get)
            w = waits[k]
            if w > max_wait_s or (k in ("rpd", "tpd") and w > 0):
                return w, k, False
            for kk, r in need.items():
                bb[kk].used += r
            return w, k, True

    def reserve(self, model, tokens_in, tokens_out_est=0):
        with self.lock:
            bb = self.b[model]
            for k, r in {"rpm": 1, "rpd": 1, "itpm": tokens_in, "tpm": tokens_in + tokens_out_est,
                         "tpd": tokens_in + tokens_out_est}.items():
                bb[k]._refill()
                bb[k].used += r

    def settle(self, model, est_out, actual_out):
        """Correct the token estimate once real usage is known."""
        with self.lock:
            for k in ("tpm", "tpd"):
                self.b[model][k]._refill()
                self.b[model][k].used = max(0.0, self.b[model][k].used + actual_out - est_out)

    def sync(self, model, headers):
        with self.lock:
            bb = self.b[model]
            for hk, k in (("x-ratelimit-remaining-requests", "rpd"), ("x-ratelimit-remaining-tokens", "tpm")):
                if hk in headers:
                    try:
                        rem = float(headers[hk])
                    except ValueError:
                        continue
                    bb[k]._refill()
                    bb[k].used = max(bb[k].used, bb[k].limit - rem)   # only ever more conservative

    def daily_fraction_left(self, model) -> float:
        with self.lock:
            bb = self.b[model]
            return min(bb["tpd"].remaining() / bb["tpd"].limit, bb["rpd"].remaining() / bb["rpd"].limit)

    # ---- shared retry budget
    def note_request(self, is_retry: bool):
        with self.lock:
            now = time.monotonic()
            self.recent.append((now, is_retry))
            while self.recent and now - self.recent[0][0] > 60:
                self.recent.popleft()

    def retry_allowed(self, fraction) -> bool:
        with self.lock:
            n = len(self.recent)
            r = sum(1 for _, x in self.recent if x)
        return (r + 1) <= max(2, fraction * n)     # always allow a couple, so a quiet system can retry
