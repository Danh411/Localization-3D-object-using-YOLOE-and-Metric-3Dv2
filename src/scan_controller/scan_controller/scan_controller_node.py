"""RunScan action server — điều phối lần quét 360° (mục 5.5).

Luồng mỗi điểm dừng: /pan_cmd -> chờ |yaw_thực - yaw_lệnh| < 0.5° -> chờ
settle_time_s -> gọi /perception/capture -> publish /db/observations -> điểm kế.
Quá timeout_per_stop_s thì ghi lỗi, bỏ điểm dừng, tiếp tục.

N = ceil(360 / step_deg); yaw điểm k = yaw_start + k*step_deg (spec A5).
Thuần điều phối; suy luận ở perception_node, ghi DB ở object_db_node.
"""
from __future__ import annotations

import math
import time

import rclpy
from rclpy.action import ActionServer, GoalResponse, CancelResponse
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from rclpy.callback_groups import ReentrantCallbackGroup

from sensor_msgs.msg import JointState
from std_msgs.msg import Float64
from scan_interfaces.action import RunScan
from scan_interfaces.srv import Capture, FinalizeScan
from scan_interfaces.msg import ObjectObservationArray


class ScanController(Node):
    def __init__(self):
        super().__init__("scan_controller")
        self.declare_parameter("step_deg", 45.0)
        self.declare_parameter("settle_time_s", 1.5)
        self.declare_parameter("frames_per_stop", 3)
        self.declare_parameter("timeout_per_stop_s", 60.0)
        self.declare_parameter("yaw_start_deg", 0.0)
        self.declare_parameter("settle_tol_deg", 0.5)
        self.declare_parameter("scan_id_prefix", "scan")

        self.yaw = None
        cb = ReentrantCallbackGroup()
        self.create_subscription(JointState, "/joint_states", self._on_joint, 50,
                                 callback_group=cb)
        self.pan_pub = self.create_publisher(Float64, "/pan_cmd", 10)
        self.obs_pub = self.create_publisher(ObjectObservationArray, "/db/observations", 10)
        self.capture_cli = self.create_client(Capture, "/perception/capture",
                                              callback_group=cb)
        self.finalize_cli = self.create_client(FinalizeScan, "/db/finalize_scan",
                                               callback_group=cb)
        self._server = ActionServer(
            self, RunScan, "/scan/run",
            execute_callback=self._execute,
            goal_callback=lambda goal: GoalResponse.ACCEPT,
            cancel_callback=lambda req: CancelResponse.ACCEPT,
            callback_group=cb)
        self.get_logger().info("scan_controller sẵn sàng (/scan/run)")

    def _on_joint(self, m: JointState):
        if "pan_joint" in m.name:
            self.yaw = m.position[m.name.index("pan_joint")]

    @staticmethod
    def _wrap(a):
        return (a + math.pi) % (2 * math.pi) - math.pi

    def _wait_yaw(self, target, tol, timeout):
        # joint_states callback tự cập nhật self.yaw ở thread executor khác;
        # ở đây chỉ chờ, không spin lại (tránh deadlock).
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            if self.yaw is not None and abs(self._wrap(self.yaw - target)) < tol:
                return True
            time.sleep(0.05)
        return False

    @staticmethod
    def _wait_future(fut, timeout):
        t0 = time.monotonic()
        while not fut.done() and time.monotonic() - t0 < timeout:
            time.sleep(0.02)
        return fut.done()

    def _execute(self, goal_handle):
        g = goal_handle.request
        step = float(g.step_deg) if g.step_deg > 0 else float(self.get_parameter("step_deg").value)
        fps = int(g.frames_per_stop) or int(self.get_parameter("frames_per_stop").value)
        settle = float(g.settle_time_s) if g.settle_time_s >= 0 else float(self.get_parameter("settle_time_s").value)
        timeout = float(self.get_parameter("timeout_per_stop_s").value)
        yaw_start = math.radians(float(self.get_parameter("yaw_start_deg").value))
        tol = math.radians(float(self.get_parameter("settle_tol_deg").value))
        n_stops = max(1, math.ceil(360.0 / step))
        scan_id = f"{self.get_parameter('scan_id_prefix').value}_{int(time.time())}"
        self.get_logger().info(f"[{scan_id}] bắt đầu: {n_stops} điểm dừng, step={step}°")

        t_start = time.monotonic()
        skipped = []
        for k in range(n_stops):
            if goal_handle.is_cancel_requested:
                goal_handle.canceled()
                self.get_logger().warn(f"[{scan_id}] bị hủy ở điểm {k}")
                return RunScan.Result(scan_id=scan_id, n_objects=0,
                                      duration_s=time.monotonic() - t_start)
            yaw_cmd = yaw_start + math.radians(k * step)
            # gửi /pan_cmd, chờ ổn định
            self.pan_pub.publish(Float64(data=yaw_cmd))
            if not self._wait_yaw(yaw_cmd, tol, timeout):
                self.get_logger().warn(f"[{scan_id}] điểm {k} quá hạn settle (yaw={math.degrees(yaw_cmd):.0f}°) -> bỏ")
                skipped.append(k)
                continue
            time.sleep(settle)

            fb = RunScan.Feedback(stop_index=k, n_stops=n_stops, yaw_rad=float(yaw_cmd))
            goal_handle.publish_feedback(fb)

            # gọi Capture
            req = Capture.Request(scan_id=scan_id, stop_index=k,
                                  yaw_rad=float(yaw_cmd), n_frames=fps)
            if not self.capture_cli.wait_for_service(timeout_sec=timeout):
                self.get_logger().warn(f"[{scan_id}] capture service không sẵn sàng ở điểm {k} -> bỏ")
                skipped.append(k)
                continue
            fut = self.capture_cli.call_async(req)
            self._wait_future(fut, timeout)
            if not fut.done() or not fut.result() or not fut.result().success:
                self.get_logger().warn(f"[{scan_id}] capture thất bại ở điểm {k} -> bỏ")
                skipped.append(k)
                continue
            obs_arr = fut.result().observations
            self.obs_pub.publish(obs_arr)
            self.get_logger().info(
                f"[{scan_id}][stop {k}] yaw={math.degrees(yaw_cmd):.0f}° "
                f"{len(obs_arr.observations)} quan sát")

        # kết thúc: yêu cầu DB hợp nhất + chốt trạng thái
        n_objects = 0
        if self.finalize_cli.wait_for_service(timeout_sec=5.0):
            freq = FinalizeScan.Request(scan_id=scan_id)
            fut = self.finalize_cli.call_async(freq)
            self._wait_future(fut, 15.0)
            if fut.done() and fut.result() and fut.result().success:
                n_objects = int(fut.result().confirmed)
        goal_handle.succeed()
        dur = time.monotonic() - t_start
        self.get_logger().info(
            f"[{scan_id}] xong {n_stops} điểm trong {dur:.1f}s; bỏ {len(skipped)} điểm {skipped}; "
            f"objects={n_objects}")
        return RunScan.Result(scan_id=scan_id,
                              n_objects=n_objects,
                              duration_s=float(dur))


def main():
    rclpy.init()
    node = ScanController()
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
