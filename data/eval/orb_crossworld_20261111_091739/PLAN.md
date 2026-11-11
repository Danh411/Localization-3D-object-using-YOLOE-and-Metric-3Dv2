# Kiểm chứng ORB trên hai world ngoài Kitchen

- Hai scene mới dùng world AWS Small House và Tiffany Living Room đã tích hợp Harmonic, nguồn và SHA được lưu ở batch crossworld trước. Các bộ ảnh calibration cũ đổi vật giữa các ảnh, do đó thu mới hai lượt ROS 18 góc × 20°, một frame/góc, settle 1,5 s.
- Giữ nguyên assets và texture chai, cốc, laptop, sách. Bốn vật đứng yên trên sàn suốt mỗi lượt. Đặt vật trong vùng đã thu được GT ở mỗi phòng. Lưu pose và tâm mesh riêng, xác minh AABB không chồng nhau và chạm mặt sàn. Giữ mọi ảnh ngoài FOV, cắt biên và không phát hiện trong đánh giá.
- Camera rig LOC3D, 1280×720, HFOV 70°, offset 5 cm. Dùng vị trí camera riêng của hai phòng từ batch crossworld, cao 0,36 m. Base yaw đặt 0 để khớp khả năng của broadcaster production, quét 360° bao phủ hướng nhìn tham chiếu cũ. Đây là kiểm chứng hai phòng ở camera thấp, khác độ cao 1,10 m của Kitchen.
- Khóa trước ORB giống từng byte với Kitchen. Tối đa 450 feature/detection, ghép Hamming hai chiều ratio 0,72, baseline >=1,2 cm, gate reprojection/conditioning/consensus giữ nguyên. Không chọn lại ngưỡng theo GT hai phòng.
- Dùng K, TF và RGB/mask YOLOE làm đầu vào ORB. P0 Metric3D gốc, ORB-A/B thuần, P1-A/B với fallback, P2 mặt sàn và P3 ORB-B → sàn → Metric3D. Oracle sàn chỉ dùng đánh giá. Cao độ sàn lấy từ scene, không fit theo depth GT.
- Dùng cùng checkpoint/prompts/association/SQLite và depth gốc. Lưu raw synchronized RGB, predicted depth, axial GT, panoptic, CameraInfo, TF/yaw, detections và observations. Replay P0 phải khớp SQLite live.
- Matching đúng instance/lớp tách khỏi sai số tọa độ. Vật nền chưa có GT ghi ngoài phạm vi. Chấm depth bề mặt, vị trí từng ảnh và XY/XYZ cuối sau association. Báo độ phủ, confirmed, wrong, duplicate, fallback và fail reasons.
- Mọi phương pháp chạy offline cùng frame. Chỉ P0 có thời gian ROS thực. Nhánh tăng tốc theo nhu cầu chỉ dùng ảnh trước và hiện tại, thời gian là ước tính từ các inference đã đo.
- Không thay production hoặc sửa dữ liệu cũ. Output mới chỉ nằm trong thư mục batch này. Dùng lại các hàm đã có. Kiểm tra regression, hashes trước/sau, SQLite/query/confidence. Ghi NOT TESTED cho phần không chạy được.
- Tiêu chí đồ án giữ AbsRel ≤15%, XY trung vị ≤30 cm, P90 ≤60 cm, recall confirmed ≥80%, precision ≥85%, duplicate ≤10%. Với bốn vật, 3/4 chưa đạt recall.
