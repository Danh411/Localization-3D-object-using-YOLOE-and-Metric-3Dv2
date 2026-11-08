#!/usr/bin/env python3
"""Summarize Metric3D predictions against aligned Gazebo depth maps."""
import argparse
import csv
import json
import os
from collections import defaultdict

import numpy as np


def read_csv(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def depth_values(rows, ground_truth_field):
    valid = []
    for row in rows:
        if not row.get(ground_truth_field) or not row.get("depth_m"):
            continue
        gt, pred = float(row[ground_truth_field]), float(row["depth_m"])
        if gt <= 0:
            continue
        valid.append((row, gt, pred))
    return valid


def metrics(values):
    if not values:
        return {"observations": 0, "mae_m": "", "rmse_m": "", "abs_rel": "", "bias_m": ""}
    errors = np.asarray([pred - gt for _, gt, pred in values], dtype=float)
    truth = np.asarray([gt for _, gt, _ in values], dtype=float)
    return {
        "observations": len(values),
        "mae_m": float(np.mean(np.abs(errors))),
        "rmse_m": float(np.sqrt(np.mean(errors ** 2))),
        "abs_rel": float(np.mean(np.abs(errors) / truth)),
        "bias_m": float(np.mean(errors)),
    }


def timing_stats(path):
    if not os.path.isfile(path):
        return "", ""
    rows = read_csv(path)
    values = [float(r["depth_ms"]) for r in rows[1:] if r.get("depth_ms")]
    if not values:
        return "", ""
    return float(np.percentile(values, 50)), float(np.percentile(values, 95))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--small", required=True, help="run_images output for 336x448")
    parser.add_argument("--large", required=True, help="run_images output for 616x1064")
    parser.add_argument("--out", required=True, help="Directory for comparison CSVs and report")
    args = parser.parse_args()
    runs = [("336x448", args.small), ("616x1064", args.large)]
    os.makedirs(args.out, exist_ok=True)

    all_values = {}
    metric_rows = []
    run_metadata = {}
    detection_counts = {}
    ground_truths = [
        ("gazebo_surface", "depth_gt_m"),
        ("gazebo_object_center_z", "depth_gt_object_center_z_m"),
    ]
    for label, run_dir in runs:
        detections = read_csv(os.path.join(run_dir, "detections.csv"))
        detection_counts[label] = defaultdict(int)
        for detection in detections:
            detection_counts[label][detection["class"]] += 1
        metadata_path = os.path.join(run_dir, "run_metadata.json")
        run_metadata[label] = json.load(open(metadata_path)) if os.path.isfile(metadata_path) else {}
        p50, p95 = timing_stats(os.path.join(run_dir, "timings.csv"))
        all_values[label] = {}
        for source, field in ground_truths:
            values = depth_values(detections, field)
            all_values[label][source] = values
            grouped = defaultdict(list)
            for value in values:
                grouped[value[0]["class"]].append(value)
            grouped["ALL_CLASSES"] = values
            for class_name, class_values in grouped.items():
                row = {"depth_input_hw": label, "ground_truth": source, "class": class_name,
                       **metrics(class_values), "depth_p50_ms": p50, "depth_p95_ms": p95}
                metric_rows.append(row)

    metrics_path = os.path.join(args.out, "depth_metrics.csv")
    fields = ["depth_input_hw", "ground_truth", "class", "observations", "mae_m", "rmse_m", "abs_rel",
              "bias_m", "depth_p50_ms", "depth_p95_ms"]
    with open(metrics_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in metric_rows:
            writer.writerow({k: (f"{v:.6f}" if isinstance(v, float) else v) for k, v in row.items()})

    small_by_key = {}
    large_by_key = {}
    for label, index in (("336x448", small_by_key), ("616x1064", large_by_key)):
        detections = read_csv(os.path.join(dict(runs)[label], "detections.csv"))
        for row in detections:
            index[(row["image"], row["class"])] = row
    paired = []
    for key in sorted(small_by_key.keys() & large_by_key.keys()):
        small, large = small_by_key[key], large_by_key[key]
        paired.append({
            "image": key[0], "class": key[1],
            "surface_gt_m": small.get("depth_gt_m", ""),
            "object_center_gt_z_m": small.get("depth_gt_object_center_z_m", ""),
            "pred_336_m": small["depth_m"], "pred_616_m": large["depth_m"],
            "surface_abs_error_336_m": small.get("depth_abs_error_m", ""),
            "surface_abs_error_616_m": large.get("depth_abs_error_m", ""),
            "center_abs_error_336_m": small.get("depth_center_abs_error_m", ""),
            "center_abs_error_616_m": large.get("depth_center_abs_error_m", ""),
            "pred_616_minus_336_m": float(large["depth_m"]) - float(small["depth_m"]),
        })
    paired_path = os.path.join(args.out, "paired_predictions.csv")
    with open(paired_path, "w", newline="") as fh:
        fields = ["image", "class", "surface_gt_m", "object_center_gt_z_m", "pred_336_m",
                  "pred_616_m", "surface_abs_error_336_m", "surface_abs_error_616_m",
                  "center_abs_error_336_m", "center_abs_error_616_m", "pred_616_minus_336_m"]
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in paired:
            writer.writerow(row)

    overall = {(row["depth_input_hw"], row["ground_truth"]): row for row in metric_rows
               if row["class"] == "ALL_CLASSES"}
    metadata_path = os.path.join(args.out, "rgb", "capture_metadata.csv")
    capture_rows = read_csv(metadata_path) if os.path.isfile(metadata_path) else []
    sync_ms = [float(row["sync_delta_ms"]) for row in capture_rows if row.get("sync_delta_ms")]
    lines = [
        "# Metric3D depth comparison",
        "",
        "This report compares per-detection median Metric3D depth with Gazebo's aligned "
        "`32FC1` depth map and with object-center depth projected from Gazebo ground-truth poses.",
        "",
        f"Captured RGB/depth pairs: **{len(capture_rows)}**; maximum timestamp difference: "
        f"**{max(sync_ms):.3f} ms**." if sync_ms else "Capture synchronization metadata unavailable.",
        "",
        "## Run settings",
        "",
        "| Input HxW | Images | Device | PyTorch | CUDA | FP16 | HFOV | Yaw source |",
        "|---|---:|---|---|---|---|---:|---|",
    ]
    for label, _ in runs:
        meta = run_metadata[label]
        lines.append(
            f"| {label} | {meta.get('image_count', 'unknown')} | {meta.get('device', 'unknown')} | "
            f"{meta.get('torch_version', 'unknown')} | {meta.get('cuda_available', 'unknown')} | "
            f"{meta.get('depth_fp16_effective', 'unknown')} | "
            f"{meta.get('camera_hfov_deg', 'unknown')}° | {meta.get('capture_yaw_source', 'unknown')} |"
        )
    lines += [
        "",
        "## Compared with visible-surface depth",
        "",
        "The sensor-depth reference is the median Gazebo depth inside the same eroded object mask.",
        "",
        "| Input HxW | Valid observations | MAE (m) | RMSE (m) | AbsRel | Bias (m) | Depth p50 (ms) | Depth p95 (ms) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, _ in runs:
        row = overall[(label, "gazebo_surface")]
        def fmt(key, precision=3):
            value = row[key]
            return "n/a" if value == "" else f"{float(value):.{precision}f}"
        lines.append(
            f"| {label} | {row['observations']} | {fmt('mae_m')} | {fmt('rmse_m')} | "
            f"{fmt('abs_rel')} | {fmt('bias_m')} | {fmt('depth_p50_ms', 1)} | {fmt('depth_p95_ms', 1)} |"
        )
    lines += [
        "",
        "## Compared with Gazebo object-center depth",
        "",
        "This reference projects each matched object's configured Gazebo center `(x, y, z)` into "
        "the camera optical frame and compares its forward `Z`. It is center depth, not the visible "
        "front surface, so it is a distinct metric and can differ by object size/shape.",
        "",
        "| Input HxW | Valid observations | MAE (m) | RMSE (m) | AbsRel | Bias (m) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for label, _ in runs:
        row = overall[(label, "gazebo_object_center_z")]
        def fmt_center(key):
            value = row[key]
            return "n/a" if value == "" else f"{float(value):.3f}"
        lines.append(
            f"| {label} | {row['observations']} | {fmt_center('mae_m')} | {fmt_center('rmse_m')} | "
            f"{fmt_center('abs_rel')} | {fmt_center('bias_m')} |"
        )
    small_mae = overall[("336x448", "gazebo_surface")]["mae_m"]
    large_mae = overall[("616x1064", "gazebo_surface")]["mae_m"]
    small_center_mae = overall[("336x448", "gazebo_object_center_z")]["mae_m"]
    large_center_mae = overall[("616x1064", "gazebo_object_center_z")]["mae_m"]
    mae_reduction = 100 * (small_mae - large_mae) / small_mae if small_mae else 0
    small_p50 = overall[("336x448", "gazebo_surface")]["depth_p50_ms"]
    large_p50 = overall[("616x1064", "gazebo_surface")]["depth_p50_ms"]
    latency_ratio = large_p50 / small_p50 if small_p50 else 0
    metric_lookup = {(row["depth_input_hw"], row["ground_truth"], row["class"]): row
                     for row in metric_rows}
    lines += [
        "",
        f"Paired same-image/class detections: **{len(paired)}**.",
        "",
        "Detected observations per run: " + "; ".join(
            f"{label}: {sum(counts.values())} (" +
            ", ".join(f"{name} {count}" for name, count in sorted(counts.items())) + ")"
            for label, counts in detection_counts.items()
        ) + ".",
        "",
        "## Takeaway",
        "",
        f"On this detected-object subset, `616x1064` reduced depth MAE by **{mae_reduction:.1f}%** "
        f"versus `336x448`, while its median depth inference was **{latency_ratio:.1f}x** slower. "
        "Against the configured object-center Z, MAE was "
        f"{small_center_mae:.3f} m (`336x448`) and {large_center_mae:.3f} m (`616x1064`). "
        "Treat that center comparison as diagnostic because Metric3D estimates visible surface "
        "depth, not necessarily the object's geometric center. These results do not establish "
        "performance on missed objects or other scenes.",
        "",
        "## Per-class MAE",
        "",
        "| Class | Surface 336x448 (m) | Surface 616x1064 (m) | Center Z 336x448 (m) | Center Z 616x1064 (m) |",
        "|---|---:|---:|---:|---:|",
    ]
    for class_name in sorted(detection_counts["336x448"]):
        surface_small = metric_lookup[("336x448", "gazebo_surface", class_name)]["mae_m"]
        surface_large = metric_lookup[("616x1064", "gazebo_surface", class_name)]["mae_m"]
        center_small = metric_lookup[("336x448", "gazebo_object_center_z", class_name)]["mae_m"]
        center_large = metric_lookup[("616x1064", "gazebo_object_center_z", class_name)]["mae_m"]
        lines.append(
            f"| {class_name} | {surface_small:.3f} | {surface_large:.3f} | "
            f"{center_small:.3f} | {center_large:.3f} |"
        )
    lines += [
        "",
        "",
        "## Interpretation limits",
        "",
        "- Metrics include only objects YOLOE detected in both the RGB image and the comparison run; "
        "they do not measure detector recall or missed objects.",
        "- Each observation compares the median predicted depth and median Gazebo depth within the "
        "same eroded detector mask; it is not a dense per-pixel depth benchmark. Object-center "
        "depth is computed from the closest same-class configured GT pose in XY.",
        "- The RGB/depth pairing tolerance is recorded in `capture_metadata.csv`; inspect it if "
        "synchronization errors are suspected.",
        "- The two runs must use the same captured RGB/depth pairs, weights, camera intrinsics and "
        "precision mode for a controlled input-size comparison. Run settings are recorded in each "
        "`run_metadata.json`.",
        "",
        "Per-class and paired values for both references are in `depth_metrics.csv` and "
        "`paired_predictions.csv`.",
        "",
    ]
    report_path = os.path.join(args.out, "SUMMARY.md")
    with open(report_path, "w") as fh:
        fh.write("\n".join(lines))
    print(f"Report: {report_path}")
    print(f"Metrics: {metrics_path}")
    print(f"Paired predictions: {paired_path}")


if __name__ == "__main__":
    main()
