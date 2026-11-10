"""W5-B2: gộp vật trùng mục 5.6 — cùng vật qua 2 góc, vòng 360°, hai vật cùng lớp
gần nhau, vật bị cắt biên, trạng thái confirmed/rejected. >= 10 test."""
import math
import tempfile
import unittest
from pathlib import Path

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "object_db"))
from object_db import association, db, queries  # noqa: E402

CFG = {"camera": {"base_xyz": [2.0, 2.0, 1.2], "hfov_deg": 70.0, "width": 1280, "height": 720},
       "scan": {"step_deg": 45, "frames_per_stop": 3}}
ASSOC = {"radius_m": 0.35, "merge_radius_m": 0.25, "min_obs": 3, "min_conf_to_create": 0.4}
FUS = {"range_floor_m": 0.5, "truncated_weight": 0.3}


def _open():
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False); tmp.close()
    conn = db.open_db(tmp.name)
    db.create_scan(conn, "s1", CFG, world_name="room")
    return conn


def obs(cls, p, conf=0.9, rng=2.0, trunc=False, stop=0):
    return {"class_name": cls, "confidence": conf, "bbox_xyxy": [0, 0, 10, 10],
            "truncated": trunc, "depth_m": 1.5, "range_m": rng, "valid_depth_ratio": 0.9,
            "p_cam": [0, 0, 1.5], "p_world": list(p), "stop_index": stop, "frame_idx": 0,
            "yaw_rad": 0.0, "stamp_ns": 1}


class TestWeight(unittest.TestCase):
    def test_weight_closer_heavier(self):
        near = association.obs_weight(0.9, 1.0, False)
        far = association.obs_weight(0.9, 4.0, False)
        self.assertGreater(near, far)

    def test_truncated_downweighted(self):
        full = association.obs_weight(0.9, 2.0, False)
        trunc = association.obs_weight(0.9, 2.0, True)
        self.assertAlmostEqual(trunc, full * 0.3)

    def test_range_floor(self):
        # r < sàn thì dùng sàn => không thổi trọng số vật siêu gần
        w = association.obs_weight(0.9, 0.1, False, range_floor_m=0.5)
        self.assertAlmostEqual(w, 0.9 / 0.25)


class TestAssociate(unittest.TestCase):
    def setUp(self):
        self.conn = _open()

    def tearDown(self):
        self.conn.close()

    def _assoc(self, o):
        return association.add_observation(self.conn, "s1", o, ASSOC, FUS)

    def test_creates_new_object(self):
        r = self._assoc(obs("bottle", (3.0, 2.9, 0.83)))
        self.assertTrue(r["created"])
        self.assertEqual(len(queries.list_objects(self.conn, "s1", status=None)), 1)

    def test_same_object_across_two_stops_merges(self):
        # cùng một chai thấy ở 2 góc cách nhau -> 1 object, n_obs=2
        self._assoc(obs("bottle", (3.0, 2.9, 0.83), stop=0))
        self._assoc(obs("bottle", (3.02, 2.92, 0.83), stop=1))
        objs = queries.list_objects(self.conn, "s1", status=None)
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0]["n_obs"], 2)

    def test_two_objects_same_class_far_apart_stay_separate(self):
        # hai chai cùng lớp cách 1.2 m (> radius) -> 2 object riêng
        self._assoc(obs("bottle", (1.0, 1.0, 0.5)))
        self._assoc(obs("bottle", (2.2, 1.0, 0.5)))
        self.assertEqual(len(queries.list_objects(self.conn, "s1", status=None)), 2)

    def test_low_confidence_not_created(self):
        r = self._assoc(obs("bottle", (3.0, 2.9, 0.8), conf=0.2))
        self.assertIsNone(r["object_id"])
        self.assertEqual(len(queries.list_objects(self.conn, "s1", status=None)), 0)

    def test_low_confidence_can_update_existing(self):
        self._assoc(obs("bottle", (3.0, 2.9, 0.8), conf=0.9))
        self._assoc(obs("bottle", (3.01, 2.9, 0.8), conf=0.2))
        objs = queries.list_objects(self.conn, "s1", status=None)
        self.assertEqual(len(objs), 1)  # vẫn 1 object, gộp được dù conf thấp
        self.assertEqual(objs[0]["n_obs"], 2)

    def test_weighted_average_position(self):
        # quan sát gần (conf cao) kéo vị trí về phía nó
        self._assoc(obs("bottle", (3.0, 3.0, 1.0), conf=0.9, rng=1.0))
        self._assoc(obs("bottle", (3.2, 3.0, 1.0), conf=0.9, rng=4.0))
        o = queries.list_objects(self.conn, "s1", status=None)[0]
        # quan sát 1 (r=1) nặng hơn -> x gần 3.0 hơn 3.2
        self.assertLess(o["x"], 3.1)

    def test_wraparound_360_last_and_first_same_object(self):
        # điểm dừng cuối (k=7) và điểm dừng đầu (k=0) nhìn cùng vật qua vòng 360°
        for stop in range(8):
            self._assoc(obs("vase", (4.0, 3.1, 0.8) if stop % 2 == 0
                            else (4.02, 3.12, 0.8), stop=stop))
        objs = queries.list_objects(self.conn, "s1", status=None)
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0]["first_seen_stop"], 0)
        self.assertEqual(objs[0]["last_seen_stop"], 7)

    def test_merges_into_one_object(self):
        # 2 object cùng lớp cách < merge_radius, đã đủ n_obs -> gộp thành 1 confirmed.
        # (tình huống thực tế: vòng 360° tạo 2 object rồi cuối scan mới phát hiện trùng)
        o1 = db.insert_object(self.conn, "s1", "bottle", 3.0, 3.0, 0.8, 3.0, 0.9, 0, 1)
        o2 = db.insert_object(self.conn, "s1", "bottle", 3.1, 3.0, 0.8, 2.0, 0.8, 0, 1)
        for oid in (o1, o2):  # mỗi object đã có 3 quan sát không truncated
            self.conn.execute("UPDATE objects SET n_obs=3 WHERE object_id=?", (oid,))
        self.conn.commit()
        res = association.run_association_pass(self.conn, "s1", ASSOC)
        self.assertEqual(len(res["merged_pairs"]), 1)
        kept = [o for o in queries.list_objects(self.conn, "s1", status=None)
                if o["status"] == "confirmed"]
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["n_obs"], 6)


    def test_confidence_tracks_all_observations_across_merge_and_update(self):
        settings = {**ASSOC, "radius_m": 0.1}
        for x, conf in ((0.0, 0.9), (0.01, 0.7), (0.2, 0.8), (0.21, 0.6)):
            association.add_observation(
                self.conn, "s1", obs("cup", (x, 0, 0), conf=conf), settings, FUS)
        objects = queries.list_objects(self.conn, "s1", status=None)
        self.assertEqual(len(objects), 2)
        for obj, total in zip(objects, (1.6, 1.4), strict=True):
            self.assertAlmostEqual(obj["conf_sum"], total)
            self.assertAlmostEqual(obj["conf_mean"], total / 2)

        result = association.run_association_pass(self.conn, "s1", settings)
        self.assertEqual(len(result["merged_pairs"]), 1)
        merged_id = result["merged_pairs"][0][1]
        merged = queries.list_objects(self.conn, "s1")[0]
        self.assertAlmostEqual(merged["conf_sum"], 3.0)
        self.assertAlmostEqual(merged["conf_mean"], 0.75)

        self._assoc(obs("cup", (0.05, 0, 0), conf=0.5))
        final = queries.list_objects(self.conn, "s1")[0]
        self.assertEqual(final["object_id"], merged_id)
        self.assertEqual(final["n_obs"], 5)
        self.assertAlmostEqual(final["conf_sum"], 3.5)
        self.assertAlmostEqual(final["conf_mean"], 0.7)
        rows = self.conn.execute("SELECT object_id FROM observations").fetchall()
        self.assertEqual([r["object_id"] for r in rows], [merged_id] * 5)


class TestStatus(unittest.TestCase):
    def setUp(self):
        self.conn = _open()

    def tearDown(self):
        self.conn.close()

    def test_confirmed_after_min_obs(self):
        for i in range(3):
            association.add_observation(self.conn, "s1",
                                        obs("bottle", (3.0, 3.0, 0.8), stop=i),
                                        ASSOC, FUS)
        counts = association.run_association_pass(self.conn, "s1", ASSOC)
        self.assertEqual(counts["confirmed"], 1)

    def test_rejected_when_few_obs(self):
        association.add_observation(self.conn, "s1", obs("bottle", (3.0, 3.0, 0.8)), ASSOC, FUS)
        counts = association.run_association_pass(self.conn, "s1", ASSOC)
        self.assertEqual(counts["rejected"], 1)

    def test_rejected_when_all_truncated(self):
        for i in range(3):
            association.add_observation(self.conn, "s1",
                                        obs("bottle", (3.0, 3.0, 0.8), trunc=True, stop=i),
                                        ASSOC, FUS)
        counts = association.run_association_pass(self.conn, "s1", ASSOC)
        self.assertEqual(counts["rejected"], 1)


if __name__ == "__main__":
    unittest.main()
