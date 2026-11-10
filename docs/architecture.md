# Kiến trúc pipeline

## Luồng live scan

```text
Gazebo rgbd_camera + pan_joint
        │ ros_gz_bridge
        ├── /camera/image (RGB, suy luận)
        ├── /camera/camera_info (K, suy luận)
        ├── /camera/depth_image (GT, đánh giá בלבד)
        └── /joint_states
                │
        scan_controller (/scan/run)
          pan_cmd → settle → /perception/capture
                │
        perception_node (một tiến trình, tuần tự)
          YOLOE masks → Metric3D depth → fusion → p_cam
          tf2(world ← camera_optical_frame) → p_world
                │ /db/observations
        object_db_node
          association radius + weighted average
          merge pass + confirmed/rejected
          SQLite: scans / observations / objects / gt_objects
                │
        /db/query, /db/approach_point, tools/query_db.py
```

## Quy ước an toàn dữ liệu

- RGB và `camera_info` là đầu vào perception; depth Gazebo và segmentation GT
  chỉ dùng đánh giá, không làm input Metric3D.
- Mọi mask resize dùng nearest; depth fusion erode mask, lọc NaN/Inf và dùng
  median trên pixel hợp lệ.
- `p_cam` ở optical frame: +X phải, +Y xuống, +Z trước. TF2 được truy vấn theo
  timestamp của ảnh; công thức geometry thuần có unit test riêng.
- SQLite bật `PRAGMA foreign_keys = ON`. Observation luôn được giữ lại; object
  bị loại đổi thành `rejected`, không xóa lịch sử.
- Mỗi scan tạo file riêng dưới `data/db/<scan_id>.sqlite`; data không commit.

## Chế độ offline

`tools/run_scan.py` dùng cùng core pipeline và association nhưng đọc
`stop*_f*.png` + metadata yaw. `tools/eval_scan.py` dùng Hungarian matching cùng
class, bán kính mặc định 0.5 m; tính e_xy, e_3d, recall, precision, dup_rate,
fp_rate. Offline pipeline có thể đối chiếu depth GT từ `.npy` nhưng không truyền
GT vào Metric3D.

## Chế độ HIL

`hil_scan.launch.py` chạy Gazebo/bridge/TF/controller ở máy chính; perception
node được chạy trong container Xavier với cùng ROS_DOMAIN_ID. Chỉ topic RGB,
CameraInfo và các interface scan đi qua DDS; depth GT không cần đưa lên Xavier.
