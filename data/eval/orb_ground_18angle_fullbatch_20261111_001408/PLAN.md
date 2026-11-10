# Thiết kế batch 18 góc

- ROS RunScan 18 điểm, cách 20°, một frame tại mỗi điểm và settle 1,5 s. Development sao nguyên scene của lượt 36×1. Holdout dịch chuyển bốn mẫu theo layout định trước và giữ camera, ánh sáng, asset và cấu hình. Dùng CameraInfo và TF thật từng stamp.
- ORB giới hạn bốn lớp mục tiêu. Ghép hai chiều ratio <0,72 giữa các mask cùng lớp. Duyệt mọi cặp ảnh, baseline TF ≥1,2 cm. Loại điểm ngoài 0,2–8 m, reprojection >1 px, sin parallax <0,002 hoặc độ nhạy Z theo 1 px >25 cm. Ít nhất 8 điểm và độ phủ ≥12 px ở cả hai ảnh. Khử lặp feature trong ảnh neo và dùng median ± max(8 cm, 3 MAD) cho axial Z.
- ORB-A lấy median XYZ của các điểm còn lại. ORB-B lấy median axial Z, chiếu qua trọng tâm mask RGB đã erode với cùng công thức K/TF. Không dùng Z Metric3D để tính ray hoặc quyết định chấp nhận ORB. Mỗi detection tối đa một observation cho mỗi replay, kể cả khi khớp nhiều feature.
- Floor dùng bộ nhận diện RGB và ngưỡng đã có từ batch trước. Khi hình học thiếu hỗ trợ, ghi GROUND_UNAVAILABLE. Oracle floor dùng riêng cho đánh giá. Không dùng hệ số theo phòng.
- P0 Metric3D. P1-A/P1-B dùng ORB tương ứng rồi Metric3D. P2 dùng floor rồi Metric3D. P3 dùng ORB-B, tiếp đến floor, rồi Metric3D. Chấm thêm ORB-A/B thuần để phân biệt độ phủ của ORB với độ phủ từ fallback.
- Dùng toàn bộ detection hậu YOLOE, production association và điều kiện confirmed. Score điểm bề mặt chỉ sau khi chọn bằng RGB/TF. Score đại diện bằng axial GT trên phần giao mask, đồng thời so XYZ với tâm mesh. Bản ghi đúng được ghép theo instance, gồm riêng sai lớp, trùng, recall và precision.
- 12/18/36 đều replay từ bộ 36×1 ở các stop bội 3/2/1. Đối chứng 18×1 mới chạy ROS riêng. Keyframe 40° thử với vị trí đã cache và kiểm projection/mask, tuổi ≤30 s sim, góc ≤40°. Cơ hội bỏ Metric3D chỉ tính với ORB từ ảnh hiện tại và ảnh đã có. Floor vẫn cần depth Metric3D cùng ảnh. Observation lan truyền có trace và số lần đo thật riêng. Các số tiết kiệm là ước tính offline.
- Giữ khóa mã và scene holdout trước khi chạy RunScan trên layout mới. Các ngưỡng 15% AbsRel, 30 cm XY trung vị, 60 cm P90, 80% recall, 85% precision và 10% duplicate dùng cho kết luận.

