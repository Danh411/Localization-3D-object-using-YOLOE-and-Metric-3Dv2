# loc3d_ws

Pipeline thử nghiệm nhận diện và định vị vật thể 3D trong Gazebo bằng YOLOE
(segmentation) và Metric3D v2. Workspace ROS 2/Gazebo này ưu tiên quét camera
quay 360° rồi chụp các ảnh tĩnh độc lập; hiện không xử lý video, không ghép ảnh,
không tracking và không hợp nhất kết quả giữa các góc nhìn.

> **Tình trạng:** pipeline capture → mask → depth → so sánh Gazebo GT đã chạy
> end-to-end. Benchmark hiện tại là baseline nghiên cứu, chưa phải hệ thống đo
> chính xác dùng trong thực tế. Đặc biệt, nhãn YOLOE đơn lẻ không chứng minh
> vật thể đã được nhận diện đúng: cần kiểm tra mask với panoptic GT.

## Mục tiêu và luồng xử lý

1. Gazebo quay camera tới từng góc; sau khi camera ổn định, capture một số ảnh
   RGB tĩnh. Với `--segmentation-gt`, cùng thời điểm đó lưu depth và panoptic
   label map từ Gazebo để làm ground truth (GT).
2. Sau khi hoàn tất toàn bộ lượt chụp, xử lý từng ảnh độc lập:
   - YOLOE tìm lớp và mask của các vật thể.
   - Metric3D v2 ước lượng depth từ ảnh RGB.
   - Lấy depth trong mask để tính khoảng cách và vị trí 3D trong hệ camera;
     `tools/run_images.py` chuyển tiếp sang hệ world để đánh giá.
3. So sánh ước lượng với depth của Gazebo và so mask với panoptic GT; ghi kết
   quả từng ảnh, ảnh overlay, bảng CSV, JSON summary và báo cáo Markdown.

Metric3D **không chạy trong lúc camera capture**. Gazebo depth được lưu cùng
RGB tại thời điểm chụp, còn inference chạy sau khi capture kết thúc. Mỗi ảnh
được tính riêng; các lần nhìn lặp lại cùng một vật là các observations độc lập.

## Trạng thái benchmark mới nhất

Kết quả đầy đủ lưu trong `data/eval/scan_panoptic_baseline/` (thư mục `data/`
bị Git ignore nên không được đưa vào commit):

- 24 ảnh, 8 hướng cách nhau 45°, 3 ảnh mỗi hướng.
- RGB, depth GT và panoptic GT khớp timestamp; độ lệch lớn nhất trong lần chạy
  này là 0 ms.
- GT chứa các nhãn `cup`, `bottle`, `laptop`, `book`.
- YOLOE tạo 9 detections: 3 bottle, 3 book, 3 laptop; không phát hiện cup.
- Bottle là kết quả đúng rõ nhất: mask IoU **0,941** với GT. Depth MAE của ba
  bottle observations là **0,099 m**; bias **+0,099 m** (ước lượng sâu hơn GT).
- Detections mang nhãn `book` và `laptop` là false positives trên vùng xám /
  hình học khác, không phải nhận diện đúng book/laptop. IoU semantic của hai
  lớp này bằng 0; vì thế MAE theo nhãn dự đoán `book` hoặc `laptop` **không phải
  sai số đo của book/laptop thật**. Hiện chưa có phép đo depth hợp lệ cho hai
  vật thể đó.
- Trên cả 9 detections, MAE depth là 0,154 m; con số này gồm false positives,
  không nên diễn giải như độ chính xác của các vật thể thật.
- Instance mask ghép ở IoU ≥ 0,5: 3/9 predicted masks khớp một instance GT.

Xem [báo cáo chi tiết](data/eval/scan_panoptic_baseline/accuracy_report.md),
[summary JSON](data/eval/scan_panoptic_baseline/accuracy_summary.json), RGB
capture và các ảnh annotation/GT trong cùng thư mục dữ liệu. Báo cáo geometry-only
trước khi thêm Fuel models ở
`data/eval/scan_accuracy_baseline_geometry_eval/accuracy_report.md`; đó là
benchmark khác, không phải kết quả semantic mới nhất.

### Diễn giải đúng metric

- **Panoptic GT:** nhãn do Gazebo segmentation camera render cho từng pixel;
  chứa semantic label và instance ID của các model đã gán nhãn.
- **Ảnh annotation:** RGB capture có vẽ mask/khung/nhãn YOLOE lên trên; đây là
  visualization của prediction, không phải ground truth.
- **Semantic IoU:** đo mức pixel trùng nhau giữa mask prediction của một lớp
  và mask GT của lớp đó.
- **Instance IoU/matching:** so từng predicted mask với từng instance GT; không
  được xem một class label đơn lẻ là true positive.
- **Depth MAE:** so Metric3D depth trên mask dự đoán với Gazebo depth tại vùng
  ảnh tương ứng. Nếu detection sai vật hoặc sai lớp thì số depth đó cũng không
  phải sai số của vật thể mà prediction ghi tên.

## Môi trường đã kiểm chứng

Môi trường phát triển/chạy benchmark hiện có:

- Ubuntu 24.04 trên WSL2
- ROS 2 Jazzy
- Gazebo Sim 8.11.0 (Harmonic)
- NVIDIA Quadro P620, CUDA-capable
- Python 3.12 virtual environment

GPU, CUDA, driver và ROS/Gazebo package có thể khác trên máy khác. Project
chưa chứng nhận tương thích với Jetson hoặc các cấu hình GPU khác.

## Cài đặt

1. Cài Ubuntu 24.04, ROS 2 Jazzy, Gazebo Harmonic và gói ROS-Gazebo bridge
   (`ros_gz_sim`, `ros_gz_bridge`).
2. Tạo virtual environment và cài PyTorch phù hợp với CUDA/driver của máy.
   Ví dụ cấu hình đã dùng trong workspace:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   python -m pip install torch==2.7.1 torchvision==0.22.1 \
     --index-url https://download.pytorch.org/whl/cu118
   python -m pip install -r requirements-perception.txt
   ```

   Chọn đúng PyTorch build cho máy nếu CUDA không tương thích với ví dụ trên.
   `requirements-perception.txt` ghim Ultralytics và khai báo OpenCV, NumPy và
   PyYAML; PyTorch được cài riêng.
3. Đảm bảo model weights `yoloe-11s-seg.pt` có sẵn ở repo root. Weights và
   Metric3D model cache không được lưu trong Git. Lần đầu chạy có thể cần mạng
   để tải Metric3D v2 từ Torch Hub.
4. Build ROS package:

   ```bash
   source /opt/ros/jazzy/setup.bash
   colcon build --packages-select room_sim --symlink-install
   source install/setup.bash
   ```

5. Sinh world và ground-truth object config từ cùng một nguồn:

   ```bash
   .venv/bin/python tools/gen_scene.py
   colcon build --packages-select room_sim --symlink-install
   ```

   Gazebo tải các model Fuel khi nạp world. Để xác thực SDF mà không cần tải
   Fuel, trước tiên tải các asset về Fuel cache; lệnh `gz sdf -k` không tự fetch
   remote includes.

## Chạy pipeline

Mở terminal có ROS environment đã source:

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch room_sim room.launch.py
```

Sau khi camera, Gazebo và ROS bridge đang hoạt động, mở terminal khác trong repo
và chạy scan 360° kèm panoptic GT:

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
.venv/bin/python tools/scan_evaluate.py \
  --segmentation-gt \
  --out data/eval/scan_panoptic
```

Mặc định lấy cấu hình từ `config/default.yaml`: mỗi 45° chụp 3 ảnh, đợi camera
settle 1,5 giây; Metric3D chạy với input 616×1064 để ưu tiên chất lượng. Dùng
thư mục `--out` mới cho mỗi run, vì chương trình không ghi đè output đã tồn tại.
Có thể tùy chỉnh `--step`, `--frames`, `--settle`, `--depth-size` và `--device`.

### Replay trên capture có sẵn

```bash
.venv/bin/python tools/scan_evaluate.py \
  --images data/eval/scan_panoptic/capture \
  --depth-dir data/eval/scan_panoptic/capture/depth_gt \
  --segmentation-dir data/eval/scan_panoptic/capture/segmentation_gt \
  --out data/eval/scan_panoptic_replay
```

Capture có thể phát lại mà không bật Gazebo; vẫn cần weights, dependencies và
Metric3D model cache. Với mesh-based GT, cần panoptic label maps; replay thiếu
`--segmentation-dir` sẽ không được coi là geometry GT.

## Artifact đầu ra

Trong mỗi thư mục run:

- `capture/stop*_f*.png`: ảnh RGB Gazebo (1280×720 theo cấu hình hiện tại).
- `capture/depth_gt/*.npy`: depth ground truth Gazebo, float32 mét.
- `capture/segmentation_gt/*.npy`: RGB panoptic label map Gazebo khi bật flag.
- `capture/capture_metadata.csv`: góc quay, timestamp RGB/depth/segmentation và
  độ lệch đồng bộ.
- `perception/annot/`: ảnh annotation YOLOE.
- `perception/semantic_mask_compare_diagnostic/`: overlay đối chiếu semantic
  mask; xanh là pixel đúng, đỏ là false positive, xanh dương là false negative.
- `perception/instance_mask_compare/`: overlay so predicted instances với GT.
- `perception/detections.csv`, `rejected.csv`: từng detection và detection bị
  loại trong depth fusion.
- `perception/segmentation_metrics.csv`,
  `instance_segmentation_metrics.csv`: kết quả mask từng ảnh/lớp.
- `perception/timings.csv`, `run_metadata.json`: timing và thông tin cấu hình.
- `accuracy_summary.json`, `accuracy_report.md`: tổng hợp cuối lượt scan.

Các file trong `data/` không commit mặc định; sao lưu/chia sẻ dataset riêng nếu
cần để tránh đưa lượng lớn ảnh và dữ liệu mô phỏng vào Git.

## Cấu trúc repository

- `config/default.yaml`: cấu hình camera, scan, YOLOE, Metric3D và depth fusion.
- `config/classes.yaml`: danh sách lớp YOLOE.
- `config/gt_objects.yaml`: tọa độ/kích thước object GT; được sinh bởi
  `tools/gen_scene.py`.
- `src/room_sim/`: Gazebo world, ROS 2 launch, bridge và node TF.
- `src/perception/perception/core/`: YOLOE, Metric3D, mask/depth fusion, geometry
  và xử lý một ảnh.
- `tools/gen_scene.py`: sinh SDF world và object GT đồng bộ.
- `tools/capture_scan.py`: quay camera và lưu RGB/depth/panoptic GT.
- `tools/run_images.py`: inference từng ảnh và ghi kết quả mask/depth.
- `tools/segmentation_gt.py`: decode Gazebo panoptic maps và metric segmentation.
- `tools/scan_evaluate.py`: điều phối live scan/replay và viết report.
- `tests/`: unit tests cho geometry, fusion và đánh giá segmentation.
- `docs/`: giả định, quyết định kỹ thuật và conventions đã xác minh.

## Test và kiểm tra

```bash
.venv/bin/python -m pytest tests -q
git diff --check
```

Kiểm tra SDF sau khi các model include đã có trong Fuel cache:

```bash
gz sdf -k src/room_sim/worlds/room.sdf
```

Đã chạy thành công 31 tests và build `room_sim` trong môi trường phát triển ở
trên. Kiểm thử đơn vị không thay thế live Gazebo smoke test hoặc đánh giá chất
lượng nhận diện.

## Hạn chế và việc tiếp theo

- Baseline panoptic hiện chỉ có ít detections đúng; book/cup/laptop chưa được
  YOLOE nhận diện đáng tin cậy. Không báo cáo các false positive đó là thành
  công chỉ vì tên class dự đoán trùng tên object GT.
- Laptop và book có thể bị khuất, nhìn nghiêng hoặc thiếu sáng; vật thể khác
  trong scene cũng gây false positives. Cần sắp xếp lại layout/vị trí camera,
  giảm che khuất và kiểm tra mask trực tiếp.
- Gazebo đã cảnh báo một số model OBJ không tìm thấy `texture.png`; model vẫn
  xuất hiện và được panoptic label, nhưng hình render có thể thiếu texture.
- Scene hiện vẫn là phòng thử nghiệm đơn giản, không phải căn hộ nội thất hoàn
  chỉnh. Thêm nội thất có thể cung cấp context indoor cho Metric3D nhưng không
  đảm bảo depth chính xác hơn; cần benchmark trên cùng capture và GT để xác nhận.
- Không bật video, temporal fusion, object tracking hay hợp nhất detections qua
  các góc. Giữ các observation độc lập để phục vụ so sánh độ chính xác.
- Sai số world position phụ thuộc vào camera intrinsics, yaw/TF, mask đúng và
  depth alignment; kiểm tra từng nguồn trước khi chỉnh scale toàn cục.

## Gazebo Fuel attribution

Các object semantic benchmark hiện dùng:

- [ACE Coffee Mug 16 oz](https://app.gazebosim.org/GoogleResearch/models/ACE_Coffee_Mug_Kristen_16_oz_cup),
  [Travel Mate notebook](https://app.gazebosim.org/GoogleResearch/models/Travel_Mate_P_series_Notebook)
  và [Eat to Live book](https://app.gazebosim.org/GoogleResearch/models/Eat_to_Live_The_Amazing_NutrientRich_Program_for_Fast_and_Sustained_Weight_Loss_Revised_Edition_Book)
  của GoogleResearch: CC BY 4.0.
- [Water Bottle](https://app.gazebosim.org/iche033/models/Water%20Bottle)
  của iche033: CC BY 4.0 theo listing Gazebo Fuel.

Giữ attribution và tuân theo license nếu phân phối lại model/scene hoặc bản sao
asset. Xem [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
