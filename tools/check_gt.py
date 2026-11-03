#!/usr/bin/env python3
"""W2-A2: so pose vật trong Gazebo với config/gt_objects.yaml (dung sai 1 cm). Cần Gazebo đang chạy room.sdf.
Chạy:  python3 tools/check_gt.py"""
import re, subprocess, yaml
txt = subprocess.run(["gz", "topic", "-e", "-t", "/world/room/pose/info", "-n", "1"], capture_output=True, text=True, timeout=30).stdout
poses = {}
for blk in re.findall(r"pose \{(.*?)\n\}", txt, re.S):
    n = re.search(r'name: "([^"]+)"', blk); p = re.search(r"position \{(.*?)\}", blk, re.S)
    if n and p:
        g = lambda k: float((re.search(k + r": ([-\d.e+]+)", p.group(1)) or [0, 0])[1])
        poses[n.group(1)] = (g("x"), g("y"), g("z"))
bad = 0
for o in yaml.safe_load(open("config/gt_objects.yaml"))["objects"]:
    p = poses.get(o["model_name"])
    if p is None: print("THIẾU", o["model_name"]); bad += 1; continue
    d = max(abs(p[0]-o["x"]), abs(p[1]-o["y"]), abs(p[2]-o["z"]))
    print(f"{o['model_name']:12s} sai lệch max {d*100:.2f} cm", "OK" if d < 0.01 else "LỆCH"); bad += d >= 0.01
print("KẾT QUẢ:", "ĐẠT" if bad == 0 else f"{bad} lỗi")
