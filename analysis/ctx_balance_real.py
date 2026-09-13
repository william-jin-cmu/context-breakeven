import json, glob, collections, numpy as np
# REAL Sept-2026 prices (miss, cache-hit, output) $/M, and ctx window (k tokens)
# sources: benchlm.ai, morphllm, cloudzero (Sept 2026 snapshots)
MODELS=[
 # name, miss, hit, out, window_k   (latest workhorse per provider)
 ('DeepSeek V4-Flash (post-cut)', 0.14, 0.0028, 0.28, 128),
 ('DeepSeek V4-Pro 0813',          0.435,0.003625,0.87,128),
 ('OpenAI GPT-5.6 sol (post-cut)', 4.00, 0.40,  20.00,272),
 ('Gemini 3.8 Flash',              0.75, 0.075,  3.75,1000),
 ('Claude Sonnet 5',               3.00, 0.30,  15.00,200),
]
def traj(jobs):
    d=collections.defaultdict(list)
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
am=np.array([mean(A,s,0) for s in steps]);ac=np.array([mean(A,s,1) for s in steps]);ao=np.array([mean(A,s,2) for s in steps])
sm=np.array([mean(S,s,0) for s in steps]);sc=np.array([mean(S,s,1) for s in steps]);so=np.array([mean(S,s,2) for s in steps])
st=np.array(steps,float); bh=np.polyfit(st,am+ac,1)
# per-step MEAN token counts for the simple verdict table (across all steps)
def allmean(D,i): 
    v=[r[i] for s in D for r in D[s]]; return np.mean(v)
ub,hb,ob=allmean(A,0),allmean(A,1),allmean(A,2)
us,hs,os_=allmean(S,0),allmean(S,1),allmean(S,2)
print(f"{'model':30s} {'r':>6s} {'r*':>6s} {'append':>9s} {'state':>9s} {'winner':>7s} {'H* ctx':>10s} {'H*/win':>7s}")
rows=[]
for name,pm,pc,po,wk in MODELS:
    PM,PC,PO=pm*1e-6,pc*1e-6,po*1e-6; r=pc/pm; rho=po/pm
    rstar=(4151+360*rho)/31442
    ca=(ub*PM+hb*PC+ob*PO)*1e3; cs=(us*PM+hs*PC+os_*PO)*1e3
    w='append' if ca<cs else 'STATE'
    acost=am*PM+ac*PC+ao*PO; scost=sm*PM+sc*PC+so*PO
    ba=np.polyfit(st,acost,1); bs=np.polyfit(st,scost,1)
    if ba[0]>bs[0]:
        tstar=(bs[1]-ba[1])/(ba[0]-bs[0]); Hstar=bh[0]*tstar+bh[1]; hs_s=f"{Hstar:,.0f}"; ratio=f"{Hstar/(wk*1000):.2f}"
    else:
        Hstar=float('inf'); hs_s="never"; ratio="--"
    print(f"{name:30s} {r:6.3f} {rstar:6.3f} {ca:8.3f}m {cs:8.3f}m {w:>7s} {hs_s:>10s} {ratio:>7s}")
