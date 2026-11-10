# Kiểm chứng Metric3D v2 trên ba world và Kitchen 360°

**AWS hỗ trợ một hệ số tỷ lệ gần ổn định trong bố trí đã thử. Tiffany cần thận trọng hơn.** Hệ số riêng Tiffany giảm mạnh XY nhưng thay đổi theo khoảng cách và loại vật. Kitchen 360° cuối xác nhận đúng 3/4 vật với hệ số Kitchen, XY trung vị 38,7 → **11,6 cm** so với nhánh gốc trên cùng dữ liệu.

## 1. Calibration và độ ổn định

AWS và Tiffany mỗi phòng có 45 điều kiện mới, gồm 27 calibration (3 vật × 1,25/1,60/2,00 m × 0°/45°/90°) và 18 holdout (3 vật × 1,42/2,15 m × 15°/55°/105°). Mỗi điều kiện chỉ dùng một bộ RGB/depth/panoptic/CameraInfo cùng stamp. Cả hai phòng có 45/45 điều kiện qua QA. Camera cố định trong mỗi world, cao 0,36 m trong hai phòng mới để tránh cắt laptop gần. Điều này khác batch trước. Không quy khác biệt giữa hai batch cho riêng model hay world. Dùng pose rig, pan và pose vật quan sát được từ Gazebo. K giữ 1280×720, HFOV 70°, fx = fy 914,014701 px, cx = 640 px, cy = 360 px. Metric3D ViT-Small giữ 616×1064. [Thiết kế AWS](aws/design.json) · [Thiết kế Tiffany](tiffany/design.json)

Fit cùng phương pháp Kitchen. Least squares dùng các pixel axial Z hợp lệ trong mask instance đã erode, với tổng trọng số bằng nhau cho mỗi điều kiện. Chọn tỷ lệ hoặc tuyến tính theo MAE cross-validation giữ lại từng nhóm khoảng cách. Báo thêm các fold theo vật và yaw. Kitchen giữ nguyên cả hệ số đã khóa và phương án tuyến tính trước đó. Độ ổn định Kitchen được đối chiếu bằng tỷ lệ GT/pred theo nhóm cũ. Hệ số được khóa trước khi chấm holdout mới. [Tệp khóa](crossworld_locked.json) · [Số đo calibration](calibration_by_world.csv) · [Nhóm ổn định](calibration_stability.csv) · [Các fold](calibration_cv.csv)

| World | Hệ số riêng | MAE CV gốc / tỷ lệ / tuyến tính | Mô hình chọn bằng CV | Ổn định |
| --- | ---: | ---: | --- | --- |
| Kitchen | 1,37203 | 42,1 / 9,6 / 13,7 cm | Tỷ lệ, giữ lock cũ | Tỷ lệ GT/pred trung vị theo khoảng cách 1,412–1,424, theo vật 1,314–1,463. Kết quả chỉ có giá trị trong dải đã đo |
| AWS | 1,31714 | 38,1 / 7,4 / 11,1 cm | Tỷ lệ | Hệ số nhóm theo khoảng cách 1,310–1,320, yaw 1,307–1,326, vật 1,282–1,385. AbsRel holdout trên mask GT 5,1%, mọi nhóm ≤6,7% |
| Tiffany | 1,97344 | 81,0 / 25,3 / 23,7 cm | Tuyến tính | Hệ số giảm từ 2,247 ở 1,25 m xuống 1,862 ở 2,00 m. Theo vật từ 1,781 cho cốc đến 2,235 cho laptop. AbsRel holdout bằng hệ số riêng vẫn 20,2% cho laptop và 17,3% ở yaw 55° |

AWS lệch −4,0% so với hệ số Kitchen và Tiffany cao hơn 43,8%. Đây là độ chênh số học trong mẫu, chưa phải kết luận ý nghĩa thống kê. Ở Tiffany, hiệu chỉnh tuyến tính đã chọn trước có AbsRel trên mask GT 7,9% và mọi nhóm ≤10,0%. Mô hình tỷ lệ đạt 13,1% khi gộp mẫu, nhưng bỏ sót sự khác biệt giữa các nhóm.

## 2. Kiểm tra chéo trên dữ liệu mới

Bảng 3×3 ghi **XY trung vị / AbsRel depth đại diện** trên detection ghép đúng instance, đúng lớp, IoU mask ≥0,5 và đủ QA. Các nhánh dùng cùng mask, UV, K và TF. Depth GT đại diện là median axial Z trên pixel hợp lệ của phần giao mask YOLOE erode và mask instance. Kitchen là lượt ROS mới ở phần 4, không dùng lượt 360° cũ làm test mới. Ba khung cùng góc của Kitchen có tương quan, nên n dưới đây là số detection, không phải số điều kiện độc lập.

| Hệ số lấy từ | Test Kitchen | Test AWS | Test Tiffany |
| --- | ---: | ---: | ---: |
| Kitchen | 8,4 cm / 8,8% | 5,2 cm / 3,6% | 57,2 cm / 33,6% |
| AWS | 5,4 cm / 6,6% | 10,5 cm / 4,1% | 62,1 cm / 36,3% |
| Tiffany | 67,1 cm / 47,2% | 66,7 cm / 46,4% | 6,3 cm / 7,8% |

Tuyến tính riêng AWS dùng 1,202875 × Z + 0,140827 m; Tiffany dùng 1,046262 × Z + 0,775164 m. Mỗi công thức có biên bảo vệ cố định từ lock cũ.

Với Metric3D gốc, XY trung vị / AbsRel lần lượt là Kitchen 37,2 cm / 25,4%, AWS 42,0 cm / 25,8%, Tiffany 85,6 cm / 51,6%.

[Nguồn world và commit](world_sources.json) · [Render AWS](aws/render.jpg) · [Render Tiffany](tiffany/render.jpg)

Khi thay mask YOLOE bằng mask GT chỉ để chấm depth trên mọi mẫu hợp lệ, AWS cho AbsRel 5,1% với hệ số AWS và 5,8% với hệ số Kitchen. Trên tập detection đúng, thứ tự đảo lại. Không có bằng chứng rằng hệ số riêng AWS thắng nhất quán. Tiffany cải thiện rõ khi dùng hệ số riêng, nhưng dùng hệ số đó ở AWS làm XY trung vị tăng từ 42,0 lên 66,7 cm. Sai số nhạy với môi trường, và batch không xác nhận được một hệ số chung dùng được ở cả ba world. Hệ số từng phòng cần axial GT để fit, hạn chế khi triển khai ở một phòng mới không có tham chiếu khoảng cách.

| World | Phương án | n | Depth MAE | AbsRel | Bias | XY TB / trung vị / P90 | XYZ TB / trung vị / P90 | XY tốt / xấu hơn gốc |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Kitchen | Gốc | 12 | 32,1 cm | 25,4% | -32,1 cm | 38,2 / 37,2 / 52,0 cm | 38,6 / 37,4 / 52,6 cm | 0 / 0 |
| Kitchen | Kitchen | 12 | 10,8 cm | 8,8% | 3,6 cm | 9,7 / 8,4 / 21,2 cm | 10,9 / 10,0 / 21,3 cm | 12 / 0 |
| Kitchen | AWS | 12 | 7,7 cm | 6,6% | -1,7 cm | 9,6 / 5,4 / 25,7 cm | 10,5 / 5,7 / 25,9 cm | 12 / 0 |
| Kitchen | Tiffany | 12 | 61,3 cm | 47,2% | 61,3 cm | 59,4 / 67,1 / 74,8 cm | 61,2 / 68,8 / 77,4 cm | 3 / 9 |
| Kitchen | Tuyến tính riêng | 12 | 10,4 cm | 8,3% | 7,9 cm | 9,0 / 7,8 / 15,0 cm | 10,0 / 8,6 / 15,5 cm | 12 / 0 |
| AWS | Gốc | 13 | 41,7 cm | 25,8% | -41,7 cm | 47,5 / 42,0 / 66,7 cm | 48,0 / 42,4 / 67,0 cm | 0 / 0 |
| AWS | Kitchen | 13 | 5,5 cm | 3,6% | 1,8 cm | 6,6 / 5,2 / 11,5 cm | 6,8 / 5,7 / 11,5 cm | 13 / 0 |
| AWS | AWS | 13 | 7,0 cm | 4,1% | -4,6 cm | 10,8 / 10,5 / 19,7 cm | 10,9 / 10,5 / 19,7 cm | 13 / 0 |
| AWS | Tiffany | 13 | 72,1 cm | 46,4% | 72,1 cm | 66,4 / 66,7 / 79,2 cm | 67,6 / 68,0 / 79,8 cm | 0 / 13 |
| AWS | Tuyến tính riêng | 13 | 7,9 cm | 4,5% | -3,9 cm | 10,4 / 7,9 / 22,5 cm | 10,6 / 7,9 / 22,6 cm | 13 / 0 |
| Tiffany | Gốc | 10 | 85,2 cm | 51,6% | -85,2 cm | 90,1 / 85,6 / 107,0 cm | 91,0 / 86,6 / 107,6 cm | 0 / 0 |
| Tiffany | Kitchen | 10 | 55,0 cm | 33,6% | -55,0 cm | 60,0 / 57,2 / 77,9 cm | 60,5 / 57,6 / 78,7 cm | 10 / 0 |
| Tiffany | AWS | 10 | 59,5 cm | 36,3% | -59,5 cm | 64,4 / 62,1 / 80,8 cm | 65,0 / 62,5 / 81,6 cm | 10 / 0 |
| Tiffany | Tiffany | 10 | 12,6 cm | 7,8% | -6,3 cm | 14,1 / 6,3 / 42,0 cm | 14,3 / 6,5 / 42,3 cm | 10 / 0 |
| Tiffany | Tuyến tính riêng | 10 | 15,0 cm | 8,8% | -3,9 cm | 15,8 / 12,9 / 24,5 cm | 16,1 / 13,3 / 24,6 cm | 10 / 0 |

Mục tiêu đồng thời là AbsRel ≤15%, XY trung vị ≤30 cm và P90 ≤60 cm. Các phương án đạt trên mẫu đã chấm gồm Kitchen / Kitchen, Kitchen / AWS, Kitchen / Tuyến tính riêng, AWS / Kitchen, AWS / AWS, AWS / Tuyến tính riêng, Tiffany / Tiffany, Tiffany / Tuyến tính riêng. AWS có 13/18 detection đúng (chai/cốc/laptop 6/3/4). Tiffany có 10/18 (6/2/2). Các mẫu còn lại thiếu match đúng. Không phát hiện sai lớp chồng lên instance ở IoU ≥0,5 trong hai holdout ngoài Kitchen. [Theo vật và phương án](holdout_summary.csv) · [Từng quan sát](holdout_scores.csv) · [Depth trên toàn mask GT và từng nhóm](holdout_dense_summary.csv) · [Các mẫu bị loại](holdout_coverage.csv)

## 3. Sách, cốc và bản vá SQLite

- **Sách.** Hai asset đều 0/3 detection đúng và 0/3 nhận nhầm chồng instance sau lọc, với pose gốc trên bàn và ba hướng bìa tương ứng. Box thô IoU 0,953–0,984 cho thấy model có box gần đúng nhưng điểm `book` chỉ 0,280–0,326 với sách cũ, 0,096–0,274 với mẫu thay thế, đều dưới 0,35. So sánh bổ sung chạy CPU với cùng checkpoint và ngưỡng để đọc điểm trước lọc. Giữ trọn khung và đổi asset chưa đủ để phục hồi detection. Chưa đủ bằng chứng quy lỗi riêng cho asset hay suy rộng sang mọi hình ảnh sách. Lần dựng mẫu thay thế đầu bị cắm xuống mặt bàn do đổi trục GLB, được giữ làm log QA và loại khỏi kết luận. Phép đối chứng dùng lần dựng đã sửa, GT xác nhận điểm thấp nhất khoảng z = 0,736–0,739 m trên mặt bàn 0,74 m. [QA trục và mặt bàn](book_fixture_qa.csv) · [CSV sách hợp lệ](book_asset_test_valid.csv) · [Ảnh sách cũ](kitchen_book_retry/00_book_1_1.47_0.jpg) · [Ảnh sách thay thế](kitchen_book_retry/01_book_alt_1.47_0.jpg) · [Nguồn Innerscene CC0](https://www.innerscene.com/tools/library/3d-parts/bound-three-books-b266be0c)
- **Cốc.** Sát mép và trọn khung đều đúng 3/3 detection, valid depth 100%. Bbox đáy khoảng hàng 718 ở vị trí cũ, vượt biên 8 px của pipeline. Ba detection đều truncated và object bị reject. Vị trí mới cho bbox đáy gần hàng 600, 0/3 truncated và cốc confirmed. Thử nghiệm thay vị trí cốc, do đó cũng thay khoảng cách và nền sau vật. Kết quả xác nhận cơ chế reject trong bố trí này. [CSV cốc](cup_visibility_test.csv) · [Trạng thái hai DB](kitchen_probe_summary.json) · [Ảnh sát mép](kitchen_probe/06_cup_1_0.97_0.jpg) · [Ảnh trọn khung](kitchen_probe/07_cup_1_1.42_0.jpg)
- **SQLite.** Test trước vá tái hiện tổng 0,9 thay vì 1,6. Bản vá cập nhật `conf_sum/conf_mean` ở cả đường thêm quan sát lẫn merge. Replay lịch sử giữ nguyên 59 quan sát, XYZ, liên kết và trạng thái 12 object, còn confidence chai tăng từ giá trị lưu sai 0,2880 lên giá trị đúng 0,8633. Các regression suite đạt 59/59 LOC3D và 79/79 YOLOE. [Bằng chứng và phạm vi bản vá](sqlite_confidence_test.md) · [Diff](sqlite_confidence.patch)

## 4. Kitchen ROS 360° sau sửa

RunScan `scan_1794324951` hoàn tất **24/24 bộ đồng bộ** tại 8 góc × 45°, 3 khung mỗi góc, chờ 1,5 s, trong **187,8 s**. Pose rig và vật kiểm tra bằng mẫu Gazebo. Sai lệch yaw lệnh tối đa 0,134°, lệch timestamp joint dùng đối chiếu TF tối đa 8 ms. A khớp toàn bộ **56** quan sát và kết quả SQLite live. Một observation chair nền ở 270° thiếu XYZ trong phản hồi ROS sau inference dù TF đầu khung đã được ghi. SQLite live bỏ observation này và cả hai nhánh replay dùng cùng 56 observation còn lại. Cả bốn vật mục tiêu nằm ngoài trường hợp thiếu này. A và B dùng cùng thứ tự quan sát và các hàm production. Query live và replay kiểm tra điểm tiếp cận 0,6 m, yaw và lọc theo lớp. [Log RunScan](kitchen_final/action.log) · [Pose](kitchen_final/pose_check.json) · [Query](kitchen_final/query_audit.json) · [CLI A](kitchen_final/query_A.log) · [CLI B](kitchen_final/query_B.log)

| Vật | Đúng / thấy GT | Sai lớp / bỏ sót | Qua depth | Confirmed A / B | XY A → B | XYZ A → B | Kết luận |
| --- | ---: | ---: | ---: | --- | ---: | ---: | --- |
| Chai | 6/6 | 0 / 0 | 6 | Có / Có | 45,0 → 11,6 | 45,4 → 11,6 | Đúng instance |
| Cốc | 3/6 | 0 / 3 | 3 | Có / Có | 26,2 → 12,0 | 26,8 → 12,4 | Đúng instance |
| Laptop | 3/6 | 0 / 3 | 3 | Có / Có | 38,7 → 4,9 | 38,8 → 7,7 | Đúng instance |
| Sách | 0/3 | 0 / 3 | 0 | Không / Không | — → — | — → — | Không có detection đúng |

XY và XYZ tính bằng cm. Số lần bỏ sót là số instance–khung không có detection đúng, gồm cả trường hợp sai lớp.

Toàn lượt thấy 4/4 vật và 21 instance–khung, có 12 đúng, 0 sai lớp và 9 bỏ sót. 12 quan sát đúng qua lọc depth. Recall detection 57,1%. Recall confirmed 75,0% → 75,0%, recall định vị trong 0,5 m 75,0% → 75,0%, precision trong phạm vi có GT 100,0% → 100,0%. Bản ghi sai / trùng A 0/0, B 0/0. Toàn cảnh confirmed A/B 6/6; vật nền thiếu GT không đi vào mẫu số. Confidence trong mọi object còn liên kết được đối chiếu trực tiếp với các observation. Confidence trung bình SQLite đã sửa của chai, cốc và laptop lần lượt là 0,8613, 0,5927 và 0,9608. Recall 75% vẫn dưới mốc 80% của đồ án. Thời gian YOLOE 13,9 s, Metric3D 105,4 s, SQLite offline 3,36 / 3,03 s.

Lượt quét giữ sách cũ vì cả hai asset đều không được nhận đúng trong đối chứng. Cốc được dời vào vùng trọn khung. Pose cuối (−0,18; −0,28) khác pose probe (−0,03; −0,23) để tránh chồng footprint laptop. Bố trí khóa trước RunScan. Các đối chiếu A/B trong bảng dùng cùng 24 khung của lượt cuối. [Bố trí đã khóa](kitchen_final/selection.json) · [Ảnh tám góc](kitchen_final/all_stops.jpg) · [Audit detection](kitchen_final/detection_audit.csv) · [CSV vị trí](kitchen_fullscan_summary.csv) · [SQLite A](kitchen_final/replay_A.sqlite) · [SQLite B](kitchen_final/replay_B.sqlite)

## 5. Trạng thái và ưu tiên

| Phép thử | Trạng thái | Bằng chứng |
| --- | --- | --- |
| Calibration và holdout AWS/Tiffany | PASS | Hai bộ 27 + 18, K/TF/GT và hệ số đã khóa |
| Hệ số tỷ lệ đủ ổn định ở AWS trong dải thử | PASS | Các nhóm gần nhau, holdout trên mask GT đạt |
| Quy luật tỷ lệ ổn định ở Tiffany | FAIL | Hệ số theo khoảng cách và vật biến thiên, hai nhóm vượt AbsRel 15% |
| Thay sách khôi phục detection | FAIL | 0/3 cho cả hai asset đủ QA |
| Cốc trọn khung có thể confirmed | PASS | Probe replay 3 quan sát không truncated và confirmed |
| Bản vá confidence | PASS | Test add/merge/add, replay lịch sử, đối chiếu giá trị DB cuối |
| Kitchen ROS và replay A/B | PASS | Xác minh riêng ROS, SQLite, query và approach |
| Camera thật, điều hướng tránh vật cản, chuyển hệ số sang bố trí chưa thử | NOT TESTED | Batch chỉ có Gazebo; điểm approach được kiểm tra hình học |

Phép nhân đáng giữ làm mốc thử đơn giản cho các bố trí gần Kitchen/AWS. Kết quả Tiffany và tác hại khi thử chéo sang AWS chưa cho phép xem nó là công thức dùng chung. **Ưu tiên tiếp theo duy nhất** là khóa trước hệ số tỷ lệ và tuyến tính của Tiffany, rồi lặp phép chấm cùng các vật ở một pose camera Tiffany mới. So trên toàn mask GT và tập detection đúng để kiểm tra lợi thế tuyến tính có giữ khi đổi bố trí hay không.

## Lệnh và tái lập

Các lệnh chính đã chạy, viết gọn đường dẫn batch bằng `BATCH`. Trong WSL dùng `/mnt/d/loc3d_ws` làm thư mục làm việc, cùng venv và cache checkpoint hiện có.

~~~bash
bash "$BATCH/capture.sh" aws tiffany
/usr/bin/python3 "$BATCH/collect_kitchen.py" "$BATCH/kitchen_probe"
.venv/bin/python "$BATCH/probe.py"
.venv/bin/python "$BATCH/repair_book_fixture.py"
/usr/bin/python3 "$BATCH/collect_book.py" "$BATCH/kitchen_book_retry"
.venv/bin/python "$BATCH/score_book.py"
.venv/bin/python "$BATCH/crossworld.py"
.venv/bin/python -m pytest -q -s -p no:cacheprovider tests/test_association.py -k confidence_tracks
.venv/bin/python -m pytest -q -s -p no:cacheprovider --basetemp="$BATCH/tmp/pytest" tests
.venv/bin/python "$BATCH/verify_confidence.py"
.venv/bin/python "$BATCH/prepare_final.py" "$BATCH"
bash "$BATCH/kitchen_final/run_ready.sh"
.venv/bin/python "$BATCH/kitchen_final/replay.py"
.venv/bin/python "$BATCH/summarize_batch.py"
/usr/bin/python3 "$BATCH/kitchen_final/pose_check.py" "$BATCH/kitchen_final/final_gazebo_pose.txt"
~~~

~~~powershell
D:\yoloe_test\.venv\Scripts\python.exe "$batch\prepare_worlds.py" "$batch"
D:\yoloe_test\.venv\Scripts\python.exe "$batch\prepare_kitchen_probe.py" "$batch"
D:\yoloe_test\.venv\Scripts\python.exe -m unittest discover -s tests
D:\yoloe_test\.venv\Scripts\python.exe "$batch\verify_batch.py"
~~~

Capture native dùng `gz sim -r -s --headless-rendering`. Lượt cuối gọi ROS RunScan thực với 45°, 3 khung và settle 1,5 s, sau đó gọi các service query và approach. [Log inference](crossworld.log) · [Log RunScan](kitchen_final/action.log) · [Log replay](kitchen_final/replay.log) · [Query ROS](kitchen_final/query_live.log) · [Manifest SHA-256](manifest.json)
