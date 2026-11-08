"""Build visible semantic masks by ray-casting configured Gazebo object geometry."""
import math

import numpy as np


def camera_rays(width, height, K, yaw, base_xyz, t_offset_m=0.0):
    fx, fy, cx, cy = K
    u, v = np.meshgrid(np.arange(width, dtype=np.float64),
                       np.arange(height, dtype=np.float64))
    nx, ny = (u - cx) / fx, (v - cy) / fy
    c, s = math.cos(yaw), math.sin(yaw)
    direction = np.stack((
        c + s * nx,
        s - c * nx,
        -ny,
    ), axis=-1)
    origin = np.asarray(base_xyz, dtype=np.float64) + np.array(
        [c * t_offset_m, s * t_offset_m, 0.0]
    )
    return origin, direction


def _box_intersection(origin, direction, center, size):
    half = np.asarray(size, dtype=np.float64) / 2.0
    lower, upper = np.asarray(center) - half, np.asarray(center) + half
    t_near = np.full(direction.shape[:2], -np.inf)
    t_far = np.full(direction.shape[:2], np.inf)
    intersects = np.ones(direction.shape[:2], dtype=bool)
    for axis in range(3):
        d = direction[..., axis]
        parallel = np.abs(d) < 1e-12
        intersects &= ~parallel | (
            (origin[axis] >= lower[axis]) & (origin[axis] <= upper[axis])
        )
        safe_d = np.where(parallel, 1.0, d)
        t1 = (lower[axis] - origin[axis]) / safe_d
        t2 = (upper[axis] - origin[axis]) / safe_d
        t1 = np.where(parallel, -np.inf, t1)
        t2 = np.where(parallel, np.inf, t2)
        t_near = np.maximum(t_near, np.minimum(t1, t2))
        t_far = np.minimum(t_far, np.maximum(t1, t2))
    distance = np.where(t_near > 0, t_near, t_far)
    intersects &= (t_far >= np.maximum(t_near, 0)) & (distance > 0)
    return distance, intersects


def _cylinder_intersection(origin, direction, center, radius, height):
    dx, dy, dz = direction[..., 0], direction[..., 1], direction[..., 2]
    ox, oy, oz = origin - np.asarray(center, dtype=np.float64)
    a = dx * dx + dy * dy
    b = 2.0 * (ox * dx + oy * dy)
    c = ox * ox + oy * oy - radius * radius
    discriminant = b * b - 4.0 * a * c
    valid_side = (a > 1e-12) & (discriminant >= 0)
    root = np.sqrt(np.maximum(discriminant, 0))
    t0 = np.where(valid_side, (-b - root) / np.where(a > 1e-12, 2 * a, 1), np.inf)
    t1 = np.where(valid_side, (-b + root) / np.where(a > 1e-12, 2 * a, 1), np.inf)
    z_min, z_max = -height / 2.0, height / 2.0
    safe_t0 = np.where(np.isfinite(t0), t0, 0)
    safe_t1 = np.where(np.isfinite(t1), t1, 0)
    z0, z1 = oz + safe_t0 * dz, oz + safe_t1 * dz
    side0 = (t0 > 0) & (z0 >= z_min) & (z0 <= z_max)
    side1 = (t1 > 0) & (z1 >= z_min) & (z1 <= z_max)
    distance = np.minimum(np.where(side0, t0, np.inf), np.where(side1, t1, np.inf))

    for cap_z in (z_min, z_max):
        valid_cap_ray = np.abs(dz) > 1e-12
        cap_t = np.where(valid_cap_ray, (cap_z - oz) / np.where(valid_cap_ray, dz, 1), np.inf)
        safe_cap_t = np.where(valid_cap_ray, cap_t, 0)
        hit_x, hit_y = ox + safe_cap_t * dx, oy + safe_cap_t * dy
        inside_cap = (hit_x * hit_x + hit_y * hit_y <= radius * radius)
        distance = np.minimum(distance, np.where((cap_t > 0) & inside_cap, cap_t, np.inf))
    intersects = np.isfinite(distance)
    return distance, intersects


def object_surface_depth(obj, origin, direction):
    shape = obj["shape"]
    center = (obj["x"], obj["y"], obj["z"])
    if shape == "box":
        size = (obj["size_x"], obj["size_y"], obj["size_z"])
        return _box_intersection(origin, direction, center, size)
    if shape == "cylinder":
        radius = obj["size_x"] / 2.0
        return _cylinder_intersection(origin, direction, center, radius, obj["size_z"])
    raise ValueError(f"Unsupported GT shape {shape!r} for {obj['model_name']}")


def visible_instance_masks(depth_gt, K, yaw, base_xyz, objects, t_offset_m=0.0,
                           visibility_tolerance_m=0.03, clip_near_m=0.1, max_depth_m=10.0):
    """Return one visible boolean mask per object, gated by Gazebo's aligned depth."""
    height, width = depth_gt.shape
    origin, direction = camera_rays(width, height, K, yaw, base_xyz, t_offset_m)
    valid_sensor = (
        np.isfinite(depth_gt) & (depth_gt > clip_near_m) & (depth_gt < max_depth_m)
    )
    masks = {}
    for obj in objects:
        surface_depth, intersects = object_surface_depth(obj, origin, direction)
        masks[obj["model_name"]] = (
            intersects & valid_sensor &
            (np.abs(surface_depth - depth_gt) <= visibility_tolerance_m)
        )
    return masks


def semantic_masks(instance_masks, objects):
    labels = {}
    for obj in objects:
        class_name = obj["class_name"]
        if class_name not in labels:
            labels[class_name] = np.zeros_like(instance_masks[obj["model_name"]], dtype=bool)
        labels[class_name] |= instance_masks[obj["model_name"]]
    return labels


def decode_panoptic_labels(label_map, objects):
    """Decode Gazebo's RGB panoptic map into class and per-instance masks."""
    label_map = np.asarray(label_map)
    if label_map.ndim != 3 or label_map.shape[2] != 3:
        raise ValueError(f"Panoptic label map must have shape (H, W, 3), got {label_map.shape}")
    if label_map.dtype != np.uint8:
        raise ValueError(f"Panoptic label map must use uint8 channels, got {label_map.dtype}")

    label_to_class = {}
    for obj in objects:
        if obj.get("semantic_label") is None:
            continue
        label_id = int(obj["semantic_label"])
        if not 1 <= label_id <= 255:
            raise ValueError(f"Gazebo semantic label must be in [1, 255], got {label_id}")
        existing_class = label_to_class.get(label_id)
        if existing_class and existing_class != obj["class_name"]:
            raise ValueError(
                f"Gazebo semantic label {label_id} maps to multiple classes: "
                f"{existing_class!r}, {obj['class_name']!r}"
            )
        label_to_class[label_id] = obj["class_name"]
    labels = label_map[..., 2]
    instance_ids = (
        label_map[..., 0].astype(np.uint16)
        | (label_map[..., 1].astype(np.uint16) << 8)
    )
    semantic = {
        class_name: labels == label_id
        for label_id, class_name in label_to_class.items()
    }
    instances = []
    for label_id in label_to_class:
        visible_ids = np.unique(instance_ids[(labels == label_id) & (instance_ids > 0)])
        for instance_id in visible_ids:
            instances.append(
                (f"label_{label_id}_instance_{int(instance_id)}",
                 (labels == label_id) & (instance_ids == instance_id))
            )
    return semantic, instances


def segmentation_metrics(predicted_masks, ground_truth_masks):
    class_names = sorted(set(predicted_masks) | set(ground_truth_masks))
    per_class = {}
    for class_name in class_names:
        pred = predicted_masks.get(class_name)
        gt = ground_truth_masks.get(class_name)
        if pred is None:
            pred = np.zeros_like(gt, dtype=bool)
        if gt is None:
            gt = np.zeros_like(pred, dtype=bool)
        pred, gt = pred.astype(bool), gt.astype(bool)
        tp = int(np.count_nonzero(pred & gt))
        fp = int(np.count_nonzero(pred & ~gt))
        fn = int(np.count_nonzero(~pred & gt))
        union = tp + fp + fn
        per_class[class_name] = {
            "iou": tp / union if union else None,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "tp_px": tp,
            "fp_px": fp,
            "fn_px": fn,
            "predicted_px": tp + fp,
            "ground_truth_px": tp + fn,
        }
    valid_ious = [v["iou"] for v in per_class.values() if v["iou"] is not None]
    present_gt_ious = [
        value["iou"] for value in per_class.values()
        if value["ground_truth_px"] > 0 and value["iou"] is not None
    ]
    return {
        "per_class": per_class,
        "mean_iou": float(np.mean(valid_ious)) if valid_ious else None,
        "mean_iou_present_gt": (
            float(np.mean(present_gt_ious)) if present_gt_ious else None
        ),
    }


def instance_segmentation_metrics(predicted_masks, ground_truth_masks, iou_threshold=0.5):
    """Match predicted masks to visible geometry masks without using class labels."""
    candidates_by_prediction = []
    for pred_index, pred_mask in enumerate(predicted_masks):
        pred_mask = np.asarray(pred_mask, dtype=bool)
        candidates = []
        for gt_index, gt_mask in enumerate(ground_truth_masks):
            gt_mask = np.asarray(gt_mask, dtype=bool)
            union = np.count_nonzero(pred_mask | gt_mask)
            iou = np.count_nonzero(pred_mask & gt_mask) / union if union else 0.0
            if iou >= iou_threshold:
                candidates.append((iou, pred_index, gt_index))
        candidates_by_prediction.append(
            sorted(candidates, key=lambda item: (-item[0], item[2]))
        )

    ground_truth_matches = {}

    def assign(pred_index, visited_ground_truth):
        for iou, _, gt_index in candidates_by_prediction[pred_index]:
            if gt_index in visited_ground_truth:
                continue
            visited_ground_truth.add(gt_index)
            current = ground_truth_matches.get(gt_index)
            if current is None or assign(current[0], visited_ground_truth):
                ground_truth_matches[gt_index] = (pred_index, iou)
                return True
        return False

    for pred_index in range(len(predicted_masks)):
        assign(pred_index, set())
    matches = [
        {
            "predicted_index": pred_index,
            "ground_truth_index": gt_index,
            "iou": float(iou),
        }
        for gt_index, (pred_index, iou) in sorted(ground_truth_matches.items())
    ]

    predicted_count = len(predicted_masks)
    ground_truth_count = len(ground_truth_masks)
    true_positives = len(matches)
    return {
        "predicted_instances": predicted_count,
        "ground_truth_instances": ground_truth_count,
        "true_positives": true_positives,
        "false_positives": predicted_count - true_positives,
        "false_negatives": ground_truth_count - true_positives,
        "precision": true_positives / predicted_count if predicted_count else None,
        "recall": true_positives / ground_truth_count if ground_truth_count else None,
        "mean_matched_iou": (
            float(np.mean([match["iou"] for match in matches])) if matches else None
        ),
        "matches": matches,
    }
