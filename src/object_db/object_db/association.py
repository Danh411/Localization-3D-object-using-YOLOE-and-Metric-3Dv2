"""Gộp vật trùng giữa các góc và các khung — mục 5.6 (A6).

Trọng số quan sát: w = s / max(r, range_floor)^2 ; nhân truncated_weight nếu bị cắt biên.
Luồng: ghi observation -> tìm vật cùng lớp gần nhất trong radius_m -> cập nhật trung bình
có trọng số; không có và conf >= min_conf_to_create thì tạo vật mới (tentative).
Sau quét: hợp nhất cặp cùng lớp < merge_radius_m (xử lý cả vòng 360°: điểm dừng cuối
và đầu nhìn cùng một vật) rồi chốt trạng thái confirmed/rejected theo min_obs.

Thuần Python trên sqlite3; không phụ thuộc ROS.
"""
from __future__ import annotations

import math
import sqlite3

from . import db


def obs_weight(confidence: float, range_m: float, truncated: bool,
               range_floor_m: float = 0.5, truncated_weight: float = 0.3) -> float:
    """w = s / max(r, sàn)^2, nhân thêm truncated_weight nếu vật bị cắt biên."""
    r = max(float(range_m), float(range_floor_m))
    w = float(confidence) / (r * r)
    return w * float(truncated_weight) if truncated else w


def _same_class_objects(conn: sqlite3.Connection, scan_id: str, class_name: str):
    return conn.execute(
        """SELECT object_id, x, y, z, weight_sum, n_obs, conf_sum
           FROM objects WHERE scan_id=? AND class_name=? AND status != 'rejected'""",
        (scan_id, class_name)).fetchall()


def _nearest(p, candidates, radius_m: float):
    """Vật gần nhất theo khoảng cách 3D; None nếu xa hơn radius_m."""
    best, best_d = None, float(radius_m)
    for o in candidates:
        d = math.dist(p, (o["x"], o["y"], o["z"]))
        if d < best_d:
            best, best_d = o, d
    return best


def add_observation(conn: sqlite3.Connection, scan_id: str, obs: dict,
                    assoc_cfg: dict, fusion_cfg: dict | None = None) -> dict:
    """Ghi một quan sát và gộp vào vật. obs cần: class_name, confidence,
    p_world (3), range_m, truncated; thêm bbox_xyxy, depth_m, valid_depth_ratio,
    p_cam, stop_index, frame_idx, yaw_rad, stamp_ns nếu có.
    Trả dict {object_id, created(bool), weight}."""
    fu = fusion_cfg or {}
    radius = assoc_cfg.get("radius_m", 0.35)
    min_conf_create = assoc_cfg.get("min_conf_to_create", 0.4)
    floor_m = fu.get("range_floor_m", 0.5)
    trunc_w = fu.get("truncated_weight", 0.3)

    cls = obs["class_name"]; p = tuple(float(v) for v in obs["p_world"])
    conf = float(obs.get("confidence", 0.0))
    w = obs_weight(conf, float(obs.get("range_m", floor_m)),
                   bool(obs.get("truncated")), floor_m, trunc_w)
    stop = obs.get("stop_index")
    untrunc = 0 if obs.get("truncated") else 1

    cand = _nearest(p, _same_class_objects(conn, scan_id, cls), radius)
    if cand is not None:
        oid = cand["object_id"]
        W = float(cand["weight_sum"])
        nx = (W * cand["x"] + w * p[0]) / (W + w)
        ny = (W * cand["y"] + w * p[1]) / (W + w)
        nz = (W * cand["z"] + w * p[2]) / (W + w)
        conf_sum = float(cand["conf_sum"]) + conf
        n = int(cand["n_obs"]) + 1
        db.update_object(conn, oid, nx, ny, nz, W + w, conf_sum, n,
                         stop if stop is not None else 0, untrunc)
        created = False
    elif conf >= min_conf_create:
        oid = db.insert_object(conn, scan_id, cls, p[0], p[1], p[2], w, conf,
                               stop if stop is not None else 0, untrunc)
        created = True
    else:
        oid = None
        created = False

    obs_id = db.insert_observation(conn, scan_id, oid, obs)
    return {"object_id": oid, "obs_id": obs_id, "created": created, "weight": w}


def merge_duplicates(conn: sqlite3.Connection, scan_id: str,
                     merge_radius_m: float = 0.25) -> list[tuple[int, int]]:
    """Gộp lần lượt các cặp vật cùng lớp cách nhau < merge_radius_m.
    Vật nguồn được gộp vào vật nặng hơn (weight_sum lớn hơn) rồi đổi trạng thái
    thành 'rejected' (giữ trong DB, không trả về truy vấn mặc định).
    Trả danh sách (object_id bị gộp, object_id giữ lại)."""
    merged: list[tuple[int, int]] = []
    while True:
        rows = conn.execute(
            """SELECT object_id, class_name, x, y, z, weight_sum, n_obs, conf_sum,
                      seen_untruncated, first_seen_stop, last_seen_stop
                 FROM objects WHERE scan_id=? AND status != 'rejected'
                 ORDER BY object_id""", (scan_id,)).fetchall()
        pair = None
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                a, b = rows[i], rows[j]
                if a["class_name"] != b["class_name"]:
                    continue
                if math.dist((a["x"], a["y"], a["z"]),
                             (b["x"], b["y"], b["z"])) < merge_radius_m:
                    pair = (a, b)
                    break
            if pair:
                break
        if pair is None:
            return merged
        a, b = pair
        keep, drop = (a, b) if a["weight_sum"] >= b["weight_sum"] else (b, a)
        W = float(keep["weight_sum"]) + float(drop["weight_sum"])
        nx = (keep["weight_sum"] * keep["x"] + drop["weight_sum"] * drop["x"]) / W
        ny = (keep["weight_sum"] * keep["y"] + drop["weight_sum"] * drop["y"]) / W
        nz = (keep["weight_sum"] * keep["z"] + drop["weight_sum"] * drop["z"]) / W
        n = int(keep["n_obs"]) + int(drop["n_obs"])
        conf_sum = float(keep["conf_sum"]) + float(drop["conf_sum"])
        first = min(keep["first_seen_stop"] or 0, drop["first_seen_stop"] or 0)
        last = max(keep["last_seen_stop"] or 0, drop["last_seen_stop"] or 0)
        seen = int(bool(keep["seen_untruncated"] or drop["seen_untruncated"]))
        conn.execute(
            """UPDATE objects SET x=?,y=?,z=?,weight_sum=?,n_obs=?,conf_sum=?,conf_mean=?,
                 first_seen_stop=?,last_seen_stop=?,seen_untruncated=?,updated_at=?
               WHERE object_id=?""",
            (nx, ny, nz, W, n, conf_sum, conf_sum / n, first, last, seen, db.utcnow(),
             keep["object_id"]))
        conn.execute(
            "UPDATE observations SET object_id=? WHERE object_id=?",
            (keep["object_id"], drop["object_id"]))
        conn.execute("UPDATE objects SET status='rejected', updated_at=? WHERE object_id=?",
                     (db.utcnow(), drop["object_id"]))
        conn.commit()
        merged.append((drop["object_id"], keep["object_id"]))


def finalize_statuses(conn: sqlite3.Connection, scan_id: str,
                      min_obs: int = 3) -> dict:
    """confirmed nếu n_obs >= min_obs và có ít nhất một quan sát không truncated;
    còn lại rejected. Trả {'confirmed': n, 'rejected': n}."""
    rows = conn.execute(
        "SELECT object_id, n_obs, seen_untruncated, status FROM objects "
        "WHERE scan_id=? AND status != 'rejected'", (scan_id,)).fetchall()
    counts = {"confirmed": 0, "rejected": 0}
    for r in rows:
        ok = int(r["n_obs"]) >= min_obs and int(r["seen_untruncated"]) >= 1
        db.set_object_status(conn, r["object_id"], "confirmed" if ok else "rejected")
        counts["confirmed" if ok else "rejected"] += 1
    return counts


def run_association_pass(conn: sqlite3.Connection, scan_id: str,
                         assoc_cfg: dict) -> dict:
    """Bước hợp nhất + chốt trạng thái sau khi quét xong (cuối mục 5.6)."""
    merged = merge_duplicates(conn, scan_id, assoc_cfg.get("merge_radius_m", 0.25))
    counts = finalize_statuses(conn, scan_id, assoc_cfg.get("min_obs", 3))
    return {"merged_pairs": merged, **counts}
