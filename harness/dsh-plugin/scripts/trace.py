#!/usr/bin/env python3
"""Print a compact step-by-step trace of a dsh session.jsonl (tool calls, results, final state)."""
import json, sys
f = sys.argv[1]
calls = []; last_ck = None; texts = []
for line in open(f):
    e = json.loads(line); t = e.get('type'); d = e.get('data')
    if d is None: continue
    if t == 'tool/call':
        a = d['arguments']
        try: a = json.loads(a)
        except Exception: pass
        calls.append((d['step'], d['name'], json.dumps(a, ensure_ascii=False)[:160]))
    elif t == 'tool/result':
        c = d['message']['content'][0]
        txt = ''.join(b.get('text', '') for b in c['content'] if isinstance(b, dict))
        calls.append((d['step'], '  ->', ('ERR ' if c.get('isError') else '') + txt.replace('\n', ' ')[:160]))
    elif t == 'user/message' and (d.get('source') or {}).get('plugin') == 'dsh-skill-state':
        last_ck = d['content'][0]['text']
    elif t == 'assistant/message':
        tx = ''.join(b.get('text', '') for b in d['message']['content'] if b.get('type') == 'text')
        if tx.strip(): texts.append((d['step'], tx[:400]))
for c in calls: print(c[0], c[1], c[2])
if last_ck: print("=== final checkpoint ==="); print(last_ck[-3000:])
print("=== assistant texts (last 3) ===")
for s, t in texts[-3:]: print(s, t)
