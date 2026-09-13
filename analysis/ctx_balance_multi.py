import json, glob, collections, numpy as np
def traj(jobs):
    d=collections.defaultdict(list)  # step -> list of (miss,cr,out)
    for j in jobs:
      for f in glob.glob(j+'/*/agent/sessions/*/*/session.jsonl'):
        si=0
        for l in open(f):
            try: e=json.loads(l)
            except: continue
            dd=e.get('data') or {}
            if e['type']=='step/start': si=dd.get('step',si)
            if e['type']=='assistant/message':
                u=dd.get('usage') or {}
                d[si].append((int(u.get('inputTokens') or 0),int(u.get('cacheReadTokens') or 0),int(u.get('outputTokens') or 0)))
    return d
A=traj(['jobs/full-tbmin-r1','jobs/full-tbmin-fix1'])
S=traj(['jobs/full-tbstate-nosearch-r1','jobs/full-tbstate-nosearch-fix1'])
steps=[s for s in sorted(A) if s in S and len(A[s])>=10 and len(S[s])>=10 and 1<=s<=60]
def mean(D,s,i): return np.mean([r[i] for r in D[s]])
am=np.array([mean(A,s,0) for s in steps]); ac=np.array([mean(A,s,1) for s in steps]); ao=np.array([mean(A,s,2) for s in steps])
sm=np.array([mean(S,s,0) for s in steps]); sc=np.array([mean(S,s,1) for s in steps]); so=np.array([mean(S,s,2) for s in steps])
ah=am+ac  # append prompt length per step
st=np.array(steps,float)
bh=np.polyfit(st,ah,1)  # append prompt length vs step
P={'DeepSeek V4 Flash':(0.14,0.014,0.28),'Anthropic':(0.80,0.08,4.00),
   'Gemini Flash':(0.075,0.01875,0.30),'OpenAI mini':(0.15,0.075,0.60)}
W={'DeepSeek V4 Flash':128,'Anthropic':200,'Gemini Flash':1000,'OpenAI mini':128}  # ctx window (k tokens, approx)
print(f"{'model':22s} {'r':>5s} {'t* (steps)':>11s} {'H* ctx (tok)':>14s} {'window':>8s} {'H*/window':>9s}")
for name,(pm,pc,po) in P.items():
    pm,pc,po=pm*1e-6,pc*1e-6,po*1e-6
    acost=am*pm+ac*pc+ao*po; scost=sm*pm+sc*pc+so*po
    diff=acost-scost  # append minus state; crossover where diff goes 0+ (append gets more expensive)
    ba=np.polyfit(st,acost,1); bs=np.polyfit(st,scost,1)
    if ba[0]<=bs[0]:
        verdict="append slope<=state: no length crossover (append stays cheaper)"
        print(f"{name:22s} {pc/pm:5.2f} {'--':>11s} {verdict}")
        continue
    tstar=(bs[1]-ba[1])/(ba[0]-bs[0])
    Hstar=bh[0]*tstar+bh[1]
    w=W[name]*1000
    if tstar<=1: note="(state cheaper from step 1 → compress always)"
    else: note=""
    print(f"{name:22s} {pc/pm:5.2f} {tstar:11.1f} {Hstar:14,.0f} {W[name]:6d}k {min(Hstar/w,9.99):8.2f}x {note}")
print(f"\nappend prompt grows {bh[0]:.0f} tok/step (intercept {bh[1]:.0f}); trajectory fixed from DeepSeek run, price varied.")
