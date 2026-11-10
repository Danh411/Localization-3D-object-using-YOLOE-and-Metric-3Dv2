"""Object DB node — mục 3.1, 6, W5-A2/A7.

Nhận /db/observations (ObjectObservationArray), ghi observation + gộp vật trùng
(association) vào SQLite. Phục vụ /db/query và /db/approach_point. Một file
sqlite cho mỗi scan_id. Thuần logic nằm trong object_db/* (không ROS).
"""
from __future__ import annotations

import math
import os

import rclpy
import yaml
from rclpy.node import Node
from rclpy.callback_groups import ReentrantCallbackGroup

from scan_interfaces.msg import ObjectObservationArray
from scan_interfaces.srv import QueryObjects, GetApproachPoint, FinalizeScan

from object_db import association, db, queries


class ObjectDbNode(Node):
    def __init__(self):
        super().__init__("object_db")
        self.declare_parameter("config", "")
        self.declare_parameter("db_dir", "data/db")
        self.declare_parameter("world_name", "room")
        self.declare_parameter("gt_config", "")
        cfg_path = self.get_parameter("config").value
        self.cfg = yaml.safe_load(open(cfg_path)) if cfg_path else {}
        self.db_dir = self.get_parameter("db_dir").value
        self.world = self.get_parameter("world_name").value
        gt_path = self.get_parameter("gt_config").value
        self.gt = (yaml.safe_load(open(gt_path)).get("objects", [])
                   if gt_path and os.path.isfile(gt_path) else [])
        self.cam_xy = tuple(self.cfg.get("camera", {}).get("base_xyz", [0, 0])[:2])
        self.assoc_cfg = self.cfg.get("assoc", {})
        self.fusion_cfg = self.cfg.get("fusion", {})
        self.standoff = self.cfg.get("approach", {}).get("standoff_m", 0.6)

        os.makedirs(self.db_dir, exist_ok=True)
        self._conn: dict[str, object] = {}   # scan_id -> sqlite conn

        cb = ReentrantCallbackGroup()
        self.create_subscription(ObjectObservationArray, "/db/observations",
                                 self._on_obs, 10, callback_group=cb)
        self.create_service(QueryObjects, "/db/query", self._on_query, callback_group=cb)
        self.create_service(GetApproachPoint, "/db/approach_point",
                            self._on_approach, callback_group=cb)
        self.create_service(FinalizeScan, "/db/finalize_scan",
                            self._on_finalize, callback_group=cb)
        self.get_logger().info(f"object_db_node sẵn sàng, db_dir={self.db_dir}")

    def _conn_for(self, scan_id: str):
        conn = self._conn.get(scan_id)
        if conn is None:
            path = os.path.join(self.db_dir, f"{scan_id}.sqlite")
            conn = db.open_db(path)
            db.create_scan(conn, scan_id, self.cfg, world_name=self.world,
                           notes="object_db_node live")
            if self.gt:
                db.load_gt_objects(conn, self.gt)
            self._conn[scan_id] = conn
            self.get_logger().info(f"mở DB {path}")
        return conn

    def _on_obs(self, arr: ObjectObservationArray):
        conn = self._conn_for(arr.scan_id)
        for o in arr.observations:
            if any(math.isnan(v) for v in o.p_world):
                continue  # chưa chiếu được world
            obs = {
                "class_name": o.class_name, "confidence": o.confidence,
                "bbox_xyxy": list(o.bbox_xyxy), "truncated": o.truncated,
                "depth_m": o.depth_m, "range_m": o.range_m,
                "valid_depth_ratio": o.valid_depth_ratio,
                "p_cam": list(o.p_cam), "p_world": list(o.p_world),
                "stop_index": o.stop_index, "frame_idx": o.frame_idx,
                "yaw_rad": o.yaw_rad,
                "stamp_ns": o.stamp.sec * 10**9 + o.stamp.nanosec,
            }
            association.add_observation(conn, arr.scan_id, obs,
                                        self.assoc_cfg, self.fusion_cfg)
        self.get_logger().info(
            f"[{arr.scan_id}][stop {arr.stop_index}] ghi {len(arr.observations)} quan sát")

    def finalize(self, scan_id: str):
        conn = self._conn.get(scan_id)
        if conn is not None:
            res = association.run_association_pass(conn, scan_id, self.assoc_cfg)
            db.finish_scan(conn, scan_id)
            self.get_logger().info(
                f"[{scan_id}] hợp nhất {len(res['merged_pairs'])} cặp; "
                f"confirmed={res['confirmed']} rejected={res['rejected']}")
            return res
        return None

    def _on_query(self, req: QueryObjects.Request, resp: QueryObjects.Response):
        # dùng scan mới nhất nếu không chỉ định
        scan = self._latest_scan()
        if not scan:
            return resp
        conn = self._conn[scan]
        for r in queries.query_objects(conn, scan, req.class_name,
                                       req.max_range_m, req.min_observations,
                                       center_xy=self.cam_xy):
            resp.object_id.append(r["object_id"]); resp.class_name.append(r["class_name"])
            resp.x.append(r["x"]); resp.y.append(r["y"]); resp.z.append(r["z"])
            resp.confidence.append(float(r["conf_mean"]))
            resp.n_observations.append(r["n_obs"])
        return resp

    def _on_approach(self, req: GetApproachPoint.Request,
                     resp: GetApproachPoint.Response):
        scan = self._latest_scan()
        if not scan:
            resp.success = False; return resp
        conn = self._conn[scan]
        r = queries.get_approach_point(conn, req.object_id, self.cam_xy,
                                       req.standoff_m or self.standoff)
        if r is None:
            resp.success = False; return resp
        resp.success = True
        resp.x, resp.y, resp.yaw_rad = r["x"], r["y"], r["yaw_rad"]
        resp.already_close = bool(r["already_close"])
        return resp

    def _on_finalize(self, req: FinalizeScan.Request, resp: FinalizeScan.Response):
        conn = self._conn.get(req.scan_id)
        if conn is None:
            resp.success = False
            return resp
        res = association.run_association_pass(conn, req.scan_id, self.assoc_cfg)
        db.finish_scan(conn, req.scan_id)
        self.get_logger().info(
            f"[{req.scan_id}] finalize: merged={len(res['merged_pairs'])} "
            f"confirmed={res['confirmed']} rejected={res['rejected']}")
        resp.success = True
        resp.confirmed = int(res["confirmed"])
        resp.rejected = int(res["rejected"])
        resp.merged_pairs = len(res["merged_pairs"])
        return resp

    def _latest_scan(self):
        rows = None
        # scan_id mới nhất theo conn đã mở; fallback đọc file DB mới nhất
        if self._conn:
            rows = sorted(self._conn.keys())[-1]
        return rows

    def destroy_node(self):
        for c in self._conn.values():
            try:
                c.close()
            except Exception:
                pass
        super().destroy_node()


def main():
    rclpy.init()
    node = ObjectDbNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
