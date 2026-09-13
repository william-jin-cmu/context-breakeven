#!/usr/bin/env python3
"""Phase 0 analysis on existing data: per-step cost/cache with across-task 95% CI,
model-time vs wall-clock (amd64 confound), and the cost break-even threshold r*.
Prices (DeepSeek V4 Flash, per token): miss 0.14/M, cache 0.014/M, out 0.28/M."""
import json, glob, collections, math
PM, PC, PO = 0.14e-6, 0.014e-6, 0.28e-6
def sess(job): 
    d={}
    for f in glob.glob(job+'/*/agent/sessions/*/*/session.jsonl'): d.setdefault(f.split('/')[2].split('__')[0], f)
    return d
def per_task(f):
    miss=cr=out=0; steps=0; t_model=0.0; last_step_t=None
    for l in open(f):
        try: e=json.loads(l)
        except: continue
        d=e.get('data') or {}
        if e['type']=='step/start': steps=d.get('step',steps); last_step_t=e.get('time')
        if e['type']=='assistant/message':
            u=d.get('usage') or {}
            miss+=int(u.get('inputTokens') or 0); cr+=int(u.get('cacheReadTokens') or 0); out+=int(u.get('outputTokens') or 0)
            if last_step_t and e.get('time'): t_model+=(e['time']-last_step_t)/1000.0
    return dict(steps=steps, miss=miss, cr=cr, out=out, tmodel=t_model)
def agg(jobs):
    d={}
    for j in jobs:
        for t,f in sess(j).items(): d.setdefault(t,f)  # first seen
    rows=[per_task(f) for f in d.values() if per_task(f)['steps']>0]
    return rows
def ci(xs):
    n=len(xs); m=sum(xs)/n
    sd=(sum((x-m)**2 for x in xs)/(n-1))**0.5 if n>1 else 0
    return m, 1.96*sd/math.sqrt(n)
ARMS={'tbmin (append-only raw)':['jobs/full-tbmin-r1','jobs/full-tbmin-fix1'],
      'tbstate (inline+search)':['jobs/full-tbstate-r1','jobs/full-tbstate-fix1'],
      'tbstate-nosearch (pure state)':['jobs/full-tbstate-nosearch-r1','jobs/full-tbstate-nosearch-fix1']}
print("=== per-step metrics, across-task mean ± 95% CI (full run) ===")
stats={}
for name,jobs in ARMS.items():
    rows=agg(jobs)
    hits=[100*r['cr']/(r['miss']+r['cr']) for r in rows if r['miss']+r['cr']>0]
    costs=[(r['miss']*PM+r['cr']*PC+r['out']*PO)/r['steps']*1e3 for r in rows]
    mps=[r['miss']/r['steps'] for r in rows]; hps=[r['cr']/r['steps'] for r in rows]; ops=[r['out']/r['steps'] for r in rows]
    tps=[r['tmodel']/r['steps'] for r in rows if r['tmodel']>0]
    hm,hc=ci(hits); cm,cc=ci(costs); tm,tc=ci(tps) if tps else (0,0)
    stats[name]=dict(miss=sum(mps)/len(mps),cache=sum(hps)/len(hps),out=sum(ops)/len(ops))
    print(f"{name:32s} n={len(rows):2d} hit={hm:4.1f}±{hc:4.1f}%  cost/step={cm:.3f}±{cc:.3f}m$  model-time/step={tm:4.1f}±{tc:.1f}s")
# break-even r* : state beats append iff r > r*,  r=PC/PM (cache discount)
b=stats['tbmin (append-only raw)']; s=stats['tbstate-nosearch (pure state)']
rho=PO/PM
rstar=((b['miss']-s['miss'])+rho*(b['out']-s['out']))/(s['cache']-b['cache'])
print(f"\n=== break-even ===\nrho=PO/PM={rho:.1f}  current r=PC/PM={PC/PM:.3f}")
print(f"append-only per-step miss={b['miss']:.0f} cache={b['cache']:.0f} out={b['out']:.0f}")
print(f"pure-state  per-step miss={s['miss']:.0f} cache={s['cache']:.0f} out={s['out']:.0f}")
print(f"r* (state wins iff cache price > r* x miss price) = {rstar:.3f}")
print(f"=> DeepSeek r={PC/PM:.2f} {'<' if PC/PM<rstar else '>'} r*={rstar:.2f} -> {'APPEND-ONLY wins' if PC/PM<rstar else 'state wins'}")
