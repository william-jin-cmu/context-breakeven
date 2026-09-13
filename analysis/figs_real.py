import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt, numpy as np
from matplotlib.patches import Patch
# per-step mean token counts (full run)
ub,hb,ob=588,35990,687; us,hs,os_=4739,4548,1047
M=[('DeepSeek\nV4-Flash\nr=0.02',0.14,0.0028,0.28),('DeepSeek\nV4-Pro\nr=0.008',0.435,0.003625,0.87),
   ('OpenAI\nGPT-5.6\nr=0.10',4.0,0.40,20.0),('Gemini\n3.8 Flash\nr=0.10',0.75,0.075,3.75),
   ('Claude\nSonnet 5\nr=0.10',3.0,0.30,15.0)]
def c(u,h,o,pm,pc,po): return (u*pm+h*pc+o*po)/1e6*1e3
names=[m[0] for m in M]
ratio=[c(us,hs,os_,*m[1:])/c(ub,hb,ob,*m[1:]) for m in M]
x=np.arange(len(M))
fig,ax=plt.subplots(figsize=(6,3.2))
ax.bar(x-0.2,[1]*len(M),0.4,label='append-only',color='#2c7fb8')
ax.bar(x+0.2,ratio,0.4,label='structured state',color='#d95f0e')
for i,v in enumerate(ratio): ax.annotate(f'{v:.2f}x',(i+0.2,v+0.03),ha='center',fontsize=8)
ax.axhline(1.0,ls=':',color='gray')
ax.set_xticks(x); ax.set_xticklabels(names,fontsize=7.5); ax.set_ylabel('cost per step (÷ append-only)')
ax.set_title('Sept-2026 real prices: append-only wins on every provider (all r<r*)')
ax.legend(fontsize=8,loc='upper right'); ax.set_ylim(0,4.4)
fig.savefig('paper/figs/fig5_providers.pdf',bbox_inches='tight')
# fig6: ctx balance. DeepSeek = no crossover (append always cheaper); r=0.10 providers H*=131k
import json,glob,collections
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
A=traj(['jobs/full-tbmin-r1','jobs/full-tbmin-fix1']); S=traj(['jobs/full-tbstate-nosearch-r1','jobs/full-tbstate-nosearch-fix1'])
steps=[s for s in sorted(A) if s in S and len(A[s])>=10 and len(S[s])>=10 and 1<=s<=60]
m=lambda D,s,i:np.mean([r[i] for r in D[s]])
am=np.array([m(A,s,0) for s in steps]);ac=np.array([m(A,s,1) for s in steps]);ao=np.array([m(A,s,2) for s in steps])
sm=np.array([m(S,s,0) for s in steps]);sc=np.array([m(S,s,1) for s in steps]);so=np.array([m(S,s,2) for s in steps])
st=np.array(steps,float); bh=np.polyfit(st,am+ac,1)
def Hstar(pm,pc,po):
    PM,PC,PO=pm*1e-6,pc*1e-6,po*1e-6
    ba=np.polyfit(st,am*PM+ac*PC+ao*PO,1); bs=np.polyfit(st,sm*PM+sc*PC+so*PO,1)
    if ba[0]<=bs[0]: return None
    t=(bs[1]-ba[1])/(ba[0]-bs[0]); return bh[0]*t+bh[1]
DAT=[('DeepSeek V4-Flash\n(r=0.02, post-cut)',Hstar(0.14,0.0028,0.28),128000),
     ('OpenAI GPT-5.6\n(r=0.10)',Hstar(4,0.40,20),272000),
     ('Gemini 3.8 Flash\n(r=0.10)',Hstar(0.75,0.075,3.75),1000000),
     ('Claude Sonnet 5\n(r=0.10)',Hstar(3,0.30,15),200000)]
fig,ax=plt.subplots(figsize=(6.4,3.0)); CAP=300000; y=np.arange(len(DAT))[::-1]
for yi,(name,H,w) in zip(y,DAT):
    ax.barh(yi,min(w,CAP),color='#e6e6e6',height=0.6,zorder=1)
    if H is None:
        ax.barh(yi,min(w,CAP),color='#2c7fb8',height=0.6,zorder=2)
        ax.annotate('no crossover — append wins at every length',(6000,yi),va='center',fontsize=7.5,color='white',zorder=3)
    else:
        ax.barh(yi,min(H,CAP),color='#d95f0e',height=0.6,zorder=2)
        ax.annotate(f'H*={H/1000:.0f}k ({100*H/w:.0f}% of window)',(min(H,CAP)+5000,yi),va='center',fontsize=7.5)
    if w>CAP: ax.annotate(f'window {w//1000}k →',(CAP-5000,yi+0.34),ha='right',fontsize=6.5,color='gray')
ax.set_yticks(y); ax.set_yticklabels([d[0] for d in DAT],fontsize=8)
ax.set_xlabel('accumulated history (tokens)'); ax.set_xlim(0,CAP)
ax.set_title("Context-length balance point at real Sept-2026 prices")
ax.legend(handles=[Patch(color='#2c7fb8',label='append-only wins'),Patch(color='#d95f0e',label='state cheaper beyond H*'),Patch(color='#e6e6e6',label='context window')],fontsize=7,loc='lower right')
fig.savefig('paper/figs/fig6_ctxbalance.pdf',bbox_inches='tight')
print('wrote fig5,fig6; ratios',[round(r,2) for r in ratio])
