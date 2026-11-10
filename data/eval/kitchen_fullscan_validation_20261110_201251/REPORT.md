# Kiểm thử toàn pipeline Kitchen 360°

**Hệ số depth đã khóa giảm XY trung vị trong SQLite từ 42,8 xuống 7,5 cm, giảm 35,3 cm (82,5%).** Cả chai và laptop đều tốt lên. Recall định vị vẫn **2/4 (50%)** ở cả hai nhánh. Cốc có năm quan sát đúng nhưng đều sát mép nên bị từ chối. Sách không có detection đúng.

## 1. Lượt quét và cách chấm

- RunScan `scan_1794316856` hoàn tất 8 góc × 3 khung trong 231,7 s. Mỗi góc chờ 1,5 s sau khi pan đến góc. Lần khởi động trước bỏ qua 0° và 45° do timeout chờ pan, được hủy sau điểm 90°. Chỉ lượt đủ khung đi vào bảng chấm. Lượt chính thêm bước xác nhận dữ liệu joint và CameraInfo đi qua bridge, dùng đúng bản sao world và bố trí đã khóa từ trước. [Log lần thiếu](initial_incomplete/action.log) · [Log lượt chính](action.log)
- 24/24 khung có RGB, axial depth GT, panoptic, CameraInfo cùng timestamp và TF ở timestamp ảnh. K = (914,014701; 914,014701; 640; 360) px, ảnh 1280×720, HFOV 70°. Sai lệch yaw so với lệnh tối đa 0,151°. Lệch stamp joint dùng đối chiếu TF tối đa 5 ms, góc TF so với joint lệch tối đa 0,000015°. Pose rig và bốn vật trong bản sao world khớp mẫu pose Gazebo thu được. [Audit capture](capture_audit.csv) · [Kiểm tra pose](pose_check.json)
- Suy luận YOLOE và Metric3D v2 ViT-Small 616×1064 trong lượt ROS, chỉ dùng RGB và K cần thiết. A giữ nguyên Z đại diện. B dùng hệ số cố định 1,3720333573615522 và biên hợp lệ đã khóa. Hai nhánh dùng cùng UV, K, TF, confidence, bộ lọc và thứ tự 59 quan sát. B tính lại range vì range quyết định trọng số gộp. Dữ liệu GT chỉ dùng để chấm. [Tệp khóa](locked.json) · [Kế hoạch và quy tắc](PLAN.md)
- Dùng các hàm association, schema SQLite và query của LOC3D. A tái lập toàn bộ quan sát và object live, gồm liên kết, trạng thái và XYZ, sau khi bỏ timestamp ghi DB. Chấm instance theo mask IoU ≥0,5 và đúng lớp. Một bản ghi cuối chỉ được chấm vị trí khi tất cả quan sát cùng thuộc đúng một instance. XY/XYZ đo tới tâm mesh. Phạm vi precision và duplicate chỉ gồm bản ghi có bằng chứng từ bốn vật mục tiêu. [Replay](replay.log) · [Audit association](association_audit.csv)

## 2. Vị trí cuối cùng trong SQLite

| Vật | Detection đúng / thấy GT | Quan sát đúng qua lọc depth | Xác nhận A / B | XY A → B | XYZ A → B |
| --- | ---: | ---: | --- | ---: | ---: |
| Chai | 6/6 | 6 | Có / Có | 45,2 → **11,9 cm** | 45,7 → 11,9 cm |
| Laptop | 3/6 | 3 | Có / Có | 40,4 → **3,1 cm** | 40,6 → 6,2 cm |
| Cốc | 5/6 | 5 | Không / Không | — | — |
| Sách | 0/3 | 0 | Không / Không | — | — |

Chai giảm 33,3 cm và laptop giảm 37,3 cm XY. B không thay đổi tập vật được xác nhận. Cốc có sai số XY trung bình **trước gộp** giảm từ khoảng 19 xuống 11 cm, nhưng AbsRel của Z đại diện tăng nhẹ từ khoảng 15% lên 16%. Cốc chưa có vị trí cuối được xác nhận để kết luận hiệu quả trong SQLite. [Điểm depth và XYZ từng quan sát](depth_scores.csv)

| Chỉ số | A | B | Đánh giá |
| --- | ---: | ---: | --- |
| Depth MAE đại diện, 14 cặp | 27,8 cm | 11,3 cm | Đo với median axial GT trên phần giao mask erode và instance |
| Depth bias đại diện | −27,8 cm | +4,5 cm | Bias đổi dấu sau B |
| Depth AbsRel ≤15% | 23,6% | 10,9% | FAIL → PASS |
| XY trung bình / trung vị, 2 vật | 42,8 / 42,8 cm | 7,5 / 7,5 cm | Trung vị ≤30 cm, FAIL → PASS |
| XY P90 ≤60 cm, 2 vật | 44,7 cm | 11,0 cm | PASS cả hai trên mẫu hiện có |
| XYZ trung bình / trung vị / P90 | 43,1 / 43,1 / 45,2 cm | 9,0 / 9,0 / 11,3 cm | 2 vật ghép cặp |
| Recall detection trên instance–khung thấy | 14/21 (66,7%) | 14/21 (66,7%) | FAIL nếu áp mục tiêu 80% |
| Recall xác nhận và định vị trong 0,5 m | 2/4 (50%) | 2/4 (50%) | FAIL mục tiêu ≥80% |
| Precision trong phạm vi có GT | 2/2 (100%) | 2/2 (100%) | PASS ngưỡng 85% trên hai bản ghi |
| Bản ghi sai / trùng trong phạm vi GT | 0 / 0 | 0 / 0 | PASS ngưỡng trùng ≤10% trên hai bản ghi |
| Toàn cảnh confirmed / rejected | 5 / 7 | 5 / 8 | Ba confirmed ngoài phạm vi GT ở mỗi nhánh |
| Thời gian association và ghi SQLite offline | 5,66 s | 5,70 s | Gồm I/O và finalize, không phải chi phí riêng của phép nhân |

Thời gian suy luận đo bên trong lượt ROS gồm YOLOE 9,27 s, Metric3D 77,31 s và hậu xử lý ảnh 1,29 s, cộng trên 24 khung. Ba khung tại cùng góc gần như lặp lại. Precision, tỷ lệ trùng và P90 với hai vật chỉ mô tả lượt này. [Số liệu chưa làm tròn](summary.json)

## 3. Chẩn đoán YOLOE, bộ lọc và SQLite

| Vật | Thấy GT | Đúng lớp và mask | Sai lớp | Bỏ sót | Bị loại và lý do |
| --- | ---: | ---: | ---: | ---: | --- |
| Chai | 6 | 6 | 0 | 0 | Qua depth và xác nhận từ góc 0° và 315° |
| Laptop | 6 | 3 | 0 | 3 | Nhận đủ ở 0°. Ở 45° chỉ còn 401 px GT sát mép phải, không có detection khớp |
| Cốc | 6 | 5 | 0 | 1 | Cả năm detection bị gắn `truncated`. Association vẫn lưu đủ năm nhưng reject vì không có quan sát nào trọn khung theo bbox YOLOE |
| Sách | 3 | 0 | 0 | 3 | Panoptic còn 12.236 px mỗi khung ở 0° và chạm mép dưới. Không có mask nào khớp. Không lặp lại lỗi sách thành chai của mốc cũ |

Cốc ở 0° có GT đến hàng 717/719, đủ pixel nhưng nằm trong biên cảnh báo. Ở 45°, GT chạm cả mép phải và dưới. Hai khung được nhận ở 45° có confidence khoảng 0,354–0,357, sát ngưỡng YOLOE 0,35. Chúng được gắn vào object cốc đã tạo ở 0° dù thấp hơn ngưỡng tạo object 0,40. Không có detection đúng nào bị loại vì depth trong batch. [Từng vật, từng góc](visibility_by_frame.csv) · [Từng detection và liên kết DB](detection_audit.csv)

Probe offline chỉ chạy YOLOE trên một khung đại diện mỗi trường hợp bỏ sót có ít nhất 1.000 px GT, với nguyên ngưỡng 0,35. Trong các box trước NMS có IoU box ≥0,5, điểm lớp sách tối đa **0,187** (box IoU 0,956) ở 0° và điểm lớp cốc tối đa **0,341** (box IoU 0,964) ở 45°. Cả hai điểm cao nhất đều mang đúng lớp, nhưng dưới ngưỡng. Đây là bằng chứng về bước lọc ở hai khung probe, còn tác động riêng của cắt mép lên điểm lớp sách chưa được kiểm chứng. [Probe điểm thô](raw_score_probe.json)

B tách cụm quan sát `dining table` nền gồm bốn quan sát của A thành hai cụm 1 và 3. Cả hai đều bị reject trong B. Đây là ảnh hưởng thật của hiệu chỉnh lên association. Các cụm chai, laptop và cốc giữ nguyên số quan sát. Không có merge cuối ở cả hai nhánh.

**Metadata confidence SQLite vẫn lỗi.** Ví dụ chai có sáu confidence với tổng thực tế 5,1795 và trung bình 0,8633, nhưng SQLite lưu 0,8941 và 0,2880 ở cả A/B. `association.add_observation` đọc `conf_sum` để cập nhật, trong khi `db.update_object` chỉ ghi `conf_mean`. Lượt này xác nhận ảnh hưởng đến confidence trả về bởi query, còn xác nhận và XYZ tái lập giữa ROS và replay A. Ngoài ra, SQLite live lưu 236/236 trường tọa độ bbox dưới dạng BLOB float32 do kiểu giá trị truyền từ ROS. Replay giữ cùng cách lưu để đối chiếu. [Audit trường confidence và liên kết](association_audit.csv)

## 4. Trạng thái kiểm thử

| Hạng mục | Kết quả | Bằng chứng |
| --- | --- | --- |
| Capture 360°, CameraInfo/TF và GT | PASS | 24/24 khung, không bỏ điểm ở lượt chính, pose đã đối chiếu |
| Nhận diện và xác nhận đủ mục tiêu | FAIL | 14/21 instance–khung đúng và 2/4 vật confirmed đúng |
| Replay A so SQLite ROS và SQLite integrity | PASS | 59/59 quan sát, mọi bản ghi và liên kết tái lập, kiểm tra DB và khóa ngoại qua |
| Truy vấn và approach 0,6 m | PASS | Service ROS live trả năm confirmed. Query trên hai DB replay và CLI qua. Kiểm tra điểm tiếp cận nằm trên đoạn camera–vật và yaw hướng vào vật |
| Confidence SQLite | FAIL | Lỗi `conf_sum/conf_mean` tái hiện với quan sát thật |
| Điều hướng tránh vật cản từ approach point | NOT TESTED | Chỉ kiểm tra hình học điểm và yaw |
| Khả năng tổng quát sang các bố trí khác | NOT TESTED | Một bố trí Kitchen, 8 hướng rig, hai vật có vị trí cuối hợp lệ |
| Regression | PASS | 58/58 LOC3D, 79/79 YOLOE. [LOC3D](regression_loc3d.log) · [YOLOE](regression_yoloe.log) |

## Một việc nên thử tiếp

**Bổ sung một góc chụp được định trước để toàn bộ cốc và sách nằm trong khung**, với cùng checkpoint, prompts và ngưỡng. Kiểm tra có đủ quan sát cốc không sát mép để xác nhận, đồng thời xem điểm lớp sách thay đổi thế nào khi nhìn trọn vật. Đây là phép thử trực tiếp vào hai trường hợp mất recall trong batch này.

## Artifact và lệnh thực tế

- [Ảnh đủ tám góc](all_stops.jpg) · [Ví dụ lỗi ở 0°](issue_stop_00_frame_0.jpg) · [Ví dụ lỗi ở 45°](issue_stop_01_frame_0.jpg)
- [SQLite A](replay_A.sqlite) · [SQLite B](replay_B.sqlite) · [SQLite ROS live](db/scan_1794316856.sqlite) · [Query replay](query_audit.json) · [Query ROS live](query_live.log)
- `frames/` chứa 24 NPZ RGB, depth GT, panoptic, predicted depth và mask nén. Các tệp `audit_scan_*.json` chứa K, TF, timestamp và detection. `manifest.json` lưu SHA-256, thông tin checkpoint, 50 mục baseline cũ và 78 mục dữ liệu fit đã đối chiếu. [Manifest](manifest.json)

WSL chạy trong `/mnt/d/loc3d_ws`, `BATCH` là thư mục báo cáo. Log giữ lệnh launch và thời gian của cả hai lần khởi động.

~~~bash
bash "$BATCH/run.sh"
ros2 service call /scan/run/_action/cancel_goal action_msgs/srv/CancelGoal '{}'
bash "$BATCH/run_ready.sh"
.venv/bin/python "$BATCH/replay.py"
.venv/bin/python tools/query_db.py "$BATCH/replay_A.sqlite" --all --stats
.venv/bin/python tools/query_db.py "$BATCH/replay_B.sqlite" --all --stats
.venv/bin/python "$BATCH/raw_score_probe.py"
.venv/bin/python -m pytest -q -s -p no:cacheprovider --basetemp="$BATCH/tmp/pytest" tests
/usr/bin/python3 "$BATCH/pose_check.py" "$BATCH/initial_incomplete/gazebo_pose_sample.txt" "$BATCH/final_gazebo_pose.txt"
~~~

~~~powershell
D:\yoloe_test\.venv\Scripts\python.exe "$batch\prepare.py" "$batch"
D:\yoloe_test\.venv\Scripts\python.exe -m unittest discover -s tests
D:\yoloe_test\.venv\Scripts\python.exe "$batch\manifest.py"
~~~

Lệnh unittest chạy từ `D:\yoloe_test`. Lượt chính chạy probe query ROS trong `run_ready.sh` trước khi dừng launch. Script, cấu hình và output của phép thử được lưu trong thư mục batch.
