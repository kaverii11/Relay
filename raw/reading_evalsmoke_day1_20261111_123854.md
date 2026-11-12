# eval reading file, evalsmoke_day1_20261111_123854

settings ['medium_rerank', 'medium_norerank', 'medium_k3_norerank']; gates medium_rerank 0.875, medium_norerank 0.713, medium_k3_norerank 0.713 on max; questions Q57,Q14,Q43,Q12,Q26,Q40,Q45,Q49,Q15,Q35,Q48,Q32,Q7,Q34,Q8,Q47,Q18,Q25,Q4,Q9

## Q57 x medium_norerank
**Q:** Do the original Transformer and H-Net use the same optimizer and learning-rate schedule?

- reply: **answer** / ok; degrade full; model openai/gpt-oss-120b; first token 2956.5 ms; total 2956.5 ms; calls 3; limiter wait 0.0 ms
- gate: 1.891 by rewrite (raw 0.051, rewrite 1.891); query: Transformer optimizer learning-rate schedule H-Net optimizer learning-rate schedule
- calls (in+out, cached): understand 248+91 (0 cached), draft 2094+119 (0 cached), check 325+63 (0 cached)

**Draft 0 (openai/gpt-oss-120b):** The papers state that 5.3 Optimizer We used the Adam optimizer [20] with β1 = 0.9, β2 = 0.98 and ϵ = [C1].
  - C1: "5.3 Optimizer We used the Adam optimizer [20] with β1 = 0.9, β2 = 0.98 and ϵ ="
  - code check: OK
  - model check: OK

**Final reply:** The papers state that 5.3 Optimizer We used the Adam optimizer [20] with β1 = 0.9, β2 = 0.98 and ϵ = [1706.03762v7 §5.3 p.7].
citations: ['[1706.03762v7 §5.3 p.7]']

**Passages the drafter saw:**
- C1 [1706.03762v7 §5.3 p.7] (bm25 26.76, ce -0.809): 5.3 Optimizer We used the Adam optimizer [20] with β1 = 0.9, β2 = 0.98 and ϵ = 10−9. We varied the learning rate over the course of training, according to the formula: lrate = d−0.5 model · min(step_num−0.5, step_num · warmup_steps−1.5) (3) This corresponds to increasing the learning rate linearly for the first warmup_steps training steps, and decreasing it thereafter proportionally to the inverse square root of the step number. We used warmup_steps = 4000.
- C2 [2507.07955v2 §3 pp.11-12] (bm25 21.28, ce 1.891): the same number of FLOPs in every forward/backward pass. scheduling with 10% linear warmup and 20% inverse-square-root decay (Ibrahim et al. 2024). Following Hägele et al. (2024) which recommends WSD schedulers with half the maximum learning rates as a cosine schedule, we adopt learning rates 2.5× higher than GPT-3 (Radford et al. 2019) standards; this corresponds to half of the maximum learning rate used in Gu and Dao (2024), yielding 6.25 × 10−4 for Large-scale models and 5.0 × 10−4 for XL-scale models. Architecture details include gated MLPs (Touvron, Martin, et al. 2023) in all Transformer layers and the main network’s Mamba layers, while Mamba layers in E and D are without an MLP.14 For Transformer layers in E and D, we use Sliding Window Attention (SWA) (Beltagy, Peters, and Cohan 2020) with the window size of 1024. As discussed Section 2.1, E and D comprise mainly Mamba-2 layers.
- C3 [2410.00037v1 §3.2.1 p.7] (bm25 19.81, ce -4.423): 3.2.1 Architecture Helium is an autoregressive language model, based on the Transformer architecture (Vaswani et al., 2017). Following previous work in this area, we make the following changes to the original architecture: First, we use RMS normalization (Zhang and Sennrich, 2019) at the input of the attention blocks, the feed-forward blocks and the output linear layer of the model. We use rotation positional embeddings (Su et al., 2024, RoPE), a context length of 4,096 tokens and FlashAttention (Dao et al., 2022) for efficient training. Finally, we change the architecture of the feed-forward blocks and use Gated Linear Units (Shazeer, 2020), with the SiLU activation as a gating function (Hendrycks and Gimpel, 2016b). Our tokenizer is based on the unigram model from SentencePiece (Kudo and Richardson, 2018), and contains 32,000 elements mostly targeting English. We split all numbers into single digits, and use byte-backoff to ensure that our tokenizer does not lose information. We train the model with the AdamW (Loshchilov and Hutter, 2017) optimizer, with a fixed learning rate followed by a cosine learning rate decay (Loshchilov and Hutter, 2016).
- C4 [2507.07955v2 §3 pp.11-12] (bm25 19.73, ce -0.758): the total number of bytes. In addition, we systematically control the data and compute budget for all models (see Table 1), matching all models carefully in both bytes-per-batch and FLOPs-per-byte:13 • Data Budget: We train all models on the 100B token subset sampled from the FineWeb-Edu dataset (Penedo et al. 2024). All tokenizer-free models process 8192 utf-8 encoded bytes per sequence, while the Transformer uses 1792 tokens from the GPT2 tokenizer (roughly equivalent to 8192 bytes). We use batch size 256 for all models; the total batch size is just under 0.5M tokens per batch for the baseline BPE Transformer, roughly matching protocols from prior work (Gu and Dao 2024). • Compute Budget: For calculating FLOPs, we follow standard methodology (Hoffmann et al. 2022) with an extension for Mamba-2 layers (see Appendix B). We use the BPE-tokenized Transformer’s #FLOPs as a reference, and the number of layers of the other models is adjusted accordingly to match the reference #FLOPs. Training employs AdamW (Loshchilov and Hutter 2017) optimizer with warmup-stable-decay (WSD) (Hu et al. 2024) 13Another way to interpret this is that every model sees the exact same underlying data (regardless of tokenization) per minibatch, and every model aims to use the same number of FLOPs in every forward/backward pass. scheduling with 10% linear warmup and 20% inverse-square-root decay (Ibrahim et al. 2024). Following Hägele et al. (2024) which recommends WSD schedulers with half the maximum learning rates as a cosine schedule, we adopt learning rates 2.5× higher than GPT-3 (Radford
- C5 [2410.00037v1 §3.2.2 pp.8-9] (bm25 18.71, ce -1.121): keep training half of the time on full text batches from the same dataset as used for Helium, using a separate optimizer state. Helium training Moshi training Hyper-parameter pre-training pre-training post-training fisher fine Temporal Transformer Model dimension 4096 same MLP dimension 11264 Number of heads 32 Number of layers 32 Context size 4096 3000 steps, e.g. 4 min. Learning rate 3 · 10−4 3 · 10−5 3 · 10−6 2 · 10−6 2 · 10−6 Depth Transformer Model dimension - 1024 MLP dimension - 4096 Number of heads - 16 Number of layers - 6 Learning rate - 2 · 10−4 5 · 10−5 4 · 10−6 2 · 10−6 Input / Output space Text cardinality 32000 32000 Audio cardinality - 2048 Frame rate - 12.5 Hz Common parameters Deduplication. We start from the WET files, which contain only the text content of webpages, which was extracted by the CommonCrawl project. Because this format contains all the text of a page, it includes a lot of boilerplate such as navigation menus. Thus, the first step of our pipeline is to deduplicate each shard (there is 100 shards per crawl) at the line level, to remove this boilerplate. To do so, we compute the FNV-1a6 hash of each line, and use a bloom filter to remove duplicates. We also train a fastText (Joulin et al., 2016) 6. http://www.isthe.com/chongo/tech/comp/fnv Moshi: a speech-text foundation model for real-time dialogue classifier on duplicates vs. non-duplicates, to perform fuzzy deduplication: here we only remove blocks of
- C6 [2410.00037v1 §4.4 p.20] (bm25 18.63, ce -3.642): 4.4 Training stages and hyper-parameters Helium pre-training. An overview of the training stages and hyper parameters is provided in Table 1. For every training phase, we use AdamW (Loshchilov and Hutter, 2019), with a weight decay of 0.1, a momentum decay of 0.9, and a decay for the online average of the squared gradient of 0.95. All models are trained on H100 GPUs, using FSDP and activation checkpointing. The core text-only language model, Helium, is trained for 500k steps, with a batch size of 4.2M tokens, using a cosine learning rate schedule starting at 3 · 10−4 with linear warmup. Moshi pre-training. Then, we initialize the Temporal Transformer in Moshi with Helium, while the Depth Transformer described in Section 3.4.1 is randomly initialized. We first train on the unsupervised audio dataset presented in Section 4.2, using a single stream of audio, with a batch size covering 16 hours of audio, each batch item consisting of a 5 mn sequence. We mask the corresponding text tokens with a probability of 30%. We randomize the delay between the text and audio tokens between -0.6 and +0.6 seconds. In order to prevent catastrophic forgetting, we also train half of the time on batches of text only data from the same dataset as used for Helium. In total, we make 1 million training steps, with a cosine learning rate starting at 3·10−5 for the Temporal Transformer, and 2·10−4 for the Depth Transformer, also with a linear warmup. In order to ensure the updates from

grade: 

## Q57 x medium_k3_norerank
**Q:** Do the original Transformer and H-Net use the same optimizer and learning-rate schedule?

- reply: **answer** / ok; degrade full; model openai/gpt-oss-120b; first token 1828.2 ms; total 1828.2 ms; calls 3; limiter wait 0.0 ms
- gate: 1.891 by rewrite (raw 0.051, rewrite 1.891); query: Transformer optimizer learning-rate schedule H-Net optimizer learning-rate schedule
- calls (in+out, cached): understand 248+86 (0 cached), draft 936+151 (0 cached), check 325+44 (0 cached)

**Draft 0 (openai/gpt-oss-120b):** The papers state that 5.3 Optimizer We used the Adam optimizer [20] with β1 = 0.9, β2 = 0.98 and ϵ = [C1].
  - C1: "5.3 Optimizer We used the Adam optimizer [20] with β1 = 0.9, β2 = 0.98 and ϵ ="
  - code check: OK
  - model check: OK

**Final reply:** The papers state that 5.3 Optimizer We used the Adam optimizer [20] with β1 = 0.9, β2 = 0.98 and ϵ = [1706.03762v7 §5.3 p.7].
citations: ['[1706.03762v7 §5.3 p.7]']

**Passages the drafter saw:**
- C1 [1706.03762v7 §5.3 p.7] (bm25 26.76, ce -0.809): 5.3 Optimizer We used the Adam optimizer [20] with β1 = 0.9, β2 = 0.98 and ϵ = 10−9. We varied the learning rate over the course of training, according to the formula: lrate = d−0.5 model · min(step_num−0.5, step_num · warmup_steps−1.5) (3) This corresponds to increasing the learning rate linearly for the first warmup_steps training steps, and decreasing it thereafter proportionally to the inverse square root of the step number. We used warmup_steps = 4000.
- C2 [2507.07955v2 §3 pp.11-12] (bm25 21.28, ce 1.891): the same number of FLOPs in every forward/backward pass. scheduling with 10% linear warmup and 20% inverse-square-root decay (Ibrahim et al. 2024). Following Hägele et al. (2024) which recommends WSD schedulers with half the maximum learning rates as a cosine schedule, we adopt learning rates 2.5× higher than GPT-3 (Radford et al. 2019) standards; this corresponds to half of the maximum learning rate used in Gu and Dao (2024), yielding 6.25 × 10−4 for Large-scale models and 5.0 × 10−4 for XL-scale models. Architecture details include gated MLPs (Touvron, Martin, et al. 2023) in all Transformer layers and the main network’s Mamba layers, while Mamba layers in E and D are without an MLP.14 For Transformer layers in E and D, we use Sliding Window Attention (SWA) (Beltagy, Peters, and Cohan 2020) with the window size of 1024. As discussed Section 2.1, E and D comprise mainly Mamba-2 layers.
- C3 [2410.00037v1 §3.2.1 p.7] (bm25 19.81, ce -4.423): 3.2.1 Architecture Helium is an autoregressive language model, based on the Transformer architecture (Vaswani et al., 2017). Following previous work in this area, we make the following changes to the original architecture: First, we use RMS normalization (Zhang and Sennrich, 2019) at the input of the attention blocks, the feed-forward blocks and the output linear layer of the model. We use rotation positional embeddings (Su et al., 2024, RoPE), a context length of 4,096 tokens and FlashAttention (Dao et al., 2022) for efficient training. Finally, we change the architecture of the feed-forward blocks and use Gated Linear Units (Shazeer, 2020), with the SiLU activation as a gating function (Hendrycks and Gimpel, 2016b). Our tokenizer is based on the unigram model from SentencePiece (Kudo and Richardson, 2018), and contains 32,000 elements mostly targeting English. We split all numbers into single digits, and use byte-backoff to ensure that our tokenizer does not lose information. We train the model with the AdamW (Loshchilov and Hutter, 2017) optimizer, with a fixed learning rate followed by a cosine learning rate decay (Loshchilov and Hutter, 2016).

grade: 

## Q57 x medium_rerank
**Q:** Do the original Transformer and H-Net use the same optimizer and learning-rate schedule?

- reply: **answer** / ok; degrade full; model openai/gpt-oss-120b; first token 1772.2 ms; total 1772.2 ms; calls 3; limiter wait 0.0 ms
- gate: 1.891 by rewrite (raw 0.672, rewrite 1.891); query: Transformer optimizer learning-rate schedule H-Net optimizer learning-rate schedule
- calls (in+out, cached): understand 248+111 (0 cached), draft 2265+150 (0 cached), check 458+84 (0 cached)

**Draft 0 (openai/gpt-oss-120b):** The papers state that the same number of FLOPs in every forward/backward pass. scheduling with 10% linear warmup and 20% inverse-square-root decay [C1].
  - C1: "the same number of FLOPs in every forward/backward pass. scheduling with 10% linear warmup and 20% inverse-square-root decay"
  - code check: OK
  - model check: OK

**Final reply:** The papers state that the same number of FLOPs in every forward/backward pass. scheduling with 10% linear warmup and 20% inverse-square-root decay [2507.07955v2 §3 pp.11-12].
citations: ['[2507.07955v2 §3 pp.11-12]']

**Passages the drafter saw:**
- C1 [2507.07955v2 §3 pp.11-12] (bm25 21.28, ce 1.891): the same number of FLOPs in every forward/backward pass. scheduling with 10% linear warmup and 20% inverse-square-root decay (Ibrahim et al. 2024). Following Hägele et al. (2024) which recommends WSD schedulers with half the maximum learning rates as a cosine schedule, we adopt learning rates 2.5× higher than GPT-3 (Radford et al. 2019) standards; this corresponds to half of the maximum learning rate used in Gu and Dao (2024), yielding 6.25 × 10−4 for Large-scale models and 5.0 × 10−4 for XL-scale models. Architecture details include gated MLPs (Touvron, Martin, et al. 2023) in all Transformer layers and the main network’s Mamba layers, while Mamba layers in E and D are without an MLP.14 For Transformer layers in E and D, we use Sliding Window Attention (SWA) (Beltagy, Peters, and Cohan 2020) with the window size of 1024. As discussed Section 2.1, E and D comprise mainly Mamba-2 layers.
- C2 [2410.00037v1 §4.4 p.20] (bm25 17.65, ce -0.559): of text only data from the same dataset as used for Helium. In total, we make 1 million training steps, with a cosine learning rate starting at 3·10−5 for the Temporal Transformer, and 2·10−4 for the Depth Transformer, also with a linear warmup. In order to ensure the updates from the text-only batches are balanced with those from the audio dataset, we use two separate optimizer states. In addition, when operating on the text stream from an audio batch, we multiply the learning rate for the text embedding and text linear layer by 0.75. Finally, as padding tokens are predominant for audio batches, we reduce their weight by 50% in the cross-entropy loss. Moshi post-training. Starting from the model obtained in the audio pre-training stage, we then further train it to augment it with multi-stream ability. First, we use PyAnnote (Bredin, 2023) to diarize the audio from the unsupervised audio dataset. We sample one speaker at random, which will act as the main speaker, and derive a binary mask over the waveform, with a value of 1 when the speaker is active based on the diarization, and 0 otherwise. This mask provides us with two waveforms: one with the speaker, and one with the residual (potentially several speakers), which are encoded separately and then used as the two input audio streams described in Section 3.4.3. The text stream only contains the text tokens from the selected main speaker, and we no longer use a variable delay between the text and
- C3 [2507.07955v2 §3 pp.11-12] (bm25 19.73, ce -0.758): the total number of bytes. In addition, we systematically control the data and compute budget for all models (see Table 1), matching all models carefully in both bytes-per-batch and FLOPs-per-byte:13 • Data Budget: We train all models on the 100B token subset sampled from the FineWeb-Edu dataset (Penedo et al. 2024). All tokenizer-free models process 8192 utf-8 encoded bytes per sequence, while the Transformer uses 1792 tokens from the GPT2 tokenizer (roughly equivalent to 8192 bytes). We use batch size 256 for all models; the total batch size is just under 0.5M tokens per batch for the baseline BPE Transformer, roughly matching protocols from prior work (Gu and Dao 2024). • Compute Budget: For calculating FLOPs, we follow standard methodology (Hoffmann et al. 2022) with an extension for Mamba-2 layers (see Appendix B). We use the BPE-tokenized Transformer’s #FLOPs as a reference, and the number of layers of the other models is adjusted accordingly to match the reference #FLOPs. Training employs AdamW (Loshchilov and Hutter 2017) optimizer with warmup-stable-decay (WSD) (Hu et al. 2024) 13Another way to interpret this is that every model sees the exact same underlying data (regardless of tokenization) per minibatch, and every model aims to use the same number of FLOPs in every forward/backward pass. scheduling with 10% linear warmup and 20% inverse-square-root decay (Ibrahim et al. 2024). Following Hägele et al. (2024) which recommends WSD schedulers with half the maximum learning rates as a cosine schedule, we adopt learning rates 2.5× higher than GPT-3 (Radford
- C4 [1706.03762v7 §5.3 p.7] (bm25 26.76, ce -0.809): 5.3 Optimizer We used the Adam optimizer [20] with β1 = 0.9, β2 = 0.98 and ϵ = 10−9. We varied the learning rate over the course of training, according to the formula: lrate = d−0.5 model · min(step_num−0.5, step_num · warmup_steps−1.5) (3) This corresponds to increasing the learning rate linearly for the first warmup_steps training steps, and decreasing it thereafter proportionally to the inverse square root of the step number. We used warmup_steps = 4000.
- C5 [2410.00037v1 §3.2.2 pp.8-9] (bm25 18.71, ce -1.121): keep training half of the time on full text batches from the same dataset as used for Helium, using a separate optimizer state. Helium training Moshi training Hyper-parameter pre-training pre-training post-training fisher fine Temporal Transformer Model dimension 4096 same MLP dimension 11264 Number of heads 32 Number of layers 32 Context size 4096 3000 steps, e.g. 4 min. Learning rate 3 · 10−4 3 · 10−5 3 · 10−6 2 · 10−6 2 · 10−6 Depth Transformer Model dimension - 1024 MLP dimension - 4096 Number of heads - 16 Number of layers - 6 Learning rate - 2 · 10−4 5 · 10−5 4 · 10−6 2 · 10−6 Input / Output space Text cardinality 32000 32000 Audio cardinality - 2048 Frame rate - 12.5 Hz Common parameters Deduplication. We start from the WET files, which contain only the text content of webpages, which was extracted by the CommonCrawl project. Because this format contains all the text of a page, it includes a lot of boilerplate such as navigation menus. Thus, the first step of our pipeline is to deduplicate each shard (there is 100 shards per crawl) at the line level, to remove this boilerplate. To do so, we compute the FNV-1a6 hash of each line, and use a bloom filter to remove duplicates. We also train a fastText (Joulin et al., 2016) 6. http://www.isthe.com/chongo/tech/comp/fnv Moshi: a speech-text foundation model for real-time dialogue classifier on duplicates vs. non-duplicates, to perform fuzzy deduplication: here we only remove blocks of
- C6 [2507.07955v2 §1 pp.2-3] (bm25 8.55, ce -1.164): show that the encoder and decoder networks are strongly improved by using SSMs, which have an inductive bias for compression (Gu 2025). Dynamic Chunking. H-Net’s core is a novel dynamic chunking (DC) mechanism which interfaces between the main network and the encoder/decoder networks, learning how to segment data while using standard differentiable optimization. DC is composed of two complementary new techniques: (i) a routing module which predicts boundaries between adjacent elements through a similarity score (ii) and a smoothing module which interpolates representations using the router’s outputs, attenuating the effect of uncertain boundaries and significantly improving learnability. By combining these with a new auxiliary loss function that targets desired downsampling ratios, and modern techniques for gradient-based learning of discrete choices (Fedus, Zoph, and Shazeer 2022; Bengio, Léonard, and Courville 2013), DC lets an H-Net learn how to compress data in a fully end-to-end fashion. Signal Propagation. We introduce several architectural and training techniques to improve stability and scalability during end-to-end optimization. These include: (i) carefully placing projections and normalization layers to balance signal propagation between interacting sub-networks, and (ii) adjusting optimization parameters for each layer based on its dimensionality and effective batch size, which changes between stages of the hierarchical structure. Altogether, H-Net learns segmentation strategies optimized jointly with the main backbone, dynamically compressing input vectors based on contextual information into meaningful chunks. H-Net represents the first truly end-to-end, tokenizer-free 3Non-hierarchical models comprised of repeated blocks, such as the standard Transformer (Vaswani et al. 2017). (c) Smoothing Module Chunking Dechunkinĝ

grade: 

## Q14 x medium_k3_norerank
**Q:** What dropout rate is applied to the sums of the embeddings and positional encodings in the base model?

- reply: **answer** / ok; degrade full; model openai/gpt-oss-120b; first token 3128.8 ms; total 3128.8 ms; calls 5; limiter wait 0.0 ms
- gate: 4.74 by raw (raw 4.74, rewrite 4.449); query: dropout rate applied to the sums of the embeddings and positional encodings
- calls (in+out, cached): understand 251+114 (0 cached), draft 1174+155 (0 cached), check 554+81 (0 cached), draft 1203+158 (0 cached), check 554+50 (0 cached)

**Draft 0 (openai/gpt-oss-120b):** The papers state that 5.4 Regularization We employ three types of regularization during training: Table 2: The Transformer achieves better BLEU scores [C1].
  - C1: "5.4 Regularization We employ three types of regularization during training: Table 2: The Transformer achieves better BLEU scores"
  - code check: OK
  - model check: FAIL (simulated: checker did not confirm support)

**Draft 1 (openai/gpt-oss-120b):** The papers state that 5.4 Regularization We employ three types of regularization during training: Table 2: The Transformer achieves better BLEU scores [C1].
  - C1: "5.4 Regularization We employ three types of regularization during training: Table 2: The Transformer achieves better BLEU scores"
  - code check: OK
  - model check: OK

**Final reply:** The papers state that 5.4 Regularization We employ three types of regularization during training: Table 2: The Transformer achieves better BLEU scores [1706.03762v7 §5.4 pp.7-8].
citations: ['[1706.03762v7 §5.4 pp.7-8]']

**Passages the drafter saw:**
- C1 [1706.03762v7 §5.4 pp.7-8] (bm25 43.9, ce 4.74): 5.4 Regularization We employ three types of regularization during training: Table 2: The Transformer achieves better BLEU scores than previous state-of-the-art models on the English-to-German and English-to-French newstest2014 tests at a fraction of the training cost. Model BLEU Training Cost (FLOPs) EN-DE EN-FR EN-DE EN-FR ByteNet [18] 23.75 Deep-Att + PosUnk [39] 39.2 1.0 · 1020 GNMT + RL [38] 24.6 39.92 2.3 · 1019 1.4 · 1020 ConvS2S [9] 25.16 40.46 9.6 · 1018 1.5 · 1020 MoE [32] 26.03 40.56 2.0 · 1019 1.2 · 1020 Deep-Att + PosUnk Ensemble [39] 40.4 8.0 · 1020 GNMT + RL Ensemble [38] 26.30 41.16 1.8 · 1020 1.1 · 1021 ConvS2S Ensemble [9] 26.36 41.29 7.7 · 1019 1.2 · 1021 Transformer (base model) 27.3 38.1 3.3 · 1018 Transformer (big) 28.4 41.8 2.3 · 1019 Residual Dropout We apply dropout [33] to the output of each sub-layer, before it is added to the sub-layer input and normalized. In addition, we apply dropout to the sums of the embeddings and the positional encodings in both the encoder and decoder stacks. For the base model, we use a rate of Pdrop = 0.1. Label Smoothing During training, we employed label smoothing of value ϵls = 0.1 [36]. This hurts perplexity, as the model learns to be more unsure, but improves accuracy and BLEU score.
- C2 [1706.03762v7 §3.5 p.6] (bm25 38.7, ce 1.138): 3.5 Positional Encoding Since our model contains no recurrence and no convolution, in order for the model to make use of the order of the sequence, we must inject some information about the relative or absolute position of the tokens in the sequence. To this end, we add "positional encodings" to the input embeddings at the bottoms of the encoder and decoder stacks. The positional encodings have the same dimension dmodel as the embeddings, so that the two can be summed. There are many choices of positional encodings, learned and fixed [9]. In this work, we use sine and cosine functions of different frequencies: PE(pos,2i) = sin(pos/100002i/dmodel) PE(pos,2i+1) = cos(pos/100002i/dmodel) where pos is the position and i is the dimension. That is, each dimension of the positional encoding corresponds to a sinusoid. The wavelengths form a geometric progression from 2π to 10000 · 2π. We chose this function because we hypothesized it would allow the model to easily learn to attend by relative positions, since for any fixed offset k, PEpos+k can be represented as a linear function of PEpos. We also experimented with using learned positional embeddings [9] instead, and found that the two versions produced nearly identical results (see Table 3 row (E)). We chose the sinusoidal version because it may allow the model to extrapolate to sequence lengths longer than the ones encountered during training.
- C3 [1706.03762v7 §6.2 p.9] (bm25 35.27, ce 1.435): vary the number of attention heads and the attention key and value dimensions, keeping the amount of computation constant, as described in Section 3.2.2. While single-head attention is 0.9 BLEU worse than the best setting, quality also drops off with too many heads. In Table 3 rows (B), we observe that reducing the attention key size dk hurts model quality. This suggests that determining compatibility is not easy and that a more sophisticated compatibility function than dot product may be beneficial. We further observe in rows (C) and (D) that, as expected, bigger models are better, and dropout is very helpful in avoiding over-fitting. In row (E) we replace our sinusoidal positional encoding with learned positional embeddings [9], and observe nearly identical results to the base model.

grade: 

## Q14 x medium_rerank
**Q:** What dropout rate is applied to the sums of the embeddings and positional encodings in the base model?

- reply: **answer** / ok; degrade small_model; model openai/gpt-oss-20b; first token 2854.3 ms; total 2854.3 ms; calls 4; limiter wait 0.0 ms
- gate: 4.74 by raw (raw 4.74, rewrite 4.449); query: dropout rate applied to the sums of the embeddings and positional encodings
- calls (in+out, cached): understand 0+0 (0 cached), understand 251+81 (0 cached), draft 1174+134 (0 cached), check 554+61 (0 cached)

**Draft 0 (openai/gpt-oss-20b):** The papers state that 5.4 Regularization We employ three types of regularization during training: Table 2: The Transformer achieves better BLEU scores [C1].
  - C1: "5.4 Regularization We employ three types of regularization during training: Table 2: The Transformer achieves better BLEU scores"
  - code check: OK
  - model check: OK

**Final reply:** The papers state that 5.4 Regularization We employ three types of regularization during training: Table 2: The Transformer achieves better BLEU scores [1706.03762v7 §5.4 pp.7-8].
citations: ['[1706.03762v7 §5.4 pp.7-8]']

**Passages the drafter saw:**
- C1 [1706.03762v7 §5.4 pp.7-8] (bm25 43.9, ce 4.74): 5.4 Regularization We employ three types of regularization during training: Table 2: The Transformer achieves better BLEU scores than previous state-of-the-art models on the English-to-German and English-to-French newstest2014 tests at a fraction of the training cost. Model BLEU Training Cost (FLOPs) EN-DE EN-FR EN-DE EN-FR ByteNet [18] 23.75 Deep-Att + PosUnk [39] 39.2 1.0 · 1020 GNMT + RL [38] 24.6 39.92 2.3 · 1019 1.4 · 1020 ConvS2S [9] 25.16 40.46 9.6 · 1018 1.5 · 1020 MoE [32] 26.03 40.56 2.0 · 1019 1.2 · 1020 Deep-Att + PosUnk Ensemble [39] 40.4 8.0 · 1020 GNMT + RL Ensemble [38] 26.30 41.16 1.8 · 1020 1.1 · 1021 ConvS2S Ensemble [9] 26.36 41.29 7.7 · 1019 1.2 · 1021 Transformer (base model) 27.3 38.1 3.3 · 1018 Transformer (big) 28.4 41.8 2.3 · 1019 Residual Dropout We apply dropout [33] to the output of each sub-layer, before it is added to the sub-layer input and normalized. In addition, we apply dropout to the sums of the embeddings and the positional encodings in both the encoder and decoder stacks. For the base model, we use a rate of Pdrop = 0.1. Label Smoothing During training, we employed label smoothing of value ϵls = 0.1 [36]. This hurts perplexity, as the model learns to be more unsure, but improves accuracy and BLEU score.
- C2 [1706.03762v7 §3.5 p.6] (bm25 38.7, ce 1.138): 3.5 Positional Encoding Since our model contains no recurrence and no convolution, in order for the model to make use of the order of the sequence, we must inject some information about the relative or absolute position of the tokens in the sequence. To this end, we add "positional encodings" to the input embeddings at the bottoms of the encoder and decoder stacks. The positional encodings have the same dimension dmodel as the embeddings, so that the two can be summed. There are many choices of positional encodings, learned and fixed [9]. In this work, we use sine and cosine functions of different frequencies: PE(pos,2i) = sin(pos/100002i/dmodel) PE(pos,2i+1) = cos(pos/100002i/dmodel) where pos is the position and i is the dimension. That is, each dimension of the positional encoding corresponds to a sinusoid. The wavelengths form a geometric progression from 2π to 10000 · 2π. We chose this function because we hypothesized it would allow the model to easily learn to attend by relative positions, since for any fixed offset k, PEpos+k can be represented as a linear function of PEpos. We also experimented with using learned positional embeddings [9] instead, and found that the two versions produced nearly identical results (see Table 3 row (E)). We chose the sinusoidal version because it may allow the model to extrapolate to sequence lengths longer than the ones encountered during training.
- C3 [1706.03762v7 §6.2 p.9] (bm25 35.27, ce 1.435): vary the number of attention heads and the attention key and value dimensions, keeping the amount of computation constant, as described in Section 3.2.2. While single-head attention is 0.9 BLEU worse than the best setting, quality also drops off with too many heads. In Table 3 rows (B), we observe that reducing the attention key size dk hurts model quality. This suggests that determining compatibility is not easy and that a more sophisticated compatibility function than dot product may be beneficial. We further observe in rows (C) and (D) that, as expected, bigger models are better, and dropout is very helpful in avoiding over-fitting. In row (E) we replace our sinusoidal positional encoding with learned positional embeddings [9], and observe nearly identical results to the base model.

grade: 

## Q14 x medium_norerank
**Q:** What dropout rate is applied to the sums of the embeddings and positional encodings in the base model?

- reply: **answer** / ok; degrade fewer_chunks; model openai/gpt-oss-120b; first token 6007.8 ms; total 6007.8 ms; calls 3; limiter wait 4112.2 ms
- gate: 4.74 by raw (raw 4.74, rewrite 4.449); query: dropout rate applied to the sums of the embeddings and positional encodings
- calls (in+out, cached): understand 251+61 (0 cached), draft 1174+132 (0 cached), check 554+57 (0 cached)

**Draft 0 (openai/gpt-oss-120b):** The papers state that 5.4 Regularization We employ three types of regularization during training: Table 2: The Transformer achieves better BLEU scores [C1].
  - C1: "5.4 Regularization We employ three types of regularization during training: Table 2: The Transformer achieves better BLEU scores"
  - code check: OK
  - model check: OK

**Final reply:** The papers state that 5.4 Regularization We employ three types of regularization during training: Table 2: The Transformer achieves better BLEU scores [1706.03762v7 §5.4 pp.7-8].
citations: ['[1706.03762v7 §5.4 pp.7-8]']

**Passages the drafter saw:**
- C1 [1706.03762v7 §5.4 pp.7-8] (bm25 43.9, ce 4.74): 5.4 Regularization We employ three types of regularization during training: Table 2: The Transformer achieves better BLEU scores than previous state-of-the-art models on the English-to-German and English-to-French newstest2014 tests at a fraction of the training cost. Model BLEU Training Cost (FLOPs) EN-DE EN-FR EN-DE EN-FR ByteNet [18] 23.75 Deep-Att + PosUnk [39] 39.2 1.0 · 1020 GNMT + RL [38] 24.6 39.92 2.3 · 1019 1.4 · 1020 ConvS2S [9] 25.16 40.46 9.6 · 1018 1.5 · 1020 MoE [32] 26.03 40.56 2.0 · 1019 1.2 · 1020 Deep-Att + PosUnk Ensemble [39] 40.4 8.0 · 1020 GNMT + RL Ensemble [38] 26.30 41.16 1.8 · 1020 1.1 · 1021 ConvS2S Ensemble [9] 26.36 41.29 7.7 · 1019 1.2 · 1021 Transformer (base model) 27.3 38.1 3.3 · 1018 Transformer (big) 28.4 41.8 2.3 · 1019 Residual Dropout We apply dropout [33] to the output of each sub-layer, before it is added to the sub-layer input and normalized. In addition, we apply dropout to the sums of the embeddings and the positional encodings in both the encoder and decoder stacks. For the base model, we use a rate of Pdrop = 0.1. Label Smoothing During training, we employed label smoothing of value ϵls = 0.1 [36]. This hurts perplexity, as the model learns to be more unsure, but improves accuracy and BLEU score.
- C2 [1706.03762v7 §3.5 p.6] (bm25 38.7, ce 1.138): 3.5 Positional Encoding Since our model contains no recurrence and no convolution, in order for the model to make use of the order of the sequence, we must inject some information about the relative or absolute position of the tokens in the sequence. To this end, we add "positional encodings" to the input embeddings at the bottoms of the encoder and decoder stacks. The positional encodings have the same dimension dmodel as the embeddings, so that the two can be summed. There are many choices of positional encodings, learned and fixed [9]. In this work, we use sine and cosine functions of different frequencies: PE(pos,2i) = sin(pos/100002i/dmodel) PE(pos,2i+1) = cos(pos/100002i/dmodel) where pos is the position and i is the dimension. That is, each dimension of the positional encoding corresponds to a sinusoid. The wavelengths form a geometric progression from 2π to 10000 · 2π. We chose this function because we hypothesized it would allow the model to easily learn to attend by relative positions, since for any fixed offset k, PEpos+k can be represented as a linear function of PEpos. We also experimented with using learned positional embeddings [9] instead, and found that the two versions produced nearly identical results (see Table 3 row (E)). We chose the sinusoidal version because it may allow the model to extrapolate to sequence lengths longer than the ones encountered during training.
- C3 [1706.03762v7 §6.2 p.9] (bm25 35.27, ce 1.435): vary the number of attention heads and the attention key and value dimensions, keeping the amount of computation constant, as described in Section 3.2.2. While single-head attention is 0.9 BLEU worse than the best setting, quality also drops off with too many heads. In Table 3 rows (B), we observe that reducing the attention key size dk hurts model quality. This suggests that determining compatibility is not easy and that a more sophisticated compatibility function than dot product may be beneficial. We further observe in rows (C) and (D) that, as expected, bigger models are better, and dropout is very helpful in avoiding over-fitting. In row (E) we replace our sinusoidal positional encoding with learned positional embeddings [9], and observe nearly identical results to the base model.

grade: 

## Q43 x medium_k3_norerank
**Q:** In the ablation study for the chunking layer, what does "XAttn" stand for?

- reply: **refusal** / ok; degrade full; model -; first token 665.1 ms; total 665.1 ms; calls 1; limiter wait 0.0 ms; refuse reason gate
- gate: -3.931 by rewrite (raw -4.701, rewrite -3.931); query: XAttn chunking layer ablation study
- calls (in+out, cached): understand 244+82 (0 cached)

**Final reply:** The papers don't say. I searched all three papers (Attention Is All You Need v7, Moshi v1, Dynamic Chunking v2) and found nothing that answers this. Closest passages: [2507.07955v2 §C pp.35-36], [2410.00037v1 §5.2 pp.24-25], [2410.00037v1 §A p.53].
citations: ['[2507.07955v2 §C pp.35-36]', '[2410.00037v1 §5.2 pp.24-25]', '[2410.00037v1 §A p.53]']

**Passages the drafter saw:**
- C1 [2507.07955v2 §C pp.35-36] (bm25 11.31, ce -4.27): C Learning Rate Modulation As discussed in Section 2.3, we employ modulated learning rates for each stage by multiplying a scalar 𝜆𝑠to the base learning rate. Empirically, we find that a reasonable set of multipliers (e.g., 𝜆0 = 2.0, 𝜆1 = 1.5, 𝜆2 = 1.0) works well in general. To provide a more systematic experimental results across different architectural configurations, we follow previous works and set learning rates to be proportionally to the (1) square root of batch size (Malladi et al. 2022; Merrill et al. 2025), and (2) inverse square root of hidden dimension (Vaswani et al. 2017; Yang and Hu 2020). Concretely, without heavy manual tuning, we define 𝜆𝑠as follows: 𝑁GPT · 𝑖=𝑠𝑁𝑖 Î𝑆 𝑖=0 𝑁𝑖· 𝐷S 𝐷𝑠, 𝑁𝑆= 1.0 (11) Mean/Max Pooling (b) Pooling (c) (a) Default 100B 120B 140B Total Training Bytes 0.79 0.80 0.81 0.82 0.83 0.84 Bits-per-byte XAttn + Res XAttn Max + Res Max Mean + Res Mean Base Figure 13: Compression Methods in chunking layer. Default: H-Net’s Downsample operation (left-a). Max/Mean: Channel-wise max and mean pooling within boundaries (left-b). XAttn: Cross-attention pooling within boundaries (left-c). +Res: Adds boundary vector residuals to compressed outputs. where 𝑁GPT is the average number of bytes per token of training dataset, which is 4.6 for the GPT-2 tokenizer on FineWeb-Edu. We note that such principles for optimizing signal propagation as neural network hyperparameters change is an active area of research, and our scaling factors are just heuristics that can likely be improved.
- C2 [2410.00037v1 §5.2 pp.24-25] (bm25 8.74, ce -8.221): conversations. Discussion. Mimi overall provides high reconstruction quality while encoding semantic information, being fully causal, and operating at low framerate and bitrate. In consequence, Mimi proves to be a well-fitted audio tokenizer to train real-time audio language models. A collateral finding of our study is a concerning lack of correlation between objective and subjective audio quality metrics. In particular, while we find VisQOL to provide a reliable proxy for perceived quality when modifying the generator architecture, changing the training objective (e.g. removing reconstruction losses) moves the score in directions that are completely decorrelated from human perception. This observation underscores the open challenge of designing reliable objective proxies for perceived quality. Moshi: a speech-text foundation model for real-time dialogue Table 5: Ablation study on the use of the RQ-Transformer. All models are initialized with Helium and pretrained on audio. When not using RQ-Transformer, we predict the 8 levels of tokens with independent classification heads, following Copet et al. (2023). Note that perplexities are only comparable between models with a given delay, as the classification task is easier with more delay for higher tokens. Acoustic Delay RQ-Transformer Perplexity [0, 1, 2, 3, 4, 5, 6, 7] 42.2 [0, 1, 2, 3, 4, 5, 6, 7] ✓ 40.3 [0, 2, 2, 2, 2, 2, 2, 2] 135.4 [0, 2, 2, 2, 2, 2, 2, 2] ✓ 36.8 Table 6: Ablation study on delay patterns, weight of the semantic token and Inner Monologue. All models are initialized with Helium, pretrained on audio and use
- C3 [2410.00037v1 §A p.53] (bm25 7.92, ce -3.931): Appendix A. Additional ablation on Mimi codec Table 17: Ablation study on hyperparameters of the Mimi codec. We evaluate semantic modeling by reporting the error rate on a phonetic ABX discriminability task. To evaluate reconstruction quality, we compute VisQOL and MOSNet. “Quantization rate” refers to applying quantization to the latent space only 50% of the time during training (independently from quantizer dropout), as described in Section 3.3. Quantization Transformer Transformer WavLM Split ABX (↓) VisQOL (↑) MOSNet (↑) Rate in encoder in decoder distillation quantizer 31.3% 2.37 2.85 ✓ 31.4% 2.30 2.82 ✓ 27.5% 2.30 2.93 ✓ ✓ 29.0% 2.25 2.94 ✓ 29.1% 2.65 2.86 ✓ ✓ 27.4% 2.69 2.83 ✓ ✓ 23.6% 2.72 2.89 ✓ ✓ ✓ 23.3% 2.82 2.89 ✓ ✓ ✓ ✓ 6.5% 2.13 2.87 ✓ ✓ ✓ ✓ 10.8% 2.68 2.84 ✓ ✓ ✓ ✓ 8.1% 2.49 2.71 ✓ ✓ ✓ ✓ 8.0% 2.36 2.88 ✓ ✓ ✓ ✓ ✓ 8.1% 2.72 2.89

grade: 

## Q43 x medium_rerank
**Q:** In the ablation study for the chunking layer, what does "XAttn" stand for?

- reply: **refusal** / ok; degrade full; model -; first token 702.9 ms; total 702.9 ms; calls 1; limiter wait 0.0 ms; refuse reason gate
- gate: -0.197 by rewrite (raw -3.54, rewrite -0.197); query: XAttn chunking layer ablation study
- calls (in+out, cached): understand 244+74 (0 cached)

**Final reply:** The papers don't say. I searched all three papers (Attention Is All You Need v7, Moshi v1, Dynamic Chunking v2) and found nothing that answers this. Closest passages: [2507.07955v2 §E.1 pp.36-37], [2507.07955v2 §2.2.1 p.6], [2507.07955v2 §3.3 pp.17-18].
citations: ['[2507.07955v2 §E.1 pp.36-37]', '[2507.07955v2 §2.2.1 p.6]', '[2507.07955v2 §3.3 pp.17-18]']

**Passages the drafter saw:**
- C1 [2507.07955v2 §E.1 pp.36-37] (bm25 4.5, ce -0.197): E.1 Different Downsampling Methods in the Chunking Layer Given the dynamically determined boundaries from the boundary predictor, we explore various compression strategies in the chunking layer. We compare the default Downsample operation of H-Net (see Section 2.2.1) against three alternatives (see Figure 13-left): channel-wise max/mean pooling and cross-attention, all applied to vectors within the same boundary. Despite its simple design, the default compression in H-Net performs on-par with the other variants as demonstrated in Figure 13-right. This shows that the sequence mixing layers in encoder are trained to implicitly compress necessary context into vectors at boundaries, without explicit compression mechanisms such as pooling or cross-attention. Model Architecture Params. Final ppl. ↓ H-Net M3T1 + T15 + M4 64M 2.705 H-Net M3T1 + M15 + M4 66M 2.697 H-Net M4 + T15 + M4 62M 2.722 H-Net M4 + M15 + M4 64M 2.706 H-Net M4 + T1M13T1 + M4 64M 2.706 Table 7: Encoder architecture ablations on HG38. Switching the encoder architecture from M3T1 to M4 leads to worse performance across the board, though the results are still better than isotropic models (Table 5). Transformers in the encoder network do not appear to be helpful for text (Figure 8), suggesting that this finding may be modality-specific. Training Base Pairs Seen 2.75 2.80 2.85 2.90 2.95 Perplexity on HG38 H-Net (T1M13T1) H-Net (Trans.) H-Net (Mamba) Figure 14: Mamba-2-only encoder loss curves during the stable phase of training. The pure Mamba-2 model is more unstable with a loss spike. Adding Transformer layers
- C2 [2507.07955v2 §2.2.1 p.6] (bm25 4.54, ce -0.32): 2.2.1 Chunking Layer The chunking layer (Chunk in equation (2)) contains a routing module and downsampler, as illustrated in Figure 1- ( bottom-right ). Routing Module. In natural data, meaningful boundaries tend to emerge at points of contextual or semantic shift. From this observation, we add an inductive bias by measuring the similarity between adjacent representations: when context changes, consecutive vectors should exhibit lower similarity. The routing module implements this intuition through cosine similarity between adjacent encoder outputs. Given encoder outputs ˆ𝑋, it calculates boundary probabilities 𝑝𝑡and boundary indicators 𝑏𝑡as follows: 𝑞𝑡= 𝑊𝑞ˆ𝑥𝑡, 𝑘𝑡= 𝑊𝑘ˆ𝑥𝑡, 𝑝𝑡= 1 𝑡𝑘𝑡−1 ∥𝑞𝑡∥∥𝑘𝑡−1∥ ∈[0, 1], 𝑏𝑡= 1{𝑝𝑡≥0.5}, (4) where 𝑝1 = 1.0 by definition, ensuring the sequence begins with a boundary. This formulation scales cosine similarity into a boundary score or probability: ideally, when consecutive vectors ˆ𝑥𝑡−1 and ˆ𝑥𝑡span a semantic boundary (e.g., between morphemes, words, or phrases), their projections 𝑞𝑡and 𝑘𝑡−1 diverge in the latent space, yielding low cosine similarity and consequently high boundary probability 𝑝𝑡. Downsampler. The downsampler compresses encoder outputs ˆ𝑥𝑠into a reduced set of vectors 𝑥𝑠+1 using boundary indicators {𝑏𝑠 𝑡}𝐿𝑠 𝑡=1. Among potential compression strategies – including mean pooling, max pooling, or cross-attention – we adopt direct selection of boundary-marked vectors for its simplicity and effectiveness (see Appendix E.1 for ablations). As illustrated in Figure 1-(b), this approach follows a straightforward selection rule: vectors where 𝑏𝑡= 1 are retained in the compressed sequence 𝑥𝑠+1, while those where 𝑏𝑡= 0 are discarded. Likewise, the same downsampler applies to boundary probabilities,
- C3 [2507.07955v2 §3.3 pp.17-18] (bm25 6.83, ce -0.577): 3.3 Ablation Studies For ablation studies, we employ H-Net at Large scale following the configurations in Table 1, training on 36B tokens randomly sampled from FineWeb-Edu. Importance of Components in H-Net. Figure 7 illustrates the impact of each architectural component on both model performance and compression ratio (𝐿𝑠+1/𝐿𝑠) stability during training. We conduct three targeted ablations: (i) using direct upsampling ˜𝑧𝑡= ˆ𝑧𝑡by removing the smoothing module (w/o smoothing), (ii) replacing the routing module that is based on scaled cosine similarity, with direct probability prediction from individual inputs (w/o cosine routing), and (iii) skipping the straight-through estimator in equation (9) (w/o STE). The smoothing module proves essential for stable training dynamics. Without this module, compression ratios fluctuate 100B 125B Total Training Bytes 0.80 0.85 0.90 0.95 1.00 1.05 Bits-per-byte (2-stage) 100B 125B Total Training Bytes 0.34 0.35 0.36 0.37 0.38 Compression Ratio L1/L0 100B 125B Total Training Bytes 0.36 0.38 0.40 0.42 0.44 Compression Ratio L2/L1 H-Net w/o smoothing w/o cosine routing w/o STE Figure 7: Ablation study on key H-Net components showing validation BPB (left) and compression ratios for the first stage 𝐿1/𝐿0 (center) and second stage 𝐿2/𝐿1 (right) during training. Using H-Net (2-stage), we evaluate the impact of removing three components: the smoothing module (w/o smoothing), the similarity-based routing module (w/o cosine routing), and Straight-Through Estimator (w/o STE). 100B 120B 140B Total Training Bytes 0.80 0.82 0.84 0.86 0.88 0.90 0.92 0.94 Bits-per-byte 100B 120B 140B Total Training Bytes 0.21 0.22 0.23 0.24 Compression Ratio L1/L0 M4-M4 M2T1-T1M2 T1M2-M2T1
- C4 [2507.07955v2 §3.3 p.18] (bm25 6.05, ce -2.379): three components: the smoothing module (w/o smoothing), the similarity-based routing module (w/o cosine routing), and Straight-Through Estimator (w/o STE). 100B 120B 140B Total Training Bytes 0.80 0.82 0.84 0.86 0.88 0.90 0.92 0.94 Bits-per-byte 100B 120B 140B Total Training Bytes 0.21 0.22 0.23 0.24 Compression Ratio L1/L0 M4-M4 M2T1-T1M2 T1M2-M2T1 T2-T2 Figure 8: Encoder-decoder architecture ablation using raw byte inputs. Validation BPB (left) and compression ratio 𝐿1/𝐿0 (right) for H-Net (1-stage) throughout training. We evaluate four encoder-decoder (E0 −D0) configurations: M4-M4 , M2T1-T1M2 and T1M2-M2T1, and T2-T2, where M denotes Mamba layers and T denotes Transformer layers. severely throughout training, preventing the model from learning consistent chunking boundaries. This instability directly manifests as substantial performance degradation, confirming that smooth gradient flow through the decompression process is crucial for effective end-to-end learning. While less critical than the smoothing module, both the similarity-based routing module and STE operation exhibit importance in training stability and final performance. These components help maintain consistent compression ratios and lead to more interpretable chunking patterns. The similarity-based approach particularly enables the model to identify natural linguistic boundaries (e.g., whitespaces, subwords) by comparing adjacent representations rather than making isolated predictions. Encoder & Decoder Layer Selection. The composition of sequence mixing layers in H-Net’s encoders and decoders substantially influences both compression efficiency and modeling capability. We systematically evaluate different architectural combinations using H-Net (1-stage) while fixing all other configurations in Table 1 the same. Four distinct encoder-decoder (E0-D0) pairings are tested: M4-M4, M2T1-T1M2, T1M2-M2T1, and T2-T2, where M denotes
- C5 [2507.07955v2 §3 p.10] (bm25 4.45, ce -2.497): 3 Experiments We first describe our general experimental protocol for language modeling, used for the majority of our experiments. In Section 3.1, we evaluate on a high-quality English dataset, showing significantly stronger performance than baselines, as well as improved robustness and interpretability from avoiding tokenization. In Section 3.2, we extend our evaluation to diverse datasets including Chinese, code, and DNA, with even larger performance improvements, demonstrating H-Net’s versatility as a general sequence model architecture. In Section 3.3, we provide comprehensive ablations that study individual architectural components and design choices. Models. We compare against a standard tokenized Transformer following the Llama architecture (Touvron, Martin, et al. 2023; Grattafiori et al. 2024).11 We additionally compare against several byte-level baselines: • MambaByte (Wang et al. 2024) is an isotropic model using pure Mamba-2 layers. • LlamaByte is an isotropic model using pure Transformer layers. • SpaceByte (Slagle 2024) represents the canonical hierarchical architecture with external boundary supervision, which chunks on spaces and "space-like" bytes. 12 On English, the space-like delimiter heuristic empirically has an average ratio of 6.0 bytes per chunk. • SpaceByte++ is our modification of SpaceByte that includes our architectural modifications to the hierarchical structure (from Section 2.1). In particular, it changes the outer encoder/decoder networks to use Mamba-2, and modifies the layer counts and widths slightly to match the H-Net models below. • H-Net (space) further improves SpaceByte++ with our training improvements to the network (Section 2.3), in particular, adding post-network norms, residual projections, and learning rate multipliers on the
- C6 [2410.00037v1 §A p.53] (bm25 7.92, ce -3.931): Appendix A. Additional ablation on Mimi codec Table 17: Ablation study on hyperparameters of the Mimi codec. We evaluate semantic modeling by reporting the error rate on a phonetic ABX discriminability task. To evaluate reconstruction quality, we compute VisQOL and MOSNet. “Quantization rate” refers to applying quantization to the latent space only 50% of the time during training (independently from quantizer dropout), as described in Section 3.3. Quantization Transformer Transformer WavLM Split ABX (↓) VisQOL (↑) MOSNet (↑) Rate in encoder in decoder distillation quantizer 31.3% 2.37 2.85 ✓ 31.4% 2.30 2.82 ✓ 27.5% 2.30 2.93 ✓ ✓ 29.0% 2.25 2.94 ✓ 29.1% 2.65 2.86 ✓ ✓ 27.4% 2.69 2.83 ✓ ✓ 23.6% 2.72 2.89 ✓ ✓ ✓ 23.3% 2.82 2.89 ✓ ✓ ✓ ✓ 6.5% 2.13 2.87 ✓ ✓ ✓ ✓ 10.8% 2.68 2.84 ✓ ✓ ✓ ✓ 8.1% 2.49 2.71 ✓ ✓ ✓ ✓ 8.0% 2.36 2.88 ✓ ✓ ✓ ✓ ✓ 8.1% 2.72 2.89

grade: 

## Q43 x medium_norerank
**Q:** In the ablation study for the chunking layer, what does "XAttn" stand for?

- reply: **refusal** / ok; degrade full; model -; first token 745.5 ms; total 745.5 ms; calls 1; limiter wait 0.0 ms; refuse reason gate
- gate: -0.577 by rewrite (raw -3.54, rewrite -0.577); query: XAttn chunking layer ablation study
- calls (in+out, cached): understand 244+45 (0 cached)

**Final reply:** The papers don't say. I searched all three papers (Attention Is All You Need v7, Moshi v1, Dynamic Chunking v2) and found nothing that answers this. Closest passages: [2507.07955v2 §C pp.35-36], [2410.00037v1 §5.2 pp.24-25], [2410.00037v1 §A p.53].
citations: ['[2507.07955v2 §C pp.35-36]', '[2410.00037v1 §5.2 pp.24-25]', '[2410.00037v1 §A p.53]']

**Passages the drafter saw:**
- C1 [2507.07955v2 §C pp.35-36] (bm25 11.31, ce -4.27): C Learning Rate Modulation As discussed in Section 2.3, we employ modulated learning rates for each stage by multiplying a scalar 𝜆𝑠to the base learning rate. Empirically, we find that a reasonable set of multipliers (e.g., 𝜆0 = 2.0, 𝜆1 = 1.5, 𝜆2 = 1.0) works well in general. To provide a more systematic experimental results across different architectural configurations, we follow previous works and set learning rates to be proportionally to the (1) square root of batch size (Malladi et al. 2022; Merrill et al. 2025), and (2) inverse square root of hidden dimension (Vaswani et al. 2017; Yang and Hu 2020). Concretely, without heavy manual tuning, we define 𝜆𝑠as follows: 𝑁GPT · 𝑖=𝑠𝑁𝑖 Î𝑆 𝑖=0 𝑁𝑖· 𝐷S 𝐷𝑠, 𝑁𝑆= 1.0 (11) Mean/Max Pooling (b) Pooling (c) (a) Default 100B 120B 140B Total Training Bytes 0.79 0.80 0.81 0.82 0.83 0.84 Bits-per-byte XAttn + Res XAttn Max + Res Max Mean + Res Mean Base Figure 13: Compression Methods in chunking layer. Default: H-Net’s Downsample operation (left-a). Max/Mean: Channel-wise max and mean pooling within boundaries (left-b). XAttn: Cross-attention pooling within boundaries (left-c). +Res: Adds boundary vector residuals to compressed outputs. where 𝑁GPT is the average number of bytes per token of training dataset, which is 4.6 for the GPT-2 tokenizer on FineWeb-Edu. We note that such principles for optimizing signal propagation as neural network hyperparameters change is an active area of research, and our scaling factors are just heuristics that can likely be improved.
- C2 [2410.00037v1 §5.2 pp.24-25] (bm25 8.74, ce -8.221): conversations. Discussion. Mimi overall provides high reconstruction quality while encoding semantic information, being fully causal, and operating at low framerate and bitrate. In consequence, Mimi proves to be a well-fitted audio tokenizer to train real-time audio language models. A collateral finding of our study is a concerning lack of correlation between objective and subjective audio quality metrics. In particular, while we find VisQOL to provide a reliable proxy for perceived quality when modifying the generator architecture, changing the training objective (e.g. removing reconstruction losses) moves the score in directions that are completely decorrelated from human perception. This observation underscores the open challenge of designing reliable objective proxies for perceived quality. Moshi: a speech-text foundation model for real-time dialogue Table 5: Ablation study on the use of the RQ-Transformer. All models are initialized with Helium and pretrained on audio. When not using RQ-Transformer, we predict the 8 levels of tokens with independent classification heads, following Copet et al. (2023). Note that perplexities are only comparable between models with a given delay, as the classification task is easier with more delay for higher tokens. Acoustic Delay RQ-Transformer Perplexity [0, 1, 2, 3, 4, 5, 6, 7] 42.2 [0, 1, 2, 3, 4, 5, 6, 7] ✓ 40.3 [0, 2, 2, 2, 2, 2, 2, 2] 135.4 [0, 2, 2, 2, 2, 2, 2, 2] ✓ 36.8 Table 6: Ablation study on delay patterns, weight of the semantic token and Inner Monologue. All models are initialized with Helium, pretrained on audio and use
- C3 [2410.00037v1 §A p.53] (bm25 7.92, ce -3.931): Appendix A. Additional ablation on Mimi codec Table 17: Ablation study on hyperparameters of the Mimi codec. We evaluate semantic modeling by reporting the error rate on a phonetic ABX discriminability task. To evaluate reconstruction quality, we compute VisQOL and MOSNet. “Quantization rate” refers to applying quantization to the latent space only 50% of the time during training (independently from quantizer dropout), as described in Section 3.3. Quantization Transformer Transformer WavLM Split ABX (↓) VisQOL (↑) MOSNet (↑) Rate in encoder in decoder distillation quantizer 31.3% 2.37 2.85 ✓ 31.4% 2.30 2.82 ✓ 27.5% 2.30 2.93 ✓ ✓ 29.0% 2.25 2.94 ✓ 29.1% 2.65 2.86 ✓ ✓ 27.4% 2.69 2.83 ✓ ✓ 23.6% 2.72 2.89 ✓ ✓ ✓ 23.3% 2.82 2.89 ✓ ✓ ✓ ✓ 6.5% 2.13 2.87 ✓ ✓ ✓ ✓ 10.8% 2.68 2.84 ✓ ✓ ✓ ✓ 8.1% 2.49 2.71 ✓ ✓ ✓ ✓ 8.0% 2.36 2.88 ✓ ✓ ✓ ✓ ✓ 8.1% 2.72 2.89
- C4 [2507.07955v2 §3.3 pp.17-18] (bm25 6.83, ce -0.577): 3.3 Ablation Studies For ablation studies, we employ H-Net at Large scale following the configurations in Table 1, training on 36B tokens randomly sampled from FineWeb-Edu. Importance of Components in H-Net. Figure 7 illustrates the impact of each architectural component on both model performance and compression ratio (𝐿𝑠+1/𝐿𝑠) stability during training. We conduct three targeted ablations: (i) using direct upsampling ˜𝑧𝑡= ˆ𝑧𝑡by removing the smoothing module (w/o smoothing), (ii) replacing the routing module that is based on scaled cosine similarity, with direct probability prediction from individual inputs (w/o cosine routing), and (iii) skipping the straight-through estimator in equation (9) (w/o STE). The smoothing module proves essential for stable training dynamics. Without this module, compression ratios fluctuate 100B 125B Total Training Bytes 0.80 0.85 0.90 0.95 1.00 1.05 Bits-per-byte (2-stage) 100B 125B Total Training Bytes 0.34 0.35 0.36 0.37 0.38 Compression Ratio L1/L0 100B 125B Total Training Bytes 0.36 0.38 0.40 0.42 0.44 Compression Ratio L2/L1 H-Net w/o smoothing w/o cosine routing w/o STE Figure 7: Ablation study on key H-Net components showing validation BPB (left) and compression ratios for the first stage 𝐿1/𝐿0 (center) and second stage 𝐿2/𝐿1 (right) during training. Using H-Net (2-stage), we evaluate the impact of removing three components: the smoothing module (w/o smoothing), the similarity-based routing module (w/o cosine routing), and Straight-Through Estimator (w/o STE). 100B 120B 140B Total Training Bytes 0.80 0.82 0.84 0.86 0.88 0.90 0.92 0.94 Bits-per-byte 100B 120B 140B Total Training Bytes 0.21 0.22 0.23 0.24 Compression Ratio L1/L0 M4-M4 M2T1-T1M2 T1M2-M2T1
- C5 [2507.07955v2 §3.3 pp.18-19] (bm25 6.43, ce -4.835): sequence mixing layers in H-Net’s encoders and decoders substantially influences both compression efficiency and modeling capability. We systematically evaluate different architectural combinations using H-Net (1-stage) while fixing all other configurations in Table 1 the same. Four distinct encoder-decoder (E0-D0) pairings are tested: M4-M4, M2T1-T1M2, T1M2-M2T1, and T2-T2, where M denotes a Mamba-2 100B 120B 140B Total Training Bytes 0.82 0.84 0.86 0.88 0.90 0.92 0.94 Bits-per-byte T2-T2 T1M2-M2T1 M2T1-T1M2 M4-M4 Figure 9: SpaceByte++ encoder-decoder architecture ablation using raw byte inputs. We evaluate four encoder-decoder (E0 −D0) configurations: M4-M4 , M2T1-T1M2 and T1M2-M2T1, and T2-T2, where M denotes Mamba layers and T denotes Transformer layers. 100B 120B 140B Total Training Bytes 0.825 0.850 0.875 0.900 0.925 0.950 0.975 1.000 Bits-per-byte T3-T3 T2M2-M2T2 M2T2-T2M2 T1M4-M4T1 M4T1-T1M4 M6-M6 Figure 10: Encoder-decoder architecture ablation using BPE-tokenized inputs. Assuming that GPT-2 tokenizer serves as the outermost encoder-decoder (i.e., E0-D0), we evaluate six E1-D1 combinations: M6-M6, M4T1-T1M4, T1M4-M4T1, M2T2-T2M2, T2M2-M2T2, and T3-T3. layer and T denotes a Transformer layer. These combinations are chosen by keeping the symmetry and replacing each Transformer layer with two Mamba-2 layers, as they contain equivalent parameter counts — 12𝐷2 for Transformer (4𝐷2 for the attention mechanism and 8𝐷2 for an MLP) vs. ≈6𝐷2 per Mamba-2 layer (no MLP). Figure 8 and Figure 9 demonstrate that Mamba layers are essential for effective byte-level sequence processing. For both H-Net and SpaceByte++, the pure Transformer configuration (T2-T2) exhibits by far the worst performance despite using more FLOPs (it also down-compresses sequences poorly compared to
- C6 [2507.07955v2 §2.1.1 p.5] (bm25 6.42, ce -5.232): belong to the same stage. Drawing inspiration from the U-Net architecture (Ronneberger, Fischer, and Brox 2015), H-Net progressively compresses input sequences into fewer vectors with richer semantic embeddings through a chunking layer, processes these representations in the main network, then decompresses the sequence back to its original resolution using a dechunking layer. Unlike traditional U-Net designs, however, H-Net dynamically determines chunking boundaries rather than using fixed-size pooling operations. The overall pipeline can be formalized as: ˆ𝑥𝑠= E𝑠(𝑥𝑠), ˆ𝑧𝑆= M(𝑥𝑆), ˆ𝑧𝑠= D𝑠(𝑧𝑠), (1) where the chunking layer and the dechunking layer operations are defined as: (𝑥𝑠+1, 𝑝𝑠) = Chunk( ˆ𝑥𝑠), (2) 𝑧𝑠= Dechunk(ˆ𝑧𝑠+1, 𝑝𝑠) + Linear( ˆ𝑥𝑠). (3) The initial input to the model is 𝑥0 ∈R𝐿0×𝐷0 where 𝐿0 is the input sequence length and 𝐷0 is the embedding dimension. Intuitively, 𝑝𝑠∈[0, 1]𝐿𝑠represents the chunking router’s confidence that the token should be passed into the main stage. 7 This value is essential for both the chunk (Section 2.2.1) and dechunk operations (Section 2.2.2).

grade: 

## Q12 x medium_k3_norerank
**Q:** In zero-shot TTS, exactly what fraction of padding tokens do they target to control the speech rate?

- reply: **answer** / ok; degrade small_model; model openai/gpt-oss-20b; first token 1667.7 ms; total 1667.7 ms; calls 3; limiter wait 0.0 ms
- gate: 4.866 by raw (raw 4.866, rewrite 4.806); query: zero-shot TTS padding tokens fraction speech rate
- calls (in+out, cached): understand 251+100 (0 cached), draft 1374+104 (0 cached), check 571+34 (0 cached)

**Draft 0 (openai/gpt-oss-20b):** The papers state that Appendix C. Delayed text LM as a zero-shot streaming ASR and TTS As explained in Section 3.4.4, Moshi [C1].
  - C1: "Appendix C. Delayed text LM as a zero-shot streaming ASR and TTS As explained in Section 3.4.4, Moshi"
  - code check: OK
  - model check: OK

**Final reply:** The papers state that Appendix C. Delayed text LM as a zero-shot streaming ASR and TTS As explained in Section 3.4.4, Moshi [2410.00037v1 §C p.55].
citations: ['[2410.00037v1 §C p.55]']

**Passages the drafter saw:**
- C1 [2410.00037v1 §C p.55] (bm25 41.98, ce 4.025): Appendix C. Delayed text LM as a zero-shot streaming ASR and TTS As explained in Section 3.4.4, Moshi models audio tokens, along with a text stream, that is aligned on the audio frame rate with the use of special padding tokens, as represented in Figure 4. We can adapt this method for ASR and TTS by introducing a delay between the audio and text tokens. In both case, the model operates in full streaming mode, with a fixed latency (here 2 seconds). ASR mode. If the audio is ahead of the text, we ignore the model prediction for the audio tokens, using instead those of some audio input, and sample the text tokens freely. Then the text streams contains the audio transcription, with fine alignments at the word level, as depicted in Figure 8. TTS mode. If the text is ahead of the audio, we can symmetrically derive a TTS engine. We need for that a properly padded set of text tokens. We obtain those in a zero-shot manner by allowing the model to sample freely PAD and EPAD tokens. As soon as the model tries to sample a different token, we instead input the next word to generate. Note that we can further control the rate of the speech by keeping an online average of the fraction of padding tokens. By introducing a small bonus on their logits when this fraction falls below a given target value, we ensure reasonable rate and a good intelligibility in all situations. Finally,
- C2 [2410.00037v1 §C pp.55-56] (bm25 34.58, ce 4.866): that we can further control the rate of the speech by keeping an online average of the fraction of padding tokens. By introducing a small bonus on their logits when this fraction falls below a given target value, we ensure reasonable rate and a good intelligibility in all situations. Finally, using a prefix with both text and audio tokens, we can control the voice of the speaker. A representation is given in Figure 9. Multistream TTS. We use this mechanism both in single and multistream mode. In multistream mode, the model outputs two sets of audio tokens. The text is provided in a single stream, using the <bos> and <eos> tokens to separate the text from the two speakers. Moshi: a speech-text foundation model for real-time dialogue ASR( ) tokens Semantic tokens shot Text token acoustic delay Token sampled by the model. Tokens forced into the model. ⎵T ⎵synthesis 2 seconds text vs. audio delay. Figure 8: Representation of the joint sequence modeled by Moshi. Representation of the joint sequence modeled by Moshi when used in ASR mode. Each column represents the tokens for a given step in the joint sequence (Vs,k), similar to the one described in Equation 6, but adapted for ASR. The text is delayed by 2 seconds, and we use an acoustic token delay τ = 2. Tokens are predicted from bottom to top in the depth Transformer. The audio tokens are kept to match those of the input audio, while text tokens are sampled freely.
- C3 [2410.00037v1 §C pp.56-57] (bm25 23.03, ce 0.555): but adapted for ASR. The text is delayed by 2 seconds, and we use an acoustic token delay τ = 2. Tokens are predicted from bottom to top in the depth Transformer. The audio tokens are kept to match those of the input audio, while text tokens are sampled freely. This methods also provides fine timestamps for the words. Moshi: a speech-text foundation model for real-time dialogue TTS("Zero-shot TTS synthesis.") Queue of words to generate EPAD tokens Semantic tokens 0 Text token 2 seconds text/audio delay Force text token from first word. Let the model sample only PAD or EPAD. No more words, only PAD predictions allowed. Once the model predicts something else, fill with PAD for 2 seconds to generate the acoustic tokens. acoustic delay Zero - shot ⎵synthesis . If the model predicts something else, forces next word into the text input. prediction Hello PAD EPAD means hanks wor for Token sampled by the model. Tokens forced into the model. ⎵T ⎵synthesis Tokens predicted but ignored. Figure 9: Representation of the joint sequence modeled by Moshi when used in TTS mode. Each column represent the tokens for a given step in the joint sequence (Vs,k), similar to the one described in Equation 6, but adapted for TTS. The audio is delayed by 2 seconds, and we use an acoustic token delay τ = 2. Tokens are predicted from bottom to top in the depth Transformer. Text predictions are usually ignored, and the tokens from the text to generate

grade: 

## Q12 x medium_rerank
**Q:** In zero-shot TTS, exactly what fraction of padding tokens do they target to control the speech rate?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.2 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q12 x medium_norerank
**Q:** In zero-shot TTS, exactly what fraction of padding tokens do they target to control the speech rate?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.3 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q26 x medium_rerank
**Q:** What specific mathematical function is used to create smooth interpolations between chunks during the upsampling process?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.2 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q26 x medium_norerank
**Q:** What specific mathematical function is used to create smooth interpolations between chunks during the upsampling process?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.2 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q26 x medium_k3_norerank
**Q:** What specific mathematical function is used to create smooth interpolations between chunks during the upsampling process?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.2 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q40 x medium_norerank
**Q:** How many sentence pairs are in the standard WMT 2014 English-German dataset used for training?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.1 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q40 x medium_k3_norerank
**Q:** How many sentence pairs are in the standard WMT 2014 English-German dataset used for training?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.2 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q40 x medium_rerank
**Q:** How many sentence pairs are in the standard WMT 2014 English-German dataset used for training?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.2 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q45 x medium_rerank
**Q:** What is the Exact Match (EM) score of the Helium model on the SQuAD 2.0 benchmark?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.2 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q45 x medium_norerank
**Q:** What is the Exact Match (EM) score of the Helium model on the SQuAD 2.0 benchmark?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.3 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q45 x medium_k3_norerank
**Q:** What is the Exact Match (EM) score of the Helium model on the SQuAD 2.0 benchmark?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.2 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q49 x medium_k3_norerank
**Q:** How does the Transformer's self-attention mechanism perform on TPUv4 hardware accelerators?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.2 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q49 x medium_rerank
**Q:** How does the Transformer's self-attention mechanism perform on TPUv4 hardware accelerators?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.2 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q49 x medium_norerank
**Q:** How does the Transformer's self-attention mechanism perform on TPUv4 hardware accelerators?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.2 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q15 x medium_k3_norerank
**Q:** In their base model, how many attention heads do they use in total per layer?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.1 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q15 x medium_rerank
**Q:** In their base model, how many attention heads do they use in total per layer?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.1 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q15 x medium_norerank
**Q:** In their base model, how many attention heads do they use in total per layer?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.1 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q35 x medium_norerank
**Q:** During the ablation of the chunking layer compression methods, which technique was the default Downsample operation compared against?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.1 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q35 x medium_k3_norerank
**Q:** During the ablation of the chunking layer compression methods, which technique was the default Downsample operation compared against?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.1 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q35 x medium_rerank
**Q:** During the ablation of the chunking layer compression methods, which technique was the default Downsample operation compared against?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.1 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q48 x medium_norerank
**Q:** What is the validation perplexity of the Transformer when evaluated on the GLUE benchmark?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.1 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q48 x medium_k3_norerank
**Q:** What is the validation perplexity of the Transformer when evaluated on the GLUE benchmark?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.1 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q48 x medium_rerank
**Q:** What is the validation perplexity of the Transformer when evaluated on the GLUE benchmark?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.1 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q32 x medium_rerank
**Q:** Why did the authors choose a target compression ratio of N=8 for the one-stage H-Net model?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.1 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q32 x medium_norerank
**Q:** Why did the authors choose a target compression ratio of N=8 for the one-stage H-Net model?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.1 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q32 x medium_k3_norerank
**Q:** Why did the authors choose a target compression ratio of N=8 for the one-stage H-Net model?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.1 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q7 x medium_k3_norerank
**Q:** How many points behind Mistral is their text backbone on MMLU?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.1 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q7 x medium_rerank
**Q:** How many points behind Mistral is their text backbone on MMLU?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.1 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q7 x medium_norerank
**Q:** How many points behind Mistral is their text backbone on MMLU?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.1 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q34 x medium_k3_norerank
**Q:** How does the inference wall-clock speed of the 2-stage H-Net compare to the Block Transformer on the Chinese language modeling dataset?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.1 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q34 x medium_rerank
**Q:** How does the inference wall-clock speed of the 2-stage H-Net compare to the Block Transformer on the Chinese language modeling dataset?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.1 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q34 x medium_norerank
**Q:** How does the inference wall-clock speed of the 2-stage H-Net compare to the Block Transformer on the Chinese language modeling dataset?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.1 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q8 x medium_k3_norerank
**Q:** What MUSHRA score did the baseline tokenizer from Zhang get at 1.5kbps?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.2 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q8 x medium_rerank
**Q:** What MUSHRA score did the baseline tokenizer from Zhang get at 1.5kbps?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.2 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q8 x medium_norerank
**Q:** What MUSHRA score did the baseline tokenizer from Zhang get at 1.5kbps?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.2 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q47 x medium_norerank
**Q:** How does Moshi's text backbone integrate with the CLIP vision encoder for multimodal tasks?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.2 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q47 x medium_k3_norerank
**Q:** How does Moshi's text backbone integrate with the CLIP vision encoder for multimodal tasks?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.1 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q47 x medium_rerank
**Q:** How does Moshi's text backbone integrate with the CLIP vision encoder for multimodal tasks?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.1 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q18 x medium_norerank
**Q:** What is the maximum path length for a single convolutional layer with kernel width k < n?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.1 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q18 x medium_k3_norerank
**Q:** What is the maximum path length for a single convolutional layer with kernel width k < n?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.1 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q18 x medium_rerank
**Q:** What is the maximum path length for a single convolutional layer with kernel width k < n?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.1 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q25 x medium_k3_norerank
**Q:** What is the downsampling target ratio for the first stage of their two-stage byte-level model?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.1 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q25 x medium_rerank
**Q:** What is the downsampling target ratio for the first stage of their two-stage byte-level model?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.1 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q25 x medium_norerank
**Q:** What is the downsampling target ratio for the first stage of their two-stage byte-level model?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.1 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q4 x medium_norerank
**Q:** When they drop quantization during training for the audio codec, what exactly gets fed into the decoder?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.1 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q4 x medium_k3_norerank
**Q:** When they drop quantization during training for the audio codec, what exactly gets fed into the decoder?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.1 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q4 x medium_rerank
**Q:** When they drop quantization during training for the audio codec, what exactly gets fed into the decoder?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.1 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q9 x medium_rerank
**Q:** For the Moshi model after multi-stream instruct tuning, what is the exact MMLU score when weights are quantized to 4 bits (W4A8) using a block size of 32?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.1 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q9 x medium_norerank
**Q:** For the Moshi model after multi-stream instruct tuning, what is the exact MMLU score when weights are quantized to 4 bits (W4A8) using a block size of 32?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.1 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

## Q9 x medium_k3_norerank
**Q:** For the Moshi model after multi-stream instruct tuning, what is the exact MMLU score when weights are quantized to 4 bits (W4A8) using a block size of 32?

- reply: **busy** / rate_limited; degrade full; model -; first token None ms; total 0.1 ms; calls 0; limiter wait 0.0 ms
- gate: None by None (raw None, rewrite None); query: None
- calls (in+out, cached): none

**Final reply:** I can't give you a checked answer right now: the assistant has hit its per-minute usage limit. Capacity for a question like yours should be back in under a minute (around 12:39). I won't send an unchecked answer instead. Please ask again then.
citations: []

**Passages the drafter saw:**

grade: 

