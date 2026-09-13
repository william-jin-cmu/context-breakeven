#!/usr/bin/env python3
"""Expose the host's loopback-only proxy (127.0.0.1:7897) to docker containers on 0.0.0.0:7898."""
import asyncio, sys
LISTEN=int(sys.argv[1]) if len(sys.argv)>1 else 7898
TARGET=("127.0.0.1", int(sys.argv[2]) if len(sys.argv)>2 else 7897)
async def pipe(r,w):
    try:
        while True:
            d=await r.read(65536)
            if not d: break
            w.write(d); await w.drain()
    except Exception: pass
    finally:
        try: w.close()
        except Exception: pass
async def handle(r,w):
    try: tr,tw=await asyncio.open_connection(*TARGET)
    except Exception:
        w.close(); return
    await asyncio.gather(pipe(r,tw),pipe(tr,w))
async def main():
    s=await asyncio.start_server(handle,"0.0.0.0",LISTEN); await s.serve_forever()
asyncio.run(main())
