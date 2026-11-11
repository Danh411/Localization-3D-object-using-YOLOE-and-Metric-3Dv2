"""Prepare independent two-world scans with the frozen Kitchen ORB implementation."""
import copy
from datetime import datetime, timezone
import hashlib
import itertools
import json
import math
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial.transform import Rotation
import yaml

ROOT = Path(__file__).resolve().parent
PREV = ROOT.parent / "orb_ground_18angle_fullbatch_20261111_001408"
CROSS = ROOT.parent / "metric3d_crossworld_fullbatch_20261110_222348"
TEMPLATE = PREV / "scan_18x1"
KEYS = ("laptop_1", "book_1", "cup_1", "bottle_1")
# Forward and lateral distances relative to the previously verified room view.
PLACEMENTS = {
    "laptop_1": (1.65, -0.52),
    "book_1": (1.80, 0.45),
    "cup_1": (1.35, 0.12),
    "bottle_1": (1.60, -0.15),
}


def put(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    assert not (ROOT / "aws").exists() and not (ROOT / "tiffany").exists()
    for file in ("orb.py", "test_diagnostic.py"):
        shutil.copyfile(PREV / file, ROOT / file)
    experiment = (PREV / "experiment.py").read_text()
    experiment = experiment.replace(
        "                np.array(f['tf']['translation']))",
        "                np.array(f['tf']['translation']), floor_height=s.cfg['camera'].get('floor_z_m', 0.))"
    )
    assert "floor_height=s.cfg" in experiment
    experiment = experiment.replace("result=dict(scan=name,id=s.id", "result=dict(scan=s.path.name,id=s.id")
    (ROOT / "experiment.py").write_text(experiment, encoding="utf-8")
    source_centers = json.loads((TEMPLATE / "mesh_centers.json").read_text())
    source_tree = ET.parse(TEMPLATE / "kitchen_controlled.sdf")
    source_poses = {obj.findtext("name"): np.array(list(map(float, obj.findtext("pose").split())))
                    for obj in source_tree.findall("./world/include")
                    if obj.findtext("name") in KEYS}
    source_gt = {obj["model_name"]: obj for obj in yaml.safe_load((TEMPLATE / "gt.yaml").read_text())["objects"]
                 if obj["model_name"] in KEYS}
    for room, domain in (("aws", 93), ("tiffany", 94)):
        dest = ROOT / room
        dest.mkdir()
        for directory in ("frames", "db"):
            (dest / directory).mkdir()
        design = json.loads((CROSS / room / "design.json").read_text())
        base = design["camera_xyz_yaw"][:3]
        heading = design["camera_xyz_yaw"][3]
        floor = design["surface_z_m"]
        tree = ET.parse(CROSS / room / "world.sdf")
        world = tree.getroot().find("world")
        world.find("./physics/max_step_size").text = "0.001"
        rig = world.find("./model[@name='camera_rig']")
        # The production TF broadcaster supports a world-aligned camera base.
        # The 360-degree scan still covers the room's original forward view.
        rig.find("pose").text = " ".join(map(str, [*base, 0, 0, 0]))
        cfg = yaml.safe_load((TEMPLATE / "config.yaml").read_text())
        cfg["camera"]["base_xyz"] = base
        cfg["camera"]["floor_z_m"] = floor
        (dest / "config.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False))
        centers = {}
        objects = []
        layout = {"room": room, "camera_pose": [*base, 0, 0, 0],
                  "reference_heading_rad": heading, "floor_z_m": floor,
                  "resource_path": design["resource_path"], "objects": {}}
        for inc in world.findall("include"):
            key = inc.findtext("name")
            if key not in KEYS:
                continue
            forward, lateral = PLACEMENTS[key]
            x = base[0] + forward * math.cos(heading) - lateral * math.sin(heading)
            y = base[1] + forward * math.sin(heading) + lateral * math.cos(heading)
            old_pose = source_poses[key]
            old = source_centers[key]
            local_min_z = old["aabb_min_m"][2] - old_pose[2]
            pose = np.array([x, y, floor - local_min_z, *old_pose[3:]])
            pose[5] = heading
            inc.find("pose").text = " ".join(map(str, pose))
            corners = np.array(list(itertools.product(*zip(old["aabb_min_m"], old["aabb_max_m"]))))
            delta_rot = Rotation.from_euler("z", heading - old_pose[5]).as_matrix()
            corners = (corners - old_pose[:3]) @ delta_rot.T + pose[:3]
            lo, hi = corners.min(axis=0), corners.max(axis=0)
            center = (lo + hi) / 2
            assert abs(lo[2] - floor) < 1e-10
            gt = copy.deepcopy(source_gt[key])
            gt.update(dict(zip("xyz", map(float, center))))
            gt.update(dict(zip(("size_x", "size_y", "size_z"), map(float, hi - lo))))
            objects.append(gt)
            centers[key] = dict(method="Source mesh AABB under translation and 0/90-degree yaw",
                                aabb_min_m=lo.tolist(), aabb_max_m=hi.tolist(),
                                mesh_aabb_center_world_m=center.tolist(),
                                yaml_ref_world_m=center.tolist(), center_minus_yaml_m=[0., 0., 0.])
            layout["objects"][key] = dict(pose=pose.tolist(), center=center.tolist(),
                                          floor_clearance_m=float(lo[2]-floor),
                                          forward_m=forward, lateral_m=lateral)
        assert set(centers) == set(KEYS)
        for a, b in itertools.combinations(KEYS, 2):
            lower = np.maximum(centers[a]["aabb_min_m"], centers[b]["aabb_min_m"])
            upper = np.minimum(centers[a]["aabb_max_m"], centers[b]["aabb_max_m"])
            assert not np.all(upper[:2] > lower[:2]), (a, b)
        tree.write(dest / "kitchen_controlled.sdf", encoding="utf-8", xml_declaration=True)
        (dest / "gt.yaml").write_text(yaml.safe_dump({"frame": "world", "objects": objects}, sort_keys=False))
        put(dest / "mesh_centers.json", centers)
        put(dest / "layout.json", layout)
        for file in ("classes.yaml", "locked.json", "locked.sha256", "audit.py", "pose_check.py", "replay.py"):
            shutil.copyfile(TEMPLATE / file, dest / file)
        launch = (TEMPLATE / "reference.launch.py").read_text()
        launch = launch.replace(str(TEMPLATE / "audit.py"), str(dest / "audit.py"))
        launch = launch.replace('models_dir = os.path.join(ws_default, "src", "room_sim", "models")',
                                "models_dir = " + repr(design["resource_path"]))
        launch = launch.replace('"base_xyz": [-1.5, -0.5, 1.1]', '"base_xyz": ' + repr(base))
        (dest / "reference.launch.py").write_text(launch)
        query = (TEMPLATE / "query_live.py").read_text().replace("origin = (-1.5,-.5)", "origin = " + repr(tuple(base[:2])))
        (dest / "query_live.py").write_text(query)
        ready = (TEMPLATE / "run_ready.sh").read_text().replace("ROS_DOMAIN_ID=91", "ROS_DOMAIN_ID=" + str(domain))
        (dest / "run_ready.sh").write_text(ready)
        put(dest / "source.json", {"source_sdf": str(CROSS / room / "world.sdf"),
                                  "source_sdf_sha256": sha(CROSS / room / "world.sdf")})
    shutil.copyfile(PREV / "capture.sh", ROOT / "capture.sh")
    tracked = [ROOT / "orb.py", ROOT / "experiment.py", ROOT / "PLAN.md"]
    tracked += [ROOT / room / name for room in ("aws", "tiffany") for name in
                ("kitchen_controlled.sdf", "config.yaml", "classes.yaml", "gt.yaml", "mesh_centers.json",
                 "layout.json", "audit.py", "reference.launch.py", "replay.py")]
    tracked += [PREV / "orb.py", PREV / "PLAN.md"]
    put(ROOT / "frozen.json", {"utc": datetime.now(timezone.utc).isoformat(),
                              "orb_identical_to_kitchen": sha(ROOT / "orb.py") == sha(PREV / "orb.py"),
                              "files": {str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p): sha(p)
                                        for p in tracked}})
    print("Prepared two independent 18x1 scenes and froze the ORB parameters", flush=True)


if __name__ == "__main__":
    main()
