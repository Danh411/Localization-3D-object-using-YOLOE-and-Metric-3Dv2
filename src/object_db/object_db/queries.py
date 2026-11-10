"""Truy vấn tối thiểu (cuối mục 6): theo lớp, gần điểm nhất, trong bán kính,
thống kê số quan sát. Phục vụ cho service /db/query và tools/query_db.py.
Mặc định chỉ trả vật confirmed (vật rejected vẫn giữ trong DB)."""
from __future__ import annotations

import math
import sqlite3

from .approach import approach_point


def list_objects(conn: sqlite3.Connection, scan_id: str,
                 class_name: str | None = None,
                 status: str = "confirmed") -> list[sqlite3.Row]:
    q = "SELECT * FROM objects WHERE scan_id=?"
    args: list = [scan_id]
    if status:
        q += " AND status=?"; args.append(status)
    if class_name:
        q += " AND class_name=?"; args.append(class_name)
    q += " ORDER BY class_name, object_id"
    return conn.execute(q, args).fetchall()


def nearest_object(conn: sqlite3.Connection, scan_id: str, x: float, y: float,
                   class_name: str | None = None,
                   status: str = "confirmed") -> sqlite3.Row | None:
    best, best_d = None, float("inf")
    for o in list_objects(conn, scan_id, class_name, status):
        d = math.hypot(o["x"] - x, o["y"] - y)
        if d < best_d:
            best, best_d = o, d
    return best


def objects_in_radius(conn: sqlite3.Connection, scan_id: str, x: float, y: float,
                      radius_m: float, class_name: str | None = None,
                      status: str = "confirmed") -> list[sqlite3.Row]:
    return [o for o in list_objects(conn, scan_id, class_name, status)
            if math.hypot(o["x"] - x, o["y"] - y) <= radius_m]


def obs_stats_by_class(conn: sqlite3.Connection, scan_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT class_name, COUNT(*) AS n_obs, COUNT(DISTINCT object_id) AS n_objects
           FROM observations WHERE scan_id=? GROUP BY class_name ORDER BY class_name""",
        (scan_id,)).fetchall()


def query_objects(conn: sqlite3.Connection, scan_id: str,
                  class_name: str = "", max_range_m: float = 0.0,
                  min_observations: int = 1,
                  center_xy: tuple[float, float] | None = None,
                  status: str = "confirmed") -> list[dict]:
    """Tương ứng QueryObjects.srv: class_name rỗng = tất cả; max_range_m = 0 là
    không giới hạn (đo từ center_xy, mặc định gốc world)."""
    cx, cy = center_xy or (0.0, 0.0)
    out = []
    for o in list_objects(conn, scan_id, class_name or None, status):
        if int(o["n_obs"]) < min_observations:
            continue
        r = math.hypot(o["x"] - cx, o["y"] - cy)
        if max_range_m and r > max_range_m:
            continue
        out.append({"object_id": o["object_id"], "class_name": o["class_name"],
                    "x": o["x"], "y": o["y"], "z": o["z"],
                    "conf_mean": o["conf_mean"], "n_obs": o["n_obs"],
                    "range_m": r})
    return out


def get_approach_point(conn: sqlite3.Connection, object_id: int,
                       cam_xy: tuple[float, float],
                       standoff_m: float = 0.6) -> dict | None:
    """Tương ứng GetApproachPoint.srv. None nếu object_id không tồn tại."""
    o = conn.execute("SELECT x, y FROM objects WHERE object_id=?",
                     (object_id,)).fetchone()
    if o is None:
        return None
    return approach_point((o["x"], o["y"]), cam_xy, standoff_m)
