#!/usr/bin/env python3
"""Quay camera và lưu các cặp ảnh RGB/depth đã đồng bộ từ Gazebo.
Cần Gazebo, ros_gz_bridge và pan_tf_node đang chạy.
  python3 tools/capture_scan.py --out data/eval/depth_comparison/rgb
      --depth-out data/eval/depth_comparison/depth_gt"""
import argparse, csv, math, os, time
from collections import deque
import numpy as np, rclpy
from rclpy.node import Node
from std_msgs.msg import Float64
from sensor_msgs.msg import Image, JointState
try:
    import cv2
    def save(p, rgb): cv2.imwrite(p, rgb[..., ::-1])       # OpenCV ghi BGR
except ImportError:
    from PIL import Image as PI
    def save(p, rgb): PI.fromarray(rgb).save(p)

class N(Node):
    def __init__(s):
        super().__init__("capture_scan"); s.pub = s.create_publisher(Float64, "/pan_cmd", 10)
        s.yaw = None; s.rgb_frames = deque(maxlen=20); s.depth_frames = deque(maxlen=20)
        s.create_subscription(JointState, "/joint_states", s.on_js, 50)
        s.create_subscription(Image, "/camera/image", s.on_rgb, 10)
        s.create_subscription(Image, "/camera/depth_image", s.on_depth, 10)
    def on_js(s, m):
        if "pan_joint" in m.name: s.yaw = m.position[m.name.index("pan_joint")]
    @staticmethod
    def stamp(m): return m.header.stamp.sec + m.header.stamp.nanosec * 1e-9
    def on_rgb(s, m):
        if m.encoding not in ("rgb8", "bgr8"):
            raise RuntimeError(f"Encoding RGB không hỗ trợ: {m.encoding}")
        a = np.frombuffer(m.data, np.uint8).reshape(m.height, m.step)
        a = a[:, :m.width * 3].reshape(m.height, m.width, 3).copy()
        if m.encoding == "bgr8": a = a[..., ::-1].copy()
        s.rgb_frames.append((s.stamp(m), a))
    def on_depth(s, m):
        if m.encoding != "32FC1":
            raise RuntimeError(f"Encoding depth cần 32FC1, nhận được: {m.encoding}")
        row_values = m.step // np.dtype(np.float32).itemsize
        a = np.frombuffer(m.data, dtype=np.float32).reshape(m.height, row_values)[:, :m.width].copy()
        if m.is_bigendian:
            a = a.byteswap().view(a.dtype.newbyteorder("="))
        s.depth_frames.append((s.stamp(m), a))
    def get_pair(s, after_stamp, timeout=10.0, tolerance=0.05):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            rclpy.spin_once(s, timeout_sec=0.02)
            rgb_candidates = [f for f in s.rgb_frames if f[0] > after_stamp]
            if not rgb_candidates: continue
            rgb = rgb_candidates[0]
            depths = list(s.depth_frames)
            if not depths: continue
            depth = min(depths, key=lambda f: abs(f[0] - rgb[0]))
            skew = abs(depth[0] - rgb[0])
            if skew <= tolerance:
                return rgb, depth, skew
        raise TimeoutError(f"Không tìm được cặp RGB-depth đồng bộ trong {timeout:g}s (dung sai {tolerance:g}s)")
    def spin(s, dt):
        t0 = time.time()
        while time.time() - t0 < dt: rclpy.spin_once(s, timeout_sec=0.02)

def wrap(a): return (a + math.pi) % (2*math.pi) - math.pi
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--step", type=float, default=45)
    ap.add_argument("--frames", type=int, default=3); ap.add_argument("--settle", type=float, default=1.5)
    ap.add_argument("--out", default="data/w2_images")
    ap.add_argument("--depth-out", default=None, help="Thư mục lưu depth .npy; mặc định <out>/depth_gt")
    ap.add_argument("--sync-tolerance-ms", type=float, default=50.0)
    a = ap.parse_args()
    depth_out = a.depth_out or os.path.join(a.out, "depth_gt")
    os.makedirs(a.out, exist_ok=True); os.makedirs(depth_out, exist_ok=True)
    rclpy.init(); n = N()
    try:
        while n.yaw is None: rclpy.spin_once(n, timeout_sec=0.2)
        t_start = time.time(); stops = int(math.ceil(360 / a.step)); last_stamp = -1.0
        with open(os.path.join(a.out, "capture_metadata.csv"), "w", newline="") as fh:
            wr = csv.writer(fh); wr.writerow(["image", "yaw_deg", "rgb_stamp_s", "depth_stamp_s", "sync_delta_ms"])
            for k in range(stops):
                cmd = wrap(math.radians(k * a.step)); n.pub.publish(Float64(data=cmd)); t0 = time.time()
                while abs(math.degrees(wrap(n.yaw - cmd))) > 0.5:
                    n.spin(0.05)
                    if time.time() - t0 > 20: raise TimeoutError(f"Stop {k}: camera không tới góc lệnh")
                n.spin(a.settle)
                if n.rgb_frames:
                    last_stamp = max(last_stamp, n.rgb_frames[-1][0])
                for j in range(a.frames):
                    (rgb_stamp, rgb), (depth_stamp, depth), skew = n.get_pair(
                        last_stamp, tolerance=a.sync_tolerance_ms / 1000.0)
                    last_stamp = rgb_stamp
                    stem = f"stop{k}_f{j}"
                    save(os.path.join(a.out, stem + ".png"), rgb)
                    np.save(os.path.join(depth_out, stem + ".npy"), depth)
                    wr.writerow([stem, f"{math.degrees(n.yaw):.3f}", f"{rgb_stamp:.9f}",
                                 f"{depth_stamp:.9f}", f"{skew * 1000:.3f}"])
                print(f"stop {k}: yaw={math.degrees(n.yaw):7.2f} deg, đã lưu {a.frames} cặp RGB-depth")
        print(f"XONG trong {time.time()-t_start:.1f} s, RGB ở {a.out}/, depth ở {depth_out}/")
    finally:
        n.pub.publish(Float64(data=0.0))
        n.destroy_node()
        rclpy.shutdown()
if __name__ == "__main__": main()
