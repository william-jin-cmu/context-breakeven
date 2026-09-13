# Apply our per-step token counts to real 2026 provider price sheets.
# token counts (across-task per-step means, full run)
app=dict(u=588,  h=35990, o=687)
sta=dict(u=4739, h=4548,  o=1047)
# (miss $/M, cached-input $/M, output $/M) approx public 2026 prices
P={
 'DeepSeek V4 Flash': (0.14, 0.014, 0.28),
 'Anthropic (cache 0.1x)': (0.80, 0.08, 4.00),
 'Google Gemini Flash (0.25x)': (0.075, 0.01875, 0.30),
 'OpenAI GPT-mini (0.5x)': (0.15, 0.075, 0.60),
}
def cost(d,pm,pc,po): return (d['u']*pm + d['h']*pc + d['o']*po)/1e6*1e3  # m$ per step
print(f"{'provider':30s} {'r=pc/pm':>8s} {'append':>9s} {'state':>9s} {'winner':>8s} {'state/app':>10s}")
for name,(pm,pc,po) in P.items():
    ca=cost(app,pm,pc,po); cs=cost(sta,pm,pc,po); r=pc/pm
    w='append' if ca<cs else 'STATE'
    print(f"{name:30s} {r:8.3f} {ca:8.3f}m {cs:8.3f}m {w:>8s} {cs/ca:9.2f}x")
