import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt, numpy as np, json, glob
pm,pc,po=1.50e-6,0.15e-6,9.00e-6
def load(job):
    D={}
    for f in glob.glob(job+'/*/result.json'):
        r=json.load(open(f)); ar=r.get('agent_result') or {}
        if ar.get('n_input_tokens') is None: continue
        i=ar['n_input_tokens']; c=ar.get('n_cache_tokens') or 0; o=ar.get('n_output_tokens') or 0
        D[r['task_name'].split('/')[-1]]=dict(miss=i-c,cache=c,out=o,cost=(i-c)*pm+c*pc+o*po)
    return D
A=load('jobs/gem-tbmin-gemini-k1'); S=load('jobs/gem-tbstate-nosearch-gemini-k1')
tasks=sorted(set(A)&set(S), key=lambda t:A[t]['cost'])
fig,(a1,a2)=plt.subplots(1,2,figsize=(8.2,3.3),gridspec_kw={'width_ratios':[1.6,1]})
x=np.arange(len(tasks)); w=0.38
a1.bar(x-w/2,[A[t]['cost'] for t in tasks],w,label='append-only',color='#2c7fb8')
a1.bar(x+w/2,[S[t]['cost'] for t in tasks],w,label='structured state',color='#d95f0e')
a1.set_yscale('log'); a1.set_xticks(x); a1.set_xticklabels([t[:14] for t in tasks],rotation=45,ha='right',fontsize=7)
a1.set_ylabel('cost per task ($, log)'); a1.set_title('(a) Gemini 3.5 Flash: paired per-task cost'); a1.legend(fontsize=7)
# (b) realized hit fraction vs prompt length for append-only steps
rows=[]
for s in glob.glob('jobs/gem-tbmin-gemini-k1/*/agent/sessions/*/*/session.jsonl'):
    for l in open(s):
        try: e=json.loads(l)
        except: continue
        if e['type']=='assistant/message':
            u=(e.get('data') or {}).get('usage') or {}; i=int(u.get('inputTokens') or 0); c=int(u.get('cacheReadTokens') or 0)
            if i+c>0: rows.append((i+c,c/(i+c)))
R=np.array(rows); edges=[0,5e3,10e3,20e3,50e3,100e3,250e3]; xs=[];ys=[];zs=[]
for lo,hi in zip(edges[:-1],edges[1:]):
    m=(R[:,0]>=lo)&(R[:,0]<hi)
    if m.sum()>=5: xs.append(f'{int(lo/1e3)}–{int(hi/1e3)}k'); ys.append(100*R[m,1].mean()); zs.append(100*np.mean(R[m,1]<0.01))
a2.bar(range(len(xs)),ys,color='#7fcdbb',label='mean hit %'); a2.plot(range(len(xs)),zs,'o-',color='#d95f0e',label='% steps with zero hit')
a2.set_xticks(range(len(xs))); a2.set_xticklabels(xs,fontsize=7,rotation=30); a2.set_ylim(0,105); a2.set_ylabel('%'); a2.set_xlabel('prompt length')
a2.set_title('(b) implicit cache is unreliable on short prompts'); a2.legend(fontsize=7)
fig.savefig('paper/figs/fig7_gemini.pdf',bbox_inches='tight')
m=sum(A[t]['miss'] for t in tasks); c=sum(A[t]['cache'] for t in tasks)
print(f"wrote fig7; paired tasks={len(tasks)}; append realized hit={100*c/(m+c):.1f}% r_eff={(m*pm+c*pc)/((m+c)*pm):.3f}")
