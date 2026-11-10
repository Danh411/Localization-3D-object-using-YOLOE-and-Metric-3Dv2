# Kế hoạch kiểm thử Kitchen 360°

## Phạm vi và điều kiện chạy

- Một lượt quét hoàn chỉnh trên bản sao Kitchen có texture, bốn vật ở bố trí mới được ghi trong design.json. Nếu khởi động thiếu điểm dừng, giữ log lần thiếu và thử lại với đúng scene đã khóa. Chỉ chấm lượt đủ dữ liệu.
- ROS RunScan thật, 8 điểm cách nhau 45°, đợi 1,5 s sau khi joint đến góc, 3 khung mỗi điểm. Trước khi gửi goal, xác nhận bridge đã có dữ liệu Gazebo và ROS. Một lần suy luận mỗi khung của lượt chính.
- Chốt 24 packet RGB, depth axial, panoptic và CameraInfo cùng stamp, TF world–optical ở stamp đó, thứ tự quan sát, predicted depth và mask. So stamp, K, yaw và TF trước khi chấp nhận kết quả.
- K dùng CameraInfo 1280×720, fx = fy ≈ 914,014701 px, cx = 640, cy = 360. Hai model và tất cả tham số production đọc từ bản đóng băng. AI chỉ nhận RGB và K cần thiết.

## Replay và tiêu chí

- A giữ nguyên Z đại diện. B nhân Z đại diện với k = 1,3720333573615522 từ locked.json, giữ giới hạn an toàn của tệp khóa. Giữ UV, confidence, timestamp và TF. Tính lại cả XYZ lẫn range vì range quyết định trọng số gộp.
- Dùng hàm association, schema, finalize và query production với hai DB riêng. So từng quan sát, object và trạng thái A với SQLite live. Với B, log từng liên kết và trọng số, object sau merge và lý do bị loại. Kiểm tra query theo lớp, phạm vi, gần nhất và approach 0,6 m. Kiểm tra service ROS trên DB live khi launch còn chạy.
- Ghép mask–instance một-một cùng lớp và IoU ≥ 0,5. Lưu sai lớp riêng. Bản ghi định vị phải được xác nhận và mọi quan sát phải cùng chỉ về đúng một instance. Chọn bản ghi chính theo số quan sát, tổng trọng số rồi ID. Các bản ghi hợp lệ thừa tính là trùng. Đo XY/XYZ tới tâm mesh, tách xác nhận đúng instance khỏi định vị trong bán kính 0,5 m.
- Recall detection tính theo instance–khung nhìn thấy. Recall xác nhận tính trên bốn vật. Precision và tỷ lệ trùng của các object đã xác nhận chỉ dùng phạm vi có bằng chứng instance, ghi riêng dự đoán lớp mục tiêu thiếu bằng chứng và biên precision bảo thủ. Không suy rộng sang vật nền. Ba khung liên tiếp không đại diện cho ba góc độc lập.
- Depth AbsRel ≤ 15% trên Z đại diện so với median axial GT tại mask erode giao instance. XY trung vị ≤ 30 cm, XY P90 ≤ 60 cm trên bản ghi chính. Recall mục tiêu ≥ 80%, precision ≥ 85%, duplicate rate ≤ 10%. Báo n cho mỗi phép chấm, trường hợp không có mẫu là NOT TESTED.
- Phân loại không thấy ngoài FOV, ở trong vùng chiếu nhưng thiếu pixel instance, mask chạm mép, YOLOE sai lớp hoặc không có match, depth filter, association và SQLite. BBox sát mép của YOLOE có thể chỉ giảm trọng số và ảnh hưởng điều kiện xác nhận. Thiếu ứng viên trước threshold/NMS thì chưa xác định cơ chế bỏ sót.
- Đối chiếu conf_sum/conf_mean với từng quan sát, chạy regression, lưu SHA-256, log, bảng từng tầng và ảnh minh họa. Báo cáo một hướng xử lý ưu tiên dựa vào số liệu batch.
