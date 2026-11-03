"""TF theo mục 2.2: world->camera_base (tĩnh) ; camera_base->pan_link (yaw=/joint_states) ;
pan_link->camera_link (offset) ; camera_link->camera_optical_frame (roll -90, yaw -90)."""
import math
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from geometry_msgs.msg import TransformStamped
from tf2_ros import TransformBroadcaster, StaticTransformBroadcaster

def quat_rpy(r, p, y):
    cr, sr, cp, sp, cy, sy = math.cos(r/2), math.sin(r/2), math.cos(p/2), math.sin(p/2), math.cos(y/2), math.sin(y/2)
    return (sr*cp*cy - cr*sp*sy, cr*sp*cy + sr*cp*sy, cr*cp*sy - sr*sp*cy, cr*cp*cy + sr*sp*sy)

def tf(parent, child, xyz, q, stamp):
    t = TransformStamped(); t.header.stamp = stamp; t.header.frame_id = parent; t.child_frame_id = child
    t.transform.translation.x, t.transform.translation.y, t.transform.translation.z = (float(v) for v in xyz)
    t.transform.rotation.x, t.transform.rotation.y, t.transform.rotation.z, t.transform.rotation.w = (float(v) for v in q)
    return t

class PanTf(Node):
    def __init__(self):
        super().__init__("pan_tf")
        self.declare_parameter("base_xyz", [2.0, 2.0, 1.2]); self.declare_parameter("t_offset_m", 0.05)
        self.base = list(self.get_parameter("base_xyz").value); off = self.get_parameter("t_offset_m").value
        self.br = TransformBroadcaster(self); sb = StaticTransformBroadcaster(self)
        now = self.get_clock().now().to_msg()
        sb.sendTransform([tf("world", "camera_base", self.base, (0, 0, 0, 1), now),
                          tf("pan_link", "camera_link", (off, 0.0, 0.0), (0, 0, 0, 1), now),
                          tf("camera_link", "camera_optical_frame", (0, 0, 0), quat_rpy(-math.pi/2, 0, -math.pi/2), now)])
        self.create_subscription(JointState, "/joint_states", self.cb, 50)
    def cb(self, m):
        if "pan_joint" not in m.name: return
        yaw = m.position[m.name.index("pan_joint")]
        self.br.sendTransform(tf("camera_base", "pan_link", (0, 0, 0), quat_rpy(0, 0, yaw), m.header.stamp))

def main():
    rclpy.init(); rclpy.spin(PanTf())
