#!/usr/bin/env bash
set -u
root="$(cd "$(dirname "$0")" && pwd)"
export PYTHONDONTWRITEBYTECODE=1
for name in "$@"; do
 room="$root/holdout_$name"
 mkdir "$room" || exit
 cp "$root/run_$name/world.sdf" "$root/run_$name/design.json" "$room/"
 export GZ_PARTITION="loc3d_holdout_${name}_184655"
 export GZ_SIM_RESOURCE_PATH="$(/usr/bin/python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["resource_path"])' "$room/design.json")"
 timeout --kill-after=4 260 gz sim -r -s --headless-rendering "$room/world.sdf" >"$room/gazebo.log" 2>&1 &
 pid=$!
 timeout --kill-after=3 235 /usr/bin/python3 "$root/collect.py" "$room" >"$room/capture.log" 2>&1
 rc=$?
 kill -TERM "$pid" 2>/dev/null || true
 wait "$pid" 2>/dev/null || true
 echo "$rc" >"$room/capture_exit.txt"
done
