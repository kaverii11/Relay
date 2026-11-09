"""Latency-only questions (written by Claude Code, NOT graded, NOT the eval set).
All distinct, so no identical prompt is resent: Groq's prompt cache would otherwise
flatter latency. The system prompt is shared, as it will be in production."""
_T = ["What does the {p} paper say about {t}?", "How is {t} used in the {p} paper?",
      "Why does the {p} paper introduce {t}?", "What are the limitations of {t} according to {p}?"]
_TERMS = [("Transformer", ["scaled dot-product attention", "multi-head attention", "positional encoding",
            "label smoothing", "the learning rate schedule", "residual dropout", "beam search", "byte-pair encoding"]),
          ("Moshi", ["the Mimi codec", "Inner Monologue", "the Helium text model", "the RQ-Transformer",
            "split residual vector quantization", "full-duplex dialogue", "acoustic delay", "watermarking"]),
          ("H-Net", ["the routing module", "the smoothing module", "the ratio loss", "the dechunking layer",
            "byte-level modeling", "two-stage hierarchy", "the straight-through estimator", "DNA modeling"])]
QUESTIONS = []
for i in range(60):
    p, terms = _TERMS[i % 3]
    QUESTIONS.append(_T[(i // 3) % 4].format(p=p, t=terms[(i // 12 + i // 3) % 8]))
assert len(set(QUESTIONS)) == len(QUESTIONS), "duplicate latency question"
