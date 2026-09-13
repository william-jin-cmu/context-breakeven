#!/usr/bin/env python3
"""Phase 3: generality. (a) second model family: Gemini 3.5 Flash on 10 TB2.1 tasks, append vs pure state.
(b) second benchmark: SWE-bench Verified 22-task subset on DeepSeek V4 Flash, append vs pure state.
Per-trial tokens from result.json agent_result; pass from verifier_result.rewards.reward.
Cost priced at each provider's list (Gemini 3.5 Flash 1.50/0.15/9.00; DeepSeek V4 Flash run-time 0.14/0.014/0.28)."""
import json, glob, math, sys
PRICES={'gemini':(1.50e-6,0.15e-6,9.00e-6),'deepseek':(0.14e-6,0.014e-6,0.28e-6)}
def load(job):
    rows=[]
    for f in glob.glob(job+'/*/result.json'):
        r=json.load(open(f)); ar=r.get('agent_result') or {}
        rew=((r.get('verifier_result') or {}).get('rewards') or {}).get('reward')
        i=ar.get('n_input_tokens'); c=ar.get('n_cache_tokens'); o=ar.get('n_output_tokens')
        if i is None: continue
        exc=(r.get('exception_info') or {}).get('exception_type')
        rows.append(dict(task=r['task_name'].split('/')[-1],miss=i-(c or 0),cache=c or 0,out=o or 0,
                         passed=(1 if (rew or 0)>=1 else 0),exc=exc))
    return rows
def ci(xs):
    n=len(xs)
    if n==0: return (0,0)
    m=sum(xs)/n; sd=(sum((x-m)**2 for x in xs)/(n-1))**0.5 if n>1 else 0
    return m,(1.96*sd/math.sqrt(n) if n>1 else 0)
def report(title,arms,price):
    pm,pc,po=PRICES[price]
    print(f"\n=== {title} ===")
    print(f"{'arm':16s} {'n':>3s} {'pass':>10s} {'hit%':>12s} {'$/task':>14s} {'miss/task':>10s} {'cache/task':>11s} {'out/task':>9s}")
    res={}
    for name,job in arms:
        rows=load(job)
        if not rows: print(f"{name:16s}   0  (no results yet)"); continue
        hits=[100*r['cache']/(r['miss']+r['cache']) for r in rows if r['miss']+r['cache']>0]
        costs=[(r['miss']*pm+r['cache']*pc+r['out']*po) for r in rows]
        pm_,pc_=ci([r['passed'] for r in rows]); hm,hc=ci(hits); cm,cc=ci(costs)
        res[name]=dict(cost=cm,hit=hm,pass_=pm_)
        print(f"{name:16s} {len(rows):3d} {100*pm_:5.1f}±{100*pc_:4.1f} {hm:6.1f}±{hc:4.1f}% {cm:7.3f}±{cc:5.3f} {sum(r['miss'] for r in rows)/len(rows):10,.0f} {sum(r['cache'] for r in rows)/len(rows):11,.0f} {sum(r['out'] for r in rows)/len(rows):9,.0f}")
        ex=[r for r in rows if r['exc']]; 
        if ex: print(f"   ({len(ex)} trials with exception: {set(r['exc'] for r in ex)})")
    if len(res)==2:
        a,s=list(res.values()); print(f"state/append cost ratio = {s['cost']/a['cost']:.2f}x   (law predicts >1 for r=0.10)")
report("(a) Gemini 3.5 Flash, TB2.1 10-task subset, k=1",
       [('append-only','jobs/gem-tbmin-gemini-k1'),('pure state','jobs/gem-tbstate-nosearch-gemini-k1')],'gemini')
report("(b) SWE-bench Verified 22-task subset, DeepSeek V4 Flash, k=1",
       [('append-only','jobs/swe-tbmin-k1'),('pure state','jobs/swe-tbstate-nosearch-k1')],'deepseek')

# ---- Deeper view: bill-weighted hit, paired per-task cost, top-task share, realized r_eff vs r* ----
def deep(title,arms,price,rstar):
    pm,pc,po=PRICES[price]
    A={r['task']:r for r in load(arms[0][1])}; S={r['task']:r for r in load(arms[1][1])}
    both=sorted(set(A)&set(S))
    if not both: return
    print(f"\n--- {title}: paired on {len(both)} shared tasks ---")
    def tw(D): 
        m=sum(D[t]['miss'] for t in both); c=sum(D[t]['cache'] for t in both); return 100*c/(m+c) if m+c else 0
    def cost(r): return r['miss']*pm+r['cache']*pc+r['out']*po
    ca=sum(cost(A[t]) for t in both); cs=sum(cost(S[t]) for t in both)
    print(f"token-weighted hit: append={tw(A):.1f}%  state={tw(S):.1f}%")
    print(f"total cost on shared tasks: append=${ca:.2f} state=${cs:.2f}  ratio={cs/ca:.2f}x")
    top=max(both,key=lambda t:cost(A[t])); print(f"largest task {top}: append ${cost(A[top]):.2f} ({100*cost(A[top])/ca:.0f}% of append total), state ${cost(S[top]):.2f}")
    rest=[t for t in both if t!=top]
    if rest:
        ca2=sum(cost(A[t]) for t in rest); cs2=sum(cost(S[t]) for t in rest); print(f"excluding it: append=${ca2:.2f} state=${cs2:.2f} ratio={cs2/ca2:.2f}x")
    wins=sum(1 for t in both if cost(S[t])<cost(A[t])); print(f"state cheaper on {wins}/{len(both)} tasks")
    # realized effective cache discount for append-only: r_eff = blended prompt price / miss price
    m=sum(A[t]['miss'] for t in both); c=sum(A[t]['cache'] for t in both)
    reff=(m*pm+c*pc)/((m+c)*pm); print(f"append realized r_eff={reff:.3f} (nominal r={pc/pm:.2f}, r*={rstar:.3f}) -> law predicts {'STATE' if reff>rstar else 'append'} wins")
    print(f"{'task':22s} {'app$':>7s} {'sta$':>7s} {'app hit%':>8s} {'sta hit%':>8s} {'app pass':>8s} {'sta pass':>8s}")
    for t in both:
        a,s=A[t],S[t]; h=lambda r:100*r['cache']/(r['miss']+r['cache']) if r['miss']+r['cache'] else 0
        print(f"{t:22s} {cost(a):7.3f} {cost(s):7.3f} {h(a):8.1f} {h(s):8.1f} {a['passed']:8d} {s['passed']:8d}")
deep("Gemini 3.5 Flash",[('append','jobs/gem-tbmin-gemini-k1'),('state','jobs/gem-tbstate-nosearch-gemini-k1')],'gemini',rstar=(4151+360*6)/31442)
deep("SWE-bench / DeepSeek",[('append','jobs/swe-tbmin-k1'),('state','jobs/swe-tbstate-nosearch-k1')],'deepseek',rstar=0.155)
