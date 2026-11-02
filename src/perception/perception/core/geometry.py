"""Hình học thuần (không ROS). Công thức mục 4.2, 5.1, 5.4."""
import math
import numpy as np

def intrinsics_from_hfov(w, h, hfov_deg):
    fx = (w / 2) / math.tan(math.radians(hfov_deg) / 2)
    return fx, fx, w / 2, h / 2

def resize_scale(w, h, input_hw=(616, 1064)):
    return min(input_hw[0] / h, input_hw[1] / w)

def canonical_to_metric(depth_canonical, fx, w, h, input_hw=(616, 1064), canonical_f=1000.0):
    """Mục 5.1: tiêu cự phải nhân với tỉ lệ resize trước khi đổi sang mét."""
    s = resize_scale(w, h, input_hw)
    return depth_canonical * (fx * s / canonical_f)

def backproject_optical(u, v, z, fx, fy, cx, cy):
    return np.array([(u - cx) * z / fx, (v - cy) * z / fy, z])

def optical_to_world(p_cam, yaw, base_xyz, t_offset=(0.0, 0.0, 0.0)):
    X, Y, Z = p_cam
    p_link = np.array([Z, -X, -Y]) + np.asarray(t_offset)
    c, s = math.cos(yaw), math.sin(yaw)
    R = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    return np.asarray(base_xyz) + R @ p_link
