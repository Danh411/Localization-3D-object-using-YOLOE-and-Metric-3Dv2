"""W5-A2: schema, ghi observation/object, truy vấn theo lớp/bán kính, FK bật."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "object_db"))
from object_db import db, queries  # noqa: E402

CFG = {"camera": {"base_xyz": [2.0, 2.0, 1.2], "hfov_deg": 70.0, "width": 1280, "height": 720},
       "scan": {"step_deg": 45, "frames_per_stop": 3}}


def _open():
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    tmp.close()
    return db.open_db(tmp.name), tmp.name


class TestSchema(unittest.TestCase):
    def test_tables_exist(self):
        conn, _ = _open()
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"scans", "objects", "observations", "gt_objects"} <= names)
        conn.close()

    def test_foreign_keys_on(self):
        conn, _ = _open()
        self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        conn.close()

    def test_observation_requires_valid_scan(self):
        conn, _ = _open()
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO observations (scan_id, class_name) VALUES ('nope','bottle')")
        conn.close()


class TestInsertAndQuery(unittest.TestCase):
    def setUp(self):
        self.conn, self.path = _open()
        db.create_scan(self.conn, "scan_test", CFG, world_name="room")

    def tearDown(self):
        self.conn.close()

    def _mkobs(self, cls, p, conf=0.9, rng=2.0, trunc=False):
        return {"class_name": cls, "confidence": conf, "bbox_xyxy": [0, 0, 10, 10],
                "truncated": trunc, "depth_m": 1.5, "range_m": rng,
                "valid_depth_ratio": 0.9, "p_cam": [0, 0, 1.5], "p_world": list(p),
                "stop_index": 0, "frame_idx": 0, "yaw_rad": 0.0, "stamp_ns": 123}

    def test_insert_and_query_by_class(self):
        db.insert_object(self.conn, "scan_test", "bottle", 3.0, 2.9, 0.83, 0.5, 0.9, 0, 1)
        db.insert_object(self.conn, "scan_test", "cup", 3.8, 3.1, 0.7, 0.4, 0.8, 0, 1)
        bottles = queries.list_objects(self.conn, "scan_test", "bottle", status=None)
        self.assertEqual(len(bottles), 1)
        self.assertEqual(bottles[0]["class_name"], "bottle")
        allt = queries.list_objects(self.conn, "scan_test", None, status=None)
        self.assertEqual(len(allt), 2)

    def test_query_objects_min_obs_and_range(self):
        db.insert_object(self.conn, "scan_test", "bottle", 3.0, 0.0, 0.8, 0.5, 0.9, 0, 1)
        db.insert_object(self.conn, "scan_test", "cup", 10.0, 0.0, 0.7, 0.5, 0.9, 0, 1)
        for oid in (1, 2):
            db.set_object_status(self.conn, oid, "confirmed")
        near = queries.query_objects(self.conn, "scan_test", max_range_m=5.0,
                                     center_xy=(0, 0), status="confirmed")
        self.assertEqual(len(near), 1)
        self.assertEqual(near[0]["class_name"], "bottle")

    def test_stats_by_class(self):
        db.insert_object(self.conn, "scan_test", "bottle", 1, 1, 1, 1, 0.9, 0, 1)
        for _ in range(3):
            db.insert_observation(self.conn, "scan_test", 1, self._mkobs("bottle", (1, 1, 1)))
        stats = queries.obs_stats_by_class(self.conn, "scan_test")
        row = [r for r in stats if r["class_name"] == "bottle"][0]
        self.assertEqual(row["n_obs"], 3)

    def test_gt_loaded(self):
        n = db.load_gt_objects(self.conn, [
            {"model_name": "b1", "class_name": "bottle", "x": 1, "y": 2, "z": 3,
             "size_x": 0.1, "size_y": 0.1, "size_z": 0.2}])
        self.assertEqual(n, 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM gt_objects").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
