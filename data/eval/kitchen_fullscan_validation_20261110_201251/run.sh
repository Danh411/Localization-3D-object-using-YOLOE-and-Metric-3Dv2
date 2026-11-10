#!/usr/bin/env bash
set -o pipefail
run="$(cd "$(dirname "$0")" && pwd)"
cd /mnt/d/loc3d_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
export ROS_DOMAIN_ID=76 ROS_LOG_DIR="$run/ros" GZ_PARTITION="loc3d_$(basename "$run")"
export LOC3D_WORLD="$run/kitchen_controlled.sdf" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
mkdir -p "$ROS_LOG_DIR"
ros2 launch "$run/reference.launch.py" config:="$run/config.yaml" classes:="$run/classes.yaml" gt:="$run/gt.yaml" db_dir:="$run/db" > "$run/launch.log" 2>&1 &
launch_pid=$!
trap 'kill -TERM "$launch_pid" 2>/dev/null || true; wait "$launch_pid" 2>/dev/null || true' EXIT
deadline=$((SECONDS + 360))
until grep -q 'Models loaded' "$run/launch.log"; do
  if (( SECONDS >= deadline )) || ! kill -0 "$launch_pid" || grep -q 'process has died' "$run/launch.log"; then exit 1; fi
  sleep 2
done
timeout 640 ros2 action send_goal /scan/run scan_interfaces/action/RunScan '{step_deg: 45.0, frames_per_stop: 3, settle_time_s: 1.5}' --feedback | tee "$run/action.log"
