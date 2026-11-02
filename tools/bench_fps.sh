#!/usr/bin/env bash
# W1-A1/A2: đo tần số topic camera. Dùng: tools/bench_fps.sh /camera/image 15
T=${1:-/camera/image}; S=${2:-15}
timeout "$S" ros2 topic hz "$T" --window 50 2>&1 | tail -n 5
