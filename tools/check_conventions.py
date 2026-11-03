#!/usr/bin/env python3
"""W2-A5: (i) z-depth hay khoảng cách tia; (ii) chiều quay yaw. Cần sim + bridge + pan_tf đang chạy.
(i) pan=0: tường phía đông là mặt phẳng x=5. Camera ở x=2.05 => z-depth mọi pixel = 2.95 m (trừ mép dưới/trên nếu chạm sàn/trần);
    nếu là khoảng cách tia, pixel xa tâm theo chiều ngang sẽ > 2.95.
(ii) pan=45 deg: cột magenta ở (3.5,3.5) phải nằm GIỮA ảnh (u ~ 640) nếu yaw dương = ngược chiều kim đồng hồ."""
import time, numpy as np, rclpy
from rclpy.node import Node
from std_msgs.msg import Float64
from sensor_msgs.msg import Image

class N(Node):
    def __init__(s):
        super().__init__("conv"); s.pub = s.create_publisher(Float64, "/pan_cmd", 10); s.rgb = s.depth = None
        s.create_subscription(Image, "/camera/image", lambda m: setattr(s, "rgb", m), 1)
        s.create_subscription(Image, "/camera/depth_image", lambda m: setattr(s, "depth", m), 1)
    def go(s, yaw, wait=3.5):
        s.pub.publish(Float64(data=yaw)); s.rgb = s.depth = None; t0 = time.time()
        while time.time() - t0 < wait or s.rgb is None or s.depth is None: rclpy.spin_once(s, timeout_sec=0.05)
def arr(m, dt, ch): return np.frombuffer(m.data, dtype=dt).reshape(m.height, m.width, ch) if ch > 1 else np.frombuffer(m.data, dtype=dt).reshape(m.height, m.width)
def main():
    rclpy.init(); n = N(); n.go(0.0); d = arr(n.depth, np.float32, 1)
    c, l, r = d[360, 640], d[360, 100], d[360, 1180]
    print(f"(i) depth tâm={c:.3f}  trái(u=100)={l:.3f}  phải(u=1180)={r:.3f}  (kỳ vọng z-depth ~2.95 ở cả ba)")
    print("    =>", "z-depth" if abs(l - c) < 0.05 and abs(r - c) < 0.05 else "có vẻ là khoảng cách tia (hoặc tường không vuông góc)")
    n.go(np.pi/4); im = arr(n.rgb, np.uint8, 3).astype(int)
    m = (im[..., 0] > 180) & (im[..., 1] < 80) & (im[..., 2] > 180)
    if m.sum() < 50: print("(ii) không thấy cột magenta: yaw có thể quay NGƯỢC chiều (thử -45 deg) hoặc chưa ổn định")
    else:
        u = np.nonzero(m)[1].mean(); print(f"(ii) u cột magenta = {u:.1f} (kỳ vọng ~640)  =>", "yaw dương = ngược chiều kim đồng hồ ĐÚNG" if abs(u - 640) < 60 else "LỆCH, kiểm tra dấu")
if __name__ == "__main__": main()
