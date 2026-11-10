# Mốc bếp có texture

Mốc ngày 10/11/2026 có 24 khung RGB, depth Gazebo và panoptic cùng timestamp.
Chỉ RGB và camera intrinsics được đưa vào suy luận. World, cấu hình và kết quả
tổng hợp có trong Git. NPZ, SQLite gốc, trọng số và archive nằm trong bản lưu
cục bộ được đối chiếu bằng SHA-256 trong manifest.

Bốn vật có nhãn GT instance cho 12 detection đúng và 3 detection sai lớp.
Cả ba detection sai là sách bị nhận thành `bottle` và tạo SQLite ID 9.
Ghép theo lớp và khoảng cách XY chọn nhầm ID 9 ở 37,1 cm. Chấm theo instance
ghép chai thật ID 5 ở 45,7 cm. Cốc và laptop lệch lần lượt 24,0 và 42,4 cm
sau gộp. Tổng cộng 3/4 vật được ghép đúng trong bán kính 0,5 m.

| Vật | Depth MAE trên cùng mask | Bias depth | Bề mặt GT → tâm mesh, trung vị XYZ |
| --- | ---: | ---: | ---: |
| Chai | 36,4 cm | −34,7 cm | 5,3 cm |
| Cốc | 20,2 cm | −17,4 cm | 6,1 cm |
| Laptop | 39,8 cm | −39,7 cm | 16,9 cm |

Phân rã đầy đủ có 11 quan sát. Một quan sát chai lệch timestamp joint 4 ms
và chỉ tham gia thống kê depth.

Xem [tổng hợp](summary.json), [audit detection](detection_audit.csv),
[phân rã XYZ](xyz_decomposition.json) và [manifest](local_capture_manifest.json).

## Chạy world tham chiếu

Từ thư mục gốc repo trên môi trường ROS 2 Jazzy và Gazebo Harmonic đã cài phụ thuộc:

```bash
export LOC3D_WS_ROOT="$PWD"
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
source install/setup.bash
LOC3D_WORLD=kitchen_reference.sdf ros2 launch loc3d_bringup sim_scan.launch.py \
  config:="$PWD/config/kitchen_reference.yaml" \
  classes:="$PWD/config/kitchen_reference_classes.yaml" \
  gt:="$PWD/config/kitchen_reference_gt.yaml"
```

Gọi action `/scan/run` với bước 45°, 3 khung mỗi điểm và settle 1,5 s.
World dùng asset chai Fuel bản 3 đi kèm repo. Xem [ghi công asset](../../src/room_sim/ASSET_ATTRIBUTION.md).

## Chấm lại bộ khung

Với bộ dữ liệu cục bộ còn đủ `frames/`, `audit_scan_*.json`, `db/`,
`mesh_centers.json` và cấu hình:

```bash
python tools/eval_kitchen_reference.py /path/to/frozen_dataset
```

Bộ chấm ghép một-một theo lớp và mask IoU ≥ 0,5. Một bản ghi SQLite chỉ đủ
điều kiện định vị khi tất cả quan sát nhất quán với một instance GT.
Luồng quét mặc định tạo SQLite. Dữ liệu GT và mask được thu riêng bằng
bộ audit của mốc cục bộ.
