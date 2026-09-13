#!/usr/bin/env python3
"""Replay per-step prompts through vLLM in order; measure prefill tokens and
prefix-cache hits per step via the token-level /metrics counters
(vllm:prefix_cache_queries_total / _hits_total). Compares append vs span.
Usage: measure.py <endpoint> <append|span> <prompts.jsonl>"""
import json, sys, urllib.request, collections, re
EP=sys.argv[1].rstrip("/"); LAYOUT=sys.argv[2]
PROMPTS=sys.argv[3] if len(sys.argv)>3 else "prompts.jsonl"
MODEL="Qwen/Qwen3-8B"
def metrics():
    t=urllib.request.urlopen(f"{EP}/metrics",timeout=30).read().decode()
    def g(n):
        m=re.search(rf"vllm:{n}_total\{{[^}}]*}} ([0-9.e+]+)",t); return float(m.group(1)) if m else 0.0
    return g("prefix_cache_queries"), g("prefix_cache_hits")
def complete(prompt):
    body=json.dumps({"model":MODEL,"prompt":prompt,"max_tokens":1,"temperature":0}).encode()
    req=urllib.request.Request(f"{EP}/v1/completions",data=body,headers={"Content-Type":"application/json"})
    return json.load(urllib.request.urlopen(req,timeout=180))["usage"]["prompt_tokens"]
rows=[json.loads(l) for l in open(PROMPTS)]
by=collections.OrderedDict()
for r in rows: by.setdefault(r["task"],[]).append(r)
tot_pt=tot_cached=0
print(f"layout={LAYOUT}")
print(f"{'task':24s} {'steps':>5s} {'prompt':>9s} {'cached':>9s} {'hit%':>5s}")
for task,seq in by.items():
    seq.sort(key=lambda r: r["step"] or 0)
    q0,h0=metrics(); pt=0
    for r in seq: pt+=complete(r[LAYOUT])
    q1,h1=metrics(); cached=int(h1-h0)
    tot_pt+=pt; tot_cached+=cached
    hit=100*cached/pt if pt else 0
    print(f"{task:24s} {len(seq):>5} {pt:>9} {cached:>9} {hit:>4.0f}%")
hit=100*tot_cached/tot_pt if tot_pt else 0
print(f"{'TOTAL':24s} {'':>5} {tot_pt:>9} {tot_cached:>9} {hit:>4.0f}%")
