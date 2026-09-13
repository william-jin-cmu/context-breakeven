import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
import json, glob, numpy as np
PM,PC,PO=0.14e-6,0.014e-6,0.28e-6
def steps(jobs):
    out=[]
    for j in jobs:
      for f in glob.glob(j+'/*/agent/sessions/*/*/session.jsonl'):
        for l in open(f):
            try: e=json.loads(l)
            except: continue
            if e['type']=='assistant/message':
                u=e.get('data',{}).get('usage') or {}
                m=int(u.get('inputTokens') or 0); c=int(u.get('cacheReadTokens') or 0); o=int(u.get('outputTokens') or 0)
                out.append((m+c,(m*PM+c*PC+o*PO)*1e3))
    return np.array(out)
APP=steps(['jobs/full-tbmin-r1','jobs/full-tbmin-fix1'])
STA=steps(['jobs/full-tbstate-nosearch-r1','jobs/full-tbstate-nosearch-fix1'])
# binned means to see trend vs prompt length
def binned(D,edges):
    H,C=D[:,0],D[:,1]; xs=[];ys=[]
    for i in range(len(edges)-1):
        m=(H>=edges[i])&(H<edges[i+1])
        if m.sum()>=15: xs.append((edges[i]+edges[i+1])/2); ys.append(C[m].mean())
    return np.array(xs),np.array(ys)
edges=np.arange(0,130001,10000)
ax_x,ax_y=binned(APP,edges); sx,sy=binned(STA,edges)
ba,aa=np.polyfit(APP[:,0],APP[:,1],1)
bs,as_=np.polyfit(STA[:,0],STA[:,1],1)
Hstar=(as_-aa)/(ba-bs)
print(f"append slope={ba*1e3:.4f}e-3  intercept={aa:.3f}")
print(f"state  slope={bs*1e3:.4f}e-3  intercept={as_:.3f}  (flat? slope vs p_c={PC*1e3:.4f}e-3)")
print(f"crossover H* (append=state) = {Hstar:,.0f} tokens")
frac=100*np.mean(APP[:,0]>Hstar)
print(f"{frac:.1f}% of append steps past H*")
fig,ax=plt.subplots(figsize=(5,3.4))
ax.scatter(APP[:,0],APP[:,1],s=3,alpha=0.08,color='#2c7fb8')
ax.scatter(STA[:,0],STA[:,1],s=3,alpha=0.08,color='#d95f0e')
xs=np.linspace(0,130000,100)
ax.plot(xs,aa+ba*xs,color='#2c7fb8',lw=2,label='append-only (fit)')
ax.plot(xs,as_+bs*xs,color='#d95f0e',lw=2,label='structured state (fit)')
ax.axvline(Hstar,ls='--',color='gray'); ax.annotate(f'H*={Hstar/1000:.0f}k',(Hstar,5.5),rotation=90,fontsize=8,color='gray',va='top')
ax.set_xlabel('prompt length = accumulated history (tokens)'); ax.set_ylabel('cost per step (m$)')
ax.set_ylim(0,6); ax.set_xlim(0,130000); ax.legend(fontsize=8)
ax.set_title('Length break-even: cheap cache is not free')
fig.savefig('paper/figs/fig4_length.pdf',bbox_inches='tight'); print('wrote fig4')
