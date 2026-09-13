#!/usr/bin/env bash
# Phase 3b: second benchmark. swebench images are x86_64-only -> force linux/amd64 (Rosetta/QEMU) on Apple Silicon;
# low concurrency + setup multiplier because emulation is CPU-heavy and may run alongside the Gemini job. SWE-bench Verified 22-task diverse subset on DeepSeek V4 Flash,
# append-only vs pure state, k=1.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
INCLUDES=(); while read -r t; do [ -n "$t" ] && INCLUDES+=(-i "$t"); done < tier1/swe-subset.txt
for P in tbmin tbstate-nosearch; do
  echo "=== arm $P $(date) ==="
  DOCKER_DEFAULT_PLATFORM=linux/amd64 PYTHONPATH="$ROOT" harbor run -p data/swebench/swe-bench-verified "${INCLUDES[@]}" \
    -a harness.dsh_agent:DshAgent --ak "profile=$P" \
    -m deepseek/deepseek-v4-flash -n 2 -k 1 -r 1 --agent-setup-timeout-multiplier 4 -o jobs --job-name "swe-$P-k1" -y
done
echo "=== SWE RUN DONE $(date) ==="
