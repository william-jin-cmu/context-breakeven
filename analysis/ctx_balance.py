import json, glob, numpy as np
PM,PC,PO=0.14e-6,0.014e-6,0.28e-6
def rows(jobs):
    out=[]
    for j in jobs:
      for f in glob.glob(j+'/*/agent/sessions/*/*/session.jsonl'):
        si=0
        for l in open(f):
            try: e=json.loads(l)
            except: continue
            d=e.get('data') or {}
            if e['type']=='step/start': si=d.get('step',si)
            if e['type']=='assistant/message':
                u=d.get('usage') or {}
                m=int(u.get('inputTokens') or 0); c=int(u.get('cacheReadTokens') or 0); o=int(u.get('outputTokens') or 0)
                out.append((si,m+c,(m*PM+c*PC+o*PO)*1e3))  # step, promptlen, cost
    return out
A=rows(['jobs/full-tbmin-r1','jobs/full-tbmin-fix1'])   # append-only
S=rows(['jobs/full-tbstate-nosearch-r1','jobs/full-tbstate-nosearch-fix1'])
import collections
def bystep(R):
    d=collections.defaultdict(list)
    for s,h,c in R: d[s].append((h,c))
    return d
A_=bystep(A); S_=bystep(S)
steps=[s for s in sorted(A_) if s in S_ and len(A_[s])>=10 and len(S_[s])>=10 and s<=60]
ac=np.array([np.mean([c for _,c in A_[s]]) for s in steps]); sc=np.array([np.mean([c for _,c in S_[s]]) for s in steps])
ah=np.array([np.mean([h for h,_ in A_[s]]) for s in steps]); st=np.array(steps)
# cost crossover in steps
ba=np.polyfit(st,ac,1); bs=np.polyfit(st,sc,1); tstar=(bs[1]-ba[1])/(ba[0]-bs[0])
# append prompt length vs step (linear), then length at tstar
bh=np.polyfit(st,ah,1); Hstar=bh[0]*tstar+bh[1]
print(f"append prompt length grows ~{bh[0]:.0f} tokens/step (intercept {bh[1]:.0f})")
print(f"per-step cost crossover t* = {tstar:.1f} steps")
print(f">>> V4 Flash ctx-length balance point: append-only context ~= {Hstar:,.0f} tokens at t*")
print(f"    (~{Hstar/1000:.0f}k tokens of accumulated history)")
# cross-check: empirical append prompt length around step 68
near=[h for s,h,_ in A if 64<=s<=72]
if near: print(f"    empirical median prompt len at steps 64-72: {np.median(near):,.0f} tokens (n={len(near)})")
# what fraction of append steps exceed Hstar
allh=[h for _,h,_ in A]
print(f"    {100*np.mean(np.array(allh)>Hstar):.1f}% of append steps already exceed this length")
print(f"    append prompt-len: median={np.median(allh):,.0f} p90={np.percentile(allh,90):,.0f} max={max(allh):,.0f}")
