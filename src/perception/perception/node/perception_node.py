"""Perception node — service /perception/capture (mục 3.1, W5-B1).

Nhận scan_id/stop_index/yaw_rad/n_frames; lấy n_frames ảnh RGB đồng bộ từ
/camera/image (kèm camera_info cho K), chạy YOLOE rồi Metric3D tuần tự (một
tiến trình — spec 3.1), tính p_cam rồi chiếu sang world bằng tf2 tại stamp ảnh,
trả ObjectObservationArray + timings_ms.

Chỉ dùng RGB + camera_info cho suy luận; depth GT không đưa vào pipeline (mục 3.1).
"""
from __future__ import annotations

import math
import time

import numpy as np
import rclpy
import yaml
from rclpy.node import Node
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.time import Time
from rclpy.duration import Duration

from sensor_msgs.msg import Image, CameraInfo
from cv_bridge import CvBridge
import tf2_ros
from tf2_ros import Buffer, TransformListener

from scan_interfaces.srv import Capture
from scan_interfaces.msg import ObjectObservation, ObjectObservationArray

from perception.core.geometry import intrinsics_from_hfov, backproject_optical
from perception.core.pipeline import process
from perception.core.yolo import YoloeDetector
from perception.core.depth import Metric3DDepth


class PerceptionNode(Node):
    def __init__(self):
        super().__init__("perception_node")
        self.declare_parameter("config", "")
        self.declare_parameter("classes_config", "")
        self.declare_parameter("device", "cuda:0")
        cfg_path = self.get_parameter("config").value
        cls_path = self.get_parameter("classes_config").value
        self.cfg = yaml.safe_load(open(cfg_path)) if cfg_path else {}
        self.classes = (yaml.safe_load(open(cls_path)).get("classes", [])
                        if cls_path else ["bottle"])
        cam = self.cfg.get("camera", {})
        self.base_xyz = tuple(cam.get("base_xyz", [0, 0, 0]))
        self.t_offset = (cam.get("t_offset_m", 0.0), 0.0, 0.0)

        y = self.cfg.get("yoloe", {})
        d = self.cfg.get("depth", {})
        dev = self.get_parameter("device").value
        wts = y.get("model", "yoloe-11s-seg")
        wts = wts if wts.endswith(".pt") else wts + ".pt"
        self.detector = YoloeDetector(self.classes, wts, y.get("conf", 0.35),
                                      y.get("iou", 0.5), y.get("imgsz", 640), dev)
        self.depth = Metric3DDepth(dev, tuple(d.get("input_size", [616, 1064])),
                                   d.get("fp16", True), d.get("canonical_focal", 1000.0),
                                   d.get("max_m", 10.0))
        self.get_logger().info(f"Models loaded: {len(self.classes)} lớp, device={dev}")

        self.bridge = CvBridge()
        self.latest_image: Image | None = None
        self.camera_info: CameraInfo | None = None
        cb = ReentrantCallbackGroup()
        from rclpy.qos import qos_profile_sensor_data
        self.create_subscription(Image, "/camera/image", self._on_img,
                                 qos_profile_sensor_data, callback_group=cb)
        self.create_subscription(CameraInfo, "/camera/camera_info", self._on_info,
                                 qos_profile_sensor_data, callback_group=cb)
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.srv = self.create_service(Capture, "/perception/capture",
                                       self._on_capture, callback_group=cb)

    def _on_img(self, m: Image):
        self.latest_image = m

    def _on_info(self, m: CameraInfo):
        self.camera_info = m

    def _K(self):
        if self.camera_info is not None:
            k = self.camera_info.k
            return k[0], k[4], k[2], k[5]
        cam = self.cfg.get("camera", {})
        return intrinsics_from_hfov(cam.get("width", 1280), cam.get("height", 720),
                                    cam.get("hfov_deg", 70.0))

    def _p_world(self, p_cam, stamp):
        """Tra cứu tf2 tại stamp; trả None nếu thiếu TF."""
        try:
            t = self.tf_buffer.lookup_transform(
                "world", "camera_optical_frame",
                Time.from_msg(stamp), Duration(seconds=1.0))
            q = t.transform.rotation; tr = t.transform.translation
            x, yy, z, w = q.x, q.y, q.z, q.w
            R = np.array([
                [1 - 2 * (yy * yy + z * z), 2 * (x * yy - z * w), 2 * (x * z + yy * w)],
                [2 * (x * yy + z * w), 1 - 2 * (x * x + z * z), 2 * (yy * z - x * w)],
                [2 * (x * z - yy * w), 2 * (yy * z + x * w), 1 - 2 * (x * x + yy * yy)]])
            return (R @ np.asarray(p_cam)) + np.array([tr.x, tr.y, tr.z])
        except Exception:
            return None

    def _grab_frames(self, n_frames: int, timeout_s: float = 10.0):
        """Lấy n_frames ảnh liên tiếp. Subscription callback tự cập nhật
        self.latest_image qua executor; ở đây chỉ chờ và lọc stamp mới."""
        frames, last_stamp, deadline = [], None, time.monotonic() + timeout_s
        while len(frames) < n_frames and time.monotonic() < deadline:
            img = self.latest_image
            if img is not None and (img.header.stamp.sec, img.header.stamp.nanosec) != last_stamp:
                frames.append(img)
                last_stamp = (img.header.stamp.sec, img.header.stamp.nanosec)
            else:
                time.sleep(0.01)
        return frames

    def _on_capture(self, req: Capture.Request, resp: Capture.Response):
        t0 = time.perf_counter()
        timings = []
        n_frames = max(1, int(req.n_frames))
        frames = self._grab_frames(n_frames)
        timings.append((time.perf_counter() - t0) * 1e3)  # lấy ảnh
        arr = ObjectObservationArray()
        arr.scan_id = req.scan_id
        arr.stop_index = req.stop_index
        arr.yaw_rad = req.yaw_rad
        arr.header.stamp = self.get_clock().now().to_msg()

        if not frames:
            resp.success = False; resp.message = "không có ảnh"
            resp.observations = arr; resp.timings_ms = timings
            return resp
        K = self._K()
        yolo_ms = depth_ms = post_ms = 0.0
        self.get_logger().info(
            f"[{req.scan_id}][stop {req.stop_index}] capture: {len(frames)} frames, "
            f"K={K}, latest rgb exists={self.latest_image is not None}")
        for fidx, img in enumerate(frames):
            rgb = self.bridge.imgmsg_to_cv2(img, desired_encoding="rgb8")
            stamp = img.header.stamp
            if fidx == 0:
                import cv2, os
                os.makedirs("/tmp/perception_dbg", exist_ok=True)
                cv2.imwrite(f"/tmp/perception_dbg/{req.scan_id}_{req.stop_index}_{fidx}.png", rgb[..., ::-1])
            out = process(rgb, K, self.detector, self.depth, self.cfg)
            t = out["timings_ms"]
            yolo_ms += t.get("yolo_ms", 0); depth_ms += t.get("depth_ms", 0)
            post_ms += t.get("post_ms", 0)
            for o in out["observations"]:
                ob = ObjectObservation()
                ob.stamp = stamp
                ob.class_id = o["class_id"]; ob.class_name = o["class_name"]
                ob.confidence = float(o["confidence"])
                ob.bbox_xyxy = [float(v) for v in o["bbox_xyxy"]]
                ob.truncated = bool(o["truncated"])
                ob.mask_area_px = int(o["mask_area_px"])
                ob.valid_depth_ratio = float(o["valid_depth_ratio"])
                ob.depth_m = float(o["depth_m"]); ob.range_m = float(o["range_m"])
                ob.p_cam = [float(v) for v in o["p_cam"]]
                pw = self._p_world(o["p_cam"], stamp)
                ob.p_world = ([float(v) for v in pw] if pw is not None
                              else [float("nan")] * 3)  # db_node bỏ qua NaN
                ob.yaw_rad = req.yaw_rad
                ob.stop_index = req.stop_index
                ob.frame_idx = fidx
                arr.observations.append(ob)
        timings += [yolo_ms, depth_ms, post_ms]

        resp.success = True
        resp.message = f"{len(arr.observations)} quan sát trên {len(frames)} khung"
        resp.observations = arr
        resp.timings_ms = [float(v) for v in timings]
        self.get_logger().info(
            f"[{req.scan_id}][stop {req.stop_index}] {len(arr.observations)} vật / "
            f"{len(frames)} khung, yolo={yolo_ms:.0f}ms depth={depth_ms:.0f}ms")
        return resp


def main():
    rclpy.init()
    node = PerceptionNode()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    finally:
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
