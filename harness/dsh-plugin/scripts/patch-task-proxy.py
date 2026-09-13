#!/usr/bin/env python3
"""Add proxy env to [environment.env] of the pilot tasks (local dataset copy only)."""
import re, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
PROXY = "http://host.docker.internal:7898"
NOPROXY = "localhost,127.0.0.1,host.docker.internal,api.deepseek.com,.deepseek.com"
ENV = {"HTTP_PROXY": PROXY, "HTTPS_PROXY": PROXY, "http_proxy": PROXY, "https_proxy": PROXY, "NO_PROXY": NOPROXY, "no_proxy": NOPROXY}
tasks = [l.strip() for l in (ROOT/"scripts/pilot-tasks.txt").read_text().splitlines() if l.strip() and not l.startswith("#")]
if "--all" in sys.argv:
    tasks = [p.name for p in (ROOT/"data/tb21/tasks").iterdir() if (p/"task.toml").exists()]
for t in tasks:
    p = ROOT/"data/tb21/tasks"/t/"task.toml"
    s = p.read_text()
    block = "[environment.env]\n" + "".join(f'{k} = "{v}"\n' for k, v in ENV.items())
    if "HTTPS_PROXY" in s:
        continue
    if re.search(r"^\[environment\.env\]\s*$", s, re.M):
        s = re.sub(r"^\[environment\.env\]\s*$", block.rstrip("\n"), s, count=1, flags=re.M)
    else:
        s = s.rstrip("\n") + "\n\n" + block
    p.write_text(s)
    print("patched", t)
