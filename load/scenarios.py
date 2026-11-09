"""Load scenarios. Offered rates are MULTIPLES OF THE MEASURED CEILING (K, DECISIONS §17).

Ceiling c ~= 2.5 questions/min: 7000 ITPM (measured 429) / ~2.8k-token draft prompt on 120b
(measured, stage 2a). Each question makes exactly one draft call on 120b.

Arrivals are OPEN-LOOP: a fixed, seeded schedule that does not wait for answers.
Patience is per person (PLACEHOLDER distribution, K to set); the system deadline is in Policy.
"""
CEILING_PER_MIN = 2.5

SCENARIOS = {
    "steady": {
        "desc": "0.6c Poisson for 60 min",
        "phases": [{"rate_mult": 0.6, "minutes": 60}],
    },
    "burst": {
        "desc": "0.6c base for 20 min, plus 40 questions arriving inside 30 s at minute 5 (an incident)",
        "phases": [{"rate_mult": 0.6, "minutes": 20}],
        "bursts": [{"at_min": 5, "n": 40, "within_s": 30}],
    },
    "overload": {
        "desc": "2c Poisson for 30 min (sustained overload)",
        "phases": [{"rate_mult": 2.0, "minutes": 30}],
    },
    "minute_limit_halved": {
        "desc": "ITPM 7000 -> 3500 (K): ceiling drops to ~1.25/min while offered stays 0.6c of the OLD ceiling (=1.2x new)",
        "phases": [{"rate_mult": 0.6, "minutes": 30}],
        "standin_limits": {"itpm": 3500},
    },
    "daily_exhausted": {
        "desc": "3pm: 120b daily tokens gone, 20b has 15k left; 0.6c for 20 min",
        "phases": [{"rate_mult": 0.6, "minutes": 20}],
        "exhaust": [{"model": "openai/gpt-oss-120b", "limit": "tpd", "leave": 0},
                    {"model": "openai/gpt-oss-20b", "limit": "tpd", "leave": 15000}],
    },
}

# PLACEHOLDER (K decides, DECISIONS §1): lognormal patience, median 15 s, sigma 0.5 -> p10 ~8 s, p90 ~28 s
PATIENCE = {"median_s": 15.0, "sigma": 0.5}
