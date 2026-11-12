"""Our own copy of the provider's limits, so we can predict a 429 before sending.

Same continuous-refill rule we measured on Groq: wait = (used + r - limit) / (limit/window).
Synced from response headers: x-ratelimit-remaining-requests (per DAY) and
x-ratelimit-remaining-tokens (per MINUTE). Parallel responses arrive out of order, so a
sync only ever makes our estimate MORE conservative (never trusts a larger 'remaining').
"""
from __future__ import annotations

import math
import threading
import time
from collections import deque

WINDOWS = {"rpm": 60, "itpm": 60, "tpm": 60, "rpd": 86400, "tpd": 86400}
DEFAULT_LIMITS = {"rpm": 30, "itpm": 7000, "tpm": 8000, "rpd": 1000, "tpd": 200000}


LEARN_DRIFT_S = 600   # K: a learned (lower) limit drifts back to the measured one over ~10 min
SPEND_KEEP_S = 3600   # spend history kept for pacing (K, 2026-11-12): longer than any pacing window we'd use


class _Bucket:
    """One limit (e.g. 120b tokens per minute) as a continuously refilling bucket, the rule measured on Groq."""
    def __init__(self, limit, window):
        self.base, self.window, self.used, self.t = float(limit), float(window), 0.0, time.monotonic()
        self.learned, self.learned_t = None, None

    @property
    def limit(self):
        """Measured limit, unless a 429 told us a lower one. The learned value drifts linearly back to
        the measured one over LEARN_DRIFT_S: nothing else would ever raise it (ITPM 7000 is not in
        the headers), and another 429 simply re-learns it."""
        if self.learned is None:
            return self.base
        f = min(1.0, (time.monotonic() - self.learned_t) / LEARN_DRIFT_S)
        if f >= 1.0:
            self.learned = None
            return self.base
        return self.learned + (self.base - self.learned) * f

    def _refill(self):
        """Give back capacity in proportion to the time passed (limit per window, continuously)."""
        now = time.monotonic()
        self.used = max(0.0, self.used - (now - self.t) * self.limit / self.window)
        self.t = now

    def wait_for(self, r):
        """Seconds until r more units fit under the limit (0 if they fit now)."""
        self._refill()
        over = self.used + r - self.limit
        return 0.0 if over <= 0 else over / (self.limit / self.window)

    def remaining(self):
        """Units left right now."""
        self._refill()
        return self.limit - self.used


class Limiter:
    """Our copy of Groq's limits for each model: predict waits, reserve capacity, learn from 429s and headers."""
    def __init__(self, models, limits=None):
        self.lock = threading.Lock()
        lim = {**DEFAULT_LIMITS, **(limits or {})}
        self.b = {m: {k: _Bucket(lim[k], WINDOWS[k]) for k in WINDOWS} for m in models}
        self.recent = deque()        # (t, is_retry) over the last 60 s, for the shared retry budget
        # pacing (K, 2026-11-12): tokens actually spent per model, (monotonic time, tokens in + out), oldest first
        self.spend = {m: deque() for m in models}

    def learn(self, model, kind, limit_value) -> bool:
        """Lower our limit to what a 429 body said ('Limit 3500'). Returns True if it changed."""
        with self.lock:
            bk = self.b[model].get(kind)
            if bk is None or limit_value >= bk.base:
                return False
            bk._refill()
            bk.learned, bk.learned_t = float(limit_value), time.monotonic()
            return True

    def peek_wait(self, model, tokens_in, tokens_out_est, ahead_tokens=0.0) -> tuple[float, str]:
        """Like predict_wait_s but with `ahead_tokens` of not-yet-reserved drafts queued in front."""
        need = {"rpm": 1, "rpd": 1, "itpm": tokens_in + ahead_tokens,
                "tpm": tokens_in + tokens_out_est + ahead_tokens, "tpd": tokens_in + tokens_out_est}
        with self.lock:
            waits = {k: self.b[model][k].wait_for(r) for k, r in need.items()}
        k = max(waits, key=waits.get)
        return waits[k], k

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
        """Count a call against every bucket (used when a call is sent without acquire())."""
        with self.lock:
            bb = self.b[model]
            for k, r in {"rpm": 1, "rpd": 1, "itpm": tokens_in, "tpm": tokens_in + tokens_out_est,
                         "tpd": tokens_in + tokens_out_est}.items():
                bb[k]._refill()
                bb[k].used += r

    def settle(self, model, est_out, actual_out, actual_in=None):
        """Correct the token estimate once real usage is known; with actual_in, also log the spend for pacing."""
        with self.lock:
            for k in ("tpm", "tpd"):
                self.b[model][k]._refill()
                self.b[model][k].used = max(0.0, self.b[model][k].used + actual_out - est_out)
            if actual_in is not None:
                self._log_spend(model, (actual_in or 0) + (actual_out or 0))

    def note_spend(self, model, tokens):
        """Log spend for pacing WITHOUT touching the buckets: a stream cut by cancellation reports no usage, so its
        reservation stays as it is (no refund) and its estimated cost still counts toward the recent spend rate."""
        with self.lock:
            self._log_spend(model, tokens)

    def _log_spend(self, model, tokens):
        """Append to the pacing spend history (caller holds the lock); drop entries older than SPEND_KEEP_S."""
        now = time.monotonic()
        h = self.spend.setdefault(model, deque())
        h.append((now, tokens))
        while h and now - h[0][0] > SPEND_KEEP_S:
            h.popleft()

    def release(self, model, tokens_in, tokens_out_est=0):
        """Give back an acquire() reservation for a call that never reached the provider (cancelled while waiting or
        before sending): the exact inverse of what acquire() added, floored at 0."""
        with self.lock:
            bb = self.b[model]
            for k, r in {"rpm": 1, "rpd": 1, "itpm": tokens_in, "tpm": tokens_in + tokens_out_est,
                         "tpd": tokens_in + tokens_out_est}.items():
                bb[k]._refill()
                bb[k].used = max(0.0, bb[k].used - r)

    def check_pacing(self, model: str, window_s: float, tolerance: float) -> tuple[bool, float, float]:
        """Spend-rate pacing (K, 2026-11-12; DECISIONS §4 "allowed rate = remaining / time until reset").
        Returns (is_exceeded, current_rate_tps, allowed_rate_tps):
          current = tokens spent in the last window_s / window_s
          allowed = tokens left in the day bucket / 86,400 s (a fixed 24 h horizon, K §72)
          exceeded = current > allowed * (1 + tolerance)
        Groq's day limit refills continuously (our model of it: the tpd bucket), so there is no reset instant. K chose
        the fixed horizon over "until the bucket is full again", which is ~0 s on a fresh day and so let the allowed
        rate run to infinity (52 of 135 drafts in the first 4 h of the simulation). A full day allows
        200,000 / 86,400 = 2.31 tok/s. Guards: no spend in the window -> current 0; window_s <= 0 -> never exceeded."""
        if window_s <= 0:
            return False, 0.0, math.inf
        with self.lock:
            now = time.monotonic()
            spent = sum(t for ts, t in self.spend.get(model, ()) if now - ts <= window_s)
            bk = self.b[model]["tpd"]
            bk._refill()
            used, limit = bk.used, bk.limit
        current = spent / window_s
        allowed = max(0.0, limit - used) / bk.window      # bk.window = 86,400 s for tpd
        return current > allowed * (1.0 + tolerance), current, allowed

    def sync(self, model, headers):
        """Tighten our counters from Groq's response headers (never loosen them)."""
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
        """Share of the day's tokens / requests still free for this model (the 20 % reserve test)."""
        with self.lock:
            bb = self.b[model]
            return min(bb["tpd"].remaining() / bb["tpd"].limit, bb["rpd"].remaining() / bb["rpd"].limit)

    # ---- shared retry budget
    def note_request(self, is_retry: bool):
        """Remember a request (and whether it was a retry) for the shared retry budget."""
        with self.lock:
            now = time.monotonic()
            self.recent.append((now, is_retry))
            while self.recent and now - self.recent[0][0] > 60:
                self.recent.popleft()

    def retry_allowed(self, fraction) -> bool:
        """True if one more retry keeps retries within the budget share of the last 60 s."""
        with self.lock:
            n = len(self.recent)
            r = sum(1 for _, x in self.recent if x)
        return (r + 1) <= max(2, fraction * n)     # always allow a couple, so a quiet system can retry
