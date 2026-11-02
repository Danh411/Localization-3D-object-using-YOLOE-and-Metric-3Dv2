"""W1-B3: đọc CSV (true_m, est_m, fx_used) và in sai số. Dùng: python tools/ruler_eval.py data/eval/w1_webcam_ruler.csv"""
import csv, sys
import numpy as np
rows = list(csv.DictReader(open(sys.argv[1])))
t = np.array([float(r["true_m"]) for r in rows]); e = np.array([float(r["est_m"]) for r in rows])
rel = (e - t) / t
print(f"n={len(t)}  AbsRel={np.mean(np.abs(rel)):.3f}  bias={np.mean(rel):+.3f}  (dương = ước lượng xa hơn thực tế)")
for lo, hi in [(0, 1), (1, 2), (2, 3), (3, 6)]:
    m = (t >= lo) & (t < hi)
    if m.any(): print(f"  {lo}-{hi} m: n={m.sum()} bias={rel[m].mean():+.3f}")
