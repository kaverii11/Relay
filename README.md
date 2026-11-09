# The Relay: what we're building, why, and where it stands

*Plain-language guide for Kaveri. Last updated Tue 10 Nov 2026. Deadline: **Fri 13 Nov, 1:47 PM IST**.*

---

## 1. The assignment in one paragraph

Build a small question-answering service over **three arXiv papers**: Transformer, Moshi and H-Net, at exact pinned versions. Every answer must **cite** the paper, section and page it came from. When the papers don't contain the answer, it must say **"the papers don't say"** instead of guessing. The service runs on **Groq's free tier**, which has strict rate limits. The real test isn't the answers; it's **how the service behaves when it is busy, slow or out of budget**. We measure that under 5 load scenarios and report it in fixed tables and a 2-page write-up.

---

## 2. What happens when someone asks a question

```
question
  │
  ├─ [0] cache: asked before (exact same text)? → reuse that answer
  ├─ busy check at arrival: will the big model have room in time? if not → "busy, try in N s"
  │
  ├─ [1] UNDERSTAND (small model, 20b): rewrite the question into a good search query
  ├─ [2] RETRIEVE (the "tool"): BM25 search → cross-encoder re-ranks → top passages
  ├─ [3] DECIDE (branch):
  │       • passages score below the cutoff → "the papers don't say" (no model call)
  │       • big model too busy → fall down the ladder:
  │             fewer passages → small model → busy reply
  ├─ [4] DRAFT (big model, 120b): answer using ONLY the passages, with [C#] citations + quotes
  └─ [5] CHECK: code checks every quote really appears in its passage, and the
          small model checks the answer is supported → if not, redraft once (the loop)
```

That covers the brief: **≥4 steps, a tool call (retrieval), a branch (the decide step), a loop (redraft)**.

**Why two models?** Each model has its *own* rate limits on Groq, which we measured: the 429 errors name the model. The big model (120b) is the bottleneck because draft prompts are large (~2.8k tokens). So the cheap steps go on the small model (20b), and the big one is saved for drafting.

---

## 3. What we measured on real Groq (and why it matters)

Free tier, for each model separately:

| Limit | Value | How we know |
|---|---|---|
| Requests per minute | 30 | measured (got the 429) |
| Input tokens per minute | **7000** | measured; **it isn't in the headers**, only in the 429 message |
| Tokens per minute | 8000 | header |
| Requests per day | 1000 | header |
| Tokens per day | 200k | Groq docs only (never hit it; you didn't approve that test) |

- **Limits refill continuously**, not in one jump every minute. Groq's "try again in X s" matched our formula to 6 decimals.
- **The ceiling** is about **2.5 drafts per minute** on 120b (7000 ÷ ~2.8k tokens). Every scenario is defined as a multiple of this number.
- **Speed** (low reasoning effort):
  - 20b understand: ~0.5 s.
  - 120b draft: ~1.1 s in total.
  - About **2.4 s from question to answer, with no load**.
- **Time of day matters a lot** (stage 2b, last night):

| | 16:19 IST (afternoon) | 22:00 IST (evening) |
|---|---|---|
| 20b first token, median | 490 ms | 838 ms |
| 20b first token, p95 | 640 ms | 2344 ms |
| share of "slow" calls | 2/40 (5%) | **9/20 (45%)** |

Details: `probe/FINDINGS.md`. Every number has a raw file behind it in `probe/raw/`.

**Real-request ledger:** **160 of 300** used. The cap is ours, to stay well inside Groq's free tier.

---

## 4. The stand-in (fake Groq) and why we need it

We can't overload real Groq for hours: it would burn the free budget and break their terms. So `standin/server.py` is a **fake Groq that behaves like the measured one**:
- same limits and same 429 messages;
- streams tokens;
- has slow calls, errors and mid-stream stalls;
- gets slower under load.

Every number it uses comes from `standin/calibration.json`, built from the real probe logs, and each one is labelled **measured** or **assumed**.

It has two **profiles** (your decision):
- **afternoon**: fitted to the 16:19 run, n=40;
- **evening**: fitted to the 22:00 run, n=20 (thin).

Known differences from real Groq (they go in the write-up):
- How it behaves beyond 16 requests in flight is assumed.
- Prompt caching isn't modelled.
- Its afternoon p95 is ~30% too slow.
- Load variants are searched as raw text, so it gives more refusals than the real thing would.

---

## 5. The 5 load scenarios

| Scenario | What it simulates |
|---|---|
| steady | normal day: 0.6× the ceiling for 60 min |
| burst | an incident: 40 questions in 30 s, many asking the same few things |
| overload | 2× the ceiling for 30 min |
| minute_limit_halved | Groq quietly halves the input limit (7000 → 3500); we're not told, so we learn it from the 429s |
| daily_exhausted | 3 pm: the big model's daily budget is gone; the small one has a little left |

- **Arrivals are "open loop":** people keep arriving whether or not earlier ones got answers, like real users.
- **Each person has a patience timer.** When it runs out they leave, and we stop spending tokens on them.
- **The rates are set on *draft* demand,** not questions, because refusals and cache hits need no draft (your decision).

`load/run_all.sh` runs everything **one after another** (never in parallel), about 4.5 h:
- all 5 scenarios under the afternoon profile;
- burst and overload again under the evening profile;
- overload in shadow mode;
- halved without learning.

**Not started yet:** it needs the decisions below.

---

## 6. What the results look like

Every request becomes one row in `results.csv`: the brief's 12 columns, plus extras such as waiting times, per-model tokens and the busy path. **Every table is recomputed from that file alone** by `analysis/tables.py`, so a reviewer can check any cell.

- **Table 1:** the real limits (above).
- **Table 2a:** latency per scenario (first token and total; p50, p95 and p99).
- **Table 2b:** outcomes: succeeded / rate-limited / gave up, retries, peak queue, tokens and cost per answer.
- **Table 3:** answer quality per retrieval setting, graded by you, on real Groq.

Your percentile rule: computed over **all** requests; a request with no answer counts as infinitely slow.

---

## 7. Where we are right now

**Done and pushed** (code only; `.md` notes and raw data stay local):
- papers fetched and checked;
- section-aware chunking;
- the full pipeline;
- the rate limiter;
- the stand-in with two profiles;
- the load generator;
- the tables;
- the arrival-time busy check;
- learning limits from 429s;
- the question-file format and checker.

**Your turn (today, Tue 10 Nov):**
1. **Write `eval/k_questions.csv`**: eval + tuning questions, 11 columns (see `eval/k_questions_template.csv`). Then run:
   `.venv/bin/python eval/check_questions.py`
   It checks your `must_include` against the cited PDF page, and shows where your searched terms appear.
2. **Send me your eight question-type names**, so the checker can reject typos.

**Then, in order:**

| # | Step | Uses Groq? | Who decides |
|---|---|---|---|
| 1 | I push your questions file | no | – |
| 2 | Real 20b rewrites of your questions + 5 "Quick question:" probes | ~60 calls, `--plan` first | you approve |
| 3 | Gate-cutoff tuning on the rewritten queries (`eval/gate_report.py`) | no | **you pick the cutoff** |
| 4 | I write the reworded load variants; you spot-check 10 | no | you |
| 5 | End-to-end set, **Tue afternoon** | ~30 calls, `--plan` first | you approve |
| 6 | End-to-end set, **Tue ~22:00** | ~30 calls, `--plan` first | you approve |
| 7 | You set: first-token target, deadline (from patience), X (% unanswerable), Y (% burst repeats), hot-set size, single-flight yes/no | no | **you** |
| 8 | `run_all.sh` overnight | no (stand-in) | – |
| 9 | Eval / Table 3 on real Groq, results.csv, tables, write-up, Drive upload | yes, within budget | you grade |

**Watch-out:** the ledger worst case gets close to 300 after steps 2, 5 and 6. I'll flag it with each `--plan`.

---

## 8. Decisions still open (all yours)

- **Gate cutoff:** how sure retrieval must be before answering (now 3.0, a placeholder).
- **Deadline:** when we give up and send the busy reply. It comes from user patience (now 10 s placeholder; you said that's too late).
- **First-token target:** set from the two end-to-end runs.
- **X / Y / hot-set size:** the load mix.
- **Single-flight:** should identical questions that arrive at the same moment share one answer? I recommended trying it behind a flag. You decide before `run_all.sh`.
- **Check mode / medium-effort check test:** decided later, from eval data.

---

## 9. Where to find things

| What | Where |
|---|---|
| The papers | `papers/*.pdf` |
| Every decision, who made it and why | `DECISIONS.md` (§1–26) |
| Real Groq measurements | `probe/FINDINGS.md`, raw data in `probe/raw/` |
| Pipeline code | `relay/` (pipeline, limiter, retrieval, prompts, config) |
| Fake Groq | `standin/` |
| Load scenarios and runner | `load/` |
| Your questions, checker, rewrites, gate report | `eval/` |
| Tables from results.csv | `analysis/tables.py` |
| All tunable numbers | `relay/config.py` (PLACEHOLDER = not decided yet) |

**Rules we keep:**
- The Groq key lives only in `.env` and is never committed.
- The org id is redacted.
- Commits are in your name.
- I show `--plan` before every real Groq run, and you approve it.
- Scenarios never run in parallel.
- No numbers are chosen before they're measured.
