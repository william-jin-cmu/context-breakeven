import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
import json, glob, numpy as np
PM,PC,PO=0.14e-6,0.014e-6,0.28e-6
def by_step(jobs):
    d={}  # step_index -> list of cost
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
                m=int(u.get('inputTokens') or 0); c=int(u.get('cacheReadTokens') or 0); o=int(u.get('outputTokens') or 0)
                d.setdefault(si,[]).append((m*PM+c*PC+o*PO)*1e3)
    return d
A=by_step(['jobs/full-tbmin-r1','jobs/full-tbmin-fix1'])
S=by_step(['jobs/full-tbstate-nosearch-r1','jobs/full-tbstate-nosearch-fix1'])
steps=sorted(s for s in A if s in S and len(A[s])>=10 and len(S[s])>=10 and s<=60)
amean=np.array([np.mean(A[s]) for s in steps]); smean=np.array([np.mean(S[s]) for s in steps])
steps=np.array(steps)
# cumulative cost over a task of length T (mean per-step curves)
cumA=np.cumsum(amean); cumS=np.cumsum(smean)
# per-step crossover
ba=np.polyfit(steps,amean,1); bs=np.polyfit(steps,smean,1)
tcross=(bs[1]-ba[1])/(ba[0]-bs[0])
print(f"append per-step cost vs step: slope={ba[0]:.4f} m$/step  intercept={ba[1]:.3f}")
print(f"state  per-step cost vs step: slope={bs[0]:.4f} m$/step  intercept={bs[1]:.3f}")
print(f"per-step crossover t* (append becomes > state) = {tcross:.0f} steps" if ba[0]>bs[0] else f"append grows slower; no per-step crossover (append stays cheaper, t*={tcross:.0f})")
# cumulative crossover
cc=np.where(cumA>cumS)[0]
print(f"cumulative task cost: append>state first at step {steps[cc[0]]}" if len(cc) else "cumulative: append-only cheaper for every task length in range")
print(f"at step 60: append cum={cumA[-1]:.1f} m$  state cum={cumS[-1]:.1f} m$  (ratio {cumA[-1]/cumS[-1]:.2f})")
fig,(a1,a2)=plt.subplots(1,2,figsize=(8,3.2))
a1.plot(steps,amean,label='append-only',color='#2c7fb8'); a1.plot(steps,smean,label='structured state',color='#d95f0e')
a1.set_xlabel('step index (task progress)'); a1.set_ylabel('cost per step (m$)'); a1.set_title('(a) per-step cost'); a1.legend(fontsize=8)
a2.plot(steps,cumA,label='append-only',color='#2c7fb8'); a2.plot(steps,cumS,label='structured state',color='#d95f0e')
a2.set_xlabel('task length (steps)'); a2.set_ylabel('cumulative cost (m$)'); a2.set_title('(b) cumulative task cost'); a2.legend(fontsize=8)
fig.suptitle('Does append-only stay cheaper as tasks get longer?',fontsize=9)
fig.savefig('paper/figs/fig4_length.pdf',bbox_inches='tight'); print('wrote fig4')
