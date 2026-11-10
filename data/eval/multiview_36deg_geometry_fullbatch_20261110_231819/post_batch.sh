#!/usr/bin/env bash
set -e
b="$(cd "$(dirname "$0")" && pwd)"
cd /mnt/d/loc3d_ws
export PYTHONDONTWRITEBYTECODE=1 TMPDIR="$b/tmp"
deadline=$((SECONDS+2500))
until [[ -f "$b/pipeline_summary.exit" ]]; do
 (( SECONDS<deadline )) || exit 3
 sleep 3
done
[[ $(cat "$b/pipeline_summary.exit") == 0 ]]
for scan in scan_8x3 scan_36x1; do
 f="$b/$scan"
 /usr/bin/python3 "$f/pose_check.py" "$f/final_gazebo_pose.txt" > "$f/pose_check.json"
 id=$(sed -n -E 's/^ *scan_id: (scan_[0-9]+).*$/\1/p' "$f/action.log")
 [[ "$id" =~ ^scan_[0-9]+$ ]]
 mkdir -p "$f/production_debug"
 for img in /tmp/perception_dbg/"$id"_*_0.png; do
  if [[ -f "$img" ]]; then mv -- "$img" "$f/production_debug/"; fi
 done
done
.venv/bin/python "$b/test_geometry_diagnostic.py" > "$b/regression_geometry_final.log" 2>&1
.venv/bin/python -m pytest -q -s -p no:cacheprovider --basetemp="$b/tmp/pytest_final" tests > "$b/regression_loc3d_final.log" 2>&1
echo 0 > "$b/post_regression.exit"

