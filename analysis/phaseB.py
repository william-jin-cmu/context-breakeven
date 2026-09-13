#!/usr/bin/env python3
"""Phase B on the MiniPIC fork server. Three cost arms + accuracy gate.
  append_text : r['append'] as text  (mutable tail last; prefix-cache friendly)
  span_text   : r['span']   as text  (no markers -> plain prefix cache)
  span_reuse  : r['span']   as MiniPIC token-id prompt (PLUS/CROSS markers -> block attn)
Cost via /metrics prefix_cache hit deltas (MiniPIC reuse counts here, since it
makes block hashes position-independent). Accuracy: greedy 48-tok continuation,
span_reuse vs full-text, token-prefix agreement.
Usage: phaseB.py <prompts.jsonl> [acc_n]"""
import json, sys, urllib.request, collections, re
from transformers import AutoTokenizer
import minipic
import os
EP="http://127.0.0.1:8000"; MODEL=os.environ.get("MODEL","Qwen/Qwen3-8B")
tok=AutoTokenizer.from_pretrained(MODEL)
def metrics():
    t=urllib.request.urlopen(f"{EP}/metrics",timeout=30).read().decode()
    def g(n):
        m=re.search(rf"vllm:{n}_total\{{[^}}]*}} ([0-9.e+]+)",t);return float(m.group(1)) if m else 0.0
    return g("prefix_cache_queries"), g("prefix_cache_hits")
def post(prompt, mt):
    body=json.dumps({"model":MODEL,"prompt":prompt,"max_tokens":mt,"temperature":0}).encode()
    req=urllib.request.Request(f"{EP}/v1/completions",data=body,headers={"Content-Type":"application/json"})
    j=json.load(urllib.request.urlopen(req,timeout=180))
    return j["choices"][0]["text"], j["usage"]["prompt_tokens"]
rows=[json.loads(l) for l in open(sys.argv[1] if len(sys.argv)>1 else "prompts.jsonl")]
MAXTOK=7400
rows=[r for r in rows if len(tok.encode(r["append"]))<=MAXTOK and len(tok.encode(r["span"]))<=MAXTOK]
print(f"(kept {len(rows)} prompts after <= {MAXTOK}-token filter)")
by=collections.OrderedDict()
for r in rows: by.setdefault(r["task"],[]).append(r)
for seq in by.values(): seq.sort(key=lambda r:r["step"] or 0)
def prompt_for(arm, r):
    if arm=="append_text": return r["append"]
    if arm=="span_text":   return r["span"]
    return minipic.build(tok, r["span"])   # span_reuse -> token ids
print("== COST (prefix-cache hit via /metrics) ==")
print(f"{'arm':12s} {'prompt':>10s} {'cached':>10s} {'hit%':>5s}")
for arm in ("append_text","span_text","span_reuse"):
    tp=tc=0
    for seq in by.values():
        q0,h0=metrics(); pt=0
        for r in seq: _,n=post(prompt_for(arm,r),1); pt+=n
        q1,h1=metrics(); tp+=pt; tc+=int(h1-h0)
    print(f"{arm:12s} {tp:>10} {tc:>10} {100*tc/tp if tp else 0:>4.0f}%")
# ACCURACY
N=int(sys.argv[2]) if len(sys.argv)>2 else 40
sample=[r for seq in by.values() for r in seq][:N]
exact=agree=total=0
for r in sample:
    full,_=post(r["span"],48)
    reuse,_=post(minipic.build(tok,r["span"]),48)
    ft=tok.encode(full,add_special_tokens=False); rt=tok.encode(reuse,add_special_tokens=False)
    m=0
    for a,b in zip(ft,rt):
        if a==b:m+=1
        else:break
    agree+=m; total+=max(len(ft),1); exact+=(full.strip()==reuse.strip())
print("\n== ACCURACY (span_reuse vs full text) ==")
print(f"prompts={len(sample)} exact_match={exact} ({100*exact/len(sample):.0f}%)  greedy-prefix-agreement={100*agree/total:.1f}%")
