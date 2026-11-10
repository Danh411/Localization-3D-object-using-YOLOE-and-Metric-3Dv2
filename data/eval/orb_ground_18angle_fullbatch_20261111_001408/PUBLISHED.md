# Snapshot trên GitHub

Snapshot gồm mã kiểm thử, cấu hình và scene thử, audit theo frame, kết quả CSV/JSON, SQLite live và replay, ảnh đối chiếu và log. `manifest.sha256` kiểm tra byte của các file công bố. `raw_frames.sha256` kiểm tra 36 NPZ gốc tại hai thư mục `frames/` trong workspace.

Để chạy lại toàn bộ từ số liệu đã thu, cần các NPZ ở đúng thư mục, file nguồn của batch 36×1, môi trường Python/ROS đã có và tài nguyên Gazebo/weights đã khóa. Để kiểm tra bảng kết quả, có thể đọc các CSV, JSON và SQLite trong snapshot. Ảnh từng frame và collage cho phép xem bố trí thử. Các cache, weight, asset phụ thuộc và log tạm của ROS lưu tại workspace. Tệp thử nghiệm SQLite tạo trước khi sửa lỗi audit cũng chỉ lưu tại workspace.

Trong WSL, từ thư mục batch, chạy `sha256sum -c manifest.sha256` để kiểm tra bản công bố. Chạy `sha256sum -c raw_frames.sha256` khi có đủ NPZ. Xem [REPORT.md](REPORT.md) để biết lệnh thu lại dữ liệu và tái lập số liệu.
