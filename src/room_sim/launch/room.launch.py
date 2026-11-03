import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import ExecuteProcess
from launch_ros.actions import Node

def generate_launch_description():
    share = get_package_share_directory("room_sim")
    world = os.path.join(share, "worlds", "room.sdf")
    return LaunchDescription([
        ExecuteProcess(cmd=["gz", "sim", "-r", world], output="screen"),
        Node(package="ros_gz_bridge", executable="parameter_bridge", output="screen",
             parameters=[{"config_file": os.path.join(share, "config", "bridge.yaml"), "use_sim_time": True}]),
        Node(package="room_sim", executable="pan_tf_node", output="screen",
             parameters=[{"use_sim_time": True, "base_xyz": [2.0, 2.0, 1.2], "t_offset_m": 0.05}]),
    ])
