#!/usr/bin/env python3
"""W2-A6: 36 góc ngẫu nhiên (seed 42), lệnh /pan_cmd, đọc /joint_states, ghi data/eval/w2_pan_repeat.csv.
Cần: sim + bridge đang chạy (ros2 launch room_sim room.launch.py)."""
import csv, math, os, random, time
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float64
from sensor_msgs.msg import JointState

class T(Node):
    def __init__(s):
        super().__init__("pan_test"); s.pub = s.create_publisher(Float64, "/pan_cmd", 10); s.yaw = None
        s.create_subscription(JointState, "/joint_states", s.cb, 50)
    def cb(s, m):
        if "pan_joint" in m.name: s.yaw = m.position[m.name.index("pan_joint")]

def wrap(a): return (a + math.pi) % (2*math.pi) - math.pi
def main(settle=3.0):
    rclpy.init(); n = T(); random.seed(42)
    while n.yaw is None: rclpy.spin_once(n, timeout_sec=0.2)
    rows = []
    for i in range(36):
        cmd = random.uniform(-math.pi, math.pi); n.pub.publish(Float64(data=cmd)); t0 = time.time()
        while time.time() - t0 < settle: rclpy.spin_once(n, timeout_sec=0.05)
        err = math.degrees(wrap(n.yaw - cmd)); rows.append((i, math.degrees(cmd), math.degrees(n.yaw), err)); print(i, f"{err:+.3f} deg")
    os.makedirs("data/eval", exist_ok=True)
    with open("data/eval/w2_pan_repeat.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["i", "cmd_deg", "actual_deg", "err_deg"]); w.writerows(rows)
    e = sorted(abs(r[3]) for r in rows); p95 = e[int(0.95*(len(e)-1))]
    print(f"p95 |err| = {p95:.3f} deg ->", "ĐẠT (<1)" if p95 < 1 else "KHÔNG ĐẠT")
if __name__ == "__main__": main()
