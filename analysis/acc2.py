#!/usr/bin/env python3
"""Valid accuracy gate: append a generation cue so the model actually generates,
then compare span_reuse (block attn, token-ids) vs full (plain text) greedy output.
High agreement => MiniPIC preserves quality on this model."""
import json,os,sys,urllib.request
from transformers import AutoTokenizer
import minipic
EP="http://127.0.0.1:8000"; MODEL=os.environ.get("MODEL","ldsjmdy/Tulu3-Block-FT")
tok=AutoTokenizer.from_pretrained(MODEL)
CUE="\n\nWrite the single next shell command to run.\nCommand:"
def post(prompt,mt):
    body=json.dumps({"model":MODEL,"prompt":prompt,"max_tokens":mt,"temperature":0}).encode()
    req=urllib.request.Request(f"{EP}/v1/completions",data=body,headers={"Content-Type":"application/json"})
    return json.load(urllib.request.urlopen(req,timeout=180))["choices"][0]["text"]
rows=[json.loads(l) for l in open("prompts.jsonl")]
rows=[r for r in rows if len(tok.encode(r["span"]))<=7200][:int(sys.argv[1]) if len(sys.argv)>1 else 40]
exact=agree=total=nonempty=0
for r in rows:
    text=r["span"]+CUE
    full=post(text,48)
    ids=minipic.build(tok, r["span"]) + tok.convert_tokens_to_ids(tok.tokenize(CUE))
    reuse=post(ids,48)
    if full.strip(): nonempty+=1
    ft=tok.encode(full,add_special_tokens=False); rt=tok.encode(reuse,add_special_tokens=False)
    m=0
    for a,b in zip(ft,rt):
        if a==b:m+=1
        else:break
    agree+=m; total+=max(len(ft),1); exact+=(full.strip()==reuse.strip() and full.strip()!="")
print(f"model={MODEL}")
print(f"prompts={len(rows)} nonempty_full={nonempty} exact_match={exact} greedy-prefix-agreement={100*agree/total:.1f}%")
