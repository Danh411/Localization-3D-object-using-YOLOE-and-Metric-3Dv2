#!/usr/bin/env bash
set -e
b="$(cd "$(dirname "$0")" && pwd)"
export PYTHONDONTWRITEBYTECODE=1
for name in "$@"; do
 room="$b/$name"
 export GZ_PARTITION="crossworld_$(basename "$b")_$name"
 export GZ_SIM_RESOURCE_PATH="$(/usr/bin/python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["resource_path"])' "$room/design.json")"
 timeout --kill-after=4 460 gz sim -r -s --headless-rendering "$room/world.sdf" >"$room/gazebo.log" 2>&1 &
 pid=$!
 rc=0
 timeout --kill-after=3 440 /usr/bin/python3 "$b/collect.py" "$room" >"$room/capture.log" 2>&1 || rc=$?
 kill -TERM "$pid" 2>/dev/null || true
 wait "$pid" 2>/dev/null || true
 echo "$rc" >"$room/capture_exit.txt"
done

