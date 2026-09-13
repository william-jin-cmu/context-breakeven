#!/usr/bin/env bash
# Error-bar run: 3 arms x 10 tasks x k=3 on DeepSeek API for run-to-run variance.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
INCLUDES=(); while read -r t; do [ -n "$t" ] && INCLUDES+=(-i "$t"); done < tier1/seed-tasks.txt
for P in tbmin tbstate-nosearch tbstate-append; do
  echo "=== arm $P $(date) ==="
  PYTHONPATH="$ROOT" harbor run -p data/tb21/tasks "${INCLUDES[@]}" \
    -a harness.dsh_agent:DshAgent --ak "profile=$P" \
    -m deepseek/deepseek-v4-flash -n 4 -k 3 -r 1 -o jobs --job-name "seed-$P-k3" -y
done
echo "=== SEED RUN DONE $(date) ==="
