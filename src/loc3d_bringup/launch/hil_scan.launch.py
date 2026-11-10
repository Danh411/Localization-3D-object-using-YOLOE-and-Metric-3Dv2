"""Hardware-in-the-loop (W8-A2): Gazebo chạy máy chính, suy luận (perception) trên
Xavier nhận ảnh qua mạng. File này chạy trên máy chính: chỉ dựng sim + bridge + TF;
perception_node chạy trên Xavier (container cùng ROS distro, cùng ROS_DOMAIN_ID).

Trên Xavier chạy:
  ros2 run perception perception_node --ros-args -p config:=<cfg> \
      -p classes_config:=<classes> -p device:=cuda:0
"""
import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import ExecuteProcess
from launch_ros.actions import Node


def generate_launch_description():
    pkg_room = get_package_share_directory("room_sim")
    world = os.path.join(pkg_room, "worlds", "room.sdf")
    return LaunchDescription([
        ExecuteProcess(cmd=["gz", "sim", "-r", world], output="screen"),
        Node(package="ros_gz_bridge", executable="parameter_bridge", output="screen",
             parameters=[{"config_file": os.path.join(pkg_room, "config", "bridge.yaml"),
                          "use_sim_time": True}]),
        Node(package="room_sim", executable="pan_tf_node", output="screen",
             parameters=[{"use_sim_time": True,
                          "base_xyz": [2.0, 2.0, 1.2], "t_offset_m": 0.05}]),
        # scan_controller có thể chạy ở máy chính hay Xavier; để ở máy chính để
        # tránh phụ thuộc container. perception_node chạy trên Xavier.
        Node(package="scan_controller", executable="scan_controller_node",
             output="screen", parameters=[{"use_sim_time": True}]),
    ])
