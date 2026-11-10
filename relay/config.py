"""All tunable numbers in one place. PLACEHOLDER = not yet decided by Kaveri from data
(see DECISIONS.md). Change them here only, so every run records what it used."""
from dataclasses import asdict, dataclass, field

PAPER_VERSIONS = ("1706.03762v7", "2410.00037v1", "2507.07955v2")
SMALL = "openai/gpt-oss-20b"
BIG = "openai/gpt-oss-120b"


@dataclass
class RetrievalSetting:
    words: int          # piece size (words per chunk)
    k: int              # pieces sent to the drafting model
    rerank: bool        # cross-encoder re-orders BM25's top-20 (the gate uses the cross-encoder either way)
    candidates: int = 20

    @property
    def name(self):
        return f"w{self.words}_k{self.k}_rr{int(self.rerank)}"


SETTINGS = {
    "small_pieces": RetrievalSetting(120, 8, False),
    "medium_rerank": RetrievalSetting(250, 6, True),
    "large_rerank": RetrievalSetting(500, 3, True),
}


@dataclass
class Policy:
    # --- "fast" (DECISIONS §1): PLACEHOLDERS until the end-to-end pipeline is measured
    system_deadline_ms: float = 8000       # K (2026-11-10 §37): 8 s, set after the evening e2e set (first token p95 5.7 s)
    # --- refusal gate (DECISIONS §29, K 2026-11-10): K's midpoint rule on max(raw, rewrite), tuning questions only
    gate_threshold: float = 0.875          # midpoint of highest refuse 0.354 (Q51) and lowest answerable above it 1.395 (Q42)
    gate_input: str = "max"                # "max": cross-encoder on the raw question AND the rewrite; the higher score is the
                                           # gate and the drafter gets that query's passages. "rewrite": rewrite only.
    # --- retries (DECISIONS §3)
    max_retries_per_question: int = 2
    retry_budget_fraction: float = 0.10    # PLACEHOLDER: retries <= 10% of requests in last 60 s
    retry_jitter: str = "jitter"           # "exact" | "jitter" (DECISIONS §18 experiment)
    backoff_base_ms: float = 250           # 5xx / timeout backoff base (full jitter)
    call_timeout_short_s: float = 8.0      # understand / check
    call_timeout_draft_s: float = 15.0
    # --- check (DECISIONS §8, PENDING K): "both" | "code_only" | "adaptive"
    check_mode: str = "both"
    check_effort: str = "low"              # K §15: test "medium" later
    # --- degradation + budget (DECISIONS §2, §4)
    daily_reserve_fraction: float = 0.20   # PLACEHOLDER: K wants burst-sized reserve after the burst scenario
    workers: int = 16                      # our own concurrency; arrivals beyond this queue
    reasoning_effort: str = "low"          # K §15
    cache: bool = True
    # --- arrival-time busy check (K, DECISIONS §21): "on" | "shadow" (log decision, admit all) | "off"
    arrival_check: str = "on"
    learn_limits: bool = True              # K: lower our limit from a 429 body, drift back over ~10 min
    extra: dict = field(default_factory=dict)

    def as_dict(self):
        return asdict(self)
