#!/usr/bin/env bash
set -e -o pipefail
run="$(cd "$(dirname "$0")" && pwd)"
cd /mnt/d/loc3d_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
export ROS_DOMAIN_ID=93 ROS_LOG_DIR="$run/ros" GZ_PARTITION="crossworld_$(basename "$(dirname "$run")")_$(basename "$run")_native"
export LOC3D_WORLD="$run/kitchen_controlled.sdf" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
export TORCH_HOME="$run/native_cache" XDG_CACHE_HOME="$run/native_cache" YOLO_CONFIG_DIR="$run/native_ultralytics" TMPDIR="$run/native_tmp"
mkdir -p "$run/native_tmp" "$run/native_cache" "$run/native_ultralytics" "$run/ros"
ros2 launch "$run/reference.launch.py" config:="$run/config.yaml" classes:="$run/classes.yaml" gt:="$run/gt.yaml" db_dir:="$run/db" > "$run/launch.log" 2>&1 &
launch_pid=$!
cleanup() {
 kill -TERM "$launch_pid" 2>/dev/null || true
 wait "$launch_pid" 2>/dev/null || true
 while IFS= read -r pid; do
  [[ -n "$pid" ]] && kill -TERM "$pid" 2>/dev/null || true
 done < <(pgrep -f "^gz sim -r -s --headless-rendering $run/kitchen_controlled.sdf$")
}
trap cleanup EXIT
# Require data on both sides of the bridge before sending a scan goal.
{
 for attempt in 1 2 3 4 5; do
  if timeout 10 gz topic -e -n 1 -t /joint_states && timeout 10 ros2 topic echo /joint_states --once --no-daemon &&
     timeout 10 ros2 topic echo /camera/camera_info --once --no-daemon; then
     break
  fi
  if [[ $attempt == 5 ]]; then exit 2; fi
 done
} > "$run/bridge_ready.log" 2>&1
deadline=$((SECONDS + 360))
until grep -q 'Models loaded' "$run/launch.log"; do
  if (( SECONDS >= deadline )) || ! kill -0 "$launch_pid" || grep -q 'process has died' "$run/launch.log"; then exit 1; fi
  sleep 2
done
timeout 1700 ros2 action send_goal /scan/run scan_interfaces/action/RunScan '{step_deg: 20.0, frames_per_stop: 1, settle_time_s: 1.5}' --feedback | tee "$run/action.log"
grep -q 'status: SUCCEEDED' "$run/action.log"
timeout 12 gz topic -e -n 1 -t /world/default/pose/info > "$run/final_gazebo_pose.txt"
timeout 35 /usr/bin/python3 "$run/query_live.py" > "$run/query_live.log" 2>&1
