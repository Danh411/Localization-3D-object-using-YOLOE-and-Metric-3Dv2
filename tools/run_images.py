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
from segmentation_gt import (
    decode_panoptic_labels,
    instance_segmentation_metrics,
    semantic_masks,
    segmentation_metrics,
    visible_instance_masks,
)

ap = argparse.ArgumentParser()
ap.add_argument("--images", default="data/w2_images"); ap.add_argument("--out", default="data/eval/w2_yoloe")
ap.add_argument("--cfg", default="config/default.yaml"); ap.add_argument("--classes", default="config/classes.yaml")
ap.add_argument("--gt", default="config/gt_objects.yaml"); ap.add_argument("--depth-size", default=None, help="HxW, mặc định theo cfg")
ap.add_argument("--depth-dir", default=None, help="Thư mục depth ground truth .npy, filenames must match RGB")
ap.add_argument("--panoptic-dir", default=None,
                help="Thư mục Gazebo panoptic label maps .npy đã đồng bộ với RGB")
ap.add_argument("--device", default="cuda:0"); ap.add_argument("--max-images", type=int, default=0)
a = ap.parse_args()
if a.panoptic_dir and not a.depth_dir:
    ap.error("--panoptic-dir requires --depth-dir so segmentation and depth use the same capture")
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
os.makedirs(os.path.join(a.out, "gt_masks"), exist_ok=True)
os.makedirs(os.path.join(a.out, "semantic_mask_compare_diagnostic"), exist_ok=True)
os.makedirs(os.path.join(a.out, "instance_mask_compare"), exist_ok=True)
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
    "panoptic_gt_dir": os.path.abspath(a.panoptic_dir) if a.panoptic_dir else None,
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
cm = cfg["camera"]
rows, rejected_rows, segmentation_rows, instance_segmentation_rows = [], [], [], []
per_class, timings, timing_rows = {c: [0, 0.0] for c in classes}, [], []
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
    if depth_gt is not None:
        if a.panoptic_dir:
            panoptic_path = os.path.join(a.panoptic_dir, stem + ".npy")
            if not os.path.isfile(panoptic_path):
                raise FileNotFoundError(f"Không tìm thấy Gazebo panoptic GT: {panoptic_path}")
            panoptic_map = np.load(panoptic_path)
            if panoptic_map.shape != (h, w, 3):
                raise ValueError(
                    f"Panoptic GT {panoptic_path} có shape {panoptic_map.shape}, "
                    f"mong đợi {(h, w, 3)}"
                )
            gt_semantic, instance_items = decode_panoptic_labels(panoptic_map, gt)
            instance_gt = dict(instance_items)
            gt_source = "gazebo_panoptic_camera"
        else:
            if any(obj.get("shape") == "mesh" for obj in gt):
                raise ValueError(
                    "Mesh-based GT requires Gazebo panoptic labels; pass --panoptic-dir "
                    "for captures made with the segmentation camera."
                )
            instance_gt = visible_instance_masks(
                depth_gt, (fx, fy, cx, cy), yaw, cm["base_xyz"], gt,
                t_offset_m=cm["t_offset_m"],
                visibility_tolerance_m=max(0.02, 4 * cm["noise_stddev"]),
                clip_near_m=cm["clip_near"], max_depth_m=cfg["depth"]["max_m"],
            )
            gt_semantic = semantic_masks(instance_gt, gt)
            gt_source = "geometry_depth_analytic"
        pred_semantic = {}
        predicted_instances = [
            observation for observation in out["observations"]
        ] + out["rejected"]
        for prediction in predicted_instances:
            class_name = prediction["class_name"]
            if class_name not in pred_semantic:
                pred_semantic[class_name] = np.zeros((h, w), dtype=bool)
            pred_semantic[class_name] |= prediction["mask"]
        segmentation_result = segmentation_metrics(pred_semantic, gt_semantic)
        predicted_masks = [prediction["mask"] for prediction in predicted_instances]
        ground_truth_instances = [
            mask for mask in instance_gt.values() if np.any(mask)
        ]
        instance_result = instance_segmentation_metrics(
            predicted_masks, ground_truth_instances
        )
        instance_segmentation_rows.append({
            "image": os.path.basename(f),
            "gt_source": gt_source,
            **{key: value for key, value in instance_result.items() if key != "matches"},
        })
        tp_pixels = np.zeros((h, w), dtype=bool)
        fp_pixels = np.zeros((h, w), dtype=bool)
        fn_pixels = np.zeros((h, w), dtype=bool)
        matched_predictions, matched_ground_truth = set(), set()
        for match in instance_result["matches"]:
            pred_index = match["predicted_index"]
            gt_index = match["ground_truth_index"]
            pred_mask = predicted_masks[pred_index]
            gt_mask = ground_truth_instances[gt_index]
            tp_pixels |= pred_mask & gt_mask
            fp_pixels |= pred_mask & ~gt_mask
            fn_pixels |= ~pred_mask & gt_mask
            matched_predictions.add(pred_index)
            matched_ground_truth.add(gt_index)
        for index, mask in enumerate(predicted_masks):
            if index not in matched_predictions:
                fp_pixels |= mask
        for index, mask in enumerate(ground_truth_instances):
            if index not in matched_ground_truth:
                fn_pixels |= mask
        instance_comparison = np.zeros((h, w, 3), dtype=np.uint8)
        instance_comparison[tp_pixels] = (0, 200, 0)
        instance_comparison[fp_pixels] = (0, 0, 255)
        instance_comparison[fn_pixels] = (255, 0, 0)
        instance_overlay = (0.55 * bgr + 0.45 * instance_comparison).astype(np.uint8)
        cv2.imwrite(os.path.join(a.out, "instance_mask_compare", stem + ".png"),
                    instance_overlay)
        mask_path = os.path.join(a.out, "gt_masks", stem + ".npz")
        np.savez_compressed(mask_path, **instance_gt)
        for class_name, metrics in segmentation_result["per_class"].items():
            segmentation_rows.append({
                "image": os.path.basename(f),
                "class": class_name,
                "gt_source": gt_source,
                **metrics,
            })
        tp_pixels = np.zeros((h, w), dtype=bool)
        fp_pixels = np.zeros((h, w), dtype=bool)
        fn_pixels = np.zeros((h, w), dtype=bool)
        for class_name in set(pred_semantic) | set(gt_semantic):
            pred_mask = pred_semantic.get(class_name, np.zeros((h, w), dtype=bool))
            gt_mask = gt_semantic.get(class_name, np.zeros((h, w), dtype=bool))
            tp_pixels |= pred_mask & gt_mask
            fp_pixels |= pred_mask & ~gt_mask
            fn_pixels |= ~pred_mask & gt_mask
        comparison = np.zeros((h, w, 3), dtype=np.uint8)
        comparison[tp_pixels] = (0, 200, 0)
        comparison[fp_pixels] = (0, 0, 255)
        comparison[fn_pixels] = (255, 0, 0)
        comparison_overlay = (0.55 * bgr + 0.45 * comparison).astype(np.uint8)
        cv2.imwrite(
            os.path.join(a.out, "semantic_mask_compare_diagnostic", stem + ".png"),
            comparison_overlay,
        )
    if fi >= 1: timings.append(out["timings_ms"])        # bỏ ảnh đầu (khởi động)
    timing_rows.append({"image": os.path.basename(f), "depth_input_hw": f"{hw[0]}x{hw[1]}",
                        **out["timings_ms"]})
    vis = bgr.copy()
    for o in out["observations"]:
        mask = o["mask"]
        vis[mask] = (0.55 * vis[mask] + 0.45 * np.array([0, 255, 0])).astype(np.uint8)
        pw = optical_to_world(o["p_cam"], yaw, cm["base_xyz"], (cm["t_offset_m"], 0, 0))
        p_gt_world = (
            optical_to_world(o["p_gt_cam_at_uv"], yaw, cm["base_xyz"], (cm["t_offset_m"], 0, 0))
            if o.get("p_gt_cam_at_uv") is not None else None
        )
        surface_xy_error = (
            math.hypot(pw[0] - p_gt_world[0], pw[1] - p_gt_world[1])
            if p_gt_world is not None else None
        )
        surface_xyz_error = (
            float(np.linalg.norm(pw - p_gt_world)) if p_gt_world is not None else None
        )
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
                     "depth_m": round(o["depth_m"], 3), "range_m": round(o["range_m"], 3),
                     "u": round(o["u"], 2), "v": round(o["v"], 2), "truncated": int(o["truncated"]),
                     "gt_model_name": closest_gt["model_name"] if closest_gt else "",
                     "depth_gt_m": "" if depth_gt_m is None else round(depth_gt_m, 4),
                     "depth_gt_at_uv_m": "" if o.get("depth_gt_at_uv_m") is None else round(o["depth_gt_at_uv_m"], 4),
                     "depth_abs_error_m": "" if abs_error is None else round(abs_error, 4),
                     "depth_abs_rel": "" if abs_rel is None else round(abs_rel, 4),
                     "e_xy_to_gt_surface_at_uv": "" if surface_xy_error is None else round(surface_xy_error, 4),
                     "e_xyz_to_gt_surface_at_uv": "" if surface_xyz_error is None else round(surface_xyz_error, 4),
                     "depth_gt_object_center_z_m": "" if center_depth_gt is None else round(center_depth_gt, 4),
                     "depth_center_abs_error_m": "" if center_abs_error is None else round(center_abs_error, 4),
                     "depth_center_abs_rel": "" if center_abs_rel is None else round(center_abs_rel, 4),
                     "valid_ratio": round(o["valid_depth_ratio"], 3), "world_x": round(pw[0], 3), "world_y": round(pw[1], 3),
                     "world_z": round(pw[2], 3), "e_xy_to_nearest_gt": None if e is None else round(e, 3)})
        per_class[o["class_name"]][0] += 1; per_class[o["class_name"]][1] += o["confidence"]
        x1, y1, x2, y2 = [int(v) for v in o["bbox_xyxy"]]
        cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(vis, f"{o['class_name']} {o['confidence']:.2f} Z={o['depth_m']:.2f}m", (x1, max(y1 - 6, 14)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    for rejected in out["rejected"]:
        mask = rejected["mask"]
        vis[mask] = (0.55 * vis[mask] + 0.45 * np.array([0, 0, 255])).astype(np.uint8)
        x1, y1, x2, y2 = [int(v) for v in rejected["bbox_xyxy"]]
        rejected_rows.append({
            "image": os.path.basename(f),
            "class": rejected["class_name"],
            "conf": round(rejected["confidence"], 3),
            "reason": rejected["reason"],
            "truncated": int(rejected["truncated"]),
            "mask_area_px": rejected["mask_area_px"],
            "valid_ratio": round(rejected["valid_depth_ratio"], 3),
        })
        cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 0, 255), 2)
        cv2.putText(vis, f"{rejected['class_name']} REJECTED: {rejected['reason']}",
                    (x1, max(y1 - 6, 14)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    cv2.imwrite(os.path.join(a.out, "annot", os.path.basename(f)), vis)
    print(f"[{fi+1}/{len(files)}] {os.path.basename(f)}: {len(out['observations'])} vat, bi loai {len(out['rejected'])}, {out['timings_ms']}")
cols = list(rows[0].keys()) if rows else ["image"]
with open(os.path.join(a.out, "detections.csv"), "w", newline="") as fh:
    wr = csv.DictWriter(fh, fieldnames=cols); wr.writeheader(); wr.writerows(rows)
rejected_cols = ["image", "class", "conf", "reason", "truncated", "mask_area_px", "valid_ratio"]
with open(os.path.join(a.out, "rejected.csv"), "w", newline="") as fh:
    wr = csv.DictWriter(fh, fieldnames=rejected_cols); wr.writeheader(); wr.writerows(rejected_rows)
segmentation_columns = [
    "image", "class", "iou", "precision", "recall", "tp_px", "fp_px", "fn_px",
    "predicted_px", "ground_truth_px", "gt_source",
]
with open(os.path.join(a.out, "segmentation_metrics.csv"), "w", newline="") as fh:
    wr = csv.DictWriter(fh, fieldnames=segmentation_columns)
    wr.writeheader()
    wr.writerows(segmentation_rows)
instance_columns = [
    "image", "predicted_instances", "ground_truth_instances", "true_positives",
    "false_positives", "false_negatives", "precision", "recall", "mean_matched_iou",
    "gt_source",
]
with open(os.path.join(a.out, "instance_segmentation_metrics.csv"), "w", newline="") as fh:
    wr = csv.DictWriter(fh, fieldnames=instance_columns)
    wr.writeheader()
    wr.writerows(instance_segmentation_rows)
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
