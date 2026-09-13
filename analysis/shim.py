#!/usr/bin/env python3
"""OpenAI-compatible shim between dsh and a MiniPIC vLLM fork.

dsh -> shim (chat/completions) -> vLLM (completions with token-id prompt).
The shim locates the <execution-state> user message, splits it on SPAN_SEP,
tokenizes each span, inserts the MiniPIC SSEP token id padded to BLOCK so each
span starts on a KV-block boundary, and forwards the assembled token-id prompt.
Pass-through mode (--passthrough) just relays, to validate connectivity first.
"""
import os, httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from transformers import AutoTokenizer

VLLM = os.environ.get("VLLM_URL", "http://127.0.0.1:8000")
MODEL = os.environ["MODEL"]
SPAN_SEP = os.environ.get("SPAN_SEP", " # # ")
BLOCK = int(os.environ.get("BLOCK", "16"))
SSEP_ID = os.environ.get("SSEP_ID")           # token id string, set once fork is up
PASSTHROUGH = os.environ.get("PASSTHROUGH", "1") == "1"
tok = AutoTokenizer.from_pretrained(MODEL)
app = FastAPI()

def pad_to_block(ids):
    r = len(ids) % BLOCK
    return ids + ([tok.pad_token_id or tok.eos_token_id] * (BLOCK - r) if r else [])

@app.post("/v1/chat/completions")
async def chat(req: Request):
    body = await req.json()
    async with httpx.AsyncClient(timeout=600) as c:
        if PASSTHROUGH:
            r = await c.post(f"{VLLM}/v1/chat/completions", json=body)
            return JSONResponse(r.json(), status_code=r.status_code)
        # span mode: build token-id prompt
        msgs = body["messages"]
        ids = []
        for m in msgs:
            content = m.get("content") or ""
            if "<execution-state>" in content and SPAN_SEP in content:
                for i, span in enumerate(content.split(SPAN_SEP)):
                    if i and SSEP_ID: ids.append(int(SSEP_ID))
                    ids += pad_to_block(tok.encode(span, add_special_tokens=False))
            else:
                ids += tok.encode(content, add_special_tokens=False)
        comp = {"model": MODEL, "prompt": ids,
                "max_tokens": body.get("max_tokens", 2048),
                "temperature": body.get("temperature", 1.0)}
        r = await c.post(f"{VLLM}/v1/completions", json=comp)
        j = r.json()
        # adapt completion -> chat shape
        txt = (j.get("choices") or [{}])[0].get("text", "")
        return JSONResponse({"choices":[{"message":{"role":"assistant","content":txt},
                             "finish_reason":"stop"}], "usage": j.get("usage",{})})
