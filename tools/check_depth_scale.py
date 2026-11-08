#!/usr/bin/env python3
"""Kiểm tra nhanh THANG ĐO độ sâu của Metric3D trên ảnh mô phỏng stop0_f0 (pan = 0).
Sự thật đã đo bằng GT Gazebo (W2-A5): ở hàng giữa ảnh, độ sâu tới tường x=5 là
   tâm (u=640) 2.958 m | trái (u=100) 2.941 m | phải (u=1180) 2.954 m   (z-depth, cả ba ~2.95).
Chạy:  python3 tools/check_depth_scale.py [--sizes 336x448,616x1064] [--fp16]
Trả lời ngay: fx đang dùng, hệ số nhân, độ sâu ước lượng và tỉ lệ so với GT. Tỉ lệ ~1.0 là đúng."""
import argparse, os, sys
import cv2, numpy as np, torch, yaml
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "src", "perception"))
from perception.core.geometry import intrinsics_from_hfov
from perception.core.depth import Metric3DDepth
ap = argparse.ArgumentParser(); ap.add_argument("--image", default="data/w2_images/stop0_f0.png")
ap.add_argument("--sizes", default="336x448,616x1064"); ap.add_argument("--fp16", action="store_true"); a = ap.parse_args()
cfg = yaml.safe_load(open(os.path.join(ROOT, "config/default.yaml")))
bgr = cv2.imread(a.image); assert bgr is not None, f"không đọc được {a.image}"
rgb = bgr[..., ::-1].copy(); h, w = rgb.shape[:2]
fx = intrinsics_from_hfov(w, h, cfg["camera"]["hfov_deg"])[0]
GT = {"tam": (640, 2.958), "trai": (100, 2.941), "phai": (1180, 2.954)}
print(f"ảnh {w}x{h}  hfov={cfg['camera']['hfov_deg']}  fx={fx:.2f} (kỳ vọng 914.01 nếu 1280x720, hfov 70)")
print(f"torch {torch.__version__}  cuda={torch.cuda.is_available()}  fp16={a.fp16}")
for s in a.sizes.split(","):
    hw = tuple(int(x) for x in s.lower().split("x"))
    m = Metric3DDepth("cuda:0" if torch.cuda.is_available() else "cpu", hw, a.fp16)
    d = m.estimate(rgb, fx)
    print(f"\n--- depth input {hw}: scale={m.last['scale']:.5f}  fx_r={m.last['fx_r']:.2f}  hệ số nhân={m.last['factor']:.4f}")
    print(f"    toàn ảnh: finite={np.isfinite(d).mean():.3f}  min={np.nanmin(d):.2f}  p50={np.nanmedian(d):.2f}  max={np.nanmax(d):.2f}")
    for k, (u, g) in GT.items():
        v = float(np.median(d[355:366, u - 5:u + 6]))
        print(f"    {k:5s} u={u:4d}: ước lượng {v:5.2f} m | GT {g:.3f} m | tỉ lệ {v/g:.2f}")
    del m; torch.cuda.empty_cache()
