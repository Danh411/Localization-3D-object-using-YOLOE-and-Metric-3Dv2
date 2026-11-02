# 0001 - Chọn bản ROS 2
Bối cảnh: WSL2 Ubuntu 24.04 + Gazebo Harmonic. Jazzy là bản ROS 2 chính thức của Ubuntu 24.04 và ghép chính thức với Harmonic (ros_gz).
Quyết định (nháp): Jazzy trên máy chính.
Xavier (JetPack 5.x = Ubuntu 20.04): không cài Jazzy native được => chạy container ROS 2 Jazzy (hoặc cùng distro với máy chính). Rủi ro: DDS, ARM64 image. Kiểm ở W4-A3.
Phương án khác: Humble trong container cả hai bên (Gazebo vẫn ở máy chính qua ros_gz Jazzy => lệch distro, DDS thường vẫn nói chuyện được nhưng phải test).
