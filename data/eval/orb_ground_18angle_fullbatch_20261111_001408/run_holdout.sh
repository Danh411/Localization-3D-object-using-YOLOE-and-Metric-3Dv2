#!/usr/bin/env bash
set -e
b="$(cd "$(dirname "$0")" && pwd)"
cd /mnt/d/loc3d_ws
export PYTHONDONTWRITEBYTECODE=1 TMPDIR="$b/tmp" YOLO_CONFIG_DIR="$b/ultralytics" OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2
.venv/bin/python "$b/test_diagnostic.py" > "$b/regression_diagnostic.log" 2>&1
deadline=$((SECONDS+340))
until [[ -s "$b/scan_18x1/experiment_summary.json" ]]; do
 (( SECONDS<deadline )) || exit 3
 sleep 2
done
.venv/bin/python "$b/prepare_scan.py" "$b" holdout_18x1
.venv/bin/python "$b/freeze_holdout.py" "$b" > "$b/holdout_freeze.log"
bash "$b/capture.sh" holdout_18x1
.venv/bin/python "$b/experiment.py" holdout_18x1 > "$b/holdout_analysis.log" 2>&1
.venv/bin/python -m pytest -q -s -p no:cacheprovider --basetemp="$b/tmp/pytest" tests > "$b/regression_loc3d.log" 2>&1

