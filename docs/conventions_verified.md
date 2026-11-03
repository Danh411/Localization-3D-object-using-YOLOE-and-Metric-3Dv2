# Quy ước đã kiểm chứng (W2-A5), 03/11/2026
- Độ sâu Gazebo (rgbd_camera, 32FC1): **z-depth**. Tường phẳng x=5, camera ở x=2.05: depth tâm 2.958, trái 2.941, phải 2.954 m.
- Chiều quay yaw: **dương = ngược chiều kim đồng hồ** nhìn từ trên xuống. Pan 45 deg đưa cột tại (3.5, 3.5) về giữa ảnh (u = 641.1).
- camera_info: fx = fy = 914.0147, cx = 640, cy = 360, không méo; frame_id = camera_optical_frame.
- Độ lặp góc pan: p95 |sai số| = 0.57 deg (36 góc ngẫu nhiên, seed 42), data/eval/w2_pan_repeat.csv.
- GT: 12/12 vật khớp config/gt_objects.yaml (0.00 cm).
