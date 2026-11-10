# Thiết kế khóa trước chấm GT

Scene Kitchen sao từ lượt ROS cuối batch ba world. A1 là RunScan 45° × 3. A2 dùng frame index 0 mỗi stop. B1 là RunScan 10° × 1. Settle 1,5 giây. Ghép một-một cùng lớp và mask IoU ≥ 0,5. Bản ghi đúng phải có toàn bộ observation gán cùng một GT instance, sau đó chấm tới tâm mesh. Match định vị dùng XY < 0,5 m. Ngoài phạm vi GT giữ riêng.

Fusion F1–F5 dùng cùng nhóm observation sau F0 và giữ trạng thái gốc để tách phép gộp khỏi association. F1 geometric median có trọng số F0. F2 Huber với delta 0,10 m. F3 fit một tâm XYZ, inlier trong 0,12 m, ít nhất 3 yaw độc lập, ≥60% tổng số và không có cụm cạnh tranh ngang phiếu. F4 kết hợp mask area, tâm ảnh, relative MAD, gradient depth, truncated qua trọng số F0. F5 cân bằng 12 ô yaw 30°, thêm đối chứng chỉ lấy một quan sát tốt mỗi ô. Mọi quy tắc độc lập GT.

Ground plane lấy mask lớp floor từ YOLOE diagnostic riêng trên RGB, giữ 0,35. GT floor oracle suy từ điểm axial GT có Z world trong 2 cm mặt phẳng. Giao tia phía trước, xa horizon ít nhất 5°, axial trong (0,1;10) m. Giữ ≥4 ô 40 px, ≥400 pixel, tỷ lệ GT-free có relative MAD ≤0,12, hệ số trong [0,5;2,5]. Median tỷ lệ giữa các ô, fallback gốc. Sai số pose ±2 cm hoặc ±1° pitch. Hệ số Kitchen khóa chỉ là tham chiếu.

Triangulation đo tâm thật từ TF, dùng ORB+ratio test và kiểm epipolar/reprojection trên vùng detection khi có correspondence. Ngưỡng tính khả thi 10 cm sai số dọc tia do 1 px, báo 0,5/1/2 px. Tâm mask chỉ dùng để phân tích độ nhạy tia, không tạo correspondence.

Temporal mỗi 20°/30° và adaptive từ RGB/YOLOE. Điểm non-key dùng world point của track đã khởi tạo bằng depth thật, chỉ truyền nếu projection lọt mask, class đúng, match duy nhất, yaw ≤30°, tuổi ≤30 giây sim. Không dùng depth map hoặc UV có nguồn từ depth hiện tại ở non-key. Đếm fresh evidence riêng và baseline theo full scan. View selection ngân sách 12 depth calls, đối chứng đều 30°, top quality, quality tối đa mỗi ô 30°. Chọn góc từ RGB/YOLOE trước khi đọc GT, không coi cost capture đã giảm nếu vẫn thu 36 ảnh.

Tập Kitchen chính là development. AWS/Tiffany dùng RGB/GT/TF lưu của holdout batch trước làm external diagnostic cho per-frame ground plane. P6 chỉ tuyên bố đã kiểm chứng nếu có holdout độc lập phù hợp.

Giữ nhánh làm ứng viên kết hợp nếu XY trung vị giảm ít nhất 2 cm, recall và số cụm sai/trùng giữ mức baseline hoặc tốt hơn. Temporal/viewpoint vẫn báo trade-off runtime dù không đủ điều kiện kết hợp. F3 dùng các ô yaw độc lập 20° để từ chối cụm chỉ có góc quá gần nhau.
