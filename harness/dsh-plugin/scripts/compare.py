#!/usr/bin/env python3
"""Compare arms of a full run: pass rates, timeouts, tokens, cost, on all tasks and on tasks every arm completed."""
import json, glob, os, sys, re, subprocess
jobs = sys.argv[1:]
def load(job):
    rows = {}
    for d in glob.glob(f'jobs/{job}/*/'):
        rp = d + 'result.json'
        if not os.path.exists(rp): continue
        r = json.load(open(rp)); task = os.path.basename(d.rstrip('/')).split('__')[0]
        exc = (r.get('exception_info') or {}).get('exception_type') or ''
        reward = ((r.get('verifier_result') or {}).get('rewards') or {}).get('reward')
        st = dict(pass_=(reward or 0) >= 1, exc=exc, steps=0, unc=0, cache=0, out=0, reason=0, prompt_max=0, upd=0, srch=0)
        f = glob.glob(d + 'agent/sessions/**/session.jsonl', recursive=True)
        if f:
            for line in open(f[0]):
                try: e = json.loads(line)
                except Exception: continue
                t = e.get('type'); dd = e.get('data') or {}
                if t == 'assistant/message':
                    u = dd.get('usage') or {}
                    if not u: continue
                    st['steps'] += 1
                    cr = u.get('cacheReadTokens', 0) or 0; inp = u.get('inputTokens', 0) or 0
                    # dsh usage: inputTokens excludes cache reads? analyze.py treats total prompt = inputTokens + cacheRead
                    st['unc'] += inp; st['cache'] += cr; st['out'] += u.get('outputTokens', 0) or 0; st['reason'] += u.get('reasoningTokens', 0) or 0
                    st['prompt_max'] = max(st['prompt_max'], inp + cr)
                elif t == 'tool/call':
                    if dd.get('name') == 'update_state': st['upd'] += 1
                    if dd.get('name') == 'search_history': st['srch'] += 1
        st['cost'] = st['unc'] / 1e6 * 0.14 + st['cache'] / 1e6 * 0.014 + st['out'] / 1e6 * 0.28
        rows[task] = st
    return rows
def load_merged(spec):
    """'jobA+jobB': later jobs override earlier ones per task (used for fix-up reruns)."""
    rows = {}
    for j in spec.split('+'):
        rows.update(load(j))
    return rows
arms = {j: load_merged(j) for j in jobs}
def summarize(name, keys, rows):
    n = len(keys); p = sum(rows[t]['pass_'] for t in keys); to = sum(rows[t]['exc'] == 'AgentTimeoutError' for t in keys)
    env = sum(rows[t]['exc'] not in ('', 'AgentTimeoutError') for t in keys)
    steps = sum(rows[t]['steps'] for t in keys); unc = sum(rows[t]['unc'] for t in keys); cache = sum(rows[t]['cache'] for t in keys)
    out = sum(rows[t]['out'] for t in keys); cost = sum(rows[t]['cost'] for t in keys)
    hit = cache / (unc + cache) * 100 if unc + cache else 0
    print(f"{name:22s} n={n:3d} pass={p:3d} ({p/n*100:4.1f}%) timeout={to:2d} envfail={env:2d} steps={steps:5d} prompt/step={(unc+cache)/max(steps,1):8,.0f} unc={unc/1e6:6.2f}M cache={cache/1e6:6.2f}M hit={hit:4.1f}% out={out/1e6:5.2f}M out/step={out/max(steps,1):5.0f} cost=${cost:5.2f}")
print("== all tasks (each arm's own completed trials) ==")
for j, rows in arms.items(): summarize(j, list(rows), rows)
common = [t for t in arms[jobs[0]] if all(t in arms[j] and arms[j][t]['exc'] == '' for j in jobs)]
print(f"\n== tasks every arm completed without exception (n={len(common)}) ==")
for j, rows in arms.items(): summarize(j, common, rows)
print("\n== pass matrix on those tasks (1=pass) ==")
hdr = ' '.join(f"{j.split('+')[0].replace('full-','').replace('-r1',''):>18s}" for j in jobs); print(f"{'task':34s} {hdr}")
for t in sorted(common):
    vals = [arms[j][t]['pass_'] for j in jobs]
    if len(set(vals)) > 1: print(f"{t:34s} " + ' '.join(f"{int(v):>18d}" for v in vals))
print("\n== timeouts per arm ==")
for j, rows in arms.items(): print(j, sorted(t for t in rows if rows[t]['exc'] == 'AgentTimeoutError'))
