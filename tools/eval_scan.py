#!/usr/bin/env python3
"""Đánh giá một file DB scan so với ground truth — mục 9 (eval_tools).

Ghép GT <-> vật confirmed bằng thuật toán Hungarian trên khoảng cách XY, chỉ cùng
lớp và khoảng cách < eval.match_radius_m. Tính e_xy, e_3d, recall, precision,
dup_rate, fp_rate theo mục 9.1.

  python3 tools/eval_scan.py data/db/<scan_id>.sqlite --gt config/gt_objects.yaml
"""
import argparse
import math
import os
import sqlite3
import sys

import yaml

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "src", "object_db"))


def hungarian_match(gt, objs, match_radius_m):
    """Ghép tối ưu GT<->object. Trả (matches, unmatched_gt, unmatched_obj).
    Mỗi match: (gt_index, obj, e_xy, e_3d)."""
    try:
        import numpy as np
        from scipy.optimize import linear_sum_assignment
        C = np.full((len(gt), len(objs)), 1e9)
        for i, g in enumerate(gt):
            for j, o in enumerate(objs):
                if g["class_name"] != o["class_name"]:
                    continue
                d = math.hypot(g["x"] - o["x"], g["y"] - o["y"])
                if d < match_radius_m:
                    C[i, j] = d
        ri, ci = linear_sum_assignment(C)
        matches, used_g, used_o = [], set(), set()
        for i, j in zip(ri, ci):
            if C[i, j] >= 1e8:
                continue
            g, o = gt[i], objs[j]
            e_xy = math.hypot(g["x"] - o["x"], g["y"] - o["y"])
            e_3d = math.dist((g["x"], g["y"], g["z"]), (o["x"], o["y"], o["z"]))
            matches.append((i, o, e_xy, e_3d))
            used_g.add(i); used_o.add(j)
        return (matches, [i for i in range(len(gt)) if i not in used_g],
                [objs[j] for j in range(len(objs)) if j not in used_o])
    except ImportError:
        # Greedy fallback khi thiếu scipy: ghép cặp cùng lớp gần nhất trước.
        pairs = []
        for i, g in enumerate(gt):
            for j, o in enumerate(objs):
                if g["class_name"] == o["class_name"]:
                    d = math.hypot(g["x"] - o["x"], g["y"] - o["y"])
                    if d < match_radius_m:
                        pairs.append((d, i, j))
        pairs.sort()
        used_g, used_o, matches = set(), set(), []
        for d, i, j in pairs:
            if i in used_g or j in used_o:
                continue
            g, o = gt[i], objs[j]
            e_3d = math.dist((g["x"], g["y"], g["z"]), (o["x"], o["y"], o["z"]))
            matches.append((i, o, d, e_3d))
            used_g.add(i); used_o.add(j)
        return (matches, [i for i in range(len(gt)) if i not in used_g],
                [objs[j] for j in range(len(objs)) if j not in used_o])


def evaluate(db_path, gt_list, match_radius_m=0.5, scan=None, status="confirmed"):
    from object_db import queries
    conn = sqlite3.connect(db_path); conn.row_factory = sqlite3.Row
    scan = scan or conn.execute(
        "SELECT scan_id FROM scans ORDER BY started_at DESC LIMIT 1").fetchone()["scan_id"]
    objs = queries.list_objects(conn, scan, None, status)
    conn.close()

    matches, miss_idx, leftover = hungarian_match(gt_list, objs, match_radius_m)
    n_gt, n_conf = len(gt_list), len(objs)
    e_xy = [m[2] for m in matches]; e_3d = [m[3] for m in matches]
    e_xy_sorted = sorted(e_xy)
    med = e_xy_sorted[len(e_xy_sorted) // 2] if e_xy_sorted else None
    p90 = e_xy_sorted[min(len(e_xy_sorted) - 1,
                          math.ceil(0.9 * len(e_xy_sorted)) - 1)] if e_xy_sorted else None
    matched_oids = {m[1]["object_id"] for m in matches}
    dups = [o for o in leftover
            if any(g["class_name"] == o["class_name"] and
                   math.hypot(g["x"] - o["x"], g["y"] - o["y"]) < match_radius_m
                   for i, g in enumerate(gt_list) if i not in miss_idx)]
    # FP là detection ngoài bán kính của MỌI GT; duplicate là detection dư
    # gần một GT đã ghép. Không gộp hai định nghĩa này thành một chỉ số.
    fps = [o for o in leftover
           if not any(g["class_name"] == o["class_name"] and
                      math.hypot(g["x"] - o["x"], g["y"] - o["y"]) < match_radius_m
                      for g in gt_list)]
    return {
        "scan_id": scan, "n_gt": n_gt, "n_confirmed": n_conf,
        "n_matched": len(matches),
        "e_xy_median_m": med, "e_xy_p90_m": p90,
        "e_xy_mean_m": (sum(e_xy) / len(e_xy)) if e_xy else None,
        "e_3d_mean_m": (sum(e_3d) / len(e_3d)) if e_3d else None,
        "recall": len(matches) / n_gt if n_gt else None,
        "precision": len(matches) / n_conf if n_conf else None,
        "dup_rate": len(dups) / n_gt if n_gt else None,
        "fp_rate": len(fps) / n_gt if n_gt else None,
        "matches": [{"gt": gt_list[i]["model_name"], "object_id": m["object_id"],
                     "class": m["class_name"], "e_xy": exy, "e_3d": e3}
                    for (i, m, exy, e3) in matches],
        "missed_gt": [gt_list[i]["model_name"] for i in miss_idx],
        "duplicate_objects": [{"object_id": o["object_id"],
                               "class": o["class_name"]} for o in dups],
        "unmatched_objects": [{"object_id": o["object_id"],
                               "class": o["class_name"]} for o in leftover],
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("db")
    p.add_argument("--gt", default=os.path.join(ROOT, "config", "gt_objects.yaml"))
    p.add_argument("--scan", default=None)
    p.add_argument("--match-radius", type=float, default=0.5)
    p.add_argument("--status", default="confirmed")
    a = p.parse_args()
    gt = yaml.safe_load(open(a.gt)).get("objects", [])
    r = evaluate(a.db, gt, a.match_radius, a.scan, a.status)

    print(f"scan={r['scan_id']}  GT={r['n_gt']}  confirmed={r['n_confirmed']}  matched={r['n_matched']}")
    f = lambda v: "n/a" if v is None else f"{v:.3f}"
    print(f"  e_xy median={f(r['e_xy_median_m'])}m  p90={f(r['e_xy_p90_m'])}m  mean={f(r['e_xy_mean_m'])}m")
    print(f"  e_3d mean={f(r['e_3d_mean_m'])}m")
    print(f"  recall={f(r['recall'])}  precision={f(r['precision'])}")
    print(f"  dup_rate={f(r['dup_rate'])}  fp_rate={f(r['fp_rate'])}")
    print("\n  -- ghép (GT -> object) --")
    for m in r["matches"]:
        print(f"    {m['gt']:12s} -> id={m['object_id']:3d} {m['class']:12s} e_xy={m['e_xy']:.3f} e_3d={m['e_3d']:.3f}")
    if r["missed_gt"]:
        print("  -- GT không ghép được --")
        for name in r["missed_gt"]:
            print(f"    {name}")
    if r["unmatched_objects"]:
        print("  -- vật confirmed không thuộc GT (dup/fp) --")
        for o in r["unmatched_objects"]:
            print(f"    id={o['object_id']} {o['class']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
