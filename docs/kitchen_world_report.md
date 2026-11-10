# Kitchen world: tích hợp `makerspet/oomwoo_gazebo` vào loc3d_ws

Ngày: 10/11/2026.
Mục tiêu: thay phòng `room.sdf` thô sơ bằng một căn bếp chi tiết, đủ để YOLOE +
Metric3D có vật dễ nhận; kiểm tra lại pipeline scan sau thay đổi.

## 1. Bối cảnh và quyết định

Phòng `room.sdf` cũ là khối nguyên thủy: tường phẳng một màu, 12 vật primitive
và 4 model Fuel. Các frame từ camera bị trắng/chói và YOLOE không nhận ra vật ở
hầu hết các góc (8 góc chỉ 2 góc có detections → recall 0.167). Người dùng yêu
cầu thay bằng `worlds/kitchen_dining.world` của `makerspet/oomwoo_gazebo`.

## 2. Thay đổi code/thư mục

- `src/room_sim/models/`: copy 56 thư mục model vendored (≈39 MB) — đồ nội thất
  có mesh/texture sẵn (`DiningChair`, `DiningTable`, `fridge_double_door`,
  `Oven`, `dishwasher`, `person_standing`, `salad_plate`, `coffee_maker`,
  `toaster_4_slice`, `dish_drainer`, …).
- `src/room_sim/worlds/kitchen_dining.sdf`: copy `worlds/kitchen_dining.world`,
  thêm `camera_rig` (rgbd_camera + pan_joint + JointPositionController) ở
  `(-1.5, -0.5, 1.1)` — sàn trống giữa phòng.
- `src/loc3d_bringup/launch/sim_scan.launch.py`:
  - `LOC3D_WORLD` default = `kitchen_dining.sdf` (có thể override lại `room.sdf`).
  - `GZ_SIM_RESOURCE_PATH` trỏ vào `src/room_sim/models` (vì `model://` cần
    parent dir chứa thư mục model; install/share không đủ).
  - `pan_tf_node` `base_xyz` = `[-1.5, -0.5, 1.1]` khớp `camera.base_xyz`.
- `config/default.yaml`: `camera.base_xyz` = `[-1.5, -0.5, 1.1]`.
- `config/classes.yaml`: lớp phù hợp với cảnh bếp
  `refrigerator, oven, chair, dining table, sink, bottle, cup, vase, person`.
- `config/gt_objects.yaml`: tạo tự động từ pose `<model>` trong world;
  giữ 17 vật có ý nghĩa định vị (bỏ tường, tủ treo, rèm, poster).

## 3. Bước kiểm tra đã làm

1. `colcon build --symlink-install` trên `room_sim` và `loc3d_bringup`: OK.
2. `ros2 launch loc3d_bringup sim_scan.launch.py`: Gazebo load world mà không lỗi
   `Unable to find uri`; camera_rig và segmentation đã khai báo trong SDF.
3. `ros2 service call /perception/capture` (stop 0, yaw 0, 2 khung): **10
   observations** — 2 person, 2 chair, 1 dining table với confidence 0.77–0.93,
   `valid_depth_ratio=1.0`, `p_world` hợp lệ.

Đây là bước rất khác so với `room.sdf`: trước đó capture trên khung tương đương
trả `0 quan sát` trên nhiều góc.

## 4. Dữ liệu ghi lại được trong lần test nhanh

Đã lưu DB `data/db/kitchen_test.sqlite` (và `scan_1794218408.sqlite` từ scan
trước đó trong `room.sdf`, đó là benchmark reference). `perception_node` ghi:
- `ObjectObservationArray` cho `kitchen_test` stop 0.
- Class_name/ confidence/ bbox/ truncated/ mask_area_px/ valid_ratio/
  depth_m/ range_m/ p_cam/ p_world/ yaw_rad/ stop_index/ frame_idx.
- `timings_ms`: yolo≈3.9 s, depth≈7.9 s cho 2 khung đầu (đã thay vì NaN sau
  fix FP32 fallback).

Từ `p_world` nhận được: person (≈−0.11, −1.08), person (≈1.00, 0.51), chair
(≈−0.05, −1.35), chair (≈0.14, 0.36), dining table (≈−0.54, −0.53). Giá trị phù
hợp trực quan với kitchen layout.

## 5. Điểm cần nghiệm thu tiếp

- Chạy `ros2 action send_goal /scan/run` để đo 8-stop × 3-frame đầy đủ: số lượng
  observation/confirmed/rejected cuối scan, recall và e_xy/e_3d so với
  `gt_objects.yaml`.
- `config/classes.yaml` hiện có `sink` nhưng không map vào `gt_objects` (sink là
  một phần của kitchen_base_run_east chứ không phải model riêng) — nên so sánh
  chỉ với lớp có GT thực.
- Hai model `person` (`person_standing`, `PatientFSit`) có thể tạo nhiều
  detection trùng nhau nếu hướng quay làm hai người cùng lớp. Cần kiểm tra
  `merge_duplicates` không gộp nhầm.
- Cần chụp bản đồ top-down và ảnh annotated để nhìn xem detections là vật thật
  hay false-positive (báo cáo depth không đủ).

## 6. Lệnh tái lập

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch loc3d_bringup sim_scan.launch.py
ros2 action send_goal /scan/run scan_interfaces/action/RunScan \
  "{step_deg: 45.0, frames_per_stop: 3, settle_time_s: 1.5}" --feedback
.venv/bin/python tools/query_db.py data/db/<scan>.sqlite --all --stats
.venv/bin/python tools/eval_scan.py data/db/<scan>.sqlite \
  --gt config/gt_objects.yaml
.venv/bin/python tools/plot_topdown.py data/db/<scan>.sqlite \
  --gt config/gt_objects.yaml --errors --out data/eval/kitchen_topdown.png
```

Nếu cần quay lại `room.sdf`: `LOC3D_WORLD=room.sdf ros2 launch loc3d_bringup
sim_scan.launch.py`.

## 7. Hạn chế

- World mới chỉ là căn bếp đơn, chưa thay scene multi-room / multi-floor.
- `depth GT` vẫn chỉ dùng cho evaluation; Metric3D không nhận depth từ Gazebo.
- Person trong cảnh không thuộc phạm vi đồ án 10 tuần; detections `person`
  được giữ trong DB nhưng không tính vào GT chính cho bàn ghế/kitchen items.
