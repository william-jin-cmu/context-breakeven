#!/usr/bin/env bash
# Run the pilot subset with one dsh profile.
# Usage: scripts/run_pilot.sh <tbmin|tbstate> [job-name] [extra harbor args...]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROFILE="${1:?profile: tbmin or tbstate}"; shift || true
JOB="${1:-pilot-$PROFILE-$(date +%Y%m%d-%H%M)}"; shift || true
INCLUDES=()
while read -r line; do
  [[ -z "$line" || "$line" == \#* ]] && continue
  INCLUDES+=(-i "$line")
done < "$ROOT/scripts/pilot-tasks.txt"
cd "$ROOT"
PYTHONPATH="$ROOT" harbor run -p data/tb21/tasks "${INCLUDES[@]}" \
  -a harness.dsh_agent:DshAgent --ak "profile=$PROFILE" \
  -m deepseek/deepseek-v4-flash -n 4 -k 1 -r 1 -o jobs --job-name "$JOB" -y "$@"
