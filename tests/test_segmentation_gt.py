import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
from segmentation_gt import (
    decode_panoptic_labels,
    object_surface_depth,
    instance_segmentation_metrics,
    segmentation_metrics,
    semantic_masks,
    visible_instance_masks,
)


def test_box_surface_intersection_uses_nearest_front_face():
    origin = np.array([0.0, 0.0, 0.0])
    direction = np.array([[[1.0, 0.0, 0.0]]])
    obj = {
        "model_name": "box",
        "shape": "box",
        "x": 3.0, "y": 0.0, "z": 0.0,
        "size_x": 1.0, "size_y": 2.0, "size_z": 2.0,
    }

    depth, hit = object_surface_depth(obj, origin, direction)

    assert hit[0, 0]
    assert depth[0, 0] == 2.5


def test_cylinder_surface_intersection_uses_nearest_side():
    origin = np.array([0.0, 0.0, 0.0])
    direction = np.array([[[1.0, 0.0, 0.0]]])
    obj = {
        "model_name": "cylinder",
        "shape": "cylinder",
        "x": 3.0, "y": 0.0, "z": 0.0,
        "size_x": 1.0, "size_y": 1.0, "size_z": 2.0,
    }

    depth, hit = object_surface_depth(obj, origin, direction)

    assert hit[0, 0]
    assert depth[0, 0] == 2.5


def test_box_ray_parallel_to_axis_is_not_clipped_to_fake_intersection():
    origin = np.array([0.0, 0.0, 0.0])
    direction = np.array([[[1.0, 0.0, 0.0]]])
    obj = {
        "model_name": "box",
        "shape": "box",
        "x": 3.0, "y": 0.0, "z": 0.0,
        "size_x": 1.0, "size_y": 2.0, "size_z": 2.0,
    }

    depth, hit = object_surface_depth(obj, origin, direction)

    assert hit[0, 0]
    assert depth[0, 0] == 2.5


def test_box_ray_parallel_outside_slab_misses():
    origin = np.array([0.0, 0.0, 0.0])
    direction = np.array([[[1.0, 0.0, 0.0]]])
    obj = {
        "model_name": "box",
        "shape": "box",
        "x": 3.0, "y": 2.0, "z": 0.0,
        "size_x": 1.0, "size_y": 1.0, "size_z": 2.0,
    }

    depth, hit = object_surface_depth(obj, origin, direction)

    assert not hit[0, 0]


def test_visible_instance_mask_excludes_depth_occluder():
    obj = {
        "model_name": "box",
        "class_name": "cup",
        "shape": "box",
        "x": 3.0, "y": 0.0, "z": 0.0,
        "size_x": 1.0, "size_y": 2.0, "size_z": 2.0,
    }
    K = (100.0, 100.0, 2.0, 2.0)
    depth = np.full((5, 5), np.nan, dtype=np.float32)
    depth[2, 2] = 2.5
    depth[2, 3] = 1.0

    masks = visible_instance_masks(
        depth, K, 0.0, (0.0, 0.0, 0.0), [obj],
        visibility_tolerance_m=0.01,
    )

    assert masks["box"][2, 2]
    assert not masks["box"][2, 3]
    assert masks["box"].sum() == 1


def test_semantic_mask_and_pixel_iou_metrics():
    objects = [
        {"model_name": "cup_a", "class_name": "cup"},
        {"model_name": "cup_b", "class_name": "cup"},
    ]
    first = np.array([[True, True], [False, False]])
    second = np.array([[False, False], [True, False]])
    gt = semantic_masks({"cup_a": first, "cup_b": second}, objects)
    pred = {"cup": np.array([[True, False], [True, True]])}

    metrics = segmentation_metrics(pred, gt)

    assert metrics["per_class"]["cup"]["tp_px"] == 2
    assert metrics["per_class"]["cup"]["fp_px"] == 1
    assert metrics["per_class"]["cup"]["fn_px"] == 1
    assert metrics["per_class"]["cup"]["iou"] == 0.5
    assert metrics["mean_iou"] == 0.5


def test_instance_metrics_match_masks_without_using_class_labels():
    gt = [
        np.array([[True, True], [False, False]]),
        np.array([[False, False], [True, True]]),
    ]
    predicted = [
        np.array([[True, True], [False, False]]),
        np.array([[False, False], [True, False]]),
        np.array([[False, False], [False, True]]),
    ]

    metrics = instance_segmentation_metrics(predicted, gt, iou_threshold=0.5)

    assert metrics["predicted_instances"] == 3
    assert metrics["ground_truth_instances"] == 2
    assert metrics["true_positives"] == 2
    assert metrics["false_positives"] == 1
    assert metrics["false_negatives"] == 0
    assert metrics["precision"] == 2 / 3
    assert metrics["recall"] == 1.0
    assert metrics["mean_matched_iou"] == 0.75


def test_decode_gazebo_panoptic_map_keeps_semantic_and_instance_ids():
    label_map = np.zeros((2, 3, 3), dtype=np.uint8)
    label_map[0, :2, 2] = 1
    label_map[0, 0, 0] = 1
    label_map[0, 1, 0] = 1
    label_map[1, 1:, 2] = 2
    label_map[1, 1:, 0] = 2
    objects = [
        {"model_name": "cup_1", "class_name": "cup", "semantic_label": 1},
        {"model_name": "bottle_1", "class_name": "bottle", "semantic_label": 2},
    ]

    semantic, instances = decode_panoptic_labels(label_map, objects)

    assert semantic["cup"].sum() == 2
    assert semantic["bottle"].sum() == 2
    assert len(instances) == 2
    assert {name for name, _ in instances} == {
        "label_1_instance_1", "label_2_instance_2"
    }
