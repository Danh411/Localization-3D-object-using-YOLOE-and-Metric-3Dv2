#!/usr/bin/env bash
set -e
cd /mnt/d/loc3d_ws
b=/mnt/d/loc3d_ws/data/eval/orb_crossworld_20261111_091739
export PYTHONDONTWRITEBYTECODE=1
.venv/bin/python "$b/verify.py" > "$b/verification.log" 2>&1
.venv/bin/python "$b/write_report.py"
cd "$b"
sha256sum -c --quiet manifest.sha256
sha256sum -c --quiet raw_frames.sha256
