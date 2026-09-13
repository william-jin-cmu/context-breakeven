import json, glob, math, collections
ARMS={'append-only (tbmin)':'jobs/seed-tbmin-k3',
      'pure state (nosearch)':'jobs/seed-tbstate-nosearch-k3',
      'append-state (Tier0)':'jobs/seed-tbstate-append-k3'}
def tp(td):
    rj=glob.glob(td+'/result.json')
    if not rj: return None,None
    r=json.load(open(rj[0]))
    vr=(r.get('verifier_result') or {}).get('rewards') or {}
    rew=vr.get('reward')
    p = (1 if rew>=1 else 0) if isinstance(rew,(int,float)) else None
    ar=r.get('agent_result') or {}
    cost=ar.get('cost_usd')
    return p,cost
def ci(xs):
    n=len(xs); 
    if n==0: return 0,0
    m=sum(xs)/n; sd=(sum((x-m)**2 for x in xs)/(n-1))**0.5 if n>1 else 0
    return m,(1.96*sd/math.sqrt(n) if n>1 else 0)
print(f"{'arm':26s} {'tasks':>5s} {'trials':>6s} {'mean-pass±CI':>16s} {'pass@k':>7s} {'all-k':>6s} {'$/task':>8s}")
rows={}
for name,job in ARMS.items():
    bt=collections.defaultdict(list); costs=[]
    for td in glob.glob(job+'/*__*'):
        task=td.split('/')[-1].split('__')[0]; p,c=tp(td)
        if p is not None: bt[task].append(p)
        if c is not None: costs.append(c)
    fr=[sum(v)/len(v) for v in bt.values()]
    pk=[max(v) for v in bt.values()]; ak=[min(v) for v in bt.values()]
    nt=sum(len(v) for v in bt.values()); m,c=ci(fr)
    rows[name]=(bt,fr)
    print(f"{name:26s} {len(bt):5d} {nt:6d}  {100*m:5.1f}±{100*c:4.1f}%      {100*sum(pk)/len(pk):5.1f}% {100*sum(ak)/len(ak):5.1f}% {sum(costs)/max(len(bt),1):8.3f}")
# per-task head-to-head (same 10 tasks all arms)
print("\nper-task pass fraction (k=3):")
tasks=sorted(rows['append-only (tbmin)'][0])
print(f"{'task':24s} {'append':>7s} {'state':>7s} {'Tier0':>7s}")
for t in tasks:
    a=rows['append-only (tbmin)'][0].get(t,[]); s=rows['pure state (nosearch)'][0].get(t,[]); z=rows['append-state (Tier0)'][0].get(t,[])
    f=lambda v: f"{sum(v)}/{len(v)}" if v else "-"
    print(f"{t:24s} {f(a):>7s} {f(s):>7s} {f(z):>7s}")
