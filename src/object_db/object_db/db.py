"""Tầng SQLite mỏng (mục 6). Một file .sqlite cho mỗi lần quét; khóa ngoại bật.
Không phụ thuộc ROS. Thời gian ISO-8601 UTC; tham số lấy từ config khi gọi."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = Path(__file__).with_name("schema.sql")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def config_hash(cfg) -> str:
    """SHA-256 rút gọn của cấu hình đã chuẩn hóa (phục vụ tái lập, mục 2.4)."""
    blob = json.dumps(cfg, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def git_commit(root: str | Path | None = None) -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                             text=True, cwd=str(root) if root else None, timeout=10)
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def open_db(path: str | Path) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    return conn


def new_scan_id(seed: int = 42, when: datetime | None = None) -> str:
    t = when or datetime.now()
    return f"scan_{t:%Y%m%d_%H%M%S}_{seed}"


def create_scan(conn: sqlite3.Connection, scan_id: str, cfg: dict,
                world_name: str = "", notes: str = "",
                git_root: str | Path | None = None) -> None:
    c = cfg.get("camera", {}); s = cfg.get("scan", {})
    x, y, z = (c.get("base_xyz") or [None, None, None])[:3]
    conn.execute(
        """INSERT INTO scans (scan_id, started_at, world_name, notes,
             cam_x, cam_y, cam_z, hfov_deg, img_w, img_h, step_deg,
             frames_per_stop, config_hash, git_commit)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (scan_id, utcnow(), world_name, notes, x, y, z,
         c.get("hfov_deg"), c.get("width"), c.get("height"),
         s.get("step_deg"), s.get("frames_per_stop"),
         config_hash(cfg), git_commit(git_root)))
    conn.commit()


def finish_scan(conn: sqlite3.Connection, scan_id: str) -> None:
    conn.execute("UPDATE scans SET finished_at=? WHERE scan_id=?",
                 (utcnow(), scan_id))
    conn.commit()


def insert_object(conn: sqlite3.Connection, scan_id: str, class_name: str,
                  x: float, y: float, z: float, weight: float, conf: float,
                  stop_index: int, seen_untruncated: int) -> int:
    now = utcnow()
    cur = conn.execute(
        """INSERT INTO objects (scan_id, class_name, x, y, z, weight_sum, n_obs,
             conf_sum, conf_mean, first_seen_stop, last_seen_stop,
             seen_untruncated, status, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'tentative', ?,?)""",
        (scan_id, class_name, x, y, z, weight, 1, conf, conf,
         stop_index, stop_index, int(bool(seen_untruncated)), now, now))
    conn.commit()
    return int(cur.lastrowid)


def update_object(conn: sqlite3.Connection, object_id: int,
                  x: float, y: float, z: float, weight: float,
                  conf_sum: float, n_obs: int, stop_index: int,
                  seen_untruncated: int) -> None:
    """Cập nhật vật sau khi gộp thêm một quan sát (vị trí/độ tin cậy đã tính)."""
    row = conn.execute(
        "SELECT first_seen_stop, last_seen_stop, seen_untruncated FROM objects WHERE object_id=?",
        (object_id,)).fetchone()
    first = min(row["first_seen_stop"], stop_index) if row["first_seen_stop"] is not None else stop_index
    last = max(row["last_seen_stop"], stop_index) if row["last_seen_stop"] is not None else stop_index
    seen = int(bool(row["seen_untruncated"] or seen_untruncated))
    conn.execute(
        """UPDATE objects SET x=?, y=?, z=?, weight_sum=?, n_obs=?, conf_sum=?, conf_mean=?,
             first_seen_stop=?, last_seen_stop=?, seen_untruncated=?, updated_at=?
           WHERE object_id=?""",
        (x, y, z, weight, n_obs, conf_sum, conf_sum / n_obs, first, last, seen, utcnow(), object_id))
    conn.commit()


def insert_observation(conn: sqlite3.Connection, scan_id: str, object_id,
                       obs: dict) -> int:
    """obs: dict các trường class_name, confidence, bbox_xyxy, truncated,
    depth_m, range_m, valid_depth_ratio, p_cam, p_world, stop_index, frame_idx,
    yaw_rad, stamp_ns."""
    b = obs.get("bbox_xyxy") or [None] * 4
    p_cam = obs.get("p_cam") or [None] * 3
    p_world = obs.get("p_world") or [None] * 3
    cur = conn.execute(
        """INSERT INTO observations (scan_id, object_id, stop_index, frame_idx,
             class_name, confidence, bbox_x1, bbox_y1, bbox_x2, bbox_y2,
             truncated, depth_m, range_m, valid_ratio,
             cam_x, cam_y, cam_z, world_x, world_y, world_z, yaw_rad, stamp_ns)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (scan_id, object_id, obs.get("stop_index"), obs.get("frame_idx"),
         obs.get("class_name"), obs.get("confidence"), b[0], b[1], b[2], b[3],
         int(bool(obs.get("truncated"))), obs.get("depth_m"), obs.get("range_m"),
         obs.get("valid_depth_ratio"), p_cam[0], p_cam[1], p_cam[2],
         p_world[0], p_world[1], p_world[2], obs.get("yaw_rad"), obs.get("stamp_ns")))
    conn.commit()
    return int(cur.lastrowid)


def set_object_status(conn: sqlite3.Connection, object_id: int, status: str) -> None:
    conn.execute("UPDATE objects SET status=?, updated_at=? WHERE object_id=?",
                 (status, utcnow(), object_id))
    conn.commit()


def link_observation_object(conn: sqlite3.Connection, obs_id: int, object_id: int) -> None:
    conn.execute("UPDATE observations SET object_id=? WHERE obs_id=?",
                 (object_id, obs_id))
    conn.commit()


def fetch_objects(conn: sqlite3.Connection, scan_id: str,
                  status: str | None = None) -> list[sqlite3.Row]:
    q = "SELECT * FROM objects WHERE scan_id=?"
    args: list = [scan_id]
    if status:
        q += " AND status=?"; args.append(status)
    return conn.execute(q, args).fetchall()


def fetch_object(conn: sqlite3.Connection, object_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM objects WHERE object_id=?",
                        (object_id,)).fetchone()


def fetch_observations_of_object(conn: sqlite3.Connection, object_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM observations WHERE object_id=? ORDER BY obs_id",
        (object_id,)).fetchall()


def load_gt_objects(conn: sqlite3.Connection, gt_list: list[dict]) -> int:
    """Nạp bảng gt_objects từ config/gt_objects.yaml (danh sách dict). Trả số dòng."""
    conn.execute("DELETE FROM gt_objects")
    for o in gt_list:
        conn.execute(
            """INSERT INTO gt_objects (model_name, class_name, x, y, z,
                 size_x, size_y, size_z) VALUES (?,?,?,?,?,?,?,?)""",
            (o.get("model_name"), o.get("class_name"), o.get("x"), o.get("y"),
             o.get("z"), o.get("size_x"), o.get("size_y"), o.get("size_z")))
    conn.commit()
    return len(gt_list)
