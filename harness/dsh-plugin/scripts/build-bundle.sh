#!/usr/bin/env bash
# Build cache/dsh-bundle-linux-amd64.tgz: node 22 + @deepseek-ai/dsh, for upload into task containers.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; mkdir -p "$ROOT/cache"
VER="${1:-0.1.2-alpha.5}"
docker run --rm --platform linux/amd64 -v "$ROOT/cache:/out" node:22-bookworm-slim bash -lc "set -e; apt-get update -qq >/dev/null && apt-get install -y -qq ca-certificates >/dev/null; npm install -g @deepseek-ai/dsh@$VER; dsh --version; tar czf /out/dsh-bundle-linux-amd64.tgz -C / usr/local/bin/node usr/local/bin/dsh usr/local/lib/node_modules/@deepseek-ai"
ls -la "$ROOT/cache"
