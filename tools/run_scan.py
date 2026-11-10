#!/usr/bin/env python3
"""Chạy quét offline một lệnh: YOLOE -> Metric3D -> tọa độ world -> gộp vật -> SQLite.

Bao trọn pipeline mục 3-6 không cần ROS: đọc ảnh (kèm capture_metadata.csv để lấy
yaw thực), chạy pipeline.core, chiếu sang world, gộp trùng (A6), ghi DB (mục 6),
chốt trạng thái, rồi đánh giá nhanh với GT nếu có.

  python3 tools/run_scan.py --images data/eval/scan_panoptic/capture \
      --db data/db/run.sqlite
Tùy chọn: --depth-dir (depth GT .npy để đối chiếu), --no-eval, --step 45.
"""
import argparse
import csv
import glob
import os
import sys

import cv2
import numpy as np
import yaml

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "src", "perception"))
sys.path.insert(0, os.path.join(ROOT, "src", "object_db"))
from perception.core.geometry import intrinsics_from_hfov, optical_to_world  # noqa: E402
from perception.core.pipeline import process                                # noqa: E402
from object_db import association, db, queries                              # noqa: E402


def yaw_for_image(name, capture_yaws, fallback_deg):
    return capture_yaws.get(name, fallback_deg)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--images", default=None)
    p.add_argument("--db", required=True)
    p.add_argument("--cfg", default=os.path.join(ROOT, "config", "default.yaml"))
    p.add_argument("--classes", default=os.path.join(ROOT, "config", "classes.yaml"))
    p.add_argument("--gt", default=os.path.join(ROOT, "config", "gt_objects.yaml"))
    p.add_argument("--depth-dir", default=None, help="depth GT .npy (chỉ để đối chiếu)")
    p.add_argument("--depth-size", default=None)
    p.add_argument("--step", type=float, default=None, help="deg mỗi điểm dừng nếu thiếu metadata")
    p.add_argument("--device", default="cuda:0")
    p.add_argument("--max-images", type=int, default=0)
    p.add_argument("--no-eval", action="store_true")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--mock", action="store_true",
                   help="bỏ qua YOLOE/Metric3D; sinh quan sát trực tiếp từ GT (test pipeline DB+eval)")
    a = p.parse_args()

    cfg = yaml.safe_load(open(a.cfg))
    classes = yaml.safe_load(open(a.classes))["classes"]
    gt = yaml.safe_load(open(a.gt)).get("objects", []) if os.path.isfile(a.gt) else []
    cam = cfg["camera"]; base = tuple(cam["base_xyz"]); t_off = (cam.get("t_offset_m", 0.0), 0.0, 0.0)
    step = a.step if a.step is not None else cfg["scan"]["step_deg"]
    hw = tuple(int(x) for x in a.depth_size.lower().split("x")) if a.depth_size else tuple(cfg["depth"]["input_size"])

    if not a.mock:
        if not a.images:
            print("cần --images khi không dùng --mock"); return 1
        files = sorted(glob.glob(os.path.join(a.images, "stop*_f*.png")))
        if a.max_images:
            files = files[: a.max_images]
        if not files:
            print("Không thấy ảnh stop*_f*.png trong", a.images); return 1

        meta_path = os.path.join(a.images, "capture_metadata.csv")
        capture_yaws = {}
        if os.path.isfile(meta_path):
            with open(meta_path, newline="") as fh:
                for r in csv.DictReader(fh):
                    if r.get("image") and r.get("yaw_deg"):
                        capture_yaws[r["image"]] = float(r["yaw_deg"])

    scan_id = db.new_scan_id(a.seed)
    conn = db.open_db(a.db)
    db.create_scan(conn, scan_id, cfg, world_name="room",
                   notes="run_scan.py offline" + (" [mock]" if a.mock else ""), git_root=ROOT)
    if gt:
        db.load_gt_objects(conn, gt)

    K = intrinsics_from_hfov(cam["width"], cam["height"], cam["hfov_deg"])
    n_obs = 0

    if a.mock:
        # sinh quan sát trực tiếp từ GT: mỗi vật được "nhìn" ở nhiều điểm dừng
        # để test association + DB + eval mà không cần mô hình.
        rng = np.random.default_rng(a.seed)
        det = dep = None
        for g in gt:
            for stop in range(3):
                jx, jy = rng.normal(0, 0.02, 2)
                association.add_observation(conn, scan_id, {
                    "class_name": g["class_name"], "confidence": 0.85,
                    "bbox_xyxy": [0, 0, 10, 10], "truncated": False,
                    "depth_m": 1.5, "range_m": 2.0, "valid_depth_ratio": 0.9,
                    "p_cam": [0, 0, 1.5],
                    "p_world": [g["x"] + jx, g["y"] + jy, g["z"]],
                    "stop_index": stop, "frame_idx": 0,
                    "yaw_rad": float(np.radians(stop * step)), "stamp_ns": stop},
                    cfg["assoc"], cfg["fusion"])
                n_obs += 1
        print(f"[mock] sinh {n_obs} quan sát từ {len(gt)} vật GT")
    else:
        import torch
        from perception.core.yolo import YoloeDetector
        from perception.core.depth import Metric3DDepth
        wts = cfg["yoloe"]["model"]
        wts = wts if wts.endswith(".pt") else wts + ".pt"
        det = YoloeDetector(classes, wts, cfg["yoloe"]["conf"], cfg["yoloe"]["iou"], cfg["yoloe"]["imgsz"], a.device)
        dep = Metric3DDepth(a.device, hw, cfg["depth"]["fp16"], cfg["depth"]["canonical_focal"], cfg["depth"]["max_m"])

        for i, f in enumerate(files):
            bgr = cv2.imread(f)
            if bgr is None:
                print("bỏ qua (không đọc được)", f); continue
            rgb = bgr[..., ::-1].copy()
            depth_gt = None
            if a.depth_dir:
                npy = os.path.join(a.depth_dir, os.path.splitext(os.path.basename(f))[0] + ".npy")
                if os.path.isfile(npy):
                    depth_gt = np.load(npy)
            out = process(rgb, K, det, dep, cfg, depth_gt=depth_gt)
            name = os.path.basename(f)
            stem = os.path.splitext(name)[0]
            parts = stem.split("_")
            stop = int(parts[0].replace("stop", "")) if parts and parts[0].startswith("stop") else 0
            frame_idx = int(parts[1].replace("f", "")) if len(parts) > 1 else 0
            yaw_deg = yaw_for_image(name, capture_yaws, stop * step)
            for o in out["observations"]:
                pw = optical_to_world(o["p_cam"], np.radians(yaw_deg), base, t_off)
                obs = {k: v for k, v in o.items() if k != "mask"}
                obs["p_cam"] = [float(v) for v in o["p_cam"]]
                obs["p_world"] = [float(v) for v in pw]
                obs["stop_index"] = stop
                obs["frame_idx"] = frame_idx
                obs["yaw_rad"] = float(np.radians(yaw_deg))
                association.add_observation(conn, scan_id, obs, cfg["assoc"], cfg["fusion"])
                n_obs += 1
            print(f"[{i+1}/{len(files)}] {name}: {len(out['observations'])} obs "
                  f"({len(out['rejected'])} loại), yaw={yaw_deg:.0f}°")

    res = association.run_association_pass(conn, scan_id, cfg["assoc"])
    db.finish_scan(conn, scan_id)
    objs = queries.list_objects(conn, scan_id, None, "confirmed")
    print(f"\nscan_id={scan_id}")
    print(f"obs={n_obs}  objects confirmed={res['confirmed']}  rejected={res['rejected']}  "
          f"merged_pairs={len(res['merged_pairs'])}")
    print(f"DB: {a.db}  ({len(objs)} vật confirmed)")

    if not a.no_eval and gt:
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        from eval_scan import evaluate
        r = evaluate(a.db, gt, cfg["eval"]["match_radius_m"], scan_id)
        print(f"\n== Đánh giá vs GT (bán kính {cfg['eval']['match_radius_m']} m) ==")
        ff = lambda v: "n/a" if v is None else f"{v:.3f}"
        print(f"  recall={ff(r['recall'])}  precision={ff(r['precision'])}  "
              f"e_xy_med={ff(r['e_xy_median_m'])}m  dup={ff(r['dup_rate'])}  fp={ff(r['fp_rate'])}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
