import os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "perception"))
from perception.core.fusion import object_depth, is_truncated, erode_mask
from perception.core.pipeline import process
from perception.core.geometry import intrinsics_from_hfov

def disk(h, w, cy, cx, r):
    yy, xx = np.mgrid[:h, :w]; return (yy - cy) ** 2 + (xx - cx) ** 2 <= r * r

def test_noisy_border_ignored():            # viền sai 5 m, lõi 2 m: sau erode median vẫn ~2
    h, w = 200, 200; m = disk(h, w, 100, 100, 40); inner = disk(h, w, 100, 100, 34)
    d = np.full((h, w), 2.0, np.float32); d[m & ~inner] = 5.0
    r = object_depth(d, m); assert r["reason"] is None and abs(r["depth_m"] - 2.0) < 1e-6

def test_tiny_mask_rejected():
    m = np.zeros((50, 50), bool); m[10:12, 10:12] = True
    assert object_depth(np.ones((50, 50), np.float32), m)["reason"] == "empty_mask"

def test_all_nan_rejected():
    m = disk(100, 100, 50, 50, 20); d = np.full((100, 100), np.nan, np.float32)
    assert object_depth(d, m)["reason"] == "low_valid_ratio"

def test_partial_nan_threshold():
    m = disk(100, 100, 50, 50, 25); d = np.full((100, 100), 3.0, np.float32); d[:50] = np.nan
    r = object_depth(d, m); assert r["reason"] is None and 0.3 <= r["valid_ratio"] <= 0.6 and abs(r["depth_m"] - 3) < 1e-6

def test_centroid_of_valid_pixels():
    m = disk(100, 100, 50, 50, 25); d = np.full((100, 100), 3.0, np.float32); d[:, 50:] = np.nan
    r = object_depth(d, m); assert r["u"] < 50 and abs(r["v"] - 49.5) < 1.5   # lệch về nửa trái hợp lệ

def test_truncated():
    assert is_truncated([2, 50, 100, 120], 1280, 720) and not is_truncated([100, 100, 200, 200], 1280, 720)

class FakeDet:
    def detect(self, rgb):
        h, w = rgb.shape[:2]; m = disk(h, w, h // 2, w // 2, 40)
        return [{"class_id": 0, "class_name": "cup", "confidence": 0.9, "bbox_xyxy": [w//2-40, h//2-40, w//2+40, h//2+40], "mask": m}]
class FakeDepth:
    def estimate(self, rgb, fx): return np.full(rgb.shape[:2], 2.0, np.float32)

def test_pipeline_center_object():
    cfg = {"fusion": dict(mask_erode_ratio=0.05, min_valid_ratio=0.3, border_px=8), "depth": dict(max_m=10.0), "camera": dict(clip_near=0.1)}
    K = intrinsics_from_hfov(1280, 720, 70.0)
    out = process(np.zeros((720, 1280, 3), np.uint8), K, FakeDet(), FakeDepth(), cfg)
    o = out["observations"][0]
    assert abs(o["depth_m"] - 2) < 1e-6 and abs(o["range_m"] - 2) < 0.01 and abs(o["p_cam"][0]) < 0.01 and not o["truncated"]

def test_pipeline_includes_ground_truth_depth():
    cfg = {"fusion": dict(mask_erode_ratio=0.05, min_valid_ratio=0.3, border_px=8), "depth": dict(max_m=10.0), "camera": dict(clip_near=0.1)}
    K = intrinsics_from_hfov(1280, 720, 70.0)
    mask = FakeDet().detect(np.zeros((720, 1280, 3), np.uint8))[0]["mask"]
    gt_mask = erode_mask(mask, cfg["fusion"]["mask_erode_ratio"])
    depth_gt = np.full((720, 1280), 8.0, np.float32)
    depth_gt[gt_mask] = 1.5
    out = process(np.zeros((720, 1280, 3), np.uint8), K, FakeDet(), FakeDepth(), cfg, depth_gt=depth_gt)
    assert out["observations"][0]["depth_gt_m"] == 1.5

def test_pipeline_rejects_mismatched_ground_truth_shape():
    cfg = {"fusion": dict(mask_erode_ratio=0.05, min_valid_ratio=0.3, border_px=8), "depth": dict(max_m=10.0), "camera": dict(clip_near=0.1)}
    K = intrinsics_from_hfov(1280, 720, 70.0)
    try:
        process(np.zeros((720, 1280, 3), np.uint8), K, FakeDet(), FakeDepth(), cfg,
                depth_gt=np.zeros((10, 10), np.float32))
    except ValueError as exc:
        assert "shape" in str(exc)
    else:
        raise AssertionError("Mismatched ground-truth shape must be rejected")
