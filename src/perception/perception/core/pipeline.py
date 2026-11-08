"""process(image_rgb, K, detector, depth_model, cfg): YOLOE rồi Metric3D TUẦN TỰ, tính p_cam (mục 3.1, 5.3, 5.4).
p_world do lớp ROS (tf2) hoặc tools/run_images.py tính; ở đây chỉ tới camera_optical_frame."""
import time
import numpy as np
from .fusion import object_depth, is_truncated, erode_mask
from .geometry import backproject_optical


def _sync():
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.synchronize()
    except Exception:
        pass


def process(image_rgb, K, detector, depth_model, cfg, depth_gt=None):
    fx, fy, cx, cy = K
    h, w = image_rgb.shape[:2]
    fu, dc, cm = cfg["fusion"], cfg["depth"], cfg["camera"]
    t = {}
    t0 = time.perf_counter(); dets = detector.detect(image_rgb); _sync(); t["yolo_ms"] = (time.perf_counter() - t0) * 1e3
    t0 = time.perf_counter(); depth = depth_model.estimate(image_rgb, fx); _sync(); t["depth_ms"] = (time.perf_counter() - t0) * 1e3
    if depth_gt is not None and depth_gt.shape != depth.shape:
        raise ValueError(f"depth_gt shape {depth_gt.shape} không khớp depth {depth.shape}")
    t0 = time.perf_counter()
    obs, rejected = [], []
    for d in dets:
        r = object_depth(depth, d["mask"], fu["mask_erode_ratio"], fu["min_valid_ratio"], cm["clip_near"], dc["max_m"])
        base = {"class_id": d["class_id"], "class_name": d["class_name"], "confidence": d["confidence"],
                "bbox_xyxy": d["bbox_xyxy"], "truncated": is_truncated(d["bbox_xyxy"], w, h, fu["border_px"]),
                "mask": d["mask"], "mask_area_px": r["mask_area_px"], "valid_depth_ratio": r["valid_ratio"]}
        if r["reason"]:
            rejected.append({**base, "reason": r["reason"]}); continue
        z = r["depth_m"]
        p = backproject_optical(r["u"], r["v"], z, fx, fy, cx, cy)
        o = {**base, "depth_m": z, "depth_p25_m": r["depth_p25_m"], "range_m": float(np.linalg.norm(p)),
             "u": r["u"], "v": r["v"], "p_cam": [float(v) for v in p]}
        if depth_gt is not None:                              # chỉ để đánh giá: GT trên cùng pixel mask
            gt_mask = erode_mask(d["mask"], fu["mask_erode_ratio"])
            g = depth_gt[gt_mask]; g = g[np.isfinite(g) & (g > cm["clip_near"])]
            o["depth_gt_m"] = float(np.median(g)) if g.size else None
            u_gt = int(np.clip(round(r["u"]), 0, w - 1))
            v_gt = int(np.clip(round(r["v"]), 0, h - 1))
            z_gt_at_uv = float(depth_gt[v_gt, u_gt])
            if np.isfinite(z_gt_at_uv) and cm["clip_near"] < z_gt_at_uv < dc["max_m"]:
                p_gt = backproject_optical(r["u"], r["v"], z_gt_at_uv, fx, fy, cx, cy)
                o["depth_gt_at_uv_m"] = z_gt_at_uv
                o["p_gt_cam_at_uv"] = [float(v) for v in p_gt]
            else:
                o["depth_gt_at_uv_m"] = None
                o["p_gt_cam_at_uv"] = None
        obs.append(o)
    t["post_ms"] = (time.perf_counter() - t0) * 1e3
    return {"observations": obs, "rejected": rejected, "depth": depth, "timings_ms": t}
