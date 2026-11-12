"""Input guardrails, checked before any model call or retrieval (K, 2026-11-12, hardening).

A question is untrusted text from outside. Before it can spend tokens:
  - control characters (other than tab / newline / CR) are removed: they have no meaning in a question and can
    hide text from a person reading the logs;
  - an empty question is rejected (nothing to answer, no reason to call the models);
  - a question longer than MAX_QUESTION_CHARS is rejected. Without this cap one pasted document could spend a
    whole minute of input tokens (ITPM 7,000 per model) and push everyone behind it into the busy reply. The
    longest question in all our question sets is 196 characters, so 1,000 never touches real use.
The rejection is a fixed reply written by code ("rejected" reply kind), like the busy reply: no model call.

Prompt injection ("ignore your rules and ..."): the question is never trusted as an instruction channel for
facts. Every claim must quote a passage word for word (code check) and pass the 20b model check, so an injected
instruction can at most produce a refusal or the "couldn't verify" reply, not an unsupported answer.
"""
from __future__ import annotations

import re

MAX_QUESTION_CHARS = 1000
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def check_question(question) -> tuple[str, str | None]:
    """(cleaned question, None) if it may go on, else (cleaned question, reason it was rejected)."""
    q = _CONTROL.sub("", question if isinstance(question, str) else "")
    if not q.strip():
        return q, "empty"
    if len(q) > MAX_QUESTION_CHARS:
        return q, f"too_long ({len(q)} > {MAX_QUESTION_CHARS} characters)"
    return q, None
