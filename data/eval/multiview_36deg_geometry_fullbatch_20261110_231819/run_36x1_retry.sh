#!/usr/bin/env bash
set -e
b="$(cd "$(dirname "$0")" && pwd)"
cd /mnt/d/loc3d_ws
f="$b/scan_36x1"
deadline=$((SECONDS+1400))
until [[ -f "$b/scan_8x3/capture_exit.txt" ]]; do
 (( SECONDS<deadline )) || exit 2
 sleep 3
done
rc=0
bash "$f/run_ready.sh" > "$f/run.log" 2>&1 || rc=$?
echo "$rc" > "$f/capture_exit.txt"
if [[ $rc = 0 ]]; then
 PYTHONDONTWRITEBYTECODE=1 TMPDIR="$f/tmp" .venv/bin/python "$f/replay.py" > "$f/replay.log" 2>&1 || rc=$?
 echo "$rc" > "$f/replay_exit.txt"
fi
exit "$rc"
