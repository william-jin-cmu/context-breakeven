#!/usr/bin/env python3
"""Accuracy gate (Phase B, runs ON the pod with the MiniPIC fork).
For each sampled prompt, greedily generate a continuation TWO ways:
  (full)  plain text prompt -> normal full causal attention (reference)
  (reuse) token-id prompt with SSEP inserted at span boundaries -> MiniPIC reuse
Compare: exact-match length of the two greedy continuations (prefix agreement)
and whether the full generations are identical. A high match rate => MiniPIC's
approximate KV reuse preserves quality. Usage: accuracy.py [prompts.jsonl] [n]
"""
import json, os, sys, urllib.request
from transformers import AutoTokenizer
EP = os.environ.get("VLLM_URL", "http://127.0.0.1:8000")
MODEL = os.environ.get("MODEL", "Qwen/Qwen3-8B")
SEP = " # # "
SSEP_ID = os.environ.get("SSEP_ID")   # set in Phase B
BLOCK = int(os.environ.get("BLOCK", "16"))
N = int(sys.argv[2]) if len(sys.argv) > 2 else 40
GEN = 48
tok = AutoTokenizer.from_pretrained(MODEL)

def gen(prompt, is_ids):
    body = {"model": MODEL, "prompt": prompt, "max_tokens": GEN, "temperature": 0}
    req = urllib.request.Request(f"{EP}/v1/completions",
          data=json.dumps(body).encode(), headers={"Content-Type":"application/json"})
    return json.load(urllib.request.urlopen(req, timeout=180))["choices"][0]["text"]

def ids_with_ssep(text):
    ids=[]
    for i,span in enumerate(text.split(SEP)):
        if i and SSEP_ID: ids.append(int(SSEP_ID))
        e=tok.encode(span, add_special_tokens=False)
        r=len(e)%BLOCK
        if r: e += [tok.pad_token_id or tok.eos_token_id]*(BLOCK-r)
        ids+=e
    return ids

rows=[json.loads(l) for l in open(sys.argv[1] if len(sys.argv)>1 else "tier1/prompts.jsonl")]
rows=[r for r in rows if r.get("span")][:N]
exact=0; agree_tokens=0; total_tokens=0
for r in rows:
    full = gen(r["span"], False)                 # plain text, full attention
    reuse = gen(ids_with_ssep(r["span"]), True)   # token-ids + SSEP, MiniPIC reuse
    ft=tok.encode(full, add_special_tokens=False); rt=tok.encode(reuse, add_special_tokens=False)
    m=0
    for a,b in zip(ft,rt):
        if a==b: m+=1
        else: break
    agree_tokens+=m; total_tokens+=max(len(ft),1); exact += (full==reuse)
print(f"prompts={len(rows)} exact_match={exact}/{len(rows)} ({100*exact/len(rows):.0f}%)")
print(f"mean greedy-prefix agreement = {100*agree_tokens/total_tokens:.1f}% of {GEN} tokens")
