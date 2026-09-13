#!/usr/bin/env bash
# Link the plugin's @deepseek-ai peer packages to the dsh installation so the
# plugin shares the harness's own module instances (cordis Service identity).
# Usage: link-peers.sh <plugin-dir> [dsh-node-modules-dir]
set -euo pipefail
PLUGIN="${1:?plugin dir}"
DSH_NM="${2:-$(npm root -g)/@deepseek-ai/dsh/node_modules/@deepseek-ai}"
mkdir -p "$PLUGIN/node_modules/@deepseek-ai"
for pkg in cordis dsh-compaction dsh-llm dsh-session dsh-system-prompt dsh-token-meter dsh-tools schemastery; do
  ln -sfn "$DSH_NM/$pkg" "$PLUGIN/node_modules/@deepseek-ai/$pkg"
done
ls -la "$PLUGIN/node_modules/@deepseek-ai"
