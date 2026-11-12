# Probe findings (real Groq, free tier, key of Kaveri Sharma)

## Stage 1: 2026-11-09 15:34 IST, 5 requests (raw: probe/raw/stage1_20261109_153435.jsonl)
Prompt = the real "understand" step (relay/prompts.py), questions from eval/seed_questions.py.

| model | reasoning_effort | prompt tok | out tok | of which reasoning | first any token ms | first ANSWER token ms | total ms |
|---|---|---|---|---|---|---|---|
| gpt-oss-20b | default | 331 | 283 | 210 | 476 | 781 | 859 |
| gpt-oss-20b | low | 317 | 55 | 18 | 158 | 209 | 263 |
| gpt-oss-120b | default | 331 | 454 | 371 | 507 | 1296 | 1456 |
| gpt-oss-120b | low | 325 | 92 | 48 | 267 | 377 | 451 |
| qwen3.8-27b | default | 294 | 58 | 0 | 158 | 158 | 269 |

n=1 per cell, so these are directions, not a distribution.

### Limits
| limit | headers (this key) | docs (console.groq.com/docs/rate-limits, fetched 2026-11-09) | confidence now |
|---|---|---|---|
| requests/day | `x-ratelimit-limit-requests: 1000` on all 3 models | RPD 1K | high (both agree) |
| tokens/min | `x-ratelimit-limit-tokens: 8000` on all 3 models | TPM 8K | high (both agree) |
| requests/min | not in headers | RPM 30 | medium, until a 429 shows it |
| tokens/day | not in headers | TPD 200K | medium, until a 429 shows it. Caveat: the page says its table is the "Developer plan" base limits, so it may not be the free tier. The header values match the table, which supports it |
| per model? | each model's `remaining-requests` started at 999 after its own first call | docs: org-level, one row per model | per-model counters for RPD and TPM: high. TPD per model: medium (not visible in headers) |

### Things we could not have guessed
1. **The daily request limit refills continuously, not at midnight.** `x-ratelimit-reset-requests` was `1m26.4s` after 1 request and `2m52.8s` after 2, on both gpt-oss models. 86.4 s = 86 400 s / 1000. So each used request comes back 86.4 s later, like a token bucket. This is inferred from 2 points; confirm with more calls. **Correction (A2):** this is shown for *requests*/day, but *tokens*/day binds first and has no header, so its refill is not measured yet (planned: `tpd` phase on Qwen). Even for requests, one slot every 86.4 s is about 42 requests/hour, roughly 14 questions/hour/model at 3 calls each. So the 3pm reply must estimate when *this person's* answer can run (their queue position × refill time), not just when the next slot opens.
2. **Reasoning dominates cost and first-token time on gpt-oss.** At the default effort, 74% (20b) and 82% (120b) of output tokens were hidden reasoning, and the first answer token came 305 ms / 789 ms after the first token of any kind. `reasoning_effort: low` cut answer-TTFT 3.7× (20b) and 3.4× (120b), and output tokens 5×.
3. **Tokens/day is the binding limit, not requests.** One question ≈ understand ~600 + draft ~3k + check ~1.5k ≈ 5k tokens. 200K TPD / 5k ≈ **40 questions per model per day**, versus 1000 RPD / 3 calls ≈ 333. TPM 8000 / 5k ≈ 1.6 questions per minute per model.

### Unexplained (to check in the TPM phase)
- The first 20b call moved `remaining-tokens` 8000 → 7474 (526) for 331 prompt tokens. It is not prompt + max_tokens (1355). It may be a charge at admission based on Groq's own estimate. Unknown.

### Option (a) test: gate on the rewritten query (cross-encoder, w250, no Groq calls)
| question | raw-question score | rewritten-query score |
|---|---|---|
| vague "explain the main idea… long sequences" (answerable), 20b rewrite | −2.53 | **4.22** |
| same, 120b rewrite | −2.53 | **3.76** |
| "BLEU on English-to-Hindi" (unanswerable), qwen rewrite | 2.17 | **−0.63** |
The rewrite lifts the vague question to the answerable range (3.76 is just under the specific minimum of 3.97) and pushes the trap further down. n=1 vague question, so this is promising, not proven.

### Understand-step risk seen
- 120b-low marked "warmup of the dechunking layer on DNA on TPUs" `in_scope: false`, but the DC paper *has* DNA experiments. If `in_scope=false` skipped retrieval, a partly answerable question would be refused without looking. Retrieval is local and costs no Groq tokens, so **always retrieve**. `in_scope` is a hint, and the gate decides.

## Stage 2a: 2026-11-09 16:19–16:25 IST (10:49–10:55Z), 56 requests, all 200, no 429
Raw: `probe/raw/spread_*_20261109_16*.jsonl`. Summary is recomputable with `analysis/probe_summary.py` → `probe/raw/spread_2a_summary.txt`. All calls use low reasoning effort and distinct questions, run sequentially (unloaded).

| call | n | first ANSWER token p50 / p90 / p95 / max (ms) | total p50 / p95 (ms) | reasoning gap p50 (ms) | answer decode tok/s p50 |
|---|---|---|---|---|---|
| 20b understand (~314 tok in) | 40 | 490 / 578 / 640 / 1245 | 536 / 675 | 64 | (too short to measure, n=7: ~800) |
| 120b understand | 10 | 557 / 742 / 858 / 974 | 649 / 945 | 110 | 571 |
| 120b draft (~2.8k tok in, ~258 out) | 6 | 650 / 700 / 702 / 705 | 1100 / 1408 | 89 | 498 |

p95 at n=40 ≈ the 2nd-slowest call; at n=10/6 the p95 is close to the max and is shown only for shape.

### What it says
1. **The slow tail is real and not explained by the work.** 2 of 40 20b calls took 1140–1245 ms to the first answer token, about 2.4× the median. Their reasoning token counts (49, 71) were normal, and one of them was even a cache hit. The delay is before the first token of *any* kind (1059–1185 ms), so it sits on Groq's side (queueing/prefill), not in reasoning. The stand-in should model this as a rare multiplicative delay **before the first token**.
2. **The prompt cache halves first-token time when it hits.** 7/40 20b calls got `cached_tokens=256` (the shared system prompt): median first answer token **202 ms vs 509 ms** uncached. Hits are intermittent and not under our control (no identical prompts were sent). n=7, so this is indicative.
3. **Prompt size barely matters, output length does.** A 2.8k-token draft prompt reaches its first token only about 100 ms later than a 314-token prompt on 120b (650 vs 557 p50). Total time is driven by decode at about 500 answer tok/s. So in the stand-in: first-token time ≈ base + small per-input-token term; total ≈ first token + out_tokens / ~500.
4. **Reasoning at low effort is a small, steady cost:** 64–110 ms median between the first token of any kind and the first answer token.

### Implication for "fast" (for K's SLO decision, not a decision)
With buffer-then-check (§8), the person's first token comes after the *whole* understand call, retrieval, the *whole* draft and the check. Unloaded medians: 536 (20b understand) + ~200 (BM25 + cross-encoder, measured locally) + 1100 (120b draft total) + check (not yet measured; ≈ 536 if it is a 20b call like understand) ≈ **2.4 s median before any load**. Rough p95 by adding the parts' p95s: 675 + 250 + 1408 + ~675 ≈ **3.0 s**. Adding p95s overstates it, so measure the real pipeline end to end. A "first token < 2 s p95" target is therefore impossible with buffer + check, even unloaded.

## Stage 2b: 2026-11-09 22:00–22:03 IST (16:30–16:33Z), 23 requests, all 200, no 429
Pre-approved by K (same commands as planned; ledger 137 → 160/300). Raw: `probe/raw/spread_short_20261109_220024.jsonl`, `probe/raw/spread_draft_20261109_220214.jsonl`; summary `probe/raw/spread_2b_summary.txt` (`analysis/probe_summary.py` on the 2b files only; the 2a summary was re-run on the 2a files separately and reproduces `spread_2a_summary.txt` exactly). Same settings as 2a: low reasoning effort, sequential, unloaded, **same questions as 2a** (20b: the first 20 of 2a's 40; 120b drafts: 3 of 2a's 6), so the prompt cache can hit.

### 2a vs 2b: INDICATIVE (n = 56 vs 23; one afternoon vs one evening)
| call | 2a 16:19 IST | 2b 22:00 IST |
|---|---|---|
| 20b understand, first answer token, all calls | n=40: p50 490 / p95 640 / max 1245 | n=20: p50 838 / p95 2344 / max 2708 |
| 20b understand, first answer token, **prompt-cache hits excluded** | n=33: p50 509 / p95 593 / max 1140 | n=17: p50 736 / p95 2401 / max 2708 |
| 20b understand, total, cache hits excluded | n=33: p50 547 / p95 642 | n=17: p50 774 / p95 2446 |
| 20b calls > 2× the 2a uncached median (> 1019 ms) | 2/40 (5%) | **9/20 (45%; Wilson 95% CI 26–66%)** |
| 120b draft, first answer token (no cache hits in either) | n=6: p50 650 / max 705 | n=3: p50 704 / max 985 |
| 120b draft, total | n=6: p50 1100 / max 1433 | n=3: p50 1231 / max 1346 |
| prompt-cache hits (20b) | 7/40 | 3/20 |

Paired on the same question (20b, n=20): 2b − 2a median **+279 ms**, slower in 16/20; with both calls uncached (n=15): **+327 ms**, slower in 13/15.

### What it says
1. **At 22:00 IST the 20b slow tail was not rare.** 9/20 calls (vs 2/40 at 16:19) were more than 2× the afternoon median, at **2.5–5.3×** it (vs ~2.4× in 2a). As in 2a, the delay is **before the first token of any kind** (89–100% of the time to first answer token) and reasoning tokens were normal (39–89, median 56), so it is on Groq's side (queueing/prefill), not in the work.
2. **The body moved too, not only the tail:** the 11 calls under the 2× line had median 635 ms vs 509 ms uncached in 2a (+25%).
3. **120b drafts barely changed** (n=3; +54 ms at p50, max 985). Too few calls to say whether 120b escapes the evening slowdown.
4. We can't tell the cause from 20 calls (time of day, a load spike, a regional route). The slow calls are spread through the run (positions 0, 1, 4, 7, 8, 13, 17, 18, 19 of 20), not one burst.
5. Side check: the RPD header read 999 at the first 2b call although 2a used ~45 20b requests today, consistent with the continuous refill of 1 request per 86.4 s (5.5 h ≈ 230 requests refilled).

### Implications (for K's decisions, not decisions)
- **Stand-in calibration:** the rare pre-first-token delay was fitted on 2a (rate 5%, multiplier 2.43×; bracket runs at 2% and 10%). 2b's 45% with 2.5–5.3× multipliers is far outside that bracket. Options: keep the afternoon profile as the baseline and add an "evening" profile (rate and multiplier spread from 2b); or widen the bracket; or fit on 2a+2b pooled. Any of these needs K's call. One evening of n=20 is thin.
- **First-token target (corrected by K):** the *deadline* comes from user patience (DECISIONS §1) and does not change with time of day. What time of day changes is how often the service misses a first-token **target**. So the real end-to-end set runs twice (Tue 2026-11-10 afternoon and ~22:00 IST) to set the first-token target and measure how often each period misses it.

## Qwen 429 tests: 2026-11-09 16:49–16:53 IST, 76 requests (raw: probe/raw/{rpm,tpm,inflight}_20261109_16*.jsonl)
Run on `qwen/qwen3.8-27b` to keep 20b/120b daily tokens for the eval. Its headers showed the same 1000 RPD / 8000 TPM as the gpt-oss models (stage 1).

### What the 429 bodies say (verbatim, org id redacted here; it is in the raw file)
- RPM: `Rate limit reached for model \`qwen/qwen3.8-27b\` in organization \`org_…\` service tier \`on_demand\` on requests per minute (RPM): Limit 30, Used 30, Requested 1. Please try again in 2s.` Header `retry-after: 2`. No `x-ratelimit-remaining-tokens` on the 429.
- Input tokens: `… on input tokens per minute (ITPM): Limit 7000, Used 5880, Requested 5989. Please try again in 41.734285714s.` Header `retry-after: 42`.

### Findings
1. **Per-model vs org: limits are keyed by (organization, model).** Every body names both. Twice, while Qwen was blocked (RPM, then ITPM), one call to gpt-oss-20b succeeded at once. So RPM and ITPM are separate per model: **high**. TPD was not observed, but the same message format and the docs' per-model table point to (org, model) too: **medium-high, not measured**. The "org level" in the docs means org rather than per user or per key, not shared across models.
2. **RPM = 30, measured.** Exactly 30 succeeded, then 429s. **Recovery is about 2 s, not about 60 s:** the first poll after the 429 burst got a 429, and the next one 2.2 s later succeeded. The window refills continuously, at 1 request per 60/30 = 2 s.
3. **A hidden input-token limit: ITPM = 7000, below the 8000 the headers report.** `x-ratelimit-limit-tokens: 8000` is the combined TPM. The 429 was on a separate *input* bucket of 7000/min. The docs mention ITPM/OTPM "if configured on your account". An output-token limit (OTPM) may exist: **not measured**. (8000 − 7000 = 1000 is only arithmetic, not evidence.)
4. **All the limits behave as continuously refilling token buckets, and `retry-after` is exact.** Predicted wait = (used + requested − limit) / (limit/60) = (5880 + 5989 − 7000) / 116.67 = **41.734286 s**. Groq said 41.734285714 s, the same to 6 decimals. With 1 req/2 s for RPM and 1 req/86.4 s for RPD (stage 1), the pattern holds for every limit seen. Consequences:
   - "Time until it recovers" depends on the size of the next request. A 89-token poll got in 0.4 s after the ITPM 429, while another 6k-token request would have waited 42 s.
   - Our limiter can predict a 429 *before* sending (keep our own buckets, synced from the headers) instead of discovering it.
   - Honour `retry-after` as exact, but still add jitter, because many queued requests sharing one retry-after would all wake together.
5. **Requests in flight: 16 at once, no rejections** (1/4/8/16 tiny requests). Median first token 147 → 218 → 183 ms, max 392 at k=16. No concurrency limit is visible below the RPM cap. Beyond 30 per minute the RPM limit hits first, so the in-flight cap can't be tested separately: **medium**.
6. Under a burst at concurrency 10, some first tokens rose from ~130 ms to ~480–494 ms. That is server-side queueing at concurrency, mild, and an input for the stand-in's load slowdown.
7. `x-ratelimit-remaining-requests` was non-monotonic under concurrency (999, 997, 998…), so headers from parallel responses arrive out of order. The limiter must take the minimum, not the latest value.

## Table 1 draft (real service)
| Limit | Value found | How found | Confidence |
|---|---|---|---|
| Requests per minute | 30 per model | 30 OK then 429 "RPM: Limit 30" (Qwen); docs | high |
| Tokens per minute | 8000 total, plus **7000 input** (ITPM) per model; output-token limit: **not measured** | headers `limit-tokens: 8000` (all 3 models); 429 "ITPM: Limit 7000" (Qwen) | high (8000, 7000) |
| Requests per day | 1000 per model, refills 1 per 86.4 s | headers on all 3 models; `reset-requests` 1m26.4s per request used | high (value); medium (refill, 2 points) |
| Tokens per day | 200K per model (docs) | docs table only; never hit (deliberately, see DECISIONS §15) | medium |
| Requests in flight at once | ≥16 with no rejection; RPM binds first | 1/4/8/16 concurrent tiny requests (Qwen) | medium |
| What it returns at a limit | HTTP 429, JSON `error.message` naming model, org, limit type, limit/used/requested, "try again in Xs"; `retry-after` header (whole s) | raw 429 bodies | high |
| Time until it recovers | RPM: ~2 s (1 slot per 2 s). Token limits: (used + req − limit)/(limit/60) s, e.g. 41.7 s for a 6k request, 0.4 s for 89 tokens | recovery polls; formula matches Groq's own figure to 6 decimals | high |
