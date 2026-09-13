import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt, numpy as np
plt.rcParams.update({'font.size':9,'figure.dpi':140,'savefig.bbox':'tight'})
PM,PC,PO=0.14e-6,0.014e-6,0.28e-6
OUT='paper/figs/'

# --- Fig 1: full-run three arms, hit% and cost/step with 95% CI (from analysis.py) ---
arms=['append-only\n(tbmin)','inline state\n(tbstate)','pure state\n(nosearch)']
hit=[97.3,49.8,48.7]; hitE=[0.5,1.8,1.3]
cost=[0.779,1.038,1.020]; costE=[0.096,0.129,0.097]
fig,(a1,a2)=plt.subplots(1,2,figsize=(7,3))
c=['#2c7fb8','#d95f0e','#d95f0e']
a1.bar(arms,hit,yerr=hitE,capsize=4,color=c); a1.set_ylabel('prefix-cache hit %'); a1.set_ylim(0,105); a1.set_title('(a) cache hit rate')
a2.bar(arms,cost,yerr=costE,capsize=4,color=c); a2.set_ylabel('cost per step (m$)'); a2.set_title('(b) cost per step'); a2.set_ylim(0,1.3)
for ax in (a1,a2): ax.tick_params(axis='x',labelsize=7.5)
fig.suptitle('Full run: 89 Terminal-Bench 2.1 tasks, DeepSeek V4 Flash',fontsize=9)
fig.savefig(OUT+'fig1_fullrun.pdf'); plt.close(fig)

# --- Fig 2: cost break-even curve vs cache-discount r ---
r=np.linspace(0,0.35,200)
# per-step token counts (across-task means, full run)
b=dict(miss=588,cache=35990,out=687); s=dict(miss=4739,cache=4548,out=1047)
def cstep(d,rr): return (d['miss']*PM + d['cache']*(rr*PM) + d['out']*PO)*1e3
cb=[cstep(b,rr) for rr in r]; cs=[cstep(s,rr) for rr in r]
rstar=((b['miss']-s['miss'])+ (PO/PM)*(b['out']-s['out']))/(s['cache']-b['cache'])
fig,ax=plt.subplots(figsize=(4.6,3.2))
ax.plot(r,cb,label='append-only',color='#2c7fb8',lw=2)
ax.plot(r,cs,label='structured state',color='#d95f0e',lw=2)
ax.axvline(rstar,ls='--',color='gray'); ax.axvline(0.10,ls=':',color='green')
ax.annotate(f'break-even r*={rstar:.2f}',(rstar,0.3),rotation=90,va='bottom',fontsize=7.5,color='gray')
ax.annotate('DeepSeek r=0.10',(0.10,1.0),rotation=90,va='bottom',fontsize=7.5,color='green')
ax.set_xlabel('cache-hit price / miss price  (r = $p_c/p_m$)'); ax.set_ylabel('cost per step (m$)')
ax.set_title('Cost break-even: state wins only when r > r*'); ax.legend(); ax.set_xlim(0,0.35)
fig.savefig(OUT+'fig2_breakeven.pdf'); plt.close(fig)

# --- Fig 3: Tier 1 — cost hit% and block-attn accuracy agreement ---
fig,(a1,a2)=plt.subplots(1,2,figsize=(7,3))
lbl=['append','span','span-reuse']; x=np.arange(3); w=0.35
qw=[77,74,74]; tu=[94,73,73]
a1.bar(x-w/2,qw,w,label='Qwen3-8B',color='#2c7fb8'); a1.bar(x+w/2,tu,w,label='Tulu3-Block-FT',color='#7fcdbb')
a1.set_xticks(x); a1.set_xticklabels(lbl,fontsize=8); a1.set_ylabel('cache hit %'); a1.set_ylim(0,105); a1.set_title('(a) KV reuse'); a1.legend(fontsize=7)
agm=['Qwen3-8B','Tulu3-Block-FT']; ag=[7.7,35.0]
a2.bar(agm,ag,color=['#2c7fb8','#7fcdbb']); a2.set_ylabel('greedy agreement vs full attn %'); a2.set_ylim(0,105); a2.set_title('(b) block-attention accuracy')
a2.axhline(100,ls=':',color='gray'); a2.tick_params(axis='x',labelsize=8)
fig.suptitle('Tier 1: position-independent KV (MiniPIC) on 268 real state prompts',fontsize=9)
fig.savefig(OUT+'fig3_tier1.pdf'); plt.close(fig)
print('wrote', OUT, 'r*=',round(rstar,3))
