#!/usr/bin/env bash
set -e
b="$(cd "$(dirname "$0")" && pwd)"
cd /mnt/d/loc3d_ws
export PYTHONDONTWRITEBYTECODE=1 TMPDIR="$b/tmp" YOLO_CONFIG_DIR="$b/ultralytics"
deadline=$((SECONDS+2600))
until [[ -f "$b/scan_8x3/replay_exit.txt" && -f "$b/scan_36x1/replay_exit.txt" ]]; do
 if (( SECONDS>=deadline )); then exit 3; fi
 for d in scan_8x3 scan_36x1; do
  if [[ -f "$b/$d/capture_exit.txt" && $(cat "$b/$d/capture_exit.txt") != 0 ]]; then exit 4; fi
 done
 sleep 3
done
[[ $(cat "$b/scan_8x3/replay_exit.txt") == 0 && $(cat "$b/scan_36x1/replay_exit.txt") == 0 ]]
for script in methods angles book_probe ground pipeline_summary; do
 rc=0
 .venv/bin/python "$b/$script.py" kitchen > "$b/$script.log" 2>&1 || rc=$?
 echo "$rc" > "$b/$script.exit"
done
