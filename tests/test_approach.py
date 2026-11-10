"""W7-A1: điểm tiếp cận theo mục 5.7. Ví dụ spec: camera (0,0), vật (3,0),
standoff 0.6 -> điểm (2.4, 0), yaw 0."""
import math
import unittest

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "object_db"))
from object_db.approach import approach_point  # noqa: E402


class TestApproach(unittest.TestCase):
    def test_spec_example(self):
        r = approach_point((3.0, 0.0), (0.0, 0.0), 0.6)
        self.assertAlmostEqual(r["x"], 2.4, places=6)
        self.assertAlmostEqual(r["y"], 0.0, places=6)
        self.assertAlmostEqual(r["yaw_rad"], 0.0, places=6)
        self.assertFalse(r["already_close"])

    def test_yaw_points_into_object(self):
        r = approach_point((0.0, 3.0), (0.0, 0.0), 0.6)
        # điểm trên đoạn vật->camera, yaw hướng vào vật (+y)
        self.assertAlmostEqual(r["x"], 0.0, places=6)
        self.assertAlmostEqual(r["y"], 2.4, places=6)
        self.assertAlmostEqual(r["yaw_rad"], math.pi / 2, places=6)

    def test_standoff_distance_kept(self):
        r = approach_point((4.0, 3.0), (0.0, 0.0), 1.0)
        d = math.hypot(r["x"] - 4.0, r["y"] - 3.0)
        self.assertAlmostEqual(d, 1.0, places=6)

    def test_already_close(self):
        r = approach_point((0.3, 0.0), (0.0, 0.0), 0.6)
        self.assertTrue(r["already_close"])
        self.assertAlmostEqual(r["x"], 0.0)
        self.assertAlmostEqual(r["y"], 0.0)

    def test_coincident_returns_close(self):
        r = approach_point((1.0, 1.0), (1.0, 1.0), 0.6)
        self.assertTrue(r["already_close"])
        self.assertEqual(r["distance_m"], 0.0)

    def test_diagonal(self):
        r = approach_point((3.0, 4.0), (0.0, 0.0), 1.0)
        self.assertAlmostEqual(math.hypot(r["x"] - 3, r["y"] - 4), 1.0, places=6)
        self.assertAlmostEqual(r["x"], 2.4, places=6)
        self.assertAlmostEqual(r["y"], 3.2, places=6)


if __name__ == "__main__":
    unittest.main()
