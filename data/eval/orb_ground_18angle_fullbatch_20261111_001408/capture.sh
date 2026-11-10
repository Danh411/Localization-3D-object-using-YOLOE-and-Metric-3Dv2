#!/usr/bin/env bash
set -e
b="$(cd "$(dirname "$0")" && pwd)"
cd /mnt/d/loc3d_ws
f="$b/$1"
export PYTHONDONTWRITEBYTECODE=1
bash "$f/run_ready.sh" > "$f/run.log" 2>&1
/usr/bin/python3 "$f/pose_check.py" "$f/final_gazebo_pose.txt" > "$f/pose_check.json"
.venv/bin/python "$f/replay.py" > "$f/replay.log" 2>&1
echo 0 > "$f/replay_exit.txt"

