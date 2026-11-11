# Phạm vi snapshot

Các file công bố gồm mã và thiết kế thử, frozen inputs, cấu hình/SDF mới, pose và tâm mesh từng world, audit đồng bộ, kết quả CSV/JSON, SQLite live/replay, ảnh render và log. `manifest.sha256` lưu SHA-256 của từng file công bố.

36 file NPZ gốc (18/world) lưu tại `D:\loc3d_ws\data\eval\orb_crossworld_20261111_091739\aws\frames` và thư mục tương ứng Tiffany. `raw_frames.sha256` băm các file này. Cache, checkpoint và tài nguyên world phụ thuộc dùng môi trường hiện có. Lượt AWS đầu không ổn định được giữ riêng tại `aws_initial_unstable`, log và thông tin lỗi có trong thư mục gốc.

Tái lập cần dữ liệu NPZ hoặc chạy lại trong thư mục batch mới, assets của hai world đã có, các file chẩn đoán Kitchen trước và môi trường ROS/Python đã khóa. Chạy `sha256sum -c manifest.sha256` để xác minh snapshot, và `sha256sum -c raw_frames.sha256` khi có các frame local. Báo cáo mô tả rõ các kết quả offline và thời gian ROS thực.
