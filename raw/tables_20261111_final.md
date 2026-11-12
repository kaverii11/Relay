
Table 2a: latency (ms). Percentiles over requests that got a reply; no-token share of all requests in the cell
| Scenario | Real or stand-in | Setting | Requests sent | Duration (s) | Offered rate (per min) | First token p50 / p95 / p99 (ms) | Total time p50 / p95 / p99 (ms) | Time to busy reply p50 / p95 (ms) |
|---|---|---|---|---|---|---|---|---|
| burst | stand-in, afternoon (2a, n=40) | w250_k6_rr1 | 86 | 1141 | 4.54 | 1842 / 4626 / 5903† (n=61; no token 29.1%) | 1842 / 4626 / 5903† (n=61; no token 29.1%) | 1 / 4643 (n=25) |
| burst | stand-in, evening (2b, n=20) | w250_k6_rr1 | 86 | 1145 | 4.54 | 2748 / 6146 / 7008† (n=51; no token 40.7%) | 2748 / 6146 / 7008† (n=51; no token 40.7%) | 1 / 5655 (n=31) |
| daily_exhausted (after 120b day budget gone) | stand-in, afternoon (2a, n=40) | w250_k6_rr1 | 44 | 1044 | 2.53 | 1294 / 3742 / 4515† (n=8; no token 81.8%) | 1294 / 3742 / 4515† (n=8; no token 81.8%) | 1 / 1592 (n=36) |
| daily_exhausted (before 120b day budget gone) | stand-in, afternoon (2a, n=40) | w250_k6_rr1 | 2 | 56 | 2.29 | 1983 / 3396 / 3522† (n=2; no token 0.0%) | 1983 / 3396 / 3522† (n=2; no token 0.0%) | no busy replies |
| e2e [evening] | groq | w250_k6_rr1 | 12 | 363 | 2.01 | 2642 / 5222 / 5623† (n=12; no token 0.0%) | 2642 / 5222 / 5623† (n=12; no token 0.0%) | no busy replies |
| eval [day1] | groq | w250_k3_rr0 | 20 | 2090 | 0.58 | 1557 / 3561 / 3589† (n=20; no token 0.0%) | 1557 / 3561 / 3589† (n=20; no token 0.0%) | no busy replies |
| eval [day1] | groq | w250_k6_rr0 | 20 | 2088 | 0.58 | 1600 / 3390 / 3548† (n=20; no token 0.0%) | 1600 / 3390 / 3548† (n=20; no token 0.0%) | no busy replies |
| eval [day1] | groq | w250_k6_rr1 | 20 | 1980 | 0.61 | 1760 / 4289 / 4680† (n=20; no token 0.0%) | 1760 / 4289 / 4680† (n=20; no token 0.0%) | no busy replies |
| minute_limit_halved | stand-in, afternoon (2a, n=40) | w250_k6_rr1 | 70 | 1789 | 2.35 | 1703 / 3347 / 5623† (n=45; no token 35.7%) | 1703 / 3347 / 5623† (n=45; no token 35.7%) | 2023 / 5744 (n=25) |
| minute_limit_halved [nolearn] | stand-in, afternoon (2a, n=40) | w250_k6_rr1 | 70 | 1789 | 2.35 | 1793 / 3471 / 5985† (n=42; no token 40.0%) | 1793 / 3471 / 5985† (n=42; no token 40.0%) | 802 / 4973 (n=28) |
| overload (after 120b day budget gone) | stand-in, afternoon (2a, n=40) | w250_k6_rr1 | 50 | 471 | 6.36 | 0 / 5180 / 6267† (n=42; no token 16.0%) | 0 / 5180 / 6267† (n=42; no token 16.0%) | 1661 / 6472 (n=8) |
| overload (after 120b day budget gone) | stand-in, evening (2b, n=20) | w250_k6_rr1 | 50 | 471 | 6.36 | 0 / 5629 / 6529† (n=46; no token 8.0%) | 0 / 5629 / 6529† (n=46; no token 8.0%) | 4320 / 6721 (n=4) |
| overload (before 120b day budget gone) | stand-in, afternoon (2a, n=40) | w250_k6_rr1 | 172 | 1317 | 7.85 | 1816 / 5769 / 7170 (n=114; no token 33.7%) | 1816 / 5769 / 7170 (n=114; no token 33.7%) | 1955 / 5591 (n=56) |
| overload (before 120b day budget gone) | stand-in, evening (2b, n=20) | w250_k6_rr1 | 172 | 1320 | 7.85 | 3044 / 6544 / 7720 (n=120; no token 30.2%) | 3044 / 6544 / 7720 (n=120; no token 30.2%) | 2567 / 6849 (n=46) |
| overload [shadow] (after 120b day budget gone) | stand-in, afternoon (2a, n=40) | w250_k6_rr1 | 47 | 429 | 6.58 | 1 / 3191 / 3350† (n=44; no token 6.4%) | 1 / 3191 / 3350† (n=44; no token 6.4%) | 929 / 3371 (n=3) |
| overload [shadow] (before 120b day budget gone) | stand-in, afternoon (2a, n=40) | w250_k6_rr1 | 175 | 1340 | 7.85 | 1863 / 5829 / 6779 (n=135; no token 22.9%) | 1863 / 5829 / 6779 (n=135; no token 22.9%) | 1874 / 6551 (n=40) |
| steady (after 120b day budget gone) | stand-in, afternoon (2a, n=40) | w250_k6_rr1 | 51 | 1074 | 2.85 | 1781 / 5405 / 7493† (n=43; no token 15.7%) | 1781 / 5405 / 7493† (n=43; no token 15.7%) | 1391 / 5660 (n=8) |
| steady (before 120b day budget gone) | stand-in, afternoon (2a, n=40) | w250_k6_rr1 | 90 | 2435 | 2.22 | 1870 / 4635 / 6971† (n=86; no token 4.4%) | 1870 / 4635 / 6971† (n=86; no token 4.4%) | 2060 / 4430 (n=4) |

Table 2b: outcomes
| Scenario | Succeeded % | (of which unverified %) | Rate-limited % | Timed out or given up % | (error %) | Retries per request | Peak queue length | Tokens per answer | Cost per 1,000 answers |
|---|---|---|---|---|---|---|---|---|---|
| burst (stand-in, afternoon (2a, n=40)) | 70.9 | 2.3 | 29.1 | 0.0 | 0.0 | 0.05 | 2 | 2507 | $0 billed (free tier); paid on-demand: $0.385 all-in [drafted $0.421, refusals $0.044, unverified $1.073; refusal share 23.0%] |
| burst (stand-in, evening (2b, n=20)) | 59.3 | 1.2 | 36.0 | 0.0 | 4.7 | 0.01 | 2 | 2816 | $0 billed (free tier); paid on-demand: $0.426 all-in [drafted $0.455, refusals $0.039, unverified $1.099; refusal share 31.4%] |
| daily_exhausted (after 120b day budget gone) (stand-in, afternoon (2a, n=40)) | 18.2 | 0.0 | 81.8 | 0.0 | 0.0 | 0.00 | 1 | 1489 | $0 billed (free tier); paid on-demand: $0.164 all-in [drafted $0.242, refusals $0.041, unverified n/a; refusal share 62.5%] |
| daily_exhausted (before 120b day budget gone) (stand-in, afternoon (2a, n=40)) | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.50 | 1 | 1467 | $0 billed (free tier); paid on-demand: $0.155 all-in [drafted $0.259, refusals $0.051, unverified n/a; refusal share 50.0%] |
| e2e [evening] (groq) | 100.0 | 8.3 | 0.0 | 0.0 | 0.0 | 0.00 | 1 | 3442 | $0 billed (free tier); paid on-demand: $0.587 all-in [drafted $0.711, refusals $0.177, unverified $0.825; refusal share 25.0%] |
| eval [day1] (groq) | 100.0 | 5.0 | 0.0 | 0.0 | 0.0 | 0.00 | 1 | 2052 | $0 billed (free tier); paid on-demand: $0.341 all-in [drafted $0.469, refusals $0.187, unverified $0.718; refusal share 50.0%] |
| eval [day1] (groq) | 100.0 | 5.0 | 0.0 | 0.0 | 0.0 | 0.00 | 1 | 3103 | $0 billed (free tier); paid on-demand: $0.502 all-in [drafted $0.732, refusals $0.306, unverified $0.809; refusal share 55.0%] |
| eval [day1] (groq) | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.00 | 1 | 3503 | $0 billed (free tier); paid on-demand: $0.577 all-in [drafted $0.860, refusals $0.294, unverified n/a; refusal share 50.0%] |
| minute_limit_halved (stand-in, afternoon (2a, n=40)) | 64.3 | 0.0 | 35.7 | 0.0 | 0.0 | 0.07 | 1 | 3135 | $0 billed (free tier); paid on-demand: $0.451 all-in [drafted $0.470, refusals $0.044, unverified n/a; refusal share 37.8%] |
| minute_limit_halved [nolearn] (stand-in, afternoon (2a, n=40)) | 60.0 | 0.0 | 40.0 | 0.0 | 0.0 | 0.09 | 1 | 3174 | $0 billed (free tier); paid on-demand: $0.483 all-in [drafted $0.536, refusals $0.042, unverified n/a; refusal share 40.5%] |
| overload (after 120b day budget gone) (stand-in, afternoon (2a, n=40)) | 84.0 | 0.0 | 16.0 | 0.0 | 0.0 | 0.00 | 1 | 1260 | $0 billed (free tier); paid on-demand: $0.134 all-in [drafted $0.138, refusals $0.017, unverified n/a; refusal share 23.8%] |
| overload (after 120b day budget gone) (stand-in, evening (2b, n=20)) | 92.0 | 2.0 | 8.0 | 0.0 | 0.0 | 0.00 | 1 | 1116 | $0 billed (free tier); paid on-demand: $0.116 all-in [drafted $0.113, refusals $0.021, unverified $0.365; refusal share 21.7%] |
| overload (before 120b day budget gone) (stand-in, afternoon (2a, n=40)) | 66.3 | 1.2 | 32.6 | 0.0 | 1.2 | 0.06 | 2 | 2705 | $0 billed (free tier); paid on-demand: $0.392 all-in [drafted $0.406, refusals $0.040, unverified $0.468; refusal share 38.6%] |
| overload (before 120b day budget gone) (stand-in, evening (2b, n=20)) | 69.8 | 0.0 | 26.7 | 0.6 | 2.9 | 0.02 | 2 | 2543 | $0 billed (free tier); paid on-demand: $0.366 all-in [drafted $0.391, refusals $0.040, unverified n/a; refusal share 35.8%] |
| overload [shadow] (after 120b day budget gone) (stand-in, afternoon (2a, n=40)) | 93.6 | 4.3 | 6.4 | 0.0 | 0.0 | 0.00 | 1 | 995 | $0 billed (free tier); paid on-demand: $0.101 all-in [drafted $0.096, refusals $0.020, unverified $0.440; refusal share 25.0%] |
| overload [shadow] (before 120b day budget gone) (stand-in, afternoon (2a, n=40)) | 77.1 | 1.1 | 22.9 | 0.0 | 0.0 | 0.03 | 2 | 2351 | $0 billed (free tier); paid on-demand: $0.338 all-in [drafted $0.393, refusals $0.041, unverified $0.547; refusal share 37.0%] |
| steady (after 120b day budget gone) (stand-in, afternoon (2a, n=40)) | 84.3 | 2.0 | 15.7 | 0.0 | 0.0 | 0.02 | 2 | 2373 | $0 billed (free tier); paid on-demand: $0.244 all-in [drafted $0.301, refusals $0.043, unverified $0.385; refusal share 30.2%] |
| steady (before 120b day budget gone) (stand-in, afternoon (2a, n=40)) | 95.6 | 6.7 | 4.4 | 0.0 | 0.0 | 0.04 | 2 | 2923 | $0 billed (free tier); paid on-demand: $0.448 all-in [drafted $0.562, refusals $0.042, unverified $1.080; refusal share 33.7%] |

Load mix (extra, K §22): question rate vs draft demand, from results.csv
| Scenario | Questions/min | Drafts/min (reached the draft) | Drafts / ceiling (2.5) | Refusals % (fresh) | Unverified % | Cache hits % | Busy % |
|---|---|---|---|---|---|---|---|
| burst (stand-in, afternoon (2a, n=40)) | 4.54 | 2.06 | 0.82x | 16.3 | 2.3 | 15.1 | 29.1 |
| burst (stand-in, evening (2b, n=20)) | 4.54 | 2.06 | 0.82x | 16.3 | 1.2 | 10.5 | 36.0 |
| daily_exhausted (after 120b day budget gone) (stand-in, afternoon (2a, n=40)) | 2.53 | 0.23 | 0.09x | 11.4 | 0.0 | 0.0 | 81.8 |
| daily_exhausted (before 120b day budget gone) (stand-in, afternoon (2a, n=40)) | 2.29 | 1.14 | 0.46x | 50.0 | 0.0 | 0.0 | 0.0 |
| e2e [evening] (groq) | 2.01 | 1.67 | 0.67x | 25.0 | 8.3 | 0.0 | 0.0 |
| eval [day1] (groq) | 0.58 | 0.46 | 0.18x | 50.0 | 5.0 | 0.0 | 0.0 |
| eval [day1] (groq) | 0.58 | 0.46 | 0.18x | 55.0 | 5.0 | 0.0 | 0.0 |
| eval [day1] (groq) | 0.61 | 0.49 | 0.19x | 50.0 | 0.0 | 0.0 | 0.0 |
| minute_limit_halved (stand-in, afternoon (2a, n=40)) | 2.35 | 1.71 | 0.69x | 24.3 | 0.0 | 0.0 | 35.7 |
| minute_limit_halved [nolearn] (stand-in, afternoon (2a, n=40)) | 2.35 | 1.78 | 0.71x | 24.3 | 0.0 | 0.0 | 40.0 |
| overload (after 120b day budget gone) (stand-in, afternoon (2a, n=40)) | 6.36 | 2.29 | 0.92x | 8.0 | 0.0 | 48.0 | 16.0 |
| overload (after 120b day budget gone) (stand-in, evening (2b, n=20)) | 6.36 | 2.29 | 0.92x | 10.0 | 2.0 | 52.0 | 8.0 |
| overload (before 120b day budget gone) (stand-in, afternoon (2a, n=40)) | 7.85 | 4.47 | 1.79x | 23.8 | 1.2 | 5.8 | 32.6 |
| overload (before 120b day budget gone) (stand-in, evening (2b, n=20)) | 7.85 | 4.61 | 1.84x | 23.3 | 0.0 | 5.8 | 26.7 |
| overload [shadow] (after 120b day budget gone) (stand-in, afternoon (2a, n=40)) | 6.58 | 1.96 | 0.78x | 10.6 | 4.3 | 55.3 | 6.4 |
| overload [shadow] (before 120b day budget gone) (stand-in, afternoon (2a, n=40)) | 7.85 | 4.40 | 1.76x | 26.3 | 1.1 | 8.0 | 22.9 |
| steady (after 120b day budget gone) (stand-in, afternoon (2a, n=40)) | 2.85 | 1.90 | 0.76x | 25.5 | 2.0 | 0.0 | 15.7 |
| steady (before 120b day budget gone) (stand-in, afternoon (2a, n=40)) | 2.22 | 1.50 | 0.60x | 32.2 | 6.7 | 0.0 | 4.4 |

Table 3: retrieval settings (real Groq, graded rows only)
| Setting | Questions asked | Correct and cited % | Correct of answerable | Wrong % | Correctly refused % | (Refused wrongly %) | Tokens per question | Tokens per drafted answer | First token p50 / p95 (ms) | Total time p50 / p95 (ms) | Limiter wait p50 / max (ms) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| w250_k3_rr0 | 20 | 35.0 | 7/13 | 15.0 | 30.0 | 20.0 | 2052 (n=20) | 2836 (n=9) | 1557 / 3561 (n=20) | 1557 / 3561 (n=20) | 0 / 0 (n=20) |
| w250_k6_rr0 | 20 | 35.0 | 7/13 | 10.0 | 30.0 | 25.0 | 3103 (n=20) | 4538 (n=8) | 1600 / 3390 (n=20) | 1600 / 3390 (n=20) | 0 / 0 (n=20) |
| w250_k6_rr1 | 20 | 35.0 | 7/13 | 20.0 | 30.0 | 15.0 | 3503 (n=20) | 5084 (n=10) | 1760 / 4289 (n=20) | 1760 / 4289 (n=20) | 0 / 0 (n=20) |

Table 3: n = 20 questions per setting (13 answerable, 7 not), one run each, graded by hand from a blinded copy. One question is 5.0 percentage points, so differences of 1-2 questions between settings are noise.

Prices: Groq on-demand, USD per 1M tokens: gpt-oss-120b $0.15 in / $0.60 out; gpt-oss-20b $0.075 in / $0.30 out. Source: https://console.groq.com/docs/model/openai/gpt-oss-120b and https://console.groq.com/docs/model/openai/gpt-oss-20b, read 2026-11-09 (pages show no date). Older Groq posts list different output prices (K: $0.75 / $0.50); the console pages are used. Reasoning tokens billed as output. Cached input priced at the full input rate.
† p99 with n < 100: the top value or next to it, not a stable estimate (K).
Stand-in evening profile: fitted on 20b only (n=20 short calls); its 120b values are n=3 or borrowed from the afternoon profile (standin/calibration.json).
Arrival check expected work 3.2 s: DERIVED from the evening e2e set's answers-only first-token p50 (n=8, incl. 2 redrafts), split pre-draft 0.8 / draft 1.8 / check 0.6 s (DECISIONS §37); not a direct measurement.
