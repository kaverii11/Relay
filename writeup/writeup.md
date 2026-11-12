# The Relay — write-up

## 1. What I built and why

The Relay answers questions about three papers on Groq's free tier, and says so when the papers are silent. Five steps: gpt-oss-20b turns the question into a query (**understand**); BM25 fetches three 250-word pieces, the tool call (**retrieve**); a MiniLM cross-encoder scores them, and below 0.713 it refuses without calling 120b (**decide**); gpt-oss-120b answers with a verbatim quote behind every claim (**draft**); code confirms each quote is in its passage and 20b judges support; one redraft, then a refusal (**check**). Around it: rate limiters, a deadline queue, a fallback ladder (cache, 20b draft, busy reply).

**The decision that shaped it most:** check the whole draft before sending a token. A token on screen can't be taken back, so a wrong start is worse than a short wait. The price is latency: unloaded first token p50 3.2 s (n=8).

## 2. The real service and my stand-in

**Limits.** Groq's headers advertise 1000 requests/day and 8000 tokens/min, but the limit that binds first is hidden: **7000 input tokens/min**, visible only in 429 bodies. That allows about 2.5 drafts/min per model. Nothing resets at midnight: requests/day refill continuously, like per-minute buckets. The 200k tokens/day is from the docs, refill unmeasured. All per model.

**Stand-in.** Heavy load would exhaust the free tier, so I wrote a stand-in with the same streaming API, calibrated on 56 + 23 unloaded real calls (latency spread, input-size slope, decode speed, slow outliers; afternoon and evening apart). It sends replies in chunks, exercising the pipeline's streaming path, and it fails, slows down and returns Groq-shaped 429s (from Groq's refill formula) on purpose. **Where it differs most:** the slowdown past 16 requests in flight is invented, there is no prompt cache, and its afternoon p95 is ~30 % high (848 vs 640 ms).

## 3. Results

**Real Groq** answered the evening e2e set (12 questions, 34 model calls), the eval (20 × 3 settings, 141 calls) and the v1/v2/v3 follow-up (60 runs, 177 calls); the tables count questions, not calls. The **stand-in** ran every load shape, on 250/6 re-rank. Tables 2a–2b give p50 / p95 / p99 with n, failures and give-ups; first token = total time, as replies are checked whole. Under load the median stays near 1.8 s; the slow end stretches (overload p95 5769 ms, n=114, 34 % got no token).

**A number I couldn't have guessed:** at 0.6× the per-minute ceiling, steady traffic drove 120b's day budget to the 20 % reserve in **41 minutes**. The day binds, not the minute. **Answer quality:** 35.0 % correct and cited on every setting (7/13 answerable), 2052–3503 tokens per question.

## 4. Where the time goes

Take one slow request, `minute_limit_halved-1-0043@nolearn` (stand-in, per-minute limit halved, not learned): **6280 ms**, split from its event log, `raw/events_minute_limit_halved_nolearn_afternoon_20261111_032925.jsonl`:

| | ms | what happened (ms after arrival) |
|---|---|---|
| Working | 1301 | understand 477, draft 570, check 251, failed call 3 |
| Retrying | 1386 | 429 on input tokens/min at 483; retry-after 1 s + jitter, until 1869 |
| Waiting | 3593 | queue 3; our limiter held the draft 3590 (1869→5459) |

All of it came before the first token: nothing is sent until the check passes. Models worked 1301 ms; the rest was waiting. results.csv's limiter_wait_ms (3536) is planned; the log's 3590 adds a 50 ms safety margin and ~4 ms timer overshoot.

## 5. When a limit is hit

A **per-minute** limit frees up soon, so a request waits if its draft can still beat the deadline, and otherwise gets the busy reply at once. A **per-day** limit doesn't, so a daily 429 is never retried: at the 20 % reserve 120b steps aside and 20b (its own quota) drafts; when 20b's day is gone too, the busy reply costs no model call. Answers get **weaker** before anyone is turned away: fewer pieces, then 20b. Nothing is dropped silently, though injected provider failures can still produce errors.

Stand-in, limit halved (70 requests): 11 of 28 answers weaker, 8 delayed, 25 busy, none gave up; past the daily reserve (44): 32 busy at arrival, 4 mid-pipeline, 3 answers from 20b.

## Retrieval: quality versus cost

Three settings on real Groq, 20 questions: 250-word pieces, 6 re-ranked; 6 in BM25 order; 3 in BM25 order. Each got 7/20 right (7/13 answerable); other gaps are 1–2 questions, noise at n=20. Cost differs (Table 3): 5084, 4538 and 2836 tokens per drafted answer. Offline (33 questions), BM25 order matched re-ranking's recall at a third to a seventh of the time.

**Chosen: 250 words, 3 pieces, BM25 order**, for capacity: ~5 drafts/min under the input-token limit vs 2.8. **Near the limit,** the same 3 pieces go to 20b. It uses ~44 % fewer draft tokens than the load runs' 250/6 re-rank, so those are pessimistic.

## How this library will mislead a naive retriever

1. **Tables lose their headers.** Ingest's chart-label filter dropped short-cell table rows. In Q9, two settings gave Moshi's MMLU score as 39.8 from the wrong column, and it passed both checks because the number really is in the passage. In Q15, Transformer Table 3's base row (h = 8) was gone, so drafts took "8" from another row.
2. **Papers share vocabulary.** Q57: one setting gave H-Net's AdamW + WSD as the Transformer's.
3. **False premises.** Q32 asks why H-Net chose N=8 (it uses N0=6, p.11). Two settings never retrieved p.11; the third did and still kept the premise.

## 6. Retries

SDK retries are off, so every retry is a counted decision. Per-minute 429s are retried after retry-after plus up to half again (≥ 0.5 s), 5xx with exponential backoff and full jitter; a per-day 429 never. At most 2 per question, none past the deadline, all within a shared cap of ≤ 10 % of traffic. Timeouts get one retry on short calls (understand, check), never on the draft.

**When retrying made it worse:** with the per-minute limit halved and not learned from the 429 body, blind retries hit 28 input-token 429s instead of 18, and success fell from 64.3 % to 60.0 %. Real Groq: 0 retries in any run (352 model calls).

## 7. What the person sees

At 3 pm, with the daily budget gone, the service makes no more model calls; even the apology would spend tokens that aren't there. The person gets a cached answer to the exact question if there is one, otherwise this template, filled by code:

> I can't give you a checked answer right now: the assistant has hit its {daily | per-minute} usage limit. Capacity for a question like yours should be back in {under a minute | about N min | about N.N h} (around {HH:MM}). I won't send an unchecked answer instead. Please ask again then.

The time is the limiter's longest counter wait, an estimate because the tokens-per-day refill is unmeasured. Timing matters too: turned away at arrival, the reply comes in ~1 ms (n=104); mid-pipeline, only after p50 2.3 s / p95 6.4 s (n=210).

## 8. What I'm unsure about, what I left out, what I learned

**Least certain assumption:** patience, modelled as lognormal with a 15 s median and never measured. If people wait longer, the 8 s deadline throws away answers; if less, the busy reply arrives after they've left.

**Not built:** (1) merging identical in-flight questions: more capacity in bursts, but one failure hits everyone waiting. (2) A clarification turn: vague Q16 and Q59 (tested offline) were silently rewritten toward the Transformer paper; my rubric has no reply type for asking back.

**What was new to me:** debugging hard and still not getting better. v2 fixed the table question it targeted (Q72) but lost Q65 and Q68; v3 never fixed Q80, the failure it was built for; the totals barely moved (9 / 8 / 8 of 20). At n=20 one question is 5 points, so a total can't tell you whether a fix worked: look at which questions it flipped, and decide beforehand what gain would count.

**Gap:** the measured runs had no spend-rate pacing. I built it after the load runs, so it is not measured under load (on by default in the code, off in every measured run). It skips 120b while its last-5-minute spend is over the day's tokens left ÷ 86,400 s by 15 % (5 % floor). In a 24 h replay of steady traffic (DECISIONS §72), 120b drafts rose from 113 to 134 and the 39-minute cliff became a ~8 h run-down, still not even. Steady demand (~2,166 drafts a day) is ~32× what 120b sustains, so ~94 % of drafts land on 20b either way.

## Your feedback on Vaani

**What stood out:** the focus on genuine conversational flow: multilingual code-switching, turn-taking, and Memories that carry context across calls. **What confused me:** "voice AI harness" didn't say whether Vaani is a developer platform, a no-code builder or an enterprise product; the homepage felt crowded. **What I'd change:** the hero, to one clear end-to-end example of building and deploying a voice agent.

## How I worked with the assistant

Claude Code (CC) built and ran everything; a second Claude chat (A2) reviewed my plans and results; Gemini in Google Sheets tidied the wording of my first new questions (Q63–Q71). Both Claude conversations are in `conversations/`, unedited apart from the Groq org id; the Sheets assistant keeps no exportable history.

**Three prompts that mattered.** (1) I told CC the deadline should come from patience, not the time of day, since patience is human, not a server property: one 8 s deadline, two measured latency profiles. (2) I asked A2 about sending overflow to another free-tier account; it cited the brief's ban, so the busy reply became the thing to get right. (3) I told A2 I wanted the table failures fixed, not just reported, which became v2. Later my own question got Helium's schedule back as the Transformer's; I had CC fix both causes and split them into v2 and v3 so each is measured on its own.

**Wrong, and caught:** A2 blamed the rejected table answers on the 12-character quote minimum. When I graded them against the papers, both were simply wrong, so that explanation was dropped.

**Overruled:** after the eval, A2 recommended freezing the system. I fixed it anyway: v2 repeats each table's caption and header in every piece and makes the check name each number's row and column; v3 adds a paper hint and stops a redraft re-rolling a claim the check rejected. On 20 new questions (Table 4) they got 9 / 8 / 8 correct, and Q80, a paraphrase of my failing question kept as a development case, stayed wrong in all three. Neither fix produced a measurable gain at n=20, so v1 stays the default. The run did show that the checker is unstable even at temperature 0 (Q77's "four times", same quote, passed in v1 and v2 and failed in v3; in development the Helium claim behind Q80 went FAIL/OK/FAIL/OK), and dropped table rows cost answers (Q72: wrong in v1, right once v2 restored Table 11's header).

**Distinctly mine:** 55 of the 60 eval questions and 12 of the 20 follow-ups (two unanswerable traps), plus asking for easy baseline questions; blind grading of all 60 eval answers; the 8 s deadline, the midpoint rule behind 0.713, the arrival check and its shadow-mode test; choosing 250/3; finding the table-row bug with my own question; the v2 and v3 rules. At my request CC graded the 60 follow-up answers against the PDFs, an exception to my no-LLM-judge rule; it also wrote 8 of the 20 questions (labelled). I re-checked the 18 disagreements against the papers and reviewed the other 42; none changed.

---

## Results tables (required)

### Table 1: Limits you found in the real service

| Limit | Value you found | How you found it | Confidence (high, medium, low) |
|---|---|---|---|
| Requests per minute | 30 | 429 body "Limit 30" after exactly 30 requests, recovered ~2000 ms later (one slot per 2000 ms); measured on the Qwen model in the same account, gpt-oss-20b/120b per the docs (limits are per model) | high |
| Tokens per minute | 8000 (plus hidden 7000 input tokens/min); output-token limit: not measured | `x-ratelimit-limit-tokens` header; ITPM from a 429 body on draft-sized prompts | high / high |
| Requests per day | 1000 per model | `x-ratelimit-limit-requests` = 1000 on every model; each model's `remaining-requests` started at 999 after its own first call, so the counter is per model; `reset-requests` 1m26.4s per request used, so it refills 1 per 86,400 ms | high (value); medium (refill, 2 points) |
| Tokens per day | 200k per model | docs only; never hit on purpose (planned to 170k) | medium |
| Requests in flight at once | at least 16, no cap found (1 / 4 / 8 / 16 concurrent tiny requests, no rejection; median first token 147 → 218 → 183 ms, max 392 ms at 16) | probe inflight phase (Qwen model); the per-minute limit stopped us before any concurrency limit showed | medium |
| What it returns when a limit is hit | HTTP 429; JSON `error.message` naming model, organization, limit type, limit / used / requested and "try again in X s"; `retry-after` header in whole seconds | raw 429 bodies from deliberate per-minute tests | high |
| Time until it recovers | continuous refill, not a window reset. Requests per minute: ~2 s (one slot per 60/30 s; a poll 2.2 s after the 429 succeeded). Token limits: (used + requested − limit) ÷ (limit/60), e.g. 41,734 ms for a 6k-token request, 400 ms for 89 tokens | recovery polls; the formula matched Groq's own "try again in" figure to 6 decimals (41.734286 vs 41.734285714 s) | high |

### Table 2a: Latency, one row per load scenario

Evaluated on the stand-in (250 words / 6 pieces / re-rank), with real Groq rows at the bottom. Percentiles cover completed replies (format: p50 / p95 / p99, sample size $n$, % receiving no tokens; † = p99 with $n < 100$). Because replies are verified before streaming, first-token time equals total time. Scenarios exceeding the 120b daily budget are split into before and after.

| Scenario | Real or stand-in | Requests sent | Duration (s) | Offered rate (per min) | First token p50 / p95 / p99 (ms) | Total time p50 / p95 / p99 (ms) | Time to busy reply p50 / p95 (ms) |
|---|---|---|---|---|---|---|---|
| steady — before the 120b day budget is gone | stand-in, afternoon | 90 | 2435 | 2.22 | 1870 / 4635 / 6971† (n=86; no token 4.4%) | 1870 / 4635 / 6971† (n=86; no token 4.4%) | 2060 / 4430 (n=4) |
| steady — after the 120b day budget is gone | stand-in, afternoon | 51 | 1074 | 2.85 | 1781 / 5405 / 7493† (n=43; no token 15.7%) | 1781 / 5405 / 7493† (n=43; no token 15.7%) | 1391 / 5660 (n=8) |
| burst | stand-in, afternoon | 86 | 1141 | 4.54 | 1842 / 4626 / 5903† (n=61; no token 29.1%) | 1842 / 4626 / 5903† (n=61; no token 29.1%) | 1 / 4643 (n=25) |
| burst | stand-in, evening | 86 | 1145 | 4.54 | 2748 / 6146 / 7008† (n=51; no token 40.7%) | 2748 / 6146 / 7008† (n=51; no token 40.7%) | 1 / 5655 (n=31) |
| sustained overload — before the 120b day budget is gone | stand-in, afternoon | 172 | 1317 | 7.85 | 1816 / 5769 / 7170 (n=114; no token 33.7%) | 1816 / 5769 / 7170 (n=114; no token 33.7%) | 1955 / 5591 (n=56) |
| sustained overload — after the 120b day budget is gone | stand-in, afternoon | 50 | 471 | 6.36 | 0 / 5180 / 6267† (n=42; no token 16.0%) | 0 / 5180 / 6267† (n=42; no token 16.0%) | 1661 / 6472 (n=8) |
| sustained overload — before the 120b day budget is gone | stand-in, evening | 172 | 1320 | 7.85 | 3044 / 6544 / 7720 (n=120; no token 30.2%) | 3044 / 6544 / 7720 (n=120; no token 30.2%) | 2567 / 6849 (n=46) |
| sustained overload — after the 120b day budget is gone | stand-in, evening | 50 | 471 | 6.36 | 0 / 5629 / 6529† (n=46; no token 8.0%) | 0 / 5629 / 6529† (n=46; no token 8.0%) | 4320 / 6721 (n=4) |
| sustained overload (arrival check in shadow mode) — before the 120b day budget is gone | stand-in, afternoon | 175 | 1340 | 7.85 | 1863 / 5829 / 6779 (n=135; no token 22.9%) | 1863 / 5829 / 6779 (n=135; no token 22.9%) | 1874 / 6551 (n=40) |
| sustained overload (arrival check in shadow mode) — after the 120b day budget is gone | stand-in, afternoon | 47 | 429 | 6.58 | 1 / 3191 / 3350† (n=44; no token 6.4%) | 1 / 3191 / 3350† (n=44; no token 6.4%) | 929 / 3371 (n=3) |
| per-minute limit halved | stand-in, afternoon | 70 | 1789 | 2.35 | 1703 / 3347 / 5623† (n=45; no token 35.7%) | 1703 / 3347 / 5623† (n=45; no token 35.7%) | 2023 / 5744 (n=25) |
| per-minute limit halved (limit not learned) | stand-in, afternoon | 70 | 1789 | 2.35 | 1793 / 3471 / 5985† (n=42; no token 40.0%) | 1793 / 3471 / 5985† (n=42; no token 40.0%) | 802 / 4973 (n=28) |
| daily budget exhausted — before the 120b day budget is gone | stand-in, afternoon | 2 | 56 | 2.29 | 1983 / 3396 / 3522† (n=2; no token 0.0%) | 1983 / 3396 / 3522† (n=2; no token 0.0%) | no busy replies |
| daily budget exhausted — after the 120b day budget is gone | stand-in, afternoon | 44 | 1044 | 2.53 | 1294 / 3742 / 4515† (n=8; no token 81.8%) | 1294 / 3742 / 4515† (n=8; no token 81.8%) | 1 / 1592 (n=36) |
| e2e evening set | real Groq | 12 | 363 | 2.01 | 2642 / 5222 / 5623† (n=12; no token 0.0%) | 2642 / 5222 / 5623† (n=12; no token 0.0%) | no busy replies |
| eval, 250/3 BM25 | real Groq | 20 | 2090 | 0.58 | 1557 / 3561 / 3589† (n=20; no token 0.0%) | 1557 / 3561 / 3589† (n=20; no token 0.0%) | no busy replies |
| eval, 250/6 BM25 | real Groq | 20 | 2088 | 0.58 | 1600 / 3390 / 3548† (n=20; no token 0.0%) | 1600 / 3390 / 3548† (n=20; no token 0.0%) | no busy replies |
| eval, 250/6 re-rank | real Groq | 20 | 1980 | 0.61 | 1760 / 4289 / 4680† (n=20; no token 0.0%) | 1760 / 4289 / 4680† (n=20; no token 0.0%) | no busy replies |
| follow-up, v1 | real Groq | 20 | 1531 | 0.79 | 2429 / 3873 / 4406† (n=20; no token 0.0%) | 2429 / 3873 / 4406† (n=20; no token 0.0%) | no busy replies |
| follow-up, v2 | real Groq | 20 | 1616 | 0.74 | 2613 / 3973 / 4381† (n=20; no token 0.0%) | 2613 / 3973 / 4381† (n=20; no token 0.0%) | no busy replies |
| follow-up, v3 | real Groq | 20 | 1617 | 0.74 | 3088 / 4721 / 5006† (n=20; no token 0.0%) | 3088 / 4721 / 5006† (n=20; no token 0.0%) | no busy replies |

**First-token medians of 0–1 ms are exact-match cache hits, not model answers.** After the 120b day budget is gone, the overload load repeats questions it already asked, and the cache answers them without a model call: 24 of 42 replies with a token (afternoon), 26 of 46 (evening) and 26 of 44 (shadow mode), each in 2.8 ms or less. The 1 ms busy-reply medians are requests turned away by the arrival check.

### Table 2b: Outcomes, same rows

*Definitions:* **Succeeded:** content reply (answer, refusal, or unverified). **Rate-limited:** busy reply. **Errors:** injected stand-in faults. **Tokens/answer:** total tokens ÷ succeeded replies. **Peak queue:** max concurrent waiting requests.

| Scenario | Succeeded % (of which unverified %) | Rate-limited % | Timed out or given up % | Errors % | Retries per request | Peak queue length | Tokens per answer | Cost per 1,000 answers |
|---|---|---|---|---|---|---|---|---|
| steady — before the 120b day budget is gone (stand-in, afternoon) | 95.6 (6.7) | 4.4 | 0.0 | 0.0 | 0.04 | 2 | 2923 | $0 billed (free tier); $0.448 at paid prices |
| steady — after the 120b day budget is gone (stand-in, afternoon) | 84.3 (2.0) | 15.7 | 0.0 | 0.0 | 0.02 | 2 | 2373 | $0 billed (free tier); $0.244 at paid prices |
| burst (stand-in, afternoon) | 70.9 (2.3) | 29.1 | 0.0 | 0.0 | 0.05 | 2 | 2507 | $0 billed (free tier); $0.385 at paid prices |
| burst (stand-in, evening) | 59.3 (1.2) | 36.0 | 0.0 | 4.7 | 0.01 | 2 | 2816 | $0 billed (free tier); $0.426 at paid prices |
| sustained overload — before the 120b day budget is gone (stand-in, afternoon) | 66.3 (1.2) | 32.6 | 0.0 | 1.2 | 0.06 | 2 | 2705 | $0 billed (free tier); $0.392 at paid prices |
| sustained overload — after the 120b day budget is gone (stand-in, afternoon) | 84.0 (0.0) | 16.0 | 0.0 | 0.0 | 0.00 | 1 | 1260 | $0 billed (free tier); $0.134 at paid prices |
| sustained overload — before the 120b day budget is gone (stand-in, evening) | 69.8 (0.0) | 26.7 | 0.6 | 2.9 | 0.02 | 2 | 2543 | $0 billed (free tier); $0.366 at paid prices |
| sustained overload — after the 120b day budget is gone (stand-in, evening) | 92.0 (2.0) | 8.0 | 0.0 | 0.0 | 0.00 | 1 | 1116 | $0 billed (free tier); $0.116 at paid prices |
| sustained overload (arrival check in shadow mode) — before the 120b day budget is gone (stand-in, afternoon) | 77.1 (1.1) | 22.9 | 0.0 | 0.0 | 0.03 | 2 | 2351 | $0 billed (free tier); $0.338 at paid prices |
| sustained overload (arrival check in shadow mode) — after the 120b day budget is gone (stand-in, afternoon) | 93.6 (4.3) | 6.4 | 0.0 | 0.0 | 0.00 | 1 | 995 | $0 billed (free tier); $0.101 at paid prices |
| per-minute limit halved (stand-in, afternoon) | 64.3 (0.0) | 35.7 | 0.0 | 0.0 | 0.07 | 1 | 3135 | $0 billed (free tier); $0.451 at paid prices |
| per-minute limit halved (limit not learned) (stand-in, afternoon) | 60.0 (0.0) | 40.0 | 0.0 | 0.0 | 0.09 | 1 | 3174 | $0 billed (free tier); $0.483 at paid prices |
| daily budget exhausted — before the 120b day budget is gone (stand-in, afternoon) | 100.0 (0.0) | 0.0 | 0.0 | 0.0 | 0.50 | 1 | 1467 | $0 billed (free tier); $0.155 at paid prices |
| daily budget exhausted — after the 120b day budget is gone (stand-in, afternoon) | 18.2 (0.0) | 81.8 | 0.0 | 0.0 | 0.00 | 1 | 1489 | $0 billed (free tier); $0.164 at paid prices |
| e2e evening set (real Groq) | 100.0 (8.3) | 0.0 | 0.0 | 0.0 | 0.00 | 1 | 3442 | $0 billed (free tier); $0.587 at paid prices |
| eval, 250/3 BM25 (real Groq) | 100.0 (5.0) | 0.0 | 0.0 | 0.0 | 0.00 | 1 | 2052 | $0 billed (free tier); $0.341 at paid prices |
| eval, 250/6 BM25 (real Groq) | 100.0 (5.0) | 0.0 | 0.0 | 0.0 | 0.00 | 1 | 3103 | $0 billed (free tier); $0.502 at paid prices |
| eval, 250/6 re-rank (real Groq) | 100.0 (0.0) | 0.0 | 0.0 | 0.0 | 0.00 | 1 | 3503 | $0 billed (free tier); $0.577 at paid prices |
| follow-up, v1 (real Groq) | 100.0 (0.0) | 0.0 | 0.0 | 0.0 | 0.00 | 1 | 2992 | $0 billed (free tier); $0.519 at paid prices |
| follow-up, v2 (real Groq) | 100.0 (5.0) | 0.0 | 0.0 | 0.0 | 0.00 | 1 | 3511 | $0 billed (free tier); $0.580 at paid prices |
| follow-up, v3 (real Groq) | 100.0 (15.0) | 0.0 | 0.0 | 0.0 | 0.00 | 1 | 3718 | $0 billed (free tier); $0.632 at paid prices |

### Table 3: Retrieval settings (at least three)

| Setting (piece size, pieces fetched, re-rank yes or no) | Questions asked | Correct and cited % | Wrong % | Correctly refused % | Tokens per answer | First token p50 / p95 (ms) | Total time p50 / p95 (ms) |
|---|---|---|---|---|---|---|---|
| 250 words, 6 pieces, re-rank (cutoff 0.875) | 20 | 35.0 (7/13 of answerable) | 20.0 | 30.0 | 3503 per question (n=20); 5084 per drafted answer (n=10) | 1760 / 4289 (n=20) | 1760 / 4289 (n=20) |
| 250 words, 6 pieces, BM25 order (0.713) | 20 | 35.0 (7/13) | 10.0 | 30.0 | 3103 (n=20); 4538 (n=8) | 1600 / 3390 (n=20) | 1600 / 3390 (n=20) |
| **250 words, 3 pieces, BM25 order (0.713) — chosen** | 20 | 35.0 (7/13) | 15.0 | 30.0 | 2052 (n=20); 2836 (n=9) | 1557 / 3561 (n=20) | 1557 / 3561 (n=20) |

*Notes:*

- **False refusals:** 15.0% / 25.0% / 20.0% across rows. With $n = 20$ (13 answerable, 7 unanswerable), each question is 5.0%, making 1–2 question differences noise. "Wrong" includes one false-premise question answered with a refusal per rubric.
- **Grading:** Blind, hand-graded by K on shuffled outputs (setting names obscured; 3-piece entries recognisable by their passage count). All run on the same 20 questions in one session (12:45–13:21 IST).
- **Chunk sizes (120 / 250 / 500 words):** Evaluated offline via recall@k on 33 tuning questions (not run on Groq). Timings reflect afternoon measurements.
- **Latency & pricing:** Latency excludes planned limiter waits. List pricing: $0.15 in / $0.60 out per 1M tokens for `gpt-oss-120b`; $0.075 / $0.30 for `gpt-oss-20b` (as of 2026-11-09). Actual cost: $0 (free tier).

### Table 4: v1 / v2 / v3 on 20 follow-up questions (real Groq, 12 Nov 13:30–13:58 IST)

| Version | Questions | Correct | Wrong | Refused correctly | Refused wrongly | Correct without the development case; that case | Tokens per question; per drafted answer | First token p50 / p95 (ms) |
|---|---|---|---|---|---|---|---|---|
| v1 | 20 | 9 (45.0%) | 7 | 1 | 3 | 9/19; Q80 wrong | 2992 (n=20); 3312 (n=14) | 2429 / 3873 (n=20) |
| v2 | 20 | 8 (40.0%) | 7 | 1 | 4 | 8/19; Q80 wrong | 3511 (n=20); 3898 (n=13) | 2613 / 3973 (n=20) |
| v3 | 20 | 8 (40.0%) | 5 | 1 | 6 | 8/19; Q80 wrong | 3718 (n=20); 4132 (n=12) | 3088 / 4721 (n=20) |

*Notes:*

- **Versions:** v1 = the measured chosen system (250/3 BM25, cutoff 0.713). v2 = v1 + table caption and header on every table piece + a check that names each number's row and column. v3 = v2 + the understand step's paper hint (one extra piece) + a redraft may not repeat a quote the check rejected. All three on the same 20 questions, arms rotated per question, answer cache off, pacing off.
- **Questions:** 12 written by K, 8 by CC (labelled in `eval/k_questions_new.csv`): 10 table look-ups, 3 implicit, 2 false premise, 1 not in the papers, 4 easy baselines. Q80 paraphrases the failure v3 was built on, so it is a development case, not held out.
- **Grading:** by CC at K's request, against the PDFs, on a shuffled file with version names hidden; an exception to K's no-LLM-judge rule. Not fully blind: CC had seen the run's console log (reply kind per question and version), and v3 entries show four passages. False premise answered with a plain refusal = wrong (§6). One question = 5.0 points, so 1–2 question differences are noise.
