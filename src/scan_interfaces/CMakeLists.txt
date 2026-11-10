cmake_minimum_required(VERSION 3.8)
project(scan_interfaces)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(std_msgs REQUIRED)
find_package(action_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/ObjectObservation.msg"
  "msg/ObjectObservationArray.msg"
  "srv/Capture.srv"
  "srv/QueryObjects.srv"
  "srv/GetApproachPoint.srv"
  "srv/FinalizeScan.srv"
  "action/RunScan.action"
  DEPENDENCIES builtin_interfaces std_msgs action_msgs
)

ament_package()
