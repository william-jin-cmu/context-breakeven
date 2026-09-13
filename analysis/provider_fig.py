import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt, numpy as np
app=dict(u=588,h=35990,o=687); sta=dict(u=4739,h=4548,o=1047)
P=[('DeepSeek\nr=0.10',0.14,0.014,0.28),('Anthropic\nr=0.10',0.80,0.08,4.00),
   ('Gemini Flash\nr=0.25',0.075,0.01875,0.30),('OpenAI mini\nr=0.50',0.15,0.075,0.60)]
def c(d,pm,pc,po): return (d['u']*pm+d['h']*pc+d['o']*po)/1e6*1e3
names=[p[0] for p in P]; ca=[c(app,*p[1:]) for p in P]; cs=[c(sta,*p[1:]) for p in P]
# normalize each provider to its append cost for comparability
csn=[s/a for s,a in zip(cs,ca)]; can=[1.0]*len(P)
x=np.arange(len(P)); w=0.36
fig,ax=plt.subplots(figsize=(5.2,3.3))
ax.bar(x-w/2,can,w,label='append-only',color='#2c7fb8')
ax.bar(x+w/2,csn,w,label='structured state',color='#d95f0e')
ax.axhline(1.0,ls=':',color='gray')
for i,v in enumerate(csn): ax.annotate(f'{v:.2f}x',(i+w/2,v+0.02),ha='center',fontsize=8)
ax.set_xticks(x); ax.set_xticklabels(names,fontsize=8); ax.set_ylabel('cost per step (÷ append-only)')
ax.set_title('Verdict flips by cache discount (r*=0.155)'); ax.legend(fontsize=8); ax.set_ylim(0,1.6)
fig.savefig('paper/figs/fig5_providers.pdf',bbox_inches='tight'); print('wrote fig5')
