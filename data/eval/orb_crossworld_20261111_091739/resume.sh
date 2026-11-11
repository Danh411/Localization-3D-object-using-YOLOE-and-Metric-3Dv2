#!/usr/bin/env bash
set -e
b="$(cd "$(dirname "$0")" && pwd)"
cd /mnt/d/loc3d_ws
export PYTHONDONTWRITEBYTECODE=1 TMPDIR="$b/tmp" YOLO_CONFIG_DIR="$b/ultralytics" OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2
.venv/bin/python "$b/test_diagnostic.py" > "$b/regression_diagnostic.log" 2>&1
for room in aws tiffany; do
  bash "$b/capture.sh" "$room"
  .venv/bin/python "$b/experiment.py" "$room" > "$b/$room/analysis.log" 2>&1
done
.venv/bin/python -m pytest -q -s -p no:cacheprovider --basetemp="$b/tmp/pytest" tests > "$b/regression_loc3d.log" 2>&1
echo 0 > "$b/batch_exit.txt"
