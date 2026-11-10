"""Điểm tiếp cận cho tìm đường — mục 5.7 (A7).

Chỉ tính trên mặt phẳng ngang (x, y). Điểm nằm trên đoạn từ tâm vật về phía
camera, cách vật standoff_m; yaw hướng từ điểm đó vào tâm vật.
Nếu camera gần vật hơn standoff_m thì trả điểm tại camera và cờ already_close.

Thuần Python; không phụ thuộc ROS.
"""
from __future__ import annotations

import math


def approach_point(obj_xy: tuple[float, float],
                   cam_xy: tuple[float, float],
                   standoff_m: float = 0.6) -> dict:
    """Ví dụ spec: camera (0,0), vật (3,0), standoff 0.6 -> (2.4, 0), yaw 0."""
    ox, oy = float(obj_xy[0]), float(obj_xy[1])
    cx, cy = float(cam_xy[0]), float(cam_xy[1])
    dx, dy = cx - ox, cy - oy                    # hướng vật -> camera
    d = math.hypot(dx, dy)
    if d < 1e-9:
        return {"x": cx, "y": cy, "yaw_rad": 0.0, "already_close": True,
                "distance_m": 0.0}
    if d <= standoff_m:
        return {"x": cx, "y": cy, "yaw_rad": math.atan2(-dy, -dx),
                "already_close": True, "distance_m": d}
    ux, uy = dx / d, dy / d                      # đơn vị hướng vật -> camera
    ax, ay = ox + ux * standoff_m, oy + uy * standoff_m
    return {"x": ax, "y": ay, "yaw_rad": math.atan2(oy - ay, ox - ax),
            "already_close": False, "distance_m": d}
