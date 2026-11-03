# Thử W1-A1 / W1-A2 (Gazebo Harmonic + ROS 2 Jazzy trên WSL2)

Terminal 1 (Gazebo):
    gz sim -r ~/loc3d_ws/src/room_sim/worlds/test_camera.sdf

Terminal 2 (bridge, sau khi source ROS):
    source /opt/ros/jazzy/setup.bash
    ros2 run ros_gz_bridge parameter_bridge \
      /camera/image@sensor_msgs/msg/Image[gz.msgs.Image \
      /camera/depth_image@sensor_msgs/msg/Image[gz.msgs.Image \
      /camera/camera_info@sensor_msgs/msg/CameraInfo[gz.msgs.CameraInfo

Terminal 3 (kiểm tra, nghiệm thu W1-A1: hz >= 5):
    source /opt/ros/jazzy/setup.bash
    ros2 topic hz /camera/image
    ros2 topic echo /camera/camera_info --once      # K phải có fx ~ 914.01, cx 640, cy 360
    ros2 topic echo /camera/depth_image --once --field encoding   # mong đợi 32FC1

Nếu Gazebo không mở/ render lỗi (W1-A2 dự phòng):
    LIBGL_ALWAYS_SOFTWARE=1 gz sim -r ...
    hoặc chạy không GUI:  gz sim -s -r ...   (server only, camera vẫn render)
