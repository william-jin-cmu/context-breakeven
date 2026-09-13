import json, glob, numpy as np
def lens(jobs):
    L=[]
    for j in jobs:
      for f in glob.glob(j+'/*/agent/sessions/*/*/session.jsonl'):
        mx=0
        for l in open(f):
            try: e=json.loads(l)
            except: continue
            if e['type']=='step/start': mx=max(mx,(e.get('data') or {}).get('step',0))
        if mx: L.append(mx)
    return np.array(L)
A=lens(['jobs/full-tbmin-r1','jobs/full-tbmin-fix1'])
print(f"append task lengths (steps): n={len(A)} median={np.median(A):.0f} p75={np.percentile(A,75):.0f} p90={np.percentile(A,90):.0f} max={A.max()}")
print(f"fraction of tasks running >68 steps: {100*np.mean(A>68):.1f}%")
# per-step sample sizes near crossover
import collections
def nbystep(jobs):
    d=collections.Counter()
    for j in jobs:
      for f in glob.glob(j+'/*/agent/sessions/*/*/session.jsonl'):
        si=0
        for l in open(f):
            try: e=json.loads(l)
            except: continue
            dd=e.get('data') or {}
            if e['type']=='step/start': si=dd.get('step',si)
            if e['type']=='assistant/message': d[si]+=1
    return d
import collections
na=nbystep(['jobs/full-tbmin-r1','jobs/full-tbmin-fix1'])
print("append n at steps 10/30/50/60:", na[10],na[30],na[50],na[60])
