#!/usr/bin/env python3
"""Capture a 360-degree still-image scan, run perception, and summarize accuracy.

Each captured image is evaluated independently. No temporal tracking or fusion is
performed; repeated views of one object remain separate observations.
"""
import argparse
import csv
from datetime import datetime
import json
import math
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]


def depth_metrics(rows):
    values = []
    for row in rows:
        if not row.get("depth_gt_m") or not row.get("depth_m"):
            continue
        gt, pred = float(row["depth_gt_m"]), float(row["depth_m"])
        if gt > 0:
            values.append((row["class"], gt, pred))
    if not values:
        return {"observations": 0, "mae_m": None, "rmse_m": None,
                "abs_rel": None, "bias_m": None}

    errors = [pred - gt for _, gt, pred in values]
    return {
        "observations": len(values),
        "mae_m": sum(abs(error) for error in errors) / len(errors),
        "rmse_m": math.sqrt(sum(error * error for error in errors) / len(errors)),
        "abs_rel": sum(abs(pred - gt) / gt for _, gt, pred in values) / len(values),
        "bias_m": sum(errors) / len(errors),
    }


def error_metrics(values):
    ordered = sorted(values)
    if not ordered:
        return {"observations": 0, "mean_m": None, "median_m": None, "p95_m": None}
    p95_index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return {
        "observations": len(ordered),
        "mean_m": statistics.mean(ordered),
        "median_m": statistics.median(ordered),
        "p95_m": ordered[p95_index],
    }


def aggregate_segmentation(segmentation_rows):
    class_totals = {}
    for row in segmentation_rows:
        totals = class_totals.setdefault(
            row["class"], {"tp_px": 0, "fp_px": 0, "fn_px": 0}
        )
        for key in ("tp_px", "fp_px", "fn_px"):
            totals[key] += int(row[key])
    per_class = {}
    for class_name, totals in class_totals.items():
        tp, fp, fn = totals["tp_px"], totals["fp_px"], totals["fn_px"]
        union = tp + fp + fn
        per_class[class_name] = {
            **totals,
            "iou": tp / union if union else None,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "predicted_px": tp + fp,
            "ground_truth_px": tp + fn,
        }
    all_ious = [v["iou"] for v in per_class.values() if v["iou"] is not None]
    gt_ious = [
        v["iou"] for v in per_class.values()
        if v["ground_truth_px"] > 0 and v["iou"] is not None
    ]
    tp = sum(v["tp_px"] for v in per_class.values())
    fp = sum(v["fp_px"] for v in per_class.values())
    fn = sum(v["fn_px"] for v in per_class.values())
    return {
        "evaluated_images": len({row["image"] for row in segmentation_rows}),
        "gt_source": (
            (segmentation_rows[0].get("gt_source") or "geometry_depth_analytic")
            if segmentation_rows else "not_evaluated"
        ),
        "per_class": per_class,
        "mean_iou": statistics.mean(all_ious) if all_ious else None,
        "mean_iou_present_gt": statistics.mean(gt_ious) if gt_ious else None,
        "micro_precision": tp / (tp + fp) if tp + fp else None,
        "micro_recall": tp / (tp + fn) if tp + fn else None,
        "micro_iou": tp / (tp + fp + fn) if tp + fp + fn else None,
    }


def aggregate_instance_segmentation(instance_rows):
    totals = {
        "predicted_instances": 0,
        "ground_truth_instances": 0,
        "true_positives": 0,
        "false_positives": 0,
        "false_negatives": 0,
    }
    matched_iou_sum = 0.0
    for row in instance_rows:
        for key in totals:
            totals[key] += int(row[key])
        if row.get("mean_matched_iou") not in (None, ""):
            matched_iou_sum += (
                float(row["mean_matched_iou"]) * int(row["true_positives"])
            )
    tp = totals["true_positives"]
    predicted = totals["predicted_instances"]
    ground_truth = totals["ground_truth_instances"]
    return {
        "evaluated_images": len({row["image"] for row in instance_rows}),
        "gt_source": instance_rows[0].get("gt_source") if instance_rows else None,
        "iou_threshold": 0.5,
        **totals,
        "precision": tp / predicted if predicted else None,
        "recall": tp / ground_truth if ground_truth else None,
        "mean_matched_iou": matched_iou_sum / tp if tp else None,
    }


def build_summary(
    rows, image_count, rejected_rows=None, segmentation_rows=None,
    instance_segmentation_rows=None,
):
    rejected_rows = rejected_rows or []
    segmentation_rows = segmentation_rows or []
    instance_segmentation_rows = instance_segmentation_rows or []
    classes = sorted({
        row["class"] for row in rows + rejected_rows if row.get("class")
    })
    valid_depth_rows = [
        row for row in rows
        if row.get("depth_gt_m") and row.get("depth_m") and float(row["depth_gt_m"]) > 0
    ]
    range_groups = {
        "near_lt_1_5m": [row for row in valid_depth_rows if float(row.get("range_m") or 0) < 1.5],
        "mid_1_5_to_2_5m": [
            row for row in valid_depth_rows if 1.5 <= float(row.get("range_m") or 0) < 2.5
        ],
        "far_gte_2_5m": [row for row in valid_depth_rows if float(row.get("range_m") or 0) >= 2.5],
    }
    surface_xy_errors = [
        float(row["e_xy_to_gt_surface_at_uv"])
        for row in rows if row.get("e_xy_to_gt_surface_at_uv") not in (None, "")
    ]
    surface_xyz_errors = [
        float(row["e_xyz_to_gt_surface_at_uv"])
        for row in rows if row.get("e_xyz_to_gt_surface_at_uv") not in (None, "")
    ]
    object_center_xy_errors = [
        float(row["e_xy_to_nearest_gt"])
        for row in rows if row.get("e_xy_to_nearest_gt") not in (None, "")
    ]

    all_depth = depth_metrics(valid_depth_rows)
    diagnostics = []
    if all_depth["observations"] >= 3 and abs(all_depth["bias_m"]) >= 0.1:
        direction = "overestimates" if all_depth["bias_m"] > 0 else "underestimates"
        diagnostics.append(
            f"Depth has a systematic signed bias ({all_depth['bias_m']:+.3f} m; "
            f"predictions {direction} the Gazebo visible-surface reference)."
        )
    for class_name in classes:
        class_metrics = depth_metrics([
            row for row in valid_depth_rows if row.get("class") == class_name
        ])
        if class_metrics["observations"] >= 3 and abs(class_metrics["bias_m"]) >= 0.1:
            direction = "overestimates" if class_metrics["bias_m"] > 0 else "underestimates"
            diagnostics.append(
                f"{class_name} has a class-specific depth bias "
                f"({class_metrics['bias_m']:+.3f} m; {direction}); inspect its mask and "
                "surface-depth samples before applying any global scale correction."
            )
    populated_ranges = sum(
        result["observations"] > 0
        for result in (depth_metrics(group_rows) for group_rows in range_groups.values())
    )
    if all_depth["observations"] and populated_ranges < 2:
        diagnostics.append(
            "The detections cover fewer than two configured range bands; this scan cannot "
            "establish whether depth error changes with range."
        )
    surface_xy_metrics = error_metrics(surface_xy_errors)
    surface_xyz_metrics = error_metrics(surface_xyz_errors)
    object_center_xy_metrics = error_metrics(object_center_xy_errors)
    if surface_xy_metrics["observations"] and surface_xy_metrics["median_m"] >= 0.1:
        diagnostics.append(
            "The same-pixel lateral 3D error is substantial; off-axis pixels convert depth "
            "error into lateral displacement, so inspect signed depth error and pixel location "
            "before attributing it to TF or camera intrinsics."
        )
    if any(row.get("truncated") in (1, "1", True) for row in valid_depth_rows):
        diagnostics.append(
            "Some evaluated detections are truncated at an image border; compare their errors "
            "separately before tuning the depth model."
        )
    if not valid_depth_rows:
        diagnostics.append(
            "No detections have aligned Gazebo depth; verify RGB/depth capture and file pairing."
        )
    if rejected_rows:
        rejected_reasons = {}
        for row in rejected_rows:
            reason = row.get("reason", "unknown")
            rejected_reasons[reason] = rejected_reasons.get(reason, 0) + 1
        diagnostics.append(
            "Some YOLOE detections were rejected by depth fusion: " +
            ", ".join(f"{reason}={count}" for reason, count in sorted(rejected_reasons.items())) +
            "; inspect their red masks in annotated images and rejected.csv."
        )
    else:
        rejected_reasons = {}
    segmentation = aggregate_segmentation(segmentation_rows)
    instance_segmentation = aggregate_instance_segmentation(instance_segmentation_rows)
    has_panoptic_gt = segmentation["gt_source"] == "gazebo_panoptic_camera"
    if segmentation_rows and not has_panoptic_gt:
        diagnostics.append(
            "Class-labelled mask IoU is diagnostic only: scene labels come from configured "
            "object names and do not establish that the simple Gazebo geometry looks like "
            "the named real-world object."
        )

    return {
        "image_count": image_count,
        "detection_count": len(rows),
        "rejected_detection_count": len(rejected_rows),
        "rejections_by_reason": rejected_reasons,
        "depth_reference": "median Gazebo depth inside each detected object's eroded mask",
        "segmentation_ground_truth": bool(segmentation_rows),
        "temporal_fusion": False,
        "all_detections": all_depth,
        "by_class": {
            class_name: {
                "detections": sum(row.get("class") == class_name for row in rows),
                "mean_confidence": (
                    statistics.mean(float(row["conf"]) for row in rows
                                    if row.get("class") == class_name and row.get("conf"))
                    if any(row.get("class") == class_name and row.get("conf") for row in rows)
                    else None
                ),
                "truncated_detections": sum(
                    row.get("class") == class_name and row.get("truncated") in (1, "1", True)
                    for row in rows
                ),
                "rejected_detections": sum(
                    row.get("class") == class_name for row in rejected_rows
                ),
                **depth_metrics([
                    row for row in valid_depth_rows if row.get("class") == class_name
                ]),
            }
            for class_name in classes
        },
        "depth_by_range": {
            name: depth_metrics(group_rows) for name, group_rows in range_groups.items()
        },
        "world_surface_xy_error": surface_xy_metrics,
        "world_surface_xyz_error": surface_xyz_metrics,
        "object_center_xy_diagnostic": object_center_xy_metrics,
        "segmentation": segmentation,
        "instance_segmentation": instance_segmentation,
        "diagnostic_signals": diagnostics,
        "interpretation": (
            "Depth metrics cover detections with valid aligned Gazebo depth only. "
            + (
                "Primary segmentation metrics compare predicted masks with class and instance "
                "labels rendered by Gazebo's panoptic camera for the selected Fuel models. "
                if has_panoptic_gt else
                "Primary segmentation metrics match masks to visible geometry instances; they "
                "measure geometric overlap, not real-object recognition. Analytic box/cylinder "
                "GT is filtered by aligned Gazebo depth. "
            )
            + "Same-pixel surface position error compares the estimated 3D point with Gazebo depth "
            "sampled at the predicted mask centroid. Object-center XY error is separate because a "
            "visible surface point need not be the geometric center. Repeated views are independent "
            "observations."
        ),
    }


def write_markdown_report(path, summary):
    overall = summary["all_detections"]
    segmentation = summary["segmentation"]
    instance_segmentation = summary["instance_segmentation"]
    semantic_benchmark = segmentation["gt_source"] == "gazebo_panoptic_camera"
    fmt = lambda value: "n/a" if value is None else f"{value:.3f}"
    semantic_heading = (
        "## Semantic mask comparison against Gazebo panoptic GT"
        if semantic_benchmark else
        "## Class-labelled mask diagnostic (not a semantic benchmark)"
    )
    semantic_note = (
        "GT comes from Gazebo's panoptic sensor and explicit class labels applied to the "
        "selected realistic Fuel models."
        if semantic_benchmark else
        "The configured labels (for example `cup` or `laptop`) are not validated against the "
        "appearance of these simple Gazebo shapes. This section is diagnostic only, not a "
        "semantic benchmark. GT masks come from analytic box/cylinder geometry filtered by "
        "aligned depth, not Gazebo-renderer segmentation output."
    )
    instance_heading = (
        "## Class-agnostic instance-mask overlap against Gazebo panoptic GT"
        if semantic_benchmark else
        "## Class-agnostic instance-mask overlap against geometry/depth GT"
    )
    instance_note = (
        "Predicted masks are matched one-to-one with Gazebo's rendered instance labels, without "
        "requiring their predicted class to agree."
        if semantic_benchmark else
        "These scores ignore the predicted class label. They assess overlap with visible configured "
        "geometry masks only, not whether YOLOE recognized a real-world object."
    )
    lines = [
        "# Static scan accuracy report",
        "",
        f"- Captured images: {summary['image_count']}",
        f"- Detections: {summary['detection_count']}",
        f"- Detections rejected by depth fusion: {summary['rejected_detection_count']}",
        f"- Temporal fusion/tracking: {'enabled' if summary['temporal_fusion'] else 'not used'}",
        f"- Segmentation GT evaluated on {segmentation['evaluated_images']} images.",
        f"- Segmentation GT source: {segmentation['gt_source']}.",
        "",
        "## Depth against aligned Gazebo visible-surface depth",
        "",
        f"Valid observations: {overall['observations']}",
        f"MAE: {overall['mae_m'] if overall['mae_m'] is not None else 'n/a'} m",
        f"RMSE: {overall['rmse_m'] if overall['rmse_m'] is not None else 'n/a'} m",
        f"AbsRel: {overall['abs_rel'] if overall['abs_rel'] is not None else 'n/a'}",
        f"Bias: {overall['bias_m'] if overall['bias_m'] is not None else 'n/a'} m",
        "",
        instance_heading,
        "",
        f"Evaluated images: {instance_segmentation['evaluated_images']}",
        f"Ground-truth instance observations across images: "
        f"{instance_segmentation['ground_truth_instances']}",
        f"Predicted mask observations across images: "
        f"{instance_segmentation['predicted_instances']}",
        f"Matched instances (IoU >= {instance_segmentation['iou_threshold']:.1f}): "
        f"{instance_segmentation['true_positives']}",
        f"Instance precision / recall: "
        f"{fmt(instance_segmentation['precision'])} / {fmt(instance_segmentation['recall'])}",
        f"Mean IoU among matched instances: "
        f"{fmt(instance_segmentation['mean_matched_iou'])}",
        "",
        instance_note,
        "",
        semantic_heading,
        "",
        f"Macro IoU: {fmt(segmentation['mean_iou'])}; "
        f"pixel precision / recall / IoU: "
        f"{fmt(segmentation['micro_precision'])} / "
        f"{fmt(segmentation['micro_recall'])} / {fmt(segmentation['micro_iou'])}.",
        "",
        (
            "| Ground-truth class | IoU | Precision | Recall | GT pixels | Predicted pixels |"
            if semantic_benchmark else
            "| Configured class name | IoU | Precision | Recall | GT pixels | Predicted pixels |"
        ),
        "|---|---:|---:|---:|---:|---:|",
    ]
    for class_name, result in segmentation["per_class"].items():
        lines.append(
            f"| {class_name} | {fmt(result['iou'])} | {fmt(result['precision'])} | "
            f"{fmt(result['recall'])} | {result['ground_truth_px']} | {result['predicted_px']} |"
        )
    lines.extend([
        "",
        semantic_note,
        "",
        "## Depth by predicted class label (diagnostic grouping)",
        "",
        "| Predicted label | Detections | Rejected | Depth observations | MAE (m) | Bias (m) | Mean confidence | Truncated |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for class_name, result in summary["by_class"].items():
        mae = "n/a" if result["mae_m"] is None else f"{result['mae_m']:.3f}"
        bias = "n/a" if result["bias_m"] is None else f"{result['bias_m']:+.3f}"
        confidence = (
            "n/a" if result["mean_confidence"] is None
            else f"{result['mean_confidence']:.3f}"
        )
        lines.append(
            f"| {class_name} | {result['detections']} | {result['rejected_detections']} | "
            f"{result['observations']} | "
            f"{mae} | {bias} | {confidence} | {result['truncated_detections']} |"
        )
    lines.extend(["", "## Depth error by range", "", "| Range | Observations | MAE (m) | Bias (m) |", "|---|---:|---:|---:|"])
    for range_name, result in summary["depth_by_range"].items():
        mae = "n/a" if result["mae_m"] is None else f"{result['mae_m']:.3f}"
        bias = "n/a" if result["bias_m"] is None else f"{result['bias_m']:+.3f}"
        lines.append(f"| {range_name} | {result['observations']} | {mae} | {bias} |")
    surface_xy = summary["world_surface_xy_error"]
    surface_xyz = summary["world_surface_xyz_error"]
    center_xy = summary["object_center_xy_diagnostic"]
    def _fmt(v):
        return "n/a" if v is None else f"{v:.3f} m"
    lines.extend([
        "",
        "## Same-pixel 3D point comparison",
        "",
        f"XY error: {surface_xy['observations']} observations; median "
        f"{_fmt(surface_xy['median_m'])}; "
        f"p95 {_fmt(surface_xy['p95_m'])}.",
        f"3D error median: {_fmt(surface_xyz['median_m'])}.",
        f"XY error to nearest same-class object center (not the same reference): median "
        f"{_fmt(center_xy['median_m'])}.",
        "",
        "## Signals to investigate",
        "",
    ])
    if summary["diagnostic_signals"]:
        lines.extend(f"- {signal}" for signal in summary["diagnostic_signals"])
    else:
        lines.append("- No automatic diagnostic signal met its threshold.")
    lines.extend(["", summary["interpretation"], ""])
    path.write_text("\n".join(lines))


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=f"data/eval/scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        help="New output directory for captured images, inference results, and summary",
    )
    parser.add_argument("--step", type=float, help="Pan angle step; defaults to config scan.step_deg")
    parser.add_argument("--frames", type=int, help="Still images per stop; defaults to config")
    parser.add_argument("--settle", type=float, help="Seconds to settle; defaults to config")
    parser.add_argument("--sync-tolerance-ms", type=float, default=50.0)
    parser.add_argument(
        "--depth-size", default="616x1064",
        help="Metric3D input HxW; default favors accuracy over inference speed",
    )
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--images", help="Reuse an existing directory of captured still PNGs")
    parser.add_argument("--depth-dir", help="Aligned Gazebo depth .npy directory for --images")
    parser.add_argument("--segmentation-gt", action="store_true",
                        help="Capture synchronized Gazebo panoptic labels during a live scan")
    parser.add_argument("--segmentation-dir",
                        help="Gazebo panoptic label-map .npy directory for replay")
    parser.add_argument("--cfg", default="config/default.yaml", help="Inference YAML configuration")
    args = parser.parse_args()

    with open(args.cfg) as fh:
        cfg = yaml.safe_load(fh)
    args.step = cfg["scan"]["step_deg"] if args.step is None else args.step
    args.frames = cfg["scan"]["frames_per_stop"] if args.frames is None else args.frames
    args.settle = cfg["scan"]["settle_time_s"] if args.settle is None else args.settle

    if not 0 < args.step <= 360:
        parser.error("--step must be greater than 0 and no more than 360 degrees")
    if args.frames < 1:
        parser.error("--frames must be at least 1")
    if args.settle < 0:
        parser.error("--settle cannot be negative")
    if args.sync_tolerance_ms <= 0:
        parser.error("--sync-tolerance-ms must be greater than 0")
    if not re.fullmatch(r"\d+x\d+", args.depth_size.lower()):
        parser.error("--depth-size must use HxW format, for example 616x1064")
    if any(int(value) < 1 for value in args.depth_size.lower().split("x")):
        parser.error("--depth-size dimensions must be positive")
    if bool(args.images) != bool(args.depth_dir):
        parser.error("--images and --depth-dir must be provided together to reuse a capture")
    if args.images and args.segmentation_gt:
        parser.error("Use --segmentation-dir, not --segmentation-gt, when replaying images")
    if args.segmentation_dir and not args.images:
        parser.error("--segmentation-dir can only be used with --images")
    return args


def main():
    args = parse_args()
    out_dir = Path(args.out).expanduser().resolve()
    if out_dir.exists():
        raise FileExistsError(f"Output directory already exists; choose a new --out: {out_dir}")

    capture_dir = Path(args.images).expanduser().resolve() if args.images else out_dir / "capture"
    depth_dir = Path(args.depth_dir).expanduser().resolve() if args.depth_dir else capture_dir / "depth_gt"
    segmentation_dir = (
        Path(args.segmentation_dir).expanduser().resolve()
        if args.segmentation_dir else capture_dir / "segmentation_gt"
    )
    inference_dir = out_dir / "perception"
    capture_cmd = [
        sys.executable, str(ROOT / "tools" / "capture_scan.py"),
        "--step", str(args.step), "--frames", str(args.frames), "--settle", str(args.settle),
        "--sync-tolerance-ms", str(args.sync_tolerance_ms),
        "--out", str(capture_dir), "--depth-out", str(depth_dir),
    ]
    if args.segmentation_gt:
        capture_cmd.append("--segmentation-gt")
    inference_cmd = [
        sys.executable, str(ROOT / "tools" / "run_images.py"),
        "--images", str(capture_dir), "--depth-dir", str(depth_dir),
        "--depth-size", args.depth_size, "--device", args.device, "--cfg", args.cfg,
        "--out", str(inference_dir),
    ]
    if args.segmentation_gt or args.segmentation_dir:
        inference_cmd.extend(["--panoptic-dir", str(segmentation_dir)])

    os.makedirs(out_dir.parent, exist_ok=True)
    if args.images:
        if not capture_dir.is_dir() or not depth_dir.is_dir():
            raise FileNotFoundError(
                f"Existing capture and aligned depth directories are required: "
                f"{capture_dir}, {depth_dir}"
            )
        if not list(capture_dir.glob("stop*_f*.png")):
            raise FileNotFoundError(f"No stop*_f*.png images found in {capture_dir}")
        if args.segmentation_dir:
            if not segmentation_dir.is_dir():
                raise FileNotFoundError(f"Panoptic GT directory not found: {segmentation_dir}")
            if not list(segmentation_dir.glob("stop*_f*.npy")):
                raise FileNotFoundError(f"No panoptic GT .npy files found in {segmentation_dir}")
    else:
        subprocess.run(capture_cmd, cwd=ROOT, check=True)
    subprocess.run(inference_cmd, cwd=ROOT, check=True)

    with open(inference_dir / "detections.csv", newline="") as fh:
        rows = list(csv.DictReader(fh))
    rejected_path = inference_dir / "rejected.csv"
    with open(rejected_path, newline="") as fh:
        rejected_rows = list(csv.DictReader(fh))
    with open(inference_dir / "segmentation_metrics.csv", newline="") as fh:
        segmentation_rows = list(csv.DictReader(fh))
    with open(inference_dir / "instance_segmentation_metrics.csv", newline="") as fh:
        instance_segmentation_rows = list(csv.DictReader(fh))
    with open(capture_dir / "capture_metadata.csv", newline="") as fh:
        image_count = sum(1 for _ in csv.DictReader(fh))
    summary = build_summary(
        rows, image_count, rejected_rows, segmentation_rows, instance_segmentation_rows
    )
    summary_path = out_dir / "accuracy_summary.json"
    with open(summary_path, "w") as fh:
        json.dump(summary, fh, indent=2)
        fh.write("\n")
    report_path = out_dir / "accuracy_report.md"
    write_markdown_report(report_path, summary)

    print(f"\nĐã hoàn tất quét ảnh tĩnh; không xử lý/gộp nhiều frame.")
    print(f"Ảnh và depth GT: {capture_dir}")
    print(f"Kết quả từng detection: {inference_dir / 'detections.csv'}")
    print(f"Detection bị loại: {rejected_path}")
    print(f"Tóm tắt độ chính xác depth: {summary_path}")
    print(f"Báo cáo chẩn đoán: {report_path}")
    print(json.dumps(summary["all_detections"], indent=2))


if __name__ == "__main__":
    main()
