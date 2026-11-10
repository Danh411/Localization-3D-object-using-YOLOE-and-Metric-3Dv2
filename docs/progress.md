# Tiến độ triển khai

Ngày cập nhật: 09/11/2026.

## Đã hoàn tất / có bằng chứng

- W1–W2 baseline của repo: ROS 2 Jazzy + Gazebo Harmonic, room/camera/pan
  và conventions z-depth/yaw đã kiểm chứng.
- Core YOLOE + Metric3D + fusion + geometry và bộ test cũ: pass.
- `tools/gen_scene.py`: scene 5×4×2.8 m, 12 vật GT, nội thất trang trí, sàn/tường
  nhiều tông, ánh sáng indoor; `room.sdf` được sinh lại.
- W5-A2: `src/object_db/object_db/{schema,db,queries}.py`, SQLite 4 bảng,
  khóa ngoại, config hash và git commit metadata.
- W5-B2: `association.py`: weighted observation, radius association,
  merge pass, vòng 360°, truncated weight, confirmed/rejected.
- W7-A1: `approach.py` và test ví dụ (3,0) → (2.4,0), yaw 0.
- W4-A2/W5-B3: `tools/plot_topdown.py`, tạo được ảnh top-down từ DB.
- Eval: `tools/eval_scan.py` Hungarian matching và các chỉ số mục 9.
- Offline full path: `tools/run_scan.py` capture → perception → world → SQLite → eval.
- ROS interfaces: `scan_interfaces` gồm `RunScan`, `Capture`, `QueryObjects`,
  `GetApproachPoint`, `FinalizeScan` và messages.
- ROS nodes/packages: `perception`, `object_db`, `scan_controller`,
  `loc3d_bringup`; `sim_scan.launch.py` và `hil_scan.launch.py`.
- Build: `colcon build --symlink-install` pass cho 6 package.
- Tests: `python3 -m pytest tests -q` → **58 passed**.
- Smoke DB: tạo scan, 3 observations bottle, finalize → 1 confirmed; eval/query/
  topdown chạy được.

## Live integration (đã chạy, giới hạn được ghi rõ)

- WSL có GPU GTX 1650 4 GB, nhưng network/DNS hỏng, không có pip/venv package;
  vì vậy không cài được torch/ultralytics vào ROS distro. Thay vì dừng ở giả định,
  đã chạy Gazebo + ros_gz_bridge trong WSL và inference thật trên Windows
  `D:\yoloe_test\.venv` (YOLOE weights `yoloe-v8s-seg.pt`, Metric3D ViT-Small
  local adapter/checkpoint đã pin). Đây kiểm chứng chức năng Gazebo RGB → YOLOE →
  Metric3D → world → SQLite, nhưng **không thay thế ROS perception_node chạy tại
  WSL/Xavier**.
- Capture RGB, Gazebo depth GT, CameraInfo K và pan yaw thực theo timestamp;
  `joint_states` kiểm tra góc dừng: 0° và 45° với sai số < 0.1° trong lần
  capture cuối. Depth GT không được truyền vào inference; chỉ so sánh sau đó.
- 6 frame mới (3 × yaw 0°, 3 × yaw 45°): **15 observations**, **3 confirmed**,
  1 rejected; DB `data/db/live_rgbd_final.sqlite`. (Đã rerun sau khi tính đúng
  `truncated` theo bbox; detection variability làm object count đổi nhẹ.)
- Depth Metric3D vs synchronized Gazebo depth trong predicted masks, pixel-weighted:
  101,389 px; MAE=0.090 m, RMSE=0.129 m, AbsRel=0.057, bias=-0.015 m. Đây là
  kết quả trên đúng hai góc, cảnh synthetic này, class masks do YOLOE dự đoán;
  không tổng quát hóa sang 360°/scene khác.
- Localization object-level vs 12 GT: matched 2/12 (recall=0.167), precision=0.5,
  median e_xy=0.171 m. Sai số này và detection/association misses cho thấy chưa
  đạt các tiêu chí cuối spec; không gọi là hoàn thành accuracy target. Chi tiết
  capture/scan là ignored data, không commit weights/data.
- Capture mở rộng 8 yaw chỉ thử một frame/góc và cho nhiều góc 0 detections; do
  đó không dùng nó để suy ra depth accuracy. Ba frame/góc cho yaw 0/45 là subset
  có kiểm tra đồng bộ.

## Chưa nghiệm thu live/đồ án

- WSL ROS `perception_node` chưa chạy YOLOE/Metric3D trực tiếp: distro không có
  pip/venv và không truy cập được network. Live integration trên Windows venv là
  workaround để đo thuật toán; cần sửa network/cài venv nếu cần xác nhận node ROS.
- Full 360°/8 stop × 3 frames với perception online chưa benchmark xong; lớp
  detections ở các góc khác nhau còn kém.
- Xavier thật, ROS DDS HIL, TensorRT, 21-run evaluation, báo cáo/slide tuần 10
  chưa thực hiện.

## Bước tiếp theo

1. Sửa WSL DNS/NAT để cài perception venv đúng ROS Jazzy hoặc chia sẻ inference
   service qua Windows; sau đó chạy `sim_scan.launch.py` thật.
2. Cải thiện YOLOE/class prompts/scene visibility; full-scan eval và phân tích
   false positives trước khi kết luận accuracy.
3. Xavier/TensorRT/HIL chỉ verify khi có phần cứng hoặc môi trường tương ứng.
4. Chạy full 360° và ghi data/eval protocol đủ seed/config/git commit.
