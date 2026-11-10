#!/usr/bin/env bash
set -e
b="$(cd "$(dirname "$0")" && pwd)"
cd /mnt/d/loc3d_ws
for name in scan_8x3 scan_36x1; do
 f="$b/$name"
 rc=0
 bash "$f/run_ready.sh" > "$f/run.log" 2>&1 || rc=$?
 echo "$rc" > "$f/capture_exit.txt"
 if [[ $rc = 0 ]]; then
  PYTHONDONTWRITEBYTECODE=1 TMPDIR="$b/tmp" .venv/bin/python "$f/replay.py" > "$f/replay.log" 2>&1 || rc=$?
  echo "$rc" > "$f/replay_exit.txt"
 fi
 if [[ $rc != 0 ]]; then exit "$rc"; fi
done
