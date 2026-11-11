"""Check synchronized two-world data, frozen inputs and surface/center separation."""
from collections import Counter
import csv
import hashlib
import itertools
import json
from pathlib import Path
import re
import sqlite3
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial.transform import Rotation
import yaml

ROOT = Path(__file__).resolve().parent
ROOMS = ("aws", "tiffany")
TYPES = {".csv", ".json", ".py", ".sh", ".yaml", ".md", ".sqlite", ".jpg", ".png",
         ".log", ".sdf", ".txt", ".sha256"}
EXCLUDE = {"manifest.sha256"}
BRANCHES = ("P0_metric", "ORB_A_only", "ORB_B_only", "P1_orb_A", "P1_orb_B",
            "P2_ground", "P3_combined", "S_key40", "S_on_demand")


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return path.read_text(encoding="utf-8-sig")


def load(path):
    return json.loads(read(path))


def csvrows(path):
    return list(csv.DictReader(read(path).splitlines()))


def csvwrite(path, data):
    keys = list(dict.fromkeys(k for row in data for k in row))
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        writer.writerows(data)


def integrity(path):
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        assert db.execute("pragma integrity_check").fetchone() == ("ok",), path
        assert db.execute("pragma foreign_key_check").fetchone() is None, path


def scene_environment(path):
    world = ET.parse(path).getroot().find("world")
    for elem in list(world):
        if elem.tag == "model" and elem.get("name") == "camera_rig":
            world.remove(elem)
        if elem.tag == "include" and elem.findtext("name") in {"laptop_1", "cup_1", "book_1", "bottle_1"}:
            world.remove(elem)
    # AWS's 5 ms step destabilizes the reused pan rig. Only its copied step is 1 ms.
    world.find("./physics/max_step_size").text = "0.001"
    # Ignore serialization indentation while comparing the original environment.
    for elem in world.iter():
        elem.text = elem.text.strip() if elem.text and elem.text.strip() else None
        elem.tail = None
    return ET.tostring(world)


def verify_room(room):
    path = ROOT / room
    cfg = yaml.safe_load(read(path / "config.yaml"))
    refs = yaml.safe_load(read(path / "gt.yaml"))["objects"]
    centers = load(path / "mesh_centers.json")
    source = load(path / "source.json")
    assert sha(Path(source["source_sdf"])) == source["source_sdf_sha256"]
    assert scene_environment(Path(source["source_sdf"])) == scene_environment(path / "kitchen_controlled.sdf")
    assert "status: SUCCEEDED" in read(path / "action.log")
    assert read(path / "replay_exit.txt").strip() == "0"
    assert "verified A against live, 18 frames" in read(path / "replay.log")
    capture = csvrows(path / "capture_audit.csv")
    assert sorted(int(row["stop"]) for row in capture) == list(range(18))
    assert len({row["stamp_ns"] for row in capture}) == 18
    for row in capture:
        assert row["frame"] == "0" and row["stamp_ns"] == row["camera_info_stamp_ns"]
        assert json.loads(row["K"]) == [914.0147013559828, 914.0147013559828, 640.0, 360.0]
        assert abs(float(row["command_error_deg"])) < .5
        assert abs(float(row["tf_joint_error_deg"])) < .5
        assert abs(int(row["joint_skew_ns"])) <= 10_000_000
    stops = [load(p) for p in path.glob("audit_scan_*.json")]
    assert len(stops) == 18
    assert len(list((path / "frames").glob("*.npz"))) == 18
    rows = []
    for stop in stops:
        f, = stop["frames"]
        assert f["tf"] and f["depth_exact_stamp"] and f["label_exact_stamp"]
        assert f["stamp_ns"] == f["camera_info_stamp_ns"]
        rotation = Rotation.from_quat(f["tf"]["quaternion"]).as_matrix()
        translation = np.array(f["tf"]["translation"])
        with np.load(path / "frames" / f["file"], allow_pickle=False) as data:
            assert set(("rgb", "gt_depth", "pred_depth", "labels_rgb")) <= set(data.files)
            rgb, gt, labels, pred = (data[k] for k in ("rgb", "gt_depth", "labels_rgb", "pred_depth"))
            assert rgb.shape == labels.shape == (720, 1280, 3)
            assert gt.shape == pred.shape == (720, 1280)
            instances = labels[..., 0].astype(np.uint16) | labels[..., 1].astype(np.uint16) << 8
            seen_instances = []
            for ref in refs:
                key = ref["model_name"]
                mask = (labels[..., 2] == ref["semantic_label"]) & (instances != 0)
                ids = np.unique(instances[mask])
                assert len(ids) <= 1, (room, key, ids.tolist())
                seen_instances.extend((ref["semantic_label"], int(value)) for value in ids)
                valid = mask & np.isfinite(gt) & (gt > .1) & (gt < 10)
                bounds = centers[key]
                corners = np.array(list(itertools.product(*zip(bounds["aabb_min_m"], bounds["aabb_max_m"]))))
                axial_bounds = ((corners - translation) @ rotation)[:, 2]
                median = float(np.median(gt[valid])) if valid.any() else None
                if median is not None:
                    assert axial_bounds.min() - .03 <= median <= axial_bounds.max() + .03, (room, key, median, axial_bounds)
                uv = np.argwhere(mask)
                rows.append(dict(room=room, stop=stop["stop_index"], target=key,
                                 stamp_ns=f["stamp_ns"], visible_pixels=int(mask.sum()),
                                 valid_gt_pixels=int(valid.sum()), instance_id=int(ids[0]) if len(ids) else None,
                                 gt_median_axial_m=median,
                                 gt_aabb_axial_min_m=float(axial_bounds.min()),
                                 gt_aabb_axial_max_m=float(axial_bounds.max()),
                                 touches_border=bool(len(uv) and
                                     (uv[:,0].min()<8 or uv[:,0].max()>711 or uv[:,1].min()<8 or uv[:,1].max()>1271)),
                                 rgb_std=float(rgb[mask].std()) if mask.any() else None))
            assert len(seen_instances) == len(set(seen_instances))
            for d in f["detections"]:
                assert d["mask"] in data.files
                mask = np.unpackbits(data[d["mask"]], axis=1, count=1280)
                assert mask.shape == (720, 1280)
    csvwrite(path / "sensor_instance_qa.csv", sorted(rows, key=lambda r:(r["stop"],r["target"])))
    summary = load(path / "experiment_summary.json")
    assert summary["frames"] == 18
    assert not summary["wire_tf_missing"]
    assert set(summary["branches"]) == set(BRANCHES)
    for branch in BRANCHES:
        integrity(path / (branch + ".sqlite"))
    for db in (path / "db").glob("*.sqlite"):
        integrity(db)
    print(f"{room}: 18 quartets, K/TF/yaw, panoptic instance and depth-vs-AABB QA PASS", flush=True)
    return {"room": room, "frames": 18, "visible_frames": dict(Counter(r["target"] for r in rows if r["visible_pixels"])),
            "environment_geometry_materials_preserved": True, "physics_step_s": 0.001,
            "max_command_yaw_error_deg": summary["max_yaw_error_deg"],
            "max_joint_skew_ms": summary["max_joint_skew_ms"], "p0_matches_live": True}


def published():
    for directory in (ROOT, *(ROOT / r for r in ROOMS), *(ROOT / r / "db" for r in ROOMS)):
        for path in directory.iterdir():
            if path.is_file() and (path.suffix in TYPES or path.name == ".gitattributes"):
                if path.name not in EXCLUDE:
                    yield path


def main():
    frozen = load(ROOT / "frozen.json")
    assert frozen["orb_identical_to_kitchen"]
    for name, expected in frozen["files"].items():
        assert sha(ROOT / name) == expected, name
    results = [verify_room(room) for room in ROOMS]
    for filename, regex in (
        ("regression_diagnostic.log", r"Ran 4 tests[\s\S]*OK"),
        ("regression_yoloe.log", r"Ran \d+ tests[\s\S]*OK"),
        ("regression_loc3d.log", r"\d+ passed in "),
    ):
        assert re.search(regex, read(ROOT / filename)), filename
    assert read(ROOT / "batch_exit.txt").strip() == "0"
    (ROOT / "verification.json").write_text(json.dumps({"frozen_hashes_unchanged": True, "rooms": results}, indent=2) + "\n")
    print("Frozen inputs and all 142 regression tests PASS", flush=True)


if __name__ == "__main__":
    main()
