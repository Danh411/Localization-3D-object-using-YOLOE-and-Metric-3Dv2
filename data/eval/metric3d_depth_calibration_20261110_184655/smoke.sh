#!/usr/bin/env bash
set -u
root="$(cd "$(dirname "$0")" && pwd)"
for name in tiffany aws; do
 if [[ "$name" == tiffany ]]; then
  pkg="$root/tiffany/src/hexapod_ws"
  file="$pkg/worlds/living_room.sdf"
 else
  pkg="$root/easynav/playground_kobuki/easynav_playground_kobuki_worlds"
  file="$pkg/worlds/small_house.world"
 fi
 export GZ_PARTITION="loc3d_original_${name}_184655" GZ_SIM_RESOURCE_PATH="$pkg/models"
 timeout --kill-after=2 17 gz sim -s -r --headless-rendering "$file" > "$root/original_$name.log" 2>&1 &
 proc=$!
 sleep 8
 gz service -l > "$root/original_${name}_services.txt"
 wait "$proc"
done
