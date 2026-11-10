"""Một lệnh chạy trọn lần quét mô phỏng (W5-A3): Gazebo + bridge + TF + controller
+ perception + DB. Sinh data/db/<scan_id>.sqlite.

  ros2 launch loc3d_bringup sim_scan.launch.py
"""
import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node



def generate_launch_description():
    pkg_room = get_package_share_directory("room_sim")
    ws_default = os.environ.get("LOC3D_WS_ROOT", "/mnt/d/loc3d_ws")
    cfg_default = os.path.join(ws_default, "config", "default.yaml")
    classes_default = os.path.join(ws_default, "config", "classes.yaml")
    gt_default = os.path.join(ws_default, "config", "gt_objects.yaml")
    db_default = os.path.join(ws_default, "data", "db")
    world_name = os.environ.get("LOC3D_WORLD", "kitchen_dining.sdf")
    world = os.path.join(pkg_room, "worlds", world_name)
    # models/ nằm ở source tree (không cài vào share): trỏ GZ_SIM_RESOURCE_PATH vào đây
    models_dir = os.path.join(ws_default, "src", "room_sim", "models")

    cfg = LaunchConfiguration("config")
    classes = LaunchConfiguration("classes")
    gt = LaunchConfiguration("gt")
    db_dir = LaunchConfiguration("db_dir")

    return LaunchDescription([
        DeclareLaunchArgument("config", default_value=cfg_default,
                             description="Path to config/default.yaml"),
        DeclareLaunchArgument("classes", default_value=classes_default,
                             description="Path to config/classes.yaml"),
        DeclareLaunchArgument("gt", default_value=gt_default,
                             description="Path to config/gt_objects.yaml"),
        DeclareLaunchArgument("db_dir", default_value=db_default,
                             description="Directory for per-scan SQLite files"),
        # Gazebo Harmonic — trỏ resource path vào models/ để resolve model://
        ExecuteProcess(cmd=["gz", "sim", "-r", "-s", "--headless-rendering", world], output="screen",
             additional_env={"GZ_SIM_RESOURCE_PATH": models_dir}),

        # Bridge Gazebo <-> ROS
        Node(package="ros_gz_bridge", executable="parameter_bridge", output="screen",
             parameters=[{"config_file": os.path.join(pkg_room, "config", "bridge.yaml"),
                          "use_sim_time": True}]),

        # TF world->camera_base->pan_link->camera_link->optical; camera base
        # khớp config/default.yaml.camera.base_xyz (hiện -1.5,-0.5,1.1 trong kitchen)
        Node(package="room_sim", executable="pan_tf_node", output="screen",
             parameters=[{"use_sim_time": True,
                          "base_xyz": [-1.5, -0.5, 1.1], "t_offset_m": 0.05}]),

        # Perception (YOLOE + Metric3D tuần tự)
        Node(package="perception", executable="perception_node", output="screen",
             prefix="/mnt/d/loc3d_ws/.venv/bin/python /mnt/d/loc3d_ws/data/eval/orb_ground_18angle_fullbatch_20261111_001408/scan_18x1/audit.py",
             parameters=[{"use_sim_time": True, "config": cfg,
                          "classes_config": classes, "device": "cuda:0"}]),

        # Object DB (ghi + gộp + truy vấn + approach)
        Node(package="object_db", executable="object_db_node", output="screen",
             parameters=[{"use_sim_time": True, "config": cfg,
                          "db_dir": db_dir, "world_name": "room",
                          "gt_config": gt}]),

        # Controller (RunScan action)
        Node(package="scan_controller", executable="scan_controller_node",
             output="screen", parameters=[{"use_sim_time": True}]),
    ])
