-- Schema SQLite cho mỗi lần quét (mục 6). Khóa ngoại bật qua PRAGMA foreign_keys.
-- Thời gian: chuỗi ISO-8601 UTC cho mốc ngày giờ; stamp_ns (nanosecond) cho mốc ảnh.

CREATE TABLE IF NOT EXISTS scans (
  scan_id          TEXT PRIMARY KEY,
  started_at       TEXT,
  finished_at      TEXT,
  world_name       TEXT,
  notes            TEXT,
  cam_x            REAL,
  cam_y            REAL,
  cam_z            REAL,
  hfov_deg         REAL,
  img_w            INTEGER,
  img_h            INTEGER,
  step_deg         REAL,
  frames_per_stop  INTEGER,
  config_hash      TEXT,
  git_commit       TEXT
);

CREATE TABLE IF NOT EXISTS objects (
  object_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  scan_id          TEXT NOT NULL REFERENCES scans(scan_id),
  class_name       TEXT NOT NULL,
  x                REAL,
  y                REAL,
  z                REAL,
  weight_sum       REAL DEFAULT 0,
  n_obs            INTEGER DEFAULT 0,
  conf_sum         REAL DEFAULT 0,
  conf_mean        REAL DEFAULT 0,
  first_seen_stop  INTEGER,
  last_seen_stop   INTEGER,
  seen_untruncated INTEGER DEFAULT 0,
  status           TEXT DEFAULT 'tentative' CHECK (status IN ('tentative','confirmed','rejected')),
  created_at       TEXT,
  updated_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_objects_scan_class ON objects(scan_id, class_name);
CREATE INDEX IF NOT EXISTS idx_objects_status ON objects(status);

CREATE TABLE IF NOT EXISTS observations (
  obs_id           INTEGER PRIMARY KEY AUTOINCREMENT,
  scan_id          TEXT NOT NULL REFERENCES scans(scan_id),
  object_id        INTEGER REFERENCES objects(object_id),
  stop_index       INTEGER,
  frame_idx        INTEGER,
  class_name       TEXT,
  confidence       REAL,
  bbox_x1          REAL,
  bbox_y1          REAL,
  bbox_x2          REAL,
  bbox_y2          REAL,
  truncated        INTEGER DEFAULT 0,
  depth_m          REAL,
  range_m          REAL,
  valid_ratio      REAL,
  cam_x            REAL,
  cam_y            REAL,
  cam_z            REAL,
  world_x          REAL,
  world_y          REAL,
  world_z          REAL,
  yaw_rad          REAL,
  stamp_ns         INTEGER
);
CREATE INDEX IF NOT EXISTS idx_obs_scan ON observations(scan_id);
CREATE INDEX IF NOT EXISTS idx_obs_object ON observations(object_id);
CREATE INDEX IF NOT EXISTS idx_obs_class ON observations(scan_id, class_name);

-- Chỉ dùng đánh giá: tâm và kích thước vật thật của cảnh.
CREATE TABLE IF NOT EXISTS gt_objects (
  gt_id            INTEGER PRIMARY KEY,
  model_name       TEXT,
  class_name       TEXT,
  x                REAL,
  y                REAL,
  z                REAL,
  size_x           REAL,
  size_y           REAL,
  size_z           REAL
);
