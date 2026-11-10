# Quét 360°, hình học và gộp quan sát

Lượt 36×1 giữ nguyên recall xác nhận (3/4 → 3/4). XY trung vị của các vật được xác nhận là 38,7 cm ở 8×3 và 37,7 cm ở 36×1. So sánh ghép cùng vật nằm bên dưới. Thời gian RunScan thật lần lượt 180,1 và 308,5 s.

## 1. RunScan và thông tin theo góc

| Chỉ số | A1 8×3 | A2 8×1 | B1 36×1 |
| --- | --- | --- | --- |
| Detection đúng / instance–khung thấy | 12/21 (57,1%) | 4/7 (57,1%) | 20/30 (66,7%) |
| Sai lớp / bỏ sót / truncated | 0 / 9 / 0 | 0 / 3 / 0 | 0 / 10 / 4 |
| Confirmed / định vị trong 0,5 m | 3/4 / 3/4 | 0/4 / 0/4 | 3/4 / 3/4 |
| Precision | 100,0% | — | 100,0% |
| Depth AbsRel | 25,4% | 25,3% | 23,7% |
| XY trung vị / P90 (cm) | 38,7 / 43,6 | — / — | 37,7 / 45,1 |
| XYZ trung vị / P90 (cm) | 38,8 / 44,0 | — / — | 37,8 / 45,6 |
| Sai association / trùng | 0 / 0 | 0 / 0 | 0 / 0 |
| RunScan thực (s) | 180,1 | NOT TESTED, lấy frame đầu | 308,5 |

| Vật | Đúng/thấy 8×3 | XY 8×3 (cm) | Đúng/thấy 36×1 | XY 36×1 (cm) |
| --- | --- | --- | --- | --- |
| book_1 | 0/3 (0 góc) | — | 2/7 (2 góc) | — |
| bottle_1 | 6/6 (2 góc) | 44,8 | 7/8 (7 góc) | 47,0 |
| cup_1 | 3/6 (1 góc) | 26,3 | 4/7 (4 góc) | 21,5 |
| laptop_1 | 3/6 (1 góc) | 38,7 | 7/8 (7 góc) | 37,7 |

Kết quả đầu ra hoặc trạng thái probe được ghi trong CSV.

Cùng scene đã khóa, camera, checkpoint và quy tắc lọc. Lượt 8×3 đầu thiếu quartet ở 225°, lượt 36×1 đầu bị hủy sau khi thiếu ở 40° và 180°. Hai lượt chính đồng bộ quartet qua Gazebo native, còn ROS thực hiện RunScan, perception, TF2, association và ghi SQLite. Lượt 8×3 chính bỏ một observation ghế nền thiếu XYZ trong phản hồi ROS, đồng nhất với SQLite live. Lượt 36×3 NOT TESTED. B1 chạy ROS thật bằng 10° và một frame mỗi điểm. A2 lấy frame index 0. Bốn góc 0°, 90°, 180°, 270° có đối chiếu riêng, các bộ thu ở thời điểm khác nhau. Bằng chứng che khuất trong CSV kiểm tra tia tới tâm với GT mặt trước, nên không diễn giải thành diện tích phần bị che. Cả ba số recall là trên bốn vật hoặc các instance–khung của một bố trí. [Góc và detection](detection_by_angle.csv) · [Depth theo góc](depth_by_angle.csv) · [Góc trùng](shared_angles.csv) · [Probe sách](book_angle_probe.csv) · [Biểu đồ](angle_diagnostics.png) · [Ảnh 8 góc](scan_8x3/all_stops.jpg) · [Ảnh 36 góc](scan_36x1/all_stops.jpg)

## 2. Gộp robust

| Fusion | XY trung vị/P90 (cm) | XYZ trung vị/P90 (cm) | Confirmed | Sai/trùng | Tốt/xấu | Tính (ms) |
| --- | --- | --- | --- | --- | --- | --- |
| F0_production | 37,7 / 45,1 | 37,8 / 45,6 | 3 | 0/0 | 0/0 | xem runtime DB |
| F1_geomedian | 39,9 / 46,4 | 40,0 / 46,9 | 3 | 0/0 | 0/3 | 19,7 |
| F2_huber | 38,6 / 45,8 | 38,7 / 46,2 | 3 | 0/0 | 0/3 | 22,7 |
| F3_RANSAC | 40,3 / 45,2 | 40,4 / 45,6 | 3 | 0/0 | 1/1 | 1,1 |
| F4_quality | 38,4 / 45,1 | 38,5 / 45,5 | 3 | 0/0 | 1/2 | 2051,5 |
| F5_angle_equal | 36,4 / 47,1 | 36,5 / 47,6 | 3 | 0/0 | 2/1 | 0,3 |
| F5_angle_one | 37,7 / 48,3 | 37,7 / 48,7 | 3 | 0/0 | 1/2 | 0,3 |

RANSAC thử tâm điểm 3D, kiểm tra khoảng cách inlier và độ phủ yaw. 4/7 cụm đủ điều kiện; phần còn lại dùng kết quả gốc. F1–F5 dùng membership và trạng thái sau association F0, nên chỉ đánh giá ảnh hưởng lên vị trí cuối. F5 phân biệt ảnh lặp và các ô yaw, giữ nhóm để so công bằng. [CSV fusion](fusion_comparison.csv) · [RANSAC](ransac_diagnostics.csv)

## 3. Mặt sàn và metric scale

| Tập | n frame | RGB áp dụng | ORACLE áp dụng | Pixel sàn GT trung vị | IoU floor trung bình |
| --- | --- | --- | --- | --- | --- |
| scan_8x3 | 24 | 0 | 6 | 0 | 0,000 |
| scan_36x1 | 36 | 0 | 5 | 0 | 0,000 |
| aws | 18 | 16 | 18 | 254082 | 0,836 |
| tiffany | 18 | 0 | 18 | 92089 | 0,000 |

| Tập | Phương án | n | Depth MAE cm | AbsRel | Bias cm | XY trung vị/P90 cm | XYZ trung vị/P90 cm | Depth tốt/xấu |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| scan_8x3 | original | 12 | 32,1 | 25,4% | -32,1 | 37,4 / 51,6 | 37,6 / 52,2 | 0 / 0 |
| scan_8x3 | kitchen_locked | 12 | 10,6 | 8,6% | 3,6 | 8,4 / 20,6 | 9,9 / 20,7 | 12 / 0 |
| scan_8x3 | rgb | 12 | 32,1 | 25,4% | -32,1 | 37,4 / 51,6 | 37,6 / 52,2 | 0 / 0 |
| scan_8x3 | oracle | 12 | 14,2 | 12,1% | -11,0 | 8,4 / 51,6 | 8,8 / 52,2 | 9 / 0 |
| scan_36x1 | original | 20 | 29,5 | 23,7% | -29,5 | 35,1 / 52,1 | 35,4 / 52,7 | 0 / 0 |
| scan_36x1 | kitchen_locked | 20 | 14,6 | 11,7% | 6,1 | 11,5 / 29,6 | 11,8 / 29,9 | 16 / 4 |
| scan_36x1 | rgb | 20 | 29,5 | 23,7% | -29,5 | 35,1 / 52,1 | 35,4 / 52,7 | 0 / 0 |
| scan_36x1 | oracle | 20 | 25,1 | 20,4% | -23,2 | 28,3 / 52,1 | 29,4 / 52,7 | 7 / 1 |
| aws | original | 13 | 41,7 | 25,8% | -41,7 | 42,0 / 66,7 | 42,4 / 67,0 | 0 / 0 |
| aws | kitchen_locked | 13 | 5,5 | 3,6% | 1,8 | 5,2 / 11,5 | 5,7 / 11,5 | 13 / 0 |
| aws | rgb | 13 | 13,3 | 8,5% | -13,3 | 16,6 / 39,1 | 16,6 / 39,5 | 11 / 0 |
| aws | oracle | 13 | 8,6 | 5,1% | -8,6 | 12,9 / 19,3 | 13,6 / 19,4 | 13 / 0 |
| tiffany | original | 10 | 85,2 | 51,6% | -85,2 | 85,6 / 107,0 | 86,6 / 107,6 | 0 / 0 |
| tiffany | kitchen_locked | 10 | 55,0 | 33,6% | -55,0 | 57,2 / 77,9 | 57,6 / 78,7 | 10 / 0 |
| tiffany | rgb | 10 | 85,2 | 51,6% | -85,2 | 85,6 / 107,0 | 86,6 / 107,6 | 0 / 0 |
| tiffany | oracle | 10 | 20,5 | 12,6% | -20,5 | 22,4 / 36,5 | 22,5 / 36,5 | 10 / 0 |

Tia đơn vị axial được tạo từ K, xoay bằng TF rồi giao mặt phẳng ngang. Loại tia sau camera, gần chân trời và ngoài dải. Hệ số RGB dùng mask YOLOE floor và depth dự đoán, rồi median theo ô ảnh. ORACLE chỉ dùng để chẩn đoán giới hạn, nhận diện sàn bằng depth GT gần mặt phẳng. Thiếu pixel/ô, ratio phân tán hoặc ngoài dải thì trả về gốc. Nhiễu chiều cao ±2 cm và pitch ±1° có trong CSV với các nhánh riêng. AWS/Tiffany là dữ liệu chẩn đoán có sẵn, mỗi điều kiện camera đứng yên, không dùng để fit hệ số GT hay xác nhận fusion nhiều góc. [Sàn Kitchen](ground_plane_feasibility.csv) · [Hiệu chỉnh Kitchen](ground_plane_correction.csv) · [Sàn ngoại phòng](crossworld_floor_frames.csv) · [Depth ngoại phòng](crossworld_check.csv)

## 4. Triangulation

Baseline quang học lớn nhất 10,0 cm trong 630 cặp TF. 25/36 cặp chồng quan sát có độ nhạy dưới 10 cm ở nhiễu 1 px. Chọn cặp chẩn đoán theo association cùng lớp và baseline. Correspondence ORB dùng RGB và mask YOLOE, rồi kiểm cheirality và reprojection ≤1 px. Nhãn GT và depth GT chỉ chấm sau đó. Độ nhạy nhiễu dùng cùng một điểm giả định chiếu vào hai camera, tránh giả định hai tâm mask là cùng điểm.

| Vật | Stop A/B | Baseline cm | ΔZ 0,5 / 1 / 2 px cm | ORB match / qua hình học | n GT / median cm |
| --- | --- | --- | --- | --- | --- |
| laptop_1 | 3/34 | 4,2 | 1,6 / 3,3 / 6,8 | 77/71 | 65 / 2,9 |
| laptop_1 | 3/35 | 3,4 | 2,3 / 4,7 / 9,9 | 92/85 | 76 / 3,6 |
| laptop_1 | 2/34 | 3,4 | 2,0 / 4,2 / 8,6 | 100/91 | 84 / 4,1 |
| laptop_1 | 0/3 | 2,6 | 2,4 / 4,9 / 10,2 | 107/90 | 87 / 4,6 |
| cup_1 | 0/3 | 2,6 | 2,0 / 4,0 / 8,3 | 130/121 | 117 / 3,7 |
| cup_1 | 0/2 | 1,7 | 3,2 / 6,7 / 14,4 | 223/218 | 215 / 2,5 |
| cup_1 | 1/3 | 1,7 | 3,0 / 6,1 / 13,1 | 134/125 | 125 / 5,0 |
| cup_1 | 1/2 | 0,9 | 6,7 / 14,4 / 33,6 | 239/230 | 229 / 9,9 |
| bottle_1 | 1/32 | 4,2 | 1,0 / 1,9 / 4,0 | 109/102 | 101 / 2,3 |
| bottle_1 | 1/33 | 3,4 | 1,4 / 2,8 / 5,7 | 81/72 | 71 / 2,6 |
| bottle_1 | 0/32 | 3,4 | 1,2 / 2,5 / 5,2 | 76/68 | 67 / 2,7 |
| bottle_1 | 32/35 | 2,6 | 1,2 / 2,4 / 5,0 | 102/97 | 96 / 3,2 |

[Chi tiết](triangulation_feasibility.md) · [Tâm quang học](optical_trajectory.csv) · [Các cặp baseline](optical_baselines.csv)

## 5. Temporal và chọn góc

| Keyframe | Gọi depth / tiết kiệm | Confirmed | AbsRel | XY median/P90 cm | Propagation / ID sai có GT | Tuổi P90 s | Depth dự kiến s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T1_full | 36/0 | 3 | 23,7% | 37,7 / 45,1 | 0 / 0 | — | 155,1 |
| T2_every20 | 18/18 | 3 | 22,3% | 35,0 / 44,6 | 14 / 0 | 5,4 | 78,3 |
| T2_every30 | 12/24 | 3 | 23,6% | 36,0 / 44,4 | 15 / 0 | 9,4 | 52,2 |
| T2_adaptive | 13/23 | 3 | 23,8% | 36,9 / 45,0 | 15 / 0 | 9,4 | 55,8 |

| Góc | Gọi depth | Confirmed | AbsRel | XY median/P90 cm | Sai/trùng | Depth dự kiến s |
| --- | --- | --- | --- | --- | --- | --- |
| full | 36 | 3 | 23,7% | 37,7 / 45,1 | 0/0 | 155,1 |
| V_equal | 12 | 0 | 21,6% | — / — | 0/0 | 52,2 |
| V_quality | 12 | 3 | 23,7% | 37,7 / 45,1 | 0/0 | 48,7 |
| V_diverse | 12 | 2 | 23,6% | 43,6 / 47,2 | 0/0 | 50,9 |

Ở non-key, dùng track điểm world gần nhất nếu projection lọt mask, khớp lớp duy nhất và đủ điều kiện tuổi/góc. Các observation lan truyền là bằng chứng nhận diện mới cho vị trí cũ, không phải đo depth độc lập. Chi phí depth dự kiến tính bằng thời gian Metric3D đã đo của chính keyframe, còn việc chọn góc chất lượng vẫn đòi xem RGB/YOLOE của các góc. Runtime của các nhánh là offline, ROS end-to-end chỉ đo A1 và B1. [Temporal](temporal_keyframe_results.csv) · [Viewpoint](viewpoint_selection.csv)

## 6. Toàn pipeline và thời gian

| Nhánh | Phương pháp | Recall | AbsRel | XY median/P90 cm | Sai/trùng | Thời gian | Trạng thái |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P0 | A1_8x3 | 75,0% | 25,4% | 38,7 / 43,6 | 0/0 | 180,1 s ROS | MEASURED_BELOW_TARGET |
| A2 | A2_8x1 | 0,0% | 25,3% | — / — | 0/0 | 0,867 s offline | MEASURED_BELOW_TARGET |
| P1 | B1_36x1 | 75,0% | 23,7% | 37,7 / 45,1 | 0/0 | 308,5 s ROS | MEASURED_BELOW_TARGET |
| P2 | F5_angle_equal | 75,0% | 23,7% | 36,4 / 47,1 | 0/0 | 0,000 s offline | FAIL_GAIN_GATE |
| P3 | P3_ground_rgb | 75,0% | 23,7% | 37,7 / 45,1 | 0/0 | 2,437 s replay + 4,8 s CPU floor | FALLBACK_ALL_FRAMES |
| P4 | T2_every20 | 75,0% | 22,3% | 35,0 / 44,6 | 0/0 | 2,318 s offline | MEASURED_BELOW_TARGET |
| P5 | V_quality | 75,0% | 23,7% | 37,7 / 45,1 | 0/0 | 2,386 s offline | MEASURED_COST_SAVINGS |
| P6 | — | — | — | — / — | — | — | NOT TESTED |

| Scan | RunScan s | Settle s | Capture service s | YOLOE s | Metric3D s | Replay+DB s | Query offline s | Peak MiB | Thiếu XYZ live |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| scan_8x3 | 180,068 | 12,000 | 159,200 | 14,358 | 106,949 | 1,621 | 0,028 | 1665 | 1 |
| scan_36x1 | 308,510 | 54,000 | 233,451 | 18,598 | 155,121 | 2,214 | 0,032 | 3329 | 0 |

GPU GTX 1650, peak lấy mẫu thiết bị 3329 MiB, bao gồm Gazebo và tiến trình khác nếu có. Jetson Xavier và navigation tránh vật cản NOT TESTED. Query và approach 0,6 m được kiểm tra hình học. Regression 59 LOC3D, 79 YOLOE, 4 test diagnostic hình học/robust đều qua. [Phương án](pipeline_comparison.csv) · [Runtime](runtime_summary.csv) · [LOC3D](regression_loc3d_final.log) · [YOLOE](regression_yoloe_final.log) · [Hình học](regression_geometry_final.log)

## 7. Kết luận

1. **36 góc tăng nhận diện nhưng chưa cải thiện định vị nhất quán.** Detection recall theo instance–khung tăng từ 12/21 lên 20/30, tương đương 57,1% → 66,7%. Cả hai xác nhận đúng 3/4 vật. XY trung vị giảm khoảng 1,0 cm nhưng P90 tăng khoảng 1,6 cm. Lượt 36×1 mất thêm 128,4 s trên GTX 1650. Đối chứng 8×1 xác nhận 0/4 vì số quan sát mỗi vật không đủ điều kiện hiện hành.
2. **Sách có tín hiệu mới.** Hai mask đúng ở 330° và 340°, confidence 0,381 và 0,399, IoU 0,968 và 0,948. Cả hai truncated, dưới cả ngưỡng confidence tạo cụm mới 0,40. Với chỉ hai quan sát, sách cũng chưa đạt min_obs = 3.
3. **Giữ weighted mean làm mốc gộp.** F5 cân bằng góc có XY trung vị 36,4 cm thay vì 37,7 cm, nhưng P90 tăng từ 45,1 lên 47,1 cm. F1 và F2 làm cả ba vật xấu đi. F3 nhận 4/7 cụm toàn cảnh, trong ba vật chấm XY có một tốt hơn, một xấu hơn và một không đổi. Trung vị F3 tăng lên 40,3 cm. Tất cả observations của từng vật nằm về một phía của tâm GT theo hướng sai số trung bình. [Audit sai lệch cụm](fusion_bias_diagnostics.csv)
4. **Geometry sàn có điều kiện.** YOLOE floor không cho scale được chấp nhận ở cả 60 khung Kitchen. Oracle đủ điều kiện ở 6/24 và 5/36. Trên AWS, RGB áp dụng được ở 16/18 khung, IoU sàn trung bình khoảng 0,84 và AbsRel trên detection được chấm giảm khoảng 25,8% → 9%. Trên Tiffany RGB áp dụng 0/18 dù oracle có thể hiệu chỉnh. Ở AWS, sai lệch pose thử nghiệm đưa AbsRel khoảng 6–15%. Chiều cao và phép chiếu có thể cung cấp tham chiếu metric khi nhận diện được sàn và có tia hợp lệ.
5. **Triangulation khả thi ở một số cặp Gazebo.** Các cặp ORB được thử có baseline 0,87–4,22 cm. Sai số axial trung vị theo cặp là 2,35–9,89 cm trên các điểm được chấm. Nhiễu 1 px gây sai số dự kiến 1,9–14,4 cm tùy cặp. Đây là phép đo điểm bề mặt trên vật có texture, chưa đánh giá tâm vật cuối trong SQLite, cảnh động hoặc camera thật.
6. **Giảm số lượt depth có triển vọng về chi phí.** Keyframe 30° dùng 12 thay vì 36 lần chạy, thời gian Metric3D dự kiến 52,2 thay vì 155,1 s. Giữ 3/4 vật, XY trung vị 36,0 cm, P90 44,4 cm. Một trong ba vật xấu đi. V_quality cũng dùng 12 lượt và tái lập kết quả B1 trên bố trí này; cần YOLOE qua toàn lượt để chọn. Cả hai đều là replay offline.
7. **Kết hợp P6 và kiểm chứng độc lập.** Chỉ T2 mỗi 20° qua ngưỡng cải thiện trung vị 2 cm đã khóa. Nhánh này làm hai trong ba vật xấu đi. F5 không qua ngưỡng, P3 fallback toàn lượt Kitchen, và viewpoint chất lượng là lựa chọn giảm chi phí cùng loại với keyframe. Không có cặp thành phần phù hợp để tiến tới holdout P6. P6 và Xavier là NOT TESTED. Các nhánh Kitchen đã đo chưa đạt đồng thời AbsRel ≤15%, XY trung vị ≤30 cm và recall ≥80%. Nút thắt định vị hiện là depth lệch có hệ thống; nút thắt recall là sách chỉ được thấy đúng ở góc bị cắt.

**Ưu tiên tiếp theo duy nhất** là khóa các kiểm tra match và reprojection ORB đã dùng, rồi kiểm chứng triangulation trên một bố trí Kitchen mới. Chấm cả độ chính xác điểm bề mặt lẫn XY tâm vật cuối, với số vật và số cặp đủ điều kiện được báo riêng.

## Artifact và lệnh chạy

[Thiết kế khóa](PLAN.md) · [SQLite A1](scan_8x3/replay_A.sqlite) · [SQLite A2](A2_8x1.sqlite) · [SQLite B1](scan_36x1/replay_A.sqlite) · [Log 8×3 lần thiếu](scan_8x3_incomplete/launch.log) · [Log 36×1 lần hủy](scan_36x1_incomplete/launch.log) · [Manifest](manifest.json)

Chạy trong WSL tại /mnt/d/loc3d_ws. Thư mục batch chứa run_scans.sh, analyze_complete.sh và các script từng nhánh. Dùng môi trường LOC3D hiện có để replay, venv Windows yoloe_test để chạy unittest. Tìm theo tên Consensus và log nghiên cứu trong hai workspace đã nêu, không tìm thấy tài liệu tương ứng.

Lệnh thực tế (WSL, từ /mnt/d/loc3d_ws; $BATCH là đường dẫn thư mục báo cáo).

~~~bash
bash "$BATCH/run_scans.sh"                 # hai lượt đầu, giữ log thiếu/hủy
ros2 service call /scan/run/_action/cancel_goal action_msgs/srv/CancelGoal '{}'
bash "$BATCH/run_native_retries.sh"        # hai lượt đầy đủ, qua ROS RunScan
.venv/bin/python "$BATCH/ground.py" external
bash "$BATCH/analyze_complete.sh"          # methods, angles, book_probe, ground, pipeline_summary
bash "$BATCH/post_batch.sh"                # pose Gazebo, hình học diagnostic, pytest LOC3D
.venv/bin/python "$BATCH/write_report.py"
~~~

Trên Windows chạy D:\yoloe_test\.venv\Scripts\python.exe -m unittest discover -s D:\yoloe_test\tests. Xác minh SHA-256 bằng verify_batch.py. Việc sửa thu đồng bộ nằm trong use_native_sync.py, chỉ áp dụng lên audit.py bản sao trong batch.
