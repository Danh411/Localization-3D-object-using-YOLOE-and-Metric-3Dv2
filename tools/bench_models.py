#!/usr/bin/env python3
"""W1-B2: p50/p95 và VRAM đỉnh cho YOLOE và Metric3D-small trên 1 ảnh mẫu (50 lần, bỏ 5 lần đầu).
  python3 tools/bench_models.py --name metric3d --depth-size 616x1064
  python3 tools/bench_models.py --name yoloe
Mỗi mô hình chạy TRONG TIẾN TRÌNH RIÊNG để VRAM đỉnh không lẫn vào nhau."""
import argparse, csv, os, sys, time
import cv2, numpy as np, torch, yaml
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "src", "perception"))
from perception.core.geometry import intrinsics_from_hfov
ap = argparse.ArgumentParser(); ap.add_argument("--name", required=True, choices=["yoloe", "metric3d"])
ap.add_argument("--image", default="data/w2_images/stop0_f0.png"); ap.add_argument("--n", type=int, default=50)
ap.add_argument("--warmup", type=int, default=5); ap.add_argument("--depth-size", default="616x1064")
ap.add_argument("--fp16", action="store_true"); ap.add_argument("--out", default="data/eval/w1_baseline.csv"); a = ap.parse_args()
cfg = yaml.safe_load(open(os.path.join(ROOT, "config/default.yaml"))); classes = yaml.safe_load(open(os.path.join(ROOT, "config/classes.yaml")))["classes"]
rgb = cv2.imread(a.image)[..., ::-1].copy(); h, w = rgb.shape[:2]; fx = intrinsics_from_hfov(w, h, cfg["camera"]["hfov_deg"])[0]
dev = "cuda:0" if torch.cuda.is_available() else "cpu"
if a.name == "yoloe":
    from perception.core.yolo import YoloeDetector
    m = YoloeDetector(classes, "yoloe-11s-seg.pt", cfg["yoloe"]["conf"], cfg["yoloe"]["iou"], cfg["yoloe"]["imgsz"], dev); fn = lambda: m.detect(rgb); tag = f"imgsz{cfg['yoloe']['imgsz']}"
else:
    from perception.core.depth import Metric3DDepth
    hw = tuple(int(x) for x in a.depth_size.split("x")); m = Metric3DDepth(dev, hw, a.fp16); fn = lambda: m.estimate(rgb, fx); tag = f"{hw[0]}x{hw[1]}{'_fp16' if a.fp16 else ''}"
torch.cuda.reset_peak_memory_stats() if dev != "cpu" else None
ts = []
for i in range(a.n + a.warmup):
    if dev != "cpu": torch.cuda.synchronize()
    t = time.perf_counter(); fn()
    if dev != "cpu": torch.cuda.synchronize()
    if i >= a.warmup: ts.append((time.perf_counter() - t) * 1e3)
vram = torch.cuda.max_memory_allocated() / 2**20 if dev != "cpu" else 0
new = not os.path.exists(a.out); os.makedirs(os.path.dirname(a.out), exist_ok=True)
with open(a.out, "a", newline="") as f:
    wr = csv.writer(f)
    if new: wr.writerow(["model", "config", "p50_ms", "p95_ms", "vram_peak_mib", "image_wh"])
    wr.writerow([a.name, tag, f"{np.percentile(ts,50):.1f}", f"{np.percentile(ts,95):.1f}", f"{vram:.0f}", f"{w}x{h}"])
print(a.name, tag, f"p50 {np.percentile(ts,50):.1f} ms  p95 {np.percentile(ts,95):.1f} ms  VRAM đỉnh {vram:.0f} MiB")
