"""12 seed questions written by Claude Code (NOT Kaveri) for the first gate probe and the
stage-1 Groq probe. Not part of the graded eval set. Labels: answerable-by-the-papers or not."""
SEED = [
    ("How many attention heads does the base Transformer use?", True),
    ("What frame rate does the Mimi codec operate at?", True),
    ("What compression ratio does the H-Net dynamic chunking learn on English text?", True),
    ("What dropout rate was used for the base Transformer model?", True),
    ("What is the theoretical latency of Moshi?", True),
    ("How does the ratio loss in dynamic chunking work?", True),
    ("What sampling rate does SoundStream use in its original paper?", False),
    ("What learning rate warmup did the dechunking layer use on DNA when trained on TPUs?", False),
    ("How many GPUs were used to train Moshi's Inner Monologue at Google?", False),
    ("What BLEU does the Transformer get on English-to-Hindi?", False),
    ("Who won the 2024 Interspeech best paper award?", False),
    ("Could you explain in a general way what the main idea is behind how these models handle long sequences of input and why it matters?", True),
]
