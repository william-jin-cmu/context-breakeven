import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt, numpy as np
M=[('DeepSeek V4 Flash',0.10,86858,128000),('Anthropic',0.10,130998,200000),
   ('Gemini Flash',0.25,24354,1000000),('OpenAI mini',0.50,11807,128000)]
names=[m[0]+f'\nr={m[1]:.2f}' for m in M]; H=[m[2] for m in M]; W=[m[3] for m in M]
y=np.arange(len(M))[::-1]
fig,ax=plt.subplots(figsize=(6.2,3.2))
# window as faint full bar (cap display at 260k so 1M Gemini doesn't squash the rest)
CAP=260000
for yi,(h,w) in zip(y,zip(H,W)):
    ax.barh(yi,min(w,CAP),color='#e6e6e6',height=0.6,zorder=1)
    ax.barh(yi,min(h,CAP),color=['#2c7fb8' if H[i]/W[i]>0.3 else '#d95f0e' for i in range(len(M))][list(y).index(yi)],height=0.6,zorder=2)
    lab=f'{h/1000:.0f}k ({100*h/w:.0f}% of window)'
    ax.annotate(lab,(min(h,CAP)+4000,yi),va='center',fontsize=8)
    if w>CAP: ax.annotate(f'window {w//1000}k →',(CAP-4000,yi+0.33),va='center',ha='right',fontsize=6.5,color='gray')
ax.set_yticks(y); ax.set_yticklabels(names,fontsize=8)
ax.set_xlabel('accumulated history (tokens)'); ax.set_xlim(0,CAP)
ax.set_title('Context-length balance point H* (append→compress), by model')
from matplotlib.patches import Patch
ax.legend(handles=[Patch(color='#2c7fb8',label='append-only wins below H* (aggressive cache)'),
                   Patch(color='#d95f0e',label='compress almost always (weak cache)'),
                   Patch(color='#e6e6e6',label='context window')],fontsize=7,loc='lower right')
fig.savefig('paper/figs/fig6_ctxbalance.pdf',bbox_inches='tight'); print('wrote fig6')
