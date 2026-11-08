#!/usr/bin/env python3
"""W2-B1: chạy YOLOE + Metric3D trên ảnh mô phỏng (data/w2_images/stop<k>_f<j>.png), ghi bảng và ảnh minh hoạ.
Tính p_world bằng công thức mục 5.4 (yaw = k*step) để so sơ bộ với GT cùng lớp gần nhất (kiểm tra chéo, chưa phải đánh giá chính thức).
  python3 tools/run_images.py [--images data/w2_images] [--out data/eval/w2_yoloe] [--depth-size 616x1064]"""
import argparse, csv, json, math, os, re, sys, glob
import cv2, numpy as np, yaml
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "src", "perception"))
from perception.core.geometry import intrinsics_from_hfov, optical_to_world, world_to_optical
from perception.core.pipeline import process

ap = argparse.ArgumentParser()
ap.add_argument("--images", default="data/w2_images"); ap.add_argument("--out", default="data/eval/w2_yoloe")
ap.add_argument("--cfg", default="config/default.yaml"); ap.add_argument("--classes", default="config/classes.yaml")
ap.add_argument("--gt", default="config/gt_objects.yaml"); ap.add_argument("--depth-size", default=None, help="HxW, mặc định theo cfg")
ap.add_argument("--depth-dir", default=None, help="Thư mục depth ground truth .npy, filenames must match RGB")
ap.add_argument("--device", default="cuda:0"); ap.add_argument("--max-images", type=int, default=0)
a = ap.parse_args()
cfg = yaml.safe_load(open(a.cfg)); classes = yaml.safe_load(open(a.classes))["classes"]
gt = yaml.safe_load(open(a.gt))["objects"]
hw = tuple(int(x) for x in a.depth_size.lower().split("x")) if a.depth_size else tuple(cfg["depth"]["input_size"])
import torch
from perception.core.yolo import YoloeDetector
from perception.core.depth import Metric3DDepth
wts = cfg["yoloe"]["model"]; wts = wts if wts.endswith(".pt") else wts + ".pt"
det = YoloeDetector(classes, wts, cfg["yoloe"]["conf"], cfg["yoloe"]["iou"], cfg["yoloe"]["imgsz"], a.device)
dep = Metric3DDepth(a.device, hw, cfg["depth"]["fp16"], cfg["depth"]["canonical_focal"], cfg["depth"]["max_m"])
os.makedirs(os.path.join(a.out, "annot"), exist_ok=True)
files = sorted(glob.glob(os.path.join(a.images, "stop*_f*.png")))
if a.max_images: files = files[:a.max_images]
capture_metadata_path = os.path.join(a.images, "capture_metadata.csv")
capture_yaws = {}
if os.path.isfile(capture_metadata_path):
    with open(capture_metadata_path, newline="") as fh:
        capture_yaws = {row["image"]: float(row["yaw_deg"])
                        for row in csv.DictReader(fh) if row.get("image") and row.get("yaw_deg")}
run_metadata = {
    "images_dir": os.path.abspath(a.images),
    "depth_gt_dir": os.path.abspath(a.depth_dir) if a.depth_dir else None,
    "object_pose_gt_file": os.path.abspath(a.gt),
    "capture_yaw_source": "capture_metadata.csv" if capture_yaws else "configured scan step",
    "image_count": len(files),
    "depth_input_hw": list(hw),
    "camera_hfov_deg": cfg["camera"]["hfov_deg"],
    "depth_fp16_configured": bool(cfg["depth"]["fp16"]),
    "depth_fp16_effective": bool(cfg["depth"]["fp16"] and a.device.startswith("cuda")),
    "device": a.device,
    "torch_version": torch.__version__,
    "cuda_available": torch.cuda.is_available(),
    "yolo_weights": wts,
    "yolo_conf": cfg["yoloe"]["conf"],
    "yolo_imgsz": cfg["yoloe"]["imgsz"],
}
with open(os.path.join(a.out, "run_metadata.json"), "w") as fh:
    json.dump(run_metadata, fh, indent=2)
cm = cfg["camera"]; rows, per_class, timings, timing_rows = [], {c: [0, 0.0] for c in classes}, [], []
for fi, f in enumerate(files):
    bgr = cv2.imread(f); rgb = bgr[..., ::-1].copy(); h, w = rgb.shape[:2]
    k = int(re.search(r"stop(\d+)_", f).group(1))
    stem = os.path.splitext(os.path.basename(f))[0]
    yaw_deg = capture_yaws.get(stem, k * cfg["scan"]["step_deg"] + cfg["scan"].get("yaw_start_deg", 0))
    yaw = math.radians(yaw_deg)
    fx, fy, cx, cy = intrinsics_from_hfov(w, h, cm["hfov_deg"])
    depth_gt = None
    if a.depth_dir:
        gt_path = os.path.join(a.depth_dir, os.path.splitext(os.path.basename(f))[0] + ".npy")
        if not os.path.isfile(gt_path):
            raise FileNotFoundError(f"Không tìm thấy depth GT cho {f}: {gt_path}")
        depth_gt = np.load(gt_path)
        if depth_gt.shape != (h, w):
            raise ValueError(f"Depth GT {gt_path} có shape {depth_gt.shape}, mong đợi {(h, w)}")
    out = process(rgb, (fx, fy, cx, cy), det, dep, cfg, depth_gt=depth_gt)
    if fi >= 1: timings.append(out["timings_ms"])        # bỏ ảnh đầu (khởi động)
    timing_rows.append({"image": os.path.basename(f), "depth_input_hw": f"{hw[0]}x{hw[1]}",
                        **out["timings_ms"]})
    vis = bgr.copy()
    for o in out["observations"]:
        pw = optical_to_world(o["p_cam"], yaw, cm["base_xyz"], (cm["t_offset_m"], 0, 0))
        same = [g for g in gt if g["class_name"] == o["class_name"]]
        closest_gt = min(same, key=lambda g: math.hypot(pw[0] - g["x"], pw[1] - g["y"]), default=None)
        e = math.hypot(pw[0] - closest_gt["x"], pw[1] - closest_gt["y"]) if closest_gt else None
        center_depth_gt = None
        if closest_gt:
            center_cam = world_to_optical(
                (closest_gt["x"], closest_gt["y"], closest_gt["z"]), yaw, cm["base_xyz"],
                (cm["t_offset_m"], 0, 0))
            center_depth_gt = float(center_cam[2]) if center_cam[2] > 0 else None
        depth_gt_m = o.get("depth_gt_m")
        abs_error = abs(o["depth_m"] - depth_gt_m) if depth_gt_m is not None else None
        abs_rel = abs_error / depth_gt_m if depth_gt_m is not None and depth_gt_m > 0 else None
        center_abs_error = (abs(o["depth_m"] - center_depth_gt)
                            if center_depth_gt is not None else None)
        center_abs_rel = (center_abs_error / center_depth_gt
                          if center_abs_error is not None and center_depth_gt > 0 else None)
        rows.append({"image": os.path.basename(f), "stop": k, "class": o["class_name"], "conf": round(o["confidence"], 3),
                     "depth_m": round(o["depth_m"], 3), "range_m": round(o["range_m"], 3), "truncated": int(o["truncated"]),
                     "gt_model_name": closest_gt["model_name"] if closest_gt else "",
                     "depth_gt_m": "" if depth_gt_m is None else round(depth_gt_m, 4),
                     "depth_abs_error_m": "" if abs_error is None else round(abs_error, 4),
                     "depth_abs_rel": "" if abs_rel is None else round(abs_rel, 4),
                     "depth_gt_object_center_z_m": "" if center_depth_gt is None else round(center_depth_gt, 4),
                     "depth_center_abs_error_m": "" if center_abs_error is None else round(center_abs_error, 4),
                     "depth_center_abs_rel": "" if center_abs_rel is None else round(center_abs_rel, 4),
                     "valid_ratio": round(o["valid_depth_ratio"], 3), "world_x": round(pw[0], 3), "world_y": round(pw[1], 3),
                     "world_z": round(pw[2], 3), "e_xy_to_nearest_gt": None if e is None else round(e, 3)})
        per_class[o["class_name"]][0] += 1; per_class[o["class_name"]][1] += o["confidence"]
        x1, y1, x2, y2 = [int(v) for v in o["bbox_xyxy"]]
        cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(vis, f"{o['class_name']} {o['confidence']:.2f} Z={o['depth_m']:.2f}m", (x1, max(y1 - 6, 14)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    cv2.imwrite(os.path.join(a.out, "annot", os.path.basename(f)), vis)
    print(f"[{fi+1}/{len(files)}] {os.path.basename(f)}: {len(out['observations'])} vat, bi loai {len(out['rejected'])}, {out['timings_ms']}")
cols = list(rows[0].keys()) if rows else ["image"]
with open(os.path.join(a.out, "detections.csv"), "w", newline="") as fh:
    wr = csv.DictWriter(fh, fieldnames=cols); wr.writeheader(); wr.writerows(rows)
with open(os.path.join(a.out, "timings.csv"), "w", newline="") as fh:
    cols = ["image", "depth_input_hw", "yolo_ms", "depth_ms", "post_ms"]
    wr = csv.DictWriter(fh, fieldnames=cols); wr.writeheader(); wr.writerows(timing_rows)
with open(os.path.join(a.out, "per_class.csv"), "w", newline="") as fh:
    wr = csv.writer(fh); wr.writerow(["class", "detections", "mean_conf", "in_gt"])
    for c, (n, s) in per_class.items(): wr.writerow([c, n, round(s / n, 3) if n else "", int(any(g["class_name"] == c for g in gt))])
print(f"\n== Số lần phát hiện theo lớp ({len(files)} ảnh) =="); [print(f"  {c:13s} {n:3d}  conf TB {s/n:.2f}" if n else f"  {c:13s}   0  (KHÔNG PHÁT HIỆN)") for c, (n, s) in per_class.items()]
if timings:
    for k_ in ("yolo_ms", "depth_ms", "post_ms"):
        v = [t[k_] for t in timings]; print(f"  {k_}: p50 {np.percentile(v,50):.0f}  p95 {np.percentile(v,95):.0f} ms")
if torch.cuda.is_available(): print(f"  VRAM đỉnh (PyTorch): {torch.cuda.max_memory_allocated()/2**20:.0f} MiB   depth input {hw}")
print("Kết quả ở", a.out)
