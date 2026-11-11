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
    gate_threshold: float | None = None   # per-setting cutoff (K §41); None = Policy.gate_threshold
    # the ladder's fewer-chunks rung (DECISIONS §2): pieces sent when the full rung would miss the deadline.
    # None = half the pieces (min 2) in this setting's own order. K (2026-11-11 §44): 250/3 in BM25 order.
    fewer_k: int | None = None
    fewer_rerank: bool | None = None

    def cutoff(self, policy) -> float:
        return self.gate_threshold if self.gate_threshold is not None else policy.gate_threshold

    @property
    def fewer(self) -> tuple[int, bool]:
        k = self.fewer_k if self.fewer_k is not None else max(2, self.k // 2)
        rr = self.fewer_rerank if self.fewer_rerank is not None else self.rerank
        return k, rr

    @property
    def name(self):
        return f"w{self.words}_k{self.k}_rr{int(self.rerank)}"


# K (2026-11-11 §44), from the offline recall table and her midpoint rule (raw/settings_table_*, raw/cutoffs_by_size_*):
# three 250-word settings, each with its own cutoff; the fewer-chunks rung is 250/3 in BM25 order for all three.
SETTINGS = {
    "medium_rerank": RetrievalSetting(250, 6, True, gate_threshold=0.875, fewer_k=3, fewer_rerank=False),      # baseline
    "medium_norerank": RetrievalSetting(250, 6, False, gate_threshold=0.713, fewer_k=3, fewer_rerank=False),
    "medium_k3_norerank": RetrievalSetting(250, 3, False, gate_threshold=0.713, fewer_k=3, fewer_rerank=False),
    # earlier candidates, kept for the offline tables only (not run on Groq)
    "small_pieces": RetrievalSetting(120, 8, False),
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
