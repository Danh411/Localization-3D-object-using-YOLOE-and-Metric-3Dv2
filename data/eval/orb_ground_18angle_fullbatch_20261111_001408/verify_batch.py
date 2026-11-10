"""Verify the two live runs and write the byte-exact publication manifest."""
import csv
import hashlib
import json
from pathlib import Path
import re
import sqlite3

ROOT = Path(__file__).resolve().parent
SCANS = ("scan_18x1", "holdout_18x1")
BRANCHES = (
    "P0_metric", "ORB_A_only", "ORB_B_only", "P1_orb_A", "P1_orb_B",
    "P2_ground", "P3_combined", "S_key40", "S_on_demand",
)
TYPES = {".csv", ".json", ".py", ".sh", ".yaml", ".md", ".sqlite", ".jpg",
         ".png", ".log", ".sdf", ".txt", ".sha256"}
OMIT = {"manifest.sha256", "initial_P0_metric.sqlite"}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return path.read_text(encoding="utf-8-sig")


def sql_integrity(path):
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        assert db.execute("pragma integrity_check").fetchone() == ("ok",), path
        assert db.execute("pragma foreign_key_check").fetchone() is None, path


def verify_scan(name):
    path = ROOT / name
    with (path / "capture_audit.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert sorted(int(row["stop"]) for row in rows) == list(range(18))
    assert len({row["stamp_ns"] for row in rows}) == 18
    assert all(row["stamp_ns"] == row["camera_info_stamp_ns"] for row in rows)
    assert all(row["frame"] == "0" for row in rows)
    assert max(abs(float(row["command_error_deg"])) for row in rows) < 0.5
    assert max(abs(float(row["tf_joint_error_deg"])) for row in rows) < 0.5
    assert max(abs(int(row["joint_skew_ns"])) for row in rows) <= 10_000_000
    k = [914.0147013559828, 914.0147013559828, 640.0, 360.0]
    assert all(json.loads(row["K"]) == k for row in rows)
    summary = json.loads(read(path / "experiment_summary.json"))
    assert not summary["wire_tf_missing"]
    assert summary["frames"] == 18 and len(list((path / "frames").glob("*.npz"))) == 18
    assert "status: SUCCEEDED" in read(path / "action.log")
    assert read(path / "replay_exit.txt").strip() == "0"
    assert "verified A against live" in read(path / "replay.log")
    assert set(summary["branches"]) == set(BRANCHES)
    for branch in BRANCHES:
        sql_integrity(path / (branch + ".sqlite"))
    for path_db in (path / "db").glob("*.sqlite"):
        sql_integrity(path_db)
    print(f"{name}: 18 synchronized stops, exact K, TF and P0 replay verified, "
          f"{len(BRANCHES)} diagnostic SQLite integrity checks")


def publication():
    for directory in (ROOT, *(ROOT / scan for scan in SCANS),
                      *(ROOT / scan / "db" for scan in SCANS)):
        for path in directory.iterdir():
            if path.is_file() and (path.suffix in TYPES or path.name == ".gitattributes"):
                if path.name not in OMIT:
                    yield path


def main():
    for name in SCANS:
        verify_scan(name)
    lock = json.loads(read(ROOT / "holdout_lock.json"))
    for path, sha in lock["files"].items():
        assert digest(ROOT / path) == sha, path
    print(f"Holdout lock verified after scoring: {len(lock['files'])} files")
    for name, pattern in (
        ("regression_diagnostic.log", r"Ran 4 tests[\s\S]*OK"),
        ("regression_yoloe.log", r"Ran \d+ tests[\s\S]*OK"),
        ("regression_loc3d.log", r"\d+ passed in "),
    ):
        assert re.search(pattern, read(ROOT / name)), name
    for name in ("Equal_12", "Equal_18", "Equal_36"):
        sql_integrity(ROOT / (name + ".sqlite"))
    for image in ("all_stops.jpg", "orb_matches.jpg", "gt_vs_sqlite.png"):
        assert all((ROOT / scan / image).stat().st_size > 0 for scan in SCANS)

    raw = sorted(path for scan in SCANS for path in (ROOT / scan / "frames").glob("*.npz"))
    for paths, name in ((raw, "raw_frames.sha256"), (None, "manifest.sha256")):
        if paths is None:
            paths = published = sorted(publication())
        with (ROOT / name).open("w", encoding="utf-8", newline="\n") as stream:
            for path in paths:
                stream.write(f"{digest(path)}  {path.relative_to(ROOT).as_posix()}\n")
    print(f"{len(published)} published artifacts and {len(raw)} local frames hashed")


if __name__ == "__main__":
    main()
