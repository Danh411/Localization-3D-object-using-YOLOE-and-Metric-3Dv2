#!/usr/bin/env python3
"""Truy vấn database vật thể của một lần quét (cuối mục 6 + service /db/query).

  python3 tools/query_db.py data/db/<scan_id>.sqlite --all
  python3 tools/query_db.py data/db/<scan_id>.sqlite --class bottle
  python3 tools/query_db.py data/db/<scan_id>.sqlite --near 3.0 2.9 --radius 1.0
  python3 tools/query_db.py data/db/<scan_id>.sqlite --stats
  python3 tools/query_db.py data/db/<scan_id>.sqlite --approach 3 --cam 2.0 2.0
"""
import argparse
import os
import sqlite3
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "src", "object_db"))
from object_db import queries  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("db")
    p.add_argument("--scan", default=None, help="scan_id; mặc định lấy scan mới nhất")
    p.add_argument("--all", action="store_true", help="liệt kê mọi vật confirmed")
    p.add_argument("--tentative", action="store_true", help="kể cả vật tentative")
    p.add_argument("--class", dest="cls", default=None, help="lọc theo lớp")
    p.add_argument("--near", nargs=2, type=float, metavar=("X", "Y"),
                   help="vật gần điểm (x,y) nhất (mặt phẳng ngang)")
    p.add_argument("--radius", type=float, default=None,
                   help="kết hợp --near: liệt kê vật trong bán kính")
    p.add_argument("--stats", action="store_true", help="thống kê số quan sát theo lớp")
    p.add_argument("--approach", type=int, metavar="OBJECT_ID",
                   help="điểm tiếp cận của vật (cần --cam hoặc lấy từ scan)")
    p.add_argument("--cam", nargs=2, type=float, metavar=("X", "Y"),
                   help="vị trí camera x,y (mặc định lấy từ scan.cam_x/cam_y)")
    p.add_argument("--standoff", type=float, default=0.6)
    a = p.parse_args()

    conn = sqlite3.connect(a.db); conn.row_factory = sqlite3.Row
    scan = a.scan
    if not scan:
        row = conn.execute(
            "SELECT scan_id FROM scans ORDER BY started_at DESC LIMIT 1").fetchone()
        if not row:
            print("Không có scan nào trong DB"); return 1
        scan = row["scan_id"]
        print(f"[scan mới nhất] {scan}")
    status = None if a.tentative else "confirmed"

    if a.stats:
        print("\n== Số quan sát theo lớp ==")
        for r in queries.obs_stats_by_class(conn, scan):
            print(f"  {r['class_name']:14s} obs={r['n_obs']:3d}  objects={r['n_objects']}")

    if a.all or (a.cls and not a.near and not a.radius):
        print(f"\n== Vật ({status or 'mọi trạng thái'}) ==")
        rows = queries.list_objects(conn, scan, a.cls, status)
        if not rows:
            print("  (trống)")
        for o in rows:
            print(f"  id={o['object_id']:3d} {o['class_name']:13s} "
                  f"({o['x']:5.2f},{o['y']:5.2f},{o['z']:5.2f}) "
                  f"n_obs={o['n_obs']} conf={o['conf_mean']:.2f} status={o['status']}")

    if a.near:
        x, y = a.near
        if a.radius is not None:
            print(f"\n== Vật trong bán kính {a.radius} m quanh ({x},{y}) ==")
            for o in queries.objects_in_radius(conn, scan, x, y, a.radius, a.cls, status):
                print(f"  id={o['object_id']:3d} {o['class_name']:13s} "
                      f"({o['x']:.2f},{o['y']:.2f}) n_obs={o['n_obs']}")
        else:
            o = queries.nearest_object(conn, scan, x, y, a.cls, status)
            print("\n== Vật gần nhất ==")
            print("  (trống)" if not o else
                  f"  id={o['object_id']} {o['class_name']} ({o['x']:.2f},{o['y']:.2f},{o['z']:.2f})")

    if a.approach is not None:
        cam = a.cam
        if cam is None:
            srow = conn.execute("SELECT cam_x, cam_y FROM scans WHERE scan_id=?",
                                (scan,)).fetchone()
            cam = (srow["cam_x"], srow["cam_y"]) if srow else (0.0, 0.0)
        r = queries.get_approach_point(conn, a.approach, cam, a.standoff)
        print(f"\n== Điểm tiếp cận object {a.approach} (standoff {a.standoff} m) ==")
        if r is None:
            print("  không tồn tại object_id")
        else:
            print(f"  đứng tại ({r['x']:.3f},{r['y']:.3f})  yaw={r['yaw_rad']:.3f} rad"
                  + ("  [already_close]" if r["already_close"] else ""))
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
