"""Độ sâu đại diện của một vật (mục 5.3). Không phụ thuộc torch/ROS."""
import cv2
import numpy as np


def erode_mask(mask, ratio=0.05):
    area = int(mask.sum())
    if area == 0:
        return mask.astype(bool)
    k = max(3, int(round(ratio * np.sqrt(area))))
    return cv2.erode(mask.astype(np.uint8), np.ones((k, k), np.uint8)) > 0


def is_truncated(bbox, w, h, border_px=8):
    x1, y1, x2, y2 = bbox
    return bool(x1 < border_px or y1 < border_px or x2 > w - 1 - border_px or y2 > h - 1 - border_px)


def object_depth(depth, mask, erode_ratio=0.05, min_valid_ratio=0.3, clip_near=0.1, max_m=10.0):
    """Trả về dict. Nếu bị loại: 'reason' khác None ('empty_mask' | 'low_valid_ratio'), ngược lại reason = None
    và có depth_m (median), depth_p25_m, u, v (trọng tâm các pixel hợp lệ), valid_ratio, mask_area_px."""
    m = erode_mask(mask, erode_ratio)
    area = int(m.sum())
    if area == 0:
        return {"reason": "empty_mask", "valid_ratio": 0.0, "mask_area_px": 0}
    d = depth[m]
    ok = np.isfinite(d) & (d > clip_near) & (d < max_m)
    ratio = float(ok.sum()) / area
    if ratio < min_valid_ratio:
        return {"reason": "low_valid_ratio", "valid_ratio": ratio, "mask_area_px": area}
    ys, xs = np.nonzero(m)
    vals = d[ok]
    return {"reason": None, "depth_m": float(np.median(vals)), "depth_p25_m": float(np.percentile(vals, 25)),
            "u": float(xs[ok].mean()), "v": float(ys[ok].mean()), "valid_ratio": ratio, "mask_area_px": area}
