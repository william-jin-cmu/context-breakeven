#!/usr/bin/env bash
# Run the full Terminal-Bench 2.1 task set with one dsh profile.
# Usage: scripts/run_full.sh <profile> [job-name] [extra harbor args...]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROFILE="${1:?profile}"; shift || true
JOB="${1:-full-$PROFILE-$(date +%Y%m%d-%H%M)}"; shift || true
cd "$ROOT"
PYTHONPATH="$ROOT" harbor run -p data/tb21/tasks \
  -a harness.dsh_agent:DshAgent --ak "profile=$PROFILE" \
  -m deepseek/deepseek-v4-flash -n 5 -k 1 -r 1 -o jobs --job-name "$JOB" -y "$@"
