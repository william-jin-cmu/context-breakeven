#!/usr/bin/env bash
# Phase 3a: second model family. Gemini 3.5 Flash (r=0.10) on the 10-task TB2.1 seed subset,
# append-only vs pure state, k=1. Budget-capped subset; cost computed offline from token counts.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
INCLUDES=(); while read -r t; do [ -n "$t" ] && INCLUDES+=(-i "$t"); done < tier1/seed-tasks.txt
for P in tbmin-gemini tbstate-nosearch-gemini; do
  echo "=== arm $P $(date) ==="
  PYTHONPATH="$ROOT" harbor run -p data/tb21/tasks "${INCLUDES[@]}" \
    -a harness.dsh_agent:DshAgent --ak "profile=$P" \
    -m google/gemini-3.5-flash -n 4 -k 1 -r 1 -o jobs --job-name "gem-$P-k1" -y
done
echo "=== GEMINI RUN DONE $(date) ==="
