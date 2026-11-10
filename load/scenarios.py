"""Load scenarios. Offered DRAFT demand is a MULTIPLE OF THE MEASURED CEILING (K, DECISIONS §17, §22).

Ceiling c ~= 2.5 drafts/min: 7000 ITPM (measured 429) / ~2.8k-token draft prompt on 120b
(measured, stage 2a). `draft_mult` = k: offered drafts/min = k x c. Not every question needs a
draft (gate refusals, cache hits), so the QUESTION rate = k x c / draft_share, where draft_share
comes from load/mix.json (gate-pass shares on K's pool at the current cutoff) and the mix X / Y
below. Both rates are written to each run's meta. k values are CC proposals (§17), K confirms.

Arrivals are OPEN-LOOP: a fixed, seeded schedule that does not wait for answers.
Patience is per person (PLACEHOLDER distribution, K to set); the system deadline is in Policy.
"""
CEILING_PER_MIN = 2.5

SCENARIOS = {
    "steady": {
        "desc": "0.6c Poisson for 60 min",
        "phases": [{"draft_mult": 0.6, "minutes": 60}],
    },
    "burst": {
        "desc": "0.6c base for 20 min, plus 40 questions arriving inside 30 s at minute 5 (an incident)",
        "phases": [{"draft_mult": 0.6, "minutes": 20}],
        "bursts": [{"at_min": 5, "n": 40, "within_s": 30}],
    },
    "overload": {
        "desc": "2c Poisson for 30 min (sustained overload)",
        "phases": [{"draft_mult": 2.0, "minutes": 30}],
    },
    "minute_limit_halved": {
        "desc": "ITPM 7000 -> 3500 (K): ceiling drops to ~1.25/min while offered stays 0.6c of the OLD ceiling (=1.2x new)",
        "phases": [{"draft_mult": 0.6, "minutes": 30}],
        "standin_limits": {"itpm": 3500},
    },
    "daily_exhausted": {
        "desc": "3pm: 120b daily tokens gone, 20b has 15k left; 0.6c for 20 min",
        "phases": [{"draft_mult": 0.6, "minutes": 20}],
        "exhaust": [{"model": "openai/gpt-oss-120b", "limit": "tpd", "leave": 0},
                    {"model": "openai/gpt-oss-20b", "limit": "tpd", "leave": 15000}],
    },
}

# Load mix (K, DECISIONS §22). None = not set yet; full runs refuse to start until K sets them.
MIX = {
    "unanswerable_share": 0.25,     # X: share of fresh questions the papers can't answer (K)
    "burst_repeat_share": 0.5,     # Y: share of burst questions that exactly repeat one of the burst's hot set (K)
    "burst_hot_set": 3,          # size of each burst's hot set (K: "2-3 questions per burst")
}

# PLACEHOLDER (K decides, DECISIONS §1): lognormal patience, median 15 s, sigma 0.5 -> p10 ~8 s, p90 ~28 s
PATIENCE = {"median_s": 15.0, "sigma": 0.5}
