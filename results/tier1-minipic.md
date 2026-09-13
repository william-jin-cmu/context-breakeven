# Tier 1 results

## Phase A — stock vLLM 0.15.0 prefix-only caching, Qwen3-8B (control)
Replay of 268 real per-step state prompts (6 Tier-0 tasks), cache hits via /metrics token counters.
| layout | prompt tok | cached tok | hit% |
|---|---|---|---|
| append | 1,024,808 | 788,128 | 77% |
| span   | 1,021,518 | 752,672 | 74% |
Span < append under prefix-only caching (reordering a fact diverges the prefix earlier; stock vLLM can't reuse a reordered span). Confirms span needs position-independent reuse (MiniPIC) to pay off. Phase B must flip span above append.

## Phase B — MiniPIC block attention, Qwen3-8B (vanilla, NOT block-FT)
Fork: IBM vllm span-semantics (VLLM_V1_SPANS_ENABLED, TRITON_ATTN, block_size 16), markers PLUS=10/CROSS=31/PAD=27.
| arm | prompt tok | cached tok | hit% |
|---|---|---|---|
| append_text | 1,024,808 | 788,128 | 77% |
| span_text   | 1,021,518 | 752,672 | 74% |
| span_reuse (block attn) | 1,060,208 | 781,568 | 74% |
Accuracy gate (span_reuse vs full attention, 40 prompts): exact 2%, greedy-prefix-agreement 7.7%.
=> On a vanilla model block attention DESTROYS output quality and gives NO cache-hit gain. Matches MiniPIC's own use of a block-attention-finetuned model. Next: test ldsjmdy/Tulu3-Block-FT (designed for this).

## Phase B — Tulu3-Block-FT (Llama-3-8B finetuned FOR block attention)
Context-filtered to <=7400 tok (244/268 prompts; Llama ctx 8192).
| arm | prompt tok | cached tok | hit% |
|---|---|---|---|
| append_text | 739,052 | 697,472 | 94% |
| span_text   | 735,667 | 536,928 | 73% |
| span_reuse (block attn) | 765,931 | 559,152 | 73% |
Span_reuse reused slightly more KV in absolute terms (559k vs 537k) but padding overhead (+30k prompt) erased the % gain. Append-only dominates (94%).
Accuracy (valid generation cue, span_reuse vs full attention): vanilla Qwen3-8B 7.7% agreement; Tulu3-Block-FT 35% agreement (exact 1/30). Even the block-FT model degrades badly on our many-small-span agent state (its finetuning was for a few RAG docs).

## TIER 1 VERDICT: negative
1. No cache-cost gain: append-only 94% >> span/span-reuse 73%. Position-independent reuse can't help because agent state churns too much per step; append-only maximizes the stable cached prefix.
2. Block attention needs a specially-finetuned model (vanilla Qwen3 -> 7.7% garbage).
3. Even the block-FT model only reaches 35% agreement on structured agent state (finetuned for RAG docs, not many small spans).
=> Confirms Tier 0 + rjgg: in a prefix-caching world, append-only wins; neither client-side layout (Tier 0) nor co-designed position-independent KV (Tier 1) beats it for this workload.
