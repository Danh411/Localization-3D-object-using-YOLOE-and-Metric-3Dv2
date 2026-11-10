# Assumptions và giới hạn hiện tại

- Máy phát triển chính của workspace là WSL2 Ubuntu 24.04 + ROS 2 Jazzy +
  Gazebo Harmonic; `LOC3D_WS_ROOT=/mnt/d/loc3d_ws` là default của launch.
- Config mặc định dùng camera 1280×720, hfov 70°, base `(2,2,1.2)`, offset pan
  0.05 m, scan 45°/3 frame/stop.
- `object_db` chỉ tạo object mới khi confidence >= 0.4; vật confirmed cần
  ít nhất 3 observations và một observation không truncated.
- Association dùng radius 0.35 m, merge radius 0.25 m; hai vật cùng class gần
  hơn các ngưỡng này có thể bị gộp nhầm. Scene GT giữ vật cùng class cách nhau
  tối thiểu 0.6 m.
- `p_world` trong ROS node phụ thuộc TF2 đúng timestamp. Nếu lookup TF thất bại,
  observation không được ghi vào DB thay vì ghi tọa độ giả.
- Depth Gazebo là ground truth đánh giá; Metric3D chỉ nhận RGB và focal length.
- Fuel mesh cần cache trước khi dùng `gz sdf -k` hoặc benchmark offline/live.
- Jetson Xavier/NX/AGX và JetPack chưa được xác nhận; HIL launch chỉ là khung
  kết nối, chưa phải bằng chứng TensorRT.
