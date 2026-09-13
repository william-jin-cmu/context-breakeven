#!/usr/bin/env bash
# Pre-pull every task's docker image (with retries) so Docker Hub flakiness doesn't fail trials.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
for f in "$ROOT"/data/tb21/tasks/*/task.toml; do
  img=$(sed -n 's/^docker_image = "\(.*\)"/\1/p' "$f")
  [ -z "$img" ] && continue
  if docker image inspect "$img" >/dev/null 2>&1; then continue; fi
  for i in 1 2 3 4; do docker pull -q "$img" >/dev/null 2>&1 && { echo "pulled $img"; break; }; echo "retry $i $img"; sleep 5; done
done
echo PREPULL DONE
