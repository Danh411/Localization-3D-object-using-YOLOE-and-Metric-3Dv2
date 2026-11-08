import math, numpy as np, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "perception"))
from perception.core.geometry import *

def test_K():
    fx, fy, cx, cy = intrinsics_from_hfov(1280, 720, 70.0)
    assert abs(fx - 914.01) < 0.5 and fx == fy and cx == 640 and cy == 360

def test_scale_example():
    assert abs(resize_scale(1280, 720) - 0.83125) < 1e-9
    fx = intrinsics_from_hfov(1280, 720, 70.0)[0]
    assert abs(canonical_to_metric(1.0, fx, 1280, 720) - 0.7598) < 1e-3

def test_scale_linear_in_fx():
    assert abs(canonical_to_metric(1.0, 2000, 1280, 720) / canonical_to_metric(1.0, 1000, 1280, 720) - 2) < 1e-9

def test_world_example():
    fx, fy, cx, cy = intrinsics_from_hfov(1280, 720, 70.0)
    p = backproject_optical(cx, cy, 2.0, fx, fy, cx, cy)
    w = optical_to_world(p, math.radians(90), (1, 1, 1))
    assert np.allclose(w, (1, 3, 1), atol=1e-3)

def test_world_optical_roundtrip_with_pan_offset():
    p_cam = np.array([0.25, -0.4, 2.3])
    yaw = math.radians(45)
    base = (2.0, 2.0, 1.2)
    offset = (0.05, 0.0, 0.0)
    p_world = optical_to_world(p_cam, yaw, base, offset)
    assert np.allclose(world_to_optical(p_world, yaw, base, offset), p_cam)
