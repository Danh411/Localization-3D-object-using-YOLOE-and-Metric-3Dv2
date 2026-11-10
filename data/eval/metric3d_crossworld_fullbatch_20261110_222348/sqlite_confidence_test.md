# Regression confidence SQLite

Lỗi tái hiện trên mã cũ bằng test mới. Hai quan sát confidence 0,9 và 0,7 cho conf_sum lưu 0,9, kỳ vọng 1,6. [Kết quả trước sửa](sqlite_before_reproduced.log)

Bản vá cập nhật cùng lúc conf_sum và conf_mean khi thêm observation vào object hiện có, và khi hợp nhất hai object. Trung bình được tính từ tổng và n_obs. Schema, ngưỡng tạo và gộp, trọng số, điều kiện confirmed và phép tính XYZ giữ theo mã hiện hành.

Test mới kiểm tra hai cụm với confidence khác nhau, merge, sau đó thêm một quan sát nữa. Kết quả cuối n_obs = 5, tổng 3,5, trung bình 0,7 và cả năm observation liên kết với object đã merge. LOC3D chạy 59 test, YOLOE chạy 79 test, đều PASS. [LOC3D](regression_loc3d.log) · [YOLOE](regression_yoloe.log)

Replay 59 observations đã lưu vào DB mới bằng chính production association. So trực tiếp với bản trước vá cho thấy 59 observations giống hệt, và 12 objects có cùng ID, XYZ, trọng số, liên kết, số quan sát và trạng thái. Hai trường confidence được đối chiếu với từng observation. Ví dụ chai đổi conf_mean từ 0,288021 thành 0,863254. DB lịch sử được mở ở chế độ chỉ đọc và SHA-256 trước/sau khớp. [Kiểm tra parity](sqlite_confidence_parity.json) · [DB sau vá](confidence_after.sqlite)

Lần gọi pytest đầu dùng chế độ capture mặc định bị lỗi tệp tạm trên WSL/DrvFS. Lần chạy lại với tùy chọn -s tái hiện đúng lỗi confidence. Tất cả kết quả regression được lấy từ lần chạy với -s.

