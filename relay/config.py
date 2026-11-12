"""All tunable numbers in one place. PLACEHOLDER = not yet decided by Kaveri from data
(see DECISIONS.md). Change them here only, so every run records what it used."""
from dataclasses import asdict, dataclass, field

PAPER_VERSIONS = ("1706.03762v7", "2410.00037v1", "2507.07955v2")
SMALL = "openai/gpt-oss-20b"
BIG = "openai/gpt-oss-120b"


@dataclass
class RetrievalSetting:
    """How the papers are split and fetched: piece size, pieces sent, re-rank, cutoff, chunker, paper hint."""
    words: int          # piece size (words per chunk)
    k: int              # pieces sent to the drafting model
    rerank: bool        # cross-encoder re-orders BM25's top-20 (the gate uses the cross-encoder either way)
    candidates: int = 20
    gate_threshold: float | None = None   # per-setting cutoff (K §41); None = Policy.gate_threshold
    # the ladder's fewer-chunks rung (DECISIONS §2): pieces sent when the full rung would miss the deadline.
    # None = half the pieces (min 2) in this setting's own order. K (2026-11-11 §44): 250/3 in BM25 order.
    fewer_k: int | None = None
    fewer_rerank: bool | None = None
    chunker: str = "v1"   # "v2" (K §51): table caption + header repeated on every table piece; rows tagged _v2
    # v3 (K 2026-11-12, change B): the understand step's "papers" hint (1-2 papers) guarantees each named paper its
    # best BM25 piece among the k sent. Rows tagged _ph.
    paper_hint: bool = False
    paper_hint_mode: str = "replace"   # "replace": swap out the lowest piece; "append": send it as an extra piece

    def cutoff(self, policy) -> float:
        """This setting's gate cutoff (its own, else the Policy default)."""
        return self.gate_threshold if self.gate_threshold is not None else policy.gate_threshold

    @property
    def fewer(self) -> tuple[int, bool]:
        """The ladder's fewer-pieces rung: (pieces, re-rank) to send when the full rung won't fit."""
        k = self.fewer_k if self.fewer_k is not None else max(2, self.k // 2)
        rr = self.fewer_rerank if self.fewer_rerank is not None else self.rerank
        return k, rr

    @property
    def name(self):
        """Short tag used in results.csv's retrieval_setting column, e.g. w250_k3_rr0_v2."""
        return (f"w{self.words}_k{self.k}_rr{int(self.rerank)}" + ("_v2" if self.chunker == "v2" else "")
                + (("_pha" if self.paper_hint_mode == "append" else "_ph") if self.paper_hint else ""))


# K (2026-11-11 §44), from the offline recall table and her midpoint rule (raw/settings_table_*, raw/cutoffs_by_size_*):
# three 250-word settings, each with its own cutoff; the fewer-chunks rung is 250/3 in BM25 order for all three.
SETTINGS = {
    "medium_rerank": RetrievalSetting(250, 6, True, gate_threshold=0.875, fewer_k=3, fewer_rerank=False),      # baseline
    "medium_norerank": RetrievalSetting(250, 6, False, gate_threshold=0.713, fewer_k=3, fewer_rerank=False),
    "medium_k3_norerank": RetrievalSetting(250, 3, False, gate_threshold=0.713, fewer_k=3, fewer_rerank=False),
    # K §50 / §52: the CHOSEN setting, by name (same object as medium_k3_norerank, so rows carry w250_k3_rr0).
    # Load scenarios keep medium_rerank (load/loadgen.py default) so Tables 2a/2b reproduce as measured.
    "chosen": None,
    # earlier candidates, kept for the offline tables only (not run on Groq)
    "small_pieces": RetrievalSetting(120, 8, False),
    "large_rerank": RetrievalSetting(500, 3, True),
}


@dataclass
class Policy:
    # --- "fast" (DECISIONS §1): PLACEHOLDERS until the end-to-end pipeline is measured
    """Every behaviour knob outside retrieval: deadline, gate, retries, checks, ladder, reserve."""
    system_deadline_ms: float = 8000       # K (2026-11-10 §37): 8 s, set after the evening e2e set (first token p95 5.7 s)
    # --- refusal gate (DECISIONS §29, K 2026-11-10): K's midpoint rule on max(raw, rewrite), tuning questions only
    gate_threshold: float = 0.875          # midpoint of highest refuse 0.354 (Q51) and lowest answerable above it 1.395 (Q42)
    gate_input: str = "max"                # "max": cross-encoder on the raw question AND the rewrite; the higher score is the
                                           # gate and the drafter gets that query's passages. "rewrite": rewrite only.
    # --- retries (DECISIONS §3)
    max_retries_per_question: int = 2
    retry_budget_fraction: float = 0.10    # PLACEHOLDER: retries <= max(2, 10% of requests in last 60 s)
    retry_jitter: str = "jitter"           # "exact" | "jitter" (DECISIONS §18 experiment)
    backoff_base_ms: float = 250           # 5xx / timeout backoff base (full jitter)
    call_timeout_short_s: float = 8.0      # understand / check
    call_timeout_draft_s: float = 15.0
    # --- check (DECISIONS §8, PENDING K): "both" | "code_only" | "adaptive"
    check_mode: str = "both"
    check_effort: str = "low"              # K §15: test "medium" later
    check_prompt: str = "v1"               # "v2" (K §51 b): name each number's table row/column or sentence
    draft_prompt: str = "v1"               # "v2" (K §61, part of a): the drafter is told the table prefix is not quotable
    # v3 (K 2026-11-12, change A): a redraft that repeats a claim (same passage, same quote) the model check already
    # rejected fails without a second model check, so the redraft cannot simply re-roll the checker
    sticky_check_fail: bool = False
    check_max_tokens_v2: int = 800         # K §59: raised with (b); CC's value: the draft's cap, 2.5x the longest
                                           # uncut v2 check reply (314 of 39; one reply hit the old 400 cap)
    # --- degradation + budget (DECISIONS §2, §4)
    daily_reserve_fraction: float = 0.20   # PLACEHOLDER: K wants burst-sized reserve after the burst scenario
                                           # (used only when pacing_enabled is False: the measured behaviour)
    # --- spend-rate pacing (K, 2026-11-12; DECISIONS §4, §72): replaces the 20 % cliff with a regulator.
    # 120b is skipped when its spend over the last pacing_window_s runs above
    # (tokens left today / seconds until the day bucket is full again) x (1 + pacing_tolerance),
    # and always below hard_reserve_fraction of the day. Values are K's, not yet measured on a load run.
    pacing_enabled: bool = True
    pacing_tolerance: float = 0.15
    pacing_window_s: float = 300.0
    hard_reserve_fraction: float = 0.05
    workers: int = 16                      # our own concurrency; arrivals beyond this queue
    reasoning_effort: str = "low"          # K §15
    cache: bool = True
    # --- arrival-time busy check (K, DECISIONS §21): "on" | "shadow" (log decision, admit all) | "off"
    arrival_check: str = "on"
    learn_limits: bool = True              # K: lower our limit from a 429 body, drift back over ~10 min
    extra: dict = field(default_factory=dict)

    def as_dict(self):
        """The policy as a dict, saved in each run's meta file."""
        return asdict(self)


SETTINGS["chosen"] = SETTINGS["medium_k3_norerank"]
# v2 (K §51, §53): the chosen setting on the v2 chunker; its cutoff is re-derived on tuning (K's midpoint rule)
SETTINGS["chosen_v2"] = RetrievalSetting(250, 3, False, gate_threshold=0.713, fewer_k=3, fewer_rerank=False, chunker="v2")
# K §56: with retrieval and the gate on the body only, v2 scores = v1 scores, so the v1 cutoff 0.713 stands.
# v3 (K 2026-11-12): v2 + paper hint (B); Policy for v3 adds sticky_check_fail (A). Cutoff: re-derived on tuning
# by eval/v3_offline.py (K's midpoint rule); 0.713 until then.
SETTINGS["chosen_v3"] = RetrievalSetting(250, 3, False, gate_threshold=0.713, fewer_k=3, fewer_rerank=False, chunker="v2",
                                         paper_hint=True)
SETTINGS["chosen_v3a"] = RetrievalSetting(250, 3, False, gate_threshold=0.713, fewer_k=3, fewer_rerank=False, chunker="v2",
                                          paper_hint=True, paper_hint_mode="append")
CHOSEN = "chosen"          # e.g. eval/e2e.py --setting chosen; loadgen --setting chosen (not used for Tables 2a/2b)
