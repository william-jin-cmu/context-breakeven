#!/usr/bin/env python3
"""Phase 2 insight: per-step cost as a function of ACCUMULATED history length.
append-only pays p_c for a cache-read prefix that grows every step; structured
state pays a ~flat block. Even at a cheap cache (r=0.10) there should be a
history length H* where append-only's per-step cost crosses the flat state cost.
Find H*, and count how many real steps already exceed it."""
import json, glob, numpy as np
PM,PC,PO=0.14e-6,0.014e-6,0.28e-6
def steps(job):
    out=[]
    for f in glob.glob(job+'/*/agent/sessions/*/*/session.jsonl'):
        si=0
        for l in open(f):
            try: e=json.loads(l)
            except: continue
            d=e.get('data') or {}
            if e['type']=='step/start': si=d.get('step',si)
            if e['type']=='assistant/message':
                u=d.get('usage') or {}
                miss=int(u.get('inputTokens') or 0); cr=int(u.get('cacheReadTokens') or 0); o=int(u.get('outputTokens') or 0)
                cost=(miss*PM+cr*PC+o*PO)*1e3
                out.append((si,miss,cr,o,cost))
    return out
def load(jobs):
    a=[]
    for j in jobs: a+=steps(j)
    return a
APP=load(['jobs/full-tbmin-r1','jobs/full-tbmin-fix1'])
STA=load(['jobs/full-tbstate-nosearch-r1','jobs/full-tbstate-nosearch-fix1'])
# history length proxy = miss+cacheRead = full prompt length
appH=np.array([m+c for _,m,c,_,_ in APP]); appCost=np.array([x[4] for x in APP])
staCost=np.array([x[4] for x in STA]); staH=np.array([m+c for _,m,c,_,_ in STA])
# state per-step cost is ~flat: use its mean (its block is bounded)
C_state=np.median(staCost)
# append per-step cost model: miss and out ~ const, cache-read grows with prompt length.
# fit append cost vs prompt length H linearly: cost ≈ a + b*H  (b≈p_c, a≈u*p_m+o*p_o)
b1,a1=np.polyfit(appH,appCost,1)
# crossover H*: a1 + b1*H* = C_state
Hstar=(C_state-a1)/b1
frac_app_over=100*np.mean(appH>Hstar)
print(f"append-only steps n={len(APP)}   structured-state median cost/step={C_state:.3f} m$")
print(f"append cost/step fit: cost ≈ {a1:.3f} + {b1*1e3:.4f}e-3 * promptlen   (slope≈p_c={PC*1e3:.4f}e-3)")
print(f"prompt-length break-even H* = {Hstar:,.0f} tokens")
print(f" -> append per-step cost exceeds compressed-state cost once history passes ~{Hstar/1000:.0f}k tokens")
print(f" -> {frac_app_over:.1f}% of real append-only steps already sit past H*")
print(f"append prompt-len: median={np.median(appH):,.0f} p90={np.percentile(appH,90):,.0f} max={appH.max():,.0f}")
# cumulative-cost crossover per task: append grows ~quadratically (sum of growing prefix), state ~linearly
# simulate avg task: tokens added/step from data
add=np.median([m for _,m,c,_,_ in APP if m>0])  # new (miss) tokens/step ~ append increment
print(f"\nmedian new(miss) tokens/step append={add:.0f}")
