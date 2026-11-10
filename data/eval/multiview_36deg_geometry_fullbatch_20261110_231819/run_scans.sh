#!/usr/bin/env bash
b="$(cd "$(dirname "$0")" && pwd)"
cd /mnt/d/loc3d_ws
for scan in scan_8x3 scan_36x1; do
  f="$b/$scan"
  rc=0
  bash "$f/run_ready.sh" > "$f/run.log" 2>&1 || rc=$?
  echo "$rc" > "$f/capture_exit.txt"
  if [[ "$rc" = 0 ]]; then
    PYTHONDONTWRITEBYTECODE=1 TMPDIR="$f/tmp" .venv/bin/python "$f/replay.py" > "$f/replay.log" 2>&1
    echo "$?" > "$f/replay_exit.txt"
  fi
done
