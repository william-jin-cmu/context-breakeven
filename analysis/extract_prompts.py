#!/usr/bin/env python3
"""Extract real per-step evolving state from Tier-0 append sessions and re-render
each step in BOTH layouts (append, span) for paired replay. Output: JSONL, one
object per (task, step) with {task, step, append, span}."""
import json, glob, sys, re

def parse_append(txt):
    """Parse an append-layout <execution-state> block into its parts."""
    task = re.search(r"# TASK \(fixed\)\n(.*?)\n\n# HISTORY", txt, re.S)
    hist = re.search(r"# HISTORY[^\n]*\n(.*?)\n\n# CURRENT STATE", txt, re.S)
    cur  = re.search(r"# CURRENT STATE[^\n]*\n(\{.*\})\n</execution-state>", txt, re.S)
    task = task.group(1) if task else ""
    log = [] if not hist or hist.group(1).strip() in ("","(none yet)") else hist.group(1).split("\n")
    st = json.loads(cur.group(1)) if cur else {}
    return task, log, st

def render_span(task, log, st, sep=" # # "):
    spans = []
    spans.append("<execution-state>\nStructured memory. Edit fields with update_state; history is maintained (sN = step N).")
    spans.append(f"# TASK\n{task}")
    for k in sorted((st.get("facts") or {})):
        spans.append(f"# FACT {k}\n{st['facts'][k]}")
    spans.append("# PLAN\n" + "\n".join(st.get("plan") or []))
    spans.append("# DONE\n" + "\n".join(st.get("done") or []))
    spans.append("# FILES\n" + "\n".join(st.get("files") or []))
    spans.append("# ISSUES\n" + "\n".join(st.get("issues") or []))
    spans.append("# HISTORY\n" + ("\n".join(log) if log else "(none yet)"))
    spans.append(f"# NEXT (step {st.get('step')})\n{st.get('next','')}\n</execution-state>")
    return sep.join(spans)

def render_append(task, log, st):
    cur = {k: st.get(k) for k in ("plan","facts","files","done","issues","next","step")}
    return ("<execution-state>\n# TASK (fixed)\n"+task+"\n\n# HISTORY\n"+
            ("\n".join(log) if log else "(none yet)")+
            "\n\n# CURRENT STATE\n"+json.dumps(cur,indent=2)+"\n</execution-state>")

def extract(session, max_steps=60):
    out=[]
    task_name=session.split("/")[2].split("__")[0] if "/jobs/" in session or session.startswith("jobs/") else session.split("__")[0]
    for l in open(session):
        e=json.loads(l); d=e.get("data") or {}
        if e["type"]=="user/message" and ((d.get("source") or {}).get("plugin"))=="dsh-skill-state":
            txt=d["content"][0]["text"]
            if "<execution-state>" not in txt: continue
            try: task,log,st=parse_append(txt)
            except Exception: continue
            out.append({"task":task_name,"step":st.get("step"),
                        "append":render_append(task,log,st),
                        "span":render_span(task,log,st)})
            if len(out)>=max_steps: break
    return out

if __name__=="__main__":
    sessions = sys.argv[1:] or sorted(glob.glob("jobs/pilot-tbstate-append-r1/*/agent/sessions/*/*/session.jsonl"))
    allrows=[]
    for s in sessions[:6]:
        rows=extract(s)
        if rows: allrows.append(rows); print(f"{rows[0]['task']}: {len(rows)} steps", file=sys.stderr)
    with open("tier1/prompts.jsonl","w") as f:
        for seq in allrows:
            for r in seq: f.write(json.dumps(r)+"\n")
    print(f"wrote tier1/prompts.jsonl: {sum(len(s) for s in allrows)} step-prompts from {len(allrows)} tasks", file=sys.stderr)
