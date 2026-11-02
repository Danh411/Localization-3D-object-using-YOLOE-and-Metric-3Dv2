"""W1-B2: đo p50/p95 và VRAM đỉnh. Cắm hàm suy luận của bạn vào REGISTRY.
Chạy: python tools/bench_models.py --name yoloe --n 50 --warmup 5 --out data/eval/w1_baseline.csv
"""
import argparse, csv, os, time
import numpy as np

def bench(fn, n=50, warmup=5):
    import torch
    cuda = torch.cuda.is_available()
    if cuda: torch.cuda.reset_peak_memory_stats()
    ts = []
    for i in range(n + warmup):
        if cuda: torch.cuda.synchronize()
        t = time.perf_counter(); fn()
        if cuda: torch.cuda.synchronize()
        if i >= warmup: ts.append((time.perf_counter() - t) * 1000)
    vram = torch.cuda.max_memory_allocated() / 2**20 if cuda else 0.0
    return float(np.percentile(ts, 50)), float(np.percentile(ts, 95)), vram

def make_yoloe():   # TODO: thay bằng code pipeline của bạn
    raise NotImplementedError("điền: load YOLOE, trả về hàm gọi 1 lần trên ảnh mẫu")
def make_metric3d():  # TODO
    raise NotImplementedError("điền: load Metric3D-small, trả về hàm gọi 1 lần")
REGISTRY = {"yoloe": make_yoloe, "metric3d": make_metric3d}

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--name", required=True)
    ap.add_argument("--n", type=int, default=50); ap.add_argument("--warmup", type=int, default=5)
    ap.add_argument("--out", default="data/eval/w1_baseline.csv"); a = ap.parse_args()
    p50, p95, vram = bench(REGISTRY[a.name](), a.n, a.warmup)
    new = not os.path.exists(a.out)
    with open(a.out, "a", newline="") as f:
        w = csv.writer(f)
        if new: w.writerow(["model", "p50_ms", "p95_ms", "vram_peak_mib"])
        w.writerow([a.name, f"{p50:.1f}", f"{p95:.1f}", f"{vram:.0f}"])
    print(a.name, p50, p95, vram)
