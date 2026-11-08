import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
from scan_evaluate import (
    aggregate_instance_segmentation,
    aggregate_segmentation,
    build_summary,
    depth_metrics,
    write_markdown_report,
)


def test_depth_metrics_match_aligned_ground_truth():
    rows = [
        {"class": "cup", "depth_gt_m": "2.0", "depth_m": "1.5"},
        {"class": "cup", "depth_gt_m": "4.0", "depth_m": "5.0"},
        {"class": "book", "depth_gt_m": "", "depth_m": "3.0"},
    ]

    metrics = depth_metrics(rows)

    assert metrics["observations"] == 2
    assert metrics["mae_m"] == 0.75
    assert metrics["rmse_m"] == (0.625 ** 0.5)
    assert metrics["abs_rel"] == 0.25
    assert metrics["bias_m"] == 0.25


def test_summary_keeps_repeat_views_as_independent_detections():
    rows = [
        {"image": "a.png", "class": "cup", "depth_gt_m": "2.0", "depth_m": "1.5",
         "range_m": "1.4", "e_xy_to_nearest_gt": "0.5", "conf": "0.8", "truncated": "0",
         "e_xy_to_gt_surface_at_uv": "0.05", "e_xyz_to_gt_surface_at_uv": "0.06"},
        {"image": "b.png", "class": "cup", "depth_gt_m": "2.0", "depth_m": "1.8",
         "range_m": "2.0", "e_xy_to_nearest_gt": "0.3", "conf": "0.6", "truncated": "1",
         "e_xy_to_gt_surface_at_uv": "0.07", "e_xyz_to_gt_surface_at_uv": "0.08"},
        {"image": "b.png", "class": "book", "depth_gt_m": "", "depth_m": "3.0",
         "range_m": "3.0", "e_xy_to_nearest_gt": "0.1", "conf": "0.9", "truncated": "0",
         "e_xy_to_gt_surface_at_uv": "", "e_xyz_to_gt_surface_at_uv": ""},
    ]

    summary = build_summary(rows, image_count=6)

    assert summary["image_count"] == 6
    assert summary["detection_count"] == 3
    assert summary["temporal_fusion"] is False
    assert summary["all_detections"]["observations"] == 2
    assert summary["by_class"]["cup"]["detections"] == 2
    assert summary["by_class"]["cup"]["truncated_detections"] == 1
    assert summary["by_class"]["book"]["observations"] == 0
    assert summary["by_class"]["book"]["mae_m"] is None
    assert summary["depth_by_range"]["near_lt_1_5m"]["observations"] == 1
    assert summary["depth_by_range"]["mid_1_5_to_2_5m"]["observations"] == 1
    assert summary["world_surface_xy_error"]["observations"] == 2
    assert abs(summary["world_surface_xy_error"]["median_m"] - 0.06) < 1e-9
    assert summary["world_surface_xyz_error"]["observations"] == 2
    assert summary["object_center_xy_diagnostic"]["observations"] == 3
    assert summary["object_center_xy_diagnostic"]["median_m"] == 0.3
    assert summary["diagnostic_signals"]
    assert summary["segmentation_ground_truth"] is False


def test_summary_warns_when_depth_range_coverage_is_narrow():
    rows = [
        {"class": "cup", "depth_gt_m": "2.0", "depth_m": "1.5", "range_m": "2.0"},
        {"class": "cup", "depth_gt_m": "2.0", "depth_m": "1.8", "range_m": "2.1"},
    ]

    summary = build_summary(rows, image_count=2)

    assert any("fewer than two configured range bands" in signal
               for signal in summary["diagnostic_signals"])


def test_same_pixel_lateral_error_is_not_assigned_to_tf_without_evidence():
    rows = [
        {"class": "cup", "depth_gt_m": "2.0", "depth_m": "1.5",
         "range_m": "2.0", "e_xy_to_gt_surface_at_uv": "0.5",
         "e_xyz_to_gt_surface_at_uv": "0.7"}
    ]

    summary = build_summary(rows, image_count=1)

    assert any("off-axis pixels convert depth error" in signal
               for signal in summary["diagnostic_signals"])
    assert not any("inspect yaw/TF" in signal for signal in summary["diagnostic_signals"])


def test_summary_reports_depth_fusion_rejections():
    rejected = [
        {"class": "bottle", "reason": "low_valid_ratio"},
        {"class": "cup", "reason": "low_valid_ratio"},
        {"class": "cup", "reason": "empty_mask"},
    ]

    summary = build_summary([], image_count=3, rejected_rows=rejected)

    assert summary["rejected_detection_count"] == 3
    assert summary["rejections_by_reason"] == {"low_valid_ratio": 2, "empty_mask": 1}
    assert summary["by_class"]["bottle"]["rejected_detections"] == 1
    assert any("low_valid_ratio=2" in signal for signal in summary["diagnostic_signals"])


def test_markdown_report_explains_metrics(tmp_path):
    rows = [
        {"image": "a.png", "class": "cup", "depth_gt_m": "2.0", "depth_m": "1.5",
         "range_m": "1.4", "e_xy_to_nearest_gt": "0.5", "conf": "0.8", "truncated": "0"},
    ]
    summary = build_summary(rows, image_count=1)
    report_path = tmp_path / "report.md"

    write_markdown_report(report_path, summary)

    report = report_path.read_text()
    assert "Depth against aligned Gazebo visible-surface depth" in report
    assert "Class-agnostic instance-mask overlap" in report
    assert "not a semantic benchmark" in report
    assert "Same-pixel 3D point comparison" in report


def test_aggregate_segmentation_uses_pixel_confusion_totals():
    rows = [
        {"image": "a.png", "class": "cup", "tp_px": "8", "fp_px": "2", "fn_px": "2"},
        {"image": "b.png", "class": "cup", "tp_px": "2", "fp_px": "0", "fn_px": "2"},
        {"image": "a.png", "class": "book", "tp_px": "0", "fp_px": "1", "fn_px": "0"},
    ]

    summary = aggregate_segmentation(rows)

    assert summary["evaluated_images"] == 2
    assert summary["per_class"]["cup"]["iou"] == 10 / 16
    assert summary["per_class"]["cup"]["precision"] == 10 / 12
    assert summary["per_class"]["cup"]["recall"] == 10 / 14
    assert summary["per_class"]["book"]["iou"] == 0.0
    assert summary["micro_precision"] == 10 / 13


def test_aggregate_instance_metrics_uses_visible_instance_counts():
    rows = [
        {
            "image": "a.png", "predicted_instances": "2", "ground_truth_instances": "1",
            "true_positives": "1", "false_positives": "1", "false_negatives": "0",
            "mean_matched_iou": "0.75",
        },
        {
            "image": "b.png", "predicted_instances": "1", "ground_truth_instances": "2",
            "true_positives": "1", "false_positives": "0", "false_negatives": "1",
            "mean_matched_iou": "0.5",
        },
    ]

    metrics = aggregate_instance_segmentation(rows)

    assert metrics["evaluated_images"] == 2
    assert metrics["true_positives"] == 2
    assert metrics["false_positives"] == 1
    assert metrics["false_negatives"] == 1
    assert metrics["precision"] == 2 / 3
    assert metrics["recall"] == 2 / 3
    assert metrics["mean_matched_iou"] == 0.625


def test_depth_metrics_without_ground_truth_are_empty():
    metrics = depth_metrics([{"class": "chair", "depth_gt_m": "", "depth_m": "2.0"}])

    assert metrics == {
        "observations": 0,
        "mae_m": None,
        "rmse_m": None,
        "abs_rel": None,
        "bias_m": None,
    }
