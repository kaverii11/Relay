# The Relay

A question-answering service over three pinned arXiv papers (Attention Is All You Need 1706.03762v7, Moshi
2410.00037v1, H-Net / Dynamic Chunking 2507.07955v2) on Groq's free tier: gpt-oss-20b rewrites the question and
checks the draft, gpt-oss-120b drafts a cited answer. Every answer quotes the papers word for word and is
checked before it is sent; when the papers don't say, it says so. The write-up is `writeup/writeup.md`; every
decision, with who made it and the measurement behind it, is in `DECISIONS.md`.

## Settings

| | Setting | Where |
|---|---|---|
| **Chosen** (K, DECISIONS §50) | 250-word pieces, 3 pieces, BM25 order (no re-rank), gate cutoff 0.713 | `relay/config.py` `SETTINGS["chosen"]` (= `medium_k3_norerank`; rows carry `w250_k3_rr0`) |
| Load scenarios (Tables 2a / 2b) | 250-word pieces, 6 pieces, cross-encoder re-rank, cutoff 0.875 | `SETTINGS["medium_rerank"]`, the default of `load/loadgen.py` and `eval/e2e.py`, kept so the load tables reproduce (§52) |
| Eval (Table 3) | the two above plus 250 / 6 / BM25 order (0.713) | `eval/run_eval.py` default |

The chosen setting sends ~44 % fewer draft tokens than the load setting, so the load results are pessimistic.

### Versions after the eval (v1 stays the measured baseline)

| Version | Changes on top of the chosen setting | Where |
|---|---|---|
| **v1** | none: the system the tables measure | `SETTINGS["chosen"]`, `Policy()` |
| **v2** (K §51) | (a) each table's caption + header row repeated on every piece of that table, and the drafter told to quote only the paper text after it; (b) the model check must name the table row / column (or sentence) of every number | `SETTINGS["chosen_v2"]`, `Policy(check_prompt="v2", draft_prompt="v2")` |
| **v3** (K §64, §66) | v2 + (c) the understand step's paper hint adds that paper's best BM25 piece when it is missing (append, so nothing is lost); (d) a redraft that repeats a claim the model check rejected fails without a second check | `SETTINGS["chosen_v3a"]`, `Policy(..., sticky_check_fail=True)` |

All three use cutoff 0.713 (re-derived for each on the tuning questions: `eval/v1_v2_recall.py`,
`eval/v3_offline.py`). They are compared on 20 new questions by `eval/run_v1v2.py` (step 12 below).

How v2 and v3 came about (details and dates in DECISIONS §50–§69): after grading the eval, Kaveri chose to fix
the table failures rather than only report them, under her rules: v1 stays the measured baseline, exactly two
changes (v2), tested on new questions. Asking the running system her own question ("What learning rate schedule
does the Transformer use?", `scripts/ask.py`) returned Moshi's Helium schedule as the Transformer's; the two
causes (the Transformer passage ranked 4th of a 3-piece cut, and a redraft that re-rolled a rejected claim until
the checker passed it) became v3, kept as a separate arm so v2 vs v1 and v3 vs v2 are each one pair of changes.

**The 20 follow-up questions** (`eval/k_questions_new.csv`, set `new`, never in the eval/tuning split; the
`author` column names who wrote each): 12 by Kaveri (table questions where the header sits in another piece,
plain-text questions that name no table or paper, a false premise, and two unanswerable traps) and 8 by Claude Code
at her request (three header-split questions, one shared-vocabulary question that tests v3's paper hint, and four
easy baseline facts). Every expected answer was checked against the rendered PDF pages. They were graded blind
(arms hidden, `eval/blind_reading.py`) by Claude Code at Kaveri's request, an exception to her no-LLM-judge rule
for the eval (§67), and re-checked by her. Table 3's eval answers (her 20 held-out questions) were graded by her.

## Setup

```sh
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python library/fetch_papers.py          # the three PDFs at their pinned versions (sha256-checked)
echo "GROQ_API_KEY=..." > .env                     # only for runs against real Groq; never committed
```

Everything that recomputes a table reads files only and makes no network call.

## Ask it a question

```sh
.venv/bin/python scripts/ask.py "How many attention heads does the base Transformer use?"        # plan: gate score, passages, budget; sends nothing
.venv/bin/python scripts/ask.py "How many attention heads does the base Transformer use?" --go   # real Groq (chosen setting)
.venv/bin/python scripts/ask.py "..." --setting chosen_v3a --go                                   # same question on v3
.venv/bin/python scripts/ask.py "..." --go --base-url http://127.0.0.1:8099/v1                   # on the stand-in (start it first)
```

Prints the reply (answer / refusal / couldn't verify / busy), its citations, each check's verdict, first-token time
and tokens; the full event log goes to `raw/ask_<time>.jsonl`. Never touches `results.csv`.
Stand-in: `.venv/bin/uvicorn standin.server:app --port 8099`.

## Recompute every table from results.csv

`results.csv` is the single raw file behind Tables 2a, 2b and 3 (1,237 rows: 9 stand-in load runs, the real
evening end-to-end set, the real eval). One row per request; columns in `relay/service.py` `COLUMNS`.

```sh
.venv/bin/python analysis/tables.py results.csv                 # Tables 2a, 2b, 3 + the load-mix table + footnotes
.venv/bin/python analysis/run_all_summary.py raw/run_all_20261110.txt   # one line per load scenario
.venv/bin/python eval/eval_breakdown.py eval_day1_20261111_124523       # per question x setting; code/model check vs grade
.venv/bin/python eval/check_vs_grade.py eval_day1_20261111_124523       # code-only vs code + model check (§8)
.venv/bin/python analysis/arrival_check.py raw/results_overload_shadow_afternoon_20261111_025926.csv   # false-busy rate
```

`results.csv` itself is rebuilt from the per-run files in `raw/`:

```sh
.venv/bin/python scripts/assemble_results.py \
  raw/results_steady_afternoon_20261110_233137.csv raw/results_burst_afternoon_20261111_003145.csv \
  raw/results_overload_afternoon_20261111_005059.csv raw/results_minute_limit_halved_afternoon_20261111_012058.csv \
  raw/results_daily_exhausted_afternoon_20261111_015059.csv raw/results_burst_evening_20261111_021009.csv \
  raw/results_overload_evening_20261111_022927.csv raw/results_overload_shadow_afternoon_20261111_025926.csv \
  raw/results_minute_limit_halved_nolearn_afternoon_20261111_032925.csv raw/results_e2e_evening_20261110_221128.csv \
  raw/results_eval_day1_20261111_124523.csv
```

Table 1 (limits of the real service) comes from the probe logs, not from `results.csv`: `probe/FINDINGS.md`,
raw calls in `probe/raw/`, summarised by `.venv/bin/python analysis/probe_summary.py probe/raw/<file>.jsonl`.
The offline retrieval tables (piece size, recall, cutoffs): `eval/settings_table.py`, `eval/cutoffs_by_size.py`,
`eval/v1_v2_recall.py` (outputs in `raw/`).

## Run order (what was run, in this order)

Every real-Groq script has `--plan` (prints requests and tokens against the per-model 170k / 24 h ceiling,
sends nothing) and `--go`; each `--go` was approved by K after its plan.

1. **Probe the real service** (`probe/probe_groq.py <phase>`, phases models / stage1 / spread / latency / rpm /
   tpm / inflight): limits, latencies, 429 bodies -> `probe/raw/`, `probe/FINDINGS.md`.
2. **Calibrate the stand-in** from those logs: `standin/calibrate.py` -> `standin/calibration.json` (every
   number labelled measured or assumed; afternoon and evening profiles).
3. **Questions:** `eval/k_questions.csv` (K's 60, split tuning / eval with seed 42, `eval/split.py`);
   `eval/check_questions.py` checks each labelled fact is in the cited page.
4. **Real 20b rewrites** of every question: `eval/rewrites.py --plan / --go` -> `eval/rewrites_20b.json`.
5. **Gate cutoff** on tuning questions only (K's midpoint rule): `eval/gate_report.py`, `eval/cutoffs_by_size.py`.
6. **End-to-end set on real Groq** (12 tuning questions): `eval/e2e.py --plan / --go --tag evening`.
7. **Check replay** (stored drafts + K's corrupted ones through the checker): `eval/replay_checks.py --plan / --go`.
8. **Load scenarios on the stand-in**, sequentially: `sh load/run_all.sh` (starts `standin/server.py`; runs
   steady, burst, overload, minute_limit_halved, daily_exhausted on the afternoon profile, burst and overload
   on the evening profile, overload with the arrival check in shadow mode, halved without limit learning).
9. **Eval on real Groq** (20 held-out questions x 3 settings): `eval/run_eval.py --plan --day 1` then `--go`.
10. **Grading by hand, blinded:** `eval/blind_reading.py <run>` -> `raw/blind_reading_<run>.md` + key;
    `eval/apply_grades.py raw/blind_reading_<run>.md --write` joins the grades back through the key.
11. `scripts/assemble_results.py` (above), then `analysis/tables.py`.
12. **v1 vs v2 vs v3 on 20 new questions** (`eval/k_questions_new.csv`, above): `eval/run_v1v2.py --questions
    eval/k_questions_new.csv --plan` then `--go` (three arms, rotated per question, ITPM-derived spacing; add
    `--base-url ... --spaced` to rehearse on the stand-in); graded blind with step 10's tools. Offline checks first: `eval/header_split.py`, `eval/v1_v2_recall.py`,
    `eval/replay_v2_checks.py`, `eval/v3_offline.py`.
13. **Write-up checks:** `scripts/verify_writeup.py` (every table cell recomputed from results.csv),
    `scripts/check_numbers.py` (every number in the prose has a source), `sh scripts/render_writeup.sh`
    (writeup/writeup.pdf; prints the page count of the writing).

## Guardrails (security, scale, tokens)

What protects the key, the daily budget and the service, and how each one is tested.
`scripts/test_guardrails.py` and `scripts/test_pacing.py` run offline: no tokens, and the real ledger is never touched.

| Risk | Guardrail | Where |
|---|---|---|
| Key leaks | key only in `.env` (gitignored); org id redacted from logs; `check_secrets.sh` before upload | `scripts/` |
| One question costs too much | output caps per call (draft 800, others 400); at most 1 redraft and 2 retries; cache first | `pipeline.py` |
| The day runs out | 170k-of-200k ceiling per model over a rolling 24 h, checked **before** each call, counting calls still in flight | `budget.py` |
| 120b's day goes in the first hour | spend-rate pacing: 120b skipped while its last-5-min spend is > 15 % over (tokens left today ÷ 86,400 s), plus a 5 % hard floor; `pacing_enabled=False` = the measured 20 % reserve. Measured runs pin it off; `analysis/pacing_sim.py` compares both over 24 h (DECISIONS §72) | `limiter.py`, `pipeline.py`, `config.py` |
| Two processes or a crash corrupt the count | ledger locked across processes, written atomically; an unreadable ledger refuses spending (fail closed) | `ledger.py` |
| Hostile or huge input | control characters stripped; empty or > 1,000 characters gets a fixed reply with no model call | `guard.py` |
| Prompt injection | every claim must quote a passage word for word (code check) and pass the 20b check; the worst outcome is a refusal or "couldn't verify", never an unchecked answer | `pipeline.py` |
| Overload | own limiter predicts 429s; deadline turns hopeless waits into a busy reply with an ETA; optional `max_queue` sheds at the door; bounded LRU cache | `limiter.py`, `service.py` |
| Retry storms | retries capped per question and at 10 % of the last minute's requests, with jitter | `pipeline.py`, `limiter.py` |

To run as several instances, the next step is to move the limiter's buckets and the ledger into one shared store
(Redis or Postgres), so every instance spends from the same Groq budget, and to put auth and per-user quotas at
an API gateway. Neither is built: today the service is a library driven by scripts on one machine (DECISIONS §70).

## Layout

| Path | What |
|---|---|
| `relay/` | the service: `pipeline.py` (understand -> retrieve -> decide -> draft -> check, one redraft), `limiter.py` (refill-formula limiter fed by Groq's headers), `retrieval.py` (BM25 + MiniLM cross-encoder), `ingest.py` (section-aware chunks with citations), `prompts.py`, `config.py` (every tunable number), `service.py` (queue, workers, CSV rows), `budget.py` (request caps + 24 h token ceiling), `ledger.py` (locked, atomic ledger file), `guard.py` (input checks) |
| `standin/` | the calibrated fake Groq (same streaming API and 429 bodies) |
| `load/` | load generator, scenarios, the question mix |
| `eval/` | questions, rewrites, gate/cutoff analysis, end-to-end and eval runners, replay, grading tools |
| `analysis/` | tables and summaries, from raw files only |
| `probe/` | real-service probe script, findings, raw logs |
| `raw/` | every run's results, event logs (one JSON line per request with every step), meta files, reading files |
| `scripts/` | `ask.py` (one question), `assemble_results.py`, `relabel_from_events.py`, `verify_writeup.py`, `check_numbers.py`, `render_writeup.sh`, `package.sh` (builds the Drive folder), `redact_org.py`, `check_secrets.sh`, `test_guardrails.py`, `test_pacing.py` (offline tests, no tokens) |
| `library/` | `fetch_papers.py`: the three PDFs at their pinned versions |

The Groq key lives only in `.env` (not committed, not in the submission). `scripts/redact_org.py` replaced the
Groq organization id in the raw logs; `scripts/check_secrets.sh` must print "clean" before upload.
