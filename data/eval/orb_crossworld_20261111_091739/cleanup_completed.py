"""Terminate only orphaned ROS/Gazebo processes belonging to one completed scan."""
import json
import os
from pathlib import Path
import signal
import sys
import time

root=Path(__file__).resolve().parent
room=sys.argv[1]
assert room in {"aws","tiffany"}
scope=root/room
assert "status: SUCCEEDED" in (scope/"action.log").read_text()
assert (scope/"experiment_summary.json").is_file()
prefix=str(scope)+"/"
matched=[]
for proc in Path("/proc").iterdir():
    if not proc.name.isdigit() or int(proc.name)==os.getpid():
        continue
    try:
        args=proc.joinpath("cmdline").read_bytes().decode().strip("\x00").split("\x00")
    except (FileNotFoundError,ProcessLookupError,PermissionError,UnicodeDecodeError):
        continue
    if not args:
        continue
    if args[0] not in {"/usr/bin/python3", "/mnt/d/loc3d_ws/.venv/bin/python",
                       "/opt/ros/jazzy/lib/ros_gz_bridge/parameter_bridge"}:
        continue
    if any(arg.startswith(prefix) for arg in args[1:]):
        matched.append({"pid":int(proc.name),"args":args})
for item in matched:
    try:os.kill(item["pid"],signal.SIGTERM)
    except ProcessLookupError:pass
time.sleep(2)
for item in matched:
    if Path(f"/proc/{item['pid']}").exists():
        try:os.kill(item["pid"],signal.SIGKILL)
        except ProcessLookupError:pass
(root/(room+"_cleanup.json")).write_text(json.dumps(matched,indent=2)+"\n")
print(f"Cleaned {len(matched)} processes scoped to completed {room}",flush=True)
