"""Which score can gate "the papers don't say"? Compares raw BM25, a BM25 top/next ratio,
bge-small cosine and a MiniLM cross-encoder on 12 hand-written questions (6+1 answerable,
5 not). Run: PYTHONPATH=. .venv/bin/python eval/gate_probe.py. No Groq calls."""
import re, time, pathlib, statistics as st, numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder, SentenceTransformer
from relay.ingest import load
cs = load(pathlib.Path('data/chunks_w250.jsonl'))
tok = lambda s: re.findall(r'\w+', s.lower())
bm = BM25Okapi([tok(c.text) for c in cs])
Q = [  # (question, answerable_by_papers)
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
t=time.perf_counter(); ce = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2'); print('ce load', round(time.perf_counter()-t,1),'s')
emb = SentenceTransformer('BAAI/bge-small-en-v1.5')
t=time.perf_counter(); E = emb.encode([c.text for c in cs], normalize_embeddings=True, batch_size=32); print('embed corpus', round(time.perf_counter()-t,1),'s', len(cs))
lat_ce, lat_emb = [], []
print(f"{'ans':>5} {'bm25top':>7} {'bm25ratio':>9} {'ce_top':>7} {'cos_top':>7}  question")
for q, ans in Q:
    s = bm.get_scores(tok(q)); idx = np.argsort(-s)[:20]
    ratio = s[idx[0]] / (s[idx[1:6]].mean() + 1e-9)
    t=time.perf_counter(); cesc = ce.predict([(q, cs[i].text) for i in idx]); lat_ce.append((time.perf_counter()-t)*1000)
    t=time.perf_counter(); qe = emb.encode([q], normalize_embeddings=True)[0]; cos = (E @ qe).max(); lat_emb.append((time.perf_counter()-t)*1000)
    print(f"{str(ans):>5} {s[idx[0]]:7.1f} {ratio:9.2f} {cesc.max():7.2f} {cos:7.3f}  {q[:70]}")
print('cross-encoder 20 pairs ms: median', round(st.median(lat_ce)), 'max', round(max(lat_ce)))
print('query embed+search ms: median', round(st.median(lat_emb)), 'max', round(max(lat_emb)))
