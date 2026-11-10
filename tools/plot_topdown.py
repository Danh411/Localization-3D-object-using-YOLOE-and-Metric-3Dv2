#!/usr/bin/env python3
"""Bản đồ top-down: vị trí GT và vật ước lượng từ DB (W4-A2, W5-B3).

  python3 tools/plot_topdown.py data/db/<scan_id>.sqlite --out data/eval/topdown.png
  python3 tools/plot_topdown.py data/db/<scan_id>.sqlite --gt config/gt_objects.yaml \
      --cam 2.0 2.0 --errors --out topdown.png
Không có matplotlib thì vẫn in bảng tọa độ (không vẽ)."""
import argparse
import math
import os
import sqlite3
import sys

import yaml

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "src", "object_db"))
from object_db import queries  # noqa: E402


def load_gt(path):
    if not path or not os.path.isfile(path):
        return []
    return yaml.safe_load(open(path)).get("objects", [])


def nearest_gt(x, y, gt):
    best, best_d = None, float("inf")
    for g in gt:
        d = math.hypot(g["x"] - x, g["y"] - y)
        if d < best_d:
            best, best_d = g, d
    return best, best_d


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("db")
    p.add_argument("--scan", default=None)
    p.add_argument("--gt", default=os.path.join(ROOT, "config", "gt_objects.yaml"))
    p.add_argument("--cam", nargs=2, type=float, default=None, metavar=("X", "Y"))
    p.add_argument("--errors", action="store_true",
                   help="vẽ mũi tên sai số GT->ước lượng")
    p.add_argument("--status", default="confirmed")
    p.add_argument("--out", default=None, help="file ảnh đầu ra (.png). Bỏ trống = chỉ in bảng")
    a = p.parse_args()

    conn = sqlite3.connect(a.db); conn.row_factory = sqlite3.Row
    scan = a.scan or conn.execute(
        "SELECT scan_id FROM scans ORDER BY started_at DESC LIMIT 1").fetchone()["scan_id"]
    srow = conn.execute("SELECT cam_x, cam_y FROM scans WHERE scan_id=?",
                        (scan,)).fetchone()
    cam = tuple(a.cam) if a.cam else (srow["cam_x"], srow["cam_y"]) if srow else (0.0, 0.0)
    objs = queries.list_objects(conn, scan, None, a.status)
    gt = load_gt(a.gt)
    conn.close()

    print(f"scan={scan}  vật={len(objs)}  GT={len(gt)}  camera={cam}")
    print(f"{'id':>4} {'class':13s} {'x':>6} {'y':>6} {'z':>6} {'n_obs':>5} {'err_xy(GT)':>10}")
    for o in objs:
        g, d = nearest_gt(o["x"], o["y"], gt)
        tag = f"{d:9.3f}m" if g else ""
        print(f"{o['object_id']:4d} {o['class_name']:13s} {o['x']:6.2f} {o['y']:6.2f} "
              f"{o['z']:6.2f} {o['n_obs']:5d} {tag}")

    if not a.out:
        return 0
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:  # noqa: BLE001
        print(f"(không vẽ được: {e}); đã in bảng ở trên")
        return 0

    fig, ax = plt.subplots(figsize=(8, 7))
    if gt:
        ax.scatter([g["x"] for g in gt], [g["y"] for g in gt],
                   marker="x", s=70, c="gray", label="ground truth", zorder=3)
        for g in gt:
            ax.annotate(g["class_name"], (g["x"], g["y"]),
                        textcoords="offset points", xytext=(4, 4), fontsize=7, color="gray")
    for o in objs:
        ax.scatter([o["x"]], [o["y"]], s=60, zorder=4)
        ax.annotate(f"{o['class_name']}#{o['object_id']} ({o['n_obs']})",
                    (o["x"], o["y"]), textcoords="offset points",
                    xytext=(4, -10), fontsize=7)
        if a.errors and gt:
            g, _ = nearest_gt(o["x"], o["y"], gt)
            if g:
                ax.annotate("", xy=(o["x"], o["y"]), xytext=(g["x"], g["y"]),
                            arrowprops=dict(arrowstyle="->", color="red", lw=1, alpha=0.6))
    ax.scatter([cam[0]], [cam[1]], marker="^", s=140, c="black",
               label="camera", zorder=5)
    ax.set_aspect("equal"); ax.grid(True, alpha=0.3)
    ax.set_xlabel("x (m)"); ax.set_ylabel("y (m)")
    ax.set_title(f"Top-down {a.status} — {scan}")
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout(); fig.savefig(a.out, dpi=140)
    print("Đã lưu", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
